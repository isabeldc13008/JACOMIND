"""Catálogo de beneficios versionado y portal empresarial (B06).

Las puntuaciones internas de riesgo nunca se exponen en el portal. La consulta
``portal`` es la única vía autorizada (también la reutiliza el asistente).
"""
from __future__ import annotations

from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, hoy, loads

FLUJO = {"enviar_revision": ("borrador", "revision"), "publicar": ("revision", "publicado"),
         "devolver": ("revision", "borrador"), "retirar": ("publicado", "retirado")}


def _fila(r) -> dict:
    d = dict(r)
    d["criterio"] = loads(d.pop("criterio_json"))
    return d


def guardar(db: BaseDatos, usuario, datos: dict) -> dict:
    """Crea un borrador (nuevo beneficio o nueva versión de uno existente)."""
    for campo in ("id", "titulo", "descripcion", "fuente", "vigencia_desde", "empresa_emisora"):
        if not datos.get(campo):
            raise ErrorApi(400, "datos_incompletos", f"Falta {campo}")
    criterio = datos.get("criterio") or {}
    if not isinstance(criterio, dict):
        raise ErrorApi(400, "criterio_invalido", "El criterio debe ser un objeto")
    with db.transaccion() as con:
        v = con.execute("SELECT coalesce(max(version), 0) + 1 FROM beneficios WHERE id = ?", (datos["id"],)).fetchone()[0]
        con.execute("""INSERT INTO beneficios (id, version, empresa_emisora, titulo, descripcion, fuente, vigencia_desde, vigencia_hasta,
                       criterio_json, politica, como_solicitar, estado, actualizado_por, actualizado_en)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?, 'borrador', ?, ?)""",
                    (datos["id"], v, datos["empresa_emisora"], datos["titulo"], datos["descripcion"], datos["fuente"],
                     datos["vigencia_desde"], datos.get("vigencia_hasta"), dumps(criterio), datos.get("politica"),
                     datos.get("como_solicitar") or "Abre una PQRS de tipo petición indicando el beneficio.", usuario.id, ahora()))
        auditar(con, usuario.id, "beneficio.guardar", f"{datos['id']} v{v}", "ok", str(v), {"politica": datos.get("politica")})
        return _fila(con.execute("SELECT * FROM beneficios WHERE id = ? AND version = ?", (datos["id"], v)).fetchone())


def transicion(db: BaseDatos, usuario, bid: str, version: int, accion: str) -> dict:
    if accion not in FLUJO:
        raise ErrorApi(400, "accion_desconocida", f"Acción no soportada: {accion}")
    if accion in ("publicar", "devolver", "retirar") and not usuario.puede("beneficios.publicar"):
        raise ErrorApi(403, "sin_permiso", "Solo Atención revisa, publica o retira beneficios")
    de, a = FLUJO[accion]
    with db.transaccion() as con:
        cur = con.execute("UPDATE beneficios SET estado = ?, actualizado_por = ?, actualizado_en = ? WHERE id = ? AND version = ? AND estado = ?",
                          (a, usuario.id, ahora(), bid, version, de))
        if cur.rowcount != 1:
            raise ErrorApi(409, "transicion_invalida", f"El beneficio no está en estado {de}")
        if accion == "publicar":  # una sola versión publicada por beneficio
            con.execute("UPDATE beneficios SET estado = 'retirado', actualizado_en = ? WHERE id = ? AND version <> ? AND estado = 'publicado'",
                        (ahora(), bid, version))
        auditar(con, usuario.id, f"beneficio.{accion}", f"{bid} v{version}", "ok", str(version))
        return _fila(con.execute("SELECT * FROM beneficios WHERE id = ? AND version = ?", (bid, version)).fetchone())


def catalogo(con) -> list[dict]:
    return [_fila(r) for r in con.execute("SELECT * FROM beneficios ORDER BY id, version DESC")]


def elegibilidad(criterio: dict, org) -> str | None:
    """'elegible', 'revision' (falta un dato) o None (no aplica / no visible)."""
    orgs = criterio.get("organizaciones")
    if orgs and org["id"] not in orgs:
        return None
    segs = criterio.get("segmentos")
    if segs:
        if not org["segmento"]:
            return "revision"
        if org["segmento"] not in segs:
            return None
    for campo in criterio.get("requiere", []):
        if org[campo] if campo in org.keys() else None:
            continue
        return "revision"
    return "elegible"


