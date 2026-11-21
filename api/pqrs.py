"""Registro, consulta y resolución de PQRS (B04).

Flujo propuesto: recibido → en_gestion → respondido → cerrado, con reapertura
(respondido/cerrado → en_gestion). Cada transición valida el estado previo y la
versión del registro, y queda en la bitácora con fecha y actor.
"""
from __future__ import annotations

import hashlib
import re
import statistics
from datetime import datetime

from .base import BaseDatos, ErrorApi, ahora, auditar, hoy, loads
from . import atencion

CATEGORIAS = ["peticion", "queja", "reclamo", "sugerencia"]
TRANSICIONES = {("recibido", "en_gestion"), ("en_gestion", "respondido"), ("respondido", "cerrado"),
                ("respondido", "en_gestion"), ("cerrado", "en_gestion")}
CAMPOS_PUBLICOS = ("radicado", "asunto", "descripcion", "estado", "creado_en", "respuesta_publicada", "respondido_en", "cerrado_en")


def _publico(r) -> dict:
    return {k: r[k] for k in CAMPOS_PUBLICOS}


def crear(db: BaseDatos, usuario, asunto: str, descripcion: str, clave: str | None) -> dict:
    asunto, descripcion = (asunto or "").strip(), (descripcion or "").strip()
    if not asunto or not descripcion:
        raise ErrorApi(400, "datos_incompletos", "Asunto y descripción son obligatorios")
    if len(descripcion) > 5000:
        raise ErrorApi(400, "texto_largo", "La descripción supera 5.000 caracteres")
    if clave:
        with db.conexion() as con:
            r = con.execute("SELECT * FROM pqrs WHERE organizacion_id = ? AND solicitante_id = ? AND clave_idempotencia = ?",
                            (usuario.organizacion_id, usuario.id, clave)).fetchone()
            if r:
                return _publico(r) | {"repetida": True}
    sugerencia = atencion.clasificar(f"{asunto}. {descripcion}")
    with db.transaccion() as con:
        if clave:
            r = con.execute("SELECT * FROM pqrs WHERE organizacion_id = ? AND solicitante_id = ? AND clave_idempotencia = ?",
                            (usuario.organizacion_id, usuario.id, clave)).fetchone()
            if r:
                return _publico(r) | {"repetida": True}
        n = con.execute("SELECT coalesce(max(id), 0) + 1 FROM pqrs").fetchone()[0]
        radicado = f"PQRS-{hoy():%Y%m%d}-{n:05d}"
        cur = con.execute(
            """INSERT INTO pqrs (radicado, organizacion_id, solicitante_id, clave_idempotencia, creado_en, asunto, descripcion,
               categoria_propuesta, estado, requiere_revision) VALUES (?,?,?,?,?,?,?,?, 'recibido', ?)""",
            (radicado, usuario.organizacion_id, usuario.id, clave, ahora(), asunto, descripcion,
             None if sugerencia["revisar"] else sugerencia["categoria"], int(sugerencia["revisar"])))
        pid = cur.lastrowid
        atencion.guardar_sugerencia(con, pid, sugerencia)
        con.execute("INSERT INTO pqrs_bitacora (pqrs_id, ts, actor, accion, de_estado, a_estado, interna) VALUES (?,?,?,?,?,?,0)",
                    (pid, ahora(), usuario.id, "radicar", None, "recibido"))
        auditar(con, usuario.id, "pqrs.crear", radicado, "ok")
        return _publico(con.execute("SELECT * FROM pqrs WHERE id = ?", (pid,)).fetchone()) | {"repetida": False}


def _cargar(con, usuario, radicado: str):
    r = con.execute("SELECT * FROM pqrs WHERE radicado = ?", (radicado,)).fetchone()
    # Para externos, un caso de otra empresa es indistinguible de uno inexistente.
    if not r or (usuario.externo and r["organizacion_id"] != usuario.organizacion_id):
        raise ErrorApi(404, "pqrs_no_encontrada", "No existe un caso con ese radicado para tu empresa")
    return r


