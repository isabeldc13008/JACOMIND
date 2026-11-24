"""Importador de publicaciones C2 (B02.3).

Valida el directorio de A, lo copia a un área temporal, comprueba conteos y
claves y activa el cierre en una sola transacción. Dos publicaciones idénticas
(misma huella) producen una única revisión. Un fallo deja intacto el cierre activo.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from contratos.agenda import ORDEN_ACCION
from contratos.validar import cargar_esquema, leer_json, validar_agenda, validar_publicacion

from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, loads, nuevo_id

TABLAS = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]

# Gancho de prueba: nombre de etapa en la que simular una interrupción.
FALLO_SIMULADO: str | None = None


CAMPOS_VOLATILES = {"generado_en"}


def _sin_volatiles(x):
    """Quita marcas de tiempo de generación: los mismos insumos deben dar la misma huella."""
    if isinstance(x, dict):
        return {k: _sin_volatiles(v) for k, v in x.items() if k not in CAMPOS_VOLATILES}
    if isinstance(x, list):
        return [_sin_volatiles(v) for v in x]
    return x


def _huella(manifiesto: dict, datos: dict) -> str:
    contenido = {"corte": manifiesto["corte"], "origen": manifiesto["origen"],
                 "versiones": manifiesto.get("versiones"),
                 "tablas": _sin_volatiles({k: v for k, v in datos.items() if k != "manifiesto"})}
    return hashlib.sha256(dumps(contenido).encode("utf-8")).hexdigest()


def manifiesto_desde_agenda(agenda: dict, origen_archivo: str = "agenda.json") -> dict:
    """Envuelve un C1 suelto en un manifiesto C2 mínimo (A aún no publica tablas)."""
    return {"version": 1, "tipo": "publicacion_analitica", "cierre_id": f"agenda-{agenda['corte']}",
            "corte": agenda["corte"], "origen": agenda["origen"], "generado_en": agenda.get("generado_en"),
            "huellas_entrada": {origen_archivo: hashlib.sha256(dumps(agenda).encode()).hexdigest()},
            "versiones": {"reglas": None, "modelo_compra": (agenda.get("modelo") or {}).get("version")},
            "tablas": {"agenda": {"archivo": origen_archivo, "filas": len(agenda["clientes"])}}}


def _simular(etapa: str) -> None:
    if FALLO_SIMULADO == etapa:
        raise RuntimeError(f"Interrupción simulada en la etapa '{etapa}'")


def _clave(tabla: str, fila: dict, i: int) -> str:
    campos = TABLAS.get(tabla, {}).get("clave")
    if not campos:
        return f"#{i:06d}"
    return "|".join(str(fila.get(c)) for c in campos)


def publicar(db: BaseDatos, manifiesto: dict, datos: dict, actor: str) -> dict:
    huella = _huella(manifiesto, datos)
    agenda = datos["agenda"]
    token = nuevo_id("stg-")
    try:
        with db.transaccion() as con:
            previo = con.execute("SELECT id, revision FROM cierres WHERE huella = ?", (huella,)).fetchone()
            if previo:
                auditar(con, actor, "cierre.publicar", previo["id"], "sin_cambios", str(previo["revision"]),
                        {"motivo": "publicación idéntica ya existente"})
                return {"cierre_id": previo["id"], "revision": previo["revision"], "ya_publicado": True}
            # 1) Área temporal
            for tabla, contenido in datos.items():
                if tabla == "manifiesto":
                    continue
                filas = contenido["clientes"] if tabla == "agenda" else contenido
                con.executemany(
                    "INSERT INTO stg_filas (token, tabla, clave, cliente_id, datos_json) VALUES (?,?,?,?,?)",
                    [(token, tabla, _clave(tabla, f, i), f.get("cliente_id"), dumps(f)) for i, f in enumerate(filas)])
            _simular("staging")
            # 2) Comprobar conteos frente al manifiesto
            for tabla, decl in manifiesto["tablas"].items():
                n = con.execute("SELECT count(*) FROM stg_filas WHERE token = ? AND tabla = ?", (token, tabla)).fetchone()[0]
                if n != decl["filas"]:
                    raise ErrorApi(422, "conteo_incorrecto", f"{tabla}: {n} filas cargadas, manifiesto declara {decl['filas']}")
            # 3) Registrar el cierre y mover filas
            revision = con.execute("SELECT coalesce(max(revision), 0) + 1 FROM cierres WHERE corte = ?",
                                   (manifiesto["corte"],)).fetchone()[0]
            cierre_id = f"{manifiesto['corte']}-r{revision}"
            meta = dict(manifiesto, cierre_origen=manifiesto["cierre_id"], resumen=agenda["resumen"],
                        modelo=agenda.get("modelo"))
            con.execute("""INSERT INTO cierres (id, corte, revision, huella, version_contrato, origen, manifiesto_json,
                           estado, publicado_por, publicado_en) VALUES (?,?,?,?,?,?,?, 'publicado', ?, ?)""",
                        (cierre_id, manifiesto["corte"], revision, huella, agenda["version"], manifiesto["origen"],
                         dumps(meta), actor, ahora()))
            segmentos = {s["cliente_id"]: s.get("segmento") for s in datos.get("segmentos", [])}
            con.executemany(
                """INSERT INTO an_agenda (cierre_id, cliente_id, accion, orden_accion, prob, frio, frecuente,
                   ingreso_cop, segmento, datos_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [(cierre_id, c["cliente_id"], c["accion"], ORDEN_ACCION[c["accion"]], c["prob_compra_30d"],
                  int(c["frio"]), int(c["frecuente"]), c["ingreso_cop"], c.get("segmento") or segmentos.get(c["cliente_id"]),
                  dumps(c)) for c in agenda["clientes"]])
            con.execute("""INSERT INTO an_filas (cierre_id, tabla, clave, cliente_id, datos_json)
                           SELECT ?, tabla, clave, cliente_id, datos_json FROM stg_filas WHERE token = ? AND tabla <> 'agenda'""",
                        (cierre_id, token))
            _simular("mover")
            n_agenda = con.execute("SELECT count(*) FROM an_agenda WHERE cierre_id = ?", (cierre_id,)).fetchone()[0]
            if n_agenda != len(agenda["clientes"]):
                raise ErrorApi(422, "conteo_incorrecto", "La agenda publicada no conserva el número de clientes")
            ingreso = con.execute("SELECT coalesce(sum(ingreso_cop), 0) FROM an_agenda WHERE cierre_id = ?", (cierre_id,)).fetchone()[0]
            if abs(ingreso - agenda["resumen"]["ingreso_cop"]) > 0.01 * (n_agenda + 1):
                raise ErrorApi(422, "suma_incorrecta", "El ingreso publicado no coincide con el resumen")
            con.execute("DELETE FROM stg_filas WHERE token = ?", (token,))
            # 4) Cambio atómico de cierre activo
            con.execute("UPDATE cierres SET estado = 'reemplazado' WHERE corte = ? AND id <> ?", (manifiesto["corte"], cierre_id))
            _simular("activar")
            con.execute("""INSERT INTO cierre_activo (id, cierre_id, activado_en) VALUES (1, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET cierre_id = excluded.cierre_id, activado_en = excluded.activado_en""",
                        (cierre_id, ahora()))
            auditar(con, actor, "cierre.publicar", cierre_id, "ok", str(revision),
                    {"clientes": n_agenda, "ingreso_cop": ingreso, "huella": huella})
    except Exception as e:
        with db.transaccion() as con:
            con.execute("DELETE FROM stg_filas WHERE token = ?", (token,))
            auditar(con, actor, "cierre.publicar", manifiesto.get("cierre_id"), "fallido", None, {"error": str(e)})
        if isinstance(e, ErrorApi):
            raise
        raise ErrorApi(500, "publicacion_fallida", f"La publicación se interrumpió; se conserva el cierre anterior ({e})") from e
    # Datos operativos: regenerar agenda humana sin tocar decisiones previas.
    from . import tareas
    try:
        tareas.sincronizar(db, cierre_id, actor)
    except Exception as e:  # la publicación ya es válida; se registra el problema
        with db.transaccion() as con:
            auditar(con, actor, "tareas.sincronizar", cierre_id, "fallido", None, {"error": str(e)})
    try:  # monitoreo M1: salud y distribución del cierre publicado (el desempeño madura después)
        from .monitoreo_modelos import observar_cierre
        observar_cierre(db, cierre_id)
    except Exception as e:  # noqa: BLE001
        with db.transaccion() as con:
            auditar(con, actor, "monitoreo.observar", cierre_id, "fallido", None, {"error": str(e)})
    return {"cierre_id": cierre_id, "revision": revision, "ya_publicado": False}


