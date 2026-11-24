"""M6 · operaciones atípicas: exclusiones A01/anuladas, identidad (tipo, ID), historia estrictamente anterior y bloque diario,
abstención, MAD cero, TRM, contexto por producto, respaldo documentado, cupo y desempate, inferencia JSON (float32 y
equivalencia con scikit-learn), casos sembrados sin contaminación, separación temporal, integridad (alteraciones,
interrupción, idempotencia), contrato C2, persistencia de casos y eventos, permisos, portal y ausencia de dependencias."""
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))
HAY_SK = importlib.util.find_spec("sklearn") is not None
CFG = json.loads((RAIZ / "modelos" / "config" / "anomalias.json").read_text(encoding="utf-8"))


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def V(vid, f, p="P1", q=4, precio="100", mon="COP", est="Confirmada", cli="C1"):
    return {"venta_id": vid, "fecha": f, "cliente_id": cli, "producto_id": p, "cantidad": q, "moneda": mon, "precio_unitario": Decimal(precio),
            "descuento_pct": Decimal("0"), "estado": est}


def C(cid, f, p="P1", q=10, costo="60", mon="COP", prv="PRV1"):
    return {"compra_id": cid, "fecha": f, "proveedor_id": prv, "producto_id": p, "cantidad": q, "moneda": mon, "costo_unitario": Decimal(costo)}


D0 = date(2025, 1, 1)


def dia(n):
    return D0 + timedelta(days=n)


def preparar_ops(ventas, compras=(), tasas=None, cfg=CFG):
    from modelos import anomalias as A
    ops, excl = A.operaciones(ventas, list(compras), tasas or {}, cfg)
    return ops, excl, A.Historial(ops, cfg["contexto"]["ventana_antecedentes"])


class ExclusionesIdentidadTests(unittest.TestCase):
    def test_anuladas_dominio_y_colision_de_ids(self):
        ops, excl, _ = preparar_ops([V("X1", dia(0)), V("X2", dia(1), est="Anulada"), V("X3", dia(2), q=0)], [C("X1", dia(0))])
        self.assertEqual({(o["tipo_operacion"], o["operacion_id"]) for o in ops}, {("venta", "X1"), ("compra", "X1")})  # mismo ID, sin colisión
        self.assertEqual(sorted(e["motivo"] for e in excl), ["fuera_de_dominio", "venta_anulada"])  # nunca anomalías comerciales
        compra = next(o for o in ops if o["tipo_operacion"] == "compra")
        self.assertIsNone(compra["cliente_id"])
        self.assertEqual(compra["proveedor_id"], "PRV1")

    def test_duplicado_tras_a01_impide_puntuar(self):
        from modelos import anomalias as A
        with self.assertRaises(ValueError):
            A.operaciones([V("X1", dia(0)), V("X1", dia(1))], [], {}, CFG)


