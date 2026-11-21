import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path


class OperacionesTests(unittest.TestCase):
    def test_importe_cop_con_descuento(self):
        from pipeline.operaciones import calcular_importe

        row = {"estado": "Confirmada", "cantidad": 2, "precio_unitario": Decimal("100000"), "descuento_pct": Decimal("10"), "moneda": "COP", "fecha": date(2026, 1, 1)}
        self.assertEqual(calcular_importe(row, {}), Decimal("180000.00"))

    def test_importe_usd_usa_tasa_de_la_fecha(self):
        from pipeline.operaciones import calcular_importe

        row = {"estado": "Confirmada", "cantidad": 3, "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "moneda": "USD", "fecha": date(2026, 1, 1)}
        self.assertEqual(calcular_importe(row, {date(2026, 1, 1): Decimal("4000")}), Decimal("1200000"))

    def test_anulada_aporta_cero(self):
        from pipeline.operaciones import calcular_importe

        row = {"estado": "Anulada", "cantidad": 2, "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "moneda": "COP", "fecha": date(2026, 1, 1)}
        self.assertEqual(calcular_importe(row, {}), Decimal("0"))

    def test_cierre_sintetico_concilia_ventas_y_compras_por_separado(self):
        from pipeline.operaciones import calcular_cierre

        root = Path(r"C:\Users\idelg\OneDrive\Documents\ChatGPT\Green_Services_Recursos_de_Prueba")
        result = calcular_cierre(root, date(2026, 10, 31))
        self.assertEqual(result.sales.confirmed_count, 1371)
        self.assertEqual(result.sales.total_cop, Decimal("5647449456.36"))
        self.assertEqual(result.purchases.operation_count, 240)
        self.assertNotEqual(result.sales.operation_count, result.sales.confirmed_count + result.purchases.operation_count)

    def test_anomalia_requiere_historia_y_usa_mad(self):
        from pipeline.operaciones import detectar_anomalias

        rows = [{"period": f"2026-0{index}", "family": "F", "currency": "COP", "value": Decimal(str(value)), "id": str(value)} for index, value in enumerate([100, 101, 99, 1000], start=1)]
        alerts = detectar_anomalias(rows, min_history=3)
        self.assertEqual([alert["id"] for alert in alerts], ["1000"])


if __name__ == "__main__":
    unittest.main()
