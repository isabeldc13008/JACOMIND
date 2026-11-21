"""Controles de salud de modelos e impacto (A11)."""
from __future__ import annotations

def evaluar_salud(actual, referencia, *, tolerancia_nulos: float = 0.01) -> dict[str, object]:
    total = max(1, int(actual.get("total", 0)))
    null_rate = float(actual.get("nulos", 0)) / total
    reference_total = max(1, int(referencia.get("total", 0)))
    reference_rate = float(referencia.get("nulos", 0)) / reference_total
    drift = null_rate - reference_rate
    return {"estado": "revisar" if abs(drift) >= tolerancia_nulos else "estable", "null_rate": null_rate, "reference_null_rate": reference_rate, "drift": drift, "denominador": total}
