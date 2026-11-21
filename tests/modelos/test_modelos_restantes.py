import unittest
from datetime import date
from decimal import Decimal


class ModelosRestantesTests(unittest.TestCase):
    def test_riesgo_y_proxima_compra_respetan_abstencion(self):
        from pipeline.riesgo import estimar_riesgo, estimar_proxima_compra

        self.assertTrue(estimar_riesgo({"cliente_id": "A", "ultima_compra": date(2026, 7, 1)}, date(2026, 10, 31))["riesgo_inactividad"])
        self.assertEqual(estimar_proxima_compra([20, 30, 40])["mediana_dias"], 30)
        self.assertEqual(estimar_proxima_compra([])["estado"], "historia_insuficiente")

    def test_oportunidades_conservan_motivos(self):
        from pipeline.oportunidades import generar_oportunidades

        result = generar_oportunidades([{"cliente_id": "A", "frio": True, "coberturas": [{"instalacion_id": "I", "fecha_fin": date(2026, 11, 10), "proxima": True}], "productos_historicos": ["P1"]}], {"P1": "F1", "P2": "F2"}, date(2026, 10, 31))
        self.assertEqual({row["tipo"] for row in result}, {"renovacion", "reactivacion", "venta_cruzada"})

    def test_pronostico_media_movil_y_escenario_trm(self):
        from pipeline.pronostico import pronosticar_media_movil
        from pipeline.cambiario import simular_exposicion

        self.assertEqual(pronosticar_media_movil([Decimal("10"), Decimal("20"), Decimal("30")], 2, 2), [Decimal("25.00"), Decimal("27.50")])
        self.assertEqual(simular_exposicion([{"usd": Decimal("300"), "trm": Decimal("4000"), "familia": "F"}], Decimal("0.08"))["diferencia_cop"], Decimal("96000.00"))

    def test_pqrs_y_salud_modelo(self):
        from pipeline.pqrs import clasificar_pqrs
        from pipeline.salud import evaluar_salud

        self.assertEqual(clasificar_pqrs("Tengo una queja por el cobro")["categoria"], "queja")
        self.assertEqual(evaluar_salud({"nulos": 2, "total": 100}, {"nulos": 1, "total": 100})["estado"], "revisar")


if __name__ == "__main__":
    unittest.main()
