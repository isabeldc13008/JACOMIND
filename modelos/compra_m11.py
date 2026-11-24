"""M1.1 · Línea experimental de compra a 30 días: variables de ciclo, dos familias y calibración sin fuga.

Protocolo en ``modelos/config/compra_30d_m11.json`` (``m1.1-protocolo-v1``). Operaciones:

* ``entrenar_m11``: congela el protocolo, construye fotografías con variables v2, ejecuta la validación
  temporal de origen creciente (cada origen se predice con modelos entrenados solo con cortes cuyas
  etiquetas maduraron antes), selecciona por familia y global, decide la calibración con predicciones
  fuera de muestra, entrena los modelos finales con todo el desarrollo y exporta artefactos JSON.
  No lee la comprobación histórica.
* ``evaluar_m11``: verifica la congelación y mide julio–septiembre de 2026 (exploratorio) frente a v1,
  M1 v2, recencia, la regla de 30 días y la tasa constante, en la población elegible y en la atendible.

Solo este módulo y ``compra.ajustar_logistica`` importan scikit-learn. Los artefactos se puntúan con
``modelos.inferencia`` / ``modelos.boosting`` (biblioteca estándar). Ningún candidato se promueve.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import metricas as M
from .compra import (LIMITACIONES, DependenciaEntrenamiento, ProtocoloError, _atendibles, _canon, _comprobar_version_protocolo,
                     _hoy_utc, _json, _leer, _primer_fin_de_mes_posterior, ajustar_logistica, conteos, entorno,
                     huella_protocolo, identidad_protocolo, poblacion)
from .compra_m1_ejecucion import (congelar, exigir_formato_nuevo, guardar_protocolo_inicial, huellas_codigo, metadatos_comunes,
                                   publicar_evaluacion, verificar)
from .datos import DatosAceptados, cargar_datos
from .ejecucion import json_bytes
from .inferencia import FORMATO, FORMATO_BOOSTING, MODELO_ID, cargar_artefacto, desde_dict, sellar
from .variables import (HORIZONTE_DIAS, VERSION_VARIABLES_V2, ajustar_transformaciones, aplicar_transformaciones,
                        construir_fotografias, cortes_mensuales, historial_compras)

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_M11 = RAIZ / "modelos" / "config" / "compra_30d_m11.json"
REFERENCIAS_REGISTRO = RAIZ / "var" / "modelos" / "compra_30d"


def _d(x: str) -> date:
    return date.fromisoformat(x)


# Datos -------------------------------------------------------------------------------------
def preparar(datos: DatosAceptados, config: dict) -> dict[str, Any]:
    version = config.get("version_variables", VERSION_VARIABLES_V2)
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    cortes = cortes_mensuales(_d(config["cortes"]["desde"]), _d(config["cortes"]["hasta"]))
    filas = construir_fotografias(datos.clientes, historial, cortes, datos.observado_hasta, horizonte=config["horizonte_dias"],
                                  contexto={"revision_datos": datos.revision, "huella_datos": datos.huella_datos},
                                  version=version)
    a, b = config["bloques"]["desarrollo"]
    t0, t1 = config["bloques"]["comprobacion_historica"]
    desarrollo = [f for f in filas if _d(a) <= f["corte"] <= _d(b)]
    prueba = [f for f in filas if _d(t0) <= f["corte"] <= _d(t1)]
    por_corte: dict[date, list[dict]] = {}
    for f in poblacion(desarrollo):
        por_corte.setdefault(f["corte"], []).append(f)
    return {"historial": historial, "filas": filas, "desarrollo": desarrollo, "prueba": prueba, "por_corte": por_corte}


def cortes_entrenamiento(cortes: list[date], origen: date, horizonte: int) -> list[date]:
    """Cortes cuyas etiquetas maduraron antes de predecir ``origen`` (t + horizonte <= origen)."""
    return [t for t in cortes if t + timedelta(days=horizonte) <= origen]


def origenes(config: dict, cortes_dev: list[date]) -> list[date]:
    a, b = (_d(x) for x in config["validacion_temporal"]["origenes"])
    return [c for c in cortes_dev if a <= c <= b]


# Especificaciones y ajuste ------------------------------------------------------------------
def especificaciones(config: dict) -> list[dict]:
    specs = []
    fl, fb = config["familias"]["logistica"], config["familias"]["boosting"]
    for nombre, variables in config["combinaciones"].items():
        for C in fl["C"]:
            specs.append({"id": f"log-{nombre}-c{C}", "familia": "logistica", "combinacion": nombre, "variables": variables,
                          "C": C, "complejidad": C})
        for prof in fb["max_depth"]:
            for n in fb["n_estimators"]:
                for lr in fb["learning_rate"]:
                    for hoja in fb["min_samples_leaf"]:
                        specs.append({"id": f"gb-{nombre}-d{prof}-n{n}-lr{lr}-h{hoja}", "familia": "boosting", "combinacion": nombre,
                                      "variables": variables, "max_depth": prof, "n_estimators": n, "learning_rate": lr,
                                      "min_samples_leaf": hoja, "complejidad": n * prof / hoja})
    return specs


def spec_control(config: dict) -> dict:
    c = config["control"]
    return {"id": c["nombre"], "familia": "logistica", "combinacion": "base_m1", "variables": c["combinacion_variables"],
            "C": c["C"], "complejidad": c["C"], "control": True}


def _estimador_logistica(config: dict) -> dict:
    fl = config["familias"]["logistica"]
    return {"solver": fl["solver"], "max_iter": fl["max_iter"], "tol": fl["tol"], "class_weight": fl["class_weight"],
            "semilla": config["semilla"]}


def ajustar(spec: dict, filas: list[dict], config: dict) -> tuple[dict, Callable[[list[dict]], list[float]]]:
    """Ajusta transformaciones y modelo SOLO con ``filas``; devuelve las partes del artefacto y la predicción de sklearn."""
    base = {"formato": FORMATO, "modelo_id": MODELO_ID, "version_variables": VERSION_VARIABLES_V2,
            "horizonte_dias": config["horizonte_dias"], "variables": list(spec["variables"]), "umbral": config["umbral"]["valor"],
            "disponible_desde": config["disponible_desde"]}
    if spec["familia"] == "logistica":
        trans, b0, w, predecir = ajustar_logistica(filas, spec["variables"], spec["C"], _estimador_logistica(config))
        return base | {"transformaciones": trans, "intercepto": b0, "pesos": w}, predecir
    try:
        import numpy as np
        from sklearn.ensemble import GradientBoostingClassifier
    except ImportError as exc:
        raise DependenciaEntrenamiento("Entrenar requiere: pip install -r requirements-modelos.txt") from exc
    trans = ajustar_transformaciones(filas, spec["variables"])
    X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
    y = np.array([int(f["compra_30d"]) for f in filas])
    modelo = GradientBoostingClassifier(loss="log_loss", max_depth=spec["max_depth"], n_estimators=spec["n_estimators"],
                                        learning_rate=spec["learning_rate"], min_samples_leaf=spec["min_samples_leaf"],
                                        subsample=config["familias"]["boosting"]["subsample"], random_state=config["semilla"])
    modelo.fit(X, y)
    prior = float(y.mean())
    arboles = []
    for est in modelo.estimators_[:, 0]:
        t = est.tree_
        arboles.append({"nodos": [
            {"izq": int(t.children_left[i]), "der": int(t.children_right[i]),
             "variable": int(t.feature[i]) if t.children_left[i] != -1 else -1,
             "umbral": float(t.threshold[i]) if t.children_left[i] != -1 else 0.0,
             "valor": float(t.value[i][0][0])} for i in range(t.node_count)]})
    partes = base | {"formato": FORMATO_BOOSTING, "transformaciones": trans, "puntaje_inicial": float(np.log(prior / (1 - prior))),
                     "tasa_aprendizaje": spec["learning_rate"], "arboles": arboles}

    def predecir(lote: list[dict]) -> list[float]:
        return [float(p) for p in modelo.predict_proba(np.array([aplicar_transformaciones(f, trans) for f in lote], dtype=float))[:, 1]]

    return partes, predecir


def _sellar(partes: dict, version: str, extra: dict | None = None, calibracion: dict | None = None) -> dict:
    d = dict(partes, version=version, **(extra or {}))
    if calibracion:
        d["calibracion"] = calibracion
    return sellar(d)


def _artefacto_temporal(spec: dict, partes: dict):
    return desde_dict(_sellar(partes, f"m11-{spec['id']}-tmp"))


# Calibración --------------------------------------------------------------------------------
def soporte_suficiente(pares: list[tuple[float, int, date]], minimo: dict) -> bool:
    pos = sum(y for _, y, _ in pares)
    return (len(pares) >= minimo["filas"] and pos >= minimo["positivos"] and len(pares) - pos >= minimo["negativos"]
            and len({c for _, _, c in pares}) >= minimo["cortes"])


def ajustar_platt(pares: list[tuple[float, int, date]]) -> dict:
    """Regresión logística de un parámetro sobre el puntaje bruto (sin regularización efectiva)."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    z = np.array([[p[0]] for p in pares], dtype=float)
    y = np.array([p[1] for p in pares])
    m = LogisticRegression(C=1e10, solver="lbfgs", max_iter=10000, tol=1e-12).fit(z, y)
    return {"tipo": "sigmoide", "a": float(m.coef_[0][0]), "b": float(m.intercept_[0])}


