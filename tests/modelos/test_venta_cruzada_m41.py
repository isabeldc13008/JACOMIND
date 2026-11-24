"""M4.1 · secuencia reciente sin fuga, antigüedad, azar reproducible y compatibilidad con M4."""
import unittest
from datetime import date, timedelta

C = date(2026, 5, 31)


def _c(fecha, p):
    return {"fecha": fecha, "producto_id": p, "importe_cop": 1.0, "venta_id": f"{p}{fecha}"}


class TransicionTests(unittest.TestCase):
    def compras(self):
        return {"A": [_c(date(2026, 1, 1), "P1"), _c(date(2026, 1, 20), "P2")],
                "B": [_c(date(2026, 2, 1), "P1"), _c(date(2026, 5, 1), "P3")],
                "Z": [_c(date(2025, 1, 1), "P4")]}

    def test_solo_eventos_maduros_y_catalogo_al_corte(self):
        from modelos.venta_cruzada import transiciones
        t = transiciones(self.compras(), C)
        self.assertEqual(t["eventos"]["P1"]["P2"], [2, 1])  # A compra P2 a los 19 días de P1; B no
        self.assertEqual(t["eventos"]["P1"]["P3"], [2, 0])  # la compra de B del 05-01 cae fuera de los 60 días
        futuras = self.compras()
        futuras["B"].append(_c(C + timedelta(days=1), "P9"))  # producto y compra posteriores al corte
        futuras["A"].append(_c(C, "P2"))                     # evento en C: no madura antes del corte
        self.assertEqual(transiciones(futuras, C), t)

    def test_suavizado_y_sin_compra_reciente(self):
        from modelos.venta_cruzada import transicion_reciente, transiciones
        t = transiciones(self.compras(), C)
        b = t["base"]["P2"]
        base = b[1] / b[0]
        self.assertAlmostEqual(transicion_reciente([_c(date(2025, 1, 1), "P4")], "P2", t, C), base)  # nada en 60 días: tasa base
        reciente = [_c(C - timedelta(days=10), "P1")]
        self.assertAlmostEqual(transicion_reciente(reciente, "P2", t, C), (1 + 20 * base) / (2 + 20))


class AzarTests(unittest.TestCase):
    def test_reproducible_y_sin_duplicados(self):
        from modelos.venta_cruzada_m41 import _azar
        ps = [{"cliente_id": "A", "corte": C, "producto_id": p} for p in ("P3", "P1", "P2", "P4", "P1")]
        a, b = _azar(ps, 7), _azar(list(reversed(ps)), 7)
        self.assertEqual([p["producto_id"] for p in a], [p["producto_id"] for p in b])
        self.assertEqual(len({p["producto_id"] for p in a}), 3)
        self.assertEqual(_azar([], 7), [])


if __name__ == "__main__":
    unittest.main()
