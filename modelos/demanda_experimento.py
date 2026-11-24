"""M5 · Experimento de demanda (``m5-protocolo-v1``): reproducir A08, preparar, seleccionar en desarrollo, evaluar la
comprobación con la selección congelada, ajustar el procedimiento para un origen nuevo y calcular bandas.

statsmodels solo se importa en ``ajustar_ets`` (entorno analítico). Separación explícita de etapas:
selección del procedimiento (desarrollo, congelada) → reestimación de parámetros en cada origen → emisión del
pronóstico → incorporación posterior del valor real (``modelos.demanda.incorporar_observaciones``).
"""
from __future__ import annotations

import hashlib
import json
import math
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .compra import DependenciaEntrenamiento, ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .demanda import (FAMILIAS, FORMATO, HORIZONTES, METODOS, MODELO_ID, REFERENCIAS, conciliar, construir_series, pron_estado, pron_media_movil_3,
                      pron_ultimo, publicar_valor, sumar_meses, tramo)
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict, sellar

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "demanda.json"
METRICAS_VERSION = "m5-metricas-v1"
MARCADOR_CONGELACION, MARCADOR_EVALUACION = "congelacion.json", "evaluacion.json"
LIMITACIONES = [
    "Datos sintéticos de 22 meses ya inspeccionados: la comprobación (objetivos julio–octubre de 2026) es exploratoria; con 2–4 errores por serie y horizonte no hay evidencia de superioridad estable.",
    "Familias y disponibilidad de productos con convenciones sintéticas (catálogo actual; primera venta observada).",
    "Las proyecciones COP incluyen cambios de precios y de moneda, no solo volumen; no son margen ni predicción de TRM.",
    "Compras a proveedores sin cobertura declarada: no se pronostican.",
]


def _leer(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def cargar_config(ruta: str | Path | None = None) -> dict:
    return _leer(Path(ruta or CONFIG_DEFECTO))


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon({"configuracion": _sin_descriptivas(config), "metricas": METRICAS_VERSION, "formato": FORMATO}).encode()).hexdigest()


# Ajuste --------------------------------------------------------------------------------------------------------------
def ajustar_ets(hist: list[float], metodo: str, config: dict) -> dict:
    """Ajusta SES u Holt amortiguado sobre ``hist`` (escalado por la media absoluta del propio origen) y devuelve el estado
    final persistible, la convergencia y los pronósticos de statsmodels para la verificación de equivalencia."""
    try:
        import numpy as np
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError as exc:
        raise DependenciaEntrenamiento("M5 requiere el entorno analítico: pip install statsmodels==0.15.0 (ver requirements-modelos.txt)") from exc
    if all(v == 0 for v in hist):
        return {"metodo": metodo, "convergio": False, "motivo": "historia toda cero: se usa la referencia"}
    escala = sum(abs(v) for v in hist) / len(hist) or 1.0
    y = np.array(hist, dtype=float) / escala
    a = config["ajuste"]
    lim = {k: tuple(v) for k, v in a["limites"].items()}
    kw = {"trend": "add", "damped_trend": True} if metodo == "holt_amortiguado" else {"trend": None}
    bounds = {k: v for k, v in lim.items() if metodo == "holt_amortiguado" or k == "smoothing_level"}
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        try:
            r = ExponentialSmoothing(y, initialization_method=a["inicializacion"], bounds=bounds, **kw).fit(optimized=True, method="L-BFGS-B", use_brute=True)
        except Exception as exc:  # noqa: BLE001 - se registra y se aplica el respaldo
            return {"metodo": metodo, "convergio": False, "motivo": f"error de ajuste: {type(exc).__name__}: {exc}"[:200]}
    ok = bool(getattr(r.mle_retvals, "success", True)) if r.mle_retvals is not None else True
    nivel, tend = float(r.level[-1]), float(r.trend[-1]) if metodo == "holt_amortiguado" else 0.0
    phi = float(r.params.get("damping_trend") or 1.0) if metodo == "holt_amortiguado" else 1.0
    finitos = all(math.isfinite(x) for x in (nivel, tend, phi))
    est = {"metodo": metodo, "nivel": nivel, "tendencia": tend if metodo == "holt_amortiguado" else None, "amortiguamiento": phi if metodo == "holt_amortiguado" else None,
           "escala": escala, "parametros": {k: (float(v) if v is not None and np.ndim(v) == 0 and not isinstance(v, bool) else None) for k, v in r.params.items()
                                            if k in ("smoothing_level", "smoothing_trend", "damping_trend", "initial_level", "initial_trend")},
           "convergio": ok and finitos, "motivo": None if ok and finitos else ("optimizador sin convergencia" if not ok else "estado no finito"),
           "avisos": sorted({str(w.message)[:160] for w in avisos}), "n_historia": len(hist),
           "statsmodels": [float(x) * escala for x in r.forecast(max(HORIZONTES))]}
    return est


