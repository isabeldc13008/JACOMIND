"""Orquestación de un lote A01 y sus artefactos auditables."""

from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .esquemas import ARCHIVOS, TABLAS, TableSpec
from .formatos import FormatoError, leer_tabla
from .lotes import escribir_json
from .normalizacion import NormalizacionError, normalizar_fila
from .validacion import Issue, TableValidation, validar_tabla


TABLE_ORDER = ["clientes", "productos", "proveedores", "trm", "instalaciones", "ventas", "compras"]


@dataclass
class LoadResult:
    status: str
    inventory: dict[str, dict[str, Any]]
    issues: list[Issue]
    manifest: dict[str, Any]


def _plain(value: object) -> object:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return value.to_eng_string()
    return value


def _write_table(path: Path, spec: TableSpec, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(spec.columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _plain(row.get(key)) for key in spec.columns})


def _issue_as_dict(issue: Issue) -> dict[str, object]:
    return {"archivo": issue.file, "fila": issue.row, "campo": issue.field, "codigo": issue.code, "motivo": issue.reason, "accion": issue.action}


def _catalogs(validated: dict[str, TableValidation]) -> dict[str, set[str]]:
    catalogs: dict[str, set[str]] = {}
    for table, result in validated.items():
        key = TABLAS[table].primary_key[0]
        catalogs[table] = {str(row[key]) for row in result.accepted if row.get(key) is not None}
    return catalogs


def cargar_lote(datos: Path, salida: Path, configuracion: Path | None = None) -> LoadResult:
    datos = datos / "01_Datos" if (datos / "01_Datos").is_dir() else datos
    salida.mkdir(parents=True, exist_ok=True)
    current = salida / "lote_actual"
    if current.exists():
        shutil.rmtree(current)
    current.mkdir()
    inventory: dict[str, dict[str, Any]] = {}
    all_issues: list[Issue] = []
    validated: dict[str, TableValidation] = {}
    raw_rows: dict[str, list[dict[str, object]]] = {}
    normalization_failures: dict[str, int] = {}
    blocking = False

    for table in TABLE_ORDER:
        spec = TABLAS[table]
        filename = next(name for name, table_name in ARCHIVOS.items() if table_name == table)
        path = datos / filename
        if not path.exists():
            issue = Issue(filename, 0, "", "ARCHIVO_FALTANTE", "No existe la tabla obligatoria", "bloquear")
            all_issues.append(issue)
            inventory[table] = {"source": filename, "read": 0, "accepted": 0, "isolated": 0, "duplicates": 0, "blocking": True}
            blocking = True
            continue
        try:
            raw = leer_tabla(path, "csv")
        except FormatoError as exc:
            issue = Issue(filename, 0, "", "ERROR_LECTURA", str(exc), "bloquear")
            all_issues.append(issue)
            inventory[table] = {"source": filename, "read": 0, "accepted": 0, "isolated": 0, "duplicates": 0, "blocking": True}
            blocking = True
            continue
        normalized: list[dict[str, object]] = []
        failed_rows = 0
        for row_number, row in enumerate(raw, start=2):
            try:
                normalized.append(normalizar_fila(row, spec))
            except NormalizacionError as exc:
                failed_rows += 1
                all_issues.append(Issue(filename, row_number, "", "ERROR_NORMALIZACION", str(exc), "aislar"))
        normalization_failures[table] = failed_rows
        raw_rows[table] = normalized
        catalogs = _catalogs(validated)
        result = validar_tabla(normalized, spec, catalogs, archivo=filename)
        validated[table] = result
        all_issues.extend(result.issues)
        inventory[table] = {"source": filename, "read": len(raw), "accepted": len(result.accepted), "isolated": len(result.isolated) + failed_rows, "duplicates": result.duplicate_count, "blocking": False}
        _write_table(current / filename, spec, result.accepted)

    # Revalida tablas dependientes después de cargar todos los catálogos.
    catalogs = _catalogs(validated)
    for table in ("instalaciones", "ventas", "compras"):
        if table not in raw_rows:
            continue
        spec = TABLAS[table]
        result = validar_tabla(raw_rows[table], spec, catalogs, archivo=next(name for name, name_table in ARCHIVOS.items() if name_table == table))
        old = validated[table]
        if result.issues != old.issues:
            all_issues = [issue for issue in all_issues if issue.file != next(name for name, name_table in ARCHIVOS.items() if name_table == table)]
            all_issues.extend(result.issues)
            validated[table] = result
            filename = next(name for name, name_table in ARCHIVOS.items() if name_table == table)
            inventory[table].update({"accepted": len(result.accepted), "isolated": len(result.isolated) + normalization_failures.get(table, 0), "duplicates": result.duplicate_count})
            _write_table(current / filename, spec, result.accepted)

    optional_path = datos / "ventas_con_incidencias_OPCIONAL.csv"
    if optional_path.exists():
        optional_rows: list[dict[str, object]] = []
        optional_failures = 0
        try:
            optional_raw = leer_tabla(optional_path, "csv")
            for row_number, row in enumerate(optional_raw, start=2):
                try:
                    optional_rows.append(normalizar_fila(row, TABLAS["ventas"]))
                except NormalizacionError as exc:
                    optional_failures += 1
                    all_issues.append(Issue(optional_path.name, row_number, "", "ERROR_NORMALIZACION", str(exc), "aislar"))
            optional_result = validar_tabla(optional_rows, TABLAS["ventas"], _catalogs(validated), archivo=optional_path.name)
            all_issues.extend(optional_result.issues)
            inventory["ventas_opcional"] = {"source": optional_path.name, "read": len(optional_raw), "accepted": len(optional_result.accepted), "isolated": len(optional_result.isolated) + optional_failures, "duplicates": optional_result.duplicate_count, "blocking": False}
        except FormatoError as exc:
            all_issues.append(Issue(optional_path.name, 0, "", "ERROR_LECTURA", str(exc), "aislar"))
            inventory["ventas_opcional"] = {"source": optional_path.name, "read": 0, "accepted": 0, "isolated": 0, "duplicates": 0, "blocking": False}

    if any(inventory.get(table, {}).get("isolated") or inventory.get(table, {}).get("duplicates") for table in TABLE_ORDER):
        status = "pendiente_revision"
    elif blocking:
        status = "fallido"
    else:
        status = "publicable"
    if any(issue.action == "bloquear" for issue in all_issues):
        status = "fallido"

    (salida / "incidencias.jsonl").write_text("".join(json.dumps(_issue_as_dict(issue), ensure_ascii=False) + "\n" for issue in all_issues), encoding="utf-8")
    inventory_doc = {"status": status, "tablas": inventory, "incidencias": len(all_issues)}
    escribir_json(salida / "inventario.json", inventory_doc)
    manifest = {"status": status, "fecha_generacion": datetime.now().astimezone().isoformat(), "tablas": inventory, "ultima_publicacion_conservada": status != "publicable"}
    escribir_json(salida / "manifiesto.json", manifest)
    if status == "publicable":
        published = salida / "publicado"
        if published.exists():
            shutil.rmtree(published)
        current.rename(published)
    return LoadResult(status, inventory, all_issues, manifest)
