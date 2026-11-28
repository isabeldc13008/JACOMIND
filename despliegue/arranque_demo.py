"""Arranque reproducible de la demo en Azure App Service.

La demo usa el paquete ficticio versionado en contratos/ejemplos. Se prepara
antes de iniciar el servidor para no ejecutar el importador de datos reales
que requiere una declaración temporal adicional.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# El App Service ejecuta «python despliegue/arranque_demo.py»: la raíz del repositorio no está en sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.base import BaseDatos, DIR_VAR
from api.demo import preparar
from api.servidor import Aplicacion, crear_servidor


def main() -> None:
    # La URL de Azure es pública: sin JACOMIND_ADMIN_PASSWORD no se crea el admin con la clave por defecto (admin123),
    # que cualquiera podría usar antes que el equipo.
    if not os.environ.get("JACOMIND_ADMIN_PASSWORD"):
        os.environ["JACOMIND_ADMIN_USUARIO"] = ""
        print("JACOMIND_ADMIN_PASSWORD no está definida: no se crea el administrador local.", file=sys.stderr)
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
