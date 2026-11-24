"""M5 · pronóstico de demanda: calendario, conciliación, referencias A08, ajuste e inferencia, evaluación por origen,
métricas, total, bandas, integridad, contrato, observaciones posteriores, API y ausencia de dependencias analíticas."""
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))
HAY_SM = importlib.util.find_spec("statsmodels") is not None
CFG = json.loads((RAIZ / "modelos" / "config" / "demanda.json").read_text(encoding="utf-8"))


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _cal(valores, desde="2025-01"):
    from modelos.demanda import sumar_meses
    return [{"periodo": sumar_meses(desde, i), "estado": "completo" if v is not None else "incompleto", "valor": v, "motivo": None if v is not None else "x"}
            for i, v in enumerate(valores)]


class MesesTests(unittest.TestCase):
    def test_horizonte_en_meses_calendario_y_cambio_de_anio(self):
        from modelos.demanda import fin_mes, sumar_meses
        self.assertEqual([sumar_meses("2026-10", h) for h in (1, 2, 3)], ["2026-11", "2026-12", "2027-01"])
        self.assertEqual(sumar_meses("2026-01", 1), "2026-02")
        self.assertEqual((fin_mes("2026-02").day, fin_mes("2024-02").day, fin_mes("2026-04").day), (28, 29, 30))

    def test_tramo_hueco_e_incompleto_no_se_imputan(self):
        from modelos.demanda import tramo
        cal = _cal([1, 2, None, 4, 5, 6, 0, 8])
        self.assertEqual(tramo(cal, "2025-08"), [4, 5, 6, 0, 8])  # el hueco de marzo corta el tramo; el cero completo se conserva
        self.assertEqual(tramo(cal, "2025-03"), [])                # origen incompleto: sin historia
        cal_pico = cal + [{"periodo": "2025-09", "estado": "completo", "valor": 1e9, "motivo": None}]
        self.assertEqual(tramo(cal_pico, "2025-08"), tramo(cal, "2025-08"))  # un pico posterior no cambia lo conocido


class ConstruccionTests(unittest.TestCase):
    def datos(self, ventas, hasta=date(2025, 4, 30)):
        prods = {"P1": {"familia_prueba": "Software"}, "P2": {"familia_prueba": "Servicios"}}
        return SimpleNamespace(ventas=ventas, productos=prods, tasas={date(2025, 2, 10): Decimal("4000")}, observado_hasta=hasta,
                               revision=1, huella_datos="h")

    def v(self, f, p, cant=1, precio="1000", mon="COP", est="Confirmada", vid=None):
        return {"venta_id": vid or f"V{f}{p}", "fecha": f, "producto_id": p, "cantidad": cant, "moneda": mon, "precio_unitario": Decimal(precio),
                "descuento_pct": Decimal("0"), "estado": est}

    def cfg(self):
        c = copy.deepcopy(CFG)
        c["series"]["ventas_cop"]["familias"] = ["Software", "Servicios"]
        return c

    def test_cero_completo_incompleto_usd_y_disponibilidad(self):
        from modelos.demanda import conciliar, construir_series
        ventas = [self.v(date(2025, 1, 5), "P1"), self.v(date(2025, 2, 10), "P1", precio="10", mon="USD"), self.v(date(2025, 2, 11), "P1", est="Anulada"),
                  self.v(date(2025, 3, 1), "P2", cant=3)]
        d = self.datos(ventas, hasta=date(2025, 4, 20))
        s = construir_series(d, self.cfg())
        sw = {m["periodo"]: m for m in s["ventas_cop:Software"]["calendario"]}
        self.assertEqual((sw["2025-01"]["valor"], sw["2025-02"]["valor"], sw["2025-03"]["valor"]), (1000.0, 40000.0, 0.0))  # USD a la TRM; anulada fuera; cero real
        self.assertEqual((sw["2025-04"]["estado"], sw["2025-04"]["valor"]), ("incompleto", None))                          # abril solo hasta el 20
        p2 = {m["periodo"]: m for m in s["ventas_unidades:P2"]["calendario"]}
        self.assertEqual((p2["2025-02"]["estado"], p2["2025-03"]["valor"]), ("no_observable", 3.0))                        # antes de la disponibilidad: no es cero
        self.assertTrue(all(m["estado"] == "sin_cobertura" and m["valor"] is None for m in s["compras_proveedores_cop:Software"]["calendario"]))
        self.assertTrue(all(c["conciliado"] for c in conciliar(d, s, self.cfg())))

    def test_tasa_ausente_deja_el_mes_incompleto(self):
        from modelos.demanda import construir_series
        d = self.datos([self.v(date(2025, 3, 5), "P1", precio="10", mon="USD")])
        sw = {m["periodo"]: m for m in construir_series(d, self.cfg())["ventas_cop:Software"]["calendario"]}
        self.assertEqual((sw["2025-03"]["estado"], sw["2025-03"]["valor"]), ("incompleto", None))


