import csv
import json
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, name: str, header: str, rows: list[str]) -> None:
    (path / name).write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")


class CargaTests(unittest.TestCase):
    def _datos_minimos(self, root: Path) -> None:
        _write(root, "clientes.csv", "cliente_id,nombre_prueba,sector_prueba,ciudad_prueba,fecha_alta,canal_preferido_prueba,origen_datos", ["CLI001,A,S,C,2026-01-01,X,p"])
        _write(root, "productos.csv", "producto_id,nombre_prueba,familia_prueba,tipo_prueba,moneda_lista,precio_lista,costo_referencia,vigencia_meses,origen_datos", ["PR001,P,F,Recurrente,COP,10,5,12,p"])
        _write(root, "proveedores.csv", "proveedor_id,nombre_prueba,origen_datos", ["PRO001,Proveedor,p"])
        _write(root, "trm_prueba.csv", "fecha,cop_por_usd,origen", ["2026-01-01,4000,p"])
        _write(root, "ventas.csv", "venta_id,fecha,cliente_id,producto_id,cantidad,moneda,precio_unitario,descuento_pct,estado,origen_datos", ["VEN001,2026-01-02,CLI001,PR001,1,COP,10,0,Confirmada,p"])
        _write(root, "compras.csv", "compra_id,fecha,proveedor_id,producto_id,cantidad,moneda,costo_unitario,origen_datos", ["COM001,2026-01-02,PRO001,PR001,1,COP,5,p"])
        _write(root, "base_instalada.csv", "instalacion_id,cliente_id,producto_id,fecha_inicio,fecha_fin,unidades,origen_datos", ["INS001,CLI001,PR001,2026-01-02,2027-01-01,1,p"])

    def test_carga_publica_tablas_inventario_e_incidencias(self):
        from pipeline.carga import cargar_lote

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            self._datos_minimos(root)
            result = cargar_lote(root, output)
            self.assertEqual(result.status, "publicable")
            self.assertEqual(json.loads((output / "inventario.json").read_text())["tablas"]["ventas"]["accepted"], 1)
            self.assertTrue((output / "publicado" / "ventas.csv").exists())
            self.assertTrue((output / "incidencias.jsonl").exists())

    def test_fila_invalida_no_reemplaza_publicacion_anterior(self):
        from pipeline.carga import cargar_lote

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "datos"
            output = Path(tmp) / "salida"
            root.mkdir()
            self._datos_minimos(root)
            cargar_lote(root, output)
            (root / "ventas.csv").write_text((root / "ventas.csv").read_text().replace("CLI001", "NO_EXISTE"), encoding="utf-8")
            result = cargar_lote(root, output)
            self.assertEqual(result.status, "pendiente_revision")
            self.assertIn("CLI001", (output / "publicado" / "ventas.csv").read_text())


if __name__ == "__main__":
    unittest.main()
