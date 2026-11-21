"""Pronóstico simple y evaluable (A08).

Evaluación con origen creciente: se entrena hasta un mes, se pronostica cada
horizonte por separado y se desplaza el origen. Se compara con el último valor
observado (ingenuo).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def pronosticar_media_movil(series, window: int, horizon: int):
    values = [Decimal(str(value)) for value in series]
    if not values or window <= 0 or len(values) < window:
        return []
    forecasts = []
    history = values[:]
    for _ in range(horizon):
        value = (sum(history[-window:], Decimal("0")) / Decimal(window)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        forecasts.append(value)
        history.append(value)
    return forecasts


def pronosticar_ingenuo(series, horizon: int):
    values = [Decimal(str(value)) for value in series]
    return [values[-1]] * horizon if values else []


def evaluar_origen_creciente(series, window: int, horizon: int, *, min_entrenamiento: int | None = None) -> dict[int, dict[str, object]]:
    """MAE, sesgo y n por horizonte para la media móvil y el ingenuo."""
    values = [Decimal(str(value)) for value in series]
    inicio = max(window, min_entrenamiento or window)
    resultado: dict[int, dict[str, object]] = {}
    for h in range(1, horizon + 1):
        err_mm, err_ing = [], []
        for origen in range(inicio, len(values) - h + 1):
            hist, real = values[:origen], values[origen + h - 1]
            err_mm.append(pronosticar_media_movil(hist, window, h)[-1] - real)
            err_ing.append(pronosticar_ingenuo(hist, h)[-1] - real)
        n = len(err_mm)

        def mae(errs):
            return (sum((abs(e) for e in errs), Decimal("0")) / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if n else None

        resultado[h] = {"n": n, "mae_media_movil": mae(err_mm), "mae_ingenuo": mae(err_ing),
                        "sesgo_media_movil": (sum(err_mm, Decimal("0")) / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if n else None}
    return resultado
