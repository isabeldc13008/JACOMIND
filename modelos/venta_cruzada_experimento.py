"""M4 · Experimento de venta cruzada (protocolo ``m4-protocolo-v1``): control A07, preparar, entrenar, evaluar y decidir.

scikit-learn/numpy solo se importan al ajustar. Universo por corte fijado ANTES de puntuar (clientes con historial y
horizonte observado); los métodos comparten candidatos, cortes, horizonte y K. Integridad como en M2/M3
(``modelos/ejecucion.py``): evidencia sellada, artefacto ligado a la selección, evaluación recuperable e idempotente.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .compra import DependenciaEntrenamiento, ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict, sellar
from .variables import FUNCION, ajustar_transformaciones, aplicar_transformaciones, cortes_mensuales
from .venta_cruzada import (FORMATO, HORIZONTE_DIAS, K, MODELO_ID, VARIABLES_AMPLIADA, VARIABLES_CLIENTE, VARIABLES_PAR, candidatos_cliente,
                            cargar_reglas, compras_por_cliente, estadisticas, etiqueta, instalaciones_por_cliente, ranking_modelo,
                            ranking_referencia, variables_cliente, variables_par)

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "venta_cruzada.json"
REGLA_DECISION = "m4-decision-v1"
METRICAS_VERSION = "m4-metricas-v1"
MARCADOR_CONGELACION, MARCADOR_EVALUACION = "congelacion.json", "evaluacion.json"
ORDEN_BLOQUES = ("ajuste", "validacion", "comprobacion_historica")
LIMITACIONES = [
    "Datos sintéticos de 120 clientes y 10 productos, ya inspeccionados: la comprobación histórica (julio y agosto de 2026) es exploratoria.",
    "La disponibilidad del catálogo usa la primera venta observada como proxy; no demuestra la fecha real de lanzamiento.",
    "Las coberturas se suponen conocidas desde su fecha de inicio (convención sintética); no hay reglas empresariales de compatibilidad.",
    "Una compra posterior no prueba aceptación de una oferta ni efecto de la recomendación.",
]


def _leer(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def cargar_config(ruta: str | Path | None = None) -> dict:
    return _leer(Path(ruta or CONFIG_DEFECTO))


def variables_combinacion(config: dict, comb: str) -> list[str]:
    v = config["variables"]
    return v["cliente"] + v["par"] + (v["ampliada_extra"] if comb == "ampliada" else [])


def identidad_protocolo(config: dict, reglas: dict) -> dict:
    vs = sorted(set(variables_combinacion(config, "ampliada")))
    return {"configuracion": _sin_descriptivas(config), "reglas_compatibilidad": reglas,
            "codigo": {"transformaciones": {v: FUNCION.get(v) for v in vs}, "formato_artefacto": FORMATO, "metricas": METRICAS_VERSION,
                       "regla_decision": REGLA_DECISION, "k": K, "horizonte": HORIZONTE_DIAS}}


def huella_protocolo(config: dict, reglas: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config, reglas)).encode()).hexdigest()


# Control A07 por familia -------------------------------------------------------------------------------------------
def control_familias(datos: DatosAceptados) -> dict:
    """Reproduce exactamente el control de ``pipeline/generar.py`` (calidad.venta_cruzada) y documenta su universo."""
    from pipeline.oportunidades import evaluar_venta_cruzada, familias_por_cliente, recomendar_popular, recomendar_venta_cruzada
    cierre = datos.observado_hasta
    corte = cierre - timedelta(days=60)
    fam = {pid: str(p.get("familia_prueba")) for pid, p in datos.productos.items()}
    antes, despues = familias_por_cliente(datos.ventas, fam, corte), familias_por_cliente(datos.ventas, fam, cierre)
    co, po = recomendar_venta_cruzada(antes, soporte_minimo=3), recomendar_popular(antes)
    con_todas = sum(1 for v in antes.values() if set(fam.values()) <= v)
    return {"corte": corte.isoformat(), "compras_hasta": cierre.isoformat(), "horizonte": f"({corte.isoformat()}, {cierre.isoformat()}] = 60 días",
            "familias": sorted(set(fam.values())), "k": 1, "soporte_minimo_coocurrencia": 3,
            "poblacion": {"clientes_con_historial": len(antes), "con_todas_las_familias": con_todas,
                          "sin_sugerencia_coocurrencia": len(antes) - len(co), "sin_sugerencia_popularidad": sum(1 for v in po.values() if not v)},
            "coocurrencia": evaluar_venta_cruzada(antes, despues, co), "popularidad": evaluar_venta_cruzada(antes, despues, recomendar_popular(antes)),
            "politica_abstencion": "un cliente sin familia por recomendar (ya tiene todas) NO entra en el denominador: el control mide 69 de 120 clientes",
            "advertencia": "Control por familia: no es comparable con las tasas por producto de M4 (otro universo, otra granularidad)."}


# Preparación ---------------------------------------------------------------------------------------------------------
def cortes_bloque(config: dict, bloque: str) -> list[date]:
    a, b = config["bloques"][bloque]
    return cortes_mensuales(_d(a), _d(b))


def preparar(datos: DatosAceptados, config: dict, reglas: dict) -> dict:
    from pipeline.operaciones import _load
    compras = compras_por_cliente(datos.ventas, datos.tasas)
    inst = instalaciones_por_cliente(_load(datos.directorio, "base_instalada.csv", "instalaciones"))
    familias = {p: str(v.get("familia_prueba", "")) for p, v in datos.productos.items()}
    bloques, snapshots = {}, {}
    for b in ORDEN_BLOQUES:
        cortes = cortes_bloque(config, b)
        excl = set(map(_d, config["separacion_temporal"]["excluidos"]))
        if excl & set(cortes):
            raise ProtocoloError(f"El bloque {b} contiene un corte de separación temporal")
        pares, universo, exclusiones = [], [], {}
        for corte in cortes:
            stats = estadisticas(compras, corte)  # snapshot con operaciones <= corte
            snapshots[corte.isoformat()] = stats
            maduro = corte + timedelta(days=HORIZONTE_DIAS) <= datos.observado_hasta
            for cl in sorted(datos.clientes, key=lambda c: str(c["cliente_id"])):
                cid = str(cl["cliente_id"])
                if cl["fecha_alta"] > corte:
                    continue
                vc = variables_cliente(compras.get(cid, []), corte)
                if vc is None:
                    continue
                info = candidatos_cliente(cid, compras.get(cid, []), inst.get(cid, []), stats, datos.productos, reglas, corte)
                for e in info["exclusiones"]:
                    exclusiones[e["motivo"]] = exclusiones.get(e["motivo"], 0) + 1
                if not maduro:
                    continue
                universo.append({"cliente_id": cid, "corte": corte, "n_candidatos": len(info["candidatos"]), "comprados": info["comprados"],
                                 "cubiertos": info["cubiertos"], "excluidos": [e["producto_id"] for e in info["exclusiones"]]})
                for c in info["candidatos"]:  # candidatos construidos antes de mirar el futuro; la etiqueta se añade después
                    par = variables_par(vc, c["producto_id"], info["comprados"], stats, familias) | {
                        "cliente_id": cid, "corte": corte, "estado_compatibilidad": c["estado_compatibilidad"]}
                    y = etiqueta(compras.get(cid, []), c["producto_id"], corte, datos.observado_hasta)
                    fut = [x["fecha"] for x in compras.get(cid, []) if x["producto_id"] == c["producto_id"] and corte < x["fecha"] <= corte + timedelta(days=HORIZONTE_DIAS)]
                    pares.append(par | {"y": y, "fecha_compra": min(fut).isoformat() if fut else None})
        bloques[b] = {"pares": pares, "universo": universo, "exclusiones": exclusiones}
    return {"compras": compras, "instalaciones": inst, "bloques": bloques, "estadisticas": snapshots, "familias": familias,
            "fronteras": verificar_fronteras(bloques, config, datos)}


def verificar_fronteras(bloques: dict, config: dict, datos: DatosAceptados) -> dict:
    """POR CÓDIGO: etiquetas de un bloque maduran antes de la primera inferencia del siguiente; la comprobación, antes de la cobertura."""
    salida = {}
    for i, b in enumerate(ORDEN_BLOQUES):
        cortes = cortes_bloque(config, b)
        ultima = max(cortes) + timedelta(days=HORIZONTE_DIAS)
        if any(p["y"] is None for p in bloques[b]["pares"]):
            raise ProtocoloError(f"{b}: hay etiquetas pendientes")
        if i + 1 < len(ORDEN_BLOQUES):
            sig = min(cortes_bloque(config, ORDEN_BLOQUES[i + 1]))
            if ultima >= sig:
                raise ProtocoloError(f"Fuga temporal: las etiquetas de {b} maduran el {ultima}, no antes de {sig}")
            salida[f"{b}->{ORDEN_BLOQUES[i + 1]}"] = {"ultima_etiqueta_madura": ultima.isoformat(), "primera_inferencia": sig.isoformat()}
        else:
            if ultima > datos.observado_hasta:
                raise ProtocoloError(f"{b}: el horizonte llega a {ultima}, después de la cobertura {datos.observado_hasta}")
            salida[f"{b}->cobertura"] = {"ultima_etiqueta_madura": ultima.isoformat(), "cobertura": datos.observado_hasta.isoformat(),
                                         "septiembre_excluido": "2026-09-30 + 60 = 2026-11-29 > cobertura"}
    return salida


def conteos(bloque: dict) -> dict:
    pares, uni = bloque["pares"], bloque["universo"]
    pos = [p for p in pares if p["y"] == 1]
    por_producto = {}
    for p in sorted({x["producto_id"] for x in pares}):
        pp = [x for x in pos if x["producto_id"] == p]
        compras_unicas = {(x["cliente_id"], x["fecha_compra"]) for x in pp}
        por_producto[p] = {"pares": sum(x["producto_id"] == p for x in pares), "positivos": len(pp), "clientes_con_positivo": len({x["cliente_id"] for x in pp}),
                           "compras_unicas": len(compras_unicas), "fotografias_repetidas_mismo_evento": len(pp) - len(compras_unicas)}
    return {"pares": len(pares), "positivos": len(pos), "negativos": len(pares) - len(pos), "clientes_corte_universo": len(uni),
            "clientes_unicos": len({u["cliente_id"] for u in uni}), "clientes_corte_sin_candidatos": sum(u["n_candidatos"] == 0 for u in uni),
            "clientes_corte_con_algun_positivo": len({(p["cliente_id"], p["corte"]) for p in pos}),
            "exclusiones_por_motivo": dict(sorted(bloque["exclusiones"].items())), "por_producto": por_producto,
            "por_corte": [{"corte": c.isoformat(), "universo": sum(u["corte"] == c for u in uni), "pares": sum(p["corte"] == c for p in pares),
                           "positivos": sum(p["corte"] == c and p["y"] == 1 for p in pares)} for c in sorted({u["corte"] for u in uni})]}


# Ajuste ------------------------------------------------------------------------------------------------------------------
def _sk():
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        return np, LogisticRegression
    except ImportError as exc:
        raise DependenciaEntrenamiento("Entrenar M4 requiere pip install -r requirements-modelos.txt") from exc


def ajustar(aj: list[dict], variables: list[str], C: float, config: dict):
    np, LR = _sk()
    trans = ajustar_transformaciones(aj, variables)
    productos = sorted({p["producto_id"] for p in aj})

    def X(pares):
        return np.array([aplicar_transformaciones(p, trans) + [float(p["producto_id"] == q) for q in productos] for p in pares], dtype=float)
    c = config["candidato"]
    m = LR(C=C, solver=c["solver"], max_iter=c["max_iter"], tol=c["tol"], random_state=c["semilla"]).fit(X(aj), np.array([p["y"] for p in aj]))
    w = [float(x) for x in m.coef_[0]]
    return trans, productos, float(m.intercept_[0]), w[:len(variables)], dict(zip(productos, w[len(variables):])), (lambda pares: list(m.decision_function(X(pares))))


def soporte(aj: list[dict]) -> dict:
    out = {}
    for p in sorted({x["producto_id"] for x in aj}):
        pos = [x for x in aj if x["producto_id"] == p and x["y"] == 1]
        out[p] = {"positivos": len(pos), "clientes": len({x["cliente_id"] for x in pos}), "compras_unicas": len({(x["cliente_id"], x["fecha_compra"]) for x in pos})}
    return out


def artefacto(comb, variables, C, trans, productos, b0, w, wp, aj, config, datos, reglas) -> dict:
    d = {"formato": FORMATO, "modelo_id": MODELO_ID, "version": "pendiente", "version_variables": "venta_cruzada-variables-v1",
         "descripcion": f"Regresión logística L2 (C={C}) compartida entre clientes y productos; combinación {comb}. Puntaje = logit sin calibrar.",
         "horizonte_dias": HORIZONTE_DIAS, "umbral": None, "combinacion": comb, "C": C, "variables": list(variables), "transformaciones": trans,
         "pesos": w, "pesos_producto": wp, "intercepto": b0, "productos_entrenamiento": productos, "producto_desconocido": "sin indicadora (peso 0) y sin soporte: popularidad",
         "soporte": soporte(aj), "soporte_minimo": config["soporte"]["minimo_positivos_ajuste_por_producto"], "fallback": "popularidad",
         "estadisticas": config["estadisticas"]["politica"], "version_reglas": reglas.get("version"), "disponible_desde": config["disponible_desde"],
         "origen_datos": config["origen_datos"], "version_protocolo": config["version_protocolo"],
         "entrenamiento": {"cortes": sorted({p["corte"].isoformat() for p in aj}), "pares": len(aj), "positivos": sum(p["y"] for p in aj),
                           "huella_datos": datos.huella_datos, "revision_datos": datos.revision}}
    d["version"] = f"venta_cruzada-m4-{comb}-c{str(C).replace('.', '_')}-" + sellar(d)["huella"][:8]
    return sellar(d)


# Métricas -------------------------------------------------------------------------------------------------------------------
def por_cliente_corte(pares: list[dict]) -> dict:
    g: dict = {}
    for p in pares:
        g.setdefault((p["cliente_id"], p["corte"]), []).append(p)
    return g


def evaluar_metodo(bloque: dict, ranker: Callable[[list[dict]], list[dict]]) -> dict:
    """Métricas sobre el universo fijo (abstención = sin acierto) y subconjuntos con denominadores explícitos."""
    grupos = por_cliente_corte(bloque["pares"])
    filas, n_sug = [], {}
    for u in bloque["universo"]:
        pares = grupos.get((u["cliente_id"], u["corte"]), [])
        lista = ranker(pares) if pares else []
        ids = [p["producto_id"] for p in lista]
        if len(ids) != len(set(ids)) or len(ids) > K:
            raise AssertionError("ranking con duplicados o más de K productos")
        pos = {p["producto_id"] for p in pares if p["y"] == 1}
        rel = [int(i in pos) for i in ids]
        ideal = sorted([1] * min(len(pos), K))
        dcg = sum(r / math.log2(i + 2) for i, r in enumerate(rel))
        idcg = sum(1 / math.log2(i + 2) for i in range(len(ideal)))
        filas.append({"cliente_id": u["cliente_id"], "corte": u["corte"], "n_candidatos": len(pares), "n_sugeridos": len(ids), "hit1": int(bool(rel) and rel[0] == 1),
                      "hit3": int(any(rel)), "aciertos3": sum(rel), "ndcg3": dcg / idcg if idcg else None, "tiene_positivo": bool(pos), "lista": ids,
                      "violaciones": sum(i in set(u["comprados"]) | set(u["cubiertos"]) | set(u["excluidos"]) for i in ids)})
        n_sug[len(ids)] = n_sug.get(len(ids), 0) + 1
    return {"filas": filas, "distribucion_sugerencias": {str(k): v for k, v in sorted(n_sug.items())}}


def resumir(ev: dict, comunes: set | None = None, productos_disponibles: int = 10) -> dict:
    f = ev["filas"]
    con = [x for x in f if x["n_candidatos"] > 0]
    com = [x for x in f if comunes is None or (x["cliente_id"], x["corte"]) in comunes]
    con_pos = [x for x in f if x["tiene_positivo"] and x["ndcg3"] is not None]
    sug = sum(x["n_sugeridos"] for x in f)
    tasa = lambda num, den: num / den if den else None  # noqa: E731
    por_corte = {}
    for x in f:
        c = por_corte.setdefault(x["corte"].isoformat(), {"universo": 0, "hit1": 0, "hit3": 0})
        c["universo"] += 1; c["hit1"] += x["hit1"]; c["hit3"] += x["hit3"]
    return {"universo": len(f), "hitrate1_universo": tasa(sum(x["hit1"] for x in f), len(f)), "hitrate3_universo": tasa(sum(x["hit3"] for x in f), len(f)),
            "aciertos1": sum(x["hit1"] for x in f), "aciertos3_clientes": sum(x["hit3"] for x in f),
            "con_candidatos": len(con), "hitrate1_con_candidatos": tasa(sum(x["hit1"] for x in con), len(con)),
            "recomendacion_comun": len(com), "hitrate1_comun": tasa(sum(x["hit1"] for x in com), len(com)),
            "precision3": tasa(sum(x["aciertos3"] for x in f), sug), "productos_sugeridos": sug,
            "ndcg3": tasa(sum(x["ndcg3"] for x in con_pos), len(con_pos)), "clientes_con_algun_positivo": len(con_pos),
            "cobertura_clientes": tasa(sum(x["n_sugeridos"] > 0 for x in f), len(f)),
            "cobertura_catalogo": len({i for x in f for i in x["lista"]}) / productos_disponibles,
            "sin_candidatos": sum(x["n_candidatos"] == 0 for x in f), "violaciones": sum(x["violaciones"] for x in f),
            "distribucion_sugerencias": ev["distribucion_sugerencias"], "por_corte": por_corte}


def por_producto(ev: dict, pares: list[dict], familias: dict) -> dict:
    pos = {(p["cliente_id"], p["corte"], p["producto_id"]) for p in pares if p["y"] == 1}
    out: dict = {}
    for x in ev["filas"]:
        for i, p in enumerate(x["lista"]):
            o = out.setdefault(p, {"familia": familias.get(p), "primera_posicion": 0, "aciertos_primera": 0, "top3": 0, "aciertos_top3": 0})
            hit = (x["cliente_id"], x["corte"], p) in pos
            o["top3"] += 1; o["aciertos_top3"] += hit
            if i == 0:
                o["primera_posicion"] += 1; o["aciertos_primera"] += hit
    return dict(sorted(out.items()))


def bootstrap(evs: dict[str, dict], a: str, b: str, B: int, semilla: int) -> dict:
    """Diferencias de HitRate@1 y de cobertura (a − b) remuestreando clientes completos (todos sus cortes juntos)."""
    fa = {(x["cliente_id"], x["corte"]): x for x in evs[a]["filas"]}
    fb = {(x["cliente_id"], x["corte"]): x for x in evs[b]["filas"]}
    por_cli: dict = {}
    for k in fa:
        por_cli.setdefault(k[0], []).append(k)
    ids = sorted(por_cli)
    rng = random.Random(semilla)
    d1, dc = [], []
    for _ in range(B):
        ks = [k for c in (rng.choice(ids) for _ in ids) for k in por_cli[c]]
        n = len(ks)
        d1.append(sum(fa[k]["hit1"] - fb[k]["hit1"] for k in ks) / n)
        dc.append(sum((fa[k]["n_sugeridos"] > 0) - (fb[k]["n_sugeridos"] > 0) for k in ks) / n)

    def ic(v):
        v = sorted(v)
        return {"p2_5": v[int(0.025 * (len(v) - 1))], "p97_5": v[int(math.ceil(0.975 * (len(v) - 1)))]}
    return {"hitrate1": ic(d1), "cobertura": ic(dc), "repeticiones": B, "unidad": "cliente completo (todos sus productos y cortes)"}


def evaluar_bloque(bloque: dict, art, familias: dict) -> tuple[dict, dict]:
    evs = {"modelo": evaluar_metodo(bloque, lambda pares: ranking_modelo(art, pares)) if art else None,
           "popularidad": evaluar_metodo(bloque, lambda pares: ranking_referencia(pares, "popularidad")),
           "coocurrencia": evaluar_metodo(bloque, lambda pares: ranking_referencia(pares, "coocurrencia"))}
    evs = {k: v for k, v in evs.items() if v}
    comunes = set.intersection(*({(x["cliente_id"], x["corte"]) for x in v["filas"] if x["n_sugeridos"] > 0} for v in evs.values()))
    res = {k: resumir(v, comunes) | {"por_producto": por_producto(v, bloque["pares"], familias)} for k, v in evs.items()}
    return res, evs


# Entrenamiento ------------------------------------------------------------------------------------------------------------
def entrenar(datos: DatosAceptados, config: dict, salida: str | Path, reglas: dict | None = None) -> dict:
    salida = Path(salida)
    reglas = reglas or cargar_reglas()
    if config.get("modelo_id") != MODELO_ID:
        raise ProtocoloError("La configuración no es de venta_cruzada")
    if (salida / "config.json").exists() and canon(_leer(salida / "config.json")) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    ds = preparar(datos, config, reglas)
    aj, va = ds["bloques"]["ajuste"]["pares"], ds["bloques"]["validacion"]["pares"]
    faltan = [b for b, ps in (("ajuste", aj), ("validacion", va)) if not ps or len({p["y"] for p in ps}) < 2]
    candidatos, equiv, val = {}, {}, {}
    if not faltan:
        for comb in ("basica", "ampliada"):
            variables = variables_combinacion(config, comb)
            for C in config["candidato"]["C"]:
                cid = f"{comb}-c{str(C).replace('.', '_')}"
                trans, productos, b0, w, wp, decision = ajustar(aj, variables, C, config)
                art_d = artefacto(comb, variables, C, trans, productos, b0, w, wp, aj, config, datos, reglas)
                art = desde_dict(json.loads(json.dumps(art_d)))
                muestra = aj + va
                dif = max(abs(a - art.puntaje(p)) for a, p in zip(decision(muestra), muestra))
                if dif > 1e-9:
                    raise ValueError(f"{cid}: el puntaje del artefacto recargado difiere de scikit-learn en {dif:g}")
                equiv[cid] = {"diferencia_maxima": dif, "pares": len(muestra)}
                candidatos[cid] = {"combinacion": comb, "C": C, "artefacto": art_d}
                val[cid] = evaluar_bloque(ds["bloques"]["validacion"], art, ds["familias"])[0]["modelo"]
    refs = evaluar_bloque(ds["bloques"]["validacion"], None, ds["familias"])[0]
    tol = config["seleccion"]["tolerancia"]
    orden = sorted(candidatos, key=lambda c: (-round(val[c]["hitrate1_universo"] / tol), -round(val[c]["hitrate3_universo"] / tol),
                                             candidatos[c]["combinacion"] != "basica", candidatos[c]["C"]))
    elegido = orden[0] if orden else None
    seleccion = {"criterio": config["seleccion"]["criterio"], "bloque": "validacion", "orden": orden, "elegido": elegido,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"] if elegido else None,
                 "sin_candidato": {"motivo": f"faltan clases en {faltan}"} if faltan else None,
                 "candidatos": {c: {"combinacion": v["combinacion"], "C": v["C"], "artefacto_huella": v["artefacto"]["huella"], "artefacto_version": v["artefacto"]["version"],
                                    "validacion": {k: x for k, x in val[c].items() if k != "por_producto"}, "equivalencia_json_sklearn": equiv[c]} for c, v in candidatos.items()},
                 "referencias_validacion": {k: {kk: x for kk, x in v.items() if kk != "por_producto"} for k, v in refs.items()},
                 "nota": "Parámetros solo del bloque de ajuste; estadísticas de cada fotografía con operaciones <= su corte; no se reentrena."}
    cont = {b: conteos(ds["bloques"][b]) for b in ORDEN_BLOQUES}
    archivos = {f"candidatos/{c}.json": json_bytes(v["artefacto"]) for c, v in candidatos.items()}
    if elegido:
        archivos["artefacto.json"] = json_bytes(candidatos[elegido]["artefacto"])
    archivos |= {"config.json": json_bytes(config), "reglas_compatibilidad.json": json_bytes(reglas), "seleccion.json": json_bytes(seleccion),
                 "protocolo.json": json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config, reglas), "identidad": identidad_protocolo(config, reglas)}),
                 "estadisticas_por_corte.json": json_bytes(ds["estadisticas"]), "control_familias.json": json_bytes(control_familias(datos)),
                 "datos.json": json_bytes(dict(datos.descripcion(), fronteras_verificadas=ds["fronteras"], conteos_por_bloque=cont,
                                               fuentes={"ventas": {"uso": "historial <= C y etiqueta (C, C+60]", **datos.cobertura.como_dict()},
                                                        "base_instalada": "exclusión por cobertura vigente (convención sintética: conocida desde fecha_inicio)",
                                                        "productos": "lista de productos y nombre; disponibilidad por primera venta observada; familia solo en la combinación ampliada (convención)",
                                                        "trm": "importe_cop_90d", "compras_proveedor": "no usada"})),
                 "universo_validacion.csv": _csv(ds["bloques"]["validacion"]["universo"], ["cliente_id", "corte", "n_candidatos", "comprados", "cubiertos", "excluidos"]),
                 "entorno.json": json_bytes(entorno())}
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config, reglas)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"] if elegido else None,
            "seleccion_elegido": elegido, "huella_datos": datos.huella_datos, "revision_datos": datos.revision, "version_reglas": reglas.get("version"),
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica"}
    marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta, volatiles={"fechas_piloto": fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": cont, "fronteras": ds["fronteras"]}


def _csv(filas: list[dict], cols: list[str]) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
    w.writeheader()
    for f in filas:
        w.writerow({k: (v.isoformat() if hasattr(v, "isoformat") else ("|".join(v) if isinstance(v, list) else v)) for k, v in f.items()})
    return buf.getvalue().encode("utf-8")


def fechas_piloto(hoy: date) -> dict:
    from .variables import fin_de_mes
    fin = fin_de_mes(hoy.year, hoy.month)
    primer = fin if fin > hoy else fin_de_mes(hoy.year + (hoy.month == 12), 1 if hoy.month == 12 else hoy.month + 1)
    return {"congelacion_real": hoy.isoformat(), "primer_corte_prospectivo": primer.isoformat(), "cobertura_requerida_para_puntuar": primer.isoformat(),
            "evaluable_desde": (primer + timedelta(days=HORIZONTE_DIAS)).isoformat()}


# Evaluación -------------------------------------------------------------------------------------------------------------------
def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, MARCADOR_CONGELACION, ProtocoloError)
    config, reglas = _leer(ejecucion / "config.json"), _leer(ejecucion / "reglas_compatibilidad.json")
    if huella_protocolo(config, reglas) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    sel = _leer(ejecucion / "seleccion.json")
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    if cong["artefacto_huella"]:
        art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
        cand = cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json", modelo_id=MODELO_ID)
        if not (art.huella == cand.huella == cong["artefacto_huella"]):
            raise ProtocoloError("artefacto.json no es el candidato seleccionado y congelado.")
    return cong


def decidir(res: dict, boot: dict, cont: dict, config: dict, hay_modelo: bool) -> dict:
    metas, mins = config["metas"], config["minimos_evidencia"]
    if not hay_modelo:
        return {"decision": "inconcluso", "estado_maximo": "sombra", "sistema_conservado": "popularidad", "cumple": {},
                "motivos": ["No se entrenó ningún candidato: se conserva popularidad con los mismos filtros"]}
    m, p = res["modelo"], res["popularidad"]
    dif = m["hitrate1_universo"] - p["hitrate1_universo"]
    cumple = {"minimos_evidencia": m["universo"] >= mins["clientes_corte_universo"] and max(m["aciertos1"], p["aciertos1"]) >= mins["aciertos_popularidad_o_modelo"]
                                   and len(cont["por_corte"]) >= mins["cortes"],
              "mejora_hitrate1_5pp": dif >= metas["mejora_hitrate1_vs_popularidad"] - 1e-12,
              "ic95_hitrate1_sobre_cero": boot["hitrate1"]["p2_5"] > 0,
              "cobertura_no_baja_mas_de_5pp": m["cobertura_clientes"] >= p["cobertura_clientes"] - metas["reduccion_maxima_cobertura"] - 1e-12,
              "cero_violaciones": m["violaciones"] == 0 and p["violaciones"] == 0}
    if all(cumple.values()):
        decision, motivos, sistema = "favorable", ["Cumple todas las metas predeclaradas en la comprobación exploratoria; con datos sintéticos solo habilita sombra."], "modelo"
    elif boot["hitrate1"]["p97_5"] < 0 or not cumple["cero_violaciones"]:
        decision, sistema = "rechazado", "popularidad"
        motivos = (["El IC 95 % de la diferencia de HitRate@1 frente a popularidad está entero por debajo de 0."] if boot["hitrate1"]["p97_5"] < 0 else []) + \
                  (["Hay recomendaciones que violan restricciones verificables."] if not cumple["cero_violaciones"] else [])
    else:
        decision, sistema = "inconcluso", "popularidad"
        motivos = [f"No cumple: {k}" for k, v in cumple.items() if not v] + ["Se conserva popularidad con los mismos filtros (predeclarado)."]
    return {"decision": decision, "estado_maximo": "ninguno" if decision == "rechazado" else "sombra", "sistema_conservado": sistema, "cumple": cumple, "motivos": motivos,
            "valores": {"hitrate1_modelo": m["hitrate1_universo"], "hitrate1_popularidad": p["hitrate1_universo"], "hitrate1_coocurrencia": res["coocurrencia"]["hitrate1_universo"],
                        "diferencia": dif, "ic95_diferencia": [boot["hitrate1"]["p2_5"], boot["hitrate1"]["p97_5"]],
                        "cobertura_modelo": m["cobertura_clientes"], "cobertura_popularidad": p["cobertura_clientes"], "universo": m["universo"]}}


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config, reglas, info = _leer(ejecucion / "config.json"), _leer(ejecucion / "reglas_compatibilidad.json"), _leer(ejecucion / "datos.json")
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = preparar(datos, config, reglas)
    if canon(ds["estadisticas"]) != canon(_leer(ejecucion / "estadisticas_por_corte.json")):
        raise ProtocoloError("Las estadísticas por corte no coinciden con las congeladas")
    bloque = ds["bloques"]["comprobacion_historica"]
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID) if cong["artefacto_huella"] else None
    res, evs = evaluar_bloque(bloque, art, ds["familias"])
    b = config["metricas"]["bootstrap"]
    boot = {"modelo_menos_popularidad": bootstrap(evs, "modelo", "popularidad", b["repeticiones"], b["semilla"]),
            "modelo_menos_coocurrencia": bootstrap(evs, "modelo", "coocurrencia", b["repeticiones"], b["semilla"])} if art else {}
    cont = conteos(bloque)
    decision = decidir(res, boot.get("modelo_menos_popularidad", {}), cont, config, art is not None)
    metricas = {"bloque": "comprobacion_historica", "alcance": "comprobación histórica EXPLORATORIA (datos sintéticos ya inspeccionados)",
                "universo": "clientes con historial al corte y horizonte observado; abstención = sin acierto", "conteos": cont, "resultados": res,
                "incertidumbre_bootstrap_clientes": boot, "soporte_ajuste": art.datos["soporte"] if art else None,
                "productos_sin_soporte": sorted(p for p, s in (art.datos["soporte"].items() if art else []) if s["positivos"] < art.datos["soporte_minimo"]),
                "control_familias": _leer(ejecucion / "control_familias.json"), "limitaciones": LIMITACIONES}
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"], candidato=cong["seleccion_elegido"],
               version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"], sello_congelacion=cong["sello"], origen_datos=config["origen_datos"],
               dimensiones={"integracion_tecnica": "contrato C2, sombra, API e interfaz implementados y probados (ver docs/modelo-venta-cruzada.md)",
                            "evidencia_predictiva": decision["decision"], "revision_comercial": "pendiente: ninguna revisión humana registrada en este protocolo",
                            "condiciones_piloto": ["revisión comercial >= 80 % pertinente entre casos evaluables", "reglas de compatibilidad empresariales",
                                                   "catálogo con fechas de vigencia", "registro de exposición, oferta, aceptación, compra y descarte"]},
               limitaciones=LIMITACIONES + ["Ningún modelo se promueve automáticamente; no se crean tareas."])
    pred = [dict(x, metodo=k) for k, v in evs.items() for x in v["filas"]]
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas), "decision.json": json_bytes(doc),
                "predicciones_comprobacion.csv": _csv(pred, ["metodo", "cliente_id", "corte", "n_candidatos", "n_sugeridos", "lista", "hit1", "hit3", "aciertos3", "ndcg3", "violaciones"])}
    marcador = publicar_lote(ejecucion, archivos, MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"]})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": _leer(ejecucion / "decision.json")}
