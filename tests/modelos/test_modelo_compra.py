import unittest
from datetime import date
from pathlib import Path



def _paquete(caso):
    from pipeline.rutas import ruta_paquete
    ruta = ruta_paquete()
    if ruta is None:
        caso.skipTest("Paquete de datos no disponible: define JACOMIND_DATOS o ubícalo junto al clon")
    return ruta

class ModeloCompraTests(unittest.TestCase):
    def test_fotografia_usa_solo_historial_y_etiqueta_futuro(self):
        from pipeline.modelo_compra import construir_fotografias

        clients = [{"cliente_id": "CLI001", "fecha_alta": date(2025, 1, 1)}]
        sales = [{"cliente_id": "CLI001", "fecha": date(2026, 1, 31), "estado": "Confirmada"}, {"cliente_id": "CLI001", "fecha": date(2026, 2, 15), "estado": "Confirmada"}]
        rows = construir_fotografias(clients, sales, date(2026, 1, 31), date(2026, 2, 28))
        self.assertEqual(rows[0]["frecuencia_30d"], 1)
        self.assertEqual(rows[0]["compra_30d"], 1)
        self.assertNotIn(date(2026, 2, 15), rows[0].get("historial_fechas", []))

    def test_reproduce_metricas_de_prueba_del_paquete(self):
        from pipeline.modelo_compra import entrenar_y_evaluar_desde_paquete

        result = entrenar_y_evaluar_desde_paquete(_paquete(self))
        self.assertEqual(result["prueba_modelo"]["TP"], 120)
        self.assertEqual(result["prueba_modelo"]["TN"], 51)
        self.assertEqual(result["prueba_modelo"]["FP"], 177)
        self.assertEqual(result["prueba_modelo"]["FN"], 12)
        self.assertEqual(result["umbral"], 0.4)


if __name__ == "__main__":
    unittest.main()
