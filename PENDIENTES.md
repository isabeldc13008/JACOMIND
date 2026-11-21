# Pendientes: despliegue en Lightsail y CI/CD

Lista de trabajo para quien termine la puesta en producción. Ya está hecho: aplicación (B01–B11), datos y modelos (A01–A11) integrados en `main` y scripts de despliegue en [`despliegue/lightsail/`](despliegue/lightsail/). Guía detallada: [docs/despliegue.md](docs/despliegue.md).

Marca cada casilla al terminar y deja en el PR la evidencia indicada.

## 1. Revisar los cambios hechos en el código de A

En la integración (PR #1) se modificó código del carril A. Su autor debe revisarlo antes de desplegar:

- [ ] `pipeline/generar.py`: genera la publicación C2 con la agenda C1 encadenando A01–A09.
- [ ] `pipeline/rutas.py` y pruebas de `tests/datos`/`tests/modelos`: sin rutas fijas; el paquete se busca en `JACOMIND_DATOS` o en la carpeta hermana.
- [ ] `pipeline/pqrs.py`: salida conforme a C4 (`categoria: null` y `revisar: true` cuando va a revisión).
- [ ] `pipeline/oportunidades.py`: venta cruzada por co-ocurrencia; **empata con popularidad (11/69)**. Decidir si se mantiene.
- [ ] `pipeline/pronostico.py`: error por horizonte con origen creciente frente al ingenuo.

**Evidencia:** comentario de aprobación en el PR o PR con los ajustes.

## 2. Desplegar en Lightsail (primera vez)

`instalar.sh` **no se ha ejecutado aún en una instancia real**. Esta es la primera prueba; si un paso falla, corrige el script en un PR.

- [ ] Crear una alerta de presupuesto en AWS Budgets (p. ej. 10 USD/mes) antes de crear recursos.
- [ ] Crear la instancia: Ubuntu 24.04 LTS, plan de 1 GB (7 USD/mes), región cercana a los usuarios.
- [ ] Asignar una IP estática. En el firewall, abrir 80 y 443 y limitar el 22 a IPs conocidas.
- [ ] Crear el registro DNS `A` del dominio hacia la IP estática.
- [ ] Ejecutar en la instancia:
  ```bash
  curl -fsSL https://raw.githubusercontent.com/isabeldc13008/JACOMIND/main/despliegue/lightsail/instalar.sh -o instalar.sh
  sudo DOMINIO=<dominio> CORREO_TLS=<correo> bash instalar.sh
  ```
- [ ] Comprobar que `https://<dominio>/app/` carga con certificado válido y que `https://<dominio>/api/estado` responde.
- [ ] Comprobar que la cookie de sesión lleva `Secure` (herramientas del navegador → Application → Cookies).
- [ ] Comprobar que `http://<IP>:8000` **no** responde desde fuera, porque la app solo escucha en local.
- [ ] Opcional: claves de Gemini y Anthropic en `/etc/jacomind/jacomind.env` y `sudo systemctl restart jacomind`.
- [ ] Copiar `01_Datos` a `/var/lib/jacomind/datos/`, publicar el cierre de octubre (ver `docs/despliegue.md`, paso 5) y activar `jacomind-cierre.timer`.
- [ ] Verificar en la app el cierre de octubre: 120 clientes, 1.371 ventas, 5.647.449.456,36 COP y 41 fríos.
- [ ] `systemctl list-timers 'jacomind-*'` muestra el respaldo diario y el cierre mensual.
- [ ] Ensayar una restauración: `python -m api restaurar` hacia una base aislada (ver `docs/operacion.md`) y anotar el tiempo.
- [ ] Sacar los respaldos de la instancia: activar snapshots automáticos de Lightsail (de pago) o copiar `/var/lib/jacomind/var/respaldos` a S3 u otro destino.

**Evidencia:** URL desplegada, captura de la agenda, salida de `systemctl status jacomind` y tiempo de restauración.

## 3. Crear el CI (integración continua)

Crear `.github/workflows/ci.yml`, que se ejecute en cada `pull_request` y en cada `push` a `main`.

- [ ] Matriz de Python 3.10 y 3.12 (en el servidor corre 3.12; el mínimo admitido es 3.10). Sin dependencias para las pruebas base.
- [ ] Pasos de prueba:
  ```bash
  python -m unittest discover                                          # carril A
  python -m unittest discover -s tests/app -t tests/app                # carril B
  python -m unittest discover -s tests/integracion -t tests/integracion
  python -m contratos.validar --publicacion contratos/ejemplos/publicacion/demo-2026-10
  ```
- [ ] Un trabajo adicional con `pip install -r requirements-llm.txt` que ejecute las pruebas de B. Comprueba que el agente funciona con LangGraph instalado, **sin** claves de API.
- [ ] `node --check app/contrato.js` y `node --input-type=module --check < app/app.js`.
- [ ] Lint de shell: `shellcheck despliegue/lightsail/*.sh` (y `bash -n` sobre cada script).
- [ ] Comprobar que los scripts de despliegue conservan finales LF (`git ls-files --eol despliegue/`).
- [ ] Decidir qué hacer con los datos. Sin el paquete `Green_Services_Recursos_de_Prueba`, las pruebas que lo necesitan **se omiten solas**. Si se quiere ejecutarlas en CI, guardar el paquete sintético como artefacto privado o en un repositorio aparte y exponerlo con `JACOMIND_DATOS`. **Nunca** subir datos empresariales.
- [ ] Proteger `main`: exigir que el CI pase y una revisión aprobada antes de fusionar.

**Aceptación:** un PR con una prueba rota queda bloqueado y uno correcto se puede fusionar.

## 4. Crear el CD (despliegue continuo)

Crear `.github/workflows/cd.yml`, que se ejecute después del CI en `main`, más un disparo manual (`workflow_dispatch`).

- [ ] Crear un *environment* `produccion` en GitHub con aprobación manual obligatoria.
- [ ] Crear en ese environment los secretos `LIGHTSAIL_HOST` (IP estática o dominio), `LIGHTSAIL_USER` (`ubuntu`), `LIGHTSAIL_SSH_KEY` (clave privada dedicada al CD, **no** la clave por defecto de la cuenta) y `LIGHTSAIL_KNOWN_HOSTS`, cuyo valor se obtiene con `ssh-keyscan <host>` para fijar la huella del servidor.
- [ ] En la instancia, añadir la clave pública del CD a `~ubuntu/.ssh/authorized_keys`. El usuario `ubuntu` ya tiene `sudo` sin contraseña en Lightsail.
- [ ] El paso de despliegue entra por SSH y ejecuta:
  ```bash
  sudo bash /opt/jacomind/app/despliegue/lightsail/actualizar.sh main
  ```
  El script hace un respaldo previo, actualiza el código, migra la base y reinicia el servicio.
- [ ] Verificación posterior: `curl -fsS https://<dominio>/api/estado` debe responder 200. Si falla, el workflow se marca en rojo.
- [ ] Documentar la vuelta atrás: `sudo bash actualizar.sh <rama-o-commit-anterior>`. Si la base se dañó, detener el servicio, restaurar el respaldo previo al despliegue y volver a arrancarlo.
- [ ] Concurrencia: `concurrency: produccion` para que nunca corran dos despliegues a la vez.
- [ ] Opcional: abrir el puerto 22 solo a los rangos de GitHub Actions o usar un runner autohospedado.

**Aceptación:** fusionar un cambio visible (p. ej. un texto de la interfaz) en `main` lo publica en el servidor tras la aprobación y la verificación pasa.

## 5. Antes de usar datos reales de Green

- [ ] Desactivar el inicio de sesión de demostración (`LOGIN_DEMO=0` al reinstalar) y poner delante un proveedor de identidad.
  - Caddy con `forward_auth` debe eliminar la cabecera `X-Usuario-Autenticado` del cliente y fijarla solo tras autenticar.
  - Activar `JACOMIND_PROXY_AUTH=1`.
- [ ] Acordar con Green la retención de registros y respaldos y quién accede a la instancia.
- [ ] Ejecutar el piloto por rol con el guion de `docs/demo.md` y registrar resultados.
