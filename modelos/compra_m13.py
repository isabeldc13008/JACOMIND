"""M1.3 · Dos candidatos predeclarados: S (tiempo hasta la próxima compra) y P (ponderación temporal + nivel).

Protocolo ``modelos/config/compra_30d_m13.json`` (``m1.3-protocolo-v1``).

* ``entrenar_m13``: guarda el protocolo, evalúa S, P, su descomposición y el control en la validación temporal
  de desarrollo (criterio principal), construye los artefactos finales y congela. No lee julio–septiembre.
* ``evaluar_m13``: verifica la congelación, mide la comprobación histórica (exploratoria) y decide cada
  candidato con su regla.

S no se entrena con etiquetas: su curva usa solo ventas con fecha <= fecha de referencia. P y el control
entrenan con cortes cuyas etiquetas maduraron antes de predecir. Nada se promueve automáticamente.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import metricas as M
from .compra import (LIMITACIONES, DependenciaEntrenamiento, ProtocoloError, _atendibles, _canon, _comprobar_version_protocolo, _hoy_utc,
                     _json, _leer, _primer_fin_de_mes_posterior, ajustar_logistica, conteos, entorno, huella_protocolo, identidad_protocolo,
                     poblacion)
from .compra_m11 import REFERENCIAS_REGISTRO, cortes_entrenamiento, origenes, preparar
from .datos import DatosAceptados, cargar_datos
from .inferencia import FORMATO, MODELO_ID, cargar_artefacto, desde_dict, sellar
from .supervivencia import FORMATO_SUPERVIVENCIA, ajustar_curva
from .variables import VERSION_INTERVALOS, VERSION_VARIABLES, ajustar_transformaciones, aplicar_transformaciones

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_M13 = RAIZ / "modelos" / "config" / "compra_30d_m13.json"


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))


def _base_logistica(config: dict, version: str, variables: list[str]) -> dict:
    return {"formato": FORMATO, "modelo_id": MODELO_ID, "version": version, "version_variables": VERSION_VARIABLES,
            "horizonte_dias": config["horizonte_dias"], "variables": list(variables), "umbral": config["umbral"]["valor"],
            "disponible_desde": config["disponible_desde"]}


def ajustar_logistica_pesada(filas: list[dict], variables: list[str], C: float, config: dict, pesos: list[float] | None):
    """Logística L2 con pesos por fila (``None`` = sin pesos). Transformaciones ajustadas sin pesos."""
    if pesos is None:
        e = config["estimador_logistica"]
        trans, b0, w, predecir = ajustar_logistica(filas, variables, C, dict(e, semilla=config["semilla"]))
        return trans, b0, w, predecir
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise DependenciaEntrenamiento("Entrenar requiere: pip install -r requirements-modelos.txt") from exc
    e = config["estimador_logistica"]
    trans = ajustar_transformaciones(filas, variables)
    X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
    y = np.array([int(f["compra_30d"]) for f in filas])
    m = LogisticRegression(C=C, solver=e["solver"], max_iter=e["max_iter"], tol=e["tol"], class_weight=e["class_weight"],
                           random_state=config["semilla"]).fit(X, y, sample_weight=np.array(pesos, dtype=float))

    def predecir(lote):
        return [float(p) for p in m.predict_proba(np.array([aplicar_transformaciones(f, trans) for f in lote], dtype=float))[:, 1]]
    return trans, float(m.intercept_[0]), [float(w) for w in m.coef_[0]], predecir


def pesos_temporales(filas: list[dict], semivida: int) -> list[float]:
    t_max = max(f["corte"] for f in filas)
    return [0.5 ** ((t_max - f["corte"]).days / semivida) for f in filas]


def ajuste_nivel(art, filas_ultimo_corte: list[dict]) -> float:
    """b tal que el nivel se alinea con la tasa observada del último corte maduro (no cambia el orden)."""
    tasa = sum(f["compra_30d"] for f in filas_ultimo_corte) / len(filas_ultimo_corte)
    media = sum(art.probabilidad(f) for f in filas_ultimo_corte) / len(filas_ultimo_corte)
    return _logit(tasa) - _logit(media)


def modelos_logisticos(entren: list[dict], config: dict, etiqueta: str, extra: dict | None = None) -> dict[str, Any]:
    """Control, P y su descomposición entrenados con ``entren`` (todas las etiquetas maduras)."""
    cP = config["candidatos"]["P"]
    t_ult = max(f["corte"] for f in entren)
    ultimo = [f for f in entren if f["corte"] == t_ult]
    salida = {}
    for nombre, con_pesos in (("control", False), ("P_solo_pesos", True)):
        variables = config["control"]["variables"] if nombre == "control" else cP["variables"]
        C = config["control"]["C"] if nombre == "control" else cP["C"]
        w = pesos_temporales(entren, cP["semivida_dias"]) if con_pesos else None
        trans, b0, pesos, predecir = ajustar_logistica_pesada(entren, variables, C, config, w)
        d = _base_logistica(config, f"{etiqueta}-{nombre}", variables) | {"transformaciones": trans, "intercepto": b0, "pesos": pesos,
                                                                           **(extra or {})}
        salida[nombre] = (desde_dict(sellar(d)), predecir)
    for nombre, base in (("P_solo_nivel", "control"), ("P", "P_solo_pesos")):
        art, predecir = salida[base]
        b = ajuste_nivel(art, ultimo)
        d = dict(art.datos, version=f"{etiqueta}-{nombre}",
                 calibracion={"tipo": "sigmoide", "a": 1.0, "b": b, "metodo": "ajuste de nivel al último corte maduro",
                              "corte_referencia": t_ult.isoformat()})
        d.pop("huella", None)
        salida[nombre] = (desde_dict(sellar(d)), predecir)
    return salida


def artefacto_supervivencia(curva: dict, config: dict, version: str, extra: dict | None = None):
    cS = config["candidatos"]["S"]
    d = {"formato": FORMATO_SUPERVIVENCIA, "modelo_id": MODELO_ID, "version": version, "version_variables": VERSION_INTERVALOS,
         "horizonte_dias": config["horizonte_dias"],
         "curva": {k: curva[k] for k in ("tiempos", "supervivencia", "cola_tasa_diaria")},
         "curva_origen": {k: curva[k] for k in ("intervalos_completos", "intervalos_abiertos", "datos_hasta")},
         "k_contraccion": cS["k_contraccion"], "umbral": config["umbral"]["valor"], "disponible_desde": config["disponible_desde"],
         **(extra or {})}
    return desde_dict(sellar(d))


def _metricas(filas: list[dict], s: Callable, prob: bool) -> dict:
    r = M.resumen_ranking(filas, s, (10, 20))["agregado"]
    out = {k: r[k] for k in ("precision_media_top10", "aciertos_top10", "denominador_top10", "aciertos_top20", "denominador_top20",
                             "average_precision_media_mensual")}
    if prob:
        out.update({"log_loss": M.log_loss(filas, s), "brier": M.brier(filas, s), "prob_media": sum(s(f) for f in filas) / len(filas),
                    "tasa_observada": sum(f["compra_30d"] for f in filas) / len(filas)})
    return out


def _media_top10(filas, s):
    meses = [M.ranking_k(g, s, 10) for g in M.por_corte(filas).values()]
    return sum(x["aciertos"] / x["k_efectivo"] for x in meses) / len(meses)


def entrenar_m13(datos: DatosAceptados, config: dict, salida: str | Path) -> dict[str, Any]:
    salida = Path(salida)
    if (salida / "congelacion.json").exists():
        raise FileExistsError(f"{salida} ya contiene una ejecución; usa otra carpeta")
    salida.mkdir(parents=True, exist_ok=True)
    _comprobar_version_protocolo(salida, config)
    protocolo = {"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config),
                 "guardado_en": _hoy_utc()}
    _json(salida / "config.json", config)
    _json(salida / "protocolo.json", protocolo)  # antes de calcular cualquier resultado
    ds = preparar(datos, dict(config, version_variables=VERSION_INTERVALOS))
    h = config["horizonte_dias"]
    cortes_dev = sorted(ds["por_corte"])
    origs = origenes(config, cortes_dev)
    nombres = ["S", "P", "P_solo_pesos", "P_solo_nivel", "control"]
    filas_oos: list[dict] = []
    por_origen = []
    for d in origs:
        curva = ajustar_curva(ds["historial"], datos.clientes, d)  # solo ventas con fecha <= d
        s_art = artefacto_supervivencia(curva, config, f"m13-S-{d}")
        entren = [f for t in cortes_entrenamiento(cortes_dev, d, h) for f in ds["por_corte"][t]]
        logs = modelos_logisticos(entren, config, f"m13-{d}")
        grupo = []
        for f in ds["por_corte"][d]:
            g = dict(f, _p_S=s_art.probabilidad(f))
            for n in ("P", "P_solo_pesos", "P_solo_nivel", "control"):
                g[f"_p_{n}"] = logs[n][0].probabilidad(f)
            grupo.append(g)
        filas_oos.extend(grupo)
        por_origen.append({"origen": d.isoformat(), "n": len(grupo), "positivos": sum(f["compra_30d"] for f in grupo),
                           "curva_intervalos": [curva["intervalos_completos"], curva["intervalos_abiertos"]],
                           **{n: {"top10": M.ranking_k(grupo, lambda f, n=n: f[f"_p_{n}"], 10)["aciertos"],
                                  "log_loss": M.log_loss(grupo, lambda f, n=n: f[f"_p_{n}"])} for n in nombres},
                           "recencia": {"top10": M.ranking_k(grupo, lambda f: -f["recencia_dias"], 10)["aciertos"]}})
    agregado = {n: _metricas(filas_oos, lambda f, n=n: f[f"_p_{n}"], True) for n in nombres}
    agregado["recencia"] = _metricas(filas_oos, lambda f: -float(f["recencia_dias"]), False)
    agregado["regla_30d"] = _metricas(filas_oos, lambda f: float(f["frecuencia_30d"] > 0), False)
    boot = config["bootstrap"]
    ic_S = M.bootstrap_clientes(filas_oos, lambda m: _media_top10(m, lambda f: f["_p_S"]) - _media_top10(m, lambda f: -f["recencia_dias"]),
                                boot["repeticiones"], boot["semilla"])
    ic_P = M.bootstrap_clientes(filas_oos, lambda m: M.log_loss(m, lambda f: f["_p_P"]) - M.log_loss(m, lambda f: f["_p_control"]),
                                boot["repeticiones"], boot["semilla"])
    desarrollo = {"origenes": [o.isoformat() for o in origs], "por_origen": por_origen, "agregado": agregado,
                  "S_menos_recencia_top10": agregado["S"]["precision_media_top10"] - agregado["recencia"]["precision_media_top10"],
                  "ic95_S_menos_recencia_top10": ic_S,
                  "P_menos_control_log_loss": agregado["P"]["log_loss"] - agregado["control"]["log_loss"],
                  "ic95_P_menos_control_log_loss": ic_P,
                  "nota": "120 clientes repetidos en 10 cortes; remuestreo por cliente completo"}
    # Artefactos finales.
    inicio = min(f["corte"] for f in ds["prueba"])
    cortes_final = cortes_entrenamiento(cortes_dev, inicio, h)
    entren = [f for t in cortes_final for f in ds["por_corte"][t]]
    extra = {"version_protocolo": config["version_protocolo"], "origen_datos": config["origen_datos"],
             "entrenamiento": {"cortes": [c.isoformat() for c in cortes_final], "filas": len(entren), "huella_datos": datos.huella_datos,
                               "revision_datos": datos.revision}}
    curva_final = ajustar_curva(ds["historial"], datos.clientes, inicio)
    s_final = artefacto_supervivencia(curva_final, config, "compra_30d-m13-S-pendiente", extra)
    s_final = artefacto_supervivencia(curva_final, config, "compra_30d-m13-S-" + s_final.huella[:8], extra)
    logs = modelos_logisticos(entren, config, "compra_30d-m13", extra)
    equivalencia = {}
    import numpy as np
    for n, (art, predecir) in logs.items():
        ref = np.array(predecir(entren), dtype=float)
        cal = art.datos.get("calibracion")
        if cal:  # referencia independiente: probabilidad de sklearn -> logit -> desplazamiento con numpy
            ref = 1 / (1 + np.exp(-(np.log(np.clip(ref, 1e-300, 1) / np.clip(1 - ref, 1e-300, 1)) + cal["b"])))
        dif = float(max(abs(a - art.probabilidad(f)) for a, f in zip(ref, entren)))
        if dif > config["tolerancia_probabilidad"]:
            raise ValueError(f"{n}: la inferencia desde JSON difiere en {dif:g}")
        equivalencia[n] = dif
    recargado = desde_dict(json.loads(json.dumps(s_final.datos)))
    equivalencia["S_recarga_json"] = max(abs(recargado.probabilidad(f) - s_final.probabilidad(f)) for f in entren)
    artefactos = {"S": s_final.datos, **{n: a.datos for n, (a, _) in logs.items()}}
    for n, d in artefactos.items():
        _json(salida / f"artefacto_{n}.json", d)
    refs = {}
    for nombre, v in (("v1_congelada", "v1"), ("m1_v2_congelado", "v2")):
        r = cargar_artefacto(REFERENCIAS_REGISTRO / v)
        refs[nombre] = {"version": r.version, "huella": r.huella}
        _json(salida / f"referencia_{nombre}.json", r.datos)
    hoy = datetime.now(timezone.utc).date()
    primer = _primer_fin_de_mes_posterior(hoy)
    cong = {"formato": 2, "congelado_en": _hoy_utc(), "protocolo": {k: protocolo[k] for k in ("version", "huella")},
            "artefactos": {n: d["huella"] for n, d in artefactos.items()}, "referencias": refs, "huella_datos": datos.huella_datos,
            "revision_datos": datos.revision, "cortes_entrenamiento_final": [c.isoformat() for c in cortes_final],
            "curva_S_datos_hasta": curva_final["datos_hasta"], "equivalencia": equivalencia,
            "bloques_usados": ["desarrollo"], "bloque_reservado": "comprobacion_historica",
            "fechas": {"congelacion_real": hoy.isoformat(), "disponibilidad_simulada_desde": config["disponible_desde"],
                       "datos_observados_hasta": datos.observado_hasta.isoformat(), "primer_corte_prospectivo": primer.isoformat(),
                       "primer_corte_prospectivo_madura_el": (primer + timedelta(days=h)).isoformat(),
                       "nota": "julio–septiembre y octubre de 2026 son comprobaciones retrospectivas"}}
    cong["sello"] = hashlib.sha256(_canon({k: cong[k] for k in ("protocolo", "artefactos", "referencias", "huella_datos")}).encode()).hexdigest()
    _json(salida / "desarrollo.json", desarrollo)
    _json(salida / "datos.json", dict(datos.descripcion(), desarrollo=conteos(ds["desarrollo"]), ejecutado_en=_hoy_utc()))
    _json(salida / "entorno.json", entorno())
    _json(salida / "congelacion.json", cong)
    return {"desarrollo": desarrollo, "congelacion": cong, "artefactos": artefactos}


def verificar_congelacion_m13(ejecucion: Path) -> dict:
    cong = _leer(ejecucion / "congelacion.json")
    if huella_protocolo(_leer(ejecucion / "config.json")) != cong["protocolo"]["huella"]:
        raise ProtocoloError(f"El protocolo de {ejecucion} cambió después de congelarse; crea una versión y una ejecución nuevas.")
    for n, h in cong["artefactos"].items():
        if cargar_artefacto(ejecucion / f"artefacto_{n}.json").huella != h:
            raise ProtocoloError(f"artefacto_{n}.json no coincide con el congelado")
    for n, r in cong["referencias"].items():
        if cargar_artefacto(ejecucion / f"referencia_{n}.json").huella != r["huella"]:
            raise ProtocoloError(f"La referencia {n} no coincide con la congelada")
    sello = hashlib.sha256(_canon({k: cong[k] for k in ("protocolo", "artefactos", "referencias", "huella_datos")}).encode()).hexdigest()
    if sello != cong["sello"]:
        raise ProtocoloError("congelacion.json fue alterado (el sello no coincide)")
    return cong


def decidir(desarrollo: dict, comprobacion: dict, config: dict) -> dict:
    mS, mP = config["metas"]["S"], config["metas"]["P"]
    dS, icS = desarrollo["S_menos_recencia_top10"], desarrollo["ic95_S_menos_recencia_top10"]
    meses = [{"corte": a["corte"], "S": a["top10"]["aciertos"], "recencia": b["top10"]["aciertos"]}
             for a, b in zip(comprobacion["S"]["elegible"]["por_mes"], comprobacion["recencia"]["elegible"]["por_mes"])
             if b["top10"]["aciertos"] - a["top10"]["aciertos"] >= mS["comprobacion_sin_meses_con_perdida"]]
    cS = {"mejora_desarrollo_top10": dS >= mS["mejora_minima_precision_top10_vs_recencia"] - 1e-12,
          "ic95_excluye_cero": icS.get("p2_5", -1) > 0, "comprobacion_sin_meses_con_perdida": not meses}
    decS = "favorable" if all(cS.values()) else ("rechazado" if dS <= -mS["margen_rechazo"] + 1e-12 else "inconcluso")
    ag = desarrollo["agregado"]
    dP, icP = desarrollo["P_menos_control_log_loss"], desarrollo["ic95_P_menos_control_log_loss"]
    cP = {"log_loss_menor_que_control": dP < 0, "ic95_log_loss_excluye_cero": icP.get("p97_5", 1) < 0,
          "brier_no_peor_que_control": ag["P"]["brier"] <= ag["control"]["brier"]}
    decP = "favorable" if all(cP.values()) else ("rechazado" if icP.get("p2_5", -1) > 0 else "inconcluso")
    return {"S": {"decision": decS, "estado_maximo": "ninguno" if decS == "rechazado" else "sombra", "cumple": cS,
                  "valores": {"diferencia_top10": dS, "ic95": [icS.get("p2_5"), icS.get("p97_5")]}, "meses_a_revisar": meses},
            "P": {"decision": decP, "estado_maximo": "ninguno" if decP == "rechazado" else "sombra", "cumple": cP,
                  "valores": {"diferencia_log_loss": dP, "ic95": [icP.get("p2_5"), icP.get("p97_5")],
                              "brier_P": ag["P"]["brier"], "brier_control": ag["control"]["brier"]}}}


def evaluar_m13(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict[str, Any]:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion_m13(ejecucion)
    config = _leer(ejecucion / "config.json")
    info = _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; define un protocolo nuevo")
    ds = preparar(datos, dict(config, version_variables=VERSION_INTERVALOS))
    filas = poblacion(ds["prueba"])
    atend = _atendibles(datos, sorted({f["corte"] for f in filas}))
    sub = [f for f in filas if f["cliente_id"] in atend[f["corte"]]]
    entren = [f for f in poblacion(ds["desarrollo"]) if f["corte"].isoformat() in set(cong["cortes_entrenamiento_final"])]
    tasa = sum(f["compra_30d"] for f in entren) / len(entren)
    metodos: dict[str, tuple[Callable, bool]] = {n: (cargar_artefacto(ejecucion / f"artefacto_{n}.json").probabilidad, True)
                                                for n in cong["artefactos"]}
    for n in cong["referencias"]:
        metodos[n] = (cargar_artefacto(ejecucion / f"referencia_{n}.json").probabilidad, True)
    metodos["recencia"] = (lambda f: -float(f["recencia_dias"]), False)
    metodos["regla_30d"] = (lambda f: float(f["frecuencia_30d"] > 0), False)
    metodos["constante"] = (lambda f: tasa, True)
    comprobacion = {}
    for n, (s, p) in metodos.items():
        comprobacion[n] = {pob: {"por_mes": M.resumen_ranking(c, s, config["k"])["por_mes"], "agregado": _metricas(c, s, p and pob == "elegible")}
                           for pob, c in (("elegible", filas), ("atendible", sub))}
    desarrollo = _leer(ejecucion / "desarrollo.json")
    decision = decidir(desarrollo, comprobacion, config)
    metricas = {"bloque": "comprobacion_historica", "evaluado_en": _hoy_utc(),
                "alcance": "comprobación histórica exploratoria: periodo ya inspeccionado; el criterio principal es la validación temporal",
                "poblacion": conteos(ds["prueba"]), "atendible_n": len(sub), "resultados": comprobacion}
    doc = {"candidatos": decision, "version_protocolo": config["version_protocolo"], "protocolo_huella": cong["protocolo"]["huella"],
           "artefactos": cong["artefactos"], "origen_datos": config["origen_datos"], "fechas": cong["fechas"], "alcance": metricas["alcance"],
           "limitaciones": LIMITACIONES + ["Ningún artefacto M1.3 se promueve automáticamente."]}
    ruta_m, ruta_d = ejecucion / "metricas_comprobacion_historica.json", ejecucion / "decision.json"
    normal = lambda d: json.loads(json.dumps({k: v for k, v in d.items() if k not in ("evaluado_en", "decidido_en")}, default=str))  # noqa: E731
    if ruta_m.exists() and normal(_leer(ruta_m)) != normal(metricas):
        raise ProtocoloError(f"{ruta_m} ya contiene métricas distintas; una ejecución congelada no se sobrescribe")
    if ruta_d.exists() and normal(_leer(ruta_d)) != normal(doc):
        raise ProtocoloError(f"{ruta_d} ya contiene una decisión distinta; una ejecución congelada no se sobrescribe")
    if not ruta_m.exists():
        _json(ruta_m, metricas)
        _json(ruta_d, dict(doc, decidido_en=_hoy_utc()))
    return {"metricas": _leer(ruta_m), "decision": _leer(ruta_d)}
