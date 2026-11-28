# Inicio de sesión y administración de roles — Diseño

## Intención

Mejorar el acceso de JACOMIND a partir del estado del despliegue #9 e incorporar una cuenta administrativa inicial capaz de gestionar usuarios, roles y permisos sin exponer contraseñas ni ampliar autorizaciones por accidente.

## Objetivos

- Conservar el acceso externo por proveedor aprobado del despliegue #9.
- Mantener los perfiles ficticios únicamente para demostración/local.
- Añadir autenticación local para usuarios administrados.
- Crear el usuario inicial `admin` con contraseña temporal `admin123`.
- Forzar el cambio de contraseña en el primer acceso.
- Permitir al administrador crear, editar, activar/desactivar roles y asignar permisos existentes.
- Permitir asignar roles a identidades administradas.
- Registrar en auditoría los cambios administrativos.

## No objetivos

- No se implementará recuperación de contraseña por correo en esta primera entrega.
- No se crearán permisos arbitrarios desde la interfaz.
- No se reemplazará el proveedor externo del piloto.
- No se permitirá que un administrador se asigne permisos fuera de la matriz registrada sin una acción explícita.

## Restricciones y decisiones

- La contraseña se almacenará únicamente como hash seguro usando la biblioteca estándar disponible; nunca se guardará `admin123` en texto plano en la base.
- `admin123` será una credencial de bootstrap temporal: el primer acceso con ella exigirá definir una nueva contraseña.
- El bootstrap será idempotente: no sobrescribirá una cuenta admin ya configurada.
- La cuenta admin será interna, tendrá un permiso administrativo dedicado y no dependerá de los roles comerciales existentes.
- Los roles administrables se almacenarán en base de datos. Sus nombres serán únicos, normalizados y no vacíos.
- Solo se podrán asignar acciones que existan en el catálogo autorizado de permisos; el administrador no podrá crear acciones nuevas desde la UI.
- Las sesiones locales conservarán la cookie `HttpOnly; SameSite=Strict`; en producción se respetará `JACOMIND_COOKIE_SEGURA=1`.
- Los endpoints administrativos exigirán sesión y el permiso `usuarios.administrar`.
- Los cambios de usuarios y roles se registrarán con actor, recurso, operación y resultado.

## Flujo previsto

1. El usuario abre la pantalla de acceso.
2. Puede entrar por proveedor externo, por perfil de demostración cuando esté habilitado, o con usuario/contraseña local cuando la base lo permita.
3. Si una cuenta local tiene contraseña temporal, la aplicación dirige a cambio obligatorio antes de mostrar el resto del sistema.
4. El administrador entra a Administración > Usuarios y roles.
5. Puede crear/editar/desactivar roles, seleccionar permisos existentes y asignarlos a usuarios.
6. Un usuario desactivado o una sesión cuyo usuario fue desactivado deja de resolver como identidad válida.

## Enfoques considerados

1. **Solo mejorar la selección de perfiles ficticios.** Menor riesgo, pero no satisface la necesidad de una administración real.
2. **Autenticación local aislada de la matriz actual.** Permite usuarios y contraseñas, pero duplicaría reglas de permisos y aumentaría el riesgo de divergencia.
3. **Autenticación local integrada con identidades, pertenencias y permisos existentes — elegido.** Reutiliza el modelo del despliegue #9, añade hash/sesión y una capa administrativa pequeña, y mantiene el proveedor externo y la demo separados por configuración.

## Resultado esperado

El login será claro para los tres modos de acceso, la cuenta bootstrap podrá convertirse en una cuenta segura, y los roles/usuarios gestionados por el administrador podrán autorizarse desde el mismo servidor que ya protege las rutas de JACOMIND.
