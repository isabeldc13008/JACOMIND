#!/usr/bin/env bash
# Respaldo consistente de SQLite + manifiesto; conserva los últimos 30 días.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY="${PYTHON:-/opt/jacomind/venv/bin/python}"
"$PY" -m api respaldo
find "${JACOMIND_VAR:?}/respaldos" -type f -mtime +30 -delete
