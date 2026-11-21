# Despliegue en Amazon Lightsail

Un único servidor Ubuntu ejecuta la aplicación (Python, biblioteca estándar y SQLite) detrás de Caddy, que obtiene y renueva solo el certificado HTTPS. Los archivos están en [`despliegue/lightsail/`](../despliegue/lightsail/).

```
Internet ──443/80──▶ Caddy (HTTPS, compresión) ──127.0.0.1:8000──▶ jacomind.service (python -m api servir)
                                                                    │
                                     /var/lib/jacomind/var ◀────────┘  SQLite, cargas, lotes, respaldos
                                     /var/lib/jacomind/salida          publicaciones de cada cierre
                                     /var/lib/jacomind/datos           insumos del cierre (no se versionan)
                                     /etc/jacomind/jacomind.env        configuración y claves (640, root:jacomind)
```

## Coste

| Plan Lightsail (Linux, IPv4 pública) | Precio | Uso recomendado |
|---|---|---|
| 0,5 GB RAM, 2 vCPU, 20 GB SSD | 5 USD/mes | demo sin asistente con modelo de lenguaje |
| **1 GB RAM, 2 vCPU, 40 GB SSD** | **7 USD/mes** | **recomendado**; también con LangChain/LangGraph (`CON_LLM=1`) |

Lightsail ofrece por tiempo limitado tres meses gratis en planes seleccionados; después se cobra el precio fijo. Los snapshots se cobran aparte. Las llamadas a Gemini o Anthropic se facturan en sus propias cuentas. Crea un presupuesto con alerta en AWS Budgets el primer día.

## 1. Crear la instancia

1. En la consola de Lightsail, **Create instance**. Región: la más cercana a los usuarios, por ejemplo `us-east-1`. Plataforma **Linux/Unix**, blueprint **OS Only → Ubuntu 24.04 LTS** y plan de **7 USD** (1 GB) con IPv4.
2. Nombre: `jacomind`. Crear.
3. **Networking → Create static IP** y asígnala a la instancia. Es gratuita mientras esté asociada.
4. **Networking → IPv4 Firewall**: deja `SSH 22` (restringe la IP de origen si puedes) y añade `HTTP 80` y `HTTPS 443`.

## 2. Dominio (para HTTPS)

Crea un registro DNS `A` que apunte a la IP estática, por ejemplo `jacomind.tudominio.com`. Puedes usar Lightsail DNS, tu proveedor o un subdominio gratuito (DuckDNS u otro). Sin dominio la aplicación funciona solo por HTTP en la IP, lo cual sirve únicamente para pruebas: la sesión viaja sin cifrar.

## 3. Instalar

Abre la consola SSH del navegador (botón **Connect**) y ejecuta:

```bash
curl -fsSL https://raw.githubusercontent.com/isabeldc13008/JACOMIND/main/despliegue/lightsail/instalar.sh -o instalar.sh
sudo DOMINIO=jacomind.tudominio.com CORREO_TLS=tu@correo.com bash instalar.sh
```

| Variable | Por defecto | Efecto |
|---|---|---|
| `DOMINIO` | vacío | con valor: HTTPS automático y cookie `Secure`; vacío: HTTP en el puerto 80 |
| `CORREO_TLS` | vacío | correo para avisos de Let's Encrypt |
| `RAMA` | `main` | rama del repositorio que se despliega |
| `CON_LLM` | `0` | `1` instala LangChain/LangGraph para el asistente con modelo |
| `LOGIN_DEMO` | `1` | `1` permite entrar con identidades ficticias (demo); `0` exige el proxy de identidad del piloto |
| `DEMO` | `1` | `1` carga datos ficticios de demostración la primera vez |

El script es idempotente: puedes repetirlo para cambiar opciones. No borra la base de datos ni las claves.

## 4. Configurar claves (opcional)

```bash
sudo nano /etc/jacomind/jacomind.env     # GEMINI_API_KEY=..., ANTHROPIC_API_KEY=...
sudo systemctl restart jacomind
```

Sin claves, el asistente responde con plantillas deterministas.

## 5. Cargar los datos reales y publicar un cierre

El paquete de datos no está en el repositorio. Cópialo desde tu equipo con la clave SSH que descargas en **Account → SSH keys**:

```bash
scp -i LightsailDefaultKey.pem -r ../Green_Services_Recursos_de_Prueba/01_Datos ubuntu@IP-ESTATICA:/tmp/
```

En la instancia:

```bash
sudo mv /tmp/01_Datos /var/lib/jacomind/datos/ && sudo chown -R jacomind:jacomind /var/lib/jacomind/datos
sudo -u jacomind bash -c 'set -a; . /etc/jacomind/jacomind.env; set +a; CORTE=2026-10-31 bash /opt/jacomind/app/despliegue/lightsail/cierre-mensual.sh'
sudo systemctl enable --now jacomind-cierre.timer        # cierre automático el día 2 de cada mes
```

## Operación diaria

| Tarea | Comando |
|---|---|
| Estado y registros | `systemctl status jacomind` · `journalctl -u jacomind -f` |
| Registros de Caddy | `sudo tail -f /var/log/caddy/jacomind.log` |
| Actualizar a la última versión | `sudo bash /opt/jacomind/app/despliegue/lightsail/actualizar.sh` (hace un respaldo antes) |
| Respaldos | automáticos a las 03:30 en `/var/lib/jacomind/var/respaldos`, se conservan 30 días |
| Próximas ejecuciones | `systemctl list-timers 'jacomind-*'` |
| Restaurar en aislado | `sudo -u jacomind /opt/jacomind/venv/bin/python -m api restaurar RESPALDO.sqlite3 --destino /var/lib/jacomind/var/ensayo.sqlite3` |

Para restaurar en producción: `sudo systemctl stop jacomind`, copia el respaldo restaurado sobre `JACOMIND_DB` y luego `sudo systemctl start jacomind`. Los respaldos viven en el mismo disco, así que cópialos fuera de la instancia o crea snapshots manuales o automáticos en Lightsail (de pago) para sobrevivir a la pérdida de la instancia.

## Seguridad

- La aplicación solo escucha en `127.0.0.1:8000`; el único punto de entrada es Caddy.
- El servicio corre con el usuario `jacomind`, sin privilegios. systemd monta el código como solo lectura y solo permite escribir en `/var/lib/jacomind`.
- Con `JACOMIND_PROXY_AUTH=1`, Caddy debe eliminar la cabecera `X-Usuario-Autenticado` que envíe el cliente y fijarla solo tras autenticar (`forward_auth`); si no, cualquiera podría suplantar una identidad.
- Con `LOGIN_DEMO=1`, cualquiera con la URL puede entrar con una identidad ficticia. Úsalo solo con datos sintéticos. Para un piloto con datos reales: `LOGIN_DEMO=0` y un proveedor de identidad delante, que fija la cabecera `X-Usuario-Autenticado` (`JACOMIND_PROXY_AUTH=1`).
- No subas datos empresariales sin la autorización acordada con Green.