class ContextoTests(unittest.TestCase):
    def test_historia_estrictamente_anterior_bloque_diario_y_futuras(self):
        from modelos import anomalias as A
        ventas = [V(f"A{i}", dia(i), q=3 + i % 3) for i in range(6)] + [V("B1", dia(6), q=4), V("B2", dia(6), q=400)]
        ops, _, h = preparar_ops(ventas)
        b1 = next(o for o in ops if o["operacion_id"] == "B1")
        c = A.contexto(b1, h, CFG)
        self.assertEqual(c["soporte"], 6)                       # B2 (mismo día, extrema) no es antecedente de B1
        self.assertLess(abs(c["variables"]["z_log_cantidad"]), 2)
        a5 = next(o for o in ops if o["operacion_id"] == "A5")
        antes = A.contexto(a5, h, CFG)
        ops2, _, h2 = preparar_ops(ventas + [V(f"F{i}", dia(30 + i), q=999, precio="5000") for i in range(10)])
        self.assertEqual(A.contexto(a5, h2, CFG), antes)        # agregar operaciones futuras no cambia el pasado

    def test_historia_insuficiente_sin_puntaje_y_mad_cero(self):
        from modelos import anomalias as A
        ops, _, h = preparar_ops([V(f"A{i}", dia(i)) for i in range(4)] + [V("Z", dia(10), precio="100"), V("Y", dia(10), precio="130")])
        a3 = next(o for o in ops if o["operacion_id"] == "A3")
        c = A.contexto(a3, h, CFG)
        self.assertEqual((c["estado"], c["variables"]), ("historia_insuficiente", None))
        ops, _, h = preparar_ops([V(f"A{i}", dia(i)) for i in range(6)] + [V("Z", dia(10), precio="100"), V("Y", dia(10), precio="130"),
                                                                          V("W", dia(10), precio="1e9")])
        z, y, w = (A.contexto(next(o for o in ops if o["operacion_id"] == k), h, CFG) for k in ("Z", "Y", "W"))
        self.assertEqual(z["dispersion"]["mad_log_valor_unitario"], 0.0)       # grupo constante: MAD 0 → piso de escala
        self.assertEqual(z["variables"]["z_log_valor_unitario"], 0.0)
        self.assertAlmostEqual(y["variables"]["z_log_valor_unitario"], __import__("math").log(1.3) / CFG["contexto"]["piso_escala_log"], places=9)
        self.assertEqual(w["variables"]["z_log_valor_unitario"], CFG["contexto"]["z_max"])  # recorte, nunca infinito
        self.assertAlmostEqual(z["razon_valor_unitario"], 1.0)

    def test_trm_solo_cambia_cop_y_trm_ausente_explicita(self):
        from modelos import anomalias as A
        ventas = [V(f"A{i}", dia(i), mon="USD", precio=str(100 + i)) for i in range(6)] + [V("T", dia(8), mon="USD", precio="104")]
        tasas = {dia(i): Decimal("4000") for i in range(9)}
        ops, _, h = preparar_ops(ventas, tasas=tasas)
        t = next(o for o in ops if o["operacion_id"] == "T")
        t2 = dict(t, trm=t["trm"] * 1.3)
        t2["importe_cop"] = round(t2["importe_origen"] * t2["trm"], 2)
        c1, c2 = A.contexto(t, h, CFG), A.contexto(t2, h, CFG)
        self.assertNotEqual(t["importe_cop"], t2["importe_cop"])
        self.assertEqual(c1["variables"], c2["variables"])
        self.assertEqual(A.puntaje_referencia(c1["variables"]), A.puntaje_referencia(c2["variables"]))
        ops, _, h = preparar_ops(ventas, tasas={})
        t = next(o for o in ops if o["operacion_id"] == "T")
        self.assertEqual((t["estado_trm"], t["trm"], t["importe_cop"]), ("ausente", None, None))  # no se sustituye por cero
        self.assertEqual(A.contexto(t, h, CFG)["estado"], "puntuada")                             # la señal comercial no depende de la TRM

    def test_productos_de_precio_distinto_en_su_contexto(self):
        from modelos import anomalias as A
        ventas = [V(f"C{i}", dia(i), p="CARO", precio=str(1_000_000 + 1000 * (i % 3))) for i in range(8)] + \
                 [V(f"B{i}", dia(i), p="BARATO", precio=str(100 + i % 3)) for i in range(8)] + \
                 [V("CX", dia(20), p="CARO", precio="1001000"), V("BX", dia(20), p="BARATO", precio="202")]
        ops, _, h = preparar_ops(ventas)
        cx, bx = (A.contexto(next(o for o in ops if o["operacion_id"] == k), h, CFG) for k in ("CX", "BX"))
        self.assertLess(abs(cx["variables"]["z_log_valor_unitario"]), 1)    # caro pero habitual
        self.assertGreater(bx["variables"]["z_log_valor_unitario"], 10)     # barato pero ×2 en su contexto
        self.assertTrue(A.reglas(bx, CFG)["valor_unitario"] and not A.reglas(cx, CFG)["senalada"])
        self.assertIn("valor_unitario", A.motivos(next(o for o in ops if o["operacion_id"] == "BX"), bx, CFG)[1])

    def test_respaldo_solo_si_esta_documentado(self):
        from modelos import anomalias as A
        cfg = copy.deepcopy(CFG)
        ventas = [V(f"A{i}", dia(i), p="P1") for i in range(6)] + [V("N", dia(10), p="P2")]
        ops, _, h = preparar_ops(ventas, cfg=cfg)
        n = next(o for o in ops if o["operacion_id"] == "N")
        self.assertEqual(A.contexto(n, h, cfg)["estado"], "historia_insuficiente")
        cfg["contexto"]["respaldos"] = {"venta:P2": {"producto_id": "P1", "misma_unidad": True, "documentacion": "misma unidad y lista de precios (prueba)"}}
        cfg["unidades"]["por_producto"] = {"P1": "licencia", "P2": "licencia"}
        ops, _, h = preparar_ops(ventas, cfg=cfg)
        c = A.contexto(next(o for o in ops if o["operacion_id"] == "N"), h, cfg)
        self.assertEqual((c["estado"], c["respaldo"]["producto_id"]), ("puntuada", "P1"))


class CupoTests(unittest.TestCase):
    def test_cupo_desempate_estable_y_abstencion(self):
        from modelos import anomalias as A
        pol = CFG["politica_alertas"]
        self.assertEqual([A.cupo(n, pol) for n in (0, 1, 20, 21, 62)], [0, 1, 1, 2, 4])
        f = lambda i, s, fe: {"tipo_operacion": "venta", "operacion_id": i, "periodo": "2026-07", "fecha": fe, "puntaje": s}  # noqa: E731
        filas = [f("B", 2.0, "2026-07-02"), f("A", 2.0, "2026-07-02"), f("C", 2.0, "2026-07-01"), f("D", None, "2026-07-01")] + \
                [f(f"Z{i}", 0.1, "2026-07-03") for i in range(17)]
        A.priorizar(filas, pol)
        orden = {x["operacion_id"]: x["prioridad"] for x in filas}
        self.assertEqual((orden["C"], orden["A"], orden["B"], orden["D"]), (1, 2, 3, None))
        self.assertEqual([x["operacion_id"] for x in filas if x["alerta"]], ["C"])  # 20 puntuadas → cupo 1


