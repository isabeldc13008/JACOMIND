"""M4 · Venta cruzada (en uso): recomendaciones, revisión de Ventas, episodios y revisión comercial.

* La publicación llega en sombra (``modelos.cli puntuar --modelo venta_cruzada``), verificada (sello, huellas, contrato y
  coherencia) y separada de los cierres: no cambia la agenda C1 ni los resultados de M1, M2 y M3.
* Solo roles internos con ``venta_cruzada.ver``; el portal externo no recibe puntajes ni recomendaciones.
* Episodio = cliente + producto + ciclo persistido. Cambiar corte, puntaje, posición o versión no crea otro ni reabre uno
  descartado. Una compra posterior del producto lo cierra sin tocar contactos, responsable, resultados ni decisiones.
* Tareas: bandera ``venta_cruzada_tareas`` desactivada por defecto. Solo propuestas ACEPTADAS por Ventas pasan a un
  seguimiento (o añaden su motivo a uno abierto); los candidatos experimentales quedan fuera de la cola operativa.
* Revisión comercial: pares de la muestra publicada, con revisor, fecha, motivo, evidencia y versión de la propuesta.
"""
from __future__ import annotations

from pathlib import Path

from contratos.validar import leer_publicacion_sombra

from .base import BaseDatos, ErrorApi, ahora, auditar, bandera, dumps, loads
from .publicacion import cierre_activo
from .tareas import CERRADOS, registrar_evento
from .estado_modelos import EN_USO

MODELO_ID = "venta_cruzada"
BANDERA = "venta_cruzada_tareas"
TIPO_TAREA = "venta_cruzada"
PRIORIDAD = 9
ACCIONES = {"aceptar": "aceptada", "aplazar": "aplazada", "descartar": "descartada", "revisar": "en_revision"}
ESTADOS_REVISION = ("pertinente", "ya_cubierto", "incompatible", "sin_necesidad", "informacion_insuficiente")
NOTA = ("Recomendación para revisión de Ventas: no es una oferta ni una tarea, no cambia la agenda, "
        "y una compra posterior no prueba que la recomendación la causara.")
ORIGEN = {"modelo": "modelo de IA (puntaje de ranking)", "popularidad": "popularidad filtrada", "coocurrencia": "coocurrencia filtrada",
          "popularidad_sin_soporte": "popularidad (el modelo no tiene soporte para este producto)"}


