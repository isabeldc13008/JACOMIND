import json
import tempfile
import unittest
from pathlib import Path

from .test_carga import CargaTests


class RegresionesRevisionTests(unittest.TestCase):
    def test_configuracion_aplica_archivo_delimitador_y_mapeo(self):
        from pipeline.carga import cargar_lote

        helper = CargaTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            helper._datos_minimos(root)
            (root / "ventas.csv").unlink()
            (root / "ventas_alternas.csv").write_text("id;f;cli;prod;cant;mon;precio;desc;estado;origen\nVEN001;2026-01-02;CLI001;PR001;1;COP;10;0;Confirmada;p\n", encoding="utf-8")
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps({"tablas": {"ventas": {"archivo": "ventas_alternas.csv", "delimitador": ";", "mapeo": {"venta_id": "id", "fecha": "f", "cliente_id": "cli", "producto_id": "prod", "cantidad": "cant", "moneda": "mon", "precio_unitario": "precio", "descuento_pct": "desc", "estado": "estado", "origen_datos": "origen"}}}}), encoding="utf-8")
            result = cargar_lote(root, output, config)
            self.assertEqual(result.status, "publicable")
            self.assertEqual(result.inventory["ventas"]["accepted"], 1)

    def test_encabezado_incompleto_bloquea_y_conserva_publicacion(self):
        from pipeline.carga import cargar_lote

        helper = CargaTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            helper._datos_minimos(root)
            cargar_lote(root, output)
            (root / "ventas.csv").write_text("wrong_header\nvalue\n", encoding="utf-8")
            result = cargar_lote(root, output)
            self.assertEqual(result.status, "fallido")
            self.assertIn("VEN001", (output / "publicado" / "ventas.csv").read_text())

    def test_reenvio_identico_reutiliza_revision_y_cambio_incrementa(self):
        from pipeline.carga import cargar_lote

        helper = CargaTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            helper._datos_minimos(root)
            first = cargar_lote(root, output)
            second = cargar_lote(root, output)
            self.assertEqual(first.manifest["revision"], second.manifest["revision"])
            self.assertEqual(second.status, "reutilizado")
            (root / "ventas.csv").write_text((root / "ventas.csv").read_text().replace(",10,0,Confirmada", ",17,0,Confirmada"), encoding="utf-8")
            third = cargar_lote(root, output)
            self.assertEqual(third.manifest["revision"], first.manifest["revision"] + 1)
            self.assertTrue((output / "historial_lotes.jsonl").exists())

    def test_incidencia_conserva_fila_fisica(self):
        from pipeline.carga import cargar_lote

        helper = CargaTests()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            helper._datos_minimos(root)
            (root / "ventas.csv").write_text((root / "ventas.csv").read_text() + "VEN002,2026-01-03,NO_EXISTE,PR001,1,COP,10,0,Confirmada,p\n", encoding="utf-8")
            result = cargar_lote(root, output)
            issue = next(issue for issue in result.issues if issue.code == "REFERENCIA_DESCONOCIDA")
            self.assertEqual(issue.row, 3)


if __name__ == "__main__":
    unittest.main()
