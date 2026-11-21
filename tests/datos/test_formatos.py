import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


class FormatosTests(unittest.TestCase):
    def test_csv_con_bom_preserva_ids_y_celdas(self):
        from pipeline.formatos import leer_csv

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clientes.csv"
            path.write_text("cliente_id,nombre\nCLI001,Cliente\n", encoding="utf-8-sig")

            self.assertEqual(leer_csv(path), [{"cliente_id": "CLI001", "nombre": "Cliente"}])

    def test_xlsx_lee_hoja_y_preserva_ids(self):
        from pipeline.formatos import leer_xlsx

        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>"""
        workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>"""
        rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>"""
        sheet = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>cliente_id</t></is></c><c r="B1" t="inlineStr"><is><t>nombre</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>CLI001</t></is></c><c r="B2" t="inlineStr"><is><t>Cliente</t></is></c></row></sheetData></worksheet>"""

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "clientes.xlsx"
            with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("[Content_Types].xml", content_types)
                archive.writestr("xl/workbook.xml", workbook)
                archive.writestr("xl/_rels/workbook.xml.rels", rels)
                archive.writestr("xl/worksheets/sheet1.xml", sheet)

            self.assertEqual(leer_xlsx(path, "Datos"), [{"cliente_id": "CLI001", "nombre": "Cliente"}])

    def test_xlsx_rechaza_hoja_inexistente(self):
        from pipeline.formatos import FormatoError, leer_xlsx

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "vacio.xlsx"
            with ZipFile(path, "w", ZIP_DEFLATED) as archive:
                archive.writestr("xl/workbook.xml", "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheets/></workbook>")
                archive.writestr("xl/_rels/workbook.xml.rels", "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'/>")
            with self.assertRaises(FormatoError):
                leer_xlsx(path, "Datos")


if __name__ == "__main__":
    unittest.main()
