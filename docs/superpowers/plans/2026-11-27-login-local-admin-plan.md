# Inicio de sesión local y administración de usuarios Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Añadir login local seguro y un panel `admin` para gestionar usuarios y roles de los perfiles actuales.

**Architecture:** Extender la capa existente de `api/auth.py` y SQLite sin reemplazar los permisos actuales. El frontend seguirá usando la sesión por cookie y mostrará login/admin según el usuario autenticado; el modo demo continuará disponible con `LOGIN_DEMO=1`.

**Tech Stack:** Python 3.10+, SQLite, biblioteca estándar (`hashlib`, `hmac`, `secrets`), JavaScript del navegador sin dependencias, `unittest`.

**Spec:** `docs/superpowers/specs/2026-11-27-login-local-admin-design.md`

## Global Constraints

- No guardar contraseñas en texto plano.
- Reutilizar roles y acciones existentes de `api/permisos.py`.
- Mantener el modo demo separado y explícito.
- No introducir dependencias externas para el login básico.
- No romper las sesiones ficticias actuales durante la transición.

## Review Focus

- Contraseña incorrecta o usuario inactivo: rechazo uniforme sin revelar qué dato falló; prueba en `tests/test_auth_local.py`.
- Contraseña almacenada: nunca aparece en SQLite ni en respuestas; prueba de hash y respuesta API.
- Usuario sin `admin`: recibe 403 en administración; prueba de autorización.
- Repetición de nombre de usuario: respuesta 409 y no duplica cuentas; prueba de creación.
- Cookie HTTPS: conserva `HttpOnly`, `SameSite=Strict` y añade `Secure` cuando la configuración lo exige; prueba de integración.

### Task 1: Persistencia y hash de credenciales

**Files:**
- Create: `api/migraciones/0009_usuarios_locales.sql`
- Modify: `api/auth.py`, `api/permisos.py`
- Test: `tests/test_auth_local.py`

- [ ] Escribir pruebas para hash, verificación, alta, baja y login local.
- [ ] Ejecutar las pruebas y observar el fallo esperado.
- [ ] Implementar `hash_password`, `verify_password`, `crear_usuario_local`, `desactivar_usuario_local` y `cargar_usuario_local` con PBKDF2-HMAC-SHA256.
- [ ] Ejecutar las pruebas y confirmar que pasan.
- [ ] Commit: `feat: add local credential storage`

### Task 2: API de sesión y administración

**Files:**
- Modify: `api/servidor.py`, `api/auth.py`, `api/__main__.py`
- Test: `tests/test_auth_local.py`, `tests/integracion/test_int_servidor.py`

- [ ] Añadir login local y resolución de sesión junto al login demo.
- [ ] Añadir `GET /api/usuarios`, `POST /api/usuarios`, `PATCH /api/usuarios/{id}` y protegerlos con `admin`.
- [ ] Crear el admin inicial desde `JACOMIND_ADMIN_USUARIO` y `JACOMIND_ADMIN_PASSWORD` al migrar; si faltan, no crear credenciales por defecto.
- [ ] Mantener cookies seguras y mensajes de error genéricos.
- [ ] Ejecutar pruebas de API y permisos.
- [ ] Commit: `feat: expose local auth and admin user API`

### Task 3: Login y panel de administración

**Files:**
- Modify: `app/app.js`, `app/navegacion.js`
- Create: `app/vistas/admin.js`
- Test: `tests/app/test_app_auth.js` o prueba equivalente existente.

- [ ] Reemplazar el acceso principal por formulario de usuario/contraseña cuando el login local esté activo.
- [ ] Mantener el selector demo únicamente cuando `login_demo` esté activo.
- [ ] Añadir navegación visible solo para `admin`.
- [ ] Crear formulario de usuario, rol y estado; no mostrar contraseñas existentes.
- [ ] Ejecutar `node --check` para los módulos JavaScript.
- [ ] Commit: `feat: add login and admin user screen`

### Task 4: Configuración y documentación de Azure

**Files:**
- Modify: `.env.example`, `docs/operacion.md`, `docs/despliegue.md`
- Test: `tests/test_auth_local.py`

- [ ] Documentar variables de Azure y el procedimiento de crear el primer admin sin subir secretos a GitHub.
- [ ] Documentar transición: validar login local, crear usuarios demo, luego cambiar `LOGIN_DEMO=0`.
- [ ] Verificar lint, pruebas base y estado del despliegue.
- [ ] Commit: `docs: document local auth setup on Azure`

### Task 5: Verificación y entrega

- [ ] Ejecutar las suites disponibles y `git diff --check`.
- [ ] Revisar manualmente login de admin, creación de una cuenta por rol, rechazo de cuenta inactiva y acceso restringido.
- [ ] Crear PR hacia `main` y desplegar a Azure solo después de confirmar variables seguras.
