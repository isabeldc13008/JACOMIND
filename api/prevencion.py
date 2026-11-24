"""M2 · Prevención de inactividad (experimental): publicación en sombra, consulta interna y episodios.

* La puntuación candidata llega como **publicación de sombra** (``modelos.cli puntuar --modelo inactividad_60d``),
  validada con el contrato y guardada aparte de los cierres: no cambia la agenda C1, ``prob_compra_30d`` ni su orden.
* La consulta solo la ven roles internos con ``prevencion.ver`` (permisos de cartera); el portal externo no la recibe.
* Episodios: identidad ``prevencion:<cliente>:<último día de compra>``, independiente de la versión del modelo. Repetir
  la sincronización no duplica nada; una compra nueva cierra el episodio; otro episodio exige volver a cumplir la
  política (estar entre los K primeros de la población aprendible). Si el cliente ya tiene un seguimiento abierto se
  añade el motivo a ese seguimiento en lugar de crear otro. Contactos, decisiones y resultados humanos no se tocan.
* La creación de tareas está DESACTIVADA por defecto (bandera ``prevencion_tareas``): sin ella solo se informa.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from contratos.validar import leer_publicacion_sombra

from .base import BaseDatos, ErrorApi, ahora, auditar, bandera, dumps, loads
from .publicacion import cierre_activo, filas as filas_cierre
from .tareas import CERRADOS, registrar_evento

MODELO_ID = "inactividad_60d"
BANDERA_TAREAS = "prevencion_tareas"
K_POLITICA = 10
TIPO_TAREA = "comprobacion"
MOTIVO = "Prevenir inactividad (experimento en sombra)"
PRIORIDAD = 9  # después de las acciones C1: no cambia su precedencia
NOTA = ("Riesgo experimental de llegar a 90 días sin compra en los próximos 60 días, calculado en sombra. No es abandono "
        "ni una venta perdida; no cambia la agenda. Una compra posterior a un contacto no demuestra que el seguimiento la causó.")


# ------------------------------------------------------------------ importación de la publicación de sombra
MODELOS_SOMBRA = ("inactividad_60d", "proxima_compra")


def importar_sombra(db: BaseDatos, directorio: str | Path, actor: str, modelo_id: str = MODELO_ID) -> dict:
    """Importa una publicación en sombra verificada (sello, huellas, contrato y coherencia).

    Una publicación de un corte ANTERIOR al de la activa se guarda pero no la desplaza (``activa = False``); una del
    mismo corte o posterior pasa a ser la activa. Repetir la importación no cambia nada."""
    errores, man, filas = leer_publicacion_sombra(directorio)
    if errores:
        from .monitoreo import registrar_integridad
        registrar_integridad(db, modelo_id, errores, str(directorio))
        raise ErrorApi(422, "sombra_invalida", "La publicación en sombra no cumple el contrato", {"errores": errores[:20]})
    if man.get("modelo_id") != modelo_id or modelo_id not in MODELOS_SOMBRA:
        raise ErrorApi(422, "sombra_invalida", f"Se esperaba una publicación de {modelo_id}, no de {man.get('modelo_id')!r}")
    sid = f"{modelo_id}:{man['corte']}:{man['sello'][:12]}"
    with db.transaccion() as con:
        previo = con.execute("SELECT id, activa FROM sombra_publicaciones WHERE sello = ?", (man["sello"],)).fetchone()
        if previo:
            auditar(con, actor, "sombra.importar", previo["id"], "sin_cambios")
            return {"sombra_id": previo["id"], "ya_importada": True, "activa": bool(previo["activa"])}
        actual = con.execute("SELECT id, corte FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (modelo_id,)).fetchone()
        activar = actual is None or man["corte"] >= actual["corte"]
        if activar:
            con.execute("UPDATE sombra_publicaciones SET activa = 0 WHERE modelo_id = ?", (modelo_id,))
        con.execute("""INSERT INTO sombra_publicaciones (id, modelo_id, corte, version_modelo, artefacto_huella, sello, estado_experimento,
                       manifiesto_json, importada_en, importada_por, activa) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, modelo_id, man["corte"], man["modelo"]["version"], man["modelo"]["artefacto_huella"], man["sello"],
                     man["estado_experimento"], dumps(man), ahora(), actor, int(activar)))
        con.executemany("INSERT INTO sombra_predicciones (sombra_id, cliente_id, modelo_id, datos_json) VALUES (?,?,?,?)",
                        [(sid, f["cliente_id"], f["modelo_id"], dumps(f)) for f in filas])
        auditar(con, actor, "sombra.importar", sid, "ok" if activar else "importada_sin_activar", None,
                {"filas": len(filas), "activa": activar, "corte_activa": actual["corte"] if actual else None})
    salida = {"sombra_id": sid, "ya_importada": False, "filas": len(filas), "activa": activar}
    if not activar:
        salida["motivo"] = f"Corte {man['corte']} anterior al de la publicación activa ({actual['corte']}): se conserva sin desplazarla."
    from .monitoreo_modelos import tras_importar
    return tras_importar(db, salida, actor)


