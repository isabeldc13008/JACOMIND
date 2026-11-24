"""Regresión de los siete hallazgos de la auditoría M1 (2026-11-23).

Las coberturas "hasta 2026-11-30" que aparecen aquí son fixtures hipotéticos para ejercitar la
maduración de etiquetas: no son datos ni resultados comerciales de noviembre.
"""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None and importlib.util.find_spec("numpy") is not None
PRODUCTOS = {"P1": {"familia_prueba": "Software", "tipo_prueba": "Recurrente"}}


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _venta(cid, fecha, vid):
    return {"venta_id": vid, "cliente_id": cid, "producto_id": "P1", "fecha": fecha, "cantidad": 1, "moneda": "COP",
            "precio_unitario": Decimal("100"), "descuento_pct": Decimal("0"), "estado": "Confirmada"}


def _artefacto(**cambios):
    from modelos.inferencia import FORMATO, sellar
    base = {"formato": FORMATO, "modelo_id": "compra_30d", "version": "fixture-op", "version_variables": "compra_30d-variables-v1",
            "horizonte_dias": 30, "variables": ["recencia_dias", "frecuencia_90d"],
            "transformaciones": [{"variable": "recencia_dias", "funcion": "log1p", "imputacion": 3.0, "media": 3.0, "desviacion": 1.0},
                                 {"variable": "frecuencia_90d", "funcion": "identidad", "imputacion": 1.0, "media": 1.0, "desviacion": 1.0}],
            "intercepto": 0.0, "pesos": [-0.5, 0.3], "umbral": 0.5, "disponible_desde": "2026-10-30", "origen_datos": "sintetico"}
    base.update(cambios)
    return sellar(base)


def _datos(observado=date(2026, 10, 31), clientes=None, ventas=None, huella="lote-a"):
    from modelos.datos import DatosAceptados
    clientes = clientes or [{"cliente_id": f"C{i:02d}", "fecha_alta": date(2025, 1, 1)} for i in range(1, 13)]
    if ventas is None:
        ventas = [_venta(f"C{i:02d}", date(2026, 10, 31 - 2 * i), f"V{i}") for i in range(1, 13)]
    return DatosAceptados(directorio=Path("."), revision=1, estado_lote="publicable", aceptacion_parcial=False, huellas={},
                          huella_datos=huella, huellas_origen={}, exclusiones={}, observado_hasta=observado,
                          fuente_cobertura="fixture", convencion_disponibilidad="fecha_evento",
                          clientes=clientes, ventas=ventas, productos=PRODUCTOS, tasas={})


def _leer_csv(p):
    with Path(p).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _escribir_csv(p, filas):
    with Path(p).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)


class _ConPuntuaciones(unittest.TestCase):
    """Puntuaciones de octubre con dos artefactos de fixture y un lote de 12 clientes."""

    def setUp(self):
        from modelos import compra
        from modelos.inferencia import desde_dict
        self.compra = compra
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-corr-"))
        self.datos = _datos()
        self.op, self.sb = desde_dict(_artefacto()), desde_dict(_artefacto(version="fixture-sombra", pesos=[-0.2, 0.6]))
        self.corte = date(2026, 10, 31)
        compra.puntuar(self.op, self.datos, self.corte, self.tmp / "op")
        compra.puntuar(self.sb, self.datos, self.corte, self.tmp / "sb")
        self.salida = self.tmp / "cmp"
        # Fixture: lote posterior con cobertura hipotética hasta el 30-11 y una compra de C01 el 10-11.
        self.maduro = _datos(observado=date(2026, 11, 30), ventas=self.datos.ventas + [_venta("C01", date(2026, 11, 10), "VN1")],
                             huella="lote-b")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def comparar(self, datos=None, sombra=None, **kw):
        return self.compra.comparar(self.tmp / "op", sombra or self.tmp / "sb", self.salida, datos, 10, **kw)

    def registrar_contacto(self, cliente="C01", **valores):
        ruta = self.salida / "piloto_registro.csv"
        filas = _leer_csv(ruta)
        humano = {"contacto_realizado": "si", "fecha_contacto": "2026-11-15", "tiempo_minutos": "12",
                  "resultado_contacto": "Solicita cotización"} | valores
        for f in filas:
            if f["cliente_id"] == cliente:
                f.update(humano)
        _escribir_csv(ruta, filas)
        return humano

    def fila(self, cliente="C01", seleccion=None):
        return next(f for f in _leer_csv(self.salida / "piloto_registro.csv")
                    if f["cliente_id"] == cliente and (seleccion is None or f["seleccion_id"] == seleccion))


