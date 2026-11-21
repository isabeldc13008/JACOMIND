"""Adaptador B ← A: construye una publicación C2 (con agenda C1) a partir de las
funciones del paquete ``pipeline`` del carril A.

La rama de A expone funciones (A01–A09) pero no un generador ``pipeline.generar``.
Este adaptador vive en el lado de B, no modifica ``pipeline/`` y solo traduce sus
resultados al contrato. Si A añade ``pipeline.generar``, el cierre mensual lo usa
con prioridad.

    python -m api generar-desde-a --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/cierres/oct
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from contratos.agenda import ORDEN_ACCION, motivos

# Último día cuya etiqueta a 30 días quedó observada en la evaluación de A04
# (prueba julio–septiembre de 2026). Antes de esta fecha no hay modelo validado.
MODELO_DISPONIBLE_DESDE = date(2026, 10, 30)
TIPO_POR_ACCION = {"Revisar reactivación": "reactivacion", "Revisar cobertura": "renovacion",
                   "Revisar oportunidad de recompra": "recompra", "Revisar primera compra": "primera_compra"}


def disponible() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in
               ("pipeline", "pipeline.operaciones", "pipeline.ficha", "pipeline.modelo_compra", "pipeline.segmentacion"))


def _f(x) -> float:
    return round(float(x), 2)


def _iso(x):
    return x.isoformat() if isinstance(x, (date, datetime)) else x


def _escribir(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def generar(datos: str | Path, corte: str, salida: str | Path) -> dict:
    """Genera ``salida/`` con manifiesto.json, agenda.json y tablas C2. Devuelve el manifiesto."""
    from pipeline import modelo_compra as mc
    from pipeline.ficha import construir_ficha
    from pipeline.operaciones import _load, _rates, calcular_cierre
    from pipeline.segmentacion import segmentar_clientes

    raiz = Path(datos)
    dir_datos = raiz / "01_Datos" if (raiz / "01_Datos").is_dir() else raiz
    cut = date.fromisoformat(corte)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    # A01: validación del lote (si falla de forma bloqueante, no se publica).
    calidad: dict = {"notas": []}
    if importlib.util.find_spec("pipeline.carga") is not None:
        from pipeline.carga import cargar_lote
        lote = cargar_lote(raiz, salida / "a01")
        calidad["a01_estado"] = lote.status
        calidad["a01_tablas"] = lote.inventory
        if lote.status == "fallido":
            raise RuntimeError(f"A01 rechazó el lote ({len(lote.issues)} incidencias); ver {salida / 'a01' / 'incidencias.jsonl'}")

    clientes = _load(raiz, "clientes.csv", "clientes")
    ventas = _load(raiz, "ventas.csv", "ventas")
    compras = _load(raiz, "compras.csv", "compras")
    productos = {str(p["producto_id"]): p for p in _load(raiz, "productos.csv", "productos")}
    instalaciones = _load(raiz, "base_instalada.csv", "instalaciones")
    tasas = _rates(raiz)

    # A02: importes por operación con la política de redondeo de A.
    cierre = calcular_cierre(raiz, cut)
    venta_por_id = {str(v["venta_id"]): v for v in ventas}
    compra_por_id = {str(c["compra_id"]): c for c in compras}
    historial = []
    for r in cierre.sales.rows:
        if r.get("status") != "Confirmada":
            continue
        v = venta_por_id[str(r["id"])]
        p = productos.get(str(v["producto_id"]), {})
        historial.append({"venta_id": str(r["id"]), "cliente_id": str(v["cliente_id"]), "producto_id": str(v["producto_id"]),
                          "producto": p.get("nombre_prueba"), "familia": r["family"], "fecha": _iso(v["fecha"]),
                          "cantidad": int(v["cantidad"]), "moneda": v["moneda"],
                          "tasa": _f(tasas[v["fecha"]]) if v["moneda"] == "USD" else None,
                          "importe_cop": _f(r["amount_cop"]), "estado": "Confirmada"})
    compras_prov = []
    for r in cierre.purchases.rows:
        if r.get("status") != "Confirmada":
            continue
        c = compra_por_id[str(r["id"])]
        compras_prov.append({"compra_id": str(r["id"]), "fecha": _iso(c["fecha"]), "proveedor_id": str(c["proveedor_id"]),
                             "producto_id": str(c["producto_id"]), "familia": r["family"], "cantidad": int(c["cantidad"]),
                             "moneda": c["moneda"], "costo_unitario": float(c["costo_unitario"]),
                             "tasa": _f(tasas[c["fecha"]]) if c["moneda"] == "USD" else None, "importe_cop": _f(r["amount_cop"])})
    if cierre.sales.missing_rates:
        calidad["notas"].append(f"Ventas aisladas por TRM faltante: {len(cierre.sales.missing_rates)}")
    calidad["anomalias_a02"] = len(cierre.anomalies)

    # A03: ficha 360° (importe por operación ya redondeado, igual que A02).
    ficha = construir_ficha(clientes, [dict(v, importe_cop=Decimal(str(h["importe_cop"])))
                                       for h in historial for v in [venta_por_id[h["venta_id"]]]], instalaciones, cut)

    # A04: modelo de compra a 30 días; inferencia en el corte con la transformación guardada.
    modelo_info, probs = None, {}
    if cut >= MODELO_DISPONIBLE_DESDE:
        ev = mc.entrenar_y_evaluar_desde_paquete(raiz)
        fotos = mc.construir_fotografias(clientes, ventas, cut)
        for fila in fotos:
            if fila["historial_n"] > 0:
                probs[fila["cliente_id"]] = round(mc._probability(fila, ev["medias"], ev["desviaciones"], ev["pesos"]), 6)
        modelo_info = {"version": "A04-logistica-reglas-v1", "umbral": ev["umbral"], "evaluacion": {
            k: ev[k] for k in ("validacion", "prueba_modelo", "prueba_linea_base", "observaciones")}}
    else:
        calidad["notas"].append("Sin modelo validado para este corte: probabilidad nula y agenda por reglas.")

    # A05: segmentación RFM.
    segs = segmentar_clientes([{"cliente_id": f["cliente_id"], "recencia_dias": f["recencia_dias"],
                                "frecuencia": f["frecuencia_operaciones"], "importe": f["valor_monetario_cop"]} for f in ficha])

    # C1: agenda.
    umbral = modelo_info["umbral"] if modelo_info else None
    filas = []
    for f in ficha:
        sin = f["ultima_compra"] is None
        prob = None if sin else probs.get(f["cliente_id"])
        c = {"cliente_id": f["cliente_id"], "ultima_compra": _iso(f["ultima_compra"]), "dias_sin_compra": f["dias_sin_compra"],
             "ventas_confirmadas": f["frecuencia_operaciones"], "ingreso_cop": _f(f["valor_monetario_cop"]),
             "productos": sorted({productos[p]["nombre_prueba"] for p in f["productos_historicos"] if p in productos}),
             "frecuente": f["frecuente"], "frio": f["frio"], "renovaciones_proximas": f["coberturas_proximas"],
             "coberturas_vencidas": f["coberturas_vencidas"], "prob_compra_30d": prob,
             "segmento": segs.get(f["cliente_id"], {}).get("segmento")}
        if c["frio"]:
            c["accion"] = "Revisar reactivación"
        elif c["renovaciones_proximas"] or c["coberturas_vencidas"]:
            c["accion"] = "Revisar cobertura"
        elif prob is not None and umbral is not None and prob >= umbral:
            c["accion"] = "Revisar oportunidad de recompra"
        elif sin:
            c["accion"] = "Revisar primera compra"
        else:
            c["accion"] = "Seguimiento habitual"
        c["motivos"] = motivos(c, umbral)
        filas.append(c)
    agenda = {"version": 1, "corte": corte, "origen": "sintetico", "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "modelo": {"version": modelo_info["version"], "umbral": umbral} if modelo_info else None,
              "resumen": {"clientes": len(filas), "ventas_confirmadas": sum(c["ventas_confirmadas"] for c in filas),
                          "ingreso_cop": _f(sum(Decimal(str(c["ingreso_cop"])) for c in filas)),
                          "clientes_frios": sum(c["frio"] for c in filas)},
              "clientes": filas}

    # Coberturas, oportunidades y segmentos.
    coberturas = []
    for f in ficha:
        for cb in f["coberturas"]:
            inst = next(i for i in instalaciones if i["instalacion_id"] == cb["instalacion_id"])
            coberturas.append({"instalacion_id": cb["instalacion_id"], "cliente_id": f["cliente_id"], "producto_id": str(cb["producto_id"]),
                               "producto": productos.get(str(cb["producto_id"]), {}).get("nombre_prueba"),
                               "fecha_inicio": _iso(inst["fecha_inicio"]), "fecha_fin": _iso(cb["fecha_fin"]),
                               "estado": "proxima" if cb["proxima"] else cb["estado"], "dias_para_fin": (cb["fecha_fin"] - cut).days,
                               "unidades": int(inst.get("unidades") or 0)})
    oportunidades = []
    for c in filas:
        if c["accion"] == "Seguimiento habitual":
            continue
        tipo = TIPO_POR_ACCION[c["accion"]]
        oportunidades.append({"oportunidad_id": f"{c['cliente_id']}:{tipo}", "episodio_id": f"{c['cliente_id']}:{tipo}",
                              "cliente_id": c["cliente_id"], "producto_id": None, "tipo": tipo, "motivos": c["motivos"],
                              "prioridad": ORDEN_ACCION[c["accion"]], "probabilidad": c["prob_compra_30d"],
                              "evidencia": {k: c[k] for k in ("dias_sin_compra", "renovaciones_proximas", "coberturas_vencidas", "prob_compra_30d")},
                              "fecha_sugerida": (cut + timedelta(days=7)).isoformat(), "version_regla": "agenda-c1-v1"})
    calidad["notas"].append("Venta cruzada (A07) no publicada: falta soporte mínimo evaluado frente a popularidad.")
    segmentos = [{"cliente_id": k, "segmento": v["segmento"], "version": v["version"]} for k, v in sorted(segs.items())]

    # Series mensuales (A02 agregados) y proyección (A08, media móvil).
    tablas_series = _series(historial, compras_prov, cut)

    # Escenarios de TRM (A09) sobre el último mes con compras en USD.
    escenarios = _escenarios(compras_prov)

    tablas = {"agenda": agenda, "historial_ventas": historial, "coberturas": coberturas, "compras_proveedor": compras_prov,
              "series_mensuales": tablas_series, "escenarios_trm": escenarios, "oportunidades": oportunidades, "segmentos": segmentos}
    declaradas = {}
    for nombre, contenido in tablas.items():
        _escribir(salida / f"{nombre}.json", contenido)
        declaradas[nombre] = {"archivo": f"{nombre}.json", "filas": len(contenido["clientes"]) if nombre == "agenda" else len(contenido)}
    declaradas["historial_ventas"]["sumas"] = {"importe_cop": _f(sum(Decimal(str(h["importe_cop"])) for h in historial))}
    huellas = {p.name: _sha(p) for p in sorted(dir_datos.glob("*.csv")) if "OPCIONAL" not in p.name}
    manifiesto = {"version": 1, "tipo": "publicacion_analitica", "cierre_id": f"a-{corte}-{hashlib.sha256(json.dumps(huellas, sort_keys=True).encode()).hexdigest()[:10]}",
                  "corte": corte, "origen": "sintetico", "generado_en": agenda["generado_en"], "huellas_entrada": huellas,
                  "versiones": {"reglas": "agenda-c1-v1", "modelo_compra": modelo_info["version"] if modelo_info else None,
                                "segmentacion": "rfm-v1", "pronostico": "media_movil_3"},
                  "tablas": declaradas, "calidad": calidad,
                  "modelos": [{"nombre": "compra_30d", "version": modelo_info["version"], "umbral": umbral,
                               "metricas_prueba": modelo_info["evaluacion"]["prueba_modelo"],
                               "referencia": {"nombre": "compra en últimos 30 días", **modelo_info["evaluacion"]["prueba_linea_base"]},
                               "limitaciones": "Datos sintéticos. Mide propensión de compra, no efecto causal del contacto."}] if modelo_info else []}
    _escribir(salida / "manifiesto.json", manifiesto)
    return manifiesto


def _series(historial: list[dict], compras: list[dict], cut: date) -> list[dict]:
    from pipeline.pronostico import pronosticar_media_movil
    agg: dict = defaultdict(lambda: [Decimal("0"), 0, 0])
    for serie, filas in (("ventas", historial), ("compras", compras)):
        for f in filas:
            for fam in (f["familia"], "Total"):
                a = agg[(f["fecha"][:7], fam, serie)]
                a[0] += Decimal(str(f["importe_cop"])); a[1] += f["cantidad"]; a[2] += 1
    meses = sorted({k[0] for k in agg})
    if not meses:
        return []
    y, m = map(int, meses[0].split("-"))
    calendario = []
    while (y, m) <= (cut.year, cut.month):
        calendario.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    salida = []
    for serie in ("ventas", "compras"):
        familias = sorted({k[1] for k in agg if k[2] == serie})
        for fam in familias:
            valores = []
            for per in calendario:
                v = agg.get((per, fam, serie))
                valores.append(v[0] if v else Decimal("0"))
                salida.append({"periodo": per, "familia": fam, "serie": serie, "tipo": "historico",
                               "valor_cop": _f(v[0]) if v else 0.0, "unidades": v[1] if v else 0,
                               "operaciones": v[2] if v else 0, "completo": True})
            y2, m2 = cut.year, cut.month
            for h, valor in enumerate(pronosticar_media_movil(valores, 3, 3), start=1):
                y2, m2 = (y2 + 1, 1) if m2 == 12 else (y2, m2 + 1)
                salida.append({"periodo": f"{y2}-{m2:02d}", "familia": fam, "serie": serie, "tipo": "pronostico",
                               "valor_cop": _f(valor), "metodo": "media_movil_3 (A08)", "horizonte": h, "mae": None,
                               "sesgo": None, "calculado_en": cut.isoformat()})
    return salida


def _escenarios(compras: list[dict]) -> list[dict]:
    from pipeline.cambiario import simular_exposicion
    usd = [c for c in compras if c["moneda"] == "USD" and c.get("tasa")]
    if not usd:
        return []
    periodo = max(c["fecha"][:7] for c in usd)
    grupos: dict = defaultdict(list)
    for c in usd:
        if c["fecha"].startswith(periodo):
            grupos[(c["familia"], c["proveedor_id"])].append({"usd": str(c["cantidad"] * c["costo_unitario"]), "trm": str(c["tasa"])})
    salida = []
    for pct in (-8, 0, 8):
        for (fam, prv), filas in sorted(grupos.items()):
            r = simular_exposicion(filas, Decimal(pct) / 100)
            salida.append({"escenario_id": f"trm{pct:+d}", "periodo": periodo, "moneda": "USD", "variacion_pct": pct, "familia": fam,
                           "proveedor_id": prv, "costo_base_cop": _f(r["base_cop"]), "costo_escenario_cop": _f(r["escenario_cop"]),
                           "diferencia_cop": _f(r["diferencia_cop"])})
    return salida
