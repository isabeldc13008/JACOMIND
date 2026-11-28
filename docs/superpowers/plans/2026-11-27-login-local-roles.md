# Login local y administración de roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir login local seguro con bootstrap `admin/admin123` temporal y gestión administrativa de usuarios, roles y permisos, manteniendo la demo y el proveedor externo del despliegue #9.

**Architecture:** Extender el modelo SQLite mediante una migración nueva y reutilizar `identidades`, `pertenencias` y `permisos`. Centralizar hash/verificación de contraseñas, creación de sesiones y control de bootstrap en `api/auth.py`; exponer rutas administrativas protegidas en `api/servidor.py`; incorporar una vista de acceso y una vista administrativa en la aplicación existente. El permiso administrativo será una acción registrada en el catálogo y resuelta por el servidor en cada solicitud.

**Tech Stack:** Python 3, SQLite, biblioteca estándar (`hashlib`, `hmac`, `secrets`), servidor HTTP existente, JavaScript modular sin dependencias, unittest/pytest según la suite existente.

**Spec:** `docs/superpowers/specs/2026-11-27-login-administrador-roles-design.md`

## Global Constraints

- `admin123` solo es contraseña inicial temporal y exige cambio en el primer acceso.
- Las contraseñas nunca se guardan en texto plano.
- No se crean permisos arbitrarios: solo acciones del catálogo autorizado.
- Se conserva el proveedor externo y la demo local por configuración.
- Las rutas administrativas exigen `usuarios.administrar`.
- Se conserva la cookie `HttpOnly; SameSite=Strict` y `Secure` cuando `JACOMIND_COOKIE_SEGURA=1`.
- Cada mutación administrativa se audita.

## Review Focus

- Cuenta bootstrap inexistente o ya configurada: la preparación debe ser idempotente y no sobrescribir una contraseña cambiada.
- Contraseña temporal en una sesión activa: debe bloquear el acceso normal hasta completar el cambio.
- Usuario o rol desactivado con una sesión existente: la resolución debe rechazarlo.
- Permisos desconocidos o rol duplicado: la API debe responder 400 sin escribir cambios.
- Último administrador o último rol asignado: no debe poder dejarse el sistema sin capacidad administrativa.

### Task 1: Modelo y migración de autenticación local

**Files:**
- Create: `api/migraciones/0008_autenticacion_local.sql`
- Modify: `api/permisos.py`
- Modify: `api/demo.py`
- Test: `tests/datos/test_autenticacion_local.py`

**Interfaces:**
- Produces tables `credenciales_locales`, `roles` and `roles_permisos`, plus the `requiere_cambio_clave` state needed by local identities.
- Produces catalog action `usuarios.administrar`.

- [ ] **Step 1: Write the failing tests**
  - Verify migration creates the new tables and the flag defaults to requiring a change.
  - Verify bootstrap creates exactly one internal `admin` identity and is idempotent.
  - Verify existing demo identities and permission matrix remain available.

- [ ] **Step 2: Run tests to verify they fail**
  - Run: `python -m unittest tests.datos.test_autenticacion_local -v`
  - Expected: FAIL because migration/bootstrap tables and action do not exist.

- [ ] **Step 3: Implement the migration and bootstrap**
  - Add foreign keys and uniqueness constraints for local credentials, roles, role permissions, and user-role memberships.
  - Add `roles` metadata for active state and a protected admin marker.
  - Add `preparar_administrador(db)` in `api/demo.py` or the existing initialization path; seed `admin` with the temporary password only when absent.
  - Keep existing demo seed behavior unchanged.

- [ ] **Step 4: Run tests to verify they pass**
  - Run: `python -m unittest tests.datos.test_autenticacion_local -v`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - Commit: `feat: add local authentication schema and bootstrap admin`

### Task 2: Hash de contraseñas, login y cambio obligatorio

**Files:**
- Modify: `api/auth.py`
- Modify: `api/servidor.py`
- Test: `tests/integracion/test_int_servidor.py`
- Test: `tests/datos/test_autenticacion_local.py`

**Interfaces:**
- Add `hash_clave(clave: str) -> str`.
- Add `verificar_clave(clave: str, almacenada: str) -> bool`.
- Add `crear_sesion_local(db: BaseDatos, usuario: str, clave: str) -> tuple[str, Usuario, bool]`.
- Add `cambiar_clave(db: BaseDatos, identidad_id: str, clave_actual: str, clave_nueva: str) -> None`.
- Extend session resolution to reject inactive identities and expose `requiere_cambio_clave`.

- [ ] **Step 1: Write the failing tests**
  - Login with `admin/admin123` returns a session and a change-required flag.
  - Wrong password returns 401 and does not create a session.
  - New password replaces the bootstrap credential and the old password stops working.
  - Weak/empty passwords return 400.
  - Session cookies retain HttpOnly and SameSite attributes.

- [ ] **Step 2: Run tests to verify they fail**
  - Run: `python -m unittest tests.integracion.test_int_servidor.PruebasServidor -v`
  - Expected: FAIL because local login and password change routes do not exist.

