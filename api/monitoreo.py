"""Monitoreo común de los modelos M1–M6 (contrato ``jacomind.monitoreo.v1``, reglas ``modelos/config/monitoreo.json``).

* Observaciones inmutables, vinculadas a su origen (cierre, publicación en sombra, evaluación de resultados o revisión),
  separadas en cuatro grupos: A ``salud`` (datos y publicación), B ``distribucion`` (puntajes y tasas: un cambio NO prueba
  deterioro), C ``desempeno`` (resultados observados, solo con madurez) y D ``revision`` (revisión humana).
* Idempotentes: la misma observación no se duplica; una corrección (mismo origen, grupo, universo y periodo con contenido
  distinto) crea otra enlazada a la anterior y conserva ambas. Una publicación antigua importada sin activar queda como
  ``vigente = 0``: no es referencia de comparación ni genera avisos estadísticos.
* Reglas versionadas con dirección de cada métrica, soporte mínimo, comparabilidad y tratamiento de ceros y nulos.
  Integridad: una publicación rechazada no se importa y deja aviso ``integridad``. Ningún aviso promueve, revierte ni
  reentrena modelos. Las métricas no estimables son nulas con motivo, nunca ceros.
* Solo biblioteca estándar. La API consume lo persistido; los resultados maduros se calculan con ``python -m api monitoreo``.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from .base import BaseDatos, ahora, dumps, loads

CONTRATO = "jacomind.monitoreo.v1"
REGLAS = Path(__file__).resolve().parents[1] / "modelos" / "config" / "monitoreo.json"
GRUPOS = ("salud", "distribucion", "desempeno", "revision")
MADUREZ = ("no_aplica", "pendiente", "parcial", "madura")
ESTADOS_MODELO = {"sin_informacion": "Sin información", "pendiente_madurez": "Pendiente de madurez", "no_comparable": "No comparable",
                  "sin_problemas": "Sin problemas detectados", "requiere_revision": "Requiere revisión", "publicacion_rechazada": "Publicación rechazada"}
MODELOS = ("compra_30d", "inactividad_60d", "proxima_compra", "venta_cruzada", "demanda", "anomalias")


@lru_cache(maxsize=1)
def reglas() -> dict:
    return json.loads(REGLAS.read_text(encoding="utf-8"))


def _canon(x) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def _sha(x) -> str:
    return hashlib.sha256(_canon(x).encode()).hexdigest()


# Contrato de observación ---------------------------------------------------------------------------------------------
def metrica(valor=None, *, numerador=None, denominador=None, soporte=None, motivo=None, unidad=None, referencia=None) -> dict:
    """Métrica con soporte. ``valor`` nulo exige motivo: una métrica desconocida nunca se convierte en cero."""
    m = {"valor": valor, "numerador": numerador, "denominador": denominador, "soporte": soporte if soporte is not None else denominador}
    if unidad is not None:
        m["unidad"] = unidad
    if referencia is not None:
        m["referencia"] = referencia
    if valor is None:
        m["motivo"] = motivo or "no estimable"
    return m


def tasa(numerador: int, denominador: int, motivo_cero: str = "denominador cero") -> dict:
    return metrica(round(numerador / denominador, 6) if denominador else None, numerador=numerador, denominador=denominador,
                   motivo=None if denominador else motivo_cero)


def observacion(*, modelo_id: str, variante: str | None, version_artefacto: str | None, origen: dict, corte: str, universo: str, grupo: str,
                conteos: dict, metricas: dict, madurez: str = "no_aplica", periodo: str | None = None, huella_datos: str | None = None,
                politica: dict | None = None, comparacion: dict | None = None, motivos: list | None = None, restriccion: str | None = None,
                emitido_en: str | None = None, extra: dict | None = None) -> dict:
    """Observación ``jacomind.monitoreo.v1``. ``comparacion`` define qué hace comparables dos observaciones."""
    obs = {"contrato": CONTRATO, "reglas": reglas()["version"], "modelo_id": modelo_id, "variante": variante, "version_artefacto": version_artefacto,
           "origen": origen, "corte": corte, "emitido_en": emitido_en, "universo": universo, "periodo": periodo or corte[:7], "grupo": grupo,
           "huella_datos": huella_datos, "politica": politica or {}, "conteos": conteos, "metricas": metricas, "madurez": madurez,
           "motivos": motivos or [], "restriccion": restriccion}
    # Comparables = misma definición: reglas (definen las métricas), modelo, grupo, universo, política y su versión, y lo que declare
    # ``comparacion`` (horizonte, cupo, referencia, unidad). No depende de qué métricas estén presentes (una pendiente no tiene).
    obs["clave_comparacion"] = _sha({"reglas": obs["reglas"], "modelo": modelo_id, "grupo": grupo, "universo": universo, "politica": obs["politica"],
                                     **(comparacion or {})})
    if extra:
        obs["extra"] = extra
    return obs


def validar_observacion(o: dict) -> list[str]:
    e = []
    if o.get("contrato") != CONTRATO:
        e.append("contrato distinto de jacomind.monitoreo.v1")
    if o.get("modelo_id") not in MODELOS:
        e.append(f"modelo_id desconocido: {o.get('modelo_id')!r}")
    if o.get("grupo") not in GRUPOS or o.get("madurez") not in MADUREZ:
        e.append("grupo o madurez no admitidos")
    if not isinstance(o.get("origen"), dict) or o["origen"].get("tipo") not in ("cierre", "sombra", "resultados", "revision") or not o["origen"].get("id"):
        e.append("origen incompleto")
    for k, m in (o.get("metricas") or {}).items():
        v = m.get("valor") if isinstance(m, dict) else None
        if not isinstance(m, dict) or (v is None and not m.get("motivo")):
            e.append(f"métrica {k}: nula sin motivo")
        elif v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf"))):
            e.append(f"métrica {k}: valor no finito")
    if o.get("grupo") == "desempeno" and o.get("madurez") == "pendiente" and any((m or {}).get("valor") is not None for m in (o.get("metricas") or {}).values()):
        e.append("una observación de desempeño pendiente de madurez no puede tener métricas")
    return e


def _clave_logica(o: dict) -> str:
    return "|".join(str(x) for x in (o["modelo_id"], o.get("variante"), o["origen"]["tipo"], o["origen"]["id"], o["grupo"], o["universo"], o.get("periodo")))


# Persistencia --------------------------------------------------------------------------------------------------------
def registrar_aviso(con, clave: str, modelo_id: str, tipo: str, severidad: str, mensaje: str, datos=None, sombra_id: str | None = None, *,
                    regla_id: str | None = None, observacion_id: str | None = None, universo: str | None = None, periodo: str | None = None,
                    restriccion: str | None = None, actor: str = "sistema") -> bool:
    """Inserta el aviso una sola vez por clave y registra su creación. Devuelve True si es nuevo."""
    cur = con.execute("""INSERT OR IGNORE INTO avisos_modelos (clave, modelo_id, sombra_id, tipo, severidad, mensaje, datos_json, creado_en,
                         regla_id, regla_version, observacion_id, universo, periodo, restriccion, estado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'activo')""",
                      (clave, modelo_id, sombra_id, tipo, severidad, mensaje, dumps(datos) if datos is not None else None, ahora(),
                       regla_id or tipo, reglas()["version"], observacion_id, universo, periodo, restriccion))
    if cur.rowcount == 1:
        con.execute("INSERT INTO avisos_eventos (clave_aviso, accion, actor, fecha, motivo) VALUES (?,?,?,?,?)", (clave, "creado", actor, ahora(), mensaje))
        return True
    return False


def registrar_integridad(db: BaseDatos, modelo_id: str, errores: list[str], origen: str) -> None:
    """Aviso de integridad en una transacción propia (la publicación rechazada no deja filas)."""
    huella = hashlib.sha256(("\n".join(errores) + origen).encode()).hexdigest()[:16]
    with db.transaccion() as con:
        registrar_aviso(con, f"integridad:{modelo_id}:{huella}", modelo_id, "publicacion_rechazada", "integridad",
                        f"Publicación rechazada por integridad ({len(errores)} {'error' if len(errores) == 1 else 'errores'}): no se importó.", {"origen": origen, "errores": errores[:10]},
                        regla_id="integridad")


def registrar_observacion(con, obs: dict, *, vigente: bool = True) -> tuple[str, str]:
    """Persiste ``obs``. Devuelve (id, 'nueva' | 'existente' | 'correccion')."""
    errores = validar_observacion(obs)
    if errores:
        raise ValueError("Observación de monitoreo inválida: " + "; ".join(errores))
    oid, logica = _sha(obs), _clave_logica(obs)
    if con.execute("SELECT 1 FROM monitoreo_observaciones WHERE id = ?", (oid,)).fetchone():
        return oid, "existente"
    prev = con.execute("SELECT id FROM monitoreo_observaciones WHERE clave_logica = ? AND reemplazada_por IS NULL ORDER BY creada_en DESC LIMIT 1",
                       (logica,)).fetchone()
    con.execute("""INSERT INTO monitoreo_observaciones (id, clave_logica, modelo_id, variante, version_artefacto, origen_tipo, origen_id, corte, periodo,
                   universo, grupo, madurez, clave_comparacion, restriccion, vigente, anterior_id, datos_json, creada_en)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (oid, logica, obs["modelo_id"], obs.get("variante"), obs.get("version_artefacto"), obs["origen"]["tipo"], obs["origen"]["id"], obs["corte"],
                 obs.get("periodo"), obs["universo"], obs["grupo"], obs["madurez"], obs["clave_comparacion"], obs.get("restriccion"), int(vigente),
                 prev["id"] if prev else None, dumps(obs), ahora()))
    if prev:
        con.execute("UPDATE monitoreo_observaciones SET reemplazada_por = ? WHERE id = ?", (oid, prev["id"]))
        return oid, "correccion"
    return oid, "nueva"


