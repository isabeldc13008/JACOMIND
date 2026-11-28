# Despliegue en Azure App Service

JACOMIND se publica en Azure App Service para Linux desde GitHub Actions. El flujo
`.github/workflows/despliegue.yml` se ejecuta después del CI de `main` o manualmente.

## Configuración única en GitHub

En **Settings → Environments → produccion** crea estas variables:

| Variable | Valor para el entorno actual |
|---|---|
| `AZURE_RESOURCE_GROUP` | `rg-jacomind-staging` |
| `AZURE_WEBAPP_NAME` | `jacomind-stg-211126` |
| `URL_PUBLICA` | `https://jacomind-stg-211126.azurewebsites.net` |

Añade estos secretos:

| Secreto | Contenido |
|---|---|
| `AZURE_CREDENTIALS` | JSON de una identidad de despliegue con permisos sobre el App Service |
| `JACOMIND_ADMIN_PASSWORD` | Contraseña inicial del usuario `admin` |

`AZURE_CREDENTIALS` puede ser un service principal con el rol **Contributor**
limitado al grupo `rg-jacomind-staging`. No se debe guardar en el repositorio.

## Puesta en marcha

1. En Azure crea o conserva el App Service Linux `jacomind-stg-211126` dentro de
   `rg-jacomind-staging`, en una región permitida por la suscripción.
2. Configura Python 3.12 y deja que el workflow establezca el comando de inicio.
3. Define las tres variables y los dos secretos del entorno `produccion`.
4. Ejecuta **Actions → Despliegue → Run workflow** para una primera publicación.
5. Comprueba `https://jacomind-stg-211126.azurewebsites.net/api/estado` y entra en
   `/app/` con el usuario `admin`.

El workflow activa el inicio de sesión local, ejecuta las migraciones al arrancar,
configura el administrador y publica únicamente el commit aprobado por CI. La
contraseña nunca se escribe en un archivo del repositorio.

## Dominio DuckDNS

El dominio `jacomind-demo.duckdns.org` debe apuntar al App Service para mostrar esta
versión. En Azure se puede añadir como **Dominio personalizado** y validar el registro
DNS solicitado. Hasta completar esa asociación, el dominio y la URL
`azurewebsites.net` pueden servir despliegues distintos.
