"""Métricas de ranking y probabilidad para compra a 30 días (biblioteca estándar).

Convenciones fijadas antes de evaluar:

* Orden: puntaje descendente y, en empate, ``cliente_id`` ascendente. Las métricas de
  ranking se calculan por corte (mes); el agregado es la media de los meses y también se
  publica la suma de aciertos.
* ``precision@K = aciertos / min(K, n)`` y ``sensibilidad@K = aciertos / positivos`` del mes
  (``None`` si el mes no tiene positivos).
* Average precision (AP): sobre ese mismo orden estricto,
  ``AP = (1/P) · Σ_{i: y_i = 1} precision@i``. Es la suma por escalones sin interpolar; en
  ausencia de empates coincide con ``sklearn.metrics.average_precision_score``.
* Brier: media de ``(p − y)²``. Calibración por diez bandas de ancho 0,1 (la última incluye 1).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping

METRICAS_VERSION = "m1-metricas-v1"  # orden con desempate por ID, min(K, n), AP por escalones, Brier, 10 bandas

Fila = Mapping[str, Any]


def ordenar(filas: Iterable[Fila], puntaje: Callable[[Fila], float]) -> list[Fila]:
    return sorted(filas, key=lambda f: (-puntaje(f), str(f["cliente_id"])))


def por_corte(filas: Iterable[Fila]) -> dict[Any, list[Fila]]:
    grupos: dict[Any, list[Fila]] = defaultdict(list)
    for f in filas:
        grupos[f["corte"]].append(f)
    return dict(sorted(grupos.items()))


def ranking_k(filas: list[Fila], puntaje: Callable[[Fila], float], k: int, etiqueta: str = "compra_30d") -> dict[str, Any]:
    orden = ordenar(filas, puntaje)
    n = len(orden)
    k_ef = min(k, n)
    positivos = sum(int(f[etiqueta]) for f in orden)
    aciertos = sum(int(f[etiqueta]) for f in orden[:k_ef])
    return {"k": k, "k_efectivo": k_ef, "n": n, "positivos": positivos, "aciertos": aciertos,
            "precision": aciertos / k_ef if k_ef else None, "sensibilidad": aciertos / positivos if positivos else None,
            "clientes": [str(f["cliente_id"]) for f in orden[:k_ef]]}


def average_precision(filas: list[Fila], puntaje: Callable[[Fila], float], etiqueta: str = "compra_30d") -> float | None:
    orden = ordenar(filas, puntaje)
    positivos = sum(int(f[etiqueta]) for f in orden)
    if not positivos:
        return None
    aciertos, suma = 0, 0.0
    for i, f in enumerate(orden, start=1):
        if int(f[etiqueta]):
            aciertos += 1
            suma += aciertos / i
    return suma / positivos


def average_precision_empates(filas: list[Fila], puntaje: Callable[[Fila], float], etiqueta: str = "compra_30d") -> float | None:
    """Average precision con las puntuaciones EMPATADAS como un solo umbral (misma definición que
    ``sklearn.metrics.average_precision_score``). ``average_precision`` (arriba) recorre el orden con desempate por
    ``cliente_id`` y coincide con esta solo sin empates; se conserva para no cambiar resultados ya publicados."""
    positivos = sum(int(f[etiqueta]) for f in filas)
    if not positivos:
        return None
    grupos: dict[float, list[int]] = defaultdict(list)
    for f in filas:
        grupos[puntaje(f)].append(int(f[etiqueta]))
    vistos = aciertos = 0
    suma = 0.0
    for p in sorted(grupos, reverse=True):
        g = grupos[p]
        vistos += len(g)
        nuevos = sum(g)
        aciertos += nuevos
        suma += (nuevos / positivos) * (aciertos / vistos)
    return suma


def brier(filas: list[Fila], prob: Callable[[Fila], float], etiqueta: str = "compra_30d") -> float | None:
    return sum((prob(f) - int(f[etiqueta])) ** 2 for f in filas) / len(filas) if filas else None


def calibracion(filas: list[Fila], prob: Callable[[Fila], float], bandas: int = 10, etiqueta: str = "compra_30d") -> list[dict[str, Any]]:
    grupos: dict[int, list[Fila]] = defaultdict(list)
    for f in filas:
        grupos[min(int(prob(f) * bandas), bandas - 1)].append(f)
    salida = []
    for b in range(bandas):
        g = grupos.get(b, [])
        salida.append({"banda": [round(b / bandas, 2), round((b + 1) / bandas, 2)], "n": len(g),
                       "prob_media": sum(prob(f) for f in g) / len(g) if g else None,
                       "tasa_observada": sum(int(f[etiqueta]) for f in g) / len(g) if g else None})
    return salida


def matriz(filas: Iterable[Fila], predice: Callable[[Fila], bool]) -> dict[str, Any]:
    tp = tn = fp = fn = 0
    for f in filas:
        y, p = int(f["compra_30d"]), bool(predice(f))
        tp += p and y; tn += (not p) and (not y); fp += p and not y; fn += (not p) and y
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"n": tp + tn + fp + fn, "TP": tp, "TN": tn, "FP": fp, "FN": fn, "precision": round(precision, 4),
            "recall": round(recall, 4), "F1": round(f1, 4), "seleccionados": tp + fp}


def resumen_ranking(filas: list[Fila], puntaje: Callable[[Fila], float], ks=(10, 20), etiqueta: str = "compra_30d") -> dict[str, Any]:
    """Por mes y agregado: precisión y sensibilidad a K, AP mensual y AP conjunta."""
    meses = []
    for corte, g in por_corte(filas).items():
        entrada = {"corte": corte.isoformat() if hasattr(corte, "isoformat") else corte, "n": len(g),
                   "clientes_unicos": len({f["cliente_id"] for f in g}),
                   "positivos": sum(int(f[etiqueta]) for f in g),
                   "negativos": sum(1 - int(f[etiqueta]) for f in g),
                   "average_precision": average_precision(g, puntaje, etiqueta)}
        for k in ks:
            entrada[f"top{k}"] = ranking_k(g, puntaje, k, etiqueta)
        meses.append(entrada)
    agregado: dict[str, Any] = {"meses": len(meses), "n": len(filas), "clientes_unicos": len({f["cliente_id"] for f in filas}),
                                "positivos": sum(int(f[etiqueta]) for f in filas)}
    for k in ks:
        precisiones = [m[f"top{k}"]["precision"] for m in meses if m[f"top{k}"]["precision"] is not None]
        sens = [m[f"top{k}"]["sensibilidad"] for m in meses if m[f"top{k}"]["sensibilidad"] is not None]
        agregado[f"precision_media_top{k}"] = sum(precisiones) / len(precisiones) if precisiones else None
        agregado[f"sensibilidad_media_top{k}"] = sum(sens) / len(sens) if sens else None
        agregado[f"aciertos_top{k}"] = sum(m[f"top{k}"]["aciertos"] for m in meses)
        agregado[f"denominador_top{k}"] = sum(m[f"top{k}"]["k_efectivo"] for m in meses)
    aps = [m["average_precision"] for m in meses if m["average_precision"] is not None]
    agregado["average_precision_media_mensual"] = sum(aps) / len(aps) if aps else None
    agregado["average_precision_conjunta"] = average_precision(list(filas), puntaje, etiqueta)
    return {"por_mes": meses, "agregado": agregado}


def resumen_probabilidad(filas: list[Fila], prob: Callable[[Fila], float], etiqueta: str = "compra_30d") -> dict[str, Any]:
    return {"brier": brier(filas, prob, etiqueta), "prob_media": sum(prob(f) for f in filas) / len(filas) if filas else None,
            "tasa_observada": sum(int(f[etiqueta]) for f in filas) / len(filas) if filas else None,
            "calibracion": calibracion(filas, prob, etiqueta=etiqueta)}


def bootstrap_clientes(filas: list[Fila], estadistico: Callable[[list[Fila]], float | None], repeticiones: int = 1000,
                       semilla: int = 20261123) -> dict[str, Any]:
    """Intervalo percentil 95 % remuestreando clientes completos (sus cortes no son independientes)."""
    import random

    por_cliente: dict[str, list[Fila]] = defaultdict(list)
    for f in filas:
        por_cliente[str(f["cliente_id"])].append(f)
    ids = sorted(por_cliente)
    rng = random.Random(semilla)
    valores = []
    for _ in range(repeticiones):
        muestra: list[Fila] = []
        for j, cid in enumerate(rng.choice(ids) for _ in ids):
            # Clientes repetidos se renombran para no fundir sus filas en el desempate.
            muestra.extend(dict(f, cliente_id=f"{cid}#{j:04d}") for f in por_cliente[cid])
        v = estadistico(muestra)
        if v is not None:
            valores.append(v)
    valores.sort()
    if not valores:
        return {"repeticiones": repeticiones, "validas": 0}
    return {"repeticiones": repeticiones, "validas": len(valores), "semilla": semilla,
            "p2_5": valores[int(0.025 * (len(valores) - 1))], "p97_5": valores[int(0.975 * (len(valores) - 1))],
            "media": sum(valores) / len(valores)}


def log_loss(filas: list[Fila], prob: Callable[[Fila], float], eps: float = 1e-15, etiqueta: str = "compra_30d") -> float | None:
    """Pérdida logarítmica media con probabilidades recortadas a [eps, 1 - eps] (añadida en M1.1)."""
    import math
    if not filas:
        return None
    total = 0.0
    for f in filas:
        p = min(max(prob(f), eps), 1 - eps)
        total += -math.log(p) if int(f[etiqueta]) else -math.log(1 - p)
    return total / len(filas)
