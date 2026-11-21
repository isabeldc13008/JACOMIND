"""Contratos de tablas de entrada y sus referencias."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    kind: str = "text"
    required: bool = True
    allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: Mapping[str, ColumnSpec]
    primary_key: tuple[str, ...]
    references: Mapping[str, tuple[str, str]] = field(default_factory=dict)
    business_key: tuple[str, ...] = ()


def _columns(names: str, kinds: Mapping[str, str] | None = None) -> dict[str, ColumnSpec]:
    kinds = kinds or {}
    return {name: ColumnSpec(name, kinds.get(name, "text")) for name in names.split()}


TABLAS = {
    "clientes": TableSpec(
        "clientes",
        _columns("cliente_id nombre_prueba sector_prueba ciudad_prueba fecha_alta canal_preferido_prueba origen_datos", {"fecha_alta": "date"}),
        ("cliente_id",),
        business_key=("cliente_id",),
    ),
    "productos": TableSpec(
        "productos",
        _columns("producto_id nombre_prueba familia_prueba tipo_prueba moneda_lista precio_lista costo_referencia vigencia_meses origen_datos", {"precio_lista": "decimal", "costo_referencia": "decimal", "vigencia_meses": "integer"}),
        ("producto_id",),
        business_key=("producto_id",),
    ),
    "proveedores": TableSpec("proveedores", _columns("proveedor_id nombre_prueba origen_datos"), ("proveedor_id",), business_key=("proveedor_id",)),
    "trm": TableSpec("trm", _columns("fecha cop_por_usd origen", {"fecha": "date", "cop_por_usd": "decimal"}), ("fecha",), business_key=("fecha",)),
    "ventas": TableSpec(
        "ventas",
        _columns("venta_id fecha cliente_id producto_id cantidad moneda precio_unitario descuento_pct estado origen_datos", {"fecha": "date", "cantidad": "integer", "precio_unitario": "decimal", "descuento_pct": "decimal"}),
        ("venta_id",),
        {"cliente_id": ("clientes", "cliente_id"), "producto_id": ("productos", "producto_id")},
        business_key=("venta_id",),
    ),
    "compras": TableSpec(
        "compras",
        _columns("compra_id fecha proveedor_id producto_id cantidad moneda costo_unitario origen_datos", {"fecha": "date", "cantidad": "integer", "costo_unitario": "decimal"}),
        ("compra_id",),
        {"proveedor_id": ("proveedores", "proveedor_id"), "producto_id": ("productos", "producto_id")},
        business_key=("compra_id",),
    ),
    "instalaciones": TableSpec(
        "instalaciones",
        _columns("instalacion_id cliente_id producto_id fecha_inicio fecha_fin unidades origen_datos", {"fecha_inicio": "date", "fecha_fin": "date", "unidades": "integer"}),
        ("instalacion_id",),
        {"cliente_id": ("clientes", "cliente_id"), "producto_id": ("productos", "producto_id")},
        business_key=("instalacion_id",),
    ),
}


ARCHIVOS = {
    "clientes.csv": "clientes",
    "productos.csv": "productos",
    "proveedores.csv": "proveedores",
    "trm_prueba.csv": "trm",
    "ventas.csv": "ventas",
    "compras.csv": "compras",
    "base_instalada.csv": "instalaciones",
}
