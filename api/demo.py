"""Datos de demostración ficticios: identidades, cierre de muestra, documentos, beneficios y PQRS."""
from __future__ import annotations

from .auth import Usuario, cargar_usuario, sembrar_identidades, sembrar_usuarios_configurados
from .base import RAIZ, BaseDatos, ErrorApi
from . import beneficios, documentos, pqrs, publicacion

MUESTRA = RAIZ / "contratos" / "ejemplos" / "publicacion" / "demo-2026-10"


def preparar(db: BaseDatos, publicar_muestra: bool = True) -> dict:
    db.migrar()
    with db.transaccion() as con:
        sembrar_identidades(con)
        hay_docs = con.execute("SELECT count(*) FROM documentos").fetchone()[0]
        hay_ben = con.execute("SELECT count(*) FROM beneficios").fetchone()[0]
        hay_pqrs = con.execute("SELECT count(*) FROM pqrs").fetchone()[0]
        hay_cierre = publicacion.cierre_activo(con)
    sembrar_usuarios_configurados(db)
    sistema = Usuario("aten1", "Semilla", "GREEN", "interna", None, {"atencion"},
                      {"beneficios.editar", "beneficios.publicar"})
    resultado = {"cierre": hay_cierre}
    if publicar_muestra and not hay_cierre:
        resultado["cierre"] = publicacion.publicar_ruta(db, MUESTRA, "ops1")["cierre_id"]
    if not hay_docs:
        documentos.sembrar(db)
    if not hay_ben:
        beneficios.sembrar(db, sistema)
    if not hay_pqrs:
        with db.conexion() as con:
            cli_a, cli_b = cargar_usuario(con, "cli_a"), cargar_usuario(con, "cli_b")
        pqrs.crear(db, cli_a, "Doble cobro en la factura de respaldo", "Nos cobraron dos veces el servicio de respaldo de octubre. Solicito revisar la factura.", "semilla-1")
        pqrs.crear(db, cli_b, "Información sobre descuento por renovación", "Quisiera información sobre el descuento por renovación anticipada de nuestro contrato.", "semilla-2")
        pqrs.crear(db, cli_a, "Comentario general", "Hola, escribo por lo del mes pasado.", "semilla-3")
    return resultado


def solo_permisos(db: BaseDatos) -> None:
    """Sincroniza permisos y deja disponible la identidad de la demo/piloto."""
    db.migrar()
    with db.transaccion() as con:
        sembrar_identidades(con)


__all__ = ["preparar", "solo_permisos", "ErrorApi"]
