"""M4 · venta cruzada: candidatos, etiquetas, estadísticas sin fuga, compatibilidad, ranking, métricas con abstención,
artefacto, integridad, contrato C2, API (permisos, revisión, episodios, importación fuera de orden) y control A07."""
import copy
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
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None
C = date(2026, 5, 31)
CAT = {p: {"nombre_prueba": f"Producto {p}", "familia_prueba": f} for p, f in (("P1", "A"), ("P2", "A"), ("P3", "B"), ("P4", "C"))}
REGLAS = {"version": "compat-test", "reglas": []}


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _c(fecha, p, imp=100.0):
    return {"fecha": fecha, "producto_id": p, "importe_cop": imp, "venta_id": f"{p}{fecha}"}


def _otros():  # clientes de referencia para que todos los productos estén disponibles y tengan popularidad
    return {"X1": [_c(date(2025, 3, 1), "P1"), _c(date(2025, 3, 2), "P2"), _c(date(2025, 3, 3), "P3")],
            "X2": [_c(date(2025, 3, 1), "P1"), _c(date(2025, 3, 5), "P3"), _c(date(2025, 3, 6), "P4")],
            "X3": [_c(date(2025, 3, 1), "P2")]}


class CandidatosTests(unittest.TestCase):
    def cand(self, compras_a, inst=(), reglas=REGLAS, corte=C, otros=None):
        from modelos.venta_cruzada import candidatos_cliente, estadisticas
        compras = (otros or _otros()) | {"A": compras_a}
        return candidatos_cliente("A", compras_a, list(inst), estadisticas(compras, corte), CAT, reglas, corte)

    def test_compra_posterior_cambia_etiqueta_pero_no_candidatura_ni_estadisticas(self):
        from modelos.venta_cruzada import estadisticas, etiqueta
        base = [_c(date(2026, 1, 10), "P1")]
        futura = base + [_c(C + timedelta(days=10), "P3")]
        self.assertEqual(self.cand(base), self.cand(futura))
        self.assertEqual(estadisticas(_otros() | {"A": base}, C), estadisticas(_otros() | {"A": futura}, C))
        self.assertEqual((etiqueta(base, "P3", C, date(2026, 10, 31)), etiqueta(futura, "P3", C, date(2026, 10, 31))), (0, 1))

    def test_compra_en_c_excluye_y_compra_de_otro_producto_no_cambia_etiqueta(self):
        from modelos.venta_cruzada import etiqueta
        r = self.cand([_c(date(2026, 1, 10), "P1"), _c(C, "P3")])
        self.assertIn({"producto_id": "P3", "motivo": "ya_comprado"}, r["exclusiones"])
        compras = [_c(date(2026, 1, 10), "P1"), _c(C + timedelta(days=5), "P4"), _c(C + timedelta(days=6), "P2"), _c(C + timedelta(days=9), "P2")]
        self.assertEqual(etiqueta(compras, "P3", C, date(2026, 10, 31)), 0)
        self.assertEqual(etiqueta(compras, "P2", C, date(2026, 10, 31)), 1)  # dos compras futuras = un positivo
        self.assertEqual(etiqueta(compras, "P2", C, C + timedelta(days=59)), None)  # horizonte incompleto
        self.assertEqual(etiqueta([_c(C + timedelta(days=60), "P2")], "P2", C, date(2026, 10, 31)), 1)
        self.assertEqual(etiqueta([_c(C + timedelta(days=61), "P2")], "P2", C, date(2026, 10, 31)), 0)

    def test_cobertura_vigente_sin_factura_y_fronteras(self):
        def inst(ini, fin):
            return [{"instalacion_id": "I1", "producto_id": "P3", "fecha_inicio": ini, "fecha_fin": fin}]
        compras = [_c(date(2026, 1, 10), "P1")]
        self.assertEqual(self.cand(compras, inst(date(2026, 1, 1), C))["exclusiones"][-1]["motivo"], "cobertura_vigente")  # fin == corte: vigente
        self.assertIn("P3", [x["producto_id"] for x in self.cand(compras, inst(date(2026, 1, 1), C - timedelta(days=1)))["candidatos"]])
        self.assertIn("P3", [x["producto_id"] for x in self.cand(compras, inst(C + timedelta(days=1), date(2027, 1, 1)))["candidatos"]])  # aún no conocida

    def test_compatibilidad_incompatible_requisito_desconocido_y_confirmada(self):
        compras = [_c(date(2026, 1, 10), "P1")]
        reglas = {"version": "t", "reglas": [{"tipo": "incompatible", "producto": "P3", "con": "P1", "evidencia": "ficha técnica"},
                                             {"tipo": "requiere", "producto": "P4", "requiere_alguno": ["P2"], "evidencia": "manual"},
                                             {"tipo": "compatible_confirmado", "producto": "P2", "evidencia": "acta"}]}
        r = self.cand(compras, reglas=reglas)
        self.assertEqual({e["producto_id"] for e in r["exclusiones"] if e["motivo"] == "incompatible_o_requisito"}, {"P3", "P4"})
        self.assertEqual(r["candidatos"], [{"producto_id": "P2", "estado_compatibilidad": "confirmada"}])
        self.assertEqual({c["estado_compatibilidad"] for c in self.cand(compras)["candidatos"]}, {"pendiente_revision"})  # desconocido ≠ compatible

    def test_catalogo_nuevo_no_disponible_al_corte(self):
        otros = {"X1": [_c(date(2025, 3, 1), "P1")], "X2": [_c(C + timedelta(days=3), "P4")]}
        r = self.cand([_c(date(2026, 1, 10), "P1")], otros=otros)
        self.assertIn({"producto_id": "P4", "motivo": "no_disponible_al_corte"}, r["exclusiones"])  # su primera venta es futura


