#!/usr/bin/env bash
# Cierre del mes anterior: genera con pipeline/ (A), valida C1/C2 y publica.
# Si algo falla, la aplicación conserva el último cierre válido.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${PYTHON:-/opt/jacomind/venv/bin/python}"
CORTE="${CORTE:-$(date -d "$(date +%Y-%m-01) -1 day" +%F)}"
"$PY" -m api cierre --corte "$CORTE" --datos "${JACOMIND_DATOS:?}" --actor programador