# Hallazgo 1 ------------------------------------------------------------------------------
class SeguimientoHumanoTests(_ConPuntuaciones):
    def test_repetir_comparar_conserva_contacto_fecha_minutos_y_resultado(self):
        self.comparar(self.datos)
        humano = self.registrar_contacto()
        self.comparar(self.datos)
        self.assertEqual({k: self.fila()[k] for k in humano}, humano)

    def test_etiquetas_maduran_sin_perder_campos_humanos(self):
        self.comparar(self.datos)
        self.assertEqual(self.fila()["estado_etiqueta"], "pendiente")
        humano = self.registrar_contacto()
        r = self.comparar(self.maduro)
        f = self.fila()
        self.assertEqual((f["estado_etiqueta"], f["compra_30d"]), ("madura", "1"))
        self.assertEqual({k: f[k] for k in humano}, humano)
        self.assertEqual(r["piloto"]["con_seguimiento_humano"], 1)
        # Una ejecución posterior sin lote de observación no degrada la etiqueta madura ni borra el contacto.
        self.comparar(None)
        self.assertEqual((self.fila()["estado_etiqueta"], self.fila()["compra_30d"]), ("madura", "1"))

    def test_repetir_la_misma_operacion_no_cambia_el_registro(self):
        self.comparar(self.maduro)
        self.registrar_contacto()
        self.comparar(self.maduro)
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        self.comparar(self.maduro)
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)

    def test_entrada_invalida_o_duplicada_conserva_el_archivo(self):
        from modelos.compra import PilotoError
        self.comparar(self.datos)
        self.registrar_contacto(tiempo_minutos="doce")
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        with self.assertRaises(PilotoError):
            self.comparar(self.maduro)
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)
        filas = _leer_csv(self.salida / "piloto_registro.csv")
        filas[1]["tiempo_minutos"] = filas[0]["tiempo_minutos"] = "12"
        filas.append(dict(filas[0]))  # clave repetida
        _escribir_csv(self.salida / "piloto_registro.csv", filas)
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        with self.assertRaises(PilotoError):
            self.comparar(self.maduro)
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)

    def test_fallo_de_escritura_conserva_el_archivo_anterior(self):
        self.comparar(self.datos)
        self.registrar_contacto()
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        with mock.patch("os.replace", side_effect=OSError("disco lleno (simulado)")), self.assertRaises(OSError):
            self.comparar(self.maduro)
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)
        self.assertEqual([p.name for p in self.salida.iterdir() if p.name.startswith(".")], [])

    def test_migra_el_formato_anterior_conservando_sus_datos(self):
        from modelos.compra import COLUMNAS_PILOTO
        self.comparar(self.datos)
        antiguas = COLUMNAS_PILOTO[:COLUMNAS_PILOTO.index("seleccion_id")]  # columnas del CSV anterior
        filas = [{c: f[c] for c in antiguas} for f in _leer_csv(self.salida / "piloto_registro.csv")]
        filas[0].update(contacto_realizado="no", fecha_contacto="2026-11-20", tiempo_minutos="5", resultado_contacto="Sin respuesta")
        _escribir_csv(self.salida / "piloto_registro.csv", filas)
        self.comparar(self.maduro)
        f = self.fila(filas[0]["cliente_id"])
        self.assertEqual((f["contacto_realizado"], f["tiempo_minutos"], f["resultado_contacto"]), ("no", "5", "Sin respuesta"))
        self.assertTrue(f["seleccion_id"].startswith("2026-10-31|s-"))
        self.assertTrue(f["seleccion_id_anterior"].endswith("|k10"))  # migración verificable del identificador anterior
        self.assertEqual(f["huella_operativa"], self.op.huella)

    def test_otra_seleccion_del_mismo_corte_no_reasigna_contactos(self):
        from modelos.compra import PilotoError
        from modelos.inferencia import desde_dict
        self.comparar(self.datos)
        humano = self.registrar_contacto()
        original = self.fila()["seleccion_id"]
        otra = desde_dict(_artefacto(version="fixture-sombra-2", pesos=[0.4, -0.1]))
        self.compra.puntuar(otra, self.datos, self.corte, self.tmp / "sb2")
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        with self.assertRaises(PilotoError):
            self.comparar(self.datos, sombra=self.tmp / "sb2")
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)
        r = self.comparar(self.datos, sombra=self.tmp / "sb2", nueva_seleccion=True)
        self.assertEqual(len(r["piloto"]["selecciones_del_corte"]), 2)
        self.assertEqual({k: self.fila(seleccion=original)[k] for k in humano}, humano)
        nueva = self.fila(seleccion=r["piloto"]["seleccion_id"])
        self.assertEqual(nueva["contacto_realizado"], "")  # el contacto no migra a la otra predicción
        self.assertEqual(nueva["version_sombra"], "fixture-sombra-2")

    def test_seguimiento_de_cliente_fuera_de_la_poblacion_se_conserva(self):
        self.comparar(self.datos)
        filas = _leer_csv(self.salida / "piloto_registro.csv")
        filas.append(dict(filas[0], cliente_id="C99", contacto_realizado="si", fecha_contacto="2026-11-02", tiempo_minutos="3",
                          resultado_contacto="Contacto previo"))
        _escribir_csv(self.salida / "piloto_registro.csv", filas)
        self.comparar(self.maduro)
        f = self.fila("C99")
        self.assertEqual((f["resultado_contacto"], f["en_cohorte_actual"]), ("Contacto previo", "False"))


