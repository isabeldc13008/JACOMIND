"""Consultas por cierre: resumen, agenda, ficha 360° y tableros por rol (B03)."""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict

from contratos.agenda import ORDEN_ACCION, motivos

from .base import ErrorApi, ahora, bandera, loads
from .publicacion import filas, resolver_cierre

TAM_MAX = 200
LIMITE_OPORTUNIDADES = 20
TIPO_A_ACCION = {"reactivacion": "Revisar reactivación", "renovacion": "Revisar cobertura",
                 "recompra": "Revisar oportunidad de recompra", "primera_compra": "Revisar primera compra"}
# Intervalos de días hasta el fin de cobertura (relativos al corte) para el tablero de Operaciones.
INTERVALOS_COBERTURA = [("vencidas", "Vencidas", None, -1), ("0-15", "Vencen en 0–15 días", 0, 15),
                        ("16-30", "Vencen en 16–30 días", 16, 30), ("31-45", "Vencen en 31–45 días", 31, 45)]


def comparacion_mensual(series: list[dict]) -> dict | None:
    """Último mes completo frente al anterior, por familia, a partir de las series históricas publicadas.

    Devuelve el par de meses comparado, el valor de cada familia en ambos y la diferencia. Un mes
    incompleto (``completo`` falso o valor nulo) no se compara y se informa aparte.
    """
    hist = [s for s in series if s.get("tipo") == "historico"]
    total = sorted((s for s in hist if s["familia"] == "Total"), key=lambda s: s["periodo"])
    if not total:
        return None
    completos = [s for s in total if s.get("valor_cop") is not None and s.get("completo", True)]
    incompletos = [s["periodo"] for s in total if s.get("valor_cop") is None or not s.get("completo", True)]
    if len(completos) < 2:
        return {"mes": completos[-1]["periodo"] if completos else None, "mes_anterior": None, "familias": [],
                "meses_incompletos": incompletos, "estado": "sin_comparacion"}
    act, ant = completos[-1], completos[-2]
    por_fam: dict[str, dict] = defaultdict(dict)
    for s in hist:
        if s["periodo"] in (act["periodo"], ant["periodo"]):
            por_fam[s["familia"]][s["periodo"]] = s.get("valor_cop")
    familias = []
    for fam, v in por_fam.items():
        a, b = v.get(ant["periodo"]), v.get(act["periodo"])
        familias.append({"familia": fam, "valor_anterior": a, "valor": b,
                         "diferencia": None if a is None or b is None else round(b - a, 2)})
    familias.sort(key=lambda f: (f["familia"] != "Total", -abs(f["diferencia"] or 0), f["familia"]))
    return {"mes": act["periodo"], "valor": act["valor_cop"], "mes_anterior": ant["periodo"], "valor_anterior": ant["valor_cop"],
            "diferencia": round(act["valor_cop"] - ant["valor_cop"], 2), "familias": familias,
            "meses_incompletos": [m for m in incompletos if m > act["periodo"]], "estado": "ok"}


def _umbral(cierre: dict) -> float | None:
    return ((cierre["manifiesto"].get("modelo") or {}).get("umbral"))


NOTA_SENALES = "Señales observadas hasta el corte que acompañan la estimación; no son causas demostradas de compra."


def predicciones_compra(con, cierre_id: str, cliente_id: str | None = None) -> dict[str, dict]:
    """Predicciones persistidas de compra a 30 días del cierre (tabla C2 ``predicciones_clientes``)."""
    return {p["cliente_id"]: p for p in filas(con, cierre_id, "predicciones_clientes", cliente_id)
            if p.get("modelo_id") == "compra_30d"}


def _prediccion_visible(p: dict | None) -> dict | None:
    if not p:
        return None
    return {k: p.get(k) for k in ("probabilidad", "estado", "version_modelo", "corte", "datos_hasta", "horizonte_dias",
                                  "umbral", "supera_umbral", "motivos")} | {"nota": NOTA_SENALES}


