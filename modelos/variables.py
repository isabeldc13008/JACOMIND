"""Fotografías cliente × corte, variables y etiqueta de compra a 30 días (B0-02, M1-02).

Una sola implementación sirve para ajustar, evaluar, puntuar y publicar. Solo usa la
biblioteca estándar.

Fronteras (``d = (corte - fecha).days``):

* Variables: ventas confirmadas con ``fecha <= corte`` (incluye el día del corte).
* Ventana de k días: ``0 <= d < k``, es decir ``[corte - (k-1), corte]``.
  Los 30 días anteriores a la última ventana: ``30 <= d < 60``.
* Etiqueta: 1 si hay una venta confirmada con ``corte < fecha <= corte + 30``; 0 si no la
  hay y ``corte + 30 <= datos_observados_hasta``; pendiente (``None``) en otro caso.
* Dos ventas del mismo día son dos operaciones y un único día de compra. Los intervalos
  se calculan entre días de compra distintos; con menos de tres días distintos (menos de
  dos intervalos) no se calcula intervalo: queda ``None`` y ``historia_insuficiente = 1``.
* Importes COP con la convención A02: importe por operación (``calcular_importe``)
  redondeado a dos decimales antes de sumar. Una venta USD sin TRM no aporta importe.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from typing import Any, Iterable, Mapping

VERSION_VARIABLES = "compra_30d-variables-v1"          # M1 (definiciones congeladas; no cambiar)
VERSION_VARIABLES_V2 = "compra_30d-variables-v2"       # M1.1: v1 + ciclo de recompra y cambio de ritmo
VERSION_INTERVALOS = "compra_30d-intervalos-v1"      # M1.3 supervivencia: v1 + lista de intervalos del cliente
VERSIONES_SOPORTADAS = {VERSION_VARIABLES, VERSION_VARIABLES_V2, VERSION_INTERVALOS}
HORIZONTE_DIAS = 30

GRUPO_A = ["recencia_dias", "frecuencia_30d", "frecuencia_90d", "historial_n"]
GRUPO_B = ["frecuencia_180d", "dias_compra_distintos", "cambio_frecuencia_30d", "intervalo_mediano_dias",
           "intervalo_dispersion_dias", "historia_insuficiente"]
GRUPO_C = ["importe_cop_90d", "ticket_medio_cop", "participacion_recurrentes"]
TODAS = GRUPO_A + GRUPO_B + GRUPO_C

# Forma funcional fija (no se ajusta). La imputación y el escalado sí se ajustan en entrenamiento.
FUNCION = {"recencia_dias": "log1p", "frecuencia_30d": "identidad", "frecuencia_90d": "identidad",
           "historial_n": "log1p", "frecuencia_180d": "identidad", "dias_compra_distintos": "log1p",
           "cambio_frecuencia_30d": "identidad", "intervalo_mediano_dias": "log1p",
           "intervalo_dispersion_dias": "log1p", "historia_insuficiente": "identidad",
           "importe_cop_90d": "log1p", "ticket_medio_cop": "log1p", "participacion_recurrentes": "identidad"}

ELEGIBLE, SIN_HISTORIAL, ALTA_POSTERIOR = "elegible", "sin_historial", "alta_posterior"
MADURA, PENDIENTE, NO_APLICA = "madura", "pendiente", "no_aplica"


# Variables v2 (M1.1). Mínimos de historia: el ciclo exige >= 3 días de compra distintos (2 intervalos);
# el cambio de intervalo exige >= 4 días distintos (3 intervalos). Por debajo, la variable queda nula
# (se imputa con la mediana de entrenamiento) y el indicador correspondiente vale 1.
GRUPO_CICLO = ["ratio_recencia_ciclo", "desfase_ciclo_dias", "cv_intervalos", "ciclo_insuficiente"]
GRUPO_CAMBIO = ["ritmo_90_vs_previo", "cambio_intervalo_rel", "operaciones_por_dia", "cambio_insuficiente"]
# Implementadas pero EXCLUIDAS del experimento principal: dependen de atributos del catálogo (tipo y
# vigencia) cuya disponibilidad histórica no puede demostrarse con el paquete (productos.csv no tiene fechas).
GRUPO_PRODUCTO = ["dias_desde_recurrente", "margen_vigencia_dias", "sin_recurrente", "ciclo_x_recurrente"]
TODAS_V2 = TODAS + GRUPO_CICLO + GRUPO_CAMBIO + GRUPO_PRODUCTO
FUNCION.update({"ratio_recencia_ciclo": "log1p", "desfase_ciclo_dias": "asinh", "cv_intervalos": "log1p",
                "ciclo_insuficiente": "identidad", "ritmo_90_vs_previo": "identidad", "cambio_intervalo_rel": "identidad",
                "operaciones_por_dia": "log1p", "cambio_insuficiente": "identidad", "dias_desde_recurrente": "log1p",
                "margen_vigencia_dias": "asinh", "sin_recurrente": "identidad", "ciclo_x_recurrente": "log1p"})
TODAS_INTERVALOS = TODAS + ["intervalos_dias"]
VARIABLES_POR_VERSION = {VERSION_VARIABLES: set(TODAS), VERSION_VARIABLES_V2: set(TODAS_V2),
                         VERSION_INTERVALOS: set(TODAS_INTERVALOS)}

# M2 · inactividad a 60 días. Frecuencias en DÍAS DE COMPRA distintos (dos ventas del mismo día cuentan una vez),
# coherentes con la etiqueta. Sin atributos del catálogo (solo se conoce su estado actual). Ver docs/modelo-inactividad.md.
VERSION_INACTIVIDAD = "inactividad_60d-variables-v1"
VARIABLES_INACTIVIDAD = ["recencia_dias", "dias_compra_30d", "dias_compra_90d", "dias_compra_180d", "dias_compra_distintos",
                         "cambio_dias_90d", "intervalo_mediano_dias", "intervalo_dispersion_dias", "ratio_recencia_ciclo",
                         "historia_insuficiente", "importe_cop_90d"]
FUNCION.update({"dias_compra_30d": "identidad", "dias_compra_90d": "identidad", "dias_compra_180d": "identidad",
                "cambio_dias_90d": "identidad"})
VARIABLES_INACTIVIDAD_POR_VERSION = {VERSION_INACTIVIDAD: set(VARIABLES_INACTIVIDAD)}
# M2.1 (protocolo m21-protocolo-v1): v1 + ventana hasta el cruce, tasa con exposición e instalaciones. Se calculan en
# ``modelos/inactividad_m21.py`` (necesitan la fecha de alta y la base instalada). ``intervalos_dias`` solo alimenta la
# supervivencia y no es una variable escalar.
VERSION_INACTIVIDAD_V2 = "inactividad_60d-variables-v2"
VARIABLES_INACTIVIDAD_V2 = VARIABLES_INACTIVIDAD + ["ventana_restante_dias", "exposicion_180d", "compras_esperadas_ventana",
                                                    "instalaciones_vigentes", "renovacion_antes_del_cruce"]
FUNCION.update({"ventana_restante_dias": "identidad", "exposicion_180d": "identidad", "compras_esperadas_ventana": "log1p",
                "instalaciones_vigentes": "log1p", "renovacion_antes_del_cruce": "identidad"})
VARIABLES_INACTIVIDAD_POR_VERSION[VERSION_INACTIVIDAD_V2] = set(VARIABLES_INACTIVIDAD_V2)
# M3 · próxima compra: mismas definiciones que inactividad v1 (días de compra distintos, intervalos, importe), calculadas
# con información <= corte por ``variables_inactividad``. Sin catálogo ni instalaciones.
# M4 · venta cruzada: variables de cliente y de par cliente-producto (modelos/venta_cruzada.py).
FUNCION.update({"n_productos": "log1p", "popularidad_rel": "identidad", "afinidad_max": "identidad", "coocurrencia_rel": "identidad",
                "familia_comprada": "identidad", "afinidad_x_recencia": "identidad",
                "antiguedad_dias": "log1p", "transicion_reciente": "identidad"})  # M4.1
VERSION_PROXIMA = "proxima_compra-variables-v1"
VARIABLES_PROXIMA = ["recencia_dias", "dias_compra_90d", "dias_compra_180d", "dias_compra_distintos", "intervalo_mediano_dias",
                     "intervalo_dispersion_dias", "historia_insuficiente", "importe_cop_90d"]


def variables_inactividad(compras: list[Mapping[str, Any]], corte: date) -> dict[str, Any] | None:
    """Variables M2 con ventas confirmadas de fecha <= corte. ``None`` si no hay compras.

    * ``dias_compra_k``: días de compra distintos con ``0 <= corte - día < k``.
    * ``cambio_dias_90d``: días de compra en ``[0, 90)`` menos días en ``[90, 180)``.
    * Intervalos entre días distintos; mediana y desviación absoluta mediana con >= 2 intervalos (si no, nulos
      e ``historia_insuficiente = 1``). ``ratio_recencia_ciclo = recencia / mediana``.
    * ``importe_cop_90d``: suma COP (A02, por operación) de las ventas con ``corte - fecha < 90``; nulo si alguna
      venta de esa ventana no tiene conversión reconstruible (TRM de su fecha ausente).
    """
    obs = [c for c in compras if c["fecha"] <= corte]
    if not obs:
        return None
    dias = sorted({c["fecha"] for c in obs})
    antig = [(corte - d).days for d in dias]
    intervalos = [(b - a).days for a, b in zip(dias, dias[1:])]
    rec = (corte - dias[-1]).days
    if len(intervalos) >= 2:
        med = float(median(intervalos))
        disp = float(median(abs(i - med) for i in intervalos))
    else:
        med = disp = None
    ventana = [c for c in obs if (corte - c["fecha"]).days < 90]
    importe = (None if any(c.get("importe_cop") is None for c in ventana)
               else float(sum((Decimal(str(c["importe_cop"])) for c in ventana), Decimal("0"))))
    d90 = sum(1 for a in antig if a < 90)
    return {"recencia_dias": rec, "dias_compra_30d": sum(1 for a in antig if a < 30), "dias_compra_90d": d90,
            "dias_compra_180d": sum(1 for a in antig if a < 180), "dias_compra_distintos": len(dias),
            "cambio_dias_90d": d90 - sum(1 for a in antig if 90 <= a < 180),
            "intervalo_mediano_dias": med, "intervalo_dispersion_dias": disp,
            "ratio_recencia_ciclo": rec / med if med else None, "historia_insuficiente": int(len(intervalos) < 2),
            "importe_cop_90d": importe}


def fin_de_mes(anio: int, mes: int) -> date:
    siguiente = date(anio + 1, 1, 1) if mes == 12 else date(anio, mes + 1, 1)
    return siguiente - timedelta(days=1)


def cortes_mensuales(desde: date, hasta: date) -> list[date]:
    """Fines de mes en ``[desde, hasta]``."""
    salida, anio, mes = [], desde.year, desde.month
    while True:
        corte = fin_de_mes(anio, mes)
        if corte > hasta:
            return salida
        if corte >= desde:
            salida.append(corte)
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def historial_compras(ventas: Iterable[Mapping[str, Any]], productos: Mapping[str, Mapping[str, Any]],
                      tasas: Mapping[date, Decimal]) -> dict[str, list[dict[str, Any]]]:
    """Ventas confirmadas por cliente, ordenadas por (fecha, venta_id), con importe A02."""
    from pipeline.operaciones import MissingRateError, calcular_importe

    salida: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for v in ventas:
        if v.get("estado", "Confirmada") != "Confirmada":
            continue
        try:
            importe = round(float(calcular_importe(v, tasas)), 2)
        except MissingRateError:
            importe = None
        producto = productos.get(str(v.get("producto_id")), {})
        salida[str(v["cliente_id"])].append({
            "venta_id": str(v.get("venta_id", "")), "fecha": v["fecha"], "importe_cop": importe,
            "familia": str(producto.get("familia_prueba", "DESCONOCIDA")),
            "recurrente": str(producto.get("tipo_prueba", "")).strip().lower() == "recurrente",
            "vigencia_meses": int(producto.get("vigencia_meses") or 0)})
    for compras in salida.values():
        compras.sort(key=lambda c: (c["fecha"], c["venta_id"]))
    return dict(salida)


def variables_al_corte(compras: list[Mapping[str, Any]], corte: date) -> dict[str, Any] | None:
    """Variables con información hasta el corte inclusive. ``None`` si no hay compras."""
    obs = [c for c in compras if c["fecha"] <= corte]
    if not obs:
        return None
    dias = [(corte - c["fecha"]).days for c in obs]
    distintos = sorted({c["fecha"] for c in obs})
    intervalos = [(b - a).days for a, b in zip(distintos, distintos[1:])]
    if len(intervalos) >= 2:
        med = float(median(intervalos))
        dispersion = float(median(abs(i - med) for i in intervalos))
    else:
        med = dispersion = None
    f30 = sum(1 for d in dias if d < 30)
    previos = sum(1 for d in dias if 30 <= d < 60)
    con_importe = [Decimal(str(c["importe_cop"])) for c in obs if c["importe_cop"] is not None]
    reciente = [Decimal(str(c["importe_cop"])) for c, d in zip(obs, dias) if d < 90 and c["importe_cop"] is not None]
    return {
        "recencia_dias": (corte - obs[-1]["fecha"]).days,
        "frecuencia_30d": f30,
        "frecuencia_90d": sum(1 for d in dias if d < 90),
        "historial_n": len(obs),
        "frecuencia_180d": sum(1 for d in dias if d < 180),
        "dias_compra_distintos": len(distintos),
        "cambio_frecuencia_30d": f30 - previos,
        "intervalo_mediano_dias": med,
        "intervalo_dispersion_dias": dispersion,
        "historia_insuficiente": int(len(intervalos) < 2),
        "importe_cop_90d": float(sum(reciente, Decimal("0"))),
        "ticket_medio_cop": float(sum(con_importe, Decimal("0")) / len(con_importe)) if con_importe else None,
        "participacion_recurrentes": sum(1 for c in obs if c["recurrente"]) / len(obs),
    }


def variables_ciclo_al_corte(compras: list[Mapping[str, Any]], corte: date) -> dict[str, Any] | None:
    """Variables v2: las de v1 más ciclo individual, cambio de ritmo y (excluidas del protocolo) producto.

    Solo usa ventas con ``fecha <= corte``; dos ventas del mismo día son dos operaciones y un día de compra.
    """
    base = variables_al_corte(compras, corte)
    if base is None:
        return None
    obs = [c for c in compras if c["fecha"] <= corte]
    dias = [(corte - c["fecha"]).days for c in obs]
    distintos = sorted({c["fecha"] for c in obs})
    intervalos = [(b - a).days for a, b in zip(distintos, distintos[1:])]
    med, disp, rec = base["intervalo_mediano_dias"], base["intervalo_dispersion_dias"], base["recencia_dias"]
    ciclo = len(intervalos) >= 2  # med >= 1 porque los días son distintos
    previos = sum(1 for d in dias if 90 <= d < 180)
    if len(intervalos) >= 3:
        med_prev = float(median(intervalos[:-1]))
        cambio_int = math.log((intervalos[-1] + 1) / (med_prev + 1))
    else:
        cambio_int = None
    recurrentes = [c for c in obs if c.get("recurrente")]
    if recurrentes:
        ultima = recurrentes[-1]
        desde = (corte - ultima["fecha"]).days
        margen = ultima.get("vigencia_meses", 0) * 30.4375 - desde
    else:
        desde = margen = None
    ratio = rec / med if ciclo else None
    return base | {
        "ratio_recencia_ciclo": ratio, "desfase_ciclo_dias": (rec - med) if ciclo else None,
        "cv_intervalos": (disp / med) if ciclo else None, "ciclo_insuficiente": int(not ciclo),
        "ritmo_90_vs_previo": math.log((base["frecuencia_90d"] + 1) / (previos + 1)),
        "cambio_intervalo_rel": cambio_int, "operaciones_por_dia": base["historial_n"] / len(distintos),
        "cambio_insuficiente": int(len(intervalos) < 3),
        "dias_desde_recurrente": desde, "margen_vigencia_dias": margen, "sin_recurrente": int(not recurrentes),
        "ciclo_x_recurrente": ratio * base["participacion_recurrentes"] if ratio is not None else None,
    }


def variables_para(version: str, compras: list[Mapping[str, Any]], corte: date) -> dict[str, Any] | None:
    """Constructor de variables de la versión pedida (cada artefacto se resuelve con sus definiciones)."""
    if version == VERSION_VARIABLES:
        return variables_al_corte(compras, corte)
    if version == VERSION_VARIABLES_V2:
        return variables_ciclo_al_corte(compras, corte)
    if version == VERSION_INTERVALOS:
        base = variables_al_corte(compras, corte)
        if base is None:
            return None
        dias = sorted({c["fecha"] for c in compras if c["fecha"] <= corte})
        return base | {"intervalos_dias": [(b - a).days for a, b in zip(dias, dias[1:])]}
    if version == VERSION_INACTIVIDAD:
        return variables_inactividad(compras, corte)
    raise ValueError(f"Versión de variables no soportada: {version}")


def etiqueta_al_corte(compras: list[Mapping[str, Any]], corte: date, observado_hasta: date,
                      horizonte: int = HORIZONTE_DIAS) -> tuple[int | None, str, date]:
    """(etiqueta, estado, fecha de maduración). Futuro incompleto → (None, 'pendiente')."""
    fin = corte + timedelta(days=horizonte)
    if fin > observado_hasta:
        return None, PENDIENTE, fin
    return int(any(corte < c["fecha"] <= fin for c in compras)), MADURA, fin


def construir_fotografias(clientes: Iterable[Mapping[str, Any]], historial: Mapping[str, list[Mapping[str, Any]]],
                          cortes: Iterable[date], observado_hasta: date, *, horizonte: int = HORIZONTE_DIAS,
                          contexto: Mapping[str, Any] | None = None, version: str = VERSION_VARIABLES) -> list[dict[str, Any]]:
    """Una fila por cliente y corte con identificación, elegibilidad, madurez y variables."""
    contexto = dict(contexto or {})
    clientes = sorted(clientes, key=lambda c: str(c["cliente_id"]))
    filas: list[dict[str, Any]] = []
    for corte in cortes:
        if corte > observado_hasta:
            raise ValueError(f"El corte {corte} es posterior a la cobertura declarada {observado_hasta}")
        for cliente in clientes:
            cid = str(cliente["cliente_id"])
            base = {"cliente_id": cid, "corte": corte, "version_variables": version,
                    "datos_observados_hasta": observado_hasta, **contexto}
            if cliente["fecha_alta"] > corte:
                filas.append(base | {"elegibilidad": ALTA_POSTERIOR, "estado_etiqueta": NO_APLICA, "compra_30d": None,
                                     "fecha_maduracion": None})
                continue
            compras = historial.get(cid, [])
            y, estado, fin = etiqueta_al_corte(compras, corte, observado_hasta, horizonte)
            vars_ = variables_para(version, compras, corte)
            fila = base | {"elegibilidad": ELEGIBLE if vars_ else SIN_HISTORIAL, "estado_etiqueta": estado,
                           "compra_30d": y, "fecha_maduracion": fin}
            nombres = {VERSION_VARIABLES: TODAS, VERSION_VARIABLES_V2: TODAS_V2}.get(version, TODAS_INTERVALOS)
            fila.update(vars_ or {k: None for k in nombres} | {"historial_n": 0})
            filas.append(fila)
    return filas


# Transformaciones compartidas -------------------------------------------------------------
def _forma(valor: float, funcion: str) -> float:
    if funcion == "log1p":
        return math.log1p(max(float(valor), 0.0))
    if funcion == "identidad":
        return float(valor)
    if funcion == "asinh":  # variables con signo y colas largas (p. ej. días de adelanto o retraso)
        return math.asinh(float(valor))
    raise ValueError(f"Función de transformación desconocida: {funcion}")


def ajustar_transformaciones(filas: list[Mapping[str, Any]], variables: list[str]) -> list[dict[str, Any]]:
    """Imputación (mediana) y escalado (media, desviación poblacional) solo con las filas dadas."""
    salida = []
    for v in variables:
        funcion = FUNCION[v]
        valores = [_forma(f[v], funcion) for f in filas if f.get(v) is not None]
        if not valores:
            raise ValueError(f"La variable {v} no tiene valores en entrenamiento")
        imput = float(median(valores))
        completos = [_forma(f[v], funcion) if f.get(v) is not None else imput for f in filas]
        media = sum(completos) / len(completos)
        desv = math.sqrt(sum((x - media) ** 2 for x in completos) / len(completos)) or 1.0
        salida.append({"variable": v, "funcion": funcion, "imputacion": imput, "media": media, "desviacion": desv})
    return salida


def aplicar_transformaciones(fila: Mapping[str, Any], transformaciones: list[Mapping[str, Any]]) -> list[float]:
    """Vector escalado de una fila con transformaciones ya ajustadas (idéntico en ajuste e inferencia)."""
    vector = []
    for t in transformaciones:
        valor = fila.get(t["variable"])
        if valor is None:
            if t.get("imputacion") is None:
                raise ValueError(f"Falta {t['variable']} y la transformación no define imputación")
            x = float(t["imputacion"])
        else:
            x = _forma(valor, t["funcion"])
        vector.append((x - float(t["media"])) / float(t["desviacion"]))
    return vector