def importar_sombra(db: BaseDatos, directorio: str | Path, actor: str) -> dict:
    errores, man, tablas = leer_publicacion_sombra(directorio)
    if errores:
        from .monitoreo import registrar_integridad
        registrar_integridad(db, MODELO_ID, errores, str(directorio))
        raise ErrorApi(422, "sombra_invalida", "La publicación en sombra no cumple el contrato", {"errores": errores[:20]})
    if man.get("modelo_id") != MODELO_ID:
        raise ErrorApi(422, "sombra_invalida", f"Se esperaba una publicación de {MODELO_ID}")
    sid = f"{MODELO_ID}:{man['corte']}:{man['sello'][:12]}"
    with db.transaccion() as con:
        previo = con.execute("SELECT id, activa FROM sombra_publicaciones WHERE sello = ?", (man["sello"],)).fetchone()
        if previo:
            return {"sombra_id": previo["id"], "ya_importada": True, "activa": bool(previo["activa"])}
        actual = con.execute("SELECT corte FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()
        activar = actual is None or man["corte"] >= actual["corte"]  # una publicación antigua no desplaza a la reciente
        if activar:
            con.execute("UPDATE sombra_publicaciones SET activa = 0 WHERE modelo_id = ?", (MODELO_ID,))
        con.execute("""INSERT INTO sombra_publicaciones (id, modelo_id, corte, version_modelo, artefacto_huella, sello, estado_experimento,
                       manifiesto_json, importada_en, importada_por, activa) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, MODELO_ID, man["corte"], man["modelo"]["version"], man["modelo"]["artefacto_huella"], man["sello"],
                     man["estado_experimento"], dumps(man), ahora(), actor, int(activar)))
        con.executemany("INSERT INTO sombra_recomendaciones (sombra_id, cliente_id, producto_id, posicion, datos_json) VALUES (?,?,?,?,?)",
                        [(sid, f["cliente_id"], f["producto_id"], f["posicion"], dumps(f)) for f in tablas["recomendaciones_productos"]])
        con.executemany("INSERT INTO sombra_cobertura_recomendaciones (sombra_id, cliente_id, datos_json) VALUES (?,?,?)",
                        [(sid, c["cliente_id"], dumps(c)) for c in tablas["cobertura_recomendaciones"]])
        if tablas.get("muestra_revision"):
            con.execute("INSERT INTO sombra_muestras_revision (sombra_id, datos_json) VALUES (?,?)", (sid, dumps(tablas["muestra_revision"])))
        auditar(con, actor, "sombra.importar", sid, "ok" if activar else "importada_sin_activar", None,
                {"recomendaciones": len(tablas["recomendaciones_productos"]), "activa": activar})
    from .monitoreo_modelos import tras_importar
    return tras_importar(db, {"sombra_id": sid, "ya_importada": False, "activa": activar, "recomendaciones": len(tablas["recomendaciones_productos"])}, actor)


def sombra_activa(con) -> dict | None:
    r = con.execute("SELECT * FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["manifiesto"] = loads(d.pop("manifiesto_json"))
    return d


def _recs(con, sid: str, cliente_id: str | None = None) -> list[dict]:
    sql, args = "SELECT datos_json FROM sombra_recomendaciones WHERE sombra_id = ?", [sid]
    if cliente_id:
        sql += " AND cliente_id = ?"; args.append(cliente_id)
    filas = [loads(r[0]) for r in con.execute(sql, args)]
    return sorted(filas, key=lambda f: (f["cliente_id"], f["posicion"]))  # posiciones ya validadas contra el ranking al importar


def _cobertura(con, sid: str, cliente_id: str | None = None) -> dict[str, dict]:
    sql, args = "SELECT datos_json FROM sombra_cobertura_recomendaciones WHERE sombra_id = ?", [sid]
    if cliente_id:
        sql += " AND cliente_id = ?"; args.append(cliente_id)
    return {c["cliente_id"]: c for c in (loads(r[0]) for r in con.execute(sql, args))}


def _episodio_vigente(con, cliente_id: str, producto_id: str):
    return con.execute("SELECT * FROM episodios_venta_cruzada WHERE cliente_id = ? AND producto_id = ? ORDER BY ciclo DESC LIMIT 1",
                       (cliente_id, producto_id)).fetchone()


def _item(con, f: dict) -> dict:
    e = _episodio_vigente(con, f["cliente_id"], f["producto_id"])
    return {k: f.get(k) for k in ("cliente_id", "producto_id", "producto_nombre", "posicion", "origen_recomendacion", "estado_compatibilidad",
                                  "motivos", "soporte", "definicion_soporte", "version_modelo", "corte")} | {
        "origen_texto": ORIGEN.get(f["origen_recomendacion"], f["origen_recomendacion"]),
        "episodio": {"episodio_id": e["episodio_id"], "estado": e["estado"], "motivo": e["motivo"], "tarea_id": e["tarea_id"], "ciclo": e["ciclo"]} if e else None}


def lista(con, filtro: str | None = None) -> dict:
    s = sombra_activa(con)
    if not s:
        return {"estado": "sin_sombra", "experimental": False, "items": [], "nota": NOTA, "mensaje": "No hay una publicación del modelo de venta cruzada importada."}
    cob = _cobertura(con, s["id"])
    recs = _recs(con, s["id"])
    items = [_item(con, f) for f in recs if not filtro or f["estado_compatibilidad"] == filtro]
    sin = [{"cliente_id": c["cliente_id"], "estado": c["estado"], "motivo": c["motivo"]} for c in cob.values() if c["estado"] != "con_recomendaciones"]
    conteo: dict = {}
    for c in cob.values():
        conteo[c["estado"]] = conteo.get(c["estado"], 0) + 1
    m = s["manifiesto"]
    return {"estado": "ok", "experimental": False, "nota": NOTA, "items": items, "sin_recomendacion": sorted(sin, key=lambda x: x["cliente_id"]),
            "conteos": conteo, "compatibilidad_pendiente": sum(f["estado_compatibilidad"] == "pendiente_revision" for f in recs),
            "sombra": {"sombra_id": s["id"], "corte": s["corte"], "version": s["version_modelo"], "estado_experimento": EN_USO,
                       "sistema_publicado": (m.get("modelo") or {}).get("sistema_publicado"), "decision": (m.get("modelo") or {}).get("decision"),
                       "versiones": m.get("versiones"), "operativa": True},
            "tareas_automaticas": bandera(con, BANDERA, False),
            "separacion": "Venta cruzada propone productos NO adquiridos; la recompra y la renovación siguen en la agenda C1 y no cambian."}


def para_ficha(con, cliente_id: str) -> dict | None:
    s = sombra_activa(con)
    if not s:
        return None
    cob = _cobertura(con, s["id"], cliente_id).get(cliente_id)
    return {"experimental": False, "corte": s["corte"], "estado_experimento": EN_USO, "nota": NOTA,
            "items": [_item(con, f) for f in _recs(con, s["id"], cliente_id)],
            "cobertura": {"estado": cob["estado"], "motivo": cob["motivo"], "n_candidatos": cob["n_candidatos"]} if cob else None}


def decidir(db: BaseDatos, usuario, cliente_id: str, producto_id: str, accion: str, motivo: str) -> dict:
    """Aceptar, aplazar, descartar o marcar en revisión una propuesta. Un episodio descartado no se reabre."""
    if accion not in ACCIONES:
        raise ErrorApi(400, "accion_invalida", f"Acción no admitida ({', '.join(ACCIONES)})")
    if not str(motivo or "").strip():
        raise ErrorApi(400, "motivo_obligatorio", "Indica el motivo de la decisión")
    with db.transaccion() as con:
        s = sombra_activa(con)
        f = next((x for x in _recs(con, s["id"], cliente_id) if x["producto_id"] == producto_id), None) if s else None
        if f is None:
            raise ErrorApi(404, "sin_propuesta", "No hay una propuesta vigente de ese producto para el cliente")
        e = _episodio_vigente(con, cliente_id, producto_id)
        if e and e["estado"] in ("descartada", "cerrada_compra"):
            raise ErrorApi(409, "episodio_cerrado", f"La propuesta está {e['estado']} en este ciclo; no se reabre")
        evid = {"corte": f["corte"], "posicion": f["posicion"], "version": f["version_modelo"], "origen": f["origen_recomendacion"]}
        nuevo = ACCIONES[accion]
        if e is None:
            eid = f"venta_cruzada:{cliente_id}:{producto_id}:1"
            con.execute("""INSERT INTO episodios_venta_cruzada (episodio_id, cliente_id, producto_id, ciclo, estado, motivo, actor, abierto_en_corte,
                           sombra_apertura, version_propuesta, ultima_evidencia_json, creado_en, actualizado_en) VALUES (?,?,?,1,?,?,?,?,?,?,?,?,?)""",
                        (eid, cliente_id, producto_id, nuevo, motivo, usuario.id, f["corte"], s["id"], f["version_modelo"], dumps(evid), ahora(), ahora()))
        else:
            eid = e["episodio_id"]
            con.execute("UPDATE episodios_venta_cruzada SET estado = ?, motivo = ?, actor = ?, ultima_evidencia_json = ?, actualizado_en = ? WHERE episodio_id = ?",
                        (nuevo, motivo, usuario.id, dumps(evid), ahora(), eid))
        registrar_evento(con, f"venta_cruzada_{nuevo}", usuario.id, None, clave=f"vc:{eid}:{nuevo}:{ahora()}", cliente_id=cliente_id,
                         datos={"episodio": eid, "producto_id": producto_id, "motivo": motivo, **evid})
        auditar(con, usuario.id, "venta_cruzada.decidir", eid, "ok", None, {"accion": accion})
    return {"episodio_id": eid, "estado": nuevo}


def sincronizar(db: BaseDatos, actor: str = "sistema") -> dict:
    """Cierra episodios por compra y, solo con la bandera, crea o comparte seguimientos de las propuestas ACEPTADAS."""
    with db.transaccion() as con:
        s = sombra_activa(con)
        if not s:
            raise ErrorApi(409, "sin_sombra", "No hay una publicación en sombra de venta cruzada importada")
        cob = _cobertura(con, s["id"])
        res = {"cerrados_compra": 0, "activada": bandera(con, BANDERA, False), "tareas_nuevas": 0, "compartidas": 0, "ignorados_evidencia_anterior": 0}
        for e in con.execute("SELECT * FROM episodios_venta_cruzada WHERE estado NOT IN ('descartada', 'cerrada_compra')").fetchall():
            if s["corte"] < e["abierto_en_corte"]:  # evidencia anterior a la apertura: no toca el episodio
                res["ignorados_evidencia_anterior"] += 1
                continue
            c = cob.get(e["cliente_id"])
            comprado = c and any(x["producto_id"] == e["producto_id"] and x["motivo"] == "ya_comprado" for x in c.get("exclusiones", []))
            if comprado:
                con.execute("UPDATE episodios_venta_cruzada SET estado = 'cerrada_compra', cerrado_en_corte = ?, actualizado_en = ? WHERE episodio_id = ?",
                            (s["corte"], ahora(), e["episodio_id"]))
                t = con.execute("SELECT * FROM tareas WHERE id = ?", (e["tarea_id"],)).fetchone() if e["tarea_id"] else None
                registrar_evento(con, "compra_posterior_observada", "sistema", t, clave=f"vc:cerrado:{e['episodio_id']}", cliente_id=e["cliente_id"],
                                 resultado="compra_posterior_observada", datos={"episodio": e["episodio_id"], "producto_id": e["producto_id"],
                                                                                "nota": "Observación, no atribución: la tarea y sus resultados humanos no se modifican."})
                res["cerrados_compra"] += 1
        if not res["activada"]:
            res["mensaje"] = "Las tareas de venta cruzada están desactivadas (bandera venta_cruzada_tareas): no se creó ningún seguimiento."
            return res
        for e in con.execute("SELECT * FROM episodios_venta_cruzada WHERE estado = 'aceptada' AND tarea_id IS NULL").fetchall():
            motivo = f"Venta cruzada: ofrecer {e['producto_id']} (propuesta aceptada por Ventas)"
            tarea = con.execute(f"""SELECT * FROM tareas WHERE cliente_id = ? AND estado NOT IN ({",".join("?" * len(CERRADOS))}) ORDER BY prioridad, id LIMIT 1""",
                                (e["cliente_id"], *sorted(CERRADOS))).fetchone()
            if tarea:  # se conserva su estado, responsable y resultados; solo se añade el motivo
                motivos = loads(tarea["motivos_json"])
                if motivo not in motivos:
                    con.execute("UPDATE tareas SET motivos_json = ?, actualizada_en = ?, version = version + 1 WHERE id = ?", (dumps(motivos + [motivo]), ahora(), tarea["id"]))
                tid, comp = tarea["id"], 1
                res["compartidas"] += 1
            else:
                cur = con.execute("""INSERT INTO tareas (episodio_id, oportunidad_id, cliente_id, tipo, motivos_json, evidencia_json, prioridad, probabilidad,
                                     fecha_revision, estado, cierre_origen, cierre_ultimo, creada_en, actualizada_en) VALUES (?,?,?,?,?,?,?,?,?, 'abierta', ?, ?, ?, ?)""",
                                  (e["episodio_id"], f"OP-{e['episodio_id']}", e["cliente_id"], TIPO_TAREA, dumps([motivo]), e["ultima_evidencia_json"], PRIORIDAD, None,
                                   None, s["id"], s["id"], ahora(), ahora()))
                tid, comp = cur.lastrowid, 0
                res["tareas_nuevas"] += 1
            con.execute("UPDATE episodios_venta_cruzada SET tarea_id = ?, tarea_compartida = ?, actualizado_en = ? WHERE episodio_id = ?", (tid, comp, ahora(), e["episodio_id"]))
        auditar(con, actor, "venta_cruzada.sincronizar", s["id"], "ok", None, res)
    return res


# Revisión comercial -------------------------------------------------------------------------------------------------------
def revision(con) -> dict:
    s = sombra_activa(con)
    if not s:
        return {"estado": "sin_sombra", "pares": [], "resumen": None}
    r = con.execute("SELECT datos_json FROM sombra_muestras_revision WHERE sombra_id = ?", (s["id"],)).fetchone()
    muestra = loads(r[0]) if r else {"pares": []}
    ultimas = {}
    for x in con.execute("SELECT * FROM revisiones_venta_cruzada WHERE sombra_id = ? ORDER BY id", (s["id"],)):
        ultimas[(x["cliente_id"], x["producto_id"])] = dict(x)
    pares = [p | {"revision": ultimas.get((p["cliente_id"], p["producto_id"]))} for p in muestra["pares"]]
    total = len(pares)
    revisados = [p for p in pares if p["revision"]]
    cuenta = {e: sum(p["revision"]["estado_revision"] == e for p in revisados) for e in ESTADOS_REVISION}
    evaluables = len(revisados) - cuenta["informacion_insuficiente"]
    return {"estado": "ok", "corte": s["corte"], "criterio": {k: muestra.get(k) for k in ("semilla", "universo", "criterio", "tamano_objetivo")}, "pares": pares,
            "resumen": {"total_muestra": total, "revisados": len(revisados), "pendientes": total - len(revisados), "por_estado": cuenta,
                        "evaluables": evaluables, "pertinencia_entre_evaluables": cuenta["pertinente"] / evaluables if evaluables else None,
                        "proporcion_informacion_insuficiente": cuenta["informacion_insuficiente"] / len(revisados) if revisados else None,
                        "meta": 0.8, "nota": "Solo revisiones humanas registradas; los pendientes siguen en el denominador total."}}


def registrar_revision(db: BaseDatos, usuario, cliente_id: str, producto_id: str, estado: str, motivo: str, evidencia: str | None) -> dict:
    if estado not in ESTADOS_REVISION:
        raise ErrorApi(400, "estado_invalido", f"Estado de revisión no admitido ({', '.join(ESTADOS_REVISION)})")
    if not str(motivo or "").strip():
        raise ErrorApi(400, "motivo_obligatorio", "Indica el motivo de la revisión")
    with db.transaccion() as con:
        s = sombra_activa(con)
        r = con.execute("SELECT datos_json FROM sombra_muestras_revision WHERE sombra_id = ?", (s["id"],)).fetchone() if s else None
        par = next((p for p in (loads(r[0])["pares"] if r else []) if p["cliente_id"] == cliente_id and p["producto_id"] == producto_id), None)
        if par is None:
            raise ErrorApi(404, "fuera_de_muestra", "El par no está en la muestra de revisión vigente")
        con.execute("""INSERT INTO revisiones_venta_cruzada (sombra_id, cliente_id, producto_id, version_propuesta, estado_revision, revisor, fecha, motivo, evidencia)
                       VALUES (?,?,?,?,?,?,?,?,?)""", (s["id"], cliente_id, producto_id, par["version_propuesta"], estado, usuario.id, ahora(), motivo, evidencia))
        auditar(con, usuario.id, "venta_cruzada.revisar", f"{cliente_id}:{producto_id}", "ok", None, {"estado": estado})
    from .monitoreo_modelos import observar_revision
    observar_revision(db, MODELO_ID)  # grupo D: revisión comercial (la observación anterior queda enlazada)
    return {"registrada": True, "estado": estado}


def episodios(con, cliente_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM episodios_venta_cruzada", []
    if cliente_id:
        sql += " WHERE cliente_id = ?"; args.append(cliente_id)
    return [dict(r) for r in con.execute(sql + " ORDER BY creado_en, episodio_id", args)]
