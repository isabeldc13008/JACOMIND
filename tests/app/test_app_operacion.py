"""B02.4 · carga CSV/Excel y B11 · cierre programado, respaldo, restauración y banderas."""
import base64
import csv
import io
import os
import shutil
import unittest
import zipfile
from pathlib import Path

from api import operacion, publicacion, tareas
from api.base import BaseDatos

from _apoyo_app import CasoBase, EJEMPLOS, MUESTRA

PAQUETE = Path(__file__).resolve().parents[3] / "Green_Services_Recursos_de_Prueba"
CABECERA = ["venta_id", "fecha", "cliente_id", "producto_id", "cantidad", "moneda", "precio_unitario", "descuento_pct", "estado", "origen_datos"]
FILAS = [
    ["VEN01", "2026-01-06", "CLI090", "PRO04", "2", "COP", "2660000.0", "0", "Confirmada", "Prueba"],
    ["VEN01", "2026-01-06", "CLI090", "PRO04", "2", "COP", "2660000.0", "0", "Confirmada", "Prueba"],  # duplicada idéntica
    ["VEN02", "2026-02-30", "CLI001", "PRO03", "3", "COP", "432000.0", "0", "Confirmada", "Prueba"],   # fecha inválida
    ["VEN03", "2026-03-01", "CLI001", "PRO03", "1", "EUR", "100", "0", "Confirmada", "Prueba"],        # moneda no cubierta
    ["VEN04", "2026-03-02", "CLI001", "PRO03", "-2", "COP", "100", "0", "Confirmada", "Prueba"],       # cantidad negativa
    ["VEN05", "2026-03-03", "CLI001", "PRO03", "1", "COP", "", "0", "Confirmada", "Prueba"],           # precio vacío
    ["VEN06", "2026-03-04", "CLI002", "PRO01", "3", "USD", "100", "10", "Anulada", "Prueba"],
    ["VEN06", "2026-03-04", "CLI002", "PRO01", "4", "USD", "100", "10", "Anulada", "Prueba"],          # ID repetido distinto
]


def csv_bytes(filas=FILAS, cab=CABECERA):
    buf = io.StringIO()
    w = csv.writer(buf); w.writerow(cab); w.writerows(filas)
    return ("﻿" + buf.getvalue()).encode("utf-8")


