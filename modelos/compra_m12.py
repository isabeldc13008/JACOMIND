"""M1.2 · Orden del cupo por fusión de rangos (recencia + modelo M1 reentrenado).

Protocolo ``modelos/config/compra_30d_m12.json`` (``m1.2-protocolo-v1``):

* ``entrenar_m12`` guarda el protocolo, evalúa en la validación temporal de desarrollo (criterio principal),
  entrena el modelo final, exporta el artefacto con ``politica_orden`` y congela. No lee julio–septiembre.
* ``evaluar_m12`` verifica la congelación, mide la comprobación histórica (exploratoria) y aplica la regla
  de decisión predeclarada.

La fusión cambia solo el ORDEN del cupo del piloto. ``prob_compra_30d`` sigue siendo la probabilidad del
modelo y C1 conserva su orden contractual.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import metricas as M
from .compra import (LIMITACIONES, ProtocoloError, _atendibles, _canon, _comprobar_version_protocolo, _hoy_utc, _json, _leer,
                     _primer_fin_de_mes_posterior, ajustar_logistica, conteos, entorno, huella_protocolo, identidad_protocolo, poblacion)
from .compra_m11 import REFERENCIAS_REGISTRO, cortes_entrenamiento, origenes, preparar
from .compra_m1_ejecucion import (congelar, exigir_formato_nuevo, guardar_protocolo_inicial, huellas_codigo, metadatos_comunes,
                                   publicar_evaluacion, verificar)
from .datos import DatosAceptados, cargar_datos
from .ejecucion import json_bytes
from .inferencia import FORMATO, MODELO_ID, cargar_artefacto, desde_dict, sellar
from .ranking import puntaje_por_corte

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_M12 = RAIZ / "modelos" / "config" / "compra_30d_m12.json"


def _d(x: str) -> date:
    return date.fromisoformat(x)


def ajustar_m12(filas: list[dict], config: dict, version: str = "m12-tmp", extra: dict | None = None):
    m = config["modelo"]
    trans, b0, w, predecir = ajustar_logistica(filas, m["variables"], m["C"], {
        "solver": m["solver"], "max_iter": m["max_iter"], "tol": m["tol"], "class_weight": m["class_weight"], "semilla": config["semilla"]})
    d = {"formato": FORMATO, "modelo_id": MODELO_ID, "version": version, "version_variables": config["version_variables"],
         "horizonte_dias": config["horizonte_dias"], "variables": list(m["variables"]), "transformaciones": trans, "intercepto": b0,
         "pesos": w, "umbral": config["umbral"]["valor"], "disponible_desde": config["disponible_desde"],
         "politica_orden": {"id": config["politica_orden"]["id"], "alcance": config["politica_orden"]["alcance"]}, **(extra or {})}
    return desde_dict(sellar(d)), predecir


def puntajes(filas: list[dict], prob: Callable[[dict], float]) -> dict[str, Callable[[dict], float]]:
    """Los comparadores del protocolo sobre un conjunto de filas (la fusión se calcula por corte)."""
    return {"fusion": puntaje_por_corte(filas, prob), "recencia": lambda f: -float(f["recencia_dias"]),
            "modelo_solo": prob, "regla_30d": lambda f: float(f["frecuencia_30d"] > 0)}


def _media_top10(filas: list[dict], s: Callable) -> float:
    meses = [M.ranking_k(g, s, 10) for g in M.por_corte(filas).values()]
    return sum(x["aciertos"] / x["k_efectivo"] for x in meses) / len(meses)


def _dif_fusion_recencia(filas: list[dict]) -> float:
    """Estadístico del bootstrap: recalcula la fusión dentro de cada corte de la muestra."""
    prob = lambda f: f["_p_modelo"]  # noqa: E731
    return _media_top10(filas, puntaje_por_corte(filas, prob)) - _media_top10(filas, lambda f: -float(f["recencia_dias"]))


def entrenar_m12(datos: DatosAceptados, config: dict, salida: str | Path) -> dict[str, Any]:
    salida = Path(salida)
    if (salida / "congelacion.json").exists():
        raise FileExistsError(f"{salida} ya contiene una ejecución; usa otra carpeta")
    salida.mkdir(parents=True, exist_ok=True)
    _comprobar_version_protocolo(salida, config)
    protocolo = {"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config),
                 "guardado_en": _hoy_utc()}
    arch = guardar_protocolo_inicial(salida, config, protocolo)  # antes de calcular cualquier resultado
    ds = preparar(datos, config)
    h = config["horizonte_dias"]
    cortes_dev = sorted(ds["por_corte"])
    origs = origenes(config, cortes_dev)
    filas_oos: list[dict] = []
    por_origen = []
    for d in origs:
        entren = [f for t in cortes_entrenamiento(cortes_dev, d, h) for f in ds["por_corte"][t]]
        art, _ = ajustar_m12(entren, config)
        grupo = [dict(f, _p_modelo=art.probabilidad(f)) for f in ds["por_corte"][d]]
        filas_oos.extend(grupo)
        p = lambda f: f["_p_modelo"]  # noqa: E731
        sc = puntajes(grupo, p)
        por_origen.append({"origen": d.isoformat(), "cortes_entrenamiento": len(cortes_entrenamiento(cortes_dev, d, h)), "n": len(grupo),
                           "positivos": sum(f["compra_30d"] for f in grupo),
                           **{m: {"top10": M.ranking_k(grupo, s, 10)["aciertos"], "top20": M.ranking_k(grupo, s, 20)["aciertos"],
                                  "ap": M.average_precision(grupo, s)} for m, s in sc.items()}})
    p = lambda f: f["_p_modelo"]  # noqa: E731
    agregado = {}
    for m, s in puntajes(filas_oos, p).items():
        r = M.resumen_ranking(filas_oos, s, config["k"])["agregado"]
        agregado[m] = {k: r[k] for k in ("precision_media_top10", "aciertos_top10", "denominador_top10", "precision_media_top20",
                                         "aciertos_top20", "denominador_top20", "average_precision_media_mensual")}
    boot = config["bootstrap"]
    ic = M.bootstrap_clientes(filas_oos, _dif_fusion_recencia, boot["repeticiones"], boot["semilla"])
    dif = agregado["fusion"]["precision_media_top10"] - agregado["recencia"]["precision_media_top10"]
    desarrollo = {"origenes": [o.isoformat() for o in origs], "por_origen": por_origen, "agregado": agregado,
                  "diferencia_fusion_menos_recencia_top10": dif, "ic95_bootstrap_clientes": ic,
                  "nota": "120 clientes repetidos en 10 cortes: el remuestreo es por cliente completo"}
    # Modelo final con todo el desarrollo maduro antes de la comprobación.
    inicio = min(f["corte"] for f in ds["prueba"])
    cortes_final = cortes_entrenamiento(cortes_dev, inicio, h)
    entren = [f for t in cortes_final for f in ds["por_corte"][t]]
    extra = {"descripcion": "M1.2: modelo M1 reentrenado + orden del cupo por fusión de rangos con recencia",
             "version_protocolo": config["version_protocolo"], "origen_datos": config["origen_datos"],
             "entrenamiento": {"cortes": [c.isoformat() for c in cortes_final], "filas": len(entren),
                               "positivos": sum(f["compra_30d"] for f in entren), "huella_datos": datos.huella_datos,
                               "revision_datos": datos.revision}}
    art, predecir = ajustar_m12(entren, config, "compra_30d-m12-pendiente", extra)
    art, predecir = ajustar_m12(entren, config, "compra_30d-m12-fusion-" + art.huella[:8], extra)
    dif_eq = max(abs(a - art.probabilidad(f)) for a, f in zip(predecir(entren), entren))
    if dif_eq > config["tolerancia_probabilidad"]:
        raise ValueError(f"La inferencia desde JSON difiere de sklearn en {dif_eq:g}")
    arch["artefacto.json"] = json_bytes(art.datos)
    refs = {}
    for nombre, v in (("v1_congelada", "v1"), ("m1_v2_congelado", "v2")):
        r = cargar_artefacto(REFERENCIAS_REGISTRO / v)
        refs[nombre] = {"version": r.version, "huella": r.huella}
        arch[f"referencia_{nombre}.json"] = json_bytes(r.datos)
    meta, volatiles = metadatos_comunes(config, protocolo, refs, datos, cortes_final, h)
    meta.update(artefacto_huella=art.huella, artefacto_version=art.version, codigo=huellas_codigo("compra_m12.py"),
                equivalencia_json_sklearn={"diferencia_maxima": dif_eq, "filas": len(entren)})
    arch["desarrollo.json"] = json_bytes(desarrollo)
    arch["datos.json"] = json_bytes(dict(datos.descripcion(), desarrollo=conteos(ds["desarrollo"])))
    arch["entorno.json"] = json_bytes(entorno())
    cong = congelar(salida, "m12", arch, meta, volatiles)
    return {"desarrollo": desarrollo, "congelacion": cong, "artefacto": art.datos}


def verificar_congelacion_m12(ejecucion: Path) -> dict:
    """Formato 3: marcador, archivos obligatorios y coherencia completos. Formato 2 (histórico): verificación parcial declarada."""
    return verificar(ejecucion, "m12")


def decidir(desarrollo: dict, comprobacion: dict, config: dict) -> dict:
    metas = config["metas"]
    dif = desarrollo["diferencia_fusion_menos_recencia_top10"]
    ic = desarrollo["ic95_bootstrap_clientes"]
    meses = [{"corte": a["corte"], "fusion": a["top10"]["aciertos"], "recencia": b["top10"]["aciertos"]}
             for a, b in zip(comprobacion["fusion"]["elegible"]["por_mes"], comprobacion["recencia"]["elegible"]["por_mes"])
             if b["top10"]["aciertos"] - a["top10"]["aciertos"] >= metas["comprobacion_sin_meses_con_perdida"]]
    cumple = {"mejora_desarrollo_top10": dif >= metas["mejora_minima_precision_top10"] - 1e-12,
              "ic95_excluye_cero": ic.get("p2_5", -1) > 0,
              "comprobacion_sin_meses_con_perdida": not meses}
    if all(cumple.values()):
        decision = "favorable"
    elif dif <= -metas["margen_rechazo_precision_top10"] + 1e-12:
        decision = "rechazado"
    else:
        decision = "inconcluso"
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "cumple": cumple,
            "valores": {"desarrollo_fusion_top10": desarrollo["agregado"]["fusion"]["precision_media_top10"],
                        "desarrollo_recencia_top10": desarrollo["agregado"]["recencia"]["precision_media_top10"],
                        "diferencia": dif, "ic95": [ic.get("p2_5"), ic.get("p97_5")]},
            "meses_a_revisar": meses}


def evaluar_m12(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict[str, Any]:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion_m12(ejecucion)
    exigir_formato_nuevo(cong)
    config = _leer(ejecucion / "config.json")
    info = _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; define un protocolo nuevo")
    ds = preparar(datos, config)
    filas = poblacion(ds["prueba"])
    atend = _atendibles(datos, sorted({f["corte"] for f in filas}))
    sub = [f for f in filas if f["cliente_id"] in atend[f["corte"]]]
    art = cargar_artefacto(ejecucion / "artefacto.json")
    entren = [f for f in poblacion(ds["desarrollo"]) if f["corte"].isoformat() in set(cong["cortes_entrenamiento_final"])]
    tasa = sum(f["compra_30d"] for f in entren) / len(entren)
    refs = {n: cargar_artefacto(ejecucion / f"referencia_{n}.json") for n in cong["referencias"]}

    def metodos(conjunto):
        base = puntajes(conjunto, art.probabilidad)
        base.update({n: a.probabilidad for n, a in refs.items()})
        base["constante"] = lambda f: tasa
        return base
    resultados = {}
    for nombre in metodos(filas):
        resultados[nombre] = {pob: M.resumen_ranking(conj, metodos(conj)[nombre], config["k"]) for pob, conj in (("elegible", filas), ("atendible", sub))}
    comprobacion = {n: {p: {"por_mes": r[p]["por_mes"], "agregado": r[p]["agregado"]} for p in r} for n, r in resultados.items()}
    desarrollo = _leer(ejecucion / "desarrollo.json")
    decision = decidir(desarrollo, comprobacion, config)
    metricas = {"bloque": "comprobacion_historica",
                "alcance": "comprobación histórica exploratoria: periodo ya inspeccionado; el criterio principal es la validación temporal",
                "poblacion": conteos(ds["prueba"]), "atendible_n": len(sub), "resultados": comprobacion,
                "probabilidad_modelo": {"brier": M.brier(filas, art.probabilidad), "log_loss": M.log_loss(filas, art.probabilidad),
                                        "prob_media": sum(art.probabilidad(f) for f in filas) / len(filas),
                                        "tasa_observada": sum(f["compra_30d"] for f in filas) / len(filas)}}
    doc = dict(decision, artefacto_version=art.version, version_protocolo=config["version_protocolo"],
               origen_datos=config["origen_datos"], fechas=cong["fechas"],
               alcance=metricas["alcance"], limitaciones=LIMITACIONES + ["La fusión define el orden del cupo; no es una probabilidad.",
                                                                         "Ningún artefacto M1.2 se promueve automáticamente."])
    pub = publicar_evaluacion(ejecucion, "m12", cong, metricas, doc)
    return {"metricas": pub["metricas"], "decision": pub["decision"]}