def pronosticar(metodo: str, hist: list[float], h: int, config: dict, cache: dict | None = None) -> dict | None:
    """Pronóstico publicado de ``metodo`` a ``h`` meses o ``None`` si no hay historia suficiente para ese método."""
    if metodo not in METODOS:
        return None
    minimo = config["minimos"]["referencias_meses"] if metodo in REFERENCIAS else config["minimos"]["candidatos_meses"]
    if len(hist) < minimo:
        return None
    sustitucion = None
    if metodo == "ultimo":
        bruto = pron_ultimo(hist, h)
    elif metodo == "media_movil_3":
        bruto = pron_media_movil_3(hist, h)
    else:
        clave = (metodo, len(hist), tuple(hist))
        est = cache.get(clave) if cache is not None else None
        if est is None:
            est = ajustar_ets(hist, metodo, config)
            if cache is not None:
                cache[clave] = est
        if est["convergio"]:
            bruto = pron_estado(est, h)
        else:
            sustitucion = {"metodo_seleccionado": metodo, "motivo": est["motivo"], "respaldo": config["ajuste"]["respaldo"]}
            bruto = pron_media_movil_3(hist, h)
    valor, rec = publicar_valor(bruto)
    return {"bruto": bruto, "valor": round(valor, 2), "recortado": rec, "sustitucion": sustitucion}


# Evaluación por origen -------------------------------------------------------------------------------------------------
def series_modelables(series: dict) -> list[str]:
    return sorted(s for s in series if s.startswith(("ventas_cop:", "ventas_unidades:")))


def filas_origen(series: dict, sid: str, origenes: list[str], config: dict, metodos=METODOS, cache=None, hasta_objetivo: str | None = None) -> list[dict]:
    """Predicción, observado y error por método, origen y horizonte (cada origen usa solo su tramo completo)."""
    cal = series[sid]["calendario"]
    reales = {m["periodo"]: m for m in cal}
    out = []
    for o in origenes:
        hist = tramo(cal, o)
        for h in HORIZONTES:
            obj = sumar_meses(o, h)
            if hasta_objetivo and obj > hasta_objetivo:
                continue
            real = reales.get(obj)
            obs = real["valor"] if real and real["estado"] == "completo" else None
            for m in metodos:
                p = pronosticar(m, hist, h, config, cache)
                if p is None:
                    continue
                out.append({"serie_id": sid, "metodo": m, "origen": o, "horizonte": h, "objetivo": obj, "n_historia": len(hist), "prediccion": p["valor"],
                            "bruto": p["bruto"], "recortado": p["recortado"], "sustitucion": p["sustitucion"], "observado": obs,
                            "error": round(p["valor"] - obs, 6) if obs is not None else None, "estado": "evaluado" if obs is not None else "pendiente"})
    return out


def metricas(filas: list[dict]) -> dict:
    ev = [f for f in filas if f["error"] is not None]
    if not ev:
        return {"n": 0, "mae": None, "wape": None, "sesgo": None, "sesgo_abs_normalizado": None}
    s_obs = sum(f["observado"] for f in ev)
    s_err = sum(f["error"] for f in ev)
    return {"n": len(ev), "mae": sum(abs(f["error"]) for f in ev) / len(ev),
            "wape": sum(abs(f["error"]) for f in ev) / s_obs if s_obs else None,  # observado 0: no disponible, no cero
            "sesgo": s_err / len(ev), "sesgo_abs_normalizado": abs(s_err) / s_obs if s_obs else None,
            "recortes": sum(f["recortado"] for f in ev), "sustituciones": sum(bool(f["sustitucion"]) for f in ev)}


