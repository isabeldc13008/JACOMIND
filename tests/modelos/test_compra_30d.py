"""Pruebas de M1 (compra a 30 días): tiempo, datos aceptados, entrenamiento, persistencia, contratos e integración.

Las pruebas con el paquete sintético se omiten si no está disponible; las de entrenamiento,
además, si faltan las dependencias opcionales (requirements-modelos.txt).
"""
import contextlib
import copy
import csv
import io
import importlib.util
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
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None and importlib.util.find_spec("numpy") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _venta(cid, fecha, vid=None, estado="Confirmada", precio="100", producto="P1"):
    return {"venta_id": vid or f"V-{cid}-{fecha}", "cliente_id": cid, "producto_id": producto, "fecha": fecha, "cantidad": 1,
            "moneda": "COP", "precio_unitario": Decimal(precio), "descuento_pct": Decimal("0"), "estado": estado}


PRODUCTOS = {"P1": {"familia_prueba": "Software", "tipo_prueba": "Recurrente"},
             "P2": {"familia_prueba": "Servicios", "tipo_prueba": "Único"}}


def _historial(ventas):
    from modelos.variables import historial_compras
    return historial_compras(ventas, PRODUCTOS, {})


def _foto(ventas, corte, observado=date(2026, 12, 31), alta=date(2025, 1, 1), cid="C1"):
    from modelos.variables import construir_fotografias
    return construir_fotografias([{"cliente_id": cid, "fecha_alta": alta}], _historial(ventas), [corte], observado)[0]


def _artefacto(**cambios):
    from modelos.inferencia import FORMATO, sellar
    base = {"formato": FORMATO, "modelo_id": "compra_30d", "version": "prueba-v1", "version_variables": "compra_30d-variables-v1",
            "horizonte_dias": 30, "variables": ["recencia_dias", "frecuencia_30d", "intervalo_mediano_dias"],
            "transformaciones": [{"variable": "recencia_dias", "funcion": "log1p", "imputacion": 3.0, "media": 3.5, "desviacion": 1.2},
                                 {"variable": "frecuencia_30d", "funcion": "identidad", "imputacion": 0.0, "media": 0.7, "desviacion": 0.8},
                                 {"variable": "intervalo_mediano_dias", "funcion": "log1p", "imputacion": 3.4, "media": 3.4, "desviacion": 0.5}],
            "intercepto": 0.1, "pesos": [-0.4, 0.2, -0.1], "umbral": 0.45, "disponible_desde": "2026-10-30", "origen_datos": "sintetico"}
    base.update(cambios)
    return sellar(base)


