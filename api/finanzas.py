"""Panel financiero, simulador de TRM e informe mensual reproducible (B09)."""
from __future__ import annotations

import hashlib
import html
from collections import defaultdict

from . import consultas, pqrs
from .base import BaseDatos, ErrorApi, ahora, auditar, dumps
from .publicacion import filas, resolver_cierre


def panel(con, cierre_ref: str, serie: str = "ventas") -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    datos = [s for s in filas(con, cierre["id"], "series_mensuales") if s["serie"] == serie]
    grupos: dict[str, dict] = defaultdict(lambda: {"historico": [], "pronostico": []})
    for s in datos:
        grupos[s["familia"]][s["tipo"]].append(s)
    salida = []
    for fam, g in sorted(grupos.items(), key=lambda kv: (kv[0] != "Total", kv[0])):
        h = sorted(g["historico"], key=lambda s: s["periodo"])
        p = sorted(g["pronostico"], key=lambda s: s["periodo"])
        cambios = []
        for a, b in zip(h, h[1:]):
            if a["valor_cop"] is None or b["valor_cop"] is None:
                cambios.append({"periodo": b["periodo"], "cambio_cop": None, "cambio_pct": None, "nota": "mes incompleto"})
                continue
            d = b["valor_cop"] - a["valor_cop"]
            cambios.append({"periodo": b["periodo"], "cambio_cop": round(d, 2),
                            "cambio_pct": round(d / a["valor_cop"] * 100, 2) if a["valor_cop"] else None})
        salida.append({"familia": fam, "historico": h, "pronostico": p, "cambios": cambios,
                       "metodo": p[0].get("metodo") if p else None, "calculado_en": p[0].get("calculado_en") if p else None,
                       "mae_por_horizonte": {x.get("horizonte"): x.get("mae") for x in p},
                       "mae_ingenuo_por_horizonte": {x.get("horizonte"): x.get("mae_ingenuo") for x in p}})
    mayores = sorted((dict(c, familia=s["familia"]) for s in salida if s["familia"] != "Total" for c in s["cambios"] if c["cambio_cop"] is not None),
                     key=lambda c: -abs(c["cambio_cop"]))[:5]
    return {"cierre": {"id": cierre["id"], "corte": cierre["corte"]}, "serie": serie, "unidad": "COP",
            "agregacion": "mensual por familia; 'Total' publicado por A (no se suma en la vista)",
            "familias": salida, "mayores_cambios": mayores, "disponible": bool(datos),
            "estado": "ok" if datos else "pronostico_no_disponible",
            "nota": "Histórico = observado; pronóstico = estimación con su error; simulación = escenario hipotético."}


def simular(con, cierre_ref: str, periodo: str, variacion_pct: float, moneda: str = "USD") -> dict:
    cierre = resolver_cierre(con, cierre_ref)
    try:
        v = float(variacion_pct)
    except (TypeError, ValueError):
        raise ErrorApi(400, "variacion_invalida", "La variación debe ser un número (porcentaje)")
    if not -50 <= v <= 50:
        raise ErrorApi(400, "variacion_fuera_de_rango", "Usa una variación entre −50 % y +50 %")
    compras = [c for c in filas(con, cierre["id"], "compras_proveedor") if c["fecha"].startswith(periodo)]
    supuestos = ["Cantidad y costo unitario en moneda de origen fijos", "Se aplica la variación a la tasa de cada operación",
                 "Componente en COP sin cambio", "Precio de venta fijo; no se estima margen (falta trazabilidad compra-venta)"]
    if not compras:
        pre = [e for e in filas(con, cierre["id"], "escenarios_trm") if e["periodo"] == periodo and e["moneda"] == moneda and e["variacion_pct"] == v]
        if not pre:
            return {"estado": "sin_datos", "cierre": cierre["id"], "periodo": periodo, "mensaje": "No hay compras publicadas para ese periodo y escenario."}
        base = sum(e["costo_base_cop"] for e in pre); esc = sum(e["costo_escenario_cop"] for e in pre)
        return {"estado": "ok", "fuente": "escenarios_trm precalculados", "cierre": cierre["id"], "periodo": periodo, "moneda": moneda,
                "variacion_pct": v, "base_cop": round(base, 2), "simulado_cop": round(esc, 2), "diferencia_cop": round(esc - base, 2),
                "detalle": pre, "supuestos": supuestos, "indicador": "variación del costo de adquisición"}
    expuestas = [c for c in compras if c["moneda"] == moneda]
    sin_tasa = [c["compra_id"] for c in expuestas if not c.get("tasa")]
    grupos = defaultdict(lambda: [0.0, 0.0])
    for c in expuestas:
        if not c.get("tasa"):
            continue
        b = c["cantidad"] * c["costo_unitario"] * c["tasa"]
        g = grupos[(c.get("familia") or "Sin familia", c["proveedor_id"])]
        g[0] += b; g[1] += b * (1 + v / 100)
    cop = round(sum(c["importe_cop"] for c in compras if c["moneda"] == "COP"), 2)
    detalle = [{"familia": f, "proveedor_id": p, "costo_base_cop": round(b, 2), "costo_escenario_cop": round(e, 2),
                "diferencia_cop": round(e - b, 2)} for (f, p), (b, e) in sorted(grupos.items())]
    base = round(sum(d["costo_base_cop"] for d in detalle), 2)
    simul = round(sum(d["costo_escenario_cop"] for d in detalle), 2)
    return {"estado": "ok" if detalle else "sin_exposicion", "fuente": "compras_proveedor", "cierre": cierre["id"], "periodo": periodo,
            "moneda": moneda, "variacion_pct": v, "base_cop": base, "simulado_cop": simul, "diferencia_cop": round(simul - base, 2),
            "componente_cop_sin_cambio": cop, "total_base_cop": round(base + cop, 2), "total_simulado_cop": round(simul + cop, 2),
            "operaciones_sin_tasa": sin_tasa, "detalle": detalle, "supuestos": supuestos,
            "indicador": "variación del costo de adquisición (no margen)",
            "nota": "El escenario no modifica el cierre publicado."}


