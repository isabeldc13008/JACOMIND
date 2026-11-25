#!/usr/bin/env bash
# Habilita el despliegue continuo desde GitHub Actions en una instancia ya instalada con instalar.sh.
#
# Uso (en la instancia): sudo CLAVE_PUBLICA="ssh-ed25519 AAAA... jacomind-ci" bash habilitar-cd.sh
#
# Crea el usuario «despliegue», sin contraseña ni shell interactiva útil. Su clave SSH solo puede ejecutar
# /usr/local/sbin/jacomind-desplegar (comando forzado, sin túneles ni terminal) y sudo solo permite ese
# programa. Aunque la clave privada se filtrara, no da acceso de administración a la instancia.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Ejecuta con sudo"; exit 1; }
: "${CLAVE_PUBLICA:?Indica CLAVE_PUBLICA con la clave pública del CI}"
APP=/opt/jacomind/app

install -o root -g root -m 755 "$APP/despliegue/lightsail/jacomind-desplegar" /usr/local/sbin/jacomind-desplegar

id despliegue >/dev/null 2>&1 || useradd --create-home --shell /bin/bash despliegue
passwd -l despliegue >/dev/null
install -d -o despliegue -g despliegue -m 700 /home/despliegue/.ssh
printf 'command="sudo /usr/local/sbin/jacomind-desplegar",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty %s\n' "$CLAVE_PUBLICA" \
  > /home/despliegue/.ssh/authorized_keys
chown despliegue:despliegue /home/despliegue/.ssh/authorized_keys
chmod 600 /home/despliegue/.ssh/authorized_keys

cat > /etc/sudoers.d/jacomind-despliegue <<'EOF'
Defaults!/usr/local/sbin/jacomind-desplegar env_keep += "SSH_ORIGINAL_COMMAND"
despliegue ALL=(root) NOPASSWD: /usr/local/sbin/jacomind-desplegar
EOF
chmod 440 /etc/sudoers.d/jacomind-despliegue
visudo -cf /etc/sudoers.d/jacomind-despliegue >/dev/null

echo "Despliegue continuo habilitado para el usuario «despliegue»."
echo "Huella del servidor para GitHub (secreto LIGHTSAIL_KNOWN_HOSTS):"
for f in /etc/ssh/ssh_host_ed25519_key.pub; do echo "$(curl -fsS --max-time 3 https://checkip.amazonaws.com || hostname -I | cut -d' ' -f1) $(cut -d' ' -f1,2 "$f")"; done