def publicar_ruta(db: BaseDatos, ruta: str | Path, actor: str) -> dict:
    """Publica un directorio C2 o un agenda.json C1 suelto."""
    ruta = Path(ruta)
    if ruta.is_dir():
        res, datos = validar_publicacion(ruta)
        if not res.valido:
            with db.transaccion() as con:
                auditar(con, actor, "cierre.publicar", str(ruta), "rechazado", None, res.como_dict())
            from .monitoreo import registrar_integridad
            registrar_integridad(db, "compra_30d", list(res.errores), str(ruta))
            raise ErrorApi(409 if res.incompatible else 422, "publicacion_invalida",
                           "La publicación no cumple el contrato; se conserva el cierre anterior", res.como_dict())
        return publicar(db, datos["manifiesto"], datos, actor)
    try:
        agenda = leer_json(ruta)
    except FileNotFoundError:
        raise ErrorApi(404, "archivo_ausente", f"No existe {ruta}")
    except json.JSONDecodeError as e:
        raise ErrorApi(422, "json_invalido", str(e))
    res = validar_agenda(agenda)
    if not res.valido:
        with db.transaccion() as con:
            auditar(con, actor, "cierre.publicar", str(ruta), "rechazado", None, res.como_dict())
        raise ErrorApi(409 if res.incompatible else 422, "agenda_invalida",
                       "La agenda no cumple C1; se conserva el cierre anterior", res.como_dict())
    return publicar(db, manifiesto_desde_agenda(agenda, ruta.name), {"agenda": agenda}, actor)


