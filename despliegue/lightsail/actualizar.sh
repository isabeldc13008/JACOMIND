#!/usr/bin/env bash
# Actualiza el código a la última versión de la rama, migra la base y reinicia.
# Uso: sudo bash /opt/jacomind/app/despliegue/lightsail/actualizar.sh [rama]
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo"; exit 1; }
APP=/opt/jacomind/app
VENV=/opt/jacomind/venv
RAMA="${1:-$(sudo -u jacomind git -C "$APP" rev-parse --abbrev-ref HEAD)}"
set -a; . /etc/jacomind/jacomind.env; set +a

sudo -u jacomind --preserve-env "$VENV/bin/python" -m api --db "$JACOMIND_DB" respaldo >/dev/null   # respaldo previo
sudo -u jacomind git -C "$APP" fetch -q origin "$RAMA"
sudo -u jacomind git -C "$APP" reset -q --hard "origin/$RAMA"
if "$VENV/bin/python" -c "import langgraph" 2>/dev/null; then
  sudo -u jacomind "$VENV/bin/pip" install -q -r "$APP/requirements-llm.txt"
fi
cd "$APP"
sudo -u jacomind --preserve-env "$VENV/bin/python" -m api migrar >/dev/null
systemctl restart jacomind
sleep 2
curl -fsS http://127.0.0.1:8000/api/estado && echo
echo "Actualizado a $(sudo -u jacomind git -C "$APP" log --oneline -1)"
