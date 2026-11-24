"""M4 · Venta cruzada (``venta_cruzada``): candidatos elegibles, etiquetas, estadísticas al corte, referencias, artefacto y
ranking de hasta tres productos por cliente. Solo biblioteca estándar (cierre, API y puntuación en sombra no cargan
dependencias de entrenamiento; el ajuste está en ``modelos/venta_cruzada_experimento.py``).

Unidad: cliente × producto × corte C. Los candidatos se construyen ANTES de mirar compras futuras:

* producto disponible al corte (PROXY sintético: alguna venta confirmada de cualquier cliente <= C);
* no comprado por el cliente hasta C inclusive (la recompra y la renovación tienen sus propios recorridos);
* sin cobertura vigente (instalación con ``fecha_inicio <= C <= fecha_fin``; convención de vigencia del proyecto y
  convención sintética de disponibilidad desde ``fecha_inicio``), aunque no haya factura;
* sin incompatibilidad conocida ni requisito incumplido (``config/compatibilidad_productos.json``). Sin regla, la
  compatibilidad queda ``pendiente_revision``; desconocido nunca se convierte en compatible.

Etiqueta: 1 si hay compra confirmada del producto en (C, C+60]; 0 si no y C+60 <= cobertura; pendiente si no.
Estadísticas (popularidad y coocurrencia): acumuladas hasta C, recalculadas en cada fotografía con la misma política
para el modelo y las referencias. Sin calibración: se publica ``puntaje`` y ``probabilidad = null``.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

from .inferencia import _finito, huella_artefacto
from .variables import aplicar_transformaciones

MODELO_ID = "venta_cruzada"
HORIZONTE_DIAS = 60
K = 3
SOPORTE_MINIMO = 10
FORMATO = "jacomind.venta_cruzada_logistica.v1"
RAIZ = Path(__file__).resolve().parents[1]
REGLAS_DEFECTO = RAIZ / "modelos" / "config" / "compatibilidad_productos.json"
VARIABLES_CLIENTE = ["recencia_dias", "dias_compra_distintos", "dias_compra_90d", "dias_compra_180d", "importe_cop_90d", "n_productos"]
VARIABLES_PAR = ["popularidad_rel", "afinidad_max", "coocurrencia_rel"]
VARIABLES_AMPLIADA = ["familia_comprada", "afinidad_x_recencia"]
ORIGENES = ("modelo", "popularidad_sin_soporte", "popularidad", "coocurrencia")
ESTADOS_COMPATIBILIDAD = ("confirmada", "pendiente_revision")
DEFINICION_SOPORTE = "positivos de entrenamiento del producto (pares cliente-producto-corte con compra en 60 días)"


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


# Datos ---------------------------------------------------------------------------------------------------------
def compras_por_cliente(ventas: Iterable[Mapping[str, Any]], tasas) -> dict[str, list[dict]]:
    """Ventas confirmadas por cliente con producto e importe COP (A02; nulo si falta la TRM de su fecha)."""
    from pipeline.operaciones import MissingRateError, calcular_importe
    salida: dict[str, list[dict]] = {}
    for v in ventas:
        if v.get("estado", "Confirmada") != "Confirmada":
            continue
        try:
            imp = round(float(calcular_importe(v, tasas)), 2)
        except MissingRateError:
            imp = None
        salida.setdefault(str(v["cliente_id"]), []).append({"fecha": _d(v["fecha"]), "producto_id": str(v["producto_id"]), "importe_cop": imp,
                                                             "venta_id": str(v.get("venta_id", ""))})
    for c in salida.values():
        c.sort(key=lambda x: (x["fecha"], x["venta_id"]))
    return salida


def instalaciones_por_cliente(instalaciones: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for i in instalaciones:
        out.setdefault(str(i["cliente_id"]), []).append({"instalacion_id": str(i.get("instalacion_id", "")), "producto_id": str(i["producto_id"]),
                                                         "fecha_inicio": _d(i["fecha_inicio"]), "fecha_fin": _d(i["fecha_fin"])})
    return out


def cargar_reglas(ruta: str | Path | None = None) -> dict:
    return json.loads(Path(ruta or REGLAS_DEFECTO).read_text(encoding="utf-8"))


# Estadísticas al corte -------------------------------------------------------------------------------------------
def estadisticas(compras: Mapping[str, list[dict]], corte: date) -> dict:
    """Popularidad y coocurrencia con operaciones <= corte (snapshot de esa fotografía)."""
    conjuntos = {}
    for cid, cs in compras.items():
        s = {c["producto_id"] for c in cs if c["fecha"] <= corte}
        if s:
            conjuntos[cid] = s
    pop: dict[str, int] = {}
    cooc: dict[str, dict[str, int]] = {}
    for s in conjuntos.values():
        for p in s:
            pop[p] = pop.get(p, 0) + 1
            for q in s:
                if q != p:
                    cooc.setdefault(q, {})[p] = cooc.get(q, {}).get(p, 0) + 1
    primera: dict[str, date] = {}
    for cs in compras.values():
        for c in cs:
            if c["fecha"] <= corte and (c["producto_id"] not in primera or c["fecha"] < primera[c["producto_id"]]):
                primera[c["producto_id"]] = c["fecha"]
    return {"corte": corte.isoformat(), "clientes": len(conjuntos), "popularidad": dict(sorted(pop.items())),
            "coocurrencia": {q: dict(sorted(v.items())) for q, v in sorted(cooc.items())},
            "catalogo_disponible": {p: f.isoformat() for p, f in sorted(primera.items())}}


VENTANA_TRANSICION = 60
SUAVIZADO_TRANSICION = 20


def transiciones(compras: Mapping[str, list[dict]], corte: date, ventana: int = VENTANA_TRANSICION) -> dict:
    """M4.1 · Estadísticas de secuencia con información MADURA al corte: para cada día t en que un cliente compró q, con
    t + ventana <= corte, cuenta si compró después cada producto p que aún no tenía en t, dentro de (t, t + ventana].
    Devuelve base[p] (tasa sin condicionar) y, por q, (eventos, compras de p). Nada posterior al corte entra."""
    eventos: dict[str, dict[str, list[int]]] = {}
    base: dict[str, list[int]] = {}
    catalogo = {c["producto_id"] for cs in compras.values() for c in cs if c["fecha"] <= corte}  # solo productos conocidos al corte
    for cs in compras.values():
        dias = sorted({c["fecha"] for c in cs if c["fecha"] + timedelta(days=ventana) <= corte})
        for t in dias:
            tenia = {c["producto_id"] for c in cs if c["fecha"] <= t}
            hoy = {c["producto_id"] for c in cs if c["fecha"] == t}
            despues = {c["producto_id"] for c in cs if t < c["fecha"] <= t + timedelta(days=ventana)}
            for p in catalogo:
                if p in tenia:
                    continue
                b = base.setdefault(p, [0, 0])
                b[0] += 1; b[1] += int(p in despues)
                for q in hoy:
                    e = eventos.setdefault(q, {}).setdefault(p, [0, 0])
                    e[0] += 1; e[1] += int(p in despues)
    return {"corte": corte.isoformat(), "ventana": ventana, "base": {p: v for p, v in sorted(base.items())},
            "eventos": {q: dict(sorted(v.items())) for q, v in sorted(eventos.items())}}


def transicion_reciente(compras_cliente: list[dict], producto: str, trans: dict, corte: date, m: int = SUAVIZADO_TRANSICION) -> float:
    """Máximo, sobre los productos q comprados en los últimos ``ventana`` días, de (compras + m·base) / (eventos + m)."""
    b = trans["base"].get(producto, [0, 0])
    tasa_base = b[1] / b[0] if b[0] else 0.0
    recientes = {c["producto_id"] for c in compras_cliente if 0 <= (corte - c["fecha"]).days < trans["ventana"]}
    valores = [(e[1] + m * tasa_base) / (e[0] + m) for q in recientes for e in [trans["eventos"].get(q, {}).get(producto, [0, 0])]]
    return max(valores, default=tasa_base)


# Compatibilidad -----------------------------------------------------------------------------------------------------
def compatibilidad(producto: str, tenencia: set[str], reglas: Mapping[str, Any]) -> tuple[str, str | None]:
    """(``excluido`` | ``confirmada`` | ``pendiente_revision``, motivo). Incompatibilidad o requisito conocido excluye."""
    for r in reglas.get("reglas", []):
        t = r.get("tipo")
        if t == "incompatible" and ((r["producto"] == producto and r["con"] in tenencia) or (r["con"] == producto and r["producto"] in tenencia)):
            otro = r["con"] if r["producto"] == producto else r["producto"]
            return "excluido", f"incompatible con {otro} ({r.get('evidencia', 'sin evidencia registrada')})"
        if t == "requiere" and r["producto"] == producto and not (set(r["requiere_alguno"]) & tenencia):
            return "excluido", f"requisito incumplido: requiere alguno de {', '.join(r['requiere_alguno'])} ({r.get('evidencia', '')})"
    if any(r.get("tipo") == "compatible_confirmado" and r["producto"] == producto for r in reglas.get("reglas", [])):
        return "confirmada", None
    return "pendiente_revision", None


def candidatos_cliente(cid: str, compras: list[dict], instalaciones: list[dict], stats: dict, catalogo: Iterable[str],
                       reglas: Mapping[str, Any], corte: date) -> dict:
    """Candidatos y exclusiones (con motivo) del cliente al corte; usa solo información <= corte."""
    comprados = {c["producto_id"] for c in compras if c["fecha"] <= corte}
    cubiertos = {i["producto_id"]: i for i in instalaciones if i["fecha_inicio"] <= corte <= i["fecha_fin"]}
    tenencia = comprados | set(cubiertos)
    disponibles = set(stats["catalogo_disponible"])
    cand, excl = [], []
    for p in sorted(set(catalogo) | disponibles):
        if p not in disponibles:
            excl.append({"producto_id": p, "motivo": "no_disponible_al_corte"})
        elif p in comprados:
            excl.append({"producto_id": p, "motivo": "ya_comprado"})
        elif p in cubiertos:
            excl.append({"producto_id": p, "motivo": "cobertura_vigente", "instalacion_id": cubiertos[p]["instalacion_id"],
                         "fecha_fin": cubiertos[p]["fecha_fin"].isoformat()})
        else:
            estado, motivo = compatibilidad(p, tenencia, reglas)
            if estado == "excluido":
                excl.append({"producto_id": p, "motivo": "incompatible_o_requisito", "detalle": motivo})
            else:
                cand.append({"producto_id": p, "estado_compatibilidad": estado})
    return {"cliente_id": cid, "comprados": sorted(comprados), "cubiertos": sorted(cubiertos), "candidatos": cand, "exclusiones": excl}


def etiqueta(compras: list[dict], producto: str, corte: date, observado_hasta: date | None) -> int | None:
    fin = corte + timedelta(days=HORIZONTE_DIAS)
    if observado_hasta is None or fin > observado_hasta:
        return None
    return int(any(c["producto_id"] == producto and corte < c["fecha"] <= fin for c in compras))


# Variables ------------------------------------------------------------------------------------------------------------
def variables_cliente(compras: list[dict], corte: date) -> dict | None:
    obs = [c for c in compras if c["fecha"] <= corte]
    if not obs:
        return None
    dias = sorted({c["fecha"] for c in obs})
    edad = [(corte - x).days for x in dias]
    ventana = [c for c in obs if (corte - c["fecha"]).days < 90]
    importe = None if any(c["importe_cop"] is None for c in ventana) else sum(c["importe_cop"] for c in ventana)
    return {"recencia_dias": (corte - dias[-1]).days, "dias_compra_distintos": len(dias), "dias_compra_90d": sum(a < 90 for a in edad),
            "dias_compra_180d": sum(a < 180 for a in edad), "importe_cop_90d": importe, "n_productos": len({c["producto_id"] for c in obs})}


def variables_par(vc: dict, producto: str, comprados: list[str], stats: dict, familias: Mapping[str, str] | None = None) -> dict:
    n = max(stats["clientes"], 1)
    pop = stats["popularidad"].get(producto, 0)
    cooc = stats["coocurrencia"]
    afin = max((cooc.get(q, {}).get(producto, 0) / stats["popularidad"][q] for q in comprados if stats["popularidad"].get(q)), default=0.0)
    suma = sum(cooc.get(q, {}).get(producto, 0) for q in comprados)
    fam = familias or {}
    return vc | {"producto_id": producto, "popularidad_rel": pop / n, "afinidad_max": afin, "coocurrencia_rel": suma / n, "coocurrencia_suma": suma,
                 "popularidad": pop, "familia_comprada": int(bool(fam.get(producto)) and fam.get(producto) in {fam.get(q) for q in comprados}),
                 "afinidad_x_recencia": afin * math.log1p(vc["recencia_dias"])}


# Referencias y ranking --------------------------------------------------------------------------------------------------
def ordenar(pares: list[dict], clave) -> list[dict]:
    """Orden descendente por clave y desempate por producto_id ascendente; sin duplicados."""
    unicos = {p["producto_id"]: p for p in pares}
    return sorted(unicos.values(), key=lambda p: (-clave(p), p["producto_id"]))


def ranking_referencia(pares: list[dict], metodo: str, k: int = K) -> list[dict]:
    clave = (lambda p: p["popularidad"]) if metodo == "popularidad" else (lambda p: (p["coocurrencia_suma"], p["popularidad"]))
    if metodo == "coocurrencia":
        unicos = {p["producto_id"]: p for p in pares}
        orden = sorted(unicos.values(), key=lambda p: (-p["coocurrencia_suma"], -p["popularidad"], p["producto_id"]))
    else:
        orden = ordenar(pares, clave)
    return [dict(p, origen=metodo, puntaje=float(p["popularidad_rel"] if metodo == "popularidad" else p["coocurrencia_rel"])) for p in orden[:k]]


# Artefacto -----------------------------------------------------------------------------------------------------------------
def validar_artefacto_vc(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") != FORMATO:
        e.append("formato incompatible")
    if d.get("modelo_id") != MODELO_ID:
        e.append(f"modelo_id {d.get('modelo_id')!r} distinto de {MODELO_ID}")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if d.get("horizonte_dias") != HORIZONTE_DIAS:
        e.append("horizonte_dias distinto de 60")
    if d.get("umbral") is not None:
        e.append("umbral debe ser nulo (ranking por cupo)")
    vs, tr, w = d.get("variables"), d.get("transformaciones"), d.get("pesos")
    if not isinstance(vs, list) or not isinstance(tr, list) or not isinstance(w, list) or not (len(vs) == len(tr) == len(w)):
        e.append("variables, transformaciones y pesos deben tener la misma dimensión")
    elif not all(_finito(x) for x in w) or any(not isinstance(t, dict) or t.get("variable") != v for t, v in zip(tr, vs)):
        e.append("pesos no finitos o transformaciones desalineadas")
    wp = d.get("pesos_producto")
    if not isinstance(wp, dict) or not all(_finito(x) for x in wp.values()):
        e.append("pesos_producto debe ser un objeto de pesos finitos")
    if not _finito(d.get("intercepto")):
        e.append("intercepto no finito")
    sop = d.get("soporte")
    if not isinstance(sop, dict) or not all(isinstance(v, dict) and isinstance(v.get("positivos"), int) for v in sop.values()):
        e.append("soporte por producto obligatorio")
    if not isinstance(d.get("soporte_minimo"), int) or d["soporte_minimo"] < 1:
        e.append("soporte_minimo entero >= 1")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoVentaCruzada:
    datos: dict

    version = property(lambda self: self.datos["version"])
    modelo_id = property(lambda self: self.datos["modelo_id"])
    huella = property(lambda self: self.datos["huella"])
    umbral = property(lambda self: None)
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))
    version_variables = property(lambda self: self.datos.get("version_variables"))

    def puntaje(self, par: Mapping[str, Any]) -> float:
        """Logit sin calibrar (no es una probabilidad): intercepto + pesos·variables escaladas + peso del producto."""
        z = aplicar_transformaciones(par, self.datos["transformaciones"])
        return float(self.datos["intercepto"]) + sum(w * x for w, x in zip(self.datos["pesos"], z)) + float(self.datos["pesos_producto"].get(par["producto_id"], 0.0))

    def con_soporte(self, producto: str) -> bool:
        return (self.datos["soporte"].get(producto) or {}).get("positivos", 0) >= self.datos["soporte_minimo"]

    def probabilidad(self, par):  # interfaz común: este modelo no publica probabilidad sin calibración validada
        raise TypeError("venta_cruzada publica un puntaje de ranking; la probabilidad es nula sin calibración validada")


def ranking_modelo(art: ArtefactoVentaCruzada, pares: list[dict], k: int = K) -> list[dict]:
    """Primero los candidatos con soporte por puntaje; después los sin soporte por popularidad (orden lexicográfico)."""
    unicos = {p["producto_id"]: p for p in pares}
    aprendidos = sorted((dict(p, puntaje=art.puntaje(p), origen="modelo") for p in unicos.values() if art.con_soporte(p["producto_id"])),
                        key=lambda p: (-p["puntaje"], p["producto_id"]))
    resto = sorted((dict(p, puntaje=float(p["popularidad_rel"]), origen="popularidad_sin_soporte") for p in unicos.values()
                    if not art.con_soporte(p["producto_id"])), key=lambda p: (-p["popularidad"], p["producto_id"]))
    return (aprendidos + resto)[:k]


# Publicación ---------------------------------------------------------------------------------------------------------------
def _motivos(p: dict, nombres: Mapping[str, str], stats: dict) -> list[str]:
    m = [f"{p['popularidad']} de {stats['clientes']} clientes con historial compraron {nombres.get(p['producto_id'], p['producto_id'])} hasta el corte"]
    if p["coocurrencia_suma"]:
        m.append(f"Afinidad con lo que ya tiene: hasta {p['afinidad_max']:.0%} de quienes compraron uno de sus productos también compraron este")
    else:
        m.append("Ningún cliente con sus productos compró también este hasta el corte")
    if p["estado_compatibilidad"] == "pendiente_revision":
        m.append("Compatibilidad por revisar: no hay reglas empresariales para este producto")
    return m


def recomendaciones(art: ArtefactoVentaCruzada | None, clientes: Iterable[Mapping[str, Any]], compras: Mapping[str, list[dict]],
                    instalaciones: Mapping[str, list[dict]], catalogo: Mapping[str, Mapping[str, Any]], reglas: Mapping[str, Any],
                    corte: date, metodo: str = "modelo") -> tuple[list[dict], list[dict]]:
    """(filas de ``recomendaciones_productos``, informe ``cobertura_recomendaciones``) del corte. Sin filas ficticias."""
    stats = estadisticas(compras, corte)
    nombres = {p: str(v.get("nombre_prueba", p)) for p, v in catalogo.items()}
    familias = {p: str(v.get("familia_prueba", "")) for p, v in catalogo.items()}
    filas, cobertura = [], []
    extra_m41 = bool(art) and metodo == "modelo" and "transicion_reciente" in art.datos.get("variables", [])
    trans = transiciones(compras, corte) if extra_m41 else None
    for cl in sorted(clientes, key=lambda c: str(c["cliente_id"])):
        cid = str(cl["cliente_id"])
        base = {"cliente_id": cid, "modelo_id": MODELO_ID, "corte": corte.isoformat()}
        if _d(cl["fecha_alta"]) > corte:
            cobertura.append(base | {"estado": "no_elegible", "motivo": "Alta posterior al corte", "n_candidatos": 0, "n_recomendaciones": 0, "exclusiones": []})
            continue
        vc = variables_cliente(compras.get(cid, []), corte)
        if vc is None:
            cobertura.append(base | {"estado": "sin_historial", "motivo": "Sin compras confirmadas hasta el corte", "n_candidatos": 0, "n_recomendaciones": 0, "exclusiones": []})
            continue
        info = candidatos_cliente(cid, compras.get(cid, []), instalaciones.get(cid, []), stats, catalogo, reglas, corte)
        pares = [variables_par(vc, c["producto_id"], info["comprados"], stats, familias) | {"estado_compatibilidad": c["estado_compatibilidad"]}
                 for c in info["candidatos"]]
        if extra_m41:  # M4.1: antigüedad y secuencia reciente (solo para esos artefactos; M4 no cambia)
            pares = [p | {"antiguedad_dias": (corte - _d(cl["fecha_alta"])).days,
                          "transicion_reciente": transicion_reciente(compras.get(cid, []), p["producto_id"], trans, corte)} for p in pares]
        if not pares:
            motivos = sorted({e["motivo"] for e in info["exclusiones"]})
            cobertura.append(base | {"estado": "sin_candidatos", "motivo": "Todos los productos están comprados, cubiertos, excluidos o no disponibles: " + ", ".join(motivos),
                                     "n_candidatos": 0, "n_recomendaciones": 0, "exclusiones": info["exclusiones"]})
            continue
        lista = ranking_modelo(art, pares) if metodo == "modelo" else ranking_referencia(pares, metodo)
        version = art.version if metodo == "modelo" else version_referencia(metodo, reglas)
        for pos, p in enumerate(lista, 1):
            sop = (art.datos["soporte"].get(p["producto_id"]) or {}).get("positivos", 0) if metodo == "modelo" else p["popularidad"]
            filas.append(base | {"producto_id": p["producto_id"], "producto_nombre": nombres.get(p["producto_id"], p["producto_id"]), "horizonte_dias": HORIZONTE_DIAS,
                                 "version_modelo": version, "posicion": pos, "puntaje": round(float(p["puntaje"]), 9),
                                 "probabilidad": None, "origen_recomendacion": p["origen"], "soporte": int(sop),
                                 "definicion_soporte": DEFINICION_SOPORTE if metodo == "modelo" else "clientes distintos con compra del producto hasta el corte",
                                 "estado": "propuesta", "estado_compatibilidad": p["estado_compatibilidad"], "motivos": _motivos(p, nombres, stats),
                                 "evidencia": {"popularidad": p["popularidad"], "clientes_con_historial": stats["clientes"], "coocurrencia_suma": p["coocurrencia_suma"],
                                               "afinidad_max": round(p["afinidad_max"], 6), "productos_del_cliente": info["comprados"], "corte_estadisticas": stats["corte"]},
                                 "version_reglas": reglas.get("version"), "version_catalogo": "primera-venta-observada-v1"})
        cobertura.append(base | {"estado": "con_recomendaciones", "motivo": None, "n_candidatos": len(pares), "n_recomendaciones": len(lista),
                                 "exclusiones": info["exclusiones"]})
    return filas, cobertura


def version_referencia(metodo: str, reglas: Mapping[str, Any]) -> str:
    return f"venta_cruzada-{metodo}-filtrada-{reglas.get('version')}"


def muestra_revision(filas: list[dict], catalogo: Mapping[str, Mapping[str, Any]], n: int = 30, semilla: int = 20261123) -> dict:
    """Muestra reproducible de pares para revisión de Ventas, repartida entre familias y terciles de puntaje (todos si hay menos)."""
    import random
    familias = {p: str(v.get("familia_prueba", "")) for p, v in catalogo.items()}
    orden = sorted(filas, key=lambda f: (f["puntaje"], f["cliente_id"], f["producto_id"]))
    tercil = {(f["cliente_id"], f["producto_id"]): min(2, i * 3 // max(len(orden), 1)) for i, f in enumerate(orden)}
    estratos: dict[tuple, list[dict]] = {}
    for f in sorted(filas, key=lambda f: (f["cliente_id"], f["producto_id"])):
        estratos.setdefault((familias.get(f["producto_id"], ""), tercil[(f["cliente_id"], f["producto_id"])]), []).append(f)
    rng = random.Random(semilla)
    for v in estratos.values():
        rng.shuffle(v)
    elegidos, claves = [], sorted(estratos)
    while len(elegidos) < min(n, len(filas)):
        for k in claves:
            if estratos[k] and len(elegidos) < n:
                elegidos.append(estratos[k].pop())
    pares = [{"cliente_id": f["cliente_id"], "producto_id": f["producto_id"], "posicion": f["posicion"], "puntaje": f["puntaje"],
              "familia": familias.get(f["producto_id"], ""), "tercil_puntaje": tercil[(f["cliente_id"], f["producto_id"])] + 1,
              "version_propuesta": f["version_modelo"]} for f in elegidos]
    return {"semilla": semilla, "tamano_objetivo": n, "universo": f"{len(filas)} recomendaciones publicadas del corte",
            "criterio": "reparto circular entre estratos familia (convención de catálogo) × tercil de puntaje, orden aleatorio con semilla dentro de cada estrato",
            "estados": ["pertinente", "ya_cubierto", "incompatible", "sin_necesidad", "informacion_insuficiente"], "pares": pares,
            "nota": "Las revisiones son humanas: no se generan automáticamente. Los fixtures de prueba solo prueban el flujo."}


def puntuar_sombra(art: ArtefactoVentaCruzada, datos, corte: date, salida: str | Path, *, estado_experimento: str,
                   decision: Mapping[str, Any] | None = None, reglas: Mapping[str, Any] | None = None, con_muestra: bool = True,
                   metodo: str = "modelo", simulacion_historica: bool = False) -> dict:
    """Publica ``recomendaciones_productos`` + ``cobertura_recomendaciones`` (+ muestra de revisión) en un directorio de SOMBRA."""
    from contratos.validar import validar_publicacion_sombra
    from pipeline.operaciones import _load
    from .datos import verificar_cobertura_corte
    from .ejecucion import json_bytes, publicar_lote
    if art.modelo_id != MODELO_ID:
        raise ValueError(f"El artefacto {art.version} no es de {MODELO_ID}")
    if corte < art.disponible_desde and not simulacion_historica:
        raise ValueError(f"{art.version} está disponible desde {art.disponible_desde}")
    verificar_cobertura_corte(corte, datos.cobertura)
    reglas = reglas or cargar_reglas()
    compras = compras_por_cliente(datos.ventas, datos.tasas)
    inst = instalaciones_por_cliente(_load(datos.directorio, "base_instalada.csv", "instalaciones"))
    filas, cobertura = recomendaciones(art, datos.clientes, compras, inst, datos.productos, reglas, corte, metodo)
    muestra = muestra_revision(filas, datos.productos) if con_muestra else None
    conteo = {}
    for c in cobertura:
        conteo[c["estado"]] = conteo.get(c["estado"], 0) + 1
    archivos = {"recomendaciones_productos.json": json_bytes(filas), "cobertura_recomendaciones.json": json_bytes(cobertura)}
    tablas = {"recomendaciones_productos": {"archivo": "recomendaciones_productos.json", "filas": len(filas)},
              "cobertura_recomendaciones": {"archivo": "cobertura_recomendaciones.json", "filas": len(cobertura)}}
    if muestra is not None:
        archivos["muestra_revision.json"] = json_bytes(muestra)
    manifiesto = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": MODELO_ID, "corte": corte.isoformat(),
                  "estado_experimento": estado_experimento, "operativa": False,
                  "advertencia": "Recomendaciones experimentales en sombra para revisión de Ventas: no son ofertas ni tareas, y una compra posterior no prueba su efecto.",
                  "simulacion_historica": simulacion_historica,
                  "modelo": {"version": art.version if metodo == "modelo" else version_referencia(metodo, reglas), "artefacto_huella": art.huella,
                             "sistema_publicado": metodo, "candidato_congelado": art.version, "horizonte_dias": HORIZONTE_DIAS, "k": K,
                             "decision": dict(decision) if decision else None},
                  "versiones": {"reglas": reglas.get("version"), "catalogo": "primera-venta-observada-v1"},
                  "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
                  "cobertura": {"corte": corte.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
                  "conteos": conteo, "tablas": tablas}
    errores = validar_publicacion_sombra(manifiesto, {"recomendaciones_productos": filas, "cobertura_recomendaciones": cobertura})
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato: " + "; ".join(errores[:5]))
    publicar_lote(salida, archivos, "manifiesto.json", manifiesto)
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas, "cobertura": cobertura}
