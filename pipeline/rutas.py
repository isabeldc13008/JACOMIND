"""Localización del paquete de datos de práctica sin rutas fijas de un equipo."""

from __future__ import annotations

import os
from pathlib import Path

NOMBRE_PAQUETE = "Green_Services_Recursos_de_Prueba"


def ruta_paquete() -> Path | None:
    """Devuelve la carpeta del paquete: JACOMIND_DATOS o la carpeta hermana del clon."""
    candidatos = []
    if os.environ.get("JACOMIND_DATOS"):
        candidatos.append(Path(os.environ["JACOMIND_DATOS"]))
    raiz = Path(__file__).resolve().parents[1]
    candidatos += [raiz.parent / NOMBRE_PAQUETE, raiz / NOMBRE_PAQUETE]
    for ruta in candidatos:
        if (ruta / "01_Datos").is_dir() or (ruta / "clientes.csv").is_file():
            return ruta
    return None