# Hallazgo 3 ------------------------------------------------------------------------------
class CohorteOriginalTests(_ConPuntuaciones):
    def test_alta_posterior_no_bloquea_la_cohorte_madura(self):
        nuevo = {"cliente_id": "C_NUEVO", "fecha_alta": date(2026, 11, 5)}
        r = self.comparar(replace(self.maduro, clientes=self.maduro.clientes + [nuevo]))
        self.assertEqual(r["estado_etiquetas"], "madura")
        self.assertEqual(r["cohorte"]["altas_posteriores_ignoradas"], 1)
        self.assertEqual(r["cohorte"]["clientes"], 12)
        self.assertEqual(r["denominadores"]["operativo"]["evaluados"], 10)
        self.assertIsNotNone(r["aciertos"]["operativo"])
        self.assertNotIn("C_NUEVO", {f["cliente_id"] for f in _leer_csv(self.salida / "piloto_registro.csv")})

    def test_horizonte_incompleto_queda_pendiente(self):
        r = self.comparar(_datos(observado=date(2026, 11, 29), ventas=self.maduro.ventas))
        self.assertEqual(r["estado_etiquetas"], "pendiente")
        self.assertEqual(set(r["aciertos"].values()), {None})
        self.assertIn("2026-11-30", r["nota"])
        self.assertEqual(r["etiquetas_por_estado"], {"pendiente": 12})

    def test_cliente_sin_informacion_no_recibe_etiqueta_inventada(self):
        sin_c02 = replace(self.maduro, clientes=[c for c in self.maduro.clientes if c["cliente_id"] != "C02"])
        r = self.comparar(sin_c02)
        self.assertEqual(r["estado_etiquetas"], "madura_con_exclusiones")
        self.assertEqual([e["cliente_id"] for e in r["excluidos"]], ["C02"])
        f = self.fila("C02")
        self.assertEqual((f["estado_etiqueta"], f["compra_30d"]), ("datos_faltantes", ""))
        for m, d in r["denominadores"].items():
            en_lista = "C02" in r["listas"][m]
            self.assertEqual(d["evaluados"], d["en_lista"] - int(en_lista))

    def test_comparaciones_incompatibles_dan_error_claro(self):
        from modelos.compra import PilotoError
        otro = _datos(observado=date(2026, 9, 30), ventas=[v for v in self.datos.ventas if v["fecha"] <= date(2026, 9, 30)])
        self.compra.puntuar(self.sb, otro, date(2026, 9, 30), self.tmp / "sep", simulacion_historica=True)
        with self.assertRaisesRegex(PilotoError, "Cortes distintos"):
            self.comparar(self.datos, sombra=self.tmp / "sep")
        # Cohorte distinta (un cliente menos) y revisión de origen distinta.
        menos = _datos(clientes=self.datos.clientes[:-1], ventas=self.datos.ventas[:-1], huella="lote-c")
        self.compra.puntuar(self.sb, menos, self.corte, self.tmp / "sb-menos")
        with self.assertRaisesRegex(PilotoError, "revisiones de datos distintas"):
            self.comparar(self.datos, sombra=self.tmp / "sb-menos")
        r = self.comparar(self.datos, sombra=self.tmp / "sb-menos", reconciliar=True)
        self.assertEqual(r["cohorte"]["clientes"], 11)
        self.assertEqual(len(r["cohorte"]["reconciliacion"]), 2)
        # Puntuaciones con un cliente duplicado.
        dup = self.tmp / "sb-dup"
        shutil.copytree(self.tmp / "sb", dup)
        filas = _leer_csv(dup / "puntuaciones.csv")
        _escribir_csv(dup / "puntuaciones.csv", filas + [filas[0]])
        with self.assertRaisesRegex(PilotoError, "repetidos"):
            self.comparar(self.datos, sombra=dup)


