"""Artefacto JSON de gradient boosting (M1.1) con inferencia en biblioteca estándar.

Formato ``jacomind.gradient_boosting.v1``: campos comunes (variables, transformaciones, umbral,
calibración opcional, fechas, huella) más ``puntaje_inicial``, ``tasa_aprendizaje`` y ``arboles``. Cada
árbol es una lista de nodos ``{"izq", "der", "variable", "umbral", "valor"}``; las hojas tienen
``izq = der = -1``. El puntaje bruto es ``puntaje_inicial + tasa · Σ valor(hoja)`` y la probabilidad su
sigmoide (con calibración si existe).

Para reproducir exactamente a scikit-learn, que compara en float32, el valor de cada variable se
redondea a float32 antes de comparar con el umbral (``x <= umbral`` va a la izquierda).

No se usa pickle: el artefacto es JSON numérico, validado antes de usarse (estructura y referencias de
nodos, ausencia de ciclos, profundidad, índices de variables, valores finitos y huella).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from .inferencia import (FORMATO_BOOSTING, VERSION_VARIABLES, _finito, huella_artefacto, sigmoide, validar_comunes)
from .variables import aplicar_transformaciones

LIMITE_ARBOLES = 1000
LIMITE_PROFUNDIDAD = 6
LIMITE_NODOS = 2 ** (LIMITE_PROFUNDIDAD + 1) - 1


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def _validar_arbol(nodos: Any, n_vars: int, donde: str) -> list[str]:
    if not isinstance(nodos, list) or not nodos or len(nodos) > LIMITE_NODOS:
        return [f"{donde}: lista de nodos vacía o mayor que {LIMITE_NODOS}"]
    e = []
    profundidad = {0: 0}
    for i, n in enumerate(nodos):
        if not isinstance(n, dict):
            return [f"{donde}[{i}]: nodo no es objeto"]
        izq, der = n.get("izq"), n.get("der")
        if not all(isinstance(x, int) and not isinstance(x, bool) for x in (izq, der)):
            e.append(f"{donde}[{i}]: izq/der deben ser enteros")
            continue
        if i not in profundidad:
            e.append(f"{donde}[{i}]: nodo inalcanzable")
            continue
        if izq == -1 and der == -1:
            if not _finito(n.get("valor")):
                e.append(f"{donde}[{i}]: valor de hoja no finito")
            continue
        # Referencias hacia delante: garantiza ausencia de ciclos.
        if not (i < izq < len(nodos) and i < der < len(nodos)) or izq == der:
            e.append(f"{donde}[{i}]: referencias de hijos inválidas ({izq}, {der})")
            continue
        if not isinstance(n.get("variable"), int) or not 0 <= n["variable"] < n_vars:
            e.append(f"{donde}[{i}]: índice de variable fuera de rango")
        if not _finito(n.get("umbral")):
            e.append(f"{donde}[{i}]: umbral no finito")
        for h in (izq, der):
            if h in profundidad:
                e.append(f"{donde}[{i}]: el nodo {h} tiene dos padres")
            profundidad[h] = profundidad[i] + 1
            if profundidad[h] > LIMITE_PROFUNDIDAD:
                e.append(f"{donde}: profundidad mayor que {LIMITE_PROFUNDIDAD}")
    return e[:20]


def validar_boosting(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") != FORMATO_BOOSTING:
        e.append(f"formato {d.get('formato')!r} distinto de {FORMATO_BOOSTING}")
    variables = validar_comunes(d, e)
    if not _finito(d.get("puntaje_inicial")):
        e.append("puntaje_inicial no finito")
    if not _finito(d.get("tasa_aprendizaje")) or not 0 < d.get("tasa_aprendizaje") <= 1:
        e.append("tasa_aprendizaje fuera de (0, 1]")
    arboles = d.get("arboles")
    if not isinstance(arboles, list) or not arboles or len(arboles) > LIMITE_ARBOLES:
        e.append(f"arboles: lista vacía o mayor que {LIMITE_ARBOLES}")
    else:
        for k, a in enumerate(arboles):
            e.extend(_validar_arbol(a.get("nodos") if isinstance(a, dict) else None, len(variables), f"arboles[{k}]"))
            if len(e) > 30:
                break
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoBoosting:
    datos: dict

    @property
    def version(self) -> str:
        return self.datos["version"]

    @property
    def version_variables(self) -> str:
        return self.datos.get("version_variables", VERSION_VARIABLES)

    @property
    def umbral(self) -> float:
        return float(self.datos["umbral"])

    @property
    def huella(self) -> str:
        return self.datos["huella"]

    @property
    def disponible_desde(self) -> date:
        return date.fromisoformat(self.datos["disponible_desde"])

    def puntaje_bruto(self, fila: Mapping[str, Any]) -> float:
        x = [_f32(v) for v in aplicar_transformaciones(fila, self.datos["transformaciones"])]
        total = 0.0
        for arbol in self.datos["arboles"]:
            nodos, i = arbol["nodos"], 0
            while nodos[i]["izq"] != -1:
                n = nodos[i]
                i = n["izq"] if x[n["variable"]] <= n["umbral"] else n["der"]
            total += nodos[i]["valor"]
        return float(self.datos["puntaje_inicial"]) + float(self.datos["tasa_aprendizaje"]) * total

    def probabilidad(self, fila: Mapping[str, Any]) -> float:
        z = self.puntaje_bruto(fila)
        cal = self.datos.get("calibracion")
        if cal:
            z = cal["a"] * z + cal["b"]
        return sigmoide(z)
