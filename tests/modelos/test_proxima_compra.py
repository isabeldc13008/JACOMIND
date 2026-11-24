"""M3 · próxima compra: seguimiento censurado, referencias, curvas, artefactos, métricas, integridad, contrato, API y
episodios. Incluye las regresiones de M2 para las correcciones compartidas (sombra, cupos, episodios, AP con empates)."""
import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))
HAY_SKSURV = importlib.util.find_spec("sksurv") is not None
C = date(2026, 4, 30)


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _c(fecha, vid="V"):
    return {"venta_id": vid, "fecha": fecha, "importe_cop": 100.0, "familia": "F", "recurrente": False, "vigencia_meses": 0}


def _huellas(base: Path):
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()} if base.exists() else {}


# ------------------------------------------------------------------------------------------ referencias y seguimiento
class ReferenciaTests(unittest.TestCase):
    def test_ejemplo_del_plan_y_vencida(self):
        from modelos.proxima_compra import referencia_personal
        self.assertEqual(referencia_personal([20, 30, 40], 10), {"estado": "disponible", "dias": 20, "mediana_intervalos": 30})
        self.assertEqual(referencia_personal([20, 30, 40], 30)["estado"], "vencida")  # 0 días: vencida, no "mañana"
        r = referencia_personal([20, 30, 40], 45)
        self.assertEqual((r["estado"], r["dias"]), ("vencida", -15))  # no se desplaza artificialmente
        self.assertEqual(referencia_personal([25], 5)["estado"], "insuficiente")  # una compra o un intervalo: sin mediana personal
        self.assertEqual(referencia_personal([], 5)["estado"], "insuficiente")


class SeguimientoTests(unittest.TestCase):
    def s(self, compras, corte=C, hasta=date(2026, 10, 31)):
        from modelos.proxima_compra import seguimiento
        return seguimiento(compras, corte, hasta)

    def test_compra_al_corte_y_mismo_dia(self):
        r = self.s([_c(C), _c(C, "V2"), _c(C + timedelta(days=5)), _c(C + timedelta(days=5), "V3")])
        self.assertEqual((r["evento"], r["duracion"]), (1, 5))  # la compra en C es historial; dos ventas del día 5 = un evento

    def test_evento_dia_60_y_censura(self):
        self.assertEqual(self.s([_c(C - timedelta(days=3)), _c(C + timedelta(days=60))])["evento"], 1)
        r = self.s([_c(C - timedelta(days=3)), _c(C + timedelta(days=61))])
        self.assertEqual((r["evento"], r["duracion"]), (0, 60))  # censura administrativa al día 60

    def test_seguimiento_cero_y_compra_posterior_a_D(self):
        self.assertIsNone(self.s([_c(C - timedelta(days=3))], hasta=C))
        r = self.s([_c(C - timedelta(days=3)), _c(C + timedelta(days=20))], hasta=C + timedelta(days=10))
        self.assertEqual((r["evento"], r["duracion"]), (0, 10))  # la compra del día 20 aún no se conocía en D

    def test_fotografias_conservan_censuras_y_no_cambian_con_ventas_posteriores_a_D(self):
        from modelos.proxima_compra import fotografias
        clientes = [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "B", "fecha_alta": date(2025, 1, 1)},
                    {"cliente_id": "N", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "F", "fecha_alta": date(2027, 1, 1)}]
        hist = {"A": [_c(date(2026, 1, 10)), _c(date(2026, 2, 10)), _c(date(2026, 3, 10))], "B": [_c(date(2026, 1, 5))]}
        D = date(2026, 4, 29)
        f1, ex = fotografias(clientes, hist, [date(2026, 2, 28)], D, date(2026, 10, 31))
        self.assertEqual({f["cliente_id"]: (f["evento"], f["duracion"]) for f in f1}, {"A": (1, 10), "B": (0, 60)})
        self.assertEqual(ex["2026-02-28"], {"alta_posterior": 1, "sin_historial": 1, "seguimiento_cero": 0})
        hist2 = copy.deepcopy(hist)
        hist2["B"].append(_c(D + timedelta(days=1)))  # venta conocida después de D
        f2, _ = fotografias(clientes, hist2, [date(2026, 2, 28)], D, date(2026, 10, 31))
        self.assertEqual(f1, f2)
        with self.assertRaises(ValueError):
            fotografias(clientes, hist, [date(2026, 2, 28)], date(2026, 11, 30), date(2026, 10, 31))


