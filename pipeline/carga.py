"""Orquestación de un lote A01 y sus artefactos auditables."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .esquemas import ARCHIVOS, TABLAS, TableSpec
from .formatos import FormatoError, leer_tabla
from .lotes import calcular_sha256, escribir_json
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


def _config_tables(configuracion: Path | None) -> dict[str, dict[str, Any]]:
    if configuracion is None:
        return {}
    return json.loads(configuracion.read_text(encoding="utf-8")).get("tablas", {})


def _source_for(table: str, datos: Path, config: dict[str, dict[str, Any]]) -> tuple[Path, str, str | None, str, dict[str, str]]:
    filename = next(name for name, table_name in ARCHIVOS.items() if table_name == table)
    options = config.get(table, {})
    source = Path(options.get("archivo", filename))
    if not source.is_absolute():
        source = datos / source
    tipo = options.get("tipo", source.suffix.lstrip(".") or "csv")
    mapping = {str(physical): str(canonical) for canonical, physical in options.get("mapeo", {}).items()}
    return source, tipo, options.get("hoja"), options.get("delimitador", ","), mapping


def _map_columns(rows: list[dict[str, str]], mapping: dict[str, str]) -> list[dict[str, str]]:
    if not mapping:
        return rows
    return [{mapping.get(key, key): value for key, value in row.items()} for row in rows]


def _promote(current: Path, published: Path, revision: int) -> None:
    staging = published.parent / f".publicado_revision_{revision}"
    backup = published.parent / ".publicado_anterior"
    for path in (staging, backup):
        if path.exists():
            shutil.rmtree(path)
    current.rename(staging)
    try:
        if published.exists():
            published.rename(backup)
        staging.rename(published)
    except Exception:
        if not published.exists() and backup.exists():
            backup.rename(published)
        if staging.exists() and not current.exists():
            staging.rename(current)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _cobertura_declarada(configuracion: Path | None) -> dict[str, str] | None:
    """``datos_observados_hasta`` de la configuración del lote ({tabla: AAAA-MM-DD}) o ``None`` si no se declara."""
    if configuracion is None:
        return None
    valor = json.loads(configuracion.read_text(encoding="utf-8")).get("datos_observados_hasta")
    if valor in (None, {}):
        return None
    if not isinstance(valor, dict) or not all(isinstance(v, str) for v in valor.values()):
        raise ValueError("datos_observados_hasta debe ser un objeto {tabla: 'AAAA-MM-DD'}")
    for v in valor.values():
        date.fromisoformat(v)
    return dict(sorted(valor.items()))


def _incoherencias_cobertura(cobertura: dict[str, str] | None, tablas_dir: Path) -> list[Issue]:
    """Transacciones aceptadas posteriores a la cobertura declarada para su tabla."""
    from .formatos import leer_csv
    if not cobertura:
        return []
    issues = []
    for tabla, hasta in cobertura.items():
        nombre = next((n for n, t in ARCHIVOS.items() if t == tabla), None)
        if nombre is None:
            issues.append(Issue("", 0, "datos_observados_hasta", "COBERTURA_INVALIDA", f"Tabla desconocida en la cobertura: {tabla}", "bloquear"))
            continue
        ruta = tablas_dir / nombre
        if not ruta.exists():
            continue
        fechas = [r["fecha"] for r in leer_csv(ruta) if r.get("fecha")]
        tardias = [f for f in fechas if f > hasta]
        if tardias:
            issues.append(Issue(nombre, 0, "fecha", "COBERTURA_INCOHERENTE",
                                f"{len(tardias)} filas de {tabla} posteriores a la cobertura declarada {hasta} (máxima {max(tardias)}); "
                                "corrige datos_observados_hasta", "bloquear"))
    return issues


def _evento_cobertura(anterior: dict | None, nueva: dict | None, revision: int) -> dict:
    motivo = ("primera_declaracion" if anterior is None and nueva is not None else
              "declaracion_retirada" if nueva is None else "declaracion_actualizada")
    return {"revision": revision, "anterior": anterior, "nueva": nueva, "motivo": motivo,
            "ts": datetime.now().astimezone().isoformat()}


def cargar_lote(datos: Path, salida: Path, configuracion: Path | None = None) -> LoadResult:
    datos = datos / "01_Datos" if (datos / "01_Datos").is_dir() else datos
    salida.mkdir(parents=True, exist_ok=True)
    config = _config_tables(configuracion)
    source_paths = {table: _source_for(table, datos, config)[0] for table in TABLE_ORDER}
    source_hashes = {table: calcular_sha256(path) for table, path in source_paths.items() if path.exists()}
    previous_manifest_path = salida / "manifiesto.json"
    previous_manifest = json.loads(previous_manifest_path.read_text(encoding="utf-8")) if previous_manifest_path.exists() else None
    cobertura = _cobertura_declarada(configuracion)
    if previous_manifest and previous_manifest.get("status") in {"publicable", "reutilizado"} and previous_manifest.get("source_hashes") == source_hashes:
        # Identidad del contenido = huellas de origen; la declaración de cobertura es una identidad aparte.
        if previous_manifest.get("datos_observados_hasta") == cobertura:
            reused = dict(previous_manifest)
            reused["status"] = "reutilizado"
            escribir_json(previous_manifest_path, reused)
            return LoadResult("reutilizado", reused.get("tablas", {}), [], reused)
        incoherentes = _incoherencias_cobertura(cobertura, salida / "publicado")
        intento = {"ts": datetime.now().astimezone().isoformat(), "evento": "cambio_cobertura", "anterior": previous_manifest.get("datos_observados_hasta"),
                   "nueva": cobertura, "revision_contenido": previous_manifest.get("revision")}
        if incoherentes:
            with (salida / "historial_lotes.jsonl").open("a", encoding="utf-8") as history:
                history.write(json.dumps(dict(intento, resultado="rechazado", incidencias=[_issue_as_dict(i) for i in incoherentes]),
                                         ensure_ascii=False) + "\n")
            return LoadResult("fallido", previous_manifest.get("tablas", {}), incoherentes,
                              dict(previous_manifest, status="fallido", motivo="declaración de cobertura incoherente; se conserva la revisión anterior"))
        revision = int(previous_manifest.get("revision", 0)) + 1
        actualizado = {k: v for k, v in previous_manifest.items() if k != "datos_observados_hasta"}
        actualizado.update({"status": "reutilizado", "revision": revision, "fecha_generacion": datetime.now().astimezone().isoformat(),
                            "contenido_de_revision": previous_manifest.get("contenido_de_revision", previous_manifest.get("revision")),
                            "cobertura_historial": previous_manifest.get("cobertura_historial", [])
                            + [_evento_cobertura(previous_manifest.get("datos_observados_hasta"), cobertura, revision)]})
        if cobertura:
            actualizado["datos_observados_hasta"] = cobertura
        with (salida / "historial_lotes.jsonl").open("a", encoding="utf-8") as history:
            history.write(json.dumps(previous_manifest, ensure_ascii=False) + "\n")
        escribir_json(previous_manifest_path, actualizado)
        return LoadResult("reutilizado", actualizado.get("tablas", {}), [], actualizado)
    current = salida / "lote_actual"
    if current.exists():
        shutil.rmtree(current)
    current.mkdir()
    inventory: dict[str, dict[str, Any]] = {}
    all_issues: list[Issue] = []
    validated: dict[str, TableValidation] = {}
    raw_rows: dict[str, list[dict[str, object]]] = {}
    source_rows_by_table: dict[str, list[int]] = {}
    normalization_failures: dict[str, int] = {}
    blocking = False

    for table in TABLE_ORDER:
        spec = TABLAS[table]
        path, source_type, sheet, delimiter, mapping = _source_for(table, datos, config)
        filename = path.name
        if not path.exists():
            issue = Issue(filename, 0, "", "ARCHIVO_FALTANTE", "No existe la tabla obligatoria", "bloquear")
            all_issues.append(issue)
            inventory[table] = {"source": filename, "read": 0, "accepted": 0, "isolated": 0, "duplicates": 0, "blocking": True}
            blocking = True
            continue
        try:
            physical_required = mapping.keys() if mapping else spec.columns.keys()
            raw = _map_columns(leer_tabla(path, source_type, hoja=sheet, delimiter=delimiter, required_columns=physical_required), mapping)
        except FormatoError as exc:
            issue = Issue(filename, 0, "", "ERROR_LECTURA", str(exc), "bloquear")
            all_issues.append(issue)
            inventory[table] = {"source": filename, "read": 0, "accepted": 0, "isolated": 0, "duplicates": 0, "blocking": True}
            blocking = True
            continue
        normalized: list[dict[str, object]] = []
        failed_rows = 0
        source_row_numbers: list[int] = []
        for row_number, row in enumerate(raw, start=2):
            try:
                normalized.append(normalizar_fila(row, spec, allow_excel_serial=source_type.lower() in {"xlsx", "xlsm"}))
                source_row_numbers.append(row_number)
            except NormalizacionError as exc:
                failed_rows += 1
                all_issues.append(Issue(filename, row_number, exc.field, "ERROR_NORMALIZACION", str(exc), "aislar"))
        normalization_failures[table] = failed_rows
        raw_rows[table] = normalized
        source_rows_by_table[table] = source_row_numbers
        catalogs = _catalogs(validated)
        result = validar_tabla(normalized, spec, catalogs, archivo=filename, source_rows=source_row_numbers)
        validated[table] = result
        all_issues.extend(result.issues)
        inventory[table] = {"source": filename, "read": len(raw), "accepted": len(result.accepted), "isolated": len(result.isolated) + failed_rows, "duplicates": result.duplicate_count, "blocking": False}
        _write_table(current / next(n for n, t in ARCHIVOS.items() if t == table), spec, result.accepted)

    # Revalida tablas dependientes después de cargar todos los catálogos.
    catalogs = _catalogs(validated)
    for table in ("instalaciones", "ventas", "compras"):
        if table not in raw_rows:
            continue
        spec = TABLAS[table]
        filename = next(name for name, name_table in ARCHIVOS.items() if name_table == table)
        result = validar_tabla(raw_rows[table], spec, catalogs, archivo=filename, source_rows=source_rows_by_table[table])
        old = validated[table]
        if result.issues != old.issues:
            all_issues = [issue for issue in all_issues if issue.file != next(name for name, name_table in ARCHIVOS.items() if name_table == table)]
            all_issues.extend(result.issues)
            validated[table] = result
            inventory[table].update({"accepted": len(result.accepted), "isolated": len(result.isolated) + normalization_failures.get(table, 0), "duplicates": result.duplicate_count})
            _write_table(current / filename, spec, result.accepted)

    optional_path = datos / "ventas_con_incidencias_OPCIONAL.csv"
    if optional_path.exists():
        optional_rows: list[dict[str, object]] = []
        optional_failures = 0
        try:
            optional_raw = leer_tabla(optional_path, "csv", required_columns=TABLAS["ventas"].columns.keys())
            optional_source_rows: list[int] = []
            for row_number, row in enumerate(optional_raw, start=2):
                try:
                    optional_rows.append(normalizar_fila(row, TABLAS["ventas"]))
                    optional_source_rows.append(row_number)
                except NormalizacionError as exc:
                    optional_failures += 1
                    all_issues.append(Issue(optional_path.name, row_number, exc.field, "ERROR_NORMALIZACION", str(exc), "aislar"))
            optional_result = validar_tabla(optional_rows, TABLAS["ventas"], _catalogs(validated), archivo=optional_path.name, source_rows=optional_source_rows)
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
    all_issues.extend(_incoherencias_cobertura(cobertura, current))
    if any(issue.action == "bloquear" for issue in all_issues):
        status = "fallido"

    (salida / "incidencias.jsonl").write_text("".join(json.dumps(_issue_as_dict(issue), ensure_ascii=False) + "\n" for issue in all_issues), encoding="utf-8")
    inventory_doc = {"status": status, "tablas": inventory, "incidencias": len(all_issues)}
    escribir_json(salida / "inventario.json", inventory_doc)
    revision = int(previous_manifest.get("revision", 0)) + 1 if previous_manifest else 1
    manifest = {"status": status, "revision": revision, "fecha_generacion": datetime.now().astimezone().isoformat(), "source_hashes": source_hashes, "tablas": inventory, "ultima_publicacion_conservada": (salida / "publicado").exists()}
    if cobertura:
        manifest["datos_observados_hasta"] = cobertura  # declarada por quien entrega el lote, p. ej. {"ventas": "AAAA-MM-DD"}
    anterior_cob = previous_manifest.get("datos_observados_hasta") if previous_manifest else None
    manifest["cobertura_historial"] = (previous_manifest or {}).get("cobertura_historial", []) + (
        [_evento_cobertura(anterior_cob, cobertura, revision)] if anterior_cob != cobertura else [])
    if status == "publicable":
        try:
            _promote(current, salida / "publicado", revision)
        except OSError as exc:
            status = "fallido"
            manifest["status"] = status
            all_issues.append(Issue("", 0, "", "ERROR_PROMOCION", str(exc), "bloquear"))
    if previous_manifest and previous_manifest.get("source_hashes") != source_hashes:
        with (salida / "historial_lotes.jsonl").open("a", encoding="utf-8") as history:
            history.write(json.dumps(previous_manifest, ensure_ascii=False) + "\n")
    escribir_json(salida / "manifiesto.json", manifest)
    return LoadResult(status, inventory, all_issues, manifest)
