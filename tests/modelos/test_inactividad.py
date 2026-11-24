"""M2 · inactividad a 60 días: etiqueta, población, variables, protocolo, integridad, contratos, API y episodios."""
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
from decimal import Decimal
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "tests" / "app"))
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _c(fecha, vid="V", cid="A", importe=100.0):
    """Compra confirmada ya procesada por historial_compras."""
    return {"venta_id": vid, "fecha": fecha, "importe_cop": importe, "familia": "F", "recurrente": False, "vigencia_meses": 0}


def _v(cid, fecha, vid, estado="Confirmada", moneda="COP"):
    return {"venta_id": vid, "cliente_id": cid, "producto_id": "P1", "fecha": fecha, "cantidad": 1, "moneda": moneda,
            "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "estado": estado}


C = date(2026, 7, 31)
OBS = date(2026, 10, 31)


def _huellas_registro():
    base = RAIZ / "var" / "modelos"
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(base.rglob("*")) if p.is_file()} if base.exists() else {}


# ------------------------------------------------------------------------------------------------- etiqueta
class EtiquetaTests(unittest.TestCase):
    def et(self, compras, corte=C, obs=OBS):
        from modelos.inactividad import etiqueta_inactividad
        return etiqueta_inactividad(compras, corte, obs)

    def test_ejemplo_obligatorio_del_plan(self):
        L = date(2026, 6, 2)  # cruce el 2026-08-31
        self.assertEqual(L + timedelta(days=90), date(2026, 8, 31))
        for compra, esperado, cruce in ((date(2026, 8, 30), 0, None), (date(2026, 8, 31), 0, None), (date(2026, 9, 1), 1, "2026-08-31")):
            with self.subTest(compra=compra):
                r = self.et([_c(L), _c(compra)])
                self.assertEqual((r["etiqueta"], r["estado"], r["fecha_cruce"]), (esperado, "madura", cruce))

    def test_cruce_dia_60_incluido_y_61_excluido(self):
        r30 = self.et([_c(C - timedelta(days=30))])  # cruce = C + 60 = fin del horizonte
        self.assertEqual((r30["etiqueta"], r30["fecha_cruce"]), (1, (C + timedelta(days=60)).isoformat()))
        r29 = self.et([_c(C - timedelta(days=29))])  # cruce = C + 61: fuera
        self.assertEqual(r29["etiqueta"], 0)

    def test_compra_posterior_no_borra_el_evento(self):
        r = self.et([_c(date(2026, 6, 2)), _c(date(2026, 9, 5))])
        self.assertEqual((r["etiqueta"], r["fecha_cruce"]), (1, "2026-08-31"))

    def test_horizonte_incompleto_es_pendiente_aunque_no_haya_compras(self):
        L = date(2026, 6, 2)
        r = self.et([_c(L)], obs=C + timedelta(days=59))
        self.assertEqual((r["etiqueta"], r["estado"]), (None, "pendiente"))
        self.assertEqual(self.et([_c(L)], obs=C + timedelta(days=60))["estado"], "madura")

    def test_mismo_dia_cuenta_como_un_dia_de_compra(self):
        from modelos.variables import variables_inactividad
        uno = [_c(date(2026, 5, 1), "1"), _c(date(2026, 6, 2), "2")]
        dos = uno + [_c(date(2026, 6, 2), "3")]
        self.assertEqual(self.et(uno), self.et(dos))
        v1, v2 = variables_inactividad(uno, C), variables_inactividad(dos, C)
        self.assertEqual(v2["dias_compra_distintos"], 2)
        self.assertEqual({k: v for k, v in v1.items() if k != "importe_cop_90d"}, {k: v for k, v in v2.items() if k != "importe_cop_90d"})

    def test_ventas_no_confirmadas_excluidas(self):
        from modelos.inactividad import poblacion_al_corte
        from modelos.variables import historial_compras
        ventas = [_v("A", date(2026, 6, 2), "1"), _v("A", date(2026, 7, 20), "2", estado="Anulada"),
                  _v("A", date(2026, 8, 20), "3", estado="Pendiente")]
        h = historial_compras(ventas, {}, {})
        self.assertEqual([c["venta_id"] for c in h["A"]], ["1"])
        self.assertEqual(poblacion_al_corte({"fecha_alta": date(2025, 1, 1)}, h["A"], C)[:2], ("aprendible", 59))
        self.assertEqual(self.et(h["A"])["etiqueta"], 1)  # la venta anulada de agosto no evita el cruce


