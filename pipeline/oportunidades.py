"""Oportunidades comerciales trazables (A07).

La venta cruzada usa co-ocurrencia de familias entre clientes, con transacciones
anteriores o iguales al corte y un soporte mínimo configurable. Se compara con la
recomendación de la familia más popular.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable, Mapping


def familias_por_cliente(ventas: Iterable[Mapping[str, object]], familias_por_producto: Mapping[str, str], cutoff: date) -> dict[str, set[str]]:
    """Familias compradas por cliente usando solo ventas confirmadas hasta el corte."""
    salida: dict[str, set[str]] = {}
    for v in ventas:
        if v.get("estado", "Confirmada") != "Confirmada" or v["fecha"] > cutoff:
            continue
        fam = familias_por_producto.get(str(v["producto_id"]))
        if fam:
            salida.setdefault(str(v["cliente_id"]), set()).add(fam)
    return salida


def recomendar_venta_cruzada(historial: Mapping[str, set[str]], *, soporte_minimo: int = 3, k: int = 1,
                             incompatibles: Mapping[str, set[str]] | None = None) -> dict[str, list[dict[str, object]]]:
    """Para cada cliente, familias no compradas que co-ocurren con las suyas en otros clientes.

    ``soporte`` = número de otros clientes que compraron alguna familia del cliente y la candidata.
    """
    incompatibles = incompatibles or {}
    salida: dict[str, list[dict[str, object]]] = {}
    for cliente, propias in historial.items():
        if not propias:
            continue
        conteo: Counter = Counter()
        for otro, familias in historial.items():
            if otro == cliente or not (familias & propias):
                continue
            for candidata in familias - propias:
                conteo[candidata] += 1
        excluidas = set().union(*(incompatibles.get(f, set()) for f in propias)) if propias else set()
        sugerencias = [{"familia": fam, "soporte": soporte,
                        "justificacion": f"{soporte} clientes con familias en común ({', '.join(sorted(propias))}) también compran {fam}"}
                       for fam, soporte in sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0]))
                       if soporte >= soporte_minimo and fam not in excluidas]
        if sugerencias:
            salida[cliente] = sugerencias[:k]
    return salida


def recomendar_popular(historial: Mapping[str, set[str]], *, k: int = 1) -> dict[str, list[str]]:
    """Línea base: la familia más comprada que el cliente aún no tiene."""
    popularidad = Counter(f for familias in historial.values() for f in familias)
    orden = [f for f, _ in sorted(popularidad.items(), key=lambda kv: (-kv[1], kv[0]))]
    return {c: [f for f in orden if f not in propias][:k] for c, propias in historial.items()}


def generar_oportunidades(fichas, familias_por_producto: Mapping[str, str], cutoff: date, *, soporte_minimo: int = 1,
                          historial_familias: Mapping[str, set[str]] | None = None):
    output = []
    sugerencias = recomendar_venta_cruzada(historial_familias, soporte_minimo=soporte_minimo) if historial_familias is not None else None
    for ficha in fichas:
        client = ficha["cliente_id"]
        if ficha.get("coberturas_proximas", 0) or any(coverage.get("proxima") for coverage in ficha.get("coberturas", [])):
            output.append({"id": f"{client}:renovacion", "cliente_id": client, "tipo": "renovacion", "evidencia": ficha.get("coberturas", [])})
        if ficha.get("frio"):
            output.append({"id": f"{client}:reactivacion", "cliente_id": client, "tipo": "reactivacion", "evidencia": {"recencia_dias": ficha.get("dias_sin_compra")}})
        if sugerencias is None:
            # Sin historial de co-ocurrencia: comportamiento original (todas las familias no compradas).
            owned = {familias_por_producto.get(product) for product in ficha.get("productos_historicos", [])}
            for family in sorted(set(familias_por_producto.values()) - owned):
                output.append({"id": f"{client}:cruzada:{family}", "cliente_id": client, "tipo": "venta_cruzada", "familia": family, "evidencia": {"soporte": soporte_minimo}})
        else:
            for s in sugerencias.get(client, []):
                output.append({"id": f"{client}:cruzada:{s['familia']}", "cliente_id": client, "tipo": "venta_cruzada", "familia": s["familia"],
                               "evidencia": {"soporte": s["soporte"], "justificacion": s["justificacion"]}})
    return output


def evaluar_venta_cruzada(antes: Mapping[str, set[str]], despues: Mapping[str, set[str]], recomendaciones: Mapping[str, list]) -> dict[str, object]:
    """Aciertos en las primeras K sugerencias frente a familias realmente compradas después del corte."""
    aciertos = evaluados = 0
    for cliente, sugeridas in recomendaciones.items():
        familias = [s["familia"] if isinstance(s, dict) else s for s in sugeridas]
        nuevas = despues.get(cliente, set()) - antes.get(cliente, set())
        if not familias:
            continue
        evaluados += 1
        aciertos += int(bool(set(familias) & nuevas))
    return {"clientes_evaluados": evaluados, "aciertos": aciertos, "tasa": round(aciertos / evaluados, 4) if evaluados else None}