def portal(con, usuario, fecha=None) -> list[dict]:
    if not usuario.externo:
        raise ErrorApi(403, "solo_empresas", "El portal de beneficios es para usuarios empresariales")
    org = con.execute("SELECT * FROM organizaciones WHERE id = ?", (usuario.organizacion_id,)).fetchone()
    f = (fecha or hoy()).isoformat()
    salida = []
    for r in con.execute("""SELECT * FROM beneficios WHERE estado = 'publicado' AND vigencia_desde <= ?
                            AND (vigencia_hasta IS NULL OR vigencia_hasta >= ?) ORDER BY titulo, id""", (f, f)):
        b = _fila(r)
        e = elegibilidad(b["criterio"], org)
        if e is None:
            continue
        salida.append({"id": b["id"], "version": b["version"], "titulo": b["titulo"], "descripcion": b["descripcion"],
                       "empresa_emisora": b["empresa_emisora"], "fuente": b["fuente"], "vigencia_desde": b["vigencia_desde"],
                       "vigencia_hasta": b["vigencia_hasta"], "como_solicitar": b["como_solicitar"], "elegibilidad": e})
    return salida


def portal_detalle(con, usuario, bid: str) -> dict:
    for b in portal(con, usuario):  # mismo control que la lista (enlace directo incluido)
        if b["id"] == bid:
            return b
    raise ErrorApi(404, "beneficio_no_disponible", "Beneficio no disponible para tu empresa")


def retencion(con) -> dict:
    filas = con.execute("""SELECT beneficio_id, count(*) seguimientos, sum(estado = 'atendida') atendidos,
                           sum(resultado LIKE '%recuper%' OR resultado = 'resultado_atribuido') recuperaciones
                           FROM tareas WHERE beneficio_id IS NOT NULL GROUP BY beneficio_id""").fetchall()
    elegibles = con.execute("SELECT count(*) FROM tareas WHERE tipo = 'reactivacion'").fetchone()[0]
    return {"elegibles_reactivacion": elegibles, "por_beneficio": [dict(r) for r in filas],
            "nota": "Las recuperaciones son observadas; la ventana de medición se acuerda con Ventas."}


def sembrar(db: BaseDatos, usuario_sistema) -> None:
    ejemplos = [
        {"id": "BEN-RENOV", "empresa_emisora": "Green Services (ficticio)", "titulo": "Descuento por renovación anticipada",
         "descripcion": "8 % sobre el precio de lista al renovar antes del vencimiento.", "fuente": "POL-BENEF v2",
         "vigencia_desde": "2026-01-01", "vigencia_hasta": "2026-12-31", "criterio": {}, "politica": "POL-BENEF v2 §Descuento"},
        {"id": "BEN-SOPORTE", "empresa_emisora": "Green Services (ficticio)", "titulo": "Soporte prioritario",
         "descripcion": "Atención prioritaria para clientes recurrentes.", "fuente": "POL-BENEF v2",
         "vigencia_desde": "2026-01-01", "criterio": {"segmentos": ["Recurrente activo", "Recurrente en pausa"]},
         "politica": "POL-BENEF v2 §Soporte"},
        {"id": "BEN-GARANTIA-B", "empresa_emisora": "Green Services (ficticio)", "titulo": "Garantía extendida de monitoreo",
         "descripcion": "Reemplazo de equipos de monitoreo durante 24 meses.", "fuente": "POL-GARANTIA-B v1",
         "vigencia_desde": "2026-01-01", "criterio": {"organizaciones": ["EMP-B"]}, "politica": "POL-GARANTIA-B"},
        {"id": "BEN-FUTURO", "empresa_emisora": "Green Services (ficticio)", "titulo": "Capacitación anual",
         "descripcion": "Taller anual para usuarios clave.", "fuente": "Borrador de política 2027",
         "vigencia_desde": "2027-01-01", "criterio": {}, "politica": "Pendiente"},
    ]
    for e in ejemplos:
        b = guardar(db, usuario_sistema, e)
        transicion(db, usuario_sistema, b["id"], b["version"], "enviar_revision")
        transicion(db, usuario_sistema, b["id"], b["version"], "publicar")
