"""M6 · Detección de operaciones atípicas (``anomalias``): operaciones válidas, contexto temporal, referencia mediana/MAD,
inferencia JSON de Isolation Forest, cola priorizada y publicación en sombra. Solo biblioteca estándar: el ajuste
(scikit-learn) vive en ``modelos/anomalias_experimento.py``.

* Identidad: ``(tipo_operacion, operacion_id)``; una venta y una compra con el mismo ID no colisionan.
* Universos separados: ventas confirmadas y compras a proveedores. Nunca se mezclan precios y costos.
* Errores de esquema, referencias y duplicados son de A01 (no llegan aquí). Ventas anuladas: excluidas con motivo.
  Valores no finitos o <= 0: excluidos (``fuera_de_dominio``), nunca convertidos en etiquetas de anomalía.
* Contexto: grupo (tipo, producto, moneda, unidad) con antecedentes de FECHA ESTRICTAMENTE ANTERIOR (bloque diario sin hora
  fiable). Menos de ``min_antecedentes`` → ``historia_insuficiente`` sin puntaje (nunca un cero).
* Señales comerciales en moneda de origen. El importe COP y la TRM se publican, pero no entran al detector: un cambio
  exclusivo de TRM deja iguales las variables y el puntaje.
* Puntaje: rareza (mayor = más raro). NO es probabilidad de fraude ni porcentaje de error.
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
import random
import struct
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from .inferencia import _finito, huella_artefacto

MODELO_ID = "anomalias"
FORMATO = "jacomind.anomalias_iforest.v1"
UNIVERSOS = ("venta", "compra")
VARIABLES = ("z_log_valor_unitario", "z_log_cantidad", "z_log_importe")
ESTADOS_PUNTUACION = ("puntuada", "historia_insuficiente")
METODOS = ("isolation_forest", "mediana_mad")
EULER_GAMMA = 0.5772156649015329
NOTA = ("Cola experimental en sombra para revisión humana. La puntuación indica rareza frente a operaciones comparables anteriores: "
        "no es una probabilidad de fraude ni demuestra un error. La cola no modifica importes, no anula operaciones ni afecta al cliente.")


# Operaciones válidas -------------------------------------------------------------------------------------------------
def cargar_compras(datos) -> list[dict]:
    """Compras de la MISMA revisión aceptada por A01 (``datos.directorio``); nunca el CSV original."""
    from pipeline.operaciones import _load
    return _load(Path(datos.directorio), "compras.csv", "compras")


def unidad(producto_id: str, config: Mapping) -> str:
    return (config.get("unidades") or {}).get("por_producto", {}).get(producto_id) or f"unidad de catálogo de {producto_id}"


def _num(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def operaciones(ventas: Iterable[Mapping], compras: Iterable[Mapping], tasas: Mapping[date, Any], config: Mapping) -> tuple[list[dict], list[dict]]:
    """(operaciones válidas, exclusiones con motivo). Las exclusiones nunca se convierten en anomalías."""
    validas, excluidas = [], []
    fuentes = [("venta", v, "venta_id", "precio_unitario") for v in ventas] + [("compra", c, "compra_id", "costo_unitario") for c in compras]
    for tipo, r, campo_id, campo_valor in fuentes:
        oid = str(r[campo_id])
        base = {"tipo_operacion": tipo, "operacion_id": oid, "fecha": r["fecha"], "producto_id": str(r["producto_id"])}
        if tipo == "venta" and r.get("estado", "Confirmada") != "Confirmada":
            excluidas.append(dict(base, motivo="venta_anulada" if r.get("estado") == "Anulada" else f"estado_{r.get('estado')}"))
            continue
        q, u = _num(r.get("cantidad")), _num(r.get(campo_valor))
        d = _num(r.get("descuento_pct", 0)) if tipo == "venta" else 0.0
        if q is None or u is None or d is None or q <= 0 or u <= 0 or not 0 <= d < 100:
            excluidas.append(dict(base, motivo="fuera_de_dominio"))
            continue
        moneda = str(r.get("moneda"))
        if moneda not in ("COP", "USD"):
            excluidas.append(dict(base, motivo="moneda_no_admitida"))
            continue
        importe = q * u * (1 - d / 100)
        trm, estado_trm = None, "no_aplica"
        if moneda == "USD":
            t = tasas.get(r["fecha"])
            trm, estado_trm = (float(t), "disponible") if t is not None and _num(t) and float(t) > 0 else (None, "ausente")
        validas.append(dict(base, cliente_id=str(r["cliente_id"]) if tipo == "venta" else None,
                            proveedor_id=str(r["proveedor_id"]) if tipo == "compra" else None, moneda=moneda,
                            unidad=unidad(str(r["producto_id"]), config), cantidad=q, valor_unitario=u, descuento_pct=d,
                            importe_origen=round(importe, 6), trm=trm, estado_trm=estado_trm,
                            importe_cop=round(importe if moneda == "COP" else importe * trm, 2) if (moneda == "COP" or trm) else None))
    claves = [(o["tipo_operacion"], o["operacion_id"]) for o in validas]
    if len(claves) != len(set(claves)):
        raise ValueError("Identidades (tipo_operacion, operacion_id) duplicadas tras A01: no se puntúa")
    return validas, excluidas


def huella_valores(op: Mapping) -> str:
    """Huella de los valores observados de la operación: una corrección de datos produce otra huella (otra revisión del caso)."""
    campos = ("tipo_operacion", "operacion_id", "fecha", "producto_id", "cliente_id", "proveedor_id", "moneda", "cantidad", "valor_unitario", "descuento_pct")
    return hashlib.sha256(json.dumps({k: (str(op.get(k)) if k == "fecha" else op.get(k)) for k in campos}, sort_keys=True).encode()).hexdigest()


# Contexto temporal ---------------------------------------------------------------------------------------------------
def grupo(op: Mapping) -> tuple:
    return (op["tipo_operacion"], op["producto_id"], op["moneda"], op["unidad"])


def _obs(op: Mapping) -> tuple:
    return (math.log(op["cantidad"]), math.log(op["valor_unitario"]), math.log(op["importe_origen"]))


class Historial:
    """Antecedentes por grupo, solo de operaciones ORIGINALES válidas, ordenados por (fecha, operacion_id).

    ``antecedentes(op)`` devuelve los de fecha estrictamente anterior (ninguna operación del mismo día) y como máximo
    los ``ventana`` más recientes. Añadir operaciones futuras no cambia los antecedentes de una fecha pasada."""

    def __init__(self, originales: Iterable[Mapping], ventana: int):
        self.ventana = int(ventana)
        self._g: dict[tuple, list] = defaultdict(list)
        for op in sorted(originales, key=lambda o: (o["fecha"], o["operacion_id"])):
            self._g[grupo(op)].append((op["fecha"], _obs(op), op["cantidad"]))
        self._fechas = {g: [x[0] for x in v] for g, v in self._g.items()}

    def antecedentes(self, g: tuple, fecha: date) -> list[tuple]:
        lista = self._g.get(g, [])
        fin = bisect.bisect_left(self._fechas.get(g, []), fecha)  # fecha estrictamente anterior
        return lista[max(0, fin - self.ventana):fin]


def _escala(valores: list[float], ctx: Mapping) -> tuple[float, float, float]:
    med = median(valores)
    mad = median(abs(v - med) for v in valores)
    return med, mad, max(float(ctx["factor_mad"]) * mad, float(ctx["piso_escala_log"]))


def _z(x: float, med: float, escala: float, zmax: float) -> float:
    return max(-zmax, min(zmax, (x - med) / escala))


def contexto(op: Mapping, historial: Historial, config: Mapping) -> dict:
    """Variables contextuales de ``op`` frente a sus antecedentes (o respaldo documentado), o abstención explícita."""
    ctx = config["contexto"]
    g = grupo(op)
    ant = historial.antecedentes(g, op["fecha"])
    respaldo = None
    if len(ant) < int(ctx["min_antecedentes"]):
        alt = (ctx.get("respaldos") or {}).get(f"{op['tipo_operacion']}:{op['producto_id']}")
        if alt:
            g2 = (op["tipo_operacion"], alt["producto_id"], op["moneda"], op["unidad"]) if alt.get("misma_unidad") else None
            ant2 = historial.antecedentes(g2, op["fecha"]) if g2 else []
            if len(ant2) >= int(ctx["min_antecedentes"]):
                ant, respaldo = ant2, {"producto_id": alt["producto_id"], "documentacion": alt.get("documentacion")}
    if len(ant) < int(ctx["min_antecedentes"]):
        return {"estado": "historia_insuficiente", "soporte": len(ant), "respaldo": None, "variables": None,
                "motivo": f"{len(ant)} antecedentes comparables anteriores (se exigen {ctx['min_antecedentes']}) y ningún respaldo documentado"}
    zmax = float(ctx["z_max"])
    lq, lu, li = _obs(op)
    mq, madq, eq = _escala([a[1][0] for a in ant], ctx)
    mu, madu, eu = _escala([a[1][1] for a in ant], ctx)
    mi, madi, ei = _escala([a[1][2] for a in ant], ctx)
    v = {"z_log_valor_unitario": _z(lu, mu, eu, zmax), "z_log_cantidad": _z(lq, mq, eq, zmax), "z_log_importe": _z(li, mi, ei, zmax)}
    return {"estado": "puntuada", "soporte": len(ant), "respaldo": respaldo, "variables": v,
            "referencia_cantidad": math.exp(mq), "referencia_valor_unitario": math.exp(mu), "referencia_importe": math.exp(mi),
            "razon_cantidad": math.exp(lq - mq), "razon_valor_unitario": math.exp(lu - mu), "razon_importe": math.exp(li - mi),
            "dispersion": {"mad_log_cantidad": madq, "mad_log_valor_unitario": madu, "mad_log_importe": madi},
            "antecedentes_desde": ant[0][0].isoformat(), "antecedentes_hasta": ant[-1][0].isoformat(),
            "percentil_90_cantidad": _percentil([a[2] for a in ant], 0.9)}


def _percentil(valores: list[float], p: float) -> float:
    s = sorted(valores)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# Referencia contextual (mediana/MAD + reglas) ---------------------------------------------------------------------------
def puntaje_referencia(v: Mapping[str, float]) -> float:
    return max(abs(v["z_log_valor_unitario"]), abs(v["z_log_cantidad"]))


def reglas(c: Mapping, config: Mapping) -> dict:
    """Variables inusuales según las reglas declaradas de la referencia (motivos legibles, sin causalidad)."""
    r = config["referencia"]["reglas"]
    v = c["variables"]
    valor = abs(v["z_log_valor_unitario"]) >= r["z_regla"] or not r["razon_valor_min"] <= c["razon_valor_unitario"] <= r["razon_valor_max"]
    cant = abs(v["z_log_cantidad"]) >= r["z_regla"] or not r["razon_cantidad_min"] <= c["razon_cantidad"] <= r["razon_cantidad_max"]
    return {"valor_unitario": valor, "cantidad": cant, "senalada": valor or cant}


def _fmt(x: float, d: int = 2) -> str:
    return f"{x:,.{d}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def motivos(op: Mapping, c: Mapping, config: Mapping) -> tuple[list[str], list[str]]:
    """(motivos, variables_inusuales): desviaciones observadas frente al contexto; no atribuyen causa ni contribuciones."""
    if c["estado"] != "puntuada":
        return [c["motivo"]], []
    zm = float(config["referencia"]["z_motivo"])
    etiqueta = config["universos"][op["tipo_operacion"]]["etiqueta_valor"]
    v, out, inus = c["variables"], [], []
    soporte = f"{c['soporte']} antecedentes del mismo producto y moneda ({c['antecedentes_desde']} a {c['antecedentes_hasta']})"
    if abs(v["z_log_valor_unitario"]) >= zm:
        inus.append("valor_unitario")
        out.append(f"{etiqueta.capitalize()} {_fmt(op['valor_unitario'])} {op['moneda']} frente a referencia {_fmt(c['referencia_valor_unitario'])} "
                   f"(×{_fmt(c['razon_valor_unitario'])}; desviación robusta {'+' if v['z_log_valor_unitario'] >= 0 else '−'}{_fmt(abs(v['z_log_valor_unitario']), 1)}) con {soporte}")
    if abs(v["z_log_cantidad"]) >= zm:
        inus.append("cantidad")
        out.append(f"Cantidad {_fmt(op['cantidad'])} frente a referencia {_fmt(c['referencia_cantidad'])} "
                   f"(×{_fmt(c['razon_cantidad'])}; desviación robusta {'+' if v['z_log_cantidad'] >= 0 else '−'}{_fmt(abs(v['z_log_cantidad']), 1)}) con {soporte}")
    if abs(v["z_log_importe"]) >= zm and not inus:
        inus.append("importe")
        out.append(f"Importe en moneda de origen ×{_fmt(c['razon_importe'])} frente a la referencia del grupo (desviación {_fmt(v['z_log_importe'], 1)}) con {soporte}")
    if not out:
        out.append(f"Ninguna variable supera por sí sola la desviación {_fmt(zm, 1)}: valores dentro del rango habitual o combinación de desviaciones moderadas ({soporte})")
    if c.get("respaldo"):
        out.append(f"Contexto de respaldo documentado: {c['respaldo']['producto_id']}")
    return out, inus


# Isolation Forest desde JSON -------------------------------------------------------------------------------------------
def a_float32(x: float) -> float:
    """scikit-learn convierte las entradas del bosque a float32 antes de recorrer los árboles."""
    return struct.unpack("f", struct.pack("f", float(x)))[0]


def longitud_media(n: float) -> float:
    """c(n) de scikit-learn (``_average_path_length``)."""
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1.0) + EULER_GAMMA) - 2.0 * (n - 1.0) / n


class Bosque:
    """Recorrido de árboles exportados: ``x[f] <= t`` va a la izquierda (como ``tree.apply``); profundidad del nodo
    (raíz = 1) + c(n_hoja) − 1, sumado en el orden de los árboles; rareza = 2^(−suma / (n_arboles · c(max_muestras)))."""

    def __init__(self, d: Mapping):
        self.n_variables = len(d["variables"])
        self.arboles = []
        for a in d["arboles"]:
            prof = [0] * len(a["izq"])
            prof[0] = 1
            for i in range(len(a["izq"])):
                if a["izq"][i] != -1:
                    prof[a["izq"][i]] = prof[a["der"][i]] = prof[i] + 1
            hoja = [(float(prof[i]) + longitud_media(a["n"][i])) - 1.0 if a["izq"][i] == -1 else None for i in range(len(a["izq"]))]
            self.arboles.append((a["var"], a["umbral"], a["izq"], a["der"], hoja))
        self.denominador = len(self.arboles) * longitud_media(d["max_muestras"])

    def rareza(self, x: list[float]) -> float:
        xs = [a_float32(v) for v in x]
        total = 0.0
        for var, umb, izq, der, hoja in self.arboles:
            n = 0
            while izq[n] != -1:
                n = izq[n] if xs[var[n]] <= umb[n] else der[n]
            total += hoja[n]
        return 2.0 ** (-(total / self.denominador)) if self.denominador else 1.0


def validar_artefacto_anomalias(d: dict, formato: str = FORMATO, politicas: tuple = ("ranking_con_cupo",), variables: tuple = VARIABLES) -> list[str]:
    e: list[str] = []
    if d.get("formato") != formato or d.get("modelo_id") != MODELO_ID:
        e.append("formato o modelo_id incompatibles")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if d.get("umbral") is not None:
        e.append("umbral debe ser nulo (la política es ranking con cupo)")
    pol = d.get("politica_alertas") or {}
    if pol.get("tipo") not in politicas or not (_finito(pol.get("cupo_fraccion")) and 0 < pol["cupo_fraccion"] <= 1) or not isinstance(pol.get("cupo_minimo"), int):
        e.append("politica_alertas inválida")
    ctx = d.get("contexto") or {}
    if not (isinstance(ctx.get("min_antecedentes"), int) and ctx["min_antecedentes"] >= 1 and isinstance(ctx.get("ventana_antecedentes"), int)
            and all(_finito(ctx.get(k)) and ctx[k] > 0 for k in ("factor_mad", "piso_escala_log", "z_max"))):
        e.append("contexto: parámetros numéricos inválidos")
    for u in UNIVERSOS:
        s = (d.get("universos") or {}).get(u)
        if not isinstance(s, dict):
            e.append(f"{u}: falta el universo")
            continue
        if s.get("metodo") not in METODOS:
            e.append(f"{u}: método inválido")
        if s.get("metodo") != "isolation_forest":
            continue
        if not isinstance(s.get("variables"), list) or not s["variables"] or set(s["variables"]) - set(variables):
            e.append(f"{u}: variables inválidas")
            continue
        arb = s.get("arboles")
        if not isinstance(arb, list) or len(arb) != s.get("n_estimadores") or not arb:
            e.append(f"{u}: número de árboles distinto de n_estimadores")
            continue
        if not isinstance(s.get("max_muestras"), int) or s["max_muestras"] < 1:
            e.append(f"{u}: max_muestras inválido")
        for k, a in enumerate(arb):
            n = len(a.get("izq", []))
            if not n or any(len(a.get(c, [])) != n for c in ("der", "var", "umbral", "n")):
                e.append(f"{u}.arboles[{k}]: dimensiones incoherentes")
                break
            if any((i != -1 and not 0 < i < n) or (i == -1) != (j == -1) or (j != -1 and not 0 < j < n) for i, j in zip(a["izq"], a["der"])):
                e.append(f"{u}.arboles[{k}]: hijos fuera de rango")
                break
            if any(i != -1 and not (isinstance(f, int) and 0 <= f < len(s["variables"]) and _finito(t)) for i, f, t in zip(a["izq"], a["var"], a["umbral"])):
                e.append(f"{u}.arboles[{k}]: variable o umbral inválidos")
                break
            if any(not (isinstance(m, int) and m >= 1) for m in a["n"]):
                e.append(f"{u}.arboles[{k}]: tamaños de nodo inválidos")
                break
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoAnomalias:
    datos: dict
    version = property(lambda self: self.datos["version"])
    modelo_id = property(lambda self: self.datos["modelo_id"])
    huella = property(lambda self: self.datos["huella"])
    umbral = property(lambda self: None)
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))
    version_variables = property(lambda self: None)

    def metodo(self, universo: str) -> str:
        return self.datos["universos"][universo]["metodo"]

    def bosque(self, universo: str) -> Bosque | None:
        cache = self.__dict__.setdefault("_bosques", {})
        if universo not in cache:
            s = self.datos["universos"][universo]
            cache[universo] = Bosque(s) if s["metodo"] == "isolation_forest" else None
        return cache[universo]

    def rareza(self, universo: str, variables: Mapping[str, float] | None) -> float | None:
        b = self.bosque(universo)
        if b is None or variables is None:
            return None
        return b.rareza([variables[v] for v in self.datos["universos"][universo]["variables"]])

    def config_contexto(self) -> dict:
        return {"contexto": self.datos["contexto"], "referencia": self.datos["referencia"], "universos": self.datos["etiquetas_universos"],
                "unidades": self.datos["unidades"]}

    def probabilidad(self, fila):  # interfaz común: no hay probabilidades
        raise TypeError("anomalias publica rareza para ordenar la revisión, no probabilidades")


# Cola priorizada ------------------------------------------------------------------------------------------------------
def periodo(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def cupo(n_puntuadas: int, politica: Mapping) -> int:
    return 0 if n_puntuadas == 0 else max(int(politica["cupo_minimo"]), math.ceil(float(politica["cupo_fraccion"]) * n_puntuadas - 1e-9))


def priorizar(filas: list[dict], politica: Mapping) -> None:
    """Prioridad 1..n por (universo, mes) con desempate estable; alerta = prioridad <= cupo. Abstenciones sin prioridad."""
    por: dict[tuple, list] = defaultdict(list)
    for f in filas:
        f["prioridad"], f["alerta"], f["cupo_periodo"] = None, False, None
        if f["puntaje"] is not None:
            por[(f["tipo_operacion"], f["periodo"])].append(f)
    for (u, p), fs in por.items():
        fs.sort(key=lambda f: (-f["puntaje"], f["fecha"], f["operacion_id"]))
        k = cupo(len(fs), politica)
        for i, f in enumerate(fs, 1):
            f["prioridad"], f["alerta"], f["cupo_periodo"] = i, i <= k, k
    for f in filas:
        if f["cupo_periodo"] is None:
            f["cupo_periodo"] = cupo(len(por.get((f["tipo_operacion"], f["periodo"]), [])), politica)


def fila_operacion(op: Mapping, c: Mapping, art: ArtefactoAnomalias, config: Mapping, info: Mapping, metodos: Mapping[str, str]) -> dict:
    u = op["tipo_operacion"]
    ref = puntaje_referencia(c["variables"]) if c["estado"] == "puntuada" else None
    cand = art.rareza(u, c["variables"]) if c["estado"] == "puntuada" else None
    metodo = metodos[u]
    if metodo == "isolation_forest" and art.metodo(u) != "isolation_forest":
        raise ValueError(f"{u}: se pidió publicar isolation_forest pero el candidato está en abstención")
    puntaje = cand if metodo == "isolation_forest" else ref
    mot, inus = motivos(op, c, config)
    rg = reglas(c, config) if c["estado"] == "puntuada" else {"senalada": False}
    r6 = lambda x: None if x is None else round(x, 6)  # noqa: E731
    return {"modelo_id": MODELO_ID, "tipo_operacion": u, "operacion_id": op["operacion_id"], "revision_datos": info.get("revision"),
            "fecha": op["fecha"].isoformat(), "periodo": periodo(op["fecha"]), "producto_id": op["producto_id"],
            "cliente_id": op.get("cliente_id"), "proveedor_id": op.get("proveedor_id"), "moneda": op["moneda"], "unidad": op["unidad"],
            "cantidad": op["cantidad"], "valor_unitario": op["valor_unitario"], "descuento_pct": op["descuento_pct"], "importe_origen": round(op["importe_origen"], 2),
            "trm": op["trm"], "estado_trm": op["estado_trm"], "importe_cop": op["importe_cop"],
            "referencia_cantidad": r6(c.get("referencia_cantidad")), "referencia_valor_unitario": r6(c.get("referencia_valor_unitario")),
            "razon_cantidad": r6(c.get("razon_cantidad")), "razon_valor_unitario": r6(c.get("razon_valor_unitario")),
            "variables": {k: round(v, 6) for k, v in c["variables"].items()} if c["variables"] else None,
            "soporte": c["soporte"], "dispersion": {k: round(v, 6) for k, v in c["dispersion"].items()} if c.get("dispersion") else None,
            "respaldo": c.get("respaldo"), "antecedentes": [c.get("antecedentes_desde"), c.get("antecedentes_hasta")] if c["estado"] == "puntuada" else None,
            "puntaje": None if puntaje is None else round(puntaje, 12), "puntaje_referencia": None if ref is None else round(ref, 12),
            "puntaje_candidato": None if cand is None else round(cand, 12), "metodo": metodo if c["estado"] == "puntuada" else None,
            "senalada_por_reglas": rg["senalada"], "motivos": mot, "variables_inusuales": inus, "estado_puntuacion": c["estado"],
            "version_modelo": art.version, "corte": info["corte"], "tipo_emision": "prospectiva" if op["fecha"] > art.disponible_desde else "reconstruccion_historica",
            "huella_valores": huella_valores(op)}


def cobertura_filas(filas: list[dict], excluidas: list[dict], desde: date, corte: date, config: Mapping) -> list[dict]:
    out = []
    claves = sorted({(f["tipo_operacion"], f["periodo"]) for f in filas} | {(e["tipo_operacion"], periodo(e["fecha"])) for e in excluidas if desde <= e["fecha"] <= corte})
    for u, p in claves:
        fs = [f for f in filas if f["tipo_operacion"] == u and f["periodo"] == p]
        ex: dict[str, int] = defaultdict(int)
        for e in excluidas:
            if e["tipo_operacion"] == u and periodo(e["fecha"]) == p and desde <= e["fecha"] <= corte:
                ex[e["motivo"]] += 1
        punt = [f for f in fs if f["estado_puntuacion"] == "puntuada"]
        alert = [f for f in punt if f["alerta"]]
        senal = [f for f in fs if f["senalada_por_reglas"]]  # incluye abstenciones con evidencia de catálogo (M6.1); en M6 solo las puntuadas se señalan
        declarada = u == "venta"
        out.append({"modelo_id": MODELO_ID, "tipo_operacion": u, "periodo": p, "validas": len(fs), "puntuadas": len(punt),
                    "abstenciones": {"historia_insuficiente": len(fs) - len(punt)}, "excluidas": dict(ex), "alertas": len(alert),
                    "cupo": cupo(len(punt), config["politica_alertas"]), "senaladas_por_reglas": len(senal),
                    "exceso_sobre_cupo": sum(1 for f in senal if not f["alerta"]),
                    "cobertura_puntuacion": round(len(punt) / len(fs), 6) if fs else None,
                    "cobertura_temporal": "declarada" if declarada else "no_declarada",
                    "nota": None if declarada else config["cobertura"]["compra"]["motivo"]})
    return out


def muestra_revision(filas: list[dict], config: Mapping, corte: str) -> dict:
    """Muestra estratificada reproducible (alertada / no_alertada) con probabilidad de inclusión: NO representativa sin ponderar."""
    m = config["muestra_revision"]
    rng = random.Random(f"{m['semilla']}:{corte}")
    sel, reasignadas = [], {}
    for u in UNIVERSOS:
        deficit = 0
        for estrato in ("alertada", "no_alertada"):
            pob = sorted([f for f in filas if f["tipo_operacion"] == u and f["estado_puntuacion"] == "puntuada" and f["alerta"] == (estrato == "alertada")],
                         key=lambda f: f["operacion_id"])
            objetivo = int(m["por_universo"][u][estrato]) + (deficit if estrato == "no_alertada" else 0)
            n = min(objetivo, len(pob))
            if estrato == "alertada":
                deficit = objetivo - n  # pocas alertas: el déficit pasa al estrato no alertado del mismo universo (registrado)
                reasignadas[u] = deficit
            for f in rng.sample(pob, n):
                sel.append({"tipo_operacion": u, "operacion_id": f["operacion_id"], "estrato": estrato, "poblacion_estrato": len(pob),
                            "probabilidad_inclusion": round(n / len(pob), 6) if pob else None})
    return {"metodo": m["metodo"], "semilla": m["semilla"], "objetivo": sum(sum(v.values()) for v in m["por_universo"].values()),
            "seleccionadas": len(sel), "deficit_alertadas_reasignado": reasignadas, "operaciones": sorted(sel, key=lambda s: (s["tipo_operacion"], s["estrato"], s["operacion_id"])),
            "revisiones_reales": 0, "nota": "Las revisiones humanas se registran en la aplicación; no se inventan revisiones."}


def monitoreo(filas: list[dict], config: Mapping) -> dict:
    out = {}
    for u in UNIVERSOS:
        fs = [f for f in filas if f["tipo_operacion"] == u]
        pts = sorted(f["puntaje"] for f in fs if f["puntaje"] is not None)
        al = sum(f["alerta"] for f in fs)
        out[u] = {"validas": len(fs), "puntuadas": len(pts), "abstenciones": len(fs) - len(pts),
                  "cobertura": round(len(pts) / len(fs), 6) if fs else None, "alertas": al,
                  "alertas_por_100_validas": round(100 * al / len(fs), 4) if fs else None,
                  "distribucion_puntaje": {"p50": round(_percentil(pts, 0.5), 6), "p90": round(_percentil(pts, 0.9), 6), "p99": round(_percentil(pts, 0.99), 6),
                                           "max": round(pts[-1], 6)} if pts else None}
    return {"universos": out, "umbrales": config["monitoreo"]["umbrales"], "nota": config["monitoreo"]["nota"]}


def puntuar_sombra(art: ArtefactoAnomalias, datos, compras: list[dict], config: Mapping, corte: date, salida: str | Path, *,
                   estado_experimento: str, metodos: Mapping[str, str], decision: Mapping | None = None) -> dict:
    """Publica ``anomalias_operaciones`` + ``cobertura_anomalias`` + muestra de revisión en sombra. No entrena ni selecciona:
    usa el artefacto congelado y el método conservado por universo según la decisión de la evaluación."""
    import time
    from contratos.validar import validar_publicacion_sombra
    from .datos import verificar_cobertura_corte
    from .ejecucion import json_bytes, publicar_lote
    t0 = time.perf_counter()
    verificar_cobertura_corte(corte, datos.cobertura)
    cfg = dict(config, **art.config_contexto())
    ops, excl = operaciones(datos.ventas, compras, datos.tasas, cfg)
    ops = [o for o in ops if o["fecha"] <= corte]
    hist = Historial(ops, cfg["contexto"]["ventana_antecedentes"])
    meses = int(config["publicacion"]["meses"])
    t = corte.year * 12 + corte.month - 1 - (meses - 1)
    desde = date(t // 12, t % 12 + 1, 1)
    info = {"revision": datos.revision, "corte": corte.isoformat()}
    filas = [fila_operacion(o, contexto(o, hist, cfg), art, cfg, info, metodos) for o in ops if o["fecha"] >= desde]
    priorizar(filas, art.datos["politica_alertas"])
    filas.sort(key=lambda f: (f["tipo_operacion"], f["periodo"], f["prioridad"] if f["prioridad"] is not None else 10**9, f["operacion_id"]))
    cob = cobertura_filas(filas, excl, desde, corte, cfg)
    muestra = muestra_revision(filas, config, corte.isoformat())
    mon = monitoreo(filas, config)
    metodos = {u: metodos[u] for u in UNIVERSOS}
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": MODELO_ID, "corte": corte.isoformat(), "desde": desde.isoformat(),
           "estado_experimento": estado_experimento, "operativa": False, "advertencia": NOTA,
           "modelo": {"version": art.version, "artefacto_huella": art.huella, "metodos_publicados": metodos,
                      "candidato_por_universo": {u: art.datos["universos"][u]["metodo"] for u in UNIVERSOS},
                      "decision": dict(decision) if decision else None},
           "politica_alertas": art.datos["politica_alertas"],
           "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
           "cobertura": {"corte": corte.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
           "cobertura_por_universo": {"venta": {"estado": "declarada", "hasta": datos.observado_hasta.isoformat()},
                                      "compra": {"estado": "no_declarada", "motivo": config["cobertura"]["compra"]["motivo"]}},
           "emision": {"tipo": "reconstruccion_historica" if all(f["tipo_emision"] == "reconstruccion_historica" for f in filas) else "mixta",
                       "nota": "Operaciones anteriores a la congelación del artefacto: reconstrucción histórica, no emisión prospectiva."},
           "conteos": {u: sum(1 for f in filas if f["tipo_operacion"] == u) for u in UNIVERSOS},
           "monitoreo": mon,
           "tablas": {"anomalias_operaciones": {"filas": len(filas)}, "cobertura_anomalias": {"filas": len(cob)}}}
    errores = validar_publicacion_sombra(man, {"anomalias_operaciones": filas, "cobertura_anomalias": cob, "muestra_revision": muestra})
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato (no se publica): " + "; ".join(errores[:5]))
    publicar_lote(salida, {"anomalias_operaciones.json": json_bytes(filas), "cobertura_anomalias.json": json_bytes(cob),
                           "muestra_revision.json": json_bytes(muestra)}, "manifiesto.json", man,
                  volatiles={"duracion_puntuacion_s": round(time.perf_counter() - t0, 3)})
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas, "cobertura": cob, "muestra": muestra}
