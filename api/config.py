"""Carga de configuración desde ``.env`` (sin dependencias). Los secretos nunca se versionan.

Las variables ya definidas en el entorno tienen prioridad sobre el archivo.
"""
from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def cargar_env(ruta: str | Path | None = None) -> dict[str, str]:
    ruta = Path(ruta or os.environ.get("JACOMIND_ENV", RAIZ / ".env"))
    leidas: dict[str, str] = {}
    if not ruta.exists():
        return leidas
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        clave = clave.strip().removeprefix("export ").strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "'\"":
            valor = valor[1:-1]
        leidas[clave] = valor
        os.environ.setdefault(clave, valor)
    return leidas
