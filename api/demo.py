"""Datos de demostración y carga inicial segura para el despliegue."""
from __future__ import annotations

from json import loads
from pathlib import Path

from .auth import Usuario, cargar_usuario, sembrar_identidades, sembrar_usuarios_configurados
from .base import RAIZ, BaseDatos, ErrorApi
from . import beneficios, documentos, pqrs, publicacion

MUESTRA = RAIZ / "contratos" / "ejemplos" / "publicacion" / "demo-2026-10"
DATOS_INICIALES = RAIZ / "datos" / "iniciales" / "Green_Services_Recursos_de_Prueba"
CORTE_INICIAL = "2026-10-31"


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


def _es_muestra_demo(con, cierre_id: str | None) -> bool:
    """Identifica únicamente la publicación ficticia que debe migrarse."""
    if not cierre_id:
        return True
    fila = con.execute("SELECT manifiesto_json FROM cierres WHERE id = ?", (cierre_id,)).fetchone()
    if not fila:
        return False
    manifiesto = loads(fila[0])
    return manifiesto.get("cierre_id") == "demo-2026-10" or "muestra_ficticia" in manifiesto.get("huellas_entrada", {})


def inicializar_datos_iniciales(db: BaseDatos) -> dict:
    """Publica los datos del paquete inicial en una base nueva o de demo.

    Es idempotente: un cierre real ya publicado no se reemplaza al reiniciar
    el servidor. La muestra de 8 clientes sí se migra una sola vez al paquete
    inicial para que el despliegue existente deje de pedir una carga manual.
    """
    db.migrar()
    with db.conexion() as con:
        activo = publicacion.cierre_activo(con)
        debe_publicar = _es_muestra_demo(con, activo)
    if not debe_publicar:
        return {"estado": "existente", "cierre": activo}
    if not DATOS_INICIALES.is_dir():
        raise ErrorApi(500, "datos_iniciales_no_disponibles", f"No existe el paquete inicial: {DATOS_INICIALES}")
    from .operacion import ejecutar_cierre
    resultado = ejecutar_cierre(db, "programador", CORTE_INICIAL, datos=str(DATOS_INICIALES), reintentos=0)
    if resultado["estado"] != "publicado":
        raise ErrorApi(500, "datos_iniciales_no_publicados", "No se pudo publicar el paquete inicial", resultado)
    return {"estado": "publicado", "cierre": resultado["ultimo_cierre_valido"], "resultado": resultado}


__all__ = ["preparar", "solo_permisos", "inicializar_datos_iniciales", "DATOS_INICIALES", "CORTE_INICIAL", "ErrorApi"]