def listar(con, usuario, estado=None, revision=None, q=None) -> list[dict]:
    where, args = [], []
    if usuario.externo:
        where.append("organizacion_id = ?"); args.append(usuario.organizacion_id)
    if estado:
        where.append("estado = ?"); args.append(estado)
    if revision in ("1", "true", True):
        where.append("requiere_revision = 1")
    if q:
        where.append("(radicado LIKE ? OR asunto LIKE ?)"); args += [f"%{q}%", f"%{q}%"]
    sql = "SELECT * FROM pqrs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY creado_en DESC, id DESC LIMIT 500"
    rows = con.execute(sql, args).fetchall()
    if usuario.externo:
        return [_publico(r) for r in rows]
    hoy_d = hoy()
    salida = []
    for r in rows:
        d = dict(r)
        d["antiguedad_dias"] = (hoy_d - datetime.fromisoformat(r["creado_en"]).date()).days
        d["vencido"] = bool(r["plazo_dias"]) and r["estado"] in ("recibido", "en_gestion") and d["antiguedad_dias"] > r["plazo_dias"]
        d["categoria"] = r["categoria_revisada"] or r["categoria_propuesta"]
        salida.append(d)
    return salida


def detalle(con, usuario, radicado: str) -> dict:
    r = _cargar(con, usuario, radicado)
    if usuario.externo:
        bit = [dict(b) for b in con.execute(
            "SELECT ts, accion, a_estado FROM pqrs_bitacora WHERE pqrs_id = ? AND interna = 0 "
            "AND accion NOT IN ('categorizar', 'reasignar') ORDER BY id", (r["id"],))]
        # Última actualización pública: el último cambio visible para la empresa.
        return _publico(r) | {"historial": bit, "actualizado_en": bit[-1]["ts"] if bit else r["creado_en"]}
    d = dict(r)
    d["bitacora"] = [dict(b) for b in con.execute("SELECT * FROM pqrs_bitacora WHERE pqrs_id = ? ORDER BY id", (r["id"],))]
    d["sugerencias"] = [dict(s) for s in con.execute("SELECT * FROM pqrs_sugerencias WHERE pqrs_id = ? ORDER BY id", (r["id"],))]
    d["borradores"] = [dict(b, fuentes=loads(b["fuentes_json"])) for b in con.execute(
        "SELECT * FROM pqrs_borradores WHERE pqrs_id = ? ORDER BY id DESC", (r["id"],))]
    d["organizacion"] = con.execute("SELECT nombre FROM organizaciones WHERE id = ?", (r["organizacion_id"],)).fetchone()[0]
    return d


def _transicion(con, r, actor: str, destino: str, accion: str, nota=None, extra: dict | None = None, publica=True):
    if (r["estado"], destino) not in TRANSICIONES:
        raise ErrorApi(409, "transicion_invalida", f"No se puede pasar de {r['estado']} a {destino}")
    cambios = {"estado": destino, **(extra or {})}
    if destino == "en_gestion" and not r["primera_gestion_en"]:
        cambios["primera_gestion_en"] = ahora()
    if destino == "respondido":
        cambios["respondido_en"] = ahora()
    if destino == "cerrado":
        cambios["cerrado_en"] = ahora()
    sets = ", ".join(f"{k} = ?" for k in cambios)
    cur = con.execute(f"UPDATE pqrs SET {sets}, version = version + 1 WHERE id = ? AND version = ? AND estado = ?",
                      (*cambios.values(), r["id"], r["version"], r["estado"]))
    if cur.rowcount != 1:
        raise ErrorApi(409, "conflicto_version", "El caso cambió en otra sesión; recarga antes de continuar")
    con.execute("INSERT INTO pqrs_bitacora (pqrs_id, ts, actor, accion, de_estado, a_estado, nota, interna) VALUES (?,?,?,?,?,?,?,?)",
                (r["id"], ahora(), actor, accion, r["estado"], destino, nota, 0 if publica else 1))


