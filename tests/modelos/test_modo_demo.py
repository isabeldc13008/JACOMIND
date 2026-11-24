"""Modo demostración del registro: operativo con datos sintéticos solo con el modo activo, decisión explícita y aprobación."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
REAL = RAIZ / "var" / "modelos" / "compra_30d"


@unittest.skipUnless((REAL / "v2" / "artefacto.json").exists(), "Sin registro local con v1 y v2")
class ModoDemoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="demo-reg-"))
        shutil.copytree(REAL, self.tmp / "compra_30d")
        reg = json.loads((self.tmp / "compra_30d" / "registro.json").read_text(encoding="utf-8"))
        if (reg.get("modo_demostracion") or {}).get("activo"):  # partir siempre del estado sin modo demostración
            from modelos import registro as R
            R.revertir(self.tmp, "compra_30d", "operativo", "v1")
            R.fijar_modo_demostracion(self.tmp, "compra_30d", False, "prueba", "estado inicial")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def decision(self, art, **c):
        return {"artefacto_huella": art.huella, "estado_maximo": "operativo", "decision": "demostracion", "origen_datos": "sintetico",
                "aprobado_por": "responsable"} | c

    def test_apagado_por_defecto_rechaza_sintetico_operativo(self):
        from modelos import registro as R
        art = R._cargar_version(self.tmp, "compra_30d", "v2")
        with self.assertRaises(R.RegistroError):
            R.promover(self.tmp, "compra_30d", "v2", art, self.decision(art), {}, "operativo")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d")[1]["version"], "v1")

    def test_activo_exige_decision_demostracion_y_aprobado_por(self):
        from modelos import registro as R
        R.fijar_modo_demostracion(self.tmp, "compra_30d", True, "responsable", "demo")
        art = R._cargar_version(self.tmp, "compra_30d", "v2")
        for malo in ({"decision": "inconcluso"}, {"aprobado_por": ""}):
            with self.subTest(malo=malo), self.assertRaises(R.RegistroError):
                R.promover(self.tmp, "compra_30d", "v2", art, self.decision(art, **malo), {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", art, self.decision(art), {}, "operativo")
        art_op, p = R.artefacto_registrado(self.tmp, "compra_30d")
        self.assertEqual((p["version"], p["decision"], p["origen_datos"]), ("v2", "demostracion", "sintetico"))

    def test_apagar_exige_revertir_y_al_leer_sin_modo_no_se_sirve(self):
        from modelos import registro as R
        R.fijar_modo_demostracion(self.tmp, "compra_30d", True, "responsable", "demo")
        art = R._cargar_version(self.tmp, "compra_30d", "v2")
        R.promover(self.tmp, "compra_30d", "v2", art, self.decision(art), {}, "operativo")
        with self.assertRaises(R.RegistroError):
            R.fijar_modo_demostracion(self.tmp, "compra_30d", False, "responsable", "fin")
        ruta = self.tmp / "compra_30d" / "registro.json"  # apagado a mano: la lectura vuelve a exigir datos empresariales
        reg = json.loads(ruta.read_text(encoding="utf-8"))
        reg["modo_demostracion"]["activo"] = False
        ruta.write_text(json.dumps(reg), encoding="utf-8")
        with self.assertRaises(R.ModeloNoDisponible):
            R.artefacto_registrado(self.tmp, "compra_30d")
        reg["modo_demostracion"]["activo"] = True
        ruta.write_text(json.dumps(reg), encoding="utf-8")
        R.revertir(self.tmp, "compra_30d", "operativo")
        R.fijar_modo_demostracion(self.tmp, "compra_30d", False, "responsable", "fin")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d")[1]["version"], "v1")


if __name__ == "__main__":
    unittest.main()