def _anterior(con, obs: dict, oid: str):
    """Observación vigente anterior del mismo modelo, grupo y universo, de OTRO origen (corte menor o igual: una publicación
    que sustituye a otra del mismo corte se compara con ella)."""
    r = con.execute("""SELECT id, datos_json, clave_comparacion FROM monitoreo_observaciones WHERE modelo_id = ? AND grupo = ? AND universo = ?
                       AND vigente = 1 AND reemplazada_por IS NULL AND id <> ? AND origen_id <> ? AND corte <= ?
                       ORDER BY corte DESC, creada_en DESC, rowid DESC LIMIT 1""",
                    (obs["modelo_id"], obs["grupo"], obs["universo"], oid, obs["origen"]["id"], obs["corte"])).fetchone()
    return (loads(r["datos_json"]), r["clave_comparacion"]) if r else (None, None)


def _valor(o: dict, k: str):
    return ((o.get("metricas") or {}).get(k) or {}).get("valor")


def deterioro_relativo(x, r, direccion: str) -> tuple[float | None, str | None]:
    """(d, motivo). d > 0 = peor que la referencia. Nunca divide por cero ni convierte un nulo en cero."""
    if x is None or r is None:
        return None, "valor_ausente"
    if r == 0:
        return (0.0, None) if x == r else (None, "referencia_cero")
    return ((x - r) / abs(r) if direccion == "menor" else (r - x) / abs(r)), None


