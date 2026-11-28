"""M6 · Operaciones atípicas (en uso): cola de revisión para Operaciones y Finanzas.

* La publicación llega en sombra (``modelos.cli puntuar --modelo anomalias``), verificada (sello, huellas, contrato y
  coherencia). Un rechazo de integridad no se importa y queda como aviso persistente.
* Capas separadas: resultado inmutable (``sombra_anomalias``), caso de revisión (``casos_anomalia``) e historial
  (``eventos_anomalia``). Reimportar no duplica casos ni eventos; cambiar corte, puntaje o versión no reabre una decisión.
  Una corrección de los valores observados crea un caso nuevo enlazado al anterior, que conserva su decisión.
* Una publicación de un corte anterior se guarda sin desplazar la activa y sin abrir casos ni eventos.
* La cola NO modifica importes, no anula operaciones ni afecta al cliente; la corrección contable sigue el flujo de datos.
* Permisos en el servidor: ``anomalias.ver`` (consulta y detalle), ``anomalias.revisar`` (decisiones), ``anomalias.exportar``.
  El importe en COP solo se entrega con ``finanzas.ver`` (restricción financiera existente). El portal externo no recibe nada.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from contratos.validar import leer_publicacion_sombra

from . import monitoreo as M
from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, loads
from .estado_modelos import EN_USO

MODELO_ID = "anomalias"
ESTADOS = ("pendiente", "error_confirmado", "cambio_legitimo", "informacion_insuficiente")
DECISIONES = ("error_confirmado", "cambio_legitimo", "informacion_insuficiente")
NOTA = ("Cola de revisión humana. El puntaje indica rareza frente a operaciones comparables anteriores: "
        "no es una probabilidad de fraude ni demuestra un error. La cola no modifica importes, no anula operaciones ni afecta al cliente; "
        "una corrección contable se hace en el flujo de datos (nueva carga A01).")
METODO = {"isolation_forest": "Isolation Forest (candidato IA)", "mediana_mad": "Mediana/MAD contextual (referencia)"}


def _caso_id(f: dict) -> str:
    return f"{MODELO_ID}:{f['tipo_operacion']}:{f['operacion_id']}:{f['huella_valores'][:12]}"


def _evidencia(sid: str, f: dict) -> dict:
    return {"sombra_id": sid, "version_modelo": f["version_modelo"], "corte": f["corte"], "puntaje": f["puntaje"], "metodo": f["metodo"],
            "prioridad": f["prioridad"], "alerta": f["alerta"], "motivos": f["motivos"], "revision_datos": f.get("revision_datos")}


def _evento(con, caso_id: str, tipo: str, actor: str, *, clave: str | None = None, anterior=None, nuevo=None, motivo=None, evidencia=None,
            version=None, sombra_id=None) -> bool:
    cur = con.execute("""INSERT OR IGNORE INTO eventos_anomalia (caso_id, tipo, estado_anterior, estado_nuevo, actor, fecha, motivo, evidencia,
                         version_examinada, sombra_id, clave_idempotencia) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (caso_id, tipo, anterior, nuevo, actor, ahora(), motivo, evidencia, version, sombra_id, clave))
    return cur.rowcount == 1


