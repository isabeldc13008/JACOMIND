"""Segmentación RFM determinista y explicable (A05)."""

from __future__ import annotations

from decimal import Decimal
from math import sqrt
from typing import Iterable, Mapping


def _standardize(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [0.0 for _ in values]
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    deviation = sqrt(variance) or 1.0
    return [(value - mean) / deviation for value in values]


def preparar_rfm(rows: Iterable[Mapping[str, object]]) -> dict[str, tuple[float, float, float]]:
    materialized = list(rows)
    recency = _standardize([float(row["recencia_dias"]) for row in materialized])
    frequency = _standardize([float(row["frecuencia"]) for row in materialized])
    monetary = _standardize([float(Decimal(str(row["importe"]))) for row in materialized])
    return {str(row["cliente_id"]): (recency[index], frequency[index], monetary[index]) for index, row in enumerate(materialized)}


def _distance(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def segmentar_clientes(rows: Iterable[Mapping[str, object]], k: int = 3) -> dict[str, dict[str, object]]:
    materialized = list(rows)
    usable = [row for row in materialized if row.get("recencia_dias") is not None and int(row.get("frecuencia", 0)) > 0]
    result = {str(row["cliente_id"]): {"cliente_id": str(row["cliente_id"]), "segmento": "sin_historial", "version": "rfm-v1"} for row in materialized if row not in usable}
    if not usable:
        return result
    vectors = preparar_rfm(usable)
    count = min(max(1, k), len(usable))
    ordered_ids = sorted(vectors)
    centroids = [vectors[client_id] for client_id in ordered_ids[:count]]
    assignments: dict[str, int] = {}
    for _ in range(25):
        new_assignments = {client_id: min(range(count), key=lambda index: _distance(vector, centroids[index])) for client_id, vector in vectors.items()}
        if new_assignments == assignments:
            break
        assignments = new_assignments
        for index in range(count):
            members = [vectors[client_id] for client_id, assigned in assignments.items() if assigned == index]
            if members:
                centroids[index] = tuple(sum(vector[dimension] for vector in members) / len(members) for dimension in range(3))
    for client_id, assigned in assignments.items():
        result[client_id] = {"cliente_id": client_id, "segmento": f"seg_{assigned + 1}", "version": "rfm-v1", "centroide": centroids[assigned]}
    return result
