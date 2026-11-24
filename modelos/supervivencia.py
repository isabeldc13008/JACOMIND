"""Tiempo hasta la próxima compra (M1.3) en biblioteca estándar: ajuste y artefacto ``jacomind.supervivencia.v1``.

Probabilidad de compra en ``(corte, corte + 30]`` para un cliente con recencia ``r`` (días desde su último día
de compra, es decir, un intervalo abierto que ya dura ``r``):

    p = 1 − S(r + 30) / S(r)

con ``S(t) = (n · S_cliente(t) + k · S_pob(t)) / (n + k)``:

* ``S_pob``: Kaplan–Meier de los intervalos entre días de compra distintos de toda la cartera, con los
  intervalos abiertos al corte como censurados. Más allá del último tiempo observado, cola exponencial
  con la tasa media de los últimos 180 días de la curva.
* ``S_cliente``: fracción de intervalos completos del propio cliente mayores que ``t``; ``n`` es su número.
* ``k``: contracción hacia la población, fijada en el protocolo (no se ajusta).

El ajuste solo usa ventas con fecha <= fecha de referencia y no necesita etiquetas. El artefacto guarda la
curva poblacional congelada; en la inferencia solo se leen la recencia y los intervalos del cliente.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

from .inferencia import MODELO_ID, _finito, huella_artefacto, sigmoide
from .variables import HORIZONTE_DIAS, VERSION_INTERVALOS

FORMATO_SUPERVIVENCIA = "jacomind.supervivencia.v1"
VENTANA_COLA = 180
TASA_MINIMA = 1e-4


def intervalos_hasta(historial: Mapping[str, list[Mapping[str, Any]]], clientes: Iterable[Mapping[str, Any]], hasta: date
                     ) -> tuple[list[int], list[int]]:
    """(intervalos completos, intervalos abiertos censurados) con información conocida en ``hasta``."""
    completos, abiertos = [], []
    for c in clientes:
        if c["fecha_alta"] > hasta:
            continue
        dias = sorted({v["fecha"] for v in historial.get(str(c["cliente_id"]), []) if v["fecha"] <= hasta})
        if not dias:
            continue
        completos.extend((b - a).days for a, b in zip(dias, dias[1:]))
        abiertos.append((hasta - dias[-1]).days)
    return completos, abiertos


def kaplan_meier(completos: list[int], censurados: list[int]) -> tuple[list[int], list[float]]:
    """Curva escalonada S(t) en los tiempos de evento (los censurados salen del riesgo después de sus eventos)."""
    eventos: dict[int, int] = {}
    for t in completos:
        eventos[t] = eventos.get(t, 0) + 1
    sal: dict[int, int] = {}
    for t in censurados:
        sal[t] = sal.get(t, 0) + 1
    en_riesgo = len(completos) + len(censurados)
    s, tiempos, valores = 1.0, [], []
    for t in sorted(set(eventos) | set(sal)):
        d = eventos.get(t, 0)
        if d and en_riesgo > 0:
            s *= 1 - d / en_riesgo
            tiempos.append(t)
            valores.append(s)
        en_riesgo -= d + sal.get(t, 0)
    return tiempos, valores


def _s_pob(t: float, tiempos: list[int], valores: list[float], tasa: float) -> float:
    if not tiempos or t < tiempos[0]:
        return 1.0
    if t > tiempos[-1]:
        return valores[-1] * math.exp(-tasa * (t - tiempos[-1]))
    lo, hi = 0, len(tiempos) - 1
    while lo < hi:  # último tiempo <= t
        mid = (lo + hi + 1) // 2
        if tiempos[mid] <= t:
            lo = mid
        else:
            hi = mid - 1
    return valores[lo]


def tasa_cola(tiempos: list[int], valores: list[float]) -> float:
    if not tiempos or valores[-1] <= 0:
        return TASA_MINIMA
    inicio = tiempos[-1] - VENTANA_COLA
    s0 = _s_pob(inicio, tiempos, valores, 0.0) if inicio >= tiempos[0] else 1.0
    ancho = tiempos[-1] - max(inicio, 0)
    if ancho <= 0 or s0 <= valores[-1]:
        return TASA_MINIMA
    return max(math.log(s0 / valores[-1]) / ancho, TASA_MINIMA)


def probabilidad(recencia: float, intervalos: list[int], curva: Mapping[str, Any], k: float, horizonte: int = HORIZONTE_DIAS) -> float:
    tiempos, valores, tasa = curva["tiempos"], curva["supervivencia"], curva["cola_tasa_diaria"]
    n = len(intervalos)

    def s(t):
        propio = sum(1 for i in intervalos if i > t) / n if n else 0.0
        return (n * propio + k * _s_pob(t, tiempos, valores, tasa)) / (n + k)
    s_r = s(recencia)
    if s_r <= 1e-12:
        p = 1 - math.exp(-tasa * horizonte)
    else:
        p = 1 - s(recencia + horizonte) / s_r
    return min(max(p, 1e-6), 1 - 1e-6)


def ajustar_curva(historial, clientes, hasta: date) -> dict[str, Any]:
    completos, abiertos = intervalos_hasta(historial, clientes, hasta)
    tiempos, valores = kaplan_meier(completos, abiertos)
    return {"tiempos": tiempos, "supervivencia": valores, "cola_tasa_diaria": tasa_cola(tiempos, valores),
            "intervalos_completos": len(completos), "intervalos_abiertos": len(abiertos), "datos_hasta": hasta.isoformat()}


def validar_supervivencia(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") != FORMATO_SUPERVIVENCIA:
        e.append("formato incompatible")
    if d.get("modelo_id") != MODELO_ID:
        e.append("modelo_id incompatible")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if d.get("version_variables") != VERSION_INTERVALOS:
        e.append(f"version_variables debe ser {VERSION_INTERVALOS}")
    if d.get("horizonte_dias") != HORIZONTE_DIAS:
        e.append("horizonte_dias incompatible")
    c = d.get("curva")
    if not isinstance(c, dict):
        e.append("curva ausente")
    else:
        t, s = c.get("tiempos"), c.get("supervivencia")
        if not isinstance(t, list) or not isinstance(s, list) or not t or len(t) != len(s):
            e.append("curva: tiempos y supervivencia deben ser listas no vacías de igual longitud")
        else:
            if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in t) or any(b <= a for a, b in zip(t, t[1:])):
                e.append("curva.tiempos debe ser creciente de enteros no negativos")
            if not all(_finito(x) and 0 <= x <= 1 for x in s) or any(b > a for a, b in zip(s, s[1:])):
                e.append("curva.supervivencia debe ser no creciente en [0, 1]")
        if not _finito(c.get("cola_tasa_diaria")) or c.get("cola_tasa_diaria") <= 0:
            e.append("curva.cola_tasa_diaria debe ser positiva y finita")
    if not _finito(d.get("k_contraccion")) or d.get("k_contraccion") <= 0:
        e.append("k_contraccion debe ser positiva y finita")
    if not _finito(d.get("umbral")) or not 0 <= d.get("umbral") <= 1:
        e.append("umbral fuera de [0, 1]")
    cal = d.get("calibracion")
    if cal is not None and (not isinstance(cal, dict) or cal.get("tipo") != "sigmoide" or not _finito(cal.get("a"))
                            or not _finito(cal.get("b")) or cal["a"] <= 0):
        e.append("calibracion inválida")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoSupervivencia:
    datos: dict

    version = property(lambda self: self.datos["version"])
    version_variables = property(lambda self: self.datos["version_variables"])
    umbral = property(lambda self: float(self.datos["umbral"]))
    huella = property(lambda self: self.datos["huella"])
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))

    def puntaje_bruto(self, fila: Mapping[str, Any]) -> float:
        p = probabilidad(float(fila["recencia_dias"]), list(fila.get("intervalos_dias") or []), self.datos["curva"],
                         float(self.datos["k_contraccion"]), self.datos["horizonte_dias"])
        return math.log(p / (1 - p))

    def probabilidad(self, fila: Mapping[str, Any]) -> float:
        z = self.puntaje_bruto(fila)
        cal = self.datos.get("calibracion")
        if cal:
            z = cal["a"] * z + cal["b"]
        return sigmoide(z)