def _abrir_o_actualizar(con, sid: str, f: dict, origen: str, actor: str) -> str:
    """Devuelve 'nuevo', 'correccion' o 'existente'. Nunca cambia el estado humano de un caso existente."""
    cid, ev = _caso_id(f), _evidencia(sid, f)
    if con.execute("SELECT 1 FROM casos_anomalia WHERE caso_id = ?", (cid,)).fetchone():
        con.execute("UPDATE casos_anomalia SET ultima_sombra = ?, ultima_evidencia_json = ?, actualizado_en = ? WHERE caso_id = ?", (sid, dumps(ev), ahora(), cid))
        _evento(con, cid, "evidencia_actualizada", actor, clave=f"evidencia:{cid}:{sid}", version=f["version_modelo"], sombra_id=sid,
                motivo="Nueva publicación de la misma operación (mismos valores): el estado de revisión no cambia")
        return "existente"
    prev = con.execute("""SELECT caso_id, estado, revision_datos FROM casos_anomalia WHERE tipo_operacion = ? AND operacion_id = ? AND reemplazado_por IS NULL
                          ORDER BY creado_en DESC LIMIT 1""", (f["tipo_operacion"], f["operacion_id"])).fetchone()
    con.execute("""INSERT INTO casos_anomalia (caso_id, tipo_operacion, operacion_id, huella_valores, revision_datos, caso_anterior, cliente_id, proveedor_id,
                   estado, origen, abierto_sombra, version_abierta, ultima_sombra, ultima_evidencia_json, creado_en, actualizado_en)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, f["tipo_operacion"], f["operacion_id"], f["huella_valores"], f.get("revision_datos"), prev["caso_id"] if prev else None,
                 f.get("cliente_id"), f.get("proveedor_id"), "pendiente", origen, sid, f["version_modelo"], sid, dumps(ev), ahora(), ahora()))
    _evento(con, cid, "apertura", actor, clave=f"apertura:{cid}", nuevo="pendiente", version=f["version_modelo"], sombra_id=sid,
            motivo=f"Caso abierto por {origen.replace('+', ' y ').replace('_', ' ')} en la publicación {sid}")
    if prev:
        con.execute("UPDATE casos_anomalia SET reemplazado_por = ?, actualizado_en = ? WHERE caso_id = ?", (cid, ahora(), prev["caso_id"]))
        _evento(con, cid, "correccion_datos", actor, clave=f"correccion:{prev['caso_id']}:{cid}", anterior=prev["estado"], nuevo="pendiente",
                version=f["version_modelo"], sombra_id=sid,
                motivo=f"Los valores observados cambiaron (revisión de datos {prev['revision_datos']} → {f.get('revision_datos')}): revisión nueva enlazada a "
                       f"{prev['caso_id']}, que conserva su decisión ({prev['estado']})")
        return "correccion"
    return "nuevo"


def importar_sombra(db: BaseDatos, directorio: str | Path, actor: str) -> dict:
    errores, man, tablas = leer_publicacion_sombra(directorio)
    if errores:
        M.registrar_integridad(db, MODELO_ID, errores, str(directorio))
        raise ErrorApi(422, "sombra_invalida", "La publicación en sombra no cumple el contrato (no se importa)", {"errores": errores[:20]})
    if man.get("modelo_id") != MODELO_ID:
        raise ErrorApi(422, "sombra_invalida", f"Se esperaba una publicación de {MODELO_ID}")
    sid = f"{MODELO_ID}:{man['corte']}:{man['sello'][:12]}"
    filas = tablas["anomalias_operaciones"]
    muestra = tablas.get("muestra_revision") or {"operaciones": []}
    en_muestra = {(m["tipo_operacion"], m["operacion_id"]) for m in muestra.get("operaciones", [])}
    with db.transaccion() as con:
        previo = con.execute("SELECT id, activa FROM sombra_publicaciones WHERE sello = ?", (man["sello"],)).fetchone()
        if previo:
            return {"sombra_id": previo["id"], "ya_importada": True, "activa": bool(previo["activa"])}
        actual = con.execute("SELECT corte, manifiesto_json FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()
        activar = actual is None or man["corte"] >= actual["corte"]  # una publicación antigua no desplaza a la activa
        if activar:
            con.execute("UPDATE sombra_publicaciones SET activa = 0 WHERE modelo_id = ?", (MODELO_ID,))
        con.execute("""INSERT INTO sombra_publicaciones (id, modelo_id, corte, version_modelo, artefacto_huella, sello, estado_experimento,
                       manifiesto_json, importada_en, importada_por, activa) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, MODELO_ID, man["corte"], man["modelo"]["version"], man["modelo"]["artefacto_huella"], man["sello"],
                     man["estado_experimento"], dumps(man), ahora(), actor, int(activar)))
        con.executemany("INSERT INTO sombra_anomalias (sombra_id, tipo_operacion, operacion_id, periodo, datos_json) VALUES (?,?,?,?,?)",
                        [(sid, f["tipo_operacion"], f["operacion_id"], f["periodo"], dumps(f)) for f in filas])
        con.executemany("INSERT INTO sombra_cobertura_anomalias (sombra_id, tipo_operacion, periodo, datos_json) VALUES (?,?,?,?)",
                        [(sid, c["tipo_operacion"], c["periodo"], dumps(c)) for c in tablas["cobertura_anomalias"]])
        con.execute("INSERT INTO sombra_muestras_revision (sombra_id, datos_json) VALUES (?,?)", (sid, dumps(muestra)))
        casos = {"nuevo": 0, "correccion": 0, "existente": 0}
        if activar:  # solo la publicación vigente abre casos: una antigua no produce eventos con cronología incoherente
            for f in filas:
                clave = (f["tipo_operacion"], f["operacion_id"])
                if f["alerta"] or clave in en_muestra:
                    origen = "+".join(x for x, ok in (("alerta", f["alerta"]), ("muestra_revision", clave in en_muestra)) if ok)
                    casos[_abrir_o_actualizar(con, sid, f, origen, actor)] += 1
        auditar(con, actor, "sombra.importar", sid, "ok" if activar else "importada_sin_activar", None,
                {"filas": len(filas), "activa": activar, "casos": casos})
    salida = {"sombra_id": sid, "ya_importada": False, "activa": activar, "filas": len(filas), "casos": casos}
    if not activar:
        salida["motivo"] = f"Corte {man['corte']} anterior al de la publicación activa ({actual['corte']}): se conserva sin desplazarla ni abrir casos."
    from .monitoreo_modelos import tras_importar
    salida = tras_importar(db, salida, actor)  # motor común de monitoreo (avisos persistentes e idempotentes)
    salida["avisos"] = (salida.get("monitoreo") or {}).get("avisos", [])
    return salida