def cuantil(v: list[float], q: float) -> float:
    v = sorted(v)
    i = q * (len(v) - 1)
    lo, hi = math.floor(i), math.ceil(i)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def banda(errores_previos: list[float], valor: float | None, config: dict) -> dict:
    """Banda empírica 10–90 con errores fuera de ajuste YA OBSERVADOS antes del origen; nula con menos de 12."""
    b = config["bandas"]
    if valor is None or len(errores_previos) < b["minimo_errores"]:
        return {"inferior": None, "superior": None, "metodo": None, "errores_disponibles": len(errores_previos), "motivo": "historia_insuficiente"}
    return {"inferior": round(max(0.0, valor - cuantil(errores_previos, 0.9)), 2), "superior": round(max(0.0, valor - cuantil(errores_previos, 0.1)), 2),
            "metodo": f"empírica: cuantiles 10–90 de {len(errores_previos)} errores fuera de ajuste previos (nominal {b['nominal']:.0%}, sin garantía)",
            "errores_disponibles": len(errores_previos), "motivo": None}


def cobertura_comprobada(filas: list[dict], metodo: str, h: int, origen: str, config: dict) -> dict:
    """Cobertura de la MISMA regla de banda en orígenes anteriores: en cada origen o' se construye la banda solo con errores
    conocidos en o' y se comprueba si el observado (objetivo <= ``origen``) cayó dentro."""
    dentro = total = 0
    for f in filas:
        if f["metodo"] != metodo or f["horizonte"] != h or f["error"] is None or f["objetivo"] > origen:
            continue
        b = banda(errores_previos(filas, metodo, h, f["origen"]), f["prediccion"], config)
        if b["inferior"] is not None:
            total += 1
            dentro += int(b["inferior"] <= f["observado"] <= b["superior"])
    return {"dentro": dentro, "evaluadas": total, "proporcion": dentro / total if total else None}


def errores_previos(filas: list[dict], metodo: str, h: int, origen: str) -> list[float]:
    """Errores del mismo método y horizonte cuyo objetivo ya estaba completo en ``origen`` (objetivo <= origen)."""
    return [f["error"] for f in filas if f["metodo"] == metodo and f["horizonte"] == h and f["error"] is not None and f["objetivo"] <= origen]


def todos_los_origenes(series: dict, sid: str) -> list[str]:
    return [m["periodo"] for m in series[sid]["calendario"] if m["estado"] == "completo"]


