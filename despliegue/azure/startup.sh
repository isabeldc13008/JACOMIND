#!/usr/bin/env bash
set -euo pipefail

APP_DATA="${JACOMIND_VAR:-/home/data/var}"
mkdir -p "$APP_DATA" "${JACOMIND_SALIDA:-/home/data/salida}" "${JACOMIND_DATOS:-/home/data/datos}"

python -m api migrar
exec python -m api servir \
  --host 0.0.0.0 \
  --puerto "${PORT:-8000}"
