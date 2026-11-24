"""M3.2 · Próxima compra con ajuste de nivel por corte (protocolo ``m32-protocolo-v1``).

Igual que M3.1 (ventana de inicio probable p10–p50 y probabilidad acumulada a 15/30/60 días), pero el Cox puede llevar un
**factor de nivel**: coeficientes y forma de la curva base fijos desde el ajuste y un multiplicador del riesgo acumulado
re-estimado en cada corte con los 3 últimos cortes cuyo seguimiento de 60 días terminó ANTES de ese corte
(``modelos.proxima_compra.factor_nivel``: compras observadas / riesgo acumulado esperado, máxima verosimilitud con forma
fija). Corrige un cambio de nivel de la tasa de compra sin reentrenar. Reutiliza datos, métricas, remuestreo, decisión
y publicación sellada de M3 / M3.1.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import proxima_compra_experimento as M3
from . import proxima_compra_m31 as M31
from .compra import ProtocoloError, _sin_descriptivas
from .datos import DatosAceptados, cargar_datos
from .ejecucion import EjecucionError, canon, json_bytes, publicar_lote, verificar_lote
from .inferencia import cargar_artefacto, desde_dict, sellar
from .proxima_compra import FORMATO, MODELO_ID, REGLA_NIVEL, factor_nivel
from .variables import FUNCION, VERSION_PROXIMA

RAIZ = Path(__file__).resolve().parents[1]
CONFIG_DEFECTO = RAIZ / "modelos" / "config" / "proxima_compra_m32.json"
METRICAS_VERSION = "m32-metricas-v1"
LIMITACIONES = M31.LIMITACIONES + [
    "M3.2 se diseñó después de conocer M3 y M3.1 en validación y comprobación: la comprobación es exploratoria y REUTILIZADA.",
    "El factor de nivel usa los 3 últimos cortes maduros: corrige un cambio de nivel con unos dos meses de retraso.",
]


def cargar_config(ruta: str | Path | None = None) -> dict:
    return json.loads(Path(ruta or CONFIG_DEFECTO).read_text(encoding="utf-8"))


def es_m32(config: dict) -> bool:
    return str(config.get("version_protocolo", "")).startswith("m32-")


def identidad_protocolo(config: dict) -> dict:
    return {"configuracion": _sin_descriptivas(config),
            "codigo": {"version_variables": VERSION_PROXIMA, "transformaciones": {v: FUNCION.get(v) for v in config["variables"]},
                       "formato_artefacto": FORMATO, "metricas": METRICAS_VERSION, "regla_decision": config["regla_decision"],
                       "regla_nivel": REGLA_NIVEL, "estimador_nivel": "eventos / suma(H0(T)·exp(eta)) en los cortes maduros previos"}}


def huella_protocolo(config: dict) -> str:
    return hashlib.sha256(canon(identidad_protocolo(config)).encode()).hexdigest()


def _versionar(d: dict, config: dict, cid: str, nivel: dict | None) -> dict:
    d = {k: v for k, v in d.items() if k != "huella"}
    d["ventana"] = dict(config["ventana"], limites=list(config["ventana"]["limites"]))
    d["probabilidades_acumuladas_dias"] = list(config["probabilidades_acumuladas_dias"])
    d["version_protocolo"] = config["version_protocolo"]
    if nivel:
        d["nivel"] = dict(nivel)
        d["descripcion"] += " Riesgo acumulado multiplicado en cada corte por el factor de nivel de los 3 últimos cortes maduros."
    d["version"] = "pendiente"
    d["version"] = f"proxima_compra-m32-{cid}-" + sellar(d)["huella"][:8]
    return sellar(d)


def con_nivel(art, filas: list[dict], clientes, historial) -> tuple[list[dict], dict]:
    """Copias de las filas con el factor de nivel de su corte (solo artefactos con 'nivel')."""
    if not art.datos.get("nivel"):
        return filas, {}
    factores = {c: factor_nivel(art, clientes, historial, c) for c in sorted({f["corte"] for f in filas})}
    return [dict(f, factor_nivel=factores[f["corte"]]["factor"]) for f in filas], {c.isoformat(): v for c, v in factores.items()}


def entrenar(datos: DatosAceptados, config: dict, salida: str | Path) -> dict:
    salida = Path(salida)
    if config.get("modelo_id") != MODELO_ID or not es_m32(config):
        raise ProtocoloError("La configuración no es un protocolo M3.2 de proxima_compra")
    if (salida / "config.json").exists() and canon(json.loads((salida / "config.json").read_text(encoding="utf-8"))) != canon(config):
        raise EjecucionError(f"{salida} pertenece a otra configuración; una configuración nueva requiere una carpeta de ejecución nueva.")
    ds = M3.preparar(datos, config)
    aj, va = ds["bloques"]["ajuste"], ds["bloques"]["validacion"]
    candidatos = {"km": {"familia": "km", "alpha": None, "artefacto": _versionar(M3.artefacto_km(aj, config, datos), config, "km", None)}}
    diagnostico, val, factores_val = {}, {}, {}
    variables = config["variables"]
    for familia, spec in config["candidatos"].items():
        for alpha in spec["alpha"]:
            cid = f"{familia}-a{str(alpha).replace('.', '_')}"
            m, trans, avisos = M3.ajustar_cox(aj, variables, alpha, config)
            art_d = _versionar(M3.artefacto_cox(m, trans, variables, alpha, aj, config, datos, avisos), config, cid, spec.get("nivel"))
            art = desde_dict(json.loads(json.dumps(art_d)))
            sin_nivel = desde_dict(json.loads(json.dumps(_versionar(M3.artefacto_cox(m, trans, variables, alpha, aj, config, datos, avisos), config, cid, None))))
            eq = M3.equivalencia(m, trans, sin_nivel, aj[:200] + va)  # la parte de Cox coincide con scikit-survival
            if eq["diferencia_maxima_supervivencia"] > config["tolerancia_equivalencia"]:
                raise ValueError(f"{cid}: el artefacto recargado difiere de scikit-survival")
            diagnostico[cid] = {"avisos": avisos, "equivalencia": eq, "coeficientes": dict(zip(variables, art_d["cox"]["coeficientes"]))}
            candidatos[cid] = {"familia": familia, "alpha": alpha, "artefacto": art_d}
    malla = M3.rejilla(aj, va, config)
    for cid, c in candidatos.items():
        art = desde_dict(json.loads(json.dumps(c["artefacto"])))
        filas, fac = con_nivel(art, va, datos.clientes, ds["historial"])
        if fac:
            factores_val[cid] = fac
        if malla["estimable"]:
            mm = M3.medir(art, aj, filas, malla["puntos"])
            val[cid] = M3._publico(mm) | {"calibracion_acumulada": M31.calibracion_acumulada(art, filas, config["probabilidades_acumuladas_dias"])}
    tol = config["seleccion"]["tolerancia"]
    complejidad = {"km": 0} | {f: s["complejidad"] for f, s in config["candidatos"].items()}
    elegido, motivo = "km", "Sin rejilla estimable en validación: se conserva Kaplan-Meier"
    if malla["estimable"]:
        orden = sorted(candidatos, key=lambda c: (round(val[c]["ibs"] / tol), complejidad[candidatos[c]["familia"]], -(candidatos[c]["alpha"] or 0)))
        mejor = orden[0]
        if mejor != "km" and val[mejor]["ibs"] < val["km"]["ibs"] - tol:
            elegido, motivo = mejor, f"{mejor} tiene el menor Brier integrado de validación y mejora a Kaplan-Meier"
        else:
            motivo = "Ningún Cox mejora el Brier integrado de Kaplan-Meier en validación: se conserva Kaplan-Meier"
    seleccion = {"criterio": config["seleccion"], "rejilla_validacion": malla, "elegido": elegido, "motivo": motivo,
                 "elegido_artefacto_huella": candidatos[elegido]["artefacto"]["huella"],
                 "candidatos": {cid: {"familia": c["familia"], "alpha": c["alpha"], "artefacto_huella": c["artefacto"]["huella"],
                                      "artefacto_version": c["artefacto"]["version"], "validacion": val.get(cid)} for cid, c in candidatos.items()},
                 "factores_nivel_validacion": factores_val, "diagnostico": diagnostico,
                 "nota": "Coeficientes y curva base solo del bloque de ajuste; el factor de nivel de cada corte usa únicamente cortes maduros antes de él."}
    km_d = candidatos["km"]["artefacto"]
    archivos = {f"candidatos/{cid}.json": json_bytes(c["artefacto"]) for cid, c in candidatos.items()}
    archivos |= {"artefacto.json": json_bytes(candidatos[elegido]["artefacto"]), "referencia_km.json": json_bytes(km_d),
                 "config.json": json_bytes(config), "seleccion.json": json_bytes(seleccion), "entorno.json": json_bytes(M3.entorno_m3()),
                 "protocolo.json": json_bytes({"version": config["version_protocolo"], "huella": huella_protocolo(config), "identidad": identidad_protocolo(config)}),
                 "datos.json": json_bytes(dict(datos.descripcion(), fronteras_verificadas=ds["fronteras"],
                                               conteos_por_bloque={b: M3.conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in M3.ORDEN_BLOQUES}))}
    meta = {"formato": 3, "modelo_id": MODELO_ID, "protocolo": {"version": config["version_protocolo"], "huella": huella_protocolo(config)},
            "artefacto_huella": seleccion["elegido_artefacto_huella"], "artefacto_version": candidatos[elegido]["artefacto"]["version"],
            "seleccion_elegido": elegido, "referencia_km_huella": km_d["huella"], "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "bloques_usados": ["ajuste", "validacion"], "bloque_reservado": "comprobacion_historica (ya vista en M3 y M3.1: exploratoria)"}
    marcador = publicar_lote(salida, archivos, M3.MARCADOR_CONGELACION, meta,
                             volatiles={"fechas_piloto": M3.fechas_piloto(datetime.now(timezone.utc).date())})
    return {"congelacion": marcador, "seleccion": seleccion, "conteos": {b: M3.conteos(ds["bloques"][b], ds["exclusiones"][b]) for b in M3.ORDEN_BLOQUES},
            "fronteras": ds["fronteras"]}


def verificar_congelacion(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    cong = verificar_lote(ejecucion, M3.MARCADOR_CONGELACION, ProtocoloError)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    if not es_m32(config) or huella_protocolo(config) != cong["protocolo"]["huella"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado; crea una version_protocolo y una ejecución nuevas.")
    sel = json.loads((ejecucion / "seleccion.json").read_text(encoding="utf-8"))
    if sel["elegido_artefacto_huella"] != cong["artefacto_huella"] or sel["elegido"] != cong["seleccion_elegido"]:
        raise ProtocoloError("La selección congelada no coincide con el artefacto principal registrado en la congelación.")
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    cand = cargar_artefacto(ejecucion / "candidatos" / f"{cong['seleccion_elegido']}.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    if not (art.huella == cand.huella == cong["artefacto_huella"]) or km.huella != cong["referencia_km_huella"]:
        raise ProtocoloError("artefacto.json o referencia_km.json no son los congelados.")
    return cong


def evaluar(ejecucion: str | Path, datos: DatosAceptados | None = None, m31: str | Path | None = None) -> dict:
    """Comprobación (exploratoria y reutilizada). ``m31``: ejecución M3.1 medida solo como contexto (sin nivel)."""
    ejecucion = Path(ejecucion)
    cong = verificar_congelacion(ejecucion)
    config = json.loads((ejecucion / "config.json").read_text(encoding="utf-8"))
    info = json.loads((ejecucion / "datos.json").read_text(encoding="utf-8"))
    if datos is None:
        datos = cargar_datos(info["directorio"], aceptar_parcial=info["aceptacion_parcial"], observado_hasta=info["datos_observados_hasta"])
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloError("La revisión de datos difiere de la congelada; una revisión nueva requiere una ejecución nueva.")
    ds = M3.preparar(datos, config)
    aj, pr0 = ds["bloques"]["ajuste"], ds["bloques"]["comprobacion_historica"]
    art = cargar_artefacto(ejecucion / "artefacto.json", modelo_id=MODELO_ID)
    km = cargar_artefacto(ejecucion / "referencia_km.json", modelo_id=MODELO_ID)
    pr, factores = con_nivel(art, pr0, datos.clientes, ds["historial"])
    malla = M3.rejilla(aj, pr, config)
    G = M3.censura_ajuste(aj)
    cont = M3.conteos(pr, ds["exclusiones"]["comprobacion_historica"])
    res: dict[str, Any] = {"conteos": cont, "rejilla": malla, "factores_nivel": factores}
    boot, cal = {}, {}
    if malla["estimable"]:
        mc, mk = M3.medir(art, aj, pr, malla["puntos"]), M3.medir(km, aj, pr0, malla["puntos"])
        mc["concordancia_ipcw"] = M3.concordancia(aj, pr, [art.predictor_lineal(f) for f in pr], malla["hasta"])
        mk["concordancia_ipcw"] = 0.5
        b = config["metricas"]["bootstrap"]
        boot = M3.bootstrap(pr, G, malla["puntos"], mc["_S"], mk["_S"], mc["_resultados"], b["repeticiones"], b["semilla"])
        cal = M31.calibracion_acumulada(art, pr, config["probabilidades_acumuladas_dias"])
        res |= {"candidato": M3._publico(mc), "km": M3._publico(mk),
                "calibracion_acumulada": {"candidato": cal, "km": M31.calibracion_acumulada(km, pr0, config["probabilidades_acumuladas_dias"])},
                "contraste_ibs_sksurv": {"candidato": abs(mc["ibs"] - M3.ibs_referencia(aj, pr, mc["_S"], malla["puntos"]))},
                "por_corte_y_grupo": {"candidato": M3._por_grupo_y_corte(art, pr, G, malla["puntos"]), "km": M3._por_grupo_y_corte(km, pr0, G, malla["puntos"])}}
        if m31:
            M31.verificar_congelacion(m31)
            a31 = cargar_artefacto(Path(m31) / "artefacto.json", modelo_id=MODELO_ID)
            m = M3.medir(a31, aj, pr0, malla["puntos"])
            res["contexto_m31"] = {"version": a31.version, "ibs": m["ibs"], "ventanas_utilizables": m["ventanas"]["utilizables"],
                                   "cobertura": m["cobertura_p10_p90"]["cobertura"],
                                   "calibracion_acumulada": M31.calibracion_acumulada(a31, pr0, config["probabilidades_acumuladas_dias"])}
        # Contexto (no cambia la selección ni la decisión): cada candidato congelado, con su factor de nivel si lo tiene
        ctx = {}
        for cand in sorted((ejecucion / "candidatos").glob("*.json")):
            a_c = cargar_artefacto(cand, modelo_id=MODELO_ID)
            filas_c, _ = con_nivel(a_c, pr0, datos.clientes, ds["historial"])
            m_c = M3.medir(a_c, aj, filas_c, malla["puntos"])
            ctx[cand.stem] = {"ibs": m_c["ibs"], "ventanas_utilizables": m_c["ventanas"]["utilizables"], "cobertura": m_c["cobertura_p10_p90"]["cobertura"],
                              "calibracion_acumulada": M31.calibracion_acumulada(a_c, filas_c, config["probabilidades_acumuladas_dias"])}
        res["contexto_candidatos"] = ctx
        decision = M31.decidir(mc, mk, boot, cont, malla, cong["seleccion_elegido"], cal, config)
    else:
        decision = M31.decidir({}, {}, {}, cont, malla, cong["seleccion_elegido"], cal, config)
    metricas = {"bloque": "comprobacion_historica", "alcance": "comprobación histórica EXPLORATORIA Y REUTILIZADA (ya vista en M3 y M3.1)",
                "ventana": config["ventana"], "artefacto": {"version": art.version, "huella": art.huella, "tipo": art.tipo, "nivel": art.datos.get("nivel")},
                "referencia_km": {"version": km.version, "huella": km.huella}, "resultados": res, "incertidumbre_bootstrap_clientes": boot,
                "nota_cobertura": "'cobertura_p10_p90' mide la ventana declarada por el artefacto (aquí p10–p50).", "limitaciones": LIMITACIONES}
    doc = dict(decision, modelo_id=MODELO_ID, artefacto_huella=cong["artefacto_huella"], artefacto_version=cong["artefacto_version"],
               candidato=cong["seleccion_elegido"], version_protocolo=config["version_protocolo"], protocolo_huella=cong["protocolo"]["huella"],
               sello_congelacion=cong["sello"], origen_datos=config["origen_datos"], alcance=metricas["alcance"],
               limitaciones=LIMITACIONES + ["Ningún modelo se promueve automáticamente; no se activan recordatorios."])
    archivos = {"metricas_comprobacion_historica.json": json_bytes(metricas), "decision.json": json_bytes(doc)}
    marcador = publicar_lote(ejecucion, archivos, M3.MARCADOR_EVALUACION, {"sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"],
                                                                            "m31_contexto": str(m31) if m31 else None})
    return {"metricas": metricas, "decision": doc, "evaluacion": marcador}


def evaluacion_publicada(ejecucion: str | Path) -> dict:
    ejecucion = Path(ejecucion)
    verificar_congelacion(ejecucion)
    m = verificar_lote(ejecucion, M3.MARCADOR_EVALUACION, ProtocoloError)
    return {"evaluacion": m, "decision": json.loads((ejecucion / "decision.json").read_text(encoding="utf-8"))}
