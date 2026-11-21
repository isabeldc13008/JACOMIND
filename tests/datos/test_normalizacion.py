import unittest
from decimal import Decimal


class NormalizacionTests(unittest.TestCase):
    def test_normaliza_tipos_sin_perder_precision(self):
        from pipeline.esquemas import TABLAS
        from pipeline.normalizacion import normalizar_fila

        row = normalizar_fila({"compra_id": "COM001", "fecha": "2026-01-02", "proveedor_id": "PRO001", "producto_id": "PR001", "cantidad": "2", "moneda": "COP", "costo_unitario": "100000.10", "origen_datos": "prueba"}, TABLAS["compras"])
        self.assertEqual(row["cantidad"], 2)
        self.assertEqual(row["costo_unitario"], Decimal("100000.10"))
        self.assertEqual(row["proveedor_id"], "PRO001")

    def test_fecha_ambigua_es_incidencia_de_normalizacion(self):
        from pipeline.esquemas import TABLAS
        from pipeline.normalizacion import NormalizacionError, normalizar_fila

        with self.assertRaises(NormalizacionError):
            normalizar_fila({"fecha": "01/02/2026"}, TABLAS["trm"])


if __name__ == "__main__":
    unittest.main()
