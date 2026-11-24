"""Políticas de orden del cupo (biblioteca estándar). Una única implementación para evaluación,
puntuación y piloto.

``fusion_rangos_recencia_v1`` (M1.2): dentro de un corte, ``rR`` = posición por menor recencia y
``rM`` = posición por mayor probabilidad del modelo (ambas con desempate por ``cliente_id``). Se ordena
por ``rR + rM``; los empates se resuelven por ``rR`` y luego por ``cliente_id``. No tiene parámetros.
El resultado es un ORDEN, no una probabilidad: no se publica como ``prob_compra_30d``.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

POLITICAS = {"fusion_rangos_recencia_v1"}


def posiciones_fusion(filas: list[Mapping[str, Any]], prob: Callable[[Mapping[str, Any]], float]) -> dict[str, int]:
    """Posición 1..n de cada ``cliente_id`` en un único corte según la fusión de rangos."""
    ids = [str(f["cliente_id"]) for f in filas]
    if len(set(ids)) != len(ids):
        raise ValueError("La fusión se calcula dentro de un corte: hay clientes repetidos")
    por_r = sorted(filas, key=lambda f: (f["recencia_dias"], str(f["cliente_id"])))
    por_m = sorted(filas, key=lambda f: (-prob(f), str(f["cliente_id"])))
    r_r = {str(f["cliente_id"]): i for i, f in enumerate(por_r, start=1)}
    r_m = {str(f["cliente_id"]): i for i, f in enumerate(por_m, start=1)}
    orden = sorted(ids, key=lambda c: (r_r[c] + r_m[c], r_r[c], c))
    return {c: i for i, c in enumerate(orden, start=1)}


def puntaje_por_corte(filas: list[Mapping[str, Any]], prob: Callable[[Mapping[str, Any]], float]) -> Callable[[Mapping[str, Any]], float]:
    """Puntaje compatible con ``metricas`` (mayor = antes) calculando la fusión por separado en cada corte."""
    grupos: dict[Any, list] = {}
    for f in filas:
        grupos.setdefault(f["corte"], []).append(f)
    pos = {(c, cid): p for c, g in grupos.items() for cid, p in posiciones_fusion(g, prob).items()}
    return lambda f: -float(pos[(f["corte"], str(f["cliente_id"]))])
