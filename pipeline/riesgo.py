"""Riesgo de inactividad y ventana de próxima compra (A06)."""
from __future__ import annotations
from datetime import date, timedelta
from statistics import median
from typing import Iterable, Mapping

def estimar_riesgo(row: Mapping[str, object], cutoff: date, *, frio_dias: int = 90, horizonte_dias: int = 60) -> dict[str, object]:
    last = row.get("ultima_compra")
    if last is None:
        return {"cliente_id": row.get("cliente_id"), "estado": "sin_historial", "riesgo_inactividad": None}
    days = (cutoff - last).days
    return {"cliente_id": row.get("cliente_id"), "estado": "ocultar" if days >= frio_dias else "activo", "riesgo_inactividad": days + horizonte_dias >= frio_dias, "recencia_dias": days}

def estimar_proxima_compra(intervalos: Iterable[int], *, min_historia: int = 2) -> dict[str, object]:
    values = sorted(int(value) for value in intervalos if int(value) > 0)
    if len(values) < min_historia:
        return {"estado": "historia_insuficiente", "mediana_dias": None, "ventana": None}
    center = int(median(values))
    return {"estado": "utilizable", "mediana_dias": center, "ventana": {"min_dias": values[0], "max_dias": values[-1], "origen": "intervalos_cliente"}}
