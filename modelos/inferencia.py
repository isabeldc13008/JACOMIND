"""Artefactos JSON de compra a 30 días y puntuación sin dependencias de entrenamiento (B0-04, M1-05, M1.1).

El cierre mensual y la API solo importan este módulo y ``boosting`` (biblioteca estándar). Formatos:

* ``jacomind.regresion_logistica.v1``: ``sigmoide(intercepto + Σ peso_j · (f_j(x_j) − media_j) / desv_j)``
  con ``f`` en {identidad, log1p, asinh}, imputación por la mediana de entrenamiento y argumento acotado a ±35.
* ``jacomind.gradient_boosting.v1`` (``modelos/boosting.py``): árboles exportados como nodos numéricos.

Ambos admiten ``calibracion`` opcional ``{"tipo": "sigmoide", "a", "b"}``: ``p = sigmoide(a · z + b)`` sobre el
puntaje bruto ``z``. Un artefacto se rechaza si su formato, versión de variables, dimensiones, valores finitos,
calibración o huella no cuadran. Los artefactos M1 (sin calibración) conservan su contenido y su huella.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from .variables import (FUNCION, HORIZONTE_DIAS, SIN_HISTORIAL, VARIABLES_INACTIVIDAD_POR_VERSION, VARIABLES_POR_VERSION,
                        VERSION_VARIABLES, VERSIONES_SOPORTADAS, aplicar_transformaciones, variables_para)

FORMATO = "jacomind.regresion_logistica.v1"
FORMATO_BOOSTING = "jacomind.gradient_boosting.v1"
MODELO_ID = "compra_30d"
TOLERANCIA_PROBABILIDAD = 1e-9
FUNCIONES = ("identidad", "log1p", "asinh")
# Especificación por modelo: un artefacto de otro modelo, horizonte o versión de variables se rechaza.
ESPECIFICACIONES = {
    "compra_30d": {"horizonte_dias": HORIZONTE_DIAS, "versiones": VARIABLES_POR_VERSION, "umbral_requerido": True},
    "inactividad_60d": {"horizonte_dias": 60, "versiones": VARIABLES_INACTIVIDAD_POR_VERSION, "umbral_requerido": False,
                        "umbral_frio_dias": 90},
}
ESTADOS_PREDICCION = ["estimado", "referencia", "sin_historial", "historia_insuficiente", "estimacion_vencida",
                      "no_elegible", "modelo_no_disponible"]


class ArtefactoInvalido(ValueError):
    """El artefacto no cumple el esquema, no es finito o es incompatible."""


def huella_artefacto(datos: Mapping[str, Any]) -> str:
    contenido = {k: v for k, v in datos.items() if k != "huella"}
    return hashlib.sha256(json.dumps(contenido, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _finito(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def sigmoide(z: float) -> float:
    return 1 / (1 + math.exp(-max(-35, min(35, z))))


def validar_comunes(d: dict, e: list[str]) -> list[str]:
    """Campos comunes a todos los formatos; devuelve la lista de variables (vacía si es inválida)."""
    esp = ESPECIFICACIONES.get(d.get("modelo_id"))
    if esp is None:
        e.append(f"modelo_id {d.get('modelo_id')!r} desconocido ({sorted(ESPECIFICACIONES)})")
        esp = ESPECIFICACIONES[MODELO_ID]
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    vv = d.get("version_variables")
    por_version = esp["versiones"]
    if vv not in por_version:
        e.append(f"version_variables {vv!r} no soportada para {d.get('modelo_id')} ({sorted(por_version)})")
    if d.get("horizonte_dias") != esp["horizonte_dias"]:
        e.append(f"horizonte_dias {d.get('horizonte_dias')!r} distinto de {esp['horizonte_dias']}")
    if "umbral_frio_dias" in esp and d.get("umbral_frio_dias") != esp["umbral_frio_dias"]:
        e.append(f"umbral_frio_dias {d.get('umbral_frio_dias')!r} distinto de {esp['umbral_frio_dias']}")
    variables, trans = d.get("variables"), d.get("transformaciones")
    if not isinstance(variables, list) or not variables or not all(isinstance(v, str) for v in variables):
        e.append("variables debe ser una lista no vacía de textos")
        variables = []
    elif len(set(variables)) != len(variables) or any(v not in FUNCION for v in variables):
        e.append("variables repetidas o desconocidas")
    elif vv in por_version and any(v not in por_version[vv] for v in variables):
        e.append(f"variables no definidas en {vv}")
    if not isinstance(trans, list) or len(trans) != len(variables):
        e.append(f"transformaciones: dimensión {len(trans) if isinstance(trans, list) else None} distinta de {len(variables)} variables")
    else:
        for i, (v, t) in enumerate(zip(variables, trans)):
            if not isinstance(t, dict) or t.get("variable") != v:
                e.append(f"transformaciones[{i}] no corresponde a {v}")
                continue
            if t.get("funcion") not in FUNCIONES:
                e.append(f"transformaciones[{i}].funcion desconocida")
            if not _finito(t.get("media")):
                e.append(f"transformaciones[{i}].media no finita")
            if not _finito(t.get("desviacion")) or t.get("desviacion") <= 0:
                e.append(f"transformaciones[{i}].desviacion no finita o no positiva")
            if t.get("imputacion") is not None and not _finito(t.get("imputacion")):
                e.append(f"transformaciones[{i}].imputacion no finita")
    if (d.get("umbral") is not None or esp["umbral_requerido"]) and (not _finito(d.get("umbral")) or not 0 <= d.get("umbral") <= 1):
        e.append("umbral fuera de [0, 1]")
    cal = d.get("calibracion")
    if cal is not None:
        if not isinstance(cal, dict) or cal.get("tipo") != "sigmoide" or not _finito(cal.get("a")) or not _finito(cal.get("b")):
            e.append("calibracion debe ser {tipo: sigmoide, a, b} con valores finitos")
        elif cal["a"] <= 0:
            e.append("calibracion.a debe ser positivo (la calibración no puede invertir el orden)")
    po = d.get("politica_orden")
    if po is not None:
        from .ranking import POLITICAS
        if not isinstance(po, dict) or po.get("id") not in POLITICAS:
            e.append(f"politica_orden desconocida ({sorted(POLITICAS)})")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    return variables


def validar_artefacto(d: Any) -> list[str]:
    """Errores de esquema, dimensiones, valores y versión (lista vacía si es válido)."""
    if not isinstance(d, dict):
        return ["el artefacto debe ser un objeto JSON"]
    if d.get("formato") == FORMATO_BOOSTING:
        from .boosting import validar_boosting
        return validar_boosting(d)
    if d.get("formato") == "jacomind.supervivencia.v1":
        from .supervivencia import validar_supervivencia
        return validar_supervivencia(d)
    if d.get("formato") in ("jacomind.inactividad_poisson.v1", "jacomind.inactividad_supervivencia.v1"):
        from .inactividad_m21 import validar_m21
        return validar_m21(d)
    if d.get("formato") == "jacomind.supervivencia_residual.v1":
        from .proxima_compra import validar_artefacto_pc
        return validar_artefacto_pc(d)
    if d.get("formato") == "jacomind.venta_cruzada_logistica.v1":
        from .venta_cruzada import validar_artefacto_vc
        return validar_artefacto_vc(d)
    if d.get("formato") == "jacomind.demanda_origen.v1":
        from .demanda import validar_artefacto_demanda
        return validar_artefacto_demanda(d)
    if d.get("formato") == "jacomind.anomalias_iforest.v1":
        from .anomalias import validar_artefacto_anomalias
        return validar_artefacto_anomalias(d)
    if d.get("formato") == "jacomind.anomalias_m61.v1":
        from .anomalias_m61 import validar_artefacto_m61
        return validar_artefacto_m61(d)
    e: list[str] = []
    if d.get("formato") != FORMATO:
        e.append(f"formato {d.get('formato')!r} incompatible (se espera {FORMATO} o {FORMATO_BOOSTING})")
    variables = validar_comunes(d, e)
    pesos = d.get("pesos")
    if not isinstance(pesos, list) or len(pesos) != len(variables):
        e.append(f"pesos: dimensión {len(pesos) if isinstance(pesos, list) else None} distinta de {len(variables)} variables")
    elif not all(_finito(p) for p in pesos):
        e.append("pesos contiene valores no finitos")
    if not _finito(d.get("intercepto")):
        e.append("intercepto no finito")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class Artefacto:
    datos: dict

    @property
    def version(self) -> str:
        return self.datos["version"]

    @property
    def modelo_id(self) -> str:
        return self.datos.get("modelo_id", MODELO_ID)

    @property
    def version_variables(self) -> str:
        return self.datos.get("version_variables", VERSION_VARIABLES)

    @property
    def umbral(self) -> float | None:
        return None if self.datos.get("umbral") is None else float(self.datos["umbral"])

    @property
    def huella(self) -> str:
        return self.datos["huella"]

    @property
    def disponible_desde(self) -> date:
        return date.fromisoformat(self.datos["disponible_desde"])

    def puntaje_bruto(self, fila: Mapping[str, Any]) -> float:
        vector = [1.0] + aplicar_transformaciones(fila, self.datos["transformaciones"])
        pesos = [float(self.datos["intercepto"])] + [float(p) for p in self.datos["pesos"]]
        return sum(w * x for w, x in zip(pesos, vector))

    def probabilidad(self, fila: Mapping[str, Any]) -> float:
        z = self.puntaje_bruto(fila)
        cal = self.datos.get("calibracion")
        if cal:
            z = cal["a"] * z + cal["b"]
        return sigmoide(z)


def sellar(datos: dict) -> dict:
    """Añade la huella y valida; devuelve el artefacto listo para guardar."""
    datos = {k: v for k, v in datos.items() if k != "huella"}
    datos["huella"] = huella_artefacto(datos)
    errores = validar_artefacto(datos)
    if errores:
        raise ArtefactoInvalido("; ".join(errores))
    return datos


def desde_dict(datos: Any):
    errores = validar_artefacto(datos)
    if errores:
        raise ArtefactoInvalido("; ".join(errores))
    if datos.get("formato") == FORMATO_BOOSTING:
        from .boosting import ArtefactoBoosting
        return ArtefactoBoosting(datos)
    if datos.get("formato") == "jacomind.supervivencia.v1":
        from .supervivencia import ArtefactoSupervivencia
        return ArtefactoSupervivencia(datos)
    if datos.get("formato") in ("jacomind.inactividad_poisson.v1", "jacomind.inactividad_supervivencia.v1"):
        from .inactividad_m21 import ArtefactoM21
        return ArtefactoM21(datos)
    if datos.get("formato") == "jacomind.supervivencia_residual.v1":
        from .proxima_compra import ArtefactoProxima
        return ArtefactoProxima(datos)
    if datos.get("formato") == "jacomind.venta_cruzada_logistica.v1":
        from .venta_cruzada import ArtefactoVentaCruzada
        return ArtefactoVentaCruzada(datos)
    if datos.get("formato") == "jacomind.demanda_origen.v1":
        from .demanda import ArtefactoDemanda
        return ArtefactoDemanda(datos)
    if datos.get("formato") == "jacomind.anomalias_iforest.v1":
        from .anomalias import ArtefactoAnomalias
        return ArtefactoAnomalias(datos)
    if datos.get("formato") == "jacomind.anomalias_m61.v1":
        from .anomalias_m61 import ArtefactoM61
        return ArtefactoM61(datos)
    return Artefacto(datos)


def cargar_artefacto(ruta: str | Path, modelo_id: str | None = None):
    """Carga ``artefacto.json`` (o el directorio que lo contiene), lo valida y lo resuelve por formato.

    Con ``modelo_id`` se rechaza un artefacto válido de otro modelo (p. ej. inactividad donde se espera compra).
    """
    ruta = Path(ruta)
    archivo = ruta / "artefacto.json" if ruta.is_dir() else ruta
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArtefactoInvalido(f"No existe {archivo}") from exc
    except json.JSONDecodeError as exc:
        raise ArtefactoInvalido(f"{archivo}: JSON inválido ({exc})") from exc
    if modelo_id is not None and isinstance(datos, dict) and datos.get("modelo_id") != modelo_id:
        raise ArtefactoInvalido(f"{archivo} es un artefacto de {datos.get('modelo_id')!r}, no de {modelo_id}")
    return desde_dict(datos)


# Predicciones publicables -----------------------------------------------------------------
def senales(v: Mapping[str, Any]) -> list[str]:
    """Señales observadas al corte que acompañan la estimación (no son causas de la compra)."""
    salida = [f"Última compra confirmada hace {v['recencia_dias']} días",
              f"{v['frecuencia_30d']} compras en los últimos 30 días y {v['frecuencia_90d']} en 90 días"]
    if v.get("intervalo_mediano_dias") is None:
        salida.append(f"{v['dias_compra_distintos']} días de compra: historia insuficiente para un intervalo típico")
    else:
        salida.append(f"Intervalo típico entre días de compra: {round(v['intervalo_mediano_dias'])} días")
    return salida


def predicciones_corte(artefacto: Artefacto | None, motivo_ausencia: str | None,
                       clientes: Iterable[Mapping[str, Any]], historial: Mapping[str, list[Mapping[str, Any]]],
                       corte: date) -> list[dict[str, Any]]:
    """Filas C2 ``predicciones_clientes`` (una por cliente) con ``modelo_id = compra_30d``.

    Sin artefacto válido o antes de su disponibilidad: probabilidad nula, estado
    ``modelo_no_disponible`` y motivo explícito; la agenda sigue por reglas.
    """
    if artefacto is not None and corte < artefacto.disponible_desde:
        motivo_ausencia = (f"El corte {corte} es anterior a la disponibilidad del modelo "
                           f"{artefacto.version} ({artefacto.disponible_desde}); se aplican solo las reglas.")
        artefacto = None
    filas = []
    for cliente in sorted(clientes, key=lambda c: str(c["cliente_id"])):
        cid = str(cliente["cliente_id"])
        base = {"cliente_id": cid, "modelo_id": MODELO_ID, "probabilidad": None, "horizonte_dias": HORIZONTE_DIAS,
                "version_modelo": artefacto.version if artefacto else None, "corte": corte.isoformat(),
                "datos_hasta": corte.isoformat(), "umbral": artefacto.umbral if artefacto else None,
                "supera_umbral": None}
        if cliente["fecha_alta"] > corte:
            filas.append(base | {"estado": "no_elegible", "motivos": ["Alta posterior al corte"]})
            continue
        v = variables_para(artefacto.version_variables if artefacto else VERSION_VARIABLES, historial.get(cid, []), corte)
        if v is None:
            filas.append(base | {"estado": SIN_HISTORIAL,
                                 "motivos": ["Sin compras confirmadas hasta el corte; se aplica la regla de primera compra"]})
            continue
        if artefacto is None:
            filas.append(base | {"estado": "modelo_no_disponible",
                                 "motivos": [motivo_ausencia or "No hay versión operativa del modelo"] + senales(v)})
            continue
        p = round(artefacto.probabilidad(v), 6)
        filas.append(base | {"estado": "estimado", "probabilidad": p, "supera_umbral": p >= artefacto.umbral,
                             "motivos": senales(v)})
    return filas
