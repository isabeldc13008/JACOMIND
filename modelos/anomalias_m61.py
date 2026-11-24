"""M6.1 · Operaciones atípicas con política de catálogo, dirección por variable y cupo como máximo con evidencia.
Solo biblioteca estándar (puntuación, API y cierre); el ajuste vive en ``modelos/anomalias_m61_experimento.py``.

Cambios frente a M6 (``m61-protocolo-v1``):

* **Catálogo** (``productos.csv`` de la misma revisión A01): precio de venta fuera de [0,90; 1,00] × precio_lista, costo de
  compra fuera de [0,90; 1,10] × costo_referencia y venta por debajo del costo reciente de compra. Son convenciones de
  demostración declaradas, no políticas aprobadas. Una operación en otra moneda que la de lista no se compara.
* **Dirección**: la cantidad solo cuenta por ALTA (``z_log_cantidad_alta = max(0, z)``); precio y costo en ambas.
* **Evidencia mínima**: solo se alerta una operación con evidencia (reglas anteriores, o rareza >= umbral de
  entrenamiento para el candidato). El cupo es un MÁXIMO: sin evidencia no hay alerta aunque quede cupo.
* Una operación sin historia suficiente no tiene puntaje ni prioridad, pero puede quedar SEÑALADA por el catálogo
  (fuera del cupo, visible como exceso pendiente).
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from . import anomalias as A

FORMATO = "jacomind.anomalias_m61.v1"
VARIABLES = ("z_log_valor_unitario", "z_log_cantidad_alta")
POLITICA = "cupo_maximo_con_evidencia"


def es_m61(config: Mapping) -> bool:
    return str(config.get("version_protocolo", "")).startswith("m61")


def catalogo(datos) -> dict[str, dict]:
    return {str(p): {"moneda_lista": str(v.get("moneda_lista")), "precio_lista": float(v["precio_lista"]), "costo_referencia": float(v["costo_referencia"])}
            for p, v in datos.productos.items()}


def contexto(op: Mapping, historial: A.Historial, config: Mapping) -> dict:
    c = A.contexto(op, historial, config)
    if c["estado"] == "puntuada":
        c = dict(c, variables=dict(c["variables"], z_log_cantidad_alta=max(0.0, c["variables"]["z_log_cantidad"])))
    return c


def puntaje_referencia(v: Mapping[str, float]) -> float:
    return max(abs(v["z_log_valor_unitario"]), v["z_log_cantidad_alta"])


def costo_reciente(op: Mapping, historial: A.Historial, config: Mapping) -> float | None:
    """exp(mediana log) de los costos de compra ANTERIORES del mismo producto y moneda (solo para ventas)."""
    if op["tipo_operacion"] != "venta":
        return None
    ant = historial.antecedentes(("compra", op["producto_id"], op["moneda"], op["unidad"]), op["fecha"])
    if len(ant) < int(config["catalogo"]["venta_bajo_costo"]["min_compras_previas"]):
        return None
    return math.exp(median(a[1][1] for a in ant))


def _f(x: float, d: int = 2) -> str:
    return A._fmt(x, d)


def evidencias(op: Mapping, c: Mapping, config: Mapping, cat: Mapping[str, dict], historial: A.Historial) -> list[dict]:
    """Evidencia declarada (id + texto legible). Describe desviaciones observadas, no causas."""
    cc, ev = config["catalogo"], []
    tol = float(cc["tolerancia_relativa"])
    p = cat.get(op["producto_id"])
    u, val = op["tipo_operacion"], op["valor_unitario"]
    if p and p["moneda_lista"] == op["moneda"]:
        ref, (lo, hi) = (p["precio_lista"], cc["venta_precio_sobre_lista"]) if u == "venta" else (p["costo_referencia"], cc["compra_costo_sobre_referencia"])
        r = val / ref
        if r < lo * (1 - tol) or r > hi * (1 + tol):
            ev.append({"id": "fuera_de_lista" if u == "venta" else "costo_fuera_de_referencia",
                       "texto": (f"Precio {_f(val)} {op['moneda']} = {_f(r * 100, 1)} % del precio de lista {_f(ref)} (política de demostración: {_f(lo * 100, 0)}–{_f(hi * 100, 0)} %)"
                                 if u == "venta" else
                                 f"Costo {_f(val)} {op['moneda']} = {_f(r * 100, 1)} % del costo de referencia {_f(ref)} (rango de demostración: {_f(lo * 100, 0)}–{_f(hi * 100, 0)} %)")})
    cr = costo_reciente(op, historial, config)
    if cr is not None and val < cr * (1 - tol):
        ev.append({"id": "venta_bajo_costo", "texto": f"Precio de venta {_f(val)} {op['moneda']} por debajo del costo reciente de compra {_f(cr)} (mediana de compras anteriores)"})
    if c["estado"] == "puntuada":
        r, v = config["referencia"]["reglas"], c["variables"]
        etiqueta = config["universos"][u]["etiqueta_valor"]
        if abs(v["z_log_valor_unitario"]) >= r["z_regla"] or not r["razon_valor_min"] <= c["razon_valor_unitario"] <= r["razon_valor_max"]:
            ev.append({"id": "valor_unitario_fuera_de_contexto",
                       "texto": f"{etiqueta.capitalize()} ×{_f(c['razon_valor_unitario'])} frente a la referencia {_f(c['referencia_valor_unitario'])} de {c['soporte']} antecedentes"})
        if v["z_log_cantidad_alta"] >= r["z_regla"] or c["razon_cantidad"] > r["razon_cantidad_max"]:
            ev.append({"id": "cantidad_alta_fuera_de_contexto",
                       "texto": f"Cantidad {_f(op['cantidad'])} = ×{_f(c['razon_cantidad'])} la referencia {_f(c['referencia_cantidad'])} de {c['soporte']} antecedentes"})
    return ev


def validar_artefacto_m61(d: dict) -> list[str]:
    e = A.validar_artefacto_anomalias(d, formato=FORMATO, politicas=(POLITICA,), variables=VARIABLES)
    for u in A.UNIVERSOS:
        s = (d.get("universos") or {}).get(u) or {}
        if s.get("metodo") == "isolation_forest" and not (A._finito(s.get("umbral_evidencia_rareza")) and 0 < s["umbral_evidencia_rareza"] <= 1):
            e.append(f"{u}: umbral_evidencia_rareza inválido")
    if not isinstance(d.get("catalogo"), dict) or not isinstance(d.get("direcciones"), dict):
        e.append("faltan la política de catálogo o las direcciones")
    return e


class ArtefactoM61(A.ArtefactoAnomalias):
    def config_contexto(self) -> dict:
        return dict(super().config_contexto(), catalogo=self.datos["catalogo"], direcciones=self.datos["direcciones"])


def priorizar(filas: list[dict], politica: Mapping) -> None:
    """Prioridad 1..n por (universo, mes) con evidencia primero; alerta = con evidencia y prioridad <= cupo."""
    por: dict[tuple, list] = {}
    for f in filas:
        f["prioridad"], f["alerta"], f["cupo_periodo"] = None, False, None
        if f["puntaje"] is not None:
            por.setdefault((f["tipo_operacion"], f["periodo"]), []).append(f)
    for fs in por.values():
        fs.sort(key=lambda f: (not f["senalada_por_reglas"], -f["puntaje"], f["fecha"], f["operacion_id"]))
        k = A.cupo(len(fs), politica)
        for i, f in enumerate(fs, 1):
            f["prioridad"], f["alerta"], f["cupo_periodo"] = i, bool(f["senalada_por_reglas"]) and i <= k, k
    for f in filas:
        if f["cupo_periodo"] is None:
            f["cupo_periodo"] = A.cupo(len(por.get((f["tipo_operacion"], f["periodo"]), [])), politica)


def fila_operacion(op: Mapping, c: Mapping, art: ArtefactoM61, config: Mapping, info: Mapping, metodos: Mapping[str, str],
                   cat: Mapping[str, dict], historial: A.Historial) -> dict:
    f = A.fila_operacion(op, c, art, config, info, metodos)
    u = op["tipo_operacion"]
    ref = puntaje_referencia(c["variables"]) if c["estado"] == "puntuada" else None
    cand = f["puntaje_candidato"]
    ev = evidencias(op, c, config, cat, historial)
    if metodos[u] == "isolation_forest" and cand is not None and cand >= art.datos["universos"][u]["umbral_evidencia_rareza"]:
        ev.append({"id": "rareza_candidato", "texto": f"Rareza {_f(cand, 3)} por encima del umbral de evidencia {_f(art.datos['universos'][u]['umbral_evidencia_rareza'], 3)} (cuantil de entrenamiento)"})
    puntaje = cand if metodos[u] == "isolation_forest" else ref
    if c["estado"] == "puntuada":
        texto, inus = [e["texto"] for e in ev], sorted({"valor_unitario" if e["id"] in ("fuera_de_lista", "costo_fuera_de_referencia", "venta_bajo_costo", "valor_unitario_fuera_de_contexto")
                                                         else "cantidad" if e["id"] == "cantidad_alta_fuera_de_contexto" else "combinacion" for e in ev})
        if not texto:
            texto = [f"Sin evidencia de anomalía: precio o costo dentro del catálogo y del contexto y cantidad no alta ({c['soporte']} antecedentes del mismo producto y moneda)"]
    else:
        texto, inus = [c["motivo"]] + [e["texto"] for e in ev], sorted({"valor_unitario" for e in ev})
    f.update(puntaje=None if puntaje is None else round(puntaje, 12), puntaje_referencia=None if ref is None else round(ref, 12),
             senalada_por_reglas=bool(ev), evidencias=[e["id"] for e in ev], motivos=texto, variables_inusuales=inus)
    return f


def puntuar_sombra(art: ArtefactoM61, datos, compras: list[dict], config: Mapping, corte: date, salida: str | Path, *,
                   estado_experimento: str, metodos: Mapping[str, str], decision: Mapping | None = None) -> dict:
    """Como ``anomalias.puntuar_sombra`` con evidencia, catálogo y cupo máximo. No entrena ni selecciona."""
    import time
    from contratos.validar import validar_publicacion_sombra
    from .datos import verificar_cobertura_corte
    from .ejecucion import json_bytes, publicar_lote
    t0 = time.perf_counter()
    verificar_cobertura_corte(corte, datos.cobertura)
    cfg = dict(config, **art.config_contexto())
    ops, excl = A.operaciones(datos.ventas, compras, datos.tasas, cfg)
    ops = [o for o in ops if o["fecha"] <= corte]
    hist = A.Historial(ops, cfg["contexto"]["ventana_antecedentes"])
    cat = catalogo(datos)
    meses = int(config["publicacion"]["meses"])
    t = corte.year * 12 + corte.month - 1 - (meses - 1)
    desde = date(t // 12, t % 12 + 1, 1)
    info = {"revision": datos.revision, "corte": corte.isoformat()}
    filas = [fila_operacion(o, contexto(o, hist, cfg), art, cfg, info, metodos, cat, hist) for o in ops if o["fecha"] >= desde]
    priorizar(filas, art.datos["politica_alertas"])
    filas.sort(key=lambda f: (f["tipo_operacion"], f["periodo"], f["prioridad"] if f["prioridad"] is not None else 10**9, f["operacion_id"]))
    cob = A.cobertura_filas(filas, excl, desde, corte, cfg)
    muestra = A.muestra_revision(filas, config, corte.isoformat())
    mon = A.monitoreo(filas, config)
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": A.MODELO_ID, "corte": corte.isoformat(), "desde": desde.isoformat(),
           "estado_experimento": estado_experimento, "operativa": False, "advertencia": A.NOTA, "version_protocolo": config["version_protocolo"],
           "modelo": {"version": art.version, "artefacto_huella": art.huella, "metodos_publicados": dict(metodos),
                      "candidato_por_universo": {u: art.datos["universos"][u]["metodo"] for u in A.UNIVERSOS},
                      "decision": dict(decision) if decision else None},
           "politica_alertas": art.datos["politica_alertas"], "catalogo": art.datos["catalogo"],
           "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
           "cobertura": {"corte": corte.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
           "cobertura_por_universo": {"venta": {"estado": "declarada", "hasta": datos.observado_hasta.isoformat()},
                                      "compra": {"estado": "no_declarada", "motivo": config["cobertura"]["compra"]["motivo"]}},
           "emision": {"tipo": "reconstruccion_historica" if all(f["tipo_emision"] == "reconstruccion_historica" for f in filas) else "mixta",
                       "nota": "Operaciones anteriores a la congelación del artefacto: reconstrucción histórica, no emisión prospectiva."},
           "conteos": {u: sum(1 for f in filas if f["tipo_operacion"] == u) for u in A.UNIVERSOS}, "monitoreo": mon,
           "tablas": {"anomalias_operaciones": {"filas": len(filas)}, "cobertura_anomalias": {"filas": len(cob)}}}
    errores = validar_publicacion_sombra(man, {"anomalias_operaciones": filas, "cobertura_anomalias": cob, "muestra_revision": muestra})
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato (no se publica): " + "; ".join(errores[:5]))
    publicar_lote(salida, {"anomalias_operaciones.json": json_bytes(filas), "cobertura_anomalias.json": json_bytes(cob),
                           "muestra_revision.json": json_bytes(muestra)}, "manifiesto.json", man,
                  volatiles={"duracion_puntuacion_s": round(time.perf_counter() - t0, 3)})
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas, "cobertura": cob, "muestra": muestra}
