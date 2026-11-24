"""Observaciones de monitoreo por modelo (``jacomind.monitoreo.v1``) desde lo YA publicado y persistido, y desempeño con
resultados maduros. Solo biblioteca estándar.

* Salud y distribución se calculan al publicar o importar (cierres de M1; sombras de M2–M6) y con
  ``python -m api monitoreo recalcular`` para lo ya importado. Revisión humana (M4 y M6) al registrar revisiones.
* Desempeño solo con ``python -m api monitoreo resultados --datos <A01>``: usa la cobertura DECLARADA de los datos para decidir
  la madurez (corte + horizonte); nunca datos posteriores para reconstruir una puntuación pasada (los puntajes son los
  publicados) y nunca convierte un cliente censurado en no comprador.
* Cada modelo conserva su propia estructura: M1–M3 por clientes, M4 por clientes con recomendaciones, M5 por serie y unidad
  (COP y unidades nunca se mezclan; cada producto en su propia unidad), M6 por universo venta/compra.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import date, timedelta

from . import monitoreo as M
from .base import BaseDatos, loads

ESTIMADOS = {"estimado"}


def _p(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 6)


def _distribucion(xs: list[float], unidad: str = "probabilidad") -> dict:
    motivo = "sin valores estimados"
    return {f"p{int(q * 100)}": M.metrica(_p(xs, q), soporte=len(xs), motivo=motivo, unidad=unidad) for q in (0.1, 0.5, 0.9)} | \
        {"media": M.metrica(round(sum(xs) / len(xs), 6) if xs else None, soporte=len(xs), motivo=motivo, unidad=unidad)}


def variante(modelo_id: str, version: str | None, man: dict | None = None) -> str | None:
    if modelo_id == "anomalias":
        return (man or {}).get("version_protocolo") or "m6-protocolo-v1"
    v = str(version or "")
    for parte in v.split("-"):
        if parte[:1] == "m" and parte[1:].isdigit():
            return parte
    return v or None


# Salud y distribución ------------------------------------------------------------------------------------------------
def obs_clientes(modelo_id: str, origen: dict, corte: str, version: str, filas: list[dict], huella: str | None, politica: dict) -> list[dict]:
    """M1, M2 y M3 (predicciones por cliente)."""
    v = variante(modelo_id, version)
    est = Counter(f.get("estado") for f in filas)
    comun = dict(modelo_id=modelo_id, variante=v, version_artefacto=version, origen=origen, corte=corte, huella_datos=huella, politica=politica)
    if modelo_id == "inactividad_60d":
        fuera = est.get("no_elegible", 0)
        elegibles = len(filas) - fuera
        cubiertos = est.get("estimado", 0) + est.get("estructural", 0)  # un estado estructural no es un fallo de puntuación
        conteos = {"filas": len(filas), "elegibles": elegibles, "estimados": est.get("estimado", 0), "estructurales": est.get("estructural", 0),
                   "fuera_de_poblacion": fuera, "abstenciones": elegibles - cubiertos, "por_estado": dict(est)}
        probs = [f["probabilidad"] for f in filas if f.get("estado") == "estimado" and f.get("probabilidad") is not None]
    elif modelo_id == "proxima_compra":
        con_prob = [f for f in filas if isinstance(f.get("prob_acumulada"), dict) and all(f["prob_acumulada"].get(h) is not None for h in ("15", "30", "60"))]
        cubiertos = len(con_prob)
        elegibles = len(filas)
        util = sum(bool(f.get("ventana_utilizable")) for f in filas)
        conteos = {"elegibles": elegibles, "con_probabilidad": cubiertos, "ventanas_utilizables": util, "ventanas_parciales_o_no_estimables": elegibles - util,
                   "abstenciones": elegibles - cubiertos, "por_estado": dict(est)}
        probs = [f["prob_acumulada"]["30"] for f in con_prob]
    else:
        elegibles = len(filas)
        cubiertos = sum(f.get("estado") in ESTIMADOS and f.get("probabilidad") is not None for f in filas)
        conteos = {"elegibles": elegibles, "estimados": cubiertos, "abstenciones": elegibles - cubiertos, "por_estado": dict(est)}
        probs = [f["probabilidad"] for f in filas if f.get("estado") in ESTIMADOS and f.get("probabilidad") is not None]
    met = {"cobertura": M.tasa(cubiertos, elegibles, "periodo sin registros elegibles")}
    if modelo_id == "proxima_compra":
        met["ventanas_utilizables"] = M.tasa(conteos["ventanas_utilizables"], elegibles, "periodo sin registros elegibles")
    salud = M.observacion(grupo="salud", universo="clientes", conteos=conteos, metricas=met, **comun)
    dmet = _distribucion(probs)
    if modelo_id == "compra_30d":
        sup = sum(bool(f.get("supera_umbral")) for f in filas if f.get("estado") in ESTIMADOS)
        dmet["supera_umbral"] = M.tasa(sup, cubiertos, "sin clientes estimados")
    dist = M.observacion(grupo="distribucion", universo="clientes", conteos={"estimados": len(probs)}, metricas=dmet,
                         motivos=["Una variación de distribución no demuestra deterioro predictivo"], **comun)
    return [salud, dist]


def obs_venta_cruzada(origen: dict, man: dict, recs: list[dict], cob: list[dict]) -> list[dict]:
    corte, version = man["corte"], man["modelo"]["version"]
    est = Counter(c.get("estado") for c in cob)
    con_cand = sum((c.get("n_candidatos") or 0) > 0 for c in cob)
    con_rec = sum((c.get("n_recomendaciones") or 0) > 0 for c in cob)
    compat = Counter(r.get("estado_compatibilidad") for r in recs)
    soporte = [r["soporte"] for r in recs if isinstance(r.get("soporte"), (int, float))]
    politica = {"id": man["modelo"].get("sistema_publicado"), "version": r0.get("version_reglas") if (r0 := (recs[0] if recs else {})) else None}
    comun = dict(modelo_id="venta_cruzada", variante=variante("venta_cruzada", version), version_artefacto=version, origen=origen, corte=corte,
                 huella_datos=(man.get("datos") or {}).get("huella_datos"), politica=politica)
    salud = M.observacion(grupo="salud", universo="clientes", conteos={"elegibles": len(cob), "con_candidatos": con_cand, "con_recomendaciones": con_rec,
                                                                       "recomendaciones": len(recs), "por_estado": dict(est),
                                                                       "compatibilidad": {"confirmada": compat.get("confirmada", 0),
                                                                                          "pendiente": compat.get("pendiente_revision", 0),
                                                                                          "incompatible": compat.get("incompatible", 0)}},
                          metricas={"cobertura": M.tasa(con_rec, len(cob), "periodo sin registros elegibles"),
                                    "compatibilidad_confirmada": M.tasa(compat.get("confirmada", 0), len(recs), "sin recomendaciones")}, **comun)
    prods = Counter(r["producto_id"] for r in recs)
    dist = M.observacion(grupo="distribucion", universo="clientes", conteos={"recomendaciones": len(recs), "productos": len(prods)},
                         metricas={"concentracion_producto_principal": M.tasa(max(prods.values()) if prods else 0, len(recs), "sin recomendaciones"),
                                   "soporte_mediano_productos": M.metrica(_p(soporte, 0.5), soporte=len(soporte), motivo="sin soporte publicado", unidad="clientes")},
                         motivos=["Concentración y soporte describen la propuesta; no miden acierto"], **comun)
    return [salud, dist]


def obs_demanda(origen: dict, man: dict, pron: list[dict]) -> list[dict]:
    """Por universo de unidad: ventas_cop (familias), ventas_cop_total, compras_cop y ventas_unidades:<producto>."""
    out = []
    grupos: dict[str, list] = defaultdict(list)
    for f in pron:
        grupos[_universo_demanda(f)].append(f)
    for u, fs in sorted(grupos.items()):
        est = Counter(f["estado"] for f in fs)
        motivos = Counter(m for f in fs if f["valor"] is None for m in (f.get("motivos") or ["sin motivo"]))
        con_banda = sum(f.get("banda_inferior") is not None for f in fs)
        estimadas = est.get("estimado", 0)
        out.append(M.observacion(modelo_id="demanda", variante=variante("demanda", man["modelo"]["version"]), version_artefacto=man["modelo"]["version"],
                                 origen=origen, corte=man["corte"], periodo=man["origen"], universo=u, grupo="salud", huella_datos=(man.get("datos") or {}).get("huella_datos"),
                                 politica={"id": "pronostico_por_serie_y_horizonte", "version": man["modelo"]["version"]}, restriccion=_restriccion(u),
                                 conteos={"elegibles": len(fs), "estimadas": estimadas, "abstenciones": len(fs) - estimadas, "abstenciones_por_motivo": dict(motivos),
                                          "con_banda": con_banda, "unidad": fs[0]["unidad"]},
                                 metricas={"cobertura": M.tasa(estimadas, len(fs), "sin series esperadas"),
                                           "cobertura_bandas": M.tasa(con_banda, len(fs), "sin series esperadas")}))
    return out


def _universo_demanda(f: dict) -> str:
    sid = f["serie_id"]
    if sid == "ventas_cop:Total":
        return "ventas_cop_total"
    if sid.startswith("ventas_cop:"):
        return "ventas_cop"
    if sid.startswith("compras_proveedores_cop:"):
        return "compras_cop"
    return sid  # ventas_unidades:<producto>: cada producto en su unidad


def _restriccion(universo: str) -> str:
    return "cop" if "cop" in universo else "unidades"


def obs_anomalias(origen: dict, man: dict, filas: list[dict], cob: list[dict]) -> list[dict]:
    out = []
    pol = man.get("politica_alertas") or {}
    politica = {"id": pol.get("tipo"), "version": man.get("version_protocolo") or "m6-protocolo-v1", "cupo_fraccion": pol.get("cupo_fraccion")}
    for u in ("venta", "compra"):
        fs = [f for f in filas if f["tipo_operacion"] == u]
        cu = [c for c in cob if c["tipo_operacion"] == u]
        punt = [f["puntaje"] for f in fs if f["puntaje"] is not None]
        alert = sum(bool(f["alerta"]) for f in fs)
        excl: Counter = Counter()
        for c in cu:
            excl.update(c.get("excluidas") or {})
        comun = dict(modelo_id="anomalias", variante=variante("anomalias", None, man), version_artefacto=man["modelo"]["version"], origen=origen,
                     corte=man["corte"], universo=u, huella_datos=(man.get("datos") or {}).get("huella_datos"), politica=politica)
        out.append(M.observacion(grupo="salud", conteos={"elegibles": len(fs), "validas": len(fs), "puntuadas": len(punt), "abstenciones": len(fs) - len(punt),
                                                         "excluidas": dict(excl), "cobertura_temporal": "declarada" if u == "venta" else "no_declarada"},
                                 metricas={"cobertura": M.tasa(len(punt), len(fs), "periodo sin operaciones válidas")}, **comun))
        out.append(M.observacion(grupo="distribucion", conteos={"validas": len(fs), "alertas": alert, "cupo": sum(c.get("cupo", 0) for c in cu),
                                                                "exceso_sobre_cupo": sum(c.get("exceso_sobre_cupo", 0) for c in cu)},
                                 metricas={"alertas_por_100": M.metrica(round(100 * alert / len(fs), 4) if fs else None, numerador=alert, denominador=len(fs),
                                                                        motivo="periodo sin operaciones válidas"),
                                           **{k: v for k, v in _distribucion(punt, "rareza").items()}},
                                 motivos=["La rareza ordena la revisión; no es probabilidad de fraude. Un cambio de distribución no prueba deterioro"], **comun))
    return out


# Revisión humana -----------------------------------------------------------------------------------------------------
def obs_revision_venta_cruzada(con, sid: str, man: dict) -> list[dict]:
    muestra = con.execute("SELECT datos_json FROM sombra_muestras_revision WHERE sombra_id = ?", (sid,)).fetchone()
    evaluables = len((loads(muestra[0]) or {}).get("pares", [])) if muestra else 0
    ultimas = {}
    for r in con.execute("SELECT cliente_id, producto_id, estado_revision FROM revisiones_venta_cruzada WHERE sombra_id = ? ORDER BY id", (sid,)):
        ultimas[(r[0], r[1])] = r[2]  # la última revisión de cada par
    revs = Counter(ultimas.values())
    total = sum(revs.values())
    return [M.observacion(modelo_id="venta_cruzada", variante=variante("venta_cruzada", man["modelo"]["version"]), version_artefacto=man["modelo"]["version"],
                          origen={"tipo": "revision", "id": sid}, corte=man["corte"], universo="muestra_revision", grupo="revision",
                          conteos={"evaluables": evaluables, "revisadas": total, "pendientes": max(evaluables - total, 0), "por_estado": dict(revs)},
                          metricas={"pertinencia": M.tasa(revs.get("pertinente", 0), total - revs.get("informacion_insuficiente", 0),
                                                          "sin revisiones comerciales concluyentes"),
                                    "descartadas": M.tasa(sum(revs.get(k, 0) for k in ("ya_cubierto", "incompatible", "sin_necesidad")), total, "sin revisiones"),
                                    "insuficientes": M.tasa(revs.get("informacion_insuficiente", 0), total, "sin revisiones")},
                          motivos=["Revisión comercial humana; no atribuye compras al recomendador"])]


def obs_revision_anomalias(con, sid: str, man: dict) -> list[dict]:
    from .anomalias import metricas_revision
    filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_anomalias WHERE sombra_id = ?", (sid,))]
    casos = {(r["tipo_operacion"], r["operacion_id"]): dict(r) for r in con.execute("SELECT * FROM casos_anomalia WHERE reemplazado_por IS NULL")}
    out = []
    for u in ("venta", "compra"):
        fu = [f for f in filas if f["tipo_operacion"] == u]
        mr = metricas_revision(fu, casos, (man.get("monitoreo") or {}).get("umbrales") or {})
        cu = [c for c in casos.values() if c["tipo_operacion"] == u]
        p, fa = mr["precision_alertas_revisadas"], mr["falsas_alertas_por_100_normales_revisadas"]
        out.append(M.observacion(modelo_id="anomalias", variante=variante("anomalias", None, man), version_artefacto=man["modelo"]["version"],
                                 origen={"tipo": "revision", "id": sid}, corte=man["corte"], universo=u, grupo="revision",
                                 conteos={"casos": len(cu), "pendientes": sum(c["estado"] == "pendiente" for c in cu), "revisadas": mr["revisadas"],
                                          "por_estado": mr["por_estado"]},
                                 metricas={"precision_alertas_revisadas": M.metrica(p["valor"], numerador=p["numerador"], denominador=p["denominador"], motivo=p["motivo"]),
                                           "falsas_alertas_por_100_normales": M.metrica(fa["por_100"], numerador=fa["numerador"], denominador=fa["denominador"], motivo=fa["motivo"])},
                                 motivos=["Rareza, alertas, revisiones y precisión comercial se reportan por separado"]))
    return out


# Puntos de integración ------------------------------------------------------------------------------------------------
def _vigente(con, sid: str) -> bool:
    r = con.execute("SELECT resultado FROM auditoria WHERE accion = 'sombra.importar' AND recurso = ? ORDER BY rowid LIMIT 1", (sid,)).fetchone()
    return not (r and r["resultado"] == "importada_sin_activar")


def observaciones_sombra(con, sid: str) -> list[dict]:
    r = con.execute("SELECT * FROM sombra_publicaciones WHERE id = ?", (sid,)).fetchone()
    man, mid = loads(r["manifiesto_json"]), r["modelo_id"]
    origen = {"tipo": "sombra", "id": sid, "sello": r["sello"]}
    if mid in ("inactividad_60d", "proxima_compra"):
        filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_predicciones WHERE sombra_id = ? AND modelo_id = ?", (sid, mid))]
        pol = {"id": "sombra_por_clientes", "version": man["modelo"]["version"]}
        return obs_clientes(mid, origen, man["corte"], man["modelo"]["version"], filas, (man.get("datos") or {}).get("huella_datos"), pol)
    if mid == "venta_cruzada":
        recs = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_recomendaciones WHERE sombra_id = ?", (sid,))]
        cob = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_cobertura_recomendaciones WHERE sombra_id = ?", (sid,))]
        return obs_venta_cruzada(origen, man, recs, cob) + obs_revision_venta_cruzada(con, sid, man)
    if mid == "demanda":
        return obs_demanda(origen, man, [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_pronosticos WHERE sombra_id = ?", (sid,))])
    if mid == "anomalias":
        filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_anomalias WHERE sombra_id = ?", (sid,))]
        cob = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_cobertura_anomalias WHERE sombra_id = ?", (sid,))]
        return obs_anomalias(origen, man, filas, cob) + obs_revision_anomalias(con, sid, man)
    return []


def observar_sombra(db: BaseDatos, sid: str) -> list[dict]:
    """Llamado tras importar una sombra (M2–M6). Idempotente; solo una publicación vigente genera avisos."""
    with db.transaccion() as con:
        vig = _vigente(con, sid)
        return [M.registrar_y_evaluar(con, o, vigente=vig, sombra_id=sid) for o in observaciones_sombra(con, sid)]


def tras_importar(db: BaseDatos, salida: dict, actor: str) -> dict:
    """Gancho tras importar una sombra: observa salud, distribución y revisión. Un fallo del monitoreo se audita y no anula
    una publicación ya válida (los errores de integridad se rechazan ANTES, en la importación)."""
    if salida.get("ya_importada"):
        return salida
    try:
        res = observar_sombra(db, salida["sombra_id"])
        salida["monitoreo"] = {"observaciones": len(res), "avisos": [a["tipo"] for x in res for a in x["avisos"]]}
    except Exception as exc:  # noqa: BLE001
        from .base import auditar
        with db.transaccion() as con:
            auditar(con, actor, "monitoreo.observar", salida["sombra_id"], "fallido", None, {"error": str(exc)})
        salida["monitoreo"] = {"error": str(exc)}
    return salida


def observar_revision(db: BaseDatos, modelo_id: str) -> list[dict]:
    """Tras una revisión humana (M4 o M6): actualiza el grupo D de la publicación activa (la anterior queda enlazada)."""
    with db.transaccion() as con:
        r = con.execute("SELECT id, manifiesto_json FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (modelo_id,)).fetchone()
        if not r:
            return []
        fn = obs_revision_venta_cruzada if modelo_id == "venta_cruzada" else obs_revision_anomalias
        return [M.registrar_y_evaluar(con, o, sombra_id=r["id"]) for o in fn(con, r["id"], loads(r["manifiesto_json"]))]


def observaciones_cierre(con, cierre_id: str) -> list[dict]:
    r = con.execute("SELECT * FROM cierres WHERE id = ?", (cierre_id,)).fetchone()
    man = loads(r["manifiesto_json"])
    filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM an_filas WHERE cierre_id = ? AND tabla = 'predicciones_clientes'", (cierre_id,))]
    if not filas:
        return []  # cierres antiguos sin predicciones: «monitoreo no disponible» (no se reconstruye)
    version = (man.get("versiones") or {}).get("modelo_compra") or filas[0].get("version_modelo")
    pol = {"id": "agenda_c1", "version": (man.get("versiones") or {}).get("reglas"), "umbral": filas[0].get("umbral")}
    huella = _sha_entradas(man)
    return obs_clientes("compra_30d", {"tipo": "cierre", "id": cierre_id, "huella": r["huella"]}, man["corte"], version, filas, huella, pol)


def _sha_entradas(man: dict) -> str | None:
    h = man.get("huellas_entrada")
    return M._sha(h) if h else None


def observar_cierre(db: BaseDatos, cierre_id: str) -> list[dict]:
    with db.transaccion() as con:
        return [M.registrar_y_evaluar(con, o) for o in observaciones_cierre(con, cierre_id)]


def recalcular(db: BaseDatos) -> dict:
    """Salud, distribución y revisión de TODO lo ya publicado (idempotente; no duplica observaciones ni avisos).
    Se procesa en orden de importación para que la comparación use la publicación vigente anterior."""
    with db.conexion() as con:
        cierres = [r[0] for r in con.execute("SELECT id FROM cierres ORDER BY corte, publicado_en")] if _hay_col(con, "cierres", "publicado_en") else \
            [r[0] for r in con.execute("SELECT id FROM cierres ORDER BY corte, rowid")]
        sombras = [r[0] for r in con.execute("SELECT id FROM sombra_publicaciones ORDER BY importada_en, rowid")]
    res = Counter()
    for c in cierres:
        for x in observar_cierre(db, c):
            res[x["estado"]] += 1
    for s in sombras:
        for x in observar_sombra(db, s):
            res[x["estado"]] += 1
    return {"cierres": len(cierres), "sombras": len(sombras), "observaciones": dict(res)}


def _hay_col(con, tabla: str, col: str) -> bool:
    return any(r[1] == col for r in con.execute(f"PRAGMA table_info({tabla})"))


# Desempeño con resultados maduros -----------------------------------------------------------------------------------------
def compras_por_cliente(datos) -> dict[str, list[date]]:
    out: dict[str, list[date]] = defaultdict(list)
    for v in datos.ventas:
        if v.get("estado", "Confirmada") == "Confirmada":
            out[str(v["cliente_id"])].append(v["fecha"])
    return {k: sorted(v) for k, v in out.items()}


def _compra_en(fechas: list[date], desde: date, hasta: date) -> bool:
    return any(desde < f <= hasta for f in fechas)


def _recencia(fechas: list[date], corte: date) -> float:
    previas = [f for f in fechas if f <= corte]
    return float((corte - previas[-1]).days) if previas else float("inf")


def _top(filas: list[dict], clave, k: int) -> list[dict]:
    return sorted(filas, key=lambda f: (-clave(f), f["cliente_id"]))[:k]


def _pendiente(modelo_id, variante_, version, origen, corte, universo, motivo, huella, politica, restriccion=None, comparacion=None) -> dict:
    """Pendiente de madurez: misma definición (``comparacion``) que la observación madura equivalente, sin métricas."""
    return M.observacion(modelo_id=modelo_id, variante=variante_, version_artefacto=version, origen=origen, corte=corte, universo=universo,
                         grupo="desempeno", madurez="pendiente", conteos={}, metricas={}, motivos=[motivo], huella_datos=huella, politica=politica,
                         restriccion=restriccion, comparacion=comparacion)


def resultados_clientes(modelo_id: str, origen: dict, corte: str, version: str, filas: list[dict], datos, politica: dict) -> list[dict]:
    """M1 (compra en 30 días) y M2 (sin compra en 60 días): Brier y precisión al cupo frente a mayor recencia, mismo universo."""
    rg = M.reglas()
    h = rg["madurez"][modelo_id]["horizonte_dias"]
    c = date.fromisoformat(corte)
    v = variante(modelo_id, version)
    origen_r = {"tipo": "resultados", "id": f"{origen['id']}:{datos.huella_datos[:12]}", "origen": origen}
    comparacion = {"horizonte": h, "cupo": rg["cupos"][modelo_id], "referencia": rg["referencias"][modelo_id]}
    if datos.observado_hasta is None or datos.observado_hasta < c + timedelta(days=h):
        return [_pendiente(modelo_id, v, version, origen_r, corte, "clientes", f"Resultado inmaduro: la cobertura declarada ({datos.observado_hasta}) no alcanza "
                           f"{c + timedelta(days=h)} (corte + {h} días)", datos.huella_datos, politica, comparacion=comparacion)]
    compras = compras_por_cliente(datos)
    uni = [f for f in filas if f.get("estado") == "estimado" and f.get("probabilidad") is not None]
    y = (lambda f: _compra_en(compras.get(f["cliente_id"], []), c, c + timedelta(days=h))) if modelo_id == "compra_30d" else \
        (lambda f: not _compra_en(compras.get(f["cliente_id"], []), c, c + timedelta(days=h)))
    rec = {f["cliente_id"]: _recencia(compras.get(f["cliente_id"], []), c) for f in uni}  # solo historia hasta el corte
    ref = (lambda f: -rec[f["cliente_id"]]) if modelo_id == "compra_30d" else (lambda f: rec[f["cliente_id"]])
    k = min(rg["cupos"][modelo_id], len(uni))
    am = sum(y(f) for f in _top(uni, lambda f: f["probabilidad"], k))
    ar = sum(y(f) for f in _top(uni, ref, k))
    n = len(uni)
    brier = round(sum((f["probabilidad"] - y(f)) ** 2 for f in uni) / n, 6) if n else None
    met = {"brier": M.metrica(brier, soporte=n, motivo="sin clientes estimados"),
           "precision_cupo": M.metrica(round(am / k, 6) if k else None, numerador=am, denominador=k, soporte=n, motivo="sin clientes estimados",
                                       referencia={"id": rg["referencias"][modelo_id], **M.metrica(round(ar / k, 6) if k else None, numerador=ar, denominador=k,
                                                                                                  motivo="sin clientes estimados")}),
           "tasa_observada": M.tasa(sum(y(f) for f in uni), n, "sin clientes estimados"),
           "probabilidad_media": M.metrica(round(sum(f["probabilidad"] for f in uni) / n, 6) if n else None, soporte=n, motivo="sin clientes estimados")}
    conteos = {"evaluados": n, "positivos": sum(y(f) for f in uni), "cupo": k}
    if modelo_id == "inactividad_60d":
        estr = [f for f in filas if f.get("estado") == "estructural"]
        conteos.update(estructurales=len(estr), estructurales_inactivos=sum(y(f) for f in estr))
    return [M.observacion(modelo_id=modelo_id, variante=v, version_artefacto=version, origen=origen_r, corte=corte, universo="clientes", grupo="desempeno",
                          madurez="madura", conteos=conteos, metricas=met, huella_datos=datos.huella_datos, politica=politica,
                          comparacion=comparacion,
                          motivos=[f"Resultado observado hasta {c + timedelta(days=h)}; puntajes tal como se publicaron"])]


def resultados_proxima(origen: dict, corte: str, version: str, filas: list[dict], datos, politica: dict) -> list[dict]:
    """M3: un resultado por horizonte maduro; los inmaduros quedan pendientes (nunca como no compradores)."""
    c, out = date.fromisoformat(corte), []
    compras = compras_por_cliente(datos)
    v = variante("proxima_compra", version)
    origen_r = {"tipo": "resultados", "id": f"{origen['id']}:{datos.huella_datos[:12]}", "origen": origen}
    for h in M.reglas()["madurez"]["proxima_compra"]["horizontes_dias"]:
        u = f"horizonte_{h}d"
        if datos.observado_hasta is None or datos.observado_hasta < c + timedelta(days=h):
            out.append(_pendiente("proxima_compra", v, version, origen_r, corte, u, f"Horizonte {h} días inmaduro: clientes censurados, no no-compradores",
                                  datos.huella_datos, politica, comparacion={"horizonte": h}))
            continue
        uni = [f for f in filas if isinstance(f.get("prob_acumulada"), dict) and f["prob_acumulada"].get(str(h)) is not None]
        y = {f["cliente_id"]: _compra_en(compras.get(f["cliente_id"], []), c, c + timedelta(days=h)) for f in uni}
        n = len(uni)
        out.append(M.observacion(modelo_id="proxima_compra", variante=v, version_artefacto=version, origen=origen_r, corte=corte, universo=u, grupo="desempeno",
                                 madurez="madura", conteos={"evaluados": n, "compraron": sum(y.values()), "censurados": 0}, huella_datos=datos.huella_datos,
                                 politica=politica, comparacion={"horizonte": h},
                                 metricas={"brier": M.metrica(round(sum((f["prob_acumulada"][str(h)] - y[f["cliente_id"]]) ** 2 for f in uni) / n, 6) if n else None,
                                                              soporte=n, motivo="sin probabilidades publicadas"),
                                           "tasa_observada": M.tasa(sum(y.values()), n, "sin probabilidades publicadas")}))
    ventanas = [f for f in filas if f.get("ventana_utilizable") and f.get("fecha_p10") and f.get("fecha_p50")]
    maduras = [f for f in ventanas if datos.observado_hasta and datos.observado_hasta >= date.fromisoformat(f["fecha_p50"])]
    dentro = sum(any(date.fromisoformat(f["fecha_p10"]) <= x <= date.fromisoformat(f["fecha_p50"]) for x in compras.get(f["cliente_id"], []) if x > c) for f in maduras)
    out.append(M.observacion(modelo_id="proxima_compra", variante=v, version_artefacto=version, origen=origen_r, corte=corte, universo="ventanas", grupo="desempeno",
                             madurez="madura" if ventanas and len(maduras) == len(ventanas) else ("parcial" if maduras else "pendiente"),
                             conteos={"ventanas_utilizables": len(ventanas), "observables": len(maduras), "censuradas": len(ventanas) - len(maduras)},
                             metricas={} if not maduras else {"cobertura_ventana": M.tasa(dentro, len(maduras), "sin ventanas observables")},
                             motivos=["Cobertura de la ventana p10–p50 solo entre ventanas ya observables; las demás quedan censuradas"],
                             huella_datos=datos.huella_datos, politica=politica, comparacion={"ventana": "p10_p50"}))
    return out


def resultados_venta_cruzada(origen: dict, man: dict, recs: list[dict], datos) -> list[dict]:
    c = date.fromisoformat(man["corte"])
    h = M.reglas()["madurez"]["venta_cruzada"]["horizonte_dias"]
    version = man["modelo"]["version"]
    origen_r = {"tipo": "resultados", "id": f"{origen['id']}:{datos.huella_datos[:12]}", "origen": origen}
    pol = {"id": man["modelo"].get("sistema_publicado"), "version": version}
    if datos.observado_hasta is None or datos.observado_hasta < c + timedelta(days=h):
        return [_pendiente("venta_cruzada", variante("venta_cruzada", version), version, origen_r, man["corte"], "clientes",
                           f"Resultado inmaduro: la cobertura declarada no alcanza {c + timedelta(days=h)}", datos.huella_datos, pol, comparacion={"horizonte": h})]
    compradas: dict[str, set] = defaultdict(set)
    for v in datos.ventas:
        if v.get("estado", "Confirmada") == "Confirmada" and c < v["fecha"] <= c + timedelta(days=h):
            compradas[str(v["cliente_id"])].add(str(v["producto_id"]))
    por_cliente: dict[str, list] = defaultdict(list)
    for r in recs:
        por_cliente[r["cliente_id"]].append(r)
    n = len(por_cliente)
    h1 = sum(any(r["posicion"] == 1 and r["producto_id"] in compradas[cl] for r in rs) for cl, rs in por_cliente.items())
    h3 = sum(any(r["producto_id"] in compradas[cl] for r in rs) for cl, rs in por_cliente.items())
    return [M.observacion(modelo_id="venta_cruzada", variante=variante("venta_cruzada", version), version_artefacto=version, origen=origen_r, corte=man["corte"],
                          universo="clientes", grupo="desempeno", madurez="madura", conteos={"clientes_con_recomendaciones": n, "con_compra_posterior": h3},
                          metricas={"hitrate1": M.tasa(h1, n, "sin clientes con recomendaciones"), "hitrate3": M.tasa(h3, n, "sin clientes con recomendaciones")},
                          huella_datos=datos.huella_datos, politica=pol, comparacion={"horizonte": h},
                          motivos=["Exposición y compra posterior: NO es atribución causal al recomendador (sin diseño experimental)"])]


def resultados_demanda(origen: dict, man: dict, pron: list[dict], cal: list[dict], datos) -> list[dict]:
    """Error firmado y absoluto, MAE, WAPE y sesgo por universo de unidad, con la referencia A08 en los mismos objetivos."""
    import json as _json
    from modelos.demanda import construir_series, fin_mes, pron_media_movil_3, tramo
    from pathlib import Path
    primer = min((f["periodo_objetivo"] for f in pron), default=None)
    if primer is None or datos.observado_hasta is None or datos.observado_hasta < fin_mes(primer):
        series = {}  # ningún mes objetivo puede estar completo: todo pendiente sin reconstruir series
    else:
        config = _json.loads((Path(__file__).resolve().parents[1] / "modelos" / "config" / "demanda.json").read_text(encoding="utf-8"))
        series = construir_series(datos, config)
    reales = {(sid, m["periodo"]): m for sid, s in series.items() for m in s["calendario"]}
    cal_s: dict[str, list] = defaultdict(list)
    for x in cal:
        cal_s[x["serie_id"]].append(x)
    origen_r = {"tipo": "resultados", "id": f"{origen['id']}:{datos.huella_datos[:12]}", "origen": origen}
    grupos: dict[str, list] = defaultdict(list)
    for f in pron:
        grupos[_universo_demanda(f)].append(f)
    out = []
    for u, fs in sorted(grupos.items()):
        ev, total = [], len(fs)
        for f in fs:
            if f["serie_id"] == "ventas_cop:Total":
                ms = [reales.get((s, f["periodo_objetivo"])) for s in series if s.startswith("ventas_cop:")]
                obs = sum(m["valor"] for m in ms) if ms and all(m and m["estado"] == "completo" for m in ms) else None
            else:
                m = reales.get((f["serie_id"], f["periodo_objetivo"]))
                obs = m["valor"] if m and m["estado"] == "completo" else None
            if obs is None or f["valor"] is None:
                continue
            hist = tramo(sorted(cal_s.get(f["serie_id"], []), key=lambda x: x["periodo"]), f["origen"]) if f["serie_id"] != "ventas_cop:Total" else []
            ref = pron_media_movil_3(hist, f["horizonte_meses"]) if len(hist) >= 3 else None
            banda = None if f.get("banda_inferior") is None else f["banda_inferior"] <= obs <= f["banda_superior"]
            ev.append((f["valor"] - obs, obs, None if ref is None else ref - obs, banda))
        pol = {"id": "pronostico_por_serie_y_horizonte", "version": man["modelo"]["version"]}
        comun = dict(modelo_id="demanda", variante=variante("demanda", man["modelo"]["version"]), version_artefacto=man["modelo"]["version"], origen=origen_r,
                     corte=man["corte"], periodo=man["origen"], universo=u, huella_datos=datos.huella_datos, politica=pol, restriccion=_restriccion(u),
                     comparacion={"unidad": fs[0]["unidad"], "horizontes": [1, 2, 3]})
        if not ev:
            out.append(M.observacion(grupo="desempeno", madurez="pendiente", conteos={"objetivos": total, "observados": 0}, metricas={},
                                     motivos=["Ningún mes objetivo está completo en la cobertura declarada"], **comun))
            continue
        n = len(ev)
        abs_e = [abs(e) for e, *_ in ev]
        suma_obs = sum(abs(o) for _, o, *_ in ev)
        con_ref = [r for *_, r, _ in ev if r is not None]
        bandas = [b for *_, b in ev if b is not None]
        out.append(M.observacion(grupo="desempeno", madurez="madura" if n == total else "parcial", conteos={"objetivos": total, "observados": n, "unidad": fs[0]["unidad"]},
                                 metricas={"mae": M.metrica(round(sum(abs_e) / n, 6), soporte=n, unidad=fs[0]["unidad"],
                                                            referencia={"id": "media_movil_3", **M.metrica(round(sum(abs(r) for r in con_ref) / len(con_ref), 6) if con_ref else None,
                                                                                                          soporte=len(con_ref), motivo="sin historia para la referencia")}),
                                           "wape": M.metrica(round(sum(abs_e) / suma_obs, 6) if suma_obs else None, soporte=n, motivo="suma observada cero"),
                                           "sesgo": M.metrica(round(sum(e for e, *_ in ev) / n, 6), soporte=n, unidad=fs[0]["unidad"]),
                                           "cobertura_banda": M.tasa(sum(bandas), len(bandas), "sin bandas publicadas con objetivo observado")},
                                 motivos=["Errores en la unidad de la serie; COP y unidades nunca se mezclan"], **comun))
    return out


def resultados(db: BaseDatos, datos, modelo: str | None = None) -> dict:
    """Desempeño de todo lo publicado con resultados maduros según ``datos`` (revisión A01). Idempotente."""
    with db.conexion() as con:
        cierres = [r[0] for r in con.execute("SELECT id FROM cierres ORDER BY corte")]
        sombras = [dict(r) for r in con.execute("SELECT id, modelo_id, manifiesto_json FROM sombra_publicaciones ORDER BY corte, importada_en")]
    res = Counter()
    nuevas = []
    for cid in cierres if modelo in (None, "compra_30d") else []:
        with db.transaccion() as con:
            r = con.execute("SELECT manifiesto_json, huella FROM cierres WHERE id = ?", (cid,)).fetchone()
            man = loads(r["manifiesto_json"])
            filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM an_filas WHERE cierre_id = ? AND tabla = 'predicciones_clientes'", (cid,))]
            if not filas:
                continue
            version = (man.get("versiones") or {}).get("modelo_compra") or filas[0].get("version_modelo")
            pol = {"id": "agenda_c1", "version": (man.get("versiones") or {}).get("reglas"), "umbral": filas[0].get("umbral")}
            for o in resultados_clientes("compra_30d", {"tipo": "cierre", "id": cid}, man["corte"], version, filas, datos, pol):
                x = M.registrar_y_evaluar(con, o)
                res[x["estado"]] += 1
                nuevas += x["avisos"]
    for s in sombras:
        mid = s["modelo_id"]
        if modelo and mid != modelo:
            continue
        man = loads(s["manifiesto_json"])
        with db.transaccion() as con:
            vig = _vigente(con, s["id"])
            origen = {"tipo": "sombra", "id": s["id"]}
            if mid in ("inactividad_60d", "proxima_compra"):
                filas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_predicciones WHERE sombra_id = ? AND modelo_id = ?", (s["id"], mid))]
                pol = {"id": "sombra_por_clientes", "version": man["modelo"]["version"]}
                obs = resultados_clientes(mid, origen, man["corte"], man["modelo"]["version"], filas, datos, pol) if mid == "inactividad_60d" else \
                    resultados_proxima(origen, man["corte"], man["modelo"]["version"], filas, datos, pol)
            elif mid == "venta_cruzada":
                obs = resultados_venta_cruzada(origen, man, [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_recomendaciones WHERE sombra_id = ?", (s["id"],))], datos)
            elif mid == "demanda":
                obs = resultados_demanda(origen, man, [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_pronosticos WHERE sombra_id = ?", (s["id"],))],
                                         [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_calendario_demanda WHERE sombra_id = ?", (s["id"],))], datos)
            else:
                obs = []  # anomalias: el desempeño solo existe con revisiones humanas (grupo «revision»)
            for o in obs:
                x = M.registrar_y_evaluar(con, o, vigente=vig, sombra_id=s["id"])
                res[x["estado"]] += 1
                nuevas += x["avisos"]
    return {"observaciones": dict(res), "avisos_nuevos": nuevas, "datos_hasta": datos.observado_hasta.isoformat() if datos.observado_hasta else None,
            "huella_datos": datos.huella_datos}
