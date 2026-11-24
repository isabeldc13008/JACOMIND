"""Resumen de resultados de los modelos de IA (``modelos.resumen_ia``) y su ruta ``GET /api/ia``."""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))
from _apoyo_app import CasoBase  # noqa: E402


class LecturaTests(unittest.TestCase):
    def filas(self, a, b, prob=0.35):
        return [{"metodo": "Nuevo", "tipo": "ia", "actual": True, "aciertos_top10": a, "de_top10": 30, "aciertos_top20": 32, "probabilidad_media": prob},
                {"metodo": "Viejo", "tipo": "ia", "actual": False, "aciertos_top10": 13, "de_top10": 30, "aciertos_top20": 30, "probabilidad_media": None},
                {"metodo": "Mayor recencia", "tipo": "regla", "actual": False, "aciertos_top10": b, "de_top10": 30, "aciertos_top20": 34, "probabilidad_media": None}]

    def test_frases_calculadas_desde_los_datos(self):
        from modelos.resumen_ia import lectura
        self.assertIn("(empate)", lectura(self.filas(17, 17), 0.367)[0])
        self.assertIn("la regla acierta algo más", lectura(self.filas(15, 17), 0.367)[0])
        self.assertIn("el modelo acierta más", lectura(self.filas(19, 17), 0.367)[0])
        txt = " ".join(lectura(self.filas(17, 17), 0.367))
        self.assertIn("Supera a Viejo (13 de 30)", txt)
        self.assertIn("35,0 % frente a 36,7 %", txt)
        self.assertIn("32 aciertos frente a 34", txt)


@unittest.skipUnless((RAIZ / "salida" / "experimentos" / "compra_30d_m13" / "ejecucion-001" / "congelacion.json").exists()
                     and (RAIZ / "salida" / "experimentos" / "inactividad_60d_m21" / "ejecucion-001" / "evaluacion.json").exists()
                     and (RAIZ / "var" / "modelos" / "compra_30d" / "registro.json").exists(), "Requiere las ejecuciones locales")
class ConstruirTests(unittest.TestCase):
    def test_resumen_marca_la_version_en_uso_y_no_inventa_cifras(self):
        from modelos import registro as R
        from modelos.resumen_ia import construir
        d = construir()
        self.assertEqual(d["origen_datos"], "sintetico")
        compra, inact = d["modelos"][:2]
        if len(d["modelos"]) > 2:
            self.assertEqual(d["modelos"][2]["modelo_id"], "proxima_compra")
            self.assertTrue(d["modelos"][2]["tabla"]["filas"])
        _, op = R.artefacto_registrado(None, "compra_30d")
        actual = [f for f in compra["filas"] if f["actual"]]
        self.assertEqual(len(actual), 1)
        self.assertEqual(compra["version"], op["artefacto_version"])
        met = json.loads((RAIZ / "salida/experimentos/compra_30d_m13/ejecucion-001/metricas_comprobacion_historica.json").read_text(encoding="utf-8"))
        rec = next(f for f in compra["filas"] if f["tipo"] == "regla")
        self.assertEqual(rec["aciertos_top10"], met["resultados"]["recencia"]["elegible"]["agregado"]["aciertos_top10"])
        self.assertIn("experimental", inact["estado"])
        self.assertTrue(all(f["metodo"] != "M2.1" or f["actual"] for f in inact["filas"]))


class RutaIATests(CasoBase):
    def test_permisos_sin_resumen_y_con_resumen(self):
        with mock.patch("api.servidor.DIR_SALIDA", self.tmp):
            self.assertEqual(self.http("GET", "/api/ia")[0], 401)
            self.assertEqual(self.http("GET", "/api/ia", como="cli_a")[0], 403)
            st, d = self.http("GET", "/api/ia", como="ventas1")
            self.assertEqual((st, d["estado"]), (200, "sin_resumen"))
            (self.tmp / "ia").mkdir()
            (self.tmp / "ia" / "resumen.json").write_text(json.dumps({"version": 1, "modelos": [], "advertencia": "x"}), encoding="utf-8")
            st, d = self.http("GET", "/api/ia", como="ger1")
            self.assertEqual((st, d["estado"]), (200, "ok"))
            (self.tmp / "ia" / "resumen.json").write_text(json.dumps({"version": 9}), encoding="utf-8")
            self.assertEqual(self.http("GET", "/api/ia", como="ops1")[0], 500)


if __name__ == "__main__":
    unittest.main()