# Hallazgos 4 y 5 -------------------------------------------------------------------------
class RegistroCorreccionesTests(unittest.TestCase):
    def setUp(self):
        from modelos.inferencia import desde_dict
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-reg2-"))
        self.v1 = desde_dict(_artefacto(version="ref"))
        self.v2 = desde_dict(_artefacto(version="cand", intercepto=0.2))
        self.d1 = {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": self.v1.huella,
                   "origen_datos": "fixture_empresarial", "aprobado_por": "fixture-referencia"}
        self.d2_sombra = {"decision": "inconcluso", "estado_maximo": "sombra", "artefacto_huella": self.v2.huella, "origen_datos": "sintetico"}
        self.d2_op = {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": self.v2.huella,
                      "origen_datos": "fixture_empresarial", "aprobado_por": "fixture-jefatura-ventas"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def reg(self):
        from modelos import registro as R
        return R.leer_registro(self.tmp, "compra_30d")

    def bytes_registro(self):
        return (self.tmp / "compra_30d" / "registro.json").read_bytes()

    def test_reversion_tras_promocion_y_tras_promocion_repetida(self):
        from modelos import registro as R
        for repetir in (False, True):
            with self.subTest(repetir=repetir):
                shutil.rmtree(self.tmp / "compra_30d", ignore_errors=True)
                R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "operativo")
                R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_op, {}, "operativo")
                if repetir:
                    antes = self.bytes_registro()
                    R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_op, {}, "operativo")
                    self.assertEqual(self.bytes_registro(), antes)  # idempotente: sin evento nuevo
                self.assertEqual(R.revertir(self.tmp, "compra_30d", "operativo")["operativo"]["version"], "v1")
                transiciones = [h for h in self.reg()["historial"] if h["accion"] in ("promover", "revertir")]
                self.assertFalse([h for h in transiciones if h["version"] == h["anterior"]])

    def test_reversion_explicita_y_rechazos_sin_cambiar_el_registro(self):
        from modelos import registro as R
        R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_sombra, {}, "sombra")
        antes = self.bytes_registro()
        with self.assertRaisesRegex(R.RegistroError, "no existe"):
            R.revertir(self.tmp, "compra_30d", "operativo", a="v7")
        with self.assertRaisesRegex(R.RegistroError, "autorización"):
            R.revertir(self.tmp, "compra_30d", "operativo", a="v2")  # solo autorizada para sombra
        with self.assertRaisesRegex(R.RegistroError, "no autoriza"):
            R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_sombra, {}, "operativo")
        ruta = self.tmp / "compra_30d" / "v2" / "artefacto.json"
        original = ruta.read_bytes()
        d = json.loads(original)
        d["pesos"][0] = 9.0
        ruta.write_text(json.dumps(d), encoding="utf-8")
        with self.assertRaisesRegex(R.RegistroError, "alterada"):
            R.revertir(self.tmp, "compra_30d", "sombra", a="v2")
        self.assertEqual(self.bytes_registro(), antes)
        ruta.write_bytes(original)
        self.assertEqual(R.revertir(self.tmp, "compra_30d", "operativo", a="v1")["operativo"]["version"], "v1")

    def test_aprobacion_posterior_se_conserva_y_permite_recuperar_la_version(self):
        from modelos import registro as R
        R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_sombra, {}, "sombra")
        R.autorizar(self.tmp, "compra_30d", "v2", self.d2_op, "fixture-jefatura", "acta de prueba (fixture)")
        self.assertEqual(self.reg()["sombra"]["version"], "v2")  # autorizar no mueve punteros
        R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_op, {}, "operativo")
        reg = self.reg()
        self.assertEqual((reg["operativo"]["version"], reg["sombra"]), ("v2", None))  # punteros coherentes
        R.revertir(self.tmp, "compra_30d", "operativo")
        self.assertEqual(self.reg()["operativo"]["version"], "v1")
        self.assertEqual(R.revertir(self.tmp, "compra_30d", "operativo", a="v2")["operativo"]["version"], "v2")
        auts = R.autorizaciones(self.tmp, "compra_30d", "v2")
        self.assertEqual([a["estado_maximo"] for a in auts], ["sombra", "operativo"])
        self.assertEqual(json.loads((self.tmp / "compra_30d" / "v2" / "decision.json").read_text(encoding="utf-8"))["decision"], "inconcluso")
        self.assertEqual(auts[1]["actor"], "fixture-jefatura")

    def test_aprobaciones_invalidas_se_rechazan(self):
        from modelos import registro as R
        R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", self.v2, self.d2_sombra, {}, "sombra")
        antes = self.bytes_registro()
        with self.assertRaisesRegex(R.RegistroError, "otra huella"):
            R.autorizar(self.tmp, "compra_30d", "v2", dict(self.d2_op, artefacto_huella=self.v1.huella), "x", "y")
        with self.assertRaisesRegex(R.RegistroError, "sintéticos"):
            R.autorizar(self.tmp, "compra_30d", "v2", dict(self.d2_op, origen_datos="sintetico"), "x", "y")
        with self.assertRaisesRegex(R.RegistroError, "aprobado_por"):
            R.autorizar(self.tmp, "compra_30d", "v2", {k: v for k, v in self.d2_op.items() if k != "aprobado_por"}, "x", "y")
        with self.assertRaisesRegex(R.RegistroError, "operativa"):
            R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "sombra")
        self.assertEqual(self.bytes_registro(), antes)

    def test_candidato_actual_con_decision_inconclusa_no_pasa_a_operativo(self):
        from modelos import registro as R
        from modelos.inferencia import cargar_artefacto
        ex = RAIZ / "salida" / "experimentos" / "compra_30d" / "ejecucion-001"
        if not (ex / "decision.json").exists():
            self.skipTest("Sin la ejecución histórica local")
        art = cargar_artefacto(ex / "artefacto.json")  # solo lectura
        decision = json.loads((ex / "decision.json").read_text(encoding="utf-8"))
        self.assertEqual(decision["decision"], "inconcluso")
        R.promover(self.tmp, "compra_30d", "v2", art, decision, {}, "sombra")
        with self.assertRaises(R.RegistroError):
            R.promover(self.tmp, "compra_30d", "v2", art, decision, {}, "operativo")
        with self.assertRaises(R.RegistroError):
            R.promover(self.tmp, "compra_30d", "v2", art, dict(decision, estado_maximo="operativo"), {}, "operativo")

    def test_registro_anterior_sin_autorizaciones_se_lee_igual(self):
        from modelos import registro as R
        R.promover(self.tmp, "compra_30d", "v1", self.v1, self.d1, {}, "operativo")
        ruta = self.tmp / "compra_30d" / "registro.json"
        reg = json.loads(ruta.read_text(encoding="utf-8"))
        reg.pop("autorizaciones")
        ruta.write_text(json.dumps(reg), encoding="utf-8")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d", "operativo")[0].version, "ref")