# Reproducción de A08 ------------------------------------------------------------------------------------------------------
def reproducir_a08(datos: DatosAceptados, series: dict) -> dict:
    """Ejecuta el cierre (pipeline.generar) en una carpeta temporal y compara su pronóstico A08 con la reconstrucción."""
    from pipeline.generar import _series
    from pipeline.pronostico import evaluar_origen_creciente, pronosticar_media_movil
    from .demanda import _importe
    fam = {str(p): str(v.get("familia_prueba", "DESCONOCIDA")) for p, v in datos.productos.items()}
    historial = [{"fecha": v["fecha"].isoformat(), "familia": fam.get(str(v["producto_id"])), "importe_cop": float(_importe(v, datos.tasas)), "cantidad": v["cantidad"]}
                 for v in datos.ventas if v.get("estado", "Confirmada") == "Confirmada" and v["fecha"] <= datos.observado_hasta]
    oper = [s for s in _series(historial, [], datos.observado_hasta) if s["serie"] == "ventas"]  # misma función que el cierre operativo
    out = {}
    for f in list(FAMILIAS) + ["Total"]:
        if f == "Total":
            vals = [sum(series[f"ventas_cop:{x}"]["calendario"][i]["valor"] for x in FAMILIAS) for i in range(len(series[f"ventas_cop:{FAMILIAS[0]}"]["calendario"]))]
        else:
            vals = [m["valor"] for m in series[f"ventas_cop:{f}"]["calendario"]]
        mm = [float(x) for x in pronosticar_media_movil(vals, 3, 3)]
        ev = evaluar_origen_creciente(vals, 3, 3, min_entrenamiento=6)
        op = {r["horizonte"]: r for r in oper if r["familia"] == f and r["tipo"] == "pronostico"}
        hist_op = [r["valor_cop"] for r in oper if r["familia"] == f and r["tipo"] == "historico"]
        out[f] = {"historico_coincide": [round(x, 2) for x in hist_op] == [round(x, 2) for x in vals],
                  "pronostico_reconstruido": mm, "pronostico_operativo": [op[h]["valor_cop"] for h in HORIZONTES],
                  "mae_reconstruido": {h: float(ev[h]["mae_media_movil"]) for h in HORIZONTES}, "mae_operativo": {h: op[h]["mae"] for h in HORIZONTES},
                  "mae_ingenuo": {h: float(ev[h]["mae_ingenuo"]) for h in HORIZONTES}, "n": {h: ev[h]["n"] for h in HORIZONTES},
                  "bandas_operativas": {h: [op[h]["banda_inferior"], op[h]["banda_superior"]] for h in HORIZONTES}}
        out[f]["coincide"] = out[f]["historico_coincide"] and all(abs(a - b) < 0.011 for a, b in zip(mm, out[f]["pronostico_operativo"])) and \
            all(abs(out[f]["mae_reconstruido"][h] - out[f]["mae_operativo"][h]) < 0.011 for h in HORIZONTES)
    return {"series": out, "notas": ["La media móvil A08 es RECURSIVA: el horizonte 2 promedia los dos últimos meses y el pronóstico del mes 1.",
                                     "Las bandas operativas son valor ± MAE (origen creciente desde 6 meses): describen el error medio, no son intervalos con cobertura.",
                                     "A08 empieza el calendario en el primer mes con alguna operación; M5 usa el inicio declarado de la cobertura (coinciden en este paquete)."]}


