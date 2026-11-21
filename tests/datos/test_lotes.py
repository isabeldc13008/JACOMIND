import tempfile
import unittest
from pathlib import Path


class LotesTests(unittest.TestCase):
    def test_huella_es_estable_y_reenvio_identico_se_reutiliza(self):
        from pipeline.lotes import calcular_sha256, clasificar_reenvio

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ventas.csv"
            path.write_text("venta_id\nVEN001\n", encoding="utf-8")
            digest = calcular_sha256(path)
            decision = clasificar_reenvio({"sha256": digest, "revision": 1}, digest, [])
            self.assertEqual(decision.status, "reutilizar")

    def test_cambio_con_misma_clave_crea_revision(self):
        from pipeline.lotes import clasificar_reenvio

        decision = clasificar_reenvio({"sha256": "old", "revision": 2, "rows": {"VEN001": {"precio": "10"}}}, "new", [("VEN001", {"precio": "12"})])
        self.assertEqual(decision.status, "nueva_revision")
        self.assertEqual(decision.revision, 3)


if __name__ == "__main__":
    unittest.main()
