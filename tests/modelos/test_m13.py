"""Pruebas de M1.3: supervivencia (S) y ponderación temporal + nivel (P)."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _v(cid, fecha, vid):
    return {"venta_id": vid, "cliente_id": cid, "producto_id": "P1", "fecha": fecha, "cantidad": 1, "moneda": "COP",
            "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "estado": "Confirmada"}


def _artefacto_s(**cambios):
    from modelos.inferencia import sellar
    d = {"formato": "jacomind.supervivencia.v1", "modelo_id": "compra_30d", "version": "fixture-S",
         "version_variables": "compra_30d-intervalos-v1", "horizonte_dias": 30,
         "curva": {"tiempos": [10, 20, 40], "supervivencia": [0.8, 0.4, 0.2], "cola_tasa_diaria": 0.04},
         "k_contraccion": 5, "umbral": 0.4, "disponible_desde": "2026-01-01"}
    d.update(cambios)
    return sellar(d)


class SupervivenciaTests(unittest.TestCase):
    def test_kaplan_meier_con_censura_y_cola(self):
        from modelos.supervivencia import kaplan_meier, tasa_cola
        t, s = kaplan_meier([10, 20, 20, 40], [15, 50])
        self.assertEqual(t, [10, 20, 40])
        for a, b in zip(s, [5 / 6, 5 / 6 * 0.5, 5 / 6 * 0.5 * 0.5]):
            self.assertAlmostEqual(a, b)
        self.assertGreater(tasa_cola(t, s), 0)

    def test_probabilidad_contraccion_y_historia_insuficiente(self):
        from modelos.supervivencia import probabilidad
        curva = {"tiempos": [10, 20, 40], "supervivencia": [0.8, 0.4, 0.2], "cola_tasa_diaria": 0.04}
        pob = probabilidad(5, [], curva, 5)  # sin intervalos propios: solo población
        self.assertAlmostEqual(pob, 1 - 0.4 / 1.0)
        regular = probabilidad(5, [30, 30, 30, 30, 30], curva, 5)  # cliente de ciclo 30: debería comprar en 30 días
        self.assertGreater(regular, pob)
        lejos = probabilidad(1000, [], curva, 5)  # más allá de la curva: cola exponencial, no 0 ni 1
        self.assertGreater(lejos, 0.0)
        self.assertLess(lejos, 1.0)

    def test_curva_solo_usa_informacion_hasta_la_fecha(self):
        from modelos.supervivencia import ajustar_curva
        from modelos.variables import historial_compras
        prod = {"P1": {"familia_prueba": "S", "tipo_prueba": "Recurrente", "vigencia_meses": 12}}
        clientes = [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "B", "fecha_alta": date(2025, 1, 1)}]
        base = [_v("A", date(2026, 1, 1), "1"), _v("A", date(2026, 2, 1), "2"), _v("B", date(2026, 1, 15), "3")]
        futura = base + [_v("B", date(2026, 7, 1), "4"), _v("A", date(2026, 6, 15), "5")]
        c1 = ajustar_curva(historial_compras(base, prod, {}), clientes, date(2026, 5, 31))
        c2 = ajustar_curva(historial_compras(futura, prod, {}), clientes, date(2026, 5, 31))
        self.assertEqual(c1, c2)

    def test_artefacto_validacion_y_recarga(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict, huella_artefacto
        a = desde_dict(_artefacto_s())
        f = {"recencia_dias": 5, "intervalos_dias": [30, 31]}
        self.assertEqual(desde_dict(json.loads(json.dumps(a.datos))).probabilidad(f), a.probabilidad(f))
        malos = {"no_monotona": {"curva": {"tiempos": [10, 20], "supervivencia": [0.4, 0.8], "cola_tasa_diaria": 0.04}},
                 "tiempos_desordenados": {"curva": {"tiempos": [20, 10], "supervivencia": [0.8, 0.4], "cola_tasa_diaria": 0.04}},
                 "nan": {"curva": {"tiempos": [10], "supervivencia": [float("nan")], "cola_tasa_diaria": 0.04}},
                 "cola_cero": {"curva": {"tiempos": [10], "supervivencia": [0.5], "cola_tasa_diaria": 0}},
                 "k": {"k_contraccion": 0}, "version_variables": {"version_variables": "compra_30d-variables-v1"}}
        base = _artefacto_s()
        for nombre, cambio in malos.items():
            d = dict(copy.deepcopy(base), **cambio)
            d["huella"] = huella_artefacto(d)
            with self.subTest(nombre), self.assertRaises(ArtefactoInvalido):
                desde_dict(d)

    def test_inferencia_en_el_cierre_usa_intervalos_hasta_el_corte(self):
        from modelos.inferencia import desde_dict, predicciones_corte
        from modelos.variables import historial_compras
        prod = {"P1": {"familia_prueba": "S", "tipo_prueba": "Recurrente", "vigencia_meses": 12}}
        h = historial_compras([_v("A", date(2026, 3, 1), "1"), _v("A", date(2026, 4, 1), "2"), _v("A", date(2026, 7, 9), "3")], prod, {})
        art = desde_dict(_artefacto_s())
        p = predicciones_corte(art, None, [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}], h, date(2026, 6, 30))[0]
        self.assertEqual(p["probabilidad"], round(art.probabilidad({"recencia_dias": 90, "intervalos_dias": [31]}), 6))


class PonderacionTests(unittest.TestCase):
    def test_pesos_y_ajuste_de_nivel(self):
        from modelos.compra_m13 import _logit, ajuste_nivel, pesos_temporales
        filas = [{"corte": date(2026, 6, 30)}, {"corte": date(2025, 12, 31)}]
        w = pesos_temporales(filas, 180)
        self.assertEqual(w[0], 1.0)
        self.assertAlmostEqual(w[1], 0.5 ** (181 / 180))

        class Fijo:
            def probabilidad(self, f):
                return 0.6
        b = ajuste_nivel(Fijo(), [{"compra_30d": 1}, {"compra_30d": 0}, {"compra_30d": 0}, {"compra_30d": 0}])
        self.assertAlmostEqual(b, _logit(0.25) - _logit(0.6))


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ExperimentoM13Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_datos_config
        from modelos.compra_m13 import CONFIG_M13, entrenar_m13
        from modelos.datos import preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m13-"))
        cls.config = json.loads(CONFIG_M13.read_text(encoding="utf-8"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos_config(cls.tmp / "a01", cls.config)
        cls.r = entrenar_m13(cls.datos, cls.config, cls.tmp / "exp" / "e1")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sin_fuga_equivalencia_y_reproducible(self):
        from modelos.compra_m13 import entrenar_m13
        cong = self.r["congelacion"]
        self.assertTrue(all(c <= "2026-06-30" for c in cong["cortes_entrenamiento_final"]))
        self.assertEqual(cong["curva_S_datos_hasta"], "2026-07-31")
        self.assertEqual(self.r["artefactos"]["P"]["calibracion"]["corte_referencia"], "2026-06-30")
        self.assertTrue(all(v <= 1e-9 for v in cong["equivalencia"].values()))
        r2 = entrenar_m13(self.datos, self.config, self.tmp / "exp" / "e2")
        self.assertEqual({n: d["huella"] for n, d in r2["artefactos"].items()}, {n: d["huella"] for n, d in self.r["artefactos"].items()})

    def test_evaluacion_sin_reajuste_ni_promocion_y_protocolo_congelado(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m13 import evaluar_m13
        registro = RAIZ / "var" / "modelos" / "compra_30d" / "registro.json"
        antes = registro.read_bytes() if registro.exists() else None
        with mock.patch("modelos.compra_m13.modelos_logisticos", side_effect=AssertionError("no debe ajustar")), \
                mock.patch("modelos.compra_m13.ajustar_curva", side_effect=AssertionError("no debe ajustar")):
            r = evaluar_m13(self.tmp / "exp" / "e1", self.datos)
        self.assertEqual(set(r["decision"]["candidatos"]), {"S", "P"})
        self.assertEqual([m["top10"]["aciertos"] for m in r["metricas"]["resultados"]["recencia"]["elegible"]["por_mes"]], [5, 7, 5])
        if antes is not None:
            self.assertEqual(registro.read_bytes(), antes)
        d = self.tmp / "alterado"
        shutil.copytree(self.tmp / "exp" / "e1", d)
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        cfg["candidatos"]["S"]["k_contraccion"] = 1
        (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            evaluar_m13(d, self.datos)

    def test_cierre_publica_con_supervivencia_sin_scikit_learn(self):
        import subprocess
        import sys
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        art = desde_dict(self.r["artefactos"]["S"])
        reg = self.tmp / "registro-aislado"
        R.promover(reg, "compra_30d", "v9", art, {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": art.huella,
                                                   "origen_datos": "fixture_empresarial", "aprobado_por": "fixture"}, {}, "operativo")
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "from pipeline.generar import generar\n"
                  "from contratos.validar import validar_publicacion\n"
                  f"generar(r'{_paquete()}', '2026-10-31', r'{self.tmp / 'cierre-s'}', registro=r'{reg}')\n"
                  f"r, d = validar_publicacion(r'{self.tmp / 'cierre-s'}')\n"
                  "assert r.valido, r.errores\n"
                  "assert sum(p['estado'] == 'estimado' for p in d['predicciones_clientes']) == 120\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
