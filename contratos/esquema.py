"""Validador mínimo de JSON Schema (subconjunto) sin dependencias.

Cubre lo que usan los contratos de ``contratos/``: type, const, enum, required,
properties, additionalProperties, items, minimum, maximum, minLength, pattern y
format (date, date-time). Un booleano nunca cuenta como entero o número.
"""
from __future__ import annotations

import re
from datetime import date, datetime

_TIPOS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
}


def _formato_valido(fmt: str, valor: str) -> bool:
    try:
        if fmt == "date":
            return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", valor)) and date.fromisoformat(valor) is not None
        if fmt == "date-time":
            datetime.fromisoformat(valor.replace("Z", "+00:00"))
            return True
    except ValueError:
        return False
    return True


def validar(valor, esquema: dict, ruta: str = "$") -> list[str]:
    """Devuelve la lista de errores (vacía si el valor cumple el esquema)."""
    errores: list[str] = []
    if "const" in esquema and valor != esquema["const"]:
        errores.append(f"{ruta}: se esperaba {esquema['const']!r} y llegó {valor!r}")
        return errores
    if "enum" in esquema and valor not in esquema["enum"]:
        errores.append(f"{ruta}: valor {valor!r} fuera de {esquema['enum']}")
        return errores
    tipos = esquema.get("type")
    if tipos is not None:
        lista = tipos if isinstance(tipos, list) else [tipos]
        if not any(_TIPOS[t](valor) for t in lista):
            errores.append(f"{ruta}: tipo {type(valor).__name__} no admitido (esperado {'/'.join(lista)})")
            return errores
    if valor is None:
        return errores
    if isinstance(valor, str):
        if len(valor) < esquema.get("minLength", 0):
            errores.append(f"{ruta}: texto vacío o demasiado corto")
        if "pattern" in esquema and not re.search(esquema["pattern"], valor):
            errores.append(f"{ruta}: no cumple el patrón {esquema['pattern']}")
        if "format" in esquema and not _formato_valido(esquema["format"], valor):
            errores.append(f"{ruta}: formato {esquema['format']} inválido ({valor!r})")
    if _TIPOS["number"](valor):
        if "minimum" in esquema and valor < esquema["minimum"]:
            errores.append(f"{ruta}: {valor} es menor que {esquema['minimum']}")
        if "maximum" in esquema and valor > esquema["maximum"]:
            errores.append(f"{ruta}: {valor} es mayor que {esquema['maximum']}")
    if isinstance(valor, dict):
        for campo in esquema.get("required", []):
            if campo not in valor:
                errores.append(f"{ruta}: falta el campo obligatorio '{campo}'")
        props = esquema.get("properties", {})
        adicional = esquema.get("additionalProperties", True)
        for campo, sub in valor.items():
            if campo in props:
                errores.extend(validar(sub, props[campo], f"{ruta}.{campo}"))
            elif isinstance(adicional, dict):
                errores.extend(validar(sub, adicional, f"{ruta}.{campo}"))
            elif adicional is False:
                errores.append(f"{ruta}: campo no permitido '{campo}'")
    if isinstance(valor, list) and "items" in esquema:
        for i, item in enumerate(valor):
            errores.extend(validar(item, esquema["items"], f"{ruta}[{i}]"))
    return errores
