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
    return {"cierre": {"id": cierre["id"], "corte": cierre["corte"], "publicado_en": cierre["publicado_en"], "origen": cierre["origen"]},
            "serie": serie, "unidad": "COP",
            "agregacion": "mensual por familia; 'Total' publicado por A (no se suma en la vista)",
            "familias": salida, "mayores_cambios": mayores, "disponible": bool(datos),
            "comparacion": consultas.comparacion_mensual(datos),
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
    nombres = {c["proveedor_id"]: c.get("proveedor") or c["proveedor_id"] for c in compras}
    detalle = [{"familia": f, "proveedor_id": p, "proveedor": nombres.get(p, p), "costo_base_cop": round(b, 2),
                "costo_escenario_cop": round(e, 2), "diferencia_cop": round(e - b, 2)} for (f, p), (b, e) in sorted(grupos.items())]
    incluidas = [{"compra_id": c["compra_id"], "fecha": c["fecha"], "proveedor": c.get("proveedor") or c["proveedor_id"],
                  "familia": c.get("familia"), "cantidad": c["cantidad"], "costo_unitario": c["costo_unitario"], "moneda": c["moneda"],
                  "tasa": c["tasa"], "costo_base_cop": round(c["cantidad"] * c["costo_unitario"] * c["tasa"], 2)}
                 for c in expuestas if c.get("tasa")]
    en_pesos = [{"compra_id": c["compra_id"], "fecha": c["fecha"], "proveedor": c.get("proveedor") or c["proveedor_id"],
                 "familia": c.get("familia"), "importe_cop": c["importe_cop"]} for c in compras if c["moneda"] == "COP"]
    base = round(sum(d["costo_base_cop"] for d in detalle), 2)
    simul = round(sum(d["costo_escenario_cop"] for d in detalle), 2)
    estado = ("parcial" if sin_tasa else "ok") if detalle else ("sin_tasa" if sin_tasa else "sin_exposicion")
    return {"estado": estado, "fuente": "compras_proveedor", "cierre": cierre["id"], "periodo": periodo,
            "moneda": moneda, "variacion_pct": v, "base_cop": base, "simulado_cop": simul, "diferencia_cop": round(simul - base, 2),
            "componente_cop_sin_cambio": cop, "total_base_cop": round(base + cop, 2), "total_simulado_cop": round(simul + cop, 2),
            "operaciones_sin_tasa": sin_tasa, "operaciones_incluidas": incluidas, "compras_en_pesos": en_pesos,
            "detalle": detalle, "supuestos": supuestos,
            "indicador": "variación del costo de adquisición (no margen)",
            "nota": "El escenario no modifica el cierre publicado."}


def _fmt(x) -> str:
    if x is None:
        return "—"
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _mes(periodo) -> str:
    if not periodo:
        return "—"
    a, m = str(periodo)[:7].split("-")
    return f"{MESES[int(m) - 1]} de {a}"


def _fecha_larga(f) -> str:
    if not f:
        return "—"
    a, m, d = str(f)[:10].split("-")
    return f"{int(d)} de {MESES[int(m) - 1]} de {a}"


def _millones(x) -> str:
    """Cifra legible: millones con dos decimales desde 1 millón; importe completo por debajo."""
    if x is None:
        return "—"
    if abs(x) >= 1_000_000:
        return f"{x / 1_000_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " millones de COP"
    return f"{x:,.0f}".replace(",", ".") + " COP"


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
    # La serie completa se guarda con el contenido: la revisión es reproducible sin volver a consultar el cierre.
    serie = [{"periodo": s["periodo"], "valor_cop": s["valor_cop"], "completo": s.get("completo", True)}
             for s in (total["historico"] if total else [])]
    return {"cierre": res["cierre"], "resumen": res["resumen"], "por_accion": res["por_accion"], "requieren_revision": res["requieren_revision"],
            "frecuentes": res["frecuentes"], "ultimo_mes": ultimo, "cambios": total["cambios"][-3:] if total else [],
            "comparacion": tab["comparacion"], "serie_total": serie,
            "mayores_cambios": pan["mayores_cambios"], "segmentos": tab["segmentos"], "oportunidades": opps,
            "escenarios": sims, "calidad": res.get("calidad"), "modelos": res.get("modelos"), "pqrs": pqrs.indicadores(con)["por_estado"]}


def _barras_html(filas_barras: list[tuple[str, float, str]]) -> str:
    """Barras horizontales imprimibles: etiqueta, valor y texto del valor siempre visibles."""
    maximo = max((abs(v) for _, v, _ in filas_barras), default=0) or 1
    e = html.escape
    return "<div class=barras>" + "".join(
        f"<div class=barra><span class=et>{e(et)}</span><span class=pista><span class=relleno style='width:{abs(v) / maximo * 100:.1f}%'></span></span>"
        f"<span class=val>{e(txt)}</span></div>" for et, v, txt in filas_barras) + "</div>"


def _signo(x) -> str:
    return ("−" if x < 0 else "+") + _millones(abs(x))


def _html(c: dict, revision: int, generado_en: str, autor: str) -> str:
    e = html.escape
    corte = c["cierre"]["corte"]
    r = c["resumen"]
    comp = c.get("comparacion") or {}
    ref_cierre = f"Datos del cierre: incluye información hasta el {_fecha_larga(corte)}."
    ref_generacion = f"Estado en el momento de generar el informe ({e(generado_en[:16].replace('T', ' '))})."
    # 1. Qué cambió y dónde se concentra
    if comp.get("estado") == "ok":
        dif = comp["diferencia"]
        verbo = "disminución" if dif < 0 else "aumento"
        cambio = (f"<p class=frase><strong>En {e(_mes(comp['mes']))} se confirmaron ventas por {e(_millones(comp['valor']))}.</strong> "
                  f"En {e(_mes(comp['mes_anterior']))} fueron {e(_millones(comp['valor_anterior']))}. "
                  f"La {verbo} fue de {e(_millones(abs(dif)))}. "
                  f"El ingreso acumulado de la cartera hasta el {e(_fecha_larga(corte))} fue de {e(_millones(r['ingreso_cop']))}.</p>")
        fams = [f for f in comp["familias"] if f["familia"] != "Total" and f["diferencia"] is not None]
        if fams:
            top = fams[0]
            donde = (f"<p><strong>Dónde se concentra.</strong> Las ventas de la familia {e(top['familia'])} "
                     f"{'disminuyeron' if top['diferencia'] < 0 else 'aumentaron'} {e(_millones(abs(top['diferencia'])))} "
                     f"entre {e(_mes(comp['mes_anterior']))} y {e(_mes(comp['mes']))}. Explicar la causa comercial requiere evidencia adicional.</p>"
                     + _barras_html([(f["familia"], f["diferencia"], _signo(f["diferencia"])) for f in fams]))
        else:
            donde = "<p>No hay series por familia para el mismo par de meses.</p>"
    else:
        cambio = (f"<p class=frase><strong>No hay dos meses completos para comparar.</strong> "
                  f"El ingreso acumulado hasta el {e(_fecha_larga(corte))} fue de {e(_millones(r['ingreso_cop']))}.</p>")
        donde = ""
    if comp.get("meses_incompletos"):
        cambio += f"<p class=meta>Meses incompletos excluidos de la comparación: {e(', '.join(_mes(m) for m in comp['meses_incompletos']))}.</p>"
    # 2. Qué merece revisión
    revision_html = (f"<p><strong>{c['requieren_revision']} de {r['clientes']} clientes requieren revisión.</strong> "
                     "Clientes por acción principal sobre toda la cartera:</p>"
                     + _barras_html([(a["accion"], a["clientes"], f"{a['clientes']} clientes") for a in c["por_accion"]]))
    filas_accion = "".join(f"<tr><td>{e(a['accion'])}</td><td class=n>{a['clientes']}</td></tr>" for a in c["por_accion"])
    filas_seg = "".join(f"<tr><td>{e(s['segmento'])}</td><td class=n>{s['clientes']}</td><td class=n>{_fmt(s['ingreso_cop'])}</td></tr>" for s in c["segmentos"])
    filas_serie = "".join(f"<tr><td>{e(_mes(x['periodo']))}</td><td class=n>{'Sin dato (mes incompleto)' if x['valor_cop'] is None else _fmt(x['valor_cop'])}</td></tr>" for x in c.get("serie_total", []))
    filas_comp = "".join(f"<tr><td>{e(f['familia'])}</td><td class=n>{_fmt(f['valor_anterior'])}</td><td class=n>{_fmt(f['valor'])}</td><td class=n>{_fmt(f['diferencia'])}</td></tr>" for f in comp.get("familias", []))
    filas_may = "".join(f"<tr><td>{e(x['familia'])}</td><td>{e(_mes(x['periodo']))}</td><td class=n>{_fmt(x['cambio_cop'])}</td></tr>" for x in c["mayores_cambios"])
    filas_opp = "".join(f"<tr><td>{e(o['cliente_id'])}</td><td>{e(o.get('accion') or o['tipo'])}</td><td>{e(', '.join(o['motivos']))}</td>"
                        f"<td>{e(_fecha_larga(o.get('fecha_sugerida')))}</td></tr>" for o in c["oportunidades"])
    filas_esc = "".join(f"<tr><td>{v:+d} %</td><td>{e(_mes(s['periodo']))}</td><td class=n>{_fmt(s['base_cop'])}</td><td class=n>{_fmt(s['simulado_cop'])}</td><td class=n>{_fmt(s['diferencia_cop'])}</td></tr>" for v, s in c["escenarios"].items())
    modelos = "".join(f"<li>{e(m.get('nombre', ''))} {e(str(m.get('version', '')))} — {e(str(m.get('limitaciones', '')))}</li>" for m in (c["modelos"] or [])) or "<li>Sin modelo publicado: se usan reglas.</li>"
    cal = c["calidad"]
    if cal:
        calidad = (f"Filas leídas {cal.get('filas_leidas', '—')}, aceptadas {cal.get('aceptadas', '—')}, duplicadas {cal.get('duplicadas', '—')}, "
                   f"aisladas {cal.get('aisladas', '—')}." + (" " + " ".join(e(str(n)) for n in cal.get("notas", [])) if cal.get("notas") else ""))
    else:
        calidad = "No informada en el manifiesto."
    esc8 = c["escenarios"].get(8)
    escenario_frase = (f"<p>Si el dólar subiera 8 %, las compras en dólares de {e(_mes(esc8['periodo']))} pasarían de {e(_millones(esc8['base_cop']))} "
                       f"a {e(_millones(esc8['simulado_cop']))}: {e(_millones(esc8['diferencia_cop']))} más. Es un escenario hipotético, no un resultado.</p>"
                       if esc8 and esc8.get("base_cop") is not None else "<p>Sin exposición en dólares publicada.</p>")
    pqrs_txt = ", ".join(f"{k.replace('_', ' ')}: {v}" for k, v in c["pqrs"].items())
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Informe mensual · {e(_mes(corte))}</title>
<style>body{{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1d2a24}}h1{{font-size:22px}}h2{{font-size:16px;margin-top:28px;border-bottom:1px solid #ccd}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #e3e6e4;padding:4px 6px;text-align:left}}.n{{text-align:right;font-variant-numeric:tabular-nums}}
.meta,.ref{{color:#566;font-size:12px}}.ref{{font-style:italic}}.aviso{{background:#fff6e0;padding:8px;border-radius:6px}}.frase{{font-size:16px}}
.barras{{display:grid;gap:4px;margin:8px 0}}.barra{{display:grid;grid-template-columns:minmax(120px,30%) 1fr minmax(140px,auto);gap:8px;align-items:center}}
.pista{{background:#eef0ee;height:14px;border-radius:3px;overflow:hidden}}.relleno{{display:block;height:100%;background:#2a78d6;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.val{{font-variant-numeric:tabular-nums;text-align:right}}.anexo{{margin-top:40px;border-top:3px double #ccd}}
@media print{{body{{margin:0}}.anexo{{break-before:page}}}}</style></head><body>
<h1>Informe mensual · {e(_mes(corte))}</h1>
<p class=meta>Cierre {e(c['cierre']['id'])} (revisión de datos {c['cierre']['revision']}) · corte {e(corte)} · origen {e(str(c['cierre']['origen']))} · informe revisión {revision} · generado {e(generado_en)} por {e(autor)} · unidad: pesos colombianos (COP)</p>
<p class=aviso>Datos de prueba sintéticos salvo indicación contraria. Las recomendaciones requieren decisión humana. Los hechos confirmados se distinguen de las estimaciones y los escenarios.</p>
<h2>Qué cambió</h2><p class=ref>{ref_cierre} Fuente: series mensuales publicadas (hechos confirmados).</p>{cambio}
<h2>Dónde se concentra la variación</h2><p class=ref>{ref_cierre}</p>{donde or '<p>Sin comparación disponible.</p>'}
<h2>Qué merece revisión</h2><p class=ref>{ref_cierre} Fuente: agenda del cierre (reglas y modelo; recomendaciones, no ventas).</p>{revision_html}
<h2>Escenario cambiario</h2><p class=ref>{ref_cierre} Escenario hipotético.</p>{escenario_frase}
<h2>Solicitudes (PQRS)</h2><p class=ref>{ref_generacion} No corresponde a la fecha del cierre.</p><p>{e(pqrs_txt)}</p>
<section class=anexo><h1>Anexo · tablas y metodología (misma revisión {revision})</h1>
<h2>Indicadores de la cartera</h2><p class=ref>{ref_cierre}</p><table><tr><td>Clientes</td><td class=n>{r['clientes']}</td></tr><tr><td>Ventas confirmadas acumuladas</td><td class=n>{r['ventas_confirmadas']}</td></tr>
<tr><td>Ingreso confirmado acumulado (COP)</td><td class=n>{_fmt(r['ingreso_cop'])}</td></tr><tr><td>Clientes fríos (90 días o más sin comprar al cierre)</td><td class=n>{r['clientes_frios']}</td></tr>
<tr><td>Clientes frecuentes (pueden ser también fríos)</td><td class=n>{c['frecuentes']}</td></tr><tr><td>Clientes que requieren revisión</td><td class=n>{c['requieren_revision']}</td></tr></table>
<h2>Serie mensual de ventas confirmadas (Total, COP)</h2><p class=ref>{ref_cierre} Serie guardada con esta revisión.</p><table><tr><th>Mes</th><th class=n>COP</th></tr>{filas_serie or '<tr><td colspan=2>Sin serie publicada.</td></tr>'}</table>
<h2>Comparación por familia ({e(_mes(comp.get('mes_anterior')))} → {e(_mes(comp.get('mes')))})</h2><table><tr><th>Familia</th><th class=n>Mes anterior</th><th class=n>Último mes completo</th><th class=n>Diferencia</th></tr>{filas_comp or '<tr><td colspan=4>Sin datos.</td></tr>'}</table>
<h2>Mayores cambios del histórico por familia</h2><p class=meta>Pueden corresponder a meses distintos.</p><table><tr><th>Familia</th><th>Mes</th><th class=n>Cambio COP</th></tr>{filas_may or '<tr><td colspan=3>Sin datos.</td></tr>'}</table>
<h2>Agenda por acción</h2><table>{filas_accion}</table>
<h2>Segmentos</h2><table><tr><th>Segmento</th><th class=n>Clientes</th><th class=n>Ingreso COP</th></tr>{filas_seg}</table>
<h2>Oportunidades prioritarias (hasta 10)</h2><table><tr><th>Cliente</th><th>Acción</th><th>Motivos</th><th>Fecha sugerida</th></tr>{filas_opp or '<tr><td colspan=4>Sin oportunidades.</td></tr>'}</table>
<h2>Exposición cambiaria (compras en USD)</h2><table><tr><th>Escenario</th><th>Mes</th><th class=n>Base COP</th><th class=n>Simulado COP</th><th class=n>Diferencia COP</th></tr>{filas_esc or '<tr><td colspan=5>Sin exposición USD publicada.</td></tr>'}</table>
<p class=meta>Indicador: variación del costo de adquisición. El margen requiere costos atribuibles y trazabilidad compra-venta.</p>
<h2>Calidad de datos</h2><p class=meta>{calidad}</p>
<h2>Modelos y limitaciones</h2><ul>{modelos}</ul></section></body></html>"""


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
    salida = []
    for r in con.execute("""SELECT i.id, i.cierre_id, i.revision, i.huella_contenido, i.generado_por, i.generado_en, c.corte
                            FROM informes i LEFT JOIN cierres c ON c.id = i.cierre_id ORDER BY i.generado_en DESC"""):
        d = dict(r)
        d["estado"] = "disponible"
        d["autor"] = (con.execute("SELECT nombre FROM identidades WHERE id = ?", (r["generado_por"],)).fetchone() or [r["generado_por"]])[0]
        salida.append(d)
    return salida


def html_informe(con, cierre_id: str, revision: int) -> str:
    r = con.execute("SELECT html FROM informes WHERE cierre_id = ? AND revision = ?", (cierre_id, revision)).fetchone()
    if not r:
        raise ErrorApi(404, "informe_no_encontrado", "Informe no encontrado")
    return r[0]