def _art(pesos_producto, soporte, variables=("popularidad_rel",)):
    from modelos.inferencia import desde_dict, sellar
    tr = [{"variable": v, "funcion": "identidad", "media": 0.0, "desviacion": 1.0, "imputacion": 0.0} for v in variables]
    return desde_dict(sellar({"formato": "jacomind.venta_cruzada_logistica.v1", "modelo_id": "venta_cruzada", "version": "vc-test", "horizonte_dias": 60,
                              "umbral": None, "variables": list(variables), "transformaciones": tr, "pesos": [0.0] * len(variables), "pesos_producto": pesos_producto,
                              "intercepto": 0.0, "soporte": {p: {"positivos": n} for p, n in soporte.items()}, "soporte_minimo": 10, "disponible_desde": "2026-10-31"}))


class RankingTests(unittest.TestCase):
    def pares(self, ids, pop=None):
        pop = pop or {}
        return [{"producto_id": p, "popularidad": pop.get(p, 1), "popularidad_rel": pop.get(p, 1) / 10, "coocurrencia_suma": 0, "coocurrencia_rel": 0.0,
                 "afinidad_max": 0.0, "estado_compatibilidad": "pendiente_revision"} for p in ids]

    def test_desempate_duplicados_menos_de_tres_y_fallback_sin_soporte(self):
        from modelos.venta_cruzada import ranking_modelo, ranking_referencia
        art = _art({"P1": 1.0, "P2": 1.0, "P3": 2.0}, {"P1": 12, "P2": 12, "P3": 12, "P9": 3})
        lista = ranking_modelo(art, self.pares(["P2", "P1", "P2"]))
        self.assertEqual([p["producto_id"] for p in lista], ["P1", "P2"])  # empate por producto_id, sin duplicados, solo 2
        lista = ranking_modelo(art, self.pares(["P1", "P9", "P3", "PX"], {"P9": 9, "PX": 1}))
        self.assertEqual([(p["producto_id"], p["origen"]) for p in lista], [("P3", "modelo"), ("P1", "modelo"), ("P9", "popularidad_sin_soporte")])
        self.assertEqual([p["producto_id"] for p in ranking_referencia(self.pares(["P2", "P1", "P3"], {"P3": 5}), "popularidad")], ["P3", "P1", "P2"])

    def test_incompatible_con_puntaje_maximo_no_aparece(self):
        from modelos.venta_cruzada import recomendaciones
        art = _art({"P3": 99.0, "P2": 0.1, "P4": 0.0}, {"P2": 20, "P3": 20, "P4": 20})
        reglas = {"version": "t", "reglas": [{"tipo": "incompatible", "producto": "P3", "con": "P1", "evidencia": "x"}]}
        compras = _otros() | {"A": [_c(date(2026, 1, 10), "P1")]}
        filas, cob = recomendaciones(art, [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}], compras, {}, CAT, reglas, C)
        self.assertNotIn("P3", [f["producto_id"] for f in filas])
        self.assertTrue(all(f["probabilidad"] is None for f in filas))

    def test_sin_historial_y_sin_candidatos_sin_filas_ficticias(self):
        from modelos.venta_cruzada import recomendaciones
        art = _art({}, {})
        compras = _otros() | {"LLENO": [_c(date(2026, 1, 1), p) for p in ("P1", "P2", "P3", "P4")]}
        clientes = [{"cliente_id": c, "fecha_alta": date(2025, 1, 1)} for c in ("LLENO", "NUEVO")] + [{"cliente_id": "FUT", "fecha_alta": date(2027, 1, 1)}]
        filas, cob = recomendaciones(art, clientes, compras, {}, CAT, REGLAS, C)
        self.assertEqual(filas, [])
        self.assertEqual({c["cliente_id"]: c["estado"] for c in cob}, {"LLENO": "sin_candidatos", "NUEVO": "sin_historial", "FUT": "no_elegible"})
        self.assertTrue(all(c["motivo"] for c in cob))


