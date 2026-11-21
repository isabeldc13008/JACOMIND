"""Operación: carga CSV/Excel (B02.4), cierre mensual, respaldo/restauración y banderas (B11).

La carga manual y la programada usan la misma validación (``validar_archivo``).
Si A expone su importador (A01) en JACOMIND_IMPORTADOR="modulo:funcion" con la firma
``importar_archivo(ruta, tabla, hoja=None, mapeo=None) -> dict`` se usa ese; si no,
una validación preliminar de B con el mismo formato de resultado.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.util
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from pathlib import Path

from . import __version__
from .base import DIR_SALIDA, DIR_VAR, RAIZ, BaseDatos, ErrorApi, ahora, auditar, bandera, dumps, hoy, loads, nuevo_id
from .publicacion import cierre_activo, publicar_ruta

IMPORTADOR_A = os.environ.get("JACOMIND_IMPORTADOR", "pipeline.importar:importar_archivo")
BANDERAS = {"asistente": "Asistente de consultas y del portal", "modelo_compra": "Probabilidad de compra a 30 días en agenda y fichas"}
EFECTO_BANDERAS = {
    "asistente": "Si lo desactivas, el asistente interno y el del portal responden que no están disponibles. Tareas, PQRS y beneficios siguen funcionando.",
    "modelo_compra": "Si lo desactivas, la agenda y las fichas muestran «Hay compras, pero falta la estimación», el orden pasa a ser acción e ID y las reglas siguen marcando reactivación, cobertura y primera compra.",
}

# Diccionario de datos del paquete (columnas, clave y tipos) para la validación preliminar.
TABLAS_CARGA = {
    "ventas": {"clave": "venta_id", "columnas": {"venta_id": "id", "fecha": "fecha", "cliente_id": "id", "producto_id": "id",
                                                  "cantidad": "entero+", "moneda": "moneda", "precio_unitario": "decimal+",
                                                  "descuento_pct": "pct", "estado": "estado"}},
    "compras": {"clave": "compra_id", "columnas": {"compra_id": "id", "fecha": "fecha", "proveedor_id": "id", "producto_id": "id",
                                                    "cantidad": "entero+", "moneda": "moneda", "costo_unitario": "decimal+"}},
    "clientes": {"clave": "cliente_id", "columnas": {"cliente_id": "id", "fecha_alta": "fecha"}},
    "productos": {"clave": "producto_id", "columnas": {"producto_id": "id", "familia_prueba": "texto", "moneda_lista": "moneda"}},
    "base_instalada": {"clave": "instalacion_id", "columnas": {"instalacion_id": "id", "cliente_id": "id", "producto_id": "id",
                                                               "fecha_inicio": "fecha", "fecha_fin": "fecha"}},
    "trm": {"clave": "fecha", "columnas": {"fecha": "fecha", "cop_por_usd": "decimal+"}},
    "proveedores": {"clave": "proveedor_id", "columnas": {"proveedor_id": "id"}},
}


# ------------------------------------------------------------------ lectura de archivos
def leer_xlsx(ruta: Path, hoja: str | None = None) -> tuple[list[str], list[list], list[str]]:
    """Lector XLSX mínimo (stdlib). Devuelve (hojas, filas, encabezado-de-hoja-usada)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    with zipfile.ZipFile(ruta) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        destino = {r.get("Id"): r.get("Target") for r in rels}
        hojas = [(s.get("name"), destino[s.get(f"{{{ns['r']}}}id")]) for s in wb.find("m:sheets", ns)]
        nombres = [h[0] for h in hojas]
        if hoja is None:
            hoja = nombres[0]
        if hoja not in nombres:
            raise ErrorApi(422, "hoja_inexistente", f"La hoja «{hoja}» no existe. Hojas: {', '.join(nombres)}")
        target = dict(hojas)[hoja].lstrip("/")
        target = target if target.startswith("xl/") else f"xl/{target}"
        compartidas = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
                compartidas.append("".join(t.text or "" for t in si.iter(f"{{{ns['m']}}}t")))
        filas = []
        for row in ET.fromstring(z.read(target)).iter(f"{{{ns['m']}}}row"):
            valores: dict[int, object] = {}
            for c in row.findall("m:c", ns):
                ref = re.match(r"([A-Z]+)", c.get("r")).group(1)
                col = 0
                for ch in ref:
                    col = col * 26 + ord(ch) - 64
                t, v = c.get("t"), c.find("m:v", ns)
                if t == "s" and v is not None:
                    valores[col] = compartidas[int(v.text)]
                elif t == "inlineStr":
                    valores[col] = "".join(x.text or "" for x in c.iter(f"{{{ns['m']}}}t"))
                elif v is not None:
                    valores[col] = v.text
            if valores:
                filas.append([valores.get(i, "") for i in range(1, max(valores) + 1)])
    return nombres, filas, filas[0] if filas else []