@unittest.skipUnless(HAY_SM, "Requiere statsmodels (entorno analítico)")
class AjusteTests(unittest.TestCase):
    def test_constante_tendencia_cero_y_equivalencia(self):
        from modelos.demanda import pron_estado
        from modelos.demanda_experimento import ajustar_ets, pronosticar
        for m in ("ses", "holt_amortiguado"):
            est = ajustar_ets([100.0] * 14, m, CFG)
            self.assertTrue(est["convergio"])
            self.assertAlmostEqual(pron_estado(est, 2), 100.0, places=4)
        tend = [10.0 + 3 * i for i in range(14)]
        est = ajustar_ets(tend, "holt_amortiguado", CFG)
        for h in (1, 2, 3):
            self.assertLess(abs(pron_estado(est, h) - est["statsmodels"][h - 1]) / abs(est["statsmodels"][h - 1]), 1e-8)
        self.assertGreater(pron_estado(est, 3), tend[-1])
        cero = pronosticar("ses", [0.0] * 14, 1, CFG)
        self.assertEqual((cero["valor"], cero["sustitucion"]["respaldo"]), (0.0, "media_movil_3"))
        self.assertIsNone(pronosticar("ses", [1.0] * 11, 1, CFG))     # candidato con < 12 meses
        self.assertIsNone(pronosticar("ultimo", [1.0] * 5, 1, CFG))   # referencia con < 6 meses

    def test_fallo_de_convergencia_usa_referencia_explicita_y_recorte(self):
        from modelos import demanda_experimento as E
        with mock.patch.object(E, "ajustar_ets", return_value={"metodo": "ses", "convergio": False, "motivo": "optimizador sin convergencia"}):
            p = E.pronosticar("ses", [5.0, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16], 1, CFG)
        self.assertEqual(p["sustitucion"]["motivo"], "optimizador sin convergencia")
        self.assertEqual(p["valor"], 15.0)  # media móvil de 3 publicada como respaldo
        with mock.patch.object(E, "pron_ultimo", return_value=-7.5):
            r = E.pronosticar("ultimo", [1.0] * 6, 1, CFG)
        self.assertEqual((r["bruto"], r["valor"], r["recortado"]), (-7.5, 0.0, True))
        m = E.metricas([{"error": r["valor"] - 2.0, "observado": 2.0, "recortado": True, "sustitucion": None}])
        self.assertEqual(m["mae"], 2.0)  # se evalúa el valor publicado


