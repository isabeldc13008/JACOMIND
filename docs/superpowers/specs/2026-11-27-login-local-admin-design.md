# Inicio de sesión local y administración de usuarios

## Intención

Sustituir el selector de identidades ficticias por un acceso local con usuario y contraseña para los perfiles actuales de demostración, manteniendo el modo demo como respaldo durante la validación.

## Alcance

- Login con nombre de usuario y contraseña.
- Contraseñas almacenadas únicamente como hash PBKDF2 con sal aleatoria.
- Sesiones con cookie `HttpOnly`, `SameSite=Strict` y `Secure` cuando Azure trabaja con HTTPS.
- Roles existentes: `admin`, `operaciones`, `ventas`, `finanzas`, `atencion`, `gerencia` y `empresa`.
- Primer administrador creado por migración mediante variables de entorno, nunca con una contraseña escrita en el código.
- Pantalla de administración para listar usuarios, crear usuarios, cambiar rol y activar/desactivar cuentas.
- Auditoría de creación, cambios de rol, activación/desactivación e inicio de sesión.

## Fuera de alcance

- Recuperación de contraseña por correo.
- MFA y federación empresarial; se deja preparado el modelo para migrar después a Microsoft Entra ID.
- Eliminación física de usuarios.
- Gestión de organizaciones empresariales más allá del vínculo ya existente.

## Enfoques considerados

1. **Usuarios locales en SQLite**: encaja con la aplicación actual, funciona en Azure sin dependencias nuevas y permite la pantalla de administración solicitada. Es la opción seleccionada para esta etapa.
2. **Microsoft Entra ID**: mejor opción para producción empresarial, pero requiere configuración del tenant, registro de aplicación y administración externa de usuarios.
3. **Azure App Service Authentication**: reduce código local, pero no proporciona una pantalla propia para crear usuarios y asignar los roles de JACOMIND.

## Diseño elegido

Se añadirá una tabla de usuarios autenticables vinculada opcionalmente a `identidades`, con `username` único, `password_hash`, `password_salt`, rol, estado activo y marcas de creación/actualización. El usuario de sesión se resolverá desde la misma capa `auth.py` que hoy resuelve identidades demo, para que los permisos existentes sigan siendo la única fuente de autorización.

La aplicación mostrará el formulario de login cuando el acceso demo esté desactivado o cuando el usuario elija «Entrar con mi perfil». La administración aparecerá solo para `admin`. Las identidades ficticias seguirán disponibles únicamente cuando `LOGIN_DEMO=1`.

## Criterios de aceptación

- Un administrador puede iniciar sesión y crear usuarios para todos los perfiles de demostración.
- Un usuario activo puede iniciar sesión y recibe exactamente los permisos de su rol.
- Un usuario inactivo no puede iniciar sesión.
- Una contraseña nunca aparece en respuestas, logs ni base de datos en texto plano.
- La sesión se invalida al cerrar sesión y expira según la configuración existente.
- Un usuario sin rol admin no puede acceder a la administración.
- El login y la administración funcionan en el despliegue HTTPS de Azure.