class MetricasTests(unittest.TestCase):
    def test_denominadores_con_abstencion_contra_calculo_manual(self):
        from modelos.venta_cruzada_experimento import evaluar_metodo, resumir
        pares = [{"cliente_id": "A", "corte": C, "producto_id": "P1", "y": 1}, {"cliente_id": "A", "corte": C, "producto_id": "P2", "y": 0},
                 {"cliente_id": "B", "corte": C, "producto_id": "P1", "y": 0}, {"cliente_id": "B", "corte": C, "producto_id": "P3", "y": 1}]
        universo = [{"cliente_id": c, "corte": C, "n_candidatos": n, "comprados": [], "cubiertos": [], "excluidos": []} for c, n in (("A", 2), ("B", 2), ("Z", 0))]
        orden = lambda ps: sorted(ps, key=lambda p: p["producto_id"])  # noqa: E731
        r = resumir(evaluar_metodo({"pares": pares, "universo": universo}, orden))
        self.assertEqual((r["universo"], r["aciertos1"]), (3, 1))           # Z sin candidatos cuenta como fallo
        self.assertAlmostEqual(r["hitrate1_universo"], 1 / 3)
        self.assertAlmostEqual(r["hitrate1_con_candidatos"], 1 / 2)
        self.assertAlmostEqual(r["hitrate3_universo"], 2 / 3)
        self.assertAlmostEqual(r["precision3"], 2 / 4)                       # 4 productos sugeridos
        self.assertAlmostEqual(r["ndcg3"], (1.0 + 1 / 1.5849625007211562) / 2)  # B: acierto en la posición 2
        self.assertAlmostEqual(r["cobertura_clientes"], 2 / 3)
        self.assertEqual(r["sin_candidatos"], 1)