def _sig(z: float) -> float:
    import math
    return 1 / (1 + math.exp(-max(-35, min(35, z))))


# Entrenamiento ------------------------------------------------------------------------------
def _resumen_origen(filas: list[dict], prob: Callable[[dict], float]) -> dict:
    r = M.ranking_k(filas, prob, 10)
    return {"top10": r["aciertos"], "k10": r["k_efectivo"], "ap": M.average_precision(filas, prob),
            "log_loss": M.log_loss(filas, prob), "brier": M.brier(filas, prob), "n": len(filas), "positivos": r["positivos"]}


def entrenar_m11(datos: DatosAceptados, config: dict, salida: str | Path) -> dict[str, Any]:
    salida = Path(salida)
    if (salida / "congelacion.json").exists():
        raise FileExistsError(f"{salida} ya contiene una ejecución; usa otra carpeta")
    salida.mkdir(parents=True, exist_ok=True)
    _comprobar_version_protocolo(salida, config)
    # 1. El protocolo queda guardado antes de ajustar nada.
    protocolo = {"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config),
                 "guardado_en": _hoy_utc()}
    arch = guardar_protocolo_inicial(salida, config, protocolo)  # formato 3: todo se publica al congelar
    ds = preparar(datos, config)
    h = config["horizonte_dias"]
    cortes_dev = sorted(ds["por_corte"])
    pendientes = [f for f in ds["desarrollo"] if f["elegibilidad"] == "elegible" and f["estado_etiqueta"] != "madura"]
    if pendientes:
        raise ValueError("El desarrollo tiene etiquetas pendientes; no se puede ajustar")
    origs = origenes(config, cortes_dev)
    specs = especificaciones(config) + [spec_control(config)]
    # 2. Validación temporal de origen creciente.
    validacion: dict[str, Any] = {}
    oos: dict[str, list[tuple[float, int, date, str]]] = {}
    for spec in specs:
        por_origen = []
        oos[spec["id"]] = []
        for d in origs:
            entren = [f for t in cortes_entrenamiento(cortes_dev, d, h) for f in ds["por_corte"][t]]
            partes, _ = ajustar(spec, entren, config)
            art = _artefacto_temporal(spec, partes)
            filas = ds["por_corte"][d]
            por_origen.append(dict(_resumen_origen(filas, art.probabilidad), origen=d.isoformat(),
                                   cortes_entrenamiento=len(cortes_entrenamiento(cortes_dev, d, h))))
            oos[spec["id"]].extend((art.puntaje_bruto(f), int(f["compra_30d"]), d, f["cliente_id"]) for f in filas)
        n = len(por_origen)
        validacion[spec["id"]] = {
            "spec": {k: v for k, v in spec.items() if k != "variables"} | {"n_variables": len(spec["variables"])},
            "precision_media_top10": sum(o["top10"] / o["k10"] for o in por_origen) / n,
            "aciertos_top10": sum(o["top10"] for o in por_origen), "denominador_top10": sum(o["k10"] for o in por_origen),
            "average_precision_media": sum(o["ap"] for o in por_origen if o["ap"] is not None) / n,
            "log_loss": sum(o["log_loss"] * o["n"] for o in por_origen) / sum(o["n"] for o in por_origen),
            "brier": sum(o["brier"] * o["n"] for o in por_origen) / sum(o["n"] for o in por_origen),
            "por_origen": por_origen}

    def clave(sid):
        v = validacion[sid]
        s = v["spec"]
        return (-round(v["precision_media_top10"], 12), -round(v["average_precision_media"], 12), round(v["log_loss"], 12),
                s["n_variables"], 0 if s["familia"] == "logistica" else 1, s["complejidad"])

    candidatos = [s["id"] for s in specs if not s.get("control")]
    mejor = {fam: sorted([i for i in candidatos if validacion[i]["spec"]["familia"] == fam], key=clave)[0] for fam in ("logistica", "boosting")}
    global_id = sorted(candidatos, key=clave)[0]
    # 3. Calibración: evaluación en desarrollo y calibrador final, solo con predicciones fuera de muestra.
    minimo = config["calibracion"]["soporte_minimo"]
    evaluar_ids = sorted(set(mejor.values()) | {config["control"]["nombre"]})
    calibracion: dict[str, Any] = {}
    for sid in evaluar_ids:
        pares = [(z, y, c) for z, y, c, _ in oos[sid]]
        crudo, cal, detalle = [], [], []
        for d in origs[-6:]:
            previos = [p for p in pares if p[2] + timedelta(days=h) <= d]
            objetivo = [p for p in pares if p[2] == d]
            if not soporte_suficiente(previos, minimo):
                detalle.append({"origen": d.isoformat(), "soporte": False, "filas_calibrador": len(previos)})
                continue
            pl = ajustar_platt(previos)
            crudo.extend((_sig(z), y) for z, y, _ in objetivo)
            cal.extend((_sig(pl["a"] * z + pl["b"]), y) for z, y, _ in objetivo)
            detalle.append({"origen": d.isoformat(), "soporte": True, "filas_calibrador": len(previos), "a": pl["a"], "b": pl["b"]})

        def ll(lst):
            filas = [{"compra_30d": y, "p": p} for p, y in lst]
            return M.log_loss(filas, lambda f: f["p"]), M.brier(filas, lambda f: f["p"])
        res = {"origenes_evaluados": detalle, "filas_evaluadas": len(crudo)}
        if crudo:
            (ll_c, br_c), (ll_k, br_k) = ll(crudo), ll(cal)
            res.update({"log_loss_sin_calibrar": ll_c, "log_loss_calibrado": ll_k, "brier_sin_calibrar": br_c, "brier_calibrado": br_k,
                        "prob_media_sin_calibrar": sum(p for p, _ in crudo) / len(crudo), "prob_media_calibrada": sum(p for p, _ in cal) / len(cal),
                        "tasa_observada": sum(y for _, y in crudo) / len(crudo)})
        soporte_final = soporte_suficiente(pares, minimo)
        res["soporte_final"] = {"filas": len(pares), "positivos": sum(y for _, y, _ in pares), "cortes": len({c for _, _, c in pares}),
                                "suficiente": soporte_final}
        res["calibrar"] = bool(crudo) and soporte_final and res["log_loss_calibrado"] < res["log_loss_sin_calibrar"]
        res["calibrador_final"] = ajustar_platt(pares) if soporte_final else None
        res["motivo"] = ("mejora el log loss fuera de muestra en desarrollo" if res["calibrar"] else
                         "sin soporte suficiente" if not soporte_final or not crudo else "no mejora el log loss en desarrollo")
        calibracion[sid] = res
    # 4. Modelos finales con todo el desarrollo cuyas etiquetas maduraron antes de la comprobación.
    inicio_prueba = _d(config["bloques"]["comprobacion_historica"][0])
    inicio_prueba = min(f["corte"] for f in ds["prueba"]) if ds["prueba"] else inicio_prueba
    cortes_final = cortes_entrenamiento(cortes_dev, inicio_prueba, h)
    entren = [f for t in cortes_final for f in ds["por_corte"][t]]
    spec_por_id = {s["id"]: s for s in specs}
    artefactos, equivalencia = {}, {}
    for papel, sid in [("global", global_id), ("mejor_logistica", mejor["logistica"]), ("mejor_boosting", mejor["boosting"]),
                       ("control", config["control"]["nombre"])]:
        if papel != "global" and sid == global_id:
            artefactos[papel] = artefactos["global"]
            continue
        spec = spec_por_id[sid]
        partes, predecir = ajustar(spec, entren, config)
        cal = calibracion.get(sid, {})
        extra = {"descripcion": f"M1.1 {spec['familia']} {spec['id']}", "poblacion": "recompra", "version_protocolo": config["version_protocolo"],
                 "especificacion": {k: v for k, v in spec.items() if k != "variables"}, "origen_datos": config["origen_datos"],
                 "entrenamiento": {"cortes": [c.isoformat() for c in cortes_final], "filas": len(entren),
                                   "positivos": sum(f["compra_30d"] for f in entren), "huella_datos": datos.huella_datos,
                                   "revision_datos": datos.revision}}
        sin_cal = _sellar(partes, f"compra_30d-m11-{sid}", extra)
        version_sc = f"compra_30d-m11-{sid}-" + sin_cal["huella"][:8]
        sin_cal = _sellar(partes, version_sc, extra)
        a = desde_dict(sin_cal)
        ref = predecir(entren)
        dif = max(abs(x - a.probabilidad(f)) for x, f in zip(ref, entren))
        if dif > config["tolerancia_probabilidad"]:
            raise ValueError(f"{sid}: la inferencia desde JSON difiere de sklearn en {dif:g}")
        equivalencia[sid] = {"diferencia_maxima_sin_calibrar": dif, "filas": len(entren)}
        entrada = {"id": sid, "sin_calibrar": sin_cal}
        if cal.get("calibrador_final"):
            calibrada = _sellar(partes, version_sc + "-cal", extra, dict(cal["calibrador_final"], ajustada_con={
                "origenes": [o.isoformat() for o in origs], "filas": cal["soporte_final"]["filas"],
                "positivos": cal["soporte_final"]["positivos"], "metodo": "predicciones fuera de muestra de la validación temporal"}))
            ac = desde_dict(calibrada)
            import numpy as np  # referencia independiente: probabilidad de sklearn -> logit -> Platt con numpy
            pr = np.clip(np.array(ref, dtype=float), 1e-300, 1 - 1e-16)
            z_ref = np.log(pr / (1 - pr))
            p_ref = 1 / (1 + np.exp(-(cal["calibrador_final"]["a"] * z_ref + cal["calibrador_final"]["b"])))
            dif_c = float(max(abs(x - ac.probabilidad(f)) for x, f in zip(p_ref, entren)))
            if dif_c > config["tolerancia_probabilidad"]:
                raise ValueError(f"{sid}: la calibración desde JSON difiere de la referencia en {dif_c:g}")
            equivalencia[sid]["diferencia_maxima_calibrado"] = dif_c
            entrada["calibrado"] = calibrada
        entrada["usar"] = "calibrado" if cal.get("calibrar") else "sin_calibrar"
        artefactos[papel] = entrada
    for papel, e in artefactos.items():
        for variante in ("sin_calibrar", "calibrado"):
            if variante in e:
                arch[f"artefacto_{papel}_{variante}.json"] = json_bytes(e[variante])
    seleccionado = artefactos["global"][artefactos["global"]["usar"]]
    arch["artefacto.json"] = json_bytes(seleccionado)
    # 5. Referencias congeladas (solo lectura) y congelación.
    refs = {}
    for nombre, v in (("v1_congelada", "v1"), ("m1_v2_congelado", "v2")):
        art = cargar_artefacto(REFERENCIAS_REGISTRO / v)
        refs[nombre] = {"version": art.version, "huella": art.huella}
        arch[f"referencia_{nombre}.json"] = json_bytes(art.datos)
    meta, volatiles = metadatos_comunes(config, protocolo, refs, datos, cortes_final, h)
    meta.update(artefacto_huella=seleccionado["huella"], artefacto_version=seleccionado["version"],
                artefactos={p: {v: e[v]["huella"] for v in ("sin_calibrar", "calibrado") if v in e} | {"id": e["id"], "usar": e["usar"]}
                            for p, e in artefactos.items()},
                equivalencia_json_sklearn=equivalencia, codigo=huellas_codigo("compra_m11.py"))
    seleccion = {"criterio": config["seleccion"], "global": global_id, "por_familia": mejor, "control": config["control"]["nombre"],
                 "validacion_temporal": validacion, "origenes": [o.isoformat() for o in origs], "calibracion": calibracion}
    arch["seleccion.json"] = json_bytes(seleccion)
    arch["datos.json"] = json_bytes(dict(datos.descripcion(), desarrollo=conteos(ds["desarrollo"])))
    arch["entorno.json"] = json_bytes(entorno())
    arch["predicciones_validacion_temporal.csv"] = _oos_bytes(oos, evaluar_ids + [global_id])
    congelacion = congelar(salida, "m11", arch, meta, volatiles)
    return {"seleccion": seleccion, "congelacion": congelacion, "artefactos": artefactos}


