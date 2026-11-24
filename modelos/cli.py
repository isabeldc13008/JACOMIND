"""CLI de modelos (ejecutar desde la raíz del proyecto).

    python -m modelos.cli preparar --datos Green_Services_Recursos_de_Prueba --salida salida/a01
    python -m modelos.cli reproducir-referencia --datos salida/a01 --salida salida/experimentos/compra_30d/referencia
    python -m modelos.cli inicializar-referencia --datos salida/a01 --registro var/modelos --version v1
    python -m modelos.cli entrenar --modelo compra_30d --datos salida/a01 --config modelos/config/compra_30d.json --salida salida/experimentos/compra_30d/ejecucion-001
    python -m modelos.cli evaluar --ejecucion salida/experimentos/compra_30d/ejecucion-001 --bloque comprobacion_historica
    python -m modelos.cli promover --ejecucion salida/experimentos/compra_30d/ejecucion-001 --registro var/modelos --version v2 --estado sombra
    python -m modelos.cli puntuar --registro var/modelos --estado sombra --datos salida/a01 --corte 2026-10-31 --salida salida/puntuaciones/2026-10-31/sombra
    python -m modelos.cli comparar --operativo salida/puntuaciones/2026-10-31/operativo --sombra salida/puntuaciones/2026-10-31/sombra --salida salida/puntuaciones/2026-10-31/comparacion
    python -m modelos.cli revertir --registro var/modelos --estado sombra
    python -m modelos.cli autorizar --registro var/modelos --version v2 --decision aprobacion.json --actor ventas.jefe --procedencia "acta 2027-01"
    python -m modelos.cli verificar-protocolo --ejecucion salida/experimentos/compra_30d/ejecucion-001 --config modelos/config/compra_30d.json --salida salida/experimentos/compra_30d/verificacion-ejecucion-001.json
    python -m modelos.cli estado --registro var/modelos

M2 · inactividad a 60 días (``--modelo inactividad_60d``; la evaluación detecta el modelo por su configuración):

    python -m modelos.cli entrenar --modelo inactividad_60d --datos salida/a01 --salida salida/experimentos/inactividad_60d/ejecucion-001
    python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d/ejecucion-001
    python -m modelos.cli puntuar --modelo inactividad_60d --ejecucion salida/experimentos/inactividad_60d/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/inactividad_60d/2026-10-31

M2.1 (misma CLI; el protocolo se detecta por ``version_protocolo``):

    python -m modelos.cli entrenar --modelo inactividad_60d --config modelos/config/inactividad_60d_m21.json --datos salida/a01 --salida salida/experimentos/inactividad_60d_m21/ejecucion-001
    python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d_m21/ejecucion-001 --m2 salida/experimentos/inactividad_60d/ejecucion-001

Códigos de salida: 0 correcto, 1 error, 2 resultado que no cumple (controles distintos, lote no aceptado o promoción rechazada).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

MODELOS = ("compra_30d", "inactividad_60d", "proxima_compra", "venta_cruzada", "demanda", "anomalias")


def _imprimir(datos) -> None:
    print(json.dumps(datos, ensure_ascii=False, indent=1, default=str))


def _config(a):
    from .compra import cargar_config
    return cargar_config(getattr(a, "config", None))


def _datos(a, config):
    from .compra import cargar_datos_config
    return cargar_datos_config(a.datos, config, aceptar_parcial=getattr(a, "aceptar_parcial", False),
                               observado_hasta=getattr(a, "observado_hasta", None))


def cmd_preparar(a) -> int:
    from .datos import preparar_lote
    r = preparar_lote(a.datos, a.salida, a.config_a01)
    _imprimir({"estado": r.status, "revision": r.manifest.get("revision"), "tablas": r.inventory,
               "publicado": str(Path(a.salida) / "publicado") if r.status in ("publicable", "reutilizado") else None})
    return 0 if r.status in ("publicable", "reutilizado") else 2


def cmd_reproducir(a) -> int:
    from .compra import _json, reproducir_referencia
    config = _config(a)
    rep = reproducir_referencia(_datos(a, config), config)
    if a.salida:
        _json(Path(a.salida) / "referencia.json", rep)
    _imprimir({"coincide": rep["controles"]["coincide"], "diferencias": rep["controles"]["diferencias"],
               "obtenido": rep["controles"]["obtenido"]})
    return 0 if rep["controles"]["coincide"] else 2


def cmd_inicializar(a) -> int:
    from . import registro as R
    from .compra import artefacto_referencia, decision_referencia, entorno, reproducir_referencia, verificar_equivalencia_referencia
    from .inferencia import desde_dict
    config = _config(a)
    datos = _datos(a, config)
    rep = reproducir_referencia(datos, config)
    if not rep["controles"]["coincide"]:
        _imprimir({"error": "La reproducción no coincide con los controles; no se registra", "diferencias": rep["controles"]["diferencias"]})
        return 2
    art = desde_dict(artefacto_referencia(rep, config))
    dif = verificar_equivalencia_referencia(art, datos, rep)
    if dif > config["tolerancia_probabilidad"]:
        _imprimir({"error": f"El artefacto difiere de la fórmula original en {dif}"})
        return 2
    origen = {"operacion": "inicializar-referencia", "datos": datos.descripcion(), "entorno": entorno(),
              "equivalencia_formula_original": {"diferencia_maxima": dif, "tolerancia": config["tolerancia_probabilidad"]}}
    reg = R.promover(a.registro, "compra_30d", a.version, art, decision_referencia(art, rep), origen, "operativo", actor="inicializar-referencia")
    _imprimir({"registro": str(R.ruta_registro(a.registro)), "operativo": reg["operativo"], "diferencia_maxima": dif})
    return 0


def _modulo_proxima(config: dict):
    """M3 (``m3-protocolo-v1``) o M3.1 (``m31-...``) según la versión de protocolo."""
    from . import proxima_compra_experimento, proxima_compra_m31, proxima_compra_m32
    if proxima_compra_m32.es_m32(config):
        return proxima_compra_m32
    return proxima_compra_m31 if proxima_compra_m31.es_m31(config) else proxima_compra_experimento


def _entrenar_proxima(a) -> int:
    from .compra import cargar_datos_config
    from .proxima_compra_experimento import cargar_config
    config = cargar_config(a.config)
    entrenar = _modulo_proxima(config).entrenar
    if config.get("modelo_id") != "proxima_compra":
        raise SystemExit(f"La configuración es de {config.get('modelo_id')}, no de proxima_compra")
    datos = cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)
    r = entrenar(datos, config, a.salida)
    sel = r["seleccion"]
    _imprimir({"ejecucion": a.salida, "elegido": sel["elegido"], "motivo": sel["motivo"],
               "artefacto": {"version": r["congelacion"]["artefacto_version"], "huella": r["congelacion"]["artefacto_huella"]},
               "validacion_ibs": {c: (v["validacion"] or {}).get("ibs") for c, v in sel["candidatos"].items()},
               "validacion_ventanas_utilizables": {c: ((v["validacion"] or {}).get("ventanas") or {}).get("proporcion_utilizables_elegibles") for c, v in sel["candidatos"].items()},
               "rejilla_validacion": [sel["rejilla_validacion"]["desde"], sel["rejilla_validacion"]["hasta"]],
               "conteos": {b: {k: c[k] for k in ("filas", "clientes_unicos", "eventos", "censuras")} for b, c in r["conteos"].items()},
               "fronteras": r["fronteras"], "sello": r["congelacion"]["sello"]})
    return 0


def _evaluar_proxima(a) -> int:
    mod = _modulo_proxima(json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8")))
    if getattr(a, "m3", None) and mod.__name__.endswith("m31"):
        r = mod.evaluar(a.ejecucion, m3=a.m3)
    elif getattr(a, "m31", None) and mod.__name__.endswith("m32"):
        r = mod.evaluar(a.ejecucion, m31=a.m31)
    else:
        r = mod.evaluar(a.ejecucion)
    _imprimir({"bloque": "comprobacion_historica (exploratoria)", "decision": r["decision"]["decision"], "motivos": r["decision"]["motivos"],
               "cumple": r["decision"]["cumple"], "valores": r["decision"].get("valores"), "evaluacion_sello": r["evaluacion"]["sello"]})
    return 0


def _puntuar_proxima(a) -> int:
    from .compra import cargar_datos_config
    from .inferencia import cargar_artefacto
    from .proxima_compra import puntuar_sombra
    from .proxima_compra_experimento import cargar_config
    if not a.ejecucion:
        raise SystemExit("proxima_compra se puntúa en sombra desde una ejecución congelada y evaluada (--ejecucion)")
    pub = _modulo_proxima(json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8"))).evaluacion_publicada(a.ejecucion)
    art = cargar_artefacto(Path(a.ejecucion) / "artefacto.json", modelo_id="proxima_compra")
    d = pub["decision"]
    decision = {"decision": d["decision"], "estado_maximo": d["estado_maximo"], "ejecucion": str(a.ejecucion), "artefacto_huella": d["artefacto_huella"],
                "version_protocolo": d["version_protocolo"], "sello_evaluacion": pub["evaluacion"]["sello"]}
    datos = cargar_datos_config(a.datos, cargar_config(), aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)
    r = puntuar_sombra(art, datos, date.fromisoformat(a.corte), a.salida, decision=decision, simulacion_historica=a.simulacion_historica,
                       estado_experimento=f"experimental en sombra · decisión {d['decision']} (datos {d['origen_datos']})")
    m = r["manifiesto"]
    _imprimir({"salida": a.salida, "modelo": m["modelo"]["version"], "tipo": m["modelo"]["tipo"], "conteos": m["conteos"],
               "ventanas_utilizables": m["ventanas_utilizables"], "sello": m["sello"]})
    return 0


def _vc_datos(a):
    from .compra import cargar_datos_config
    from .venta_cruzada_experimento import cargar_config
    config = cargar_config(a.config)
    if config.get("modelo_id") != "venta_cruzada":
        raise SystemExit(f"La configuración es de {config.get('modelo_id')}, no de venta_cruzada")
    return config, cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)


def _dm_datos(a):
    from .compra import cargar_datos_config
    from .demanda_experimento import cargar_config
    config = cargar_config(a.config)
    if config.get("modelo_id") != "demanda":
        raise SystemExit(f"La configuración es de {config.get('modelo_id')}, no de demanda")
    return config, cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)


def _preparar_demanda(a) -> int:
    from .demanda import conciliar, construir_series
    from .ejecucion import json_bytes, publicar_lote
    config, datos = _dm_datos(a)
    series = construir_series(datos, config)
    conc = conciliar(datos, series, config)
    m = publicar_lote(a.salida, {"series.json": json_bytes(series), "conciliacion.json": json_bytes(conc)}, "preparacion.json",
                      {"modelo_id": "demanda", "huella_datos": datos.huella_datos, "revision_datos": datos.revision})
    _imprimir({"salida": a.salida, "series": len(series), "meses": len(next(iter(series.values()))["calendario"]),
               "conciliacion": {"filas": len(conc), "conciliadas": sum(c["conciliado"] for c in conc), "max_diferencia": max((abs(c["diferencia"]) for c in conc), default=0)},
               "sello": m["sello"]})
    return 0


def _an_datos(a):
    from .anomalias import cargar_compras
    from .anomalias_experimento import cargar_config
    from .compra import cargar_datos_config
    config = cargar_config(getattr(a, "config", None))
    datos = cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)
    return config, datos, cargar_compras(datos)


def _preparar_anomalias(a) -> int:
    """M6: operaciones válidas, exclusiones, soporte por bloque, cobertura y control A02 reproducido (idempotente)."""
    from .anomalias_experimento import control_a02, diagnostico, preparar
    from .ejecucion import json_bytes, publicar_lote
    config, datos, compras = _an_datos(a)
    prep = preparar(datos, compras, config)
    diag, a02 = diagnostico(datos, compras, prep, config), control_a02(datos)
    excl = [dict(e, fecha=e["fecha"].isoformat()) for e in prep["excluidas"]]
    m = publicar_lote(a.salida, {"diagnostico.json": json_bytes(diag), "control_a02.json": json_bytes(a02), "exclusiones.json": json_bytes(excl)},
                      "preparacion.json", {"modelo_id": "anomalias", "huella_datos": datos.huella_datos, "revision_datos": datos.revision})
    _imprimir({"salida": a.salida, "entrada": diag["conteos_entrada"], "universos": {u: {k: v[k] for k in ("validas", "excluidas", "por_bloque")} for u, v in diag["universos"].items()},
               "control_a02": {k: a02[k] for k in ("alertas_cierre", "alertas_reproducidas", "coincide")}, "sello": m["sello"]})
    return 0


def _modulo_anomalias(config: dict):
    """M6 (``m6-protocolo-v1``) o M6.1 (``m61-...``) según la versión de protocolo."""
    from . import anomalias_experimento, anomalias_m61_experimento
    from .anomalias_m61 import es_m61
    return anomalias_m61_experimento if es_m61(config) else anomalias_experimento


def _entrenar_anomalias(a) -> int:
    config, datos, compras = _an_datos(a)
    r = _modulo_anomalias(config).entrenar(datos, config, a.salida, compras)
    _imprimir({"ejecucion": a.salida, "seleccion": {u: {k: s.get(k) for k in ("estado", "elegido", "filas_entrenamiento")} for u, s in r["seleccion"].items()},
               "validacion_deteccion": {u: {"referencia": v["referencia"]["deteccion"], **{k: c["deteccion"] for k, c in (v.get("candidatos") or {}).items()}}
                                        for u, v in r["validacion"].items()},
               "equivalencia_json_sklearn": all(e["equivalente"] for e in r["equivalencia"].values()),
               "artefacto": {"version": r["artefacto"]["version"], "huella": r["artefacto"]["huella"]}, "sello": r["congelacion"]["sello"]})
    return 0


def _evaluar_anomalias(a) -> int:
    if not a.datos:
        raise SystemExit("anomalias: la comprobación necesita --datos (la misma revisión A01 congelada)")
    _, datos, compras = _an_datos(a)
    config = json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8"))
    mod = _modulo_anomalias(config)
    r = mod.evaluar(a.ejecucion, datos, compras, m6=a.m6) if mod.__name__.endswith("m61_experimento") else mod.evaluar(a.ejecucion, datos, compras)
    _imprimir({"bloque": "comprobacion_historica (exploratoria)",
               "por_universo": {u: {"referencia": m["referencia"]["deteccion"], "candidato": (m["candidato"] or {}).get("deteccion"), "bootstrap": m["bootstrap"],
                                    "controles_negativos": {"referencia": m["referencia"]["controles_negativos"]["alertas"],
                                                            "candidato": (m["candidato"] or {}).get("controles_negativos", {}).get("alertas")},
                                    "decision": r["decision"]["decisiones"][u]["decision"], "sistema_conservado": r["decision"]["decisiones"][u]["sistema_conservado"],
                                    "motivos": r["decision"]["decisiones"][u]["motivos"]} for u, m in r["metricas"].items()},
               "evaluacion_sello": r["evaluacion"]["sello"]})
    return 0


def _puntuar_anomalias(a) -> int:
    from .anomalias_experimento import evaluacion_publicada
    from .anomalias_m61 import es_m61
    from .inferencia import cargar_artefacto
    if not a.ejecucion:
        raise SystemExit("anomalias se puntúa en sombra desde una ejecución congelada y evaluada (--ejecucion)")
    pub = evaluacion_publicada(a.ejecucion)
    art = cargar_artefacto(Path(a.ejecucion) / "artefacto.json", modelo_id="anomalias")
    _, datos, compras = _an_datos(a)
    config = json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8"))  # el protocolo congelado de la ejecución
    if es_m61(config):
        from .anomalias_m61 import puntuar_sombra
    else:
        from .anomalias import puntuar_sombra
    decs = pub["decision"]["decisiones"]
    metodos = {u: d["sistema_conservado"] for u, d in decs.items()}
    decision = {"decisiones": decs, "artefacto_huella": pub["decision"]["artefacto_huella"], "version_protocolo": pub["decision"]["version_protocolo"],
                "sello_evaluacion": pub["evaluacion"]["sello"], "ejecucion": str(a.ejecucion)}
    resumen = " · ".join(f"{u}: {d['decision']} ({d['sistema_conservado']})" for u, d in decs.items())
    r = puntuar_sombra(art, datos, compras, config, date.fromisoformat(a.corte), a.salida, metodos=metodos, decision=decision,
                       estado_experimento=f"experimental en sombra · {resumen} (datos {config['origen_datos']})")
    m = r["manifiesto"]
    _imprimir({"salida": a.salida, "desde": m["desde"], "corte": m["corte"], "metodos_publicados": m["modelo"]["metodos_publicados"], "conteos": m["conteos"],
               "alertas": {u: v["alertas"] for u, v in m["monitoreo"]["universos"].items()}, "muestra_revision": r["muestra"]["seleccionadas"], "sello": m["sello"]})
    return 0


def cmd_preparar_modelo(a) -> int:
    """M4: control A07, conteos, universo y estadísticas por corte; M5: series y conciliación; M6: dataset y diagnóstico (idempotente)."""
    if a.modelo == "demanda":
        return _preparar_demanda(a)
    if a.modelo == "anomalias":
        return _preparar_anomalias(a)
    from .ejecucion import json_bytes, publicar_lote
    from .venta_cruzada import cargar_reglas
    from .venta_cruzada_experimento import ORDEN_BLOQUES, conteos, control_familias, preparar
    config, datos = _vc_datos(a)
    reglas = cargar_reglas(a.reglas)
    ds = preparar(datos, config, reglas)
    archivos = {"control_familias.json": json_bytes(control_familias(datos)), "estadisticas_por_corte.json": json_bytes(ds["estadisticas"]),
                "conteos.json": json_bytes({b: conteos(ds["bloques"][b]) for b in ORDEN_BLOQUES}), "fronteras.json": json_bytes(ds["fronteras"]),
                "reglas_compatibilidad.json": json_bytes(reglas)}
    m = publicar_lote(a.salida, archivos, "preparacion.json", {"modelo_id": "venta_cruzada", "huella_datos": datos.huella_datos})
    ctl = control_familias(datos)
    _imprimir({"salida": a.salida, "control_familias": {k: ctl[k] for k in ("corte", "coocurrencia", "popularidad", "poblacion")}, "sello": m["sello"]})
    return 0


def _modulo_vc(config: dict):
    """M4 (``m4-protocolo-v1``) o M4.1 (``m41-...``) según la versión de protocolo."""
    from . import venta_cruzada_experimento, venta_cruzada_m41
    return venta_cruzada_m41 if venta_cruzada_m41.es_m41(config) else venta_cruzada_experimento


def _entrenar_vc(a) -> int:
    from .venta_cruzada import cargar_reglas
    config, datos = _vc_datos(a)
    entrenar = _modulo_vc(config).entrenar
    r = entrenar(datos, config, a.salida, cargar_reglas(a.reglas))
    sel = r["seleccion"]
    _imprimir({"ejecucion": a.salida, "elegido": sel["elegido"], "artefacto": {"version": r["congelacion"]["artefacto_version"], "huella": r["congelacion"]["artefacto_huella"]},
               "validacion_hitrate1": {c: v["validacion"]["hitrate1_universo"] for c, v in sel["candidatos"].items()},
               "referencias_validacion_hitrate1": {k: v["hitrate1_universo"] for k, v in sel["referencias_validacion"].items()},
               "conteos": {b: {k: c[k] for k in ("pares", "positivos", "clientes_corte_universo")} for b, c in r["conteos"].items()},
               "fronteras": r["fronteras"], "sello": r["congelacion"]["sello"]})
    return 0


def _evaluar_vc(a) -> int:
    mod = _modulo_vc(json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8")))
    r = mod.evaluar(a.ejecucion, m4=a.m4) if getattr(a, "m4", None) and mod.__name__.endswith("m41") else mod.evaluar(a.ejecucion)
    _imprimir({"bloque": "comprobacion_historica (exploratoria)", "decision": r["decision"]["decision"], "sistema_conservado": r["decision"]["sistema_conservado"],
               "motivos": r["decision"]["motivos"], "cumple": r["decision"]["cumple"], "valores": r["decision"].get("valores"), "evaluacion_sello": r["evaluacion"]["sello"]})
    return 0


def _puntuar_vc(a) -> int:
    from .inferencia import cargar_artefacto
    from .venta_cruzada import cargar_reglas, puntuar_sombra
    if not a.ejecucion:
        raise SystemExit("venta_cruzada se puntúa en sombra desde una ejecución congelada y evaluada (--ejecucion)")
    pub = _modulo_vc(json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8"))).evaluacion_publicada(a.ejecucion)
    d = pub["decision"]
    art = cargar_artefacto(Path(a.ejecucion) / "artefacto.json", modelo_id="venta_cruzada")
    reglas = json.loads((Path(a.ejecucion) / "reglas_compatibilidad.json").read_text(encoding="utf-8"))
    config, datos = _vc_datos(a)
    decision = {"decision": d["decision"], "estado_maximo": d["estado_maximo"], "sistema_conservado": d["sistema_conservado"], "ejecucion": str(a.ejecucion),
                "artefacto_huella": d["artefacto_huella"], "version_protocolo": d["version_protocolo"], "sello_evaluacion": pub["evaluacion"]["sello"]}
    r = puntuar_sombra(art, datos, date.fromisoformat(a.corte), a.salida, decision=decision, reglas=reglas, metodo=d["sistema_conservado"],
                       simulacion_historica=a.simulacion_historica,
                       estado_experimento=f"experimental en sombra · decisión {d['decision']} · sistema {d['sistema_conservado']} (datos {d['origen_datos']})")
    m = r["manifiesto"]
    _imprimir({"salida": a.salida, "sistema_publicado": m["modelo"]["sistema_publicado"], "version": m["modelo"]["version"], "conteos": m["conteos"],
               "recomendaciones": len(r["filas"]), "sello": m["sello"]})
    return 0


def _entrenar_demanda(a) -> int:
    from .demanda_experimento import entrenar
    config, datos = _dm_datos(a)
    r = entrenar(datos, config, a.salida)
    _imprimir({"ejecucion": a.salida, "seleccion": {sid: {h: x["elegido"] for h, x in s["por_horizonte"].items()} for sid, s in r["seleccion"].items()},
               "conciliacion_ok": all(c["conciliado"] for c in r["conciliacion"]), "sello": r["congelacion"]["sello"]})
    return 0


def _evaluar_demanda(a) -> int:
    from .demanda_experimento import evaluar
    r = evaluar(a.ejecucion)
    _imprimir({"bloque": "comprobacion_historica (exploratoria)", "resumen": r["decision"]["resumen"],
               "decisiones": {sid: {h: x["decision"] for h, x in d.items()} for sid, d in r["decision"]["decisiones"].items()}, "evaluacion_sello": r["evaluacion"]["sello"]})
    return 0


def cmd_ajustar_origen(a) -> int:
    from .demanda_experimento import ajustar_origen
    config, datos = _dm_datos(a)
    r = ajustar_origen(a.ejecucion, datos, a.origen, a.salida)
    _imprimir({"salida": a.salida, "version": r["artefacto"]["version"], "huella": r["artefacto"]["huella"],
               "equivalencia_max_relativa": max((e["diferencia_relativa"] for e in r["equivalencias"]), default=0.0), "sello": r["marcador"]["sello"]})
    return 0


def cmd_incorporar(a) -> int:
    from .demanda import incorporar_observaciones
    config, datos = _dm_datos(a)
    r = incorporar_observaciones(a.publicacion, datos, config, a.salida)
    _imprimir({"evaluadas": r["evaluadas"], "pendientes": r["pendientes"], "salida": a.salida})
    return 0


def _puntuar_demanda(a) -> int:
    from .demanda import puntuar_sombra
    from .demanda_experimento import evaluacion_publicada
    from .inferencia import cargar_artefacto
    if not a.artefacto or not a.ejecucion:
        raise SystemExit("demanda se puntúa con un artefacto ya ajustado para el origen (--artefacto) y su ejecución evaluada (--ejecucion)")
    config, datos = _dm_datos(a)
    pub = evaluacion_publicada(a.ejecucion)
    art = cargar_artefacto(a.artefacto, modelo_id="demanda")
    if art.datos.get("sello_evaluacion") != pub["evaluacion"]["sello"]:
        raise SystemExit("El artefacto no procede de la evaluación publicada de esa ejecución")
    r = puntuar_sombra(art, datos, config, a.salida, decision={"resumen": pub["decision"]["resumen"], "decisiones": pub["decision"]["decisiones"], "sello_evaluacion": pub["evaluacion"]["sello"]},
                       estado_experimento=f"experimental en sombra · decisión por serie y horizonte (datos {config['origen_datos']})")
    m = r["manifiesto"]
    _imprimir({"salida": a.salida, "origen": m["origen"], "filas": len(r["filas"]), "sello": m["sello"]})
    return 0


def cmd_entrenar(a) -> int:
    if a.modelo == "anomalias":
        return _entrenar_anomalias(a)
    if a.modelo == "demanda":
        return _entrenar_demanda(a)
    if a.modelo == "venta_cruzada":
        return _entrenar_vc(a)
    if a.modelo == "proxima_compra":
        return _entrenar_proxima(a)
    if a.modelo == "inactividad_60d":
        return _entrenar_inactividad(a)
    from .compra import entrenar
    config = _config(a)
    if config["modelo_id"] != a.modelo:
        raise SystemExit(f"La configuración es de {config['modelo_id']}, no de {a.modelo}")
    r = entrenar(_datos(a, config), config, a.salida)
    _imprimir({"ejecucion": a.salida, "elegido": r["seleccion"]["elegido"], "umbral": r["umbral"],
               "artefacto": {"version": r["artefacto"]["version"], "huella": r["artefacto"]["huella"]},
               "validacion_top10": {k: r["validacion"][k]["ranking"]["agregado"]["precision_media_top10"] for k in ("candidato", "original_congelado")},
               "equivalencia": r["congelacion"]["equivalencia_json_sklearn"],
               "referencia_reproducida": r["reproduccion"]["controles"]["coincide"]})
    return 0


def _modelo_de_ejecucion(ejecucion) -> str:
    cfg = Path(ejecucion) / "config.json"
    return json.loads(cfg.read_text(encoding="utf-8")).get("modelo_id", "compra_30d") if cfg.exists() else "compra_30d"


def _modulo_inactividad(config: dict):
    """M2 (``m2-protocolo-v1``) o M2.1 (``m21-...``) según la versión de protocolo de la configuración."""
    from . import inactividad_experimento, inactividad_m21_experimento
    return inactividad_m21_experimento if inactividad_m21_experimento.es_m21(config) else inactividad_experimento


def _entrenar_inactividad(a) -> int:
    from .compra import cargar_datos_config
    from .inactividad_experimento import cargar_config
    config = cargar_config(a.config)
    entrenar = _modulo_inactividad(config).entrenar
    if config.get("modelo_id") != "inactividad_60d":
        raise SystemExit(f"La configuración es de {config.get('modelo_id')}, no de inactividad_60d")
    datos = cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)
    r = entrenar(datos, config, a.salida)
    sel = r["seleccion"]
    _imprimir({"ejecucion": a.salida, "elegido": sel["elegido"], "sin_candidato": sel["sin_candidato"],
               "artefacto": {"version": r["congelacion"]["artefacto_version"], "huella": r["congelacion"]["artefacto_huella"]},
               "validacion_precision_media_top10": {c: v["validacion"]["ranking"]["agregado"]["precision_media_top10"] if "ranking" in v["validacion"]
                                                    else v["validacion"]["agregado"]["precision_media_top10"] for c, v in sel["candidatos"].items()},
               "mayor_recencia_validacion_top10": sel["referencias_validacion"]["mayor_recencia"]["agregado"]["precision_media_top10"],
               "conteos": {b: {k: c[k] for k in ("aprendibles_maduras", "eventos", "clientes_unicos_aprendibles")} for b, c in r["conteos"].items()},
               "fronteras": r["fronteras"], "sello": r["congelacion"]["sello"]})
    return 0


def _evaluar_inactividad(a) -> int:
    mod = _modulo_inactividad(json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8")))
    r = mod.evaluar(a.ejecucion, m2=a.m2) if getattr(a, "m2", None) else mod.evaluar(a.ejecucion)
    res = r["metricas"]["resultados"]
    _imprimir({"bloque": "comprobacion_historica (exploratoria)", "decision": r["decision"]["decision"], "motivos": r["decision"]["motivos"],
               "cumple": r["decision"]["cumple"], "valores": r["decision"]["valores"],
               "aciertos_top10_por_mes": {k: [m["top10"]["aciertos"] for m in res[k]["por_mes"]] for k in ("candidato", "mayor_recencia", "constante") if res.get(k)},
               "evaluacion_sello": r["evaluacion"]["sello"]})
    return 0


def cmd_evaluar(a) -> int:
    if _modelo_de_ejecucion(a.ejecucion) == "anomalias":
        return _evaluar_anomalias(a)
    if _modelo_de_ejecucion(a.ejecucion) == "demanda":
        return _evaluar_demanda(a)
    if _modelo_de_ejecucion(a.ejecucion) == "venta_cruzada":
        return _evaluar_vc(a)
    if _modelo_de_ejecucion(a.ejecucion) == "proxima_compra":
        return _evaluar_proxima(a)
    if _modelo_de_ejecucion(a.ejecucion) == "inactividad_60d":
        return _evaluar_inactividad(a)
    from .compra import evaluar
    r = evaluar(a.ejecucion, bloque=a.bloque)
    res = r["metricas"]["resultados"]
    _imprimir({"bloque": a.bloque, "decision": r["decision"]["decision"], "estado_maximo": r["decision"]["estado_maximo"],
               "cumple": r["decision"]["cumple"], "valores": r["decision"]["valores"], "meses_a_revisar": r["decision"]["meses_a_revisar"],
               "aciertos_top10_por_mes": {k: [m["top10"]["aciertos"] for m in v["ranking"]["por_mes"]] for k, v in res.items()},
               "precision_media_top10": {k: v["ranking"]["agregado"]["precision_media_top10"] for k, v in res.items()},
               "brier": {k: v["probabilidad"]["brier"] for k, v in res.items() if "probabilidad" in v}})
    return 0


def cmd_promover(a) -> int:
    from . import registro as R
    from .compra import entorno
    from .inferencia import cargar_artefacto
    ejec = Path(a.ejecucion)
    decision_path = ejec / "decision.json"
    if not decision_path.exists():
        _imprimir({"error": "La ejecución no tiene decision.json: evalúa antes de promover"})
        return 2
    art = cargar_artefacto(ejec / "artefacto.json")
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    origen = {"operacion": "promover", "ejecucion": str(ejec.resolve()), "estado": a.estado, "entorno": entorno(),
              "datos": json.loads((ejec / "datos.json").read_text(encoding="utf-8"))}
    try:
        reg = R.promover(a.registro, "compra_30d", a.version, art, decision, origen, a.estado)
    except R.RegistroError as exc:
        _imprimir({"error": str(exc)})
        return 2
    _imprimir({"operativo": reg["operativo"], "sombra": reg["sombra"]})
    return 0


def cmd_revertir(a) -> int:
    from . import registro as R
    try:
        reg = R.revertir(a.registro, "compra_30d", a.estado, a.a)
    except R.RegistroError as exc:
        _imprimir({"error": str(exc)})
        return 2
    _imprimir({"operativo": reg["operativo"], "sombra": reg["sombra"], "ultimo": reg["historial"][-1]})
    return 0


def cmd_resumen_ia(a) -> int:
    from .resumen_ia import publicar
    doc = publicar(a.salida, a.registro)
    _imprimir({"salida": str(Path(a.salida) / "resumen.json"),
               "modelos": [{"modelo": m["modelo_id"], "estado": m["estado"], "version": m["version"], "lectura": m["lectura"]} for m in doc["modelos"]]})
    return 0


def cmd_modo_demo(a) -> int:
    from . import registro as R
    if a.modelo == "anomalias":
        raise SystemExit("anomalias (M6) se mantiene en sombra: con evidencia sintética no se habilita modo demostración ni promoción operativa")
    try:
        reg = R.fijar_modo_demostracion(a.registro, a.modelo, a.activar, a.actor, a.motivo)
    except R.RegistroError as exc:
        _imprimir({"error": str(exc)})
        return 2
    _imprimir({"modelo": a.modelo, "modo_demostracion": reg.get("modo_demostracion")})
    return 0


def cmd_promover_demo(a) -> int:
    """Pasa a operativa una versión YA registrada, evaluada con datos sintéticos, solo con el modo demostración activo."""
    from . import registro as R
    if a.modelo == "anomalias":
        raise SystemExit("anomalias (M6) se mantiene en sombra: con evidencia sintética no se habilita modo demostración ni promoción operativa")
    reg = R.leer_registro(a.registro, a.modelo)
    if not R.modo_demostracion(reg):
        _imprimir({"error": "El modo demostración está apagado: actívalo con 'modo-demo --activar' (actor y motivo)"})
        return 2
    try:
        if a.artefacto:  # versión nueva: artefacto validado y de este modelo
            from .inferencia import ArtefactoInvalido, cargar_artefacto
            try:
                art = cargar_artefacto(a.artefacto, modelo_id=a.modelo)
            except ArtefactoInvalido as exc:
                raise R.RegistroError(str(exc)) from exc
        else:
            art = R._cargar_version(a.registro, a.modelo, a.version)
    except R.RegistroError as exc:
        _imprimir({"error": str(exc)})
        return 2
    previa = [x["documento"] for x in R.autorizaciones(a.registro, a.modelo, a.version, reg) if x.get("artefacto_huella") == art.huella]
    decision = {"artefacto_huella": art.huella, "estado_maximo": "operativo", "decision": "demostracion", "origen_datos": "sintetico",
                "aprobado_por": a.aprobado_por, "motivo": a.motivo,
                "decision_evaluacion": previa[0].get("decision") if previa else None,
                "advertencia": "Operativa solo como demostración: evaluada con datos sintéticos; no es una validación con datos empresariales."}
    try:
        reg = R.promover(a.registro, a.modelo, a.version, art, decision, {"operacion": "promover-demo", "actor": a.aprobado_por,
                                                                         "artefacto": str(a.artefacto) if a.artefacto else None},
                         "operativo", actor=a.aprobado_por, procedencia="promover-demo")
    except R.RegistroError as exc:
        _imprimir({"error": str(exc)})
        return 2
    _imprimir({"operativo": reg["operativo"], "sombra": reg["sombra"]})
    return 0


def cmd_autorizar(a) -> int:
    from . import registro as R
    decision = json.loads(Path(a.decision).read_text(encoding="utf-8"))
    reg = R.autorizar(a.registro, "compra_30d", a.version, decision, a.actor, a.procedencia)
    _imprimir({"version": a.version, "autorizaciones": [{k: x.get(k) for k in ("procedencia", "estado_maximo", "decision", "actor", "ts")}
                                                         for x in R.autorizaciones(a.registro, "compra_30d", a.version, reg)]})
    return 0


def cmd_verificar_protocolo(a) -> int:
    from .compra import _json, verificar_protocolo_heredado
    r = verificar_protocolo_heredado(a.ejecucion, a.config)
    if a.salida:
        _json(Path(a.salida), r)
    _imprimir(r)
    return 0 if r["coincide"] and r["artefacto"]["coincide_con_congelado"] else 2


def cmd_m11_entrenar(a) -> int:
    from .compra import cargar_config
    from .compra_m11 import CONFIG_M11, entrenar_m11
    config = cargar_config(a.config or CONFIG_M11)
    r = entrenar_m11(_datos(a, config), config, a.salida)
    s = r["seleccion"]
    _imprimir({"ejecucion": a.salida, "global": s["global"], "por_familia": s["por_familia"],
               "calibracion": {k: {"calibrar": v["calibrar"], "motivo": v["motivo"]} for k, v in s["calibracion"].items()},
               "validacion_top10": {k: round(v["precision_media_top10"], 4) for k, v in s["validacion_temporal"].items()
                                    if k in set(s["por_familia"].values()) | {s["control"]}},
               "equivalencia": r["congelacion"]["equivalencia_json_sklearn"]})
    return 0


def cmd_m11_evaluar(a) -> int:
    from .compra_m11 import evaluar_m11
    r = evaluar_m11(a.ejecucion)
    res = r["metricas"]["resultados"]
    _imprimir({"seleccionado": r["metricas"]["seleccionado"], "decision": r["decision"]["decision"], "cumple": r["decision"]["cumple"],
               "valores": r["decision"]["valores"],
               "top10_elegible": {k: [m["top10"]["aciertos"] for m in v["elegible"]["ranking"]["por_mes"]] for k, v in res.items()},
               "top10_atendible": {k: [m["top10"]["aciertos"] for m in v["atendible"]["ranking"]["por_mes"]] for k, v in res.items()}})
    return 0


def cmd_m12_entrenar(a) -> int:
    from .compra import cargar_config
    from .compra_m12 import CONFIG_M12, entrenar_m12
    config = cargar_config(a.config or CONFIG_M12)
    r = entrenar_m12(_datos(a, config), config, a.salida)
    d = r["desarrollo"]
    _imprimir({"ejecucion": a.salida, "artefacto": r["artefacto"]["version"],
               "desarrollo_top10": {k: f"{v['aciertos_top10']}/{v['denominador_top10']}" for k, v in d["agregado"].items()},
               "desarrollo_top20": {k: f"{v['aciertos_top20']}/{v['denominador_top20']}" for k, v in d["agregado"].items()},
               "diferencia_fusion_menos_recencia": d["diferencia_fusion_menos_recencia_top10"],
               "ic95": [d["ic95_bootstrap_clientes"].get("p2_5"), d["ic95_bootstrap_clientes"].get("p97_5")],
               "primer_corte_prospectivo": r["congelacion"]["fechas"]["primer_corte_prospectivo"]})
    return 0


def cmd_m12_evaluar(a) -> int:
    from .compra_m12 import evaluar_m12
    r = evaluar_m12(a.ejecucion)
    res = r["metricas"]["resultados"]
    _imprimir({"decision": r["decision"]["decision"], "cumple": r["decision"]["cumple"], "valores": r["decision"]["valores"],
               "comprobacion_top10_elegible": {k: [m["top10"]["aciertos"] for m in v["elegible"]["por_mes"]] for k, v in res.items()},
               "comprobacion_top10_atendible": {k: [m["top10"]["aciertos"] for m in v["atendible"]["por_mes"]] for k, v in res.items()}})
    return 0


def cmd_m13_entrenar(a) -> int:
    from .compra import cargar_config
    from .compra_m13 import CONFIG_M13, entrenar_m13
    config = cargar_config(a.config or CONFIG_M13)
    r = entrenar_m13(_datos(a, config), config, a.salida)
    d = r["desarrollo"]
    _imprimir({"ejecucion": a.salida, "agregado": d["agregado"],
               "S_menos_recencia_top10": d["S_menos_recencia_top10"],
               "ic95_S": [d["ic95_S_menos_recencia_top10"].get("p2_5"), d["ic95_S_menos_recencia_top10"].get("p97_5")],
               "P_menos_control_log_loss": d["P_menos_control_log_loss"],
               "ic95_P": [d["ic95_P_menos_control_log_loss"].get("p2_5"), d["ic95_P_menos_control_log_loss"].get("p97_5")],
               "equivalencia": r["congelacion"]["equivalencia"]})
    return 0


def cmd_m13_evaluar(a) -> int:
    from .compra_m13 import evaluar_m13
    r = evaluar_m13(a.ejecucion)
    res = r["metricas"]["resultados"]
    _imprimir({"decision": r["decision"]["candidatos"],
               "comprobacion_top10_elegible": {k: [m["top10"]["aciertos"] for m in v["elegible"]["por_mes"]] for k, v in res.items()},
               "comprobacion_top10_atendible": {k: [m["top10"]["aciertos"] for m in v["atendible"]["por_mes"]] for k, v in res.items()},
               "probabilidad": {k: {x: v["elegible"]["agregado"].get(x) for x in ("brier", "log_loss", "prob_media")}
                                for k, v in res.items() if "brier" in v["elegible"]["agregado"]}})
    return 0


def cmd_estado(a) -> int:
    from . import registro as R
    if a.modelo == "anomalias":  # M6 no se registra ni promociona: estado verificado de la ejecución
        from .anomalias_experimento import ProtocoloM6Error, evaluacion_publicada, verificar_congelacion
        if not a.ejecucion:
            raise SystemExit("anomalias: indica --ejecucion (M6 está en sombra y no tiene punteros de registro)")
        cong = verificar_congelacion(a.ejecucion)
        try:
            pub = evaluacion_publicada(a.ejecucion)
            dec = {u: {k: d[k] for k in ("decision", "sistema_conservado")} for u, d in pub["decision"]["decisiones"].items()}
        except ProtocoloM6Error as exc:
            dec = f"sin evaluación verificable: {exc}"
        _imprimir({"modelo": "anomalias", "estado": "sombra (sin promoción)", "congelacion": {k: cong[k] for k in ("artefacto_version", "artefacto_huella", "sello")},
                   "fecha_congelacion": (cong.get("volatiles") or {}).get("fecha_congelacion"), "decisiones": dec})
        return 0
    _imprimir(R.leer_registro(a.registro, a.modelo))
    return 0


def resumen_comparacion(metricas: dict, decision: dict) -> dict:
    """Resumen legible de la comprobación histórica (ya publicada y verificada) para la vista interna."""
    res = metricas["resultados"]
    c, r, k = res["candidato"], res["mayor_recencia"], res.get("constante")
    pc = c["probabilidad"]
    prev = (metricas.get("contexto_todos_los_candidatos") or {}).get("m2_congelado")
    return {"bloque": "comprobación histórica " + " y ".join(metricas["cortes"]), "alcance": metricas["alcance"],
            "casos": res["conteos"]["aprendibles_maduras"], "eventos": res["conteos"]["eventos"],
            "modelo": {"aciertos_top10_por_mes": [m["top10"]["aciertos"] for m in c["por_mes"]],
                       "precision_media_top10": c["agregado"]["precision_media_top10"], "aciertos_top20": c["agregado"]["aciertos_top20"],
                       "sensibilidad_top10": c["agregado"]["sensibilidad_agregada_top10"], "brier": pc["brier"],
                       "probabilidad_media": pc["distribucion"]["media"]},
            "mayor_recencia": {"aciertos_top10_por_mes": [m["top10"]["aciertos"] for m in r["por_mes"]],
                               "precision_media_top10": r["agregado"]["precision_media_top10"], "aciertos_top20": r["agregado"]["aciertos_top20"],
                               "sensibilidad_top10": r["agregado"]["sensibilidad_agregada_top10"]},
            "constante": {"brier": k["probabilidad"]["brier"]} if k else None,
            "tasa_observada": res["conteos"]["eventos"] / res["conteos"]["aprendibles_maduras"],
            "ic95_diferencia_top10": decision["valores"]["ic95_diferencia"],
            "modelo_anterior": {"version": prev["version"], "precision_media_top10": prev["precision_media_top10"]} if prev else None}


def _puntuar_inactividad(a) -> int:
    from . import registro as R
    from .compra import cargar_datos_config
    from .inactividad import puntuar_sombra
    from .inactividad_experimento import cargar_config
    from .inferencia import cargar_artefacto
    decision = None
    if a.ejecucion:
        cfg_ej = json.loads((Path(a.ejecucion) / "config.json").read_text(encoding="utf-8"))
        pub = _modulo_inactividad(cfg_ej).evaluacion_publicada(a.ejecucion)  # verifica congelación y evaluación antes de usar el artefacto
        art = cargar_artefacto(Path(a.ejecucion) / "artefacto.json", modelo_id="inactividad_60d")
        d = pub["decision"]
        decision = {"decision": d["decision"], "estado_maximo": d["estado_maximo"], "ejecucion": str(a.ejecucion), "artefacto_huella": d.get("artefacto_huella"),
                    "version_protocolo": d["version_protocolo"], "sello_evaluacion": pub["evaluacion"]["sello"]}
        if a.con_resumen:
            metricas = json.loads((Path(a.ejecucion) / "metricas_comprobacion_historica.json").read_text(encoding="utf-8"))
            decision["resumen"] = resumen_comparacion(metricas, d)
        estado = f"experimental en sombra · decisión {d['decision']} (datos {d['origen_datos']})"
    elif a.artefacto:
        art = cargar_artefacto(a.artefacto, modelo_id="inactividad_60d")
        estado = "experimental en sombra · artefacto sin decisión asociada"
    else:
        art, _ = R.artefacto_registrado(a.registro, "inactividad_60d", a.estado)
        estado = f"registro · {a.estado}"
    config = cargar_config(a.config)
    datos = cargar_datos_config(a.datos, config, aceptar_parcial=a.aceptar_parcial, observado_hasta=a.observado_hasta)
    r = puntuar_sombra(art, datos, date.fromisoformat(a.corte), a.salida, estado_experimento=estado, decision=decision,
                       simulacion_historica=a.simulacion_historica)
    m = r["manifiesto"]
    _imprimir({"salida": a.salida, "modelo": m["modelo"]["version"], "estado_experimento": m["estado_experimento"], "conteos": m["conteos"],
               "estimados": sum(f["estado"] == "estimado" for f in r["filas"]), "sello": m["sello"]})
    return 0


def cmd_puntuar(a) -> int:
    from . import registro as R
    from .compra import puntuar
    from .inferencia import cargar_artefacto
    if a.modelo == "inactividad_60d":
        return _puntuar_inactividad(a)
    if a.modelo == "proxima_compra":
        return _puntuar_proxima(a)
    if a.modelo == "venta_cruzada":
        return _puntuar_vc(a)
    if a.modelo == "demanda":
        return _puntuar_demanda(a)
    if a.modelo == "anomalias":
        return _puntuar_anomalias(a)
    if a.ejecucion:
        raise SystemExit("--ejecucion solo se usa con --modelo inactividad_60d")
    if a.artefacto:
        art = cargar_artefacto(a.artefacto, modelo_id="compra_30d")
    else:
        art, _ = R.artefacto_registrado(a.registro, "compra_30d", a.estado)
    config = _config(a)
    r = puntuar(art, _datos(a, config), date.fromisoformat(a.corte), a.salida, simulacion_historica=a.simulacion_historica,
                etiqueta=a.estado or "artefacto")
    _imprimir(r["resumen"])
    return 0


def cmd_comparar(a) -> int:
    from .compra import comparar
    datos = _datos(a, _config(a)) if a.datos else None
    _imprimir(comparar(a.operativo, a.sombra, a.salida, datos, a.k, reconciliar=a.reconciliar, nueva_seleccion=a.nueva_seleccion))
    return 0


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m modelos.cli", description="Entrenar, evaluar, puntuar y promover modelos de JACOMIND")
    sub = p.add_subparsers(dest="cmd", required=True)

    def con_datos(sp, requerido=True):
        sp.add_argument("--datos", required=requerido, help="salida A01 (con manifiesto.json) o su carpeta publicado/")
        sp.add_argument("--config", default=None, help="configuración del modelo (por defecto modelos/config/compra_30d.json)")
        sp.add_argument("--aceptar-parcial", action="store_true", help="usar un lote pendiente de revisión con sus filas aceptadas")
        sp.add_argument("--observado-hasta", default=None, help="sobrescribe la cobertura declarada (AAAA-MM-DD)")

    s = sub.add_parser("preparar", help="A01: normaliza y valida el paquete")
    s.add_argument("--datos", required=True); s.add_argument("--salida", required=True); s.add_argument("--config-a01", default=None)
    s.set_defaults(f=cmd_preparar)
    s = sub.add_parser("reproducir-referencia", help="reproduce el modelo original y sus controles")
    con_datos(s); s.add_argument("--salida", default=None); s.set_defaults(f=cmd_reproducir)
    s = sub.add_parser("inicializar-referencia", help="registra el modelo original como versión operativa")
    con_datos(s); s.add_argument("--registro", default=None); s.add_argument("--version", default="v1"); s.set_defaults(f=cmd_inicializar)
    s = sub.add_parser("entrenar", help="ajusta, selecciona en validación y congela el candidato")
    s.add_argument("--modelo", choices=MODELOS, default="compra_30d"); con_datos(s); s.add_argument("--salida", required=True)
    s.add_argument("--reglas", default=None, help="venta_cruzada: tabla de compatibilidad")
    s.set_defaults(f=cmd_entrenar)
    s = sub.add_parser("preparar-modelo", help="venta_cruzada: control A07, conteos, universo y estadísticas por corte")
    s.add_argument("--modelo", choices=["venta_cruzada", "demanda", "anomalias"], default="venta_cruzada"); con_datos(s); s.add_argument("--salida", required=True)
    s.add_argument("--reglas", default=None, help="tabla de compatibilidad (por defecto modelos/config/compatibilidad_productos.json)")
    s.set_defaults(f=cmd_preparar_modelo)
    s = sub.add_parser("ajustar-origen", help="demanda: reestima el procedimiento congelado para un origen nuevo y escribe su artefacto")
    con_datos(s); s.add_argument("--ejecucion", required=True); s.add_argument("--origen", required=True, help="AAAA-MM: último mes completo")
    s.add_argument("--salida", required=True); s.set_defaults(f=cmd_ajustar_origen)
    s = sub.add_parser("incorporar-observaciones", help="demanda: evalúa una emisión publicada con meses ya completos, sin modificarla")
    con_datos(s); s.add_argument("--publicacion", required=True); s.add_argument("--salida", required=True); s.set_defaults(f=cmd_incorporar)
    s = sub.add_parser("evaluar", help="mide un bloque con el artefacto congelado, sin reajustar")
    s.add_argument("--ejecucion", required=True)
    s.add_argument("--bloque", default="comprobacion_historica", choices=["validacion", "comprobacion_historica"])
    s.add_argument("--m2", default=None, help="inactividad_60d M2.1: ejecución M2 congelada que se mide solo como contexto")
    s.add_argument("--m3", default=None, help="proxima_compra M3.1: ejecución M3 congelada que se mide solo como contexto")
    s.add_argument("--m31", default=None, help="proxima_compra M3.2: ejecución M3.1 congelada que se mide solo como contexto")
    s.add_argument("--m4", default=None, help="venta_cruzada M4.1: ejecución M4 congelada que se mide solo como contexto")
    s.add_argument("--m6", default=None, help="anomalias M6.1: ejecución M6 congelada que se mide solo como contexto")
    con_datos(s, requerido=False)  # anomalias: la comprobación reconstruye los casos desde la misma revisión A01 congelada
    s.set_defaults(f=cmd_evaluar)
    s = sub.add_parser("promover", help="registra la ejecución como sombra u operativa si su decisión lo autoriza")
    s.add_argument("--ejecucion", required=True); s.add_argument("--registro", default=None); s.add_argument("--version", required=True)
    s.add_argument("--estado", choices=["sombra", "operativo"], default="sombra"); s.set_defaults(f=cmd_promover)
    s = sub.add_parser("revertir", help="restituye la versión anterior de un puntero")
    s.add_argument("--registro", default=None); s.add_argument("--estado", choices=["sombra", "operativo"], default="operativo")
    s.add_argument("--a", default=None, help="versión explícita"); s.set_defaults(f=cmd_revertir)
    s = sub.add_parser("resumen-ia", help="resumen de resultados de los modelos para la aplicación (GET /api/ia)")
    s.add_argument("--registro", default=None); s.add_argument("--salida", default=str(Path(__file__).resolve().parents[1] / "salida" / "ia"))
    s.set_defaults(f=cmd_resumen_ia)
    s = sub.add_parser("modo-demo", help="activa o apaga el modo demostración del registro (permite operativo con datos sintéticos)")
    s.add_argument("--registro", default=None); s.add_argument("--modelo", choices=MODELOS, default="compra_30d")
    g = s.add_mutually_exclusive_group(required=True); g.add_argument("--activar", action="store_true"); g.add_argument("--apagar", action="store_true")
    s.add_argument("--actor", required=True); s.add_argument("--motivo", required=True); s.set_defaults(f=cmd_modo_demo)
    s = sub.add_parser("promover-demo", help="modo demostración: pasa a operativa una versión ya registrada evaluada con datos sintéticos")
    s.add_argument("--registro", default=None); s.add_argument("--modelo", choices=MODELOS, default="compra_30d")
    s.add_argument("--version", required=True); s.add_argument("--aprobado-por", required=True); s.add_argument("--motivo", required=True)
    s.add_argument("--artefacto", default=None, help="artefacto JSON para registrar una versión nueva (si no, la versión debe existir)")
    s.set_defaults(f=cmd_promover_demo)
    s = sub.add_parser("m11-entrenar", help="M1.1: congela el protocolo, valida en el tiempo, calibra y exporta (sin leer la comprobación)")
    con_datos(s); s.add_argument("--salida", required=True); s.set_defaults(f=cmd_m11_entrenar)
    s = sub.add_parser("m11-evaluar", help="M1.1: comprobación histórica exploratoria sin reajustar")
    s.add_argument("--ejecucion", required=True); s.set_defaults(f=cmd_m11_evaluar)
    s = sub.add_parser("m12-entrenar", help="M1.2: orden por fusión recencia+modelo; validación temporal y congelación")
    con_datos(s); s.add_argument("--salida", required=True); s.set_defaults(f=cmd_m12_entrenar)
    s = sub.add_parser("m12-evaluar", help="M1.2: comprobación histórica exploratoria y decisión predeclarada")
    s.add_argument("--ejecucion", required=True); s.set_defaults(f=cmd_m12_evaluar)
    s = sub.add_parser("m13-entrenar", help="M1.3: supervivencia (S) y ponderación + nivel (P); validación temporal y congelación")
    con_datos(s); s.add_argument("--salida", required=True); s.set_defaults(f=cmd_m13_entrenar)
    s = sub.add_parser("m13-evaluar", help="M1.3: comprobación histórica exploratoria y decisiones predeclaradas")
    s.add_argument("--ejecucion", required=True); s.set_defaults(f=cmd_m13_evaluar)
    s = sub.add_parser("estado", help="muestra el registro (anomalias: estado verificado de --ejecucion)"); s.add_argument("--registro", default=None)
    s.add_argument("--modelo", choices=MODELOS, default="compra_30d"); s.add_argument("--ejecucion", default=None); s.set_defaults(f=cmd_estado)
    s = sub.add_parser("puntuar", help="inferencia de un corte desde el artefacto JSON")
    con_datos(s); s.add_argument("--corte", required=True); s.add_argument("--salida", required=True)
    s.add_argument("--artefacto", default=None); s.add_argument("--registro", default=None)
    s.add_argument("--ejecucion", default=None, help="inactividad_60d: ejecución congelada y evaluada cuyo artefacto se puntúa en sombra")
    s.add_argument("--con-resumen", action="store_true", help="inactividad_60d: incluye en la sombra el resumen de la comprobación histórica para la vista")
    s.add_argument("--estado", choices=["sombra", "operativo"], default=None)
    s.add_argument("--modelo", choices=MODELOS, default="compra_30d")
    s.add_argument("--simulacion-historica", action="store_true", help="permite cortes anteriores a la disponibilidad del artefacto")
    s.set_defaults(f=cmd_puntuar)
    s = sub.add_parser("comparar", help="operativo frente a sombra y recencia a igual cupo")
    s.add_argument("--operativo", required=True); s.add_argument("--sombra", required=True); s.add_argument("--salida", required=True)
    s.add_argument("--k", type=int, default=10); con_datos(s, requerido=False)
    s.add_argument("--reconciliar", action="store_true", help="comparar la intersección si cohortes o revisiones de origen difieren")
    s.add_argument("--nueva-seleccion", action="store_true", help="añadir otra selección del mismo corte sin reasignar contactos")
    s.set_defaults(f=cmd_comparar)
    s = sub.add_parser("autorizar", help="registra una autorización nueva de una versión sin mover punteros")
    s.add_argument("--registro", default=None); s.add_argument("--version", required=True); s.add_argument("--decision", required=True)
    s.add_argument("--actor", required=True); s.add_argument("--procedencia", required=True); s.set_defaults(f=cmd_autorizar)
    s = sub.add_parser("verificar-protocolo", help="compara la configuración de una ejecución (p. ej. heredada) con otra (verificación posterior)")
    s.add_argument("--ejecucion", required=True); s.add_argument("--config", default=str(Path(__file__).parent / "config" / "compra_30d.json"))
    s.add_argument("--salida", default=None); s.set_defaults(f=cmd_verificar_protocolo)
    a = p.parse_args(argv)
    if a.cmd == "puntuar" and not a.artefacto and not a.estado and not a.ejecucion:
        p.error("puntuar necesita --artefacto, --ejecucion o --registro con --estado")
    from .anomalias_experimento import ProtocoloM6Error
    from .compra import PilotoError, ProtocoloError
    from .datos import CoberturaInsuficiente, LoteNoAceptado
    from .ejecucion import EjecucionError
    from .inferencia import ArtefactoInvalido
    from .registro import RegistroError
    try:
        return a.f(a)
    except CoberturaInsuficiente as exc:
        print(f"COBERTURA INSUFICIENTE: {exc}", file=sys.stderr)
        return 2
    except LoteNoAceptado as exc:
        print(f"LOTE NO ACEPTADO: {exc}", file=sys.stderr)
        return 2
    except (ProtocoloError, PilotoError, RegistroError, EjecucionError, ArtefactoInvalido, ProtocoloM6Error) as exc:
        print(f"RECHAZADO: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - la CLI informa y devuelve código ≠ 0
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
