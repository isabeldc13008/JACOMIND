import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path



def _paquete(caso):
    from pipeline.rutas import ruta_paquete
    ruta = ruta_paquete()
    if ruta is None:
        caso.skipTest("Paquete de datos no disponible: define JACOMIND_DATOS o ubícalo junto al clon")
    return ruta

class FichaTests(unittest.TestCase):
    def test_ficha_distingue_frecuente_frio_y_sin_historial(self):
        from pipeline.ficha import construir_ficha

        clients = [{"cliente_id": "CLI001", "fecha_alta": date(2026, 1, 1)}, {"cliente_id": "CLI002", "fecha_alta": date(2026, 1, 1)}]
        sales = [{"venta_id": f"V{i}", "cliente_id": "CLI001", "fecha": date(2026, 8, 2), "cantidad": 1, "producto_id": "P", "importe_cop": Decimal("10"), "estado": "Confirmada"} for i in range(8)]
        sales.append({"venta_id": "V9", "cliente_id": "CLI001", "fecha": date(2026, 10, 31), "cantidad": 1, "producto_id": "P", "importe_cop": Decimal("10"), "estado": "Confirmada"})
        rows = construir_ficha(clients, sales, [], date(2026, 10, 31), frecuente_min=8, frio_dias=90)
        cli1 = next(row for row in rows if row["cliente_id"] == "CLI001")
        cli2 = next(row for row in rows if row["cliente_id"] == "CLI002")
        self.assertTrue(cli1["frecuente"])
        self.assertFalse(cli1["frio"])
        self.assertTrue(cli2["sin_compras"])
        self.assertIsNone(cli2["ultima_compra"])

    def test_intervalos_usan_dias_distintos_y_cobertura_proxima_tambien_vigente(self):
        from pipeline.ficha import construir_ficha

        clients = [{"cliente_id": "CLI001", "fecha_alta": date(2026, 1, 1)}]
        sales = [{"venta_id": "V1", "cliente_id": "CLI001", "fecha": date(2026, 1, 1), "cantidad": 1, "producto_id": "P", "importe_cop": Decimal("10"), "estado": "Confirmada"}, {"venta_id": "V2", "cliente_id": "CLI001", "fecha": date(2026, 1, 11), "cantidad": 1, "producto_id": "P", "importe_cop": Decimal("10"), "estado": "Confirmada"}, {"venta_id": "V3", "cliente_id": "CLI001", "fecha": date(2026, 1, 11), "cantidad": 1, "producto_id": "P", "importe_cop": Decimal("10"), "estado": "Confirmada"}]
        installs = [{"instalacion_id": "I1", "cliente_id": "CLI001", "producto_id": "P", "fecha_inicio": date(2026, 1, 1), "fecha_fin": date(2026, 12, 15), "unidades": 1}, {"instalacion_id": "I2", "cliente_id": "CLI001", "producto_id": "P", "fecha_inicio": date(2026, 1, 1), "fecha_fin": date(2026, 10, 31), "unidades": 1}]
        row = construir_ficha(clients, sales, installs, date(2026, 10, 31))[0]
        self.assertEqual(row["intervalos_compra_dias"], [10])
        self.assertEqual(row["coberturas_vigentes"], 2)
        self.assertEqual(row["coberturas_proximas"], 2)

    def test_paquete_sintetico_concilia_120_clientes_y_41_frios(self):
        from pipeline.ficha import construir_ficha_desde_paquete

        root = _paquete(self)
        rows = construir_ficha_desde_paquete(root, date(2026, 10, 31))
        self.assertEqual(len(rows), 120)
        self.assertEqual(sum(row["frio"] for row in rows), 41)


if __name__ == "__main__":
    unittest.main()
