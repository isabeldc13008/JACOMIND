"""M3 · Próxima compra (``proxima_compra``): tiempo residual hasta la próxima compra confirmada desde el corte.

Solo biblioteca estándar: el cierre, la API y la puntuación en sombra importan este módulo sin dependencias de
entrenamiento. El ajuste (Cox con scikit-survival) y la evaluación están en ``modelos/proxima_compra_experimento.py``.

Pregunta: «Desde este cierre, ¿cuánto tiempo podría faltar hasta la próxima compra confirmada?». No es abandono, ni
vencimiento de coberturas, ni probabilidad de compra a 30 días, ni duración media de un intervalo completo.

Fotografía (cliente, corte C), elegible si alta <= C y tiene al menos una compra confirmada <= C. Con H = 60 y D la
fecha hasta la que se conoce el seguimiento EN ESE AJUSTE O EVALUACIÓN:

* ``fin_seguimiento = min(C + H, D)``. Con seguimiento de cero días (``fin <= C``) la fila se excluye.
* Si hay compra en ``(C, fin]`` → ``evento = 1`` y ``duracion`` = días hasta la primera. Si no → ``evento = 0`` y
  ``duracion = fin − C`` (censura administrativa). Las compras posteriores a ``D`` no existen para esa fila.
* Las compras del mismo día cuentan como un día de compra; una compra el día C pertenece al historial.

Curvas S(t) en días enteros 0..T (T = soporte del ajuste, <= H): S(0) = 1, no creciente, en [0, 1]; fuera del
soporte no se extrapola. Cuantil q = primer t del soporte con 1 − S(t) >= q; si no se alcanza, nulo.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping

from .inferencia import _finito, aplicar_transformaciones, huella_artefacto
from .variables import VERSION_PROXIMA, variables_inactividad

MODELO_ID = "proxima_compra"
HORIZONTE_DIAS = 60
FORMATO = "jacomind.supervivencia_residual.v1"
CUANTILES = (0.1, 0.5, 0.9)
ANCHO_MAXIMO_VENTANA = 30
TOL_CUANTIL = 1e-12
ESTADOS_ESTIMACION = ("estimado", "estimacion_parcial")
GRUPOS = ("reciente", "habitual", "ocasional", "frio")
REGLA_NIVEL = "ultimos_cortes_maduros"
TIPOS_COX = ("cox", "cox_estratificado")


def _d(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def dias_de_compra(compras: Iterable[Mapping[str, Any]], hasta: date | None = None) -> list[date]:
    return sorted({c["fecha"] for c in compras if hasta is None or c["fecha"] <= hasta})


def grupo(recencia: int, dias_distintos: int) -> str:
    if recencia >= 90:
        return "frio"
    if dias_distintos < 3:
        return "ocasional"
    return "reciente" if recencia < 30 else "habitual"


# Referencia personal --------------------------------------------------------------------------------------
def referencia_personal(intervalos: list[int], recencia: int) -> dict[str, Any]:
    """Mediana de >= 2 intervalos positivos menos la recencia. <= 0 → vencida (sin desplazarla); < 2 → insuficiente."""
    positivos = [i for i in intervalos if i > 0]
    if len(positivos) < 2:
        return {"estado": "insuficiente", "dias": None, "mediana_intervalos": None}
    med = median(positivos)
    resto = med - recencia
    resto = int(resto) if float(resto).is_integer() else resto
    return {"estado": "disponible" if resto > 0 else "vencida", "dias": resto, "mediana_intervalos": med}


# Seguimiento censurado -------------------------------------------------------------------------------------
def seguimiento(compras: list[Mapping[str, Any]], corte: date, hasta: date, horizonte: int = HORIZONTE_DIAS) -> dict[str, Any]:
    """{evento, duracion, fin_seguimiento, fecha_evento} o ``None`` si el seguimiento es de cero días."""
    fin = min(corte + timedelta(days=horizonte), hasta)
    if fin <= corte:
        return None
    siguiente = next((d for d in dias_de_compra(compras) if corte < d <= fin), None)
    if siguiente is not None:
        return {"evento": 1, "duracion": (siguiente - corte).days, "fin_seguimiento": fin.isoformat(), "fecha_evento": siguiente.isoformat()}
    return {"evento": 0, "duracion": (fin - corte).days, "fin_seguimiento": fin.isoformat(), "fecha_evento": None}


def fotografias(clientes: Iterable[Mapping[str, Any]], historial: Mapping[str, list[Mapping[str, Any]]], cortes: Iterable[date],
                hasta: date, observado_hasta: date) -> tuple[list[dict], dict]:
    """Filas elegibles con seguimiento positivo y conteo de exclusiones por corte."""
    if hasta > observado_hasta:
        raise ValueError(f"El seguimiento hasta {hasta} supera la cobertura declarada {observado_hasta}")
    filas, excl = [], {}
    for corte in cortes:
        e = excl.setdefault(corte.isoformat(), {"alta_posterior": 0, "sin_historial": 0, "seguimiento_cero": 0})
        for cl in sorted(clientes, key=lambda c: str(c["cliente_id"])):
            cid = str(cl["cliente_id"])
            if cl["fecha_alta"] > corte:
                e["alta_posterior"] += 1
                continue
            compras = historial.get(cid, [])
            v = variables_inactividad(compras, corte)
            if v is None:
                e["sin_historial"] += 1
                continue
            s = seguimiento(compras, corte, hasta)
            if s is None:
                e["seguimiento_cero"] += 1
                continue
            dias = dias_de_compra(compras, corte)
            intervalos = [(b - a).days for a, b in zip(dias, dias[1:])]
            ref = referencia_personal(intervalos, v["recencia_dias"])
            filas.append({"cliente_id": cid, "corte": corte, **v, **s, "grupo": grupo(v["recencia_dias"], v["dias_compra_distintos"]),
                          "ref_personal_estado": ref["estado"], "ref_personal_dias": ref["dias"], "seguimiento_hasta": hasta.isoformat()})
    return filas, excl


# Kaplan–Meier (biblioteca estándar) ----------------------------------------------------------------------
def kaplan_meier(duraciones: list[int], eventos: list[int]) -> tuple[list[int], list[float]]:
    """Curva escalonada en los tiempos de evento; los censurados en t salen del riesgo después de los eventos en t."""
    ev: dict[int, int] = {}
    sal: dict[int, int] = {}
    for t, e in zip(duraciones, eventos):
        sal[t] = sal.get(t, 0) + 1
        if e:
            ev[t] = ev.get(t, 0) + 1
    riesgo, s, tiempos, valores = len(duraciones), 1.0, [], []
    for t in sorted(sal):
        d = ev.get(t, 0)
        if d and riesgo > 0:
            s *= 1 - d / riesgo
            tiempos.append(t)
            valores.append(s)
        riesgo -= sal[t]
    return tiempos, valores


def escalon(t: float, tiempos: list[float], valores: list[float], inicial: float) -> float:
    """Valor de una función escalonada continua por la derecha en ``t`` (``inicial`` antes del primer salto)."""
    lo, hi, r = 0, len(tiempos) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if tiempos[mid] <= t:
            r, lo = mid, mid + 1
        else:
            hi = mid - 1
    return inicial if r is None else valores[r]


# Curvas y cuantiles ----------------------------------------------------------------------------------------
def cuantil(curva: list[float], q: float) -> int | None:
    """Primer día t >= 1 del soporte (índices de ``curva``) con 1 − S(t) >= q; ``None`` si no se alcanza."""
    for t in range(1, len(curva)):
        if 1 - curva[t] >= q - TOL_CUANTIL:
            return t
    return None


def validar_curva(curva: list[float]) -> list[str]:
    e = []
    if not curva or curva[0] != 1.0:
        e.append("S(0) debe ser 1")
    if not all(_finito(x) and 0 <= x <= 1 for x in curva):
        e.append("S(t) fuera de [0, 1] o no finita")
    if any(b > a + 1e-15 for a, b in zip(curva, curva[1:])):
        e.append("S(t) crece en algún tramo")
    return e


def validar_artefacto_pc(d: dict) -> list[str]:
    e: list[str] = []
    if d.get("formato") != FORMATO:
        e.append(f"formato {d.get('formato')!r} incompatible")
    if d.get("modelo_id") != MODELO_ID:
        e.append(f"modelo_id {d.get('modelo_id')!r} distinto de {MODELO_ID}")
    if not isinstance(d.get("version"), str) or not d.get("version"):
        e.append("version ausente")
    if d.get("version_variables") != VERSION_PROXIMA:
        e.append(f"version_variables debe ser {VERSION_PROXIMA}")
    if d.get("horizonte_dias") != HORIZONTE_DIAS:
        e.append(f"horizonte_dias {d.get('horizonte_dias')!r} distinto de {HORIZONTE_DIAS}")
    T = d.get("soporte_dias")
    if not isinstance(T, int) or isinstance(T, bool) or not 1 <= T <= HORIZONTE_DIAS:
        e.append("soporte_dias debe ser un entero en [1, horizonte]")
    if d.get("umbral") is not None:
        e.append("umbral debe ser nulo")
    if d.get("tipo") == "km":
        km = d.get("km") or {}
        t, s = km.get("tiempos"), km.get("supervivencia")
        if not isinstance(t, list) or not isinstance(s, list) or len(t) != len(s):
            e.append("km: tiempos y supervivencia deben ser listas de igual longitud")
        elif any(not isinstance(x, int) or x < 1 for x in t) or any(b <= a for a, b in zip(t, t[1:])) or \
                not all(_finito(x) and 0 <= x <= 1 for x in s) or any(b > a for a, b in zip(s, s[1:])):
            e.append("km: tiempos crecientes >= 1 y supervivencia no creciente en [0, 1]")
    elif d.get("tipo") == "cox":
        c = d.get("cox") or {}
        vs, tr, w = c.get("variables"), c.get("transformaciones"), c.get("coeficientes")
        if not isinstance(vs, list) or not isinstance(tr, list) or not isinstance(w, list) or not (len(vs) == len(tr) == len(w)) or not vs:
            e.append("cox: variables, transformaciones y coeficientes deben tener la misma dimensión")
        elif not all(_finito(x) for x in w) or any(not isinstance(t_, dict) or t_.get("variable") != v for t_, v in zip(tr, vs)):
            e.append("cox: coeficientes no finitos o transformaciones desalineadas")
        tb, hb = c.get("tiempos_base"), c.get("riesgo_acumulado_base")
        if not isinstance(tb, list) or not isinstance(hb, list) or len(tb) != len(hb) or not tb:
            e.append("cox: tiempos_base y riesgo_acumulado_base deben ser listas no vacías de igual longitud")
        elif any(b <= a for a, b in zip(tb, tb[1:])) or tb[0] < 1 or not all(_finito(x) and x >= 0 for x in hb) or any(b < a for a, b in zip(hb, hb[1:])):
            e.append("cox: tiempos base crecientes >= 1 y riesgo acumulado no decreciente >= 0")
    elif d.get("tipo") == "cox_estratificado":  # M3.1: coeficientes comunes y curva base de Breslow por grupo
        c = d.get("cox") or {}
        vs, tr, w = c.get("variables"), c.get("transformaciones"), c.get("coeficientes")
        if not isinstance(vs, list) or not isinstance(tr, list) or not isinstance(w, list) or not (len(vs) == len(tr) == len(w)) or not vs \
                or not all(_finito(x) for x in w) or any(not isinstance(t_, dict) or t_.get("variable") != v for t_, v in zip(tr, vs)):
            e.append("cox_estratificado: variables, transformaciones y coeficientes inválidos")
        est = c.get("estratos")
        if c.get("variable_estrato") != "grupo" or not isinstance(est, dict) or not est or any(g not in GRUPOS for g in est):
            e.append(f"cox_estratificado: estratos por 'grupo' ({', '.join(GRUPOS)}) obligatorios")
        else:
            for g, b in est.items():
                tb, hb = (b or {}).get("tiempos_base"), (b or {}).get("riesgo_acumulado_base")
                if not isinstance(tb, list) or not isinstance(hb, list) or len(tb) != len(hb) or not tb or any(y <= x for x, y in zip(tb, tb[1:])) \
                        or tb[0] < 1 or not all(_finito(x) and x >= 0 for x in hb) or any(y < x for x, y in zip(hb, hb[1:])):
                    e.append(f"cox_estratificado: curva base del estrato {g} inválida")
    else:
        e.append("tipo debe ser 'km', 'cox' o 'cox_estratificado'")
    nv = d.get("nivel")
    if nv is not None and (d.get("tipo") != "cox" or not isinstance(nv, dict) or nv.get("regla") != REGLA_NIVEL
                           or not isinstance(nv.get("cortes"), int) or not 1 <= nv["cortes"] <= 12):
        e.append(f"nivel: solo para tipo 'cox', con regla {REGLA_NIVEL!r} y cortes entre 1 y 12")
    v = d.get("ventana")
    if v is not None and (not isinstance(v, dict) or v.get("limites") not in (["p10", "p90"], ["p10", "p50"])
                          or not isinstance(v.get("ancho_maximo_dias"), int) or v["ancho_maximo_dias"] < 1):
        e.append("ventana: limites ['p10','p90'] o ['p10','p50'] y ancho_maximo_dias entero >= 1")
    pa = d.get("probabilidades_acumuladas_dias")
    if pa is not None and (not isinstance(pa, list) or not all(isinstance(t, int) and 1 <= t <= (T if isinstance(T, int) else 0) for t in pa)):
        e.append("probabilidades_acumuladas_dias: días enteros dentro del soporte")
    try:
        date.fromisoformat(str(d.get("disponible_desde")))
    except ValueError:
        e.append("disponible_desde no es una fecha ISO")
    if d.get("huella") != huella_artefacto(d):
        e.append("huella no coincide con el contenido (artefacto alterado)")
    return e


@dataclass(frozen=True)
class ArtefactoProxima:
    datos: dict

    version = property(lambda self: self.datos["version"])
    modelo_id = property(lambda self: self.datos["modelo_id"])
    version_variables = property(lambda self: self.datos["version_variables"])
    umbral = property(lambda self: None)
    huella = property(lambda self: self.datos["huella"])
    disponible_desde = property(lambda self: date.fromisoformat(self.datos["disponible_desde"]))
    soporte = property(lambda self: int(self.datos["soporte_dias"]))
    tipo = property(lambda self: self.datos["tipo"])

    def predictor_lineal(self, fila: Mapping[str, Any]) -> float:
        if self.tipo not in TIPOS_COX:
            return 0.0
        c = self.datos["cox"]
        return sum(w * x for w, x in zip(c["coeficientes"], aplicar_transformaciones(fila, c["transformaciones"])))

    def curva(self, fila: Mapping[str, Any]) -> list[float]:
        """S(t) para t = 0..soporte (días enteros)."""
        T = self.soporte
        if self.tipo == "km":
            km = self.datos["km"]
            return [escalon(t, km["tiempos"], km["supervivencia"], 1.0) for t in range(T + 1)]
        tb, hb = self._base(fila)
        if tb is None:
            return []  # estrato sin curva base: sin soporte (validar_curva lo rechaza)
        r = math.exp(max(-50.0, min(50.0, self.predictor_lineal(fila)))) * self.factor(fila)
        return [math.exp(-escalon(t, tb, hb, 0.0) * r) for t in range(T + 1)]

    def _base(self, fila: Mapping[str, Any]):
        c = self.datos["cox"]
        if self.tipo == "cox":
            return c["tiempos_base"], c["riesgo_acumulado_base"]
        b = c["estratos"].get(grupo(int(fila["recencia_dias"]), int(fila["dias_compra_distintos"])))
        return (b["tiempos_base"], b["riesgo_acumulado_base"]) if b else (None, None)

    def supervivencia(self, fila: Mapping[str, Any], t: float) -> float | None:
        """S(t) en un tiempo real; ``None`` fuera del soporte (sin extrapolación)."""
        if t < 0 or t > self.soporte:
            return None
        if self.tipo == "km":
            km = self.datos["km"]
            return escalon(t, km["tiempos"], km["supervivencia"], 1.0)
        tb, hb = self._base(fila)
        if tb is None:
            return None
        return math.exp(-escalon(t, tb, hb, 0.0) * math.exp(max(-50.0, min(50.0, self.predictor_lineal(fila)))) * self.factor(fila))

    def factor(self, fila: Mapping[str, Any]) -> float:
        """Factor de nivel del corte (M3.2). Un artefacto con 'nivel' exige que la fila lo traiga calculado."""
        if not self.datos.get("nivel"):
            return 1.0
        f = fila.get("factor_nivel")
        if not _finito(f) or f <= 0:
            raise ValueError(f"{self.version}: falta el factor de nivel del corte (calcúlalo con factor_nivel)")
        return float(f)

    def riesgo_acumulado(self, fila: Mapping[str, Any], t: float) -> float:
        """H0(t)·exp(predictor) SIN factor de nivel (para estimar el factor)."""
        tb, hb = self._base(fila)
        return escalon(t, tb, hb, 0.0) * math.exp(max(-50.0, min(50.0, self.predictor_lineal(fila))))

    def probabilidad(self, fila):  # interfaz común del registro: este modelo no publica una probabilidad escalar
        raise TypeError("proxima_compra publica curvas y cuantiles, no una probabilidad escalar")


def cortes_nivel(corte: date, n: int, horizonte: int = HORIZONTE_DIAS) -> list[date]:
    """Los ``n`` últimos fines de mes C' cuyo seguimiento completo (C' + horizonte) termina ANTES de ``corte``."""
    from .variables import fin_de_mes
    salida, anio, mes = [], corte.year, corte.month
    while len(salida) < n:
        c = fin_de_mes(anio, mes)
        if c + timedelta(days=horizonte) < corte:
            salida.append(c)
        anio, mes = (anio - 1, 12) if mes == 1 else (anio, mes - 1)
    return sorted(salida)


def factor_nivel(artefacto, clientes, historial, corte: date) -> dict[str, Any]:
    """Estimación de máxima verosimilitud del multiplicador del riesgo acumulado con forma y coeficientes fijos:
    compras observadas / Σ H0(T_i)·exp(η_i), en los cortes de ``cortes_nivel`` con seguimiento hasta ``corte − 1``."""
    n = artefacto.datos["nivel"]["cortes"]
    cortes = cortes_nivel(corte, n)
    hasta = corte - timedelta(days=1)
    filas, _ = fotografias(clientes, historial, cortes, hasta, hasta)
    if any(date.fromisoformat(f["fin_seguimiento"]) >= corte for f in filas):
        raise AssertionError("fuga temporal en el factor de nivel")
    eventos = sum(f["evento"] for f in filas)
    esperado = sum(artefacto.riesgo_acumulado(f, f["duracion"]) for f in filas)
    factor = eventos / esperado if esperado > 0 and eventos > 0 else 1.0
    return {"factor": factor, "cortes": [c.isoformat() for c in cortes], "filas": len(filas), "eventos": eventos, "esperado": esperado,
            "seguimiento_hasta": hasta.isoformat()}


def ventana(curva: list[float], corte: date, ancho_maximo: int = ANCHO_MAXIMO_VENTANA, limites: tuple = ("p10", "p90")) -> dict[str, Any]:
    """Cuantiles p10/p50/p90 y ventana entre ``limites`` (M3: p10–p90; M3.1: p10–p50, «inicio probable»)."""
    p = {q: cuantil(curva, q) for q in CUANTILES}
    out = {}
    for q, nombre in zip(CUANTILES, ("p10", "p50", "p90")):
        out[f"dias_{nombre}"] = p[q]
        out[f"fecha_{nombre}"] = (corte + timedelta(days=p[q])).isoformat() if p[q] is not None else None
    lo, hi = out[f"dias_{limites[0]}"], out[f"dias_{limites[1]}"]
    ancho = hi - lo if lo is not None and hi is not None else None
    out["ancho_ventana_dias"] = ancho
    out["ventana_utilizable"] = ancho is not None and 0 <= ancho <= ancho_maximo
    return out


# Predicciones publicables (C2 predicciones_clientes, modelo_id = proxima_compra) -----------------------------
def predicciones_proxima(artefacto: ArtefactoProxima | None, motivo_ausencia: str | None, clientes: Iterable[Mapping[str, Any]],
                         historial: Mapping[str, list[Mapping[str, Any]]], corte: date) -> list[dict[str, Any]]:
    if artefacto is not None and artefacto.modelo_id != MODELO_ID:
        raise ValueError(f"El artefacto {artefacto.version} no es de {MODELO_ID}")
    if artefacto is not None and corte < artefacto.disponible_desde:
        motivo_ausencia = f"El corte {corte} es anterior a la disponibilidad del modelo {artefacto.version} ({artefacto.disponible_desde})."
        artefacto = None
    ancho_max = int((artefacto.datos.get("ancho_maximo_ventana_dias") if artefacto else None) or ANCHO_MAXIMO_VENTANA)
    conf_v = artefacto.datos.get("ventana") if artefacto else None  # solo artefactos M3.1 (las filas de M3 no cambian)
    limites = tuple(conf_v["limites"]) if conf_v else ("p10", "p90")
    if conf_v:
        ancho_max = conf_v["ancho_maximo_dias"]
    horizontes = artefacto.datos.get("probabilidades_acumuladas_dias") if artefacto else None
    nivel = factor_nivel(artefacto, clientes, historial, corte) if artefacto is not None and artefacto.datos.get("nivel") else None
    extra_nulos = ({"ventana_tipo": "_".join(limites), "prob_acumulada": None} if conf_v else {})
    nulos = {"dias_p10": None, "dias_p50": None, "dias_p90": None, "fecha_p10": None, "fecha_p50": None, "fecha_p90": None,
             "ancho_ventana_dias": None, "ventana_utilizable": False}
    filas = []
    for cl in sorted(clientes, key=lambda c: str(c["cliente_id"])):
        cid = str(cl["cliente_id"])
        base = {"cliente_id": cid, "modelo_id": MODELO_ID, "probabilidad": None, "horizonte_dias": HORIZONTE_DIAS,
                "version_modelo": artefacto.version if artefacto else None, "corte": corte.isoformat(), "datos_hasta": corte.isoformat(),
                "soporte_dias": artefacto.soporte if artefacto else None, "ancho_maximo_ventana_dias": ancho_max,
                "recencia_dias": None, "grupo": None, "origen_estimacion": None,
                "referencia_personal_estado": None, "referencia_personal_dias": None, **nulos, **extra_nulos}
        if cl["fecha_alta"] > corte:
            filas.append(base | {"estado": "no_elegible", "motivos": ["Alta posterior al corte"]})
            continue
        compras = historial.get(cid, [])
        v = variables_inactividad(compras, corte)
        if v is None:
            filas.append(base | {"estado": "sin_historial",
                                 "motivos": ["Sin compras confirmadas hasta el corte: no hay ritmo de compra del que partir; no se estima fecha"]})
            continue
        dias = dias_de_compra(compras, corte)
        ref = referencia_personal([(b - a).days for a, b in zip(dias, dias[1:])], v["recencia_dias"])
        comun = base | {"recencia_dias": v["recencia_dias"], "grupo": grupo(v["recencia_dias"], v["dias_compra_distintos"]),
                        "referencia_personal_estado": ref["estado"], "referencia_personal_dias": ref["dias"]}
        senales = _senales(v, ref, dias[-1])
        if artefacto is None:
            filas.append(comun | {"estado": "modelo_no_disponible",
                                  "motivos": [motivo_ausencia or "No hay versión del modelo de próxima compra"] + senales})
            continue
        if nivel:
            v = dict(v, factor_nivel=nivel["factor"])
        curva = artefacto.curva(v)
        errores = validar_curva(curva)
        if errores:
            filas.append(comun | {"estado": "sin_soporte", "motivos": ["Curva inválida: " + "; ".join(errores)] + senales})
            continue
        w = ventana(curva, corte, ancho_max, limites)
        origen = "modelo_cox" if artefacto.tipo in TIPOS_COX else "poblacional_km"
        completa = all(w[f"dias_{n}"] is not None for n in ("p10", "p50", "p90"))
        motivos = [_texto_ventana(w, artefacto.soporte, origen, limites)] + senales
        extra = {}
        if conf_v:
            extra = {"ventana_tipo": "_".join(limites),
                     "prob_acumulada": {str(t): round(1 - curva[t], 6) for t in (horizontes or []) if t < len(curva)} or None}
        if nivel:
            extra["factor_nivel"] = round(nivel["factor"], 6)
        filas.append(comun | w | extra | {"origen_estimacion": origen, "estado": "estimado" if completa else "estimacion_parcial", "motivos": motivos})
    return filas


def _texto_ventana(w: dict, soporte: int, origen: str, limites: tuple = ("p10", "p90")) -> str:
    fuente = "modelo con las variables del cliente" if origen == "modelo_cox" else "curva poblacional (igual para todos los clientes)"
    if limites == ("p10", "p50"):
        if w["dias_p10"] is None:
            return f"Ni siquiera el 10 % de probabilidad de compra se alcanza en {soporte} días ({fuente}); no se estima fecha"
        if w["dias_p50"] is None:
            return f"Inicio probable desde el día {w['dias_p10']}; la mitad de probabilidad no se alcanza en {soporte} días ({fuente})"
        return (f"Inicio probable entre el día {w['dias_p10']} (10 %) y el día {w['dias_p50']} (50 %) ({fuente})"
                + ("" if w["dias_p90"] is not None else f"; el 90 % no se alcanza en {soporte} días"))
    if w["dias_p10"] is None:
        return f"Ni siquiera el 10 % de probabilidad de compra se alcanza en {soporte} días ({fuente}); no se estima fecha"
    if w["dias_p90"] is None:
        central = f"; mitad de probabilidad hacia el día {w['dias_p50']}" if w["dias_p50"] is not None else "; la mediana no se alcanza dentro del horizonte"
        return (f"Ventana estimada desde el día {w['dias_p10']}{central}; el límite superior (90 %) no se alcanza en {soporte} días ({fuente})")
    return f"Ventana estimada del día {w['dias_p10']} al {w['dias_p90']} (80 % central), mediana el día {w['dias_p50']} ({fuente})"


def _senales(v: Mapping[str, Any], ref: dict, ultima: date) -> list[str]:
    s = [f"Última compra confirmada el {ultima.isoformat()} (hace {v['recencia_dias']} días)",
         f"{v['dias_compra_180d']} días de compra en los últimos 180 días y {v['dias_compra_distintos']} en total"]
    if ref["estado"] == "disponible":
        s.append(f"Referencia personal: intervalo mediano de {ref['mediana_intervalos']} días → faltarían unos {ref['dias']} días")
    elif ref["estado"] == "vencida":
        s.append(f"Referencia personal vencida: ya pasaron {v['recencia_dias']} días frente a un intervalo mediano de {ref['mediana_intervalos']}")
    else:
        s.append("Historia insuficiente para una referencia personal (menos de dos intervalos entre compras)")
    return s


# Publicación en sombra -----------------------------------------------------------------------------------------
def puntuar_sombra(artefacto: ArtefactoProxima, datos, corte: date, salida: str | Path, *, estado_experimento: str,
                   decision: Mapping[str, Any] | None = None, simulacion_historica: bool = False) -> dict[str, Any]:
    from contratos.validar import validar_publicacion_sombra
    from .datos import verificar_cobertura_corte
    from .ejecucion import json_bytes, publicar_lote
    from .variables import historial_compras

    if artefacto.modelo_id != MODELO_ID:
        raise ValueError(f"El artefacto {artefacto.version} es de {artefacto.modelo_id!r}, no de {MODELO_ID}")
    if corte < artefacto.disponible_desde and not simulacion_historica:
        raise ValueError(f"{artefacto.version} está disponible desde {artefacto.disponible_desde}; para cortes anteriores usa una simulación histórica explícita")
    verificar_cobertura_corte(corte, datos.cobertura)
    historial = historial_compras(datos.ventas, datos.productos, datos.tasas)
    art = artefacto
    if simulacion_historica and corte < artefacto.disponible_desde:
        from dataclasses import replace
        art = replace(artefacto, datos=dict(artefacto.datos, disponible_desde=corte.isoformat()))  # solo en memoria
    filas = predicciones_proxima(art, None, datos.clientes, historial, corte)
    nivel = factor_nivel(art, datos.clientes, historial, corte) if art.datos.get("nivel") else None
    conteo = {}
    for f in filas:
        conteo[f["estado"]] = conteo.get(f["estado"], 0) + 1
    manifiesto = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": MODELO_ID, "corte": corte.isoformat(),
                  "estado_experimento": estado_experimento, "operativa": False,
                  "advertencia": "Ventana estimada en sombra: no es una fecha contractual ni cambia la agenda C1; no crea recordatorios por sí sola.",
                  "simulacion_historica": simulacion_historica,
                  "modelo": {"version": artefacto.version, "artefacto_huella": artefacto.huella, "tipo": artefacto.tipo,
                             "version_variables": artefacto.version_variables, "horizonte_dias": HORIZONTE_DIAS,
                             "soporte_dias": artefacto.soporte, "decision": dict(decision) if decision else None,
                             **({"nivel": nivel} if nivel else {})},
                  "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
                  "cobertura": {"corte": corte.isoformat(), **datos.cobertura.como_dict(), "estado": "verificada"},
                  "conteos": conteo, "ventanas_utilizables": sum(f["ventana_utilizable"] for f in filas),
                  "tablas": {"predicciones_clientes": {"archivo": "predicciones_clientes.json", "filas": len(filas)}}}
    errores = validar_publicacion_sombra(manifiesto, filas)
    if errores:
        raise ValueError("La publicación en sombra no cumple el contrato: " + "; ".join(errores[:5]))
    publicar_lote(salida, {"predicciones_clientes.json": json_bytes(filas)}, "manifiesto.json", manifiesto)
    return {"manifiesto": json.loads((Path(salida) / "manifiesto.json").read_text(encoding="utf-8")), "filas": filas}