# Consulta ----------------------------------------------------------------------------------------------------------------
def _activa(con):
    return con.execute("SELECT * FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()


def _visible(f: dict, usuario) -> dict:
    """Restricción financiera existente: el importe en COP solo con ``finanzas.ver``."""
    if usuario.puede("finanzas.ver"):
        return f
    return dict(f, importe_cop=None, importe_cop_oculto=True)


def _casos_vigentes(con) -> dict:
    return {(r["tipo_operacion"], r["operacion_id"]): dict(r) for r in con.execute("SELECT * FROM casos_anomalia WHERE reemplazado_por IS NULL")}


def metricas_revision(filas: list[dict], casos: dict, umbrales: dict) -> dict:
    """Métricas humanas con numeradores y denominadores; nulas con explicación si no son estimables. Las operaciones sin
    revisar nunca cuentan como falsas alertas."""
    rev = [(f, casos[(f["tipo_operacion"], f["operacion_id"])]) for f in filas
           if (f["tipo_operacion"], f["operacion_id"]) in casos and casos[(f["tipo_operacion"], f["operacion_id"])]["estado"] != "pendiente"
           and casos[(f["tipo_operacion"], f["operacion_id"])]["huella_valores"] == f["huella_valores"]]
    al_rev = [(f, c) for f, c in rev if f["alerta"] and c["estado"] in ("error_confirmado", "cambio_legitimo")]
    normales = [(f, c) for f, c in rev if c["estado"] == "cambio_legitimo"]
    minimo = int(umbrales.get("min_revisiones_precision", 30))
    prec = {"numerador": sum(c["estado"] == "error_confirmado" for _, c in al_rev), "denominador": len(al_rev)}
    prec["valor"] = round(prec["numerador"] / prec["denominador"], 4) if prec["denominador"] else None
    fa = {"numerador": sum(bool(f["alerta"]) for f, _ in normales), "denominador": len(normales)}
    fa["por_100"] = round(100 * fa["numerador"] / fa["denominador"], 2) if fa["denominador"] else None
    for m in (prec, fa):
        m["motivo"] = ("Sin revisiones humanas que permitan estimarla" if not m["denominador"] else
                       f"Soporte {m['denominador']} < {minimo}: valor descriptivo, no certifica la meta" if m["denominador"] < minimo else None)
    return {"revisadas": len(rev), "por_estado": {e: sum(c["estado"] == e for _, c in rev) for e in DECISIONES},
            "precision_alertas_revisadas": prec, "falsas_alertas_por_100_normales_revisadas": fa,
            "nota": "Informacion insuficiente no cuenta como normal ni como error. La prevalencia de casos sembrados no se usa para afirmar precisión comercial."}


def lista(con, usuario, universo: str = "venta", periodo: str | None = None, producto: str | None = None, moneda: str | None = None,
          estado: str | None = None, vista: str = "cola") -> dict:
    r = _activa(con)
    if not r:
        return {"estado": "sin_sombra", "experimental": False, "nota": NOTA, "mensaje": "No hay una publicación del modelo de operaciones atípicas importada."}
    if universo not in ("venta", "compra"):
        raise ErrorApi(400, "universo_invalido", "El universo debe ser venta o compra")
    if estado and estado not in ESTADOS + ("sin_caso",):
        raise ErrorApi(400, "estado_invalido", "Estado de revisión desconocido")
    man = loads(r["manifiesto_json"])
    todas = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_anomalias WHERE sombra_id = ?", (r["id"],))]
    casos = _casos_vigentes(con)
    muestra = loads((con.execute("SELECT datos_json FROM sombra_muestras_revision WHERE sombra_id = ?", (r["id"],)).fetchone() or ["{}"])[0])
    en_muestra = {(m["tipo_operacion"], m["operacion_id"]): m for m in muestra.get("operaciones", [])}
    filas = [f for f in todas if f["tipo_operacion"] == universo]
    opciones = {"periodos": sorted({f["periodo"] for f in filas}, reverse=True), "productos": sorted({f["producto_id"] for f in filas}),
                "monedas": sorted({f["moneda"] for f in filas})}
    items = []
    for f in filas:
        c = casos.get((f["tipo_operacion"], f["operacion_id"]))
        c = c if c and c["huella_valores"] == f["huella_valores"] else None
        est = c["estado"] if c else "sin_caso"
        en_cola = f["alerta"] or f["senalada_por_reglas"] or (f["tipo_operacion"], f["operacion_id"]) in en_muestra or c is not None
        if vista == "cola" and not en_cola:
            continue
        if vista == "sin_historia" and f["estado_puntuacion"] != "historia_insuficiente":
            continue
        if (periodo and f["periodo"] != periodo) or (producto and f["producto_id"] != producto) or (moneda and f["moneda"] != moneda) or (estado and est != estado):
            continue
        m = en_muestra.get((f["tipo_operacion"], f["operacion_id"]))
        items.append(dict(_visible(f, usuario), estado_revision=est, caso_id=c["caso_id"] if c else None,
                          fuera_de_cupo=bool(f["senalada_por_reglas"] and not f["alerta"]), muestra=m))
    items.sort(key=lambda x: (x["periodo"], -(x["alerta"]), x["prioridad"] if x["prioridad"] is not None else 10**9, x["operacion_id"]))
    items.sort(key=lambda x: x["periodo"], reverse=True)
    cob = [loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_cobertura_anomalias WHERE sombra_id = ? AND tipo_operacion = ? ORDER BY periodo",
                                            (r["id"], universo))]
    casos_u = [c for c in casos.values() if c["tipo_operacion"] == universo]
    mon = ((man.get("monitoreo") or {}).get("universos") or {}).get(universo) or {}
    resumen = {"validas": sum(c["validas"] for c in cob), "puntuadas": sum(c["puntuadas"] for c in cob),
               "abstenciones": sum(sum(c["abstenciones"].values()) for c in cob), "excluidas": _sumar([c["excluidas"] for c in cob]),
               "alertas": sum(c["alertas"] for c in cob), "capacidad_revision": sum(c["cupo"] for c in cob),
               "exceso_sobre_cupo": sum(c["exceso_sobre_cupo"] for c in cob),
               "casos_pendientes": sum(c["estado"] == "pendiente" for c in casos_u), "casos_revisados": sum(c["estado"] != "pendiente" for c in casos_u),
               "cobertura_temporal": "declarada" if universo == "venta" else "no_declarada",
               "nota_cobertura": None if universo == "venta" else (man.get("cobertura_por_universo") or {}).get("compra", {}).get("motivo"),
               "distribucion_puntaje": mon.get("distribucion_puntaje"), "alertas_por_100_validas": mon.get("alertas_por_100_validas")}
    decision = ((man.get("modelo") or {}).get("decision") or {}).get("decisiones", {}).get(universo)
    return {"estado": "ok", "experimental": False, "nota": NOTA, "advertencia": man.get("advertencia"), "universo": universo, "sombra_id": r["id"],
            "corte": man["corte"], "desde": man.get("desde"), "version": r["version_modelo"], "estado_experimento": EN_USO,
            "metodo": man["modelo"]["metodos_publicados"][universo], "metodo_texto": METODO.get(man["modelo"]["metodos_publicados"][universo]),
            "candidato": man["modelo"]["candidato_por_universo"][universo], "decision": decision, "politica_alertas": man.get("politica_alertas"),
            "emision": man.get("emision"), "resumen": resumen, "cobertura": cob, "opciones": opciones,
            "filtros": {"periodo": periodo, "producto": producto, "moneda": moneda, "estado": estado, "vista": vista},
            "metricas_revision": metricas_revision(filas, casos, (man.get("monitoreo") or {}).get("umbrales") or {}),
            "muestra": {k: muestra.get(k) for k in ("metodo", "objetivo", "seleccionadas", "deficit_alertadas_reasignado")},
            "puede_revisar": usuario.puede("anomalias.revisar"), "puede_exportar": usuario.puede("anomalias.exportar"),
            "importe_cop_visible": usuario.puede("finanzas.ver"), "items": items}