def evaluar_reglas(con, obs: dict, oid: str, *, sombra_id: str | None = None) -> list[dict]:
    """Aplica las reglas versionadas a una observación VIGENTE y persiste los avisos (idempotentes por clave)."""
    rg, out = reglas()["reglas"], []
    m, u, base = obs["modelo_id"], obs["universo"], f"{obs['origen']['id']}:{obs['universo']}"
    kw = dict(observacion_id=oid, universo=u, periodo=obs.get("periodo"), restriccion=obs.get("restriccion"))

    def aviso(tipo, severidad, mensaje, datos, clave=None):
        clave = clave or f"{tipo}:{base}"
        if registrar_aviso(con, clave, m, tipo, severidad, mensaje, datos, sombra_id, regla_id=tipo, **kw):
            out.append({"tipo": tipo, "clave": clave, "universo": u})
    prev, clave_prev = _anterior(con, obs, oid)
    if obs["grupo"] == "salud":
        el = obs["conteos"].get("elegibles")
        if el == 0:
            aviso("sin_registros", "estadistico", f"{u}: el periodo publicado no tiene registros elegibles (0): cobertura no estimable.",
                  {"elegibles": 0, "regla": rg["sin_registros"]["definicion"]})
    if prev is None or obs["grupo"] == "revision":
        return out
    if clave_prev != obs["clave_comparacion"]:
        aviso("cambio_politica", "informativo", f"{u}: cambió la política, la versión o la definición respecto de {prev['origen']['id']}: "
              "las observaciones no son comparables y no se evalúa deterioro.", {"anterior": prev["origen"], "politica_anterior": prev.get("politica"),
                                                                                  "politica_actual": obs.get("politica")})
        return out
    if obs["grupo"] == "salud":
        c, cp = _valor(obs, "cobertura"), _valor(prev, "cobertura")
        if c is not None and cp is not None:
            caida = round(100 * (cp - c), 4)
            if caida >= rg["caida_cobertura"]["umbral_pp"]:
                aviso("caida_cobertura", "estadistico", f"{u}: la cobertura bajó {caida} pp ({cp:.1%} → {c:.1%}) frente a {prev['origen']['id']}; revisar historia o datos.",
                      {"previa": cp, "actual": c, "caida_pp": caida, "umbral_pp": rg["caida_cobertura"]["umbral_pp"],
                       "soporte": [prev["conteos"].get("elegibles"), obs["conteos"].get("elegibles")]})
    if obs["grupo"] == "distribucion" and "alertas_por_100" in obs["metricas"]:
        rgl = rg["cambio_tasa_alertas"]
        a, b = _valor(obs, "alertas_por_100"), _valor(prev, "alertas_por_100")
        na, nb = obs["conteos"].get("validas", 0), prev["conteos"].get("validas", 0)
        if a is not None and b is not None and na >= rgl["min_operaciones"] and nb >= rgl["min_operaciones"]:
            if b > 0 and abs(a - b) / b >= rgl["umbral_relativo"]:
                aviso("cambio_tasa_alertas", "estadistico", f"{u}: alertas por 100 válidas {b} → {a} (cambio relativo {abs(a - b) / b:.0%}, n={nb}→{na}). "
                      "Con política de cupo la tasa depende del cupo y de la cobertura: no indica deterioro predictivo sin revisiones comparables.",
                      {"previa_por_100": b, "actual_por_100": a, "cambio_relativo": round(abs(a - b) / b, 4), "umbral": rgl["umbral_relativo"], "validas": [nb, na]})
            elif b == 0 and obs["conteos"].get("alertas", 0) >= rgl["min_alertas_desde_cero"]:
                aviso("cambio_tasa_alertas", "estadistico", f"{u}: aparecen alertas ({a} por 100) donde antes no había (cambio desde cero; relativo no definido).",
                      {"previa_por_100": 0, "actual_por_100": a, "cambio_relativo": None, "motivo": "desde_cero", "validas": [nb, na]})
    if obs["grupo"] == "desempeno" and obs["madurez"] == "madura":
        rgl, dirs = rg["deterioro_frente_referencia"], reglas()["direccion_metricas"]
        for k, mt in obs["metricas"].items():
            if k not in dirs or not isinstance(mt.get("referencia"), dict):
                continue
            d, _ = deterioro_relativo(mt.get("valor"), mt["referencia"].get("valor"), dirs[k])
            pm = (prev.get("metricas") or {}).get(k) or {}
            dp, _ = deterioro_relativo(pm.get("valor"), (pm.get("referencia") or {}).get("valor"), dirs[k]) if prev["madurez"] == "madura" else (None, None)
            soporte_ok = (mt.get("soporte") or 0) >= rgl["soporte_minimo"] and (pm.get("soporte") or 0) >= rgl["soporte_minimo"]
            if d is not None and dp is not None and d > rgl["umbral_relativo"] and dp > rgl["umbral_relativo"] and soporte_ok:
                aviso("deterioro_frente_referencia", "estadistico",
                      f"{u}: {k} peor que la referencia en más de {rgl['umbral_relativo']:.0%} en dos cortes maduros consecutivos ({prev['corte']}: {dp:.0%}; {obs['corte']}: {d:.0%}). "
                      "Revisar antes de cualquier decisión: no se promueve, revierte ni reentrena automáticamente.",
                      {"metrica": k, "direccion": dirs[k], "deterioro_actual": round(d, 4), "deterioro_anterior": round(dp, 4), "umbral": rgl["umbral_relativo"],
                       "soporte": [pm.get("soporte"), mt.get("soporte")]}, clave=f"deterioro_frente_referencia:{base}:{k}")
    return out