def _fmt(x) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _contenido_informe(con, cierre_ref: str) -> dict:
    res = consultas.resumen(con, cierre_ref)
    cid = res["cierre"]["id"]
    pan = panel(con, cid)
    total = next((f for f in pan["familias"] if f["familia"] == "Total"), None)
    ultimo = total["historico"][-1]["periodo"] if total and total["historico"] else None
    sims = {}
    meses_usd = sorted({c["fecha"][:7] for c in filas(con, cid, "compras_proveedor") if c["moneda"] == "USD"})
    if meses_usd:
        for v in (0, 8):
            s = simular(con, cid, meses_usd[-1], v)
            sims[v] = {"periodo": s.get("periodo"), "base_cop": s.get("base_cop"), "simulado_cop": s.get("simulado_cop"), "diferencia_cop": s.get("diferencia_cop")}
    tab = consultas.tablero(con, cid, "gerencia")
    opps = consultas.tablero(con, cid, "ventas")["oportunidades"][:10]
    return {"cierre": res["cierre"], "resumen": res["resumen"], "por_accion": res["por_accion"], "requieren_revision": res["requieren_revision"],
            "frecuentes": res["frecuentes"], "ultimo_mes": ultimo, "cambios": total["cambios"][-3:] if total else [],
            "mayores_cambios": pan["mayores_cambios"], "segmentos": tab["segmentos"], "oportunidades": opps,
            "escenarios": sims, "calidad": res.get("calidad"), "modelos": res.get("modelos"), "pqrs": pqrs.indicadores(con)["por_estado"]}