def _sumar(dicts: list[dict]) -> dict:
    out: dict = {}
    for d in dicts:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out


def detalle(con, usuario, tipo: str, operacion_id: str) -> dict:
    if tipo not in ("venta", "compra"):
        raise ErrorApi(400, "universo_invalido", "El tipo debe ser venta o compra")
    pubs = [dict(loads(x["datos_json"]), sombra_id=x["sombra_id"], publicacion_activa=bool(x["activa"]), importada_en=x["importada_en"])
            for x in con.execute("""SELECT a.datos_json, a.sombra_id, p.activa, p.importada_en FROM sombra_anomalias a JOIN sombra_publicaciones p ON p.id = a.sombra_id
                                    WHERE a.tipo_operacion = ? AND a.operacion_id = ? ORDER BY p.corte DESC, p.importada_en DESC""", (tipo, operacion_id))]
    if not pubs:
        raise ErrorApi(404, "no_encontrada", "La operación no aparece en ninguna publicación de operaciones atípicas")
    casos = [dict(c, ultima_evidencia=loads(c["ultima_evidencia_json"])) for c in
             (dict(x) for x in con.execute("SELECT * FROM casos_anomalia WHERE tipo_operacion = ? AND operacion_id = ? ORDER BY creado_en", (tipo, operacion_id)))]
    for c in casos:
        c.pop("ultima_evidencia_json", None)
    ids = [c["caso_id"] for c in casos]
    eventos = [dict(e) for e in con.execute(f"SELECT * FROM eventos_anomalia WHERE caso_id IN ({','.join('?' * len(ids))}) ORDER BY id", ids)] if ids else []
    return {"tipo_operacion": tipo, "operacion_id": operacion_id, "experimental": False, "nota": NOTA,
            "publicaciones": [_visible(p, usuario) for p in pubs], "casos": casos, "eventos": eventos,
            "caso_vigente": next((c for c in reversed(casos) if not c["reemplazado_por"]), None), "puede_revisar": usuario.puede("anomalias.revisar")}


