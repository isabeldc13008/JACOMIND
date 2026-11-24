"""Monitoreo común M1–M6 (contrato jacomind.monitoreo.v1, reglas monitoreo-reglas-v1): reglas con ceros y nulos, madurez,
comparabilidad, idempotencia, correcciones enlazadas, publicaciones históricas, métricas por modelo, unidades, estados
estructurales, permisos, integridad y ausencia de promoción o reversión automáticas."""
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))


def _con():
    from api.base import BaseDatos
    tmp = Path(tempfile.mkdtemp(prefix="mon-"))
    db = BaseDatos(tmp / "m.sqlite3")
    db.migrar()
    return tmp, db


def _salud(origen, corte, elegibles, cubiertos, *, modelo="inactividad_60d", politica=None, universo="clientes"):
    from api import monitoreo as M
    return M.observacion(modelo_id=modelo, variante="v", version_artefacto="x", origen={"tipo": "sombra", "id": origen}, corte=corte, universo=universo,
                         grupo="salud", conteos={"elegibles": elegibles, "estimados": cubiertos}, politica=politica or {"id": "p", "version": "1"},
                         metricas={"cobertura": M.tasa(cubiertos, elegibles, "periodo sin registros elegibles")})


def _alertas(origen, corte, validas, alertas):
    from api import monitoreo as M
    return M.observacion(modelo_id="anomalias", variante="m6", version_artefacto="x", origen={"tipo": "sombra", "id": origen}, corte=corte, universo="venta",
                         grupo="distribucion", conteos={"validas": validas, "alertas": alertas}, politica={"id": "cupo", "version": "1"},
                         metricas={"alertas_por_100": M.metrica(round(100 * alertas / validas, 4) if validas else None, numerador=alertas, denominador=validas,
                                                               motivo="sin operaciones")})


def _desemp(origen, corte, x, r, soporte=40, madurez="madura"):
    from api import monitoreo as M
    return M.observacion(modelo_id="compra_30d", variante="v", version_artefacto="x", origen={"tipo": "resultados", "id": origen}, corte=corte,
                         universo="clientes", grupo="desempeno", madurez=madurez, conteos={"evaluados": soporte}, politica={"id": "c1", "version": "1"},
                         metricas={} if madurez == "pendiente" else {"precision_cupo": M.metrica(x, numerador=None, denominador=None, soporte=soporte,
                                                                                                 referencia={"id": "recencia", **M.metrica(r, soporte=soporte)})})