# Entrenamiento (selección en desarrollo) -------------------------------------------------------------------------------------
def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID:
        raise ProtocoloError("La configuración no es de demanda")
    if (salida / "config.json").exists() and canon(_leer(salida / "config.json")) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    series = construir_series(datos, config)
    conc = conciliar(datos, series, config)
    no_conciliadas = sorted({c["serie_id"] for c in conc if not c["conciliado"]})
    dev = config["desarrollo"]
    cache: dict = {}
    desarrollo, diagnostico, seleccion = [], [], {}
    for sid in series_modelables(series):
        if sid in no_conciliadas:
            seleccion[sid] = {"estado": "error_conciliacion", "por_horizonte": {}}
            continue
        origenes = [o for o in todos_los_origenes(series, sid) if dev["desde"] <= o < dev["hasta"]]
        principales = [o for o in origenes if len(tramo(series[sid]["calendario"], o)) >= config["minimos"]["candidatos_meses"]]
        filas = filas_origen(series, sid, principales, config, cache=cache, hasta_objetivo=dev["hasta"])
        desarrollo += filas
        diagnostico += [f for f in filas_origen(series, sid, [o for o in origenes if o not in principales], config, REFERENCIAS, cache, dev["hasta"])]
        por_h = {}
        for h in HORIZONTES:
            mets = {m: metricas([f for f in filas if f["metodo"] == m and f["horizonte"] == h]) for m in METODOS}
            con = {m: v for m, v in mets.items() if v["n"] > 0}
            if not con:
                por_h[str(h)] = {"elegido": "sin_historia", "motivo": "sin orígenes de desarrollo con 12 meses completos", "metricas": mets}
                continue
            orden = sorted(con, key=lambda m: (round(con[m]["mae"], 9), METODOS.index(m)))
            refs = [m for m in orden if m in REFERENCIAS]
            cands = [m for m in orden if m not in REFERENCIAS]
            por_h[str(h)] = {"elegido": orden[0], "mejor_referencia": refs[0] if refs else None, "mejor_candidato": cands[0] if cands else None,
                             "n_comparaciones": con[orden[0]]["n"], "metricas": mets}
        seleccion[sid] = {"estado": "seleccionada", "por_horizonte": por_h}
    archivos = {"config.json": json_bytes(config), "series.json": json_bytes(series), "conciliacion.json": json_bytes(conc),
                "desarrollo.json": json_bytes(desarrollo), "diagnostico_referencias.json": json_bytes(diagnostico), "seleccion.json": json_bytes(seleccion),
                "control_a08.json": json_bytes(reproducir_a08(datos, series)), "entorno.json": json_bytes(entorno_m5()),
                "datos.json": json_bytes(dict(datos.descripcion(), cobertura_fuentes=config["cobertura_fuentes"],
                                              meses=[m["periodo"] for m in series[f"ventas_cop:{FAMILIAS[0]}"]["calendario"]]))}
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "huella_datos": datos.huella_datos, "revision_datos": datos.revision, "series_no_conciliadas": no_conciliadas,
            "etapa": "selección congelada antes de la comprobación (objetivos julio–octubre de 2026)"}
    m = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta, volatiles={"fechas_piloto": fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": m, "seleccion": seleccion, "conciliacion": conc}


def entorno_m5() -> dict:
    e = entorno()
    try:
        import statsmodels
        e["statsmodels"] = statsmodels.__version__
    except ImportError:
        e["statsmodels"] = None
    return e


def fechas_piloto(hoy: date) -> dict:
    o = f"{hoy.year}-{hoy.month:02d}"
    return {"congelacion_real": hoy.isoformat(), "primer_origen_prospectivo": o, "requiere_mes_completo": f"{o} completo y declarado en la cobertura",
            "objetivos": [sumar_meses(o, h) for h in HORIZONTES], "nota": "el primer origen prospectivo es el primer mes que se complete después de la congelación"}


# Evaluación (comprobación con la selección congelada) -------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    if huella_protocolo(_leer(ejecucion / "config.json")) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    return cong


def decidir(sel_h: dict, met_elegido: dict, met_ref: dict, config: dict) -> dict:
    metas = config["metas"]
    elegido, ref = sel_h.get("elegido"), sel_h.get("mejor_referencia")
    if elegido in (None, "sin_historia"):
        return {"decision": "sin_historia", "motivo": sel_h.get("motivo", "historia insuficiente")}
    if elegido in REFERENCIAS:
        return {"decision": "referencia_conservada", "motivo": f"en desarrollo ganó la referencia {elegido}"}
    if met_ref.get("mae") in (None, 0) and met_ref.get("n"):
        return {"decision": "referencia_conservada", "motivo": "MAE de la referencia igual a 0: no se calcula mejora relativa"}
    n, mc, mr = met_elegido["n"], met_elegido["mae"], met_ref.get("mae")
    if n < metas["minimo_errores_superioridad"] or mr is None:
        return {"decision": "inconcluso", "motivo": f"evidencia insuficiente ({n} errores)"}
    reduccion = (mr - mc) / mr
    sesgo_ok = met_elegido["sesgo_abs_normalizado"] is None or met_elegido["sesgo_abs_normalizado"] <= metas["sesgo_absoluto_normalizado_max"]
    if reduccion >= metas["reduccion_mae_vs_mejor_referencia"] - 1e-12 and sesgo_ok:
        return {"decision": "candidato_exploratorio_favorable", "motivo": f"MAE {reduccion:.0%} menor que {ref} con {n} errores (exploratorio)", "reduccion": reduccion}
    if reduccion <= -metas["reduccion_mae_vs_mejor_referencia"]:
        return {"decision": "rechazado", "motivo": f"MAE {-reduccion:.0%} mayor que {ref}", "reduccion": reduccion}
    return {"decision": "inconcluso", "motivo": f"reducción {reduccion:.0%} frente a {ref}" + ("" if sesgo_ok else "; sesgo normalizado > 15 %"), "reduccion": reduccion}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config, seleccion, info = _leer(ejecucion / "config.json"), _leer(ejecucion / "seleccion.json"), _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    series = construir_series(datos, config)
    if canon(series) != canon(_leer(ejecucion / "series.json")):
        raise ProtocoloError("Las series reconstruidas no coinciden con las congeladas")
    cache: dict = {}
    origenes = config["comprobacion"]["origenes"]
    compr, resultados, decisiones = [], {}, {}
    for sid, sel in seleccion.items():
        if sel["estado"] != "seleccionada":
            decisiones[sid] = {h: {"decision": "sin_historia", "motivo": sel["estado"]} for h in map(str, HORIZONTES)}
            continue
        resultados[sid], decisiones[sid] = {}, {}
        for h in HORIZONTES:
            sh = sel["por_horizonte"][str(h)]
            filas = [f for f in filas_origen(series, sid, origenes[str(h)], config, cache=cache) if f["horizonte"] == h]
            compr += filas
            por_met = {m: metricas([f for f in filas if f["metodo"] == m]) for m in METODOS}
            me = por_met.get(sh.get("elegido"), {"n": 0}) if sh.get("elegido") not in (None, "sin_historia") else {"n": 0}
            mr = por_met.get(sh.get("mejor_referencia")) or {"n": 0}
            resultados[sid][str(h)] = {"elegido": sh.get("elegido"), "mejor_referencia": sh.get("mejor_referencia"), "metodos": por_met,
                                       "tabla": [{k: f[k] for k in ("metodo", "origen", "objetivo", "prediccion", "observado", "error", "recortado", "sustitucion")} for f in filas]}
            decisiones[sid][str(h)] = decidir(sh, me, mr, config) | {"n": me.get("n", 0), "mae_elegido": me.get("mae"), "mae_referencia": mr.get("mae")}
    total = evaluar_total(series, seleccion, config, cache)
    metricas_doc = {"bloque": "comprobacion_historica", "alcance": "EXPLORATORIA (datos sintéticos ya inspeccionados); objetivos 2026-07..2026-10",
                    "resultados": resultados, "total": total, "limitaciones": LIMITACIONES}
    resumen = {}
    for sid, d in decisiones.items():
        for h, x in d.items():
            resumen[x["decision"]] = resumen.get(x["decision"], 0) + 1
    doc = {"modelo_id": MODELO_ID, "version_protocolo": config["version_protocolo"], "sello_congelacion": cong["sello"], "decisiones": decisiones,
           "resumen": resumen, "decision_global": "sin ganador global: decisión por serie y horizonte", "origen_datos": config["origen_datos"],
           "estado_maximo": "sombra", "limitaciones": LIMITACIONES + ["Ningún modelo se promueve automáticamente; las series_mensuales operativas no cambian."]}
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas_doc), "comprobacion.json": json_bytes(compr), "decision.json": json_bytes(doc)}
    m = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"]})
    return {"metricas": metricas_doc, "decision": doc, "evaluacion": m}