def _preparar(c: dict, umbral, modelo_activo: bool, segmento=None, prediccion: dict | None = None) -> dict:
    c = dict(c)
    if segmento and not c.get("segmento"):
        c["segmento"] = segmento
    if not modelo_activo:
        c["prob_compra_30d"] = None
        c["estado_modelo"] = "Modelo no disponible"
        c["prediccion"] = None
    else:
        c["estado_modelo"] = "Modelo no disponible" if c.get("prob_compra_30d") is None and c.get("ultima_compra") else None
        # Agenda, ficha y asistente muestran la misma fila persistida; C2 garantiza que coincide con la agenda.
        c["prediccion"] = _prediccion_visible(prediccion)
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
    preds = predicciones_compra(con, cid) if modelo_activo else {}
    items = [_preparar(c, umbral, modelo_activo, r[1], preds.get(c["cliente_id"])) for r in cur for c in [loads(r[0])]]
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
    pred = predicciones_compra(con, cid, cliente_id).get(cliente_id) if modelo_activo else None
    c = _preparar(loads(r[0]), _umbral(cierre), modelo_activo, r[1], pred)
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
        "historial_total": len(historial),
        "productos": [dict(producto=k, **{**v, "importe_cop": round(v["importe_cop"], 2)}) for k, v in sorted(por_producto.items())],
        "coberturas": sorted(filas(con, cid, "coberturas", cliente_id), key=lambda x: x["fecha_fin"]),
        "segmento": seg[0] if seg else ({"segmento": c.get("segmento")} if c.get("segmento") else None),
        "oportunidades": [o | {"accion": TIPO_A_ACCION.get(o.get("tipo"), o.get("tipo"))}
                          for o in filas(con, cid, "oportunidades", cliente_id)],
        "modelo": (cierre["manifiesto"].get("modelo") if modelo_activo else None),
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
        desc = {s["segmento"]: s.get("descripcion") for s in filas(con, cid, "segmentos")}
        todas = sorted(filas(con, cid, "oportunidades"), key=lambda o: (o["prioridad"], -(o.get("probabilidad") or -1), o["cliente_id"]))
        opps = [o | {"accion": TIPO_A_ACCION.get(o.get("tipo"), o.get("tipo"))} for o in todas[:LIMITE_OPORTUNIDADES]]
        return base | {"segmentos": [{"segmento": k, "clientes": v, "descripcion": desc.get(k)}
                                     for k, v in sorted(seg.items(), key=lambda kv: (-kv[1], kv[0]))],
                       "total_clientes": len(clientes),
                       "oportunidades": opps, "limite_oportunidades": LIMITE_OPORTUNIDADES, "total_oportunidades": len(todas),
                       "etiquetas": {"frecuentes": sum(c["frecuente"] for c in clientes), "frios": sum(c["frio"] for c in clientes),
                                     "ambas": sum(bool(c["frecuente"] and c["frio"]) for c in clientes),
                                     "nota": "Un cliente puede ser frecuente y frío a la vez."}}
    if rol == "operaciones":
        cob = filas(con, cid, "coberturas")
        tareas = {r[0]: r[1] for r in con.execute("SELECT estado, count(*) FROM tareas GROUP BY estado")}
        proximas = sorted((c for c in cob if c["estado"] == "proxima"), key=lambda c: (c.get("dias_para_fin") or 0, c["cliente_id"]))
        vencidas = sorted((c for c in cob if c["estado"] == "vencida"), key=lambda c: (c.get("dias_para_fin") or 0, c["cliente_id"]))
        intervalos = []
        for clave, etiqueta, desde, hasta in INTERVALOS_COBERTURA:
            if desde is None:
                n = len(vencidas)
            else:
                n = sum(1 for c in proximas if c.get("dias_para_fin") is not None and desde <= c["dias_para_fin"] <= hasta)
            intervalos.append({"clave": clave, "etiqueta": etiqueta, "coberturas": n, "desde": desde, "hasta": hasta})
        return base | {"coberturas_proximas": proximas,
                       "coberturas_vencidas": vencidas,
                       "intervalos": intervalos, "unidad_intervalos": "coberturas (un cliente puede tener varias)",
                       "detalle_disponible": bool(cob),
                       "resumen_coberturas": {"renovaciones_proximas": sum(c["renovaciones_proximas"] for c in clientes),
                                              "coberturas_vencidas": sum(c["coberturas_vencidas"] for c in clientes)},
                       "tareas_por_estado": tareas, "tareas_consultadas_en": ahora(),
                       "nota": "La ventana de cobertura es contractual; la próxima compra estimada es una predicción."}
    if rol == "gerencia":
        ventas = [s for s in filas(con, cid, "series_mensuales") if s["serie"] == "ventas"]
        series = [s for s in ventas if s["familia"] == "Total" and s["tipo"] == "historico"]
        seg = defaultdict(lambda: {"clientes": 0, "ingreso_cop": 0.0})
        for c in clientes:
            s = seg[c.get("segmento") or "Sin segmento"]
            s["clientes"] += 1; s["ingreso_cop"] += c["ingreso_cop"]
        res = cierre["manifiesto"]["resumen"]
        return base | {"indicadores": {"ingreso_cop": res["ingreso_cop"], "ventas_confirmadas": res["ventas_confirmadas"],
                                       "clientes": res["clientes"], "clientes_frios": res["clientes_frios"],
                                       "unidad": "COP acumulado al corte (histórico)"},
                       "evolucion": sorted(series, key=lambda s: s["periodo"]),
                       "comparacion": comparacion_mensual(ventas),
                       "fuente": {"cierre_id": cid, "origen": cierre["origen"], "publicado_en": cierre["publicado_en"],
                                  "tablas": ["series_mensuales", "agenda"]},
                       "segmentos": [{"segmento": k, "clientes": v["clientes"], "ingreso_cop": round(v["ingreso_cop"], 2)}
                                     for k, v in sorted(seg.items(), key=lambda kv: (-kv[1]["ingreso_cop"], kv[0]))]}
    raise ErrorApi(404, "tablero_desconocido", f"No existe el tablero {rol}")


def exportar_csv(con, cierre_ref: str, accion=None, segmento=None, q=None, frio=None) -> str:
    """Exporta la agenda con los mismos filtros que la vista (sin filtros: toda la cartera)."""
    cierre = resolver_cierre(con, cierre_ref)
    filtros = {"accion": accion or None, "segmento": segmento or None, "q": q or None, "frio": frio or None}
    datos = agenda(con, cierre["id"], tam=TAM_MAX, pagina=1, **filtros)
    todos = list(datos["items"])
    for p in range(2, datos["paginas"] + 1):
        todos += agenda(con, cierre["id"], tam=TAM_MAX, pagina=p, **filtros)["items"]
    buf = io.StringIO()
    campos = ["cliente_id", "accion", "motivos", "prob_compra_30d", "dias_sin_compra", "ventas_confirmadas", "ingreso_cop",
              "frecuente", "frio", "renovaciones_proximas", "coberturas_vencidas", "segmento"]
    w = csv.DictWriter(buf, fieldnames=campos, extrasaction="ignore")
    w.writeheader()
    for c in todos:
        w.writerow(c | {"motivos": " | ".join(c["motivos"])})
    return buf.getvalue()
