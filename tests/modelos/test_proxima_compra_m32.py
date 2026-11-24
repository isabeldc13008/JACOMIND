"""M3.2 · factor de nivel por corte: cortes maduros sin fuga, estimador de máxima verosimilitud, artefacto y contrato."""
import importlib.util
import math
import unittest
from datetime import date, timedelta

HAY_SKSURV = importlib.util.find_spec("sksurv") is not None


def _c(fecha):
    return {"venta_id": "V", "fecha": fecha, "importe_cop": 1.0}


def _art(nivel=True):
    from modelos.inferencia import desde_dict, sellar
    tr = [{"variable": "recencia_dias", "funcion": "identidad", "media": 0.0, "desviacion": 1.0, "imputacion": 0.0}]
    d = {"formato": "jacomind.supervivencia_residual.v1", "modelo_id": "proxima_compra", "version": "t", "version_variables": "proxima_compra-variables-v1",
         "horizonte_dias": 60, "soporte_dias": 60, "umbral": None, "ancho_maximo_ventana_dias": 30, "disponible_desde": "2026-10-31", "tipo": "cox",
         "cox": {"variables": ["recencia_dias"], "transformaciones": tr, "coeficientes": [0.0], "tiempos_base": [10, 30, 60],
                 "riesgo_acumulado_base": [0.2, 0.6, 1.2]},
         "ventana": {"limites": ["p10", "p50"], "ancho_maximo_dias": 30}, "probabilidades_acumuladas_dias": [15, 30, 60]}
    if nivel:
        d["nivel"] = {"regla": "ultimos_cortes_maduros", "cortes": 3}
    return desde_dict(sellar(d))


class NivelTests(unittest.TestCase):
    def test_cortes_maduros_antes_del_corte(self):
        from modelos.proxima_compra import cortes_nivel
        self.assertEqual(cortes_nivel(date(2026, 7, 31), 3), [date(2026, 3, 31), date(2026, 4, 30), date(2026, 5, 31)])  # 31-05 + 60 = 30-07
        self.assertEqual(cortes_nivel(date(2026, 7, 30), 3)[-1], date(2026, 4, 30))  # 31-05 + 60 no es anterior al 30-07
        for c in (date(2026, 4, 30), date(2026, 10, 31)):
            self.assertTrue(all(x + timedelta(days=60) < c for x in cortes_nivel(c, 3)))

    def test_estimador_y_sin_fuga(self):
        from modelos.proxima_compra import factor_nivel
        art = _art()
        clientes = [{"cliente_id": f"C{i}", "fecha_alta": date(2025, 1, 1)} for i in range(4)]
        hist = {"C0": [_c(date(2026, 2, 20)), _c(date(2026, 3, 10))], "C1": [_c(date(2026, 1, 5))],
                "C2": [_c(date(2026, 3, 1)), _c(date(2026, 4, 25))], "C3": []}
        f = factor_nivel(art, clientes, hist, date(2026, 5, 31))
        self.assertEqual(f["seguimiento_hasta"], "2026-05-30")
        self.assertAlmostEqual(f["factor"], f["eventos"] / f["esperado"])
        hist2 = dict(hist, C1=hist["C1"] + [_c(date(2026, 5, 31))])  # compra el mismo día del corte: no se usa
        self.assertEqual(factor_nivel(art, clientes, hist2, date(2026, 5, 31)), f)

    def test_artefacto_exige_factor_y_lo_aplica(self):
        from modelos.inferencia import ArtefactoInvalido, sellar
        art = _art()
        fila = {"recencia_dias": 10, "dias_compra_distintos": 5}
        with self.assertRaises(ValueError):
            art.curva(fila)
        s1 = art.supervivencia(dict(fila, factor_nivel=1.0), 30)
        s07 = art.supervivencia(dict(fila, factor_nivel=0.7), 30)
        self.assertAlmostEqual(s1, math.exp(-0.6))
        self.assertAlmostEqual(s07, math.exp(-0.6 * 0.7))
        self.assertEqual(_art(nivel=False).supervivencia(fila, 30), s1)
        with self.assertRaises(ArtefactoInvalido):
            sellar(dict(art.datos, nivel={"regla": "otra", "cortes": 3}))

    def test_contrato_factor_nivel(self):
        from contratos.validar import _reglas_proxima
        base = {"probabilidad": None, "estado": "sin_historial", "soporte_dias": 60, "ancho_maximo_ventana_dias": 30, "ventana_utilizable": False,
                "ancho_ventana_dias": None, "corte": "2026-10-31"}
        self.assertEqual(_reglas_proxima(dict(base, factor_nivel=0.7), "f"), [])
        self.assertTrue(_reglas_proxima(dict(base, factor_nivel=0), "f"))


if __name__ == "__main__":
    unittest.main()