def revisar(db: BaseDatos, usuario, tipo: str, operacion_id: str, estado: str, motivo: str, evidencia: str | None = None) -> dict:
    """Decisión humana con motivo obligatorio. No toca importes ni la operación: solo el caso y su historial."""
    if estado not in DECISIONES:
        raise ErrorApi(400, "estado_invalido", f"Estado de revisión no admitido: usa {', '.join(DECISIONES)}")
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise ErrorApi(400, "motivo_obligatorio", "Indica el motivo de la revisión")
    with db.transaccion() as con:
        r = _activa(con)
        caso = con.execute("SELECT * FROM casos_anomalia WHERE tipo_operacion = ? AND operacion_id = ? AND reemplazado_por IS NULL ORDER BY creado_en DESC LIMIT 1",
                           (tipo, operacion_id)).fetchone()
        if caso is None:  # revisión de una operación de la publicación activa que no estaba en la cola
            fila = con.execute("SELECT datos_json FROM sombra_anomalias WHERE sombra_id = ? AND tipo_operacion = ? AND operacion_id = ?",
                               (r["id"] if r else "", tipo, operacion_id)).fetchone()
            if not fila:
                raise ErrorApi(404, "no_encontrada", "La operación no está en la publicación activa de operaciones atípicas")
            _abrir_o_actualizar(con, r["id"], loads(fila[0]), "revision_manual", usuario.id)
            caso = con.execute("SELECT * FROM casos_anomalia WHERE tipo_operacion = ? AND operacion_id = ? AND reemplazado_por IS NULL ORDER BY creado_en DESC LIMIT 1",
                               (tipo, operacion_id)).fetchone()
        ev = loads(caso["ultima_evidencia_json"])
        con.execute("UPDATE casos_anomalia SET estado = ?, actualizado_en = ? WHERE caso_id = ?", (estado, ahora(), caso["caso_id"]))
        _evento(con, caso["caso_id"], "revision", usuario.id, anterior=caso["estado"], nuevo=estado, motivo=motivo, evidencia=(evidencia or "").strip() or None,
                version=ev.get("version_modelo"), sombra_id=ev.get("sombra_id"))
        auditar(con, usuario.id, "anomalias.revisar", caso["caso_id"], "ok", None, {"estado_anterior": caso["estado"], "estado": estado})
    from .monitoreo_modelos import observar_revision
    observar_revision(db, MODELO_ID)  # grupo D: resultados de revisión humana
    return {"caso_id": caso["caso_id"], "estado_anterior": caso["estado"], "estado": estado, "version_examinada": ev.get("version_modelo")}