class ContratoTests(unittest.TestCase):
    def pub(self, recs, cob):
        from contratos.validar import validar_publicacion_sombra
        man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "venta_cruzada", "corte": "2026-10-31", "estado_experimento": "x", "operativa": False,
               "modelo": {"version": "v", "artefacto_huella": "f" * 64}, "versiones": {"reglas": "r", "catalogo": "c"},
               "cobertura": {"corte": "2026-10-31", "datos_observados_hasta": "2026-10-31", "fuente": "t", "estado": "verificada"},
               "tablas": {"recomendaciones_productos": {"filas": len(recs)}, "cobertura_recomendaciones": {"filas": len(cob)}}}
        return validar_publicacion_sombra(man, {"recomendaciones_productos": recs, "cobertura_recomendaciones": cob})

    def fila(self, p, pos, pt, **k):
        return {"cliente_id": "A", "producto_id": p, "modelo_id": "venta_cruzada", "corte": "2026-10-31", "horizonte_dias": 60, "version_modelo": "v",
                "posicion": pos, "puntaje": pt, "probabilidad": None, "origen_recomendacion": "modelo", "soporte": 12, "definicion_soporte": "d",
                "estado": "propuesta", "estado_compatibilidad": "pendiente_revision", "motivos": ["m"], "version_reglas": "r", "version_catalogo": "c"} | k

    def cob(self, n, excl=()):
        return [{"cliente_id": "A", "modelo_id": "venta_cruzada", "corte": "2026-10-31", "estado": "con_recomendaciones", "n_candidatos": 4,
                 "n_recomendaciones": n, "exclusiones": [{"producto_id": e, "motivo": "ya_comprado"} for e in excl], "motivo": None}]

    def test_valido_y_violaciones(self):
        ok = [self.fila("P2", 1, 0.9), self.fila("P3", 2, 0.5)]
        self.assertEqual(self.pub(ok, self.cob(2, ["P1"])), [])
        malos = [([self.fila("P1", 1, 0.9)], self.cob(1, ["P1"])),                                   # producto excluido
                 ([self.fila("P2", 1, 0.1), self.fila("P3", 2, 0.5)], self.cob(2)),                    # posiciones contra el ranking
                 ([self.fila(p, i, 1 - i / 10) for i, p in enumerate(["P2", "P3", "P4", "P5"], 1)], self.cob(4)),  # más de tres
                 ([self.fila("P2", 1, 0.9), self.fila("P2", 2, 0.5)], self.cob(2)),                    # clave repetida
                 ([self.fila("P2", 2, 0.9)], self.cob(1)),                                             # posición no 1..n
                 ([self.fila("P2", 1, float("nan"))], self.cob(1)),
                 ([self.fila("P2", 1, 0.9, probabilidad=1.5)], self.cob(1)),
                 ([], [dict(self.cob(0)[0], estado="sin_candidatos", motivo=None)])]                 # lista vacía sin motivo
        for recs, cob in malos:
            with self.subTest(recs=recs):
                self.assertTrue(self.pub(recs, cob))


