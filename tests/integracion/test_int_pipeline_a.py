"""Prueba de fusión con el carril A (datos y modelos).

Se activa sola cuando existe el paquete ``pipeline`` de A y la carpeta hermana de
datos. Comprueba el contrato de extremo a extremo con las cifras de referencia:
regenerar octubre → validar C1/C2 → publicar → la API devuelve lo mismo que A.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
PAQUETE = Path(os.environ.get("JACOMIND_DATOS", RAIZ.parent / "Green_Services_Recursos_de_Prueba"))
HAY_PIPELINE = importlib.util.find_spec("pipeline") is not None and importlib.util.find_spec("pipeline.generar") is not None

from api import base, consultas, publicacion  # noqa: E402
from api.base import BaseDatos  # noqa: E402
from api.demo import solo_permisos  # noqa: E402
from contratos.validar import validar_agenda, validar_publicacion  # noqa: E402


@unittest.skipUnless(HAY_PIPELINE and PAQUETE.exists(), "Requiere pipeline/ (carril A) y el paquete de datos hermano")
class PruebasFusionConA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.salida = cls.tmp / "octubre"
        cls.salida.mkdir()

        def generar(destino):
            p = subprocess.run([sys.executable, "-m", "pipeline.generar", "--datos", str(PAQUETE), "--corte", "2026-10-31",
                                "--salida", str(destino / "agenda.json")], cwd=RAIZ, capture_output=True, text=True, timeout=1800)
            if p.returncode != 0:
                raise AssertionError(f"pipeline.generar falló: {p.stderr[-2000:]}")
        generar(cls.salida)
        cls.repeticion = cls.tmp / "repeticion"; cls.repeticion.mkdir()
        generar(cls.repeticion)
        cls.agenda = json.loads((cls.salida / "agenda.json").read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_contrato_c1(self):
        r = validar_agenda(self.agenda)
        self.assertTrue(r.valido, r.errores)
        if (self.salida / "manifiesto.json").exists():
            r2, _ = validar_publicacion(self.salida)
            self.assertTrue(r2.valido, r2.errores)

    def test_cifras_de_referencia_octubre(self):
        res = self.agenda["resumen"]
        self.assertEqual(res["clientes"], 120)
        self.assertEqual(res["ventas_confirmadas"], 1371)
        # La referencia (,36) depende del nivel de redondeo; el propio ejemplo_operaciones.py da ,40.
        # A02 documenta su política; aquí se admite la diferencia de redondeo entre ambas.
        self.assertAlmostEqual(res["ingreso_cop"], 5647449456.36, delta=0.5)
        self.assertEqual(res["clientes_frios"], 41)

    def test_repeticion_mensual_produce_la_misma_agenda(self):
        otra = json.loads((self.repeticion / "agenda.json").read_text(encoding="utf-8"))
        quitar = lambda a: {k: v for k, v in a.items() if k != "generado_en"}  # noqa: E731
        self.assertEqual(quitar(self.agenda), quitar(otra))

    def test_publicar_y_conciliar_api_con_fila_de_a(self):
        base.fijar_hoy("2026-11-21")
        try:
            db = BaseDatos(self.tmp / "int.sqlite3")
            solo_permisos(db)
            objetivo = self.salida if (self.salida / "manifiesto.json").exists() else self.salida / "agenda.json"
            r = publicacion.publicar_ruta(db, objetivo, "ops1")
            with db.conexion() as con:
                res = consultas.resumen(con, r["cierre_id"])
                self.assertEqual(res["resumen"], self.agenda["resumen"])
                fila = sorted(self.agenda["clientes"], key=lambda c: c["cliente_id"])[0]
                ficha = consultas.ficha(con, r["cierre_id"], fila["cliente_id"])["cliente"]
                for k in ("dias_sin_compra", "ventas_confirmadas", "ingreso_cop", "frio", "frecuente", "accion", "prob_compra_30d"):
                    self.assertEqual(ficha[k], fila[k], k)
                with self.assertRaises(base.ErrorApi):
                    consultas.ficha(con, r["cierre_id"], "CLI999")
            self.assertTrue(publicacion.publicar_ruta(db, objetivo, "ops1")["ya_publicado"])
        finally:
            base.fijar_hoy(None)


if __name__ == "__main__":
    unittest.main()
