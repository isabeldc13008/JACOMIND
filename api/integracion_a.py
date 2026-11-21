"""Enlace B → A: delega en ``pipeline.generar`` (carril A) para construir la publicación C2.

Se mantiene para la CLI ``python -m api generar-desde-a`` y como respaldo del cierre
programado cuando ``pipeline.generar`` se ejecuta en el mismo proceso.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def disponible() -> bool:
    return importlib.util.find_spec("pipeline") is not None and importlib.util.find_spec("pipeline.generar") is not None


def generar(datos: str | Path, corte: str, salida: str | Path) -> dict:
    from pipeline.generar import generar as generar_a
    return generar_a(datos, corte, salida)