# Hallazgo 2 ------------------------------------------------------------------------------
class CoberturaUnitariaTests(unittest.TestCase):
    def test_politica_compartida(self):
        from modelos.datos import Cobertura, CoberturaInsuficiente, resolver_cobertura, verificar_cobertura_corte
        verificar_cobertura_corte(date(2026, 10, 31), Cobertura(date(2026, 10, 31), "fixture"))  # no exige el futuro
        with self.assertRaisesRegex(CoberturaInsuficiente, "solo están completos hasta 2026-10-31"):
            verificar_cobertura_corte(date(2026, 11, 30), Cobertura(date(2026, 10, 31), "fixture"))
        with self.assertRaisesRegex(CoberturaInsuficiente, "desconocida"):
            verificar_cobertura_corte(date(2026, 10, 31), Cobertura(None, "no declarada"))
        self.assertFalse(resolver_cobertura({"source_hashes": {"ventas": "otra"}}).conocida)  # lote empresarial sin metadatos
        self.assertEqual(resolver_cobertura({"datos_observados_hasta": {"ventas": "2027-01-31"}}).observado_hasta, date(2027, 1, 31))

    def test_puntuar_rechaza_corte_posterior_a_la_cobertura(self):
        from modelos import compra
        from modelos.datos import CoberturaInsuficiente
        from modelos.inferencia import desde_dict
        with self.assertRaises(CoberturaInsuficiente):
            compra.puntuar(desde_dict(_artefacto()), _datos(), date(2026, 11, 30))
        r = compra.puntuar(desde_dict(_artefacto()), _datos(), date(2026, 10, 31))
        self.assertEqual(r["resumen"]["etiquetas"]["pendientes"], 12)

    def test_contrato_detecta_contradicciones_de_cobertura(self):
        from contratos.validar import validar_cobertura
        est = [{"cliente_id": "C1", "estado": "estimado", "datos_hasta": "2026-11-30"}]
        casos = {"sin_cobertura": ({}, est), "hasta_anterior": ({"estado": "verificada", "datos_observados_hasta": "2026-10-31", "fuente": "x"}, est),
                 "no_verificada": ({"estado": "no_verificada", "datos_observados_hasta": None, "fuente": "x"}, est),
                 "corte_distinto": ({"estado": "verificada", "datos_observados_hasta": "2026-12-31", "fuente": "x", "corte": "2026-10-31"}, est),
                 "sin_fuente": ({"estado": "verificada", "datos_observados_hasta": "2026-12-31"}, est)}
        for nombre, (cob, preds) in casos.items():
            man = {"corte": "2026-11-30", **({"cobertura": cob} if cob else {})}
            with self.subTest(nombre):
                self.assertTrue(validar_cobertura(man, preds))
        ok = {"corte": "2026-11-30", "cobertura": {"estado": "verificada", "datos_observados_hasta": "2026-11-30", "fuente": "x", "corte": "2026-11-30"}}
        self.assertEqual(validar_cobertura(ok, est), [])
        abst = {"corte": "2026-11-30", "cobertura": {"estado": "no_verificada", "datos_observados_hasta": None, "fuente": "x"}}
        self.assertEqual(validar_cobertura(abst, [{"estado": "modelo_no_disponible"}]), [])


