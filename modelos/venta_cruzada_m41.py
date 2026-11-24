"""M4.1 · Venta cruzada con antigüedad y secuencia reciente; azar y techo por producto como referencias fijas.

Protocolo ``m41-protocolo-v1`` (``modelos/config/venta_cruzada_m41.json``). Reutiliza de M4 (``venta_cruzada_experimento``)
candidatos, etiquetas, estadísticas, métricas con universo fijo, remuestreo por cliente, decisión y publicación sellada.

* ``antiguedad_dias``: corte − fecha de alta.
* ``transicion_reciente``: secuencia «compró q en los últimos 60 días → compra p», suavizada hacia la tasa base de p, con
  eventos MADUROS al corte (``modelos.venta_cruzada.transiciones``).
* Referencias: popularidad (comparador de la decisión), coocurrencia, azar reproducible, techo por producto (diagnóstico
  que usa la respuesta del bloque: nunca para elegir) y el candidato congelado de M4.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import venta_cruzada_experimento as M4
from .compra import ProtocoloError, _sin_descriptivas, entorno
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict
from .variables import FUNCION
from .venta_cruzada import FORMATO, MODELO_ID, cargar_reglas, ranking_modelo, ranking_referencia, transicion_reciente, transiciones

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "venta_cruzada_m41.json"
METRICAS_VERSION = "m41-metricas-v1"
LIMITACIONES = M4.LIMITACIONES + [
    "M4.1 se diseñó después de conocer M4 en validación y comprobación: la comprobación es exploratoria y REUTILIZADA.",
    "El techo por producto usa la respuesta del bloque evaluado: es un diagnóstico del margen disponible, no un método.",
]


def cargar_config(ruta: str | Path | None = None) -> dict:
    return json.loads(Path(ruta or CONFIG_DEFECTO).read_text(encoding="utf-8"))


def es_m41(config: dict) -> bool:
    return str(config.get("version_protocolo", "")).startswith("m41-")


def variables_combinacion(config: dict, comb: str) -> list[str]:
    v = config["variables"]
    return v["cliente"] + v["par"] + ["antiguedad_dias"] + (["transicion_reciente"] if comb == "completa" else [])


def identidad_protocolo(config: dict, reglas: dict) -> dict:
    vs = sorted(set(variables_combinacion(config, "completa")))
    return {"configuracion": _sin_descriptivas(config), "reglas_compatibilidad": reglas,
            "codigo": {"transformaciones": {v: FUNCION.get(v) for v in vs}, "formato_artefacto": FORMATO, "metricas": METRICAS_VERSION,
                       "regla_decision": config["regla_decision"], "transicion": "ventana 60, suavizado 20, eventos maduros, catálogo al corte"}}


def huella_protocolo(config: dict, reglas: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config, reglas)).encode()).hexdigest()


def preparar(datos: DatosAceptados, config: dict, reglas: dict) -> dict:
    """Datos de M4 + antigüedad y secuencia reciente por par, con estadísticas de transición de cada corte (solo <= C)."""
    ds = M4.preparar(datos, config, reglas)
    altas = {str(c["cliente_id"]): c["fecha_alta"] for c in datos.clientes}
    snaps = {}
    for b in M4.ORDEN_BLOQUES:
        for p in ds["bloques"][b]["pares"]:
            k = p["corte"].isoformat()
            if k not in snaps:
                snaps[k] = transiciones(ds["compras"], p["corte"])
            p["antiguedad_dias"] = (p["corte"] - altas[p["cliente_id"]]).days
            p["transicion_reciente"] = transicion_reciente(ds["compras"].get(p["cliente_id"], []), p["producto_id"], snaps[k], p["corte"])
    ds["transiciones"] = snaps
    return ds


def _azar(ps: list[dict], semilla: int) -> list[dict]:
    if not ps:
        return []
    c = ps[0]
    rng = random.Random(f"{semilla}:{c['cliente_id']}:{c['corte']}")
    orden = sorted({p["producto_id"]: p for p in ps}.values(), key=lambda p: p["producto_id"])
    rng.shuffle(orden)
    return orden[:3]


def evaluar_bloque(bloque: dict, art, familias: dict, semilla: int, art_m4=None) -> tuple[dict, dict]:
    pr = bloque["pares"]
    tasa = {p: sum(x["y"] for x in pr if x["producto_id"] == p) / max(1, sum(x["producto_id"] == p for x in pr)) for p in {x["producto_id"] for x in pr}}
    rankers = {"modelo": (lambda ps: ranking_modelo(art, ps)) if art else None,
               "popularidad": lambda ps: ranking_referencia(ps, "popularidad"),
               "coocurrencia": lambda ps: ranking_referencia(ps, "coocurrencia"),
               "azar": lambda ps: _azar(ps, semilla),
               "techo_por_producto": lambda ps: sorted({p["producto_id"]: p for p in ps}.values(), key=lambda p: (-tasa[p["producto_id"]], p["producto_id"]))[:3],
               "m4": (lambda ps: ranking_modelo(art_m4, ps)) if art_m4 else None}
    evs = {k: M4.evaluar_metodo(bloque, f) for k, f in rankers.items() if f}
    comunes = set.intersection(*({(x["cliente_id"], x["corte"]) for x in v["filas"] if x["n_sugeridos"] > 0} for v in evs.values()))
    res = {k: M4.resumir(v, comunes) | {"por_producto": M4.por_producto(v, pr, familias)} for k, v in evs.items()}
    return res, evs


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path, reglas: dict | None = None) -> dict:
    salida = Path(salida)
    reglas = reglas or cargar_reglas()
    if config.get("modelo_id") != MODELO_ID or not es_m41(config):
        raise ProtocoloError("La configuración no es un protocolo M4.1 de venta_cruzada")
    if (salida / "config.json").exists() and canon(json.loads((salida / "config.json").read_text(encoding="utf-8"))) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    ds = preparar(datos, config, reglas)
    aj, va = ds["bloques"]["ajuste"]["pares"], ds["bloques"]["validacion"]["pares"]
    semilla = config["metricas"]["bootstrap"]["semilla"]
    candidatos, equiv, val = {}, {}, {}
    for comb in ("antiguedad", "completa"):
        variables = variables_combinacion(config, comb)
        for C in config["candidato"]["C"]:
            cid = f"{comb}-c{str(C).replace('.', '_')}"
            trans, productos, b0, w, wp, decision = M4.ajustar(aj, variables, C, config)
            art_d = M4.artefacto(f"m41-{comb}", variables, C, trans, productos, b0, w, wp, aj, config, datos, reglas)
            art = desde_dict(json.loads(json.dumps(art_d)))
            dif = max(abs(a - art.puntaje(p)) for a, p in zip(decision(aj + va), aj + va))
            if dif > 1e-9:
                raise ValueError(f"{cid}: el artefacto recargado difiere de scikit-learn en {dif:g}")
            equiv[cid] = {"diferencia_maxima": dif, "pares": len(aj) + len(va)}
            candidatos[cid] = {"combinacion": comb, "C": C, "artefacto": art_d}
            val[cid] = evaluar_bloque(ds["bloques"]["validacion"], art, ds["familias"], semilla)[0]["modelo"]
    refs = evaluar_bloque(ds["bloques"]["validacion"], None, ds["familias"], semilla)[0]
    tol = config["seleccion"]["tolerancia"]
    orden = sorted(candidatos, key=lambda c: (-round(val[c]["hitrate1_universo"] / tol), -round(val[c]["hitrate3_universo"] / tol),
                                             candidatos[c]["combinacion"] != "antiguedad", candidatos[c]["C"]))
    elegido = orden[0]
    seleccion = {"criterio": config["seleccion"]["criterio"], "bloque": "validacion", "orden": orden, "elegido": elegido,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"],
                 "candidatos": {c: {"combinacion": v["combinacion"], "C": v["C"], "artefacto_huella": v["artefacto"]["huella"], "artefacto_version": v["artefacto"]["version"],
                                    "validacion": {k: x for k, x in val[c].items() if k != "por_producto"}, "equivalencia_json_sklearn": equiv[c]} for c, v in candidatos.items()},
                 "referencias_validacion": {k: {kk: x for kk, x in v.items() if kk != "por_producto"} for k, v in refs.items()},
                 "nota": "El techo por producto de validación es un diagnóstico (usa la respuesta) y no interviene en la selección."}
    cont = {b: M4.conteos(ds["bloques"][b]) for b in M4.ORDEN_BLOQUES}
    archivos = {f"candidatos/{c}.json": json_bytes(v["artefacto"]) for c, v in candidatos.items()}
    archivos |= {"artefacto.json": json_bytes(candidatos[elegido]["artefacto"]), "config.json": json_bytes(config), "reglas_compatibilidad.json": json_bytes(reglas),
                 "seleccion.json": json_bytes(seleccion), "estadisticas_por_corte.json": json_bytes(ds["estadisticas"]),
                 "transiciones_por_corte.json": json_bytes(ds["transiciones"]), "entorno.json": json_bytes(entorno()),
                 "protocolo.json": json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config, reglas), "identidad": identidad_protocolo(config, reglas)}),
                 "datos.json": json_bytes(dict(datos.descripcion(), fronteras_verificadas=ds["fronteras"], conteos_por_bloque=cont))}
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config, reglas)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"], "seleccion_elegido": elegido,
            "huella_datos": datos.huella_datos, "revision_datos": datos.revision, "version_reglas": reglas.get("version"),
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica (ya vista en M4: exploratoria)"}
    marcador = publicar_lote(salida, archivos, M4.MARCADOR_CONGELACION, meta, volatiles={"fechas_piloto": M4.fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": cont, "fronteras": ds["fronteras"]}


def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, M4.MARCADOR_CONGELACION, ProtocoloError)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    reglas = json.loads((ejecucion / "reglas_compatibilidad.json").read_text(encoding="utf-8"))
    if not es_m41(config) or huella_protocolo(config, reglas) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    sel = json.loads((ejecucion / "seleccion.json").read_text(encoding="utf-8"))
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    if art.huella != cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json").huella or art.huella != cong["artefacto_huella"]:
        raise ProtocoloError("artefacto.json no es el candidato seleccionado y congelado.")
    return cong


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None, m4: str | Path | None = None) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    reglas = json.loads((ejecucion / "reglas_compatibilidad.json").read_text(encoding="utf-8"))
    info = json.loads((ejecucion / "datos.json").read_text(encoding="utf-8"))
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = preparar(datos, config, reglas)
    for nombre, valor in (("estadisticas_por_corte.json", ds["estadisticas"]), ("transiciones_por_corte.json", ds["transiciones"])):
        if canon(valor) != canon(json.loads((ejecucion / nombre).read_text(encoding="utf-8"))):
            raise ProtocoloError(f"{nombre} no coincide con lo congelado")
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    art_m4 = None
    if m4:
        M4.verificar_congelacion(m4)
        art_m4 = cargar_artefacto(Path(m4) / "artefacto.json", modelo_id=MODELO_ID)
    b = config["metricas"]["bootstrap"]
    res, evs = evaluar_bloque(ds["bloques"]["comprobacion_historica"], art, ds["familias"], b["semilla"], art_m4)
    boot = {f"modelo_menos_{r}": M4.bootstrap(evs, "modelo", r, b["repeticiones"], b["semilla"]) for r in ("popularidad", "azar", "coocurrencia")}
    cont = M4.conteos(ds["bloques"]["comprobacion_historica"])
    decision = M4.decidir(res, boot["modelo_menos_popularidad"], cont, config, True)
    metricas = {"bloque": "comprobacion_historica", "alcance": "comprobación histórica EXPLORATORIA Y REUTILIZADA (ya vista en M4)",
                "universo": "clientes con historial al corte y horizonte observado; abstención = sin acierto", "conteos": cont, "resultados": res,
                "incertidumbre_bootstrap_clientes": boot, "nota_techo": "techo_por_producto usa la tasa real de compra de cada producto en este bloque: margen máximo de un orden por producto",
                "limitaciones": LIMITACIONES}
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"], candidato=cong["seleccion_elegido"],
               version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"], sello_congelacion=cong["sello"], origen_datos=config["origen_datos"],
               dimensiones={"integracion_tecnica": "la de M4 (contrato, sombra, API e interfaz)", "evidencia_predictiva": decision["decision"],
                            "revision_comercial": "pendiente: ninguna revisión humana registrada", "condiciones_piloto": ["revisión comercial", "reglas de compatibilidad", "catálogo con fechas"]},
               limitaciones=LIMITACIONES + ["Ningún modelo se promueve automáticamente; no se crean tareas."])
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas), "decision.json": json_bytes(doc)}
    marcador = publicar_lote(ejecucion, archivos, M4.MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"],
                                                                            "m4_contexto": str(m4) if m4 else None})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, M4.MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": json.loads((ejecucion / "decision.json").read_text(encoding="utf-8"))}
