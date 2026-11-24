"""M3 · Experimento de próxima compra (protocolo ``m3-protocolo-v1``): preparar, entrenar, seleccionar, congelar y evaluar.

scikit-survival / numpy solo se importan dentro de las funciones de ajuste y de las métricas de referencia (entorno
analítico opcional). La puntuación y la publicación viven en ``modelos/proxima_compra.py`` (biblioteca estándar).

Integridad (``modelos/ejecucion.py``): ``congelacion.json`` sella configuración, protocolo, datos, referencias,
selección, evidencia de validación y artefactos; el artefacto principal debe ser el candidato elegido. ``evaluar``
verifica todo antes de calcular y publica métricas, predicciones y decisión con ``evaluacion.json`` al final:
recuperable tras una interrupción, idempotente y sin sobrescribir resultados distintos.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import warnings
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
from typing import Any

from .compra import DependenciaEntrenamiento, ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict, sellar
from .proxima_compra import (ANCHO_MAXIMO_VENTANA, CUANTILES, FORMATO, HORIZONTE_DIAS, MODELO_ID, escalon, fotografias,
                             kaplan_meier, ventana)
from .variables import FUNCION, VERSION_PROXIMA, ajustar_transformaciones, aplicar_transformaciones, cortes_mensuales, historial_compras

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "proxima_compra.json"
REGLA_DECISION = "m3-decision-v1"
METRICAS_VERSION = "m3-metricas-v1"
MARCADOR_CONGELACION = "congelacion.json"
MARCADOR_EVALUACION = "evaluacion.json"
ORDEN_BLOQUES = ("ajuste", "validacion", "comprobacion_historica")
LIMITACIONES = [
    "Datos sintéticos de 120 clientes ya inspeccionados en M1 y M2: la comprobación histórica (julio y agosto de 2026) es exploratoria.",
    "Todas las censuras son administrativas (60 días sin compra o fin del seguimiento conocido); no se infiere abandono.",
    "Las fotografías mensuales de un mismo cliente están relacionadas: la incertidumbre se estima remuestreando clientes completos.",
    "El error entre compradores observados no describe a toda la cartera.",
]


def _leer(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def cargar_config(ruta: str | Path | None = None) -> dict:
    return _leer(Path(ruta or CONFIG_DEFECTO))


def identidad_protocolo(config: dict) -> dict:
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": VERSION_PROXIMA, "transformaciones": {v: FUNCION.get(v) for v in config["variables"]},
                       "formato_artefacto": FORMATO, "metricas": METRICAS_VERSION, "regla_decision": REGLA_DECISION,
                       "cuantiles": list(CUANTILES)}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config)).encode()).hexdigest()


# Datos y bloques -------------------------------------------------------------------------------------------
def cortes_bloque(config: dict, bloque: str) -> list[date]:
    a, b = config["bloques"][bloque]["cortes"]
    return cortes_mensuales(_d(a), _d(b))


def preparar(datos: DatosAceptados, config: dict) -> dict:
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    bloques, exclusiones = {}, {}
    for b in ORDEN_BLOQUES:
        hasta = _d(config["bloques"][b]["seguimiento_hasta"])
        bloques[b], exclusiones[b] = fotografias(datos.clientes, historial, cortes_bloque(config, b), hasta, datos.observado_hasta)
    return {"historial": historial, "bloques": bloques, "exclusiones": exclusiones, "fronteras": verificar_fronteras(bloques, config, datos)}


def verificar_fronteras(bloques: dict, config: dict, datos: DatosAceptados) -> dict:
    """POR CÓDIGO: todo fin de seguimiento de un bloque <= su D < primer corte del siguiente; el último D <= cobertura."""
    salida = {}
    for i, b in enumerate(ORDEN_BLOQUES):
        D = _d(config["bloques"][b]["seguimiento_hasta"])
        ultimo_fin = max((_d(f["fin_seguimiento"]) for f in bloques[b]), default=None)
        if ultimo_fin is None or ultimo_fin > D:
            raise ProtocoloError(f"{b}: seguimiento hasta {ultimo_fin}, posterior a su D {D}")
        if i + 1 < len(ORDEN_BLOQUES):
            sig = min(cortes_bloque(config, ORDEN_BLOQUES[i + 1]))
            if D >= sig:
                raise ProtocoloError(f"Fuga temporal: el seguimiento de {b} llega a {D}, no antes del primer corte de {ORDEN_BLOQUES[i + 1]} ({sig})")
            salida[f"{b}->{ORDEN_BLOQUES[i + 1]}"] = {"ultimo_fin_seguimiento": ultimo_fin.isoformat(), "seguimiento_hasta": D.isoformat(),
                                                       "primera_prediccion_siguiente": sig.isoformat()}
        elif datos.observado_hasta is None or D > datos.observado_hasta:
            raise ProtocoloError(f"{b}: el seguimiento hasta {D} supera la cobertura declarada {datos.observado_hasta}")
        else:
            salida[f"{b}->cobertura"] = {"ultimo_fin_seguimiento": ultimo_fin.isoformat(), "seguimiento_hasta": D.isoformat(),
                                         "cobertura_ventas": datos.observado_hasta.isoformat()}
    return salida


def conteos(filas: list[dict], excl: dict) -> dict:
    por_corte = []
    for c in sorted({f["corte"] for f in filas}):
        g = [f for f in filas if f["corte"] == c]
        por_corte.append({"corte": c.isoformat(), "filas": len(g), "eventos": sum(f["evento"] for f in g),
                          "censuras": sum(1 - f["evento"] for f in g), **{f"excluidas_{k}": v for k, v in excl.get(c.isoformat(), {}).items()},
                          "por_grupo": {gr: sum(f["grupo"] == gr for f in g) for gr in ("reciente", "habitual", "ocasional", "frio")}})
    return {"filas": len(filas), "clientes_unicos": len({f["cliente_id"] for f in filas}), "eventos": sum(f["evento"] for f in filas),
            "censuras": sum(1 - f["evento"] for f in filas), "proporcion_censurada": (sum(1 - f["evento"] for f in filas) / len(filas)) if filas else None,
            "exclusiones": {k: sum(e[k] for e in excl.values()) for k in ("alta_posterior", "sin_historial", "seguimiento_cero")},
            "referencia_personal": {k: sum(f["ref_personal_estado"] == k for f in filas) for k in ("disponible", "vencida", "insuficiente")},
            "por_grupo": {gr: sum(f["grupo"] == gr for f in filas) for gr in ("reciente", "habitual", "ocasional", "frio")},
            "por_corte": por_corte}


# Artefactos --------------------------------------------------------------------------------------------------
def _comunes(config: dict, datos: DatosAceptados, aj: list[dict], tipo: str, descripcion: str) -> dict:
    return {"formato": FORMATO, "modelo_id": MODELO_ID, "version": "pendiente", "version_variables": VERSION_PROXIMA, "tipo": tipo,
            "descripcion": descripcion, "horizonte_dias": HORIZONTE_DIAS, "soporte_dias": max(f["duracion"] for f in aj), "umbral": None,
            "cuantiles": list(CUANTILES), "ancho_maximo_ventana_dias": config["ventana"]["ancho_maximo_dias"],
            "disponible_desde": config["disponible_desde"], "origen_datos": config["origen_datos"], "version_protocolo": config["version_protocolo"],
            "entrenamiento": {"cortes": sorted({f["corte"].isoformat() for f in aj}), "filas": len(aj), "eventos": sum(f["evento"] for f in aj),
                              "seguimiento_hasta": config["bloques"]["ajuste"]["seguimiento_hasta"], "huella_datos": datos.huella_datos,
                              "revision_datos": datos.revision}}


def _versionar(d: dict, cid: str) -> dict:
    d["version"] = f"proxima_compra-m3-{cid}-" + sellar(d)["huella"][:8]
    return sellar(d)


def artefacto_km(aj: list[dict], config: dict, datos: DatosAceptados) -> dict:
    t, s = kaplan_meier([f["duracion"] for f in aj], [f["evento"] for f in aj])
    d = _comunes(config, datos, aj, "km", "Kaplan-Meier global de tiempos residuales desde el corte (con censura); igual para todos los clientes.")
    d["km"] = {"tiempos": t, "supervivencia": s}
    return _versionar(d, "km")


def ajustar_cox(aj: list[dict], variables: list[str], alpha: float, config: dict):
    try:
        import numpy as np
        from sksurv.linear_model import CoxPHSurvivalAnalysis
        from sksurv.util import Surv
    except ImportError as exc:
        raise DependenciaEntrenamiento("M3 requiere el entorno analítico: pip install scikit-survival==0.26.0 (ver requirements-modelos.txt)") from exc
    trans = ajustar_transformaciones(aj, variables)
    X = np.array([aplicar_transformaciones(f, trans) for f in aj], dtype=float)
    y = Surv.from_arrays(event=[bool(f["evento"]) for f in aj], time=[float(f["duracion"]) for f in aj])
    c = config["candidato"]
    m = CoxPHSurvivalAnalysis(alpha=alpha, ties=c["ties"], n_iter=c["n_iter"], tol=c["tol"])
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        m.fit(X, y)
    if not np.all(np.isfinite(m.coef_)):
        raise ValueError(f"Cox alpha={alpha}: coeficientes no finitos")
    return m, trans, [str(a.message) for a in avisos]


def artefacto_cox(m, trans, variables: list[str], alpha: float, aj: list[dict], config: dict, datos: DatosAceptados, avisos: list[str]) -> dict:
    base = m.cum_baseline_hazard_
    tiempos = [int(round(x)) for x in base.x]
    if any(abs(x - round(x)) > 1e-9 for x in base.x):
        raise ValueError("tiempos base no enteros")
    d = _comunes(config, datos, aj, "cox", f"Cox L2 (alpha={alpha}, empates de Breslow) sobre tiempos residuales; curva base de Breslow.")
    d["cox"] = {"variables": list(variables), "transformaciones": trans, "coeficientes": [float(w) for w in m.coef_],
                "tiempos_base": tiempos, "riesgo_acumulado_base": [float(h) for h in base.y], "alpha": alpha,
                "penalizacion": "scikit-survival 0.26: pérdida media + sum(alpha·w²)/(2n) ≡ log-verosimilitud parcial total + alpha·||w||²/2",
                "ties": config["candidato"]["ties"], "avisos_ajuste": avisos}
    return _versionar(d, f"cox-a{str(alpha).replace('.', '_')}")


def equivalencia(m, trans, art, filas: list[dict]) -> dict:
    """Curva de scikit-survival frente al artefacto recargado desde JSON, en todas las filas y tiempos base."""
    import numpy as np
    X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
    sk = m.predict_survival_function(X, return_array=True)
    tiempos = list(m.unique_times_)
    dif = max(abs(sk[i, j] - art.supervivencia(f, t)) for i, f in enumerate(filas) for j, t in enumerate(tiempos))
    lp = max(abs(float(a) - art.predictor_lineal(f)) for a, f in zip(m.predict(X), filas))
    return {"diferencia_maxima_supervivencia": float(dif), "diferencia_maxima_predictor": lp, "filas": len(filas), "tiempos": len(tiempos)}


# Métricas con censura ---------------------------------------------------------------------------------------
def censura_ajuste(aj: list[dict]) -> tuple[list[int], list[float]]:
    """G(t): Kaplan-Meier de la censura en el ajuste con la convención de scikit-survival (``reverse=True``): en un
    empate, las compras salen del riesgo ANTES que las censuras (en riesgo = n(>= t) − compras en t)."""
    tiempos = sorted({f["duracion"] for f in aj})
    g, ts, vs = 1.0, [], []
    for t in tiempos:
        en_riesgo = sum(f["duracion"] >= t for f in aj) - sum(f["duracion"] == t and f["evento"] for f in aj)
        cens = sum(f["duracion"] == t and not f["evento"] for f in aj)
        if cens and en_riesgo > 0:
            g *= 1 - cens / en_riesgo
            ts.append(t)
            vs.append(g)
    return ts, vs


def rejilla(aj: list[dict], prueba: list[dict], config: dict) -> dict:
    G = censura_ajuste(aj)
    lo = max(1, min(f["duracion"] for f in prueba))
    hi = min(HORIZONTE_DIAS - 1, max(f["duracion"] for f in prueba) - 1, max(f["duracion"] for f in aj) - 1)
    puntos = [t for t in range(lo, hi + 1) if escalon(t, *G, 1.0) > 0]
    estimable = len(puntos) >= config["rejilla_metrica"]["minimo_puntos"] and puntos == list(range(lo, hi + 1))
    return {"desde": lo, "hasta": hi, "puntos": puntos, "estimable": estimable,
            "nota": f"Brier integrado sobre los días {lo}–{hi} (no es una evaluación completa a {HORIZONTE_DIAS} días)" if estimable
                    else "Soporte insuficiente: métrica no estimable"}


def brier_ipcw(G, filas: list[dict], S: list[list[float]], puntos: list[int]) -> list[float]:
    """Brier por tiempo con pesos de censura del ajuste (misma fórmula que sksurv.metrics.brier_score)."""
    gT = [escalon(f["duracion"], *G, 1.0) for f in filas]
    salida = []
    for j, t in enumerate(puntos):
        gt = escalon(t, *G, 1.0)
        tot = 0.0
        for i, f in enumerate(filas):
            s = S[i][j]
            if f["duracion"] <= t and f["evento"]:
                tot += s * s / gT[i] if gT[i] > 0 else math.inf
            elif f["duracion"] > t:
                tot += (1 - s) ** 2 / gt if gt > 0 else math.inf
        salida.append(tot / len(filas))
    return salida


def integrar(puntos: list[int], valores: list[float]) -> float:
    area = sum((puntos[i + 1] - puntos[i]) * (valores[i] + valores[i + 1]) / 2 for i in range(len(puntos) - 1))
    return area / (puntos[-1] - puntos[0])


def ibs(G, filas, S, puntos) -> float:
    return integrar(puntos, brier_ipcw(G, filas, S, puntos))


def matriz(art, filas: list[dict], puntos: list[int]) -> list[list[float]]:
    return [[art.supervivencia(f, t) for t in puntos] for f in filas]


def ibs_referencia(aj, prueba, S, puntos) -> float:
    """Brier integrado de scikit-survival (implementación de referencia) para contrastar ``ibs``."""
    import numpy as np
    from sksurv.metrics import integrated_brier_score
    from sksurv.util import Surv
    ytr = Surv.from_arrays([bool(f["evento"]) for f in aj], [float(f["duracion"]) for f in aj])
    yte = Surv.from_arrays([bool(f["evento"]) for f in prueba], [float(f["duracion"]) for f in prueba])
    return float(integrated_brier_score(ytr, yte, np.array(S), np.array(puntos, dtype=float)))


def concordancia(aj, prueba, riesgo: list[float], tau: int) -> float | None:
    import numpy as np
    from sksurv.metrics import concordance_index_ipcw
    from sksurv.util import Surv
    if len(prueba) < 2 or not any(f["evento"] for f in prueba):
        return None
    ytr = Surv.from_arrays([bool(f["evento"]) for f in aj], [float(f["duracion"]) for f in aj])
    yte = Surv.from_arrays([bool(f["evento"]) for f in prueba], [float(f["duracion"]) for f in prueba])
    return float(concordance_index_ipcw(ytr, yte, np.array(riesgo, dtype=float), tau=float(tau))[0])


def config_ventana(art) -> tuple[tuple, int]:
    """Límites y ancho máximo de la ventana del artefacto (M3: p10–p90; M3.1 lo declara en ``ventana``)."""
    v = art.datos.get("ventana")
    return (tuple(v["limites"]), v["ancho_maximo_dias"]) if v else (("p10", "p90"), art.datos["ancho_maximo_ventana_dias"])


def ventanas_de(art, filas: list[dict]) -> list[dict]:
    limites, ancho = config_ventana(art)
    return [dict(ventana(art.curva(f), f["corte"], ancho, limites), _limites=limites) for f in filas]


def resultado_ventana(f: dict, w: dict) -> str:
    """dentro | antes | despues | indeterminado | sin_ventana. Un censurado después de p90 está fuera (se sabe que T > p90)."""
    lo_n, hi_n = w.get("_limites", ("p10", "p90"))
    p10, p90 = w[f"dias_{lo_n}"], w[f"dias_{hi_n}"]
    if p10 is None or p90 is None:
        return "sin_ventana"
    if f["evento"]:
        return "antes" if f["duracion"] < p10 else "despues" if f["duracion"] > p90 else "dentro"
    return "despues" if f["duracion"] >= p90 else "indeterminado"  # censurado en c >= p90: se sabe que T > c >= p90


def medir(art, aj, prueba, puntos, corte_ref: date | None = None) -> dict:
    """Métricas de un artefacto en un bloque (todas las filas, sin eliminar casos)."""
    S = matriz(art, prueba, puntos)
    G = censura_ajuste(aj)
    bs = brier_ipcw(G, prueba, S, puntos)
    ws = ventanas_de(art, prueba)
    res = [resultado_ventana(f, w) for f, w in zip(prueba, ws)]
    det = [r for r in res if r in ("dentro", "antes", "despues")]
    eventos = [(f, w) for f, w in zip(prueba, ws) if f["evento"] and w["dias_p50"] is not None]
    comun = [(f, w) for f, w in zip(prueba, ws) if f["evento"] and w["dias_p50"] is not None and f["ref_personal_estado"] == "disponible"]
    anchos = [w["ancho_ventana_dias"] for w in ws if w["ancho_ventana_dias"] is not None]
    return {"ibs": integrar(puntos, bs), "brier_por_tiempo": {str(t): b for t, b in zip(puntos, bs)},
            "cobertura_cuantiles": {n: sum(w[f"dias_{n}"] is not None for w in ws) / len(ws) for n in ("p10", "p50", "p90")},
            "ventanas": {"con_ventana": sum(w["ancho_ventana_dias"] is not None for w in ws), "utilizables": sum(w["ventana_utilizable"] for w in ws),
                         "proporcion_utilizables_elegibles": sum(w["ventana_utilizable"] for w in ws) / len(ws),
                         "ancho_mediano": median(anchos) if anchos else None, "denominador_elegibles": len(ws)},
            "cobertura_p10_p90": {"dentro": res.count("dentro"), "antes": res.count("antes"), "despues": res.count("despues"),
                                  "indeterminado": res.count("indeterminado"), "sin_ventana": res.count("sin_ventana"),
                                  "determinados": len(det), "cobertura": res.count("dentro") / len(det) if det else None},
            "error_mediano_eventos": {"n": len(eventos), "dias": median(abs(w["dias_p50"] - f["duracion"]) for f, w in eventos) if eventos else None,
                                      "nota": "solo compradores observados con p50 disponible; no describe a toda la cartera"},
            "comparacion_personal": {"n_comun": len(comun),
                                     "candidato_dias": median(abs(w["dias_p50"] - f["duracion"]) for f, w in comun) if comun else None,
                                     "personal_dias": median(abs(f["ref_personal_dias"] - f["duracion"]) for f, _ in comun) if comun else None,
                                     "subconjunto": "eventos observados con p50 del candidato y referencia personal disponible (> 0)"},
            "_ventanas": ws, "_resultados": res, "_S": S}


def bootstrap(prueba: list[dict], G, puntos, S_c, S_k, res_c, B: int, semilla: int) -> dict:
    """Remuestreo de clientes completos: diferencia de IBS (candidato − KM) y cobertura p10–p90 del candidato."""
    por_cliente: dict[str, list[int]] = {}
    for i, f in enumerate(prueba):
        por_cliente.setdefault(f["cliente_id"], []).append(i)
    ids = sorted(por_cliente)
    rng = random.Random(semilla)
    difs, covs = [], []
    for _ in range(B):
        idx = [i for c in (rng.choice(ids) for _ in ids) for i in por_cliente[c]]
        filas = [prueba[i] for i in idx]
        difs.append(ibs(G, filas, [S_c[i] for i in idx], puntos) - ibs(G, filas, [S_k[i] for i in idx], puntos))
        det = [res_c[i] for i in idx if res_c[i] in ("dentro", "antes", "despues")]
        if det:
            covs.append(det.count("dentro") / len(det))

    def ic(v):
        v = sorted(x for x in v if math.isfinite(x))
        return {"p2_5": v[int(0.025 * (len(v) - 1))], "p97_5": v[int(math.ceil(0.975 * (len(v) - 1)))], "n": len(v)} if v else {}
    return {"ibs_candidato_menos_km": ic(difs), "cobertura_p10_p90": ic(covs), "repeticiones": B, "unidad": "cliente completo"}


def _publico(m: dict) -> dict:
    return {k: v for k, v in m.items() if not k.startswith("_")}


def _por_grupo_y_corte(art, prueba, G, puntos) -> dict:
    out = {}
    for clave, valor in [("corte", c) for c in sorted({f["corte"] for f in prueba})] + [("grupo", g) for g in ("reciente", "habitual", "ocasional", "frio")]:
        sub = [f for f in prueba if f[clave] == valor]
        if not sub:
            continue
        ws = ventanas_de(art, sub)
        res = [resultado_ventana(f, w) for f, w in zip(sub, ws)]
        det = [r for r in res if r in ("dentro", "antes", "despues")]
        out[f"{clave}={valor.isoformat() if hasattr(valor, 'isoformat') else valor}"] = {
            "filas": len(sub), "eventos": sum(f["evento"] for f in sub), "censuras": sum(1 - f["evento"] for f in sub),
            "ibs": ibs(G, sub, matriz(art, sub, puntos), puntos),
            "ventanas_utilizables": sum(w["ventana_utilizable"] for w in ws),
            "cobertura_p10_p90": {"dentro": det.count("dentro"), "determinados": len(det)}}
    return out


# Entrenamiento -------------------------------------------------------------------------------------------------
def fechas_piloto(hoy: date) -> dict:
    from .variables import fin_de_mes
    fin = fin_de_mes(hoy.year, hoy.month)
    primer = fin if fin > hoy else fin_de_mes(hoy.year + (hoy.month == 12), 1 if hoy.month == 12 else hoy.month + 1)
    return {"congelacion_real": hoy.isoformat(), "primer_corte_prospectivo": primer.isoformat(), "cobertura_requerida_para_puntuar": primer.isoformat(),
            "seguimiento_completo_desde": (primer + timedelta(days=HORIZONTE_DIAS)).isoformat(),
            "nota": "fechas calculadas desde la ejecución real; la comprobación de julio y agosto de 2026 es retrospectiva"}


def _estabilidad(aj, variables, alpha, config, completo) -> dict:
    import numpy as np
    from sksurv.linear_model import CoxPHSurvivalAnalysis
    from sksurv.util import Surv
    por_cliente: dict[str, list[dict]] = {}
    for f in aj:
        por_cliente.setdefault(f["cliente_id"], []).append(f)
    ids = sorted(por_cliente)
    rng = random.Random(config["candidato"]["semilla"])
    coefs = []
    for _ in range(config["candidato"]["estabilidad_bootstrap"]):
        filas = [f for c in (rng.choice(ids) for _ in ids) for f in por_cliente[c]]
        trans = ajustar_transformaciones(filas, variables)
        X = np.array([aplicar_transformaciones(f, trans) for f in filas], dtype=float)
        y = Surv.from_arrays([bool(f["evento"]) for f in filas], [float(f["duracion"]) for f in filas])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m = CoxPHSurvivalAnalysis(alpha=alpha, ties=config["candidato"]["ties"], n_iter=config["candidato"]["n_iter"], tol=config["candidato"]["tol"]).fit(X, y)
        coefs.append([float(w) for w in m.coef_])
    out = {}
    for j, v in enumerate(variables):
        col = [c[j] for c in coefs]
        mu = sum(col) / len(col)
        out[v] = {"completo": completo[j], "media_bootstrap": mu, "desviacion_bootstrap": (sum((x - mu) ** 2 for x in col) / len(col)) ** 0.5,
                  "mismo_signo": sum((x > 0) == (completo[j] > 0) for x in col) / len(col)}
    return {"repeticiones": len(coefs), "por_variable": out, "nota": "remuestreo de clientes completos del bloque de ajuste"}


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID:
        raise ProtocoloError(f"La configuración es de {config.get('modelo_id')!r}, no de {MODELO_ID}")
    if (salida / "config.json").exists() and canon(_leer(salida / "config.json")) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    ds = preparar(datos, config)
    aj, va = ds["bloques"]["ajuste"], ds["bloques"]["validacion"]
    if not aj or not any(f["evento"] for f in aj):
        raise ProtocoloError("El bloque de ajuste no tiene eventos: no se puede estimar ninguna curva")
    km_d = artefacto_km(aj, config, datos)
    km = desde_dict(json.loads(json.dumps(km_d)))
    malla = rejilla(aj, va, config)
    candidatos = {"km": {"tipo": "km", "alpha": None, "artefacto": km_d}}
    diagnostico, val = {}, {}
    variables = config["variables"]
    for alpha in config["candidato"]["alpha"]:
        cid = f"cox-a{str(alpha).replace('.', '_')}"
        try:
            m, trans, avisos = ajustar_cox(aj, variables, alpha, config)
        except (ValueError, ArithmeticError, np_error()) as exc:  # problema numérico: se registra y se descarta
            diagnostico[cid] = {"ajustado": False, "error": str(exc)}
            continue
        art_d = artefacto_cox(m, trans, variables, alpha, aj, config, datos, avisos)
        art = desde_dict(json.loads(json.dumps(art_d)))
        eq = equivalencia(m, trans, art, aj[:200] + va)
        if eq["diferencia_maxima_supervivencia"] > config["tolerancia_equivalencia"]:
            raise ValueError(f"{cid}: la curva del artefacto recargado difiere de scikit-survival en {eq['diferencia_maxima_supervivencia']:g}")
        diagnostico[cid] = {"ajustado": True, "avisos": avisos, "convergencia": not any("converge" in a.lower() for a in avisos),
                            "coeficientes": dict(zip(variables, art_d["cox"]["coeficientes"])), "equivalencia_json_sksurv": eq,
                            "estabilidad": _estabilidad(aj, variables, alpha, config, art_d["cox"]["coeficientes"])}
        candidatos[cid] = {"tipo": "cox", "alpha": alpha, "artefacto": art_d}
    referencia_sksurv = None
    for cid, c in candidatos.items():
        art = desde_dict(json.loads(json.dumps(c["artefacto"])))
        if malla["estimable"]:
            mm = medir(art, aj, va, malla["puntos"])
            val[cid] = _publico(mm)
            if cid == "km":
                referencia_sksurv = {"ibs_propio": mm["ibs"], "ibs_sksurv": ibs_referencia(aj, va, mm["_S"], malla["puntos"])}
                referencia_sksurv["diferencia"] = abs(referencia_sksurv["ibs_propio"] - referencia_sksurv["ibs_sksurv"])
    tol = config["seleccion"]["tolerancia"]
    elegido, motivo = "km", "Sin rejilla estimable en validación: se conserva Kaplan-Meier"
    if malla["estimable"]:
        cox = [c for c in candidatos if c != "km"]
        mejor = sorted(cox, key=lambda c: (round(val[c]["ibs"] / tol), -candidatos[c]["alpha"]))[0] if cox else None
        if mejor and val[mejor]["ibs"] < val["km"]["ibs"] - tol:
            elegido, motivo = mejor, f"{mejor} tiene el menor Brier integrado de validación y mejora a Kaplan-Meier"
        else:
            motivo = "Ningún Cox mejora el Brier integrado de Kaplan-Meier en validación: se conserva Kaplan-Meier"
    seleccion = {"criterio": config["seleccion"], "rejilla_validacion": malla, "elegido": elegido, "motivo": motivo,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"],
                 "candidatos": {cid: {"tipo": c["tipo"], "alpha": c["alpha"], "artefacto_huella": c["artefacto"]["huella"],
                                      "artefacto_version": c["artefacto"]["version"], "validacion": val.get(cid)}
                                for cid, c in candidatos.items()},
                 "diagnostico_cox": diagnostico, "contraste_ibs_sksurv": referencia_sksurv,
                 "nota": "Parámetros ajustados solo con el bloque de ajuste (seguimiento hasta su D); no se reajusta con validación ni prueba."}
    archivos = {f"candidatos/{cid}.json": json_bytes(c["artefacto"]) for cid, c in candidatos.items()}
    archivos["artefacto.json"] = json_bytes(candidatos[elegido]["artefacto"])
    archivos["referencia_km.json"] = json_bytes(km_d)
    archivos["config.json"] = json_bytes(config)
    archivos["protocolo.json"] = json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config)})
    archivos["datos.json"] = json_bytes(dict(datos.descripcion(), fronteras_verificadas=ds["fronteras"],
                                             conteos_por_bloque={b: conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in ORDEN_BLOQUES},
                                             fuentes={"ventas": {"uso": "variables (<= C) y seguimiento (<= D de cada bloque)", **datos.cobertura.como_dict()},
                                                      "clientes": "elegibilidad por fecha_alta <= C", "trm": "importe_cop_90d con la TRM de cada venta",
                                                      "no_usadas": ["base_instalada", "productos (catálogo)", "compras a proveedores"]}))
    archivos["seleccion.json"] = json_bytes(seleccion)
    archivos["predicciones_validacion.csv"] = _csv_filas(va, {cid: desde_dict(json.loads(json.dumps(c["artefacto"]))) for cid, c in candidatos.items()}, "validacion")
    archivos["entorno.json"] = json_bytes(entorno_m3())
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"],
            "seleccion_elegido": elegido, "referencia_km_huella": km_d["huella"], "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica"}
    marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta,
                             volatiles={"fechas_piloto": fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": {b: conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in ORDEN_BLOQUES},
            "fronteras": ds["fronteras"]}


def np_error():
    try:
        import numpy as np
        return np.linalg.LinAlgError
    except ImportError:  # pragma: no cover
        return ArithmeticError


def entorno_m3() -> dict:
    e = entorno()
    try:
        import sksurv
        e["scikit_survival"] = sksurv.__version__
    except ImportError:
        e["scikit_survival"] = None
    return e


def _csv_filas(filas: list[dict], arts: dict, bloque: str) -> bytes:
    buf = io.StringIO()
    cols = ["cliente_id", "corte", "bloque", "grupo", "recencia_dias", "evento", "duracion", "fin_seguimiento", "ref_personal_estado", "ref_personal_dias"]
    cols += [f"{cid}_{n}" for cid in arts for n in ("p10", "p50", "p90")]
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
    w.writeheader()
    for f in filas:
        fila = {k: (f[k].isoformat() if hasattr(f.get(k), "isoformat") else f.get(k)) for k in cols[:10] if k != "bloque"} | {"bloque": bloque}
        for cid, art in arts.items():
            v = ventana(art.curva(f), f["corte"])
            fila |= {f"{cid}_{n}": v[f"dias_{n}"] for n in ("p10", "p50", "p90")}
        w.writerow(fila)
    return buf.getvalue().encode("utf-8")


# Evaluación ------------------------------------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    config = _leer(ejecucion / "config.json")
    if huella_protocolo(config) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    sel = _leer(ejecucion / "seleccion.json")
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    cand = cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    if not (art.huella == cand.huella == cong["artefacto_huella"]) or km.huella != cong["referencia_km_huella"]:
        raise ProtocoloError("artefacto.json o referencia_km.json no son los congelados.")
    return cong


def decidir(c: dict, k: dict, boot: dict, cont: dict, malla: dict, elegido: str, config: dict) -> dict:
    metas, mins = config["metas"], config["minimos_evidencia"]
    if not malla["estimable"]:
        return {"decision": "inconcluso", "estado_maximo": "sombra", "motivos": ["Brier integrado no estimable con el soporte de prueba"], "cumple": {}}
    ev_corte = [m["eventos"] for m in cont["por_corte"]]
    det = c["cobertura_p10_p90"]["determinados"]
    cp = c["comparacion_personal"]
    ic_d, ic_c = boot.get("ibs_candidato_menos_km", {}), boot.get("cobertura_p10_p90", {})
    red = (k["ibs"] - c["ibs"]) / k["ibs"] if k["ibs"] else None
    cumple = {"minimos_evidencia": cont["filas"] >= mins["filas"] and cont["eventos"] >= mins["eventos"] and min(ev_corte) >= mins["eventos_por_corte"]
                                   and len(malla["puntos"]) >= mins["puntos_rejilla"],
              "reduccion_ibs_5pct": red is not None and red >= metas["reduccion_relativa_ibs_vs_km"] - 1e-12,
              "ic95_ibs_bajo_cero": bool(ic_d) and ic_d["p97_5"] < 0,
              "error_no_peor_que_personal": cp["n_comun"] >= mins["eventos_comunes_personal"] and cp["candidato_dias"] <= cp["personal_dias"],
              "ventanas_utilizables_50pct": c["ventanas"]["proporcion_utilizables_elegibles"] >= metas["proporcion_ventanas_utilizables_elegibles"],
              "cobertura_80_compatible": det >= mins["ventanas_determinadas"] and bool(ic_c) and ic_c["p97_5"] >= metas["cobertura_nominal"]}
    motivos = []
    if elegido == "km":
        motivos.append("Cox no mejoró a Kaplan-Meier en validación: el artefacto principal es la referencia poblacional (no hay candidato que comparar).")
    if all(cumple.values()) and elegido != "km":
        decision = "favorable"
        motivos.append("Cumple todas las metas predeclaradas en la comprobación exploratoria; con datos sintéticos solo habilita sombra.")
    elif (ic_d and ic_d["p2_5"] > 0 and elegido != "km") or (cumple["minimos_evidencia"] and det >= mins["ventanas_determinadas"] and ic_c and ic_c["p97_5"] < metas["cobertura_nominal"]):
        decision = "rechazado"
        if ic_d and ic_d["p2_5"] > 0 and elegido != "km":
            motivos.append("El IC 95 % de (IBS candidato − IBS Kaplan-Meier) está entero por encima de 0.")
        if ic_c and ic_c["p97_5"] < metas["cobertura_nominal"]:
            motivos.append("El IC 95 % de la cobertura p10–p90 está entero por debajo del 80 % nominal.")
    else:
        decision = "inconcluso"
        motivos += [f"No cumple: {k_}" for k_, v in cumple.items() if not v]
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "cumple": cumple, "motivos": motivos,
            "valores": {"ibs_candidato": c["ibs"], "ibs_km": k["ibs"], "reduccion_relativa": red, "ic95_ibs_candidato_menos_km": [ic_d.get("p2_5"), ic_d.get("p97_5")],
                        "error_mediano_candidato": cp["candidato_dias"], "error_mediano_personal": cp["personal_dias"], "n_comun": cp["n_comun"],
                        "proporcion_ventanas_utilizables": c["ventanas"]["proporcion_utilizables_elegibles"],
                        "cobertura_p10_p90": c["cobertura_p10_p90"]["cobertura"], "ic95_cobertura": [ic_c.get("p2_5"), ic_c.get("p97_5")],
                        "ventanas_determinadas": det, "rejilla": [malla["desde"], malla["hasta"]]}}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config, info, sel = _leer(ejecucion / "config.json"), _leer(ejecucion / "datos.json"), _leer(ejecucion / "seleccion.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = preparar(datos, config)
    aj, pr = ds["bloques"]["ajuste"], ds["bloques"]["comprobacion_historica"]
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    malla = rejilla(aj, pr, config)
    G = censura_ajuste(aj)
    cont = conteos(pr, ds["exclusiones"]["comprobacion_historica"])
    resultados: dict[str, Any] = {"conteos": cont, "rejilla": malla}
    boot = {}
    if malla["estimable"]:
        mc, mk = medir(art, aj, pr, malla["puntos"]), medir(km, aj, pr, malla["puntos"])
        tau = malla["hasta"]
        mc["concordancia_ipcw"] = concordancia(aj, pr, [art.predictor_lineal(f) for f in pr], tau)
        mk["concordancia_ipcw"] = concordancia(aj, pr, [0.0] * len(pr), tau)
        sub = [f for f in pr if f["ref_personal_estado"] in ("disponible", "vencida")]
        resultados["referencia_personal"] = {
            "n": len(sub), "concordancia_ipcw_subconjunto": concordancia(aj, sub, [-float(f["ref_personal_dias"]) for f in sub], tau),
            "concordancia_candidato_subconjunto": concordancia(aj, sub, [art.predictor_lineal(f) for f in sub], tau),
            "vencidas": sum(f["ref_personal_estado"] == "vencida" for f in pr), "insuficientes": sum(f["ref_personal_estado"] == "insuficiente" for f in pr)}
        b = config["metricas"]["bootstrap"]
        boot = bootstrap(pr, G, malla["puntos"], mc["_S"], mk["_S"], mc["_resultados"], b["repeticiones"], b["semilla"])
        resultados["contraste_ibs_sksurv"] = {"candidato": abs(mc["ibs"] - ibs_referencia(aj, pr, mc["_S"], malla["puntos"])),
                                              "km": abs(mk["ibs"] - ibs_referencia(aj, pr, mk["_S"], malla["puntos"]))}
        resultados["candidato"], resultados["km"] = _publico(mc), _publico(mk)
        resultados["por_corte_y_grupo"] = {"candidato": _por_grupo_y_corte(art, pr, G, malla["puntos"]), "km": _por_grupo_y_corte(km, pr, G, malla["puntos"])}
        decision = decidir(mc, mk, boot, cont, malla, cong["seleccion_elegido"], config)
    else:
        decision = decidir({}, {}, {}, cont, malla, cong["seleccion_elegido"], config)
    metricas = {"bloque": "comprobacion_historica", "alcance": "comprobación histórica EXPLORATORIA (datos sintéticos ya inspeccionados)",
                "artefacto": {"version": art.version, "huella": art.huella, "tipo": art.tipo}, "referencia_km": {"version": km.version, "huella": km.huella},
                "resultados": resultados, "incertidumbre_bootstrap_clientes": boot, "limitaciones": LIMITACIONES}
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"],
               candidato=cong["seleccion_elegido"], version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"],
               sello_congelacion=cong["sello"], origen_datos=config["origen_datos"], alcance=metricas["alcance"],
               limitaciones=LIMITACIONES + ["Ningún modelo se promueve automáticamente; no se activan recordatorios."])
    arts = {"candidato": art, "km": km}
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas), "predicciones_comprobacion.csv": _csv_filas(pr, arts, "comprobacion_historica"),
                "decision.json": json_bytes(doc)}
    marcador = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"]})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": _leer(ejecucion / "decision.json")}
