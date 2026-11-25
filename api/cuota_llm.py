"""Orquestador de cuotas de Gemini (plan gratuito): reparte las llamadas entre claves y modelos sin pasar los límites.

Cada clave de Gemini tiene, por modelo, tres límites: solicitudes por minuto (RPM), tokens por minuto (TPM) y
solicitudes por día (RPD). El día se reinicia a medianoche de la hora del Pacífico, como en Google.

* **Antes** de cada llamada se reserva un hueco: si la clave y el modelo ya están cerca de un límite (con margen),
  se pasa al siguiente candidato sin llamar a Google.
* **Después** se anotan los tokens reales. Si Google responde 429 de todos modos (por ejemplo, otra aplicación usa
  la misma clave), la combinación se bloquea hasta el minuto siguiente o hasta el cambio de día, según el mensaje.
* Las **tareas** fijan el orden de preferencia:
  - ``chat`` (asistente): primero los Flash Lite de 500 solicitudes al día, en las dos claves; después Gemma 4
    (14 400 al día, pero 16 000 tokens por minuto) y los Flash de 20 al día. Los mejores modelos quedan como último
    recurso y solo con una parte de su cupo, porque se reservan para la redacción.
  - ``redaccion`` (textos de la aplicación, en lotes y guardados): primero los mejores modelos (Flash 3.8, 3.6 y 3);
    si se agotan, los Flash Lite, pero solo hasta el 30 % de su cupo diario para no dejar sin servicio al asistente.

El registro de uso vive en un SQLite propio (``var/llm_cuota.sqlite3``), compartido por el servidor y los comandos,
y nunca guarda las claves: solo una huella corta (SHA-256).
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import DIR_VAR


@dataclass(frozen=True)
class Limite:
    rpm: int
    tpm: int
    rpd: int
    nombre: str


# Límites del plan gratuito de la cuenta (consola de Google AI Studio, noviembre de 2026).
CATALOGO: dict[str, Limite] = {
    "gemini-3.5-flash-lite": Limite(15, 250_000, 500, "Gemini 3.5 Flash Lite"),
    "gemini-3.1-flash-lite": Limite(15, 250_000, 500, "Gemini 3.1 Flash Lite"),
    "gemma-4-31b-it": Limite(30, 16_000, 14_400, "Gemma 4 31B"),
    "gemma-4-26b-a4b-it": Limite(30, 16_000, 14_400, "Gemma 4 26B"),
    "gemini-2.5-flash-lite": Limite(10, 250_000, 20, "Gemini 2.5 Flash Lite"),
    "gemini-2.5-flash": Limite(5, 250_000, 20, "Gemini 2.5 Flash"),
    "gemini-3.8-flash": Limite(5, 250_000, 20, "Gemini 3.8 Flash"),
    "gemini-3.6-flash": Limite(5, 250_000, 20, "Gemini 3.6 Flash"),
    "gemini-3-flash-preview": Limite(5, 250_000, 20, "Gemini 3 Flash"),
}

# (modelo, fracción máxima del cupo diario que la tarea puede usar)
TAREAS: dict[str, list[tuple[str, float]]] = {
    "chat": [("gemini-3.5-flash-lite", 1.0), ("gemini-3.1-flash-lite", 1.0),
             ("gemma-4-31b-it", 1.0), ("gemma-4-26b-a4b-it", 1.0),
             ("gemini-2.5-flash-lite", 1.0), ("gemini-2.5-flash", 1.0),
             ("gemini-3-flash-preview", 0.25), ("gemini-3.6-flash", 0.25), ("gemini-3.8-flash", 0.25)],
    "redaccion": [("gemini-3.8-flash", 1.0), ("gemini-3.6-flash", 1.0), ("gemini-3-flash-preview", 1.0),
                  ("gemini-3.5-flash-lite", 0.3), ("gemini-3.1-flash-lite", 0.3)],
}

MARGEN = float(os.environ.get("JACOMIND_LLM_MARGEN", "0.9"))   # usa como máximo el 90 % de cada límite
VARIABLES_CLAVE = ("GEMINI_API_KEY", "GEMINI_API_KEY2", "GEMINI_API_KEY_2", "GEMINI_API_KEY3", "GEMINI_API_KEY_3", "GOOGLE_API_KEY")

_cerrojo = threading.Lock()
_preparado: set[str] = set()


# ---------------------------------------------------------------- claves y tiempo
def claves() -> list[tuple[str, str]]:
    """[(huella, clave)] sin repetir, en el orden de las variables de entorno."""
    vistas, salida = set(), []
    for v in VARIABLES_CLAVE:
        c = (os.environ.get(v) or "").strip().strip('"')
        if c and c not in vistas:
            vistas.add(c)
            salida.append(("k" + hashlib.sha256(c.encode()).hexdigest()[:8], c))
    return salida


def _pacifico(ts: float) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("America/Los_Angeles"))
    except Exception:  # sin base de zonas horarias: UTC-8 (reinicia una hora tarde en verano; es conservador)
        return datetime.fromtimestamp(ts, timezone(timedelta(hours=-8)))


def dia(ts: float | None = None) -> str:
    return _pacifico(time.time() if ts is None else ts).date().isoformat()


def proximo_dia(ts: float | None = None) -> float:
    """Instante (epoch) de la siguiente medianoche del Pacífico."""
    ahora = _pacifico(time.time() if ts is None else ts)
    manana = (ahora + timedelta(days=1)).replace(hour=0, minute=0, second=5, microsecond=0)
    return manana.timestamp()


# ---------------------------------------------------------------- almacenamiento
def ruta() -> Path:
    return Path(os.environ.get("JACOMIND_LLM_CUOTA_DB") or DIR_VAR / "llm_cuota.sqlite3")


def _con() -> sqlite3.Connection:
    p = ruta()
    con = sqlite3.connect(p, timeout=15, isolation_level=None)
    if str(p) not in _preparado:
        p.parent.mkdir(parents=True, exist_ok=True)
        con.executescript("""
          PRAGMA journal_mode=WAL;
          CREATE TABLE IF NOT EXISTS solicitudes (id INTEGER PRIMARY KEY, ts REAL NOT NULL, dia TEXT NOT NULL, clave TEXT NOT NULL,
            modelo TEXT NOT NULL, tarea TEXT NOT NULL, tokens INTEGER NOT NULL, estado TEXT NOT NULL, detalle TEXT);
          CREATE INDEX IF NOT EXISTS solicitudes_cm ON solicitudes (clave, modelo, ts);
          CREATE TABLE IF NOT EXISTS bloqueos (clave TEXT NOT NULL, modelo TEXT NOT NULL, hasta REAL NOT NULL, motivo TEXT,
            PRIMARY KEY (clave, modelo));""")
        _preparado.add(str(p))
    return con


def _efectivo(valor: int, fraccion: float = 1.0) -> int:
    return max(1, int(valor * MARGEN * fraccion))


def _uso(con, clave: str, modelo: str, ahora: float) -> tuple[int, int, int, int]:
    """(solicitudes último minuto, tokens último minuto, solicitudes hoy, solicitudes hoy de redacción)."""
    cuenta = "estado IN ('reservada', 'ok', 'error')"   # un 429 no consume cupo en Google
    rpm, tpm = con.execute(f"SELECT count(*), coalesce(sum(tokens), 0) FROM solicitudes WHERE clave=? AND modelo=? AND ts>? AND {cuenta}",
                           (clave, modelo, ahora - 60)).fetchone()
    hoy, hoy_red = con.execute(f"SELECT count(*), coalesce(sum(tarea='redaccion'), 0) FROM solicitudes WHERE clave=? AND modelo=? AND dia=? AND {cuenta}",
                               (clave, modelo, dia(ahora))).fetchone()
    return rpm, tpm, hoy, hoy_red


# ---------------------------------------------------------------- reserva y resultado
def candidatos(tarea: str) -> list[tuple[str, str, str, float]]:
    """[(huella, clave, modelo, fracción)] en orden: por modelo según la tarea y, dentro, la clave menos usada hoy."""
    lista = claves()
    if not lista:
        return []
    orden = TAREAS.get(tarea) or TAREAS["chat"]
    with _cerrojo:
        con = _con()
        try:
            hoy = dia()
            usados = {(c, m): n for c, m, n in con.execute(
                "SELECT clave, modelo, count(*) FROM solicitudes WHERE dia=? AND estado IN ('reservada','ok','error') GROUP BY clave, modelo", (hoy,))}
        finally:
            con.close()
    salida = []
    for modelo, fraccion in orden:
        for huella, clave in sorted(lista, key=lambda x: usados.get((x[0], modelo), 0)):
            salida.append((huella, clave, modelo, fraccion))
    return salida


def reservar(huella: str, modelo: str, tarea: str, tokens: int, fraccion: float = 1.0) -> int | None:
    """Reserva un hueco si cabe dentro de los límites (con margen). Devuelve el id de la reserva o None."""
    lim = CATALOGO.get(modelo)
    if lim is None:
        return None
    ahora = time.time()
    with _cerrojo:
        con = _con()
        try:
            con.execute("BEGIN IMMEDIATE")
            b = con.execute("SELECT hasta FROM bloqueos WHERE clave=? AND modelo=?", (huella, modelo)).fetchone()
            if b and b[0] > ahora:
                con.execute("ROLLBACK"); return None
            rpm, tpm, hoy, hoy_red = _uso(con, huella, modelo, ahora)
            # La fracción limita lo que esa tarea puede gastar del día; la otra tarea conserva el resto.
            hoy_tarea = hoy_red if tarea == "redaccion" else hoy - hoy_red
            if (rpm + 1 > _efectivo(lim.rpm) or tpm + tokens > _efectivo(lim.tpm) or hoy + 1 > _efectivo(lim.rpd)
                    or hoy_tarea + 1 > _efectivo(lim.rpd, fraccion)):
                con.execute("ROLLBACK"); return None
            cur = con.execute("INSERT INTO solicitudes (ts, dia, clave, modelo, tarea, tokens, estado) VALUES (?,?,?,?,?,?, 'reservada')",
                              (ahora, dia(ahora), huella, modelo, tarea, int(tokens)))
            con.execute("COMMIT")
            return cur.lastrowid
        finally:
            con.close()


def confirmar(reserva: int, tokens: int) -> None:
    with _cerrojo:
        con = _con()
        try:
            con.execute("UPDATE solicitudes SET estado='ok', tokens=? WHERE id=?", (int(tokens), reserva))
        finally:
            con.close()


def _segundos_reintento(texto: str) -> float | None:
    m = re.search(r"retry(?:Delay)?[^0-9]{0,20}(\d+(?:\.\d+)?)\s*s", texto, re.I)
    return float(m.group(1)) if m else None


def clasificar_error(e: BaseException) -> tuple[str, float]:
    """(tipo, segundos de bloqueo) a partir del error del proveedor."""
    texto = f"{type(e).__name__} {e}"
    if re.search(r"429|RESOURCE_EXHAUSTED|RateLimit|ResourceExhausted|quota", texto, re.I):
        if re.search(r"per ?day|PerDay|daily", texto, re.I):
            return "cuota_dia", max(60.0, proximo_dia() - time.time())
        return "cuota_minuto", min(120.0, (_segundos_reintento(texto) or 55.0) + 5)
    if re.search(r"404|NOT_FOUND|NotFound|PERMISSION_DENIED|403", texto):
        return "no_disponible", 6 * 3600.0
    if re.search(r"503|UNAVAILABLE|overloaded|high demand|500|INTERNAL", texto, re.I):
        return "saturado", 45.0
    if re.search(r"timeout|timed out|Deadline", texto, re.I):
        return "tiempo", 30.0
    return "error", 20.0


def fallo(reserva: int, huella: str, modelo: str, e: BaseException) -> str:
    """Anota el fallo y bloquea la combinación el tiempo que corresponda. Devuelve el tipo."""
    tipo, segundos = clasificar_error(e)
    with _cerrojo:
        con = _con()
        try:
            con.execute("UPDATE solicitudes SET estado=?, detalle=? WHERE id=?",
                        ("rechazada" if tipo.startswith("cuota") else "error", f"{tipo}: {type(e).__name__}"[:200], reserva))
            con.execute("INSERT INTO bloqueos (clave, modelo, hasta, motivo) VALUES (?,?,?,?) "
                        "ON CONFLICT(clave, modelo) DO UPDATE SET hasta=excluded.hasta, motivo=excluded.motivo",
                        (huella, modelo, time.time() + segundos, tipo))
        finally:
            con.close()
    return tipo


def limpiar(dias: int = 7) -> None:
    with _cerrojo:
        con = _con()
        try:
            con.execute("DELETE FROM solicitudes WHERE ts < ?", (time.time() - dias * 86400,))
            con.execute("DELETE FROM bloqueos WHERE hasta < ?", (time.time(),))
        finally:
            con.close()


# ---------------------------------------------------------------- estado (para la pantalla de operación)
def estado() -> dict:
    """Uso de hoy por clave y modelo frente a sus límites. Nunca incluye las claves."""
    ahora = time.time()
    lista = claves()
    filas = []
    with _cerrojo:
        con = _con()
        try:
            bloqueos = {(c, m): (h, mot) for c, m, h, mot in con.execute("SELECT clave, modelo, hasta, motivo FROM bloqueos WHERE hasta > ?", (ahora,))}
            for n, (huella, _) in enumerate(lista, 1):
                for modelo, lim in CATALOGO.items():
                    rpm, tpm, hoy, hoy_red = _uso(con, huella, modelo, ahora)
                    b = bloqueos.get((huella, modelo))
                    filas.append({"clave": f"Clave {n}", "huella": huella, "modelo": modelo, "nombre": lim.nombre,
                                  "hoy": hoy, "hoy_redaccion": hoy_red, "rpd": lim.rpd, "rpd_efectivo": _efectivo(lim.rpd),
                                  "ultimo_minuto": rpm, "rpm": lim.rpm, "tokens_minuto": tpm, "tpm": lim.tpm,
                                  "bloqueado_hasta": datetime.fromtimestamp(b[0], timezone.utc).isoformat(timespec="seconds") if b else None,
                                  "motivo_bloqueo": b[1] if b else None})
        finally:
            con.close()
    return {"dia_pacifico": dia(ahora), "reinicio": datetime.fromtimestamp(proximo_dia(ahora), timezone.utc).isoformat(timespec="seconds"),
            "claves": len(lista), "margen": MARGEN, "tareas": {t: [m for m, _ in v] for t, v in TAREAS.items()}, "uso": filas}
