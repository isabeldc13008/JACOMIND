"""Pruebas de M1.1: variables de ciclo, ausencia de fuga, artefactos de boosting, calibración e integración."""
import contextlib
import copy
import csv
import importlib.util
import io
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None
PRODUCTOS = {"P1": {"familia_prueba": "Software", "tipo_prueba": "Recurrente", "vigencia_meses": 12},
             "P2": {"familia_prueba": "Servicios", "tipo_prueba": "Único", "vigencia_meses": 0}}


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _v(cid, fecha, vid, producto="P1"):
    return {"venta_id": vid, "cliente_id": cid, "producto_id": producto, "fecha": fecha, "cantidad": 1, "moneda": "COP",
            "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "estado": "Confirmada"}


def _hist(ventas):
    from modelos.variables import historial_compras
    return historial_compras(ventas, PRODUCTOS, {})


class VariablesCicloTests(unittest.TestCase):
    corte = date(2026, 6, 30)

    def var(self, ventas):
        from modelos.variables import variables_ciclo_al_corte
        return variables_ciclo_al_corte(_hist(ventas).get("C1", []), self.corte)

    def test_ciclo_calculado_con_historia_suficiente(self):
        v = self.var([_v("C1", date(2026, 3, 1), "a"), _v("C1", date(2026, 4, 1), "b"), _v("C1", date(2026, 5, 1), "c"),
                      _v("C1", date(2026, 6, 10), "d")])
        self.assertEqual(v["intervalo_mediano_dias"], 31.0)
        self.assertAlmostEqual(v["ratio_recencia_ciclo"], 20 / 31)
        self.assertEqual(v["desfase_ciclo_dias"], 20 - 31)
        self.assertEqual((v["ciclo_insuficiente"], v["cambio_insuficiente"]), (0, 0))
        self.assertAlmostEqual(v["cambio_intervalo_rel"], math.log((40 + 1) / (30.5 + 1)))  # mediana de los intervalos previos [31, 30]

    def test_historia_insuficiente_no_inventa_ciclos(self):
        v = self.var([_v("C1", date(2026, 5, 1), "a"), _v("C1", date(2026, 6, 1), "b")])  # un solo intervalo
        self.assertIsNone(v["ratio_recencia_ciclo"])
        self.assertIsNone(v["desfase_ciclo_dias"])
        self.assertIsNone(v["cv_intervalos"])
        self.assertIsNone(v["cambio_intervalo_rel"])
        self.assertEqual((v["ciclo_insuficiente"], v["cambio_insuficiente"]), (1, 1))
        self.assertIsNone(self.var([]))  # sin compras: sin fila de variables

    def test_mismo_dia_y_operaciones_por_dia(self):
        dia = date(2026, 6, 1)
        v = self.var([_v("C1", dia, "a"), _v("C1", dia, "b"), _v("C1", dia, "c")])
        self.assertEqual((v["historial_n"], v["dias_compra_distintos"], v["operaciones_por_dia"]), (3, 1, 3.0))
        self.assertIsNone(v["ratio_recencia_ciclo"])  # sin intervalos: no hay división por cero

    def test_eventos_posteriores_al_corte_no_cambian_variables(self):
        from modelos.variables import TODAS_V2
        base = [_v("C1", date(2026, 3, 1), "a"), _v("C1", date(2026, 4, 1), "b"), _v("C1", date(2026, 5, 15), "c")]
        a = self.var(base)
        b = self.var(base + [_v("C1", date(2026, 7, 1), "f"), _v("C1", date(2026, 6, 30) .replace(day=30), "g", "P2")][:1])
        self.assertEqual({k: a[k] for k in TODAS_V2}, {k: b[k] for k in TODAS_V2})

    def test_entrenamiento_e_inferencia_construyen_las_mismas_variables(self):
        from modelos.inferencia import desde_dict, predicciones_corte
        from modelos.variables import TODAS_V2, VERSION_VARIABLES_V2, construir_fotografias, variables_para
        ventas = [_v("C1", date(2026, 3, 1), "a"), _v("C1", date(2026, 4, 1), "b"), _v("C1", date(2026, 5, 15), "c")]
        h = _hist(ventas)
        foto = construir_fotografias([{"cliente_id": "C1", "fecha_alta": date(2025, 1, 1)}], h, [self.corte], date(2026, 10, 31),
                                     version=VERSION_VARIABLES_V2)[0]
        directo = variables_para(VERSION_VARIABLES_V2, h["C1"], self.corte)
        self.assertEqual({k: foto[k] for k in TODAS_V2}, directo)
        art = desde_dict(_artefacto_v2(disponible_desde="2026-01-01"))
        p = predicciones_corte(art, None, [{"cliente_id": "C1", "fecha_alta": date(2025, 1, 1)}], h, self.corte)[0]
        self.assertEqual(p["probabilidad"], round(art.probabilidad(directo), 6))


def _artefacto_v2(**cambios):
    from modelos.inferencia import FORMATO, sellar
    d = {"formato": FORMATO, "modelo_id": "compra_30d", "version": "fixture-v2", "version_variables": "compra_30d-variables-v2",
         "horizonte_dias": 30, "variables": ["recencia_dias", "ratio_recencia_ciclo", "ciclo_insuficiente"],
         "transformaciones": [{"variable": "recencia_dias", "funcion": "log1p", "imputacion": 3.0, "media": 3.0, "desviacion": 1.0},
                              {"variable": "ratio_recencia_ciclo", "funcion": "log1p", "imputacion": 0.7, "media": 0.7, "desviacion": 0.4},
                              {"variable": "ciclo_insuficiente", "funcion": "identidad", "imputacion": 0.0, "media": 0.3, "desviacion": 0.5}],
         "intercepto": 0.1, "pesos": [-0.3, -0.2, 0.1], "umbral": 0.4, "disponible_desde": "2026-10-30"}
    d.update(cambios)
    return sellar(d)


def _boosting(**cambios):
    from modelos.inferencia import FORMATO_BOOSTING, sellar
    d = {"formato": FORMATO_BOOSTING, "modelo_id": "compra_30d", "version": "fixture-gb", "version_variables": "compra_30d-variables-v2",
         "horizonte_dias": 30, "variables": ["recencia_dias", "frecuencia_90d"],
         "transformaciones": [{"variable": "recencia_dias", "funcion": "log1p", "imputacion": 3.0, "media": 3.0, "desviacion": 1.0},
                              {"variable": "frecuencia_90d", "funcion": "identidad", "imputacion": 1.0, "media": 1.0, "desviacion": 1.0}],
         "puntaje_inicial": -0.1, "tasa_aprendizaje": 0.1,
         "arboles": [{"nodos": [{"izq": 1, "der": 2, "variable": 0, "umbral": 0.0, "valor": 0.0},
                                {"izq": -1, "der": -1, "variable": -1, "umbral": 0.0, "valor": 0.8},
                                {"izq": -1, "der": -1, "variable": -1, "umbral": 0.0, "valor": -0.6}]}],
         "umbral": 0.4, "disponible_desde": "2026-10-30"}
    d.update(cambios)
    return sellar(d)


class ArtefactoBoostingTests(unittest.TestCase):
    def test_inferencia_y_rechazos_estructurales(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict, huella_artefacto
        a = desde_dict(_boosting())
        cerca, lejos = {"recencia_dias": 2, "frecuencia_90d": 1}, {"recencia_dias": 200, "frecuencia_90d": 1}
        self.assertAlmostEqual(a.puntaje_bruto(cerca), -0.1 + 0.1 * 0.8)
        self.assertAlmostEqual(a.puntaje_bruto(lejos), -0.1 - 0.1 * 0.6)
        base = _boosting()

        def mal(mutar):
            d = copy.deepcopy(base)
            mutar(d)
            d["huella"] = huella_artefacto(d)
            return d
        casos = {"ciclo": lambda d: d["arboles"][0]["nodos"][0].update(izq=0),
                 "fuera_de_rango": lambda d: d["arboles"][0]["nodos"][0].update(der=7),
                 "variable": lambda d: d["arboles"][0]["nodos"][0].update(variable=5),
                 "hoja_nan": lambda d: d["arboles"][0]["nodos"][1].update(valor=float("nan")),
                 "umbral_inf": lambda d: d["arboles"][0]["nodos"][0].update(umbral=float("inf")),
                 "sin_arboles": lambda d: d.update(arboles=[]),
                 "tasa": lambda d: d.update(tasa_aprendizaje=0),
                 "calibracion_invierte": lambda d: d.update(calibracion={"tipo": "sigmoide", "a": -1.0, "b": 0.0}),
                 "variables_de_otra_version": lambda d: d.update(version_variables="compra_30d-variables-v1",
                                                                  variables=["recencia_dias", "ratio_recencia_ciclo"])}
        for nombre, mutar in casos.items():
            with self.subTest(nombre), self.assertRaises(ArtefactoInvalido):
                desde_dict(mal(mutar))
        profundo = [{"izq": i + 1, "der": i + 2, "variable": 0, "umbral": float(i), "valor": 0.0} for i in range(0, 14, 2)]
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(mal(lambda d: d["arboles"][0].update(nodos=profundo)))
        alterado = copy.deepcopy(base)
        alterado["arboles"][0]["nodos"][1]["valor"] = 5.0  # sin recalcular huella
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(alterado)

    def test_calibracion_conserva_el_orden(self):
        from modelos.inferencia import desde_dict
        sin = desde_dict(_artefacto_v2())
        con = desde_dict(_artefacto_v2(calibracion={"tipo": "sigmoide", "a": 0.7, "b": -0.4}))
        filas = [{"recencia_dias": r, "ratio_recencia_ciclo": q, "ciclo_insuficiente": i}
                 for r, q, i in [(1, 0.1, 0), (30, 1.0, 0), (90, None, 1), (5, 2.0, 0), (200, None, 1)]]
        orden = lambda art: sorted(range(len(filas)), key=lambda k: -art.probabilidad(filas[k]))  # noqa: E731
        self.assertEqual(orden(sin), orden(con))
        self.assertNotEqual([sin.probabilidad(f) for f in filas], [con.probabilidad(f) for f in filas])

    def test_artefactos_historicos_conservan_huella_y_prediccion(self):
        from modelos.inferencia import cargar_artefacto
        v1 = RAIZ / "var" / "modelos" / "compra_30d" / "v1"
        if not v1.exists():
            self.skipTest("Sin registro local")
        art = cargar_artefacto(v1)
        self.assertEqual(art.huella, "b6c3d4a83ad8d1fd26c820282d4b2aa4aa1295edbceebf72cce649c7aca81cfe")
        self.assertEqual(art.version_variables, "compra_30d-variables-v1")


@unittest.skipIf(not HAY_SKLEARN, "requiere requirements-modelos.txt")
class EquivalenciaSklearnTests(unittest.TestCase):
    def test_gradient_boosting_exportado_equivale_a_sklearn(self):
        import random
        from modelos.compra_m11 import ajustar, _artefacto_temporal
        rng = random.Random(7)
        filas = []
        for i in range(400):
            rec = rng.randint(0, 300)
            filas.append({"cliente_id": f"C{i}", "recencia_dias": rec, "frecuencia_90d": rng.randint(0, 6),
                          "ratio_recencia_ciclo": None if i % 5 == 0 else rng.random() * 3, "ciclo_insuficiente": int(i % 5 == 0),
                          "compra_30d": int(rng.random() < (0.7 if rec < 40 else 0.3))})
        config = json.loads((RAIZ / "modelos" / "config" / "compra_30d_m11.json").read_text(encoding="utf-8"))
        spec = {"id": "gb-prueba", "familia": "boosting", "variables": ["recencia_dias", "frecuencia_90d", "ratio_recencia_ciclo",
                                                                       "ciclo_insuficiente"],
                "max_depth": 3, "n_estimators": 40, "learning_rate": 0.1, "min_samples_leaf": 10, "complejidad": 1}
        partes, predecir = ajustar(spec, filas, config)
        art = _artefacto_temporal(spec, partes)
        dif = max(abs(a - art.probabilidad(f)) for a, f in zip(predecir(filas), filas))
        self.assertLessEqual(dif, 1e-9)
        # Inferencia con scikit-learn y numpy bloqueados.
        with mock.patch.dict(sys.modules, {"sklearn": None, "numpy": None}):
            from modelos.inferencia import desde_dict
            self.assertEqual(desde_dict(art.datos).probabilidad(filas[0]), art.probabilidad(filas[0]))


class ValidacionTemporalTests(unittest.TestCase):
    def test_cortes_de_entrenamiento_respetan_la_madurez(self):
        from modelos.compra_m11 import cortes_entrenamiento
        from modelos.variables import cortes_mensuales
        cortes = cortes_mensuales(date(2025, 3, 31), date(2026, 6, 30))
        for d in cortes[6:]:
            usados = cortes_entrenamiento(cortes, d, 30)
            self.assertTrue(all((d - t).days >= 30 for t in usados), d)
        # Febrero: la etiqueta del 31-01 madura el 02-03, después del 28-02; no puede entrenar ese origen.
        self.assertNotIn(date(2026, 1, 31), cortes_entrenamiento(cortes, date(2026, 2, 28), 30))
        self.assertIn(date(2025, 12, 31), cortes_entrenamiento(cortes, date(2026, 2, 28), 30))


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ExperimentoM11Tests(unittest.TestCase):
    """Protocolo reducido (versión de prueba) para verificar el flujo completo sin fuga."""

    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_datos_config
        from modelos.compra_m11 import CONFIG_M11, entrenar_m11
        from modelos.datos import preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m11-"))
        c = json.loads(CONFIG_M11.read_text(encoding="utf-8"))
        c["version_protocolo"] = "m1.1-protocolo-prueba"
        c["combinaciones"] = {"base_ciclo": c["combinaciones"]["base_ciclo"]}
        c["familias"]["logistica"]["C"] = [1]
        c["familias"]["boosting"].update(n_estimators=[20], min_samples_leaf=[20])
        cls.config = c
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos_config(cls.tmp / "a01", c)
        cls.r = entrenar_m11(cls.datos, c, cls.tmp / "exp" / "e1")
        # Copia del paquete con ventas solo después del 30-07-2026 (periodo de comprobación).
        copia = cls.tmp / "paquete-mod"
        shutil.copytree(_paquete() / "01_Datos", copia / "01_Datos")
        with (copia / "01_Datos" / "ventas.csv").open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([["VEN91001", "2026-08-12", "CLI001", "PRO01", "3", "COP", "5000000", "0", "Confirmada", "Prueba"],
                                     ["VEN91002", "2026-09-03", "CLI010", "PRO02", "1", "COP", "100000", "0", "Confirmada", "Prueba"]])
        preparar_lote(copia, cls.tmp / "a01-mod")
        cls.r_mod = entrenar_m11(cargar_datos_config(cls.tmp / "a01-mod", c, observado_hasta="2026-10-31"), c, cls.tmp / "exp" / "e2")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sin_fuga_y_comprobacion_reservada(self):
        cong = self.r["congelacion"]
        self.assertEqual(cong["bloques_usados"], ["desarrollo"])
        self.assertTrue(all(date.fromisoformat(c) <= date(2026, 6, 30) for c in cong["cortes_entrenamiento_final"]))
        for sid, v in self.r["seleccion"]["validacion_temporal"].items():
            for o in v["por_origen"]:
                d = date.fromisoformat(o["origen"])
                self.assertLessEqual(d, date(2026, 6, 30))
        # Cambiar solo ventas del periodo de comprobación no cambia ningún artefacto, selección ni calibración.
        for papel in ("global", "mejor_boosting", "control"):
            a, b = self.r["artefactos"][papel], self.r_mod["artefactos"][papel]
            for v in ("sin_calibrar", "calibrado"):
                if v in a:
                    ka = {k: a[v][k] for k in a[v] if k not in ("entrenamiento", "huella", "version")}
                    kb = {k: b[v][k] for k in b[v] if k not in ("entrenamiento", "huella", "version")}
                    self.assertEqual(ka, kb, (papel, v))
        self.assertEqual(self.r["seleccion"]["global"], self.r_mod["seleccion"]["global"])

    def test_calibracion_solo_con_predicciones_fuera_de_muestra_y_soporte(self):
        for sid, c in self.r["seleccion"]["calibracion"].items():
            for o in c["origenes_evaluados"]:
                if o["soporte"]:
                    self.assertGreaterEqual(o["filas_calibrador"], self.config["calibracion"]["soporte_minimo"]["filas"])
            self.assertIn(c["motivo"], ("mejora el log loss fuera de muestra en desarrollo", "no mejora el log loss en desarrollo",
                                        "sin soporte suficiente"))
            if "calibrado" in self.r["artefactos"]["global"]:
                cal = self.r["artefactos"]["global"]["calibrado"]["calibracion"]
                self.assertTrue(all(o <= "2026-06-30" for o in cal["ajustada_con"]["origenes"]))

    def test_equivalencia_y_evaluacion_sin_reajuste_ni_promocion(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m11 import evaluar_m11
        for sid, e in self.r["congelacion"]["equivalencia_json_sklearn"].items():
            self.assertLessEqual(max(v for k, v in e.items() if k.startswith("diferencia")), 1e-9, sid)
        registro_real = RAIZ / "var" / "modelos" / "compra_30d" / "registro.json"
        antes = registro_real.read_bytes() if registro_real.exists() else None
        with mock.patch("modelos.compra_m11.ajustar", side_effect=AssertionError("evaluar no debe ajustar")):
            r = evaluar_m11(self.tmp / "exp" / "e1", self.datos)
        self.assertIn(r["decision"]["decision"], ("favorable", "inconcluso", "rechazado"))
        self.assertIn(r["decision"]["estado_maximo"], ("sombra", "ninguno"))
        res = r["metricas"]["resultados"]
        self.assertEqual([m["top10"]["aciertos"] for m in res["recencia"]["elegible"]["ranking"]["por_mes"]], [5, 7, 5])
        self.assertEqual([m["top10"]["aciertos"] for m in res["m1_v2_congelado"]["elegible"]["ranking"]["por_mes"]], [5, 7, 5])
        self.assertEqual([m["top10"]["aciertos"] for m in res["v1_congelada"]["elegible"]["ranking"]["por_mes"]], [5, 4, 4])
        if antes is not None:
            self.assertEqual(registro_real.read_bytes(), antes)  # ningún candidato se promueve
        cfg = json.loads((self.tmp / "exp" / "e1" / "config.json").read_text(encoding="utf-8"))
        cfg["metas"]["mejora_minima_precision_top10"] = 0
        d = self.tmp / "alterado"
        shutil.copytree(self.tmp / "exp" / "e1", d)
        (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            evaluar_m11(d, self.datos)

    def test_cierre_puntua_un_boosting_sin_scikit_learn(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        art = desde_dict(self.r["artefactos"]["mejor_boosting"]["sin_calibrar"])
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
                  f"m = generar(r'{_paquete()}', '2026-10-31', r'{self.tmp / 'cierre-gb'}', registro=r'{reg}')\n"
                  "r, d = validar_publicacion(r'" + str(self.tmp / 'cierre-gb') + "')\n"
                  "assert r.valido, r.errores\n"
                  "assert d['agenda']['modelo']['version'] == m['versiones']['modelo_compra']\n"
                  "assert sum(p['estado'] == 'estimado' for p in d['predicciones_clientes']) == 120\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


if __name__ == "__main__":
    unittest.main()