# Lectura de cierres ----------------------------------------------------------
def cierre_activo(con) -> str | None:
    r = con.execute("SELECT cierre_id FROM cierre_activo WHERE id = 1").fetchone()
    return r[0] if r else None


def resolver_cierre(con, cierre: str) -> dict:
    cid = cierre_activo(con) if cierre in ("activo", "", None) else cierre
    if not cid:
        raise ErrorApi(404, "sin_cierre", "Aún no hay un cierre publicado")
    r = con.execute("SELECT * FROM cierres WHERE id = ?", (cid,)).fetchone()
    if not r:
        raise ErrorApi(404, "cierre_desconocido", f"No existe el cierre {cid}")
    d = dict(r)
    d["manifiesto"] = loads(d.pop("manifiesto_json"))
    d["activo"] = cid == cierre_activo(con)
    return d


def listar_cierres(con) -> list[dict]:
    act = cierre_activo(con)
    return [{"id": r["id"], "corte": r["corte"], "revision": r["revision"], "estado": r["estado"],
             "origen": r["origen"], "publicado_en": r["publicado_en"], "publicado_por": r["publicado_por"],
             "activo": r["id"] == act}
            for r in con.execute("SELECT * FROM cierres ORDER BY corte DESC, revision DESC")]


def filas(con, cierre_id: str, tabla: str, cliente_id: str | None = None) -> list[dict]:
    if cliente_id is None:
        cur = con.execute("SELECT datos_json FROM an_filas WHERE cierre_id = ? AND tabla = ? ORDER BY clave", (cierre_id, tabla))
    else:
        cur = con.execute("SELECT datos_json FROM an_filas WHERE cierre_id = ? AND tabla = ? AND cliente_id = ? ORDER BY clave",
                          (cierre_id, tabla, cliente_id))
    return [loads(r[0]) for r in cur]
