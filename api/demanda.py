"""M5 · Pronóstico de demanda (experimental): publicación en sombra y panel interno.

* La publicación llega en sombra (``modelos.cli puntuar --modelo demanda``), verificada y separada de los cierres: las
  ``series_mensuales`` operativas (A08) y sus consumidores no cambian.
* Permisos: las series en COP (ingresos) solo con ``demanda.ver_cop`` (Finanzas y Gerencia, como los datos financieros);
  las unidades por producto con ``demanda.ver_unidades`` (también Operaciones). El portal externo no recibe nada.
* Un pronóstico emitido no se modifica: una publicación de un origen anterior no desplaza a la activa.
"""
from __future__ import annotations

from pathlib import Path

from contratos.validar import leer_publicacion_sombra

from .base import BaseDatos, ErrorApi, ahora, auditar, dumps, loads

MODELO_ID = "demanda"
NOTA = ("Proyección experimental en sombra: no es ingreso realizado, margen, orden de compra ni predicción de TRM. "
        "Las series mensuales operativas del cierre no cambian.")


def importar_sombra(db: BaseDatos, directorio: str | Path, actor: str) -> dict:
    errores, man, tablas = leer_publicacion_sombra(directorio)
    if errores:
        raise ErrorApi(422, "sombra_invalida", "La publicación en sombra no cumple el contrato", {"errores": errores[:20]})
    if man.get("modelo_id") != MODELO_ID:
        raise ErrorApi(422, "sombra_invalida", f"Se esperaba una publicación de {MODELO_ID}")
    sid = f"{MODELO_ID}:{man['origen']}:{man['sello'][:12]}"
    with db.transaccion() as con:
        previo = con.execute("SELECT id, activa FROM sombra_publicaciones WHERE sello = ?", (man["sello"],)).fetchone()
        if previo:
            return {"sombra_id": previo["id"], "ya_importada": True, "activa": bool(previo["activa"])}
        actual = con.execute("SELECT corte FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()
        activar = actual is None or man["origen"] >= actual["corte"]  # 'corte' guarda el origen (AAAA-MM)
        if activar:
            con.execute("UPDATE sombra_publicaciones SET activa = 0 WHERE modelo_id = ?", (MODELO_ID,))
        con.execute("""INSERT INTO sombra_publicaciones (id, modelo_id, corte, version_modelo, artefacto_huella, sello, estado_experimento,
                       manifiesto_json, importada_en, importada_por, activa) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (sid, MODELO_ID, man["origen"], man["modelo"]["version"], man["modelo"]["artefacto_huella"], man["sello"],
                     man["estado_experimento"], dumps(man), ahora(), actor, int(activar)))
        con.executemany("INSERT INTO sombra_pronosticos (sombra_id, serie_id, horizonte_meses, datos_json) VALUES (?,?,?,?)",
                        [(sid, f["serie_id"], f["horizonte_meses"], dumps(f)) for f in tablas["pronosticos_demanda"]])
        con.executemany("INSERT INTO sombra_calendario_demanda (sombra_id, serie_id, periodo, datos_json) VALUES (?,?,?,?)",
                        [(sid, c["serie_id"], c["periodo"], dumps(c)) for c in tablas["calendario_demanda"]])
        auditar(con, actor, "sombra.importar", sid, "ok" if activar else "importada_sin_activar", None, {"filas": len(tablas["pronosticos_demanda"])})
    salida = {"sombra_id": sid, "ya_importada": False, "activa": activar, "filas": len(tablas["pronosticos_demanda"])}
    if not activar:
        salida["motivo"] = f"Origen {man['origen']} anterior al de la publicación activa ({actual['corte']}): se conserva sin desplazarla."
    return salida


def _permitida(usuario, serie_id: str) -> bool:
    if serie_id.startswith(("ventas_cop:", "compras_proveedores_cop:")):
        return usuario.puede("demanda.ver_cop")
    return usuario.puede("demanda.ver_unidades")


def panel(con, usuario, serie_id: str | None = None) -> dict:
    r = con.execute("SELECT * FROM sombra_publicaciones WHERE modelo_id = ? AND activa = 1", (MODELO_ID,)).fetchone()
    if not r:
        return {"estado": "sin_sombra", "experimental": True, "series": [], "nota": NOTA, "mensaje": "No hay una publicación en sombra de demanda importada."}
    man = loads(r["manifiesto_json"])
    disponibles = sorted({x[0] for x in con.execute("SELECT DISTINCT serie_id FROM sombra_pronosticos WHERE sombra_id = ?", (r["id"],))
                          if _permitida(usuario, x[0])})
    if not disponibles:
        raise ErrorApi(403, "sin_permiso", "Tu perfil no tiene acceso a ninguna serie de demanda")
    serie_id = serie_id if serie_id in disponibles else ("ventas_cop:Total" if "ventas_cop:Total" in disponibles else disponibles[0])
    pron = sorted((loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_pronosticos WHERE sombra_id = ? AND serie_id = ?", (r["id"], serie_id))),
                  key=lambda f: f["horizonte_meses"])
    if serie_id == "ventas_cop:Total":
        fams = [s for s in disponibles if s.startswith("ventas_cop:") and s != "ventas_cop:Total"]
        cal = {}
        for s in fams:
            for x in con.execute("SELECT datos_json FROM sombra_calendario_demanda WHERE sombra_id = ? AND serie_id = ?", (r["id"], s)):
                c = loads(x[0])
                t = cal.setdefault(c["periodo"], {"serie_id": serie_id, "periodo": c["periodo"], "estado": "completo", "valor": 0.0, "motivo": None, "unidad": "COP"})
                if c["estado"] != "completo" or t["valor"] is None:
                    t.update(estado=c["estado"] if c["estado"] != "completo" else t["estado"], valor=None, motivo=c["motivo"] or t["motivo"])
                else:
                    t["valor"] = round(t["valor"] + c["valor"], 2)
        calendario = [cal[k] for k in sorted(cal)]
    else:
        calendario = sorted((loads(x[0]) for x in con.execute("SELECT datos_json FROM sombra_calendario_demanda WHERE sombra_id = ? AND serie_id = ?", (r["id"], serie_id))),
                            key=lambda c: c["periodo"])
    dec = ((man.get("modelo") or {}).get("decision") or {}).get("decisiones", {}).get(serie_id, {})
    return {"estado": "ok", "experimental": True, "nota": NOTA, "serie_id": serie_id, "series": disponibles, "origen": man["origen"], "corte": man["corte"],
            "estado_experimento": r["estado_experimento"], "version": r["version_modelo"], "calendario": calendario, "pronosticos": pron, "decisiones": dec,
            "advertencia": man.get("advertencia")}