class PoblacionTests(unittest.TestCase):
    def test_recencias_29_30_89_90_sin_historial_y_alta_posterior(self):
        from modelos.inactividad import predicciones_inactividad
        clientes = [{"cliente_id": f"R{r}", "fecha_alta": date(2025, 1, 1)} for r in (29, 30, 89, 90)]
        clientes += [{"cliente_id": "SIN", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "NUEVO", "fecha_alta": date(2026, 8, 1)}]
        historial = {f"R{r}": [_c(C - timedelta(days=r))] for r in (29, 30, 89, 90)}
        filas = {f["cliente_id"]: f for f in predicciones_inactividad(None, "sin modelo", clientes, historial, C)}
        self.assertEqual((filas["R29"]["estado"], filas["R29"]["probabilidad"], filas["R29"]["poblacion"]), ("estructural", 0.0, "estructural"))
        self.assertIn("estructural cero", filas["R29"]["motivos"][0])
        for r in ("R30", "R89"):
            self.assertEqual((filas[r]["estado"], filas[r]["probabilidad"], filas[r]["poblacion"]), ("modelo_no_disponible", None, "aprendible"))
        self.assertEqual((filas["R90"]["estado"], filas["R90"]["probabilidad"]), ("no_elegible", None))
        self.assertTrue(filas["R90"]["motivos"][0].startswith("ya_frio"))
        self.assertEqual((filas["SIN"]["estado"], filas["SIN"]["probabilidad"], filas["SIN"]["recencia_dias"]), ("sin_historial", None, None))
        self.assertEqual((filas["NUEVO"]["estado"], filas["NUEVO"]["probabilidad"]), ("no_elegible", None))
        self.assertTrue(all(f["horizonte_dias"] == 60 and f["umbral_frio_dias"] == 90 and f["modelo_id"] == "inactividad_60d" for f in filas.values()))

    def test_venta_futura_no_cambia_variables_ni_puntuacion(self):
        from modelos.inactividad import fotografias, predicciones_inactividad
        art = _artefacto_minimo()
        cli = [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}]
        base = {"A": [_c(date(2026, 3, 1), "1"), _c(date(2026, 6, 2), "2")]}
        futura = {"A": base["A"] + [_c(date(2026, 8, 3), "3")]}
        p1 = predicciones_inactividad(art, None, cli, base, C)
        p2 = predicciones_inactividad(art, None, cli, futura, C)
        self.assertEqual(p1, p2)
        f1 = fotografias(cli, base, [C], OBS)[0]
        f2 = fotografias(cli, futura, [C], OBS)[0]
        self.assertNotEqual(f1["inactivo_60d"], f2["inactivo_60d"])  # la etiqueta sí mira el futuro...
        self.assertEqual({k: f1[k] for k in _variables()}, {k: f2[k] for k in _variables()})  # ...las variables no

    def test_importe_nulo_si_falta_la_conversion(self):
        from modelos.variables import variables_inactividad
        self.assertIsNone(variables_inactividad([_c(date(2026, 6, 2), importe=None)], C)["importe_cop_90d"])
        self.assertEqual(variables_inactividad([_c(date(2026, 1, 2), importe=None), _c(date(2026, 6, 2))], C)["importe_cop_90d"], 100.0)


def _variables():
    from modelos.variables import VARIABLES_INACTIVIDAD
    return VARIABLES_INACTIVIDAD


def _artefacto_minimo(**cambios):
    from modelos.inferencia import desde_dict, sellar
    d = {"formato": "jacomind.regresion_logistica.v1", "modelo_id": "inactividad_60d", "version": "fixture-m2",
         "version_variables": "inactividad_60d-variables-v1", "horizonte_dias": 60, "umbral_frio_dias": 90,
         "variables": ["recencia_dias"], "transformaciones": [{"variable": "recencia_dias", "funcion": "log1p", "imputacion": 4.0, "media": 4.0, "desviacion": 0.5}],
         "intercepto": -0.2, "pesos": [1.1], "umbral": None, "disponible_desde": "2026-01-01"}
    d.update(cambios)
    return desde_dict(sellar(d))


