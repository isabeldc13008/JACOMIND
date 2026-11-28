"""Arranque reproducible de la demo en Azure App Service.

La demo usa el paquete ficticio versionado en contratos/ejemplos. Se prepara
antes de iniciar el servidor para no ejecutar el importador de datos reales
que requiere una declaración temporal adicional.
"""

from __future__ import annotations

import os

from api.base import BaseDatos, DIR_VAR
from api.demo import preparar
from api.servidor import Aplicacion, crear_servidor


def main() -> None:
    db = BaseDatos(os.environ.get("JACOMIND_DB", str(DIR_VAR / "jacomind.sqlite3")))
    preparar(db, publicar_muestra=True)
    servidor = crear_servidor(
        Aplicacion(db, practica=False, login_demo=True),
        "0.0.0.0",
        int(os.environ.get("PORT", "8000")),
    )
    servidor.serve_forever()


if __name__ == "__main__":
    main()
