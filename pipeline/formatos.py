"""Lectores de formatos físicos sin dependencias externas."""

from __future__ import annotations

import csv
import posixpath
from pathlib import Path
from typing import Iterable
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree as ET


class FormatoError(ValueError):
    """Error de estructura o lectura del archivo de entrada."""


def _validar_encabezados(headers: list[str]) -> list[str]:
    cleaned = [header.strip() for header in headers]
    if not cleaned or any(not header for header in cleaned):
        raise FormatoError("El archivo no tiene encabezados válidos")
    if len(set(cleaned)) != len(cleaned):
        raise FormatoError("El archivo contiene encabezados duplicados")
    return cleaned


def _rows_from_matrix(matrix: Iterable[list[str]], required_columns: Iterable[str] = ()) -> list[dict[str, str]]:
    iterator = iter(matrix)
    try:
        headers = _validar_encabezados(next(iterator))
    except StopIteration as exc:
        raise FormatoError("El archivo está vacío") from exc
    missing = sorted(set(required_columns) - set(headers))
    if missing:
        raise FormatoError(f"Faltan columnas obligatorias: {', '.join(missing)}")
    rows: list[dict[str, str]] = []
    for values in iterator:
        values = list(values)
        if len(values) > len(headers):
            raise FormatoError("Una fila tiene más celdas que el encabezado")
        values.extend([""] * (len(headers) - len(values)))
        rows.append(dict(zip(headers, values)))
    return rows


def leer_csv(ruta: Path, encoding: str = "utf-8-sig", delimiter: str = ",", required_columns: Iterable[str] = ()) -> list[dict[str, str]]:
    """Lee un CSV manteniendo todas las celdas como texto."""
    try:
        with ruta.open("r", encoding=encoding, newline="") as stream:
            return _rows_from_matrix(csv.reader(stream, delimiter=delimiter, strict=True), required_columns)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise FormatoError(f"No se pudo leer CSV {ruta}: {exc}") from exc


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def _xlsx_cell(cell: ET.Element, shared: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _text(cell.find(f"{{{_MAIN_NS}}}is"))
    value = _text(cell.find(f"{{{_MAIN_NS}}}v"))
    if cell_type == "s" and value:
        try:
            return shared[int(value)]
        except (IndexError, ValueError) as exc:
            raise FormatoError(f"Índice de texto compartido inválido: {value}") from exc
    return value


def _column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha()).upper()
    index = 0
    for character in letters:
        index = index * 26 + ord(character) - ord("A") + 1
    return index - 1


def leer_xlsx(ruta: Path, hoja: str | None = None, required_columns: Iterable[str] = ()) -> list[dict[str, str]]:
    """Lee una hoja XLSX sencilla, incluyendo textos inline y compartidos."""
    try:
        with ZipFile(ruta) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            rel_targets = {
                relationship.attrib["Id"]: relationship.attrib["Target"]
                for relationship in relationships.findall(f"{{{_PKG_REL_NS}}}Relationship")
            }
            sheets = workbook.find(f"{{{_MAIN_NS}}}sheets")
            selected = None
            for sheet in (list(sheets) if sheets is not None else []):
                if hoja is None or sheet.attrib.get("name") == hoja:
                    selected = sheet
                    break
            if selected is None:
                requested = hoja or "primera hoja"
                raise FormatoError(f"Hoja inexistente: {requested}")
            relationship_id = selected.attrib.get(f"{{{_REL_NS}}}id")
            target = rel_targets.get(relationship_id or "")
            if not target:
                raise FormatoError("La hoja no tiene una relación válida")
            worksheet_path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [_text(item) for item in shared_root.findall(f"{{{_MAIN_NS}}}si")]
            root = ET.fromstring(archive.read(worksheet_path))
            matrix: list[list[str]] = []
            for row in root.findall(f".//{{{_MAIN_NS}}}row"):
                cells = row.findall(f"{{{_MAIN_NS}}}c")
                values: list[str] = []
                for cell in cells:
                    index = _column_index(cell.attrib.get("r", "A1"))
                    if index >= len(values):
                        values.extend([""] * (index + 1 - len(values)))
                    values[index] = _xlsx_cell(cell, shared)
                matrix.append(values)
            return _rows_from_matrix(matrix, required_columns)
    except FormatoError:
        raise
    except (OSError, KeyError, ET.ParseError, ValueError, BadZipFile) as exc:
        raise FormatoError(f"No se pudo leer XLSX {ruta}: {exc}") from exc


def leer_tabla(ruta: Path, tipo: str, hoja: str | None = None, delimiter: str = ",", required_columns: Iterable[str] = ()) -> list[dict[str, str]]:
    if tipo.lower() == "csv":
        return leer_csv(ruta, delimiter=delimiter, required_columns=required_columns)
    if tipo.lower() in {"xlsx", "xlsm"}:
        return leer_xlsx(ruta, hoja=hoja, required_columns=required_columns)
    raise FormatoError(f"Tipo de archivo no soportado: {tipo}")