class ArtefactoYContratoTests(unittest.TestCase):
    def test_rechaza_otro_modelo_horizonte_o_esquema(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict, huella_artefacto
        base = _artefacto_minimo().datos
        for nombre, cambio in {"horizonte": {"horizonte_dias": 30}, "frio": {"umbral_frio_dias": 60},
                               "variables_de_compra": {"version_variables": "compra_30d-variables-v1"},
                               "modelo": {"modelo_id": "otro"}, "variable_ajena": {"variables": ["frecuencia_30d"]}}.items():
            d = dict(copy.deepcopy(base), **cambio)
            d["huella"] = huella_artefacto(d)
            with self.subTest(nombre), self.assertRaises(ArtefactoInvalido):
                desde_dict(d)

    def test_artefacto_de_un_modelo_no_sirve_para_el_otro(self):
        from modelos.compra import puntuar
        from modelos.inferencia import ArtefactoInvalido, cargar_artefacto
        tmp = Path(tempfile.mkdtemp())
        try:
            (tmp / "a.json").write_text(json.dumps(_artefacto_minimo().datos), encoding="utf-8")
            with self.assertRaises(ArtefactoInvalido):
                cargar_artefacto(tmp / "a.json", modelo_id="compra_30d")
            with self.assertRaises(ArtefactoInvalido):
                puntuar(_artefacto_minimo(), None, C)
            compra = RAIZ / "var" / "modelos" / "compra_30d" / "v1"
            if compra.exists():
                with self.assertRaises(ArtefactoInvalido):
                    cargar_artefacto(compra, modelo_id="inactividad_60d")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_contrato_coexistencia_y_coherencia_de_estados(self):
        from contratos.validar import validar_predicciones, validar_tabla, cargar_esquema
        from modelos.inactividad import predicciones_inactividad
        man = {"corte": C.isoformat()}
        clientes = [{"cliente_id": "A", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "B", "fecha_alta": date(2025, 1, 1)}]
        hist = {"A": [_c(date(2026, 6, 2))], "B": [_c(date(2026, 7, 20))]}
        inac = predicciones_inactividad(_artefacto_minimo(), None, clientes, hist, C)
        compra = [{"cliente_id": c, "modelo_id": "compra_30d", "probabilidad": 0.4, "estado": "estimado", "horizonte_dias": 30,
                   "version_modelo": "v1", "corte": C.isoformat(), "datos_hasta": C.isoformat(), "motivos": ["x"]} for c in ("A", "B")]
        defin = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]["predicciones_clientes"]
        filas = compra + inac
        self.assertEqual(validar_tabla("predicciones_clientes", filas, defin, {"filas": len(filas)}), [])
        self.assertEqual(validar_predicciones(filas, None, man), [])
        dup = filas + [dict(inac[0])]
        self.assertTrue(any("clave duplicada" in e for e in validar_tabla("predicciones_clientes", dup, defin, {"filas": len(dup)})))
        malos = {"estructural_con_p": dict(inac[1], probabilidad=0.2), "estimado_frio": dict(inac[0], recencia_dias=95),
                 "frio_con_cero": dict(inac[0], estado="estructural", probabilidad=0.0, recencia_dias=95),
                 "horizonte": dict(inac[0], horizonte_dias=30), "umbral": dict(inac[0], umbral_frio_dias=60),
                 "sin_historial_con_recencia": dict(inac[0], estado="sin_historial", probabilidad=None),
                 "compra_estructural": dict(compra[0], estado="estructural", probabilidad=0.0)}
        for nombre, fila in malos.items():
            with self.subTest(nombre):
                self.assertTrue(validar_predicciones([fila], None, man), nombre)

    def test_ranking_menos_de_k_y_desempates(self):
        from modelos.inactividad_experimento import medir
        filas = [{"cliente_id": c, "corte": C, "inactivo_60d": y, "recencia_dias_corte": r}
                 for c, y, r in (("B", 1, 50), ("A", 0, 50), ("C", 1, 40))]
        m = medir(filas, lambda f: float(f["recencia_dias_corte"]), False)
        t = m["por_mes"][0]["top10"]
        self.assertEqual((t["k_efectivo"], t["clientes"], t["aciertos"], t["falsos_positivos"]), (3, ["A", "B", "C"], 2, 1))
        self.assertEqual(M_rank(filas, 1), ["A"])


def M_rank(filas, k):
    from modelos import metricas as M
    return M.ranking_k(filas, lambda f: float(f["recencia_dias_corte"]), k, "inactivo_60d")["clientes"]


# ------------------------------------------------------------------------------------- publicador recuperable
class PublicadorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_interrupcion_reintento_idempotencia_y_no_sobrescritura(self):
        from modelos import ejecucion as E
        archivos = {"metricas.json": b'{"a": 1}\n', "predicciones.csv": b"x\n", "decision.json": b'{"d": "inconcluso"}\n'}
        E.FALLO_SIMULADO = "metricas.json"
        with self.assertRaises(RuntimeError):
            E.publicar_lote(self.tmp, archivos, "evaluacion.json", {"m": 1})
        self.assertTrue((self.tmp / "metricas.json").exists())
        self.assertFalse((self.tmp / "decision.json").exists())
        E.FALLO_SIMULADO = None
        m1 = E.publicar_lote(self.tmp, archivos, "evaluacion.json", {"m": 1})  # reintento sin borrar nada
        m2 = E.publicar_lote(self.tmp, archivos, "evaluacion.json", {"m": 1})
        self.assertEqual(m1, m2)
        with self.assertRaises(E.EjecucionError):
            E.publicar_lote(self.tmp, dict(archivos, **{"decision.json": b'{"d": "favorable"}\n'}), "evaluacion.json", {"m": 1})
        (self.tmp / "decision.json").write_text('{"d": "favorable"}\n', encoding="utf-8")
        with self.assertRaises(E.EjecucionError):
            E.verificar_lote(self.tmp, "evaluacion.json")
        with self.assertRaises(E.EjecucionError):
            E.publicar_lote(self.tmp, archivos, "evaluacion.json", {"m": 1})

    def test_parcial_distinto_sin_marcador_no_se_sobrescribe(self):
        from modelos import ejecucion as E
        (self.tmp / "metricas.json").write_bytes(b"otro\n")
        with self.assertRaises(E.EjecucionError):
            E.publicar_lote(self.tmp, {"metricas.json": b"nuevo\n"}, "evaluacion.json")


