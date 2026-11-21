"""Conversión de celdas físicas a tipos estables del contrato."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .esquemas import TableSpec


class NormalizacionError(ValueError):
    """Una celda no cumple el formato declarado."""

    def __init__(self, message: str, field: str = ""):
        super().__init__(message)
        self.field = field


def _date(value: str, allow_excel_serial: bool = False) -> date:
    value = str(value).strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        if not allow_excel_serial:
            raise NormalizacionError(f"Fecha no ISO: {value}")
        try:
            serial = Decimal(value)
        except InvalidOperation as exc:
            raise NormalizacionError(f"Fecha no ISO: {value}") from exc
        if serial != serial.to_integral_value() or serial < 1 or serial > 2958465:
            raise NormalizacionError(f"Fecha Excel fuera de rango: {value}")
        try:
            return date(1899, 12, 30) + timedelta(days=int(serial))
        except OverflowError as exc:
            raise NormalizacionError(f"Fecha Excel fuera de rango: {value}") from exc


def _decimal(value: str) -> Decimal:
    raw = str(value).strip()
    if not raw or "," in raw:
        raise NormalizacionError(f"Decimal inválido: {value}")
    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise NormalizacionError(f"Decimal inválido: {value}") from exc
    if not result.is_finite():
        raise NormalizacionError(f"Decimal no finito: {value}")
    return result


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


def normalizar_fila(row: Mapping[str, str], spec: TableSpec, *, allow_excel_serial: bool = False) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, column in spec.columns.items():
        value = row.get(name, "")
        if value is None:
            value = ""
        if isinstance(value, str):
            value = value.strip()
        if value == "" and column.required:
            raise NormalizacionError(f"Campo requerido vacío: {name}", name)
        if value == "":
            result[name] = None
        elif column.kind == "date":
            try:
                result[name] = _date(str(value), allow_excel_serial)
            except NormalizacionError as exc:
                raise NormalizacionError(str(exc), name) from exc
        elif column.kind == "decimal":
            try:
                result[name] = _decimal(str(value))
            except NormalizacionError as exc:
                raise NormalizacionError(str(exc), name) from exc
        elif column.kind == "integer":
            try:
                result[name] = _integer(str(value))
            except NormalizacionError as exc:
                raise NormalizacionError(str(exc), name) from exc
        else:
            result[name] = str(value)
    return result
