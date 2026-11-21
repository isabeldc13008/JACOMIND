"""Atención asistida: clasificación (C4), enrutamiento y borradores con aprobación (B10)."""
from __future__ import annotations

import importlib
import os
import re

from contratos.esquema import validar as validar_esquema
from contratos.validar import cargar_esquema

from . import documentos, llm
from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, loads

UMBRAL_CONFIANZA = float(os.environ.get("JACOMIND_UMBRAL_PQRS", "0.6"))
ESQUEMA_CLASIF = cargar_esquema("asistencia.v1.schema.json")["$defs"]["clasificacion_pqrs"]
# Ruta del clasificador de A (C4). Formato "modulo:funcion"; la función recibe el texto
# y devuelve {"categoria", "confianza", "version", "revisar", "motivo"?, "responsable"?}.
CLASIFICADOR_A = os.environ.get("JACOMIND_CLASIFICADOR", "modelos.clasificador_pqrs:clasificar")
AREAS = {"reclamo": "Facturación y cartera", "queja": "Calidad del servicio", "peticion": "Atención general",
         "sugerencia": "Mejora continua"}
PALABRAS = {
    "reclamo": ["cobro", "cobraron", "factura", "facturacion", "reembolso", "devolucion", "garantia", "dano", "danado",
                "incumpl", "error en", "doble cobro", "no funciona", "falla"],
    "queja": ["mal servicio", "demora", "demoro", "molest", "inconform", "trato", "grosero", "nadie responde",
              "no responden", "tarde", "pesimo"],
    "sugerencia": ["sugiero", "sugerencia", "propongo", "seria bueno", "seria util", "mejorar", "recomiendo", "ojala"],
    "peticion": ["solicito", "informacion", "quisiera", "certificado", "requiero", "consulta", "como puedo", "renovar",
                 "cotizacion", "beneficio", "necesito"],
}


def _simulado(texto: str) -> dict:
    t = documentos.normalizar(texto)
    puntajes = {c: sum(t.count(p) for p in ps) for c, ps in PALABRAS.items()}
    total = sum(puntajes.values())
    if not t.strip() or total == 0:
        return {"categoria": "peticion", "confianza": 0.0, "version": "simulado-reglas-1", "revisar": True,
                "motivo": "Sin señales reconocibles; requiere revisión humana", "responsable": None}
    orden = sorted(puntajes.items(), key=lambda kv: (-kv[1], kv[0]))
    cat, top = orden[0]
    conf = round(top / total * min(1.0, 0.5 + 0.25 * top), 3)
    motivo = None
    if orden[1][1] == top:
        motivo = "Dos intenciones con el mismo peso"
    elif conf < UMBRAL_CONFIANZA:
        motivo = "Confianza baja"
    return {"categoria": cat, "confianza": conf, "version": "simulado-reglas-1",
            "revisar": conf < UMBRAL_CONFIANZA or motivo is not None, "motivo": motivo, "responsable": AREAS[cat]}


def _cargar_clasificador_a():
    if os.environ.get("JACOMIND_CLASIFICADOR_DESACTIVADO") == "1":
        return None
    modulo, _, funcion = CLASIFICADOR_A.partition(":")
    try:
        return getattr(importlib.import_module(modulo), funcion)
    except (ImportError, AttributeError):
        return None


def clasificar(texto: str) -> dict:
    """Usa el clasificador de A si existe y cumple C4; si falla, el simulado. Nunca bloquea el alta."""
    fn = _cargar_clasificador_a()
    if fn is not None:
        try:
            r = fn(texto)
            errores = validar_esquema(r, ESQUEMA_CLASIF)
            if not errores:
                r = dict(r)
                r["revisar"] = bool(r["revisar"] or r["confianza"] < UMBRAL_CONFIANZA)
                r.setdefault("responsable", AREAS.get(r["categoria"]))
                return r
            return _simulado(texto) | {"revisar": True, "motivo": f"Salida del clasificador fuera de contrato: {errores[0]}"}
        except Exception as e:
            return _simulado(texto) | {"revisar": True, "motivo": f"Clasificador no disponible: {e}"}
    return _simulado(texto)


