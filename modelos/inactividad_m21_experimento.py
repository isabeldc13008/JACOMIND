"""M2.1 · Experimento de inactividad a 60 días con candidatos estructurales (protocolo ``m21-protocolo-v1``).

Misma etiqueta, poblaciones, bloques, métricas, metas, regla de decisión y garantías de integridad que M2
(``modelos/inactividad_experimento.py``, cuyas funciones se reutilizan sin cambios). Lo nuevo:

* Variables ``inactividad_60d-variables-v2`` (``modelos/inactividad_m21.py``), con la base instalada bajo un supuesto
  declarado de disponibilidad.
* Cuatro familias predeclaradas: Poisson (m ∈ {30, 90, 180}), supervivencia contraída (k ∈ {1, 3, 10}),
  logística reducida y logística con instalaciones (C ∈ {0,1; 1; 10}). Solo la logística necesita scikit-learn.
* Selección en validación por precisión media a 10, sensibilidad, Brier, complejidad e hiperparámetro.
* La comprobación histórica ya fue vista en M2: es exploratoria y reutilizada (ver la configuración).
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import metricas as M
from .compra import ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inactividad import DEFINICION_ETIQUETA, ETIQUETA, HORIZONTE_DIAS, MODELO_ID, UMBRAL_FRIO_DIAS, fotografias
from .inactividad_experimento import (COLUMNAS_BASE, _escribir_csv, _media_top, _recencia, ajustar, aprendibles, cobertura_por_fuente,
                                      conteos, cortes_bloque, decidir, fechas_piloto, medir, regla_existente, verificar_fronteras)
from .inactividad_m21 import (FORMATO_POISSON, FORMATO_SUPERVIVENCIA, RENOVACION_DIAS, instalaciones_por_cliente,
                              variables_inactividad_v2)
from .inferencia import FORMATO, cargar_artefacto, desde_dict, sellar
from .variables import FUNCION, VERSION_INACTIVIDAD_V2, historial_compras

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "inactividad_60d_m21.json"
VERSION_PROTOCOLO = "m21-protocolo-v1"
REGLA_DECISION = "m2-decision-v1"
METRICAS_VERSION = M.METRICAS_VERSION + "+inactividad"
MARCADOR_CONGELACION = "congelacion.json"
MARCADOR_EVALUACION = "evaluacion.json"
LIMITACIONES = [
    "Datos sintéticos de 120 clientes ya inspeccionados.",
    "M2.1 se diseñó después de conocer los resultados de M2 en validación y comprobación: la comprobación histórica "
    "(julio y agosto de 2026) es exploratoria y REUTILIZADA; no confirma una mejora. Solo el piloto prospectivo o datos "
    "empresariales pueden hacerlo.",
    "La base instalada se usa con el supuesto no verificable de que cada instalación se conoce desde su fecha_inicio.",
    "Mide el riesgo de llegar a 90 días sin compra; no es abandono ni efecto causal del seguimiento.",
]


def _leer(ruta: Path) -> Any:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def cargar_config(ruta: str | Path | None = None) -> dict:
    return _leer(Path(ruta or CONFIG_DEFECTO))


def es_m21(config: dict) -> bool:
    return config.get("version_protocolo", "").startswith("m21-")


def identidad_protocolo(config: dict) -> dict:
    variables = sorted({v for f in config["familias"].values() for v in f.get("variables", [])})
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": VERSION_INACTIVIDAD_V2, "transformaciones": {v: FUNCION.get(v) for v in variables},
                       "definicion_etiqueta": DEFINICION_ETIQUETA, "metricas": METRICAS_VERSION, "regla_decision": REGLA_DECISION,
                       "formatos": [FORMATO, FORMATO_POISSON, FORMATO_SUPERVIVENCIA], "renovacion_dias": RENOVACION_DIAS}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config)).encode()).hexdigest()


def cargar_instalaciones(datos: DatosAceptados) -> dict[str, list[dict]]:
    from pipeline.operaciones import _load
    return instalaciones_por_cliente(_load(datos.directorio, "base_instalada.csv", "instalaciones"))


def preparar(datos: DatosAceptados, config: dict) -> dict:
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    inst = cargar_instalaciones(datos)
    altas = {str(c["cliente_id"]): c["fecha_alta"] for c in datos.clientes}
    cortes = sorted({c for b in config["bloques"] for c in cortes_bloque(config, b)})
    filas = fotografias(datos.clientes, historial, cortes, datos.observado_hasta,
                        {"revision_datos": datos.revision, "huella_datos": datos.huella_datos})
    for f in filas:
        if f["poblacion"] in ("aprendible", "estructural"):
            f.update(variables_inactividad_v2(historial.get(f["cliente_id"], []), f["corte"], altas[f["cliente_id"]],
                                              inst.get(f["cliente_id"], [])))
            f["version_variables"] = VERSION_INACTIVIDAD_V2
    bloques = {b: [f for f in filas if f["corte"] in set(cortes_bloque(config, b))] for b in config["bloques"]}
    return {"historial": historial, "filas": filas, "bloques": bloques, "fronteras": verificar_fronteras(bloques, config),
            "instalaciones": {"clientes": len(inst), "registros": sum(len(v) for v in inst.values())}}


def cobertura_m21(datos: DatosAceptados) -> dict:
    c = cobertura_por_fuente(datos)
    no_usadas = dict(c.pop("no_usadas"))
    no_usadas.pop("base_instalada", None)
    c["base_instalada"] = {"estado": "sin cobertura declarada: SUPUESTO de disponibilidad desde fecha_inicio",
                           "uso": "instalaciones_vigentes y renovacion_antes_del_cruce (fecha_inicio <= corte)"}
    c["no_usadas"] = no_usadas
    return c


# Candidatos --------------------------------------------------------------------------------------------------
def candidato_id(familia: str, valor) -> str:
    return f"{familia}-{str(valor).replace('.', '_')}"


def _comunes(config: dict, datos: DatosAceptados, ajuste: list[dict], familia: str, valor, descripcion: str) -> dict:
    return {"modelo_id": MODELO_ID, "version": "pendiente", "version_variables": VERSION_INACTIVIDAD_V2, "descripcion": descripcion,
            "horizonte_dias": HORIZONTE_DIAS, "umbral_frio_dias": UMBRAL_FRIO_DIAS, "umbral": None,
            "politica": {"tipo": "cupo", "k": config["k_principal"], "orden": "probabilidad descendente, desempate por cliente_id"},
            "poblacion": "aprendible: alta <= corte, al menos una compra confirmada y recencia 30–89 días",
            "familia": familia, "hiperparametro": {config["familias"][familia]["hiperparametro"]: valor},
            "disponible_desde": config["disponible_desde"], "origen_datos": config["origen_datos"],
            "version_protocolo": config["version_protocolo"], "etiqueta": DEFINICION_ETIQUETA,
            "entrenamiento": {"cortes": sorted({f["corte"].isoformat() for f in ajuste}), "filas": len(ajuste),
                              "eventos": sum(f[ETIQUETA] for f in ajuste), "huella_datos": datos.huella_datos,
                              "revision_datos": datos.revision}}


def _versionar(borrador: dict, cid: str) -> dict:
    borrador["version"] = f"inactividad_60d-m21-{cid}-" + sellar(borrador)["huella"][:8]
    return sellar(borrador)


def construir_candidatos(aj: list[dict], va: list[dict], config: dict, datos: DatosAceptados, historial) -> tuple[dict, dict]:
    """Devuelve ({cid: candidato}, {cid: equivalencia}) ajustados SOLO con el bloque de ajuste."""
    from .supervivencia import ajustar_curva
    candidatos, equivalencia = {}, {}
    fam = config["familias"]
    tasa0 = sum(f["dias_compra_180d"] for f in aj) / sum(f["exposicion_180d"] for f in aj)
    for m in fam["poisson"]["valores"]:
        cid = candidato_id("poisson", m)
        d = _comunes(config, datos, aj, "poisson", m, f"Poisson con contracción m={m} días: p = exp(-lambda · (90 - recencia)).")
        d |= {"formato": FORMATO_POISSON, "tasa_poblacional_diaria": tasa0, "contraccion_dias": float(m)}
        candidatos[cid] = {"familia": "poisson", "valor": m, "complejidad": fam["poisson"]["complejidad"], "variables": [], "artefacto": _versionar(d, cid)}
    hasta = date.fromisoformat(fam["supervivencia"]["curva_hasta"])
    if max(f["corte"] for f in aj) != hasta:
        raise ProtocoloError(f"curva_hasta {hasta} no es el último corte de ajuste")
    curva = ajustar_curva(historial, datos.clientes, hasta)
    for k in fam["supervivencia"]["valores"]:
        cid = candidato_id("supervivencia", k)
        d = _comunes(config, datos, aj, "supervivencia", k, f"Supervivencia contraída k={k}: p = S(90) / S(recencia).")
        d |= {"formato": FORMATO_SUPERVIVENCIA, "curva": curva, "k_contraccion": float(k)}
        candidatos[cid] = {"familia": "supervivencia", "valor": k, "complejidad": fam["supervivencia"]["complejidad"], "variables": [],
                           "artefacto": _versionar(d, cid)}
    for familia in ("logistica_reducida", "logistica_instalaciones"):
        variables = fam[familia]["variables"]
        for C in fam[familia]["valores"]:
            cid = candidato_id(familia, C)
            trans, b0, w, predecir = ajustar(aj, variables, C, config)
            d = _comunes(config, datos, aj, familia, C, f"Regresión logística L2 (C={C}) sobre {familia}.")
            d |= {"formato": FORMATO, "variables": list(variables), "transformaciones": trans, "intercepto": b0, "pesos": w,
                  "estimador": config["estimador"], "semilla": config["semilla"]}
            art_d = _versionar(d, cid)
            art = desde_dict(json.loads(json.dumps(art_d)))
            dif = max(abs(a - art.probabilidad(f)) for a, f in zip(predecir(aj + va), aj + va))
            if dif > config["tolerancia_probabilidad"]:
                raise ValueError(f"{cid}: la probabilidad del artefacto recargado difiere de sklearn en {dif:g}")
            equivalencia[cid] = {"diferencia_maxima": dif, "filas": len(aj) + len(va)}
            candidatos[cid] = {"familia": familia, "valor": C, "complejidad": fam[familia]["complejidad"], "variables": variables, "artefacto": art_d}
    for cid, c in candidatos.items():  # todo artefacto se usa tal como se recarga desde JSON
        c["modelo"] = desde_dict(json.loads(json.dumps(c["artefacto"])))
    return candidatos, equivalencia


# Entrenamiento -----------------------------------------------------------------------------------------------
def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID or not es_m21(config):
        raise ProtocoloError("La configuración no es un protocolo M2.1 de inactividad_60d")
    if (salida / "config.json").exists() and canon(_leer(salida / "config.json")) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    ds = preparar(datos, config)
    aj, va = aprendibles(ds["bloques"]["ajuste"]), aprendibles(ds["bloques"]["validacion"])
    conteo_bloques = {b: conteos(f) for b, f in ds["bloques"].items()}
    faltan = [f"{b}: {c}" for b, filas in (("ajuste", aj), ("validacion", va))
              for c, n in (("positivos", sum(f[ETIQUETA] for f in filas)), ("negativos", sum(1 - f[ETIQUETA] for f in filas)))
              if n < config["minimos_clases"][b][c]]
    tasa = sum(f[ETIQUETA] for f in aj) / len(aj) if aj else None
    candidatos, equivalencia, metricas_val = {}, {}, {}
    for f in va:
        f["p_constante"] = tasa
    if not faltan:
        candidatos, equivalencia = construir_candidatos(aj, va, config, datos, ds["historial"])
        for cid, c in candidatos.items():
            for f in va:
                f[f"p_{cid}"] = c["modelo"].probabilidad(f)
            metricas_val[cid] = medir(va, lambda f, x=cid: f[f"p_{x}"], True, config["k"])
    refs_val = {"mayor_recencia": medir(va, _recencia, False, config["k"]),
                "constante": medir(va, lambda f: f["p_constante"], True, config["k"]) if tasa is not None else None,
                "regla_existente": regla_existente([f for f in ds["bloques"]["validacion"] if f["poblacion"] in ("aprendible", "estructural")])}
    tol = config["seleccion"]["tolerancia_empate"]

    def clave(cid):
        ag, pr = metricas_val[cid]["agregado"], metricas_val[cid]["probabilidad"]
        r = lambda x: round(x / tol) if x is not None else 0  # noqa: E731
        return (-r(ag["precision_media_top10"]), -r(ag["sensibilidad_agregada_top10"] or 0), r(pr["brier"]),
                candidatos[cid]["complejidad"], candidatos[cid]["valor"])
    orden = sorted(candidatos, key=clave)
    elegido = orden[0] if orden else None
    seleccion = {"criterio": config["seleccion"]["criterio"], "bloque": "validacion", "orden": orden, "elegido": elegido,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"] if elegido else None,
                 "sin_candidato": {"motivo": "; ".join(faltan)} if faltan else None,
                 "candidatos": {cid: {"familia": c["familia"], "hiperparametro": c["artefacto"]["hiperparametro"], "complejidad": c["complejidad"],
                                      "variables": c["variables"], "artefacto_huella": c["artefacto"]["huella"],
                                      "artefacto_version": c["artefacto"]["version"], "validacion": metricas_val[cid],
                                      "equivalencia_json_sklearn": equivalencia.get(cid)}
                                for cid, c in candidatos.items()},
                 "referencias_validacion": refs_val, "tasa_constante_ajuste": tasa,
                 "nota": "Parámetros ajustados solo con el bloque de ajuste; no se reajusta antes de la comprobación."}
    archivos: dict[str, bytes] = {f"candidatos/{cid}.json": json_bytes(c["artefacto"]) for cid, c in candidatos.items()}
    if elegido:
        archivos["artefacto.json"] = json_bytes(candidatos[elegido]["artefacto"])
    cols = COLUMNAS_BASE + ["ventana_restante_dias", "instalaciones_vigentes", "renovacion_antes_del_cruce"] + [f"p_{c}" for c in candidatos] + ["p_constante"]
    archivos["predicciones_validacion.csv"] = _escribir_csv([dict(f, bloque="validacion") for f in va], cols)
    archivos["config.json"] = json_bytes(config)
    archivos["protocolo.json"] = json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config),
                                             "identidad": identidad_protocolo(config)})
    archivos["datos.json"] = json_bytes(dict(datos.descripcion(), cobertura_por_fuente=cobertura_m21(datos), instalaciones=ds["instalaciones"],
                                             fronteras_verificadas=ds["fronteras"], conteos_por_bloque=conteo_bloques,
                                             separacion_temporal=config["separacion_temporal"]))
    archivos["seleccion.json"] = json_bytes(seleccion)
    archivos["entorno.json"] = json_bytes(entorno())
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"],
            "artefacto_version": candidatos[elegido]["artefacto"]["version"] if elegido else None,
            "seleccion_elegido": elegido, "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "referencias": {"constante_tasa_ajuste": tasa, "mayor_recencia": "recencia descendente, desempate cliente_id",
                            "regla_existente": "recencia + 60 >= 90"},
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica (ya vista en M2: exploratoria)"}
    marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta,
                             volatiles={"fechas_piloto": fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": conteo_bloques, "fronteras": ds["fronteras"],
            "artefacto": candidatos[elegido]["artefacto"] if elegido else None}


# Evaluación --------------------------------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    config = _leer(ejecucion / "config.json")
    if not es_m21(config) or huella_protocolo(config) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado (código o configuración distintos); "
                             "crea una version_protocolo y una ejecución nuevas.")
    sel = _leer(ejecucion / "seleccion.json")
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    if cong["artefacto_huella"] is not None:
        art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
        cand = cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json", modelo_id=MODELO_ID)
        if not (art.huella == cand.huella == cong["artefacto_huella"]):
            raise ProtocoloError("artefacto.json no es el candidato seleccionado y congelado.")
    return cong


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None, m2: str | Path | None = None) -> dict:
    """Comprobación histórica (exploratoria, reutilizada) del artefacto congelado; publica métricas, predicciones y decisión.

    ``m2``: ejecución M2 congelada cuyo candidato se mide como contexto (no interviene en la decisión)."""
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config = _leer(ejecucion / "config.json")
    info = _leer(ejecucion / "datos.json")
    sel = _leer(ejecucion / "seleccion.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = preparar(datos, config)
    bloque = ds["bloques"]["comprobacion_historica"]
    filas = aprendibles(bloque)
    tasa = cong["referencias"]["constante_tasa_ajuste"]
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID) if cong["artefacto_huella"] else None
    familias = {}
    for cid in sel["orden"]:  # contexto: cada candidato congelado (sin intervenir en la decisión)
        c = cargar_artefacto(ejecucion / "candidatos" / f"{cid}.json", modelo_id=MODELO_ID)
        familias[cid] = c
    art_m2 = None
    if m2:
        from .inactividad_experimento import verificar_congelacion as verificar_m2
        verificar_m2(m2)
        art_m2 = cargar_artefacto(Path(m2) / "artefacto.json", modelo_id=MODELO_ID)
    for f in filas:
        f["p_candidato"] = art.probabilidad(f) if art else None
        f["p_constante"] = tasa
        for cid, c in familias.items():
            f[f"p_{cid}"] = c.probabilidad(f)
        if art_m2:
            f["p_m2"] = art_m2.probabilidad(f)  # las variables v1 están contenidas en v2
    comp: dict[str, Any] = {"conteos": conteos(bloque), "sin_candidato": sel.get("sin_candidato"),
                            "mayor_recencia": medir(filas, _recencia, False, config["k"]),
                            "constante": medir(filas, lambda f: f["p_constante"], True, config["k"]) if tasa is not None else None,
                            "regla_existente": regla_existente([f for f in bloque if f["poblacion"] in ("aprendible", "estructural")]),
                            "candidato": medir(filas, lambda f: f["p_candidato"], True, config["k"]) if art else None}
    contexto = {cid: {"precision_media_top10": medir(filas, lambda f, x=cid: f[f"p_{x}"], True, config["k"])["agregado"]["precision_media_top10"],
                      "brier": M.brier(filas, lambda f, x=cid: f[f"p_{x}"], ETIQUETA)} for cid in familias}
    if art_m2:
        contexto["m2_congelado"] = {"version": art_m2.version, **{k: v for k, v in (
            ("precision_media_top10", medir(filas, lambda f: f["p_m2"], True, config["k"])["agregado"]["precision_media_top10"]),
            ("brier", M.brier(filas, lambda f: f["p_m2"], ETIQUETA)))}}
    b = config["metricas"]["bootstrap"]
    boot = {}
    if art:
        def dif_top(m):
            a, r_ = _media_top(m, "p_candidato"), _media_top(m, "recencia_dias_corte")
            return None if a is None or r_ is None else a - r_

        def dif_brier(m):
            return sum((f["p_candidato"] - f[ETIQUETA]) ** 2 - (f["p_constante"] - f[ETIQUETA]) ** 2 for f in m) / len(m) if m else None
        boot = {"precision_media_top10_candidato_menos_recencia": M.bootstrap_clientes(filas, dif_top, b["repeticiones"], b["semilla"]),
                "brier_candidato_menos_constante": M.bootstrap_clientes(filas, dif_brier, b["repeticiones"], b["semilla"]),
                "nota": "remuestreo de clientes completos con todas sus observaciones mensuales"}
    decision = decidir(comp, boot, config)
    if decision["decision"] == "favorable":
        decision["motivos"].append("Bloque ya visto en M2: el resultado favorable es exploratorio y solo habilita sombra y el piloto prospectivo.")
    metricas = {"bloque": "comprobacion_historica", "cortes": comp["conteos"]["cortes"],
                "alcance": "comprobación histórica EXPLORATORIA Y REUTILIZADA (ya vista en M2); no es validación independiente",
                "poblacion_comparada": "aprendible (recencia 30–89) con etiqueta madura; mismos clientes por corte para todos los métodos",
                "artefacto": {"version": art.version, "huella": art.huella} if art else None, "resultados": comp,
                "contexto_todos_los_candidatos": contexto,
                "nota_contexto": "Medición de todos los candidatos y de M2 en la comprobación SOLO como contexto: la selección ya se hizo en validación y no se cambia.",
                "incertidumbre_bootstrap_clientes": boot, "limitaciones": LIMITACIONES}
    pos_c, pos_r = {}, {}
    for corte, g in M.por_corte(filas).items():
        if art:
            pos_c.update({(f["cliente_id"], corte): i for i, f in enumerate(M.ordenar(g, lambda f: f["p_candidato"]), 1)})
        pos_r.update({(f["cliente_id"], corte): i for i, f in enumerate(M.ordenar(g, _recencia), 1)})
    cols = COLUMNAS_BASE + ["ventana_restante_dias", "instalaciones_vigentes", "renovacion_antes_del_cruce", "p_candidato", "p_constante",
                            "posicion_candidato", "posicion_mayor_recencia"]
    pred = [dict(f, bloque="comprobacion_historica", posicion_candidato=pos_c.get((f["cliente_id"], f["corte"])),
                 posicion_mayor_recencia=pos_r.get((f["cliente_id"], f["corte"]))) for f in filas]
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"],
               candidato=cong["seleccion_elegido"], version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"],
               sello_congelacion=cong["sello"], origen_datos=config["origen_datos"], alcance=metricas["alcance"],
               limitaciones=LIMITACIONES + ["Ningún candidato se promueve automáticamente; no existe registro operativo de inactividad_60d."])
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas),
                "predicciones_comprobacion.csv": _escribir_csv(pred, cols), "decision.json": json_bytes(doc)}
    marcador = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION,
                             {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"],
                              "m2_contexto": str(m2) if m2 else None})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": _leer(ejecucion / "decision.json")}