def xlsx_bytes(filas, hoja="Ventas"):
    """XLSX mínimo con cadenas en línea y una fecha nativa de Excel en la columna 2."""
    def celda(ref, v):
        if isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{v}</t></is></c>'
    filas_xml = "".join(f'<row r="{i}">' + "".join(celda(f"{chr(65 + j)}{i}", v) for j, v in enumerate(f)) + "</row>" for i, f in enumerate(filas, start=1))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Notas" sheetId="1" r:id="rId1"/><sheet name="{hoja}" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="ws"/><Relationship Id="rId2" Target="worksheets/sheet2.xml" Type="ws"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>notas</t></is></c></row></sheetData></worksheet>')
        z.writestr("xl/worksheets/sheet2.xml", f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{filas_xml}</sheetData></worksheet>')
    return buf.getvalue()


class PruebasCarga(CasoBase):
    def cargar(self, nombre, contenido, tabla="ventas", hoja=None, periodo="2026-10", mapeo=None):
        return self.http("POST", "/api/cargas", {"nombre": nombre, "contenido_b64": base64.b64encode(contenido).decode(), "tabla": tabla,
                                                  "periodo": periodo, "hoja": hoja, "mapeo": mapeo}, como="ops1")

    def test_previsualizacion_concilia_cada_fila_una_vez(self):
        st, r = self.cargar("ventas.csv", csv_bytes())
        self.assertEqual(st, 200)
        self.assertEqual((r["leidas"], r["aceptadas"], r["duplicadas"], r["aisladas"]), (8, 2, 1, 5))
        self.assertEqual(r["leidas"], r["aceptadas"] + r["duplicadas"] + r["aisladas"])
        motivos = " ".join(i["motivo"] for i in r["incidencias"])
        for m in ("duplicada", "Fecha inválida", "EUR", "Cantidad", "vacío", "ID repetido"):
            self.assertIn(m, motivos)

    def test_reenvio_identico_reutiliza_lote_y_confirmacion(self):
        _, a = self.cargar("ventas.csv", csv_bytes())
        _, b = self.cargar("ventas.csv", csv_bytes())
        self.assertEqual(a["lote_id"], b["lote_id"]); self.assertTrue(b["reutilizado"])
        st, c = self.http("POST", f"/api/cargas/{a['lote_id']}/confirmar", {}, como="ops1")
        self.assertEqual((st, c["estado"]), (200, "confirmado"))
        self.assertTrue(self.http("POST", f"/api/cargas/{a['lote_id']}/confirmar", {}, como="ops1")[1]["repetida"])

    def test_lote_bloqueante_no_se_confirma(self):
        _, r = self.cargar("malo.csv", csv_bytes(cab=["a", "b"], filas=[["1", "2"]]))
        self.assertTrue(r["bloqueante"]); self.assertIn("mapeo", r["incidencias"][0]["accion"])
        self.assertEqual(self.http("POST", f"/api/cargas/{r['lote_id']}/confirmar", {}, como="ops1")[0], 409)

    def test_excel_hoja_fecha_nativa_y_mapeo(self):
        filas = [["Venta", "Fecha venta", "cliente_id", "producto_id", "cantidad", "moneda", "precio_unitario", "descuento_pct", "estado"],
                 ["VEN09", 46031, "CLI001", "PRO03", 2, "COP", 100000, 10, "Confirmada"]]
        datos = xlsx_bytes(filas)
        st, e = self.cargar("v.xlsx", datos, hoja="NoExiste")
        self.assertEqual(st, 422); self.assertIn("Ventas", e["mensaje"])
        mapeo = {"Venta": "venta_id", "Fecha venta": "fecha"}
        _, r = self.cargar("v.xlsx", datos, hoja="Ventas", mapeo=mapeo)
        self.assertEqual((r["aceptadas"], r["aisladas"]), (1, 0)); self.assertEqual(r["hojas"], ["Notas", "Ventas"])
        _, sin_mapeo = self.cargar("v.xlsx", datos, hoja="Ventas")
        self.assertTrue(sin_mapeo["bloqueante"])

    def test_misma_venta_csv_y_xlsx(self):
        fila = ["VEN10", "2026-01-12", "CLI012", "PRO03", "3", "COP", "432000.0", "0", "Confirmada"]
        tmp_csv, tmp_x = self.tmp / "a.csv", self.tmp / "a.xlsx"
        tmp_csv.write_bytes(csv_bytes([fila + ["Prueba"]]))
        tmp_x.write_bytes(xlsx_bytes([CABECERA[:-1], fila]))
        a, _ = operacion.leer_tabla(tmp_csv, None, None)
        b, _ = operacion.leer_tabla(tmp_x, "Ventas", None)
        for k in CABECERA[:-1]:
            self.assertEqual(a[0][k], b[0][k], k)

    def test_id_con_ceros_iniciales_se_conserva(self):
        p = self.tmp / "c.csv"
        p.write_bytes(csv_bytes([["00123", "2026-01-01", "CLI001", "PRO01", "1", "COP", "10", "0", "Confirmada", "x"]]))
        filas, _ = operacion.leer_tabla(p, None, None)
        self.assertEqual(filas[0]["venta_id"], "00123")

    @unittest.skipUnless((PAQUETE / "01_Datos" / "ventas_con_incidencias_OPCIONAL.csv").exists(), "paquete de datos no disponible")
    def test_archivo_opcional_con_incidencias_sembradas(self):
        contenido = (PAQUETE / "01_Datos" / "ventas_con_incidencias_OPCIONAL.csv").read_bytes()
        _, r = self.cargar("ventas_con_incidencias_OPCIONAL.csv", contenido)
        self.assertEqual(r["leidas"], 81)
        self.assertEqual(r["duplicadas"] + r["aisladas"], 5)  # duplicado, fecha, EUR, cantidad, precio (CLI999/PRO99 los valida A01)
        self.assertEqual(r["leidas"], r["aceptadas"] + r["duplicadas"] + r["aisladas"])


class PruebasCierreYRecuperacion(CasoBase):
    def setUp(self):
        super().setUp()
        os.environ["JACOMIND_SIN_ESPERA"] = "1"

    def test_cierre_desde_directorio_es_idempotente(self):
        r1 = operacion.ejecutar_cierre(self.db, "programador", "2026-10-31", desde=str(MUESTRA))
        self.assertEqual(r1["estado"], "publicado"); self.assertTrue(r1["resultado"]["ya_publicado"])
        self.assertEqual([e["etapa"] for e in r1["etapas"]], ["validar_y_publicar"])

    def test_fallo_de_generacion_conserva_ultimo_valido_y_registra_reintentos(self):
        with self.db.conexion() as con:
            previo = publicacion.cierre_activo(con)
        r = operacion.ejecutar_cierre(self.db, "programador", "2026-11-30", datos=str(self.tmp / "no-existe"), reintentos=1,
                                      salida_base=self.tmp / "salida")
        self.assertEqual(r["estado"], "fallido"); self.assertEqual(r["intentos"], 2)
        self.assertEqual(r["ultimo_cierre_valido"], previo)
        _, op = self.http("GET", "/api/operacion", como="ops1")
        self.assertEqual(op["ejecuciones"][0]["estado"], "fallido")

    def test_contrato_invalido_no_se_reintenta(self):
        d = self.tmp / "inc"; d.mkdir()
        shutil.copy(EJEMPLOS / "incompatible.json", d / "agenda.json")
        r = operacion.ejecutar_cierre(self.db, "programador", "2026-10-31", desde=str(d), reintentos=3)
        self.assertEqual((r["estado"], r["intentos"], r["error"]["codigo"]), ("fallido", 1, "agenda_invalida"))

    def test_respaldo_y_restauracion_aislada(self):
        t = tareas.listar(self.db.conectar(), cliente_id="DEMO02")[0]
        tareas.accion(self.db, self.usuario("ventas1"), t["id"], "asignar", {"version": t["version"]})
        resp = operacion.respaldar(self.db, self.tmp / "resp" / "r.sqlite3")
        # Acción posterior al respaldo: no debe aparecer tras restaurar (punto de recuperación).
        t2 = tareas.listar(self.db.conectar(), cliente_id="DEMO03")[0]
        tareas.accion(self.db, self.usuario("ventas1"), t2["id"], "descartar", {"version": t2["version"], "motivo": "posterior"})
        rest = operacion.restaurar(resp["archivo"], self.tmp / "ensayo.sqlite3")
        self.assertEqual(rest["integridad"], "ok"); self.assertTrue(rest["coincide_con_manifiesto"])
        db2 = BaseDatos(rest["destino"])
        with db2.conexion() as con:
            self.assertEqual(con.execute("SELECT estado FROM tareas WHERE id = ?", (t["id"],)).fetchone()[0], "asignada")
            self.assertEqual(con.execute("SELECT estado FROM tareas WHERE id = ?", (t2["id"],)).fetchone()[0], "abierta")
            self.assertEqual(publicacion.cierre_activo(con), resp["cierre_activo"])

    def test_respaldo_alterado_se_rechaza(self):
        resp = operacion.respaldar(self.db, self.tmp / "r.sqlite3")
        with open(resp["archivo"], "ab") as f:
            f.write(b"x")
        from api.base import ErrorApi
        with self.assertRaises(ErrorApi):
            operacion.restaurar(resp["archivo"], self.tmp / "otra.sqlite3")

    def test_importador_de_a_con_firma_distinta_no_bloquea(self):
        import sys, types
        m = types.ModuleType("imp_falso"); m.importar_archivo = lambda ruta: {}
        sys.modules["imp_falso"] = m
        anterior = operacion.IMPORTADOR_A
        operacion.IMPORTADOR_A = "imp_falso:importar_archivo"
        try:
            p = self.tmp / "v.csv"; p.write_bytes(csv_bytes())
            r = operacion.validar_archivo(p, "ventas")
            self.assertIn("aviso_integracion", r); self.assertEqual(r["aceptadas"], 2)
        finally:
            operacion.IMPORTADOR_A = anterior


if __name__ == "__main__":
    unittest.main()