- [ ] **Step 3: Implement minimal authentication**
  - Use a salted, iterated password hash from the standard library and constant-time comparison.
  - Add `POST /api/sesion/local` and `POST /api/sesion/cambiar-clave`.
  - Keep external proxy resolution and demo `POST /api/sesion` behavior intact.
  - Do not reveal whether a username exists in failed-login messages.
  - Prevent normal protected routes while the session requires a password change.

- [ ] **Step 4: Run tests to verify they pass**
  - Run: `python -m unittest tests.integracion.test_int_servidor -v`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - Commit: `feat: add secure local login and forced password change`

### Task 3: API administrativa de usuarios, roles y permisos

**Files:**
- Modify: `api/auth.py`
- Modify: `api/servidor.py`
- Modify: `api/permisos.py`
- Test: `tests/integracion/test_int_servidor.py`
- Test: `tests/datos/test_autenticacion_local.py`

**Interfaces:**
- Add `listar_roles(db) -> list[dict]`, `crear_rol(db, actor, nombre, permisos) -> dict`, `actualizar_rol(db, actor, rol_id, nombre, permisos, activo) -> dict`.
- Add `listar_usuarios(db) -> list[dict]`, `crear_usuario_local(db, actor, usuario, nombre, clave_inicial, roles) -> dict`, `actualizar_usuario(db, actor, identidad_id, activo, roles) -> dict`.
- Add routes:
  - `GET /api/admin/permisos`
  - `GET /api/admin/roles`
  - `POST /api/admin/roles`
  - `PATCH /api/admin/roles/{id}`
  - `GET /api/admin/usuarios`
  - `POST /api/admin/usuarios`
  - `PATCH /api/admin/usuarios/{id}`

- [ ] **Step 1: Write the failing tests**
  - Non-admin receives 403 for all admin routes.
  - Admin can create a role with existing permissions and assign it to a user.
  - Unknown permission, duplicate role name, duplicate username, and blank names return 400 with no partial write.
  - Admin cannot deactivate the last active administrator or remove the last administrative capability.
  - Every successful mutation creates an audit row with the admin actor.

- [ ] **Step 2: Run tests to verify they fail**
  - Run: `python -m unittest tests.integracion.test_int_servidor tests.datos.test_autenticacion_local -v`
  - Expected: FAIL because routes and management functions do not exist.

- [ ] **Step 3: Implement server-side administration**
  - Enforce `usuarios.administrar` via `auth.exigir`.
  - Validate and write role/user changes in one transaction.
  - Recompute effective actions from database memberships; do not trust actions supplied by the browser.
  - Keep the protected bootstrap administrator from being deleted or silently stripped of administrative access.

- [ ] **Step 4: Run tests to verify they pass**
  - Run: `python -m unittest tests.integracion.test_int_servidor tests.datos.test_autenticacion_local -v`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - Commit: `feat: add role and user administration API`

### Task 4: Interfaz de acceso y administración

**Files:**
- Modify: `app/app.js`
- Modify: `app/nucleo.js`
- Modify: `app/navegacion.js`
- Modify: `app/estilos.css`
- Test: `tests/app/test_app_navegacion.py`
- Test: `tests/app/test_app_vistas.py`

**Interfaces:**
- Add login form state for local credentials and forced password change.
- Add an admin route/menu item gated by `usuarios.administrar`.
- Add API calls for listing permissions, roles, and users and submitting validated mutations.

- [ ] **Step 1: Write the failing tests**
  - The admin profile sees exactly one administration destination for users/roles.
  - Other profiles do not see or reach that destination.
  - The login view presents local login only when enabled by API state.
  - A forced-change response renders the password-change form and does not route to the normal home.

- [ ] **Step 2: Run tests to verify they fail**
  - Run: `python -m unittest tests.app.test_app_navegacion tests.app.test_app_vistas -v`
  - Expected: FAIL because the route/view and local login UI do not exist.

- [ ] **Step 3: Implement the UI**
  - Preserve the current demo profile selector and external-access copy.
  - Add accessible labels, focus handling, disabled submit state, generic login errors, and password-change confirmation.
  - Keep role/permission management as a focused administrative screen with explicit save feedback.
  - Do not render password values or server-side secrets.

- [ ] **Step 4: Run tests to verify they pass**
  - Run: `python -m unittest tests.app.test_app_navegacion tests.app.test_app_vistas -v`
  - Expected: PASS.

- [ ] **Step 5: Commit**
  - Commit: `feat: improve login and add role administration view`

### Task 5: Verificación completa y documentación de despliegue

**Files:**
- Modify: `docs/despliegue.md`
- Modify: `README.md`
- Test: existing full suite

- [ ] **Step 1: Add documentation checks**
  - Document bootstrap `admin/admin123`, mandatory first change, how to disable demo login, and how to configure `JACOMIND_COOKIE_SEGURA=1`.
  - State clearly that the temporary password must be changed before production use.

- [ ] **Step 2: Run focused tests**
  - Run: `python -m unittest tests.datos.test_autenticacion_local tests.integracion.test_int_servidor tests.app.test_app_navegacion tests.app.test_app_vistas -v`
  - Expected: PASS.

- [ ] **Step 3: Run the full suite**
  - Run: `python -m unittest discover -v`
  - Expected: PASS with no new failures.

- [ ] **Step 4: Commit**
  - Commit: `docs: document local login and role administration`
