import unittest
from datetime import date
from decimal import Decimal


class SegmentacionTests(unittest.TestCase):
    def test_escalado_hace_invariante_la_escala_del_importe(self):
        from pipeline.segmentacion import preparar_rfm

        rows = [{"cliente_id": "A", "recencia_dias": 10, "frecuencia": 2, "importe": Decimal("100")}, {"cliente_id": "B", "recencia_dias": 20, "frecuencia": 1, "importe": Decimal("200")}]
        scaled = preparar_rfm(rows)
        scaled_10 = preparar_rfm([{**row, "importe": row["importe"] * 10} for row in rows])
        self.assertEqual(scaled["A"][2], scaled_10["A"][2])

    def test_clientes_sin_historial_quedan_aparte(self):
        from pipeline.segmentacion import segmentar_clientes

        rows = [{"cliente_id": "A", "recencia_dias": 10, "frecuencia": 2, "importe": Decimal("100")}, {"cliente_id": "B", "recencia_dias": None, "frecuencia": 0, "importe": Decimal("0")}]
        result = segmentar_clientes(rows, k=2)
        self.assertEqual(result["B"]["segmento"], "sin_historial")
        self.assertEqual(result["A"]["segmento"][:3], "seg")


if __name__ == "__main__":
    unittest.main()
