"""Modelo temporal reproducible de propensión de compra a 30 días (A04)."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Mapping

from .operaciones import _load


FIELDS = ["recencia_dias", "frecuencia_30d", "frecuencia_90d", "historial_n"]


def _month_end(year: int, month: int) -> date:
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return next_month - timedelta(days=1)


def _cuts() -> list[date]:
    return [_month_end(year, month) for year in (2025, 2026) for month in range(1, 13) if date(year, month, 1) >= date(2025, 3, 1) and _month_end(year, month) <= date(2026, 9, 30)]


def construir_fotografias(clients: Iterable[Mapping[str, object]], sales: Iterable[Mapping[str, object]], cutoff: date, label_cutoff: date | None = None) -> list[dict[str, object]]:
    history: dict[str, list[date]] = defaultdict(list)
    for sale in sales:
        if sale.get("estado", "Confirmada") == "Confirmada":
            history[str(sale["cliente_id"])].append(sale["fecha"])
    output: list[dict[str, object]] = []
    for client in clients:
        client_id = str(client["cliente_id"])
        if client["fecha_alta"] > cutoff:
            continue
        observed = sorted(day for day in history[client_id] if day <= cutoff)
        recency = (cutoff - observed[-1]).days if observed else 730
        future_end = label_cutoff or cutoff + timedelta(days=30)
        label = int(any(cutoff < day <= future_end for day in history[client_id]))
        output.append({"cliente_id": client_id, "corte": cutoff, "recencia_dias": recency, "frecuencia_30d": sum(0 <= (cutoff - day).days < 30 for day in observed), "frecuencia_90d": sum(0 <= (cutoff - day).days < 90 for day in observed), "historial_n": len(observed), "compra_30d": label, "historial_fechas": observed})
    return output


def _all_snapshots(clients: list[Mapping[str, object]], sales: list[Mapping[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for cut in _cuts():
        rows.extend(construir_fotografias(clients, sales, cut))
    return rows


def _vector(row: Mapping[str, object], means: list[float], deviations: list[float]) -> list[float]:
    return [1.0] + [(float(row[field]) - mean) / deviation for field, mean, deviation in zip(FIELDS, means, deviations)]


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def _fit(train: list[dict[str, object]]) -> tuple[list[float], list[float], list[float]]:
    means = [statistics.mean(float(row[field]) for row in train) for field in FIELDS]
    deviations = [statistics.pstdev(float(row[field]) for row in train) or 1 for field in FIELDS]
    weights = [0.0] * (len(FIELDS) + 1)
    for _ in range(600):
        gradient = [0.0] * len(weights)
        for row in train:
            vector = _vector(row, means, deviations)
            error = _sigmoid(sum(weight * value for weight, value in zip(weights, vector))) - int(row["compra_30d"])
            for index, value in enumerate(vector):
                gradient[index] += error * value
        weights = [weight - 0.1 * (gradient[index] / len(train) + (0.001 * weight if index else 0)) for index, weight in enumerate(weights)]
    return means, deviations, weights


def _probability(row: Mapping[str, object], means: list[float], deviations: list[float], weights: list[float]) -> float:
    return _sigmoid(sum(weight * value for weight, value in zip(weights, _vector(row, means, deviations))))


def evaluar(rows: Iterable[Mapping[str, object]], predictor) -> dict[str, object]:
    tp = tn = fp = fn = 0
    count = 0
    for row in rows:
        count += 1
        actual = int(row["compra_30d"])
        predicted = bool(predictor(row))
        tp += int(predicted and actual)
        tn += int(not predicted and not actual)
        fp += int(predicted and not actual)
        fn += int(not predicted and actual)
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {"n": count, "TP": tp, "TN": tn, "FP": fp, "FN": fn, "precision": round(precision, 4), "recall": round(recall, 4), "F1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0}


def entrenar_y_evaluar_desde_paquete(root: Path) -> dict[str, object]:
    clients = _load(root, "clientes.csv", "clientes")
    sales = _load(root, "ventas.csv", "ventas")
    rows = _all_snapshots(clients, sales)
    train = [row for row in rows if row["corte"] <= date(2026, 4, 30)]
    valid = [row for row in rows if date(2026, 5, 1) <= row["corte"] <= date(2026, 6, 30)]
    test = [row for row in rows if date(2026, 7, 1) <= row["corte"] <= date(2026, 9, 30)]
    means, deviations, weights = _fit(train)
    probability = lambda row: _probability(row, means, deviations, weights)
    thresholds = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    threshold = max(thresholds, key=lambda value: evaluar(valid, lambda row: probability(row) >= value)["F1"])
    return {"modelo": "Regresión logística didáctica; pesos aprendidos en datos de prueba", "umbral": threshold, "variables": FIELDS, "entrenamiento_hasta": date(2026, 4, 30), "validacion": evaluar(valid, lambda row: probability(row) >= threshold), "prueba_modelo": evaluar(test, lambda row: probability(row) >= threshold), "prueba_linea_base": evaluar(test, lambda row: row["frecuencia_30d"] > 0), "medias": means, "desviaciones": deviations, "pesos": weights, "observaciones": len(rows)}
