"""Ficha 360 de clientes, recurrencia y coberturas (A03)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping

from .esquemas import TABLAS
from .formatos import leer_csv
from .normalizacion import normalizar_fila
from .operaciones import _load, _rates, calcular_importe


def construir_ficha(
    clients: Iterable[Mapping[str, object]],
    sales: Iterable[Mapping[str, object]],
    installations: Iterable[Mapping[str, object]],
    cutoff: date,
    *,
    frecuente_min: int = 8,
    frio_dias: int = 90,
    nuevo_dias: int = 30,
) -> list[dict[str, object]]:
    sales_by_client: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for sale in sales:
        if sale.get("estado", "Confirmada") == "Confirmada" and sale["fecha"] <= cutoff:
            sales_by_client[str(sale["cliente_id"])].append(sale)
    installs_by_client: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for install in installations:
        if install["fecha_inicio"] <= cutoff:
            installs_by_client[str(install["cliente_id"])].append(install)
    output: list[dict[str, object]] = []
    for client in clients:
        client_id = str(client["cliente_id"])
        client_sales = sorted(sales_by_client.get(client_id, []), key=lambda row: row["fecha"])
        dates = sorted({row["fecha"] for row in client_sales})
        intervals = [(right - left).days for left, right in zip(dates, dates[1:])]
        last = dates[-1] if dates else None
        days_without = (cutoff - last).days if last else None
        active_installs = installs_by_client.get(client_id, [])
        near = 0
        expired = 0
        current = 0
        coverage_detail: list[dict[str, object]] = []
        for install in active_installs:
            delta = (install["fecha_fin"] - cutoff).days
            is_current = install["fecha_fin"] >= cutoff
            is_near = 0 <= delta <= 45
            current += int(is_current)
            near += int(is_near)
            expired += int(install["fecha_fin"] < cutoff)
            coverage_detail.append({"instalacion_id": install["instalacion_id"], "producto_id": install["producto_id"], "fecha_fin": install["fecha_fin"], "estado": "vigente" if is_current else "vencida", "proxima": is_near})
        age = (cutoff - client["fecha_alta"]).days
        output.append({
            "cliente_id": client_id,
            "fecha_corte": cutoff,
            "fecha_alta": client["fecha_alta"],
            "recencia_dias": days_without,
            "dias_sin_compra": days_without,
            "frecuencia_operaciones": len(client_sales),
            "frecuente": len(client_sales) >= frecuente_min,
            "frio": days_without is not None and days_without >= frio_dias,
            "nuevo": 0 <= age <= nuevo_dias,
            "sin_compras": not bool(client_sales),
            "valor_monetario_cop": sum((Decimal(str(row.get("importe_cop", 0))) for row in client_sales), Decimal("0")),
            "primera_compra": dates[0] if dates else None,
            "ultima_compra": last,
            "intervalos_compra_dias": intervals,
            "productos_historicos": sorted({str(row["producto_id"]) for row in client_sales}),
            "coberturas_vigentes": current,
            "coberturas_proximas": near,
            "coberturas_vencidas": expired,
            "coberturas": coverage_detail,
        })
    return output


def construir_ficha_desde_paquete(root: Path, cutoff: date) -> list[dict[str, object]]:
    clients = _load(root, "clientes.csv", "clientes")
    sales = _load(root, "ventas.csv", "ventas")
    installations = _load(root, "base_instalada.csv", "instalaciones")
    rates = _rates(root)
    sales_with_amount: list[dict[str, object]] = []
    for sale in sales:
        copy = dict(sale)
        copy["importe_cop"] = calcular_importe(sale, rates)
        sales_with_amount.append(copy)
    return construir_ficha(clients, sales_with_amount, installations, cutoff)