class MetricasTests(unittest.TestCase):
    def test_wape_y_sesgo_con_denominador_cero_y_mejora_sin_division(self):
        from modelos.demanda_experimento import decidir, metricas
        m = metricas([{"error": 1.0, "observado": 0.0, "recortado": False, "sustitucion": None}, {"error": -1.0, "observado": 0.0, "recortado": False, "sustitucion": None}])
        self.assertEqual((m["mae"], m["wape"], m["sesgo_abs_normalizado"]), (1.0, None, None))
        d = decidir({"elegido": "ses", "mejor_referencia": "ultimo"}, {"n": 4, "mae": 1.0, "sesgo_abs_normalizado": None}, {"n": 4, "mae": 0.0}, CFG)
        self.assertEqual(d["decision"], "referencia_conservada")
        self.assertEqual(decidir({"elegido": "ses", "mejor_referencia": "ultimo"}, {"n": 2, "mae": 1.0, "sesgo_abs_normalizado": 0.0}, {"n": 2, "mae": 9.0}, CFG)["decision"], "inconcluso")
        self.assertEqual(decidir({"elegido": "ses", "mejor_referencia": "ultimo"}, {"n": 4, "mae": 8.0, "sesgo_abs_normalizado": 0.05}, {"n": 4, "mae": 10.0}, CFG)["decision"],
                         "candidato_exploratorio_favorable")
        self.assertEqual(decidir({"elegido": "ses", "mejor_referencia": "ultimo"}, {"n": 3, "mae": 12.0, "sesgo_abs_normalizado": 0.05}, {"n": 3, "mae": 10.0}, CFG)["decision"], "rechazado")

    def test_bandas_minimo_doce_y_sin_errores_futuros(self):
        from modelos.demanda_experimento import banda, errores_previos
        self.assertEqual(banda([1.0] * 11, 100.0, CFG)["inferior"], None)
        b = banda([float(i) for i in range(-6, 6)], 100.0, CFG)
        self.assertEqual((b["errores_disponibles"], b["inferior"] <= 100 <= b["superior"]), (12, True))
        filas = [{"metodo": "ultimo", "horizonte": 1, "error": 1.0, "objetivo": "2026-06"}, {"metodo": "ultimo", "horizonte": 1, "error": 5.0, "objetivo": "2026-07"}]
        self.assertEqual(errores_previos(filas, "ultimo", 1, "2026-06"), [1.0])  # el error de julio no se conocía en junio


class ContratoTests(unittest.TestCase):
    def fila(self, sid, h, v, unidad="COP", **k):
        from modelos.demanda import sumar_meses
        return {"modelo_id": "demanda", "origen": "2026-10", "serie_id": sid, "fuente": "ventas", "medida": "m", "unidad": unidad, "horizonte_meses": h,
                "periodo_objetivo": sumar_meses("2026-10", h), "valor": v, "metodo": "ultimo", "estado": "estimado" if v is not None else "sin_historia",
                "version_modelo": "v", "motivos": ["m"], "n_evaluaciones": 0, "banda_soporte": 0, "banda_inferior": None, "banda_superior": None,
                "banda_motivo": "historia_insuficiente"} | k

    def pub(self, filas):
        from contratos.validar import validar_publicacion_sombra
        man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "demanda", "corte": "2026-10-31", "origen": "2026-10", "estado_experimento": "x", "operativa": False,
               "modelo": {"version": "v", "artefacto_huella": "f" * 64}, "cobertura": {"corte": "2026-10-31", "datos_observados_hasta": "2026-10-31", "fuente": "t", "estado": "verificada"},
               "tablas": {"pronosticos_demanda": {"filas": len(filas)}, "calendario_demanda": {"filas": 0}}}
        return validar_publicacion_sombra(man, {"pronosticos_demanda": filas, "calendario_demanda": []})

    def test_total_horizonte_bandas_y_unidades(self):
        fams = [self.fila(f"ventas_cop:{f}", 1, 10.0) for f in ("A", "B")]
        ok = fams + [self.fila("ventas_cop:Total", 1, 20.0, metodo="suma_de_familias")]
        self.assertEqual(self.pub(ok), [])
        malos = [fams + [self.fila("ventas_cop:Total", 1, 25.0)],                               # total ≠ suma
                 [self.fila("ventas_cop:A", 2, 1.0, periodo_objetivo="2026-11")],                # mes objetivo incorrecto
                 [self.fila("ventas_cop:A", 1, 1.0, banda_inferior=0.5, banda_superior=2.0, banda_soporte=5, banda_metodo="x")],  # banda sin soporte
                 [self.fila("ventas_cop:A", 1, 1.0, banda_inferior=3.0, banda_superior=2.0, banda_soporte=12, banda_metodo="x")],  # desordenada
                 [self.fila("ventas_unidades:P1", 1, 1.0, unidad="COP")],                       # unidad incoherente
                 [self.fila("ventas_cop:A", 1, float("inf"))], [self.fila("ventas_cop:A", 1, None, motivos=[])],
                 [self.fila("ventas_cop:A", 1, 1.0), self.fila("ventas_cop:A", 1, 2.0)]]       # clave repetida
        for f in malos:
            with self.subTest(f=f):
                self.assertTrue(self.pub(f))


