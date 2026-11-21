"""Matriz de acceso rol × acción (punto de partida a acordar con Green).

Operaciones publica cierres, Ventas tramita oportunidades, Finanzas consulta
exposición, Atención tramita PQRS y el usuario empresarial consulta únicamente
sus beneficios y casos. La empresa siempre se resuelve en el servidor.
"""
from __future__ import annotations

ROLES = ["operaciones", "ventas", "finanzas", "atencion", "gerencia", "empresa"]

MATRIZ: dict[str, set[str]] = {
    "cartera.ver": {"operaciones", "ventas", "gerencia"},
    "cartera.exportar": {"operaciones", "gerencia"},
    "cierres.publicar": {"operaciones"},
    "cargas.ejecutar": {"operaciones"},
    "tablero.ventas": {"ventas", "gerencia"},
    "tablero.operaciones": {"operaciones", "gerencia"},
    "tablero.gerencia": {"gerencia", "finanzas"},
    "tareas.ver": {"ventas", "operaciones", "gerencia"},
    "tareas.gestionar": {"ventas"},
    "finanzas.ver": {"finanzas", "gerencia"},
    "informes.ver": {"gerencia", "finanzas", "operaciones"},
    "informes.generar": {"operaciones", "gerencia"},
    "pqrs.crear": {"empresa"},
    "pqrs.ver_propias": {"empresa"},
    "pqrs.gestionar": {"atencion"},
    "pqrs.indicadores": {"gerencia", "atencion"},
    "pqrs.exportar": {"atencion"},
    "beneficios.portal": {"empresa"},
    "beneficios.ver_interno": {"ventas", "atencion", "gerencia"},
    "beneficios.editar": {"ventas", "atencion"},
    "beneficios.publicar": {"atencion"},
    "documentos.gestionar": {"atencion"},
    "documentos.consultar": {"atencion", "ventas", "operaciones", "gerencia", "finanzas", "empresa"},
    "agente.datos": {"ventas", "operaciones", "gerencia", "finanzas"},
    "agente.portal": {"empresa", "atencion"},
    "operacion.administrar": {"operaciones"},
    "auditoria.ver": {"operaciones", "gerencia"},
    "eventos.exportar": {"operaciones", "gerencia"},
}


def filas_permisos() -> list[tuple[str, str]]:
    return sorted((rol, accion) for accion, roles in MATRIZ.items() for rol in roles)


# Identidades ficticias para la demo local y las pruebas.
ORGANIZACIONES = [
    ("GREEN", "Green Services (interno, ficticio)", "interna", None, None),
    ("EMP-A", "Empresa de ensayo A", "empresa", "DEMO01", "Recurrente en pausa"),
    ("EMP-B", "Empresa de ensayo B", "empresa", "DEMO02", None),
]
IDENTIDADES = [
    ("ops1", "Olga Operaciones (ficticia)", "GREEN", "operaciones"),
    ("ventas1", "Víctor Ventas (ficticio)", "GREEN", "ventas"),
    ("ventas2", "Valeria Ventas (ficticia)", "GREEN", "ventas"),
    ("fin1", "Fernando Finanzas (ficticio)", "GREEN", "finanzas"),
    ("aten1", "Ana Atención (ficticia)", "GREEN", "atencion"),
    ("ger1", "Gabriela Gerencia (ficticia)", "GREEN", "gerencia"),
    ("cli_a", "Usuario externo Empresa A", "EMP-A", "empresa"),
    ("cli_b", "Usuario externo Empresa B", "EMP-B", "empresa"),
]
