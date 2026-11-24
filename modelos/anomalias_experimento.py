"""M6 · Protocolo experimental de operaciones atípicas: preparación, control A02, referencia contextual, Isolation Forest
(scikit-learn, solo aquí), exportación JSON verificada, casos sembrados y controles negativos, selección en validación,
congelación y comprobación histórica exploratoria con decisión predeclarada (``m6-decision-v1``).

Separación temporal (``config.particion``): el bosque se ajusta SOLO con operaciones originales puntuables del
entrenamiento; configuración y desempate se eligen en validación (casos sembrados de validación); la selección se congela
(``congelacion.json``) antes de construir y medir la comprobación. Las referencias contextuales usan antecedentes
anteriores ya observados (política fija), nunca etiquetas futuras ni reajustes.

Los casos sembrados y controles negativos son copias con ID nuevo: no entran al historial, al entrenamiento ni a los
grupos de comparación de otras operaciones. Se insertan de uno en uno en el conjunto de originales de su universo y mes
para medir la detección a igual cupo (empates pesimistas).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import platform
import random
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from . import anomalias as A
from .ejecucion import EjecucionError, ahora_utc, canon, json_bytes, publicar_lote, sha, sha_archivo, verificar_lote

CONFIG = Path(__file__).resolve().parent / "config" / "anomalias.json"
BLOQUES = ("entrenamiento", "validacion", "comprobacion_historica")


class ProtocoloM6Error(ValueError):
    """La ejecución no respeta el protocolo congelado (alteración, datos distintos o evaluación sin congelar)."""


def cargar_config(ruta: str | Path | None = None) -> dict:
    c = json.loads(Path(ruta or CONFIG).read_text(encoding="utf-8"))
    if c.get("modelo_id") != A.MODELO_ID:
        raise ProtocoloM6Error(f"La configuración es de {c.get('modelo_id')}, no de {A.MODELO_ID}")
    return c


def bloque_de(d: date, config: Mapping) -> str | None:
    for b in BLOQUES:
        lo, hi = config["particion"][b]
        if date.fromisoformat(lo) <= d <= date.fromisoformat(hi):
            return b
    return None


# Preparación -----------------------------------------------------------------------------------------------------------
def preparar(datos, compras: list[dict], config: Mapping) -> dict:
    ops, excl = A.operaciones(datos.ventas, compras, datos.tasas, config)
    hist = A.Historial(ops, config["contexto"]["ventana_antecedentes"])
    ctx = {(o["tipo_operacion"], o["operacion_id"]): A.contexto(o, hist, config) for o in ops}
    return {"ops": ops, "excluidas": excl, "historial": hist, "contextos": ctx}


def diagnostico(datos, compras: list[dict], prep: Mapping, config: Mapping) -> dict:
    out: dict[str, Any] = {"revision_datos": datos.revision, "huella_datos": datos.huella_datos, "exclusiones_a01": datos.exclusiones,
                           "conteos_entrada": {"ventas": len(datos.ventas), "ventas_confirmadas": sum(v.get("estado") == "Confirmada" for v in datos.ventas),
                                               "ventas_anuladas": sum(v.get("estado") == "Anulada" for v in datos.ventas), "compras": len(compras)},
                           "rango_fechas": {"ventas": [min(v["fecha"] for v in datos.ventas).isoformat(), max(v["fecha"] for v in datos.ventas).isoformat()],
                                            "compras": [min(c["fecha"] for c in compras).isoformat(), max(c["fecha"] for c in compras).isoformat()] if compras else None},
                           "cobertura": {"venta": datos.cobertura.como_dict(), "compra": config["cobertura"]["compra"]},
                           "descuentos": {"valores_distintos": sorted({str(v.get("descuento_pct")) for v in datos.ventas}),
                                          "nota": "sin variación útil: no se afirma que el detector aprenda descuentos anómalos"},
                           "universos": {}}
    for u in A.UNIVERSOS:
        uo = [o for o in prep["ops"] if o["tipo_operacion"] == u]
        por_b = {}
        for b in BLOQUES + (None,):
            bo = [o for o in uo if A_bloque(o, config) == b]
            punt = [o for o in bo if prep["contextos"][(u, o["operacion_id"])]["estado"] == "puntuada"]
            por_b[b or "fuera_de_particion"] = {"validas": len(bo), "puntuadas": len(punt), "historia_insuficiente": len(bo) - len(punt)}
        ex: dict[str, int] = defaultdict(int)
        for e in prep["excluidas"]:
            if e["tipo_operacion"] == u:
                ex[e["motivo"]] += 1
        grupos = defaultdict(int)
        for o in uo:
            grupos[f"{o['producto_id']}|{o['moneda']}"] += 1
        out["universos"][u] = {"validas": len(uo), "excluidas": dict(ex), "por_bloque": por_b, "grupos": dict(sorted(grupos.items())),
                               "trm_ausente": sum(o["estado_trm"] == "ausente" for o in uo)}
    return out


def A_bloque(o: Mapping, config: Mapping) -> str | None:
    return bloque_de(o["fecha"], config)


# Control A02 -----------------------------------------------------------------------------------------------------------
def _a02_filas(datos) -> list[dict]:
    from pipeline.operaciones import _summarize
    s = _summarize(datos.ventas, datos.productos, datos.tasas, datos.observado_hasta)
    return [{"period": r["fecha"].strftime("%Y-%m"), "family": r["family"], "currency": r["currency"], "value": r["amount_cop"], "id": r["id"]}
            for r in s.rows if r.get("status") == "Confirmada"]


def control_a02(datos) -> dict:
    """Reproduce el detector A02 (``calcular_cierre`` sobre la revisión aceptada) y documenta su alcance."""
    from pipeline.operaciones import calcular_cierre, detectar_anomalias
    cierre = calcular_cierre(Path(datos.directorio), datos.observado_hasta)
    propio = detectar_anomalias(_a02_filas(datos))
    ids_c, ids_p = [a["id"] for a in cierre.anomalies], [a["id"] for a in propio]
    return {"alertas_cierre": len(ids_c), "alertas_reproducidas": len(ids_p), "coincide": ids_c == ids_p,
            "ventas_confirmadas_evaluadas": len(_a02_filas(datos)), "compras": "no cubiertas por A02",
            "parametros": {"min_history": 3, "threshold": 3}, "ids": ids_p}


class A02:
    """Regla A02 aplicada a una operación en la posición de su base (historia: ventas anteriores en orden (periodo, id))."""

    def __init__(self, datos):
        self.filas = sorted(_a02_filas(datos), key=lambda r: (r["period"], str(r["id"])))
        self.pos = {r["id"]: i for i, r in enumerate(self.filas)}
        self.fam = {str(p): str(v.get("familia_prueba", "DESCONOCIDA")) for p, v in datos.productos.items()}

    def alerta(self, base_id: str, producto_id: str, moneda: str, importe_cop: float | None) -> bool | None:
        from decimal import Decimal
        from statistics import median
        if importe_cop is None or base_id not in self.pos:
            return None
        fam = self.fam.get(producto_id, "DESCONOCIDA")
        prev = [r["value"] for r in self.filas[:self.pos[base_id]] if r["family"] == fam and r["currency"] == moneda]
        if len(prev) < 3:
            return False
        med = Decimal(str(median(prev)))
        mad = Decimal(str(median([abs(x - med) for x in prev])))
        v = Decimal(str(round(importe_cop, 2)))
        return bool(abs(v - med) > 3 * mad if mad else v != med)


# Isolation Forest: ajuste y exportación -----------------------------------------------------------------------------------
def matriz(ops: list[dict], contextos: Mapping, variables: list[str]) -> tuple[list[list[float]], list[dict]]:
    filas, usadas = [], []
    for o in ops:
        c = contextos[(o["tipo_operacion"], o["operacion_id"])]
        if c["estado"] == "puntuada":
            filas.append([c["variables"][v] for v in variables])
            usadas.append(o)
    return filas, usadas


def ajustar(X: list[list[float]], conf: Mapping, cand: Mapping):
    import numpy as np
    from sklearn.ensemble import IsolationForest
    m = IsolationForest(n_estimators=int(cand["n_estimadores"]), max_samples=min(int(conf["max_muestras"]), len(X)),
                        max_features=float(cand["max_features"]), bootstrap=bool(cand["bootstrap"]), random_state=int(cand["semilla"]))
    return m.fit(np.asarray(X, dtype=float))


def exportar(m, variables: list[str], X_shape1: int) -> dict:
    sub = m._max_features != X_shape1
    arboles = []
    for est, feats in zip(m.estimators_, m.estimators_features_):
        t = est.tree_
        izq, der = [int(x) for x in t.children_left], [int(x) for x in t.children_right]
        arboles.append({"var": [(int(feats[f]) if sub else int(f)) if i != -1 else 0 for f, i in zip(t.feature, izq)],
                        "umbral": [float(x) if i != -1 else 0.0 for x, i in zip(t.threshold, izq)],
                        "izq": izq, "der": der, "n": [int(x) for x in t.n_node_samples]})
    return {"variables": list(variables), "n_estimadores": len(arboles), "max_muestras": int(m.max_samples_), "arboles": arboles}


def _vecinos_f32(t: float) -> list[float]:
    import struct
    b = struct.unpack("<i", struct.pack("<f", t))[0]
    return [struct.unpack("<f", struct.pack("<i", b + d))[0] for d in (-1, 1)]


def puntos_equivalencia(X: list[list[float]], export: Mapping, zmax: float, semilla: int) -> dict[str, list[list[float]]]:
    """Casos reales, constantes, extremos y valores en/junto a umbrales de los árboles."""
    k = len(export["variables"])
    rng = random.Random(semilla)
    cerca = []
    for a in export["arboles"][:40]:
        for n in range(len(a["izq"])):
            if a["izq"][n] != -1 and rng.random() < 0.5:
                base = list(X[rng.randrange(len(X))])
                t = a["umbral"][n]
                for v in [t] + _vecinos_f32(t) + [t - 1e-9, t + 1e-9]:
                    p = list(base)
                    p[a["var"][n]] = v
                    cerca.append(p)
    return {"reales": X, "constantes": [[0.0] * k, [1.0] * k, [-1.0] * k, [2.5] * k],
            "extremos": [[s * zmax] * k for s in (1, -1)] + [[zmax if i == j else 0.0 for i in range(k)] for j in range(k)] + [[-zmax if i == j else 0.0 for i in range(k)] for j in range(k)],
            "cerca_de_umbrales": cerca}


def equivalencia(m, export: Mapping, puntos: Mapping[str, list[list[float]]], tolerancia: float, politica: Mapping) -> dict:
    import numpy as np
    b = A.Bosque(export)
    out, ok = {}, True
    for nombre, P in puntos.items():
        sk = (-m.score_samples(np.asarray(P, dtype=float))).tolist()
        js = [b.rareza(p) for p in P]
        dif = max(abs(x - y) for x, y in zip(sk, js)) if P else 0.0
        orden_sk = sorted(range(len(P)), key=lambda i: (-sk[i], i))
        orden_js = sorted(range(len(P)), key=lambda i: (-js[i], i))
        k = A.cupo(len(P), politica)
        al_ok = set(orden_sk[:k]) == set(orden_js[:k])
        out[nombre] = {"n": len(P), "max_diferencia_absoluta": dif, "ranking_identico": orden_sk == orden_js, "alertas_identicas": al_ok}
        ok = ok and dif <= tolerancia and orden_sk == orden_js and al_ok
    return {"tolerancia_absoluta": tolerancia, "equivalente": ok, "conjuntos": out}


# Casos sembrados y controles negativos -----------------------------------------------------------------------------------
def _recalcular(op: dict) -> dict:
    op["importe_origen"] = round(op["cantidad"] * op["valor_unitario"] * (1 - op["descuento_pct"] / 100), 6)
    op["importe_cop"] = round(op["importe_origen"] if op["moneda"] == "COP" else op["importe_origen"] * op["trm"], 2) if (op["moneda"] == "COP" or op["trm"]) else None
    return op


def _tipicos(u: str, moneda: str, fecha: date, prep: Mapping, config: Mapping) -> list[tuple[str, float, float]]:
    """(producto, valor de referencia, cantidad de referencia) de los grupos del universo y moneda con soporte suficiente."""
    from statistics import median
    out = []
    prods = sorted({o["producto_id"] for o in prep["ops"] if o["tipo_operacion"] == u and o["moneda"] == moneda})
    for p in prods:
        ant = prep["historial"].antecedentes((u, p, moneda, A.unidad(p, config)), fecha)
        if len(ant) >= int(config["contexto"]["min_antecedentes"]):
            out.append((p, math.exp(median(a[1][1] for a in ant)), math.exp(median(a[1][0] for a in ant))))
    return out


def casos(prep: Mapping, config: Mapping, bloque: str) -> list[dict]:
    """Copias con ID nuevo, trazables a su base; nunca se añaden al historial ni al entrenamiento."""
    cs = config["casos_sembrados"]
    out = []
    for u in A.UNIVERSOS:
        pob = sorted([o for o in prep["ops"] if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == bloque
                      and prep["contextos"][(u, o["operacion_id"])]["estado"] == "puntuada"], key=lambda o: o["operacion_id"])
        semilla = f"{cs['semilla']}:{u}:{bloque}"
        bases = random.Random(semilla).sample(pob, min(int(cs["bases_por_bloque"][u]), len(pob)))
        for base in sorted(bases, key=lambda o: o["operacion_id"]):
            comun = {"base": {"tipo_operacion": u, "operacion_id": base["operacion_id"]}, "bloque": bloque, "semilla": semilla}
            for tipo, por_bloque in cs["tipos"][u].items():
                clave_b = "validacion" if bloque == "validacion" else "comprobacion"
                for inten in por_bloque[clave_b]:
                    op = copy.deepcopy(base)
                    if tipo in ("precio_elevado", "costo_alterado"):
                        op["valor_unitario"] = round(base["valor_unitario"] * inten, 6)
                    elif tipo == "cantidad_extrema":
                        op["cantidad"] = float(max(1, round(base["cantidad"] * inten)))
                    else:
                        pf, qf = inten
                        op["valor_unitario"] = round(base["valor_unitario"] * pf, 6)
                        op["cantidad"] = float(max(1, round(base["cantidad"] * qf)))
                    etiqueta = "x".join(f"{x:g}" for x in (inten if isinstance(inten, list) else [inten]))
                    op["operacion_id"] = f"SEM-{bloque[:4].upper()}-{base['operacion_id']}-{tipo}-{etiqueta}"
                    out.append(dict(comun, caso_id=op["operacion_id"], clase="anomalia_sembrada", transformacion=tipo, intensidad=inten,
                                    etiqueta_sintetica="anomalia", motivo=f"{tipo} ×{etiqueta} sobre {base['operacion_id']}", op=_recalcular(op)))
            out.extend(_controles(base, comun, prep, config, bloque))
    return out


def _controles(base: dict, comun: dict, prep: Mapping, config: Mapping, bloque: str) -> list[dict]:
    neg = config["casos_sembrados"]["controles_negativos"]
    u, out = base["tipo_operacion"], []

    def caso(tipo: str, op: dict, motivo: str) -> dict:
        op["operacion_id"] = f"CTL-{bloque[:4].upper()}-{base['operacion_id']}-{tipo}"
        return dict(comun, caso_id=op["operacion_id"], clase="control_negativo", transformacion=tipo, intensidad=None,
                    etiqueta_sintetica="normal_construido", motivo=motivo, op=_recalcular(op))
    if base["moneda"] == "USD" and base["trm"]:
        op = copy.deepcopy(base)
        op["trm"] = round(base["trm"] * neg["cambio_trm"]["factor_trm"], 6)
        out.append(caso("cambio_trm", op, f"Solo cambia la TRM (×{neg['cambio_trm']['factor_trm']}); precio y cantidad de origen iguales"))
    tip = _tipicos(u, base["moneda"], base["fecha"], prep, config)
    if tip:
        p, val, cant = max(tip, key=lambda t: t[1])
        op = copy.deepcopy(base)
        op.update(producto_id=p, unidad=A.unidad(p, config), valor_unitario=round(val, 6), cantidad=float(max(1, round(cant))))
        out.append(caso("producto_mas_costoso", op, f"Producto habitualmente más costoso ({p}) con su valor y cantidad de referencia"))
        otros = [t for t in tip if t[0] != base["producto_id"]]
        if otros:
            idx = sum(map(ord, base["operacion_id"])) % len(otros)
            p, val, cant = otros[idx]
            op = copy.deepcopy(base)
            op.update(producto_id=p, unidad=A.unidad(p, config), valor_unitario=round(val, 6), cantidad=float(max(1, round(cant))))
            out.append(caso("cambio_mezcla", op, f"Cambio legítimo de mezcla: {base['producto_id']} → {p} con valores habituales"))
    c = prep["contextos"][(u, base["operacion_id"])]
    op = copy.deepcopy(base)
    op["cantidad"] = float(max(1, round(c["percentil_90_cantidad"])))
    out.append(caso("volumen_alto_habitual", op, f"Cantidad en el percentil 90 habitual del grupo ({op['cantidad']:g})"))
    return out


# Puntuación de bloques -----------------------------------------------------------------------------------------------------
def puntajes(metodo: str, bosque: A.Bosque | None, variables: list[str] | None, c: Mapping) -> float | None:
    if c["estado"] != "puntuada":
        return None
    if metodo == "mediana_mad":
        return A.puntaje_referencia(c["variables"])
    return bosque.rareza([c["variables"][v] for v in variables])


def conjunto(prep: Mapping, config: Mapping, bloque: str, u: str, metodo: str, bosque=None, variables=None) -> dict[str, list[float]]:
    """Puntajes de los originales puntuados del bloque, por mes."""
    por: dict[str, list[float]] = defaultdict(list)
    for o in prep["ops"]:
        if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == bloque:
            s = puntajes(metodo, bosque, variables, prep["contextos"][(u, o["operacion_id"])])
            if s is not None:
                por[A.periodo(o["fecha"])].append(s)
    return dict(por)


def detectado(s: float | None, pool: list[float], politica: Mapping) -> bool | None:
    if s is None:
        return None
    rango = 1 + sum(1 for x in pool if x >= s)  # empates pesimistas: el original igual se ordena delante
    return rango <= A.cupo(len(pool), politica)


def evaluar_metodo(prep: Mapping, config: Mapping, cs: list[dict], bloque: str, u: str, metodo: str, bosque=None, variables=None, a02: A02 | None = None) -> dict:
    pol = config["politica_alertas"]
    pools = conjunto(prep, config, bloque, u, metodo, bosque, variables)
    res = []
    for c in cs:
        if c["base"]["tipo_operacion"] != u:
            continue
        ctx = A.contexto(c["op"], prep["historial"], config)
        s = puntajes(metodo, bosque, variables, ctx)
        base_s = puntajes(metodo, bosque, variables, prep["contextos"][(u, c["base"]["operacion_id"])])
        r = {"caso_id": c["caso_id"], "base": c["base"]["operacion_id"], "clase": c["clase"], "transformacion": c["transformacion"],
             "intensidad": c["intensidad"], "puntaje": s, "puntaje_base": base_s, "estado": ctx["estado"],
             "detectado": detectado(s, pools.get(A.periodo(c["op"]["fecha"]), []), pol)}
        if a02 is not None and u == "venta":
            r["a02"] = a02.alerta(c["base"]["operacion_id"], c["op"]["producto_id"], c["op"]["moneda"], c["op"]["importe_cop"])
        res.append(r)
    sem = [r for r in res if r["clase"] == "anomalia_sembrada"]
    neg = [r for r in res if r["clase"] == "control_negativo"]
    sem_ok = [r for r in sem if r["detectado"] is not None]

    def tasa(rs):
        n = len(rs)
        return {"numerador": sum(bool(r["detectado"]) for r in rs), "denominador": n, "tasa": round(sum(bool(r["detectado"]) for r in rs) / n, 6) if n else None}
    por_tipo = defaultdict(list)
    for r in sem_ok:
        por_tipo[f"{r['transformacion']}|{json.dumps(r['intensidad'])}"].append(r)
    neg_por = defaultdict(list)
    for r in neg:
        if r["detectado"] is not None:
            neg_por[r["transformacion"]].append(r)
    n_val = sum(1 for o in prep["ops"] if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == bloque)
    alertas = sum(A.cupo(len(p), pol) for p in pools.values())
    trm = [r for r in neg if r["transformacion"] == "cambio_trm"]
    return {"metodo": metodo, "deteccion": tasa(sem_ok), "abstenciones_sembradas": len(sem) - len(sem_ok),
            "por_tipo_intensidad": {k: tasa(v) for k, v in sorted(por_tipo.items())},
            "combinacion_moderada": tasa([r for r in sem_ok if r["transformacion"] == "combinacion_moderada"]),
            "controles_negativos": {"alertas": tasa([r for r in neg if r["detectado"] is not None]), "por_tipo": {k: tasa(v) for k, v in sorted(neg_por.items())},
                                    "cambio_trm_puntaje_identico": {"identicos": sum(r["puntaje"] == r["puntaje_base"] for r in trm), "total": len(trm)}},
            "originales": {"validas": n_val, "puntuadas": sum(len(p) for p in pools.values()), "alertas_cupo": alertas,
                           "alertas_por_100_validas": round(100 * alertas / n_val, 4) if n_val else None,
                           "cobertura_puntuacion": round(sum(len(p) for p in pools.values()) / n_val, 6) if n_val else None},
            "casos": res}


def bootstrap(cand: list[dict], ref: list[dict], config: Mapping) -> dict:
    """IC de la diferencia de detección (candidato − referencia) remuestreando OPERACIONES BASE (clústeres)."""
    b = config["evaluacion"]["bootstrap"]
    porb: dict[str, list[tuple[bool, bool]]] = defaultdict(list)
    rmap = {r["caso_id"]: r for r in ref}
    for c in cand:
        r = rmap.get(c["caso_id"])
        if c["clase"] == "anomalia_sembrada" and c["detectado"] is not None and r and r["detectado"] is not None:
            porb[c["base"]].append((bool(c["detectado"]), bool(r["detectado"])))
    bases = sorted(porb)
    if not bases:
        return {"diferencia": None, "ic95": None, "bases": 0, "motivo": "sin casos sembrados comparables"}
    def dif(bs):
        xs = [x for bb in bs for x in porb[bb]]
        return sum(a for a, _ in xs) / len(xs) - sum(r for _, r in xs) / len(xs)
    rng = random.Random(b["semilla"])
    reps = sorted(dif([rng.choice(bases) for _ in bases]) for _ in range(int(b["replicas"])))
    a = (1 - b["nivel"]) / 2
    return {"diferencia": round(dif(bases), 6), "ic95": [round(reps[int(a * len(reps))], 6), round(reps[min(len(reps) - 1, int((1 - a) * len(reps)))], 6)],
            "bases": len(bases), "casos": sum(len(v) for v in porb.values()), "replicas": int(b["replicas"]), "agrupacion": b["agrupacion"]}


# Entrenamiento, selección y congelación ----------------------------------------------------------------------------------
def _versiones() -> dict:
    import numpy
    import sklearn
    return {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "numpy": numpy.__version__}


def _codigo() -> dict:
    d = Path(__file__).resolve().parent
    return {n: sha_archivo(d / n) for n in ("anomalias.py", "anomalias_experimento.py")}


def entrenar(datos, config: Mapping, salida: str | Path, compras: list[dict] | None = None) -> dict:
    compras = A.cargar_compras(datos) if compras is None else compras
    prep = preparar(datos, compras, config)
    cand_cfg = config["candidato"]
    zmax = float(config["contexto"]["z_max"])
    pol = config["politica_alertas"]
    cs_val = casos(prep, config, "validacion")
    a02 = A02(datos)
    universos, equivalencias, validacion, seleccion = {}, {}, {}, {}
    for u in A.UNIVERSOS:
        tr = [o for o in prep["ops"] if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == "entrenamiento"]
        ref = evaluar_metodo(prep, config, cs_val, "validacion", u, "mediana_mad", a02=a02)
        validacion[u] = {"referencia": _sin_casos(ref)}
        X0, _ = matriz(tr, prep["contextos"], list(A.VARIABLES))
        if len(X0) < int(cand_cfg["min_entrenamiento"]):
            seleccion[u] = {"estado": "candidato_en_abstencion", "elegido": None, "filas_entrenamiento": len(X0),
                            "motivo": f"{len(X0)} filas utilizables (< {cand_cfg['min_entrenamiento']}): se conserva la referencia"}
            universos[u] = {"metodo": "mediana_mad", "config_id": None, "soporte_entrenamiento": len(X0)}
            continue
        resultados, exportados = {}, {}
        for conf in cand_cfg["configuraciones"]:
            vs = config["variables"]["conjuntos"][conf["variables"]]
            X, _ = matriz(tr, prep["contextos"], vs)
            m = ajustar(X, conf, cand_cfg)
            exp = exportar(m, vs, len(vs))
            eq = equivalencia(m, exp, puntos_equivalencia(X, exp, zmax, cand_cfg["semilla"]), cand_cfg["equivalencia"]["tolerancia_absoluta"], pol)
            Xv, _ = matriz([o for o in prep["ops"] if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == "validacion"], prep["contextos"], vs)
            eqv = equivalencia(m, exp, {"validacion": Xv}, cand_cfg["equivalencia"]["tolerancia_absoluta"], pol)
            eq["equivalente"] = eq["equivalente"] and eqv["equivalente"]
            eq["conjuntos"].update(eqv["conjuntos"])
            equivalencias[f"{u}:{conf['id']}"] = eq
            if not eq["equivalente"]:
                raise ProtocoloM6Error(f"{u}:{conf['id']}: la inferencia JSON no es equivalente a scikit-learn ({eq['conjuntos']}); no se publica un exportador aproximado")
            r = evaluar_metodo(prep, config, cs_val, "validacion", u, "isolation_forest", A.Bosque(exp), vs)
            resultados[conf["id"]] = r
            exportados[conf["id"]] = (exp, conf, len(X))
        orden = {c["id"]: c["orden"] for c in cand_cfg["configuraciones"]}
        elegido = sorted(resultados, key=lambda k: (-(resultados[k]["deteccion"]["tasa"] or 0), -(resultados[k]["combinacion_moderada"]["tasa"] or 0),
                                                      resultados[k]["controles_negativos"]["alertas"]["tasa"] or 0, orden[k]))[0]
        exp, conf, n = exportados[elegido]
        validacion[u]["candidatos"] = {k: _sin_casos(v) for k, v in resultados.items()}
        seleccion[u] = {"estado": "seleccionada", "elegido": elegido, "filas_entrenamiento": n, "criterio": config["seleccion"],
                        "validacion_deteccion": {k: v["deteccion"] for k, v in resultados.items()}}
        universos[u] = dict(exp, metodo="isolation_forest", config_id=elegido, semilla=cand_cfg["semilla"], soporte_entrenamiento=n,
                            contamination_no_usada=True)
    art = {"formato": A.FORMATO, "modelo_id": A.MODELO_ID, "version_protocolo": config["version_protocolo"], "umbral": None,
           "disponible_desde": config["fijado_en"], "origen_datos": config["origen_datos"],
           "contexto": config["contexto"], "referencia": config["referencia"], "politica_alertas": pol, "etiquetas_universos": config["universos"],
           "unidades": config["unidades"], "universos": universos, "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
           "puntaje": "rareza = 2^(−E[h(x)]/c(max_muestras)); mayor = más raro; no es probabilidad",
           "convenciones_numericas": {"entrada": "float32 antes de recorrer los árboles (como scikit-learn)", "division": "x[var] <= umbral va a la izquierda",
                                      "hoja": "profundidad (raíz = 1) + c(n_hoja) − 1"}}
    art["version"] = "m6-" + sha(canon({k: v for k, v in art.items()}).encode())[:10]
    from .inferencia import huella_artefacto
    art["huella"] = huella_artefacto(art)
    errores = A.validar_artefacto_anomalias(art)
    if errores:
        raise ProtocoloM6Error("Artefacto inválido: " + "; ".join(errores))
    diag = diagnostico(datos, compras, prep, config)
    archivos = {"config.json": json_bytes(config), "datos.json": json_bytes(dict(datos.descripcion(), compras=len(compras))),
                "preparacion.json": json_bytes(diag), "control_a02.json": json_bytes(control_a02(datos)),
                "casos_validacion.json": json_bytes([_caso_pub(c) for c in cs_val]), "validacion.json": json_bytes(validacion),
                "equivalencia.json": json_bytes(equivalencias), "seleccion.json": json_bytes(seleccion), "artefacto.json": json_bytes(art)}
    meta = {"modelo_id": A.MODELO_ID, "version_protocolo": config["version_protocolo"], "artefacto_version": art["version"], "artefacto_huella": art["huella"],
            "huella_seleccion": sha(archivos["seleccion.json"]), "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "versiones": _versiones(), "codigo": _codigo(), "estado": "congelado_antes_de_la_comprobacion"}
    marc = publicar_lote(salida, archivos, "congelacion.json", meta, volatiles={"fecha_congelacion": ahora_utc()})
    return {"seleccion": seleccion, "validacion": validacion, "equivalencia": equivalencias, "artefacto": art, "congelacion": marc, "diagnostico": diag}


def _sin_casos(r: Mapping) -> dict:
    return {k: v for k, v in r.items() if k != "casos"}


def _caso_pub(c: Mapping) -> dict:
    op = dict(c["op"], fecha=c["op"]["fecha"].isoformat())
    return {k: v for k, v in c.items() if k != "op"} | {"op": op}


def verificar_congelacion(ejecucion: str | Path) -> dict:
    d = Path(ejecucion)
    try:
        m = verificar_lote(d, "congelacion.json", ProtocoloM6Error)
    except EjecucionError as exc:
        raise ProtocoloM6Error(str(exc)) from exc
    art = json.loads((d / "artefacto.json").read_text(encoding="utf-8"))
    from .inferencia import huella_artefacto
    if art.get("huella") != m["artefacto_huella"] or huella_artefacto(art) != art.get("huella"):
        raise ProtocoloM6Error("El artefacto no coincide con el congelado")
    sel = json.loads((d / "seleccion.json").read_text(encoding="utf-8"))
    for u, s in sel.items():
        if (s.get("elegido") or None) != art["universos"][u].get("config_id"):
            raise ProtocoloM6Error(f"{u}: la selección no coincide con el artefacto congelado")
    return m


# Comprobación histórica y decisión -----------------------------------------------------------------------------------------
def decidir(u: str, sel: Mapping, cand: Mapping | None, ref: Mapping, boot: Mapping | None, config: Mapping) -> dict:
    rd = config["regla_decision"]
    meta = float(rd["meta_deteccion"])
    base = {"universo": u, "regla": rd["id"], "estado_maximo": "favorable_demostracion_sombra (sin promoción operativa)", "origen_datos": config["origen_datos"]}
    if cand is None:
        return dict(base, decision="referencia_conservada", sistema_conservado="mediana_mad", motivos=[sel.get("motivo", "candidato en abstención")], cumple={})
    dc, dr = cand["deteccion"]["tasa"], ref["deteccion"]["tasa"]
    nc, nr = cand["controles_negativos"]["alertas"]["tasa"] or 0.0, ref["controles_negativos"]["alertas"]["tasa"] or 0.0
    trm = cand["controles_negativos"]["cambio_trm_puntaje_identico"]
    cumple = {"meta_deteccion_candidato": dc is not None and dc >= meta, "meta_deteccion_referencia": dr is not None and dr >= meta,
              "supera_referencia_ic": bool(boot and boot.get("ic95") and boot["diferencia"] > 0 and boot["ic95"][0] > 0),
              "controles_negativos_no_peores": nc <= nr, "trm_sin_cambio": trm["identicos"] == trm["total"]}
    valores = {"deteccion_candidato": dc, "deteccion_referencia": dr, "diferencia": boot.get("diferencia") if boot else None,
               "ic95": boot.get("ic95") if boot else None, "alertas_controles_candidato": nc, "alertas_controles_referencia": nr}
    if all(cumple[k] for k in ("meta_deteccion_candidato", "supera_referencia_ic", "controles_negativos_no_peores", "trm_sin_cambio")):
        return dict(base, decision="favorable_demostracion_sombra", sistema_conservado="isolation_forest", cumple=cumple, valores=valores,
                    motivos=["El candidato supera a la referencia a igual cupo en casos sembrados; solo evidencia sintética: demostración en sombra"])
    if not cumple["meta_deteccion_candidato"] and not cumple["meta_deteccion_referencia"]:
        return dict(base, decision="inconcluso", sistema_conservado="mediana_mad", cumple=cumple, valores=valores,
                    motivos=[f"Ni candidato ({dc}) ni referencia ({dr}) alcanzan la meta de detección {meta}"])
    mot = []
    if not cumple["supera_referencia_ic"]:
        mot.append("El candidato no supera a la referencia a igual cupo con un IC95 por encima de 0 (agrupado por base)")
    if not cumple["meta_deteccion_candidato"]:
        mot.append(f"Detección del candidato {dc} < meta {meta}")
    if not cumple["controles_negativos_no_peores"]:
        mot.append(f"Más alertas en controles negativos que la referencia ({nc} > {nr})")
    if not cumple["trm_sin_cambio"]:
        mot.append("Un cambio exclusivo de TRM modificó el puntaje")
    return dict(base, decision="referencia_conservada", sistema_conservado="mediana_mad", cumple=cumple, valores=valores, motivos=mot)


def evaluar(ejecucion: str | Path, datos, compras: list[dict] | None = None) -> dict:
    d = Path(ejecucion)
    cong = verificar_congelacion(d)
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloM6Error("Los datos no son la revisión congelada (huella distinta): no se evalúa")
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    art = json.loads((d / "artefacto.json").read_text(encoding="utf-8"))
    sel = json.loads((d / "seleccion.json").read_text(encoding="utf-8"))
    compras = A.cargar_compras(datos) if compras is None else compras
    prep = preparar(datos, compras, config)
    cs = casos(prep, config, "comprobacion_historica")
    a02 = A02(datos)
    metricas, decisiones, detalle = {}, {}, {}
    for u in A.UNIVERSOS:
        ref = evaluar_metodo(prep, config, cs, "comprobacion_historica", u, "mediana_mad", a02=a02)
        s = art["universos"][u]
        cand = evaluar_metodo(prep, config, cs, "comprobacion_historica", u, "isolation_forest", A.Bosque(s), s["variables"]) if s["metodo"] == "isolation_forest" else None
        boot = bootstrap(cand["casos"], ref["casos"], config) if cand else None
        a02_sem = [r.get("a02") for r in ref["casos"] if r["clase"] == "anomalia_sembrada" and r.get("a02") is not None]
        a02_trm = [r for r in ref["casos"] if r["transformacion"] == "cambio_trm" and r.get("a02") is not None]
        metricas[u] = {"referencia": _sin_casos(ref), "candidato": _sin_casos(cand) if cand else None, "bootstrap": boot,
                       "control_a02": ({"deteccion_sembradas_bandera": {"numerador": sum(a02_sem), "denominador": len(a02_sem)},
                                        "cambio_trm_con_alerta_a02": {"numerador": sum(r["a02"] for r in a02_trm), "denominador": len(a02_trm)},
                                        "nota": "Bandera A02 (familia, moneda, importe COP; sin cupo): control de compatibilidad, no comparación a igual cupo"}
                                       if u == "venta" else {"nota": "A02 no cubre compras"}),
                       "revision_humana": {"originales_revisadas": 0, "originales_sin_revisar": metricas_pendientes(prep, config, u),
                                           "precision_primeras_n": None, "falsas_alertas_por_100_normales": None,
                                           "motivo": "0 revisiones humanas reales: precisión comercial y falsas alertas no son estimables"}}
        decisiones[u] = decidir(u, sel[u], cand, ref, boot, config)
        detalle[u] = {"referencia": ref["casos"], "candidato": cand["casos"] if cand else None}
    casos_pub = [_caso_pub(c) for c in cs]
    decision = {"decisiones": decisiones, "artefacto_huella": cong["artefacto_huella"], "version_protocolo": config["version_protocolo"],
                "sello_congelacion": cong["sello"], "origen_datos": config["origen_datos"],
                "alcance": "comprobación histórica EXPLORATORIA (datos sintéticos ya inspeccionados); no es piloto prospectivo"}
    archivos = {"casos_comprobacion.json": json_bytes(casos_pub), "comprobacion.json": json_bytes(metricas),
                "detalle_casos.json": json_bytes(detalle), "decision.json": json_bytes(decision)}
    marc = publicar_lote(d, archivos, "evaluacion.json", {"modelo_id": A.MODELO_ID, "sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"]},
                         volatiles={"fecha_evaluacion": ahora_utc()})
    return {"metricas": metricas, "decision": decision, "evaluacion": marc}


def metricas_pendientes(prep: Mapping, config: Mapping, u: str) -> int:
    return sum(1 for o in prep["ops"] if o["tipo_operacion"] == u and bloque_de(o["fecha"], config) == "comprobacion_historica")


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    d = Path(ejecucion)
    cong = verificar_congelacion(d)
    try:
        ev = verificar_lote(d, "evaluacion.json", ProtocoloM6Error)
    except EjecucionError as exc:
        raise ProtocoloM6Error(str(exc)) from exc
    if ev.get("sello_congelacion") != cong["sello"]:
        raise ProtocoloM6Error("La evaluación no corresponde a la congelación vigente")
    dec = json.loads((d / "decision.json").read_text(encoding="utf-8"))
    if dec.get("artefacto_huella") != cong["artefacto_huella"]:
        raise ProtocoloM6Error("La decisión corresponde a otro artefacto")
    return {"decision": dec, "evaluacion": ev, "congelacion": cong}