def gestionar(db: BaseDatos, usuario, radicado: str, accion: str, cuerpo: dict) -> dict:
    with db.transaccion() as con:
        r = _cargar(con, usuario, radicado)
        if int(cuerpo.get("version", -1)) != r["version"]:
            raise ErrorApi(409, "conflicto_version", "Otro operador modificó este caso; recarga para ver los cambios",
                           {"version_actual": r["version"], "estado_actual": r["estado"]})
        if accion == "asignar":
            resp = cuerpo.get("responsable") or usuario.id
            if not con.execute("SELECT 1 FROM pertenencias WHERE identidad_id = ? AND rol = 'atencion'", (resp,)).fetchone():
                raise ErrorApi(400, "responsable_invalido", "El responsable debe pertenecer a Atención")
            if r["estado"] == "recibido":
                _transicion(con, r, usuario.id, "en_gestion", "asignar", cuerpo.get("nota"), {"responsable_id": resp})
            else:
                con.execute("UPDATE pqrs SET responsable_id = ?, version = version + 1 WHERE id = ?", (resp, r["id"]))
                con.execute("INSERT INTO pqrs_bitacora (pqrs_id, ts, actor, accion, de_estado, a_estado, nota) VALUES (?,?,?,?,?,?,?)",
                            (r["id"], ahora(), usuario.id, "reasignar", r["estado"], r["estado"], resp))
        elif accion == "categorizar":
            cat = cuerpo.get("categoria")
            if cat not in CATEGORIAS:
                raise ErrorApi(400, "categoria_invalida", f"Categoría debe ser una de {CATEGORIAS}")
            con.execute("""UPDATE pqrs SET categoria_revisada = ?, fecha_revision = ?, requiere_revision = 0,
                           version = version + 1 WHERE id = ?""", (cat, ahora(), r["id"]))
            con.execute("INSERT INTO pqrs_bitacora (pqrs_id, ts, actor, accion, de_estado, a_estado, nota) VALUES (?,?,?,?,?,?,?)",
                        (r["id"], ahora(), usuario.id, "categorizar", r["estado"], r["estado"], cat))
        elif accion == "responder":
            texto = (cuerpo.get("respuesta") or "").strip()
            if not texto:
                raise ErrorApi(400, "falta_respuesta", "Escribe la respuesta que verá el cliente")
            if r["estado"] == "recibido":
                _transicion(con, r, usuario.id, "en_gestion", "iniciar_gestion")
                r = con.execute("SELECT * FROM pqrs WHERE id = ?", (r["id"],)).fetchone()
            _transicion(con, r, usuario.id, "respondido", "responder", None,
                        {"respuesta_publicada": texto, "respuesta_aprobada_por": usuario.id})
        elif accion == "cerrar":
            _transicion(con, r, usuario.id, "cerrado", "cerrar", cuerpo.get("nota"))
        elif accion == "reabrir":
            if not (cuerpo.get("nota") or "").strip():
                raise ErrorApi(400, "falta_motivo", "Reabrir requiere un motivo")
            _transicion(con, r, usuario.id, "en_gestion", "reabrir", cuerpo["nota"])
        elif accion == "plazo":
            dias = cuerpo.get("plazo_dias")
            con.execute("UPDATE pqrs SET plazo_dias = ?, version = version + 1 WHERE id = ?", (dias, r["id"]))
        elif accion == "autorizar_uso":
            con.execute("UPDATE pqrs SET uso_autorizado = ?, version = version + 1 WHERE id = ?", (int(bool(cuerpo.get("autorizado"))), r["id"]))
        else:
            raise ErrorApi(400, "accion_desconocida", f"Acción no soportada: {accion}")
        auditar(con, usuario.id, f"pqrs.{accion}", radicado, "ok")
        return detalle(con, usuario, radicado)


