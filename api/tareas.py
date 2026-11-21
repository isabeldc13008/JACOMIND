"""Oportunidad calculada → tarea humana, avisos y eventos C3 (B05).

La oportunidad pertenece al cierre (reproducible); la tarea es operativa y
sobrevive a la regeneración. Una tarea por episodio; los motivos se acumulan y
la evidencia anterior se conserva.
"""
from __future__ import annotations

from contratos.agenda import ORDEN_ACCION, motivos as motivos_agenda

from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, hoy, loads, nuevo_id
from .publicacion import filas, resolver_cierre

TIPOS_ACCION = {"Revisar reactivación": "reactivacion", "Revisar cobertura": "renovacion",
                "Revisar oportunidad de recompra": "recompra", "Revisar primera compra": "primera_compra"}
CERRADOS = {"descartada", "atendida"}


def _oportunidades(con, cierre: dict) -> list[dict]:
    opps = filas(con, cierre["id"], "oportunidades")
    if opps:
        return opps
    umbral = (cierre["manifiesto"].get("modelo") or {}).get("umbral")
    salida = []
    for r in con.execute("SELECT datos_json FROM an_agenda WHERE cierre_id = ? AND accion <> 'Seguimiento habitual'", (cierre["id"],)):
        c = loads(r[0])
        tipo = TIPOS_ACCION[c["accion"]]
        salida.append({"oportunidad_id": f"OP-{c['cliente_id']}-{tipo}", "episodio_id": f"{c['cliente_id']}:{tipo}",
                       "cliente_id": c["cliente_id"], "tipo": tipo, "motivos": motivos_agenda(c, umbral),
                       "prioridad": ORDEN_ACCION[c["accion"]], "probabilidad": c["prob_compra_30d"],
                       "evidencia": {k: c.get(k) for k in ("dias_sin_compra", "renovaciones_proximas",
                                                            "coberturas_vencidas", "prob_compra_30d", "ultima_compra")},
                       "fecha_sugerida": None, "version_regla": "derivada-de-agenda"})
    return salida


