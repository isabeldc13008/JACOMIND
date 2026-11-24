"""Publicación consistente, recuperable e idempotente de los archivos de una ejecución (M2 en adelante).

Corrige, para los experimentos nuevos, los tres problemas que la auditoría encontró en M1.1–M1.3:

A. El artefacto principal podía no coincidir con el candidato congelado → ``congelacion.json`` guarda la huella del
   artefacto y la de la selección; la verificación exige que coincidan (``verificar_lote`` + comprobaciones del modelo).
B. Una evidencia de desarrollo podía cambiar sin invalidar la congelación → el marcador guarda el SHA-256 de cada
   archivo de evidencia y su sello cubre el marcador entero; cualquier cambio se rechaza con un mensaje que lo nombra.
C. Un fallo entre la escritura de métricas y decisión impedía recuperar → todos los archivos de un lote se escriben de
   forma atómica (temporal + ``os.replace``) y el marcador se escribe el ÚLTIMO. Un reintento completa los que falten.

Reglas de ``publicar_lote``:

* Con marcador: si los contenidos nuevos tienen las mismas huellas, no se reescribe nada (idempotente; un archivo
  perdido se restituye porque su contenido es determinista). Si difieren, se rechaza: no se sobrescriben resultados.
* Sin marcador (publicación interrumpida): los archivos ya escritos con contenido idéntico se conservan; uno distinto
  se rechaza (la ejecución cambió: código, datos o configuración) en vez de sobrescribirse en silencio.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Gancho de prueba: nombre del archivo tras cuya escritura se simula una interrupción.
FALLO_SIMULADO: str | None = None


class EjecucionError(ValueError):
    """La ejecución contiene resultados distintos o evidencia alterada; no se sobrescribe."""


def ahora_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_defecto)


def _defecto(o):
    return o.isoformat() if hasattr(o, "isoformat") else str(o)


def json_bytes(datos: Any) -> bytes:
    """Serialización estable (claves en orden de inserción, sangría fija) para archivos publicados."""
    return (json.dumps(datos, ensure_ascii=False, indent=1, default=_defecto) + "\n").encode("utf-8")


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha_archivo(ruta: Path) -> str:
    return sha(Path(ruta).read_bytes())


def escribir_atomico(ruta: Path, contenido: bytes) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=ruta.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


EXCLUIDAS_SELLO = ("sello", "escrito_en", "volatiles")


def sello(marcador: dict) -> str:
    """SHA-256 del marcador salvo su sello y los datos volátiles (fecha de escritura y fechas derivadas de ella)."""
    return sha(canon({k: v for k, v in marcador.items() if k not in EXCLUIDAS_SELLO}).encode())


def publicar_lote(directorio: str | Path, archivos: dict[str, bytes], marcador: str, metadatos: dict | None = None,
                  volatiles: dict | None = None) -> dict:
    """Escribe ``archivos`` y, al final, el marcador ``{archivos: {nombre: sha256}, **metadatos, sello}``.

    ``volatiles`` (p. ej. la fecha real de congelación) se guarda fuera del sello y conserva el valor de la primera
    escritura: repetir la misma ejecución otro día es idempotente. Lanza ``EjecucionError`` si ya hay resultados distintos.
    """
    directorio = Path(directorio)
    huellas = {n: sha(b) for n, b in sorted(archivos.items())}
    nuevo = dict(metadatos or {}, archivos=huellas)
    nuevo["sello"] = sello(nuevo)
    ruta_m = directorio / marcador
    if ruta_m.exists():
        previo = json.loads(ruta_m.read_text(encoding="utf-8"))
        if previo.get("sello") != nuevo["sello"]:
            distintos = sorted(n for n in set(huellas) | set(previo.get("archivos", {}))
                               if huellas.get(n) != previo.get("archivos", {}).get(n))
            otros = sorted(k for k in set(nuevo) | set(previo) if k not in ("archivos",) + EXCLUIDAS_SELLO
                           and canon(nuevo.get(k)) != canon(previo.get(k)))
            raise EjecucionError(f"{directorio} ya tiene resultados publicados distintos ({marcador}); no se sobrescriben. "
                                 f"Archivos que cambiarían: {distintos or '—'}; metadatos: {otros or '—'}. Usa otra carpeta de ejecución.")
        for n, b in archivos.items():  # idempotente; restituye un archivo perdido o alterado con el contenido determinista
            ruta = directorio / n
            if not ruta.exists():
                escribir_atomico(ruta, b)
            elif sha_archivo(ruta) != huellas[n]:
                raise EjecucionError(f"{ruta} fue modificado después de publicarse (huella distinta de {marcador}); no se acepta.")
        return previo
    for n, b in archivos.items():
        ruta = directorio / n
        if ruta.exists() and sha_archivo(ruta) != huellas[n]:
            raise EjecucionError(f"{ruta} existe con un contenido distinto del que produce esta ejecución y no hay {marcador} "
                                 "que lo respalde: no se sobrescribe. Usa otra carpeta de ejecución o revisa qué cambió.")
    for n, b in archivos.items():
        ruta = directorio / n
        if not ruta.exists():
            escribir_atomico(ruta, b)
        if FALLO_SIMULADO == n:
            raise RuntimeError(f"Interrupción simulada después de escribir {n}")
    escribir_atomico(ruta_m, json_bytes(dict(nuevo, volatiles=volatiles or {}, escrito_en=ahora_utc())))
    return json.loads(ruta_m.read_text(encoding="utf-8"))


def verificar_lote(directorio: str | Path, marcador: str, error=EjecucionError) -> dict:
    """Comprueba sello y huella de cada archivo del marcador. Devuelve el marcador."""
    directorio = Path(directorio)
    ruta_m = directorio / marcador
    if not ruta_m.exists():
        raise error(f"{directorio} no tiene {marcador}: la publicación no terminó o no existe.")
    m = json.loads(ruta_m.read_text(encoding="utf-8"))
    if sello(m) != m.get("sello"):
        raise error(f"{ruta_m} fue alterado (el sello no coincide con su contenido).")
    for n, h in m.get("archivos", {}).items():
        ruta = directorio / n
        if not ruta.exists():
            raise error(f"Falta {ruta}, registrado en {marcador}.")
        if sha_archivo(ruta) != h:
            raise error(f"{ruta} cambió después de congelarse (SHA-256 distinto del registrado en {marcador}). "
                        "La evidencia congelada no se recalcula: crea una ejecución nueva.")
    return m
