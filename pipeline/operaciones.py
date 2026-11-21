"""Cálculos contables reproducibles para A02."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from statistics import median
from typing import Iterable, Mapping

from .esquemas import TABLAS
from .formatos import leer_csv
from .normalizacion import normalizar_fila


CENTAVOS = Decimal("0.01")


class MissingRateError(ValueError):
    """Una operación USD no tiene TRM para su fecha."""


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def calcular_importe(row: Mapping[str, object], tasas: Mapping[date, Decimal]) -> Decimal:
    if row.get("estado") == "Anulada":
        return Decimal("0")
    quantity = int(row["cantidad"])
    unit = float(row.get("precio_unitario", row.get("costo_unitario", 0)))
    discount = float(row.get("descuento_pct", 0))
    amount = Decimal(str(quantity * unit * (1 - discount / 100)))
    if row.get("moneda") == "COP":
        return amount
    if row.get("moneda") == "USD":
        try:
            rate = tasas[row["fecha"]]
        except KeyError as exc:
            raise MissingRateError(f"No hay TRM para {row['fecha']}") from exc
        return Decimal(str(float(amount) * float(rate)))
    raise ValueError(f"Moneda no admitida: {row.get('moneda')}")


@dataclass
class OperationSummary:
    operation_count: int = 0
    confirmed_count: int = 0
    total_cop: Decimal = Decimal("0")
    rows: list[dict[str, object]] = field(default_factory=list)
    aggregates: dict[tuple[str, str, str, str], Decimal] = field(default_factory=dict)
    missing_rates: list[str] = field(default_factory=list)


@dataclass
class ClosureResult:
    sales: OperationSummary
    purchases: OperationSummary
    anomalies: list[dict[str, object]]


def _root(root: Path) -> Path:
    return root / "01_Datos" if (root / "01_Datos").is_dir() else root


def _load(root: Path, filename: str, table: str) -> list[dict[str, object]]:
    raw = leer_csv(_root(root) / filename, required_columns=TABLAS[table].columns.keys())
    return [normalizar_fila(row, TABLAS[table]) for row in raw]


def _rates(root: Path) -> dict[date, Decimal]:
    return {row["fecha"]: row["cop_por_usd"] for row in _load(root, "trm_prueba.csv", "trm")}


def _summarize(rows: Iterable[dict[str, object]], products: Mapping[str, Mapping[str, object]], rates: Mapping[date, Decimal], cutoff: date, *, purchase: bool = False) -> OperationSummary:
    result = OperationSummary()
    for row in rows:
        if row["fecha"] > cutoff:
            continue
        result.operation_count += 1
        if row.get("estado", "Confirmada") == "Anulada":
            result.rows.append({"id": row.get("compra_id", row.get("venta_id")), "fecha": row["fecha"], "amount_cop": Decimal("0"), "status": "Anulada"})
            continue
        if purchase:
            amount_row = dict(row)
            amount_row["precio_unitario"] = row["costo_unitario"]
            amount_row["descuento_pct"] = Decimal("0")
            amount = calcular_importe(amount_row, rates)
        else:
            try:
                amount = calcular_importe(row, rates)
            except MissingRateError:
                result.missing_rates.append(str(row.get("venta_id", row.get("compra_id"))))
                continue
        # Compatibilidad con la referencia del paquete: cada operación se
        # redondea a dos decimales antes de agregarla al cierre.
        amount = Decimal(str(round(float(amount), 2)))
        result.confirmed_count += 1
        result.total_cop += amount
        product = products.get(str(row["producto_id"]), {})
        family = str(product.get("familia_prueba", "DESCONOCIDA"))
        key = (row["fecha"].strftime("%Y-%m"), family, str(row["moneda"]), str(row.get("proveedor_id", "")))
        result.aggregates[key] = result.aggregates.get(key, Decimal("0")) + amount
        result.rows.append({"id": row.get("compra_id", row.get("venta_id")), "fecha": row["fecha"], "family": family, "currency": row["moneda"], "supplier_id": row.get("proveedor_id", ""), "amount_cop": amount, "status": "Confirmada"})
    result.total_cop = _money(result.total_cop)
    result.aggregates = {key: _money(value) for key, value in result.aggregates.items()}
    return result


def detectar_anomalias(rows: Iterable[Mapping[str, object]], min_history: int = 3, threshold: Decimal = Decimal("3")) -> list[dict[str, object]]:
    history: dict[tuple[str, str], list[Decimal]] = {}
    alerts: list[dict[str, object]] = []
    for row in sorted(rows, key=lambda item: (str(item["period"]), str(item.get("id", "")))):
        key = (str(row["family"]), str(row["currency"]))
        previous = history.setdefault(key, [])
        value = Decimal(row["value"])
        if len(previous) >= min_history:
            med = Decimal(str(median(previous)))
            deviations = [abs(item - med) for item in previous]
            mad = Decimal(str(median(deviations)))
            abnormal = abs(value - med) > threshold * mad if mad else value != med
            if abnormal:
                alerts.append({"id": row.get("id"), "period": row["period"], "family": row["family"], "currency": row["currency"], "value": value, "median": med, "mad": mad, "reason": "valor fuera de la historia previa"})
        previous.append(value)
    return alerts


def calcular_cierre(root: Path, cutoff: date) -> ClosureResult:
    products = {str(row["producto_id"]): row for row in _load(root, "productos.csv", "productos")}
    rates = _rates(root)
    sales = _summarize(_load(root, "ventas.csv", "ventas"), products, rates, cutoff)
    purchases = _summarize(_load(root, "compras.csv", "compras"), products, rates, cutoff, purchase=True)
    history_rows = [{"period": row["fecha"].strftime("%Y-%m"), "family": row["family"], "currency": row["currency"], "value": row["amount_cop"], "id": row["id"]} for row in sales.rows if row.get("status") == "Confirmada"]
    return ClosureResult(sales, purchases, detectar_anomalias(history_rows))