def indicadores(con) -> dict:
    hoy_d = hoy()
    por_estado = {e: 0 for e in ("recibido", "en_gestion", "respondido", "cerrado")}
    antiguedad: dict[str, list[int]] = {e: [] for e in por_estado}
    primera: dict[str, list[float]] = {}
    resolucion: dict[str, list[float]] = {}
    abiertos_cat: dict[str, int] = {}
    for r in con.execute("SELECT * FROM pqrs"):
        por_estado[r["estado"]] += 1
        antiguedad[r["estado"]].append((hoy_d - datetime.fromisoformat(r["creado_en"]).date()).days)
        cat = r["categoria_revisada"] or r["categoria_propuesta"] or "sin_categoria"
        ini = datetime.fromisoformat(r["creado_en"])
        if r["primera_gestion_en"]:
            primera.setdefault(cat, []).append((datetime.fromisoformat(r["primera_gestion_en"]) - ini).total_seconds() / 3600)
        if r["respondido_en"]:
            resolucion.setdefault(cat, []).append((datetime.fromisoformat(r["respondido_en"]) - ini).total_seconds() / 3600)
        if r["estado"] in ("recibido", "en_gestion"):
            abiertos_cat[cat] = abiertos_cat.get(cat, 0) + 1
    med = lambda xs: round(statistics.median(xs), 2) if xs else None  # noqa: E731
    return {"por_estado": por_estado,
            "pendientes": por_estado["recibido"] + por_estado["en_gestion"],
            "en_revision": con.execute("SELECT count(*) FROM pqrs WHERE requiere_revision = 1").fetchone()[0],
            "antiguedad_mediana_dias": {e: med(v) for e, v in antiguedad.items()},
            "horas_primera_gestion_mediana": {k: med(v) for k, v in primera.items()},
            "horas_resolucion_mediana": {k: med(v) for k, v in resolucion.items()},
            "casos_medidos_primera_gestion": {k: len(v) for k, v in primera.items()},
            "casos_medidos_resolucion": {k: len(v) for k, v in resolucion.items()},
            "horas_primera_gestion_mediana_total": med([x for v in primera.values() for x in v]),
            "horas_resolucion_mediana_total": med([x for v in resolucion.values() for x in v]),
            "definicion_mediana": "Valor central de los tiempos medidos: la mitad de los casos tardó menos y la otra mitad más.",
            "abiertos_por_categoria": abiertos_cat,
            "nota": "Los vencimientos solo se calculan para casos con plazo aprobado."}


_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_RE_NUM = re.compile(r"\+?\d[\d\s().-]{5,}\d")


def anonimizar(texto: str) -> str:
    texto = _RE_EMAIL.sub("[CORREO]", texto)
    texto = _RE_NUM.sub("[NUMERO]", texto)
    return re.sub(r"PQRS-\d{8}-\d+", "[RADICADO]", texto)


def exportar_anonimizado(con) -> dict:
    eventos = []
    for r in con.execute("SELECT * FROM pqrs WHERE uso_autorizado = 1 AND categoria_revisada IS NOT NULL ORDER BY id"):
        eventos.append({"evento_id": hashlib.sha256(r["radicado"].encode()).hexdigest()[:16], "tipo": "pqrs_revisada",
                        "fecha": r["creado_en"], "actor": "atencion",
                        "empresa": hashlib.sha256(r["organizacion_id"].encode()).hexdigest()[:10],
                        "categoria_revisada": r["categoria_revisada"], "fecha_revision": r["fecha_revision"],
                        "texto": anonimizar(f"{r['asunto']}. {r['descripcion']}")})
    return {"version": 1, "tipo": "pqrs_anonimizadas", "exportado_en": ahora(), "eventos": eventos}
