import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


class ClasificadorC4Tests(unittest.TestCase):
    def test_salida_cumple_c4(self):
        from contratos.esquema import validar
        from contratos.validar import cargar_esquema
        from pipeline.pqrs import clasificar

        esquema = cargar_esquema("asistencia.v1.schema.json")["$defs"]["clasificacion_pqrs"]
        for texto in ("Solicito un certificado", "Tengo una queja y sugiero mejorar", "", "Hola"):
            r = clasificar(texto)
            self.assertEqual(validar(r, esquema), [], r)
            if r["categoria"] is None:
                self.assertTrue(r["revisar"])

    def test_dos_intenciones_y_tildes(self):
        from pipeline.pqrs import clasificar_pqrs

        self.assertTrue(clasificar_pqrs("Quiero información y sugiero cambios")["revisar"])
        self.assertEqual(clasificar_pqrs("Solicito información")["categoria"], "peticion")
        self.assertEqual(clasificar_pqrs("Pido devolución del dinero")["categoria"], "reclamo")


class VentaCruzadaTests(unittest.TestCase):
    def test_soporte_minimo_excluye_propias_e_incompatibles(self):
        from pipeline.oportunidades import recomendar_venta_cruzada

        hist = {"A": {"F1"}, "B": {"F1", "F2"}, "C": {"F1", "F2"}, "D": {"F1", "F3"}}
        r = recomendar_venta_cruzada(hist, soporte_minimo=2)
        self.assertEqual(r["A"][0]["familia"], "F2")
        self.assertEqual(r["A"][0]["soporte"], 2)
        self.assertNotIn("F1", [s["familia"] for s in r.get("B", [])])
        r2 = recomendar_venta_cruzada(hist, soporte_minimo=2, incompatibles={"F1": {"F2"}})
        self.assertNotIn("A", r2)
        self.assertEqual(recomendar_venta_cruzada(hist, soporte_minimo=5), {})

    def test_solo_transacciones_hasta_el_corte(self):
        from pipeline.oportunidades import familias_por_cliente

        ventas = [{"cliente_id": "A", "producto_id": "P1", "fecha": date(2026, 9, 1), "estado": "Confirmada"},
                  {"cliente_id": "A", "producto_id": "P2", "fecha": date(2026, 11, 1), "estado": "Confirmada"},
                  {"cliente_id": "A", "producto_id": "P3", "fecha": date(2026, 9, 1), "estado": "Anulada"}]
        self.assertEqual(familias_por_cliente(ventas, {"P1": "F1", "P2": "F2", "P3": "F3"}, date(2026, 10, 31)), {"A": {"F1"}})

    def test_evaluacion_frente_a_popularidad(self):
        from pipeline.oportunidades import evaluar_venta_cruzada, recomendar_popular

        antes = {"A": {"F1"}, "B": {"F1", "F2"}}
        despues = {"A": {"F1", "F2"}, "B": {"F1", "F2"}}
        r = evaluar_venta_cruzada(antes, despues, recomendar_popular(antes))
        self.assertEqual((r["aciertos"], r["clientes_evaluados"]), (1, 1))  # B ya tiene todo: sin sugerencia


class PronosticoTests(unittest.TestCase):
    def test_origen_creciente_por_horizonte(self):
        from pipeline.pronostico import evaluar_origen_creciente

        r = evaluar_origen_creciente([10] * 8, 3, 2)
        self.assertEqual(r[1]["mae_media_movil"], Decimal("0.00"))
        self.assertEqual(r[1]["n"], 5)
        self.assertEqual(r[2]["n"], 4)

    def test_pico_futuro_no_cambia_pronostico_de_origen_anterior(self):
        from pipeline.pronostico import pronosticar_media_movil

        sin_pico, con_pico = [10, 12, 14, 16, 18], [10, 12, 14, 16, 999]
        # El pronóstico desde el origen 4 solo usa los 4 primeros meses: el pico del mes 5 no lo altera.
        self.assertEqual(pronosticar_media_movil(sin_pico[:4], 3, 1), pronosticar_media_movil(con_pico[:4], 3, 1))
        self.assertEqual(pronosticar_media_movil(sin_pico[:4], 3, 1), [Decimal("14.00")])


class GeneradorTests(unittest.TestCase):
    """El cierre ya no entrena: los preparativos crean de forma explícita el artefacto de referencia."""

    @classmethod
    def setUpClass(cls):
        from pipeline.rutas import ruta_paquete

        cls.paquete = ruta_paquete()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.registro = Path(cls.tmp.name) / "registro"
        if cls.paquete is not None:
            a01 = Path(cls.tmp.name) / "a01"
            for args in (["preparar", "--datos", str(cls.paquete), "--salida", str(a01)],
                         ["inicializar-referencia", "--datos", str(a01), "--registro", str(cls.registro), "--version", "v1"]):
                p = subprocess.run([sys.executable, "-m", "modelos.cli", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
                assert p.returncode == 0, p.stderr

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_cierre_octubre_cumple_contrato_y_referencia(self):
        paquete = self.paquete
        if paquete is None:
            self.skipTest("Paquete de datos no disponible")
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, "-m", "pipeline.generar", "--datos", str(paquete), "--corte", "2026-10-31",
                                "--salida", str(Path(tmp) / "agenda.json"), "--registro", str(self.registro)],
                               cwd=RAIZ, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            v = subprocess.run([sys.executable, "-m", "contratos.validar", "--publicacion", tmp], cwd=RAIZ, capture_output=True, text=True)
            self.assertEqual(v.returncode, 0, v.stdout)
            agenda = json.loads((Path(tmp) / "agenda.json").read_text(encoding="utf-8"))
            self.assertEqual(agenda["resumen"], {"clientes": 120, "ventas_confirmadas": 1371, "ingreso_cop": 5647449456.36, "clientes_frios": 41})
            self.assertEqual(agenda["modelo"]["umbral"], 0.4)

    def test_corte_sin_modelo_validado_deja_probabilidad_nula(self):
        from pipeline.generar import generar

        paquete = self.paquete
        if paquete is None:
            self.skipTest("Paquete de datos no disponible")
        with tempfile.TemporaryDirectory() as tmp:
            m = generar(paquete, "2026-09-30", tmp, registro=self.registro)
            agenda = json.loads((Path(tmp) / "agenda.json").read_text(encoding="utf-8"))
            self.assertIsNone(agenda["modelo"])
            self.assertTrue(all(c["prob_compra_30d"] is None for c in agenda["clientes"]))
            self.assertIsNone(m["versiones"]["modelo_compra"])

    def test_datos_inexistentes_devuelven_codigo_de_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = subprocess.run([sys.executable, "-m", "pipeline.generar", "--datos", str(Path(tmp) / "no"), "--corte", "2026-10-31",
                                "--salida", str(Path(tmp) / "s" / "agenda.json")], cwd=RAIZ, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