def _fecha(v) -> str | None:
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            return date.fromisoformat(s).isoformat()
        except ValueError:
            return None
    if re.fullmatch(r"\d+(\.0+)?", s) and 20000 < float(s) < 80000:  # fecha nativa de Excel
        return (date(1899, 12, 30) + timedelta(days=int(float(s)))).isoformat()
    return None


def leer_tabla(ruta: Path, hoja: str | None, mapeo: dict | None) -> tuple[list[dict], list[str]]:
    if ruta.suffix.lower() in (".xlsx", ".xlsm"):
        hojas, filas, _ = leer_xlsx(ruta, hoja)
        if not filas:
            return [], hojas
        enc = [str(x).strip() for x in filas[0]]
        datos = [dict(zip(enc, [("" if x is None else str(x)) for x in f])) for f in filas[1:]]
    else:
        hojas = []
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            datos = list(csv.DictReader(f))
    if mapeo:
        datos = [{mapeo.get(k, k): v for k, v in d.items()} for d in datos]
    return datos, hojas


def _validacion_preliminar(ruta: Path, tabla: str, hoja=None, mapeo=None) -> dict:
    if tabla not in TABLAS_CARGA:
        raise ErrorApi(400, "tabla_desconocida", f"Tabla no soportada: {tabla}")
    spec = TABLAS_CARGA[tabla]
    datos, hojas = leer_tabla(ruta, hoja, mapeo)
    incid = []
    if not datos:
        return {"leidas": 0, "aceptadas": 0, "duplicadas": 0, "aisladas": 0, "bloqueante": True, "hojas": hojas,
                "incidencias": [{"fila": None, "campo": None, "motivo": "Archivo sin filas", "accion": "rechazar lote"}]}
    faltan = [c for c in spec["columnas"] if c not in datos[0]]
    if faltan:
        return {"leidas": len(datos), "aceptadas": 0, "duplicadas": 0, "aisladas": 0, "bloqueante": True, "hojas": hojas,
                "incidencias": [{"fila": None, "campo": ", ".join(faltan), "motivo": "Faltan columnas obligatorias (¿hoja o mapeo equivocado?)",
                                 "accion": "corregir mapeo"}]}
    vistos: dict[str, dict] = {}
    aceptadas = duplicadas = aisladas = 0
    for i, d in enumerate(datos, start=2):
        motivos = []
        for campo, tipo in spec["columnas"].items():
            v = (d.get(campo) or "").strip()
            if v == "":
                motivos.append((campo, "Valor vacío")); continue
            if tipo == "fecha" and not _fecha(v):
                motivos.append((campo, f"Fecha inválida «{v}»"))
            elif tipo in ("entero+", "decimal+", "pct"):
                try:
                    n = float(v)
                    if tipo == "entero+" and (n <= 0 or n != int(n)):
                        motivos.append((campo, f"Cantidad no válida «{v}»"))
                    elif tipo == "decimal+" and n <= 0:
                        motivos.append((campo, f"Importe no positivo «{v}»"))
                    elif tipo == "pct" and not 0 <= n <= 100:
                        motivos.append((campo, f"Descuento fuera de 0–100 «{v}»"))
                except ValueError:
                    motivos.append((campo, f"Número inválido «{v}»"))
            elif tipo == "moneda" and v not in ("COP", "USD"):
                motivos.append((campo, f"Moneda no cubierta por las tasas «{v}»"))
            elif tipo == "estado" and v not in ("Confirmada", "Anulada"):
                motivos.append((campo, f"Estado desconocido «{v}»"))
        clave = (d.get(spec["clave"]) or "").strip()
        if clave in vistos:
            if vistos[clave] == d:
                duplicadas += 1
                incid.append({"fila": i, "campo": spec["clave"], "motivo": f"Fila duplicada idéntica ({clave})", "accion": "descartar duplicado"})
                continue
            motivos.append((spec["clave"], f"ID repetido con valores distintos ({clave})"))
        if motivos:
            aisladas += 1
            for campo, m in motivos:  # una fila con varios motivos cuenta una sola vez
                incid.append({"fila": i, "campo": campo, "motivo": m, "accion": "aislar fila"})
        else:
            aceptadas += 1
            vistos[clave] = d
    return {"leidas": len(datos), "aceptadas": aceptadas, "duplicadas": duplicadas, "aisladas": aisladas,
            "bloqueante": aceptadas == 0, "hojas": hojas, "incidencias": incid,
            "validador": "preliminar-B (referencias entre tablas las valida A01)"}