class BosqueTests(unittest.TestCase):
    def arbol(self, umbral):
        from modelos.inferencia import huella_artefacto
        uni = {"metodo": "isolation_forest", "variables": ["z_log_valor_unitario", "z_log_cantidad"], "n_estimadores": 1, "max_muestras": 4,
               "arboles": [{"var": [0, 0, 0], "umbral": [umbral, 0.0, 0.0], "izq": [1, -1, -1], "der": [2, -1, -1], "n": [4, 1, 3]}]}
        art = {"formato": "jacomind.anomalias_iforest.v1", "modelo_id": "anomalias", "version": "m6-prueba", "umbral": None, "disponible_desde": "2026-11-23",
               "politica_alertas": CFG["politica_alertas"], "contexto": CFG["contexto"], "referencia": CFG["referencia"], "etiquetas_universos": CFG["universos"],
               "unidades": CFG["unidades"], "universos": {"venta": uni, "compra": {"metodo": "mediana_mad"}}}
        art["huella"] = huella_artefacto(art)
        return art

    def test_float32_umbral_hoja_y_alteraciones(self):
        from modelos import anomalias as A
        from modelos.inferencia import ArtefactoInvalido, desde_dict
        art = desde_dict(self.arbol(0.1))
        c = lambda n: A.longitud_media(n)  # noqa: E731
        izq = 2 ** (-((1 + c(1)) / c(4)))   # hoja de 1 muestra: profundidad 2 − 1 + c(1)
        der = 2 ** (-((1 + c(3)) / c(4)))
        self.assertAlmostEqual(art.rareza("venta", {"z_log_valor_unitario": 0.09, "z_log_cantidad": 0.0}), izq, places=15)  # x <= umbral → izquierda
        # scikit-learn convierte la entrada a float32: float32(0.1) = 0.10000000149 > 0.1 (umbral float64) → derecha
        self.assertGreater(A.a_float32(0.1), 0.1)
        self.assertAlmostEqual(art.rareza("venta", {"z_log_valor_unitario": 0.1, "z_log_cantidad": 0.0}), der, places=15)
        self.assertAlmostEqual(art.rareza("venta", {"z_log_valor_unitario": A.a_float32(0.1) - 1e-9, "z_log_cantidad": 0.0}),
                               art.rareza("venta", {"z_log_valor_unitario": 0.1, "z_log_cantidad": 0.0}), places=15)  # mismo float32
        self.assertAlmostEqual(art.rareza("venta", {"z_log_valor_unitario": 5.0, "z_log_cantidad": 0.0}), der, places=15)
        self.assertGreater(izq, der)  # aislar antes = más raro
        self.assertIsNone(art.rareza("compra", {"z_log_valor_unitario": 5.0, "z_log_cantidad": 0.0}))
        mal = self.arbol(0.1)
        mal["universos"]["venta"]["arboles"][0]["umbral"][0] = 9.0
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(mal)                                    # huella no coincide
        mal = self.arbol(0.1)
        mal["universos"]["venta"]["arboles"][0]["izq"][0] = 7
        from modelos.inferencia import huella_artefacto
        mal["huella"] = huella_artefacto(mal)
        self.assertTrue(any("fuera de rango" in e for e in A.validar_artefacto_anomalias(mal)))
        mal = self.arbol(0.1)
        mal["umbral"] = 0.5
        mal["huella"] = huella_artefacto(mal)
        self.assertTrue(A.validar_artefacto_anomalias(mal))


class MetricasRevisionTests(unittest.TestCase):
    def test_desconocidas_nulas_y_sin_revisar_no_son_falsas_alertas(self):
        from api.anomalias import metricas_revision
        filas = [{"tipo_operacion": "venta", "operacion_id": f"V{i}", "alerta": i < 3, "huella_valores": "h"} for i in range(10)]
        m = metricas_revision(filas, {}, {"min_revisiones_precision": 30})
        self.assertIsNone(m["precision_alertas_revisadas"]["valor"])
        self.assertIsNone(m["falsas_alertas_por_100_normales_revisadas"]["por_100"])
        self.assertTrue(m["precision_alertas_revisadas"]["motivo"])
        casos = {("venta", "V0"): {"estado": "error_confirmado", "huella_valores": "h"}, ("venta", "V1"): {"estado": "cambio_legitimo", "huella_valores": "h"},
                 ("venta", "V5"): {"estado": "cambio_legitimo", "huella_valores": "h"}, ("venta", "V6"): {"estado": "informacion_insuficiente", "huella_valores": "h"}}
        m = metricas_revision(filas, casos, {"min_revisiones_precision": 30})
        self.assertEqual((m["precision_alertas_revisadas"]["numerador"], m["precision_alertas_revisadas"]["denominador"]), (1, 2))
        self.assertEqual((m["falsas_alertas_por_100_normales_revisadas"]["numerador"], m["falsas_alertas_por_100_normales_revisadas"]["denominador"]), (1, 2))
        self.assertIn("no certifica", m["precision_alertas_revisadas"]["motivo"])


class SinDependenciasTests(unittest.TestCase):
    def test_puntuacion_api_y_cierre_sin_bibliotecas_analiticas(self):
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy', 'pandas', 'statsmodels', 'sksurv', 'joblib'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.anomalias, api.monitoreo, modelos.anomalias, modelos.cli, pipeline.operaciones\n"
                  "from modelos.anomalias import Bosque\n"
                  "b = Bosque({'variables': ['a'], 'max_muestras': 4, 'arboles': [{'var': [0, 0, 0], 'umbral': [0.5, 0, 0], 'izq': [1, -1, -1], 'der': [2, -1, -1], 'n': [4, 1, 3]}]})\n"
                  "assert b.rareza([0.0]) > b.rareza([1.0])\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])


# ------------------------------------------------------------------------------------------------------ publicación sintética
def _filas(corte, ops, version="m6-fx"):
    """Filas C2 coherentes construidas con las funciones reales de priorización y cobertura."""
    from modelos import anomalias as A
    filas = []
    for o in ops:
        punt = o.get("puntaje") is not None
        f = {"modelo_id": "anomalias", "tipo_operacion": o["tipo"], "operacion_id": o["id"], "revision_datos": o.get("rev", 1), "fecha": o["fecha"],
             "periodo": o["fecha"][:7], "producto_id": "PRO01", "cliente_id": "CLI001" if o["tipo"] == "venta" else None,
             "proveedor_id": "PRV01" if o["tipo"] == "compra" else None, "moneda": "COP", "unidad": "u", "cantidad": o.get("cantidad", 3.0),
             "valor_unitario": o.get("valor", 100.0), "descuento_pct": 0.0, "importe_origen": 300.0, "trm": None, "estado_trm": "no_aplica", "importe_cop": 300.0,
             "referencia_cantidad": 3.0 if punt else None, "referencia_valor_unitario": 100.0 if punt else None, "razon_cantidad": 1.0 if punt else None,
             "razon_valor_unitario": 1.0 if punt else None, "variables": None, "soporte": 9 if punt else 2, "puntaje": o.get("puntaje"),
             "puntaje_referencia": o.get("puntaje"), "puntaje_candidato": None, "metodo": "mediana_mad" if punt else None,
             "senalada_por_reglas": bool(o.get("senal")), "motivos": ["m"], "variables_inusuales": [], "estado_puntuacion": "puntuada" if punt else "historia_insuficiente",
             "version_modelo": version, "corte": corte, "tipo_emision": "reconstruccion_historica"}
        from modelos.anomalias import huella_valores
        f["huella_valores"] = huella_valores({"tipo_operacion": f["tipo_operacion"], "operacion_id": f["operacion_id"], "fecha": f["fecha"], "producto_id": "PRO01",
                                              "cliente_id": f["cliente_id"], "proveedor_id": f["proveedor_id"], "moneda": "COP", "cantidad": f["cantidad"],
                                              "valor_unitario": f["valor_unitario"], "descuento_pct": 0.0})
        filas.append(f)
    A.priorizar(filas, CFG["politica_alertas"])
    return filas