class SinDependenciasTests(unittest.TestCase):
    def test_api_cierre_y_puntuacion_sin_statsmodels(self):
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('statsmodels', 'sklearn', 'numpy', 'scipy', 'pandas', 'sksurv'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.demanda, modelos.demanda, pipeline.generar\n"
                  "from modelos.demanda import pron_estado\n"
                  "assert abs(pron_estado({'metodo': 'holt_amortiguado', 'nivel': 1.0, 'tendencia': 0.5, 'amortiguamiento': 0.9, 'escala': 10.0}, 2) - (1 + 0.5 * (0.9 + 0.81)) * 10) < 1e-12\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


@unittest.skipIf(_paquete() is None or not HAY_SM, "Requiere el paquete y statsmodels")
class ExperimentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.demanda_experimento import entrenar
        cls.tmp = Path(tempfile.mkdtemp(prefix="m5-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cls.r = entrenar(cls.datos, CFG, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_a08_reproducido_conciliacion_y_origenes_identicos(self):
        a = json.loads((self.tmp / "e1" / "control_a08.json").read_text(encoding="utf-8"))
        self.assertTrue(all(v["coincide"] for v in a["series"].values()))
        self.assertTrue(all(c["conciliado"] for c in self.r["conciliacion"]))
        dev = json.loads((self.tmp / "e1" / "desarrollo.json").read_text(encoding="utf-8"))
        s = [f for f in dev if f["serie_id"] == "ventas_cop:Software"]
        orig = {m: {(f["origen"], f["horizonte"]) for f in s if f["metodo"] == m} for m in ("ultimo", "media_movil_3", "ses", "holt_amortiguado")}
        self.assertEqual(len({frozenset(v) for v in orig.values()}), 1)  # mismos orígenes y objetivos para todos los métodos
        self.assertEqual({h: sum(1 for o, hh in orig["ses"] if hh == h) for h in (1, 2, 3)}, {1: 6, 2: 5, 3: 4})

    def test_seleccion_congelada_interrupcion_idempotencia_y_reproducible(self):
        from modelos import ejecucion
        from modelos.compra import ProtocoloError
        from modelos.demanda_experimento import entrenar, evaluar, verificar_congelacion
        self.assertEqual(entrenar(self.datos, CFG, self.tmp / "e2")["congelacion"]["sello"], self.r["congelacion"]["sello"])
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        ejecucion.FALLO_SIMULADO = "comprobacion.json"
        with self.assertRaises(RuntimeError):
            evaluar(d, self.datos)
        ejecucion.FALLO_SIMULADO = None
        a, b = evaluar(d, self.datos), evaluar(d, self.datos)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        sel = json.loads((d / "seleccion.json").read_text(encoding="utf-8"))
        for sid, dd in a["decision"]["decisiones"].items():
            for h, x in dd.items():
                if sel[sid]["estado"] == "seleccionada":
                    self.assertEqual(a["metricas"]["resultados"][sid][h]["elegido"], sel[sid]["por_horizonte"][h]["elegido"])  # no se vuelve a seleccionar
        x = self.tmp / "alt"
        shutil.copytree(self.tmp / "e1", x)
        sel["ventas_cop:Software"]["por_horizonte"]["1"]["elegido"] = "holt_amortiguado"
        (x / "seleccion.json").write_text(json.dumps(sel), encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            verificar_congelacion(x)

    def test_origen_sombra_total_y_observaciones_que_no_sobrescriben(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.demanda import incorporar_observaciones, puntuar_sombra
        from modelos.demanda_experimento import ajustar_origen, evaluar
        from modelos.inferencia import cargar_artefacto
        d = self.tmp / "ev2"
        shutil.copytree(self.tmp / "e1", d)
        evaluar(d, self.datos)
        r = ajustar_origen(d, self.datos, "2026-10", self.tmp / "origen")
        self.assertTrue(all(e["diferencia_relativa"] < 1e-8 for e in r["equivalencias"]))
        art = cargar_artefacto(self.tmp / "origen" / "artefacto.json", modelo_id="demanda")
        out = self.tmp / "sombra"
        puntuar_sombra(art, self.datos, CFG, out, estado_experimento="experimental")
        errores, man, t = leer_publicacion_sombra(out)
        self.assertEqual(errores, [])
        filas = t["pronosticos_demanda"]
        for h in (1, 2, 3):
            fam = [f["valor"] for f in filas if f["serie_id"].startswith("ventas_cop:") and f["serie_id"] != "ventas_cop:Total" and f["horizonte_meses"] == h]
            tot = next(f for f in filas if f["serie_id"] == "ventas_cop:Total" and f["horizonte_meses"] == h)
            self.assertAlmostEqual(tot["valor"], round(sum(fam), 2), places=2)
        antes = (out / "pronosticos_demanda.json").read_bytes()
        ev = incorporar_observaciones(out, self.datos, CFG, self.tmp / "evals")
        self.assertEqual(ev["evaluadas"], 0)  # noviembre aún no está completo: pendientes
        self.assertEqual((out / "pronosticos_demanda.json").read_bytes(), antes)
        self.assertEqual(sorted(t["pronosticos_demanda"][0]), sorted(filas[0]))


# ------------------------------------------------------------------------------------------------- API
from _apoyo_app import CasoBase  # noqa: E402


def _pub(directorio, origen, valor=10.0):
    from modelos.demanda import sumar_meses
    from modelos.ejecucion import json_bytes, publicar_lote
    fila = lambda sid, h, v, u="COP": {"modelo_id": "demanda", "origen": origen, "serie_id": sid, "fuente": "ventas", "medida": "m", "unidad": u, "horizonte_meses": h,  # noqa: E731
                                       "periodo_objetivo": sumar_meses(origen, h), "valor": v, "metodo": "ultimo", "estado": "estimado", "version_modelo": "dm-fx",
                                       "motivos": ["m"], "n_evaluaciones": 4, "mae": 1.0, "banda_soporte": 3, "banda_inferior": None, "banda_superior": None,
                                       "banda_motivo": "historia_insuficiente"}
    filas = [fila("ventas_cop:Software", h, valor) for h in (1, 2, 3)] + [dict(fila("ventas_cop:Total", h, valor), metodo="suma_de_familias") for h in (1, 2, 3)] + \
            [fila("ventas_unidades:PRO01", h, 3.0, "cantidad") for h in (1, 2, 3)]
    cal = [{"serie_id": "ventas_cop:Software", "periodo": origen, "estado": "completo", "valor": 9.0, "motivo": None, "unidad": "COP"},
           {"serie_id": "ventas_unidades:PRO01", "periodo": origen, "estado": "completo", "valor": 2.0, "motivo": None, "unidad": "cantidad"}]
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "demanda", "corte": f"{origen}-28", "origen": origen, "estado_experimento": "experimental · prueba",
           "operativa": False, "modelo": {"version": "dm-fx", "artefacto_huella": "f" * 64}, "advertencia": "x",
           "cobertura": {"corte": f"{origen}-28", "datos_observados_hasta": f"{origen}-28", "fuente": "t", "estado": "verificada"},
           "tablas": {"pronosticos_demanda": {"filas": len(filas)}, "calendario_demanda": {"filas": len(cal)}}}
    publicar_lote(directorio, {"pronosticos_demanda.json": json_bytes(filas), "calendario_demanda.json": json_bytes(cal)}, "manifiesto.json", man)
    return directorio


class DemandaApiTests(CasoBase):
    def test_permisos_cop_unidades_portal_y_fuera_de_orden(self):
        from api import demanda
        self.assertEqual(self.http("GET", "/api/demanda", como="fin1")[1]["estado"], "sin_sombra")
        self.assertTrue(demanda.importar_sombra(self.db, _pub(self.tmp / "dic", "2026-12"), "ops1")["activa"])
        self.assertFalse(demanda.importar_sombra(self.db, _pub(self.tmp / "nov", "2026-11", 99.0), "ops1")["activa"])
        st, d = self.http("GET", "/api/demanda", como="fin1")
        self.assertEqual((st, d["origen"], d["serie_id"]), (200, "2026-12", "ventas_cop:Total"))
        st, d = self.http("GET", "/api/demanda?serie=ventas_cop:Software", como="ops1")  # Operaciones: solo unidades
        self.assertEqual((st, d["series"], d["serie_id"]), (200, ["ventas_unidades:PRO01"], "ventas_unidades:PRO01"))
        for u in ("ventas1", "aten1", "cli_a"):
            self.assertEqual(self.http("GET", "/api/demanda", como=u)[0], 403, u)


if __name__ == "__main__":
    unittest.main()
