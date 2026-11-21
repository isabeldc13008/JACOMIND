#!/usr/bin/env bash
# Prueba instalar.sh y actualizar.sh en un Ubuntu 24.04 con systemd (simula Lightsail).
# Requiere Docker. Uso, desde la raíz del repo:
#   bash despliegue/lightsail/prueba/probar-instalacion.sh          # deja el contenedor en http://localhost:8080/app/
#   LIMPIAR=1 bash despliegue/lightsail/prueba/probar-instalacion.sh  # lo elimina al terminar (CI)
# Variables: RAMA (rama a desplegar, por defecto la actual), PUERTO (8080).
set -euo pipefail
export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/../../.."
NOMBRE=jacomind-lightsail-prueba
PUERTO="${PUERTO:-8080}"
RAMA="${RAMA:-$(git rev-parse --abbrev-ref HEAD)}"

docker build -q -t jacomind-lightsail-sim despliegue/lightsail/prueba >/dev/null
docker rm -f "$NOMBRE" >/dev/null 2>&1 || true
docker run -d --name "$NOMBRE" --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  --tmpfs /run --tmpfs /run/lock -p "$PUERTO:80" jacomind-lightsail-sim >/dev/null
trap '[ "${LIMPIAR:-0}" = "1" ] && docker rm -f "$NOMBRE" >/dev/null' EXIT
for _ in $(seq 1 30); do docker exec "$NOMBRE" systemctl is-system-running 2>/dev/null | grep -qE 'running|degraded' && break; sleep 1; done

echo "==> instalar.sh (rama $RAMA)"
docker cp despliegue/lightsail/instalar.sh "$NOMBRE":/root/instalar.sh
docker exec -e RAMA="$RAMA" "$NOMBRE" bash /root/instalar.sh
echo "==> comprobaciones"
docker exec "$NOMBRE" systemctl is-active jacomind caddy jacomind-respaldo.timer
docker exec "$NOMBRE" bash -c 'ps -eo user,cmd | grep "[a]pi servir" | grep -q "^jacomind "'
curl -fsS "http://127.0.0.1:$PUERTO/api/estado" >/dev/null
curl -fsS "http://127.0.0.1:$PUERTO/app/" >/dev/null
echo "==> actualizar.sh"
docker exec "$NOMBRE" bash /opt/jacomind/app/despliegue/lightsail/actualizar.sh "$RAMA" >/dev/null
docker exec "$NOMBRE" bash -c 'ls /var/lib/jacomind/var/respaldos/*.sqlite3 >/dev/null'
echo "==> reinstalación (idempotente)"
docker exec -e RAMA="$RAMA" "$NOMBRE" bash /root/instalar.sh >/dev/null
docker exec "$NOMBRE" systemctl is-active jacomind caddy >/dev/null
echo "OK: instalación probada. Aplicación en http://localhost:$PUERTO/app/"