# Datos y tiempo -----------------------------------------------------------------------------
class FronterasTemporalesTests(unittest.TestCase):
    corte = date(2026, 6, 30)

    def test_compra_al_corte_entra_en_variables_y_no_en_etiqueta(self):
        f = _foto([_venta("C1", self.corte)], self.corte)
        self.assertEqual((f["historial_n"], f["recencia_dias"], f["frecuencia_30d"]), (1, 0, 1))
        self.assertEqual((f["compra_30d"], f["estado_etiqueta"]), (0, "madura"))

    def test_dia_30_entra_y_dia_31_queda_fuera(self):
        previa = _venta("C1", date(2026, 6, 1), "V0")
        self.assertEqual(_foto([previa, _venta("C1", date(2026, 7, 30), "V1")], self.corte)["compra_30d"], 1)
        self.assertEqual(_foto([previa, _venta("C1", date(2026, 7, 31), "V1")], self.corte)["compra_30d"], 0)

    def test_horizonte_incompleto_permanece_pendiente(self):
        f = _foto([_venta("C1", date(2026, 6, 1))], self.corte, observado=date(2026, 7, 29))
        self.assertEqual((f["compra_30d"], f["estado_etiqueta"]), (None, "pendiente"))
        # Aunque exista una compra observada dentro del tramo visible, la etiqueta no se adelanta.
        f2 = _foto([_venta("C1", date(2026, 6, 1), "V0"), _venta("C1", date(2026, 7, 10), "V1")], self.corte, observado=date(2026, 7, 29))
        self.assertEqual(f2["estado_etiqueta"], "pendiente")
        self.assertEqual(_foto([_venta("C1", date(2026, 6, 1))], self.corte, observado=date(2026, 7, 30))["estado_etiqueta"], "madura")

    def test_alta_futura_queda_excluida(self):
        from modelos.compra import poblacion
        from modelos.inferencia import predicciones_corte
        f = _foto([], self.corte, alta=date(2026, 7, 1))
        self.assertEqual((f["elegibilidad"], f["compra_30d"]), ("alta_posterior", None))
        self.assertEqual(poblacion([f]), [])
        p = predicciones_corte(None, None, [{"cliente_id": "C1", "fecha_alta": date(2026, 7, 1)}], {}, self.corte)[0]
        self.assertEqual((p["estado"], p["probabilidad"]), ("no_elegible", None))

    def test_cliente_sin_compras_obtiene_sin_historial(self):
        from modelos.inferencia import desde_dict, predicciones_corte
        f = _foto([_venta("C1", date(2026, 7, 5))], self.corte)
        self.assertEqual(f["elegibilidad"], "sin_historial")
        art = desde_dict(_artefacto(disponible_desde="2026-01-01"))
        p = predicciones_corte(art, None, [{"cliente_id": "C1", "fecha_alta": date(2025, 1, 1)}], {}, self.corte)[0]
        self.assertEqual((p["estado"], p["probabilidad"]), ("sin_historial", None))
        self.assertTrue(p["motivos"])

    def test_venta_futura_no_modifica_variables_y_si_la_etiqueta(self):
        from modelos.variables import TODAS
        base = [_venta("C1", date(2026, 3, 1), "V0"), _venta("C1", date(2026, 6, 20), "V1")]
        a = _foto(base, self.corte)
        b = _foto(base + [_venta("C1", date(2026, 7, 2), "V2", precio="999999")], self.corte)
        self.assertEqual({k: a[k] for k in TODAS}, {k: b[k] for k in TODAS})
        self.assertEqual((a["compra_30d"], b["compra_30d"]), (0, 1))

    def test_mismo_dia_son_dos_operaciones_y_un_dia_de_compra(self):
        dia = date(2026, 6, 10)
        f = _foto([_venta("C1", dia, "V1"), _venta("C1", dia, "V2")], self.corte)
        self.assertEqual((f["historial_n"], f["dias_compra_distintos"]), (2, 1))
        self.assertIsNone(f["intervalo_mediano_dias"])  # no se inventa un intervalo
        self.assertEqual(f["historia_insuficiente"], 1)
        g = _foto([_venta("C1", date(2026, 4, 1), "A"), _venta("C1", date(2026, 5, 1), "B"), _venta("C1", date(2026, 5, 1), "C"),
                   _venta("C1", date(2026, 6, 10), "D")], self.corte)
        self.assertEqual((g["dias_compra_distintos"], g["intervalo_mediano_dias"], g["historia_insuficiente"]), (3, 35.0, 0))

    def test_ventanas_y_anuladas(self):
        ventas = [_venta("C1", date(2026, 6, 1), "A"), _venta("C1", date(2026, 5, 31), "B"),  # d=29 y d=30
                  _venta("C1", date(2026, 5, 2), "C"), _venta("C1", date(2026, 6, 15), "X", estado="Anulada")]
        f = _foto(ventas, self.corte)
        self.assertEqual((f["frecuencia_30d"], f["historial_n"], f["cambio_frecuencia_30d"]), (1, 3, 1 - 2))

    def test_cortes_y_fronteras_del_protocolo(self):
        from modelos.compra import cargar_config, verificar_fronteras
        from modelos.variables import cortes_mensuales
        config = cargar_config()
        cortes = cortes_mensuales(date(2025, 3, 31), date(2026, 9, 30))
        self.assertEqual((len(cortes), cortes[0], cortes[-1]), (19, date(2025, 3, 31), date(2026, 9, 30)))
        bloques = {n: [{"corte": c} for c in cortes if date.fromisoformat(a) <= c <= date.fromisoformat(b)]
                   for n, (a, b) in config["bloques"].items()}
        fr = verificar_fronteras(bloques, config)
        self.assertEqual(fr["validacion->comprobacion_historica"]["ultima_etiqueta_madura"], "2026-07-30")
        bloques["validacion"].append({"corte": date(2026, 7, 15)})
        with self.assertRaises(ValueError):
            verificar_fronteras(bloques, config)


