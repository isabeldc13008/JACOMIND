"""Consultas por cierre: resumen, agenda, ficha 360° y tableros por rol (B03)."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict

from contratos.agenda import ORDEN_ACCION, motivos

from .base import ErrorApi, bandera, loads
from .publicacion import filas, resolver_cierre

TAM_MAX = 200


def _umbral(cierre: dict) -> float | None:
    return ((cierre["manifiesto"].get("modelo") or {}).get("umbral"))


def _preparar(c: dict, umbral, modelo_activo: bool, segmento=None) -> dict:
    c = dict(c)
    if segmento and not c.get("segmento"):
        c["segmento"] = segmento
    if not modelo_activo:
        c["prob_compra_30d"] = None
        c["estado_modelo"] = "Modelo no disponible"
    else:
        c["estado_modelo"] = "Modelo no disponible" if c.get("prob_compra_30d") is None and c.get("ultima_compra") else None
    c["sin_historial"] = c.get("ultima_compra") is None
    c["motivos"] = motivos(c, umbral if modelo_activo else None)
    if c["sin_historial"] and "Revisar primera compra" not in c["motivos"]:
        c["motivos"].append("Revisar primera compra")
    return c


def resumen(con, cierre_ref: str) -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    cid = cierre["id"]
    acciones = {r[0]: r[1] for r in con.execute(
        "SELECT accion, count(*) FROM an_agenda WHERE cierre_id = ? GROUP BY accion", (cid,))}
    frecuentes = con.execute("SELECT count(*) FROM an_agenda WHERE cierre_id = ? AND frecuente = 1", (cid,)).fetchone()[0]
    m = cierre["manifiesto"]
    return {
        "cierre": {"id": cid, "corte": cierre["corte"], "revision": cierre["revision"], "origen": cierre["origen"],
                   "publicado_en": cierre["publicado_en"], "activo": cierre["activo"], "versiones": m.get("versiones")},
        "alcance": "cartera_completa",
        "resumen": m["resumen"],
        "frecuentes": frecuentes,
        "nota_etiquetas": "Las etiquetas frecuente y frío pueden superponerse; sus recuentos no se suman.",
        "por_accion": [{"accion": a, "clientes": acciones.get(a, 0)} for a in ORDEN_ACCION],
        "requieren_revision": sum(v for k, v in acciones.items() if k != "Seguimiento habitual"),
        "modelo": m.get("modelo") if bandera(con, "modelo_compra") else None,
        "modelo_activo": bandera(con, "modelo_compra"),
        "calidad": m.get("calidad"),
        "modelos": m.get("modelos", []),
    }


def agenda(con, cierre_ref: str, accion=None, segmento=None, q=None, frio=None, pagina=1, tam=25) -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    cid = cierre["id"]
    where, args = ["cierre_id = ?"], [cid]
    if accion:
        if accion not in ORDEN_ACCION:
            raise ErrorApi(400, "accion_desconocida", f"Acción no reconocida: {accion}")
        where.append("accion = ?"); args.append(accion)
    if segmento:
        where.append("segmento = ?"); args.append(segmento)
    if q:
        where.append("upper(cliente_id) LIKE ?"); args.append(f"%{q.strip().upper()}%")
    if frio in ("1", "true", True):
        where.append("frio = 1")
    w = " AND ".join(where)
    total, ingreso = con.execute(f"SELECT count(*), coalesce(sum(ingreso_cop), 0) FROM an_agenda WHERE {w}", args).fetchone()
    tam = max(1, min(int(tam), TAM_MAX))
    pagina = max(1, int(pagina))
    modelo_activo = bandera(con, "modelo_compra")
    # Orden estable: acción, probabilidad desc (nulos al final), ID; se pagina después de ordenar.
    orden = "orden_accion, prob IS NULL, prob DESC, cliente_id" if modelo_activo else "orden_accion, cliente_id"
    cur = con.execute(f"SELECT datos_json, segmento FROM an_agenda WHERE {w} ORDER BY {orden} LIMIT ? OFFSET ?",
                      args + [tam, (pagina - 1) * tam])
    umbral = _umbral(cierre)
    items = [_preparar(loads(r[0]), umbral, modelo_activo, r[1]) for r in cur]
    segmentos = [r[0] for r in con.execute(
        "SELECT DISTINCT segmento FROM an_agenda WHERE cierre_id = ? AND segmento IS NOT NULL ORDER BY 1", (cid,))]
    return {"cierre_id": cid, "corte": cierre["corte"], "total": total, "ingreso_cop_filtrado": round(ingreso, 2),
            "pagina": pagina, "tam": tam, "paginas": max(1, -(-total // tam)), "items": items,
            "filtros": {"accion": accion, "segmento": segmento, "q": q, "frio": frio},
            "segmentos_disponibles": segmentos, "estado": "ok" if total else "sin_coincidencias"}


def ficha(con, cierre_ref: str, cliente_id: str) -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    cid = cierre["id"]
    r = con.execute("SELECT datos_json, segmento FROM an_agenda WHERE cierre_id = ? AND cliente_id = ?",
                    (cid, cliente_id)).fetchone()
    if not r:
        raise ErrorApi(404, "cliente_no_encontrado", f"Cliente {cliente_id} no encontrado en el cierre {cid}; no se inventa historial")
    modelo_activo = bandera(con, "modelo_compra")
    c = _preparar(loads(r[0]), _umbral(cierre), modelo_activo, r[1])
    historial = sorted(filas(con, cid, "historial_ventas", cliente_id), key=lambda v: (v["fecha"], v["venta_id"]), reverse=True)
    por_producto = defaultdict(lambda: {"operaciones": 0, "unidades": 0, "importe_cop": 0.0, "ultima": None})
    for v in historial:
        p = por_producto[v.get("producto") or v["producto_id"]]
        p["operaciones"] += 1; p["unidades"] += v["cantidad"]; p["importe_cop"] += v["importe_cop"]
        p["ultima"] = max(p["ultima"] or v["fecha"], v["fecha"])
    seg = [s for s in filas(con, cid, "segmentos", cliente_id)]
    tarea = con.execute("SELECT id, estado, responsable_id, tipo, motivos_json FROM tareas WHERE cliente_id = ? ORDER BY prioridad LIMIT 1",
                        (cliente_id,)).fetchone()
    return {
        "cierre": {"id": cid, "corte": cierre["corte"]},
        "cliente": c,
        "historial_disponible": bool(historial) or c["sin_historial"],
        "historial": historial[:100],
        "productos": [dict(producto=k, **{**v, "importe_cop": round(v["importe_cop"], 2)}) for k, v in sorted(por_producto.items())],
        "coberturas": sorted(filas(con, cid, "coberturas", cliente_id), key=lambda x: x["fecha_fin"]),
        "segmento": seg[0] if seg else ({"segmento": c.get("segmento")} if c.get("segmento") else None),
        "oportunidades": filas(con, cid, "oportunidades", cliente_id),
        "tarea": dict(tarea, motivos=loads(tarea["motivos_json"])) if tarea else None,
        "rfm": {"recencia_dias": c.get("dias_sin_compra"), "frecuencia": c.get("ventas_confirmadas"),
                "monetario_cop": c.get("ingreso_cop")},
    }


def tablero(con, cierre_ref: str, rol: str) -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    cid = cierre["id"]
    clientes = [loads(r[0]) | {"segmento": r[1]} for r in con.execute(
        "SELECT datos_json, segmento FROM an_agenda WHERE cierre_id = ?", (cid,))]
    base = {"cierre": {"id": cid, "corte": cierre["corte"]}, "rol": rol}
    if rol == "ventas":
        seg = Counter(c.get("segmento") or "Sin segmento" for c in clientes)
        opps = sorted(filas(con, cid, "oportunidades"), key=lambda o: (o["prioridad"], -(o.get("probabilidad") or -1), o["cliente_id"]))
        return base | {"segmentos": [{"segmento": k, "clientes": v} for k, v in sorted(seg.items())],
                       "oportunidades": opps[:20],
                       "etiquetas": {"frecuentes": sum(c["frecuente"] for c in clientes), "frios": sum(c["frio"] for c in clientes),
                                     "nota": "Un cliente puede ser frecuente y frío a la vez."}}
    if rol == "operaciones":
        cob = filas(con, cid, "coberturas")
        tareas = {r[0]: r[1] for r in con.execute("SELECT estado, count(*) FROM tareas GROUP BY estado")}
        return base | {"coberturas_proximas": [c for c in cob if c["estado"] == "proxima"],
                       "coberturas_vencidas": [c for c in cob if c["estado"] == "vencida"],
                       "resumen_coberturas": {"renovaciones_proximas": sum(c["renovaciones_proximas"] for c in clientes),
                                              "coberturas_vencidas": sum(c["coberturas_vencidas"] for c in clientes)},
                       "tareas_por_estado": tareas,
                       "nota": "La ventana de cobertura es contractual; la próxima compra estimada es una predicción."}
    if rol == "gerencia":
        series = [s for s in filas(con, cid, "series_mensuales") if s["familia"] == "Total" and s["tipo"] == "historico" and s["serie"] == "ventas"]
        seg = defaultdict(lambda: {"clientes": 0, "ingreso_cop": 0.0})
        for c in clientes:
            s = seg[c.get("segmento") or "Sin segmento"]
            s["clientes"] += 1; s["ingreso_cop"] += c["ingreso_cop"]
        res = cierre["manifiesto"]["resumen"]
        return base | {"indicadores": {"ingreso_cop": res["ingreso_cop"], "ventas_confirmadas": res["ventas_confirmadas"],
                                       "clientes": res["clientes"], "clientes_frios": res["clientes_frios"],
                                       "unidad": "COP acumulado al corte (histórico)"},
                       "evolucion": sorted(series, key=lambda s: s["periodo"]),
                       "segmentos": [{"segmento": k, "clientes": v["clientes"], "ingreso_cop": round(v["ingreso_cop"], 2)}
                                     for k, v in sorted(seg.items())]}
    raise ErrorApi(404, "tablero_desconocido", f"No existe el tablero {rol}")


def exportar_csv(con, cierre_ref: str) -> str:
    cierre = resolver_cierre(con, cierre_ref)
    datos = agenda(con, cierre["id"], tam=TAM_MAX, pagina=1)
    todos = list(datos["items"])
    for p in range(2, datos["paginas"] + 1):
        todos += agenda(con, cierre["id"], tam=TAM_MAX, pagina=p)["items"]
    buf = io.StringIO()
    campos = ["cliente_id", "accion", "motivos", "prob_compra_30d", "dias_sin_compra", "ventas_confirmadas", "ingreso_cop",
              "frecuente", "frio", "renovaciones_proximas", "coberturas_vencidas", "segmento"]
    w = csv.DictWriter(buf, fieldnames=campos, extrasaction="ignore")
    w.writeheader()
    for c in todos:
        w.writerow(c | {"motivos": " | ".join(c["motivos"])})
    return buf.getvalue()
