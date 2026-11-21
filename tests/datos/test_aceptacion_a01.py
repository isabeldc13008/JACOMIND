import unittest
from pathlib import Path
import tempfile


class AceptacionA01Tests(unittest.TestCase):
    def test_paquete_sintetico_conserva_conteos_principales(self):
        from pipeline.carga import cargar_lote

        data_root = Path(r"C:\Users\idelg\OneDrive\Documents\ChatGPT\Green_Services_Recursos_de_Prueba")
        if not data_root.exists():
            self.skipTest("Paquete sintético no disponible en este equipo")
        with tempfile.TemporaryDirectory() as tmp:
            result = cargar_lote(data_root, Path(tmp) / "salida")
            self.assertEqual(result.inventory["clientes"]["accepted"], 120)
            self.assertEqual(result.inventory["ventas"]["accepted"], 1407)
            self.assertEqual(result.inventory["compras"]["accepted"], 240)
            self.assertEqual(result.inventory["instalaciones"]["accepted"], 243)
            self.assertEqual(result.inventory["trm"]["accepted"], 669)
            self.assertEqual(result.inventory["ventas_opcional"]["duplicates"], 1)
            self.assertEqual(result.inventory["ventas_opcional"]["isolated"], 6)
            self.assertEqual(len(result.issues), 7)


if __name__ == "__main__":
    unittest.main()
