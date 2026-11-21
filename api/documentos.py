"""Inventario documental, indexación y respuestas con fuentes (B08).

Recuperación por palabras (BM25) limitada ANTES de puntuar a documentos vigentes
y autorizados para la identidad. El texto recuperado es contenido de referencia:
se cita, nunca se ejecuta como instrucción.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

from .base import DIR_API, BaseDatos, ErrorApi, ahora, auditar, dumps, hoy, loads

STOP = set("""a al algo como con de del el ella ellos en entre es esta este esto fue ha hay la las le les lo los mas me mi
mis muy no nos o para pero por que se si sin sobre su sus te tiene tu un una uno y ya yo cual cuales cuando donde
qué cómo puedo puede pueden debo hacer tengo mi nuestra nuestro nuestros son ser está están cuanto cuantos cuanta
cuantas cual cuales quiero saber""".split())
SCORE_MINIMO = 1.2
COBERTURA_MINIMA = 0.5  # fracción de términos de la pregunta presentes en el fragmento
VERSION_RAG = "bm25-extractivo-1"


def normalizar(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def tokens(t: str) -> list[str]:
    salida = []
    for w in re.findall(r"[a-z0-9]+", normalizar(t)):
        if w in STOP or len(w) < 2:
            continue
        # raíz ligera: plural/feminino simple para mejorar paráfrasis
        for suf in ("ciones", "cion", "es", "s"):
            if len(w) > 5 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        salida.append(w[:6])  # raíz por prefijo: renuevo/renueven, descuento/descuentan
    return salida


def fragmentar(texto: str) -> list[tuple[str, str]]:
    """Divide por páginas (\\f) o secciones Markdown (##) y conserva el localizador."""
    piezas: list[tuple[str, str]] = []
    if "\f" in texto:
        for i, pag in enumerate(texto.split("\f"), start=1):
            if pag.strip():
                piezas.append((f"página {i}", pag.strip()))
    else:
        actual, buf = "inicio", []
        for linea in texto.splitlines():
            m = re.match(r"^#{1,3}\s+(.*)", linea)
            if m:
                if "".join(buf).strip():
                    piezas.append((f"sección «{actual}»", "\n".join(buf).strip()))
                actual, buf = m.group(1).strip(), []
            else:
                buf.append(linea)
        if "".join(buf).strip():
            piezas.append((f"sección «{actual}»", "\n".join(buf).strip()))
    salida = []
    for loc, txt in piezas:
        if len(txt) <= 1200:
            salida.append((loc, txt))
            continue
        parrafos, bloque, k = re.split(r"\n\s*\n", txt), "", 1
        for p in parrafos:
            if len(bloque) + len(p) > 1200 and bloque:
                salida.append((f"{loc} (parte {k})", bloque.strip())); k += 1; bloque = ""
            bloque += p + "\n\n"
        if bloque.strip():
            salida.append((f"{loc} (parte {k})", bloque.strip()))
    return salida


def invalidar_cache(con) -> None:
    con.execute("DELETE FROM consultas_cache")


def importar(db: BaseDatos, actor: str, meta: dict, texto: str) -> dict:
    for campo in ("id", "titulo", "propietario", "vigencia_desde"):
        if not meta.get(campo):
            raise ErrorApi(400, "metadatos_incompletos", f"Falta {campo}")
    roles = meta.get("roles") or ["atencion", "empresa", "ventas", "operaciones", "gerencia", "finanzas"]
    with db.transaccion() as con:
        huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()
        previa = con.execute("SELECT version, huella FROM documentos WHERE id = ? ORDER BY version DESC LIMIT 1", (meta["id"],)).fetchone()
        if previa and previa["huella"] == huella:
            return {"id": meta["id"], "version": previa["version"], "sin_cambios": True}
        version = (previa["version"] + 1) if previa else 1
        con.execute("UPDATE documentos SET estado = 'reemplazado' WHERE id = ? AND estado = 'vigente'", (meta["id"],))
        con.execute("""INSERT INTO documentos (id, version, titulo, tema, propietario, organizacion_id, roles_json, vigencia_desde,
                       vigencia_hasta, precedencia, estado, huella, importado_por, importado_en)
                       VALUES (?,?,?,?,?,?,?,?,?,?, 'vigente', ?, ?, ?)""",
                    (meta["id"], version, meta["titulo"], meta.get("tema"), meta["propietario"], meta.get("organizacion_id"),
                     dumps(sorted(roles)), meta["vigencia_desde"], meta.get("vigencia_hasta"), int(meta.get("precedencia", 0)),
                     huella, actor, ahora()))
        frs = fragmentar(texto)
        con.executemany("INSERT INTO fragmentos (documento_id, version, localizador, texto) VALUES (?,?,?,?)",
                        [(meta["id"], version, loc, txt) for loc, txt in frs])
        invalidar_cache(con)
        _marcar_borradores(con, meta["id"], "Se publicó una nueva versión de una fuente citada")
        auditar(con, actor, "documento.importar", f"{meta['id']} v{version}", "ok", str(version), {"fragmentos": len(frs)})
        return {"id": meta["id"], "version": version, "fragmentos": len(frs), "sin_cambios": False}


def _marcar_borradores(con, doc_id: str, motivo: str) -> None:
    for b in con.execute("SELECT id, fuentes_json FROM pqrs_borradores WHERE estado = 'pendiente'").fetchall():
        if any(f.get("documento_id") == doc_id for f in loads(b["fuentes_json"])):
            con.execute("UPDATE pqrs_borradores SET estado = 'requiere_revision', motivo_revision = ? WHERE id = ?", (motivo, b["id"]))


def retirar(db: BaseDatos, actor: str, doc_id: str) -> dict:
    with db.transaccion() as con:
        cur = con.execute("UPDATE documentos SET estado = 'retirado' WHERE id = ? AND estado = 'vigente'", (doc_id,))
        if cur.rowcount == 0:
            raise ErrorApi(404, "documento_no_vigente", "No hay una versión vigente de ese documento")
        invalidar_cache(con)
        _marcar_borradores(con, doc_id, "Se retiró una fuente citada")
        auditar(con, actor, "documento.retirar", doc_id, "ok")
        return {"id": doc_id, "retirado": True}


def cambiar_permisos(db: BaseDatos, actor: str, doc_id: str, roles: list[str], organizacion_id=None) -> dict:
    with db.transaccion() as con:
        cur = con.execute("UPDATE documentos SET roles_json = ?, organizacion_id = ? WHERE id = ? AND estado = 'vigente'",
                          (dumps(sorted(roles)), organizacion_id, doc_id))
        if cur.rowcount == 0:
            raise ErrorApi(404, "documento_no_vigente", "No hay una versión vigente de ese documento")
        invalidar_cache(con)
        auditar(con, actor, "documento.permisos", doc_id, "ok", None, {"roles": roles, "organizacion_id": organizacion_id})
        return {"id": doc_id, "roles": roles, "organizacion_id": organizacion_id}


def inventario(con) -> list[dict]:
    return [dict(r, roles=loads(r["roles_json"]),
                 fragmentos=con.execute("SELECT count(*) FROM fragmentos WHERE documento_id = ? AND version = ?", (r["id"], r["version"])).fetchone()[0])
            for r in con.execute("SELECT * FROM documentos ORDER BY id, version")]


def _autorizados_sql(alcance: dict) -> tuple[str, list]:
    """Filtro de seguridad: vigentes, en fecha, de la empresa (o generales) y del rol."""
    hoy_s = hoy().isoformat()
    where = ["d.estado = 'vigente'", "d.vigencia_desde <= ?", "(d.vigencia_hasta IS NULL OR d.vigencia_hasta >= ?)"]
    args: list = [hoy_s, hoy_s]
    if alcance["externo"]:
        where.append("(d.organizacion_id IS NULL OR d.organizacion_id = ?)")
        args.append(alcance["organizacion_id"])
    elif alcance.get("organizacion_caso"):
        where.append("(d.organizacion_id IS NULL OR d.organizacion_id = ?)")
        args.append(alcance["organizacion_caso"])
    roles_cond = " OR ".join("d.roles_json LIKE ?" for _ in alcance["roles"]) or "0"
    where.append(f"({roles_cond})")
    args += [f'%"{r}"%' for r in alcance["roles"]]
    return " AND ".join(where), args


def alcance_de(usuario, organizacion_caso=None) -> dict:
    roles = sorted(usuario.roles)
    if organizacion_caso:  # borrador para un cliente: solo lo que ese cliente podría ver
        roles = ["empresa"]
    return {"externo": usuario.externo, "organizacion_id": usuario.organizacion_id, "roles": roles,
            "organizacion_caso": organizacion_caso}


def buscar(con, alcance: dict, consulta: str, k: int = 5) -> list[dict]:
    q = tokens(consulta)
    if not q:
        return []
    w, args = _autorizados_sql(alcance)
    frs = con.execute(f"""SELECT f.id, f.documento_id, f.version, f.localizador, f.texto, d.titulo, d.tema, d.precedencia,
                          d.vigencia_desde, d.vigencia_hasta FROM fragmentos f
                          JOIN documentos d ON d.id = f.documento_id AND d.version = f.version WHERE {w}""", args).fetchall()
    if not frs:
        return []
    docs = [Counter(tokens(f["texto"] + " " + f["titulo"])) for f in frs]
    n = len(docs)
    media = sum(sum(d.values()) for d in docs) / n
    df = Counter(t for d in docs for t in d)
    res = []
    for f, d in zip(frs, docs):
        largo = sum(d.values()) or 1
        s = 0.0
        for t in set(q):
            if t in d:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * d[t] * 2.2 / (d[t] + 1.2 * (0.25 + 0.75 * largo / media))
        if s > 0:
            cobertura = len(set(q) & set(d)) / len(set(q))
            res.append(dict(f) | {"score": round(s, 4), "cobertura": round(cobertura, 3)})
    res.sort(key=lambda x: (-x["score"], x["documento_id"], x["id"]))
    return res[:k]


def _oraciones(texto: str, q: list[str], maximo=2) -> str:
    ors = [o.strip() for o in re.split(r"(?<=[.;:])\s+|\n+", texto) if o.strip()]
    if not ors:
        return texto[:300]
    qs = set(q)
    puntuadas = sorted(ors, key=lambda o: -len(qs & set(tokens(o))))
    elegidas = [o for o in ors if o in puntuadas[:maximo]]
    return " ".join(elegidas)[:600]


def cita(f: dict) -> dict:
    return {"documento_id": f["documento_id"], "version": f["version"], "titulo": f["titulo"], "localizador": f["localizador"],
            "fragmento_id": f["id"], "enlace": f"/api/documentos/{f['documento_id']}/{f['version']}/fragmentos/{f['id']}",
            "vigencia_hasta": f["vigencia_hasta"]}


def responder(con, alcance: dict, pregunta: str, usar_cache: bool = True) -> dict:
    clave = hashlib.sha256(dumps([normalizar(pregunta.strip()), alcance, hoy().isoformat()]).encode()).hexdigest()
    if usar_cache:
        r = con.execute("SELECT respuesta_json FROM consultas_cache WHERE clave = ?", (clave,)).fetchone()
        if r:
            return loads(r[0]) | {"cache": True}
    resultados = buscar(con, alcance, pregunta, k=5)
    q = tokens(pregunta)
    if not resultados or resultados[0]["score"] < SCORE_MINIMO or resultados[0]["cobertura"] < COBERTURA_MINIMA:
        resp = {"estado": "sin_datos", "texto": "No encontré una disposición vigente y autorizada que responda esta pregunta. "
                "Te remito a Atención para revisarla.", "fuentes": [], "remitir_a": "atencion"}
    else:
        top = resultados[0]
        rivales = [r for r in resultados[1:] if r["tema"] and r["tema"] == top["tema"] and r["documento_id"] != top["documento_id"]
                   and r["precedencia"] == top["precedencia"] and r["score"] >= top["score"] * 0.6]
        if rivales:
            otro = rivales[0]
            resp = {"estado": "incertidumbre",
                    "texto": (f"Hay dos disposiciones vigentes sobre «{top['tema']}» sin una precedencia definida: "
                              f"«{_oraciones(top['texto'], q, 1)}» ({top['titulo']} v{top['version']}, {top['localizador']}) y "
                              f"«{_oraciones(otro['texto'], q, 1)}» ({otro['titulo']} v{otro['version']}, {otro['localizador']}). "
                              "No puedo determinar cuál aplica; Atención revisará el caso."),
                    "fuentes": [cita(top), cita(otro)], "remitir_a": "atencion"}
        else:
            resp = {"estado": "ok",
                    "texto": f"Según {top['titulo']} (versión {top['version']}, {top['localizador']}): «{_oraciones(top['texto'], q)}»",
                    "fuentes": [cita(top)] + [cita(r) for r in resultados[1:3] if r["documento_id"] == top["documento_id"]]}
    resp |= {"version": VERSION_RAG, "recuperados": [{"fragmento_id": r["id"], "score": r["score"], "cobertura": r["cobertura"]} for r in resultados]}
    con.execute("INSERT OR REPLACE INTO consultas_cache (clave, respuesta_json, creado_en) VALUES (?,?,?)", (clave, dumps(resp), ahora()))
    return resp | {"cache": False}


def fragmento(con, alcance: dict, doc_id: str, version: int, frag_id: int) -> dict:
    w, args = _autorizados_sql(alcance)
    r = con.execute(f"""SELECT f.*, d.titulo FROM fragmentos f JOIN documentos d ON d.id = f.documento_id AND d.version = f.version
                        WHERE f.id = ? AND f.documento_id = ? AND f.version = ? AND {w}""", [frag_id, doc_id, version] + args).fetchone()
    if not r:
        raise ErrorApi(404, "fragmento_no_disponible", "Fragmento inexistente, retirado o no autorizado")
    return dict(r)


def sembrar(db: BaseDatos) -> None:
    indice = json.loads((DIR_API / "semillas" / "documentos" / "indice.json").read_text(encoding="utf-8"))
    for meta in indice:
        texto = (DIR_API / "semillas" / "documentos" / meta.pop("archivo")).read_text(encoding="utf-8")
        importar(db, "semilla", meta, texto)