def _oos_bytes(oos: dict, ids: list[str]) -> bytes:
    import io
    fh = io.StringIO(newline="")
    w = csv.writer(fh, lineterminator="\n")
    w.writerow(["especificacion", "origen", "cliente_id", "puntaje_bruto", "compra_30d"])
    for sid in sorted(set(ids)):
        for z, y, c, cid in oos[sid]:
            w.writerow([sid, c.isoformat(), cid, round(z, 12), y])
    return fh.getvalue().encode("utf-8")


def verificar_congelacion_m11(ejecucion: Path) -> dict:
    """Formato 3: marcador, archivos obligatorios y coherencia completos. Formato 2 (histórico): verificación parcial declarada."""
    return verificar(ejecucion, "m11")


# Evaluación exploratoria --------------------------------------------------------------------
def _decidir(res: dict, refs: dict, config: dict) -> dict:
    metas = config["metas"]
    p_c = res["elegible"]["ranking"]["agregado"]["precision_media_top10"]
    p_r = refs["recencia"]["elegible"]["ranking"]["agregado"]["precision_media_top10"]
    meses = [{"corte": a["corte"], "candidato": a["top10"]["aciertos"], "recencia": b["top10"]["aciertos"]}
             for a, b in zip(res["elegible"]["ranking"]["por_mes"], refs["recencia"]["elegible"]["ranking"]["por_mes"])
             if b["top10"]["aciertos"] - a["top10"]["aciertos"] >= metas["compradores_perdidos_mes_revisar"]]
    b_c, b_k = res["elegible"]["probabilidad"]["brier"], refs["constante"]["elegible"]["probabilidad"]["brier"]
    l_c, l_m = res["elegible"]["probabilidad"]["log_loss"], refs["m1_v2_congelado"]["elegible"]["probabilidad"]["log_loss"]
    cumple = {"mejora_precision_top10": p_c - p_r >= metas["mejora_minima_precision_top10"] - 1e-12, "sin_meses_con_perdida": not meses,
              "brier_no_peor_que_constante": b_c <= b_k, "log_loss_no_peor_que_m1_v2": l_c <= l_m}
    if all(cumple.values()):
        decision = "favorable"
    elif p_c - p_r <= -metas["margen_rechazo_precision_top10"] + 1e-12 or not cumple["brier_no_peor_que_constante"]:
        decision = "rechazado"
    else:
        decision = "inconcluso"
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "cumple": cumple,
            "valores": {"precision_media_top10_candidato": p_c, "precision_media_top10_recencia": p_r, "mejora": p_c - p_r,
                        "brier_candidato": b_c, "brier_constante": b_k, "log_loss_candidato": l_c, "log_loss_m1_v2": l_m},
            "meses_a_revisar": meses}


