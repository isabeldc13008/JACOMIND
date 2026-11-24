"""M2 · Riesgo de inactividad a 60 días (``inactividad_60d``): población, etiqueta, fotografías y puntuación.

Solo biblioteca estándar: el cierre, la API y la puntuación en sombra importan este módulo sin dependencias de
entrenamiento. El ajuste y la evaluación están en ``modelos/inactividad_experimento.py``.

Objetivo: probabilidad de que un cliente hoy activo (recencia < 90 días) llegue a 90 días sin compra confirmada en
algún momento de los próximos 60 días. No es abandono definitivo, cancelación contractual ni (1 − recompra).

Población al corte ``C`` (alta <= C; recencia ``r = C − L`` con ``L`` el último día de compra confirmada <= C):

* ``alta_posterior`` → ``no_elegible`` (probabilidad nula).
* sin compras → ``sin_historial`` (nula).
* ``r >= 90`` → ``no_elegible`` con motivo ``ya_frio`` (nula). Se evalúa en reactivación, fuera de este objetivo.
* ``0 <= r <= 29`` → ``estructural``: el cruce L+90 cae después de C+60, el evento es imposible; probabilidad 0
  exacta con motivo. Cuenta en la cobertura, no entra en el aprendizaje ni en la comparación principal.
* ``30 <= r <= 89`` → ``aprendible``: población que se aprende, se prioriza y se compara.

Etiqueta (``etiqueta_inactividad``), con los días DISTINTOS de compra confirmada y el estado al final de cada día:
sea E = C + 60 y el cruce L + 90. Si el cruce cae en (C, E] y no hay compra entre L (excluido) y el día del cruce
(incluido), evento = 1 con ``fecha_cruce``. Una compra el mismo día o antes del cruce lo evita: L pasa a esa compra
y se repite. Una compra posterior a un cruce no borra el evento. Sin cruce y con E <= cobertura → 0. Si la cobertura
no llega a E → pendiente (también para cruces ya observados: se exige el horizonte completo, igual para 0 y 1).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .variables import VERSION_INACTIVIDAD, VERSION_INACTIVIDAD_V2, variables_inactividad

MODELO_ID = "inactividad_60d"
HORIZONTE_DIAS = 60
UMBRAL_FRIO_DIAS = 90
RECENCIA_MIN_APRENDIBLE = UMBRAL_FRIO_DIAS - HORIZONTE_DIAS  # 30
ETIQUETA = "inactivo_60d"
DEFINICION_ETIQUETA = ("inactividad-60d-etiqueta-v1: 1 si el cliente alcanza 90 días sin compra confirmada en (C, C+60], "
                       "recalculando el cruce L+90 tras cada día de compra (una compra el mismo día del cruce lo evita; "
                       "una compra posterior no borra el evento); 0 sin cruce y con cobertura hasta C+60; si no, pendiente")
POBLACIONES = ("aprendible", "estructural", "ya_frio", "sin_historial", "alta_posterior")
MADURA, PENDIENTE, NO_APLICA = "madura", "pendiente", "no_aplica"


def dias_de_compra(compras: Iterable[Mapping[str, Any]], hasta: date | None = None) -> list[date]:
    """Días distintos de compra confirmada (``historial_compras`` ya excluye las no confirmadas)."""
    return sorted({c["fecha"] for c in compras if hasta is None or c["fecha"] <= hasta})


def poblacion_al_corte(cliente: Mapping[str, Any], compras: list[Mapping[str, Any]], corte: date) -> tuple[str, int | None, date | None]:
    """(población, recencia en días, último día de compra) con información hasta el corte inclusive."""
    if cliente["fecha_alta"] > corte:
        return "alta_posterior", None, None
    dias = dias_de_compra(compras, corte)
    if not dias:
        return "sin_historial", None, None
    r = (corte - dias[-1]).days
    if r >= UMBRAL_FRIO_DIAS:
        return "ya_frio", r, dias[-1]
    if r < RECENCIA_MIN_APRENDIBLE:
        return "estructural", r, dias[-1]
    return "aprendible", r, dias[-1]


def etiqueta_inactividad(compras: list[Mapping[str, Any]], corte: date, observado_hasta: date | None,
                         horizonte: int = HORIZONTE_DIAS, umbral: int = UMBRAL_FRIO_DIAS) -> dict[str, Any]:
    """{etiqueta: 1|0|None, estado: madura|pendiente|no_aplica, fecha_cruce, fin_horizonte}.

    Solo aplica a clientes activos al corte (con compras y recencia < umbral)."""
    fin = corte + timedelta(days=horizonte)
    previos = dias_de_compra(compras, corte)
    if not previos or (corte - previos[-1]).days >= umbral:
        return {"etiqueta": None, "estado": NO_APLICA, "fecha_cruce": None, "fin_horizonte": fin.isoformat()}
    if observado_hasta is None or fin > observado_hasta:
        return {"etiqueta": None, "estado": PENDIENTE, "fecha_cruce": None, "fin_horizonte": fin.isoformat()}
    futuros = [d for d in dias_de_compra(compras) if corte < d <= fin]
    ultimo = previos[-1]
    while True:
        cruce = ultimo + timedelta(days=umbral)
        if cruce > fin:
            return {"etiqueta": 0, "estado": MADURA, "fecha_cruce": None, "fin_horizonte": fin.isoformat()}
        siguiente = next((d for d in futuros if d > ultimo), None)
        if siguiente is not None and siguiente <= cruce:  # comprar el mismo día del cruce lo evita
            ultimo = siguiente
            continue
        return {"etiqueta": 1, "estado": MADURA, "fecha_cruce": cruce.isoformat(), "fin_horizonte": fin.isoformat()}


def fotografias(clientes: Iterable[Mapping[str, Any]], historial: Mapping[str, list[Mapping[str, Any]]], cortes: Iterable[date],
                observado_hasta: date, contexto: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    """Una fila por cliente y corte: población, recencia, etiqueta (si aplica) y variables con datos <= corte."""
    contexto = dict(contexto or {})
    clientes = sorted(clientes, key=lambda c: str(c["cliente_id"]))
    filas = []
    for corte in cortes:
        if corte > observado_hasta:
            raise ValueError(f"El corte {corte} es posterior a la cobertura declarada {observado_hasta}")
        for cliente in clientes:
            cid = str(cliente["cliente_id"])
            compras = historial.get(cid, [])
            pob, r, ultimo = poblacion_al_corte(cliente, compras, corte)
            fila = {"cliente_id": cid, "corte": corte, "poblacion": pob, "recencia_dias_corte": r,
                    "ultima_compra": ultimo.isoformat() if ultimo else None, "version_variables": VERSION_INACTIVIDAD,
                    "datos_observados_hasta": observado_hasta, **contexto}
            if pob in ("aprendible", "estructural"):
                et = etiqueta_inactividad(compras, corte, observado_hasta)
                fila.update({ETIQUETA: et["etiqueta"], "estado_etiqueta": et["estado"], "fecha_cruce": et["fecha_cruce"],
                             "fin_horizonte": et["fin_horizonte"]})
                if pob == "estructural" and et["etiqueta"] == 1:  # imposible por construcción: se detiene
                    raise AssertionError(f"Evento en población estructural ({cid}, {corte}): revisar la etiqueta")
                fila.update(variables_inactividad(compras, corte) or {})
            else:
                fila.update({ETIQUETA: None, "estado_etiqueta": NO_APLICA, "fecha_cruce": None, "fin_horizonte": None})
            filas.append(fila)
    return filas


# Predicciones publicables (C2 predicciones_clientes, modelo_id = inactividad_60d) ------------------------
def senales(v: Mapping[str, Any], ultima: str | None) -> list[str]:
    salida = [f"Última compra confirmada hace {v['recencia_dias']} días"]
    if ultima:
        cruce = date.fromisoformat(ultima) + timedelta(days=UMBRAL_FRIO_DIAS)
        salida.append(f"Si no compra, cumpliría 90 días sin compra el {cruce.isoformat()}")
    salida.append(f"{v['dias_compra_90d']} días de compra en los últimos 90 días y {v['dias_compra_180d']} en 180")
    if v.get("intervalo_mediano_dias") is None:
        salida.append(f"{v['dias_compra_distintos']} días de compra: historia insuficiente para un intervalo típico")
    else:
        salida.append(f"Intervalo típico entre días de compra: {round(v['intervalo_mediano_dias'])} días")
    if v.get("renovacion_antes_del_cruce"):  # solo variables v2 (M2.1)
        salida.append("Tiene una instalación cuya renovación se abre antes de cumplir 90 días sin compra")
    return salida


def predicciones_inactividad(artefacto, motivo_ausencia: str | None, clientes: Iterable[Mapping[str, Any]],
                             historial: Mapping[str, list[Mapping[str, Any]]], corte: date,
                             instalaciones: Mapping[str, list[Mapping[str, Any]]] | None = None) -> list[dict[str, Any]]:
    """Filas C2 de ``inactividad_60d``: una por cliente; ``posicion`` ordena la población aprendible estimada.

    Un artefacto con variables ``inactividad_60d-variables-v2`` (M2.1) se puntúa con las variables v2 (fecha de alta y
    ``instalaciones`` por cliente); las señales mostradas son las mismas."""
    if artefacto is not None and artefacto.datos.get("modelo_id") != MODELO_ID:
        raise ValueError(f"El artefacto {artefacto.version} no es de {MODELO_ID}")
    if artefacto is not None and corte < artefacto.disponible_desde:
        motivo_ausencia = (f"El corte {corte} es anterior a la disponibilidad del modelo {artefacto.version} "
                           f"({artefacto.disponible_desde}).")
        artefacto = None
    filas = []
    for cliente in sorted(clientes, key=lambda c: str(c["cliente_id"])):
        cid = str(cliente["cliente_id"])
        compras = historial.get(cid, [])
        pob, r, ultimo = poblacion_al_corte(cliente, compras, corte)
        base = {"cliente_id": cid, "modelo_id": MODELO_ID, "probabilidad": None, "horizonte_dias": HORIZONTE_DIAS,
                "umbral_frio_dias": UMBRAL_FRIO_DIAS, "version_modelo": artefacto.version if artefacto else None,
                "corte": corte.isoformat(), "datos_hasta": corte.isoformat(), "recencia_dias": r, "poblacion": pob,
                "posicion": None}
        if pob == "alta_posterior":
            filas.append(base | {"estado": "no_elegible", "motivos": ["Alta posterior al corte"]})
        elif pob == "sin_historial":
            filas.append(base | {"estado": "sin_historial", "motivos": ["Sin compras confirmadas hasta el corte: no hay actividad que pueda interrumpirse"]})
        elif pob == "ya_frio":
            filas.append(base | {"estado": "no_elegible", "motivos": [f"ya_frio: {r} días sin compra (>= 90); corresponde a reactivación, no a prevención"]})
        elif pob == "estructural":
            filas.append(base | {"estado": "estructural", "probabilidad": 0.0,
                                 "motivos": [f"Riesgo estructural cero: con {r} días sin compra no puede llegar a 90 días dentro de los próximos 60"]})
        else:
            v = variables_inactividad(compras, corte)
            if artefacto is not None and artefacto.version_variables == VERSION_INACTIVIDAD_V2:
                from .inactividad_m21 import variables_inactividad_v2
                v = variables_inactividad_v2(compras, corte, cliente["fecha_alta"], (instalaciones or {}).get(cid, []))
            if artefacto is None:
                filas.append(base | {"estado": "modelo_no_disponible",
                                     "motivos": [motivo_ausencia or "No hay versión del modelo de inactividad para este contexto"] + senales(v, ultimo.isoformat())})
            else:
                p = round(artefacto.probabilidad(v), 6)
                filas.append(base | {"estado": "estimado", "probabilidad": p, "motivos": senales(v, ultimo.isoformat())})
    estimadas = sorted((f for f in filas if f["estado"] == "estimado"), key=lambda f: (-f["probabilidad"], f["cliente_id"]))
    for i, f in enumerate(estimadas, start=1):
        f["posicion"] = i
    return filas


# Publicación en sombra (separada del cierre operativo) -------------------------------------------------------
def puntuar_sombra(artefacto, datos, corte: date, salida: str | Path, *, estado_experimento: str,
                   decision: Mapping[str, Any] | None = None, simulacion_historica: bool = False) -> dict[str, Any]:
    """Publica ``manifiesto.json`` + ``predicciones_clientes.json`` de inactividad en un directorio de SOMBRA.

    No entrena, exige cobertura hasta el corte y el artefacto de ``inactividad_60d``. La publicación se valida con el
    contrato C2 antes de escribir el marcador; repetirla con los mismos insumos no cambia nada (idempotente).
    """
    from contratos.validar import validar_publicacion_sombra
    from .datos import verificar_cobertura_corte
    from .ejecucion import json_bytes, publicar_lote
    from .variables import historial_compras

    if artefacto.datos.get("modelo_id") != MODELO_ID:
        raise ValueError(f"El artefacto {artefacto.version} es de {artefacto.datos.get('modelo_id')!r}, no de {MODELO_ID}")
    if corte < artefacto.disponible_desde and not simulacion_historica:
        raise ValueError(f"{artefacto.version} está disponible desde {artefacto.disponible_desde}; para cortes anteriores usa "
                         "una simulación histórica explícita")
    verificar_cobertura_corte(corte, datos.cobertura)
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    art = artefacto
    if simulacion_historica and corte < artefacto.disponible_desde:
        from dataclasses import replace
        art = replace(artefacto, datos=dict(artefacto.datos, disponible_desde=corte.isoformat()))  # solo en memoria
    inst = None
    if artefacto.version_variables == VERSION_INACTIVIDAD_V2:
        from pipeline.operaciones import _load
        from .inactividad_m21 import instalaciones_por_cliente
        inst = instalaciones_por_cliente(_load(datos.directorio, "base_instalada.csv", "instalaciones"))
    filas = predicciones_inactividad(art, None, datos.clientes, historial, corte, inst)
    conteo = {p: sum(f["poblacion"] == p for f in filas) for p in POBLACIONES}
    manifiesto = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": MODELO_ID, "corte": corte.isoformat(),
                  "estado_experimento": estado_experimento, "operativa": False,
                  "advertencia": "Puntuación experimental en sombra: no cambia la agenda C1 ni crea tareas por sí sola.",
                  "simulacion_historica": simulacion_historica,
                  "modelo": {"version": artefacto.version, "artefacto_huella": artefacto.huella,
                             "version_variables": artefacto.version_variables, "horizonte_dias": HORIZONTE_DIAS,
                             "umbral_frio_dias": UMBRAL_FRIO_DIAS, "decision": dict(decision) if decision else None},
                  "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
                  "cobertura": {"corte": corte.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
                  "conteos": conteo, "tablas": {"predicciones_clientes": {"archivo": "predicciones_clientes.json", "filas": len(filas)}}}
    errores = validar_publicacion_sombra(manifiesto, filas)
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato: " + "; ".join(errores[:5]))
    publicar_lote(salida, {"predicciones_clientes.json": json_bytes(filas)}, "manifiesto.json", manifiesto)
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas}