def registrar_y_evaluar(con, obs: dict, *, vigente: bool = True, sombra_id: str | None = None) -> dict:
    oid, estado = registrar_observacion(con, obs, vigente=vigente)
    avisos_nuevos = evaluar_reglas(con, obs, oid, sombra_id=sombra_id) if vigente and estado != "existente" else []
    return {"id": oid, "estado": estado, "avisos": avisos_nuevos}


# Compatibilidad M6 (umbrales del manifiesto) ---------------------------------------------------------------------------
def comparar(actual: dict, previo: dict | None, umbrales: dict) -> list[dict]:
    """[Compatibilidad] comparación directa de dos bloques ``monitoreo.universos`` de M6. Ver ``evaluar_reglas``."""
    out = []
    for u, a in (actual or {}).items():
        p = (previo or {}).get(u)
        if not p or not a.get("validas") or not p.get("validas"):
            continue
        if a.get("cobertura") is not None and p.get("cobertura") is not None:
            caida = round(100 * (p["cobertura"] - a["cobertura"]), 4)
            if caida >= float(umbrales["caida_cobertura_pp"]):
                out.append({"tipo": "caida_cobertura", "universo": u, "datos": {"previa": p["cobertura"], "actual": a["cobertura"], "caida_pp": caida}})
    return out