def ordenar_estimadas(preds: dict[str, dict]) -> list[dict]:
    """Clientes únicos con estimación, ordenados por probabilidad descendente y cliente_id (no se confía en ``posicion``)."""
    unicos = {f["cliente_id"]: f for f in preds.values() if f.get("estado") == "estimado" and isinstance(f.get("probabilidad"), (int, float))}
    orden = sorted(unicos.values(), key=lambda f: (-f["probabilidad"], f["cliente_id"]))
    return [dict(f, posicion=i) for i, f in enumerate(orden, 1)]


def _evidencia_anterior(e, s: dict) -> bool:
    """La sombra es anterior a la apertura o a la última evidencia del episodio: no debe modificarlo."""
    ultima = (loads(e["ultima_evidencia_json"]) or {}).get("corte") or e["abierto_en_corte"]
    return s["corte"] < max(e["abierto_en_corte"], ultima)


def sombra_activa(con, modelo_id: str = MODELO_ID) -> dict | None:
    r = con.execute("SELECT * FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (modelo_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["manifiesto"] = loads(d.pop("manifiesto_json"))
    return d


def predicciones_sombra(con, sombra_id: str, cliente_id: str | None = None) -> dict[str, dict]:
    sql, args = "SELECT datos_json FROM sombra_predicciones WHERE sombra_id = ?", [sombra_id]
    if cliente_id:
        sql += " AND cliente_id = ?"; args.append(cliente_id)
    return {f["cliente_id"]: f for f in (loads(r[0]) for r in con.execute(sql, args))}


def _ultima_compra(f: dict) -> str | None:
    if f.get("recencia_dias") is None:
        return None
    return (date.fromisoformat(f["corte"]) - timedelta(days=f["recencia_dias"])).isoformat()


def _encabezado(s: dict) -> dict:
    m = s["manifiesto"]
    return {"sombra_id": s["id"], "corte": s["corte"], "version_modelo": s["version_modelo"], "estado_experimento": s["estado_experimento"],
            "operativa": False, "decision": (m.get("modelo") or {}).get("decision"), "advertencia": m.get("advertencia"),
            "simulacion_historica": m.get("simulacion_historica"), "conteos": m.get("conteos"), "importada_en": s["importada_en"]}


# ------------------------------------------------------------------ consulta interna
def para_ficha(con, cliente_id: str) -> dict | None:
    """Resultado de sombra de un cliente para la ficha interna (no altera la precedencia C1)."""
    s = sombra_activa(con)
    if not s:
        return None
    f = predicciones_sombra(con, s["id"], cliente_id).get(cliente_id)
    if not f:
        return None
    rango = next((x["posicion"] for x in ordenar_estimadas(predicciones_sombra(con, s["id"])) if x["cliente_id"] == cliente_id), None)
    f = dict(f, posicion=rango)  # posición recalculada, no la suministrada
    return {k: f.get(k) for k in ("estado", "probabilidad", "posicion", "recencia_dias", "poblacion", "motivos", "version_modelo", "corte",
                                  "horizonte_dias", "umbral_frio_dias")} | {"experimental": True, "estado_experimento": s["estado_experimento"], "nota": NOTA}


def lista(con, k: int = K_POLITICA) -> dict:
    s = sombra_activa(con)
    if not s:
        return {"estado": "sin_sombra", "experimental": True, "items": [], "nota": NOTA,
                "mensaje": "No hay una publicación en sombra de inactividad importada."}
    k = max(1, min(int(k), 200))
    preds = predicciones_sombra(con, s["id"])
    aprendibles = ordenar_estimadas(preds)
    por_recencia = {f["cliente_id"]: i for i, f in enumerate(sorted(aprendibles, key=lambda f: (-f["recencia_dias"], f["cliente_id"])), 1)}
    cid = cierre_activo(con)
    agenda, corte_cierre = {}, None
    if cid:
        corte_cierre = con.execute("SELECT corte FROM cierres WHERE id = ?", (cid,)).fetchone()[0]
        agenda = {r[0]: loads(r[1]) for r in con.execute("SELECT cliente_id, datos_json FROM an_agenda WHERE cierre_id = ?", (cid,))}
    episodios = {r["cliente_id"]: dict(r) for r in con.execute("SELECT * FROM episodios_prevencion WHERE estado = 'abierto'")}
    items = []
    for f in aprendibles[:k]:
        c = agenda.get(f["cliente_id"]) or {}
        e = episodios.get(f["cliente_id"])
        items.append({"cliente_id": f["cliente_id"], "posicion": f["posicion"], "posicion_mayor_recencia": por_recencia[f["cliente_id"]],
                      "probabilidad": f["probabilidad"], "recencia_dias": f["recencia_dias"], "ultima_compra": _ultima_compra(f),
                      "motivos": f["motivos"], "accion_c1": c.get("accion"), "motivos_c1": c.get("motivos"),
                      "episodio": {"episodio_id": e["episodio_id"], "tarea_id": e["tarea_id"], "compartida": bool(e["tarea_compartida"])} if e else None})
    conteos = {p: sum(f.get("poblacion") == p for f in preds.values()) for p in ("aprendible", "estructural", "ya_frio", "sin_historial", "alta_posterior")}
    return {"estado": "ok", "experimental": True, "sombra": _encabezado(s), "k": k, "items": items, "total_aprendibles": len(aprendibles),
            "conteos": conteos, "cierre_activo": {"id": cid, "corte": corte_cierre,
                                                   "coincide_corte": corte_cierre == s["corte"] if corte_cierre else None},
            "tareas_automaticas": bandera(con, BANDERA_TAREAS, False),
            "orden": "probabilidad de sombra descendente, desempate por cliente_id; se muestra también la posición por mayor recencia",
            "nota": NOTA, "precedencia_c1": "La acción C1 de cada cliente no cambia; la prevención solo se añade como motivo."}


# ------------------------------------------------------------------ episodios y tareas
def sincronizar(db: BaseDatos, actor: str = "sistema", k: int = K_POLITICA) -> dict:
    """Aplica la política a la sombra activa. Sin la bandera ``prevencion_tareas`` no escribe nada (solo propone)."""
    with db.transaccion() as con:
        s = sombra_activa(con)
        if not s:
            raise ErrorApi(409, "sin_sombra", "No hay una publicación en sombra de inactividad importada")
        preds = predicciones_sombra(con, s["id"])
        califican = ordenar_estimadas(preds)[:k]
        if not bandera(con, BANDERA_TAREAS, False):
            return {"activada": False, "escrito": False, "propuestos": sorted(f["cliente_id"] for f in califican),
                    "mensaje": "La creación de tareas de prevención está desactivada (bandera prevencion_tareas); no se creó nada."}
        res = {"activada": True, "nuevos": 0, "compartidos": 0, "tareas_nuevas": 0, "cerrados_compra": 0, "cerrados_frio": 0, "sin_cambios": 0}
        for f in sorted(preds.values(), key=lambda f: f["cliente_id"]):  # 1) cerrar episodios con compra nueva o ya fríos
            e = con.execute("SELECT * FROM episodios_prevencion WHERE cliente_id = ? AND estado = 'abierto'", (f["cliente_id"],)).fetchone()
            if not e:
                continue
            if _evidencia_anterior(e, s):
                res["ignorados_evidencia_anterior"] = res.get("ignorados_evidencia_anterior", 0) + 1
                continue
            ultima = _ultima_compra(f)
            if ultima and ultima > e["ultima_compra_ancla"]:
                _cerrar(con, e, "cerrado_compra", s, actor, ultima)
                res["cerrados_compra"] += 1
            elif f.get("poblacion") == "ya_frio":
                _cerrar(con, e, "cerrado_frio", s, actor, None)
                res["cerrados_frio"] += 1
        for f in sorted(califican, key=lambda f: f["posicion"]):  # 2) abrir o actualizar
            ancla = _ultima_compra(f)
            eid = f"prevencion:{f['cliente_id']}:{ancla}"
            evid = {"probabilidad_sombra": f["probabilidad"], "posicion": f["posicion"], "recencia_dias": f["recencia_dias"],
                    "ultima_compra": ancla, "version_modelo": f["version_modelo"], "corte": f["corte"]}
            e = con.execute("SELECT * FROM episodios_prevencion WHERE episodio_id = ?", (eid,)).fetchone()
            if e:
                if _evidencia_anterior(e, s):
                    res["ignorados_evidencia_anterior"] = res.get("ignorados_evidencia_anterior", 0) + 1
                    continue
                if e["estado"] == "abierto":
                    con.execute("UPDATE episodios_prevencion SET ultima_evidencia_json = ?, actualizado_en = ? WHERE episodio_id = ?",
                                (dumps(evid), ahora(), eid))
                    if e["tarea_id"]:
                        con.execute("INSERT OR IGNORE INTO tarea_evidencias (tarea_id, cierre_id, motivos_json, evidencia_json, version_modelo, ts) VALUES (?,?,?,?,?,?)",
                                    (e["tarea_id"], s["id"], dumps([MOTIVO]), dumps(evid), f["version_modelo"], ahora()))
                res["sin_cambios"] += 1
                continue
            tarea = con.execute(f"""SELECT * FROM tareas WHERE cliente_id = ? AND estado NOT IN ({",".join("?" * len(CERRADOS))})
                                   ORDER BY prioridad, id LIMIT 1""", (f["cliente_id"], *sorted(CERRADOS))).fetchone()
            compartida = tarea is not None
            if compartida:  # mismo seguimiento: se añade el motivo; estado, responsable y resultados humanos intactos
                motivos = loads(tarea["motivos_json"])
                if MOTIVO not in motivos:
                    con.execute("UPDATE tareas SET motivos_json = ?, actualizada_en = ?, version = version + 1 WHERE id = ?",
                                (dumps(motivos + [MOTIVO]), ahora(), tarea["id"]))
                tid = tarea["id"]
                res["compartidos"] += 1
            else:
                cur = con.execute(
                    """INSERT INTO tareas (episodio_id, oportunidad_id, cliente_id, tipo, motivos_json, evidencia_json, prioridad,
                       probabilidad, fecha_revision, estado, cierre_origen, cierre_ultimo, creada_en, actualizada_en)
                       VALUES (?,?,?,?,?,?,?,?,?, 'abierta', ?, ?, ?, ?)""",
                    (eid, f"OP-{eid}", f["cliente_id"], TIPO_TAREA, dumps([MOTIVO]), dumps(evid), PRIORIDAD, None,
                     f["corte"], s["id"], s["id"], ahora(), ahora()))
                tid = cur.lastrowid
                res["tareas_nuevas"] += 1
            con.execute("INSERT OR IGNORE INTO tarea_evidencias (tarea_id, cierre_id, motivos_json, evidencia_json, version_modelo, ts) VALUES (?,?,?,?,?,?)",
                        (tid, s["id"], dumps([MOTIVO]), dumps(evid), f["version_modelo"], ahora()))
            con.execute("""INSERT INTO episodios_prevencion (episodio_id, cliente_id, ultima_compra_ancla, estado, tarea_id, tarea_compartida,
                           abierto_en_corte, sombra_apertura, version_modelo_apertura, ultima_evidencia_json, creado_en, actualizado_en)
                           VALUES (?,?,?, 'abierto', ?,?,?,?,?,?,?,?)""",
                        (eid, f["cliente_id"], ancla, tid, int(compartida), f["corte"], s["id"], f["version_modelo"], dumps(evid), ahora(), ahora()))
            t = con.execute("SELECT * FROM tareas WHERE id = ?", (tid,)).fetchone()
            registrar_evento(con, "prevencion_compartida" if compartida else "expuesta", actor, t, clave=f"prevencion:abrir:{eid}",
                             cierre_id=s["id"], datos={"episodio_prevencion": eid, **evid})
            res["nuevos"] += 1
        auditar(con, actor, "prevencion.sincronizar", s["id"], "ok", None, res)
    return res


def _cerrar(con, e, estado: str, s: dict, actor: str, fecha_compra: str | None) -> None:
    con.execute("""UPDATE episodios_prevencion SET estado = ?, cerrado_en_corte = ?, fecha_compra_cierre = ?, actualizado_en = ?
                   WHERE episodio_id = ?""", (estado, s["corte"], fecha_compra, ahora(), e["episodio_id"]))
    t = con.execute("SELECT * FROM tareas WHERE id = ?", (e["tarea_id"],)).fetchone() if e["tarea_id"] else None
    tipo = "compra_posterior_observada" if estado == "cerrado_compra" else "cruce_90_dias_observado"
    registrar_evento(con, tipo, "sistema", t, clave=f"prevencion:{estado}:{e['episodio_id']}", cierre_id=s["id"],
                     resultado=tipo, cliente_id=e["cliente_id"],
                     datos={"episodio_prevencion": e["episodio_id"], "fecha_compra": fecha_compra,
                            "nota": "Observación, no atribución: el episodio se cierra; la tarea y sus resultados humanos no se modifican."})


def episodios(con, cliente_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM episodios_prevencion", []
    if cliente_id:
        sql += " WHERE cliente_id = ?"; args.append(cliente_id)
    return [dict(r, ultima_evidencia=loads(r["ultima_evidencia_json"])) for r in con.execute(sql + " ORDER BY creado_en, episodio_id", args)]
