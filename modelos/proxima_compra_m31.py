"""M3.1 · Próxima compra con ventana de inicio probable (p10–p50), probabilidad acumulada y Cox estratificado por grupo.

Protocolo ``m31-protocolo-v1`` (``modelos/config/proxima_compra_m31.json``). Reutiliza de M3 (``proxima_compra_experimento``)
los datos con censura, las fronteras, la rejilla, el Brier integrado IPCW, la concordancia, el remuestreo por cliente y
la publicación sellada. Lo nuevo:

* Candidatos: Kaplan–Meier global (referencia), Cox L2 sin estratos (como M3) y Cox L2 ESTRATIFICADO por grupo
  (coeficientes comunes, curva base de Breslow por grupo) con el ritmo relativo ``ratio_recencia_ciclo``.
* El Cox estratificado se ajusta aquí (scikit-survival no admite estratos) maximizando la verosimilitud parcial
  estratificada con empates de Breslow y penalización ``alpha·||w||²/2`` sobre la log-verosimilitud TOTAL, la misma
  semántica que ``CoxPHSurvivalAnalysis``; con un único estrato reproduce sus coeficientes y su curva base (se comprueba).
* Artefactos con ``ventana = {limites: [p10, p50], ancho_maximo_dias: 30}`` y ``probabilidades_acumuladas_dias``.
* Metas: además de las de M3, cobertura nominal del 40 % de p10–p50 y calibración de la probabilidad acumulada.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from . import proxima_compra_experimento as M3
from .compra import DependenciaEntrenamiento, ProtocoloError, _sin_descriptivas
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict
from .proxima_compra import FORMATO, GRUPOS, MODELO_ID, grupo, kaplan_meier, escalon
from .variables import FUNCION, VERSION_PROXIMA, ajustar_transformaciones, aplicar_transformaciones

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "proxima_compra_m31.json"
REGLA_DECISION = "m31-decision-v1"
METRICAS_VERSION = "m31-metricas-v1"
MARCADOR_CONGELACION, MARCADOR_EVALUACION = "congelacion.json", "evaluacion.json"
LIMITACIONES = M3.LIMITACIONES + [
    "M3.1 se diseñó después de conocer los resultados de M3 en validación y comprobación: la comprobación es exploratoria y REUTILIZADA.",
    "La ventana p10–p50 indica el inicio probable de la próxima compra; no cubre el 80 % central y casi la mitad de las compras caen después.",
]


def cargar_config(ruta: str | Path | None = None) -> dict:
    return json.loads(Path(ruta or CONFIG_DEFECTO).read_text(encoding="utf-8"))


def es_m31(config: dict) -> bool:
    return str(config.get("version_protocolo", "")).startswith("m31-")


def identidad_protocolo(config: dict) -> dict:
    vs = sorted(set(config["variables"]) | set(config["variables_m31"]))
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": VERSION_PROXIMA, "transformaciones": {v: FUNCION.get(v) for v in vs}, "formato_artefacto": FORMATO,
                       "metricas": METRICAS_VERSION, "regla_decision": REGLA_DECISION, "grupos": list(GRUPOS)}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config)).encode()).hexdigest()


# Cox estratificado ------------------------------------------------------------------------------------------
def _np():
    try:
        import numpy as np
        from scipy.optimize import minimize
        return np, minimize
    except ImportError as exc:
        raise DependenciaEntrenamiento("M3.1 requiere el entorno analítico (numpy, scipy): pip install -r requirements-modelos.txt") from exc


def _riesgos(np, eta, tiempos, estratos):
    """Por estrato: S0(t) y S1(t) en el conjunto en riesgo {j: t_j >= t} (empates de Breslow)."""
    out = []
    for g in sorted(set(estratos)):
        idx = np.where(estratos == g)[0]
        o = idx[np.argsort(-tiempos[idx], kind="mergesort")]
        out.append((g, o))
    return out


def ajustar_cox_estratificado(X, tiempos, eventos, estratos, alpha: float, config: dict) -> dict:
    """Coeficientes que minimizan −log VP estratificada (Breslow) + alpha·||w||²/2 y curva base de Breslow por estrato."""
    np, minimize = _np()
    X, t, e, s = (np.asarray(X, dtype=float), np.asarray(tiempos, dtype=float), np.asarray(eventos, dtype=bool), np.asarray(estratos))
    ordenes = _riesgos(np, None, t, s)

    def objetivo(w):
        eta = X @ w
        r = np.exp(eta)
        ll, grad = 0.0, np.zeros_like(w)
        for _, o in ordenes:
            to, ro, Xo, eo = t[o], r[o], X[o], e[o]
            cs0 = np.cumsum(ro)
            cs1 = np.cumsum(ro[:, None] * Xo, axis=0)
            # último índice (en orden descendente) de cada tiempo: el conjunto en riesgo incluye todos los empatados
            ultimo = np.searchsorted(-to, -to, side="right") - 1
            s0, s1 = cs0[ultimo], cs1[ultimo]
            ll += np.sum((eta[o] - np.log(s0))[eo])
            grad += np.sum((Xo - s1 / s0[:, None])[eo], axis=0)
        return -ll + alpha * w @ w / 2, -grad + alpha * w

    a = config["ajuste_numerico"]
    res = minimize(objetivo, np.zeros(X.shape[1]), jac=True, method="L-BFGS-B", options={"gtol": a["gtol"], "ftol": 1e-15, "maxiter": a["max_iter"], "maxls": 50})
    w = res.x
    if not np.all(np.isfinite(w)):
        raise ValueError("coeficientes no finitos")
    eta = X @ w
    r = np.exp(eta)
    bases = {}
    for g, o in ordenes:
        to, ro, eo = t[o], r[o], e[o]
        tiempos_ev = sorted(set(to[eo].tolist()))
        H, tb, hb = 0.0, [], []
        for tt in tiempos_ev:
            d = int(np.sum(eo & (to == tt)))
            H += d / float(np.sum(ro[to >= tt]))
            tb.append(int(round(tt)))
            hb.append(H)
        bases[str(g)] = {"tiempos_base": tb, "riesgo_acumulado_base": hb, "filas": int(len(o)), "eventos": int(np.sum(eo)),
                         "max_duracion": int(np.max(to))}
    return {"coef": [float(x) for x in w], "bases": bases, "convergio": bool(res.success), "mensaje": str(res.message), "iteraciones": int(res.nit),
            "gradiente_max": float(np.max(np.abs(objetivo(w)[1])))}


def contraste_sksurv(aj: list[dict], variables: list[str], alpha: float, config: dict) -> dict:
    """Con un único estrato, el ajuste propio debe reproducir CoxPHSurvivalAnalysis (coeficientes y curva base)."""
    np, _ = _np()
    from sksurv.linear_model import CoxPHSurvivalAnalysis
    from sksurv.util import Surv
    trans = ajustar_transformaciones(aj, variables)
    X = np.array([aplicar_transformaciones(f, trans) for f in aj], dtype=float)
    t = np.array([f["duracion"] for f in aj], dtype=float)
    e = np.array([bool(f["evento"]) for f in aj])
    propio = ajustar_cox_estratificado(X, t, e, np.zeros(len(aj), dtype=int), alpha, config)
    sk = CoxPHSurvivalAnalysis(alpha=alpha, ties="breslow", n_iter=200, tol=1e-12).fit(X, Surv.from_arrays(e, t))
    base = propio["bases"]["0"]
    hb_sk = dict(zip([int(round(x)) for x in sk.cum_baseline_hazard_.x], sk.cum_baseline_hazard_.y))
    return {"diferencia_coeficientes": float(np.max(np.abs(np.array(propio["coef"]) - sk.coef_))),
            "diferencia_riesgo_base": max(abs(h - hb_sk[tt]) for tt, h in zip(base["tiempos_base"], base["riesgo_acumulado_base"])),
            "alpha": alpha}


# Artefactos ----------------------------------------------------------------------------------------------------
def _m31(d: dict, config: dict, cid: str) -> dict:
    d = dict(d)
    d["ventana"] = dict(config["ventana"], limites=list(config["ventana"]["limites"]))
    d["probabilidades_acumuladas_dias"] = list(config["probabilidades_acumuladas_dias"])
    d["version_protocolo"] = config["version_protocolo"]
    d.pop("huella", None)
    d["version"] = "pendiente"
    from .inferencia import sellar
    d["version"] = f"proxima_compra-m31-{cid}-" + sellar(d)["huella"][:8]
    return sellar(d)


def artefacto_estratificado(ajuste: dict, trans, variables, alpha, aj, config, datos, minimo: int) -> tuple[dict, dict]:
    soporte = max(f["duracion"] for f in aj)
    estratos = {g: {"tiempos_base": b["tiempos_base"], "riesgo_acumulado_base": b["riesgo_acumulado_base"]}
                for g, b in ajuste["bases"].items() if b["eventos"] >= minimo and b["max_duracion"] >= soporte}
    omitidos = {g: b for g, b in ajuste["bases"].items() if g not in estratos}
    d = M3._comunes(config, datos, aj, "cox_estratificado",
                    f"Cox L2 estratificado por grupo (alpha={alpha}); coeficientes comunes y curva base de Breslow por grupo.")
    d["cox"] = {"variables": list(variables), "transformaciones": trans, "coeficientes": ajuste["coef"], "variable_estrato": "grupo",
                "estratos": estratos, "alpha": alpha, "ties": "breslow",
                "penalizacion": "log-verosimilitud parcial estratificada total + alpha·||w||²/2 (semántica de scikit-survival 0.26)",
                "ajuste": {k: ajuste[k] for k in ("convergio", "mensaje", "iteraciones", "gradiente_max")},
                "estratos_sin_soporte": {g: {"eventos": b["eventos"], "max_duracion": b["max_duracion"]} for g, b in omitidos.items()}}
    return d, omitidos


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID or not es_m31(config):
        raise ProtocoloError("La configuración no es un protocolo M3.1 de proxima_compra")
    if (salida / "config.json").exists() and canon(json.loads((salida / "config.json").read_text(encoding="utf-8"))) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    np, _ = _np()
    ds = M3.preparar(datos, config)
    aj, va = ds["bloques"]["ajuste"], ds["bloques"]["validacion"]
    candidatos = {"km": {"familia": "km", "alpha": None, "artefacto": _m31(M3.artefacto_km(aj, config, datos), config, "km")}}
    diagnostico, val = {}, {}
    for familia, spec in config["candidatos"].items():
        variables = config[spec["variables"]]
        for alpha in spec["alpha"]:
            cid = f"{familia}-a{str(alpha).replace('.', '_')}"
            if familia == "cox":
                m, trans, avisos = M3.ajustar_cox(aj, variables, alpha, config)
                art_d = _m31(M3.artefacto_cox(m, trans, variables, alpha, aj, config, datos, avisos), config, cid)
                art = desde_dict(json.loads(json.dumps(art_d)))
                eq = M3.equivalencia(m, trans, art, aj[:200] + va)
                diagnostico[cid] = {"avisos": avisos, "equivalencia": eq, "coeficientes": dict(zip(variables, art_d["cox"]["coeficientes"]))}
            else:
                trans = ajustar_transformaciones(aj, variables)
                X = np.array([aplicar_transformaciones(f, trans) for f in aj], dtype=float)
                gr = np.array([f["grupo"] for f in aj])
                aju = ajustar_cox_estratificado(X, [f["duracion"] for f in aj], [f["evento"] for f in aj], gr, alpha, config)
                art_d, omitidos = artefacto_estratificado(aju, trans, variables, alpha, aj, config, datos, spec["minimo_eventos_estrato"])
                art_d = _m31(art_d, config, cid)
                art = desde_dict(json.loads(json.dumps(art_d)))
                # equivalencia: S(t|x) del artefacto recargado frente al cálculo directo con numpy
                dif = 0.0
                for f in aj[:200] + va:
                    g = grupo(f["recencia_dias"], f["dias_compra_distintos"])
                    if g not in art_d["cox"]["estratos"]:
                        continue
                    b = art_d["cox"]["estratos"][g]
                    lp = float(np.dot(aju["coef"], aplicar_transformaciones(f, trans)))
                    for tt, h in zip(b["tiempos_base"], b["riesgo_acumulado_base"]):
                        dif = max(dif, abs(math.exp(-h * math.exp(lp)) - art.supervivencia(f, tt)))
                diagnostico[cid] = {"ajuste": art_d["cox"]["ajuste"], "estratos": {g: {k: v for k, v in b.items() if k in ("filas", "eventos", "max_duracion")}
                                                                                   for g, b in aju["bases"].items()},
                                    "estratos_sin_soporte": list(omitidos), "equivalencia": {"diferencia_maxima_supervivencia": dif},
                                    "coeficientes": dict(zip(variables, aju["coef"]))}
                if not aju["convergio"]:
                    diagnostico[cid]["descartado"] = "no convergió"
                    continue
            if diagnostico[cid]["equivalencia"]["diferencia_maxima_supervivencia"] > config["tolerancia_equivalencia"]:
                raise ValueError(f"{cid}: el artefacto recargado difiere del ajuste")
            candidatos[cid] = {"familia": familia, "alpha": alpha, "artefacto": art_d}
    contraste = contraste_sksurv(aj, config["variables"], 1.0, config)
    malla = M3.rejilla(aj, va, config)
    complejidad = {"km": 0, "cox": config["candidatos"]["cox"]["complejidad"], "cox_estratificado": config["candidatos"]["cox_estratificado"]["complejidad"]}
    for cid, c in candidatos.items():
        if malla["estimable"]:
            val[cid] = M3._publico(M3.medir(desde_dict(json.loads(json.dumps(c["artefacto"]))), aj, va, malla["puntos"]))
    tol = config["seleccion"]["tolerancia"]
    elegido, motivo = "km", "Sin rejilla estimable en validación: se conserva Kaplan-Meier"
    if malla["estimable"]:
        orden = sorted(candidatos, key=lambda c: (round(val[c]["ibs"] / tol), complejidad[candidatos[c]["familia"]], -(candidatos[c]["alpha"] or 0)))
        mejor = orden[0]
        if mejor != "km" and val[mejor]["ibs"] < val["km"]["ibs"] - tol:
            elegido, motivo = mejor, f"{mejor} tiene el menor Brier integrado de validación y mejora a Kaplan-Meier"
        else:
            motivo = "Ningún Cox mejora el Brier integrado de Kaplan-Meier en validación: se conserva Kaplan-Meier"
    seleccion = {"criterio": config["seleccion"], "rejilla_validacion": malla, "elegido": elegido, "motivo": motivo,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"],
                 "candidatos": {cid: {"familia": c["familia"], "alpha": c["alpha"], "artefacto_huella": c["artefacto"]["huella"],
                                      "artefacto_version": c["artefacto"]["version"], "validacion": val.get(cid)} for cid, c in candidatos.items()},
                 "diagnostico": diagnostico, "contraste_cox_propio_vs_sksurv_un_estrato": contraste,
                 "nota": "Parámetros ajustados solo con el bloque de ajuste; no se reajusta con validación ni prueba."}
    km_d = candidatos["km"]["artefacto"]
    archivos = {f"candidatos/{cid}.json": json_bytes(c["artefacto"]) for cid, c in candidatos.items()}
    archivos |= {"artefacto.json": json_bytes(candidatos[elegido]["artefacto"]), "referencia_km.json": json_bytes(km_d),
                 "config.json": json_bytes(config), "seleccion.json": json_bytes(seleccion), "entorno.json": json_bytes(M3.entorno_m3()),
                 "protocolo.json": json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config)}),
                 "datos.json": json_bytes(dict(datos.descripcion(), fronteras_verificadas=ds["fronteras"],
                                               conteos_por_bloque={b: M3.conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in M3.ORDEN_BLOQUES})),
                 "predicciones_validacion.csv": M3._csv_filas(va, {cid: desde_dict(json.loads(json.dumps(c["artefacto"]))) for cid, c in candidatos.items()}, "validacion")}
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"],
            "seleccion_elegido": elegido, "referencia_km_huella": km_d["huella"], "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica (ya vista en M3: exploratoria)"}
    marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta,
                             volatiles={"fechas_piloto": M3.fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": {b: M3.conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in M3.ORDEN_BLOQUES},
            "fronteras": ds["fronteras"]}


# Evaluación ----------------------------------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    if not es_m31(config) or huella_protocolo(config) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    sel = json.loads((ejecucion / "seleccion.json").read_text(encoding="utf-8"))
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    cand = cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    if not (art.huella == cand.huella == cong["artefacto_huella"]) or km.huella != cong["referencia_km_huella"]:
        raise ProtocoloError("artefacto.json o referencia_km.json no son los congelados.")
    return cong


def calibracion_acumulada(art, prueba: list[dict], dias: list[int]) -> dict:
    """Probabilidad media de compra hasta t frente a la proporción observada (Kaplan–Meier de prueba, con censura)."""
    t_km, s_km = kaplan_meier([f["duracion"] for f in prueba], [f["evento"] for f in prueba])
    out = {}
    for t in dias:
        pred = [1 - art.supervivencia(f, t) for f in prueba if art.supervivencia(f, t) is not None]
        obs = 1 - escalon(t, t_km, s_km, 1.0)
        out[str(t)] = {"media_estimada": sum(pred) / len(pred) if pred else None, "observada_km": obs,
                       "error": abs(sum(pred) / len(pred) - obs) if pred else None, "n": len(pred)}
    return out


def decidir(c, k, boot, cont, malla, elegido, cal, config) -> dict:
    metas, mins = config["metas"], config["minimos_evidencia"]
    if not malla["estimable"]:
        return {"decision": "inconcluso", "estado_maximo": "sombra", "motivos": ["Brier integrado no estimable"], "cumple": {}, "valores": {}}
    nominal = metas["cobertura_nominal_ventana"]
    ev_corte = [m["eventos"] for m in cont["por_corte"]]
    det, cp = c["cobertura_p10_p90"]["determinados"], c["comparacion_personal"]
    ic_d, ic_c = boot.get("ibs_candidato_menos_km", {}), boot.get("cobertura_p10_p90", {})
    red = (k["ibs"] - c["ibs"]) / k["ibs"] if k["ibs"] else None
    err_cal = max((v["error"] for v in cal.values() if v["error"] is not None), default=None)
    cumple = {"minimos_evidencia": cont["filas"] >= mins["filas"] and cont["eventos"] >= mins["eventos"] and min(ev_corte) >= mins["eventos_por_corte"]
                                   and len(malla["puntos"]) >= mins["puntos_rejilla"],
              "reduccion_ibs_5pct": red is not None and red >= metas["reduccion_relativa_ibs_vs_km"] - 1e-12,
              "ic95_ibs_bajo_cero": bool(ic_d) and ic_d["p97_5"] < 0,
              "error_no_peor_que_personal": cp["n_comun"] >= mins["eventos_comunes_personal"] and cp["candidato_dias"] <= cp["personal_dias"],
              "ventanas_utilizables_50pct": c["ventanas"]["proporcion_utilizables_elegibles"] >= metas["proporcion_ventanas_utilizables_elegibles"],
              "cobertura_40_compatible": det >= mins["ventanas_determinadas"] and bool(ic_c) and ic_c["p2_5"] <= nominal <= ic_c["p97_5"],
              "calibracion_acumulada": err_cal is not None and err_cal <= metas["calibracion_acumulada_max_error"]}
    motivos = []
    if elegido == "km":
        motivos.append("Ningún Cox mejoró a Kaplan-Meier en validación: el artefacto principal es la referencia poblacional.")
    fuera = cumple["minimos_evidencia"] and det >= mins["ventanas_determinadas"] and ic_c and (ic_c["p97_5"] < nominal or ic_c["p2_5"] > nominal)
    if all(cumple.values()) and elegido != "km":
        decision = "favorable"
        motivos.append("Cumple todas las metas predeclaradas en una comprobación ya vista: solo habilita sombra y el piloto prospectivo.")
    elif (ic_d and ic_d["p2_5"] > 0 and elegido != "km") or fuera:
        decision = "rechazado"
        if ic_d and ic_d["p2_5"] > 0 and elegido != "km":
            motivos.append("El IC 95 % de (IBS candidato − IBS Kaplan-Meier) está entero por encima de 0.")
        if fuera:
            motivos.append(f"El IC 95 % de la cobertura p10–p50 está entero fuera del {nominal:.0%} nominal.")
    else:
        decision = "inconcluso"
        motivos += [f"No cumple: {k_}" for k_, v in cumple.items() if not v]
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "cumple": cumple, "motivos": motivos,
            "valores": {"ibs_candidato": c["ibs"], "ibs_km": k["ibs"], "reduccion_relativa": red, "ic95_ibs_candidato_menos_km": [ic_d.get("p2_5"), ic_d.get("p97_5")],
                        "error_mediano_candidato": cp["candidato_dias"], "error_mediano_personal": cp["personal_dias"], "n_comun": cp["n_comun"],
                        "proporcion_ventanas_utilizables": c["ventanas"]["proporcion_utilizables_elegibles"], "cobertura_p10_p50": c["cobertura_p10_p90"]["cobertura"],
                        "ic95_cobertura": [ic_c.get("p2_5"), ic_c.get("p97_5")], "ventanas_determinadas": det,
                        "error_max_calibracion_acumulada": err_cal, "rejilla": [malla["desde"], malla["hasta"]]}}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None, m3: str | Path | None = None) -> dict:
    """Comprobación (exploratoria y reutilizada) del artefacto congelado. ``m3``: ejecución M3 medida solo como contexto."""
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    info = json.loads((ejecucion / "datos.json").read_text(encoding="utf-8"))
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = M3.preparar(datos, config)
    aj, pr = ds["bloques"]["ajuste"], ds["bloques"]["comprobacion_historica"]
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    malla = M3.rejilla(aj, pr, config)
    G = M3.censura_ajuste(aj)
    cont = M3.conteos(pr, ds["exclusiones"]["comprobacion_historica"])
    res: dict[str, Any] = {"conteos": cont, "rejilla": malla}
    boot, cal = {}, {}
    if malla["estimable"]:
        mc, mk = M3.medir(art, aj, pr, malla["puntos"]), M3.medir(km, aj, pr, malla["puntos"])
        tau = malla["hasta"]
        mc["concordancia_ipcw"] = M3.concordancia(aj, pr, [art.predictor_lineal(f) for f in pr], tau)
        mk["concordancia_ipcw"] = 0.5
        b = config["metricas"]["bootstrap"]
        boot = M3.bootstrap(pr, G, malla["puntos"], mc["_S"], mk["_S"], mc["_resultados"], b["repeticiones"], b["semilla"])
        cal = calibracion_acumulada(art, pr, config["probabilidades_acumuladas_dias"])
        res |= {"candidato": M3._publico(mc), "km": M3._publico(mk), "calibracion_acumulada": {"candidato": cal,
                "km": calibracion_acumulada(km, pr, config["probabilidades_acumuladas_dias"])},
                "contraste_ibs_sksurv": {"candidato": abs(mc["ibs"] - M3.ibs_referencia(aj, pr, mc["_S"], malla["puntos"]))},
                "por_corte_y_grupo": {"candidato": M3._por_grupo_y_corte(art, pr, G, malla["puntos"]), "km": M3._por_grupo_y_corte(km, pr, G, malla["puntos"])}}
        if m3:
            M3.verificar_congelacion(m3)
            a3 = cargar_artefacto(Path(m3) / "artefacto.json", modelo_id=MODELO_ID)
            m3m = M3.medir(a3, aj, pr, malla["puntos"])
            # misma ventana p10–p50 para comparar el número de ventanas útiles con el modelo de M3
            w3 = [M3.ventana(a3.curva(f), f["corte"], config["ventana"]["ancho_maximo_dias"], tuple(config["ventana"]["limites"])) for f in pr]
            res["contexto_m3"] = {"version": a3.version, "ibs": m3m["ibs"], "ventanas_p10_p50_utilizables": sum(w["ventana_utilizable"] for w in w3)}
        decision = decidir(mc, mk, boot, cont, malla, cong["seleccion_elegido"], cal, config)
    else:
        decision = decidir({}, {}, {}, cont, malla, cong["seleccion_elegido"], cal, config)
    metricas = {"bloque": "comprobacion_historica", "alcance": "comprobación histórica EXPLORATORIA Y REUTILIZADA (ya vista en M3)",
                "ventana": config["ventana"], "artefacto": {"version": art.version, "huella": art.huella, "tipo": art.tipo},
                "referencia_km": {"version": km.version, "huella": km.huella}, "resultados": res, "incertidumbre_bootstrap_clientes": boot,
                "nota_cobertura": "En los resultados, 'cobertura_p10_p90' mide la ventana declarada por el artefacto (aquí p10–p50).",
                "limitaciones": LIMITACIONES}
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"],
               candidato=cong["seleccion_elegido"], version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"],
               sello_congelacion=cong["sello"], origen_datos=config["origen_datos"], alcance=metricas["alcance"],
               limitaciones=LIMITACIONES + ["Ningún modelo se promueve automáticamente; no se activan recordatorios."])
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas), "decision.json": json_bytes(doc),
                "predicciones_comprobacion.csv": M3._csv_filas(pr, {"candidato": art, "km": km}, "comprobacion_historica")}
    marcador = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"],
                                                                         "m3_contexto": str(m3) if m3 else None})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": json.loads((ejecucion / "decision.json").read_text(encoding="utf-8"))}