# Consulta --------------------------------------------------------------------------------------------------------------
def avisos(con, modelo_id: str | None = None, *, estado: str | None = None, severidad: str | None = None, tipo: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM avisos_modelos WHERE 1=1", []
    for col, val in (("modelo_id", modelo_id), ("estado", estado), ("severidad", severidad), ("tipo", tipo)):
        if val:
            q += f" AND {col} = ?"
            args.append(val)
    return [dict(r, datos=loads(r["datos_json"]) if r["datos_json"] else None) | {"datos_json": None}
            for r in (dict(x) for x in con.execute(q + " ORDER BY creado_en DESC, clave", args))]


def estado_modelo(obs: list[dict], avs: list[dict]) -> str:
    """Estado visible de un modelo. «Sin problemas» solo con desempeño maduro observado y sin avisos activos."""
    activos = [a for a in avs if a.get("estado") != "resuelto"]
    if not obs and not activos:
        return "sin_informacion"
    if any(a["severidad"] == "integridad" for a in activos):
        return "publicacion_rechazada"
    if any(a["severidad"] == "estadistico" for a in activos):
        return "requiere_revision"
    vigentes = [o for o in obs if o["vigente"] and not o["reemplazada_por"]]
    if vigentes and any(a["tipo"] == "cambio_politica" for a in activos):
        ultimo = max(o["corte"] for o in vigentes)
        if any(a["tipo"] == "cambio_politica" and (a.get("periodo") or "")[:7] == ultimo[:7] for a in activos):
            return "no_comparable"
    desempeno = [o for o in vigentes if o["grupo"] == "desempeno"]
    if not desempeno:
        return "pendiente_madurez"
    ultimo = max(o["corte"] for o in desempeno)  # el estado describe la ÚLTIMA publicación, no un corte maduro antiguo
    if any(o["madurez"] != "madura" for o in desempeno if o["corte"] == ultimo):
        return "pendiente_madurez"
    if not any(m.get("valor") is not None for o in desempeno if o["corte"] == ultimo for m in (o["datos"]["metricas"] if "datos" in o else loads(o["datos_json"])["metricas"]).values()):
        return "sin_informacion"  # maduro pero sin nada estimable (p. ej. todo en abstención): no es «sin problemas»
    return "sin_problemas"


# API (permisos en el servidor) ------------------------------------------------------------------------------------------
# Un panel global no abre acceso indirecto: cada modelo exige además su propio permiso de consulta, y en M5 las series en COP
# solo con demanda.ver_cop (las de unidades con demanda.ver_unidades). El portal externo no tiene monitoreo.ver.
PERMISO_MODELO = {"compra_30d": ("cartera.ver",), "inactividad_60d": ("prevencion.ver",), "proxima_compra": ("proxima.ver",),
                  "venta_cruzada": ("venta_cruzada.ver",), "demanda": ("demanda.ver_cop", "demanda.ver_unidades"), "anomalias": ("anomalias.ver",)}
NOMBRES = {"compra_30d": "M1 · Compra a 30 días", "inactividad_60d": "M2 · Inactividad a 60 días", "proxima_compra": "M3 · Próxima compra",
           "venta_cruzada": "M4 · Venta cruzada", "demanda": "M5 · Pronóstico de demanda", "anomalias": "M6 · Operaciones atípicas"}


def modelos_visibles(usuario) -> list[str]:
    return [m for m in MODELOS if any(usuario.puede(p) for p in PERMISO_MODELO[m])]


def _restriccion_visible(usuario, restriccion) -> bool:
    if restriccion == "cop":
        return usuario.puede("demanda.ver_cop")
    if restriccion == "unidades":
        return usuario.puede("demanda.ver_unidades")
    return True


def _obs_fila(r) -> dict:
    return {k: r[k] for k in ("id", "modelo_id", "variante", "version_artefacto", "origen_tipo", "origen_id", "corte", "periodo", "universo", "grupo",
                              "madurez", "vigente", "anterior_id", "reemplazada_por", "creada_en", "restriccion")} | {"datos": loads(r["datos_json"])}


def panel(con, usuario, *, modelo: str | None = None, variante: str | None = None, periodo: str | None = None, estado: str | None = None,
          severidad: str | None = None, tipo: str | None = None) -> dict:
    """Resumen por modelo desde lo PERSISTIDO (no calcula métricas retrospectivas en la consulta)."""
    from .base import ErrorApi
    visibles = modelos_visibles(usuario)
    if modelo and modelo not in visibles:
        raise ErrorApi(403, "sin_permiso", "Tu perfil no tiene acceso al monitoreo de ese modelo")
    out = []
    for m in [modelo] if modelo else visibles:
        q, args = "SELECT * FROM monitoreo_observaciones WHERE modelo_id = ?", [m]
        if variante:
            q += " AND (variante = ? OR version_artefacto = ?)"
            args += [variante, variante]
        if periodo:
            q += " AND (periodo LIKE ? OR corte LIKE ?)"
            args += [periodo + "%", periodo + "%"]
        obs = [o for o in (_obs_fila(r) for r in con.execute(q + " ORDER BY corte DESC, creada_en DESC", args)) if _restriccion_visible(usuario, o["restriccion"])]
        avs = [a for a in avisos(con, m) if _restriccion_visible(usuario, a.get("restriccion"))]
        est = estado_modelo(obs, avs)
        if estado and est != estado:
            continue
        avs_f = [a for a in avs if (not severidad or a["severidad"] == severidad) and (not tipo or a["tipo"] == tipo)]
        vig = [o for o in obs if o["vigente"] and not o["reemplazada_por"]]
        ultimo = max((o["corte"] for o in vig), default=None)
        recientes = [o for o in vig if o["corte"] == ultimo]
        out.append({"modelo_id": m, "nombre": NOMBRES[m], "estado": est, "estado_texto": ESTADOS_MODELO[est], "ultimo_corte": ultimo,
                    "ultima_publicacion": recientes[0]["origen_id"] if recientes else None,
                    "salud": [o for o in recientes if o["grupo"] == "salud"], "distribucion": [o for o in recientes if o["grupo"] == "distribucion"],
                    "desempeno": [o for o in vig if o["grupo"] == "desempeno"][:12], "revision": [o for o in recientes if o["grupo"] == "revision"],
                    "avisos_activos": [a for a in avs_f if a.get("estado") != "resuelto"], "avisos_resueltos": sum(1 for a in avs_f if a.get("estado") == "resuelto"),
                    "observaciones": len(obs), "historicas_no_vigentes": sum(1 for o in obs if not o["vigente"]),
                    "corregidas": sum(1 for o in obs if o["reemplazada_por"])})
    return {"reglas": {k: reglas()[k] for k in ("version", "contrato", "nota")}, "estados": ESTADOS_MODELO, "modelos": out,
            "puede_reconocer": usuario.puede("monitoreo.reconocer"),
            "nota": "Una variación de distribución no demuestra deterioro predictivo; ningún aviso promueve, revierte ni reentrena modelos."}


def detalle_aviso(con, usuario, clave: str) -> dict:
    from .base import ErrorApi
    r = con.execute("SELECT * FROM avisos_modelos WHERE clave = ?", (clave,)).fetchone()
    if not r or r["modelo_id"] not in modelos_visibles(usuario) or not _restriccion_visible(usuario, r["restriccion"]):
        raise ErrorApi(404, "no_encontrado", "Aviso no encontrado")
    a = dict(r) | {"datos": loads(r["datos_json"]) if r["datos_json"] else None, "datos_json": None}
    obs = con.execute("SELECT * FROM monitoreo_observaciones WHERE id = ?", (r["observacion_id"],)).fetchone() if r["observacion_id"] else None
    ev = [dict(x) for x in con.execute("SELECT * FROM avisos_eventos WHERE clave_aviso = ? ORDER BY id", (clave,))]
    return {"aviso": a, "observacion": _obs_fila(obs) if obs else None, "historial": ev,
            "regla": reglas()["reglas"].get(a.get("regla_id") or a["tipo"]) or {}}


def cambiar_estado_aviso(db: BaseDatos, usuario, clave: str, accion: str, motivo: str) -> dict:
    """Reconocer (alguien lo revisa) NO es resolver (el problema se corrigió o se explicó). El aviso original se conserva."""
    from .base import ErrorApi, auditar
    if accion not in ("reconocido", "resuelto"):
        raise ErrorApi(400, "accion_invalida", "La acción debe ser reconocido o resuelto")
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise ErrorApi(400, "motivo_obligatorio", "Indica el motivo")
    with db.transaccion() as con:
        r = con.execute("SELECT * FROM avisos_modelos WHERE clave = ?", (clave,)).fetchone()
        if not r or r["modelo_id"] not in modelos_visibles(usuario) or not _restriccion_visible(usuario, r["restriccion"]):
            raise ErrorApi(404, "no_encontrado", "Aviso no encontrado")
        if r["estado"] == "resuelto":
            raise ErrorApi(409, "ya_resuelto", "El aviso ya está resuelto")
        con.execute("UPDATE avisos_modelos SET estado = ? WHERE clave = ?", (accion, clave))
        con.execute("INSERT INTO avisos_eventos (clave_aviso, accion, actor, fecha, motivo) VALUES (?,?,?,?,?)", (clave, accion, usuario.id, ahora(), motivo))
        auditar(con, usuario.id, f"monitoreo.{accion}", clave, "ok", None, {"motivo": motivo})
    return {"clave": clave, "estado": accion}


def exportar_csv(con, usuario, modelo: str | None = None) -> str:
    import csv
    import io
    d = panel(con, usuario, modelo=modelo)
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["modelo_id", "estado", "corte", "grupo", "universo", "madurez", "metrica", "valor", "numerador", "denominador", "soporte", "motivo"])
    for m in d["modelos"]:
        for g in ("salud", "distribucion", "desempeno", "revision"):
            for o in m[g]:
                for k, x in o["datos"]["metricas"].items():
                    w.writerow([m["modelo_id"], m["estado"], o["corte"], g, o["universo"], o["madurez"], k, x.get("valor"), x.get("numerador"),
                                x.get("denominador"), x.get("soporte"), x.get("motivo")])
    return b.getvalue()