def exportar_csv(con, usuario, universo: str = "venta") -> str:
    d = lista(con, usuario, universo)
    if d["estado"] != "ok":
        raise ErrorApi(404, "sin_sombra", d["mensaje"])
    campos = ["tipo_operacion", "operacion_id", "fecha", "producto_id", "cliente_id", "proveedor_id", "moneda", "cantidad", "valor_unitario",
              "referencia_cantidad", "referencia_valor_unitario", "soporte", "puntaje", "metodo", "prioridad", "alerta", "fuera_de_cupo", "estado_puntuacion",
              "estado_revision", "version_modelo", "corte"] + (["importe_cop"] if d["importe_cop_visible"] else [])
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(campos + ["motivos"])
    for it in d["items"]:
        w.writerow([it.get(k) for k in campos] + [" | ".join(it["motivos"])])
    return b.getvalue()


def panel_monitoreo(con) -> dict:
    pubs = []
    for r in con.execute("SELECT id, corte, version_modelo, activa, importada_en, manifiesto_json FROM sombra_publicaciones WHERE modelo_id = ? ORDER BY corte DESC, importada_en DESC",
                         (MODELO_ID,)):
        man = loads(r["manifiesto_json"])
        pubs.append({"sombra_id": r["id"], "corte": r["corte"], "version": r["version_modelo"], "activa": bool(r["activa"]), "importada_en": r["importada_en"],
                     "monitoreo": man.get("monitoreo"), "duracion_puntuacion_s": (man.get("volatiles") or {}).get("duracion_puntuacion_s")})
    estados = {e: n for e, n in con.execute("SELECT estado, count(*) FROM casos_anomalia WHERE reemplazado_por IS NULL GROUP BY estado")}
    return {"publicaciones": pubs, "casos_por_estado": estados, "avisos": M.avisos(con, MODELO_ID), "experimental": False}  # vista global: /api/monitoreo
