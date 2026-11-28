"""Sesiones e identidad resuelta en el servidor.

La demo local usa identidades ficticias (inicio de sesión por selección). En el
piloto, el proveedor aprobado se conecta como proxy de autenticación que fija la
cabecera ``X-Usuario-Autenticado``; solo se acepta si JACOMIND_PROXY_AUTH=1.
"""
from __future__ import annotations

import os
import secrets
import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .base import BaseDatos, ErrorApi, ahora
from .permisos import IDENTIDADES, ORGANIZACIONES, ROLES, MATRIZ, filas_permisos

DURACION_SESION_MIN = int(os.environ.get("JACOMIND_SESION_MIN", "480"))
PBKDF2_ITERACIONES = 310_000


@dataclass
class Usuario:
    id: str
    nombre: str
    organizacion_id: str
    tipo_org: str
    cliente_id: str | None
    roles: set[str] = field(default_factory=set)
    acciones: set[str] = field(default_factory=set)
    requiere_cambio_clave: bool = False

    @property
    def externo(self) -> bool:
        return self.tipo_org == "empresa"

    def puede(self, accion: str) -> bool:
        return accion in self.acciones

    def como_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "organizacion_id": self.organizacion_id,
                "externo": self.externo, "roles": sorted(self.roles), "acciones": sorted(self.acciones),
                "requiere_cambio_clave": self.requiere_cambio_clave}


def sembrar_identidades(con) -> None:
    for org in ORGANIZACIONES:
        con.execute("INSERT OR IGNORE INTO organizaciones (id, nombre, tipo, cliente_id, segmento) VALUES (?,?,?,?,?)", org)
    for ident, nombre, org, rol in IDENTIDADES:
        con.execute("INSERT OR IGNORE INTO identidades (id, nombre, organizacion_id) VALUES (?,?,?)", (ident, nombre, org))
        con.execute("INSERT OR IGNORE INTO pertenencias VALUES (?,?,?)", (ident, org, rol))
    con.execute("DELETE FROM permisos")
    con.executemany("INSERT INTO permisos (rol, accion) VALUES (?,?)", filas_permisos())
    for rol in ROLES:
        con.execute("INSERT OR IGNORE INTO roles (id, nombre, sistema) VALUES (?,?,1)", (rol, rol))
    for accion, roles in MATRIZ.items():
        for rol in roles:
            con.execute("INSERT OR IGNORE INTO roles_permisos (rol_id, accion) VALUES (?,?)", (rol, accion))


