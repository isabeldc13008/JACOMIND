"""M3 · Próxima compra (en uso): ventana estimada, consulta interna y recordatorios configurables.

* La puntuación llega como **publicación de sombra** (``modelos.cli puntuar --modelo proxima_compra``), verificada (sello,
  huellas, contrato y coherencia) y guardada aparte de los cierres: no cambia la agenda C1, ``prob_compra_30d``, el riesgo
  de inactividad ni las acciones.
* Una ventana estimada NO es una fecha contractual: las coberturas registradas se muestran aparte y nunca se alteran.
* Solo roles internos con ``proxima.ver``; el portal externo no la recibe.
* Recordatorios: bandera ``proxima_recordatorios`` desactivada por defecto. Solo con ventana utilizable (p10 y p90
  dentro del horizonte y ancho <= límite); sin ella no se crea ninguna fecha. Episodio estable
  ``proxima:<cliente>:<última compra>``; una compra posterior lo cierra; la tarea y sus resultados humanos se conservan.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from .base import BaseDatos, ErrorApi, ahora, auditar, bandera, dumps, loads
from .prevencion import importar_sombra as _importar, predicciones_sombra, sombra_activa
from .publicacion import cierre_activo
from .tareas import CERRADOS, registrar_evento
from .estado_modelos import EN_USO

MODELO_ID = "proxima_compra"
BANDERA = "proxima_recordatorios"
MOTIVO = "Ventana estimada de próxima compra (M3)"
TIPO_TAREA = "comprobacion"
PRIORIDAD = 9  # después de las acciones C1
NOTA = ("Ventana estimada por comportamiento de compra: no es una fecha contractual ni un vencimiento de "
        "cobertura, no cambia la agenda y no garantiza una compra.")
LIMITACIONES = ["Datos sintéticos de práctica: resultados orientativos.",
                "Si el límite superior no se alcanza en 60 días no hay ventana: no se inventa una fecha.",
                "Una compra posterior a un contacto no demuestra que el seguimiento la causó."]


def importar_sombra(db: BaseDatos, directorio: str | Path, actor: str) -> dict:
    return _importar(db, directorio, actor, modelo_id=MODELO_ID)


def _ultima_compra(f: dict) -> str | None:
    if f.get("recencia_dias") is None:
        return None
    return (date.fromisoformat(f["corte"]) - timedelta(days=f["recencia_dias"])).isoformat()


def _campos(f: dict) -> dict:
    return {k: f.get(k) for k in ("estado", "origen_estimacion", "dias_p10", "dias_p50", "dias_p90", "fecha_p10", "fecha_p50", "fecha_p90",
                                  "ventana_utilizable", "ancho_ventana_dias", "soporte_dias", "horizonte_dias", "referencia_personal_estado",
                                  "referencia_personal_dias", "recencia_dias", "grupo", "motivos", "version_modelo", "corte",
                                  "prob_acumulada")} | {"ventana_tipo": f.get("ventana_tipo", "p10_p90")} | _limites(f)


def _limites(f: dict) -> dict:
    """Inicio y fin de la ventana según su tipo (M3: p10–p90; M3.1: p10–p50, «inicio probable»)."""
    sup = "p50" if f.get("ventana_tipo") == "p10_p50" else "p90"
    return {"ventana_desde": f.get("fecha_p10"), "ventana_hasta": f.get(f"fecha_{sup}")}


def para_ficha(con, cliente_id: str) -> dict | None:
    s = sombra_activa(con, MODELO_ID)
    if not s:
        return None
    f = predicciones_sombra(con, s["id"], cliente_id).get(cliente_id)
    if not f:
        return None
    return _campos(f) | {"etiqueta": "ventana estimada", "experimental": False, "estado_experimento": EN_USO,
                         "nota": NOTA, "limitaciones": LIMITACIONES, "ultima_compra": _ultima_compra(f)}


def utilizables(preds: dict[str, dict]) -> list[dict]:
    """Clientes únicos con ventana utilizable, verificada otra vez aquí (no se confía solo en el indicador publicado)."""
    salida = []
    for f in preds.values():
        sup = "p50" if f.get("ventana_tipo") == "p10_p50" else "p90"
        p10, p90, ancho_max = f.get("dias_p10"), f.get(f"dias_{sup}"), f.get("ancho_maximo_ventana_dias")
        if f.get("estado") in ("estimado", "estimacion_parcial") and isinstance(p10, int) and isinstance(p90, int) \
                and isinstance(ancho_max, int) and 0 <= p90 - p10 <= ancho_max and f.get("ventana_utilizable") is True:
            salida.append(f)
    return sorted({f["cliente_id"]: f for f in salida}.values(), key=lambda f: (f["fecha_p10"], f["cliente_id"]))


def lista(con, dias: int = 30) -> dict:
    """Seguimiento en sombra: ventanas que empiezan en los próximos ``dias`` desde el corte (y el resto de estados, contados)."""
    s = sombra_activa(con, MODELO_ID)
    if not s:
        return {"estado": "sin_sombra", "experimental": False, "items": [], "nota": NOTA,
                "mensaje": "No hay una publicación del modelo de próxima compra importada."}
    dias = max(1, min(int(dias), 60))
    preds = predicciones_sombra(con, s["id"])
    limite = (date.fromisoformat(s["corte"]) + timedelta(days=dias)).isoformat()
    cid = cierre_activo(con)
    agenda, coberturas = {}, {}
    if cid:
        agenda = {r[0]: loads(r[1]) for r in con.execute("SELECT cliente_id, datos_json FROM an_agenda WHERE cierre_id = ?", (cid,))}
        for r in con.execute("SELECT datos_json FROM an_filas WHERE cierre_id = ? AND tabla = 'coberturas'", (cid,)):
            c = loads(r[0])
            if c.get("fecha_fin") and c["fecha_fin"] >= s["corte"]:
                prev = coberturas.get(c["cliente_id"])
                coberturas[c["cliente_id"]] = min(prev, c["fecha_fin"]) if prev else c["fecha_fin"]
    episodios = {r["cliente_id"]: dict(r) for r in con.execute("SELECT * FROM episodios_proxima WHERE estado = 'abierto'")}
    items = []
    for f in utilizables(preds):
        if f["fecha_p10"] > limite:
            continue
        e = episodios.get(f["cliente_id"])
        items.append(_campos(f) | {"cliente_id": f["cliente_id"], "accion_c1": (agenda.get(f["cliente_id"]) or {}).get("accion"),
                                   "proximo_fin_cobertura": coberturas.get(f["cliente_id"]),
                                   "episodio": {"episodio_id": e["episodio_id"], "tarea_id": e["tarea_id"], "compartida": bool(e["tarea_compartida"])} if e else None})
    conteo: dict[str, int] = {}
    for f in preds.values():
        clave = "ventana_utilizable" if f.get("ventana_utilizable") else f.get("estado")
        conteo[clave] = conteo.get(clave, 0) + 1
    m = s["manifiesto"]
    return {"estado": "ok", "experimental": False, "etiqueta": "ventana estimada", "dias": dias, "items": items,
            "sombra": {"sombra_id": s["id"], "corte": s["corte"], "version_modelo": s["version_modelo"], "estado_experimento": EN_USO,
                       "tipo": (m.get("modelo") or {}).get("tipo"), "decision": (m.get("modelo") or {}).get("decision"), "operativa": True},
            "conteos": conteo, "recordatorios_automaticos": bandera(con, BANDERA, False), "nota": NOTA, "limitaciones": LIMITACIONES,
            "precedencia_c1": "La acción C1, la probabilidad de compra a 30 días y el riesgo de inactividad no cambian."}


def _evidencia_anterior(e, s: dict) -> bool:
    ultima = (loads(e["ultima_evidencia_json"]) or {}).get("corte") or e["abierto_en_corte"]
    return s["corte"] < max(e["abierto_en_corte"], ultima)


def sincronizar(db: BaseDatos, actor: str = "sistema") -> dict:
    """Recordatorios por ventana utilizable. Sin la bandera ``proxima_recordatorios`` no escribe nada (solo propone)."""
    with db.transaccion() as con:
        s = sombra_activa(con, MODELO_ID)
        if not s:
            raise ErrorApi(409, "sin_sombra", "No hay una publicación en sombra de próxima compra importada")
        preds = predicciones_sombra(con, s["id"])
        califican = utilizables(preds)
        if not bandera(con, BANDERA, False):
            return {"activada": False, "escrito": False, "propuestos": [f["cliente_id"] for f in califican],
                    "mensaje": "Los recordatorios por ventana estimada están desactivados (bandera proxima_recordatorios); no se creó nada."}
        res = {"activada": True, "nuevos": 0, "compartidos": 0, "tareas_nuevas": 0, "cerrados_compra": 0, "sin_cambios": 0, "ignorados_evidencia_anterior": 0}
        for f in sorted(preds.values(), key=lambda f: f["cliente_id"]):  # 1) una compra posterior cierra el episodio
            e = con.execute("SELECT * FROM episodios_proxima WHERE cliente_id = ? AND estado = 'abierto'", (f["cliente_id"],)).fetchone()
            if not e:
                continue
            if _evidencia_anterior(e, s):
                res["ignorados_evidencia_anterior"] += 1
                continue
            ultima = _ultima_compra(f)
            if ultima and ultima > e["ultima_compra_ancla"]:
                con.execute("""UPDATE episodios_proxima SET estado = 'cerrado_compra', cerrado_en_corte = ?, fecha_compra_cierre = ?, actualizado_en = ?
                               WHERE episodio_id = ?""", (s["corte"], ultima, ahora(), e["episodio_id"]))
                t = con.execute("SELECT * FROM tareas WHERE id = ?", (e["tarea_id"],)).fetchone() if e["tarea_id"] else None
                registrar_evento(con, "compra_posterior_observada", "sistema", t, clave=f"proxima:cerrado:{e['episodio_id']}", cierre_id=s["id"],
                                 resultado="compra_posterior_observada", cliente_id=e["cliente_id"],
                                 datos={"episodio_proxima": e["episodio_id"], "fecha_compra": ultima,
                                        "nota": "Observación, no atribución: la tarea y sus resultados humanos no se modifican."})
                res["cerrados_compra"] += 1
        for f in califican:  # 2) abrir o actualizar
            ancla = _ultima_compra(f)
            eid = f"proxima:{f['cliente_id']}:{ancla}"
            evid = {"fecha_p10": f["fecha_p10"], "fecha_p50": f["fecha_p50"], "fecha_p90": f["fecha_p90"], "origen": f["origen_estimacion"],
                    "ventana_tipo": f.get("ventana_tipo", "p10_p90"),
                    "version_modelo": f["version_modelo"], "corte": f["corte"], "etiqueta": "ventana estimada"}
            e = con.execute("SELECT * FROM episodios_proxima WHERE episodio_id = ?", (eid,)).fetchone()
            if e:
                if _evidencia_anterior(e, s):
                    res["ignorados_evidencia_anterior"] += 1
                    continue
                if e["estado"] == "abierto":
                    con.execute("UPDATE episodios_proxima SET ultima_evidencia_json = ?, actualizado_en = ? WHERE episodio_id = ?", (dumps(evid), ahora(), eid))
                res["sin_cambios"] += 1
                continue
            tarea = con.execute(f"""SELECT * FROM tareas WHERE cliente_id = ? AND estado NOT IN ({",".join("?" * len(CERRADOS))})
                                   ORDER BY prioridad, id LIMIT 1""", (f["cliente_id"], *sorted(CERRADOS))).fetchone()
            compartida = tarea is not None
            if compartida:  # se añade el motivo; estado, responsable, fechas y resultados humanos intactos
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
                     f["fecha_p10"], s["id"], s["id"], ahora(), ahora()))
                tid = cur.lastrowid
                res["tareas_nuevas"] += 1
            con.execute("""INSERT INTO episodios_proxima (episodio_id, cliente_id, ultima_compra_ancla, estado, tarea_id, tarea_compartida,
                           abierto_en_corte, sombra_apertura, version_modelo_apertura, ultima_evidencia_json, creado_en, actualizado_en)
                           VALUES (?,?,?, 'abierto', ?,?,?,?,?,?,?,?)""",
                        (eid, f["cliente_id"], ancla, tid, int(compartida), f["corte"], s["id"], f["version_modelo"], dumps(evid), ahora(), ahora()))
            t = con.execute("SELECT * FROM tareas WHERE id = ?", (tid,)).fetchone()
            registrar_evento(con, "proxima_compartida" if compartida else "expuesta", actor, t, clave=f"proxima:abrir:{eid}",
                             cierre_id=s["id"], datos={"episodio_proxima": eid, **evid})
            res["nuevos"] += 1
        auditar(con, actor, "proxima.sincronizar", s["id"], "ok", None, res)
    return res


def episodios(con, cliente_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM episodios_proxima", []
    if cliente_id:
        sql += " WHERE cliente_id = ?"; args.append(cliente_id)
    return [dict(r, ultima_evidencia=loads(r["ultima_evidencia_json"])) for r in con.execute(sql + " ORDER BY creado_en, episodio_id", args)]