class SinDependenciasTests(unittest.TestCase):
    def test_api_y_cierre_sin_librerias_de_entrenamiento(self):
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy', 'sksurv', 'pandas'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.venta_cruzada, modelos.venta_cruzada, pipeline.generar\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y scikit-learn")
class ExperimentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.venta_cruzada_experimento import cargar_config, entrenar
        cls.tmp = Path(tempfile.mkdtemp(prefix="m4-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cfg = cargar_config()
        cfg["metricas"]["bootstrap"]["repeticiones"] = 50  # rapidez: otra configuración, otra carpeta
        cls.config = cfg
        cls.r = entrenar(cls.datos, cfg, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_control_familias_reproducido(self):
        ctl = json.loads((self.tmp / "e1" / "control_familias.json").read_text(encoding="utf-8"))
        self.assertEqual((ctl["corte"], ctl["coocurrencia"]["aciertos"], ctl["coocurrencia"]["clientes_evaluados"], ctl["popularidad"]["aciertos"]),
                         ("2026-09-01", 11, 69, 11))

    def test_fronteras_seleccion_equivalencia_y_reproducibilidad(self):
        from modelos.ejecucion import EjecucionError
        from modelos.venta_cruzada_experimento import entrenar
        self.assertEqual(self.r["fronteras"]["ajuste->validacion"]["ultima_etiqueta_madura"], "2026-04-29")
        sel = self.r["seleccion"]
        self.assertTrue(all(c["equivalencia_json_sklearn"]["diferencia_maxima"] < 1e-9 for c in sel["candidatos"].values()))
        art = json.loads((self.tmp / "e1" / "artefacto.json").read_text(encoding="utf-8"))
        self.assertEqual(art["huella"], sel["elegido_artefacto_huella"])
        self.assertEqual(entrenar(self.datos, self.config, self.tmp / "e2")["congelacion"]["sello"], self.r["congelacion"]["sello"])
        otra = copy.deepcopy(self.config)
        otra["candidato"]["C"] = [5]
        with self.assertRaises(EjecucionError):
            entrenar(self.datos, otra, self.tmp / "e1")

    def test_recuperacion_idempotencia_y_evidencia_alterada(self):
        from modelos import ejecucion
        from modelos.compra import ProtocoloError
        from modelos.venta_cruzada_experimento import evaluar, verificar_congelacion
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        for archivo in ("metricas_comprobacion_historica.json", "decision.json"):  # interrupción antes y después de métricas
            ejecucion.FALLO_SIMULADO = archivo
            with self.assertRaises(RuntimeError):
                evaluar(d, self.datos)
        ejecucion.FALLO_SIMULADO = None
        a, b = evaluar(d, self.datos), evaluar(d, self.datos)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        self.assertEqual(a["metricas"]["resultados"]["modelo"]["violaciones"], 0)
        x = self.tmp / "alt"
        shutil.copytree(self.tmp / "e1", x)
        (x / "reglas_compatibilidad.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            verificar_congelacion(x)

    def test_sombra_contrato_muestra_y_manifiesto_alterado(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.inferencia import cargar_artefacto
        from modelos.venta_cruzada import puntuar_sombra
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="venta_cruzada")
        out = self.tmp / "sombra"
        r1 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental", metodo="popularidad")
        r2 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental", metodo="popularidad")
        self.assertEqual(r1["manifiesto"]["sello"], r2["manifiesto"]["sello"])
        errores, man, tablas = leer_publicacion_sombra(out)
        self.assertEqual(errores, [])
        self.assertLessEqual(len(tablas["muestra_revision"]["pares"]), 30)
        self.assertEqual(len(tablas["cobertura_recomendaciones"]), 120)
        m = json.loads((out / "manifiesto.json").read_text(encoding="utf-8"))
        m["estado_experimento"] = "operativo"
        (out / "manifiesto.json").write_text(json.dumps(m), encoding="utf-8")
        self.assertTrue(leer_publicacion_sombra(out)[0])


# ------------------------------------------------------------------------------------------------- API
from _apoyo_app import CasoBase  # noqa: E402


def _publicar_vc(directorio, corte, recs, cobertura, muestra=None):
    from modelos.ejecucion import json_bytes, publicar_lote
    archivos = {"recomendaciones_productos.json": json_bytes(recs), "cobertura_recomendaciones.json": json_bytes(cobertura)}
    if muestra:
        archivos["muestra_revision.json"] = json_bytes(muestra)
    conteos = {}
    for c in cobertura:
        conteos[c["estado"]] = conteos.get(c["estado"], 0) + 1
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "venta_cruzada", "corte": corte.isoformat(), "estado_experimento": "experimental en sombra · prueba",
           "operativa": False, "modelo": {"version": "vc-fx", "artefacto_huella": "f" * 64, "sistema_publicado": "popularidad"},
           "versiones": {"reglas": "r", "catalogo": "c"}, "conteos": conteos,
           "cobertura": {"corte": corte.isoformat(), "datos_observados_hasta": corte.isoformat(), "fuente": "prueba", "estado": "verificada"},
           "tablas": {"recomendaciones_productos": {"filas": len(recs)}, "cobertura_recomendaciones": {"filas": len(cobertura)}}}
    publicar_lote(directorio, archivos, "manifiesto.json", man)
    return directorio


def _fx(corte, comprados_demo05=()):
    f = lambda c, p, pos, pt: {"cliente_id": c, "producto_id": p, "producto_nombre": p, "modelo_id": "venta_cruzada", "corte": corte.isoformat(), "horizonte_dias": 60,  # noqa: E731
                               "version_modelo": "vc-fx", "posicion": pos, "puntaje": pt, "probabilidad": None, "origen_recomendacion": "popularidad", "soporte": 30,
                               "definicion_soporte": "d", "estado": "propuesta", "estado_compatibilidad": "pendiente_revision", "motivos": ["evidencia"],
                               "version_reglas": "r", "version_catalogo": "c"}
    recs = [f("DEMO02", "PRO05", 1, 0.9), f("DEMO02", "PRO07", 2, 0.5)] + ([] if "PRO04" in comprados_demo05 else [f("DEMO05", "PRO04", 1, 0.8)])
    cob = [{"cliente_id": "DEMO02", "modelo_id": "venta_cruzada", "corte": corte.isoformat(), "estado": "con_recomendaciones", "n_candidatos": 3, "n_recomendaciones": 2, "exclusiones": [], "motivo": None},
           {"cliente_id": "DEMO05", "modelo_id": "venta_cruzada", "corte": corte.isoformat(), "estado": "con_recomendaciones" if "PRO04" not in comprados_demo05 else "sin_candidatos",
            "n_candidatos": 1 if "PRO04" not in comprados_demo05 else 0, "n_recomendaciones": 0 if "PRO04" in comprados_demo05 else 1,
            "exclusiones": [{"producto_id": p, "motivo": "ya_comprado"} for p in comprados_demo05], "motivo": "Todos comprados" if "PRO04" in comprados_demo05 else None},
           {"cliente_id": "DEMO04", "modelo_id": "venta_cruzada", "corte": corte.isoformat(), "estado": "sin_historial", "n_candidatos": 0, "n_recomendaciones": 0, "exclusiones": [], "motivo": "Sin compras"}]
    muestra = {"semilla": 1, "universo": "fx", "criterio": "fx", "tamano_objetivo": 30, "pares": [{"cliente_id": "DEMO02", "producto_id": "PRO05", "posicion": 1, "puntaje": 0.9, "familia": "Servicios",
                                                                                                   "tercil_puntaje": 3, "version_propuesta": "vc-fx"}]}
    return recs, cob, muestra


class VentaCruzadaApiTests(CasoBase):
    def importar(self, nombre, corte, comprados=()):
        from api import venta_cruzada
        recs, cob, muestra = _fx(corte, comprados)
        return venta_cruzada.importar_sombra(self.db, _publicar_vc(self.tmp / nombre, corte, recs, cob, muestra), "ops1")

    def test_permisos_portal_y_ficha_coexistente(self):
        from api.permisos import MATRIZ
        for rol, u in {"operaciones": "ops1", "ventas": "ventas1", "finanzas": "fin1", "atencion": "aten1", "gerencia": "ger1", "empresa": "cli_a"}.items():
            self.assertEqual(self.http("GET", "/api/venta-cruzada", como=u)[0], 200 if rol in MATRIZ["venta_cruzada.ver"] else 403, rol)
        _, antes = self.http("GET", "/api/cierres/activo/clientes/DEMO02", como="ventas1")
        self.importar("s1", date(2026, 11, 30))
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO02", como="ventas1")
        self.assertEqual([i["producto_id"] for i in f["venta_cruzada_sombra"]["items"]], ["PRO05", "PRO07"])
        for k in ("cliente", "prediccion"):
            self.assertEqual(f.get(k), antes.get(k))  # agenda C1 y M1 intactos
        self.assertIn("proxima_sombra", f)
        self.assertIn("inactividad_sombra", f)
        _, portal = self.http("GET", "/api/portal/beneficios", como="cli_a")
        self.assertNotIn("venta_cruzada", json.dumps(portal).lower())
        self.assertEqual(self.http("POST", "/api/venta-cruzada/decision", {"cliente_id": "DEMO02", "producto_id": "PRO05", "accion": "aceptar", "motivo": "x"}, como="ops1")[0], 403)

    def test_importacion_fuera_de_orden(self):
        self.assertTrue(self.importar("dic", date(2026, 12, 31))["activa"])
        self.assertFalse(self.importar("nov", date(2026, 11, 30))["activa"])
        _, d = self.http("GET", "/api/venta-cruzada", como="ventas1")
        self.assertEqual(d["sombra"]["corte"], "2026-12-31")

    def test_revision_humana_denominadores(self):
        self.importar("s1", date(2026, 11, 30))
        _, r = self.http("GET", "/api/venta-cruzada/revision", como="ventas1")
        self.assertEqual((r["resumen"]["total_muestra"], r["resumen"]["revisados"], r["resumen"]["pertinencia_entre_evaluables"]), (1, 0, None))
        self.assertEqual(self.http("POST", "/api/venta-cruzada/revision", {"cliente_id": "DEMO05", "producto_id": "PRO04", "estado": "pertinente", "motivo": "x"}, como="ventas1")[0], 404)
        st, _ = self.http("POST", "/api/venta-cruzada/revision", {"cliente_id": "DEMO02", "producto_id": "PRO05", "estado": "informacion_insuficiente", "motivo": "falta ficha"}, como="ventas1")
        self.assertEqual(st, 200)
        _, r = self.http("GET", "/api/venta-cruzada/revision", como="ventas1")
        self.assertEqual((r["resumen"]["revisados"], r["resumen"]["evaluables"], r["resumen"]["proporcion_informacion_insuficiente"]), (1, 0, 1.0))
        self.assertEqual(r["pares"][0]["revision"]["revisor"], "ventas1")

    def test_episodios_descartado_no_se_reabre_y_compra_cierra_conservando_resultados(self):
        from api import operacion, venta_cruzada
        from api.auth import cargar_usuario
        self.importar("s1", date(2026, 11, 30))
        d = lambda c, p, a: self.http("POST", "/api/venta-cruzada/decision", {"cliente_id": c, "producto_id": p, "accion": a, "motivo": "motivo"}, como="ventas1")  # noqa: E731
        self.assertEqual(d("DEMO02", "PRO07", "descartar")[0], 200)
        self.assertEqual(d("DEMO02", "PRO07", "aceptar")[0], 409)
        self.importar("s2", date(2026, 12, 31))  # otro corte, mismo producto: el episodio sigue descartado
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO02", como="ventas1")
        self.assertEqual([i["episodio"]["estado"] for i in f["venta_cruzada_sombra"]["items"] if i["producto_id"] == "PRO07"], ["descartada"])
        self.assertEqual(d("DEMO05", "PRO04", "aceptar")[0], 200)
        r = venta_cruzada.sincronizar(self.db, "ops1")
        self.assertFalse(r["activada"])
        with self.db.conexion() as con:
            operacion.fijar_bandera(self.db, cargar_usuario(con, "ops1"), "venta_cruzada_tareas", True)
        r1, r2 = venta_cruzada.sincronizar(self.db, "ops1"), venta_cruzada.sincronizar(self.db, "ops1")
        self.assertEqual(r1["tareas_nuevas"] + r1["compartidas"], 1)
        self.assertEqual(r2["tareas_nuevas"] + r2["compartidas"], 0)  # sin duplicados
        with self.db.transaccion() as con:
            ep = con.execute("SELECT * FROM episodios_venta_cruzada WHERE cliente_id='DEMO05'").fetchone()
            con.execute("UPDATE tareas SET resultado = 'contactado', responsable_id = 'ventas1' WHERE id = ?", (ep["tarea_id"],))
        self.importar("s3", date(2027, 1, 31), comprados=("PRO04",))
        self.assertEqual(venta_cruzada.sincronizar(self.db, "ops1")["cerrados_compra"], 1)
        with self.db.conexion() as con:
            ep = con.execute("SELECT * FROM episodios_venta_cruzada WHERE cliente_id='DEMO05'").fetchone()
            t = con.execute("SELECT * FROM tareas WHERE id = ?", (ep["tarea_id"],)).fetchone()
        self.assertEqual(ep["estado"], "cerrada_compra")
        self.assertEqual((t["resultado"], t["responsable_id"]), ("contactado", "ventas1"))


if __name__ == "__main__":
    unittest.main()