def _validar(ruta: Path, tabla: str, hoja=None, mapeo=None) -> dict:
    modulo, _, funcion = IMPORTADOR_A.partition(":")
    try:
        fn = getattr(importlib.import_module(modulo), funcion)
    except (ImportError, AttributeError):
        fn = None
    if fn is not None:
        try:
            r = dict(fn(str(ruta), tabla, hoja=hoja, mapeo=mapeo))
        except TypeError as e:  # firma distinta a la acordada: no bloquear la carga
            r = _validacion_preliminar(ruta, tabla, hoja, mapeo)
            r["aviso_integracion"] = f"El importador de A no cumple la firma acordada ({e}); se usó la validación preliminar"
            return r
        r.setdefault("validador", f"A01:{IMPORTADOR_A}")
        return r
    return _validacion_preliminar(ruta, tabla, hoja, mapeo)


def validar_archivo(ruta: Path, tabla: str, hoja=None, mapeo=None) -> dict:
    """Valida el archivo y añade lo necesario para mapear columnas con controles en la vista."""
    r = _validar(ruta, tabla, hoja, mapeo)
    if "encabezados" not in r:
        try:
            datos, _ = leer_tabla(ruta, hoja, None)
            r["encabezados"] = list(datos[0].keys()) if datos else []
        except Exception:  # noqa: BLE001 - los encabezados son una ayuda, no bloquean la validación
            r["encabezados"] = []
    r.setdefault("columnas_esperadas", list(TABLAS_CARGA.get(tabla, {}).get("columnas", {})))
    return r


def previsualizar_carga(db: BaseDatos, usuario, nombre: str, contenido: bytes, tabla: str, periodo: str | None,
                        hoja: str | None = None, mapeo: dict | None = None) -> dict:
    ext = Path(nombre).suffix.lower()
    if ext not in (".csv", ".xlsx", ".xlsm"):
        raise ErrorApi(400, "formato_no_soportado", "Solo se aceptan archivos CSV o Excel (.xlsx)")
    if len(contenido) > 20 * 1024 * 1024:
        raise ErrorApi(413, "archivo_grande", "El archivo supera 20 MB")
    huella = hashlib.sha256(contenido + dumps([tabla, hoja, mapeo, periodo]).encode()).hexdigest()
    destino = DIR_VAR / "cargas" / f"{huella[:20]}{ext}"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)
    try:
        res = validar_archivo(destino, tabla, hoja, mapeo)
    except ErrorApi:
        raise
    except (zipfile.BadZipFile, UnicodeDecodeError, csv.Error, KeyError, ET.ParseError) as e:
        raise ErrorApi(422, "archivo_ilegible", f"No se pudo leer el archivo: {e}")
    with db.transaccion() as con:
        previo = con.execute("SELECT id, estado FROM lotes WHERE huella = ?", (huella,)).fetchone()
        if previo:  # reenvío idéntico: se reutiliza el lote
            return {"lote_id": previo["id"], "estado": previo["estado"], "reutilizado": True, **res}
        cur = con.execute("""INSERT INTO lotes (huella, origen, tabla, periodo, cargado_por, cargado_en, estado, resumen_json)
                             VALUES (?,?,?,?,?,?, 'previsualizado', ?)""",
                          (huella, nombre, tabla, periodo, usuario.id, ahora(), dumps({k: v for k, v in res.items() if k != "incidencias"} | {"archivo": str(destino), "hoja": hoja, "mapeo": mapeo})))
        auditar(con, usuario.id, "carga.previsualizar", nombre, "ok", None, {"tabla": tabla, "aceptadas": res["aceptadas"], "aisladas": res["aisladas"]})
        return {"lote_id": cur.lastrowid, "estado": "previsualizado", "reutilizado": False, **res}