def _medir(filas: list[dict], sub: list[dict], s: Callable, probabilistico: bool, ks) -> dict:
    out = {"elegible": {"ranking": M.resumen_ranking(filas, s, ks)}, "atendible": {"ranking": M.resumen_ranking(sub, s, ks)}}
    if probabilistico:
        prob = M.resumen_probabilidad(filas, s)
        prob["log_loss"] = M.log_loss(filas, s)
        prob["por_corte"] = [{"corte": c.isoformat(), "n": len(g), "brier": M.brier(g, s), "log_loss": M.log_loss(g, s),
                              "prob_media": sum(s(f) for f in g) / len(g), "tasa_observada": sum(f["compra_30d"] for f in g) / len(g)}
                             for c, g in M.por_corte(filas).items()]
        out["elegible"]["probabilidad"] = prob
    return out


def evaluar_m11(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict[str, Any]:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion_m11(ejecucion)
    exigir_formato_nuevo(cong)
    config = _leer(ejecucion / "config.json")
    info = _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; define un protocolo nuevo")
    ds = preparar(datos, config)
    filas = poblacion(ds["prueba"])
    cortes = sorted({f["corte"] for f in filas})
    atend = _atendibles(datos, cortes)
    sub = [f for f in filas if f["cliente_id"] in atend[f["corte"]]]
    cortes_final = [_d(c) for c in cong["cortes_entrenamiento_final"]]
    entren = [f for f in poblacion(ds["desarrollo"]) if f["corte"] in set(cortes_final)]
    tasa = sum(f["compra_30d"] for f in entren) / len(entren)
    ks = config["k"]
    metodos: dict[str, tuple[Callable, bool]] = {}
    for papel, e in cong["artefactos"].items():
        for v in ("sin_calibrar", "calibrado"):
            if v in e:
                a = cargar_artefacto(ejecucion / f"artefacto_{papel}_{v}.json")
                metodos[f"{papel}:{e['id']}:{v}"] = (a.probabilidad, True)
    for nombre in cong["referencias"]:
        a = cargar_artefacto(ejecucion / f"referencia_{nombre}.json")
        metodos[nombre] = (a.probabilidad, True)
    metodos["recencia"] = (lambda f: -float(f["recencia_dias"]), False)
    metodos["regla_30d"] = (lambda f: float(f["frecuencia_30d"] > 0), False)
    metodos["constante"] = (lambda f: tasa, True)
    resultados = {m: _medir(filas, sub, s, p, ks) for m, (s, p) in metodos.items()}
    g = cong["artefactos"]["global"]
    clave_sel = f"global:{g['id']}:{g['usar']}"
    decision = _decidir(resultados[clave_sel], resultados, config)
    s_sel = metodos[clave_sel][0]
    rec = metodos["recencia"][0]

    def dif_top10(m):
        def media(sc):
            meses = [M.ranking_k(gr, sc, 10) for gr in M.por_corte(m).values()]
            return sum(x["aciertos"] / x["k_efectivo"] for x in meses) / len(meses)
        return media(s_sel) - media(rec)
    boot = config["bootstrap"]
    incertidumbre = {"precision_top10_candidato_menos_recencia": M.bootstrap_clientes(filas, dif_top10, boot["repeticiones"], boot["semilla"]),
                     "nota": "remuestreo de clientes completos (sus tres cortes juntos); clientes repetidos se renombran"}
    a_sel = cargar_artefacto(ejecucion / "artefacto.json")
    cupo = [{"corte": c.isoformat(), "elegibles": len(gr), "seleccionados_umbral": sum(a_sel.probabilidad(f) >= a_sel.umbral for f in gr),
             "aciertos_umbral": sum(f["compra_30d"] for f in gr if a_sel.probabilidad(f) >= a_sel.umbral),
             "cupo_k10": min(10, len(gr)), "aciertos_cupo_k10": M.ranking_k(gr, a_sel.probabilidad, 10)["aciertos"]}
            for c, gr in M.por_corte(filas).items()]
    metricas = {"bloque": "comprobacion_historica",
                "alcance": "comprobación histórica exploratoria: periodo ya inspeccionado; no es validación prospectiva",
                "seleccionado": clave_sel, "poblacion": conteos(ds["prueba"]), "atendible_n": len(sub), "tasa_entrenamiento_final": tasa,
                "resultados": resultados, "incertidumbre_bootstrap_clientes": incertidumbre,
                "experimento_cupo": {"descripcion": "umbral comercial 0,40 frente a cupo fijo K=10 por mes; mide reducción de carga, no mejora predictiva",
                                     "por_mes": cupo}}
    if a_sel.huella != cong["artefacto_huella"]:  # ya verificado; se repite junto al uso
        raise ProtocoloError("artefacto.json no es el artefacto congelado")
    decision_doc = dict(decision, artefacto_version=a_sel.version, origen_datos=config["origen_datos"],
                        version_protocolo=config["version_protocolo"], fechas=cong["fechas"],
                        alcance=metricas["alcance"], limitaciones=LIMITACIONES + ["Ningún candidato M1.1 se promueve automáticamente."])
    pub = publicar_evaluacion(ejecucion, "m11", cong, metricas, decision_doc)
    return {"metricas": pub["metricas"], "decision": pub["decision"]}
