"""Conversión de celdas físicas a tipos estables del contrato."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .esquemas import TableSpec


class NormalizacionError(ValueError):
    """Una celda no cumple el formato declarado."""


def _date(value: str) -> date:
    value = str(value).strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            serial = Decimal(value)
        except InvalidOperation as exc:
            raise NormalizacionError(f"Fecha no ISO: {value}") from exc
        if serial != serial.to_integral_value() or serial < 1:
            raise NormalizacionError(f"Fecha no ISO: {value}")
        return date(1899, 12, 30) + timedelta(days=int(serial))


def _decimal(value: str) -> Decimal:
    raw = str(value).strip()
    if not raw or "," in raw:
        raise NormalizacionError(f"Decimal inválido: {value}")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise NormalizacionError(f"Decimal inválido: {value}") from exc


def _integer(value: str) -> int:
    raw = str(value).strip()
    try:
        result = int(raw)
    except ValueError as exc:
        raise NormalizacionError(f"Entero inválido: {value}") from exc
    if raw.startswith("+") or raw.startswith("-"):
        digits = raw[1:]
    else:
        digits = raw
    if not digits.isdigit():
        raise NormalizacionError(f"Entero inválido: {value}")
    return result


def normalizar_fila(row: Mapping[str, str], spec: TableSpec) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, column in spec.columns.items():
        value = row.get(name, "")
        if value is None:
            value = ""
        if isinstance(value, str):
            value = value.strip()
        if value == "" and column.required:
            raise NormalizacionError(f"Campo requerido vacío: {name}")
        if value == "":
            result[name] = None
        elif column.kind == "date":
            result[name] = _date(str(value))
        elif column.kind == "decimal":
            result[name] = _decimal(str(value))
        elif column.kind == "integer":
            result[name] = _integer(str(value))
        else:
            result[name] = str(value)
    return result
