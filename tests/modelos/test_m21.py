"""M2.1 · inactividad a 60 días con candidatos estructurales: variables v2, fórmulas, artefactos, protocolo e integridad."""
import copy
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None
C = date(2026, 7, 31)


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _c(fecha):
    return {"venta_id": "V", "fecha": fecha, "importe_cop": 100.0, "familia": "F", "recurrente": False, "vigencia_meses": 0}


def _huellas(base: Path):
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()} if base.exists() else {}


class VariablesV2Tests(unittest.TestCase):
    def v(self, compras, alta=date(2025, 1, 1), inst=()):
        from modelos.inactividad_m21 import variables_inactividad_v2
        return variables_inactividad_v2(compras, C, alta, inst)

    def test_ventana_exposicion_y_compras_esperadas(self):
        v = self.v([_c(C - timedelta(days=100)), _c(C - timedelta(days=40))])
        self.assertEqual((v["recencia_dias"], v["ventana_restante_dias"], v["exposicion_180d"]), (40, 50, 180))
        self.assertAlmostEqual(v["compras_esperadas_ventana"], 2 / 180 * 50)
        self.assertEqual(v["intervalos_dias"], [60])
        nuevo = self.v([_c(C - timedelta(days=35))], alta=C - timedelta(days=59))
        self.assertEqual(nuevo["exposicion_180d"], 60)  # alta reciente: exposición = días desde el alta, inclusive

    def test_venta_futura_no_cambia_las_variables(self):
        base = [_c(C - timedelta(days=50))]
        self.assertEqual(self.v(base), self.v(base + [_c(C + timedelta(days=1))]))

    def test_instalaciones_supuesto_y_frontera_de_renovacion(self):
        compras = [_c(C - timedelta(days=50))]  # w = 40 → la renovación debe abrirse a más tardar el día C + 40
        justo = {"fecha_inicio": C - timedelta(days=10), "fecha_fin": C + timedelta(days=40 + 45)}
        tarde = {"fecha_inicio": C - timedelta(days=10), "fecha_fin": C + timedelta(days=40 + 46)}
        futura = {"fecha_inicio": C + timedelta(days=1), "fecha_fin": C + timedelta(days=50)}  # aún no conocida
        vencida = {"fecha_inicio": C - timedelta(days=300), "fecha_fin": C}  # fin == corte: no vigente
        self.assertEqual(self.v(compras, inst=[justo])["renovacion_antes_del_cruce"], 1)
        self.assertEqual(self.v(compras, inst=[tarde])["renovacion_antes_del_cruce"], 0)
        r = self.v(compras, inst=[futura, vencida])
        self.assertEqual((r["instalaciones_vigentes"], r["renovacion_antes_del_cruce"]), (0, 0))


class FormulasTests(unittest.TestCase):
    def test_poisson_formula_y_orden_por_ventana(self):
        from modelos.inactividad_m21 import prob_poisson
        f = {"dias_compra_180d": 3, "exposicion_180d": 180, "ventana_restante_dias": 20}
        lam = (3 + 90 * 0.02) / (180 + 90)
        self.assertAlmostEqual(prob_poisson(f, 0.02, 90), math.exp(-lam * 20))
        self.assertGreater(prob_poisson(dict(f, ventana_restante_dias=5), 0.02, 90), prob_poisson(f, 0.02, 90))
        self.assertGreater(prob_poisson(dict(f, dias_compra_180d=1), 0.02, 90), prob_poisson(f, 0.02, 90))

    def test_supervivencia_intervalo_exacto_de_90_no_es_evento(self):
        from modelos.inactividad_m21 import prob_supervivencia
        curva = {"tiempos": [10, 200], "supervivencia": [0.5, 0.25], "cola_tasa_diaria": 0.01}
        # Solo intervalos propios (k muy pequeño): un intervalo de 90 exactos evita el cruce (compra el día 90).
        self.assertLess(prob_supervivencia({"recencia_dias": 50, "intervalos_dias": [90, 90]}, curva, 1e-9), 1e-3)
        self.assertGreater(prob_supervivencia({"recencia_dias": 50, "intervalos_dias": [91, 91]}, curva, 1e-9), 0.999)
        # Sin intervalos propios: la curva poblacional S(90)/S(50) = 0.5/0.5.
        self.assertAlmostEqual(prob_supervivencia({"recencia_dias": 50, "intervalos_dias": []}, curva, 3), 1.0 - 1e-6)


