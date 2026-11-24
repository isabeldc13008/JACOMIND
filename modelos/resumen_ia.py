"""Resumen de resultados de los modelos de IA para la aplicación (``salida/ia/resumen.json``).

Solo lee evidencia ya publicada y verificada (congelación y evaluación de cada ejecución) y el registro de modelos.
No entrena ni recalcula métricas. La aplicación lo sirve en ``GET /api/ia``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .ejecucion import escribir_atomico, json_bytes

RAIZ = Path(__file__).resolve().parents[1]
M13 = RAIZ / "salida" / "experimentos" / "compra_30d_m13" / "ejecucion-001"
M21 = RAIZ / "salida" / "experimentos" / "inactividad_60d_m21" / "ejecucion-001"
M31 = RAIZ / "salida" / "experimentos" / "proxima_compra_m31" / "ejecucion-001"
M41 = RAIZ / "salida" / "experimentos" / "venta_cruzada_m41" / "ejecucion-001"
M6 = RAIZ / "salida" / "experimentos" / "anomalias" / "ejecucion-001"
M61 = RAIZ / "salida" / "experimentos" / "anomalias_m61" / "ejecucion-001"
VERSION = 1


def _leer(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _fila(nombre: str, descripcion: str, a: dict, de: int, tipo: str, actual: bool = False) -> dict:
    return {"metodo": nombre, "descripcion": descripcion, "tipo": tipo, "actual": actual,
            "aciertos_top10": a.get("aciertos_top10"), "de_top10": de, "aciertos_top20": a.get("aciertos_top20"),
            "probabilidad_media": a.get("prob_media"), "brier": a.get("brier")}


def _pct(x: float) -> str:
    return f"{x * 100:.1f} %".replace(".", ",")


def lectura(filas: list[dict], tasa: float) -> list[str]:
    """Frases calculadas a partir de las filas: modelo actual frente a la regla y a la mejor versión anterior."""
    act = next(f for f in filas if f["actual"])
    regla = next(f for f in filas if f["tipo"] == "regla")
    previas = [f for f in filas if f["tipo"] == "ia" and not f["actual"] and f["aciertos_top10"] is not None]
    a, b = act["aciertos_top10"], regla["aciertos_top10"]
    salida = [f"Entre los 10 primeros de cada mes acierta {a} de {act['de_top10']}; la regla de {regla['metodo'].lower()} acierta {b}"
              + (" (empate)." if a == b else " (el modelo acierta más)." if a > b else " (la regla acierta algo más).")]
    if previas:
        peor = min(previas, key=lambda f: f["aciertos_top10"])
        if a > peor["aciertos_top10"]:
            salida.append(f"Supera a {peor['metodo']} ({peor['aciertos_top10']} de {peor['de_top10']}).")
    if act.get("probabilidad_media") is not None:
        salida.append(f"Probabilidad media estimada {_pct(act['probabilidad_media'])} frente a {_pct(tasa)} observada.")
    if act.get("aciertos_top20") is not None and regla.get("aciertos_top20") is not None:
        x, y = act["aciertos_top20"], regla["aciertos_top20"]
        salida.append(f"Entre los 20 primeros: {x} aciertos frente a {y} de la regla.")
    return salida


def resumen_compra(m13: Path, registro: Path) -> dict:
    from . import registro as R
    from .compra_m13 import verificar_congelacion_m13
    verificar_congelacion_m13(m13)
    met, dec = _leer(m13 / "metricas_comprobacion_historica.json"), _leer(m13 / "decision.json")
    reg = R.leer_registro(registro, "compra_30d")
    _, operativo = R.artefacto_registrado(registro, "compra_30d", "operativo")
    huellas = {"P": dec["artefactos"]["P"]}
    for v in ("v1", "v2"):
        if (Path(registro) / "compra_30d" / v / "artefacto.json").exists():
            huellas[v] = R._cargar_version(registro, "compra_30d", v).huella
    res = met["resultados"]
    ag = lambda k: res[k]["elegible"]["agregado"]  # noqa: E731
    de = ag("recencia")["denominador_top10"]
    filas = [
        _fila("M1.3 «P»", "Regresión con más peso a los meses recientes y nivel ajustado a la tasa de compra actual", ag("P"), de, "ia",
              operativo["huella"] == huellas["P"]),
        _fila("M1 v2", "Regresión logística con variables de recencia y frecuencia", ag("m1_v2_congelado"), de, "ia",
              operativo["huella"] == huellas.get("v2")),
        _fila("M1 v1", "Regresión original del proyecto", ag("v1_congelada"), de, "ia", operativo["huella"] == huellas.get("v1")),
        _fila("Mayor recencia", "Regla: primero quien compró hace menos (ordena, no da probabilidad)", ag("recencia"), de, "regla"),
        _fila("Tasa fija", "La misma probabilidad para todos", ag("constante"), de, "referencia"),
    ]
    return {"modelo_id": "compra_30d", "titulo": "Probabilidad de compra en los próximos 30 días",
            "pregunta": "¿Qué clientes tienen más probabilidad de comprar en los 30 días siguientes al cierre?",
            "uso": "Ordena la revisión de oportunidades de recompra en la agenda y aparece en la ficha de cada cliente.",
            "estado": "operativo (modo demostración)" if operativo.get("decision") == "demostracion" else "operativo",
            "version": operativo["artefacto_version"], "version_registro": operativo["version"],
            "modo_demostracion": R.modo_demostracion(reg),
            "periodo": [c["corte"] for c in res["recencia"]["elegible"]["por_mes"]],
            "casos": met["poblacion"]["poblacion"], "eventos": met["poblacion"]["positivos"],
            "tasa_observada": ag("P")["tasa_observada"], "filas": filas,
            "lectura": lectura(filas, ag("P")["tasa_observada"])}


def resumen_inactividad(m21: Path) -> dict:
    from .inactividad_m21_experimento import evaluacion_publicada
    pub = evaluacion_publicada(m21)
    met = _leer(m21 / "metricas_comprobacion_historica.json")
    res, ctx = met["resultados"], met.get("contexto_todos_los_candidatos", {})
    c, r, k = res["candidato"], res["mayor_recencia"], res["constante"]
    de = sum(m["top10"]["k_efectivo"] for m in c["por_mes"])

    def fila(nombre, desc, x, tipo, actual=False, top10=None, prob=None, brier=None):
        return {"metodo": nombre, "descripcion": desc, "tipo": tipo, "actual": actual,
                "aciertos_top10": top10 if top10 is not None else x["agregado"]["aciertos_top10"], "de_top10": de,
                "aciertos_top20": x["agregado"]["aciertos_top20"] if x else None, "probabilidad_media": prob, "brier": brier}
    filas = [fila("M2.1", "Probabilidad de no comprar en los días que faltan para cumplir 90, según el ritmo de cada cliente", c, "ia", True,
                  prob=c["probabilidad"]["distribucion"]["media"], brier=c["probabilidad"]["brier"]),
             fila("Mayor recencia", "Regla: primero quien lleva más días sin comprar (ordena, no da probabilidad)", r, "regla"),
             fila("Tasa fija", "La misma probabilidad para todos", k, "referencia", prob=k["probabilidad"]["distribucion"]["media"],
                  brier=k["probabilidad"]["brier"])]
    if ctx.get("m2_congelado"):
        m2 = ctx["m2_congelado"]
        filas.insert(1, {"metodo": "M2", "descripcion": "Primera versión (regresión logística con 11 variables)", "tipo": "ia", "actual": False,
                         "aciertos_top10": round(m2["precision_media_top10"] * de), "de_top10": de, "aciertos_top20": None,
                         "probabilidad_media": None, "brier": m2["brier"]})
    return {"modelo_id": "inactividad_60d", "titulo": "Riesgo de inactividad a 60 días",
            "pregunta": "¿Qué clientes activos corren más riesgo de llegar a 90 días sin comprar en los próximos 60 días?",
            "uso": "Lista de prevención y bloque en la ficha del cliente. Experimental: no cambia la agenda.",
            "estado": f"experimental (sombra) · decisión {pub['decision']['decision']}", "version": pub["decision"]["artefacto_version"],
            "periodo": met["cortes"], "casos": res["conteos"]["aprendibles_maduras"], "eventos": res["conteos"]["eventos"],
            "tasa_observada": res["conteos"]["eventos"] / res["conteos"]["aprendibles_maduras"], "filas": filas,
            "ic95_diferencia_top10": pub["decision"]["valores"]["ic95_diferencia"],
            "lectura": lectura(filas, res["conteos"]["eventos"] / res["conteos"]["aprendibles_maduras"])}


def _p(x: float | None, dec: int = 1) -> str:
    return "—" if x is None else f"{x * 100:.{dec}f} %".replace(".", ",")


def _n(x: float | None, dec: int = 3) -> str:
    return "—" if x is None else f"{x:.{dec}f}".replace(".", ",")


def resumen_proxima(m31: Path) -> dict:
    """M3.1 en una tabla propia: sus métricas son de tiempo (Brier integrado, ventanas y cobertura), no de cupo."""
    from .proxima_compra_m31 import evaluacion_publicada
    pub = evaluacion_publicada(m31)
    met = _leer(m31 / "metricas_comprobacion_historica.json")
    r, v = met["resultados"], pub["decision"]["valores"]
    c, k = r["candidato"], r["km"]
    cal_c, cal_k = r["calibracion_acumulada"]["candidato"], r["calibracion_acumulada"]["km"]
    cov = lambda m: f"{m['cobertura_p10_p90']['dentro']} de {m['cobertura_p10_p90']['determinados']} ({_p(m['cobertura_p10_p90']['cobertura'], 0)})"  # noqa: E731
    filas = [
        ["Error de Brier integrado, días 1–59 (menos es mejor)", _n(c["ibs"]), _n(k["ibs"]), "—"],
        ["Ventanas de inicio probable de 30 días o menos", f"{c['ventanas']['utilizables']} de {c['ventanas']['denominador_elegibles']}",
         f"{k['ventanas']['utilizables']} de {k['ventanas']['denominador_elegibles']} (la misma para todos)", "—"],
        ["Compras dentro de la ventana (nominal 40 %)", cov(c), cov(k), "—"],
        ["Probabilidad de compra a 30 días: estimada / real", f"{_p(cal_c['30']['media_estimada'])} / {_p(cal_c['30']['observada_km'])}",
         f"{_p(cal_k['30']['media_estimada'])} / {_p(cal_k['30']['observada_km'])}", "No da probabilidad"],
        ["Error mediano de la fecha central entre compradores (días)", _n(v["error_mediano_candidato"], 0), "—", _n(v["error_mediano_personal"], 0)],
    ]
    return {"modelo_id": "proxima_compra", "titulo": "Ventana de próxima compra",
            "pregunta": "Desde este cierre, ¿cuándo es probable que el cliente vuelva a comprar?",
            "uso": "Ventana de inicio probable (del 10 % al 50 % de probabilidad) y probabilidad de compra a 15, 30 y 60 días, en la ficha y en la consulta de próxima compra. Experimental: no cambia la agenda ni crea recordatorios.",
            "estado": f"experimental (sombra) · decisión {pub['decision']['decision']}", "version": pub["decision"]["artefacto_version"],
            "periodo": [x["corte"] for x in r["conteos"]["por_corte"]], "casos": r["conteos"]["filas"], "eventos": r["conteos"]["eventos"],
            "tasa_observada": None, "filas": [],
            "tabla": {"columnas": ["Medida", "Modelo de IA (Cox)", "Curva poblacional (Kaplan–Meier)", "Referencia personal (ritmo del cliente)"], "filas": filas},
            "lectura": [f"Reduce el error de la curva un {_p(v['reduccion_relativa'], 0)} frente a la curva poblacional (intervalo del 95 % entero por debajo de 0).",
                        f"Da una ventana de inicio probable útil para {c['ventanas']['utilizables']} de {c['ventanas']['denominador_elegibles']} casos, y adapta su ancho a cada cliente.",
                        f"El {_p(c['cobertura_p10_p90']['cobertura'], 0)} de las compras cayó dentro de la ventana; lo esperado era el 40 %"
                        + ("; el intervalo de confianza es compatible." if pub["decision"]["cumple"].get("cobertura_40_compatible") else "; el intervalo de confianza no es compatible."),
                        (f"A 30 días estimó {_p(cal_c['30']['media_estimada'])} de compra y se observó {_p(cal_c['30']['observada_km'])}: "
                         + ("sobrestima en ese periodo, en el que se compró menos que cuando aprendió." if cal_c['30']['media_estimada'] > cal_c['30']['observada_km']
                            else "subestima en ese periodo.")),
                        (f"La referencia personal acierta mejor la fecha central ({_n(v['error_mediano_personal'], 0)} frente a {_n(v['error_mediano_candidato'], 0)} días de error mediano)."
                         if (v["error_mediano_personal"] or 0) < (v["error_mediano_candidato"] or 0)
                         else f"Acierta la fecha central al menos tan bien como la referencia personal ({_n(v['error_mediano_candidato'], 0)} días de error mediano).")]}


def resumen_venta_cruzada(m41: Path) -> dict:
    """M4/M4.1 con azar y techo por producto como referencias fijas (los métodos casi empatan con el azar)."""
    from .venta_cruzada_m41 import evaluacion_publicada
    pub = evaluacion_publicada(m41)
    met = _leer(m41 / "metricas_comprobacion_historica.json")
    r = met["resultados"]
    cols = [("m4", "M4 (IA)"), ("modelo", "M4.1 (IA)"), ("popularidad", "Popularidad (en uso)"), ("coocurrencia", "Coocurrencia"),
            ("azar", "Azar"), ("techo_por_producto", "Techo por producto*")]
    cols = [(k, n) for k, n in cols if k in r]
    fila = lambda nombre, f: [nombre] + [f(r[k]) for k, _ in cols]  # noqa: E731
    filas = [fila("Acierto del primer producto (HitRate@1, universo fijo)", lambda x: f"{_p(x['hitrate1_universo'])} ({x['aciertos1']} de {x['universo']})"),
             fila("Acierto en alguno de los tres (HitRate@3)", lambda x: _p(x["hitrate3_universo"])),
             fila("Precision@3 (sobre productos sugeridos)", lambda x: _p(x["precision3"])),
             fila("Clientes con propuesta", lambda x: _p(x["cobertura_clientes"])),
             fila("Propuestas que violan restricciones", lambda x: str(x["violaciones"]))]
    ia = max((r[k]["hitrate1_universo"] for k in ("m4", "modelo") if k in r), default=None)
    return {"modelo_id": "venta_cruzada", "titulo": "Venta cruzada (productos complementarios)",
            "pregunta": "¿Qué productos que el cliente aún no tiene podría comprar en los próximos 60 días?",
            "uso": "Hasta tres propuestas por cliente para revisión de Ventas, con evidencia y compatibilidad por revisar. Experimental: publica popularidad filtrada y no crea tareas.",
            "estado": f"experimental (sombra) · decisión {pub['decision']['decision']} · se publica popularidad filtrada", "version": pub["decision"]["artefacto_version"],
            "periodo": met["conteos"] and [x["corte"] for x in met["conteos"]["por_corte"]], "casos": met["conteos"]["clientes_corte_universo"],
            "eventos": met["conteos"]["positivos"], "tasa_observada": None, "filas": [],
            "tabla": {"columnas": ["Medida"] + [n for _, n in cols], "filas": filas},
            "lectura": [f"El mejor modelo acierta el primer producto en el {_p(ia)} de los casos; elegir al azar entre los mismos candidatos da {_p(r['azar']['hitrate1_universo'])}.",
                        f"Ni conociendo la tasa real de cada producto se pasaría del {_p(r['techo_por_producto']['hitrate1_universo'])}: en estos datos de práctica las compras de productos nuevos son casi aleatorias.",
                        "Por eso se publica la popularidad filtrada y el valor está en las restricciones verificables y en la revisión de Ventas (pendiente).",
                        "* El techo usa la respuesta del periodo evaluado: mide el margen disponible, no es un método."]}


def resumen_anomalias(m6: Path) -> dict:
    """M6: detección de anomalías SEMBRADAS a igual cupo (Isolation Forest frente a mediana/MAD) por universo."""
    from .anomalias_experimento import evaluacion_publicada
    pub = evaluacion_publicada(m6)
    met = _leer(m6 / "comprobacion.json")
    decs = pub["decision"]["decisiones"]
    cols = [(u, k) for u in ("venta", "compra") for k in ("candidato", "referencia") if met[u].get(k)]
    nombre = {("venta", "candidato"): "Ventas · Isolation Forest (IA)", ("venta", "referencia"): "Ventas · mediana/MAD",
              ("compra", "candidato"): "Compras · Isolation Forest (IA)", ("compra", "referencia"): "Compras · mediana/MAD"}
    t = lambda x: "—" if not x or x.get("denominador") in (None, 0) else f"{_p(x['tasa'])} ({x['numerador']} de {x['denominador']})"  # noqa: E731
    def tipo(m, prefijo):
        xs = [v for k, v in m["por_tipo_intensidad"].items() if k.startswith(prefijo)]
        n, d = sum(v["numerador"] for v in xs), sum(v["denominador"] for v in xs)
        return {"numerador": n, "denominador": d, "tasa": n / d if d else None}
    filas = [["Anomalías sembradas detectadas a igual cupo"] + [t(met[u][k]["deteccion"]) for u, k in cols],
             ["Cantidad extrema"] + [t(tipo(met[u][k], "cantidad_extrema")) for u, k in cols],
             ["Precio o costo elevado"] + [t(tipo(met[u][k], "precio_elevado" if u == "venta" else "costo_alterado")) for u, k in cols],
             ["Alertas en controles negativos (normales construidos)"] + [t(met[u][k]["controles_negativos"]["alertas"]) for u, k in cols],
             ["Cambio solo de TRM sin cambio de puntaje"] + [f"{met[u][k]['controles_negativos']['cambio_trm_puntaje_identico']['identicos']} de "
                                                            f"{met[u][k]['controles_negativos']['cambio_trm_puntaje_identico']['total']}" for u, k in cols]]
    lect = []
    for u, et in (("venta", "ventas"), ("compra", "compras")):
        m, d = met[u], decs[u]
        if m.get("candidato") and m.get("bootstrap"):
            b = m["bootstrap"]
            pp = lambda x: f"{x * 100:+.1f} pp".replace(".", ",").replace("-", "−")  # noqa: E731
            c, nc, nr = d.get("cumple") or {}, m["candidato"]["controles_negativos"]["alertas"], m["referencia"]["controles_negativos"]["alertas"]
            por = ([] if c.get("supera_referencia_ic") else ["la mejora no es concluyente (el intervalo incluye 0)"]) +                   ([] if c.get("controles_negativos_no_peores", True) else [f"alerta en {nc['numerador']} de {nc['denominador']} controles negativos frente a {nr['numerador']} de la referencia"])
            lect.append(f"En {et}, la IA detecta {_p(m['candidato']['deteccion']['tasa'])} de las anomalías sembradas frente a {_p(m['referencia']['deteccion']['tasa'])} "
                        f"de la referencia ({pp(b['diferencia'])}; IC95 {pp(b['ic95'][0])} a {pp(b['ic95'][1])}, agrupado por operación base). "
                        f"Regla predeclarada: {d['decision'].replace('_', ' ')}" + (f", porque {' y '.join(por)}." if por else "."))
    lect += ["Son anomalías SEMBRADAS en copias de operaciones (datos sintéticos): no hay revisiones humanas reales, así que la precisión comercial no es estimable.",
             "El puntaje es rareza para ordenar la revisión, no probabilidad de fraude; la cola no modifica importes."]
    n_ops = sum(met[u]["referencia"]["originales"]["validas"] for u in ("venta", "compra"))
    n_sem = sum(met[u]["referencia"]["deteccion"]["denominador"] for u in ("venta", "compra"))
    return {"modelo_id": "anomalias", "titulo": "Operaciones atípicas (ventas y compras)",
            "pregunta": "¿Qué operaciones tienen precio, costo o cantidad inusuales frente a operaciones comparables anteriores?",
            "uso": "Cola de revisión para Operaciones y Finanzas con motivos, soporte y decisiones humanas. Experimental en sombra: publica la referencia mediana/MAD y muestra el puntaje IA como candidato.",
            "estado": "experimental (sombra) · " + " · ".join(f"{u}: {d['decision'].replace('_', ' ')}" for u, d in decs.items()),
            "version": pub["congelacion"]["artefacto_version"], "periodo": ["2026-07", "2026-08", "2026-09", "2026-10"], "casos": n_ops, "eventos": n_sem,
            "tasa_observada": None, "filas": [], "tabla": {"columnas": ["Medida"] + [nombre[c] for c in cols], "filas": filas}, "lectura": lect}


def resumen_anomalias_m61(m61: Path) -> dict:
    """M6.1: política de catálogo, cantidad solo alta y cupo máximo con evidencia; la referencia de M6 solo como contexto."""
    from .anomalias_experimento import evaluacion_publicada
    pub = evaluacion_publicada(m61)
    met = _leer(m61 / "comprobacion.json")
    decs = pub["decision"]["decisiones"]
    t = lambda x: "—" if not x or not x.get("denominador") else f"{_p(x['tasa'])} ({x['numerador']} de {x['denominador']})"  # noqa: E731
    cols = [(u, k) for u in ("venta", "compra") for k in ("contexto_m6_referencia", "referencia", "candidato") if met[u].get(k)]
    nombre = {"contexto_m6_referencia": "M6 (antes)", "referencia": "M6.1 reglas (en uso)", "candidato": "M6.1 IA"}
    et = {"venta": "Ventas", "compra": "Compras"}
    al = lambda m: m["originales"].get("alertas", m["originales"].get("alertas_cupo"))  # noqa: E731
    filas = [["Anomalías sembradas detectadas"] + [t(met[u][k]["deteccion"]) for u, k in cols],
             ["Operaciones normales construidas con alerta"] + [t(met[u][k]["controles_negativos"]["alertas"]) for u, k in cols],
             ["Alertas en operaciones reales (jul–oct)"] + [f"{al(met[u][k])} de {met[u][k]['originales']['validas']}" for u, k in cols]]
    lect = []
    for u, e in (("venta", "ventas"), ("compra", "compras")):
        m6, r, c = met[u]["contexto_m6_referencia"], met[u]["referencia"], met[u]["candidato"]
        if m6:
            lect.append(f"En {e}, M6.1 detecta {_p(r['deteccion']['tasa'])} de las anomalías sembradas (M6: {_p(m6['deteccion']['tasa'])}), alerta en "
                        f"{_p(r['controles_negativos']['alertas']['tasa'])} de las operaciones normales construidas (M6: {_p(m6['controles_negativos']['alertas']['tasa'])}) "
                        f"y deja {al(r)} {'alerta real' if al(r) == 1 else 'alertas reales'} en lugar de {al(m6)}.")
        if c:
            lect.append(f"La IA (Isolation Forest) en {e} detecta {_p(c['deteccion']['tasa'])}: sin mejora demostrable, la regla predeclarada conserva las reglas.")
    lect += ["Comprobación exploratoria y no independiente (datos ya vistos al diagnosticar M6); anomalías sembradas, 0 revisiones humanas reales.",
             "El puntaje es rareza para ordenar la revisión, no probabilidad de fraude; la cola no modifica importes."]
    return {"modelo_id": "anomalias", "titulo": "Operaciones atípicas (ventas y compras) · M6.1",
            "pregunta": "¿Qué operaciones tienen precio, costo o cantidad fuera del catálogo o de lo habitual, con evidencia verificable?",
            "uso": "Cola corta de revisión para Operaciones y Finanzas: solo alerta con evidencia (catálogo, venta bajo costo o desviación fuerte), hasta el cupo. Experimental en sombra.",
            "estado": "experimental (sombra) · " + " · ".join(f"{u}: {d['decision'].replace('_', ' ')}" for u, d in decs.items()),
            "version": pub["congelacion"]["artefacto_version"], "periodo": ["2026-07", "2026-08", "2026-09", "2026-10"],
            "casos": sum(met[u]["referencia"]["originales"]["validas"] for u in ("venta", "compra")),
            "eventos": sum(met[u]["referencia"]["deteccion"]["denominador"] for u in ("venta", "compra")), "tasa_observada": None, "filas": [],
            "tabla": {"columnas": ["Medida"] + [f"{et[u]} · {nombre[k]}" for u, k in cols], "filas": filas}, "lectura": lect}


def construir(registro: str | Path | None = None, m13: Path = M13, m21: Path = M21, m31: Path = M31, m41: Path = M41, m6: Path = M6, m61: Path = M61) -> dict:
    from . import registro as R
    return {"version": VERSION, "origen_datos": "sintetico",
            "advertencia": ("Resultados con los datos de práctica del paquete (sintéticos) en meses ya revisados al diseñar los modelos: "
                            "son orientativos. Solo un piloto con datos reales de la empresa puede confirmarlos."),
            "modelos": [resumen_compra(m13, R.ruta_registro(registro)), resumen_inactividad(m21)]
                       + ([resumen_proxima(m31)] if (Path(m31) / "evaluacion.json").exists() else [])
                       + ([resumen_venta_cruzada(m41)] if (Path(m41) / "evaluacion.json").exists() else [])
                       + ([resumen_anomalias_m61(m61)] if (Path(m61) / "evaluacion.json").exists()
                          else [resumen_anomalias(m6)] if (Path(m6) / "evaluacion.json").exists() else [])}


def publicar(salida: str | Path, registro: str | Path | None = None) -> dict:
    """Escribe ``resumen.json`` (atómico). Es un derivado: se regenera cuando cambia el registro o una evaluación."""
    doc = dict(construir(registro), generado_en=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    Path(salida).mkdir(parents=True, exist_ok=True)
    escribir_atomico(Path(salida) / "resumen.json", json_bytes(doc))
    return doc
