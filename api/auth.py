"""Sesiones e identidad resuelta en el servidor.

La demo local usa identidades ficticias (inicio de sesión por selección). En el
piloto, el proveedor aprobado se conecta como proxy de autenticación que fija la
cabecera ``X-Usuario-Autenticado``; solo se acepta si JACOMIND_PROXY_AUTH=1.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .base import BaseDatos, ErrorApi, ahora
from .permisos import IDENTIDADES, ORGANIZACIONES, filas_permisos

DURACION_SESION_MIN = int(os.environ.get("JACOMIND_SESION_MIN", "480"))


@dataclass
class Usuario:
    id: str
    nombre: str
    organizacion_id: str
    tipo_org: str
    cliente_id: str | None
    roles: set[str] = field(default_factory=set)
    acciones: set[str] = field(default_factory=set)

    @property
    def externo(self) -> bool:
        return self.tipo_org == "empresa"

    def puede(self, accion: str) -> bool:
        return accion in self.acciones

    def como_dict(self) -> dict:
        return {"id": self.id, "nombre": self.nombre, "organizacion_id": self.organizacion_id,
                "externo": self.externo, "roles": sorted(self.roles), "acciones": sorted(self.acciones)}


def sembrar_identidades(con) -> None:
    for org in ORGANIZACIONES:
        con.execute("INSERT OR IGNORE INTO organizaciones (id, nombre, tipo, cliente_id, segmento) VALUES (?,?,?,?,?)", org)
    for ident, nombre, org, rol in IDENTIDADES:
        con.execute("INSERT OR IGNORE INTO identidades (id, nombre, organizacion_id) VALUES (?,?,?)", (ident, nombre, org))
        con.execute("INSERT OR IGNORE INTO pertenencias VALUES (?,?,?)", (ident, org, rol))
    con.execute("DELETE FROM permisos")
    con.executemany("INSERT INTO permisos (rol, accion) VALUES (?,?)", filas_permisos())


def cargar_usuario(con, identidad_id: str) -> Usuario | None:
    r = con.execute("""SELECT i.id, i.nombre, i.organizacion_id, o.tipo, o.cliente_id FROM identidades i
                       JOIN organizaciones o ON o.id = i.organizacion_id WHERE i.id = ? AND i.activo = 1""",
                    (identidad_id,)).fetchone()
    if not r:
        return None
    roles = {x[0] for x in con.execute("SELECT rol FROM pertenencias WHERE identidad_id = ? AND organizacion_id = ?",
                                       (r["id"], r["organizacion_id"]))}
    acciones = {x[0] for x in con.execute(
        f"SELECT DISTINCT accion FROM permisos WHERE rol IN ({','.join('?' * len(roles)) or 'NULL'})", tuple(roles))}
    return Usuario(r["id"], r["nombre"], r["organizacion_id"], r["tipo"], r["cliente_id"], roles, acciones)


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
        return cargar_usuario(con, r["identidad_id"])


def exigir(usuario: Usuario | None, accion: str | None = None) -> Usuario:
    if usuario is None:
        raise ErrorApi(401, "sin_sesion", "Inicia sesión para continuar")
    if accion and not usuario.puede(accion):
        raise ErrorApi(403, "sin_permiso", f"Tu rol no permite: {accion}")
    return usuario