def confirmar_carga(db: BaseDatos, usuario, lote_id: int) -> dict:
    with db.transaccion() as con:
        l = con.execute("SELECT * FROM lotes WHERE id = ?", (lote_id,)).fetchone()
        if not l:
            raise ErrorApi(404, "lote_no_encontrado", "Lote no encontrado")
        res = loads(l["resumen_json"])
        if res.get("bloqueante"):
            raise ErrorApi(409, "lote_bloqueado", "El lote tiene errores que impiden publicarlo; corrige el archivo y vuelve a cargarlo")
        if l["estado"] == "confirmado":
            return {"lote_id": lote_id, "estado": "confirmado", "repetida": True}
        dest = DIR_VAR / "lotes" / (l["periodo"] or "sin-periodo")
        dest.mkdir(parents=True, exist_ok=True)
        archivo = Path(res["archivo"])
        shutil.copy2(archivo, dest / f"{l['tabla']}{archivo.suffix}")
        con.execute("UPDATE lotes SET estado = 'confirmado' WHERE id = ?", (lote_id,))
        auditar(con, usuario.id, "carga.confirmar", str(lote_id), "ok", None, {"destino": str(dest)})
        return {"lote_id": lote_id, "estado": "confirmado", "directorio_lote": str(dest), "repetida": False,
                "siguiente_paso": "Ejecutar el cierre mensual sobre el directorio del lote"}


def listar_lotes(con) -> list[dict]:
    return [dict(r, resumen=loads(r["resumen_json"])) for r in con.execute("SELECT * FROM lotes ORDER BY id DESC LIMIT 50")]


# ------------------------------------------------------------------ cierre mensual
def ejecutar_cierre(db: BaseDatos, actor: str, corte: str, datos: str | None = None, desde: str | None = None,
                    reintentos: int = 2, salida_base: Path | None = None) -> dict:
    """Genera (pipeline de A), valida y publica. Reintentos seguros: publicar es idempotente por huella."""
    run_id = nuevo_id(f"cierre-{corte}-")
    etapas: list[dict] = []
    with db.transaccion() as con:
        con.execute("INSERT INTO ejecuciones (id, tipo, corte, inicio, estado) VALUES (?, 'cierre', ?, ?, 'en_curso')", (run_id, corte, ahora()))
    salida = Path(desde) if desde else (salida_base or DIR_SALIDA / "cierres") / run_id
    resultado, estado, error = None, "fallido", None

    def etapa(nombre, fn):
        t0 = time.perf_counter()
        try:
            r = fn()
            etapas.append({"etapa": nombre, "segundos": round(time.perf_counter() - t0, 3), "estado": "ok"})
            return r
        except Exception as e:
            etapas.append({"etapa": nombre, "segundos": round(time.perf_counter() - t0, 3), "estado": "fallido", "error": str(e)})
            raise

    intentos = 0
    for intentos in range(1, reintentos + 2):
        try:
            if not desde:
                def generar():
                    if not datos:
                        raise RuntimeError("Indica --datos con la carpeta de insumos")
                    salida.mkdir(parents=True, exist_ok=True)
                    if importlib.util.find_spec("pipeline") is not None and importlib.util.find_spec("pipeline.generar") is not None:
                        cmd = [sys.executable, "-m", "pipeline.generar", "--datos", str(datos), "--corte", corte,
                               "--salida", str(salida / "agenda.json")]
                        p = subprocess.run(cmd, cwd=RAIZ, capture_output=True, text=True, timeout=1800)
                        if p.returncode != 0:
                            raise RuntimeError(f"pipeline.generar terminó con código {p.returncode}: {(p.stderr or p.stdout)[-800:]}")
                        return
                    from . import integracion_a
                    if not integracion_a.disponible():
                        raise RuntimeError("No está disponible el pipeline del carril A (pipeline/)")
                    integracion_a.generar(datos, corte, salida)
                etapa("generar", generar)
            objetivo = salida if (salida / "manifiesto.json").exists() else salida / "agenda.json"
            resultado = etapa("validar_y_publicar", lambda: publicar_ruta(db, objetivo, actor))
            estado = "publicado"
            break
        except ErrorApi as e:  # contrato inválido: reintentar no lo arregla
            error = {"codigo": e.codigo, "mensaje": e.mensaje, "detalle": e.detalle}
            break
        except Exception as e:
            error = {"codigo": "fallo_etapa", "mensaje": str(e)}
            if intentos <= reintentos:
                time.sleep(min(2 ** intentos, 10) if not os.environ.get("JACOMIND_SIN_ESPERA") else 0)
    with db.transaccion() as con:
        con.execute("UPDATE ejecuciones SET fin = ?, estado = ?, intentos = ?, etapas_json = ?, detalle_json = ? WHERE id = ?",
                    (ahora(), estado, intentos, dumps(etapas), dumps({"resultado": resultado, "error": error, "salida": str(salida)}), run_id))
        auditar(con, actor, "cierre.ejecutar", run_id, estado, None, {"corte": corte, "error": error})
    return {"ejecucion_id": run_id, "estado": estado, "intentos": intentos, "etapas": etapas, "resultado": resultado,
            "error": error, "ultimo_cierre_valido": _ultimo_valido(db)}


