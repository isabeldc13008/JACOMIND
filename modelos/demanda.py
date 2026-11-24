"""M5 · Pronóstico de demanda (``demanda``): series mensuales, conciliación, referencias, inferencia desde estados y
publicación en sombra. Solo biblioteca estándar: el ajuste (statsmodels) vive en ``modelos/demanda_experimento.py``.

Calendario mensual continuo por serie, desde el inicio DECLARADO de cobertura de su fuente (nunca desde la primera venta):

* ``completo``: todo el mes dentro de la cobertura; sin operaciones vale 0.
* ``incompleto``: mes parcialmente cubierto, o con operaciones sin conversión a COP → nulo con motivo.
* ``no_observable``: anterior a la disponibilidad del producto (proxy: primera venta observada) → nulo, no cero.
* ``sin_cobertura``: fuente sin cobertura declarada (compras a proveedores) → nulo.

Horizontes en meses calendario: el objetivo de origen O a h meses es O + h (mes), sin múltiplos de 30 días.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from .inferencia import _finito, huella_artefacto

MODELO_ID = "demanda"
HORIZONTES = (1, 2, 3)
FORMATO = "jacomind.demanda_origen.v1"
FAMILIAS = ("Continuidad", "Servicios", "Software", "Soporte")
METODOS = ("ultimo", "media_movil_3", "ses", "holt_amortiguado")
REFERENCIAS = ("ultimo", "media_movil_3")


# Meses -----------------------------------------------------------------------------------------------------------
def periodo(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def sumar_meses(p: str, n: int) -> str:
    y, m = int(p[:4]), int(p[5:7])
    t = y * 12 + (m - 1) + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def meses(desde: str, hasta: str) -> list[str]:
    out, p = [], desde
    while p <= hasta:
        out.append(p)
        p = sumar_meses(p, 1)
    return out


def fin_mes(p: str) -> date:
    return date.fromisoformat(sumar_meses(p, 1) + "-01") - timedelta(days=1)


# Series ----------------------------------------------------------------------------------------------------------
def _importe(v, tasas) -> Decimal | None:
    from pipeline.operaciones import MissingRateError, calcular_importe
    try:
        return Decimal(str(round(float(calcular_importe(v, tasas)), 2)))  # convención A02: redondeo por operación
    except MissingRateError:
        return None


def construir_series(datos, config: dict) -> dict[str, dict]:
    """Series ``ventas_cop:<familia>``, ``ventas_unidades:<producto>`` y ``compras_proveedores_cop:<familia>`` con calendario."""
    cob = config["cobertura_fuentes"]["ventas"]
    desde = date.fromisoformat(cob["desde"])
    hasta = datos.observado_hasta
    if hasta is None:
        raise ValueError("Sin cobertura declarada de ventas: no se construyen series")
    ultimo = periodo(hasta) if hasta == fin_mes(periodo(hasta)) else sumar_meses(periodo(hasta), -1)
    cal = meses(periodo(desde), periodo(hasta))
    fam = {str(p): str(v.get("familia_prueba", "DESCONOCIDA")) for p, v in datos.productos.items()}
    acum: dict[tuple, list] = {}
    primera: dict[str, date] = {}
    sin_tasa: dict[tuple, int] = {}
    for v in datos.ventas:
        if v.get("estado", "Confirmada") != "Confirmada" or not desde <= v["fecha"] <= hasta:
            continue
        pid, per = str(v["producto_id"]), periodo(v["fecha"])
        primera[pid] = min(primera.get(pid, v["fecha"]), v["fecha"])
        imp = _importe(v, datos.tasas)
        if imp is None:
            sin_tasa[(fam.get(pid), per)] = sin_tasa.get((fam.get(pid), per), 0) + 1
        else:
            a = acum.setdefault(("ventas_cop", fam.get(pid), per), [Decimal("0"), 0])
            a[0] += imp; a[1] += 1
        u = acum.setdefault(("ventas_unidades", pid, per), [Decimal("0"), 0])
        u[0] += Decimal(str(v["cantidad"])); u[1] += 1

    def estado_mes(per: str) -> tuple[str, str | None]:
        if per > ultimo:
            return "incompleto", f"Mes cubierto solo hasta {hasta.isoformat()}"
        if date.fromisoformat(per + "-01") < desde:
            return "incompleto", "Anterior al inicio de la cobertura declarada"
        return "completo", None

    series: dict[str, dict] = {}
    for f in config["series"]["ventas_cop"]["familias"]:
        filas = []
        for per in cal:
            est, motivo = estado_mes(per)
            a = acum.get(("ventas_cop", f, per), [Decimal("0"), 0])
            if est == "completo" and sin_tasa.get((f, per)):
                est, motivo = "incompleto", f"{sin_tasa[(f, per)]} operaciones sin TRM de su fecha: importe no reconstruible"
            filas.append({"periodo": per, "estado": est, "valor": float(a[0]) if est == "completo" else None, "operaciones": a[1], "motivo": motivo})
        series[f"ventas_cop:{f}"] = {"serie_id": f"ventas_cop:{f}", "fuente": "ventas", "medida": "ingreso por ventas confirmadas", "unidad": "COP",
                                     "familia": f, "producto_id": None, "calendario": filas}
    for pid in sorted(datos.productos):
        disp = primera.get(pid)
        filas = []
        for per in cal:
            est, motivo = estado_mes(per)
            if disp is None or per < periodo(disp):
                est, motivo = "no_observable", "Anterior a la disponibilidad del producto (proxy: primera venta observada)"
            a = acum.get(("ventas_unidades", pid, per), [Decimal("0"), 0])
            filas.append({"periodo": per, "estado": est, "valor": float(a[0]) if est == "completo" else None, "operaciones": a[1], "motivo": motivo})
        series[f"ventas_unidades:{pid}"] = {"serie_id": f"ventas_unidades:{pid}", "fuente": "ventas", "medida": "cantidad vendida",
                                            "unidad": config["series"]["ventas_unidades"]["unidad"], "familia": fam.get(pid), "producto_id": pid,
                                            "disponible_desde": disp.isoformat() if disp else None, "calendario": filas}
    for f in config["series"]["ventas_cop"]["familias"]:
        series[f"compras_proveedores_cop:{f}"] = {
            "serie_id": f"compras_proveedores_cop:{f}", "fuente": "compras_proveedores", "medida": "compras a proveedores", "unidad": "COP",
            "familia": f, "producto_id": None,
            "calendario": [{"periodo": per, "estado": "sin_cobertura", "valor": None, "operaciones": None,
                            "motivo": config["cobertura_fuentes"]["compras_proveedores"]["motivo"]} for per in cal]}
    return series


def conciliar(datos, series: Mapping[str, dict], config: dict) -> list[dict]:
    """Por mes y familia: serie M5 frente a A02 (``_summarize``). Diferencia fuera de tolerancia = error de conciliación."""
    from pipeline.operaciones import _summarize
    resumen = _summarize(datos.ventas, datos.productos, datos.tasas, datos.observado_hasta)
    a02: dict[tuple, Decimal] = {}
    ops: dict[tuple, int] = {}
    for (per, f, _mon, _prv), v in resumen.aggregates.items():
        a02[(per, f)] = a02.get((per, f), Decimal("0")) + v
    for r in resumen.rows:
        if r["status"] == "Confirmada":
            k = (r["fecha"].strftime("%Y-%m"), r["family"])
            ops[k] = ops.get(k, 0) + 1
    tol = config["conciliacion"]["tolerancia_cop_por_operacion"]
    filas = []
    for sid, s in series.items():
        if not sid.startswith("ventas_cop:"):
            continue
        for m in s["calendario"]:
            if m["estado"] != "completo":
                continue
            ref = float(a02.get((m["periodo"], s["familia"]), Decimal("0")))
            dif = round(m["valor"] - ref, 2)
            lim = tol * max(1, ops.get((m["periodo"], s["familia"]), 0))
            filas.append({"periodo": m["periodo"], "fuente": "ventas", "serie_id": sid, "m5": m["valor"], "a02": ref, "diferencia": dif,
                          "tolerancia": lim, "operaciones_m5": m["operaciones"], "operaciones_a02": ops.get((m["periodo"], s["familia"]), 0),
                          "conciliado": abs(dif) <= lim and m["operaciones"] == ops.get((m["periodo"], s["familia"]), 0)})
    return filas


def tramo(calendario: list[dict], origen: str) -> list[float]:
    """Valores completos y CONSECUTIVOS que terminan en ``origen`` (un hueco corta el tramo; nunca se imputan ceros)."""
    hist = []
    for m in reversed([m for m in calendario if m["periodo"] <= origen]):
        if m["estado"] != "completo":
            break
        hist.append(m["valor"])
    if not hist or not [m for m in calendario if m["periodo"] == origen and m["estado"] == "completo"]:
        return []
    return list(reversed(hist))


# Referencias e inferencia ------------------------------------------------------------------------------------------
def pron_ultimo(hist: list[float], h: int) -> float:
    return float(hist[-1])


def pron_media_movil_3(hist: list[float], h: int) -> float:
    """A08 exacto (``pipeline.pronostico``): recursiva, cada paso incorpora los pronósticos previos."""
    from pipeline.pronostico import pronosticar_media_movil
    return float(pronosticar_media_movil(hist, 3, h)[h - 1])


def pron_estado(estado: Mapping[str, Any], h: int) -> float:
    """SES: nivel. Holt amortiguado: nivel + (φ + … + φ^h)·tendencia. Ambos en escala original."""
    nivel, tend, phi = float(estado["nivel"]), float(estado.get("tendencia") or 0.0), float(estado.get("amortiguamiento") or 1.0)
    suma = sum(phi ** i for i in range(1, h + 1)) if estado["metodo"] == "holt_amortiguado" else 0.0
    return (nivel + suma * tend) * float(estado["escala"])


def publicar_valor(bruto: float) -> tuple[float, bool]:
    """Política de salida no negativa: (publicado, recortado)."""
    return (0.0, True) if bruto < 0 else (float(bruto), False)


# Artefacto de origen ------------------------------------------------------------------------------------------------
def validar_artefacto_demanda(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") != FORMATO or d.get("modelo_id") != MODELO_ID:
        e.append("formato o modelo_id incompatibles")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if not isinstance(d.get("origen"), str) or len(d["origen"]) != 7:
        e.append("origen debe ser AAAA-MM")
    if d.get("umbral") is not None:
        e.append("umbral debe ser nulo")
    for sid, s in (d.get("series") or {}).items():
        sel = s.get("seleccion") or {}
        if set(sel) - {str(h) for h in HORIZONTES} or any(m not in METODOS + ("sin_historia",) for m in sel.values()):
            e.append(f"{sid}: selección inválida")
        for m, est in (s.get("estados") or {}).items():
            if m in ("ses", "holt_amortiguado") and not all(_finito(est.get(k)) for k in ("nivel", "escala")):
                e.append(f"{sid}.{m}: estado no finito")
        if s.get("ultimo_mes_completo") not in (None, d.get("origen")):
            e.append(f"{sid}: el estado corresponde a otro origen ({s.get('ultimo_mes_completo')})")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoDemanda:
    datos: dict
    version = property(lambda self: self.datos["version"])
    modelo_id = property(lambda self: self.datos["modelo_id"])
    huella = property(lambda self: self.datos["huella"])
    umbral = property(lambda self: None)
    origen = property(lambda self: self.datos["origen"])
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))
    version_variables = property(lambda self: None)

    def pronostico(self, serie_id: str, h: int) -> dict:
        """Valor bruto y publicado del método seleccionado para la serie y el horizonte, sin dependencias de entrenamiento."""
        s = self.datos["series"][serie_id]
        metodo = s["seleccion"].get(str(h))
        if metodo in (None, "sin_historia"):
            return {"metodo": "sin_historia", "bruto": None, "valor": None, "recortado": False, "sustitucion": None}
        sustitucion = None
        if metodo in ("ses", "holt_amortiguado"):
            est = s["estados"].get(metodo) or {}
            if not est.get("convergio"):
                sustitucion = {"metodo_seleccionado": metodo, "motivo": est.get("motivo") or "ajuste no convergió", "respaldo": "media_movil_3"}
                metodo = "media_movil_3"
            else:
                bruto = pron_estado(est, h)
        if metodo == "ultimo":
            bruto = pron_ultimo(s["historia"], h)
        elif metodo == "media_movil_3":
            bruto = pron_media_movil_3(s["historia"], h)
        valor, rec = publicar_valor(bruto)
        return {"metodo": metodo, "bruto": bruto, "valor": round(valor, 2), "recortado": rec, "sustitucion": sustitucion}

    def probabilidad(self, fila):  # interfaz común: no hay probabilidades
        raise TypeError("demanda publica valores pronosticados, no probabilidades")


# Publicación ---------------------------------------------------------------------------------------------------------
def filas_pronostico(art: ArtefactoDemanda, series: Mapping[str, dict], datos_info: Mapping[str, Any]) -> list[dict]:
    """Filas C2 ``pronosticos_demanda`` del origen del artefacto (+ total de ventas COP como suma de familias)."""
    filas = []
    for sid in sorted(art.datos["series"]):
        s, meta = art.datos["series"][sid], series[sid]
        for h in HORIZONTES:
            p = art.pronostico(sid, h)
            ev = (s.get("evaluacion") or {}).get(str(h)) or {}
            banda = (s.get("bandas") or {}).get(str(h)) or {"inferior": None, "superior": None, "metodo": None, "errores_disponibles": 0,
                                                             "motivo": "historia_insuficiente"}
            estado = "estimado" if p["valor"] is not None else "sin_historia"
            motivos = list(s.get("motivos") or [])
            if p["sustitucion"]:
                motivos.append(f"El ajuste de {p['sustitucion']['metodo_seleccionado']} no convergió ({p['sustitucion']['motivo']}): se usa {p['sustitucion']['respaldo']}")
            if p["recortado"]:
                motivos.append(f"Valor bruto {p['bruto']:.2f} recortado a 0 (política de salida no negativa)")
            if not motivos:
                motivos.append("Pronóstico del método seleccionado en desarrollo con la historia completa hasta el origen")
            filas.append({"modelo_id": MODELO_ID, "origen": art.origen, "serie_id": sid, "fuente": meta["fuente"], "medida": meta["medida"], "unidad": meta["unidad"],
                          "familia": meta.get("familia"), "producto_id": meta.get("producto_id"), "horizonte_meses": h, "periodo_objetivo": sumar_meses(art.origen, h),
                          "valor": p["valor"], "valor_bruto": None if p["bruto"] is None else round(p["bruto"], 6), "recortado": p["recortado"],
                          "metodo": p["metodo"], "tipo_metodo": "referencia" if p["metodo"] in REFERENCIAS else ("candidato" if p["metodo"] != "sin_historia" else None),
                          "estado": estado, "version_modelo": art.version, "revision_datos": datos_info.get("revision"), "cobertura_hasta": datos_info.get("cobertura_hasta"),
                          "mae": ev.get("mae"), "n_evaluaciones": ev.get("n", 0), "periodo_evaluacion": ev.get("periodo"), "alcance_evaluacion": ev.get("alcance"),
                          "banda_inferior": banda["inferior"], "banda_superior": banda["superior"], "banda_metodo": banda.get("metodo"),
                          "banda_soporte": banda.get("errores_disponibles", 0), "banda_motivo": banda.get("motivo"), "motivos": motivos})
    for h in HORIZONTES:
        fams = [f for f in filas if f["serie_id"].startswith("ventas_cop:") and f["horizonte_meses"] == h]
        completo = len(fams) == len(FAMILIAS) and all(f["valor"] is not None for f in fams)
        tot = (art.datos.get("total") or {}).get(str(h)) or {}
        banda = tot.get("banda") or {"inferior": None, "superior": None, "metodo": None, "errores_disponibles": 0, "motivo": "historia_insuficiente"}
        filas.append({"modelo_id": MODELO_ID, "origen": art.origen, "serie_id": "ventas_cop:Total", "fuente": "ventas", "medida": "ingreso por ventas confirmadas",
                      "unidad": "COP", "familia": "Total", "producto_id": None, "horizonte_meses": h, "periodo_objetivo": sumar_meses(art.origen, h),
                      "valor": round(sum(f["valor"] for f in fams), 2) if completo else None, "valor_bruto": None, "recortado": False,
                      "metodo": "suma_de_familias", "tipo_metodo": "agregado", "estado": "estimado" if completo else "total_incompleto",
                      "version_modelo": art.version, "revision_datos": datos_info.get("revision"), "cobertura_hasta": datos_info.get("cobertura_hasta"),
                      "mae": tot.get("mae"), "n_evaluaciones": tot.get("n", 0), "periodo_evaluacion": tot.get("periodo"), "alcance_evaluacion": tot.get("alcance"),
                      "banda_inferior": banda["inferior"], "banda_superior": banda["superior"], "banda_metodo": banda.get("metodo"),
                      "banda_soporte": banda.get("errores_disponibles", 0), "banda_motivo": banda.get("motivo"),
                      "motivos": ["Suma de los pronósticos publicados de las cuatro familias" if completo else "Falta el pronóstico de alguna familia: el total no se publica"]})
    return filas


def calendario_publicable(series: Mapping[str, dict]) -> list[dict]:
    return [{"serie_id": sid, "periodo": m["periodo"], "estado": m["estado"], "valor": m["valor"], "motivo": m["motivo"], "unidad": s["unidad"]}
            for sid, s in sorted(series.items()) for m in s["calendario"]]


def puntuar_sombra(art: ArtefactoDemanda, datos, config: dict, salida: str | Path, *, estado_experimento: str, decision: Mapping[str, Any] | None = None) -> dict:
    """Publica ``pronosticos_demanda`` + ``calendario_demanda`` en sombra. No ajusta nada: usa los estados del artefacto."""
    from contratos.validar import validar_publicacion_sombra
    from .ejecucion import json_bytes, publicar_lote
    series = construir_series(datos, config)
    ultimo = max(m["periodo"] for m in series[f"ventas_cop:{FAMILIAS[0]}"]["calendario"] if m["estado"] == "completo")
    if ultimo != art.origen:
        raise ValueError(f"El artefacto es del origen {art.origen} y los datos completos llegan a {ultimo}: ajusta el procedimiento congelado para ese origen")
    info = {"revision": datos.revision, "cobertura_hasta": datos.observado_hasta.isoformat()}
    filas, cal = filas_pronostico(art, series, info), calendario_publicable(series)
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": MODELO_ID, "corte": datos.observado_hasta.isoformat(), "origen": art.origen,
           "estado_experimento": estado_experimento, "operativa": False,
           "advertencia": "Proyección experimental en sombra: no es ingreso realizado, margen, orden de compra ni predicción de TRM; no sustituye las series_mensuales operativas.",
           "modelo": {"version": art.version, "artefacto_huella": art.huella, "decision": dict(decision) if decision else None},
           "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
           "cobertura": {"corte": datos.observado_hasta.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
           "tablas": {"pronosticos_demanda": {"filas": len(filas)}, "calendario_demanda": {"filas": len(cal)}}}
    errores = validar_publicacion_sombra(man, {"pronosticos_demanda": filas, "calendario_demanda": cal})
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato: " + "; ".join(errores[:5]))
    publicar_lote(salida, {"pronosticos_demanda.json": json_bytes(filas), "calendario_demanda.json": json_bytes(cal)}, "manifiesto.json", man)
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas}


def incorporar_observaciones(publicacion: str | Path, datos, config: dict, salida: str | Path) -> dict:
    """Evalúa una emisión YA publicada con meses que ahora están completos. Nunca modifica el pronóstico original:
    escribe ``evaluaciones_<hasta>.json`` vinculadas a cada fila (serie, origen, horizonte) en otra carpeta."""
    from contratos.validar import leer_publicacion_sombra
    from .ejecucion import json_bytes, publicar_lote
    errores, man, tablas = leer_publicacion_sombra(publicacion)
    if errores:
        raise ValueError("Publicación inválida: " + "; ".join(errores[:3]))
    series = construir_series(datos, config)
    reales = {(sid, m["periodo"]): m for sid, s in series.items() for m in s["calendario"]}
    evals = []
    for f in tablas["pronosticos_demanda"]:
        if f["serie_id"] == "ventas_cop:Total":
            ms = [reales.get((f"ventas_cop:{x}", f["periodo_objetivo"])) for x in FAMILIAS]
            obs = sum(m["valor"] for m in ms) if all(m and m["estado"] == "completo" for m in ms) else None
        else:
            m = reales.get((f["serie_id"], f["periodo_objetivo"]))
            obs = m["valor"] if m and m["estado"] == "completo" else None
        estado = "pendiente" if obs is None else ("sin_pronostico" if f["valor"] is None else "evaluado")
        evals.append({"serie_id": f["serie_id"], "origen": f["origen"], "horizonte_meses": f["horizonte_meses"], "periodo_objetivo": f["periodo_objetivo"],
                      "valor_publicado": f["valor"], "observado": obs, "error": round(f["valor"] - obs, 2) if estado == "evaluado" else None, "estado": estado,
                      "version_modelo": f["version_modelo"], "sello_publicacion": man["sello"]})
    hasta = datos.observado_hasta.isoformat()
    publicar_lote(salida, {f"evaluaciones_{hasta}.json": json_bytes(evals)}, f"evaluaciones_{hasta}.marcador.json",
                  {"publicacion": str(publicacion), "sello_publicacion": man["sello"], "datos_hasta": hasta, "revision_datos": datos.revision})
    return {"evaluadas": sum(e["estado"] == "evaluado" for e in evals), "pendientes": sum(e["estado"] == "pendiente" for e in evals), "evaluaciones": evals}
