"""Validación de filas y lotes, con incidencias aptas para auditoría."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping

from .esquemas import TableSpec


@dataclass(frozen=True)
class Issue:
    file: str
    row: int
    field: str
    code: str
    reason: str
    action: str


@dataclass
class TableValidation:
    accepted: list[dict[str, object]] = field(default_factory=list)
    isolated: list[dict[str, object]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    duplicate_count: int = 0
    blocking: bool = False


def _issue(file: str, row: int, field: str, code: str, reason: str, action: str = "aislar") -> Issue:
    return Issue(file=file, row=row, field=field, code=code, reason=reason, action=action)


def validar_fila(
    row: Mapping[str, object],
    spec: TableSpec,
    catalogos: Mapping[str, set[str]],
    *,
    archivo: str = "",
    fila: int = 0,
) -> list[Issue]:
    issues: list[Issue] = []
    for name, column in spec.columns.items():
        if column.required and (name not in row or row[name] is None or row[name] == ""):
            issues.append(_issue(archivo, fila, name, "CAMPO_REQUERIDO", "Falta un campo obligatorio"))
    for field_name, (table, key) in spec.references.items():
        value = row.get(field_name)
        if value is not None and str(value) not in catalogos.get(table, set()):
            issues.append(_issue(archivo, fila, field_name, "REFERENCIA_DESCONOCIDA", f"No existe {table}.{key}={value}"))
    if spec.name in {"ventas", "compras"}:
        currency = row.get("moneda")
        if currency not in {"COP", "USD"}:
            issues.append(_issue(archivo, fila, "moneda", "MONEDA_NO_ADMITIDA", f"Moneda no admitida: {currency}"))
        if row.get("cantidad") is not None and row.get("cantidad", 0) <= 0:
            issues.append(_issue(archivo, fila, "cantidad", "CANTIDAD_NO_POSITIVA", "La cantidad debe ser mayor que cero"))
    if spec.name == "ventas":
        if row.get("descuento_pct") is not None and not (Decimal("0") <= row["descuento_pct"] <= Decimal("100")):
            issues.append(_issue(archivo, fila, "descuento_pct", "DESCUENTO_FUERA_DE_RANGO", "El descuento debe estar entre 0 y 100"))
        if row.get("estado") not in {"Confirmada", "Anulada"}:
            issues.append(_issue(archivo, fila, "estado", "ESTADO_NO_ADMITIDO", f"Estado no admitido: {row.get('estado')}"))
    if spec.name == "productos":
        if row.get("moneda_lista") not in {"COP", "USD"}:
            issues.append(_issue(archivo, fila, "moneda_lista", "MONEDA_NO_ADMITIDA", "La moneda de lista debe ser COP o USD"))
        if row.get("tipo_prueba") not in {"Recurrente", "Único", "Unico"}:
            issues.append(_issue(archivo, fila, "tipo_prueba", "TIPO_NO_ADMITIDO", "Tipo de producto no admitido"))
    return issues


def validar_tabla(
    rows: Iterable[Mapping[str, object]],
    spec: TableSpec,
    catalogos: Mapping[str, set[str]],
    *,
    archivo: str = "",
) -> TableValidation:
    result = TableValidation()
    seen: dict[tuple[object, ...], dict[str, object]] = {}
    for row_number, row in enumerate(rows, start=2):
        key = tuple(row.get(column) for column in spec.primary_key)
        issues = validar_fila(row, spec, catalogos, archivo=archivo, fila=row_number)
        if key in seen:
            if dict(seen[key]) == dict(row):
                result.duplicate_count += 1
                result.issues.append(_issue(archivo, row_number, spec.primary_key[0], "DUPLICADO_IDENTICO", "La fila ya fue recibida con los mismos valores"))
                continue
            issues.append(_issue(archivo, row_number, spec.primary_key[0], "DUPLICADO_CONFLICTIVO", "La clave ya existe con valores distintos"))
        if issues:
            result.isolated.append(dict(row))
            result.issues.extend(issues)
        else:
            result.accepted.append(dict(row))
            seen[key] = dict(row)
    return result
