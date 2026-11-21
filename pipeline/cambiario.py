"""Sensibilidad de costos de compras USD (A09)."""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP

def simular_exposicion(rows, cambio: Decimal) -> dict[str, object]:
    base = sum((Decimal(row["usd"]) * Decimal(row["trm"]) for row in rows), Decimal("0"))
    scenario = (base * (Decimal("1") + Decimal(cambio))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    base = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {"base_cop": base, "escenario_cop": scenario, "diferencia_cop": scenario - base, "cambio": Decimal(cambio), "universo": len(rows)}