# ------------------------------------------------------------------------------------------ curvas y cuantiles
class CurvasTests(unittest.TestCase):
    def km(self, durs, evs):
        from modelos.inferencia import sellar
        from modelos.proxima_compra import kaplan_meier
        t, s = kaplan_meier(durs, evs)
        return sellar({"formato": "jacomind.supervivencia_residual.v1", "modelo_id": "proxima_compra", "version": "t", "tipo": "km",
                       "version_variables": "proxima_compra-variables-v1", "horizonte_dias": 60, "soporte_dias": max(durs), "umbral": None,
                       "km": {"tiempos": t, "supervivencia": s}, "ancho_maximo_ventana_dias": 30, "disponible_desde": "2026-10-31"})

    def test_curva_valida_y_cuantiles_no_alcanzados(self):
        from modelos.inferencia import desde_dict
        from modelos.proxima_compra import validar_curva, ventana
        art = desde_dict(self.km([5, 10, 60, 60, 60, 60], [1, 1, 0, 0, 0, 0]))  # S(60) = 4/6: p50 y p90 no se alcanzan
        curva = art.curva({})
        self.assertEqual(validar_curva(curva), [])
        self.assertEqual(curva[0], 1.0)
        w = ventana(curva, C)
        self.assertEqual((w["dias_p10"], w["dias_p50"], w["dias_p90"], w["fecha_p90"], w["ventana_utilizable"]), (5, None, None, None, False))
        self.assertIsNone(art.supervivencia({}, 61))  # sin extrapolación fuera del soporte
        sin_eventos = desde_dict(self.km([60, 60, 60], [0, 0, 0]))
        self.assertEqual(ventana(sin_eventos.curva({}), C)["dias_p10"], None)
        self.assertTrue(validar_curva([1.0, 0.9, 0.95]))  # crece: inválida
        self.assertTrue(validar_curva([0.9, 0.8]))         # S(0) != 1

    def test_artefacto_alterado_o_de_otro_modelo(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict
        d = self.km([5, 10, 60], [1, 1, 0])
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(dict(d, soporte_dias=59))
        for cambio in ({"modelo_id": "compra_30d"}, {"horizonte_dias": 30}, {"umbral": 0.5}):
            with self.subTest(cambio=cambio), self.assertRaises(ArtefactoInvalido):
                from modelos.inferencia import sellar
                sellar(dict(d, **cambio))


@unittest.skipUnless(HAY_SKSURV, "Requiere scikit-survival (entorno analítico)")
class ReferenciaBibliotecaTests(unittest.TestCase):
    def datos(self, n=300, semilla=3):
        import random
        rng = random.Random(semilla)
        filas = []
        for i in range(n):
            x = rng.random()
            t = min(60, max(1, int(rng.expovariate(0.02 + 0.05 * x))))
            filas.append({"cliente_id": f"C{i % 50}", "corte": C, "recencia_dias": int(x * 100), "dias_compra_90d": rng.randint(0, 5),
                          "dias_compra_180d": rng.randint(0, 9), "dias_compra_distintos": rng.randint(1, 20), "intervalo_mediano_dias": None if i % 7 == 0 else 10 + 50 * x,
                          "intervalo_dispersion_dias": 5.0, "historia_insuficiente": int(i % 7 == 0), "importe_cop_90d": 1000.0 * x,
                          "duracion": t, "evento": int(t < 60 and rng.random() > 0.1), "ref_personal_estado": "insuficiente", "ref_personal_dias": None, "grupo": "habitual"})
        return filas

    def test_km_ibs_y_equivalencia_cox_contra_scikit_survival(self):
        import numpy as np
        from sksurv.nonparametric import kaplan_meier_estimator
        from modelos.inferencia import desde_dict
        from modelos.proxima_compra import kaplan_meier
        from modelos.proxima_compra_experimento import (ajustar_cox, artefacto_cox, censura_ajuste, equivalencia, ibs, ibs_referencia,
                                                         matriz, rejilla)
        f = self.datos()
        t, s = kaplan_meier([x["duracion"] for x in f], [x["evento"] for x in f])
        tt, ss = kaplan_meier_estimator(np.array([bool(x["evento"]) for x in f]), np.array([float(x["duracion"]) for x in f]))
        ref = {int(a): b for a, b in zip(tt, ss)}
        self.assertTrue(all(abs(ref[a] - b) < 1e-12 for a, b in zip(t, s)))
        cfg = json.loads((RAIZ / "modelos/config/proxima_compra.json").read_text(encoding="utf-8"))
        aj, pr = f[:200], f[200:]

        class D:
            huella_datos, revision = "x" * 64, 1
        m, trans, avisos = ajustar_cox(aj, cfg["variables"], 1.0, cfg)
        art = desde_dict(json.loads(json.dumps(artefacto_cox(m, trans, cfg["variables"], 1.0, aj, cfg, D, avisos))))
        eq = equivalencia(m, trans, art, f)
        self.assertLess(eq["diferencia_maxima_supervivencia"], 1e-9)
        malla = rejilla(aj, pr, dict(cfg, rejilla_metrica={"minimo_puntos": 5}))
        S = matriz(art, pr, malla["puntos"])
        self.assertAlmostEqual(ibs(censura_ajuste(aj), pr, S, malla["puntos"]), ibs_referencia(aj, pr, S, malla["puntos"]), places=12)

    def test_soporte_insuficiente_y_ipcw_no_definido(self):
        from modelos.proxima_compra_experimento import brier_ipcw, rejilla
        cfg = json.loads((RAIZ / "modelos/config/proxima_compra.json").read_text(encoding="utf-8"))
        aj = [{"duracion": d, "evento": 1} for d in (3, 4, 5)] + [{"duracion": 6, "evento": 0}]
        pr = [{"duracion": 2, "evento": 1}, {"duracion": 5, "evento": 0}]
        self.assertFalse(rejilla(aj, pr, cfg)["estimable"])  # 4 puntos < 30: métrica no estimable
        G = ([6], [0.0])  # censura total en el día 6: G = 0
        self.assertEqual(brier_ipcw(G, [{"duracion": 7, "evento": 0}], [[0.5]], [6]), [float("inf")])


class MetricasRegresionTests(unittest.TestCase):
    def test_average_precision_con_empates_como_sklearn(self):
        from modelos.metricas import average_precision, average_precision_empates
        filas = [{"cliente_id": f"C{i}", "y": y, "p": p} for i, (y, p) in enumerate([(1, .9), (0, .5), (1, .5), (0, .5), (1, .2), (0, .1)])]
        sin_empates = [dict(f, p=f["p"] + i * 1e-6) for i, f in enumerate(filas)]
        if importlib.util.find_spec("sklearn"):
            from sklearn.metrics import average_precision_score
            self.assertAlmostEqual(average_precision_empates(filas, lambda f: f["p"], "y"),
                                   average_precision_score([f["y"] for f in filas], [f["p"] for f in filas]), places=12)
            self.assertAlmostEqual(average_precision(sin_empates, lambda f: f["p"], "y"),
                                   average_precision_score([f["y"] for f in sin_empates], [f["p"] for f in sin_empates]), places=12)
        # con empates, la versión histórica depende del desempate por cliente_id: se documenta, no se usa en M3
        self.assertNotAlmostEqual(average_precision(filas, lambda f: f["p"], "y"), average_precision_empates(filas, lambda f: f["p"], "y"))


# ------------------------------------------------------------------------------------------ contrato C2
def _fila(cid, modelo, **k):
    base = {"cliente_id": cid, "modelo_id": modelo, "probabilidad": None, "estado": "sin_historial", "horizonte_dias": 60,
            "version_modelo": "v", "corte": "2026-10-31", "datos_hasta": "2026-10-31", "motivos": ["m"]}
    if modelo == "proxima_compra":
        base |= {"dias_p10": None, "dias_p50": None, "dias_p90": None, "fecha_p10": None, "fecha_p50": None, "fecha_p90": None, "soporte_dias": 60,
                 "ancho_ventana_dias": None, "ventana_utilizable": False, "ancho_maximo_ventana_dias": 30, "origen_estimacion": None,
                 "referencia_personal_estado": None, "referencia_personal_dias": None, "recencia_dias": None}
    return base | k


class ContratoTests(unittest.TestCase):
    def errores(self, filas):
        from contratos.validar import validar_predicciones
        return validar_predicciones(filas, None, {"corte": "2026-10-31"})

    def test_cuantiles_fechas_nulos_y_ventana(self):
        ok = _fila("A", "proxima_compra", estado="estimado", origen_estimacion="poblacional_km", dias_p10=3, dias_p50=12, dias_p90=30,
                   fecha_p10="2026-11-03", fecha_p50="2026-11-12", fecha_p90="2026-11-30", ancho_ventana_dias=27, ventana_utilizable=True,
                   recencia_dias=20, referencia_personal_estado="vencida", referencia_personal_dias=-2)
        self.assertEqual(self.errores([ok]), [])
        parcial = dict(ok, estado="estimacion_parcial", dias_p90=None, fecha_p90=None, ancho_ventana_dias=None, ventana_utilizable=False)
        self.assertEqual(self.errores([parcial]), [])
        malos = [dict(ok, probabilidad=0.5), dict(ok, fecha_p50="2026-11-13"), dict(ok, dias_p50=40, fecha_p50="2026-12-10"),
                 dict(parcial, ventana_utilizable=True), dict(ok, dias_p90=61, fecha_p90="2026-12-31", ancho_ventana_dias=58, ventana_utilizable=False),
                 dict(parcial, dias_p50=None, fecha_p50=None, dias_p90=30, fecha_p90="2026-11-30", ancho_ventana_dias=27, ventana_utilizable=True),
                 dict(ok, estado="estimado", dias_p90=None, fecha_p90=None, ancho_ventana_dias=None, ventana_utilizable=False),
                 _fila("B", "proxima_compra", recencia_dias=4), dict(ok, referencia_personal_estado="disponible", referencia_personal_dias=-2)]
        for m in malos:
            with self.subTest(m=m):
                self.assertTrue(self.errores([m]))

    def test_coexisten_tres_objetivos_para_un_cliente(self):
        from contratos.validar import cargar_esquema, validar_tabla
        filas = [_fila("A", "compra_30d", estado="estimado", probabilidad=0.4, horizonte_dias=30),
                 _fila("A", "inactividad_60d", estado="estimado", probabilidad=0.3, umbral_frio_dias=90, recencia_dias=40),
                 _fila("A", "proxima_compra", estado="estimacion_parcial", origen_estimacion="poblacional_km", dias_p10=5, fecha_p10="2026-11-05", recencia_dias=40)]
        d = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]["predicciones_clientes"]
        self.assertEqual(validar_tabla("predicciones_clientes", filas, d, {"filas": 3}), [])
        self.assertEqual(self.errores(filas), [])
        self.assertTrue(validar_tabla("predicciones_clientes", filas + [filas[2]], d, {"filas": 4}))  # clave duplicada


