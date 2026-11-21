"""Oportunidades comerciales trazables (A07)."""
from __future__ import annotations
from datetime import date
from typing import Mapping

def generar_oportunidades(fichas, familias_por_producto: Mapping[str, str], cutoff: date, *, soporte_minimo: int = 1):
    output = []
    for ficha in fichas:
        client = ficha["cliente_id"]
        if ficha.get("coberturas_proximas", 0) or any(coverage.get("proxima") for coverage in ficha.get("coberturas", [])):
            output.append({"id": f"{client}:renovacion", "cliente_id": client, "tipo": "renovacion", "evidencia": ficha.get("coberturas", [])})
        if ficha.get("frio"):
            output.append({"id": f"{client}:reactivacion", "cliente_id": client, "tipo": "reactivacion", "evidencia": {"recencia_dias": ficha.get("dias_sin_compra")}})
        owned = {familias_por_producto.get(product) for product in ficha.get("productos_historicos", [])}
        for family in sorted(set(familias_por_producto.values()) - owned):
            output.append({"id": f"{client}:cruzada:{family}", "cliente_id": client, "tipo": "venta_cruzada", "familia": family, "evidencia": {"soporte": soporte_minimo}})
    return output
