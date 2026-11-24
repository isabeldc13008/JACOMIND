"""M2.1 · Inactividad a 60 días: variables v2 y artefactos sin entrenamiento iterativo (biblioteca estándar).

Misma etiqueta y poblaciones que M2 (``modelos/inactividad.py``). Un cliente aprendible con recencia ``r`` cruza los
90 días sin compra si no compra en los próximos ``w = 90 − r`` días (1–60). Dos formatos nuevos modelan eso
directamente; la puntuación solo lee variables calculadas al corte:

* ``jacomind.inactividad_poisson.v1``: ``p = exp(−λ · w)``, con ``λ = (días de compra en 180 d + m · λ0) /
  (exposición + m)``; ``λ0`` es la tasa poblacional del bloque de ajuste y ``m`` la contracción (días).
* ``jacomind.inactividad_supervivencia.v1``: ``p = S(90) / S(r)`` con ``S`` la mezcla contraída de los intervalos del
  cliente y la curva Kaplan–Meier de la cartera (``modelos/supervivencia.py``). El evento ocurre exactamente si el
  intervalo abierto (que ya dura ``r``) supera 90 días: una compra el día 90 lo evita.

La familia logística de M2.1 usa el formato existente ``jacomind.regresion_logistica.v1`` con la versión de
variables ``inactividad_60d-variables-v2``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

from .inferencia import _finito, huella_artefacto
from .variables import VERSION_INACTIVIDAD_V2, variables_inactividad

MODELO_ID = "inactividad_60d"
HORIZONTE_DIAS = 60
UMBRAL_FRIO_DIAS = 90
VENTANA_EXPOSICION = 180
RENOVACION_DIAS = 45
FORMATO_POISSON = "jacomind.inactividad_poisson.v1"
FORMATO_SUPERVIVENCIA = "jacomind.inactividad_supervivencia.v1"
FORMATOS = (FORMATO_POISSON, FORMATO_SUPERVIVENCIA)
P_MIN, P_MAX = 1e-6, 1 - 1e-6


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def instalaciones_por_cliente(instalaciones: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    salida: dict[str, list[dict]] = {}
    for i in instalaciones:
        salida.setdefault(str(i["cliente_id"]), []).append({"fecha_inicio": _d(i["fecha_inicio"]), "fecha_fin": _d(i["fecha_fin"])})
    return salida


def variables_inactividad_v2(compras: list[Mapping[str, Any]], corte: date, fecha_alta: date,
                             instalaciones: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any] | None:
    """Variables v1 + ventana hasta el cruce, exposición, compras esperadas, intervalos e instalaciones al corte.

    Supuesto declarado: una instalación (con su ``fecha_fin``) se conoce desde su ``fecha_inicio``; solo se usan
    instalaciones con ``fecha_inicio <= corte``.
    """
    v = variables_inactividad(compras, corte)
    if v is None:
        return None
    dias = sorted({c["fecha"] for c in compras if c["fecha"] <= corte})
    w = max(UMBRAL_FRIO_DIAS - v["recencia_dias"], 0)
    expo = max(1, min(VENTANA_EXPOSICION, (corte - _d(fecha_alta)).days + 1))
    vigentes = [i for i in instalaciones if _d(i["fecha_inicio"]) <= corte < _d(i["fecha_fin"])]
    renov = any((_d(i["fecha_fin"]) - corte).days - RENOVACION_DIAS <= w for i in vigentes)
    return v | {"ventana_restante_dias": w, "exposicion_180d": expo,
                "compras_esperadas_ventana": v["dias_compra_180d"] / expo * w,
                "intervalos_dias": [(b - a).days for a, b in zip(dias, dias[1:])],
                "instalaciones_vigentes": len(vigentes), "renovacion_antes_del_cruce": int(renov)}


def _acotar(p: float) -> float:
    return min(max(p, P_MIN), P_MAX)


def prob_poisson(fila: Mapping[str, Any], tasa0: float, m: float) -> float:
    lam = (float(fila["dias_compra_180d"]) + m * tasa0) / (float(fila["exposicion_180d"]) + m)
    return _acotar(math.exp(-lam * float(fila["ventana_restante_dias"])))


def prob_supervivencia(fila: Mapping[str, Any], curva: Mapping[str, Any], k: float) -> float:
    from .supervivencia import _s_pob
    tiempos, valores, tasa = curva["tiempos"], curva["supervivencia"], curva["cola_tasa_diaria"]
    intervalos = list(fila.get("intervalos_dias") or [])
    n = len(intervalos)

    def s(t: float) -> float:
        propio = sum(1 for i in intervalos if i > t) / n if n else 0.0
        return (n * propio + k * _s_pob(t, tiempos, valores, tasa)) / (n + k)
    r = float(fila["recencia_dias"])
    s_r = s(r)
    if s_r <= 1e-12:
        return _acotar(math.exp(-tasa * (UMBRAL_FRIO_DIAS - r)))
    return _acotar(s(UMBRAL_FRIO_DIAS) / s_r)


def validar_m21(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") not in FORMATOS:
        e.append(f"formato {d.get('formato')!r} incompatible")
    if d.get("modelo_id") != MODELO_ID:
        e.append(f"modelo_id {d.get('modelo_id')!r}: estos formatos solo sirven para {MODELO_ID}")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if d.get("version_variables") != VERSION_INACTIVIDAD_V2:
        e.append(f"version_variables debe ser {VERSION_INACTIVIDAD_V2}")
    if d.get("horizonte_dias") != HORIZONTE_DIAS:
        e.append(f"horizonte_dias {d.get('horizonte_dias')!r} distinto de {HORIZONTE_DIAS}")
    if d.get("umbral_frio_dias") != UMBRAL_FRIO_DIAS:
        e.append(f"umbral_frio_dias {d.get('umbral_frio_dias')!r} distinto de {UMBRAL_FRIO_DIAS}")
    if d.get("umbral") is not None:
        e.append("umbral debe ser nulo (la política es un cupo)")
    if d.get("formato") == FORMATO_POISSON:
        if not _finito(d.get("tasa_poblacional_diaria")) or not 0 < d["tasa_poblacional_diaria"] < 1:
            e.append("tasa_poblacional_diaria debe estar en (0, 1)")
        if not _finito(d.get("contraccion_dias")) or d["contraccion_dias"] <= 0:
            e.append("contraccion_dias debe ser positiva y finita")
    elif d.get("formato") == FORMATO_SUPERVIVENCIA:
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
        if not _finito(d.get("k_contraccion")) or d["k_contraccion"] <= 0:
            e.append("k_contraccion debe ser positiva y finita")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoM21:
    datos: dict

    version = property(lambda self: self.datos["version"])
    modelo_id = property(lambda self: self.datos["modelo_id"])
    version_variables = property(lambda self: self.datos["version_variables"])
    umbral = property(lambda self: None)
    huella = property(lambda self: self.datos["huella"])
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))

    def probabilidad(self, fila: Mapping[str, Any]) -> float:
        if self.datos["formato"] == FORMATO_POISSON:
            return prob_poisson(fila, float(self.datos["tasa_poblacional_diaria"]), float(self.datos["contraccion_dias"]))
        return prob_supervivencia(fila, self.datos["curva"], float(self.datos["k_contraccion"]))
