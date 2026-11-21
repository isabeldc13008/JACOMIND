"""Regenera las muestras ficticias de contrato de forma determinista.

    python -m contratos.ejemplos.generar_ejemplos

Las muestras viven aquí (no en ``salida/``) y no proceden de ninguna ejecución real.
Empresas de ensayo: EMP-A ↔ cliente DEMO01, EMP-B ↔ cliente DEMO02.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DIR = Path(__file__).resolve().parent
RAIZ = DIR.parents[1]
CORTE = date(2026, 10, 31)

PRODUCTOS = {
    "PRD01": ("Licencia de gestión documental", "Software", "USD", 180.0),
    "PRD02": ("Servicio de respaldo", "Continuidad", "COP", 350000.0),
    "PRD03": ("Mantenimiento de equipos", "Infraestructura", "COP", 420000.0),
    "PRD04": ("Monitoreo de red", "Infraestructura", "COP", 2600000.0),
}
TASA = 4000.0

# cliente: (ventas, ultima_compra, productos, prob, renov, vencidas, accion, segmento)
CLIENTES = [
    ("DEMO01", 9, "2026-08-02", ["PRD02", "PRD03", "PRD01"], 0.31, 1, 0, "Revisar reactivación", "Recurrente en pausa"),
    ("DEMO02", 4, "2026-10-10", ["PRD02", "PRD04"], 0.55, 1, 0, "Revisar cobertura", "Valor alto"),
    ("DEMO03", 6, "2026-10-25", ["PRD03"], 0.72, 0, 0, "Revisar oportunidad de recompra", "Recurrente activo"),
    ("DEMO04", 0, None, [], None, 0, 0, "Revisar primera compra", None),
    ("DEMO05", 2, "2026-09-15", ["PRD01"], 0.0, 0, 0, "Seguimiento habitual", "Ocasional"),
    ("DEMO06", 5, "2026-10-05", ["PRD02", "PRD03"], 0.48, 0, 1, "Revisar cobertura", "Recurrente activo"),
    ("DEMO07", 3, "2026-10-20", ["PRD04"], 0.12, 0, 0, "Seguimiento habitual", "Valor alto"),
    ("DEMO08", 8, "2026-06-30", ["PRD03", "PRD02"], None, 0, 0, "Revisar reactivación", "Recurrente en pausa"),
]
UMBRAL = 0.4


def escribir(ruta: Path, datos) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def construir():
    ventas, filas = [], []
    num = 0
    for cid, n, ultima, prods, prob, renov, venc, accion, _seg in CLIENTES:
        importe_cliente = 0.0
        if n:
            u = date.fromisoformat(ultima)
            for k in range(n):
                num += 1
                pid = prods[k % len(prods)]
                nombre, familia, moneda, precio = PRODUCTOS[pid]
                cantidad = 1 + (k % 3)
                fecha = u - timedelta(days=23 * k)
                origen = round(cantidad * precio, 2)
                tasa = TASA if moneda == "USD" else None
                cop = round(origen * (tasa or 1), 2)
                importe_cliente += cop
                ventas.append({"venta_id": f"VD{num:04d}", "cliente_id": cid, "producto_id": pid, "producto": nombre,
                               "familia": familia, "fecha": fecha.isoformat(), "cantidad": cantidad, "moneda": moneda,
                               "importe_origen": origen, "tasa": tasa, "importe_cop": cop, "estado": "Confirmada"})
        dias = (CORTE - date.fromisoformat(ultima)).days if ultima else None
        filas.append({"cliente_id": cid, "ultima_compra": ultima, "dias_sin_compra": dias, "ventas_confirmadas": n,
                      "ingreso_cop": round(importe_cliente, 2),
                      "productos": sorted({PRODUCTOS[p][0] for p in prods}) if n else [],
                      "frecuente": n >= 8, "frio": dias is not None and dias >= 90,
                      "renovaciones_proximas": renov, "coberturas_vencidas": venc, "prob_compra_30d": prob,
                      "accion": accion})
    agenda = {"version": 1, "corte": CORTE.isoformat(), "origen": "sintetico",
              "modelo": {"version": "demo-logistica-0", "umbral": UMBRAL},
              "resumen": {"clientes": len(filas), "ventas_confirmadas": sum(f["ventas_confirmadas"] for f in filas),
                          "ingreso_cop": round(sum(f["ingreso_cop"] for f in filas), 2),
                          "clientes_frios": sum(f["frio"] for f in filas)},
              "clientes": filas}
    return agenda, ventas


def coberturas():
    def cob(iid, cid, pid, ini, fin):
        f = date.fromisoformat(fin)
        d = (f - CORTE).days
        estado = "vencida" if d < 0 else ("proxima" if d <= 45 else "vigente")
        return {"instalacion_id": iid, "cliente_id": cid, "producto_id": pid, "producto": PRODUCTOS[pid][0],
                "fecha_inicio": ini, "fecha_fin": fin, "estado": estado, "dias_para_fin": d, "unidades": 1}
    return [
        cob("INSD01", "DEMO01", "PRD02", "2025-12-15", "2026-12-15"),
        cob("INSD02", "DEMO02", "PRD02", "2025-11-20", "2026-11-20"),
        cob("INSD03", "DEMO02", "PRD04", "2026-03-01", "2027-03-01"),
        cob("INSD04", "DEMO06", "PRD03", "2025-09-01", "2026-09-01"),
        cob("INSD05", "DEMO03", "PRD03", "2026-05-01", "2027-05-01"),
    ]


def compras():
    filas = []
    base = [("CD01", "2026-08-12", "PRV01", "PRD02", 10, "COP", 210000.0, None),
            ("CD02", "2026-09-03", "PRV02", "PRD03", 6, "COP", 250000.0, None),
            ("CD03", "2026-10-07", "PRV03", "PRD01", 3, "USD", 100.0, 4000.0),
            ("CD04", "2026-10-15", "PRV01", "PRD02", 4, "COP", 215000.0, None),
            ("CD05", "2026-09-21", "PRV03", "PRD01", 2, "USD", 110.0, 3950.0)]
    for cid, f, prv, pid, q, mon, costo, tasa in base:
        filas.append({"compra_id": cid, "fecha": f, "proveedor_id": prv, "proveedor": f"Proveedor ficticio {prv[-2:]}",
                      "producto_id": pid, "familia": PRODUCTOS[pid][1], "cantidad": q, "moneda": mon,
                      "costo_unitario": costo, "tasa": tasa, "importe_cop": round(q * costo * (tasa or 1), 2)})
    return filas


def series(ventas, compras_):
    agg = defaultdict(lambda: [0.0, 0, 0])
    for serie, filas, campo in (("ventas", ventas, "importe_cop"), ("compras", compras_, "importe_cop")):
        for f in filas:
            per = f["fecha"][:7]
            for fam in (f["familia"], "Total"):
                a = agg[(per, fam, serie)]
                a[0] += f[campo]; a[1] += f["cantidad"]; a[2] += 1
    out = []
    familias = ["Total", "Software", "Continuidad", "Infraestructura"]
    periodos = [f"2026-{m:02d}" for m in range(5, 11)]
    for serie in ("ventas", "compras"):
        for fam in familias:
            ultimo = None
            for per in periodos:
                v = agg.get((per, fam, serie))
                completo = not (serie == "compras" and per == "2026-05")  # mes con ingestión incompleta
                valor = None if not completo else round(v[0], 2) if v else 0.0
                out.append({"periodo": per, "familia": fam, "serie": serie, "tipo": "historico", "valor_cop": valor,
                            "unidades": (v[1] if v else 0) if completo else None,
                            "operaciones": (v[2] if v else 0) if completo else None, "completo": completo})
                if valor is not None:
                    ultimo = valor
            for h, per in enumerate(["2026-11", "2026-12", "2027-01"], start=1):
                out.append({"periodo": per, "familia": fam, "serie": serie, "tipo": "pronostico",
                            "valor_cop": ultimo, "metodo": "ultimo_mes_observado", "horizonte": h,
                            "mae": round((ultimo or 0) * 0.18 * h, 2), "sesgo": 0.0,
                            "calculado_en": CORTE.isoformat()})
    return out


def escenarios(compras_):
    out = []
    usd = [c for c in compras_ if c["moneda"] == "USD" and c["fecha"].startswith("2026-10")]
    for pct in (-8, 0, 8):
        grupos = defaultdict(lambda: [0.0, 0.0])
        for c in usd:
            base = c["cantidad"] * c["costo_unitario"] * c["tasa"]
            g = grupos[(c["familia"], c["proveedor_id"])]
            g[0] += base; g[1] += base * (1 + pct / 100)
        for (fam, prv), (b, e) in sorted(grupos.items()):
            out.append({"escenario_id": f"trm{pct:+d}", "periodo": "2026-10", "moneda": "USD", "variacion_pct": pct,
                        "familia": fam, "proveedor_id": prv, "costo_base_cop": round(b, 2),
                        "costo_escenario_cop": round(e, 2), "diferencia_cop": round(e - b, 2)})
    return out


def oportunidades(agenda):
    tipos = {"Revisar reactivación": "reactivacion", "Revisar cobertura": "renovacion",
             "Revisar oportunidad de recompra": "recompra", "Revisar primera compra": "primera_compra"}
    import sys
    sys.path.insert(0, str(RAIZ))
    from contratos.agenda import ORDEN_ACCION, motivos
    out = []
    for c in agenda["clientes"]:
        if c["accion"] == "Seguimiento habitual":
            continue
        tipo = tipos[c["accion"]]
        out.append({"oportunidad_id": f"OP-{c['cliente_id']}-{tipo}", "episodio_id": f"{c['cliente_id']}:{tipo}",
                    "cliente_id": c["cliente_id"], "producto_id": None, "tipo": tipo,
                    "motivos": motivos(c, UMBRAL), "prioridad": ORDEN_ACCION[c["accion"]],
                    "probabilidad": c["prob_compra_30d"],
                    "evidencia": {"dias_sin_compra": c["dias_sin_compra"], "renovaciones_proximas": c["renovaciones_proximas"],
                                  "coberturas_vencidas": c["coberturas_vencidas"], "prob_compra_30d": c["prob_compra_30d"]},
                    "fecha_sugerida": (CORTE + timedelta(days=7)).isoformat(), "version_regla": "reglas-demo-1"})
    return out


def segmentos():
    desc = {"Recurrente activo": "Compra con regularidad", "Recurrente en pausa": "Historial recurrente con recencia alta",
            "Valor alto": "Pocas operaciones de importe alto", "Ocasional": "Compras esporádicas"}
    return [{"cliente_id": c[0], "segmento": c[8], "descripcion": desc[c[8]], "version": "rfm-demo-1"}
            for c in CLIENTES if c[8]]


def main():
    agenda, ventas = construir()
    ej = DIR / "agenda"
    escribir(ej / "valido.json", agenda)
    escribir(RAIZ / "app" / "fixtures" / "agenda.json", agenda)
    escribir(ej / "vacio.json", {"version": 1, "corte": CORTE.isoformat(), "origen": "sintetico",
                                 "resumen": {"clientes": 0, "ventas_confirmadas": 0, "ingreso_cop": 0, "clientes_frios": 0},
                                 "clientes": []})
    incompleto = copy.deepcopy(agenda)
    del incompleto["clientes"][0]["accion"]
    escribir(ej / "incompleto.json", incompleto)
    incompatible = copy.deepcopy(agenda)
    incompatible["version"] = 2
    escribir(ej / "incompatible.json", incompatible)
    duplicado = copy.deepcopy(agenda)
    duplicado["clientes"][1]["cliente_id"] = duplicado["clientes"][0]["cliente_id"]
    escribir(ej / "id_repetido.json", duplicado)
    tipos = copy.deepcopy(agenda)
    tipos["clientes"][2]["prob_compra_30d"] = "0.7"
    escribir(ej / "tipo_invalido.json", tipos)

    pub = DIR / "publicacion" / "demo-2026-10"
    comp = compras()
    tablas = {
        "agenda": agenda, "historial_ventas": ventas, "coberturas": coberturas(), "compras_proveedor": comp,
        "series_mensuales": series(ventas, comp), "escenarios_trm": escenarios(comp),
        "oportunidades": oportunidades(agenda), "segmentos": segmentos(),
    }
    declaradas = {}
    for nombre, contenido in tablas.items():
        escribir(pub / f"{nombre}.json", contenido)
        filas = len(contenido["clientes"]) if nombre == "agenda" else len(contenido)
        declaradas[nombre] = {"archivo": f"{nombre}.json", "filas": filas}
    declaradas["historial_ventas"]["sumas"] = {"importe_cop": round(sum(v["importe_cop"] for v in ventas), 2)}
    huella = hashlib.sha256(json.dumps(agenda, sort_keys=True).encode()).hexdigest()
    escribir(pub / "manifiesto.json", {
        "version": 1, "tipo": "publicacion_analitica", "cierre_id": "demo-2026-10", "corte": CORTE.isoformat(),
        "origen": "sintetico", "generado_en": "2026-11-01T06:00:00+00:00",
        "huellas_entrada": {"muestra_ficticia": huella},
        "versiones": {"reglas": "reglas-demo-1", "modelo_compra": "demo-logistica-0", "segmentacion": "rfm-demo-1",
                      "pronostico": "ultimo_mes_observado"},
        "tablas": declaradas,
        "calidad": {"filas_leidas": 40, "aceptadas": 37, "duplicadas": 1, "aisladas": 2,
                    "notas": ["Muestra ficticia de contrato; no procede de una ejecución."]},
        "modelos": [{"nombre": "compra_30d", "version": "demo-logistica-0", "umbral": UMBRAL,
                     "metricas_prueba": {"precision": 0.404, "recall": 0.9091, "F1": 0.5594},
                     "referencia": {"nombre": "compra en últimos 30 días", "F1": 0.5368},
                     "limitaciones": "Muestra ficticia. Mide propensión, no efecto causal del contacto."}],
    })

    escribir(DIR / "trabajo" / "eventos.json", {"version": 1, "tipo": "eventos_seguimiento",
        "exportado_en": "2026-11-05T12:00:00+00:00", "eventos": [
            {"evento_id": "EV-1", "tipo": "asignada", "oportunidad_id": "OP-DEMO01-reactivacion",
             "episodio_id": "DEMO01:reactivacion", "cliente_id": "DEMO01", "cierre_id": "demo-2026-10",
             "fecha": "2026-11-02T09:00:00+00:00", "actor": "ventas1", "estado": "asignada", "resultado": None},
            {"evento_id": "EV-2", "tipo": "atendida", "oportunidad_id": "OP-DEMO01-reactivacion",
             "episodio_id": "DEMO01:reactivacion", "cliente_id": "DEMO01", "cierre_id": "demo-2026-10",
             "fecha": "2026-11-04T15:30:00+00:00", "actor": "ventas1", "estado": "atendida",
             "resultado": "contacto_registrado"}]})
    escribir(DIR / "asistencia" / "clasificacion.json", [
        {"categoria": "reclamo", "confianza": 0.86, "version": "simulado-0", "revisar": False, "motivo": None, "responsable": "atencion"},
        {"categoria": "peticion", "confianza": 0.41, "version": "simulado-0", "revisar": True, "motivo": "confianza baja", "responsable": None}])
    print("Muestras regeneradas en", DIR)


if __name__ == "__main__":
    main()
