"""CLI para ejecutar la carga A01."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .carga import cargar_lote


def main() -> int:
    parser = argparse.ArgumentParser(description="Carga, normaliza y valida un lote de datos")
    parser.add_argument("--datos", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()
    result = cargar_lote(args.datos, args.salida, args.config)
    print(json.dumps(result.manifest, ensure_ascii=False, indent=2))
    return 0 if result.status == "publicable" else 2


if __name__ == "__main__":
    raise SystemExit(main())