def evaluar_total(series: dict, seleccion: dict, config: dict, cache: dict) -> dict:
    """Total = suma de los pronósticos publicados de las familias (mismo origen y horizonte), evaluado contra el total real."""
    out = {}
    origenes = config["comprobacion"]["origenes"]
    for h in HORIZONTES:
        filas = []
        for o in origenes[str(h)]:
            partes, obs = [], []
            for f in FAMILIAS:
                sid = f"ventas_cop:{f}"
                m = seleccion[sid]["por_horizonte"][str(h)]["elegido"]
                p = pronosticar(m, tramo(series[sid]["calendario"], o), h, config, cache) if m not in (None, "sin_historia") else None
                real = next((x for x in series[sid]["calendario"] if x["periodo"] == sumar_meses(o, h)), None)
                partes.append(p["valor"] if p else None)
                obs.append(real["valor"] if real and real["estado"] == "completo" else None)
            pred = round(sum(partes), 2) if None not in partes else None
            o_tot = sum(obs) if None not in obs else None
            filas.append({"origen": o, "objetivo": sumar_meses(o, h), "prediccion": pred, "observado": o_tot,
                          "error": round(pred - o_tot, 6) if pred is not None and o_tot is not None else None, "recortado": False, "sustitucion": None,
                          "metodo": "suma_de_familias", "horizonte": h})
        total_serie = {"calendario": [{"periodo": p, "estado": "completo", "valor": sum(series[f"ventas_cop:{f}"]["calendario"][i]["valor"] for f in FAMILIAS)}
                                      for i, p in enumerate(m_["periodo"] for m_ in series[f"ventas_cop:{FAMILIAS[0]}"]["calendario"])]}
        comparador = [f for f in filas_origen({"t": total_serie}, "t", origenes[str(h)], config, ("media_movil_3", "ses"), cache) if f["horizonte"] == h]
        out[str(h)] = {"suma_de_familias": metricas(filas) | {"tabla": filas},
                       "comparador_total_directo": {m: metricas([f for f in comparador if f["metodo"] == m]) for m in ("media_movil_3", "ses")},
                       "nota": "el total publicado es la suma de familias; el ajuste directo solo es contexto"}
    return out


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": _leer(ejecucion / "decision.json")}


