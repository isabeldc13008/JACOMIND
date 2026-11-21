#!/usr/bin/env bash
# Instala JACOMIND en una instancia Amazon Lightsail (Ubuntu 24.04 LTS).
#
# Uso (en la instancia, por SSH):
#   curl -fsSL https://raw.githubusercontent.com/isabeldc13008/JACOMIND/main/despliegue/lightsail/instalar.sh -o instalar.sh
#   sudo DOMINIO=jacomind.ejemplo.com bash instalar.sh
#
# Variables opcionales:
#   DOMINIO      nombre DNS que apunta a la IP estática. Vacío = solo HTTP por IP (pruebas).
#   CORREO_TLS   correo para avisos de Let's Encrypt (opcional).
#   RAMA         rama a desplegar (por defecto: main).
#   REPO_URL     repositorio (por defecto: el de GitHub).
#   CON_LLM      1 = instala LangChain/LangGraph para el asistente con modelo (por defecto: 0).
#   LOGIN_DEMO   1 = inicio de sesión con identidades ficticias (demo). 0 = solo proxy de identidad.
#   DEMO         1 = carga datos ficticios de demostración la primera vez (por defecto: 1).
#
# Se puede volver a ejecutar: actualiza el código y la configuración sin borrar datos.
set -euo pipefail

DOMINIO="${DOMINIO:-}"
CORREO_TLS="${CORREO_TLS:-}"
RAMA="${RAMA:-main}"
REPO_URL="${REPO_URL:-https://github.com/isabeldc13008/JACOMIND.git}"
CON_LLM="${CON_LLM:-0}"
LOGIN_DEMO="${LOGIN_DEMO:-1}"
DEMO="${DEMO:-1}"

USUARIO=jacomind
APP=/opt/jacomind/app
VENV=/opt/jacomind/venv
DATOS=/var/lib/jacomind
CONF=/etc/jacomind
ENV_FILE="$CONF/jacomind.env"