# Datos aceptados (A01) --------------------------------------------------------------------
@unittest.skipIf(_paquete() is None, "Paquete de datos no disponible")
class DatosAceptadosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-datos-"))
        self.copia = self.tmp / "paquete"
        shutil.copytree(_paquete() / "01_Datos", self.copia / "01_Datos")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _anadir_ventas(self, filas):
        ruta = self.copia / "01_Datos" / "ventas.csv"
        with ruta.open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows(filas)

    def test_paquete_original_sin_revision_se_rechaza(self):
        from modelos.datos import LoteNoAceptado, cargar_datos
        with self.assertRaises(LoteNoAceptado):
            cargar_datos(self.copia, observado_hasta="2026-10-31")

    def test_duplicados_y_filas_aisladas_no_llegan_al_entrenamiento(self):
        from modelos.datos import LoteNoAceptado, cargar_datos, preparar_lote
        original = (self.copia / "01_Datos" / "ventas.csv").read_text(encoding="utf-8-sig").splitlines()
        duplicada = next(csv.reader([original[1]]))
        self._anadir_ventas([duplicada, ["VEN99999", "2026-02-10", "CLI999", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"]])
        r = preparar_lote(self.copia, self.tmp / "a01")
        self.assertEqual(r.status, "pendiente_revision")
        with self.assertRaises(LoteNoAceptado):
            cargar_datos(self.tmp / "a01", observado_hasta="2026-10-31")
        d = cargar_datos(self.tmp / "a01", aceptar_parcial=True, observado_hasta="2026-10-31")
        ids = [v["venta_id"] for v in d.ventas]
        self.assertEqual(len(ids), len(original) - 1)
        self.assertEqual(ids.count(duplicada[0]), 1)
        self.assertNotIn("VEN99999", ids)
        self.assertTrue(d.aceptacion_parcial)
        self.assertGreater(d.exclusiones["ventas"]["aisladas"] + d.exclusiones["ventas"]["duplicadas"], 0)

    def test_lote_pendiente_no_sustituye_al_ultimo_valido(self):
        from modelos.datos import LoteNoAceptado, cargar_datos, preparar_lote
        self.assertEqual(preparar_lote(self.copia, self.tmp / "a01").status, "publicable")
        antes = (self.tmp / "a01" / "publicado" / "ventas.csv").read_bytes()
        self._anadir_ventas([["VEN99998", "2026-02-10", "CLI999", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"]])
        self.assertEqual(preparar_lote(self.copia, self.tmp / "a01").status, "pendiente_revision")
        self.assertEqual((self.tmp / "a01" / "publicado" / "ventas.csv").read_bytes(), antes)
        with self.assertRaises(LoteNoAceptado):
            cargar_datos(self.tmp / "a01", observado_hasta="2026-10-31")

    def test_generar_rechaza_lote_pendiente_salvo_aceptacion_parcial(self):
        from pipeline.generar import generar
        self._anadir_ventas([["VEN99997", "2026-10-10", "CLI999", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"]])
        with self.assertRaises(RuntimeError):
            generar(self.copia, "2026-10-31", self.tmp / "pub", registro=self.tmp / "sin_registro")
        m = generar(self.copia, "2026-10-31", self.tmp / "pub2", registro=self.tmp / "sin_registro", aceptar_parcial=True,
                    observado_hasta="2026-10-31")  # la copia modificada no hereda la cobertura del paquete sintético
        hist = json.loads((self.tmp / "pub2" / "historial_ventas.json").read_text(encoding="utf-8"))
        self.assertNotIn("CLI999", {h["cliente_id"] for h in hist})
        self.assertTrue(m["calidad"]["datos_aceptados"]["aceptacion_parcial"])

    def test_cobertura_debe_declararse_y_ser_coherente(self):
        from modelos.datos import CoberturaInsuficiente, LoteNoAceptado, cargar_datos, preparar_lote
        preparar_lote(self.copia, self.tmp / "a01")
        # Copia idéntica del paquete: aplica la declaración registrada (huellas de origen idénticas).
        d = cargar_datos(self.tmp / "a01")
        self.assertEqual(d.observado_hasta, date(2026, 10, 31))
        self.assertIn("declaración registrada", d.fuente_cobertura)
        with self.assertRaises(LoteNoAceptado):
            cargar_datos(self.tmp / "a01", observado_hasta="2026-09-30")  # hay ventas posteriores: incoherente
        # Lote distinto (simula un lote empresarial sin metadatos): no hereda la fecha sintética.
        self._anadir_ventas([["VEN99996", "2026-10-20", "CLI001", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"]])
        preparar_lote(self.copia, self.tmp / "a01-b")
        with self.assertRaises(CoberturaInsuficiente):
            cargar_datos(self.tmp / "a01-b")  # sin declaración no se deduce de la última venta
        self.assertEqual(cargar_datos(self.tmp / "a01-b", observado_hasta="2026-10-31").observado_hasta, date(2026, 10, 31))


# Métricas ---------------------------------------------------------------------------------
class MetricasTests(unittest.TestCase):
    def test_empates_por_cliente_y_denominador_min_k_n(self):
        from modelos import metricas as M
        filas = [{"cliente_id": c, "corte": date(2026, 7, 31), "compra_30d": y, "p": 0.5} for c, y in (("C3", 1), ("C1", 0), ("C2", 1))]
        r = M.ranking_k(filas, lambda f: f["p"], 2)
        self.assertEqual(r["clientes"], ["C1", "C2"])
        self.assertEqual((r["aciertos"], r["precision"], r["k_efectivo"]), (1, 0.5, 2))
        r10 = M.ranking_k(filas, lambda f: f["p"], 10)
        self.assertEqual((r10["k_efectivo"], r10["precision"], r10["sensibilidad"]), (3, 2 / 3, 1.0))
        self.assertAlmostEqual(M.average_precision(filas, lambda f: f["p"]), (1 / 2 + 2 / 3) / 2)

    def test_average_precision_coincide_con_sklearn_sin_empates(self):
        if not HAY_SKLEARN:
            self.skipTest("sin sklearn")
        from sklearn.metrics import average_precision_score
        from modelos import metricas as M
        ys = [1, 0, 1, 1, 0, 0, 1, 0]
        ps = [0.9, 0.8, 0.7, 0.6, 0.55, 0.4, 0.3, 0.1]
        filas = [{"cliente_id": f"C{i}", "compra_30d": y, "p": p} for i, (y, p) in enumerate(zip(ys, ps))]
        self.assertAlmostEqual(M.average_precision(filas, lambda f: f["p"]), average_precision_score(ys, ps))


# Persistencia -----------------------------------------------------------------------------
class ArtefactoTests(unittest.TestCase):
    def test_guardar_y_recargar_conserva_probabilidades(self):
        from modelos.inferencia import TOLERANCIA_PROBABILIDAD, cargar_artefacto, desde_dict
        datos = _artefacto()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "artefacto.json").write_text(json.dumps(datos), encoding="utf-8")
            recargado = cargar_artefacto(tmp)
        fila = {"recencia_dias": 12, "frecuencia_30d": 2, "intervalo_mediano_dias": None}
        self.assertLessEqual(abs(recargado.probabilidad(fila) - desde_dict(datos).probabilidad(fila)), TOLERANCIA_PROBABILIDAD)

    def test_rechaza_dimensiones_nan_infinito_y_versiones(self):
        from modelos.inferencia import ArtefactoInvalido, desde_dict, huella_artefacto
        buena = _artefacto()

        def resellar(d):
            d = copy.deepcopy(d)
            d["huella"] = huella_artefacto(d)
            return d
        casos = {"dimension": dict(buena, pesos=[0.1, 0.2]), "nan": dict(buena, pesos=[math.nan, 0.2, 0.1]),
                 "infinito": dict(buena, intercepto=math.inf), "variables": dict(buena, version_variables="compra_30d-variables-v9"),
                 "formato": dict(buena, formato="otro.v2"), "horizonte": dict(buena, horizonte_dias=60),
                 "desviacion": dict(buena, transformaciones=[dict(buena["transformaciones"][0], desviacion=0)] + buena["transformaciones"][1:])}
        for nombre, d in casos.items():
            with self.subTest(nombre), self.assertRaises(ArtefactoInvalido):
                desde_dict(resellar(d))
        alterado = dict(buena, umbral=0.1)  # sin recalcular huella
        with self.assertRaises(ArtefactoInvalido):
            desde_dict(alterado)

    def test_puntuar_con_entrenamiento_deshabilitado(self):
        from modelos import compra
        from modelos.datos import DatosAceptados
        from modelos.inferencia import desde_dict
        datos = DatosAceptados(directorio=Path("."), revision=1, estado_lote="publicable", aceptacion_parcial=False, huellas={},
                               huella_datos="x", huellas_origen={}, exclusiones={}, observado_hasta=date(2026, 10, 31),
                               fuente_cobertura="prueba", convencion_disponibilidad="fecha_evento",
                               clientes=[{"cliente_id": "C1", "fecha_alta": date(2025, 1, 1)}, {"cliente_id": "C2", "fecha_alta": date(2025, 1, 1)}],
                               ventas=[_venta("C1", date(2026, 10, 1)), _venta("C1", date(2026, 9, 1))], productos=PRODUCTOS, tasas={})
        bloqueo = {m: None for m in ("sklearn", "sklearn.linear_model", "numpy", "scipy")}
        with mock.patch.dict(sys.modules, bloqueo), \
                mock.patch.object(compra, "ajustar_logistica", side_effect=AssertionError("no debe entrenar")), \
                mock.patch.object(compra, "entrenar", side_effect=AssertionError("no debe entrenar")):
            r = compra.puntuar(desde_dict(_artefacto()), datos, date(2026, 10, 31))
        estados = {f["cliente_id"]: f["estado"] for f in r["filas"]}
        self.assertEqual(estados, {"C1": "estimado", "C2": "sin_historial"})
        self.assertEqual(r["resumen"]["etiquetas"]["pendientes"], 2)
        self.assertEqual(r["resumen"]["etiquetas"]["maduran_el"], "2026-11-30")
        with self.assertRaises(ValueError):  # antes de la disponibilidad requiere simulación explícita
            compra.puntuar(desde_dict(_artefacto()), datos, date(2026, 9, 30))


class RegistroTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-reg-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _decision(self, art, decision="inconcluso", maximo="sombra", origen="sintetico"):
        d = {"decision": decision, "estado_maximo": maximo, "artefacto_huella": art.huella, "origen_datos": origen}
        if maximo == "operativo" and origen != "sintetico":
            d["aprobado_por"] = "fixture-aprobador"
        return d

    def test_promocion_sombra_operativo_y_reversion(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        v1, v2 = desde_dict(_artefacto(version="ref")), desde_dict(_artefacto(version="cand", intercepto=0.3))
        R.promover(self.tmp, "compra_30d", "v1", v1, self._decision(v1, "favorable", "operativo", "fixture"), {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", v2, self._decision(v2), {}, "sombra")
        with self.assertRaises(R.RegistroError):  # sintético inconcluso: solo sombra
            R.promover(self.tmp, "compra_30d", "v2", v2, self._decision(v2), {}, "operativo")
        with self.assertRaises(R.RegistroError):  # rechazado: ni sombra
            R.promover(self.tmp, "compra_30d", "v3", v2, self._decision(v2, "rechazado", "ninguno"), {}, "sombra")
        with self.assertRaises(R.RegistroError):  # decisión de otro artefacto
            R.promover(self.tmp, "compra_30d", "v4", v2, self._decision(v1), {}, "sombra")
        with self.assertRaises(R.RegistroError):  # versión inmutable
            R.promover(self.tmp, "compra_30d", "v1", v2, self._decision(v2), {}, "sombra")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d", "operativo")[0].version, "ref")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d", "sombra")[0].version, "cand")
        # Un registro empresarial aprobado puede pasar a operativo y revertirse a la versión anterior.
        R.promover(self.tmp, "compra_30d", "v2", v2, self._decision(v2, "favorable", "operativo", "empresarial"), {}, "operativo")
        reg = R.leer_registro(self.tmp, "compra_30d")
        self.assertEqual((reg["operativo"]["version"], reg["sombra"]), ("v2", None))
        reg = R.revertir(self.tmp, "compra_30d", "operativo")
        self.assertEqual(reg["operativo"]["version"], "v1")
        self.assertTrue((self.tmp / "compra_30d" / "v2" / "artefacto.json").exists())  # nada se borra
        self.assertFalse([p for p in (self.tmp / "compra_30d").iterdir() if p.name.startswith(".")])  # sin temporales

    def test_artefacto_alterado_en_registro_queda_no_disponible(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        v1 = desde_dict(_artefacto())
        R.promover(self.tmp, "compra_30d", "v1", v1, self._decision(v1, "favorable", "operativo", "fixture"), {}, "operativo")
        ruta = self.tmp / "compra_30d" / "v1" / "artefacto.json"
        d = json.loads(ruta.read_text(encoding="utf-8"))
        d["pesos"][0] = float("nan")
        ruta.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaises(R.ModeloNoDisponible):
            R.artefacto_registrado(self.tmp, "compra_30d", "operativo")
        with self.assertRaises(R.ModeloNoDisponible):
            R.artefacto_registrado(self.tmp / "vacio", "compra_30d", "operativo")


# Contratos --------------------------------------------------------------------------------
class ContratoPrediccionesTests(unittest.TestCase):
    def _publicacion(self, tmp, predicciones, agenda_prob=0.5):
        agenda = {"version": 1, "corte": "2026-10-31", "origen": "sintetico", "modelo": {"version": "m", "umbral": 0.4},
                  "resumen": {"clientes": 1, "ventas_confirmadas": 1, "ingreso_cop": 10.0, "clientes_frios": 0},
                  "clientes": [{"cliente_id": "C1", "ultima_compra": "2026-10-01", "dias_sin_compra": 30, "ventas_confirmadas": 1,
                                "ingreso_cop": 10.0, "productos": [], "frecuente": False, "frio": False, "renovaciones_proximas": 0,
                                "coberturas_vencidas": 0, "prob_compra_30d": agenda_prob, "accion": "Revisar oportunidad de recompra"}]}
        man = {"version": 1, "tipo": "publicacion_analitica", "cierre_id": "x", "corte": "2026-10-31", "origen": "sintetico",
               "cobertura": {"corte": "2026-10-31", "datos_observados_hasta": "2026-10-31", "fuente": "fixture", "estado": "verificada"},
               "huellas_entrada": {}, "versiones": {}, "tablas": {"agenda": {"archivo": "agenda.json", "filas": 1},
                                                              "predicciones_clientes": {"archivo": "p.json", "filas": len(predicciones)}}}
        for nombre, datos in (("manifiesto.json", man), ("agenda.json", agenda), ("p.json", predicciones)):
            (Path(tmp) / nombre).write_text(json.dumps(datos), encoding="utf-8")

    def _fila(self, **c):
        return {"cliente_id": "C1", "modelo_id": "compra_30d", "probabilidad": 0.5, "estado": "estimado", "horizonte_dias": 30,
                "version_modelo": "m", "corte": "2026-10-31", "datos_hasta": "2026-10-31", "motivos": ["Última compra hace 30 días"]} | c

    def test_valida_tipos_rangos_claves_y_coherencia(self):
        from contratos.validar import validar_publicacion
        casos = {"valido": ([self._fila()], 0.5, True), "duplicada": ([self._fila(), self._fila()], 0.5, False),
                 "rango": ([self._fila(probabilidad=1.5)], 1.5, False), "estado": ([self._fila(estado="sin_historial")], 0.5, False),
                 "nula_estimada": ([self._fila(probabilidad=None)], None, False), "agenda_distinta": ([self._fila()], 0.4, False),
                 "horizonte": ([self._fila(horizonte_dias=60)], 0.5, False), "corte": ([self._fila(corte="2026-09-30")], 0.5, False),
                 "tipo": ([self._fila(probabilidad="0.5")], 0.5, False), "modelo": ([self._fila(modelo_id="otro")], 0.5, False),
                 "version": ([self._fila(version_modelo="otra")], 0.5, False), "sin_motivos": ([self._fila(motivos=[])], 0.5, False),
                 "futuro": ([self._fila(datos_hasta="2026-11-15")], 0.5, False)}
        for nombre, (filas, prob_agenda, valido) in casos.items():
            with self.subTest(nombre), tempfile.TemporaryDirectory() as tmp:
                self._publicacion(tmp, filas, prob_agenda)
                r, _ = validar_publicacion(tmp)
                self.assertEqual(r.valido, valido, r.errores)

    def test_agenda_rechaza_id_repetido(self):
        from contratos.validar import validar_agenda
        agenda = json.loads((RAIZ / "contratos" / "ejemplos" / "agenda" / "valido.json").read_text(encoding="utf-8"))
        agenda["clientes"].append(dict(agenda["clientes"][0]))
        agenda["resumen"]["clientes"] += 1
        self.assertFalse(validar_agenda(agenda).valido)


# Entrenamiento e integración con el paquete ------------------------------------------------
@unittest.skipIf(_paquete() is None, "Paquete de datos no disponible")
class IntegracionPaqueteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.cli import main
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1-int-"))
        cls.a01 = cls.tmp / "a01"
        cls.registro = cls.tmp / "registro"
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["preparar", "--datos", str(_paquete()), "--salida", str(cls.a01)]) == 0
            assert main(["inicializar-referencia", "--datos", str(cls.a01), "--registro", str(cls.registro), "--version", "v1"]) == 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_referencia_reproduce_controles(self):
        from modelos.compra import cargar_config, cargar_datos_config, reproducir_referencia
        config = cargar_config()
        rep = reproducir_referencia(cargar_datos_config(self.a01, config), config)
        self.assertTrue(rep["controles"]["coincide"], rep["controles"]["diferencias"])
        self.assertEqual(rep["controles"]["obtenido"]["top10_recencia"], {"2026-07-31": 5, "2026-08-31": 7, "2026-09-30": 5})

    def test_cierre_usa_el_artefacto_seleccionado_y_reproduce_la_referencia(self):
        from contratos.validar import validar_publicacion
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        from pipeline.generar import generar
        salida = self.tmp / "oct-v1"
        generar(_paquete(), "2026-10-31", salida, registro=self.registro)
        r, datos = validar_publicacion(salida)
        self.assertTrue(r.valido, r.errores)
        agenda = datos["agenda"]
        self.assertEqual(agenda["modelo"], {"version": "A04-logistica-reglas-v1", "umbral": 0.4})
        self.assertEqual(agenda["resumen"], {"clientes": 120, "ventas_confirmadas": 1371, "ingreso_cop": 5647449456.36, "clientes_frios": 41})
        # Otro artefacto registrado como operativo cambia la publicación sin reentrenar.
        reg2 = self.tmp / "registro2"
        shutil.copytree(self.registro, reg2)
        otro = desde_dict(_artefacto(version="otro-operativo", disponible_desde="2026-10-30"))
        R.promover(reg2, "compra_30d", "v9", otro, {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": otro.huella,
                                                     "origen_datos": "fixture", "aprobado_por": "fixture"}, {}, "operativo")
        salida2 = self.tmp / "oct-v9"
        m = generar(_paquete(), "2026-10-31", salida2, registro=reg2)
        r2, datos2 = validar_publicacion(salida2)
        self.assertTrue(r2.valido, r2.errores)
        self.assertEqual(datos2["agenda"]["modelo"]["version"], "otro-operativo")
        self.assertEqual(m["versiones"]["modelo_compra"], "otro-operativo")
        preds = {p["cliente_id"]: p for p in datos2["predicciones_clientes"]}
        for c in datos2["agenda"]["clientes"]:
            self.assertEqual(c["prob_compra_30d"], preds[c["cliente_id"]]["probabilidad"])
        R.revertir(reg2, "compra_30d", "operativo")
        generar(_paquete(), "2026-10-31", self.tmp / "oct-revertido", registro=reg2)
        rev = json.loads((self.tmp / "oct-revertido" / "agenda.json").read_text(encoding="utf-8"))
        self.assertEqual(rev["clientes"], agenda["clientes"])

    def test_ausencia_de_modelo_genera_nulos_entendibles(self):
        from contratos.validar import validar_publicacion
        from pipeline.generar import generar
        salida = self.tmp / "sin-modelo"
        m = generar(_paquete(), "2026-10-31", salida, registro=self.tmp / "vacio")
        r, datos = validar_publicacion(salida)
        self.assertTrue(r.valido, r.errores)
        self.assertIsNone(datos["agenda"]["modelo"])
        self.assertTrue(all(c["prob_compra_30d"] is None for c in datos["agenda"]["clientes"]))
        self.assertNotIn("Revisar oportunidad de recompra", {c["accion"] for c in datos["agenda"]["clientes"]})
        estados = {p["estado"] for p in datos["predicciones_clientes"]}
        self.assertEqual(estados, {"modelo_no_disponible"})
        self.assertIn("No hay versión operativa", datos["predicciones_clientes"][0]["motivos"][0])
        self.assertEqual(m["calidad"]["modelo_compra"]["estado"], "no_disponible")
        # Corte anterior a la disponibilidad: abstención explícita aunque exista el artefacto.
        generar(_paquete(), "2026-09-30", self.tmp / "sep", registro=self.registro)
        p = json.loads((self.tmp / "sep" / "predicciones_clientes.json").read_text(encoding="utf-8"))
        self.assertTrue(all(x["probabilidad"] is None for x in p))
        self.assertIn("anterior a la disponibilidad", p[0]["motivos"][0])

    def test_agenda_ficha_coinciden_y_regenerar_preserva_tareas(self):
        from api import base, consultas, publicacion, tareas
        from api.auth import cargar_usuario
        from api.base import BaseDatos
        from api.demo import preparar
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        from pipeline.generar import generar
        base.fijar_hoy("2026-11-21")
        try:
            db = BaseDatos(self.tmp / "app.sqlite3")
            preparar(db, publicar_muestra=False)
            generar(_paquete(), "2026-10-31", self.tmp / "pub1", registro=self.registro)
            c1 = publicacion.publicar_ruta(db, self.tmp / "pub1", "ops1")["cierre_id"]
            with db.conexion() as con:
                items = consultas.agenda(con, c1, tam=200)["items"]
                self.assertEqual(len(items), 120)
                for it in items:
                    f = consultas.ficha(con, c1, it["cliente_id"])["cliente"]
                    self.assertEqual((f["prob_compra_30d"], f["prediccion"]), (it["prob_compra_30d"], it["prediccion"]))
                    self.assertEqual(it["prob_compra_30d"], it["prediccion"]["probabilidad"])
                    self.assertTrue(it["prediccion"]["motivos"])
                lista = tareas.listar(con)
                usuario = cargar_usuario(con, "ventas1")
            self.assertTrue(lista)
            descartada, pospuesta = lista[0], lista[1]
            tareas.accion(db, usuario, descartada["id"], "descartar", {"version": descartada["version"], "motivo": "Decisión humana"})
            tareas.accion(db, usuario, pospuesta["id"], "posponer", {"version": pospuesta["version"], "hasta": "2026-12-15"})
            # Regenerar el mismo corte con otra versión operativa.
            reg2 = self.tmp / "registro-tareas"
            shutil.copytree(self.registro, reg2)
            otro = desde_dict(_artefacto(version="otro-tareas", intercepto=2.0))
            R.promover(reg2, "compra_30d", "v9", otro, {"decision": "favorable", "estado_maximo": "operativo", "aprobado_por": "fixture",
                                                         "artefacto_huella": otro.huella, "origen_datos": "fixture"}, {}, "operativo")
            generar(_paquete(), "2026-10-31", self.tmp / "pub2", registro=reg2)
            r2 = publicacion.publicar_ruta(db, self.tmp / "pub2", "ops1")
            self.assertFalse(r2["ya_publicado"])
            with db.conexion() as con:
                todas = con.execute("SELECT episodio_id, count(*) FROM tareas GROUP BY episodio_id HAVING count(*) > 1").fetchall()
                self.assertEqual(todas, [])
                d = tareas.detalle(con, descartada["id"])
                p = tareas.detalle(con, pospuesta["id"])
            self.assertEqual(d["estado"], "descartada")
            self.assertEqual(p["estado"], "pospuesta")
        finally:
            base.fijar_hoy(None)

    def test_publicacion_invalida_conserva_el_cierre_anterior(self):
        from api import base, publicacion
        from api.base import BaseDatos, ErrorApi
        from api.demo import solo_permisos
        from pipeline.generar import generar
        base.fijar_hoy("2026-11-21")
        try:
            db = BaseDatos(self.tmp / "pub.sqlite3")
            solo_permisos(db)
            generar(_paquete(), "2026-10-31", self.tmp / "valida", registro=self.registro)
            activo = publicacion.publicar_ruta(db, self.tmp / "valida", "ops1")["cierre_id"]
            mala = self.tmp / "mala"
            shutil.copytree(self.tmp / "valida", mala)
            p = json.loads((mala / "predicciones_clientes.json").read_text(encoding="utf-8"))
            p[1] = dict(p[0])  # clave duplicada cliente_id + modelo_id
            (mala / "predicciones_clientes.json").write_text(json.dumps(p), encoding="utf-8")
            with self.assertRaises(ErrorApi):
                publicacion.publicar_ruta(db, mala, "ops1")
            with db.conexion() as con:
                self.assertEqual(publicacion.cierre_activo(con), activo)
        finally:
            base.fijar_hoy(None)

    def test_api_y_cierre_funcionan_sin_dependencias_de_entrenamiento(self):
        codigo = (
            "import sys\n"
            "class B:\n"
            "    def find_spec(self, n, p=None, t=None):\n"
            "        if n.split('.')[0] in ('sklearn', 'numpy', 'scipy'): raise ImportError('bloqueado: ' + n)\n"
            "sys.meta_path.insert(0, B())\n"
            "import api.servidor, api.consultas, modelos.inferencia, modelos.registro, modelos.datos\n"
            "from pipeline.generar import generar\n"
            f"m = generar(r'{_paquete()}', '2026-10-31', r'{self.tmp / 'sin-deps'}', registro=r'{self.registro}')\n"
            "assert m['versiones']['modelo_compra'] == 'A04-logistica-reglas-v1'\n"
            "assert 'sklearn' not in sys.modules and 'numpy' not in sys.modules\n"
            "print('ok')\n")
        p = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-2000:])
        self.assertIn("ok", p.stdout)


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class EntrenamientoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_config, cargar_datos_config, entrenar
        from modelos.datos import preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1-ent-"))
        cls.config = cargar_config()
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos_config(cls.tmp / "a01", cls.config)
        cls.res = entrenar(cls.datos, cls.config, cls.tmp / "ejecucion")
        # Copia del paquete con cambios solo en el periodo de comprobación (después del 30 de julio de 2026).
        copia = cls.tmp / "paquete-mod"
        shutil.copytree(_paquete() / "01_Datos", copia / "01_Datos")
        with (copia / "01_Datos" / "ventas.csv").open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerows([["VEN90001", "2026-08-12", "CLI001", "PRO01", "3", "COP", "5000000", "0", "Confirmada", "Prueba"],
                                     ["VEN90002", "2026-09-03", "CLI002", "PRO02", "1", "COP", "100000", "0", "Confirmada", "Prueba"],
                                     ["VEN90003", "2026-08-31", "CLI050", "PRO04", "2", "COP", "70000", "0", "Confirmada", "Prueba"]])
        preparar_lote(copia, cls.tmp / "a01-mod")
        cls.res_mod = entrenar(cargar_datos_config(cls.tmp / "a01-mod", cls.config, observado_hasta="2026-10-31"), cls.config, None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_modificar_solo_prueba_no_cambia_candidato_transformaciones_ni_umbral(self):
        a, b = self.res["artefacto"], self.res_mod["artefacto"]
        self.assertNotEqual(a["entrenamiento"]["huella_datos"], b["entrenamiento"]["huella_datos"])
        for campo in ("variables", "transformaciones", "intercepto", "pesos", "umbral", "combinacion", "C"):
            self.assertEqual(a[campo], b[campo], campo)
        self.assertEqual(self.res["seleccion"]["rejilla"], self.res_mod["seleccion"]["rejilla"])

    def test_seleccion_usa_solo_ajuste_y_validacion(self):
        cong = self.res["congelacion"]
        self.assertEqual(cong["bloques_usados"], ["ajuste", "validacion"])
        self.assertNotIn("comprobacion_historica", self.res["datos"]["bloques"])
        self.assertEqual(self.res["artefacto"]["politica_umbral"]["bloque"], "validacion")
        cortes = self.res["artefacto"]["entrenamiento"]["cortes"]
        self.assertEqual((cortes[0], cortes[-1]), ("2025-03-31", "2026-04-30"))
        self.assertEqual(len(self.res["seleccion"]["rejilla"]), 9)

    def test_equivalencia_json_y_evaluacion_sin_reajuste(self):
        from modelos.compra import evaluar
        from modelos.inferencia import TOLERANCIA_PROBABILIDAD
        self.assertLessEqual(self.res["congelacion"]["equivalencia_json_sklearn"]["diferencia_maxima"], TOLERANCIA_PROBABILIDAD)
        antes = (self.tmp / "ejecucion" / "artefacto.json").read_bytes()
        with mock.patch("modelos.compra.ajustar_logistica", side_effect=AssertionError("evaluar no debe ajustar")):
            r = evaluar(self.tmp / "ejecucion", self.datos)
        self.assertEqual((self.tmp / "ejecucion" / "artefacto.json").read_bytes(), antes)
        self.assertIn(r["decision"]["decision"], ("favorable", "rechazado", "inconcluso"))
        res = r["metricas"]["resultados"]
        self.assertEqual(set(res), {"candidato", "original_congelado", "regla_30d", "recencia", "constante"})
        self.assertEqual([m["top10"]["aciertos"] for m in res["recencia"]["ranking"]["por_mes"]], [5, 7, 5])
        self.assertEqual(res["original_congelado"]["matriz"]["TP"], 120)
        self.assertEqual(r["metricas"]["poblacion"]["poblacion"], 360)
        self.assertTrue((self.tmp / "ejecucion" / "predicciones.csv").exists())


if __name__ == "__main__":
    unittest.main()
