"""M2 · Experimento de inactividad a 60 días: preparar, entrenar (seleccionar y congelar) y evaluar.

Importa scikit-learn solo dentro de ``ajustar`` (entrenamiento). La puntuación vive en ``modelos/inactividad.py``.

Integridad (ver ``modelos/ejecucion.py``):

* ``entrenar`` escribe toda la evidencia (configuración, protocolo, datos, selección, candidatos, artefacto,
  predicciones de validación y entorno) y, al final, ``congelacion.json`` con el SHA-256 de cada archivo y un sello.
  El artefacto principal debe tener la huella del candidato elegido en ``seleccion.json``.
* ``evaluar`` vuelve a verificar TODO (también en los reintentos) antes de calcular; publica métricas, predicciones y
  decisión con el marcador ``evaluacion.json`` al final. Un fallo parcial se completa al reintentar; un resultado
  distinto nunca sobrescribe al existente; repetir es idempotente.
* Una configuración o revisión de datos distinta exige otra carpeta de ejecución.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import metricas as M
from .compra import DependenciaEntrenamiento, ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inactividad import (DEFINICION_ETIQUETA, ETIQUETA, HORIZONTE_DIAS, MADURA, MODELO_ID, POBLACIONES,
                          UMBRAL_FRIO_DIAS, fotografias)
from .inferencia import FORMATO, cargar_artefacto, desde_dict, sellar
from .variables import (FUNCION, VERSION_INACTIVIDAD, aplicar_transformaciones, ajustar_transformaciones, cortes_mensuales,
                        historial_compras)

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "inactividad_60d.json"
REGLA_DECISION = "m2-decision-v1"
METRICAS_VERSION = M.METRICAS_VERSION + "+inactividad"
MARCADOR_CONGELACION = "congelacion.json"
MARCADOR_EVALUACION = "evaluacion.json"
LIMITACIONES = [
    "Datos sintéticos de 120 clientes ya inspeccionados: la comprobación histórica (julio y agosto de 2026) es exploratoria, no prospectiva.",
    "Dos meses de comprobación con clientes repetidos: no demuestran estabilidad.",
    "Mide el riesgo de llegar a 90 días sin compra; no es abandono, cancelación ni efecto causal del seguimiento.",
    "Una compra posterior a un contacto no demuestra que el seguimiento evitó la inactividad.",
]


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def _leer(ruta: Path) -> Any:
    return json.loads(Path(ruta).read_text(encoding="utf-8"))


def cargar_config(ruta: str | Path | None = None) -> dict:
    return _leer(Path(ruta or CONFIG_DEFECTO))


# Protocolo ---------------------------------------------------------------------------------------------------
def identidad_protocolo(config: dict) -> dict:
    variables = sorted({v for vs in config["combinaciones"].values() for v in vs})
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": VERSION_INACTIVIDAD, "transformaciones": {v: FUNCION.get(v) for v in variables},
                       "definicion_etiqueta": DEFINICION_ETIQUETA, "metricas": METRICAS_VERSION, "regla_decision": REGLA_DECISION,
                       "formato_artefacto": FORMATO}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config)).encode()).hexdigest()


# Datos y bloques ---------------------------------------------------------------------------------------------
def cortes_bloque(config: dict, bloque: str) -> list[date]:
    a, b = config["bloques"][bloque]
    return cortes_mensuales(_d(a), _d(b))


def verificar_fronteras(bloques: dict[str, list[dict]], config: dict) -> dict:
    """Comprueba POR CÓDIGO que cada etiqueta usada en un bloque madura antes de la primera inferencia del siguiente."""
    orden = ["ajuste", "validacion", "comprobacion_historica"]
    excluidos = {_d(c) for c in config["separacion_temporal"]["excluidos"]}
    salida = {}
    for nombre in orden:
        if excluidos & {f["corte"] for f in bloques[nombre]}:
            raise ProtocoloError(f"El bloque {nombre} contiene un corte de separación temporal {sorted(excluidos)}")
    for previo, siguiente in zip(orden, orden[1:]):
        usadas = [f for f in bloques[previo] if f["poblacion"] == "aprendible" and f["estado_etiqueta"] == MADURA]
        primera = min(f["corte"] for f in bloques[siguiente])
        ultima = max((_d(f["fin_horizonte"]) for f in usadas), default=None)
        if ultima is None or ultima >= primera:
            raise ProtocoloError(f"Fuga temporal: etiquetas de {previo} maduran el {ultima}, no antes de la primera inferencia de {siguiente} ({primera})")
        salida[f"{previo}->{siguiente}"] = {"ultima_etiqueta_madura": ultima.isoformat(), "primera_inferencia": primera.isoformat(),
                                            "etiquetas_comprobadas": len(usadas)}
    return salida


def preparar(datos: DatosAceptados, config: dict) -> dict:
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    cortes = sorted({c for b in config["bloques"] for c in cortes_bloque(config, b)})
    filas = fotografias(datos.clientes, historial, cortes, datos.observado_hasta,
                        {"revision_datos": datos.revision, "huella_datos": datos.huella_datos})
    bloques = {b: [f for f in filas if f["corte"] in set(cortes_bloque(config, b))] for b in config["bloques"]}
    return {"historial": historial, "filas": filas, "bloques": bloques, "fronteras": verificar_fronteras(bloques, config)}


def aprendibles(filas: list[dict]) -> list[dict]:
    """Población de aprendizaje y comparación: recencia 30–89 con etiqueta madura."""
    return [f for f in filas if f["poblacion"] == "aprendible" and f["estado_etiqueta"] == MADURA]


def conteos(filas: list[dict]) -> dict:
    apr = aprendibles(filas)
    por_mes = []
    for corte, g in M.por_corte(filas).items():
        ga = aprendibles(g)
        por_mes.append({"corte": corte.isoformat(), "clientes": len(g), **{p: sum(f["poblacion"] == p for f in g) for p in POBLACIONES},
                        "aprendibles_maduras": len(ga), "pendientes": sum(f["poblacion"] == "aprendible" and f["estado_etiqueta"] != MADURA for f in g),
                        "eventos": sum(f[ETIQUETA] for f in ga), "no_eventos": sum(1 - f[ETIQUETA] for f in ga),
                        "estructurales_maduras_con_evento": sum(1 for f in g if f["poblacion"] == "estructural" and f[ETIQUETA] == 1)})
    return {"fotografias": len(filas), "cortes": [m["corte"] for m in por_mes], "clientes_unicos": len({f["cliente_id"] for f in filas}),
            "por_poblacion": {p: sum(f["poblacion"] == p for f in filas) for p in POBLACIONES},
            "aprendibles_maduras": len(apr), "clientes_unicos_aprendibles": len({f["cliente_id"] for f in apr}),
            "eventos": sum(f[ETIQUETA] for f in apr), "no_eventos": sum(1 - f[ETIQUETA] for f in apr),
            "clientes_unicos_con_evento": len({f["cliente_id"] for f in apr if f[ETIQUETA]}),
            "pendientes_excluidas": sum(f["poblacion"] == "aprendible" and f["estado_etiqueta"] != MADURA for f in filas),
            "por_mes": por_mes}


def cobertura_por_fuente(datos: DatosAceptados) -> dict:
    """Cobertura declarada por fuente usada. Solo las ventas tienen ``datos_observados_hasta`` declarado."""
    fechas_trm = sorted(datos.tasas)
    return {"ventas": {"estado": "declarada", **datos.cobertura.como_dict(),
                       "uso": "variables (fecha <= corte) y etiqueta (cobertura >= corte + 60)"},
            "clientes": {"estado": "maestro sin fecha de corte", "uso": "elegibilidad por fecha_alta <= corte",
                         "convencion": "alta conocida desde su fecha (convención sintética)"},
            "trm": {"estado": "por fecha (sin declaración de cobertura)", "desde": fechas_trm[0].isoformat() if fechas_trm else None,
                    "hasta": fechas_trm[-1].isoformat() if fechas_trm else None,
                    "uso": "importe_cop_90d con la TRM de la fecha de cada venta; si falta, la variable queda nula"},
            "no_usadas": {"base_instalada": "coberturas e instalaciones sin disponibilidad histórica reconstruible",
                          "productos": "atributos del catálogo solo en su estado actual", "compras": "no aplica a este objetivo",
                          "incidencias_a01": "no se usan como datos de entrenamiento"}}


# Ajuste ------------------------------------------------------------------------------------------------------
def ajustar(filas: list[dict], variables: list[str], C: float, config: dict):
    """Transformaciones y regresión L2 ajustadas SOLO con ``filas``. Devuelve (trans, b0, w, predicción sklearn)."""
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise DependenciaEntrenamiento("Entrenar requiere las dependencias opcionales: pip install -r requirements-modelos.txt") from exc
    trans = ajustar_transformaciones(filas, variables)
    X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
    y = np.array([int(f[ETIQUETA]) for f in filas])
    e = config["estimador"]
    modelo = LogisticRegression(C=C, solver=e["solver"], max_iter=e["max_iter"], tol=e["tol"], class_weight=e["class_weight"],
                                random_state=config["semilla"])
    modelo.fit(X, y)

    def predecir(lote: list[dict]) -> list[float]:
        return [float(p) for p in modelo.predict_proba(np.array([aplicar_transformaciones(f, trans) for f in lote], dtype=float))[:, 1]]

    return trans, float(modelo.intercept_[0]), [float(w) for w in modelo.coef_[0]], predecir


def candidato_id(combinacion: str, C: float) -> str:
    return f"{combinacion}-c{str(C).replace('.', '_')}"


def artefacto_candidato(combinacion: str, variables: list[str], C: float, trans, b0, w, config: dict, datos: DatosAceptados,
                        ajuste: list[dict]) -> dict:
    borrador = {"formato": FORMATO, "modelo_id": MODELO_ID, "version": "pendiente", "version_variables": VERSION_INACTIVIDAD,
                "descripcion": f"Regresión logística L2 (C={C}) sobre la combinación {combinacion}; población aprendible (recencia 30–89).",
                "horizonte_dias": HORIZONTE_DIAS, "umbral_frio_dias": UMBRAL_FRIO_DIAS, "variables": list(variables),
                "transformaciones": trans, "intercepto": b0, "pesos": w, "umbral": None,
                "politica": {"tipo": "cupo", "k": config["k_principal"], "orden": "probabilidad descendente, desempate por cliente_id"},
                "poblacion": "aprendible: alta <= corte, al menos una compra confirmada y recencia 30–89 días",
                "combinacion": combinacion, "C": C, "estimador": config["estimador"], "semilla": config["semilla"],
                "disponible_desde": config["disponible_desde"], "origen_datos": config["origen_datos"],
                "version_protocolo": config["version_protocolo"], "etiqueta": DEFINICION_ETIQUETA,
                "entrenamiento": {"cortes": sorted({f["corte"].isoformat() for f in ajuste}), "filas": len(ajuste),
                                  "eventos": sum(f[ETIQUETA] for f in ajuste), "huella_datos": datos.huella_datos,
                                  "revision_datos": datos.revision}}
    borrador["version"] = f"inactividad_60d-m2-{candidato_id(combinacion, C)}-" + sellar(borrador)["huella"][:8]
    return sellar(borrador)


# Métricas ----------------------------------------------------------------------------------------------------
def _distribucion(valores: list[float]) -> dict:
    v = sorted(valores)
    if not v:
        return {}
    q = lambda p: v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))]  # noqa: E731
    return {"n": len(v), "min": v[0], "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "max": v[-1], "media": sum(v) / len(v)}


def medir(filas: list[dict], puntaje: Callable[[dict], float], probabilistico: bool, ks=(10, 20)) -> dict:
    """Ranking por mes y agregado (media mensual y sumas), falsos positivos, sensibilidad agregada y probabilidad."""
    r = M.resumen_ranking(filas, puntaje, ks, ETIQUETA)
    for m in r["por_mes"]:
        for k in ks:
            t = m[f"top{k}"]
            t["falsos_positivos"] = t["k_efectivo"] - t["aciertos"]
    ag = r["agregado"]
    ag["eventos"] = ag.pop("positivos")
    for k in ks:
        ag[f"falsos_positivos_top{k}"] = ag[f"denominador_top{k}"] - ag[f"aciertos_top{k}"]
        ag[f"sensibilidad_agregada_top{k}"] = ag[f"aciertos_top{k}"] / ag["eventos"] if ag["eventos"] else None
        ag[f"precision_agregada_top{k}"] = ag[f"aciertos_top{k}"] / ag[f"denominador_top{k}"] if ag[f"denominador_top{k}"] else None
    ag["nota"] = ("precision_media_topK = media de los meses; *_agregada_topK = suma de aciertos entre suma de denominadores "
                  "o de eventos; average precision por escalones (no interpolada)")
    if probabilistico:
        p = M.resumen_probabilidad(filas, puntaje, ETIQUETA)
        p["log_loss"] = M.log_loss(filas, puntaje, etiqueta=ETIQUETA)
        p["distribucion"] = _distribucion([puntaje(f) for f in filas])
        p["por_mes"] = [{"corte": c.isoformat(), "n": len(g), "brier": M.brier(g, puntaje, ETIQUETA),
                         "prob_media": sum(puntaje(f) for f in g) / len(g), "tasa_observada": sum(f[ETIQUETA] for f in g) / len(g)}
                        for c, g in M.por_corte(filas).items()]
        r["probabilidad"] = p
    return r


def regla_existente(filas_activos: list[dict]) -> dict:
    """Regla ``recencia + 60 >= 90`` (A06): alertas, eventos detectados y falsas alarmas, sin tratarla como probabilidad."""
    meses = []
    for corte, g in M.por_corte(filas_activos).items():
        maduras = [f for f in g if f["estado_etiqueta"] == MADURA]
        alerta = [f for f in maduras if f["recencia_dias_corte"] + HORIZONTE_DIAS >= UMBRAL_FRIO_DIAS]
        ev = sum(f[ETIQUETA] for f in maduras)
        tp = sum(f[ETIQUETA] for f in alerta)
        meses.append({"corte": corte.isoformat(), "activos_maduros": len(maduras), "alertas": len(alerta), "eventos": ev,
                      "eventos_detectados": tp, "falsas_alarmas": len(alerta) - tp,
                      "precision": tp / len(alerta) if alerta else None, "sensibilidad": tp / ev if ev else None})
    tot = {k: sum(m[k] for m in meses) for k in ("activos_maduros", "alertas", "eventos", "eventos_detectados", "falsas_alarmas")}
    tot["precision"] = tot["eventos_detectados"] / tot["alertas"] if tot["alertas"] else None
    tot["sensibilidad"] = tot["eventos_detectados"] / tot["eventos"] if tot["eventos"] else None
    return {"definicion": "alerta si recencia + 60 >= 90 (booleano; no es una probabilidad calibrada)", "por_mes": meses, "total": tot,
            "limitacion": "Sobre la población aprendible (recencia 30–89) la regla marca a todos: su sensibilidad es 1 y su precisión "
                          "es la tasa de eventos. No ordena ni cabe en un cupo; por eso el comparador del cupo es mayor recencia."}


def _media_top(filas: list[dict], clave: str, k: int = 10) -> float | None:
    meses = [M.ranking_k(g, lambda f: f[clave], k, ETIQUETA) for g in M.por_corte(filas).values()]
    meses = [m for m in meses if m["k_efectivo"]]
    return sum(m["aciertos"] / m["k_efectivo"] for m in meses) / len(meses) if meses else None


def _recencia(f: dict) -> float:
    return float(f["recencia_dias_corte"])


def _escribir_csv(filas: list[dict], columnas: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=columnas, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow({k: (v.isoformat() if hasattr(v, "isoformat") else (round(v, 12) if isinstance(v, float) else v))
                    for k, v in f.items()})
    return buf.getvalue().encode("utf-8")


COLUMNAS_BASE = ["cliente_id", "corte", "bloque", "poblacion", "recencia_dias_corte", "ultima_compra", "estado_etiqueta",
                 ETIQUETA, "fecha_cruce", "fin_horizonte"]


# Entrenamiento -----------------------------------------------------------------------------------------------
def _comprobar_carpeta(salida: Path, config: dict) -> None:
    if (salida / "config.json").exists() and canon(_leer(salida / "config.json")) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    if (salida / MARCADOR_CONGELACION).exists() and (salida / "datos.json").exists():
        pass  # la comparación de datos y evidencia la hace publicar_lote (rechaza si difiere)


def _primer_fin_de_mes_posterior(dia: date) -> date:
    from .variables import fin_de_mes
    fin = fin_de_mes(dia.year, dia.month)
    return fin if fin > dia else fin_de_mes(dia.year + (dia.month == 12), 1 if dia.month == 12 else dia.month + 1)


def fechas_piloto(hoy: date) -> dict:
    primer = _primer_fin_de_mes_posterior(hoy)
    return {"congelacion_real": hoy.isoformat(), "primer_corte_prospectivo": primer.isoformat(),
            "cobertura_requerida_para_puntuar": primer.isoformat(),
            "evaluable_desde": (primer + timedelta(days=HORIZONTE_DIAS)).isoformat(),
            "cobertura_requerida_para_evaluar": (primer + timedelta(days=HORIZONTE_DIAS)).isoformat(),
            "nota": "fechas calculadas desde la ejecución real; la comprobación histórica (julio y agosto de 2026) es retrospectiva"}


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    """Ajusta los candidatos predeclarados en el bloque de ajuste, selecciona en validación y congela la evidencia."""
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID:
        raise ProtocoloError(f"La configuración es de {config.get('modelo_id')!r}, no de {MODELO_ID}")
    _comprobar_carpeta(salida, config)
    ds = preparar(datos, config)
    aj, va = aprendibles(ds["bloques"]["ajuste"]), aprendibles(ds["bloques"]["validacion"])
    conteo_bloques = {b: conteos(f) for b, f in ds["bloques"].items()}
    tasa = sum(f[ETIQUETA] for f in aj) / len(aj) if aj else None
    minimos = config["minimos_clases"]
    faltan = [f"{b}: {c}" for b, filas in (("ajuste", aj), ("validacion", va))
              for c, n in (("positivos", sum(f[ETIQUETA] for f in filas)), ("negativos", sum(1 - f[ETIQUETA] for f in filas)))
              if n < minimos[b][c]]
    archivos: dict[str, bytes] = {}
    candidatos, metricas_val, equivalencia = {}, {}, {}
    for f in va:
        f["p_constante"] = tasa
    if not faltan:
        for comb in config["candidatos"]["combinaciones"]:
            variables = config["combinaciones"][comb]
            for C in config["candidatos"]["C"]:
                cid = candidato_id(comb, C)
                trans, b0, w, predecir = ajustar(aj, variables, C, config)
                art_d = artefacto_candidato(comb, variables, C, trans, b0, w, config, datos, aj)
                art = desde_dict(json.loads(json.dumps(art_d)))  # recarga desde JSON
                dif = max(abs(a - art.probabilidad(f)) for a, f in zip(predecir(aj + va), aj + va))
                if dif > config["tolerancia_probabilidad"]:
                    raise ValueError(f"{cid}: la probabilidad del artefacto recargado difiere de sklearn en {dif:g}")
                equivalencia[cid] = {"diferencia_maxima": dif, "filas": len(aj) + len(va), "tolerancia": config["tolerancia_probabilidad"]}
                for f in va:
                    f[f"p_{cid}"] = art.probabilidad(f)
                candidatos[cid] = {"combinacion": comb, "C": C, "variables": variables, "artefacto": art_d}
                metricas_val[cid] = medir(va, lambda f, c=cid: f[f"p_{c}"], True, config["k"])
    refs_val = {"mayor_recencia": medir(va, _recencia, False, config["k"]),
                "constante": medir(va, lambda f: f["p_constante"], True, config["k"]) if tasa is not None else None,
                "regla_existente": regla_existente([f for f in ds["bloques"]["validacion"] if f["poblacion"] in ("aprendible", "estructural")])}
    tol = config["seleccion"]["tolerancia_empate"]

    def clave(cid):
        ag, pr = metricas_val[cid]["agregado"], metricas_val[cid]["probabilidad"]
        r = lambda x: round(x / tol) if x is not None else 0  # noqa: E731 - empates dentro de la tolerancia
        return (-r(ag["precision_media_top10"]), -r(ag["sensibilidad_agregada_top10"] or 0), r(pr["brier"]),
                len(candidatos[cid]["variables"]), candidatos[cid]["C"])
    orden = sorted(candidatos, key=clave)
    elegido = orden[0] if orden else None
    seleccion = {"criterio": config["seleccion"]["criterio"], "bloque": "validacion", "orden": orden, "elegido": elegido,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"] if elegido else None,
                 "sin_candidato": {"motivo": "; ".join(faltan)} if faltan else None,
                 "candidatos": {cid: {"combinacion": c["combinacion"], "C": c["C"], "variables": c["variables"],
                                      "artefacto_huella": c["artefacto"]["huella"], "artefacto_version": c["artefacto"]["version"],
                                      "validacion": metricas_val[cid], "equivalencia_json_sklearn": equivalencia[cid]}
                                for cid, c in candidatos.items()},
                 "referencias_validacion": refs_val, "tasa_constante_ajuste": tasa,
                 "nota": "Pesos y transformaciones ajustados solo con el bloque de ajuste; no se reentrena antes de la comprobación."}
    for cid, c in candidatos.items():
        archivos[f"candidatos/{cid}.json"] = json_bytes(c["artefacto"])
    if elegido:
        archivos["artefacto.json"] = json_bytes(candidatos[elegido]["artefacto"])
    cols = COLUMNAS_BASE + [f"p_{c}" for c in candidatos] + ["p_constante"]
    archivos["predicciones_validacion.csv"] = _escribir_csv([dict(f, bloque="validacion") for f in va], cols)
    archivos["config.json"] = json_bytes(config)
    archivos["protocolo.json"] = json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config),
                                             "identidad": identidad_protocolo(config)})
    archivos["datos.json"] = json_bytes(dict(datos.descripcion(), cobertura_por_fuente=cobertura_por_fuente(datos),
                                             fronteras_verificadas=ds["fronteras"], conteos_por_bloque=conteo_bloques,
                                             separacion_temporal=config["separacion_temporal"]))
    archivos["seleccion.json"] = json_bytes(seleccion)
    archivos["entorno.json"] = json_bytes(entorno())
    hoy = datetime.now(timezone.utc).date()
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"] if elegido else None,
            "seleccion_elegido": elegido, "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "referencias": {"constante_tasa_ajuste": tasa, "mayor_recencia": "recencia descendente, desempate cliente_id",
                            "regla_existente": "recencia + 60 >= 90"},
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica"}
    marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta, volatiles={"fechas_piloto": fechas_piloto(hoy)})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": conteo_bloques, "fronteras": ds["fronteras"],
            "artefacto": candidatos[elegido]["artefacto"] if elegido else None}


# Evaluación --------------------------------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    """Antes de cualquier evaluación (y de cada reintento): huellas de toda la evidencia, protocolo y artefacto."""
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    config = _leer(ejecucion / "config.json")
    if huella_protocolo(config) != cong["protocolo"]["huella"]:
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


def decidir(comp: dict, boot: dict, config: dict) -> dict:
    metas, minimos = config["metas"], config["minimos_evidencia"]
    if comp.get("candidato") is None:
        return {"decision": "inconcluso", "estado_maximo": "ninguno", "motivos": ["No se entrenó ningún candidato: " + str(comp.get("sin_candidato"))],
                "cumple": {}, "valores": {}}
    c, r = comp["candidato"]["agregado"], comp["mayor_recencia"]["agregado"]
    pc, pr = comp["candidato"]["probabilidad"]["brier"], comp["constante"]["probabilidad"]["brier"]
    dif = c["precision_media_top10"] - r["precision_media_top10"]
    ic, icb = boot["precision_media_top10_candidato_menos_recencia"], boot["brier_candidato_menos_constante"]
    eventos_mes = [m["eventos"] for m in comp["conteos"]["por_mes"]]
    cumple = {"minimos_evidencia": comp["conteos"]["eventos"] >= minimos["eventos_bloque"] and len(eventos_mes) >= minimos["meses"]
                                   and min(eventos_mes) >= minimos["eventos_por_mes"],
              "mejora_minima": dif >= metas["mejora_minima_precision_top10_vs_mayor_recencia"] - 1e-12,
              "ic95_excluye_cero": (ic.get("p2_5") or -1) > 0,
              "sensibilidad_no_menor": (c["sensibilidad_agregada_top10"] or 0) >= (r["sensibilidad_agregada_top10"] or 0) - 1e-12,
              "brier_no_peor_que_constante": pr is None or pc <= pr + 1e-12}
    motivos = []
    if all(cumple.values()):
        decision = "favorable"
        motivos.append("Cumple todas las metas predeclaradas en la comprobación histórica exploratoria; solo habilita sombra.")
    elif (ic.get("p97_5") is not None and ic["p97_5"] < 0) or (icb.get("p2_5") is not None and icb["p2_5"] > 0):
        decision = "rechazado"
        if ic.get("p97_5") is not None and ic["p97_5"] < 0:
            motivos.append("El IC 95 % de la diferencia de precisión a 10 frente a mayor recencia está entero por debajo de 0.")
        if icb.get("p2_5") is not None and icb["p2_5"] > 0:
            motivos.append("El IC 95 % de (Brier candidato − Brier constante) está entero por encima de 0.")
    else:
        decision = "inconcluso"
        motivos += [f"No cumple: {k}" for k, v in cumple.items() if not v] or ["Resultados contradictorios"]
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "cumple": cumple, "motivos": motivos,
            "valores": {"precision_media_top10_candidato": c["precision_media_top10"], "precision_media_top10_mayor_recencia": r["precision_media_top10"],
                        "diferencia": dif, "ic95_diferencia": [ic.get("p2_5"), ic.get("p97_5")],
                        "sensibilidad_agregada_top10_candidato": c["sensibilidad_agregada_top10"],
                        "sensibilidad_agregada_top10_mayor_recencia": r["sensibilidad_agregada_top10"],
                        "brier_candidato": pc, "brier_constante": pr, "ic95_brier_candidato_menos_constante": [icb.get("p2_5"), icb.get("p97_5")],
                        "eventos": comp["conteos"]["eventos"], "eventos_por_mes": eventos_mes}}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict:
    """Mide la comprobación histórica con el artefacto congelado (sin reajustar) y publica métricas, predicciones y decisión."""
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
    for f in filas:
        f["p_candidato"] = art.probabilidad(f) if art else None
        f["p_constante"] = tasa
    comp: dict[str, Any] = {"conteos": conteos(bloque), "sin_candidato": sel.get("sin_candidato"),
                            "mayor_recencia": medir(filas, _recencia, False, config["k"]),
                            "constante": medir(filas, lambda f: f["p_constante"], True, config["k"]) if tasa is not None else None,
                            "regla_existente": regla_existente([f for f in bloque if f["poblacion"] in ("aprendible", "estructural")]),
                            "candidato": medir(filas, lambda f: f["p_candidato"], True, config["k"]) if art else None}
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
                "nota": "remuestreo de clientes completos con todas sus observaciones mensuales; clientes repetidos se renombran"}
    decision = decidir(comp, boot, config)
    total = len(bloque)
    cobertura = {"activos": sum(f["poblacion"] in ("aprendible", "estructural") for f in bloque),
                 "con_estimacion_modelo": len(filas) if art else 0, "estructurales_probabilidad_cero": sum(f["poblacion"] == "estructural" for f in bloque),
                 "ya_frios_excluidos": sum(f["poblacion"] == "ya_frio" for f in bloque), "sin_historial": sum(f["poblacion"] == "sin_historial" for f in bloque),
                 "alta_posterior": sum(f["poblacion"] == "alta_posterior" for f in bloque),
                 "pendientes_excluidas": comp["conteos"]["pendientes_excluidas"], "sin_modelo": 0 if art else len(filas), "fotografias": total}
    metricas = {"bloque": "comprobacion_historica", "cortes": comp["conteos"]["cortes"],
                "alcance": "comprobación histórica EXPLORATORIA: periodo ya inspeccionado; no es validación prospectiva independiente",
                "poblacion_comparada": "aprendible (recencia 30–89) con etiqueta madura; mismos clientes por corte para todos los métodos",
                "artefacto": {"version": art.version, "huella": art.huella} if art else None, "resultados": comp,
                "incertidumbre_bootstrap_clientes": boot, "cobertura": cobertura, "limitaciones": LIMITACIONES}
    cols = COLUMNAS_BASE + ["p_candidato", "p_constante", "posicion_candidato", "posicion_mayor_recencia", "alerta_regla"]
    pos_c, pos_r = {}, {}
    for corte, g in M.por_corte(filas).items():
        if art:
            pos_c.update({(f["cliente_id"], corte): i for i, f in enumerate(M.ordenar(g, lambda f: f["p_candidato"]), 1)})
        pos_r.update({(f["cliente_id"], corte): i for i, f in enumerate(M.ordenar(g, _recencia), 1)})
    pred = [dict(f, bloque="comprobacion_historica", posicion_candidato=pos_c.get((f["cliente_id"], f["corte"])),
                 posicion_mayor_recencia=pos_r.get((f["cliente_id"], f["corte"])), alerta_regla=True) for f in filas]
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"],
               candidato=cong["seleccion_elegido"], version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"],
               sello_congelacion=cong["sello"], origen_datos=config["origen_datos"], alcance=metricas["alcance"],
               limitaciones=LIMITACIONES + ["Ningún candidato se promueve automáticamente; el registro operativo de compra_30d no se toca."])
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas),
                "predicciones_comprobacion.csv": _escribir_csv(pred, cols),
                "decision.json": json_bytes(doc)}
    marcador = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION,
                             {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"]})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    """Decisión ya publicada y verificada (para puntuar en sombra con su estado)."""
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": _leer(ejecucion / "decision.json")}