@unittest.skipIf(_paquete() is None, "Paquete de datos no disponible")
class CoberturaCierreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.cli import main
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1-cob-"))
        cls.registro = cls.tmp / "registro"
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["preparar", "--datos", str(_paquete()), "--salida", str(cls.tmp / "a01")]) == 0
            assert main(["inicializar-referencia", "--datos", str(cls.tmp / "a01"), "--registro", str(cls.registro)]) == 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_corte_igual_a_la_cobertura_publica_y_deja_etiquetas_pendientes(self):
        from contratos.validar import validar_publicacion
        from pipeline.generar import generar
        m = generar(_paquete(), "2026-10-31", self.tmp / "oct", registro=self.registro)
        r, datos = validar_publicacion(self.tmp / "oct")
        self.assertTrue(r.valido, r.errores)
        self.assertEqual((m["cobertura"]["estado"], m["cobertura"]["datos_observados_hasta"]), ("verificada", "2026-10-31"))
        self.assertIn("declaración registrada", m["cobertura"]["fuente"])
        self.assertEqual(sum(p["estado"] == "estimado" for p in datos["predicciones_clientes"]), 120)

    def test_corte_posterior_no_publica_y_conserva_la_publicacion_previa(self):
        from modelos.datos import CoberturaInsuficiente
        from pipeline.generar import generar
        salida = self.tmp / "misma-carpeta"
        generar(_paquete(), "2026-10-31", salida, registro=self.registro)
        huellas = {p.name: _sha(p) for p in salida.glob("*.json")}
        with self.assertRaisesRegex(CoberturaInsuficiente, "2026-11-30"):
            generar(_paquete(), "2026-11-30", salida, registro=self.registro)
        self.assertEqual({p.name: _sha(p) for p in salida.glob("*.json")}, huellas)
        self.assertEqual([p.name for p in salida.iterdir() if p.name.startswith(".")], [])

    def test_lote_distinto_sin_cobertura_no_hereda_la_fecha_sintetica(self):
        from contratos.validar import validar_publicacion
        from modelos.datos import CoberturaInsuficiente
        from pipeline.generar import generar
        copia = self.tmp / "lote-empresarial-fixture"
        shutil.copytree(_paquete() / "01_Datos", copia / "01_Datos")
        with (copia / "01_Datos" / "ventas.csv").open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["VEN88888", "2026-10-15", "CLI001", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"])
        with self.assertRaisesRegex(CoberturaInsuficiente, "desconocida"):
            generar(copia, "2026-10-31", self.tmp / "emp", registro=self.registro)
        m = generar(copia, "2026-10-31", self.tmp / "emp-parcial", registro=self.registro, sin_cobertura_verificada=True)
        r, datos = validar_publicacion(self.tmp / "emp-parcial")
        self.assertTrue(r.valido, r.errores)
        self.assertEqual((m["cobertura"]["estado"], m["cobertura"]["publicacion"]), ("no_verificada", "sin_cobertura_verificada"))
        self.assertIsNone(datos["agenda"]["modelo"])
        self.assertEqual({p["estado"] for p in datos["predicciones_clientes"]}, {"modelo_no_disponible"})
        self.assertIn("Cobertura temporal no verificada", datos["predicciones_clientes"][0]["motivos"][0])
        m2 = generar(copia, "2026-10-31", self.tmp / "emp-declarado", registro=self.registro, observado_hasta="2026-10-31")
        self.assertEqual((m2["cobertura"]["estado"], m2["cobertura"]["fuente"][:9]), ("verificada", "argumento"))

    def test_fallo_del_cierre_programado_conserva_el_cierre_activo(self):
        from api import base, operacion, publicacion
        from api.base import BaseDatos
        from api.demo import solo_permisos
        from pipeline.generar import generar
        base.fijar_hoy("2026-11-23")
        try:
            db = BaseDatos(self.tmp / "op.sqlite3")
            solo_permisos(db)
            generar(_paquete(), "2026-10-31", self.tmp / "valida", registro=self.registro)
            activo = publicacion.publicar_ruta(db, self.tmp / "valida", "ops1")["cierre_id"]
            with mock.patch.dict(os.environ, {"JACOMIND_MODELOS": str(self.registro), "JACOMIND_SIN_ESPERA": "1"}):
                r = operacion.ejecutar_cierre(db, "ops1", "2026-11-30", datos=str(_paquete()), reintentos=0, salida_base=self.tmp / "prog")
            self.assertEqual(r["estado"], "fallido")
            self.assertIn("2026-11-30", r["error"]["mensaje"])
            with db.conexion() as con:
                self.assertEqual(publicacion.cierre_activo(con), activo)
        finally:
            base.fijar_hoy(None)


# Hallazgo 6 ------------------------------------------------------------------------------
class FechasTests(unittest.TestCase):
    def test_primer_corte_prospectivo(self):
        from modelos.compra import _primer_fin_de_mes_posterior
        self.assertEqual(_primer_fin_de_mes_posterior(date(2026, 11, 23)), date(2026, 11, 30))
        self.assertEqual(_primer_fin_de_mes_posterior(date(2026, 11, 30)), date(2026, 12, 31))
        self.assertEqual(_primer_fin_de_mes_posterior(date(2026, 12, 31)), date(2027, 1, 31))

    def test_huella_semantica_ignora_formato_y_detecta_cambios(self):
        from modelos.compra import cargar_config, huella_protocolo
        c = cargar_config()
        reordenado = json.loads(json.dumps(dict(reversed(list(c.items()))), indent=7))
        self.assertEqual(huella_protocolo(reordenado), huella_protocolo(c))
        self.assertEqual(huella_protocolo(dict(c, nota="otro texto")), huella_protocolo(c))
        for cambio in ({"metas": dict(c["metas"], mejora_minima_precision_top10=0)}, {"horizonte_dias": 60},
                       {"bloques": dict(c["bloques"], validacion=["2026-05-01", "2026-07-31"])}, {"referencias": ["recencia"]},
                       {"umbral": dict(c["umbral"], politica="otra")}, {"regularizacion_C": [1]}):
            with self.subTest(cambio=list(cambio)):
                self.assertNotEqual(huella_protocolo(dict(c, **cambio)), huella_protocolo(c))


@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class ProtocoloCongeladoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_config, cargar_datos_config, entrenar
        from modelos.datos import preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1-prot-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.config = cargar_config()
        cls.datos = cargar_datos_config(cls.tmp / "a01", cls.config)
        cls.exp = cls.tmp / "experimentos"
        cls.r1 = entrenar(cls.datos, cls.config, cls.exp / "e1")
        from modelos.compra import evaluar
        cls.ev1 = evaluar(cls.exp / "e1", cls.datos)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copia(self, nombre):
        destino = self.tmp / "copias" / nombre
        shutil.copytree(self.exp / "e1", destino)
        return destino

    def test_dictamen_inconcluso_no_cambia(self):
        self.assertEqual((self.ev1["decision"]["decision"], self.ev1["decision"]["estado_maximo"]), ("inconcluso", "sombra"))
        self.assertEqual(self.ev1["decision"]["protocolo_huella"], self.r1["congelacion"]["protocolo"]["huella"])
        self.assertEqual(self.r1["congelacion"]["fechas"]["disponibilidad_simulada_desde"], "2026-10-30")

    def test_cambios_de_protocolo_tras_congelar_se_detectan(self):
        from modelos.compra import ProtocoloError, evaluar
        c = self.config
        for nombre, cambio in {"metas": {"metas": dict(c["metas"], mejora_minima_precision_top10=0)},
                               "bloques": {"bloques": dict(c["bloques"], comprobacion_historica=["2026-08-01", "2026-09-30"])},
                               "horizonte": {"horizonte_dias": 31}, "referencia": {"referencias": ["recencia", "constante"]}}.items():
            with self.subTest(nombre):
                d = self.copia(nombre)
                (d / "config.json").write_text(json.dumps(dict(c, **cambio)), encoding="utf-8")
                decision = (d / "decision.json").read_bytes()
                with self.assertRaisesRegex(ProtocoloError, "cambió después de congelarse"):
                    evaluar(d, self.datos)
                self.assertEqual((d / "decision.json").read_bytes(), decision)

    def test_referencia_alterada_y_decision_sobrescrita_se_detectan(self):
        from modelos.compra import ProtocoloError, evaluar
        from modelos.inferencia import sellar
        d = self.copia("referencia-alterada")
        ref = json.loads((d / "referencia_artefacto.json").read_text(encoding="utf-8"))
        (d / "referencia_artefacto.json").write_text(json.dumps(sellar(dict(ref, umbral=0.3))), encoding="utf-8")
        with self.assertRaisesRegex(ProtocoloError, "referencia"):
            evaluar(d, self.datos)
        d2 = self.copia("decision")
        dec = json.loads((d2 / "decision.json").read_text(encoding="utf-8"))
        (d2 / "decision.json").write_text(json.dumps(dict(dec, decision="favorable")), encoding="utf-8")
        with self.assertRaisesRegex(ProtocoloError, "no se sobrescribe"):
            evaluar(d2, self.datos)

    def test_formato_json_distinto_no_altera_y_reevaluar_es_estable(self):
        from modelos.compra import evaluar
        d = self.copia("formato")
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        (d / "config.json").write_text(json.dumps(dict(reversed(list(cfg.items()))), indent=8, ensure_ascii=True), encoding="utf-8")
        antes = (d / "decision.json").read_bytes()
        r = evaluar(d, self.datos)
        self.assertEqual(r["decision"]["decision"], "inconcluso")
        self.assertEqual((d / "decision.json").read_bytes(), antes)
        self.assertIsNone(evaluar(d, self.datos, bloque="validacion")["decision"])  # validación no emite decisión
        self.assertEqual((d / "decision.json").read_bytes(), antes)

    def test_reproducible_y_modificacion_exige_ejecucion_y_version_nuevas(self):
        from modelos.compra import ProtocoloError, entrenar
        r2 = entrenar(self.datos, self.config, self.exp / "e2")
        self.assertEqual(r2["artefacto"]["huella"], self.r1["artefacto"]["huella"])
        self.assertEqual(r2["congelacion"]["protocolo"]["huella"], self.r1["congelacion"]["protocolo"]["huella"])
        original = {p.name: _sha(p) for p in (self.exp / "e1").iterdir()}
        cambiado = dict(self.config, metas=dict(self.config["metas"], mejora_minima_precision_top10=0))
        with self.assertRaisesRegex(ProtocoloError, "versión nueva"):
            entrenar(self.datos, cambiado, self.exp / "e3")
        r3 = entrenar(self.datos, dict(cambiado, version_protocolo="m1-protocolo-v2-prueba"), self.exp / "e3")
        self.assertNotEqual(r3["congelacion"]["protocolo"]["huella"], self.r1["congelacion"]["protocolo"]["huella"])
        self.assertEqual({p.name: _sha(p) for p in (self.exp / "e1").iterdir()}, original)

    def test_ejecucion_heredada_se_lee_pero_no_decide(self):
        from modelos.compra import ProtocoloError, evaluar, verificar_protocolo_heredado
        from modelos.inferencia import cargar_artefacto
        d = self.copia("heredada")
        cong = json.loads((d / "congelacion.json").read_text(encoding="utf-8"))
        for k in ("formato", "protocolo", "sello", "referencia_huella", "huella_datos", "revision_datos", "fechas"):
            cong.pop(k, None)
        (d / "congelacion.json").write_text(json.dumps(cong), encoding="utf-8")
        decision = (d / "decision.json").read_bytes()
        with self.assertRaisesRegex(ProtocoloError, "heredada"):
            evaluar(d, self.datos)
        self.assertEqual((d / "decision.json").read_bytes(), decision)
        self.assertEqual(cargar_artefacto(d / "artefacto.json").huella, self.r1["artefacto"]["huella"])  # inferencia intacta
        v = verificar_protocolo_heredado(d, RAIZ / "modelos" / "config" / "compra_30d.json")
        self.assertEqual((v["tipo"], v["coincide"], v["tiene_huella_protocolo"]), ("verificacion_posterior", True, False))
        self.assertIn("no prueba", v["advertencia"])


if __name__ == "__main__":
    unittest.main()