[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo"; exit 1; }
log() { printf '\n==> %s\n' "$*"; }

log "Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv git caddy sqlite3 curl

log "Memoria de intercambio (instancias de 0,5–1 GB)"
if ! swapon --show | grep -q /swapfile; then
  if { [ -f /swapfile ] || { fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null; }; } && swapon /swapfile 2>/dev/null; then
    grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  else
    echo "Aviso: no se pudo activar la memoria de intercambio (se continúa sin ella)"
  fi
fi

log "Usuario y directorios"
id "$USUARIO" >/dev/null 2>&1 || useradd --system --home /opt/jacomind --shell /usr/sbin/nologin "$USUARIO"
mkdir -p /opt/jacomind "$DATOS"/{var,salida,datos} "$CONF"
chown -R "$USUARIO:$USUARIO" /opt/jacomind "$DATOS"

log "Código ($REPO_URL, rama $RAMA)"
if [ -d "$APP/.git" ]; then
  sudo -u "$USUARIO" git -C "$APP" fetch -q origin "$RAMA"
  sudo -u "$USUARIO" git -C "$APP" checkout -q "$RAMA"
  sudo -u "$USUARIO" git -C "$APP" reset -q --hard "origin/$RAMA"
else
  sudo -u "$USUARIO" git clone -q --branch "$RAMA" "$REPO_URL" "$APP"
fi

log "Entorno Python"
if [ ! -x "$VENV/bin/python" ]; then
  sudo -u "$USUARIO" python3 -m venv "$VENV"
fi
if [ "$CON_LLM" = "1" ]; then
  sudo -u "$USUARIO" "$VENV/bin/pip" install -q --upgrade pip
  sudo -u "$USUARIO" "$VENV/bin/pip" install -q -r "$APP/requirements-llm.txt"
fi

log "Configuración y secretos ($ENV_FILE)"
if [ ! -f "$ENV_FILE" ]; then
  cp "$APP/.env.example" "$ENV_FILE"
  cat >> "$ENV_FILE" <<EOF

# --- Lightsail (generado por instalar.sh) ---
JACOMIND_DB=$DATOS/var/jacomind.sqlite3
JACOMIND_VAR=$DATOS/var
JACOMIND_SALIDA=$DATOS/salida
JACOMIND_DATOS=$DATOS/datos
JACOMIND_ENV=$ENV_FILE
EOF
fi
# Valores que dependen de esta ejecución (se reescriben siempre).
sed -i '/^JACOMIND_COOKIE_SEGURA=/d; /^JACOMIND_LLM=/d' "$ENV_FILE"
if [ -n "$DOMINIO" ]; then echo "JACOMIND_COOKIE_SEGURA=1" >> "$ENV_FILE"; else echo "JACOMIND_COOKIE_SEGURA=0" >> "$ENV_FILE"; fi
echo "JACOMIND_LLM=$CON_LLM" >> "$ENV_FILE"
chown root:"$USUARIO" "$ENV_FILE"
chmod 640 "$ENV_FILE"

log "Base de datos"
set -a; . "$ENV_FILE"; set +a
cd "$APP"
if [ "$DEMO" = "1" ]; then
  sudo -u "$USUARIO" --preserve-env "$VENV/bin/python" -m api demo >/dev/null
else
  sudo -u "$USUARIO" --preserve-env "$VENV/bin/python" -m api migrar >/dev/null
fi

log "Servicios systemd"
ARGS_LOGIN=""
[ "$LOGIN_DEMO" = "1" ] || ARGS_LOGIN="--sin-login-demo"
sed -e "s|@APP@|$APP|g" -e "s|@VENV@|$VENV|g" -e "s|@ENV@|$ENV_FILE|g" -e "s|@USUARIO@|$USUARIO|g" \
    -e "s|@DATOS@|$DATOS|g" -e "s|@ARGS_LOGIN@|$ARGS_LOGIN|g" \
    "$APP/despliegue/lightsail/jacomind.service" > /etc/systemd/system/jacomind.service
for u in jacomind-respaldo.service jacomind-respaldo.timer jacomind-cierre.service jacomind-cierre.timer; do
  sed -e "s|@APP@|$APP|g" -e "s|@VENV@|$VENV|g" -e "s|@ENV@|$ENV_FILE|g" -e "s|@USUARIO@|$USUARIO|g" -e "s|@DATOS@|$DATOS|g" \
      "$APP/despliegue/lightsail/$u" > "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now jacomind.service jacomind-respaldo.timer >/dev/null
systemctl restart jacomind.service
# El cierre mensual programado solo se activa si ya hay insumos en $DATOS/datos.
if [ -n "$(ls -A "$DATOS/datos" 2>/dev/null)" ]; then
  systemctl enable --now jacomind-cierre.timer >/dev/null
else
  echo "Cierre mensual programado: inactivo hasta copiar los insumos en $DATOS/datos"
fi

log "Caddy (proxy inverso${DOMINIO:+ con HTTPS para $DOMINIO})"
mkdir -p /var/log/caddy && chown caddy:caddy /var/log/caddy
{
  if [ -n "$CORREO_TLS" ]; then printf '{\n\temail %s\n}\n\n' "$CORREO_TLS"; fi
  if [ -n "$DOMINIO" ]; then printf '%s {\n' "$DOMINIO"; else printf ':80 {\n'; fi
  cat "$APP/despliegue/lightsail/Caddyfile.bloque"
  printf '}\n'
} > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy >/dev/null
systemctl reload caddy || systemctl restart caddy

log "Comprobación"
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/api/estado >/dev/null; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8000/api/estado && echo
URL="http://$(curl -fsS --max-time 3 https://checkip.amazonaws.com 2>/dev/null || echo IP-DE-LA-INSTANCIA)/app/"
[ -n "$DOMINIO" ] && URL="https://$DOMINIO/app/"
cat <<EOF

JACOMIND instalado.
  Aplicación:   $URL
  Secretos:     sudo nano $ENV_FILE   (GEMINI_API_KEY / ANTHROPIC_API_KEY) y luego: sudo systemctl restart jacomind
  Registros:    journalctl -u jacomind -f
  Respaldos:    $DATOS/var/respaldos (diario, 03:30)
  Actualizar:   sudo bash $APP/despliegue/lightsail/actualizar.sh
EOF
