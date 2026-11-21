"""Pronóstico simple y evaluable (A08)."""
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
