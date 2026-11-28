# Despliegue en Azure App Service

Azure App Service es el entorno de **staging** y se despliega **solo a mano**. La demo
pública sigue en AWS Lightsail, que se actualiza sola tras cada CI correcto de `main`.

Para desplegar en Azure: **Actions → Despliegue → Run workflow**, destino `azure`. Se
publica el commit de la rama elegida.

## Configuración única en GitHub

| Tipo | Nombre | Contenido |
|---|---|---|
| Secreto del repositorio | `AZURE_WEBAPP_PUBLISH_PROFILE` | Perfil de publicación descargado del App Service (**Descargar perfil de publicación**) |

El trabajo usa el entorno de GitHub `azure-staging`, separado de `produccion` (Lightsail).

## Configuración en el App Service

- **Comando de inicio** (Configuración → General): `python despliegue/arranque_demo.py`
- **Configuración de la aplicación** (variables de entorno, nunca en el repositorio):
  `JACOMIND_ADMIN_PASSWORD` con una clave propia de 8 o más caracteres. Sin ella no se crea
  el administrador local: la URL es pública y la clave por defecto `admin123` la podría
  usar cualquiera.

## Puesta en marcha

1. En Azure crea o conserva el App Service Linux `jacomind-stg-211126` dentro de
   `rg-jacomind-staging`, en una región permitida por la suscripción.
2. Configura la pila Python 3.12.
3. Define el comando de inicio, `JACOMIND_ADMIN_PASSWORD` y el secreto del perfil de publicación.
4. Ejecuta **Actions → Despliegue → Run workflow** con destino `azure`.
5. Comprueba `https://jacomind-stg-211126.azurewebsites.net/api/estado` y entra en
   `/app/` con el usuario `admin`.

Al arrancar se ejecutan las migraciones y se prepara la demo. La contraseña nunca se
escribe en un archivo del repositorio.

## Dominio DuckDNS

`jacomind-demo.duckdns.org` apunta a Lightsail. No lo cambies a Azure mientras Lightsail
sea la demo pública.