def _html(c: dict, revision: int, generado_en: str, autor: str) -> str:
    e = html.escape
    filas_accion = "".join(f"<tr><td>{e(a['accion'])}</td><td class=n>{a['clientes']}</td></tr>" for a in c["por_accion"])
    filas_seg = "".join(f"<tr><td>{e(s['segmento'])}</td><td class=n>{s['clientes']}</td><td class=n>{_fmt(s['ingreso_cop'])}</td></tr>" for s in c["segmentos"])
    filas_cam = "".join(f"<tr><td>{e(x['periodo'])}</td><td class=n>{_fmt(x['cambio_cop'])}</td><td class=n>{_fmt(x['cambio_pct'])}</td></tr>" for x in c["cambios"])
    filas_may = "".join(f"<tr><td>{e(x['familia'])}</td><td>{e(x['periodo'])}</td><td class=n>{_fmt(x['cambio_cop'])}</td></tr>" for x in c["mayores_cambios"])
    filas_opp = "".join(f"<tr><td>{e(o['cliente_id'])}</td><td>{e(o['tipo'])}</td><td>{e(', '.join(o['motivos']))}</td></tr>" for o in c["oportunidades"])
    filas_esc = "".join(f"<tr><td>{v:+d} %</td><td>{e(str(s['periodo']))}</td><td class=n>{_fmt(s['base_cop'])}</td><td class=n>{_fmt(s['simulado_cop'])}</td><td class=n>{_fmt(s['diferencia_cop'])}</td></tr>" for v, s in c["escenarios"].items())
    modelos = "".join(f"<li>{e(m.get('nombre', ''))} {e(str(m.get('version', '')))} — {e(str(m.get('limitaciones', '')))}</li>" for m in (c["modelos"] or [])) or "<li>Sin modelo publicado: se usan reglas.</li>"
    calidad = e(dumps(c["calidad"])) if c["calidad"] else "No informada en el manifiesto."
    r = c["resumen"]
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe mensual {e(c['cierre']['corte'])}</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d2a24}}h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #ccd}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #e3e6e4;padding:4px 6px;text-align:left}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
.meta{{color:#566;font-size:12px}}.aviso{{background:#fff6e0;padding:8px;border-radius:6px}}@media print{{body{{margin:0}}}}</style></head><body>
<h1>Informe mensual · cierre {e(c['cierre']['corte'])}</h1>
<p class=meta>Cierre {e(c['cierre']['id'])} (revisión de datos {c['cierre']['revision']}) · origen {e(str(c['cierre']['origen']))} · informe revisión {revision} · generado {e(generado_en)} por {e(autor)}</p>
<p class=aviso>Datos de prueba sintéticos salvo indicación contraria. Las recomendaciones requieren decisión humana.</p>
<h2>Resumen ejecutivo</h2><table><tr><td>Clientes</td><td class=n>{r['clientes']}</td></tr><tr><td>Ventas confirmadas acumuladas</td><td class=n>{r['ventas_confirmadas']}</td></tr>
<tr><td>Ingreso confirmado acumulado (COP)</td><td class=n>{_fmt(r['ingreso_cop'])}</td></tr><tr><td>Clientes fríos</td><td class=n>{r['clientes_frios']}</td></tr>
<tr><td>Clientes frecuentes (pueden ser también fríos)</td><td class=n>{c['frecuentes']}</td></tr><tr><td>Clientes que requieren revisión</td><td class=n>{c['requieren_revision']}</td></tr></table>
<h2>Agenda por acción</h2><table>{filas_accion}</table>
<h2>Variaciones de ventas (Total, COP)</h2><table><tr><th>Mes</th><th class=n>Cambio COP</th><th class=n>Cambio %</th></tr>{filas_cam or '<tr><td colspan=3>Sin serie publicada.</td></tr>'}</table>
<h2>Mayores cambios por familia</h2><table><tr><th>Familia</th><th>Mes</th><th class=n>Cambio COP</th></tr>{filas_may or '<tr><td colspan=3>Sin datos.</td></tr>'}</table>
<h2>Segmentos</h2><table><tr><th>Segmento</th><th class=n>Clientes</th><th class=n>Ingreso COP</th></tr>{filas_seg}</table>
<h2>Oportunidades prioritarias</h2><table><tr><th>Cliente</th><th>Tipo</th><th>Motivos</th></tr>{filas_opp or '<tr><td colspan=3>Sin oportunidades.</td></tr>'}</table>
<h2>Exposición cambiaria (compras en USD)</h2><table><tr><th>Escenario</th><th>Periodo</th><th class=n>Base COP</th><th class=n>Simulado COP</th><th class=n>Diferencia COP</th></tr>{filas_esc or '<tr><td colspan=5>Sin exposición USD publicada.</td></tr>'}</table>
<p class=meta>Indicador: variación del costo de adquisición. El margen requiere costos atribuibles y trazabilidad compra-venta.</p>
<h2>PQRS por estado</h2><p>{e(', '.join(f'{k}: {v}' for k, v in c['pqrs'].items()))}</p>
<h2>Calidad de datos</h2><p class=meta>{calidad}</p>
<h2>Modelos y limitaciones</h2><ul>{modelos}</ul></body></html>"""


def generar_informe(db: BaseDatos, usuario, cierre_ref: str) -> dict:
    with db.conexion() as con:
        contenido = _contenido_informe(con, cierre_ref)
    huella = hashlib.sha256(dumps(contenido).encode()).hexdigest()
    cid = contenido["cierre"]["id"]
    with db.transaccion() as con:
        previo = con.execute("SELECT id, revision, generado_en FROM informes WHERE cierre_id = ? AND huella_contenido = ?", (cid, huella)).fetchone()
        if previo:
            return {"cierre_id": cid, "revision": previo["revision"], "huella": huella, "reutilizado": True, "generado_en": previo["generado_en"]}
        rev = con.execute("SELECT coalesce(max(revision), 0) + 1 FROM informes WHERE cierre_id = ?", (cid,)).fetchone()[0]
        gen = ahora()
        con.execute("INSERT INTO informes (cierre_id, revision, huella_contenido, html, generado_por, generado_en) VALUES (?,?,?,?,?,?)",
                    (cid, rev, huella, _html(contenido, rev, gen, usuario.id), usuario.id, gen))
        auditar(con, usuario.id, "informe.generar", cid, "ok", str(rev), {"huella": huella})
        return {"cierre_id": cid, "revision": rev, "huella": huella, "reutilizado": False, "generado_en": gen}


def listar_informes(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, cierre_id, revision, huella_contenido, generado_por, generado_en FROM informes ORDER BY generado_en DESC")]


def html_informe(con, cierre_id: str, revision: int) -> str:
    r = con.execute("SELECT html FROM informes WHERE cierre_id = ? AND revision = ?", (cierre_id, revision)).fetchone()
    if not r:
        raise ErrorApi(404, "informe_no_encontrado", "Informe no encontrado")
    return r[0]
