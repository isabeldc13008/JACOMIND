"""M3.1 · próxima compra: Cox estratificado (contraste con scikit-survival), ventana p10–p50, probabilidad acumulada,
contrato, compatibilidad con M3 y experimento completo."""
import copy
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKSURV = importlib.util.find_spec("sksurv") is not None
C = date(2026, 10, 31)


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _base_artefacto(**k):
    from modelos.inferencia import sellar
    d = {"formato": "jacomind.supervivencia_residual.v1", "modelo_id": "proxima_compra", "version": "t", "version_variables": "proxima_compra-variables-v1",
         "horizonte_dias": 60, "soporte_dias": 60, "umbral": None, "ancho_maximo_ventana_dias": 30, "disponible_desde": "2026-10-31"}
    return sellar(d | k)


def _estratificado(estratos, ventana=True):
    tr = [{"variable": "recencia_dias", "funcion": "identidad", "media": 0.0, "desviacion": 1.0, "imputacion": 0.0}]
    extra = {"ventana": {"limites": ["p10", "p50"], "ancho_maximo_dias": 30}, "probabilidades_acumuladas_dias": [15, 30, 60]} if ventana else {}
    return _base_artefacto(tipo="cox_estratificado", cox={"variables": ["recencia_dias"], "transformaciones": tr, "coeficientes": [0.0],
                                                          "variable_estrato": "grupo", "estratos": estratos}, **extra)


class ArtefactoM31Tests(unittest.TestCase):
    def test_curva_por_grupo_estrato_sin_soporte_y_ventana_p10_p50(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict
        from modelos.proxima_compra import predicciones_proxima
        rapido = {"tiempos_base": [5, 10], "riesgo_acumulado_base": [0.2, 1.0]}
        lento = {"tiempos_base": [30], "riesgo_acumulado_base": [0.15]}
        art = desde_dict(_estratificado({"reciente": rapido, "frio": lento}))
        f_rec = {"recencia_dias": 5, "dias_compra_distintos": 6}
        f_frio = {"recencia_dias": 120, "dias_compra_distintos": 6}
        self.assertLess(art.curva(f_rec)[20], art.curva(f_frio)[20])  # cada grupo con su curva base
        self.assertEqual(art.curva({"recencia_dias": 45, "dias_compra_distintos": 6}), [])  # 'habitual' sin estrato: sin soporte
        with self.assertRaises(ArtefactoInvalido):
            _estratificado({"otro": rapido})
        hist = {"A": [{"venta_id": "1", "fecha": date(2026, 9, 1), "importe_cop": 1.0}, {"venta_id": "2", "fecha": date(2026, 10, 1), "importe_cop": 1.0},
                      {"venta_id": "3", "fecha": date(2026, 10, 26), "importe_cop": 1.0}],
                "H": [{"venta_id": "4", "fecha": date(2026, 8, 1), "importe_cop": 1.0}, {"venta_id": "5", "fecha": date(2026, 8, 20), "importe_cop": 1.0},
                      {"venta_id": "6", "fecha": date(2026, 9, 15), "importe_cop": 1.0}]}
        filas = {f["cliente_id"]: f for f in predicciones_proxima(art, None, [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)},
                                                                              {"cliente_id": "H", "fecha_alta": date(2025, 1, 1)}], hist, C)}
        a = filas["A"]
        self.assertEqual((a["ventana_tipo"], a["dias_p10"], a["ancho_ventana_dias"]), ("p10_p50", a["dias_p10"], a["dias_p50"] - a["dias_p10"]))
        self.assertTrue(a["ventana_utilizable"])
        self.assertEqual(sorted(a["prob_acumulada"]), ["15", "30", "60"])
        self.assertEqual(filas["H"]["estado"], "sin_soporte")
        from contratos.validar import validar_predicciones
        self.assertEqual(validar_predicciones(list(filas.values()), None, {"corte": "2026-10-31"}), [])
        malo = dict(a, prob_acumulada={"15": 0.6, "30": 0.5})  # no decreciente
        self.assertTrue(validar_predicciones([malo], None, {"corte": "2026-10-31"}))
        self.assertTrue(validar_predicciones([dict(a, ventana_tipo="p25_p75")], None, {"corte": "2026-10-31"}))

    def test_artefacto_m3_sin_ventana_no_cambia_sus_filas(self):
        from modelos.inferencia import desde_dict
        from modelos.proxima_compra import predicciones_proxima
        km = desde_dict(_base_artefacto(tipo="km", km={"tiempos": [5, 20], "supervivencia": [0.8, 0.4]}))
        f = predicciones_proxima(km, None, [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}],
                                 {"A": [{"venta_id": "1", "fecha": date(2026, 10, 1), "importe_cop": 1.0}]}, C)[0]
        self.assertNotIn("ventana_tipo", f)
        self.assertNotIn("prob_acumulada", f)