# Ajuste para un origen nuevo (fuera del cierre y de la API) --------------------------------------------------------------------
def ajustar_origen(ejecucion: str | Path, datos: DatosAceptados, origen: str, salida: str | Path) -> dict:
    """Reestima el procedimiento CONGELADO con la historia hasta ``origen`` y escribe el artefacto de ese origen (estados,
    selección, MAE de la comprobación y bandas con errores previos). No vuelve a seleccionar métodos."""
    ejecucion = Path(ejecucion)
    pub = evaluacion_publicada(ejecucion)
    config, seleccion = _leer(ejecucion / "config.json"), _leer(ejecucion / "seleccion.json")
    metricas_doc = _leer(ejecucion / "metricas_comprobacion_historica.json")
    series = construir_series(datos, config)
    ultimo = max(m["periodo"] for m in series[f"ventas_cop:{FAMILIAS[0]}"]["calendario"] if m["estado"] == "completo")
    if origen != ultimo:
        raise ProtocoloError(f"El origen {origen} no es el último mes completo de los datos ({ultimo})")
    cache: dict = {}
    salida_series, equivalencias = {}, []
    for sid in series_modelables(series):
        sel = seleccion.get(sid, {"estado": "sin_seleccion", "por_horizonte": {}})
        hist = tramo(series[sid]["calendario"], origen)
        elegidos = {h: (sel["por_horizonte"].get(h) or {}).get("elegido", "sin_historia") for h in map(str, HORIZONTES)}
        estados = {}
        for m in sorted({x for x in elegidos.values() if x in ("ses", "holt_amortiguado")}):
            est = ajustar_ets(hist, m, config) if len(hist) >= config["minimos"]["candidatos_meses"] else {"metodo": m, "convergio": False, "motivo": "historia < 12 meses"}
            estados[m] = est
            if est["convergio"]:
                for h in HORIZONTES:
                    a, b = pron_estado(est, h), est["statsmodels"][h - 1]
                    equivalencias.append({"serie_id": sid, "metodo": m, "horizonte": h, "artefacto": a, "statsmodels": b, "diferencia_relativa": abs(a - b) / max(1.0, abs(b))})
        bandas, evaluacion = {}, {}
        todas = filas_origen(series, sid, [o for o in todos_los_origenes(series, sid) if o < origen], config, cache=cache)
        for h in HORIZONTES:
            m = elegidos[str(h)]
            res = (metricas_doc["resultados"].get(sid) or {}).get(str(h)) or {}
            mm = (res.get("metodos") or {}).get(m) or {}
            evaluacion[str(h)] = {"mae": mm.get("mae"), "n": mm.get("n", 0), "periodo": "objetivos 2026-07..2026-10", "alcance": "comprobación histórica exploratoria (datos sintéticos)"}
            p = pronosticar(m, hist, h, config, cache) if m not in ("sin_historia", None) else None
            bandas[str(h)] = banda(errores_previos(todas, m, h, origen), p["valor"] if p else None, config)
            if bandas[str(h)]["inferior"] is not None:
                cc = cobertura_comprobada(todas, m, h, origen, config)
                bandas[str(h)]["cobertura_comprobada"] = cc
                bandas[str(h)]["metodo"] += (f"; cobertura comprobada {cc['dentro']} de {cc['evaluadas']} en orígenes anteriores" if cc["evaluadas"]
                                             else "; cobertura aún no comprobada (sin orígenes anteriores con 12 errores)")
        motivos = [] if hist else ["Sin meses completos en el origen"]
        if sel["estado"] != "seleccionada":
            motivos.append(f"Serie no seleccionable: {sel['estado']}")
        salida_series[sid] = {"seleccion": elegidos, "estados": estados, "historia": hist, "ultimo_mes_completo": origen if hist else None,
                              "historia_huella": hashlib.sha256(canon(hist).encode()).hexdigest(), "evaluacion": evaluacion, "bandas": bandas, "motivos": motivos}
    tol = config["ajuste"]["tolerancia_equivalencia_relativa"]
    if any(e["diferencia_relativa"] > tol for e in equivalencias):
        raise ValueError("La inferencia desde el estado no reproduce statsmodels dentro de la tolerancia")
    total = {}
    fam_sid = [f"ventas_cop:{f}" for f in FAMILIAS]
    for h in HORIZONTES:
        t = (metricas_doc["total"].get(str(h)) or {}).get("suma_de_familias") or {}
        filas_tot = []  # errores del TOTAL sumado ya observados antes del origen (nunca se suman límites de familias)
        for o in [x for x in todos_los_origenes(series, fam_sid[0]) if sumar_meses(x, h) <= origen]:
            partes = [pronosticar(salida_series[sid]["seleccion"][str(h)], tramo(series[sid]["calendario"], o), h, config, cache)
                      if salida_series[sid]["seleccion"][str(h)] not in ("sin_historia", None) else None for sid in fam_sid]
            reales = [next(m for m in series[sid]["calendario"] if m["periodo"] == sumar_meses(o, h)) for sid in fam_sid]
            if None not in partes and all(r["estado"] == "completo" for r in reales):
                pred, obs = round(sum(p["valor"] for p in partes), 2), sum(r["valor"] for r in reales)
                filas_tot.append({"metodo": "suma_de_familias", "horizonte": h, "origen": o, "objetivo": sumar_meses(o, h), "prediccion": pred, "observado": obs, "error": pred - obs})
        actual = [pronosticar(salida_series[sid]["seleccion"][str(h)], salida_series[sid]["historia"], h, config, cache) for sid in fam_sid]
        valor_total = round(sum(p["valor"] for p in actual), 2) if None not in actual else None
        bt = banda(errores_previos(filas_tot, "suma_de_familias", h, origen), valor_total, config)
        if bt["inferior"] is not None:
            cc = cobertura_comprobada(filas_tot, "suma_de_familias", h, origen, config)
            bt["cobertura_comprobada"] = cc
            bt["metodo"] += (f"; cobertura comprobada {cc['dentro']} de {cc['evaluadas']} en orígenes anteriores" if cc["evaluadas"]
                             else "; cobertura aún no comprobada (sin orígenes anteriores con 12 errores)")
        total[str(h)] = {"mae": t.get("mae"), "n": t.get("n", 0), "periodo": "objetivos 2026-07..2026-10", "alcance": "comprobación histórica exploratoria", "banda": bt}
    d = {"formato": FORMATO, "modelo_id": MODELO_ID, "version": "pendiente", "origen": origen, "umbral": None, "series": salida_series, "total": total,
         "politica_salida": config["ajuste"]["salida"], "redondeo": "0,01 por serie; total = suma de familias redondeadas",
         "version_protocolo": config["version_protocolo"], "sello_evaluacion": pub["evaluacion"]["sello"], "huella_datos": datos.huella_datos,
         "revision_datos": datos.revision, "disponible_desde": config["disponible_desde"], "origen_datos": config["origen_datos"]}
    d["version"] = f"demanda-m5-{origen}-" + sellar(d)["huella"][:8]
    art = sellar(d)
    marcador = publicar_lote(salida, {"artefacto.json": json_bytes(art), "equivalencia.json": json_bytes(equivalencias), "entorno.json": json_bytes(entorno_m5())},
                             "origen.json", {"origen": origen, "artefacto_huella": art["huella"], "sello_evaluacion": pub["evaluacion"]["sello"], "huella_datos": datos.huella_datos})
    return {"artefacto": art, "equivalencias": equivalencias, "marcador": marcador}