def guardar_sugerencia(con, pqrs_id: int, s: dict) -> None:
    con.execute("""INSERT INTO pqrs_sugerencias (pqrs_id, categoria, responsable, confianza, version, revisar, motivo, creado_en)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (pqrs_id, s.get("categoria"), s.get("responsable"), s.get("confianza"), s.get("version"),
                 int(bool(s.get("revisar"))), s.get("motivo"), ahora()))


def reclasificar(db: BaseDatos, usuario, radicado: str) -> dict:
    """Reprocesa la sugerencia sin tocar la categoría revisada por el operador."""
    with db.conexion() as con:
        r = con.execute("SELECT * FROM pqrs WHERE radicado = ?", (radicado,)).fetchone()
    if not r:
        raise ErrorApi(404, "pqrs_no_encontrada", "Caso no encontrado")
    s = clasificar(f"{r['asunto']}. {r['descripcion']}")
    with db.transaccion() as con:
        guardar_sugerencia(con, r["id"], s)
        if r["categoria_revisada"] is None:
            con.execute("UPDATE pqrs SET categoria_propuesta = ?, requiere_revision = ? WHERE id = ?",
                        (None if s["revisar"] else s["categoria"], int(s["revisar"]), r["id"]))
        auditar(con, usuario.id, "pqrs.reclasificar", radicado, "ok", None, s)
    return s


def generar_borrador(db: BaseDatos, usuario, radicado: str) -> dict:
    with db.conexion() as con:
        r = con.execute("SELECT * FROM pqrs WHERE radicado = ?", (radicado,)).fetchone()
        if not r:
            raise ErrorApi(404, "pqrs_no_encontrada", "Caso no encontrado")
        org = con.execute("SELECT nombre FROM organizaciones WHERE id = ?", (r["organizacion_id"],)).fetchone()[0]
        alcance = documentos.alcance_de(usuario, organizacion_caso=r["organizacion_id"])
        frs = documentos.buscar(con, alcance, f"{r['asunto']} {r['descripcion']}", k=3)
    frs = [f for f in frs if f["score"] >= documentos.SCORE_MINIMO and f["cobertura"] >= documentos.COBERTURA_MINIMA / 2]
    categoria = r["categoria_revisada"] or r["categoria_propuesta"] or "sin categoría revisada"
    hechos = (f"Caso {r['radicado']} de {org}, radicado el {r['creado_en'][:10]}, categoría {categoria}, "
              f"estado {r['estado']}. Asunto: {r['asunto']}.")
    if not frs:
        texto = (f"Estimado cliente de {org}: recibimos su caso {r['radicado']} sobre «{r['asunto']}». "
                 "[REVISIÓN REQUERIDA: no se encontró una disposición vigente que respalde la respuesta; "
                 "complete las condiciones aplicables antes de aprobar.]")
        estado, motivo, fuentes = "requiere_revision", "Falta evidencia documental vigente", []
    else:
        q = documentos.tokens(r["descripcion"])
        partes = [f"«{documentos._oraciones(f['texto'], q, 2)}» ({f['titulo']}, versión {f['version']}, {f['localizador']})" for f in frs[:2]]
        texto = (f"Estimado cliente de {org}: en relación con su caso {r['radicado']} sobre «{r['asunto']}», "
                 f"le informamos lo que establece la documentación vigente: {' '.join(partes)}. "
                 "Si necesita más información, responda a este caso.")
        estado, motivo = "pendiente", None
        fuentes = [documentos.cita(f) for f in frs[:2]]
    contexto = " ".join(f["texto"] for f in frs[:2])
    texto, version = llm.redactar(texto, hechos + " " + contexto)
    with db.transaccion() as con:
        cur = con.execute("""INSERT INTO pqrs_borradores (pqrs_id, texto, fuentes_json, version_generador, version_caso, estado,
                             motivo_revision, creado_por, creado_en) VALUES (?,?,?,?,?,?,?,?,?)""",
                          (r["id"], texto, dumps(fuentes), f"{documentos.VERSION_RAG}+{version}", r["version"], estado, motivo,
                           usuario.id, ahora()))
        auditar(con, usuario.id, "pqrs.borrador", radicado, "ok", None, {"borrador": cur.lastrowid, "estado": estado})
        b = con.execute("SELECT * FROM pqrs_borradores WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(b, fuentes=fuentes)


def _fuentes_vigentes(con, fuentes: list[dict]) -> bool:
    for f in fuentes:
        ok = con.execute("SELECT 1 FROM documentos WHERE id = ? AND version = ? AND estado = 'vigente'",
                         (f["documento_id"], f["version"])).fetchone()
        if not ok:
            return False
    return True


def editar_borrador(db: BaseDatos, usuario, borrador_id: int, texto: str) -> dict:
    with db.transaccion() as con:
        cur = con.execute("UPDATE pqrs_borradores SET texto = ? WHERE id = ? AND estado IN ('pendiente','requiere_revision')",
                          (texto.strip(), borrador_id))
        if cur.rowcount != 1:
            raise ErrorApi(409, "borrador_no_editable", "El borrador ya fue aprobado o descartado")
        auditar(con, usuario.id, "pqrs.borrador_editar", str(borrador_id), "ok")
        b = con.execute("SELECT * FROM pqrs_borradores WHERE id = ?", (borrador_id,)).fetchone()
        return dict(b, fuentes=loads(b["fuentes_json"]))


def aprobar_borrador(db: BaseDatos, usuario, borrador_id: int, confirmar_revision: bool = False) -> dict:
    """Aprobación explícita: publica al cliente una sola vez y registra quién aprobó."""
    from . import pqrs as modulo_pqrs
    with db.transaccion() as con:
        b = con.execute("SELECT * FROM pqrs_borradores WHERE id = ?", (borrador_id,)).fetchone()
        if not b:
            raise ErrorApi(404, "borrador_no_encontrado", "Borrador no encontrado")
        r = con.execute("SELECT * FROM pqrs WHERE id = ?", (b["pqrs_id"],)).fetchone()
        if b["estado"] == "aprobado":
            return {"radicado": r["radicado"], "publicado": True, "repetida": True, "aprobado_por": b["aprobado_por"]}
        if b["estado"] == "descartado":
            raise ErrorApi(409, "borrador_descartado", "El borrador fue descartado")
        fuentes = loads(b["fuentes_json"])
        if b["version_caso"] != r["version"] and b["estado"] == "pendiente":
            con.execute("UPDATE pqrs_borradores SET estado = 'requiere_revision', motivo_revision = ? WHERE id = ?",
                        ("El caso cambió después de generar el borrador", borrador_id))
            raise ErrorApi(409, "borrador_desactualizado", "El caso cambió; revisa el borrador antes de aprobar")
        if not _fuentes_vigentes(con, fuentes):
            con.execute("UPDATE pqrs_borradores SET estado = 'requiere_revision', motivo_revision = ? WHERE id = ?",
                        ("Una fuente citada ya no está vigente", borrador_id))
            raise ErrorApi(409, "fuente_retirada", "Una fuente citada se retiró; genera un nuevo borrador")
        if b["estado"] == "requiere_revision" and not confirmar_revision:
            raise ErrorApi(409, "requiere_revision", f"Borrador marcado para revisión: {b['motivo_revision']}. Confirma la revisión para aprobar.")
        if "[REVISIÓN REQUERIDA" in b["texto"]:
            raise ErrorApi(409, "requiere_revision", "Completa las condiciones marcadas antes de aprobar")
        cur = con.execute("""UPDATE pqrs_borradores SET estado = 'aprobado', aprobado_por = ?, aprobado_en = ?
                             WHERE id = ? AND estado IN ('pendiente','requiere_revision')""", (usuario.id, ahora(), borrador_id))
        if cur.rowcount != 1:
            raise ErrorApi(409, "conflicto", "Otra sesión aprobó o modificó el borrador")
        if r["estado"] == "recibido":
            modulo_pqrs._transicion(con, r, usuario.id, "en_gestion", "iniciar_gestion")
            r = con.execute("SELECT * FROM pqrs WHERE id = ?", (r["id"],)).fetchone()
        elif r["estado"] == "cerrado":
            raise ErrorApi(409, "caso_cerrado", "El caso está cerrado; reábrelo antes de responder")
        modulo_pqrs._transicion(con, r, usuario.id, "respondido", "publicar_respuesta", None,
                                {"respuesta_publicada": b["texto"], "respuesta_aprobada_por": usuario.id})
        con.execute("UPDATE pqrs_borradores SET estado = 'descartado' WHERE pqrs_id = ? AND id <> ? AND estado IN ('pendiente','requiere_revision')",
                    (r["id"], borrador_id))
        auditar(con, usuario.id, "pqrs.aprobar_borrador", r["radicado"], "ok", None, {"borrador": borrador_id})
        return {"radicado": r["radicado"], "publicado": True, "repetida": False, "aprobado_por": usuario.id}


def bandeja_revision(con) -> list[dict]:
    casos = [dict(r) for r in con.execute("SELECT radicado, asunto, estado, categoria_propuesta, creado_en FROM pqrs WHERE requiere_revision = 1 ORDER BY creado_en")]
    borr = [dict(r) for r in con.execute("""SELECT b.id, p.radicado, b.estado, b.motivo_revision, b.creado_en FROM pqrs_borradores b
                                            JOIN pqrs p ON p.id = b.pqrs_id WHERE b.estado IN ('pendiente','requiere_revision') ORDER BY b.id""")]
    return {"casos_sin_clasificar": casos, "borradores": borr}


# Asistente del portal: enruta por intención dentro del contexto autenticado -------
_RE_RADICADO = re.compile(r"PQRS-\d{8}-\d{5}", re.I)


def asistente_portal(con, usuario, pregunta: str) -> dict:
    from . import beneficios, pqrs as modulo_pqrs
    t = documentos.normalizar(pregunta)
    m = _RE_RADICADO.search(pregunta)
    if m or re.search(r"\b(mi caso|mis casos|estado de mi|radicado)\b", t):
        if m:
            try:
                c = modulo_pqrs.detalle(con, usuario, m.group(0).upper())
            except ErrorApi:
                return {"estado": "no_encontrado", "herramienta": "pqrs", "parametros": {"radicado": m.group(0).upper()},
                        "evidencia": {"fuentes": []}, "texto": "No encontré ese radicado entre los casos de tu empresa."}
            texto = f"Tu caso {c['radicado']} («{c['asunto']}») está en estado {c['estado'].replace('_', ' ')}."
            if c.get("respuesta_publicada"):
                texto += f" Respuesta publicada: {c['respuesta_publicada']}"
            return {"estado": "ok", "herramienta": "pqrs", "parametros": {"radicado": c["radicado"]},
                    "resultado": {"estado": c["estado"]}, "evidencia": {"detalle": f"#/pqrs/{c['radicado']}", "fuentes": []}, "texto": texto}
        casos = modulo_pqrs.listar(con, usuario) if usuario.externo else []
        texto = ("No tienes casos registrados." if not casos else
                 "Tus casos: " + "; ".join(f"{c['radicado']} ({c['estado'].replace('_', ' ')})" for c in casos[:5]) + ".")
        return {"estado": "ok" if casos else "sin_datos", "herramienta": "pqrs", "parametros": {}, "resultado": casos[:5],
                "evidencia": {"fuentes": []}, "texto": texto}
    if "beneficio" in t or "descuento" in t or "fidelizacion" in t:
        lista = beneficios.portal(con, usuario) if usuario.externo else []
        if not lista:
            texto = "No hay beneficios vigentes publicados para tu empresa en este momento."
        else:
            texto = "Beneficios disponibles: " + "; ".join(
                f"{b['titulo']} ({'consulta tu elegibilidad con Atención' if b['elegibilidad'] == 'revision' else 'vigente hasta ' + (b['vigencia_hasta'] or 'nuevo aviso')})"
                for b in lista) + ". Para solicitarlo, abre una PQRS de tipo petición."
        return {"estado": "ok" if lista else "sin_datos", "herramienta": "beneficios", "parametros": {}, "resultado": lista,
                "evidencia": {"fuentes": [{"beneficio_id": b["id"], "version": b["version"], "fuente": b["fuente"]} for b in lista]},
                "texto": texto}
    r = documentos.responder(con, documentos.alcance_de(usuario), pregunta)
    return {"estado": r["estado"], "herramienta": "documentos", "parametros": {"pregunta": pregunta}, "resultado": None,
            "evidencia": {"fuentes": r["fuentes"]}, "texto": r["texto"]}