class ReglasTests(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db = _con()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reg(self, obs, vigente=True):
        from api import monitoreo as M
        with self.db.transaccion() as con:
            return M.registrar_y_evaluar(con, obs, vigente=vigente)

    def tipos(self, r):
        return [a["tipo"] for a in r["avisos"]]

    def test_cobertura_100_a_0_y_periodo_sin_registros(self):
        self.assertEqual(self.tipos(self.reg(_salud("a", "2026-08-31", 50, 50))), [])           # primer corte: sin referencia previa
        self.assertEqual(self.tipos(self.reg(_salud("b", "2026-09-30", 50, 0))), ["caida_cobertura"])
        r = self.reg(_salud("c", "2026-10-31", 0, 0))
        from api import monitoreo as M
        self.assertEqual(self.tipos(r), ["sin_registros"])                                       # cero registros: estado explícito
        with self.db.conexion() as con:
            o = json.loads(con.execute("SELECT datos_json FROM monitoreo_observaciones WHERE origen_id = 'c'").fetchone()[0])
        self.assertIsNone(o["metricas"]["cobertura"]["valor"])                                    # nunca 0 % ni 100 %
        self.assertTrue(o["metricas"]["cobertura"]["motivo"])
        self.assertEqual(M.deterioro_relativo(None, 0.5, "mayor"), (None, "valor_ausente"))

    def test_tasa_de_alertas_desde_cero_y_hasta_cero(self):
        self.reg(_alertas("a", "2026-08-31", 40, 0))
        self.assertEqual(self.tipos(self.reg(_alertas("b", "2026-09-30", 40, 3))), ["cambio_tasa_alertas"])  # 0 → positiva
        self.assertEqual(self.tipos(self.reg(_alertas("c", "2026-10-31", 40, 0))), ["cambio_tasa_alertas"])  # positiva → 0
        self.assertEqual(self.tipos(self.reg(_alertas("d", "2026-11-30", 40, 0))), [])                       # 0 → 0: sin cambio
        self.assertEqual(self.tipos(self.reg(_alertas("e", "2026-12-31", 10, 9))), [])                       # soporte insuficiente

    def test_no_comparables_y_cambio_de_politica(self):
        self.reg(_salud("a", "2026-08-31", 50, 50))
        r = self.reg(_salud("b", "2026-09-30", 50, 0, politica={"id": "otra", "version": "2"}))
        self.assertEqual(self.tipos(r), ["cambio_politica"])                                     # no compara ni declara caída

    def test_deterioro_dos_cortes_maduros_inmaduro_y_referencia_cero(self):
        from api import monitoreo as M
        self.assertEqual(self.tipos(self.reg(_desemp("r1", "2026-07-31", 0.5, 0.8))), [])         # un corte deteriorado no basta
        self.assertEqual(self.tipos(self.reg(_desemp("r2", "2026-08-31", None, None, madurez="pendiente"))), [])
        self.assertEqual(self.tipos(self.reg(_desemp("r3", "2026-09-30", 0.5, 0.8))), [])         # el anterior inmediato está inmaduro
        self.assertEqual(self.tipos(self.reg(_desemp("r4", "2026-10-31", 0.55, 0.8))), ["deterioro_frente_referencia"])
        self.assertEqual(self.tipos(self.reg(_desemp("r5", "2026-11-30", 0.5, 0.8, soporte=10))), [])  # soporte mínimo
        self.assertEqual(M.deterioro_relativo(0.3, 0.0, "menor"), (None, "referencia_cero"))
        self.assertEqual(M.deterioro_relativo(0.0, 0.0, "menor"), (0.0, None))
        self.assertAlmostEqual(M.deterioro_relativo(0.6, 0.5, "menor")[0], 0.2)
        self.assertAlmostEqual(M.deterioro_relativo(0.4, 0.5, "mayor")[0], 0.2)
        with self.assertRaises(ValueError):                                                     # pendiente no lleva métricas
            self.reg(dict(_desemp("x", "2026-12-31", None, None, madurez="pendiente"), metricas={"brier": M.metrica(0.2, soporte=5)}))

    def test_idempotencia_correccion_e_historica_no_vigente(self):
        a = _salud("a", "2026-08-31", 50, 50)
        r1, r2 = self.reg(a), self.reg(a)
        self.assertEqual((r1["estado"], r2["estado"]), ("nueva", "existente"))
        b = _salud("a", "2026-08-31", 50, 49)                                                     # mismo origen corregido
        rc = self.reg(b)
        self.assertEqual(rc["estado"], "correccion")
        with self.db.conexion() as con:
            filas = [dict(x) for x in con.execute("SELECT id, anterior_id, reemplazada_por FROM monitoreo_observaciones ORDER BY creada_en")]
            n_av = con.execute("SELECT count(*) FROM avisos_modelos").fetchone()[0]
        self.assertEqual(len(filas), 2)                                                          # se conservan ambas
        self.assertEqual((filas[1]["anterior_id"], filas[0]["reemplazada_por"]), (filas[0]["id"], filas[1]["id"]))
        self.reg(_salud("vieja", "2026-07-31", 50, 0), vigente=False)                            # histórica importada después
        self.assertEqual(self.tipos(self.reg(_salud("b", "2026-09-30", 50, 49))), [])            # compara con la vigente, no con la vieja
        for _ in range(2):
            self.reg(_salud("c", "2026-10-31", 50, 0))
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM avisos_modelos WHERE tipo = 'caida_cobertura'").fetchone()[0], 1)  # sin duplicados
        self.assertEqual(n_av, 0)

    def test_sin_promocion_reversion_ni_reentrenamiento(self):
        for m in ("api/monitoreo.py", "api/monitoreo_modelos.py"):
            fuente = (RAIZ / m).read_text(encoding="utf-8")
            for prohibido in ("registro", "promover", "revertir", "entrenar"):
                self.assertNotIn(f"import {prohibido}", fuente)
                self.assertNotIn(f".{prohibido}(", fuente)


class SinDependenciasTests(unittest.TestCase):
    def test_monitoreo_api_cierre_y_verificador_m1_sin_bibliotecas_analiticas(self):
        import subprocess
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy', 'pandas', 'statsmodels', 'sksurv', 'joblib'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.monitoreo, api.monitoreo_modelos, api.publicacion, api.operacion, modelos.compra_m1_ejecucion, modelos.cli\n"
                  "from api.monitoreo import deterioro_relativo\n"
                  "assert deterioro_relativo(0.3, 0.0, 'menor') == (None, 'referencia_cero')\n"
                  "print('ok')\n")
        r = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])


