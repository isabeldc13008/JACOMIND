"""M1 · Compra a 30 días: referencia, dataset, entrenamiento, evaluación, puntuación y sombra.

Operaciones (ver ``modelos/cli.py``):

* ``reproducir_referencia``: ejecuta el modelo original (``pipeline.modelo_compra``) sobre la
  revisión aceptada y compara sus controles con los esperados.
* ``artefacto_referencia``: congela ese modelo original en un artefacto JSON (inicialización
  explícita; el cierre ya no entrena).
* ``entrenar``: ajusta la rejilla L2 en *ajuste*, selecciona variables, C y umbral en
  *validación* y congela el candidato. No toca la comprobación histórica.
* ``evaluar``: carga el artefacto congelado y mide el bloque pedido frente a las cuatro
  referencias, sin reajustar.
* ``puntuar``: inferencia pura desde JSON para un corte; las etiquetas inmaduras quedan pendientes.
* ``comparar``: operativo frente a sombra (y recencia) a igual cupo, con resultados pendientes o maduros.

Solo ``ajustar_logistica`` importa scikit-learn/numpy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from . import metricas as M
from .datos import DatosAceptados, cargar_datos, verificar_cobertura_corte
from .inferencia import FORMATO, MODELO_ID, Artefacto, ArtefactoInvalido, cargar_artefacto, desde_dict, sellar
from .variables import (ELEGIBLE, FUNCION, HORIZONTE_DIAS, MADURA, VERSION_VARIABLES, ajustar_transformaciones,
                        aplicar_transformaciones, construir_fotografias, cortes_mensuales, etiqueta_al_corte,
                        historial_compras)

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "compra_30d.json"
LIMITACIONES = ["Datos sintéticos de 120 clientes; la comprobación histórica (julio–septiembre de 2026) ya fue inspeccionada y es exploratoria.",
                "Mide propensión de compra, no el efecto causal de contactar al cliente ni el valor de la venta.",
                "Tres meses de comprobación con cortes del mismo cliente correlacionados: no demuestran estabilidad.",
                "El ranking predictivo puro no es la agenda operativa, que aplica prioridades de reactivación y cobertura."]


class DependenciaEntrenamiento(RuntimeError):
    """Faltan las dependencias opcionales de entrenamiento."""


def _hoy_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _d(x: str) -> date:
    return date.fromisoformat(x)


def _json(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=lambda o: o.isoformat() if hasattr(o, "isoformat") else str(o)),
                    encoding="utf-8")


def _leer(ruta: Path) -> Any:
    return json.loads(ruta.read_text(encoding="utf-8"))


def cargar_config(ruta: str | Path | None = None) -> dict[str, Any]:
    return _leer(Path(ruta or CONFIG_DEFECTO))


# Protocolo congelado ---------------------------------------------------------------------
FORMATO_CONGELACION = 2
REGLA_DECISION_VERSION = "m1-decision-v1"
DEFINICION_ETIQUETA = "1 si hay venta confirmada en (corte, corte + horizonte]; 0 solo con el horizonte completo observado; si no, pendiente"
CLAVES_DESCRIPTIVAS = {"nota", "fijado_en"}


class ProtocoloError(ValueError):
    """La ejecución no puede evaluarse con este protocolo (modificado, no congelado o inconsistente)."""


def _canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sin_descriptivas(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _sin_descriptivas(v) for k, v in x.items() if k not in CLAVES_DESCRIPTIVAS}
    if isinstance(x, list):
        return [_sin_descriptivas(v) for v in x]
    return x


def identidad_protocolo(config: dict) -> dict[str, Any]:
    """Todo lo que define el experimento: objetivo, horizonte, bloques, población, variables y sus
    transformaciones, rejillas, política de umbral, métricas, referencias, metas y regla de decisión.

    Se excluyen solo textos descriptivos (``nota``, ``fijado_en``). El formato del JSON no influye:
    la serialización es canónica (claves ordenadas, sin espacios).
    """
    variables = sorted({v for vs in config.get("combinaciones", {}).values() for v in vs})
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": config.get("version_variables", VERSION_VARIABLES),
                       "transformaciones": {v: FUNCION.get(v) for v in variables},
                       "definicion_etiqueta": DEFINICION_ETIQUETA, "metricas": M.METRICAS_VERSION,
                       "regla_decision": config.get("regla_decision", REGLA_DECISION_VERSION),
                       "formato_artefacto": config.get("formatos_artefacto", FORMATO)}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(_canon(identidad_protocolo(config)).encode()).hexdigest()


def _primer_fin_de_mes_posterior(dia: date) -> date:
    from .variables import fin_de_mes
    fin = fin_de_mes(dia.year, dia.month)
    return fin if fin > dia else fin_de_mes(dia.year + (dia.month == 12), 1 if dia.month == 12 else dia.month + 1)


def _sello_congelacion(c: dict) -> str:
    return hashlib.sha256(_canon({k: c[k] for k in ("artefacto_huella", "referencia_huella", "huella_datos", "revision_datos")}
                                 | {"protocolo": c["protocolo"]["huella"]}).encode()).hexdigest()


def verificar_congelacion(ejecucion: str | Path) -> dict[str, Any]:
    """Comprueba que configuración, artefacto, referencia y datos son los congelados.

    Ejecuciones anteriores al formato 2 (sin huella de protocolo) se rechazan para emitir decisiones:
    su lectura e inferencia siguen disponibles y ``verificar_protocolo_heredado`` compara su
    configuración con una de referencia, sin presentarlo como prueba de congelación histórica.
    """
    ejecucion = Path(ejecucion)
    cong = _leer(ejecucion / "congelacion.json")
    if "protocolo" not in cong:
        raise ProtocoloError(
            f"{ejecucion} es una ejecución heredada sin huella de protocolo congelada: no puede emitir decisiones nuevas. "
            "Su artefacto, métricas y decisión originales siguen siendo legibles. Para verificar su configuración usa "
            "'python -m modelos.cli verificar-protocolo --ejecucion ... --config ...' y, para una decisión con protocolo "
            "congelado, entrena una ejecución nueva en otra carpeta con el mismo protocolo.")
    config = _leer(ejecucion / "config.json")
    actual = huella_protocolo(config)
    if actual != cong["protocolo"]["huella"]:
        raise ProtocoloError(
            f"El protocolo de {ejecucion} cambió después de congelarse (huella {actual[:12]}… frente a "
            f"{cong['protocolo']['huella'][:12]}… congelada). No se evalúa: crea una version_protocolo nueva y una ejecución nueva.")
    if config.get("version_protocolo") != cong["protocolo"]["version"]:
        raise ProtocoloError("version_protocolo distinta de la congelada")
    art = cargar_artefacto(ejecucion / "artefacto.json")
    ref = cargar_artefacto(ejecucion / "referencia_artefacto.json")
    if art.huella != cong["artefacto_huella"]:
        raise ProtocoloError("El artefacto no coincide con el congelado; la evaluación se detiene")
    if ref.huella != cong["referencia_huella"]:
        raise ProtocoloError("La referencia original no coincide con la congelada; la evaluación se detiene")
    if _sello_congelacion(cong) != cong.get("sello"):
        raise ProtocoloError("congelacion.json fue alterado (el sello no coincide)")
    return cong


def verificar_protocolo_heredado(ejecucion: str | Path, config_referencia: str | Path) -> dict[str, Any]:
    """Compara la configuración de una ejecución heredada con una configuración dada (verificación posterior)."""
    ejecucion = Path(ejecucion)
    cong = _leer(ejecucion / "congelacion.json")
    propia, ref = _leer(ejecucion / "config.json"), _leer(Path(config_referencia))
    diferencias = sorted(k for k in set(propia) | set(ref)
                         if k not in CLAVES_DESCRIPTIVAS and _canon(_sin_descriptivas(propia.get(k))) != _canon(_sin_descriptivas(ref.get(k))))
    art = cargar_artefacto(ejecucion / "artefacto.json")
    return {"ejecucion": str(ejecucion), "verificado_en": _hoy_utc(), "tipo": "verificacion_posterior",
            "advertencia": "Comparación hecha después de la evaluación: confirma que la configuración guardada coincide con la de "
                           "referencia, pero no prueba qué configuración estaba congelada antes de evaluar.",
            "formato_congelacion": cong.get("formato", 1), "tiene_huella_protocolo": "protocolo" in cong,
            "config_referencia": str(config_referencia), "huella_config_ejecucion": huella_protocolo(propia),
            "huella_config_referencia": huella_protocolo(ref), "coincide": not diferencias, "claves_distintas": diferencias,
            "artefacto": {"version": art.version, "huella": art.huella, "coincide_con_congelado": art.huella == cong.get("artefacto_huella")}}


def cargar_datos_config(ruta: str | Path, config: dict, *, aceptar_parcial: bool = False,
                        observado_hasta: str | None = None) -> DatosAceptados:
    return cargar_datos(ruta, aceptar_parcial=aceptar_parcial, observado_hasta=observado_hasta,
                        cobertura_config=config.get("cobertura"))


def entorno() -> dict[str, Any]:
    """Versión de código y dependencias del proceso que entrena (para reproducibilidad)."""
    info: dict[str, Any] = {"python": platform.python_version()}
    try:
        info["git_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                                            timeout=10).stdout.strip() or None
        info["git_cambios_sin_confirmar"] = bool(subprocess.run(["git", "status", "--porcelain", "--", "modelos", "pipeline"], cwd=RAIZ,
                                                                capture_output=True, text=True, timeout=10).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        info["git_commit"] = None
    for mod in ("sklearn", "numpy", "scipy"):
        try:
            info[mod] = __import__(mod).__version__
        except ImportError:
            info[mod] = None
    return info


# Dataset ----------------------------------------------------------------------------------
def preparar_dataset(datos: DatosAceptados, config: dict) -> dict[str, Any]:
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    cortes = cortes_mensuales(_d(config["cortes"]["desde"]), _d(config["cortes"]["hasta"]))
    filas = construir_fotografias(datos.clientes, historial, cortes, datos.observado_hasta,
                                  horizonte=config["horizonte_dias"],
                                  contexto={"revision_datos": datos.revision, "huella_datos": datos.huella_datos})
    bloques = {nombre: [f for f in filas if _d(a) <= f["corte"] <= _d(b)] for nombre, (a, b) in config["bloques"].items()}
    return {"historial": historial, "filas": filas, "bloques": bloques, "fronteras": verificar_fronteras(bloques, config)}


def verificar_fronteras(bloques: dict[str, list[dict]], config: dict) -> dict[str, Any]:
    """Las etiquetas de un bloque maduran antes de la primera inferencia del siguiente."""
    h = timedelta(days=config["horizonte_dias"])
    orden = ["ajuste", "validacion", "comprobacion_historica"]
    salida = {}
    for previo, siguiente in zip(orden, orden[1:]):
        madura = max(f["corte"] for f in bloques[previo]) + h
        primera = min(f["corte"] for f in bloques[siguiente])
        if madura > primera:
            raise ValueError(f"Fuga temporal: etiquetas de {previo} maduran el {madura}, después de la primera inferencia de {siguiente} ({primera})")
        salida[f"{previo}->{siguiente}"] = {"ultima_etiqueta_madura": madura.isoformat(), "primera_inferencia": primera.isoformat()}
    return salida


def poblacion(filas: list[dict]) -> list[dict]:
    """Recompra con etiqueta observada: elegibles y maduras."""
    return [f for f in filas if f["elegibilidad"] == ELEGIBLE and f["estado_etiqueta"] == MADURA]


def conteos(filas: list[dict]) -> dict[str, Any]:
    pob = poblacion(filas)
    return {"fotografias": len(filas), "cortes": sorted({f["corte"].isoformat() for f in filas}),
            "clientes_unicos": len({f["cliente_id"] for f in filas}),
            "excluidas_sin_historial": sum(f["elegibilidad"] == "sin_historial" for f in filas),
            "excluidas_alta_posterior": sum(f["elegibilidad"] == "alta_posterior" for f in filas),
            "excluidas_etiqueta_pendiente": sum(f["elegibilidad"] == ELEGIBLE and f["estado_etiqueta"] != MADURA for f in filas),
            "poblacion": len(pob), "clientes_poblacion": len({f["cliente_id"] for f in pob}),
            "positivos": sum(f["compra_30d"] for f in pob), "negativos": sum(1 - f["compra_30d"] for f in pob)}


# Referencia original -----------------------------------------------------------------------
def reproducir_referencia(datos: DatosAceptados, config: dict) -> dict[str, Any]:
    """Ejecuta el modelo original sobre la revisión aceptada y contrasta sus controles."""
    from pipeline import modelo_compra as mc

    ev = mc.entrenar_y_evaluar_desde_paquete(datos.directorio)
    snaps = mc._all_snapshots(datos.clientes, datos.ventas)
    tramos = {"entrenamiento": [r for r in snaps if r["corte"] <= date(2026, 4, 30)],
              "validacion": [r for r in snaps if date(2026, 5, 1) <= r["corte"] <= date(2026, 6, 30)],
              "prueba": [r for r in snaps if date(2026, 7, 1) <= r["corte"] <= date(2026, 9, 30)]}
    prob = lambda r: mc._probability(r, ev["medias"], ev["desviaciones"], ev["pesos"])  # noqa: E731
    top_p, top_r = {}, {}
    for corte, g in M.por_corte(tramos["prueba"]).items():
        top_p[corte.isoformat()] = M.ranking_k(g, prob, 10)["aciertos"]
        top_r[corte.isoformat()] = M.ranking_k(g, lambda r: -r["recencia_dias"], 10)["aciertos"]
    pm = ev["prueba_modelo"]
    obtenido = {"fotografias": {k: len(v) for k, v in tramos.items()}, "umbral": ev["umbral"],
                "matriz_prueba": {k: pm[k] for k in ("TP", "TN", "FP", "FN")},
                "precision": pm["precision"], "recall": pm["recall"], "F1": pm["F1"],
                "top10_probabilidad": top_p, "top10_recencia": top_r}
    esperado = config["controles_referencia"]
    diferencias = [k for k in esperado if esperado[k] != obtenido.get(k)]
    return {"ejecutado_en": _hoy_utc(), "datos": datos.descripcion(), "modelo": ev["modelo"], "variables": ev["variables"],
            "medias": ev["medias"], "desviaciones": ev["desviaciones"], "pesos": ev["pesos"], "umbral": ev["umbral"],
            "validacion": ev["validacion"], "prueba_modelo": ev["prueba_modelo"], "prueba_linea_base": ev["prueba_linea_base"],
            "observaciones": ev["observaciones"],
            "poblacion": "Original: clientes dados de alta al corte, incluidos los que no tienen compras (177 fotografías en entrenamiento).",
            "sin_historial_por_tramo": {k: sum(r["historial_n"] == 0 for r in v) for k, v in tramos.items()},
            "controles": {"esperado": esperado, "obtenido": obtenido, "diferencias": diferencias, "coincide": not diferencias}}


def artefacto_referencia(reproduccion: dict, config: dict) -> dict:
    """Artefacto JSON del modelo original congelado (mismas medias, desviaciones y pesos)."""
    pesos = reproduccion["pesos"]
    datos = {
        "formato": FORMATO, "modelo_id": MODELO_ID, "version": config.get("referencia_version", "A04-logistica-reglas-v1"),
        "descripcion": "Regresión logística original A04 (descenso de gradiente, 600 iteraciones, L2 0,001), congelada.",
        "version_variables": VERSION_VARIABLES, "horizonte_dias": HORIZONTE_DIAS, "variables": list(reproduccion["variables"]),
        "transformaciones": [{"variable": v, "funcion": "identidad", "imputacion": None, "media": m, "desviacion": s}
                             for v, m, s in zip(reproduccion["variables"], reproduccion["medias"], reproduccion["desviaciones"])],
        "intercepto": pesos[0], "pesos": pesos[1:], "umbral": reproduccion["umbral"],
        "politica_umbral": {"politica": "max_f1_validacion", "rejilla": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]},
        "poblacion": "original (incluye clientes sin compras en el ajuste; publica probabilidad solo con historial)",
        "disponible_desde": config["disponible_desde"], "origen_datos": config["origen_datos"],
        "entrenamiento": {"cortes_ajuste": ["2025-03-31", "2026-04-30"], "cortes_validacion": ["2026-05-31", "2026-06-30"],
                          "huella_datos": reproduccion["datos"]["huella_datos"], "revision_datos": reproduccion["datos"]["revision"]},
        "evaluacion": {k: reproduccion[k] for k in ("validacion", "prueba_modelo", "prueba_linea_base", "observaciones")},
    }
    return sellar(datos)


def verificar_equivalencia_referencia(art: Artefacto, datos: DatosAceptados, reproduccion: dict) -> float:
    """Diferencia máxima entre el artefacto JSON y la fórmula original en todas las fotografías con historial."""
    from pipeline import modelo_compra as mc

    snaps = [r for r in mc._all_snapshots(datos.clientes, datos.ventas) if r["historial_n"] > 0]
    return max(abs(art.probabilidad(r) - mc._probability(r, reproduccion["medias"], reproduccion["desviaciones"], reproduccion["pesos"]))
               for r in snaps)


def decision_referencia(art: Artefacto, reproduccion: dict) -> dict:
    return {"decision": "referencia_vigente", "estado_maximo": "operativo", "artefacto_huella": art.huella,
            "origen_datos": art.datos["origen_datos"],
            "motivo": "Modelo operativo anterior a M1 (A04). Se registra para conservarlo y reproducirlo sin entrenar en el cierre; "
                      "no es una validación empresarial nueva.",
            "controles_reproducidos": reproduccion["controles"]["coincide"], "limitaciones": LIMITACIONES}


# Candidato ---------------------------------------------------------------------------------
def ajustar_logistica(filas: list[dict], variables: list[str], C: float, estimador: dict) -> tuple[list[dict], float, list[float], Callable]:
    """Ajusta transformaciones y regresión L2 solo con ``filas``. Devuelve también la predicción de sklearn."""
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
    except ImportError as exc:
        raise DependenciaEntrenamiento("Entrenar requiere las dependencias opcionales: pip install -r requirements-modelos.txt") from exc
    trans = ajustar_transformaciones(filas, variables)
    X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
    y = np.array([int(f["compra_30d"]) for f in filas])
    modelo = LogisticRegression(C=C, solver=estimador["solver"], max_iter=estimador["max_iter"], tol=estimador["tol"],
                                class_weight=estimador["class_weight"], random_state=estimador["semilla"])
    modelo.fit(X, y)

    def predecir_sklearn(lote: list[dict]) -> list[float]:
        return [float(p) for p in modelo.predict_proba(np.array([aplicar_transformaciones(f, trans) for f in lote], dtype=float))[:, 1]]

    return trans, float(modelo.intercept_[0]), [float(w) for w in modelo.coef_[0]], predecir_sklearn


def _artefacto_candidato(nombre: str, variables: list[str], C: float, trans, intercepto, pesos, umbral: float, config: dict,
                         datos: DatosAceptados, ajuste: list[dict], politica: dict) -> dict:
    borrador = {
        "formato": FORMATO, "modelo_id": MODELO_ID, "version": "pendiente", "version_variables": VERSION_VARIABLES,
        "descripcion": f"Regresión logística L2 (C={C}) sobre la combinación {nombre}; población de recompra.",
        "horizonte_dias": HORIZONTE_DIAS, "variables": list(variables), "transformaciones": trans, "intercepto": intercepto,
        "pesos": pesos, "umbral": umbral, "politica_umbral": politica, "poblacion": "recompra (alta al corte y al menos una compra confirmada)",
        "combinacion": nombre, "C": C, "estimador": config["estimador"], "disponible_desde": config["disponible_desde"],
        "origen_datos": config["origen_datos"], "version_protocolo": config["version_protocolo"],
        "entrenamiento": {"cortes": sorted({f["corte"].isoformat() for f in ajuste}), "filas": len(ajuste),
                          "positivos": sum(f["compra_30d"] for f in ajuste), "huella_datos": datos.huella_datos,
                          "revision_datos": datos.revision},
    }
    borrador["version"] = f"compra_30d-m1-{nombre.lower()}-c{str(C).replace('.', '_')}-" + sellar(borrador)["huella"][:8]
    return sellar(borrador)


def elegir_umbral(filas: list[dict], prob: Callable[[dict], float], rejilla: list[float]) -> tuple[float, list[dict]]:
    tabla = [dict(M.matriz(filas, lambda f, u=u: prob(f) >= u), umbral=u) for u in rejilla]
    mejor = max(tabla, key=lambda t: (t["F1"], t["umbral"]))
    return mejor["umbral"], tabla


def _metricas_bloque(filas: list[dict], prob: Callable[[dict], float], ks) -> dict:
    r = M.resumen_ranking(filas, prob, ks)
    return {"ranking": r, "probabilidad": M.resumen_probabilidad(filas, prob)}


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path | None = None) -> dict[str, Any]:
    """Rejilla en ajuste, selección en validación y congelación. No lee la comprobación histórica."""
    ds = preparar_dataset(datos, config)
    ajuste, valid = poblacion(ds["bloques"]["ajuste"]), poblacion(ds["bloques"]["validacion"])
    for nombre, bloque in (("ajuste", ds["bloques"]["ajuste"]), ("validacion", ds["bloques"]["validacion"])):
        if any(f["elegibilidad"] == ELEGIBLE and f["estado_etiqueta"] != MADURA for f in bloque):
            raise ValueError(f"El bloque {nombre} tiene etiquetas pendientes; no se puede ajustar ni seleccionar")
    ks = config["k"]
    rejilla = []
    for nombre, variables in config["combinaciones"].items():
        for C in config["regularizacion_C"]:
            trans, b0, w, _ = ajustar_logistica(ajuste, variables, C, config["estimador"])
            art = desde_dict(sellar({"formato": FORMATO, "modelo_id": MODELO_ID, "version": "rejilla", "version_variables": VERSION_VARIABLES,
                                     "horizonte_dias": HORIZONTE_DIAS, "variables": variables, "transformaciones": trans, "intercepto": b0,
                                     "pesos": w, "umbral": 0.5, "disponible_desde": config["disponible_desde"]}))
            m = _metricas_bloque(valid, art.probabilidad, ks)
            ag = m["ranking"]["agregado"]
            rejilla.append({"combinacion": nombre, "n_variables": len(variables), "C": C,
                            "precision_media_top10": ag["precision_media_top10"], "aciertos_top10": ag["aciertos_top10"],
                            "average_precision_media_mensual": ag["average_precision_media_mensual"],
                            "brier": m["probabilidad"]["brier"], "intercepto": b0, "pesos": dict(zip(variables, w))})
    # Redondeo a 12 decimales: medias iguales de precisión no deben separarse por ruido de coma flotante.
    orden = sorted(rejilla, key=lambda r: (-round(r["precision_media_top10"], 12), -round(r["average_precision_media_mensual"], 12),
                                           round(r["brier"], 12), r["n_variables"], r["C"]))
    elegido = orden[0]
    variables = config["combinaciones"][elegido["combinacion"]]
    trans, b0, w, predecir_sklearn = ajustar_logistica(ajuste, variables, elegido["C"], config["estimador"])
    provisional = desde_dict(sellar({"formato": FORMATO, "modelo_id": MODELO_ID, "version": "provisional", "version_variables": VERSION_VARIABLES,
                                     "horizonte_dias": HORIZONTE_DIAS, "variables": variables, "transformaciones": trans, "intercepto": b0,
                                     "pesos": w, "umbral": 0.5, "disponible_desde": config["disponible_desde"]}))
    umbral, tabla_umbral = elegir_umbral(valid, provisional.probabilidad, config["umbral"]["rejilla"])
    politica = dict(config["umbral"], umbral_elegido=umbral, bloque="validacion")
    artefacto = _artefacto_candidato(elegido["combinacion"], variables, elegido["C"], trans, b0, w, umbral, config, datos, ajuste, politica)
    art = desde_dict(artefacto)
    filas_eq = ajuste + valid
    dif = max(abs(a - b) for a, b in zip(predecir_sklearn(filas_eq), (art.probabilidad(f) for f in filas_eq)))
    if dif > config["tolerancia_probabilidad"]:
        raise ValueError(f"La inferencia desde JSON difiere de sklearn en {dif:g} (> {config['tolerancia_probabilidad']})")
    reproduccion = reproducir_referencia(datos, config)
    ref = artefacto_referencia(reproduccion, config)
    validacion = {"candidato": _metricas_bloque(valid, art.probabilidad, ks),
                  "original_congelado": _metricas_bloque(valid, desde_dict(ref).probabilidad, ks),
                  "matriz_candidato": M.matriz(valid, lambda f: art.probabilidad(f) >= umbral), "tabla_umbral": tabla_umbral}
    ref_art = desde_dict(ref)
    hoy = datetime.now(timezone.utc).date()
    primer = _primer_fin_de_mes_posterior(hoy)
    congelacion = {"formato": FORMATO_CONGELACION, "congelado_en": _hoy_utc(), "artefacto_huella": art.huella, "artefacto_version": art.version,
                   "referencia_huella": ref_art.huella, "referencia_version": ref_art.version,
                   "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
                   "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config),
                                 "identidad": identidad_protocolo(config)},
                   "fechas": {"congelacion_real": hoy.isoformat(), "disponibilidad_simulada_desde": config["disponible_desde"],
                              "datos_observados_hasta": datos.observado_hasta.isoformat(),
                              "primer_corte_prospectivo": primer.isoformat(),
                              "primer_corte_prospectivo_madura_el": (primer + timedelta(days=config["horizonte_dias"])).isoformat(),
                              "nota": "Cortes no posteriores a la congelación real son comprobaciones retrospectivas."},
                   "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica",
                   "equivalencia_json_sklearn": {"diferencia_maxima": dif, "tolerancia": config["tolerancia_probabilidad"], "filas": len(filas_eq)},
                   "disponibilidad_simulada": {"ajuste_conocido_desde": ds["fronteras"]["ajuste->validacion"]["ultima_etiqueta_madura"],
                                               "validacion_conocida_desde": ds["fronteras"]["validacion->comprobacion_historica"]["ultima_etiqueta_madura"]}}
    congelacion["sello"] = _sello_congelacion(congelacion)
    resumen = {"seleccion": {"criterio": config["seleccion"]["criterio"], "elegido": {k: elegido[k] for k in ("combinacion", "C", "n_variables")},
                             "rejilla": orden},
               "umbral": umbral, "artefacto": art.datos, "referencia_artefacto": ref, "reproduccion": reproduccion,
               "validacion": validacion, "congelacion": congelacion,
               "datos": dict(datos.descripcion(), fronteras=ds["fronteras"],
                             bloques={k: conteos(v) for k, v in ds["bloques"].items() if k != "comprobacion_historica"},
                             ejecutado_en=_hoy_utc(), datos_maximos_usados=datos.observado_hasta.isoformat())}
    if salida is not None:
        salida = Path(salida)
        if (salida / "artefacto.json").exists():
            raise FileExistsError(f"{salida} ya contiene una ejecución; usa otra carpeta")
        _comprobar_version_protocolo(salida, config)
        salida.mkdir(parents=True, exist_ok=True)
        _json(salida / "config.json", config)
        _json(salida / "datos.json", resumen["datos"])
        _json(salida / "referencia.json", reproduccion)
        _json(salida / "referencia_artefacto.json", ref)
        _json(salida / "artefacto.json", art.datos)
        _json(salida / "seleccion.json", {"seleccion": resumen["seleccion"], "validacion": validacion, "umbral": umbral})
        _json(salida / "congelacion.json", congelacion)
        _json(salida / "entorno.json", entorno())
        _escribir_predicciones(salida / "predicciones_validacion.csv", ds["bloques"]["validacion"], {"validacion": True},
                               {"candidato": art, "original_congelado": desde_dict(ref)})
    return resumen


def _comprobar_version_protocolo(salida: Path, config: dict) -> None:
    """Una misma version_protocolo no puede congelarse con contenidos distintos en ejecuciones hermanas."""
    huella = huella_protocolo(config)
    for otra in sorted(salida.parent.glob("*/congelacion.json")):
        c = _leer(otra)
        p = c.get("protocolo")
        if p and p.get("version") == config["version_protocolo"] and p.get("huella") != huella:
            raise ProtocoloError(f"version_protocolo '{config['version_protocolo']}' ya se congeló en {otra.parent.name} con otro "
                                 "contenido; asigna una versión nueva al protocolo modificado.")


# Evaluación ---------------------------------------------------------------------------------
def _atendibles(datos: DatosAceptados, cortes: list[date]) -> dict[date, set[str]]:
    """Clientes que la agenda C1 no captura antes por reactivación (frío) o cobertura, por corte.

    Las coberturas usan ``base_instalada`` con disponibilidad por fecha de inicio (convención sintética).
    """
    from pipeline.ficha import construir_ficha
    from pipeline.operaciones import _load

    instalaciones = _load(datos.directorio, "base_instalada.csv", "instalaciones")
    salida = {}
    for corte in cortes:
        ficha = construir_ficha(datos.clientes, datos.ventas, instalaciones, corte)
        salida[corte] = {f["cliente_id"] for f in ficha
                         if not f["frio"] and not f["coberturas_proximas"] and not f["coberturas_vencidas"]}
    return salida


def _escribir_predicciones(ruta: Path, filas: list[dict], bloque_de, modelos: dict[str, Artefacto]) -> None:
    campos = ["cliente_id", "corte", "bloque", "elegibilidad", "estado_etiqueta", "fecha_maduracion", "compra_30d", "recencia_dias",
              "frecuencia_30d"] + [f"prob_{k}" for k in modelos] + ["version_variables", "revision_datos", "huella_datos"]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for fila in sorted(filas, key=lambda r: (r["corte"], r["cliente_id"])):
            fuera = {k: (round(a.probabilidad(fila), 9) if fila["elegibilidad"] == ELEGIBLE else None) for k, a in modelos.items()}
            bloque = next((b for b, ok in bloque_de.items() if ok is True or (callable(ok) and ok(fila))), None)
            w.writerow(dict(fila, bloque=bloque, corte=fila["corte"].isoformat(),
                            fecha_maduracion=fila["fecha_maduracion"].isoformat() if fila["fecha_maduracion"] else None,
                            **{f"prob_{k}": v for k, v in fuera.items()}))


def _decidir(cand: dict, refs: dict, config: dict) -> dict:
    metas = config["metas"]
    p_c = cand["ranking"]["agregado"]["precision_media_top10"]
    p_r = refs["recencia"]["ranking"]["agregado"]["precision_media_top10"]
    mejora = p_c - p_r
    meses = []
    for mc_, mr in zip(cand["ranking"]["por_mes"], refs["recencia"]["ranking"]["por_mes"]):
        perdidos = mr["top10"]["aciertos"] - mc_["top10"]["aciertos"]
        if perdidos >= metas["compradores_perdidos_mes_revisar"]:
            meses.append({"corte": mc_["corte"], "candidato": mc_["top10"]["aciertos"], "recencia": mr["top10"]["aciertos"], "perdidos": perdidos})
    b_c = cand["probabilidad"]["brier"]
    b_k = refs["constante"]["probabilidad"]["brier"]
    cumple = {"mejora_precision_top10": mejora >= metas["mejora_minima_precision_top10"] - 1e-12,
              "sin_meses_con_perdida": not meses, "brier_no_peor_que_constante": b_c <= b_k}
    if all(cumple.values()):
        decision = "favorable"
    elif mejora <= -metas["margen_rechazo_precision_top10"] + 1e-12 or not cumple["brier_no_peor_que_constante"]:
        decision = "rechazado"
    else:
        decision = "inconcluso"
    # Sombra no cambia decisiones de usuarios; "operativo" nunca se concede desde esta evaluación.
    maximo = "ninguno" if decision == "rechazado" else "sombra"
    return {"decision": decision, "estado_maximo": maximo, "metas": metas, "cumple": cumple,
            "valores": {"precision_media_top10_candidato": p_c, "precision_media_top10_recencia": p_r, "mejora": mejora,
                        "brier_candidato": b_c, "brier_constante": b_k},
            "meses_a_revisar": meses,
            "nota_operativo": "Ninguna evaluación de esta ejecución concede 'operativo': la comprobación es sintética y ya inspeccionada. "
                              "Pasar a operativo requiere datos empresariales posteriores a la congelación y aprobación registrada."}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None, bloque: str = "comprobacion_historica") -> dict[str, Any]:
    """Mide el artefacto congelado en ``bloque`` sin reajustar y escribe métricas, predicciones y decisión."""
    ejecucion = Path(ejecucion)
    congelacion = verificar_congelacion(ejecucion)
    config = _leer(ejecucion / "config.json")
    art = cargar_artefacto(ejecucion / "artefacto.json")
    ref = cargar_artefacto(ejecucion / "referencia_artefacto.json")
    info_datos = _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info_datos["directorio"], aceptar_parcial=info_datos["aceptacion_parcial"],
                             observado_hasta=info_datos["datos_observados_hasta"])
    if datos.huella_datos != info_datos["huella_datos"] or datos.huella_datos != congelacion["huella_datos"]:
        raise ValueError("La revisión de datos difiere de la usada para entrenar; define un protocolo nuevo para evaluarla")
    ds = preparar_dataset(datos, config)
    filas = poblacion(ds["bloques"][bloque])
    pendientes = [f for f in ds["bloques"][bloque] if f["elegibilidad"] == ELEGIBLE and f["estado_etiqueta"] != MADURA]
    if not filas:
        raise ValueError(f"El bloque {bloque} no tiene etiquetas maduras")
    ajuste = poblacion(ds["bloques"]["ajuste"])
    tasa = sum(f["compra_30d"] for f in ajuste) / len(ajuste)
    ks = config["k"]
    puntajes: dict[str, Callable[[dict], float]] = {
        "candidato": art.probabilidad, "original_congelado": ref.probabilidad,
        "regla_30d": lambda f: float(f["frecuencia_30d"] > 0), "recencia": lambda f: -float(f["recencia_dias"]),
        "constante": lambda f: tasa}
    probabilisticos = {"candidato", "original_congelado", "constante"}
    resultados: dict[str, Any] = {}
    for nombre, s in puntajes.items():
        entrada: dict[str, Any] = {"ranking": M.resumen_ranking(filas, s, ks)}
        if nombre in probabilisticos:
            entrada["probabilidad"] = M.resumen_probabilidad(filas, s)
        resultados[nombre] = entrada
    resultados["candidato"]["matriz"] = M.matriz(filas, lambda f: art.probabilidad(f) >= art.umbral)
    resultados["original_congelado"]["matriz"] = M.matriz(filas, lambda f: ref.probabilidad(f) >= ref.umbral)
    resultados["regla_30d"]["matriz"] = M.matriz(filas, lambda f: f["frecuencia_30d"] > 0)
    resultados["constante"]["nota"] = f"Probabilidad fija igual a la tasa de compra del ajuste ({tasa:.4f}); su orden es solo el desempate por cliente_id."
    resultados["regla_30d"]["nota"] = "Puntaje 1/0; dentro de cada grupo el orden es el desempate por cliente_id."
    # Lista atendible: clientes que la agenda no asigna antes a reactivación o cobertura.
    cortes = sorted({f["corte"] for f in filas})
    atendibles = _atendibles(datos, cortes)
    sub = [f for f in filas if f["cliente_id"] in atendibles[f["corte"]]]
    agenda_operativa = {nombre: M.resumen_ranking(sub, s, ks) for nombre, s in puntajes.items() if nombre != "constante"}
    # Errores comerciales del candidato en los diez primeros.
    errores = []
    for corte, g in M.por_corte(filas).items():
        orden = M.ordenar(g, art.probabilidad)
        top = orden[:10]
        errores.append({"corte": corte.isoformat(),
                        "falsos_positivos_top10": [{"cliente_id": f["cliente_id"], "prob": round(art.probabilidad(f), 4),
                                                    "recencia_dias": f["recencia_dias"], "frecuencia_90d": f["frecuencia_90d"]}
                                                   for f in top if not f["compra_30d"]],
                        "omisiones": [{"cliente_id": f["cliente_id"], "posicion": i, "prob": round(art.probabilidad(f), 4),
                                       "recencia_dias": f["recencia_dias"]}
                                      for i, f in enumerate(orden, start=1) if f["compra_30d"] and i > 10][:5]})
    boot = config.get("bootstrap", {})
    incertidumbre = {
        "ap_candidato_menos_recencia": M.bootstrap_clientes(
            filas, lambda m: (M.average_precision(m, art.probabilidad) or 0) - (M.average_precision(m, puntajes["recencia"]) or 0),
            boot.get("repeticiones", 1000), boot.get("semilla", 20261123)),
        "brier_candidato_menos_constante": M.bootstrap_clientes(
            filas, lambda m: M.brier(m, art.probabilidad) - M.brier(m, puntajes["constante"]),
            boot.get("repeticiones", 1000), boot.get("semilla", 20261123))}
    decision = _decidir(resultados["candidato"], resultados, config)
    metricas = {"bloque": bloque, "evaluado_en": _hoy_utc(), "alcance": "comprobación histórica exploratoria: periodo ya inspeccionado",
                "artefacto": {"version": art.version, "huella": art.huella, "umbral": art.umbral, "variables": art.datos["variables"]},
                "referencia_original": {"version": ref.version, "huella": ref.huella, "umbral": ref.umbral},
                "poblacion": conteos(ds["bloques"][bloque]), "pendientes": len(pendientes),
                "tasa_ajuste": tasa, "resultados": resultados, "agenda_operativa": {
                    "definicion": "Ranking restringido a clientes sin reactivación ni cobertura al corte (los que la agenda ordena por probabilidad).",
                    "n": len(sub), "por_metodo": agenda_operativa},
                "errores_comerciales": errores, "incertidumbre_bootstrap_clientes": incertidumbre,
                "reproduccion_original": _leer(ejecucion / "referencia.json")["controles"]}
    decision_doc = dict(decision, artefacto_huella=art.huella, artefacto_version=art.version, origen_datos=config["origen_datos"],
                        bloque=bloque, alcance=metricas["alcance"], decidido_en=_hoy_utc(), version_protocolo=config["version_protocolo"],
                        protocolo_huella=congelacion["protocolo"]["huella"], congelacion_sello=congelacion["sello"],
                        fechas=congelacion["fechas"],
                        version_sustituida=None, limitaciones=LIMITACIONES,
                        politica_recomendada=("Mantener la versión operativa vigente y el orden contractual de C1; "
                                              + ("usar el candidato solo en sombra." if decision["estado_maximo"] == "sombra"
                                                 else "conservar el ranking por recencia como comparador del piloto.")))
    # Todas las comprobaciones antes de escribir: un rechazo no modifica métricas, predicciones ni decisión.
    ruta_metricas = ejecucion / f"metricas_{bloque}.json"
    normal = lambda d: json.loads(json.dumps({k: v for k, v in d.items() if k != "evaluado_en"}, default=str))  # noqa: E731
    metricas_previas = _leer(ruta_metricas) if ruta_metricas.exists() else None
    if metricas_previas is not None and normal(metricas_previas) != normal(metricas):
        raise ProtocoloError(f"{ruta_metricas} ya contiene métricas distintas de las recalculadas; no se sobrescriben. "
                             "Usa una ejecución nueva.")
    previa = ejecucion / "decision.json"
    anterior = None
    if bloque == "comprobacion_historica" and previa.exists():
        claves = ("decision", "estado_maximo", "cumple", "valores", "artefacto_huella", "protocolo_huella", "meses_a_revisar")
        anterior = _leer(previa)
        if {k: anterior.get(k) for k in claves} != json.loads(json.dumps({k: decision_doc.get(k) for k in claves}, default=str)):
            raise ProtocoloError(f"{previa} ya contiene una decisión distinta; una ejecución congelada no se sobrescribe. "
                                 "Usa una ejecución nueva.")
    if metricas_previas is None:
        _json(ruta_metricas, metricas)
    else:
        metricas = metricas_previas  # mismas métricas: se conserva el documento original
    if bloque != "comprobacion_historica":
        return {"metricas": metricas, "decision": None}  # la validación no emite decisiones
    if anterior is not None:
        decision_doc = anterior
    else:
        _json(previa, decision_doc)
    _escribir_predicciones(ejecucion / "predicciones.csv", ds["filas"],
                           {b: (lambda f, a=a, z=z: _d(a) <= f["corte"] <= _d(z)) for b, (a, z) in config["bloques"].items()},
                           {"candidato": art, "original_congelado": ref})
    return {"metricas": metricas, "decision": decision_doc}


# Puntuación y sombra ------------------------------------------------------------------------
def puntuar(art: Artefacto, datos: DatosAceptados, corte: date, salida: str | Path | None = None, *,
            simulacion_historica: bool = False, etiqueta: str = "") -> dict[str, Any]:
    """Inferencia de un corte desde el artefacto JSON (sin entrenamiento)."""
    if art.datos.get("modelo_id", MODELO_ID) != MODELO_ID:
        raise ArtefactoInvalido(f"{art.version} es un artefacto de {art.datos.get('modelo_id')!r}, no de {MODELO_ID}")
    if corte < art.disponible_desde and not simulacion_historica:
        raise ValueError(f"{art.version} está disponible desde {art.disponible_desde}; para cortes anteriores usa una simulación histórica explícita")
    verificar_cobertura_corte(corte, datos.cobertura)  # misma política que el cierre
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    filas = construir_fotografias(datos.clientes, historial, [corte], datos.observado_hasta,
                                  contexto={"revision_datos": datos.revision, "huella_datos": datos.huella_datos},
                                  version=art.version_variables)
    elegibles = [f for f in filas if f["elegibilidad"] == ELEGIBLE]
    politica = (art.datos.get("politica_orden") or {}).get("id")
    if politica == "fusion_rangos_recencia_v1":  # orden del cupo M1.2; la probabilidad no cambia
        from .ranking import posiciones_fusion
        orden_p = posiciones_fusion(elegibles, art.probabilidad) if elegibles else {}
    else:
        orden_p = {f["cliente_id"]: i for i, f in enumerate(M.ordenar(elegibles, art.probabilidad), start=1)}
    orden_r = {f["cliente_id"]: i for i, f in enumerate(M.ordenar(elegibles, lambda f: -f["recencia_dias"]), start=1)}
    salida_filas = []
    for f in filas:
        e = f["elegibilidad"] == ELEGIBLE
        salida_filas.append({"cliente_id": f["cliente_id"], "corte": corte.isoformat(), "modelo_id": MODELO_ID,
                             "version_modelo": art.version, "artefacto_huella": art.huella,
                             "estado": "estimado" if e else ("sin_historial" if f["elegibilidad"] == "sin_historial" else "no_elegible"),
                             "probabilidad": round(art.probabilidad(f), 9) if e else None,
                             "supera_umbral": (art.probabilidad(f) >= art.umbral) if e else None,
                             "posicion": orden_p.get(f["cliente_id"]), "posicion_recencia": orden_r.get(f["cliente_id"]),
                             "recencia_dias": f["recencia_dias"], "estado_etiqueta": f["estado_etiqueta"],
                             "compra_30d": f["compra_30d"], "fecha_maduracion": f["fecha_maduracion"].isoformat() if f["fecha_maduracion"] else None})
    resumen = {"ejecutado_en": _hoy_utc(), "corte": corte.isoformat(), "datos_hasta": corte.isoformat(),
               "datos_observados_hasta": datos.observado_hasta.isoformat(), "simulacion_historica": simulacion_historica,
               "etiqueta": etiqueta, "artefacto": {"version": art.version, "huella": art.huella, "umbral": art.umbral},
               "politica_orden": politica or "probabilidad_descendente",
               "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
               "clientes": len(filas), "estimados": len(elegibles),
               "abstenciones": {"sin_historial": sum(f["elegibilidad"] == "sin_historial" for f in filas),
                                "no_elegible": sum(f["elegibilidad"] == "alta_posterior" for f in filas)},
               "etiquetas": {"pendientes": sum(f["estado_etiqueta"] == "pendiente" for f in filas),
                             "maduras": sum(f["estado_etiqueta"] == MADURA for f in filas),
                             "maduran_el": (corte + timedelta(days=HORIZONTE_DIAS)).isoformat()},
               "supera_umbral": sum(1 for f in salida_filas if f["supera_umbral"])}
    if salida is not None:
        salida = Path(salida)
        salida.mkdir(parents=True, exist_ok=True)
        _json(salida / "resumen.json", resumen)
        with (salida / "puntuaciones.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(salida_filas[0]))
            w.writeheader()
            w.writerows(salida_filas)
    return {"resumen": resumen, "filas": salida_filas}


class PilotoError(ValueError):
    """Puntuaciones incompatibles o registro del piloto inconsistente; no se escribe nada."""


CAMPOS_HUMANOS = ["contacto_realizado", "fecha_contacto", "tiempo_minutos", "resultado_contacto"]
CAMPOS_SELECCION = ["version_operativa", "huella_operativa", "version_sombra", "huella_sombra", "huella_datos_puntuacion",
                    "posicion_operativa", "prob_operativa", "posicion_sombra", "prob_sombra", "posicion_recencia",
                    "en_cupo_operativo", "en_cupo_sombra", "en_cupo_recencia"]
CAMPOS_ETIQUETA = ["compra_30d", "estado_etiqueta", "motivo_etiqueta", "fecha_maduracion"]
# Orden histórico (compatibilidad con el CSV anterior) + columnas nuevas al final.
COLUMNAS_PILOTO = ["corte", "cliente_id", "version_operativa", "posicion_operativa", "prob_operativa", "version_sombra",
                   "posicion_sombra", "prob_sombra", "posicion_recencia", "en_cupo_operativo", "en_cupo_sombra", "en_cupo_recencia",
                   "contacto_realizado", "fecha_contacto", "tiempo_minutos", "resultado_contacto", "compra_30d", "estado_etiqueta",
                   "fecha_maduracion", "seleccion_id", "huella_operativa", "huella_sombra", "huella_datos_puntuacion",
                   "motivo_etiqueta", "en_cohorte_actual", "seleccion_id_anterior"]
POLITICA_SELECCION = ("seleccion-v1: top K por 'posicion' de cada puntuación dentro de la cohorte; recencia por "
                      "'posicion_recencia' de la puntuación operativa; desempate por cliente_id")


def identidad_seleccion(corte: str, r_o: dict, r_s: dict, cohorte: list[str], k: int, reconciliacion: list[str]) -> tuple[str, dict]:
    """Identidad determinista de una selección: corte, artefactos, revisiones de datos, cohorte, cupo y política.

    El lote usado después para observar etiquetas NO forma parte de la identidad: actualizar resultados no
    crea una selección nueva.
    """
    componentes = {"corte": corte, "k": k, "politica": POLITICA_SELECCION,
                   "artefactos": {"operativo": r_o["artefacto"]["huella"], "sombra": r_s["artefacto"]["huella"]},
                   "datos_puntuacion": {"operativo": (r_o.get("datos") or {}).get("huella_datos"),
                                        "sombra": (r_s.get("datos") or {}).get("huella_datos")},
                   "cohorte": hashlib.sha256(",".join(sorted(cohorte)).encode()).hexdigest(),
                   "cohorte_clientes": len(cohorte),
                   "reconciliacion": {"aplicada": bool(reconciliacion), "detalle": list(reconciliacion),
                                      "politica": "interseccion de cohortes" if reconciliacion else None}}
    return f"{corte}|s-{hashlib.sha256(_canon(componentes).encode()).hexdigest()[:16]}", componentes


def _leer_puntuaciones(directorio: Path) -> tuple[dict, list[dict]]:
    """Lee y valida un directorio de ``puntuar``: un cliente por fila y el mismo corte en todas."""
    directorio = Path(directorio)
    if not (directorio / "resumen.json").is_file() or not (directorio / "puntuaciones.csv").is_file():
        raise PilotoError(f"{directorio} no contiene resumen.json y puntuaciones.csv; genera primero 'modelos.cli puntuar'")
    resumen = _leer(directorio / "resumen.json")
    with (directorio / "puntuaciones.csv").open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    ids = [f["cliente_id"] for f in filas]
    repetidos = sorted({i for i in ids if ids.count(i) > 1})
    if repetidos:
        raise PilotoError(f"{directorio}: clientes repetidos en puntuaciones.csv {repetidos[:5]}; la puntuación no es válida")
    if any(f["corte"] != resumen["corte"] for f in filas):
        raise PilotoError(f"{directorio}: hay filas con un corte distinto del resumen ({resumen['corte']})")
    return resumen, filas


def _escribir_texto_atomico(ruta: Path, texto: str) -> None:
    """Escribe en un temporal del mismo directorio y sustituye al final; un fallo deja el archivo anterior."""
    import os
    import tempfile
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(texto)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _validar_humanos(fila: dict, donde: str) -> list[str]:
    e = []
    if fila.get("contacto_realizado", "") not in ("", "si", "no"):
        e.append(f"{donde}: contacto_realizado debe ser 'si', 'no' o vacío (llegó {fila['contacto_realizado']!r})")
    if fila.get("fecha_contacto"):
        try:
            date.fromisoformat(fila["fecha_contacto"])
        except ValueError:
            e.append(f"{donde}: fecha_contacto {fila['fecha_contacto']!r} no es AAAA-MM-DD")
    t = fila.get("tiempo_minutos", "")
    if t not in ("", None) and (not str(t).isdigit()):
        e.append(f"{donde}: tiempo_minutos {t!r} debe ser un entero de minutos no negativo")
    return e


def _tiene_humanos(fila: dict) -> bool:
    return any(str(fila.get(c) or "").strip() for c in CAMPOS_HUMANOS)


def _leer_registro_piloto(ruta: Path) -> list[dict]:
    """Lee el CSV del piloto (formato actual o anterior) y valida claves y campos humanos."""
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8-sig", newline="") as fh:
        lector = csv.DictReader(fh)
        faltan = [c for c in ["corte", "cliente_id", "version_operativa", "version_sombra", *CAMPOS_HUMANOS] if c not in (lector.fieldnames or [])]
        if faltan:
            raise PilotoError(f"{ruta}: faltan columnas {faltan}; no se modifica el registro del piloto")
        filas = [dict(f) for f in lector]
    # Migración de filas del formato anterior (sin seleccion_id): se deriva de corte, versiones y cupo.
    cupos: dict[tuple, int] = {}
    for f in filas:
        if not f.get("seleccion_id"):
            clave = (f["corte"], f["version_operativa"], f["version_sombra"])
            cupos[clave] = cupos.get(clave, 0) + (f.get("en_cupo_operativo") == "True")
    errores = []
    vistos = set()
    for i, f in enumerate(filas, start=2):
        if not f.get("seleccion_id"):
            f["seleccion_id"] = f"{f['corte']}|{f['version_operativa']}|{f['version_sombra']}|k{cupos[(f['corte'], f['version_operativa'], f['version_sombra'])]}"
        for c in COLUMNAS_PILOTO:
            f.setdefault(c, "")
        clave = (f["corte"], f["cliente_id"], f["seleccion_id"])
        if clave in vistos:
            errores.append(f"fila {i}: clave repetida corte={clave[0]} cliente_id={clave[1]} seleccion={clave[2]}")
        vistos.add(clave)
        errores.extend(_validar_humanos(f, f"fila {i} ({f['cliente_id']})"))
    if errores:
        raise PilotoError(f"{ruta} tiene datos inconsistentes; no se modifica. Corrígelos y repite: " + "; ".join(errores[:10]))
    return filas


def _texto_piloto(filas: list[dict]) -> str:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNAS_PILOTO, extrasaction="ignore", lineterminator="\r\n")
    w.writeheader()
    for f in sorted(filas, key=lambda f: (f["corte"], f["seleccion_id"], f["cliente_id"])):
        w.writerow({c: f.get(c, "") for c in COLUMNAS_PILOTO})
    return buf.getvalue()


def etiquetas_cohorte(cohorte: list[str], corte: date, datos: DatosAceptados | None) -> dict[str, dict[str, Any]]:
    """Etiqueta de cada cliente de la cohorte puntuada, observada con un lote (posiblemente posterior).

    Estados: ``madura`` (0/1), ``pendiente`` (horizonte no cubierto), ``datos_faltantes`` (el cliente no
    está en el lote de observación) y ``no_aplica`` (el lote lo da de alta después del corte). Nunca se
    convierte la falta de información en compra = 0. Las altas posteriores fuera de la cohorte se ignoran.
    """
    fin = corte + timedelta(days=HORIZONTE_DIAS)
    if datos is None:
        return {c: {"compra_30d": None, "estado_etiqueta": "pendiente", "motivo_etiqueta": "sin lote de observación"} for c in cohorte}
    if not datos.cobertura.conocida:
        return {c: {"compra_30d": None, "estado_etiqueta": "pendiente",
                    "motivo_etiqueta": f"cobertura del lote de observación desconocida ({datos.fuente_cobertura})"} for c in cohorte}
    clientes = {str(c["cliente_id"]): c for c in datos.clientes}
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    salida = {}
    for cid in cohorte:
        cli = clientes.get(cid)
        if cli is None:
            salida[cid] = {"compra_30d": None, "estado_etiqueta": "datos_faltantes",
                           "motivo_etiqueta": "el cliente no aparece en el lote de observación"}
        elif cli["fecha_alta"] > corte:
            salida[cid] = {"compra_30d": None, "estado_etiqueta": "no_aplica",
                           "motivo_etiqueta": f"el lote de observación lo da de alta el {cli['fecha_alta']}, después del corte"}
        else:
            y, estado, _ = etiqueta_al_corte(historial.get(cid, []), corte, datos.observado_hasta)
            salida[cid] = {"compra_30d": y, "estado_etiqueta": estado,
                           "motivo_etiqueta": "" if estado == MADURA else
                           f"datos completos hasta {datos.observado_hasta}; el horizonte termina el {fin}"}
    return salida


def comparar(operativo: str | Path, sombra: str | Path, salida: str | Path, datos: DatosAceptados | None = None,
             k: int = 10, *, reconciliar: bool = False, nueva_seleccion: bool = False) -> dict[str, Any]:
    """Operativo frente a sombra y recencia a igual cupo, sobre la cohorte puntuada originalmente.

    * La cohorte son los clientes ``estimado`` de las puntuaciones; ambas puntuaciones deben tener el
      mismo corte, la misma cohorte y la misma revisión de datos de origen (o ``reconciliar=True``,
      que usa la intersección y lo informa).
    * Las etiquetas se observan con ``datos`` (lote posterior, otra huella es lo esperado).
    * ``piloto_registro.csv`` se actualiza conservando los campos humanos por (corte, cliente_id,
      seleccion_id). Una selección distinta para el mismo corte exige ``nueva_seleccion=True`` y se
      añade sin reasignar contactos. Todo se valida antes de escribir y la escritura es atómica.
    """
    r_o, f_o = _leer_puntuaciones(Path(operativo))
    r_s, f_s = _leer_puntuaciones(Path(sombra))
    if r_o["corte"] != r_s["corte"]:
        raise PilotoError(f"Cortes distintos: operativo {r_o['corte']} y sombra {r_s['corte']}; compara puntuaciones del mismo corte")
    corte = _d(r_o["corte"])
    reconciliacion = []
    h_o, h_s = r_o.get("datos", {}).get("huella_datos"), r_s.get("datos", {}).get("huella_datos")
    if h_o != h_s:
        if not reconciliar:
            raise PilotoError("Las puntuaciones usan revisiones de datos distintas (huella_datos); vuelve a puntuar ambas con el mismo "
                              "lote o usa --reconciliar para compararlas igualmente")
        reconciliacion.append(f"revisiones de datos distintas: {str(h_o)[:12]}… y {str(h_s)[:12]}…")
    est_o = {f["cliente_id"] for f in f_o if f["estado"] == "estimado"}
    est_s = {f["cliente_id"] for f in f_s if f["estado"] == "estimado"}
    if est_o != est_s:
        if not reconciliar:
            raise PilotoError(f"Cohortes distintas: {len(est_o - est_s)} clientes solo en operativo y {len(est_s - est_o)} solo en sombra; "
                              "usa --reconciliar para comparar la intersección")
        reconciliacion.append(f"cohortes distintas: se compara la intersección ({len(est_o & est_s)} clientes)")
    cohorte = sorted(est_o & est_s)
    por_o = {f["cliente_id"]: f for f in f_o}
    por_s = {f["cliente_id"]: f for f in f_s}

    def top(por, campo):
        return [c for c in sorted(cohorte, key=lambda c: int(por[c][campo]))][:k]

    listas = {"operativo": top(por_o, "posicion"), "sombra": top(por_s, "posicion"), "recencia": top(por_o, "posicion_recencia")}
    etiquetas = etiquetas_cohorte(cohorte, corte, datos)
    conteo_estados: dict[str, int] = {}
    for e in etiquetas.values():
        conteo_estados[e["estado_etiqueta"]] = conteo_estados.get(e["estado_etiqueta"], 0) + 1
    pendientes = conteo_estados.get("pendiente", 0)
    excluidos = {c: e for c, e in etiquetas.items() if e["estado_etiqueta"] in ("datos_faltantes", "no_aplica")}
    if pendientes:
        estado_cohorte = "pendiente"
    elif excluidos:
        estado_cohorte = "madura_con_exclusiones"
    else:
        estado_cohorte = MADURA
    altas_posteriores = 0
    if datos is not None:
        altas_posteriores = sum(1 for c in datos.clientes if str(c["cliente_id"]) not in set(cohorte) and c["fecha_alta"] > corte)
    resultado = {"corte": corte.isoformat(), "k": k, "comparado_en": _hoy_utc(),
                 "versiones": {"operativo": r_o["artefacto"]["version"], "sombra": r_s["artefacto"]["version"]},
                 "huellas_artefacto": {"operativo": r_o["artefacto"]["huella"], "sombra": r_s["artefacto"]["huella"]},
                 "cohorte": {"clientes": len(cohorte), "huella_datos_puntuacion": h_o, "reconciliacion": reconciliacion,
                             "altas_posteriores_ignoradas": altas_posteriores},
                 "lote_observacion": ({"huella_datos": datos.huella_datos, "revision": datos.revision,
                                       "datos_observados_hasta": datos.observado_hasta.isoformat() if datos.observado_hasta else None,
                                       "fuente_cobertura": datos.fuente_cobertura} if datos is not None else None),
                 "listas": listas, "coincidencias": {"operativo_sombra": len(set(listas["operativo"]) & set(listas["sombra"])),
                                                     "sombra_recencia": len(set(listas["sombra"]) & set(listas["recencia"]))},
                 "estado_etiquetas": estado_cohorte, "etiquetas_por_estado": conteo_estados,
                 "maduran_el": (corte + timedelta(days=HORIZONTE_DIAS)).isoformat(),
                 "excluidos": [{"cliente_id": c, **e} for c, e in sorted(excluidos.items())]}
    if pendientes:
        motivos = sorted({e["motivo_etiqueta"] for e in etiquetas.values() if e["estado_etiqueta"] == "pendiente"})
        resultado["aciertos"] = {m: None for m in listas}
        resultado["nota"] = (f"{pendientes} de {len(cohorte)} etiquetas pendientes ({'; '.join(motivos)}). "
                             f"Los resultados se conocerán con datos completos hasta {resultado['maduran_el']}.")
    else:
        resultado["aciertos"] = {}
        for m, lst in listas.items():
            evaluados = [c for c in lst if etiquetas[c]["estado_etiqueta"] == MADURA]
            acierto = sum(etiquetas[c]["compra_30d"] for c in evaluados)
            resultado["aciertos"][m] = acierto
            resultado.setdefault("denominadores", {})[m] = {"en_lista": len(lst), "evaluados": len(evaluados),
                                                            "excluidos": len(lst) - len(evaluados),
                                                            "precision": acierto / len(evaluados) if evaluados else None}
        resultado["nota"] = ("Compras observadas en el horizonte. No miden el efecto del contacto: un comprador contactado "
                             "no demuestra que el contacto causó la compra.")

    # Registro del piloto: se lee y valida todo antes de escribir.
    salida = Path(salida)
    ruta = salida / "piloto_registro.csv"
    existentes = _leer_registro_piloto(ruta)
    seleccion_id, componentes = identidad_seleccion(corte.isoformat(), r_o, r_s, cohorte, k, reconciliacion)
    resultado["seleccion"] = {"seleccion_id": seleccion_id, **componentes}
    nuevas = {}
    for c in sorted(set(por_o) | set(por_s)):
        fo, fs = por_o.get(c, {}), por_s.get(c, {})
        nuevas[c] = {"corte": corte.isoformat(), "cliente_id": c, "seleccion_id": seleccion_id,
                     "version_operativa": r_o["artefacto"]["version"], "huella_operativa": r_o["artefacto"]["huella"],
                     "version_sombra": r_s["artefacto"]["version"], "huella_sombra": r_s["artefacto"]["huella"],
                     "huella_datos_puntuacion": h_o or "", "posicion_operativa": fo.get("posicion", ""),
                     "prob_operativa": fo.get("probabilidad", ""), "posicion_sombra": fs.get("posicion", ""),
                     "prob_sombra": fs.get("probabilidad", ""), "posicion_recencia": fo.get("posicion_recencia", ""),
                     "en_cupo_operativo": str(c in listas["operativo"]), "en_cupo_sombra": str(c in listas["sombra"]),
                     "en_cupo_recencia": str(c in listas["recencia"]), "fecha_maduracion": resultado["maduran_el"]}
    # Migración verificable de identificadores anteriores ("corte|versión|versión|kN"): solo se reidentifican
    # si TODAS sus filas coinciden con la selección recalculada; si no, quedan como selección aparte.
    antiguo = f"{corte.isoformat()}|{r_o['artefacto']['version']}|{r_s['artefacto']['version']}|k{k}"
    filas_antiguas = [f for f in existentes if f["seleccion_id"] == antiguo]
    migradas = 0
    if filas_antiguas and not any(f["seleccion_id"] == seleccion_id for f in existentes):
        def coincide(f):
            n = nuevas.get(f["cliente_id"])
            return n is not None and all(f.get(c) in ("", None) or str(f[c]) == str(n[c]) for c in CAMPOS_SELECCION)
        if all(coincide(f) for f in filas_antiguas):
            for f in filas_antiguas:
                f["seleccion_id_anterior"], f["seleccion_id"] = antiguo, seleccion_id
            migradas = len(filas_antiguas)
    resultado["seleccion"]["filas_migradas_de_formato_anterior"] = migradas
    otras = {f["seleccion_id"] for f in existentes if f["corte"] == corte.isoformat() and f["seleccion_id"] != seleccion_id}
    existe = any(f["seleccion_id"] == seleccion_id for f in existentes)
    if otras and not existe and not nueva_seleccion:
        con_humanos = sum(1 for f in existentes if f["seleccion_id"] in otras and _tiene_humanos(f))
        raise PilotoError(f"El registro ya contiene otra selección para el corte {corte} ({sorted(otras)}; {con_humanos} filas con "
                          "seguimiento humano). No se reasignan contactos: usa --nueva-seleccion para añadir la nueva selección "
                          "conservando la anterior, o una carpeta de salida distinta.")
    errores = []
    final = []
    usados = set()
    for f in existentes:
        f = dict(f)
        if f["corte"] == corte.isoformat():
            e = etiquetas.get(f["cliente_id"])
            if e is not None and not (e["estado_etiqueta"] != MADURA and f.get("estado_etiqueta") == MADURA):
                # Una etiqueta madura no se pierde porque esta ejecución no tenga datos suficientes.
                f.update({"compra_30d": "" if e["compra_30d"] is None else str(e["compra_30d"]),
                          "estado_etiqueta": e["estado_etiqueta"], "motivo_etiqueta": e["motivo_etiqueta"]})
            if f["seleccion_id"] == seleccion_id and f["cliente_id"] in nuevas:
                n = nuevas[f["cliente_id"]]
                for campo in CAMPOS_SELECCION:
                    if f.get(campo) not in ("", None) and str(f[campo]) != str(n[campo]):
                        errores.append(f"{f['cliente_id']}: {campo} registrado {f[campo]!r} distinto del recalculado {n[campo]!r}")
                    elif f.get(campo) in ("", None):
                        f[campo] = n[campo]  # completa columnas nuevas de filas del formato anterior
                f["en_cohorte_actual"] = str(f["cliente_id"] in etiquetas)
                usados.add(f["cliente_id"])
            elif f["seleccion_id"] == seleccion_id:
                f["en_cohorte_actual"] = "False"  # seguimiento anterior de un cliente que ya no está: se conserva
        final.append(f)
    if errores:
        raise PilotoError("La selección registrada no coincide con la recalculada para la misma clave; no se reasignan contactos ni "
                          "se modifica el registro: " + "; ".join(errores[:10]))
    for c, n in nuevas.items():
        if c in usados:
            continue
        e = etiquetas.get(c, {"compra_30d": None, "estado_etiqueta": "no_aplica", "motivo_etiqueta": "no estimado en la puntuación"})
        final.append(dict(n, **{h: "" for h in CAMPOS_HUMANOS}, compra_30d="" if e["compra_30d"] is None else str(e["compra_30d"]),
                          estado_etiqueta=e["estado_etiqueta"], motivo_etiqueta=e["motivo_etiqueta"],
                          en_cohorte_actual=str(c in etiquetas)))
    texto = _texto_piloto(final)
    resultado["piloto"] = {"filas": len(final), "con_seguimiento_humano": sum(_tiene_humanos(f) for f in final),
                           "seleccion_id": seleccion_id, "selecciones_del_corte": sorted(otras | {seleccion_id})}
    _escribir_texto_atomico(ruta, texto)
    _escribir_texto_atomico(salida / "comparacion.json", json.dumps(resultado, ensure_ascii=False, indent=1, default=str))
    return resultado