def _pub(directorio, corte, ops, version="m6-fx", alterar=None):
    from modelos import anomalias as A
    from modelos.ejecucion import json_bytes, publicar_lote
    filas = _filas(corte, ops, version)
    desde = date.fromisoformat(min(f["fecha"] for f in filas)[:8] + "01")
    cob = A.cobertura_filas(filas, [], desde, date.fromisoformat(corte), CFG)
    muestra = A.muestra_revision(filas, CFG, corte)
    mon = A.monitoreo(filas, CFG)
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "anomalias", "corte": corte, "desde": desde.isoformat(), "estado_experimento": "experimental · prueba",
           "operativa": False, "advertencia": "x", "modelo": {"version": version, "artefacto_huella": "f" * 64, "metodos_publicados": {"venta": "mediana_mad", "compra": "mediana_mad"},
                                                                 "candidato_por_universo": {"venta": "isolation_forest", "compra": "isolation_forest"}},
           "politica_alertas": CFG["politica_alertas"], "datos": {"revision": 1, "huella_datos": "d" * 64},
           "cobertura": {"corte": corte, "datos_observados_hasta": corte, "fuente": "prueba", "estado": "verificada"},
           "cobertura_por_universo": {"compra": {"estado": "no_declarada", "motivo": "sin cobertura"}}, "conteos": {u: sum(f["tipo_operacion"] == u for f in filas) for u in A.UNIVERSOS},
           "monitoreo": mon, "tablas": {"anomalias_operaciones": {"filas": len(filas)}, "cobertura_anomalias": {"filas": len(cob)}}}
    if alterar:
        alterar(man, filas, cob)
    publicar_lote(directorio, {"anomalias_operaciones.json": json_bytes(filas), "cobertura_anomalias.json": json_bytes(cob),
                               "muestra_revision.json": json_bytes(muestra)}, "manifiesto.json", man)
    return directorio


def _ops_base(mes="2026-10", n=21, extra=None):
    ops = [{"tipo": "venta", "id": f"VEN{i:03d}", "fecha": f"{mes}-{1 + i % 27:02d}", "puntaje": round(0.1 * i, 3)} for i in range(n)]
    ops += [{"tipo": "compra", "id": "VEN001", "fecha": f"{mes}-05", "puntaje": 2.5},       # mismo ID que una venta: no colisiona
            {"tipo": "compra", "id": "COM002", "fecha": f"{mes}-06", "puntaje": 0.3},
            {"tipo": "venta", "id": "VEN900", "fecha": f"{mes}-07", "puntaje": None}]       # historia insuficiente
    return ops + (extra or [])


class ContratoAnomaliasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m6c-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valida_y_rechaza_incoherencias(self):
        from contratos.validar import leer_publicacion_sombra
        self.assertEqual(leer_publicacion_sombra(_pub(self.tmp / "ok", "2026-10-31", _ops_base()))[0], [])
        malos = {
            "puntaje_no_finito": lambda m, f, c: f[0].update(puntaje=float("nan")),
            "abstencion_con_puntaje": lambda m, f, c: next(x for x in f if x["estado_puntuacion"] == "historia_insuficiente").update(puntaje=1.0),
            "prioridad_desordenada": lambda m, f, c: [x.update(prioridad=99) for x in f[:1]],
            "identidad_duplicada": lambda m, f, c: (f.append(dict(f[0])), m["tablas"]["anomalias_operaciones"].update(filas=len(f))),
            "compra_con_cliente": lambda m, f, c: next(x for x in f if x["tipo_operacion"] == "compra").update(cliente_id="CLI1"),
            "conteos": lambda m, f, c: c[0].update(validas=c[0]["validas"] + 1),
            "version": lambda m, f, c: f[0].update(version_modelo="otra"),
            "alerta_fuera_de_cupo": lambda m, f, c: next(x for x in f if x["prioridad"] == 3).update(alerta=True),
            "sin_huella_datos": lambda m, f, c: m.pop("datos"),
        }
        for nombre, fn in malos.items():
            with self.subTest(nombre):
                errores, _, _ = leer_publicacion_sombra(_pub(self.tmp / nombre, "2026-10-31", _ops_base(), alterar=fn))
                self.assertTrue(errores, nombre)

    def test_manifiesto_o_tabla_alterados_tras_sellar(self):
        from contratos.validar import leer_publicacion_sombra
        d = _pub(self.tmp / "s", "2026-10-31", _ops_base())
        f = d / "anomalias_operaciones.json"
        f.write_text(f.read_text(encoding="utf-8").replace('"puntaje": 0.5', '"puntaje": 0.55', 1), encoding="utf-8")
        self.assertTrue(leer_publicacion_sombra(d)[0])
        d = _pub(self.tmp / "m", "2026-10-31", _ops_base())
        m = json.loads((d / "manifiesto.json").read_text(encoding="utf-8"))
        m["estado_experimento"] = "operativo"
        (d / "manifiesto.json").write_text(json.dumps(m), encoding="utf-8")
        self.assertIn("sello", leer_publicacion_sombra(d)[0][0])