@unittest.skipUnless(HAY_SKSURV, "Requiere scikit-survival")
class CoxEstratificadoTests(unittest.TestCase):
    def test_un_estrato_reproduce_scikit_survival(self):
        import random
        from modelos.proxima_compra_m31 import cargar_config, contraste_sksurv
        rng = random.Random(5)
        filas = []
        for i in range(250):
            x = rng.random()
            t = min(60, max(1, int(rng.expovariate(0.02 + 0.06 * x))))
            filas.append({"recencia_dias": int(100 * x), "dias_compra_90d": rng.randint(0, 5), "dias_compra_180d": rng.randint(0, 9),
                          "dias_compra_distintos": rng.randint(1, 20), "intervalo_mediano_dias": 10 + 40 * x, "intervalo_dispersion_dias": 4.0,
                          "historia_insuficiente": 0, "importe_cop_90d": 10.0 * x, "duracion": t, "evento": int(t < 60)})
        cfg = cargar_config()
        for alpha in (0.1, 10):
            r = contraste_sksurv(filas, cfg["variables"], alpha, cfg)
            self.assertLess(r["diferencia_coeficientes"], 1e-5)
            self.assertLess(r["diferencia_riesgo_base"], 1e-6)


@unittest.skipIf(_paquete() is None or not HAY_SKSURV, "Requiere el paquete y scikit-survival")
class ExperimentoM31Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.proxima_compra_m31 import cargar_config, entrenar
        cls.tmp = Path(tempfile.mkdtemp(prefix="m31-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cfg = cargar_config()
        cfg["metricas"]["bootstrap"]["repeticiones"] = 20  # rapidez: otra configuración, otra carpeta
        cls.config = cfg
        cls.r = entrenar(cls.datos, cfg, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_candidatos_seleccion_y_contraste(self):
        sel = self.r["seleccion"]
        self.assertEqual(len(sel["candidatos"]), 9)  # KM + 4 Cox + 4 Cox estratificados
        self.assertLess(sel["contraste_cox_propio_vs_sksurv_un_estrato"]["diferencia_coeficientes"], 1e-5)
        art = json.loads((self.tmp / "e1" / "artefacto.json").read_text(encoding="utf-8"))
        self.assertEqual(art["ventana"]["limites"], ["p10", "p50"])
        self.assertEqual(art["huella"], sel["elegido_artefacto_huella"])

    def test_evaluacion_idempotente_sombra_y_otra_configuracion(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.ejecucion import EjecucionError
        from modelos.inferencia import cargar_artefacto
        from modelos.proxima_compra import puntuar_sombra
        from modelos.proxima_compra_m31 import entrenar, evaluar
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        a, b = evaluar(d, self.datos), evaluar(d, self.datos)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        self.assertIn("calibracion_acumulada", a["metricas"]["resultados"])
        art = cargar_artefacto(d / "artefacto.json", modelo_id="proxima_compra")
        puntuar_sombra(art, self.datos, C, self.tmp / "sombra", estado_experimento="experimental en sombra")
        errores, man, filas = leer_publicacion_sombra(self.tmp / "sombra")
        self.assertEqual(errores, [])
        self.assertTrue(all(f.get("ventana_tipo") == "p10_p50" for f in filas))
        otra = copy.deepcopy(self.config)
        otra["ventana"]["ancho_maximo_dias"] = 20
        with self.assertRaises(EjecucionError):
            entrenar(self.datos, otra, self.tmp / "e1")


if __name__ == "__main__":
    unittest.main()