def cargar_usuario(con, identidad_id: str) -> Usuario | None:
    r = con.execute("""SELECT i.id, i.nombre, i.organizacion_id, o.tipo, o.cliente_id,
                              COALESCE(u.requiere_cambio_clave, 0) AS requiere_cambio_clave
                       FROM identidades i
                       JOIN organizaciones o ON o.id = i.organizacion_id
                       LEFT JOIN usuarios_locales u ON u.identidad_id = i.id
                       WHERE i.id = ? AND i.activo = 1""",
                    (identidad_id,)).fetchone()
    if not r:
        return None
    roles = {x[0] for x in con.execute("SELECT rol FROM pertenencias WHERE identidad_id = ? AND organizacion_id = ?",
                                       (r["id"], r["organizacion_id"]))}
    acciones = {x[0] for x in con.execute(
        f"SELECT DISTINCT accion FROM permisos WHERE rol IN ({','.join('?' * len(roles)) or 'NULL'})", tuple(roles))}
    if roles:
        acciones.update(x[0] for x in con.execute(
            f"SELECT DISTINCT accion FROM roles_permisos WHERE rol_id IN ({','.join('?' * len(roles)) or 'NULL'})", tuple(roles)))
    return Usuario(r["id"], r["nombre"], r["organizacion_id"], r["tipo"], r["cliente_id"], roles, acciones,
                   bool(r["requiere_cambio_clave"]))


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Genera salt y hash PBKDF2; nunca devuelve la contraseña original."""
    if not isinstance(password, str) or len(password) < 8:
        raise ErrorApi(422, "clave_invalida", "La contraseña debe tener al menos 8 caracteres")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERACIONES)
    return salt.hex(), digest.hex()


def verificar_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        _, digest = hash_password(password, bytes.fromhex(salt_hex))
        return hmac.compare_digest(digest, hash_hex)
    except (TypeError, ValueError, ErrorApi):
        return False


def cargar_usuario_local(con, usuario: str) -> Usuario | None:
    r = con.execute("""SELECT identidad_id FROM usuarios_locales
                       WHERE usuario = ? AND activo = 1""", (usuario,)).fetchone()
    return cargar_usuario(con, r["identidad_id"]) if r else None


def autenticar_local(db: BaseDatos, usuario: str, password: str) -> Usuario:
    usuario = str(usuario or "").strip().lower()
    with db.conexion() as con:
        r = con.execute("""SELECT identidad_id, password_salt, password_hash FROM usuarios_locales
                           WHERE usuario = ? AND activo = 1""", (usuario,)).fetchone()
        if not r or not verificar_password(password, r["password_salt"], r["password_hash"]):
            raise ErrorApi(401, "credenciales_invalidas", "Credenciales inválidas")
        u = cargar_usuario(con, r["identidad_id"])
        if not u:
            raise ErrorApi(401, "credenciales_invalidas", "Credenciales inválidas")
        return u


def _crear_usuario_con(con, usuario: str, nombre: str, rol: str, password: str,
                       organizacion_id: str = "GREEN", cliente_id: str | None = None) -> dict:
    usuario = str(usuario or "").strip().lower()
    if not usuario or not usuario.replace("_", "").replace("-", "").isalnum():
        raise ErrorApi(422, "usuario_invalido", "El usuario solo puede contener letras, números, guion y guion bajo")
    if not con.execute("SELECT 1 FROM roles WHERE id = ? AND activo = 1", (rol,)).fetchone():
        raise ErrorApi(422, "rol_invalido", "Rol no reconocido")
    if con.execute("SELECT 1 FROM usuarios_locales WHERE usuario = ?", (usuario,)).fetchone():
        raise ErrorApi(409, "usuario_existente", "Ya existe un usuario con ese nombre")
    org = con.execute("SELECT id, tipo, cliente_id FROM organizaciones WHERE id = ?", (organizacion_id,)).fetchone()
    if not org:
        raise ErrorApi(422, "organizacion_invalida", "Organización no reconocida")
    salt, digest = hash_password(password)
    ahora_ = ahora()
    con.execute("INSERT OR IGNORE INTO identidades (id, nombre, organizacion_id, activo) VALUES (?,?,?,1)",
                (usuario, nombre.strip() or usuario, organizacion_id))
    con.execute("INSERT OR IGNORE INTO pertenencias VALUES (?,?,?)", (usuario, organizacion_id, rol))
    con.execute("""INSERT INTO usuarios_locales
                   (identidad_id, usuario, password_salt, password_hash, activo, creado_en, actualizado_en, requiere_cambio_clave)
                   VALUES (?,?,?,?,1,?,?,1)""", (usuario, usuario, salt, digest, ahora_, ahora_))
    return {"id": usuario, "usuario": usuario, "nombre": nombre.strip() or usuario, "rol": rol, "activo": True}


def crear_usuario_local(db: BaseDatos, usuario: str, nombre: str, rol: str, password: str,
                        organizacion_id: str = "GREEN", cliente_id: str | None = None) -> dict:
    db.migrar()
    with db.transaccion() as con:
        return _crear_usuario_con(con, usuario, nombre, rol, password, organizacion_id, cliente_id)


def listar_usuarios(db: BaseDatos) -> list[dict]:
    with db.conexion() as con:
        return [dict(r) for r in con.execute("""SELECT u.identidad_id AS id, u.usuario, i.nombre,
                    p.rol, u.activo, u.creado_en, u.actualizado_en
                    FROM usuarios_locales u JOIN identidades i ON i.id = u.identidad_id
                    LEFT JOIN pertenencias p ON p.identidad_id = u.identidad_id
                    ORDER BY u.usuario, p.rol""")]


def actualizar_usuario_local(db: BaseDatos, identidad_id: str, *, activo: bool | None = None,
                             rol: str | None = None, password: str | None = None) -> dict:
    db.migrar()
    with db.transaccion() as con:
        if not con.execute("SELECT 1 FROM usuarios_locales WHERE identidad_id = ?", (identidad_id,)).fetchone():
            raise ErrorApi(404, "usuario_no_encontrado", "Usuario no encontrado")
        cambios = []
        valores = []
        if activo is not None:
            cambios.append("activo = ?"); valores.append(int(activo))
        if password is not None:
            salt, digest = hash_password(password)
            cambios.extend(["password_salt = ?", "password_hash = ?"]); valores.extend([salt, digest])
        if password is not None:
            cambios.append("requiere_cambio_clave = 1")
        if cambios:
            cambios.append("actualizado_en = ?"); valores.append(ahora())
            con.execute(f"UPDATE usuarios_locales SET {', '.join(cambios)} WHERE identidad_id = ?", (*valores, identidad_id))
        if rol:
            if not con.execute("SELECT 1 FROM roles WHERE id = ? AND activo = 1", (rol,)).fetchone():
                raise ErrorApi(422, "rol_invalido", "Rol no reconocido")
            con.execute("DELETE FROM pertenencias WHERE identidad_id = ?", (identidad_id,))
            identidad = con.execute("SELECT organizacion_id FROM identidades WHERE id = ?", (identidad_id,)).fetchone()
            con.execute("INSERT INTO pertenencias VALUES (?,?,?)", (identidad_id, identidad[0], rol))
        u = cargar_usuario(con, identidad_id)
        return {"id": u.id, "nombre": u.nombre, "roles": sorted(u.roles), "activo": bool(con.execute("SELECT activo FROM usuarios_locales WHERE identidad_id = ?", (identidad_id,)).fetchone()[0])}


def sembrar_usuarios_configurados(db: BaseDatos) -> None:
    """Crea admin/admin123 una sola vez; las variables permiten cambiar el bootstrap."""
    admin = os.environ.get("JACOMIND_ADMIN_USUARIO", "admin")
    password = os.environ.get("JACOMIND_ADMIN_PASSWORD", "admin123")
    demo_password = os.environ.get("JACOMIND_DEMO_PASSWORD")
    if not (admin and password) and not demo_password:
        return
    with db.transaccion() as con:
        if admin and password:
            if not con.execute("SELECT 1 FROM usuarios_locales WHERE usuario = ?", (admin.lower(),)).fetchone():
                _crear_usuario_con(con, admin, os.environ.get("JACOMIND_ADMIN_NOMBRE", "Administrador JACOMIND"), "admin", password)
        if demo_password:
            for ident, nombre, org, rol in IDENTIDADES:
                if not con.execute("SELECT 1 FROM usuarios_locales WHERE usuario = ?", (ident,)).fetchone():
                    _crear_usuario_con(con, ident, nombre, rol, demo_password, org)


def crear_sesion(db: BaseDatos, identidad_id: str) -> tuple[str, Usuario]:
    with db.transaccion() as con:
        u = cargar_usuario(con, identidad_id)
        if not u:
            raise ErrorApi(401, "identidad_desconocida", "Identidad no reconocida")
        token = secrets.token_urlsafe(32)
        expira = (datetime.now(timezone.utc) + timedelta(minutes=DURACION_SESION_MIN)).isoformat()
        con.execute("INSERT INTO sesiones VALUES (?,?,?,?)", (token, identidad_id, ahora(), expira))
        return token, u


def cerrar_sesion(db: BaseDatos, token: str) -> None:
    with db.transaccion() as con:
        con.execute("DELETE FROM sesiones WHERE token = ?", (token,))


def resolver(db: BaseDatos, token: str | None, cabecera_proxy: str | None = None) -> Usuario | None:
    with db.conexion() as con:
        if cabecera_proxy and os.environ.get("JACOMIND_PROXY_AUTH") == "1":
            return cargar_usuario(con, cabecera_proxy)
        if not token:
            return None
        r = con.execute("SELECT identidad_id, expira_en FROM sesiones WHERE token = ?", (token,)).fetchone()
        if not r:
            return None
        if datetime.fromisoformat(r["expira_en"]) < datetime.now(timezone.utc):
            con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
            return None
        local = con.execute("SELECT activo FROM usuarios_locales WHERE identidad_id = ?", (r["identidad_id"],)).fetchone()
        if local is not None and not local["activo"]:
            con.execute("DELETE FROM sesiones WHERE token = ?", (token,))
            return None
        return cargar_usuario(con, r["identidad_id"])


def exigir(usuario: Usuario | None, accion: str | None = None) -> Usuario:
    if usuario is None:
        raise ErrorApi(401, "sin_sesion", "Inicia sesión para continuar")
    if accion and not usuario.puede(accion):
        raise ErrorApi(403, "sin_permiso", f"Tu rol no permite: {accion}")
    return usuario


def cambiar_clave(db: BaseDatos, identidad_id: str, actual: str, nueva: str) -> Usuario:
    with db.transaccion() as con:
        r = con.execute("SELECT password_salt, password_hash FROM usuarios_locales WHERE identidad_id = ? AND activo = 1", (identidad_id,)).fetchone()
        if not r or not verificar_password(actual, r["password_salt"], r["password_hash"]):
            raise ErrorApi(401, "credenciales_invalidas", "La contraseña actual no es válida")
        salt, digest = hash_password(nueva)
        con.execute("UPDATE usuarios_locales SET password_salt = ?, password_hash = ?, requiere_cambio_clave = 0, actualizado_en = ? WHERE identidad_id = ?",
                    (salt, digest, ahora(), identidad_id))
        return cargar_usuario(con, identidad_id)


def listar_roles(db: BaseDatos) -> list[dict]:
    with db.conexion() as con:
        return [dict(r) | {"permisos": [p[0] for p in con.execute("SELECT accion FROM roles_permisos WHERE rol_id = ? ORDER BY accion", (r["id"],))]}
                for r in con.execute("SELECT id, nombre, sistema, activo FROM roles ORDER BY nombre")]


def crear_rol(db: BaseDatos, rol_id: str, nombre: str, permisos: list[str]) -> dict:
    rol_id = str(rol_id or "").strip().lower()
    nombre = str(nombre or "").strip()
    permisos = sorted(set(permisos or []))
    validos = set(MATRIZ) | {p[1] for p in filas_permisos()}
    if not rol_id or not rol_id.replace("_", "").replace("-", "").isalnum() or not nombre:
        raise ErrorApi(400, "rol_invalido", "Indica un identificador y un nombre válidos")
    if rol_id in ROLES:
        raise ErrorApi(409, "rol_existente", "Ese rol del sistema ya existe")
    if any(p not in validos for p in permisos):
        raise ErrorApi(400, "permiso_invalido", "El rol contiene un permiso no reconocido")
    with db.transaccion() as con:
        if con.execute("SELECT 1 FROM roles WHERE id = ? OR nombre = ?", (rol_id, nombre)).fetchone():
            raise ErrorApi(409, "rol_existente", "Ya existe un rol con ese identificador o nombre")
        con.execute("INSERT INTO roles (id, nombre, sistema) VALUES (?,?,0)", (rol_id, nombre))
        con.executemany("INSERT INTO roles_permisos (rol_id, accion) VALUES (?,?)", [(rol_id, p) for p in permisos])
    return {"id": rol_id, "nombre": nombre, "sistema": 0, "activo": 1, "permisos": permisos}


def actualizar_rol(db: BaseDatos, rol_id: str, *, permisos: list[str] | None = None, activo: bool | None = None) -> dict:
    with db.transaccion() as con:
        r = con.execute("SELECT id, nombre, sistema, activo FROM roles WHERE id = ?", (rol_id,)).fetchone()
        if not r:
            raise ErrorApi(404, "rol_no_encontrado", "Rol no encontrado")
        if activo is False and r["sistema"]:
            raise ErrorApi(400, "rol_sistema", "Los roles del sistema no se pueden desactivar")
        if permisos is not None:
            validos = set(MATRIZ)
            if any(p not in validos for p in permisos):
                raise ErrorApi(400, "permiso_invalido", "El rol contiene un permiso no reconocido")
            con.execute("DELETE FROM roles_permisos WHERE rol_id = ?", (rol_id,))
            con.executemany("INSERT INTO roles_permisos (rol_id, accion) VALUES (?,?)", [(rol_id, p) for p in sorted(set(permisos))])
        if activo is not None:
            con.execute("UPDATE roles SET activo = ? WHERE id = ?", (int(activo), rol_id))
        return {"id": r["id"], "nombre": r["nombre"], "sistema": r["sistema"],
                "activo": int(activo) if activo is not None else r["activo"],
                "permisos": [p[0] for p in con.execute("SELECT accion FROM roles_permisos WHERE rol_id = ? ORDER BY accion", (rol_id,))]}