def _datos(ventas, hasta):
    return SimpleNamespace(ventas=ventas, observado_hasta=hasta, huella_datos="h" * 64)


def _v(c, f, p="P1"):
    return {"cliente_id": c, "fecha": f, "producto_id": p, "estado": "Confirmada"}


class MetricasModelosTests(unittest.TestCase):
    def test_m1_brier_cupo_frente_a_recencia_y_madurez(self):
        from api.monitoreo_modelos import resultados_clientes
        corte = date(2026, 8, 31)
        filas = [{"cliente_id": f"C{i}", "estado": "estimado", "probabilidad": p} for i, p in enumerate([0.9, 0.8, 0.1, 0.2])]
        ventas = [_v("C0", corte + timedelta(days=5)), _v("C2", corte - timedelta(days=1)), _v("C2", corte + timedelta(days=10)),
                  _v("C1", corte + timedelta(days=45))]  # C1 compra fuera del horizonte
        o = resultados_clientes("compra_30d", {"tipo": "cierre", "id": "c"}, corte.isoformat(), "v", filas, _datos(ventas, corte + timedelta(days=29)), {})
        self.assertEqual((o[0]["madurez"], o[0]["metricas"]), ("pendiente", {}))                # inmaduro: sin métricas
        o = resultados_clientes("compra_30d", {"tipo": "cierre", "id": "c"}, corte.isoformat(), "v", filas, _datos(ventas, corte + timedelta(days=30)), {})[0]
        self.assertEqual(o["madurez"], "madura")
        self.assertAlmostEqual(o["metricas"]["brier"]["valor"], ((0.9 - 1) ** 2 + 0.8 ** 2 + (0.1 - 1) ** 2 + 0.2 ** 2) / 4, places=6)
        self.assertEqual(o["metricas"]["precision_cupo"]["denominador"], 4)                      # cupo 10 limitado al universo
        self.assertEqual(o["metricas"]["precision_cupo"]["referencia"]["id"], "mayor_recencia (menos días desde la última compra primero)")

    def test_m2_estructurales_no_son_fallos(self):
        from api.monitoreo_modelos import obs_clientes
        filas = [{"cliente_id": "a", "estado": "estimado", "probabilidad": 0.3}, {"cliente_id": "b", "estado": "estructural", "probabilidad": 0.0},
                 {"cliente_id": "c", "estado": "no_elegible", "probabilidad": None}, {"cliente_id": "d", "estado": "sin_historia", "probabilidad": None}]
        s = obs_clientes("inactividad_60d", {"tipo": "sombra", "id": "x"}, "2026-10-31", "inactividad_60d-m21-x", filas, None, {})[0]
        self.assertEqual((s["conteos"]["elegibles"], s["conteos"]["estructurales"], s["conteos"]["abstenciones"]), (3, 1, 1))
        self.assertEqual((s["metricas"]["cobertura"]["numerador"], s["metricas"]["cobertura"]["denominador"]), (2, 3))

    def test_m3_horizontes_maduros_y_censurados(self):
        from api.monitoreo_modelos import resultados_proxima
        corte = date(2026, 9, 30)
        filas = [{"cliente_id": "a", "prob_acumulada": {"15": 0.2, "30": 0.5, "60": 0.7}, "ventana_utilizable": False}]
        obs = resultados_proxima({"tipo": "sombra", "id": "x"}, corte.isoformat(), "proxima_compra-m31-x", filas,
                                 _datos([_v("a", corte + timedelta(days=20))], corte + timedelta(days=31)), {})
        por = {o["universo"]: o for o in obs}
        self.assertEqual(por["horizonte_15d"]["metricas"]["tasa_observada"]["numerador"], 0)
        self.assertEqual(por["horizonte_30d"]["metricas"]["tasa_observada"]["numerador"], 1)
        self.assertEqual((por["horizonte_60d"]["madurez"], por["horizonte_60d"]["metricas"]), ("pendiente", {}))  # censurado, no «no compró»

    def test_m5_resultados_maduros_errores_wape_sesgo_bandas_y_referencia(self):
        """Fixture de PRUEBA (no datos comerciales): una familia en COP y su producto en unidades."""
        from decimal import Decimal
        from api.monitoreo_modelos import resultados_demanda
        ventas = []
        for i, (mes, n) in enumerate([("2025-0%d" % m, m) for m in range(1, 10)] + [("2025-10", 20)]):
            ventas.append({"venta_id": f"V{i}", "fecha": date.fromisoformat(mes + "-15"), "cliente_id": "C", "producto_id": "P1", "cantidad": n, "moneda": "COP",
                           "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "estado": "Confirmada"})
        datos = SimpleNamespace(ventas=ventas, productos={"P1": {"familia_prueba": "Software"}}, tasas={}, observado_hasta=date(2025, 10, 31), huella_datos="h" * 64)
        cal = [{"serie_id": "ventas_cop:Software", "periodo": "2025-%02d" % m, "estado": "completo", "valor": 100.0 * m, "unidad": "COP"} for m in range(1, 10)] +               [{"serie_id": "ventas_unidades:P1", "periodo": "2025-%02d" % m, "estado": "completo", "valor": float(m), "unidad": "u"} for m in range(1, 10)]
        pron = [{"serie_id": "ventas_cop:Software", "origen": "2025-09", "horizonte_meses": 1, "periodo_objetivo": "2025-10", "valor": 1500.0, "unidad": "COP",
                 "banda_inferior": 1000.0, "banda_superior": 2500.0},
                {"serie_id": "ventas_cop:Software", "origen": "2025-09", "horizonte_meses": 2, "periodo_objetivo": "2025-11", "valor": 1500.0, "unidad": "COP",
                 "banda_inferior": None, "banda_superior": None},
                {"serie_id": "ventas_unidades:P1", "origen": "2025-09", "horizonte_meses": 1, "periodo_objetivo": "2025-10", "valor": 10.0, "unidad": "u",
                 "banda_inferior": None, "banda_superior": None}]
        man = {"corte": "2025-09-30", "origen": "2025-09", "modelo": {"version": "dm-prueba"}}
        obs = {o["universo"]: o for o in resultados_demanda({"tipo": "sombra", "id": "x"}, man, pron, cal, datos)}
        cop, uni = obs["ventas_cop"], obs["ventas_unidades:P1"]
        self.assertEqual((cop["madurez"], cop["conteos"]["observados"], cop["conteos"]["objetivos"]), ("parcial", 1, 2))  # noviembre aún no observado
        self.assertEqual(cop["metricas"]["mae"]["valor"], 500.0)                       # |1500 − 2000|
        self.assertEqual(cop["metricas"]["sesgo"]["valor"], -500.0)                    # error firmado
        self.assertEqual(cop["metricas"]["wape"]["valor"], 0.25)
        self.assertEqual(cop["metricas"]["mae"]["referencia"]["valor"], 1200.0)        # A08: media de 700, 800, 900 = 800 → |800 − 2000|
        self.assertEqual((cop["metricas"]["cobertura_banda"]["numerador"], cop["metricas"]["cobertura_banda"]["denominador"]), (1, 1))
        self.assertEqual((uni["metricas"]["mae"]["valor"], uni["metricas"]["mae"]["unidad"]), (10.0, "u"))  # unidades aparte, nunca sumadas a COP
        self.assertIsNone(uni["metricas"]["cobertura_banda"]["valor"])                 # sin banda publicada: nulo con motivo
        self.assertTrue(uni["metricas"]["cobertura_banda"]["motivo"])

    def test_m5_unidades_separadas_y_restriccion_cop(self):
        from api.monitoreo_modelos import obs_demanda
        f = lambda sid, u, v: {"serie_id": sid, "unidad": u, "valor": v, "estado": "estimado" if v is not None else "sin_historia",  # noqa: E731
                               "motivos": [] if v is not None else ["sin historia"], "banda_inferior": None}
        man = {"corte": "2026-10-31", "origen": "2026-10", "modelo": {"version": "dm-x"}}
        obs = obs_demanda({"tipo": "sombra", "id": "x"}, man, [f("ventas_cop:Software", "COP", 1.0), f("ventas_unidades:PRO01", "cantidad", 2.0),
                                                               f("ventas_unidades:PRO02", "cantidad", None)])
        por = {o["universo"]: o for o in obs}
        self.assertEqual(set(por), {"ventas_cop", "ventas_unidades:PRO01", "ventas_unidades:PRO02"})  # productos nunca agregados
        self.assertEqual((por["ventas_cop"]["restriccion"], por["ventas_unidades:PRO01"]["restriccion"]), ("cop", "unidades"))
        self.assertEqual(por["ventas_unidades:PRO02"]["conteos"]["abstenciones_por_motivo"], {"sin historia": 1})


# ---------------------------------------------------------------------------------------------------------------- API
from _apoyo_app import CasoBase  # noqa: E402

SOMBRAS = RAIZ / "salida" / "sombra"


@unittest.skipUnless((SOMBRAS / "demanda" / "2026-10" / "manifiesto.json").exists() and (SOMBRAS / "inactividad_60d_m21" / "2026-10-31-con-resumen").exists(),
                     "Requiere las publicaciones en sombra locales")
class MonitoreoApiTests(CasoBase):
    def importar(self):
        from api import demanda, prevencion
        r1 = prevencion.importar_sombra(self.db, SOMBRAS / "inactividad_60d_m21" / "2026-10-31-con-resumen", "ops1")
        r2 = demanda.importar_sombra(self.db, SOMBRAS / "demanda" / "2026-10", "ops1")
        return r1, r2

    def test_permisos_cop_portal_y_estados(self):
        self.importar()
        for u in ("ventas1", "aten1", "cli_a"):
            self.assertEqual(self.http("GET", "/api/monitoreo", como=u)[0], 403, u)
            self.assertEqual(self.http("GET", "/api/monitoreo/exportar.csv", como=u)[0], 403, u)
        st, d = self.http("GET", "/api/monitoreo", como="fin1")
        self.assertEqual({m["modelo_id"] for m in d["modelos"]}, {"demanda", "anomalias"})        # Finanzas: sin modelos de clientes
        dm = next(m for m in d["modelos"] if m["modelo_id"] == "demanda")
        self.assertTrue(any(o["restriccion"] == "cop" for o in dm["salud"]))
        st, d = self.http("GET", "/api/monitoreo", como="ops1")
        dm = next(m for m in d["modelos"] if m["modelo_id"] == "demanda")
        self.assertFalse(any(o["restriccion"] == "cop" for o in dm["salud"]))                   # Operaciones: solo unidades
        self.assertEqual(self.http("GET", "/api/monitoreo?modelo=compra_30d", como="fin1")[0], 403)
        estados = {m["modelo_id"]: m["estado"] for m in d["modelos"]}
        self.assertEqual(estados["inactividad_60d"], "pendiente_madurez")                       # nunca «saludable» sin resultados
        self.assertEqual(estados["proxima_compra"], "sin_informacion")
        csv = self.http("GET", "/api/monitoreo/exportar.csv", como="ops1")[1]
        self.assertNotIn("ventas_cop", str(csv))

    def test_reimportacion_integridad_reconocimiento_e_historial(self):
        from api import prevencion
        from api.base import ErrorApi
        self.importar()
        with self.db.conexion() as con:
            n = con.execute("SELECT count(*) FROM monitoreo_observaciones").fetchone()[0]
        self.importar()
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM monitoreo_observaciones").fetchone()[0], n)  # sin duplicados
        d = self.tmp / "alterada"
        shutil.copytree(SOMBRAS / "inactividad_60d_m21" / "2026-10-31-con-resumen", d)
        p = d / "predicciones_clientes.json"
        p.write_text(p.read_text(encoding="utf-8").replace('"estado": "estimado"', '"estado": "estructural"', 1), encoding="utf-8")
        with self.assertRaises(ErrorApi):
            prevencion.importar_sombra(self.db, d, "ops1")
        st, panel = self.http("GET", "/api/monitoreo?modelo=inactividad_60d", como="ops1")
        m = panel["modelos"][0]
        self.assertEqual(m["estado"], "publicacion_rechazada")
        clave = next(a["clave"] for a in m["avisos_activos"] if a["severidad"] == "integridad")
        self.assertEqual(self.http("POST", "/api/monitoreo/aviso", {"clave": clave, "accion": "reconocido", "motivo": "x"}, como="fin1")[0], 403)
        self.assertEqual(self.http("POST", "/api/monitoreo/aviso", {"clave": clave, "accion": "reconocido", "motivo": ""}, como="ops1")[0], 400)
        st, r = self.http("POST", "/api/monitoreo/aviso", {"clave": clave, "accion": "reconocido", "motivo": "Revisando el lote"}, como="ops1")
        self.assertEqual((st, r["estado"]), (200, "reconocido"))
        self.assertEqual(self.http("GET", "/api/monitoreo?modelo=inactividad_60d", como="ops1")[1]["modelos"][0]["estado"], "publicacion_rechazada")  # reconocer ≠ resolver
        self.http("POST", "/api/monitoreo/aviso", {"clave": clave, "accion": "resuelto", "motivo": "Lote corregido y reimportado"}, como="ops1")
        st, det = self.http("GET", f"/api/monitoreo/aviso?clave={clave}", como="ger1")
        self.assertEqual([e["accion"] for e in det["historial"]], ["creado", "reconocido", "resuelto"])
        self.assertIn("errores", det["aviso"]["datos"])                                         # el aviso original se conserva
        self.assertEqual(self.http("GET", "/api/monitoreo?modelo=inactividad_60d", como="ops1")[1]["modelos"][0]["estado"], "pendiente_madurez")

    def test_resultados_maduros_desde_la_cli_y_cierre_m1(self):
        from api import monitoreo_modelos as MM
        from api.publicacion import publicar_ruta
        from contratos.validar import validar_publicacion
        cierre = next((d for d in sorted((RAIZ / "salida" / "cierres").glob("cierre-2026-10-31-*")) if (d / "predicciones_clientes.json").exists()
                       and validar_publicacion(d)[0].valido), None)
        if cierre is None:
            self.skipTest("Sin cierre C2 local válido con predicciones")
        publicar_ruta(self.db, cierre, "ops1")
        self.importar()
        datos = _datos([], date(2026, 10, 31))
        r = MM.resultados(self.db, datos)
        self.assertEqual(r["avisos_nuevos"], [])
        st, d = self.http("GET", "/api/monitoreo?modelo=compra_30d", como="ger1")
        m = d["modelos"][0]
        self.assertEqual(m["salud"][0]["datos"]["conteos"]["elegibles"], 120)
        self.assertEqual([o["madurez"] for o in m["desempeno"]], ["pendiente"])                 # corte 31-10, datos hasta 31-10
        self.assertEqual(m["estado"], "pendiente_madurez")
        self.assertEqual(MM.resultados(self.db, datos)["observaciones"], {"existente": sum(r["observaciones"].values())})  # idempotente
        agosto = next(iter(sorted((RAIZ / "salida" / "cierres").glob("cierre-2026-08-31-*"))), None)
        if agosto and validar_publicacion(agosto)[0].valido:  # maduro pero todo en abstención (modelo no disponible): «sin información»
            publicar_ruta(self.db, agosto, "ops1")
            MM.resultados(self.db, _datos([], date(2026, 10, 31)))
            from api import monitoreo as MON
            with self.db.conexion() as con:
                obs = [dict(r) for r in con.execute("SELECT * FROM monitoreo_observaciones WHERE modelo_id = 'compra_30d' AND corte = '2026-08-31'")]
                self.assertTrue(any(o["grupo"] == "desempeno" and o["madurez"] == "madura" for o in obs))
                self.assertEqual(MON.estado_modelo([o for o in obs], []), "sin_informacion")


if __name__ == "__main__":
    unittest.main()