class ArtefactoTests(unittest.TestCase):
    def poisson(self, **cambios):
        from modelos.inferencia import sellar
        d = {"formato": "jacomind.inactividad_poisson.v1", "modelo_id": "inactividad_60d", "version": "t",
             "version_variables": "inactividad_60d-variables-v2", "horizonte_dias": 60, "umbral_frio_dias": 90, "umbral": None,
             "tasa_poblacional_diaria": 0.02, "contraccion_dias": 90.0, "disponible_desde": "2026-10-31"}
        return sellar(d | cambios)

    def test_valido_alterado_y_otros_modelos(self):
        from modelos.inferencia import ArtefactoInvalido, cargar_artefacto, desde_dict
        art = desde_dict(self.poisson())
        self.assertIsNone(art.umbral)
        alterado = dict(self.poisson(), contraccion_dias=1.0)
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(alterado)
        for cambio in ({"horizonte_dias": 30}, {"umbral_frio_dias": 120}, {"version_variables": "inactividad_60d-variables-v1"},
                       {"umbral": 0.5}, {"modelo_id": "compra_30d"}, {"tasa_poblacional_diaria": 0}):
            with self.subTest(cambio=cambio), self.assertRaises(ArtefactoInvalido):
                self.poisson(**cambio)
        tmp = Path(tempfile.mkdtemp(prefix="m21a-"))
        try:
            (tmp / "a.json").write_text(json.dumps(self.poisson()), encoding="utf-8")
            with self.assertRaises(ArtefactoInvalido):
                cargar_artefacto(tmp / "a.json", modelo_id="compra_30d")
            from modelos.compra import puntuar  # noqa: F401 - puntuar de compra rechaza artefactos de otro modelo
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_puntuacion_sin_librerias_de_entrenamiento(self):
        codigo = ("import sys, json\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "from modelos.inferencia import desde_dict\n"
                  "import modelos.inactividad, modelos.inactividad_m21\n"
                  f"a = desde_dict(json.loads({json.dumps(json.dumps(self.poisson()))}))\n"
                  "print(a.probabilidad({'dias_compra_180d': 2, 'exposicion_180d': 180, 'ventana_restante_dias': 30}))\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ExperimentoM21Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.inactividad_m21_experimento import cargar_config, entrenar
        cls.registro_antes = _huellas(RAIZ / "var" / "modelos")
        cls.m2_antes = _huellas(RAIZ / "salida" / "experimentos" / "inactividad_60d")
        cls.tmp = Path(tempfile.mkdtemp(prefix="m21-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cls.config = cargar_config()
        cls.r = entrenar(cls.datos, cls.config, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_mismas_fronteras_y_poblacion_que_m2(self):
        self.assertEqual(self.r["fronteras"]["ajuste->validacion"]["ultima_etiqueta_madura"], "2026-04-29")
        self.assertEqual(self.r["fronteras"]["validacion->comprobacion_historica"]["primera_inferencia"], "2026-07-31")
        self.assertEqual({b: c["aprendibles_maduras"] for b, c in self.r["conteos"].items()},
                         {"ajuste": 309, "validacion": 107, "comprobacion_historica": 69})

    def test_doce_candidatos_predeclarados_y_artefacto_principal(self):
        from modelos.inferencia import cargar_artefacto
        sel = self.r["seleccion"]
        self.assertEqual(len(sel["candidatos"]), 12)
        self.assertEqual({c["familia"] for c in sel["candidatos"].values()},
                         {"poisson", "supervivencia", "logistica_reducida", "logistica_instalaciones"})
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="inactividad_60d")
        self.assertEqual(art.huella, cargar_artefacto(self.tmp / "e1" / "candidatos" / f"{sel['elegido']}.json").huella)
        self.assertTrue(all(c["equivalencia_json_sklearn"]["diferencia_maxima"] <= 1e-9
                            for c in sel["candidatos"].values() if c["equivalencia_json_sklearn"]))
        cur = json.loads((self.tmp / "e1" / "candidatos" / "supervivencia-1.json").read_text(encoding="utf-8"))["curva"]
        self.assertEqual(cur["datos_hasta"], "2026-02-28")  # la curva solo usa información del bloque de ajuste

    def test_reproducible_en_otra_carpeta(self):
        from modelos.inactividad_m21_experimento import entrenar
        r2 = entrenar(self.datos, self.config, self.tmp / "e2")
        self.assertEqual(r2["congelacion"]["sello"], self.r["congelacion"]["sello"])

    def test_evaluacion_idempotente_rechazos_y_sombra(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.compra import ProtocoloError
        from modelos.ejecucion import EjecucionError
        from modelos.inactividad import puntuar_sombra
        from modelos.inactividad_m21_experimento import entrenar, evaluar, verificar_congelacion
        from modelos.inferencia import cargar_artefacto
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        a = evaluar(d, self.datos)
        b = evaluar(d, self.datos)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        self.assertIn(a["decision"]["decision"], ("favorable", "inconcluso", "rechazado"))
        self.assertIn("REUTILIZADA", a["metricas"]["alcance"])
        # evidencia alterada
        x = self.tmp / "alterada"
        shutil.copytree(self.tmp / "e1", x)
        sel = json.loads((x / "seleccion.json").read_text(encoding="utf-8"))
        sel["elegido"] = sel["orden"][-1]
        (x / "seleccion.json").write_text(json.dumps(sel), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            verificar_congelacion(x)
        # otra configuración en la misma carpeta
        otra = copy.deepcopy(self.config)
        otra["familias"]["poisson"]["valores"] = [60]
        with self.assertRaises(EjecucionError):
            entrenar(self.datos, otra, self.tmp / "e1")
        # sombra con variables v2 (instalaciones y alta) y contrato C2
        art = cargar_artefacto(d / "artefacto.json", modelo_id="inactividad_60d")
        out = self.tmp / "sombra"
        r1 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        r2 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        self.assertEqual(r1["manifiesto"]["sello"], r2["manifiesto"]["sello"])
        errores, man, filas = leer_publicacion_sombra(out)
        self.assertEqual(errores, [])
        self.assertEqual(sum(f["estado"] == "estimado" for f in filas), man["conteos"]["aprendible"])

    def test_no_toca_registro_ni_ejecuciones_m2(self):
        self.assertEqual(_huellas(RAIZ / "var" / "modelos"), self.registro_antes)
        self.assertEqual(_huellas(RAIZ / "salida" / "experimentos" / "inactividad_60d"), self.m2_antes)
        self.assertFalse((RAIZ / "var" / "modelos" / "inactividad_60d").exists())


if __name__ == "__main__":
    unittest.main()
