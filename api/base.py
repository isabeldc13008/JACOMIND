"""Conexión SQLite, migraciones, reloj y utilidades comunes."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

DIR_API = Path(__file__).resolve().parent
RAIZ = DIR_API.parent
DIR_MIGRACIONES = DIR_API / "migraciones"


class ErrorApi(Exception):
    """Error con código HTTP y mensaje legible."""

    def __init__(self, status: int, codigo: str, mensaje: str, detalle=None):
        super().__init__(mensaje)
        self.status, self.codigo, self.mensaje, self.detalle = status, codigo, mensaje, detalle

    def como_dict(self) -> dict:
        d = {"error": self.codigo, "mensaje": self.mensaje}
        if self.detalle is not None:
            d["detalle"] = self.detalle
        return d


# Reloj controlable para pruebas y ensayos de cierre ------------------------
_hoy_forzado: date | None = None


def fijar_hoy(d: date | str | None) -> None:
    global _hoy_forzado
    _hoy_forzado = date.fromisoformat(d) if isinstance(d, str) else d


def hoy() -> date:
    if _hoy_forzado:
        return _hoy_forzado
    env = os.environ.get("JACOMIND_HOY")
    return date.fromisoformat(env) if env else date.today()


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def nuevo_id(prefijo: str = "") -> str:
    return f"{prefijo}{uuid.uuid4().hex[:16]}"


def dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def loads(s):
    return None if s is None else json.loads(s)


class BaseDatos:
    """Envuelve la ruta de la base; cada operación abre su conexión (seguro entre hilos)."""

    def __init__(self, ruta: str | Path):
        self.ruta = str(ruta)
        self._lock = threading.Lock()
        if self.ruta != ":memory:":
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)

    def conectar(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.ruta, timeout=30, isolation_level=None, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("PRAGMA busy_timeout = 30000")
        if self.ruta != ":memory:":
            con.execute("PRAGMA journal_mode = WAL")
        return con

    @contextmanager
    def conexion(self):
        con = self.conectar()
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def transaccion(self, inmediata: bool = True):
        """Transacción explícita. IMMEDIATE serializa escritores (publicaciones concurrentes)."""
        con = self.conectar()
        try:
            con.execute("BEGIN IMMEDIATE" if inmediata else "BEGIN")
            yield con
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def migrar(self) -> list[str]:
        aplicadas = []
        with self.conexion() as con:
            con.execute("CREATE TABLE IF NOT EXISTS esquema_migraciones (version TEXT PRIMARY KEY, aplicada_en TEXT NOT NULL)")
            hechas = {r[0] for r in con.execute("SELECT version FROM esquema_migraciones")}
            for f in sorted(DIR_MIGRACIONES.glob("*.sql")):
                if f.stem in hechas:
                    continue
                con.executescript("BEGIN;\n" + f.read_text(encoding="utf-8") +
                                  f"\nINSERT INTO esquema_migraciones VALUES ('{f.stem}', '{ahora()}');\nCOMMIT;")
                aplicadas.append(f.stem)
        return aplicadas

    def version_esquema(self) -> str | None:
        with self.conexion() as con:
            try:
                r = con.execute("SELECT max(version) FROM esquema_migraciones").fetchone()
            except sqlite3.OperationalError:
                return None
            return r[0]


def auditar(con: sqlite3.Connection, actor: str | None, accion: str, recurso: str | None,
            resultado: str, revision: str | None = None, detalle=None) -> None:
    con.execute("INSERT INTO auditoria (ts, actor, accion, recurso, revision, resultado, detalle) VALUES (?,?,?,?,?,?,?)",
                (ahora(), actor, accion, recurso, revision, resultado, None if detalle is None else dumps(detalle)))


def bandera(con: sqlite3.Connection, nombre: str, defecto: bool = True) -> bool:
    r = con.execute("SELECT activo FROM banderas WHERE nombre = ?", (nombre,)).fetchone()
    return defecto if r is None else bool(r[0])
