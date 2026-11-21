"""Reglas compartidas de presentación de la agenda C1 (orden y motivos).

A asigna una única ``accion`` por cliente; B ordena y muestra todos los motivos
aplicables. Ambos pueden importar estas constantes para no divergir.
"""
from __future__ import annotations

ACCIONES = [
    "Revisar reactivación",
    "Revisar cobertura",
    "Revisar oportunidad de recompra",
    "Revisar primera compra",
    "Seguimiento habitual",
]
ORDEN_ACCION = {a: i + 1 for i, a in enumerate(ACCIONES)}


def motivos(cliente: dict, umbral: float | None = None) -> list[str]:
    """Todos los motivos aplicables a una fila de agenda, en orden de prioridad."""
    salida: list[str] = []
    if cliente.get("frio"):
        salida.append("Revisar reactivación")
    if (cliente.get("renovaciones_proximas") or 0) > 0 or (cliente.get("coberturas_vencidas") or 0) > 0:
        salida.append("Revisar cobertura")
    prob = cliente.get("prob_compra_30d")
    if prob is not None and (
        (umbral is not None and prob >= umbral)
        or (umbral is None and cliente.get("accion") == "Revisar oportunidad de recompra")
    ):
        salida.append("Revisar oportunidad de recompra")
    if cliente.get("ultima_compra") is None and (cliente.get("ventas_confirmadas") or 0) == 0:
        salida.append("Revisar primera compra")
    accion = cliente.get("accion")
    if accion in ORDEN_ACCION and accion not in salida and accion != "Seguimiento habitual":
        salida.append(accion)
    salida.sort(key=lambda m: ORDEN_ACCION.get(m, 99))
    return salida or ["Seguimiento habitual"]


def clave_orden(cliente: dict) -> tuple:
    """Orden estable: acción, probabilidad descendente (nulos al final), ID ascendente."""
    prob = cliente.get("prob_compra_30d")
    return (
        ORDEN_ACCION.get(cliente.get("accion"), 99),
        1 if prob is None else 0,
        -(prob or 0.0),
        str(cliente.get("cliente_id")),
    )


def ordenar(clientes: list[dict]) -> list[dict]:
    return sorted(clientes, key=clave_orden)