def _ultimo_valido(db: BaseDatos):
    with db.conexion() as con:
        return cierre_activo(con)


def estado_operacion(con) -> dict:
    act = cierre_activo(con)
    c = con.execute("SELECT * FROM cierres WHERE id = ?", (act,)).fetchone() if act else None
    frescura = (hoy() - date.fromisoformat(c["corte"])).days if c else None
    ejec = [dict(r, etapas=loads(r["etapas_json"]), detalle=loads(r["detalle_json"])) for r in
            con.execute("SELECT * FROM ejecuciones ORDER BY inicio DESC LIMIT 10")]
    rechazadas = sum((loads(r[0]) or {}).get("aisladas", 0) for r in con.execute("SELECT resumen_json FROM lotes"))
    man = loads(c["manifiesto_json"]) if c else {}
    return {"version_app": __version__, "cierre_activo": act, "corte": c["corte"] if c else None,
            "publicado_en": c["publicado_en"] if c else None, "frescura_dias": frescura,
            "versiones": man.get("versiones"), "ejecuciones": ejec, "filas_aisladas_en_cargas": rechazadas,
            "banderas": {k: {"activo": bandera(con, k), "descripcion": d, "efecto": EFECTO_BANDERAS.get(k)} for k, d in BANDERAS.items()},
            "tablas_carga": {t: list(spec["columnas"]) for t, spec in TABLAS_CARGA.items()}}


def fijar_bandera(db: BaseDatos, usuario, nombre: str, activo: bool) -> dict:
    if nombre not in BANDERAS:
        raise ErrorApi(400, "bandera_desconocida", f"Bandera no soportada: {nombre}")
    with db.transaccion() as con:
        con.execute("INSERT INTO banderas VALUES (?,?,?) ON CONFLICT(nombre) DO UPDATE SET activo = excluded.activo, actualizado_en = excluded.actualizado_en",
                    (nombre, int(activo), ahora()))
        auditar(con, usuario.id, "bandera.fijar", nombre, "ok", None, {"activo": activo})
    return {"nombre": nombre, "activo": activo}


# ------------------------------------------------------------------ respaldo y restauración
def respaldar(db: BaseDatos, destino: str | Path | None = None) -> dict:
    destino = Path(destino or DIR_VAR / "respaldos" / f"jacomind-{ahora()[:19].replace(':', '')}.sqlite3")
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen = sqlite3.connect(db.ruta)
    copia = sqlite3.connect(str(destino))
    try:
        origen.backup(copia)
    finally:
        copia.close(); origen.close()
    with db.conexion() as con:
        manifiesto = {"creado_en": ahora(), "version_app": __version__, "esquema": db.version_esquema(),
                      "cierre_activo": cierre_activo(con),
                      "documentos": [f"{r[0]} v{r[1]}" for r in con.execute("SELECT id, version FROM documentos WHERE estado = 'vigente'")],
                      "conteos": {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cierres", "tareas", "pqrs", "eventos", "beneficios")},
                      "huella": hashlib.sha256(destino.read_bytes()).hexdigest()}
    Path(str(destino) + ".json").write_text(json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"archivo": str(destino), **manifiesto}


def restaurar(origen: str | Path, destino_db: str | Path) -> dict:
    """Restaura en una base aislada (no sobrescribe la activa salvo que se indique esa ruta)."""
    origen, destino_db = Path(origen), Path(destino_db)
    meta_path = Path(str(origen) + ".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    if meta.get("huella") and hashlib.sha256(origen.read_bytes()).hexdigest() != meta["huella"]:
        raise ErrorApi(422, "respaldo_alterado", "La huella del respaldo no coincide con su manifiesto")
    t0 = time.perf_counter()
    destino_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(origen)); dst = sqlite3.connect(str(destino_db))
    try:
        src.backup(dst)
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        conteos = {t: dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("cierres", "tareas", "pqrs", "eventos", "beneficios")}
    finally:
        dst.close(); src.close()
    return {"destino": str(destino_db), "integridad": ok, "conteos": conteos, "manifiesto": meta,
            "segundos": round(time.perf_counter() - t0, 3), "coincide_con_manifiesto": (not meta) or conteos == meta.get("conteos")}