# ------------------------------------------------------------------------------------ experimento completo
@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ExperimentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.datos import cargar_datos, preparar_lote
        from modelos.inactividad_experimento import cargar_config, entrenar
        cls.registro_antes = _huellas_registro()
        cls.tmp = Path(tempfile.mkdtemp(prefix="m2-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cls.config = cargar_config()
        cls.r = entrenar(cls.datos, cls.config, cls.tmp / "e1")

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copia(self, nombre):
        d = self.tmp / nombre
        shutil.copytree(self.tmp / "e1", d)
        return d

    def test_fronteras_y_disponibilidad_de_transformaciones(self):
        from modelos.inactividad_experimento import aprendibles, preparar, verificar_fronteras
        from modelos.compra import ProtocoloError
        from modelos.variables import ajustar_transformaciones
        self.assertEqual(self.r["fronteras"]["ajuste->validacion"]["ultima_etiqueta_madura"], "2026-04-29")
        self.assertEqual(self.r["fronteras"]["validacion->comprobacion_historica"]["ultima_etiqueta_madura"], "2026-07-30")
        art = self.r["artefacto"]
        self.assertTrue(all("2025-03-31" <= c <= "2026-02-28" for c in art["entrenamiento"]["cortes"]))
        ds = preparar(self.datos, self.config)
        aj = aprendibles(ds["bloques"]["ajuste"])
        self.assertEqual(ajustar_transformaciones(aj, art["variables"]), art["transformaciones"])
        malo = copy.deepcopy(self.config)
        malo["bloques"]["validacion"] = ["2026-03-01", "2026-05-31"]  # incluye marzo: solapa con el ajuste
        with self.assertRaises(ProtocoloError):
            verificar_fronteras(preparar(self.datos, dict(malo, separacion_temporal={"excluidos": []}))["bloques"], malo)
        self.assertFalse({"2026-09-30", "2026-03-31", "2026-06-30"} & {f["corte"].isoformat() for f in ds["filas"]})

    def test_seleccion_equivalencia_y_artefacto_principal(self):
        from modelos.inferencia import cargar_artefacto, desde_dict
        sel, cong = self.r["seleccion"], self.r["congelacion"]
        self.assertEqual(len(sel["candidatos"]), 6)
        self.assertEqual(sel["elegido_artefacto_huella"], cong["artefacto_huella"])
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="inactividad_60d")
        self.assertEqual(art.huella, cargar_artefacto(self.tmp / "e1" / "candidatos" / f"{sel['elegido']}.json").huella)
        self.assertTrue(all(c["equivalencia_json_sklearn"]["diferencia_maxima"] <= 1e-9 for c in sel["candidatos"].values()))
        self.assertEqual(desde_dict(json.loads(json.dumps(art.datos))).probabilidad({"recencia_dias": 40}), art.probabilidad({"recencia_dias": 40}))
        self.assertEqual(set(cong["archivos"]) >= {"config.json", "protocolo.json", "datos.json", "seleccion.json", "artefacto.json",
                                                   "predicciones_validacion.csv", "entorno.json"}, True)

    def test_reproducible_en_otra_carpeta_e_idempotente(self):
        from modelos.ejecucion import EjecucionError
        from modelos.inactividad_experimento import entrenar
        r2 = entrenar(self.datos, self.config, self.tmp / "e2")
        self.assertEqual(r2["congelacion"]["archivos"], self.r["congelacion"]["archivos"])
        self.assertEqual(r2["congelacion"]["sello"], self.r["congelacion"]["sello"])
        r3 = entrenar(self.datos, self.config, self.tmp / "e2")  # repetir en la misma carpeta: idempotente
        self.assertEqual(r3["congelacion"]["escrito_en"], r2["congelacion"]["escrito_en"])
        otra = dict(self.config, semilla=1)
        with self.assertRaises(EjecucionError):
            entrenar(self.datos, otra, self.tmp / "e2")

    def test_evaluacion_recuperable_tras_interrupcion(self):
        from modelos import ejecucion
        from modelos.inactividad_experimento import evaluar
        d = self.copia("ev-interrumpida")
        ejecucion.FALLO_SIMULADO = "metricas_comprobacion_historica.json"
        with self.assertRaises(RuntimeError):
            evaluar(d, self.datos)
        ejecucion.FALLO_SIMULADO = None
        self.assertFalse((d / "decision.json").exists())
        with mock.patch("modelos.inactividad_experimento.ajustar", side_effect=AssertionError("no debe reajustar")):
            r = evaluar(d, self.datos)  # reintento sin borrar archivos
            r2 = evaluar(d, self.datos)
        self.assertEqual(r["evaluacion"]["sello"], r2["evaluacion"]["sello"])
        dec = json.loads((d / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual(dec["artefacto_huella"], self.r["congelacion"]["artefacto_huella"])
        self.assertIn(dec["decision"], ("favorable", "inconcluso", "rechazado"))
        self.assertEqual(r["metricas"]["artefacto"]["huella"], dec["artefacto_huella"])
        self.assertIn("exploratoria", dec["alcance"].lower())
        with mock.patch("modelos.inactividad_experimento.decidir", return_value={"decision": "favorable", "estado_maximo": "sombra",
                                                                                 "cumple": {}, "motivos": [], "valores": {}}):
            with self.assertRaises(ejecucion.EjecucionError):
                evaluar(d, self.datos)  # un resultado distinto no sobrescribe

    def test_rechazo_de_evidencia_o_artefactos_modificados(self):
        from modelos.compra import ProtocoloError
        from modelos.inactividad_experimento import evaluar
        from modelos.inferencia import sellar
        casos = {
            "seleccion": lambda d: (d / "seleccion.json").write_text((d / "seleccion.json").read_text(encoding="utf-8").replace('"elegido"', '"elegido" ', 1), encoding="utf-8"),
            "predicciones_validacion": lambda d: (d / "predicciones_validacion.csv").write_text("alterado\n", encoding="utf-8"),
            "artefacto_otro_candidato": lambda d: shutil.copy(d / "candidatos" / [c for c in self.r["seleccion"]["candidatos"] if c != self.r["seleccion"]["elegido"]][0].__add__(".json"), d / "artefacto.json"),
            "artefacto_resellado": lambda d: (d / "artefacto.json").write_text(json.dumps(sellar(dict(json.loads((d / "artefacto.json").read_text(encoding="utf-8")), intercepto=0.0))), encoding="utf-8"),
            "datos_json": lambda d: (d / "datos.json").write_text((d / "datos.json").read_text(encoding="utf-8") + " ", encoding="utf-8"),
            "congelacion": lambda d: (d / "congelacion.json").write_text((d / "congelacion.json").read_text(encoding="utf-8").replace('"formato": 3', '"formato": 4'), encoding="utf-8"),
        }
        for nombre, alterar in casos.items():
            with self.subTest(nombre):
                d = self.copia(f"alterado-{nombre}")
                alterar(d)
                with self.assertRaises(ProtocoloError):
                    evaluar(d, self.datos)
                self.assertFalse((d / "decision.json").exists())

    def test_un_solo_tipo_de_etiqueta_no_entrena_y_conserva_la_referencia(self):
        from modelos import inactividad_experimento as X
        original = X.preparar

        def sin_eventos(datos, config):
            ds = original(datos, config)
            for f in ds["bloques"]["ajuste"]:
                if f.get("inactivo_60d") is not None:
                    f["inactivo_60d"] = 0
            return ds
        with mock.patch.object(X, "preparar", side_effect=sin_eventos), mock.patch.object(X, "ajustar", side_effect=AssertionError("no debe ajustar")):
            r = X.entrenar(self.datos, self.config, self.tmp / "sin-eventos")
        self.assertIsNone(r["seleccion"]["elegido"])
        self.assertIn("ajuste: positivos", r["seleccion"]["sin_candidato"]["motivo"])
        self.assertFalse((self.tmp / "sin-eventos" / "artefacto.json").exists())
        ev = X.evaluar(self.tmp / "sin-eventos", self.datos)
        self.assertEqual(ev["decision"]["decision"], "inconcluso")
        self.assertIsNotNone(ev["metricas"]["resultados"]["mayor_recencia"])

    def test_puntuar_en_sombra_idempotente_y_separado_del_cierre(self):
        from contratos.validar import leer_publicacion_sombra
        from modelos.inactividad import puntuar_sombra
        from modelos.inferencia import cargar_artefacto
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="inactividad_60d")
        out = self.tmp / "sombra" / "2026-10-31"
        r1 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        r2 = puntuar_sombra(art, self.datos, date(2026, 10, 31), out, estado_experimento="experimental en sombra")
        self.assertEqual(r1["manifiesto"]["sello"], r2["manifiesto"]["sello"])
        errores, man, filas = leer_publicacion_sombra(out)
        self.assertEqual(errores, [])
        self.assertFalse(man["operativa"])
        self.assertEqual(len(filas), 120)
        self.assertEqual(sum(man["conteos"].values()), 120)
        self.assertFalse((out / "agenda.json").exists())
        from modelos.datos import CoberturaInsuficiente
        with self.assertRaises(CoberturaInsuficiente):
            puntuar_sombra(art, self.datos, date(2026, 11, 30), self.tmp / "sombra" / "nov", estado_experimento="x")

    def test_cierre_y_api_sin_librerias_de_entrenamiento_y_coexistencia(self):
        from modelos import registro as R
        from modelos.inferencia import cargar_artefacto
        reg = self.tmp / "registro-aislado"
        if (RAIZ / "var" / "modelos" / "compra_30d").exists():
            shutil.copytree(RAIZ / "var" / "modelos" / "compra_30d", reg / "compra_30d")
        art = cargar_artefacto(self.tmp / "e1" / "artefacto.json", modelo_id="inactividad_60d")
        R.promover(reg, "inactividad_60d", "v1", art, {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": art.huella,
                                                        "origen_datos": "fixture_empresarial", "aprobado_por": "fixture"}, {}, "operativo")
        codigo = ("import sys\n"
                  "class B:\n"
                  "    def find_spec(self, n, p=None, t=None):\n"
                  "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy'): raise ImportError(n)\n"
                  "sys.meta_path.insert(0, B())\n"
                  "import api.servidor, api.prevencion, modelos.inactividad\n"
                  "from pipeline.generar import generar\n"
                  "from contratos.validar import validar_publicacion\n"
                  f"generar(r'{_paquete()}', '2026-10-31', r'{self.tmp / 'cierre'}', registro=r'{reg}')\n"
                  f"r, d = validar_publicacion(r'{self.tmp / 'cierre'}')\n"
                  "assert r.valido, r.errores\n"
                  "p = d['predicciones_clientes']\n"
                  "assert sum(f['modelo_id'] == 'inactividad_60d' for f in p) == 120\n"
                  "assert sum(f['modelo_id'] == 'compra_30d' for f in p) == 120\n"
                  "assert all(c['prob_compra_30d'] == next(f['probabilidad'] for f in p if f['cliente_id'] == c['cliente_id'] and f['modelo_id'] == 'compra_30d') for c in d['agenda']['clientes'])\n"
                  "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])

    def test_registro_operativo_de_compra_sin_cambios(self):
        self.assertEqual(_huellas_registro(), self.registro_antes)
        if self.registro_antes:
            reg = json.loads((RAIZ / "var" / "modelos" / "compra_30d" / "registro.json").read_text(encoding="utf-8"))
            estado = (reg["operativo"]["version"], (reg.get("sombra") or {}).get("version"))
            # Estado previo, o el de demostración autorizado (versión de demostración operativa con el modo activo; v1 recuperable).
            demo = (reg["operativo"]["decision"] == "demostracion"
                    and (reg.get("modo_demostracion") or {}).get("activo"))
            self.assertTrue(estado == ("v1", "v2") or demo, estado)
            self.assertFalse((RAIZ / "var" / "modelos" / "inactividad_60d").exists())


# ------------------------------------------------------------------------- API: permisos, portal y episodios
from _apoyo_app import CasoBase  # noqa: E402


def _fila_sombra(cid, corte, ultima, p, version="m2-fixture-a"):
    r = (corte - ultima).days if ultima else None
    base = {"cliente_id": cid, "modelo_id": "inactividad_60d", "horizonte_dias": 60, "umbral_frio_dias": 90, "version_modelo": version,
            "corte": corte.isoformat(), "datos_hasta": corte.isoformat(), "recencia_dias": r, "posicion": None}
    if r is None:
        return base | {"estado": "sin_historial", "probabilidad": None, "poblacion": "sin_historial", "motivos": ["Sin compras"]}
    if r >= 90:
        return base | {"estado": "no_elegible", "probabilidad": None, "poblacion": "ya_frio", "motivos": ["ya_frio"]}
    if r < 30:
        return base | {"estado": "estructural", "probabilidad": 0.0, "poblacion": "estructural", "motivos": ["Riesgo estructural cero"]}
    return base | {"estado": "estimado", "probabilidad": p, "poblacion": "aprendible", "motivos": [f"Última compra hace {r} días"]}


def _publicar_sombra(directorio, corte, ultimas, version="m2-fixture-a"):
    from modelos.ejecucion import json_bytes, publicar_lote
    filas = [_fila_sombra(c, corte, u, p, version) for c, (u, p) in sorted(ultimas.items())]
    est = sorted((f for f in filas if f["estado"] == "estimado"), key=lambda f: (-f["probabilidad"], f["cliente_id"]))
    for i, f in enumerate(est, 1):
        f["posicion"] = i
    man = {"version": 1, "tipo": "publicacion_sombra", "modelo_id": "inactividad_60d", "corte": corte.isoformat(),
           "estado_experimento": "experimental en sombra · prueba", "operativa": False, "advertencia": "prueba",
           "modelo": {"version": version, "artefacto_huella": "f" * 64, "decision": {"decision": "inconcluso"}},
           "cobertura": {"corte": corte.isoformat(), "datos_observados_hasta": corte.isoformat(), "fuente": "prueba", "estado": "verificada"},
           "conteos": {}, "tablas": {"predicciones_clientes": {"archivo": "predicciones_clientes.json", "filas": len(filas)}}}
    publicar_lote(directorio, {"predicciones_clientes.json": json_bytes(filas)}, "manifiesto.json", man)
    return directorio


# Últimas compras de la demo (agenda 2026-10-31) para cortes posteriores coherentes.
ULTIMAS = {"DEMO01": date(2026, 8, 2), "DEMO02": date(2026, 10, 10), "DEMO03": date(2026, 10, 25), "DEMO04": None,
           "DEMO05": date(2026, 9, 15), "DEMO06": date(2026, 10, 5), "DEMO07": date(2026, 10, 20), "DEMO08": date(2026, 6, 30)}
PROB = {"DEMO02": 0.31, "DEMO03": 0.22, "DEMO05": 0.74, "DEMO06": 0.45, "DEMO07": 0.40}


class PrevencionApiTests(CasoBase):
    def sombra(self, nombre, corte, cambios=None, version="m2-fixture-a"):
        from api import prevencion
        ult = {c: (u, PROB.get(c, 0.5)) for c, u in ULTIMAS.items()}
        ult.update(cambios or {})
        d = _publicar_sombra(self.tmp / nombre, corte, ult, version)
        return prevencion.importar_sombra(self.db, d, "ops1")

    def test_permisos_internos_y_exclusion_del_portal(self):
        from api.permisos import MATRIZ
        ident = {"operaciones": "ops1", "ventas": "ventas1", "finanzas": "fin1", "atencion": "aten1", "gerencia": "ger1", "empresa": "cli_a"}
        self.assertNotIn("empresa", MATRIZ["prevencion.ver"])
        for rol, u in ident.items():
            st, d = self.http("GET", "/api/prevencion", como=u)
            self.assertEqual(st, 200 if rol in MATRIZ["prevencion.ver"] else 403, rol)
        self.assertEqual(self.http("GET", "/api/prevencion")[0], 401)
        self.sombra("s1", date(2026, 11, 30))
        st, d = self.http("GET", "/api/prevencion", como="ventas1")
        self.assertTrue(d["experimental"])
        self.assertIn("sombra", d["sombra"]["estado_experimento"])
        self.assertEqual([i["cliente_id"] for i in d["items"]], ["DEMO05", "DEMO06", "DEMO07", "DEMO02", "DEMO03"])
        self.assertEqual(d["items"][0]["accion_c1"], "Seguimiento habitual")  # la acción C1 no cambia
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO05", como="ventas1")
        self.assertEqual(f["inactividad_sombra"]["probabilidad"], 0.74)
        self.assertTrue(f["inactividad_sombra"]["experimental"])
        _, a = self.http("GET", "/api/cierres/activo/agenda?q=DEMO05", como="ventas1")
        self.assertNotIn("inactividad", json.dumps(a))
        _, portal = self.http("GET", "/api/portal/beneficios", como="cli_a")
        self.assertNotIn("inactividad", json.dumps(portal).lower())
        self.assertEqual(self.http("POST", "/api/prevencion/sincronizar", {}, como="ventas1")[0], 403)
        self.assertEqual(self.http("POST", "/api/prevencion/sombra", {"ruta": str(self.tmp / "s1")}, como="ventas1")[0], 403)

    def test_tareas_desactivadas_por_defecto(self):
        from api import prevencion
        self.sombra("s1", date(2026, 11, 30))
        antes = self._tareas()
        r = prevencion.sincronizar(self.db, "ops1")
        self.assertFalse(r["activada"])
        self.assertEqual(r["propuestos"], ["DEMO02", "DEMO03", "DEMO05", "DEMO06", "DEMO07"])
        self.assertEqual(self._tareas(), antes)
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM episodios_prevencion").fetchone()[0], 0)

    def _tareas(self):
        with self.db.conexion() as con:
            return [dict(r) for r in con.execute("SELECT * FROM tareas ORDER BY id")]

    def _activar(self):
        self.assertEqual(self.http("POST", "/api/operacion/banderas", {"nombre": "prevencion_tareas", "activo": True}, como="ops1")[0], 200)

    def test_episodios_identidad_cierre_por_compra_y_resultados_humanos(self):
        from api import prevencion, tareas
        from api.publicacion import cierre_activo
        with self.db.conexion() as con:
            cid = cierre_activo(con)
        tareas.sincronizar(self.db, cid)  # seguimientos C1 existentes (cobertura, recompra, reactivación)
        c1 = {t["cliente_id"]: t for t in self._tareas()}
        self._activar()
        self.sombra("s1", date(2026, 11, 30))
        r = prevencion.sincronizar(self.db, "ops1")
        self.assertEqual((r["nuevos"], r["compartidos"], r["tareas_nuevas"]), (5, 3, 2))
        ts = self._tareas()
        self.assertEqual(len(ts), len(c1) + 2)
        for cliente in ("DEMO02", "DEMO03", "DEMO06"):  # mismo seguimiento, motivo añadido
            t = next(t for t in ts if t["cliente_id"] == cliente)
            self.assertEqual(t["id"], c1[cliente]["id"])
            self.assertIn(prevencion.MOTIVO, json.loads(t["motivos_json"]))
        # Repetir la sincronización no duplica nada.
        r2 = prevencion.sincronizar(self.db, "ops1")
        self.assertEqual((r2["nuevos"], r2["tareas_nuevas"], r2["sin_cambios"]), (0, 0, 5))
        self.assertEqual(len(self._tareas()), len(ts))
        # Acción humana sobre la tarea de DEMO05.
        t5 = next(t for t in self._tareas() if t["cliente_id"] == "DEMO05")
        tareas.accion(self.db, self.usuario("ventas1"), t5["id"], "asignar", {"version": t5["version"]})
        t5 = next(t for t in self._tareas() if t["cliente_id"] == "DEMO05")
        tareas.accion(self.db, self.usuario("ventas1"), t5["id"], "contacto", {"version": t5["version"], "siguiente_paso": "Llamar el lunes"})
        humano = {k: v for k, v in next(t for t in self._tareas() if t["cliente_id"] == "DEMO05").items() if k in ("estado", "responsable_id", "siguiente_paso", "resultado")}
        # Nuevo corte con OTRA versión de modelo: DEMO05 compró el 10-12 (episodio cerrado); DEMO07 sigue igual (mismo episodio).
        self.sombra("s2", date(2026, 12, 31), {"DEMO05": (date(2026, 12, 10), 0.5)}, version="m2-fixture-b")
        r3 = prevencion.sincronizar(self.db, "ops1")
        self.assertEqual(r3["cerrados_compra"], 1)
        self.assertEqual(r3["nuevos"], 0)
        with self.db.conexion() as con:
            ep = {r["episodio_id"]: dict(r) for r in con.execute("SELECT * FROM episodios_prevencion")}
        self.assertEqual(ep["prevencion:DEMO05:2026-09-15"]["estado"], "cerrado_compra")
        self.assertEqual(ep["prevencion:DEMO05:2026-09-15"]["fecha_compra_cierre"], "2026-12-10")
        self.assertEqual(ep["prevencion:DEMO07:2026-10-20"]["version_modelo_apertura"], "m2-fixture-a")
        t5b = next(t for t in self._tareas() if t["id"] == t5["id"])
        self.assertEqual({k: t5b[k] for k in humano}, humano)  # resultados humanos intactos
        # La persona cierra la tarea; DEMO05 vuelve a cumplir la política con otra última compra: episodio y tarea nuevos.
        tareas.accion(self.db, self.usuario("ventas1"), t5["id"], "atender", {"version": t5b["version"], "resultado": "Cliente contactado"})
        self.sombra("s3", date(2027, 2, 28), {"DEMO05": (date(2026, 12, 10), 0.8)}, version="m2-fixture-b")
        r4 = prevencion.sincronizar(self.db, "ops1")
        with self.db.conexion() as con:
            ep = {r["episodio_id"]: dict(r) for r in con.execute("SELECT * FROM episodios_prevencion")}
        self.assertEqual(ep["prevencion:DEMO05:2026-12-10"]["estado"], "abierto")
        self.assertGreaterEqual(r4["nuevos"], 1)
        viejo = next(t for t in self._tareas() if t["id"] == t5["id"])
        self.assertEqual((viejo["estado"], viejo["resultado"]), ("atendida", "Cliente contactado"))
        nuevas5 = [t for t in self._tareas() if t["cliente_id"] == "DEMO05"]
        self.assertEqual(len(nuevas5), 2)
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM (SELECT episodio_id FROM tareas GROUP BY 1 HAVING count(*) > 1)").fetchone()[0], 0)
            n_ev = con.execute("SELECT count(*) FROM eventos").fetchone()[0]
        prevencion.sincronizar(self.db, "ops1")
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM eventos").fetchone()[0], n_ev)

    def test_sombra_alterada_se_rechaza(self):
        from api import prevencion
        from api.base import ErrorApi
        d = _publicar_sombra(self.tmp / "s-alt", date(2026, 11, 30), {c: (u, 0.5) for c, u in ULTIMAS.items()})
        f = json.loads((d / "predicciones_clientes.json").read_text(encoding="utf-8"))
        f[0]["probabilidad"] = 0.99
        (d / "predicciones_clientes.json").write_text(json.dumps(f), encoding="utf-8")
        with self.assertRaises(ErrorApi):
            prevencion.importar_sombra(self.db, d, "ops1")


if __name__ == "__main__":
    unittest.main()
