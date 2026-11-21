import unittest
from decimal import Decimal


class ValidacionNumericaTests(unittest.TestCase):
    def test_rechaza_decimal_no_finito_y_tasas_no_positivas(self):
        from pipeline.esquemas import TABLAS
        from pipeline.normalizacion import NormalizacionError, normalizar_fila
        from pipeline.validacion import validar_fila

        with self.assertRaises(NormalizacionError):
            normalizar_fila({"cop_por_usd": "NaN", "fecha": "2026-01-01", "origen": "p"}, TABLAS["trm"])
        issues = validar_fila({"fecha": "2026-01-01", "cop_por_usd": Decimal("0"), "origen": "p"}, TABLAS["trm"], {})
        self.assertEqual(issues[0].code, "TASA_NO_POSITIVA")


if __name__ == "__main__":
    unittest.main()