def registrar_evento(con, tipo: str, actor: str, tarea=None, clave: str | None = None, cierre_id=None,
                     resultado=None, datos=None, cliente_id=None) -> bool:
    """Inserta un evento C3. Devuelve False si la clave de idempotencia ya existía."""
    if clave and con.execute("SELECT 1 FROM eventos WHERE clave_idempotencia = ?", (clave,)).fetchone():
        return False
    con.execute("""INSERT INTO eventos (evento_id, clave_idempotencia, tipo, oportunidad_id, episodio_id, cliente_id,
                   cierre_id, fecha, actor, estado, resultado, datos_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (nuevo_id("EV-"), clave, tipo, tarea["oportunidad_id"] if tarea else None,
                 tarea["episodio_id"] if tarea else None, (tarea["cliente_id"] if tarea else cliente_id),
                 cierre_id or (tarea["cierre_ultimo"] if tarea else None), ahora(), actor,
                 tarea["estado"] if tarea else None, resultado, dumps(datos) if datos else None))
    return True


def _aviso(con, clave: str, tarea_id, tipo: str, mensaje: str, destinatario=None) -> None:
    con.execute("INSERT OR IGNORE INTO avisos (clave_dedup, tarea_id, tipo, mensaje, destinatario, creado_en) VALUES (?,?,?,?,?,?)",
                (clave, tarea_id, tipo, mensaje, destinatario, ahora()))


def sincronizar(db: BaseDatos, cierre_id: str, actor: str = "sistema") -> dict:
    nuevas = actualizadas = 0
    with db.transaccion() as con:
        cierre = resolver_cierre(con, cierre_id)
        corte = cierre["corte"]
        version_modelo = (cierre["manifiesto"].get("versiones") or {}).get("modelo_compra")
        agenda = {r[0]: loads(r[1]) for r in con.execute("SELECT cliente_id, datos_json FROM an_agenda WHERE cierre_id = ?", (cierre_id,))}
        for o in _oportunidades(con, cierre):
            t = con.execute("SELECT * FROM tareas WHERE episodio_id = ?", (o["episodio_id"],)).fetchone()
            evid = o.get("evidencia") or {}
            if t is None:
                cur = con.execute(
                    """INSERT INTO tareas (episodio_id, oportunidad_id, cliente_id, tipo, motivos_json, evidencia_json, prioridad,
                       probabilidad, fecha_revision, estado, cierre_origen, cierre_ultimo, creada_en, actualizada_en)
                       VALUES (?,?,?,?,?,?,?,?,?, 'abierta', ?, ?, ?, ?)""",
                    (o["episodio_id"], o["oportunidad_id"], o["cliente_id"], o["tipo"], dumps(o["motivos"]), dumps(evid),
                     o["prioridad"], o.get("probabilidad"), o.get("fecha_sugerida") or corte, cierre_id, cierre_id, ahora(), ahora()))
                tid = cur.lastrowid
                con.execute("INSERT OR IGNORE INTO tarea_evidencias (tarea_id, cierre_id, motivos_json, evidencia_json, version_modelo, ts) VALUES (?,?,?,?,?,?)",
                            (tid, cierre_id, dumps(o["motivos"]), dumps(evid), version_modelo, ahora()))
                t = con.execute("SELECT * FROM tareas WHERE id = ?", (tid,)).fetchone()
                registrar_evento(con, "expuesta", actor, t, clave=f"expuesta:{o['episodio_id']}:{cierre_id}", cierre_id=cierre_id)
                _aviso(con, f"{o['episodio_id']}:nueva", tid, "nueva", f"Nueva oportunidad {o['tipo']} para {o['cliente_id']}")
                nuevas += 1
                continue
            motivos_prev = loads(t["motivos_json"])
            union = sorted(set(motivos_prev) | set(o["motivos"]), key=lambda m: ORDEN_ACCION.get(m, 99))
            cambios = {"motivos_json": dumps(union), "evidencia_json": dumps(evid), "probabilidad": o.get("probabilidad"),
                       "cierre_ultimo": cierre_id, "actualizada_en": ahora()}
            if evid != loads(t["evidencia_json"]) or union != motivos_prev:
                con.execute("INSERT OR IGNORE INTO tarea_evidencias (tarea_id, cierre_id, motivos_json, evidencia_json, version_modelo, ts) VALUES (?,?,?,?,?,?)",
                            (t["id"], cierre_id, dumps(o["motivos"]), dumps(evid), version_modelo, ahora()))
            if o["prioridad"] != t["prioridad"]:
                _aviso(con, f"{o['episodio_id']}:prioridad:{t['prioridad']}>{o['prioridad']}:{cierre_id}", t["id"], "cambio_prioridad",
                       f"La prioridad de {o['cliente_id']} pasó de {t['prioridad']} a {o['prioridad']}", t["responsable_id"])
                cambios["prioridad"] = o["prioridad"]
            if t["estado"] == "pospuesta" and t["pospuesta_hasta"] and t["pospuesta_hasta"] <= corte:
                cambios["estado"] = "asignada" if t["responsable_id"] else "abierta"
                _aviso(con, f"{o['episodio_id']}:fin_aplazamiento:{t['pospuesta_hasta']}", t["id"], "fin_aplazamiento",
                       f"Terminó el aplazamiento de {o['cliente_id']}", t["responsable_id"])
            # Respetar cierres manuales y aplazamientos vigentes: no se reabren.
            sets = ", ".join(f"{k} = ?" for k in cambios)
            con.execute(f"UPDATE tareas SET {sets}, version = version + 1 WHERE id = ?", (*cambios.values(), t["id"]))
            actualizadas += 1
        # Compra posterior observada (no implica atribución al seguimiento).
        for t in con.execute("SELECT * FROM tareas").fetchall():
            c = agenda.get(t["cliente_id"])
            if c and c.get("ultima_compra") and c["ultima_compra"] > t["creada_en"][:10]:
                registrar_evento(con, "compra_posterior_observada", "sistema", t,
                                 clave=f"compra:{t['episodio_id']}:{c['ultima_compra']}", cierre_id=cierre_id,
                                 resultado="compra_posterior_observada", datos={"fecha_compra": c["ultima_compra"]})
        hoy_s = hoy().isoformat()
        for t in con.execute("SELECT * FROM tareas WHERE estado IN ('abierta','asignada') AND fecha_revision < ?", (hoy_s,)).fetchall():
            _aviso(con, f"{t['episodio_id']}:vencida:{t['fecha_revision']}", t["id"], "vencimiento",
                   f"Revisión vencida para {t['cliente_id']} (sugerida {t['fecha_revision']})", t["responsable_id"])
        auditar(con, actor, "tareas.sincronizar", cierre_id, "ok", None, {"nuevas": nuevas, "actualizadas": actualizadas})
    return {"nuevas": nuevas, "actualizadas": actualizadas}


def _fila(t) -> dict:
    d = dict(t)
    d["motivos"] = loads(d.pop("motivos_json"))
    d["evidencia"] = loads(d.pop("evidencia_json"))
    return d


def listar(con, responsable=None, estado=None, k=None, cliente_id=None) -> list[dict]:
    where, args = [], []
    if responsable:
        where.append("responsable_id = ?"); args.append(responsable)
    if estado:
        where.append("estado = ?"); args.append(estado)
    else:
        where.append("estado NOT IN ('descartada','atendida')")
    if cliente_id:
        where.append("cliente_id = ?"); args.append(cliente_id)
    sql = "SELECT * FROM tareas" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY prioridad, probabilidad IS NULL, probabilidad DESC, cliente_id"
    if k:
        sql += f" LIMIT {max(1, int(k))}"
    return [_fila(t) for t in con.execute(sql, args)]


def detalle(con, tarea_id: int) -> dict:
    t = con.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
    if not t:
        raise ErrorApi(404, "tarea_no_encontrada", "Tarea no encontrada")
    d = _fila(t)
    d["historial_evidencia"] = [dict(r, motivos=loads(r["motivos_json"]), evidencia=loads(r["evidencia_json"]))
                                for r in con.execute("SELECT cierre_id, motivos_json, evidencia_json, version_modelo, ts FROM tarea_evidencias WHERE tarea_id = ? ORDER BY id", (tarea_id,))]
    d["eventos"] = [dict({k: r[k] for k in ("evento_id", "tipo", "fecha", "actor", "estado", "resultado")},
                         datos=loads(r["datos_json"]) if r["datos_json"] else None)
                    for r in con.execute("SELECT evento_id, tipo, fecha, actor, estado, resultado, datos_json FROM eventos WHERE episodio_id = ? ORDER BY fecha", (t["episodio_id"],))]
    return d


def accion(db: BaseDatos, usuario, tarea_id: int, tipo: str, cuerpo: dict, clave: str | None = None) -> dict:
    """Asignar, posponer, descartar, registrar contacto o marcar atendida (con control de versión)."""
    with db.transaccion() as con:
        t = con.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
        if not t:
            raise ErrorApi(404, "tarea_no_encontrada", "Tarea no encontrada")
        if clave and con.execute("SELECT 1 FROM eventos WHERE clave_idempotencia = ?", (clave,)).fetchone():
            return detalle(con, tarea_id) | {"repetida": True}
        if "version" not in cuerpo:
            raise ErrorApi(400, "falta_version", "Incluye la versión de la tarea que estás editando")
        if int(cuerpo["version"]) != t["version"]:
            raise ErrorApi(409, "conflicto_version", "Otra sesión modificó esta tarea; recarga para ver el estado actual",
                           {"version_actual": t["version"], "estado_actual": t["estado"]})
        if t["estado"] in CERRADOS:
            raise ErrorApi(409, "tarea_cerrada", f"La tarea ya está {t['estado']}")
        cambios: dict = {}
        resultado = None
        if tipo == "asignar":
            resp = cuerpo.get("responsable") or usuario.id
            if not con.execute("SELECT 1 FROM pertenencias WHERE identidad_id = ? AND rol = 'ventas'", (resp,)).fetchone():
                raise ErrorApi(400, "responsable_invalido", "El responsable debe pertenecer a Ventas")
            cambios = {"responsable_id": resp, "estado": "asignada", "fecha_revision": cuerpo.get("fecha_revision") or t["fecha_revision"]}
        elif tipo == "posponer":
            hasta = cuerpo.get("hasta")
            if not hasta or hasta <= hoy().isoformat():
                raise ErrorApi(400, "fecha_invalida", "Indica una fecha futura para posponer")
            cambios = {"estado": "pospuesta", "pospuesta_hasta": hasta, "fecha_revision": hasta}
        elif tipo == "descartar":
            if not (cuerpo.get("motivo") or "").strip():
                raise ErrorApi(400, "falta_motivo", "Descartar requiere un motivo")
            cambios = {"estado": "descartada", "motivo_descarte": cuerpo["motivo"].strip()}
        elif tipo == "contacto":
            cambios = {"siguiente_paso": cuerpo.get("siguiente_paso") or t["siguiente_paso"]}
            resultado = "contacto_registrado"
        elif tipo == "atender":
            if not (cuerpo.get("resultado") or "").strip():
                raise ErrorApi(400, "falta_resultado", "Registra el resultado del seguimiento")
            cambios = {"estado": "atendida", "resultado": cuerpo["resultado"].strip(),
                       "siguiente_paso": cuerpo.get("siguiente_paso"), "beneficio_id": cuerpo.get("beneficio_id") or t["beneficio_id"]}
            resultado = "resultado_atribuido" if cuerpo.get("atribuido") else cuerpo["resultado"].strip()
        else:
            raise ErrorApi(400, "accion_desconocida", f"Acción no soportada: {tipo}")
        cambios["actualizada_en"] = ahora()
        sets = ", ".join(f"{k} = ?" for k in cambios)
        con.execute(f"UPDATE tareas SET {sets}, version = version + 1 WHERE id = ? AND version = ?",
                    (*cambios.values(), tarea_id, t["version"]))
        nt = con.execute("SELECT * FROM tareas WHERE id = ?", (tarea_id,)).fetchone()
        tipo_evento = {"asignar": "asignada", "posponer": "pospuesta", "descartar": "descartada",
                       "contacto": "contacto_registrado", "atender": "atendida"}[tipo]
        registrar_evento(con, tipo_evento, usuario.id, nt, clave=clave, resultado=resultado,
                         datos={k: v for k, v in cuerpo.items() if k != "version"})
        if tipo == "atender" and cuerpo.get("atribuido"):
            registrar_evento(con, "resultado_atribuido", usuario.id, nt, resultado="resultado_atribuido")
        auditar(con, usuario.id, f"tarea.{tipo}", str(tarea_id), "ok")
        return detalle(con, tarea_id)


def avisos(con, destinatario=None) -> list[dict]:
    if destinatario:
        cur = con.execute("SELECT * FROM avisos WHERE destinatario = ? OR destinatario IS NULL ORDER BY id DESC LIMIT 100", (destinatario,))
    else:
        cur = con.execute("SELECT * FROM avisos ORDER BY id DESC LIMIT 100")
    return [dict(r) for r in cur]


def metricas(con, responsable=None) -> dict:
    """Medición del equipo (todas las tareas) y, aparte, el total pendiente de la selección antes del cupo."""
    where, args = "estado NOT IN ('descartada','atendida')", []
    if responsable:
        where += " AND responsable_id = ?"; args.append(responsable)
    pendientes = con.execute(f"SELECT count(*) FROM tareas WHERE {where}", args).fetchone()[0]
    por_tipo = {}
    for r in con.execute("""SELECT tipo, count(*) total, sum(estado = 'atendida') atendidas, sum(estado = 'descartada') descartadas
                            FROM tareas GROUP BY tipo"""):
        por_tipo[r["tipo"]] = {"total": r["total"], "atendidas": r["atendidas"], "descartadas": r["descartadas"],
                               "fraccion_atendida": round(r["atendidas"] / r["total"], 4),
                               "tasa_descarte": round(r["descartadas"] / r["total"], 4)}
    dup = con.execute("SELECT count(*) FROM (SELECT tarea_id, tipo, mensaje FROM avisos GROUP BY 1,2,3 HAVING count(*) > 1)").fetchone()[0]
    multi = con.execute("SELECT count(*) FROM (SELECT episodio_id FROM tareas GROUP BY 1 HAVING count(*) > 1)").fetchone()[0]
    expuestas = con.execute("SELECT count(DISTINCT episodio_id) FROM eventos WHERE tipo = 'expuesta'").fetchone()[0]
    return {"por_tipo": por_tipo, "alcance": "equipo (todas las tareas, con independencia del filtro por responsable)",
            "pendientes_seleccion": pendientes, "seleccion": {"responsable": responsable},
            "avisos_duplicados": dup, "episodios_con_varias_tareas": multi,
            "denominador_expuestas": expuestas,
            "nota": "Compra posterior observada ≠ contacto registrado ≠ resultado atribuido al seguimiento."}


def exportar_eventos(con) -> dict:
    evs = [{k: r[k] for k in ("evento_id", "tipo", "oportunidad_id", "episodio_id", "cliente_id", "cierre_id", "fecha",
                              "actor", "estado", "resultado")} for r in con.execute("SELECT * FROM eventos ORDER BY fecha, evento_id")]
    return {"version": 1, "tipo": "eventos_seguimiento", "exportado_en": ahora(), "eventos": evs}