# ------------------------------------------------------------------------------------------------------ protocolo con el paquete
@unittest.skipIf(_paquete() is None or not HAY_SK, "Requiere el paquete sintético y scikit-learn")
class ExperimentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos import anomalias as A
        from modelos.anomalias_experimento import entrenar
        from modelos.datos import cargar_datos, preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m6-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cls.compras = A.cargar_compras(cls.datos)
        cls.r = entrenar(cls.datos, CFG, cls.tmp / "e1", cls.compras)

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_conteos_a02_equivalencia_y_separacion_temporal(self):
        diag = self.r["diagnostico"]
        self.assertEqual(diag["conteos_entrada"]["ventas_confirmadas"], 1371)
        self.assertEqual(diag["conteos_entrada"]["compras"], 240)
        self.assertEqual(diag["universos"]["venta"]["excluidas"], {"venta_anulada": 36})
        a02 = json.loads((self.tmp / "e1" / "control_a02.json").read_text(encoding="utf-8"))
        self.assertTrue(a02["coincide"])
        self.assertTrue(all(e["equivalente"] for e in self.r["equivalencia"].values()))
        for e in self.r["equivalencia"].values():
            self.assertTrue(all(c["ranking_identico"] and c["alertas_identicas"] for c in e["conjuntos"].values()))
            self.assertGreater(e["conjuntos"]["cerca_de_umbrales"]["n"], 100)
        for u, s in self.r["seleccion"].items():
            entren = diag["universos"][u]["por_bloque"]["entrenamiento"]["puntuadas"]
            self.assertEqual(s["filas_entrenamiento"], entren)      # el bosque solo ve el entrenamiento
        cv = json.loads((self.tmp / "e1" / "casos_validacion.json").read_text(encoding="utf-8"))
        self.assertTrue(all("2026-01-01" <= c["op"]["fecha"] <= "2026-06-30" for c in cv))
        self.assertFalse((self.tmp / "e1" / "casos_comprobacion.json").exists())  # la comprobación no se construye antes de congelar

    def test_casos_sembrados_no_contaminan_historial_ni_bloques(self):
        from modelos.anomalias_experimento import casos, preparar
        prep = preparar(self.datos, self.compras, CFG)
        antes = copy.deepcopy(prep["contextos"])
        val, comp = casos(prep, CFG, "validacion"), casos(prep, CFG, "comprobacion_historica")
        self.assertEqual(preparar(self.datos, self.compras, CFG)["contextos"], antes)
        originales = {(o["tipo_operacion"], o["operacion_id"]) for o in prep["ops"]}
        self.assertFalse({(c["base"]["tipo_operacion"], c["caso_id"]) for c in val + comp} & originales)
        self.assertFalse({c["base"]["operacion_id"] for c in val} & {c["base"]["operacion_id"] for c in comp})   # bases disjuntas
        iv = {(c["transformacion"], json.dumps(c["intensidad"])) for c in val if c["clase"] == "anomalia_sembrada"}
        ic = {(c["transformacion"], json.dumps(c["intensidad"])) for c in comp if c["clase"] == "anomalia_sembrada"}
        self.assertFalse(iv & ic)                                                                                  # variantes reservadas
        self.assertTrue(all(c["base"] and c["semilla"] and c["bloque"] and c["etiqueta_sintetica"] and c["motivo"] for c in val))

    def test_evaluacion_interrupcion_idempotencia_alteraciones_y_puntuacion(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos import anomalias as A
        from modelos import ejecucion
        from modelos.anomalias_experimento import ProtocoloM6Error, evaluacion_publicada, evaluar, verificar_congelacion
        from modelos.inferencia import cargar_artefacto
        d = self.tmp / "ev"
        shutil.copytree(self.tmp / "e1", d)
        ejecucion.FALLO_SIMULADO = "comprobacion.json"
        with self.assertRaises(RuntimeError):
            evaluar(d, self.datos, self.compras)
        ejecucion.FALLO_SIMULADO = None
        with self.assertRaises(ProtocoloM6Error):
            evaluacion_publicada(d)                                          # sin marcador: no hay evaluación publicada
        a, b = evaluar(d, self.datos, self.compras), evaluar(d, self.datos, self.compras)
        self.assertEqual(a["evaluacion"]["sello"], b["evaluacion"]["sello"])
        for u, dec in a["decision"]["decisiones"].items():
            self.assertIn(dec["decision"], ("favorable_demostracion_sombra", "referencia_conservada", "inconcluso"))
            m = a["metricas"][u]
            self.assertIsNone(m["revision_humana"]["precision_primeras_n"])
            self.assertEqual(m["referencia"]["controles_negativos"]["cambio_trm_puntaje_identico"]["identicos"],
                             m["referencia"]["controles_negativos"]["cambio_trm_puntaje_identico"]["total"])
        pub = evaluacion_publicada(d)
        art = cargar_artefacto(d / "artefacto.json", modelo_id="anomalias")
        metodos = {u: x["sistema_conservado"] for u, x in pub["decision"]["decisiones"].items()}
        r1 = A.puntuar_sombra(art, self.datos, self.compras, CFG, date(2026, 10, 31), self.tmp / "s1", estado_experimento="experimental", metodos=metodos)
        self.assertEqual(leer_publicacion_sombra(self.tmp / "s1")[0], [])
        self.assertEqual(r1["muestra"]["seleccionadas"], r1["muestra"]["objetivo"])  # >= 50 con el déficit reasignado y registrado
        r0 = A.puntuar_sombra(art, self.datos, self.compras, CFG, date(2026, 9, 30), self.tmp / "s0", estado_experimento="experimental", metodos=metodos)
        p1 = {(f["tipo_operacion"], f["operacion_id"]): (f["puntaje"], f["puntaje_candidato"]) for f in r1["filas"]}
        comunes = [(k, v) for k, v in ((k, (f["puntaje"], f["puntaje_candidato"])) for k, f in
                                       (((f["tipo_operacion"], f["operacion_id"]), f) for f in r0["filas"])) if k in p1]
        self.assertGreater(len(comunes), 100)
        self.assertTrue(all(p1[k] == v for k, v in comunes))                 # datos posteriores no cambian puntajes ya emitidos
        self.assertEqual(A.puntuar_sombra(art, self.datos, self.compras, CFG, date(2026, 10, 31), self.tmp / "s1", estado_experimento="experimental",
                                          metodos=metodos)["manifiesto"]["sello"], r1["manifiesto"]["sello"])  # reintento idéntico
        x = self.tmp / "alt"
        shutil.copytree(d, x)
        dec = json.loads((x / "decision.json").read_text(encoding="utf-8"))
        dec["decisiones"]["venta"]["sistema_conservado"] = "isolation_forest"
        (x / "decision.json").write_text(json.dumps(dec), encoding="utf-8")
        with self.assertRaises(ProtocoloM6Error):
            evaluacion_publicada(x)                                          # decisión alterada
        y = self.tmp / "alt2"
        shutil.copytree(d, y)
        art_d = json.loads((y / "artefacto.json").read_text(encoding="utf-8"))
        art_d["universos"]["venta"]["n_estimadores"] = 1
        (y / "artefacto.json").write_text(json.dumps(art_d), encoding="utf-8")
        with self.assertRaises(ProtocoloM6Error):
            verificar_congelacion(y)                                         # artefacto alterado
        otro = copy.copy(self.datos)
        otro.huella_datos = "0" * 64
        with self.assertRaises(ProtocoloM6Error):
            evaluar(self.tmp / "e1", otro, self.compras)                     # otra revisión de datos


# ------------------------------------------------------------------------------------------------------ API y persistencia
from _apoyo_app import CasoBase  # noqa: E402


class AnomaliasApiTests(CasoBase):
    def casos(self):
        with self.db.conexion() as con:
            return {r["caso_id"]: dict(r) for r in con.execute("SELECT * FROM casos_anomalia")}

    def eventos(self):
        with self.db.conexion() as con:
            return [dict(r) for r in con.execute("SELECT * FROM eventos_anomalia ORDER BY id")]

    def test_flujo_importar_revisar_reimportar_correccion_y_antigua(self):
        from api import anomalias
        self.assertEqual(self.http("GET", "/api/anomalias", como="ops1")[1]["estado"], "sin_sombra")
        r = anomalias.importar_sombra(self.db, _pub(self.tmp / "oct", "2026-10-31", _ops_base()), "ops1")
        self.assertTrue(r["activa"])
        n_casos, n_ev = len(self.casos()), len(self.eventos())
        self.assertGreater(n_casos, 0)
        self.assertTrue(anomalias.importar_sombra(self.db, self.tmp / "oct", "ops1")["ya_importada"])
        self.assertEqual((len(self.casos()), len(self.eventos())), (n_casos, n_ev))           # reimportar no duplica
        st, d = self.http("GET", "/api/anomalias?universo=compra", como="ops1")
        compra = next(i for i in d["items"] if i["operacion_id"] == "VEN001")
        self.assertIsNone(compra["cliente_id"])
        st, x = self.http("POST", "/api/anomalias/revision", {"tipo_operacion": "compra", "operacion_id": "VEN001", "estado": "cambio_legitimo",
                                                              "motivo": "Precio pactado con el proveedor", "evidencia": "OC-123"}, como="ops1")
        self.assertEqual((st, x["estado"]), (200, "cambio_legitimo"))                             # compra revisable sin cliente
        st, x = self.http("POST", "/api/anomalias/revision", {"tipo_operacion": "venta", "operacion_id": "VEN020", "estado": "error_confirmado", "motivo": " "}, como="ops1")
        self.assertEqual(st, 400)                                                                 # motivo obligatorio
        self.assertEqual(self.http("POST", "/api/anomalias/revision", {"tipo_operacion": "venta", "operacion_id": "VEN020", "estado": "error_confirmado",
                                                                       "motivo": "Precio digitado con un cero de más"}, como="fin1")[0], 200)
        # Publicación antigua: se guarda sin desplazar ni abrir casos o eventos
        ev_antes = len(self.eventos())
        r = anomalias.importar_sombra(self.db, _pub(self.tmp / "sep", "2026-09-30", _ops_base("2026-09", extra=[{"tipo": "venta", "id": "VSEP", "fecha": "2026-09-09", "puntaje": 9.0}])), "ops1")
        self.assertFalse(r["activa"])
        self.assertEqual(len(self.eventos()), ev_antes)
        self.assertEqual(self.http("GET", "/api/anomalias", como="ops1")[1]["corte"], "2026-10-31")
        # Publicación posterior con los mismos valores (otro corte y versión): no reabre decisiones cerradas
        r = anomalias.importar_sombra(self.db, _pub(self.tmp / "nov", "2026-11-30", _ops_base(extra=[{"tipo": "venta", "id": "VNOV", "fecha": "2026-11-03", "puntaje": 0.2}]),
                                                    version="m6-fx2"), "ops1")
        self.assertTrue(r["activa"])
        c = {k: v for k, v in self.casos().items() if ":VEN020:" in k}
        self.assertEqual([v["estado"] for v in c.values()], ["error_confirmado"])
        # Corrección de datos: otra huella → caso nuevo enlazado; el anterior conserva su decisión
        ops = _ops_base()
        next(o for o in ops if o["id"] == "VEN020").update(valor=1000.0, rev=2)
        anomalias.importar_sombra(self.db, _pub(self.tmp / "dic", "2026-12-31", ops, version="m6-fx2"), "ops1")
        c = sorted((v for v in self.casos().values() if v["operacion_id"] == "VEN020" and v["tipo_operacion"] == "venta"), key=lambda v: v["creado_en"] + v["caso_id"])
        self.assertEqual(len(c), 2)
        viejo = next(v for v in c if v["reemplazado_por"])
        nuevo = next(v for v in c if not v["reemplazado_por"])
        self.assertEqual((viejo["estado"], nuevo["estado"], nuevo["caso_anterior"]), ("error_confirmado", "pendiente", viejo["caso_id"]))
        st, det = self.http("GET", "/api/anomalias/caso?tipo=venta&id=VEN020", como="ops1")
        self.assertEqual([e["tipo"] for e in det["eventos"] if e["tipo"] in ("revision", "correccion_datos")], ["revision", "correccion_datos"])
        rev = next(e for e in det["eventos"] if e["tipo"] == "revision")
        self.assertEqual((rev["actor"], rev["version_examinada"]), ("fin1", "m6-fx"))           # quién decidió y sobre qué versión
        self.assertGreaterEqual(len(det["publicaciones"]), 3)                                    # puntuaciones históricas inmutables

    def test_permisos_cop_portal_exportacion_e_integridad(self):
        from api import anomalias
        anomalias.importar_sombra(self.db, _pub(self.tmp / "oct", "2026-10-31", _ops_base()), "ops1")
        for u in ("ventas1", "aten1", "cli_a", "cli_b"):
            self.assertEqual(self.http("GET", "/api/anomalias", como=u)[0], 403, u)
            self.assertEqual(self.http("GET", "/api/anomalias/caso?tipo=venta&id=VEN001", como=u)[0], 403, u)
            self.assertEqual(self.http("GET", "/api/anomalias/exportar.csv", como=u)[0], 403, u)
            self.assertEqual(self.http("POST", "/api/anomalias/revision", {"tipo_operacion": "venta", "operacion_id": "VEN001", "estado": "cambio_legitimo",
                                                                           "motivo": "abc"}, como=u)[0], 403, u)
        self.assertEqual(self.http("POST", "/api/anomalias/revision", {"tipo_operacion": "venta", "operacion_id": "VEN001", "estado": "cambio_legitimo",
                                                                       "motivo": "abc"}, como="ger1")[0], 403)   # Gerencia consulta, no decide
        it_ops = self.http("GET", "/api/anomalias", como="ops1")[1]["items"][0]
        it_fin = self.http("GET", "/api/anomalias", como="fin1")[1]["items"][0]
        self.assertIsNone(it_ops["importe_cop"])
        self.assertIsNotNone(it_fin["importe_cop"])
        st, csv = self.http("GET", "/api/anomalias/exportar.csv?universo=venta", como="ops1")
        self.assertEqual(st, 200)
        self.assertNotIn("importe_cop", str(csv).splitlines()[0])
        st, portal = self.http("GET", "/api/portal/beneficios", como="cli_a")
        self.assertNotIn("anomal", json.dumps(portal, ensure_ascii=False).lower())
        # Integridad: una publicación alterada no se importa y deja un aviso persistente e idempotente
        d = _pub(self.tmp / "bad", "2026-11-30", _ops_base())
        f = d / "anomalias_operaciones.json"
        f.write_text(f.read_text(encoding="utf-8").replace('"alerta": false', '"alerta": true', 1), encoding="utf-8")
        from api.base import ErrorApi
        for _ in range(2):
            with self.assertRaises(ErrorApi):
                anomalias.importar_sombra(self.db, d, "ops1")
        self.assertEqual(self.http("POST", "/api/anomalias/sombra", {"ruta": str(d)}, como="ops1")[0], 400)  # fuera de salida/ o var/
        mon = self.http("GET", "/api/anomalias/monitoreo", como="ger1")[1]
        self.assertEqual([a["tipo"] for a in mon["avisos"]], ["publicacion_rechazada"])
        self.assertEqual(self.http("GET", "/api/anomalias", como="ops1")[1]["corte"], "2026-10-31")

    def test_aviso_estadistico_por_caida_de_cobertura(self):
        from api import anomalias
        anomalias.importar_sombra(self.db, _pub(self.tmp / "a", "2026-10-31", _ops_base(n=40)), "ops1")
        sin = [{"tipo": "venta", "id": f"VSH{i}", "fecha": "2026-11-10", "puntaje": None} for i in range(30)]
        r = anomalias.importar_sombra(self.db, _pub(self.tmp / "b", "2026-11-30", _ops_base("2026-11", n=40, extra=sin)), "ops1")
        self.assertIn("caida_cobertura", r["avisos"])
        mon = self.http("GET", "/api/anomalias/monitoreo", como="ops1")[1]
        aviso = next(a for a in mon["avisos"] if a["tipo"] == "caida_cobertura")
        self.assertEqual((aviso["severidad"], aviso["datos"]["umbral_pp"]), ("estadistico", 10.0))


# ------------------------------------------------------------------------------------------------------ M6.1
CFG61 = json.loads((RAIZ / "modelos" / "config" / "anomalias_m61.json").read_text(encoding="utf-8"))
CAT = {"P1": {"moneda_lista": "COP", "precio_lista": 100.0, "costo_referencia": 60.0}}


class M61Tests(unittest.TestCase):
    def ctx(self, ventas, compras=()):
        from modelos import anomalias_m61 as M
        ops, _, h = preparar_ops(ventas, compras, cfg=CFG61)
        return {o["operacion_id"]: (o, M.contexto(o, h, CFG61)) for o in ops}, h

    def test_catalogo_direccion_y_venta_bajo_costo(self):
        from modelos import anomalias_m61 as M
        ventas = [V(f"A{i}", dia(i), q=4 + i % 3, precio=str(90 + 5 * (i % 3))) for i in range(8)] +                  [V("LISTA", dia(20), precio="100"), V("BAJA", dia(20), precio="80"), V("Q1", dia(20), q=1), V("QX", dia(20), q=40), V("BC", dia(30), precio="55")]
        compras = [C(f"K{i}", dia(i), costo="60") for i in range(4)] + [C("CX", dia(25), costo="75")]
        m, h = self.ctx(ventas, compras)
        ev = {k: [e["id"] for e in M.evidencias(o, c, CFG61, CAT, h)] for k, (o, c) in m.items()}
        self.assertNotIn("fuera_de_lista", ev["LISTA"])                  # precio de lista: dentro de la política
        self.assertIn("fuera_de_lista", ev["BAJA"])                      # 80 % de lista: fuera
        self.assertEqual(ev["Q1"], [])                                    # cantidad baja: no es evidencia
        self.assertIn("cantidad_alta_fuera_de_contexto", ev["QX"])
        self.assertIn("venta_bajo_costo", ev["BC"])                       # por debajo del costo reciente de compra
        self.assertIn("costo_fuera_de_referencia", ev["CX"])              # 125 % del costo de referencia
        self.assertEqual(m["Q1"][1]["variables"]["z_log_cantidad_alta"], 0.0)
        o = dict(m["BAJA"][0], moneda="USD")
        self.assertNotIn("fuera_de_lista", [e["id"] for e in M.evidencias(o, m["BAJA"][1], CFG61, CAT, h)])  # otra moneda: no se compara

    def test_cupo_maximo_sin_evidencia_no_alerta(self):
        from modelos import anomalias_m61 as M
        f = lambda i, s, ev: {"tipo_operacion": "venta", "operacion_id": i, "periodo": "2026-07", "fecha": "2026-07-01", "puntaje": s, "senalada_por_reglas": ev}  # noqa: E731
        filas = [f("A", 9.0, False), f("B", 1.0, True)] + [f(f"Z{i}", 0.1, False) for i in range(30)]
        M.priorizar(filas, CFG61["politica_alertas"])
        al = {x["operacion_id"]: (x["prioridad"], x["alerta"]) for x in filas}
        self.assertEqual(al["B"], (1, True))                              # con evidencia primero
        self.assertEqual(al["A"], (2, False))                             # rareza alta sin evidencia: no llena el cupo
        self.assertEqual(sum(x["alerta"] for x in filas), 1)

    def test_contrato_rechaza_alerta_sin_evidencia(self):
        from contratos.validar import validar_anomalias
        from modelos import anomalias_m61 as M
        filas = _filas("2026-10-31", _ops_base())
        for x in filas:
            x["senalada_por_reglas"] = x["operacion_id"] == "VEN020"
        M.priorizar(filas, CFG61["politica_alertas"])
        man = {"corte": "2026-10-31", "politica_alertas": CFG61["politica_alertas"], "modelo": {"version": "m6-fx", "metodos_publicados": {"venta": "mediana_mad", "compra": "mediana_mad"}}}
        self.assertFalse([e for e in validar_anomalias(filas, [], man) if "alerta" in e or "orden" in e])
        next(x for x in filas if x["operacion_id"] == "VEN019").update(alerta=True)
        self.assertTrue([e for e in validar_anomalias(filas, [], man) if "alerta incoherente" in e])


@unittest.skipIf(_paquete() is None or not HAY_SK, "Requiere el paquete sintético y scikit-learn")
class M61ExperimentoTests(unittest.TestCase):
    def test_siembra_sobre_maximo_entrenamiento_evaluacion_y_publicacion(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos import anomalias as A
        from modelos import anomalias_m61 as M
        from modelos import anomalias_m61_experimento as X
        from modelos.anomalias_experimento import ProtocoloM6Error, verificar_congelacion
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.inferencia import cargar_artefacto
        tmp = Path(tempfile.mkdtemp(prefix="m61-"))
        try:
            preparar_lote(_paquete(), tmp / "a01")
            datos = cargar_datos(tmp / "a01")
            compras = A.cargar_compras(datos)
            prep = X.preparar(datos, compras, CFG61)
            for c in X.casos(prep, CFG61, "validacion"):
                if c["transformacion"] == "cantidad_extrema":
                    maximo = max(a[2] for a in prep["historial"].antecedentes(A.grupo(prep_op(prep, c)), c["op"]["fecha"]))
                    self.assertGreater(c["op"]["cantidad"], maximo)        # por encima del máximo histórico
            r = X.entrenar(datos, CFG61, tmp / "e", compras)
            self.assertTrue(all(e["equivalente"] for e in r["equivalencia"].values()))
            ev = X.evaluar(tmp / "e", datos, compras)
            for u, d in ev["decision"]["decisiones"].items():
                self.assertIn(d["decision"], ("favorable_demostracion_sombra", "referencia_conservada", "inconcluso"))
                self.assertEqual(ev["metricas"][u]["referencia"]["controles_negativos"]["por_tipo"]["cantidad_baja_habitual"]["numerador"], 0)
            art = cargar_artefacto(tmp / "e" / "artefacto.json", modelo_id="anomalias")
            metodos = {u: d["sistema_conservado"] for u, d in ev["decision"]["decisiones"].items()}
            out = M.puntuar_sombra(art, datos, compras, CFG61, date(2026, 10, 31), tmp / "s", estado_experimento="experimental", metodos=metodos)
            self.assertEqual(leer_publicacion_sombra(tmp / "s")[0], [])
            self.assertTrue(all(f["senalada_por_reglas"] for f in out["filas"] if f["alerta"]))   # nunca alerta sin evidencia
            a = json.loads((tmp / "e" / "artefacto.json").read_text(encoding="utf-8"))
            a["catalogo"]["venta_precio_sobre_lista"] = [0.5, 1.0]
            (tmp / "e" / "artefacto.json").write_text(json.dumps(a), encoding="utf-8")
            with self.assertRaises(ProtocoloM6Error):
                verificar_congelacion(tmp / "e")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def prep_op(prep, c):
    return next(o for o in prep["ops"] if o["tipo_operacion"] == c["base"]["tipo_operacion"] and o["operacion_id"] == c["base"]["operacion_id"])


if __name__ == "__main__":
    unittest.main()
