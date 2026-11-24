"""Pruebas de M1.2: orden del cupo por fusión de rangos sin alterar probabilidades ni C1."""
import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from tests.modelos.test_m1_correcciones import _artefacto, _datos

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


class FusionTests(unittest.TestCase):
    def test_definicion_y_desempates(self):
        from modelos.ranking import posiciones_fusion
        filas = [{"cliente_id": "A", "recencia_dias": 1, "p": 0.1}, {"cliente_id": "B", "recencia_dias": 5, "p": 0.9},
                 {"cliente_id": "C", "recencia_dias": 3, "p": 0.5}, {"cliente_id": "D", "recencia_dias": 3, "p": 0.5}]
        # rR: A1 C2 D3 B4 ; rM: B1 C2 D3 A4 -> sumas A5 B5 C4 D6 -> C, A (rR 1) , B, D
        self.assertEqual(posiciones_fusion(filas, lambda f: f["p"]), {"C": 1, "A": 2, "B": 3, "D": 4})
        self.assertEqual(posiciones_fusion(list(reversed(filas)), lambda f: f["p"]), {"C": 1, "A": 2, "B": 3, "D": 4})
        with self.assertRaises(ValueError):
            posiciones_fusion(filas + [filas[0]], lambda f: f["p"])

    def test_puntuar_usa_la_fusion_sin_cambiar_probabilidades(self):
        from modelos import compra
        from modelos.inferencia import ArtefactoInvalido, desde_dict, sellar
        from modelos.ranking import posiciones_fusion
        base = _artefacto()
        fus = desde_dict(sellar(dict(base, politica_orden={"id": "fusion_rangos_recencia_v1"})))
        datos = _datos()
        r_base = compra.puntuar(desde_dict(base), datos, date(2026, 10, 31))
        r_fus = compra.puntuar(fus, datos, date(2026, 10, 31))
        self.assertEqual([f["probabilidad"] for f in r_base["filas"]], [f["probabilidad"] for f in r_fus["filas"]])
        esperado = posiciones_fusion([f for f in compra.construir_fotografias(
            datos.clientes, compra.historial_compras(datos.ventas, datos.productos, datos.tasas), [date(2026, 10, 31)],
            datos.observado_hasta) if f["elegibilidad"] == "elegible"], fus.probabilidad)
        self.assertEqual({f["cliente_id"]: f["posicion"] for f in r_fus["filas"]}, esperado)
        self.assertEqual(r_fus["resumen"]["politica_orden"], "fusion_rangos_recencia_v1")
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(sellar(dict(base, politica_orden={"id": "inventada"})))


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ExperimentoM12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_datos_config
        from modelos.compra_m12 import CONFIG_M12, entrenar_m12
        from modelos.datos import preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m12-"))
        cls.config = json.loads(CONFIG_M12.read_text(encoding="utf-8"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos_config(cls.tmp / "a01", cls.config)
        cls.r = entrenar_m12(cls.datos, cls.config, cls.tmp / "exp" / "e1")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_validacion_temporal_sin_fuga_y_reproducible(self):
        from modelos.compra_m12 import entrenar_m12
        d = self.r["desarrollo"]
        self.assertEqual(len(d["por_origen"]), 10)
        for o in d["por_origen"]:
            self.assertLessEqual(o["origen"], "2026-06-30")
        self.assertTrue(all(c <= "2026-06-30" for c in self.r["congelacion"]["cortes_entrenamiento_final"]))
        self.assertLessEqual(self.r["congelacion"]["equivalencia_json_sklearn"]["diferencia_maxima"], 1e-9)
        r2 = entrenar_m12(self.datos, self.config, self.tmp / "exp" / "e2")
        self.assertEqual(r2["artefacto"]["huella"], self.r["artefacto"]["huella"])
        self.assertEqual(r2["desarrollo"]["agregado"], d["agregado"])

    def test_evaluacion_decide_sin_reajustar_ni_promover_y_detecta_cambios(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m12 import evaluar_m12
        registro = RAIZ / "var" / "modelos" / "compra_30d" / "registro.json"
        antes = registro.read_bytes() if registro.exists() else None
        with mock.patch("modelos.compra_m12.ajustar_m12", side_effect=AssertionError("no debe ajustar")):
            r = evaluar_m12(self.tmp / "exp" / "e1", self.datos)
        self.assertIn(r["decision"]["decision"], ("favorable", "inconcluso", "rechazado"))
        self.assertEqual([m["top10"]["aciertos"] for m in r["metricas"]["resultados"]["recencia"]["elegible"]["por_mes"]], [5, 7, 5])
        if antes is not None:
            self.assertEqual(registro.read_bytes(), antes)
        d = self.tmp / "alterado"
        shutil.copytree(self.tmp / "exp" / "e1", d)
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        cfg["metas"]["mejora_minima_precision_top10"] = -1
        (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            evaluar_m12(d, self.datos)

    def test_c1_conserva_la_probabilidad_del_modelo(self):
        from contratos.validar import validar_publicacion
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        from pipeline.generar import generar
        art = desde_dict(self.r["artefacto"])
        reg = self.tmp / "registro-aislado"
        R.promover(reg, "compra_30d", "v9", art, {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": art.huella,
                                                   "origen_datos": "fixture_empresarial", "aprobado_por": "fixture"}, {}, "operativo")
        generar(_paquete(), "2026-10-31", self.tmp / "cierre", registro=reg)
        res, datos = validar_publicacion(self.tmp / "cierre")
        self.assertTrue(res.valido, res.errores)
        from modelos.variables import historial_compras, variables_al_corte
        from modelos.datos import cargar_datos
        d = cargar_datos(self.tmp / "a01")
        h = historial_compras(d.ventas, d.productos, d.tasas)
        for c in datos["agenda"]["clientes"][:20]:
            v = variables_al_corte(h.get(c["cliente_id"], []), date(2026, 10, 31))
            self.assertEqual(c["prob_compra_30d"], round(art.probabilidad(v), 6))  # probabilidad real, no un rango


if __name__ == "__main__":
    unittest.main()