# ------------------------------------------------------------------------------------------ experimento completo
@unittest.skipIf(_paquete() is None or not HAY_SKSURV, "Requiere el paquete y scikit-survival")
class ExperimentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.proxima_compra_experimento import cargar_config, entrenar
        cls.registro_antes = _huellas(RAIZ / "var" / "modelos")
        cls.ejecuciones_antes = _huellas(RAIZ / "salida" / "experimentos" / "inactividad_60d")
        cls.tmp = Path(tempfile.mkdtemp(prefix="m3-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cfg = cargar_config()
        cfg["candidato"]["estabilidad_bootstrap"] = 3       # rapidez en pruebas: otra configuración, otra carpeta
        cfg["metricas"]["bootstrap"]["repeticiones"] = 20
        cls.config = cfg
        cls.r = entrenar(cls.datos, cfg, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_fronteras_conteos_y_seleccion_ligada(self):
        from modelos.inferencia import cargar_artefacto
        fr = self.r["fronteras"]
        self.assertEqual(fr["ajuste->validacion"]["seguimiento_hasta"], "2026-04-29")
        self.assertLess(fr["validacion->comprobacion_historica"]["seguimiento_hasta"], fr["validacion->comprobacion_historica"]["primera_prediccion_siguiente"])
        aj = self.r["conteos"]["ajuste"]
        self.assertGreater(aj["censuras"], 0)  # los censurados permanecen
        self.assertEqual(aj["eventos"] + aj["censuras"], aj["filas"])
        sel = self.r["seleccion"]
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="proxima_compra")
        self.assertEqual(art.huella, cargar_artefacto(self.tmp / "e1" / "candidatos" / f"{sel['elegido']}.json").huella)
        self.assertLess(sel["contraste_ibs_sksurv"]["diferencia"], 1e-12)
        for d in sel["diagnostico_cox"].values():
            self.assertLess(d["equivalencia_json_sksurv"]["diferencia_maxima_supervivencia"], 1e-9)

    def test_reproducible_y_otra_configuracion_rechazada(self):
        from modelos.ejecucion import EjecucionError
        from modelos.proxima_compra_experimento import entrenar
        self.assertEqual(entrenar(self.datos, self.config, self.tmp / "e2")["congelacion"]["sello"], self.r["congelacion"]["sello"])
        otra = copy.deepcopy(self.config)
        otra["candidato"]["alpha"] = [5]
        with self.assertRaises(EjecucionError):
            entrenar(self.datos, otra, self.tmp / "e1")

    def test_evaluacion_recuperable_idempotente_y_evidencia_alterada(self):
        from modelos import ejecucion
        from modelos.compra import ProtocoloError
        from modelos.proxima_compra_experimento import evaluar, verificar_congelacion
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        ejecucion.FALLO_SIMULADO = "metricas_comprobacion_historica.json"
        with self.assertRaises(RuntimeError):
            evaluar(d, self.datos)
        ejecucion.FALLO_SIMULADO = None
        a = evaluar(d, self.datos)  # el reintento completa sin borrar nada
        b = evaluar(d, self.datos)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        self.assertIn(a["decision"]["decision"], ("favorable", "inconcluso", "rechazado"))
        x = self.tmp / "alterada"
        shutil.copytree(self.tmp / "e1", x)
        (x / "referencia_km.json").write_text((x / "referencia_km.json").read_text(encoding="utf-8").replace('"tipo": "km"', '"tipo": "km" '), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            verificar_congelacion(x)

    def test_sombra_contrato_y_sin_cambios_operativos(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.inferencia import cargar_artefacto
        from modelos.proxima_compra import puntuar_sombra
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="proxima_compra")
        out = self.tmp / "sombra"
        r1 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        r2 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        self.assertEqual(r1["manifiesto"]["sello"], r2["manifiesto"]["sello"])
        errores, man, filas = leer_publicacion_sombra(out)
        self.assertEqual(errores, [])
        self.assertEqual(len(filas), 120)
        self.assertTrue(all(f["probabilidad"] is None for f in filas))
        self.assertTrue(all(not f["ventana_utilizable"] or f["dias_p90"] is not None for f in filas))
        self.assertEqual(_huellas(RAIZ / "var" / "modelos"), self.registro_antes)
        self.assertEqual(_huellas(RAIZ / "salida" / "experimentos" / "inactividad_60d"), self.ejecuciones_antes)
        self.assertFalse((RAIZ / "var" / "modelos" / "proxima_compra").exists())


class SinDependenciasTests(unittest.TestCase):
    def test_api_y_puntuacion_sin_librerias_analiticas(self):
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sksurv', 'sklearn', 'numpy', 'scipy', 'pandas'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.proxima, modelos.proxima_compra, pipeline.generar\n"
                  "from modelos.inferencia import sellar, desde_dict\n"
                  "a = desde_dict(sellar({'formato': 'jacomind.supervivencia_residual.v1', 'modelo_id': 'proxima_compra', 'version': 't', 'tipo': 'km',"
                  " 'version_variables': 'proxima_compra-variables-v1', 'horizonte_dias': 60, 'soporte_dias': 60, 'umbral': None,"
                  " 'km': {'tiempos': [5, 20], 'supervivencia': [0.8, 0.4]}, 'disponible_desde': '2026-10-31'}))\n"
                  "assert a.curva({})[20] == 0.4\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


# ------------------------------------------------------------------------------------------ API, episodios y regresiones M2
from _apoyo_app import CasoBase  # noqa: E402


def _publicar(directorio, modelo, corte, filas, version="fx", manip=None):
    from modelos.ejecucion import json_bytes, publicar_lote
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": modelo, "corte": corte.isoformat(),
           "estado_experimento": "experimental en sombra · prueba", "operativa": False, "advertencia": "prueba",
           "modelo": {"version": version, "artefacto_huella": "f" * 64, "decision": {"decision": "inconcluso"}},
           "cobertura": {"corte": corte.isoformat(), "datos_observados_hasta": corte.isoformat(), "fuente": "prueba", "estado": "verificada"},
           "conteos": {}, "tablas": {"predicciones_clientes": {"archivo": "predicciones_clientes.json", "filas": len(filas)}}}
    if manip:
        manip(man, filas)
    publicar_lote(directorio, {"predicciones_clientes.json": json_bytes(filas)}, "manifiesto.json", man)
    return directorio


def _pc(cid, corte, ultima, p10, p90, version="fx"):
    r = (corte - ultima).days
    f = _fila(cid, "proxima_compra", corte=corte.isoformat(), datos_hasta=corte.isoformat(), version_modelo=version, recencia_dias=r,
              referencia_personal_estado="insuficiente", grupo="habitual")
    if p10 is None:
        return f | {"estado": "estimacion_parcial", "origen_estimacion": "poblacional_km"}
    d = lambda n: (corte + timedelta(days=n)).isoformat()  # noqa: E731
    return f | {"estado": "estimado", "origen_estimacion": "modelo_cox", "dias_p10": p10, "dias_p50": (p10 + p90) // 2, "dias_p90": p90,
                "fecha_p10": d(p10), "fecha_p50": d((p10 + p90) // 2), "fecha_p90": d(p90), "ancho_ventana_dias": p90 - p10,
                "ventana_utilizable": p90 - p10 <= 30}


ULT = {"DEMO01": date(2026, 8, 2), "DEMO02": date(2026, 10, 10), "DEMO03": date(2026, 10, 25), "DEMO05": date(2026, 9, 15),
       "DEMO06": date(2026, 10, 5), "DEMO07": date(2026, 10, 20), "DEMO08": date(2026, 6, 30)}


class ProximaApiTests(CasoBase):
    def sombra(self, nombre, corte, cambios=None):
        from api import proxima
        ventanas = {"DEMO02": (5, 25), "DEMO03": (10, 35), "DEMO05": (2, 20), "DEMO06": (None, None), "DEMO07": (3, 50)}
        ventanas.update(cambios or {})
        filas = [_pc(c, corte, u, *ventanas.get(c, (None, None))) for c, u in sorted(ULT.items())]
        filas.append(_fila("DEMO04", "proxima_compra", corte=corte.isoformat(), datos_hasta=corte.isoformat(), version_modelo="fx"))
        return proxima.importar_sombra(self.db, _publicar(self.tmp / nombre, "proxima_compra", corte, filas), "ops1")

    def test_permisos_portal_y_ficha_sin_alterar_c1(self):
        from api.permisos import MATRIZ
        for rol, u in {"operaciones": "ops1", "ventas": "ventas1", "finanzas": "fin1", "atencion": "aten1", "gerencia": "ger1", "empresa": "cli_a"}.items():
            self.assertEqual(self.http("GET", "/api/proxima", como=u)[0], 200 if rol in MATRIZ["proxima.ver"] else 403, rol)
        _, antes = self.http("GET", "/api/cierres/activo/clientes/DEMO05", como="ventas1")
        self.sombra("s1", date(2026, 11, 30))
        st, d = self.http("GET", "/api/proxima?dias=30", como="ventas1")
        self.assertEqual([i["cliente_id"] for i in d["items"]], ["DEMO05", "DEMO02", "DEMO03"])  # DEMO07: ventana de 47 días, no utilizable
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO05", como="ventas1")
        self.assertEqual(f["proxima_sombra"]["etiqueta"], "ventana estimada")
        for k in ("cliente", "prediccion"):
            self.assertEqual(f.get(k), antes.get(k))  # prob_compra_30d y acción C1 intactas
        self.assertIsNone(self.http("GET", "/api/cierres/activo/clientes/DEMO06", como="ventas1")[1]["proxima_sombra"]["fecha_p10"])
        _, portal = self.http("GET", "/api/portal/beneficios", como="cli_a")
        self.assertNotIn("proxima", json.dumps(portal).lower())
        self.assertEqual(self.http("POST", "/api/proxima/sincronizar", {}, como="ventas1")[0], 403)

    def test_recordatorios_desactivados_episodios_y_compra_que_cierra(self):
        from api import operacion, proxima
        from api.auth import cargar_usuario
        self.sombra("s1", date(2026, 11, 30))
        with self.db.conexion() as con:
            n0 = con.execute("SELECT count(*) FROM tareas").fetchone()[0]
        r = proxima.sincronizar(self.db, "ops1")
        self.assertFalse(r["activada"])
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM tareas").fetchone()[0], n0)
            operacion.fijar_bandera(self.db, cargar_usuario(con, "ops1"), "proxima_recordatorios", True)
        r1 = proxima.sincronizar(self.db, "ops1")
        r2 = proxima.sincronizar(self.db, "ops1")
        self.assertEqual(r1["nuevos"], 3)
        self.assertEqual((r2["nuevos"], r2["tareas_nuevas"], r2["sin_cambios"]), (0, 0, 3))
        with self.db.conexion() as con:
            tareas = con.execute("SELECT * FROM tareas WHERE episodio_id LIKE 'proxima:%'").fetchall()
            self.assertTrue(all(t["fecha_revision"] for t in tareas))
            eps = proxima.episodios(con)
        self.assertEqual(len({e["episodio_id"] for e in eps}), len(eps))
        self.assertNotIn("DEMO06", {e["cliente_id"] for e in eps})  # sin ventana utilizable: ninguna fecha
        nueva = date(2026, 12, 10)  # DEMO05 compra: se cierra el episodio; un corte anterior no lo toca
        self.sombra("s2", date(2026, 12, 31), cambios={})
        with self.db.transaccion() as con:  # el corte de diciembre ve la compra de DEMO05
            sid = con.execute("SELECT id FROM sombra_publicaciones WHERE modelo_id='proxima_compra' AND activa=1").fetchone()[0]
            fila = json.loads(con.execute("SELECT datos_json FROM sombra_predicciones WHERE sombra_id=? AND cliente_id='DEMO05'", (sid,)).fetchone()[0])
            fila["recencia_dias"] = (date(2026, 12, 31) - nueva).days
            con.execute("UPDATE sombra_predicciones SET datos_json=? WHERE sombra_id=? AND cliente_id='DEMO05'", (json.dumps(fila), sid))
        r3 = proxima.sincronizar(self.db, "ops1")
        self.assertEqual(r3["cerrados_compra"], 1)
        with self.db.conexion() as con:
            e = [x for x in proxima.episodios(con, "DEMO05") if x["estado"] == "cerrado_compra"]
        self.assertEqual(len(e), 1)


class RegresionesSombraM2Tests(CasoBase):
    def filas_m2(self, corte, version="m2-fx", posiciones=None):
        sys.path.insert(0, str(RAIZ / "tests" / "modelos"))
        from test_inactividad import PROB, ULTIMAS, _fila_sombra
        filas = [_fila_sombra(c, corte, u, PROB.get(c, 0.5), version) for c, u in sorted(ULTIMAS.items())]
        est = sorted((f for f in filas if f["estado"] == "estimado"), key=lambda f: (-f["probabilidad"], f["cliente_id"]))
        for i, f in enumerate(est, 1):
            f["posicion"] = (posiciones or {}).get(f["cliente_id"], i)
        return filas

    def test_publicacion_antigua_no_desplaza_a_la_reciente(self):
        from api import prevencion
        dic = prevencion.importar_sombra(self.db, _publicar(self.tmp / "dic", "inactividad_60d", date(2026, 12, 31), self.filas_m2(date(2026, 12, 31)), "m2-fx"), "ops1")
        nov = prevencion.importar_sombra(self.db, _publicar(self.tmp / "nov", "inactividad_60d", date(2026, 11, 30), self.filas_m2(date(2026, 11, 30)), "m2-fx"), "ops1")
        self.assertTrue(dic["activa"])
        self.assertFalse(nov["activa"])
        with self.db.conexion() as con:
            self.assertEqual(prevencion.sombra_activa(con)["corte"], "2026-12-31")

    def test_sello_version_y_posiciones_manipuladas(self):
        from api import prevencion
        from api.base import ErrorApi
        d = _publicar(self.tmp / "a", "inactividad_60d", date(2026, 11, 30), self.filas_m2(date(2026, 11, 30)), "m2-fx")
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        m["estado_experimento"] = "favorable"  # manifiesto editado sin volver a sellar
        (d / "manifiesto.json").write_text(json.dumps(m), encoding="utf-8")
        with self.assertRaises(ErrorApi):
            prevencion.importar_sombra(self.db, d, "ops1")
        otra = _publicar(self.tmp / "b", "inactividad_60d", date(2026, 11, 30), self.filas_m2(date(2026, 11, 30), version="otra"), "m2-fx")
        with self.assertRaises(ErrorApi):  # filas de otra versión que el manifiesto
            prevencion.importar_sombra(self.db, otra, "ops1")
        falsas = self.filas_m2(date(2026, 11, 30), posiciones={"DEMO03": 1, "DEMO05": 5})  # posiciones suministradas engañosas
        prevencion.importar_sombra(self.db, _publicar(self.tmp / "c", "inactividad_60d", date(2026, 11, 30), falsas, "m2-fx"), "ops1")
        with self.db.conexion() as con:
            items = prevencion.lista(con, 2)["items"]
        self.assertEqual([i["cliente_id"] for i in items], ["DEMO05", "DEMO06"])  # orden por probabilidad, no por 'posicion'

    def test_episodio_no_se_modifica_con_evidencia_anterior(self):
        from api import prevencion
        e = {"abierto_en_corte": "2026-12-31", "ultima_evidencia_json": json.dumps({"corte": "2026-12-31"})}
        self.assertTrue(prevencion._evidencia_anterior(e, {"corte": "2026-11-30"}))
        self.assertFalse(prevencion._evidencia_anterior(e, {"corte": "2026-12-31"}))


if __name__ == "__main__":
    unittest.main()
