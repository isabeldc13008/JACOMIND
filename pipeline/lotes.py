"""Huella, inventario y decisiones de revisión de lotes."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .esquemas import TableSpec


@dataclass(frozen=True)
class BatchDecision:
    status: str
    revision: int
    reason: str


@dataclass(frozen=True)
class BatchRecord:
    sha256: str
    revision: int
    status: str
    rows: dict[str, object]


def calcular_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clave_negocio(row: Mapping[str, object], spec: TableSpec) -> str:
    values = [str(row.get(name, "")) for name in (spec.business_key or spec.primary_key)]
    return "|".join(values)


def clasificar_reenvio(previous: Mapping[str, object] | None, current_hash: str, business_rows: Iterable[tuple[str, Mapping[str, object]]]) -> BatchDecision:
    if previous is None:
        return BatchDecision("nuevo", 1, "No existe un lote publicado previamente")
    previous_revision = int(previous.get("revision", 0))
    if previous.get("sha256") == current_hash:
        return BatchDecision("reutilizar", previous_revision, "La huella del archivo es idéntica")
    previous_rows = previous.get("rows", {})
    changed = any(previous_rows.get(key) != dict(row) for key, row in business_rows)
    if changed:
        return BatchDecision("nueva_revision", previous_revision + 1, "Cambió una clave de negocio existente")
    return BatchDecision("nuevo_lote", previous_revision + 1, "El lote contiene nuevas claves de negocio")


def serializar_valor(value: object) -> object:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "to_eng_string"):
        return value.to_eng_string()
    return value


def escribir_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=serializar_valor), encoding="utf-8")
