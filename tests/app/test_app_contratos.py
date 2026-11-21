"""B01 · Contratos C1/C2: esquema, muestras, CLI independiente de la pantalla y paridad JS."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contratos.agenda import motivos, ordenar
from contratos.validar import validar_agenda, validar_publicacion

from _apoyo_app import EJEMPLOS, MUESTRA, RAIZ, agenda_valida, escribir, leer


class PruebasAgendaC1(unittest.TestCase):
    def test_muestras_versionadas(self):
        esperado = {"valido": True, "vacio": True, "incompleto": False, "incompatible": False, "id_repetido": False, "tipo_invalido": False}
        for nombre, ok in esperado.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(validar_agenda(leer(EJEMPLOS / f"{nombre}.json")).valido, ok)

    def test_version_desconocida_es_incompatible(self):
        r = validar_agenda(leer(EJEMPLOS / "incompatible.json"))
        self.assertTrue(r.incompatible)

    def test_null_y_cero_en_probabilidad_son_validos_y_distintos(self):
        a = agenda_valida()
        probs = {c["cliente_id"]: c["prob_compra_30d"] for c in a["clientes"]}
        self.assertIsNone(probs["DEMO04"])
        self.assertEqual(probs["DEMO05"], 0.0)
        self.assertTrue(validar_agenda(a).valido)

    def test_booleano_no_cuenta_como_entero(self):
        a = agenda_valida()
        a["clientes"][0]["ventas_confirmadas"] = True
        self.assertFalse(validar_agenda(a).valido)

    def test_cliente_sin_compras_no_puede_estar_frio(self):
        a = agenda_valida()
        sin = next(c for c in a["clientes"] if c["cliente_id"] == "DEMO04")
        sin["frio"] = True
        a["resumen"]["clientes_frios"] += 1
        self.assertIn("frío", " ".join(validar_agenda(a).errores))

    def test_resumen_debe_conciliar(self):
        a = agenda_valida()
        a["resumen"]["ingreso_cop"] += 1000
        self.assertFalse(validar_agenda(a).valido)

    def test_campos_opcionales_nuevos_preservan_c1(self):
        a = agenda_valida()
        a["clientes"][0]["riesgo_inactividad"] = 0.3
        a["nuevo_bloque"] = {"x": 1}
        self.assertTrue(validar_agenda(a).valido)

    def test_fecha_imposible(self):
        a = agenda_valida()
        a["clientes"][0]["ultima_compra"] = "2026-02-30"
        self.assertFalse(validar_agenda(a).valido)


class PruebasOrdenYMotivos(unittest.TestCase):
    def test_orden_estable_accion_prob_id(self):
        a = agenda_valida()
        ids = [c["cliente_id"] for c in ordenar(a["clientes"])]
        self.assertEqual(ids, ["DEMO01", "DEMO08", "DEMO02", "DEMO06", "DEMO03", "DEMO04", "DEMO07", "DEMO05"])

    def test_nulos_al_final_dentro_de_la_accion(self):
        cs = [{"cliente_id": "B", "accion": "Seguimiento habitual", "prob_compra_30d": None},
              {"cliente_id": "A", "accion": "Seguimiento habitual", "prob_compra_30d": 0.0}]
        self.assertEqual([c["cliente_id"] for c in ordenar(cs)], ["A", "B"])

    def test_motivos_superpuestos(self):
        c = {"frio": True, "renovaciones_proximas": 1, "coberturas_vencidas": 0, "prob_compra_30d": 0.5,
             "ultima_compra": "2026-01-01", "ventas_confirmadas": 3, "accion": "Revisar reactivación"}
        self.assertEqual(motivos(c, 0.4), ["Revisar reactivación", "Revisar cobertura", "Revisar oportunidad de recompra"])


class PruebasPublicacionC2(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def copia(self):
        d = self.tmp / "pub"
        shutil.copytree(MUESTRA, d)
        return d

    def test_muestra_valida(self):
        r, datos = validar_publicacion(MUESTRA)
        self.assertTrue(r.valido, r.errores)
        self.assertIn("historial_ventas", datos)

    def test_clave_duplicada_invalida_el_lote(self):
        d = self.copia()
        h = leer(d / "historial_ventas.json")
        h.append(dict(h[0]))
        escribir(d / "historial_ventas.json", h)
        m = leer(d / "manifiesto.json")
        m["tablas"]["historial_ventas"]["filas"] += 1
        m["tablas"]["historial_ventas"]["sumas"]["importe_cop"] += h[0]["importe_cop"]
        escribir(d / "manifiesto.json", m)
        r, _ = validar_publicacion(d)
        self.assertTrue(any("clave duplicada" in e for e in r.errores), r.errores)

    def test_conteo_y_suma_declarados(self):
        d = self.copia()
        m = leer(d / "manifiesto.json")
        m["tablas"]["coberturas"]["filas"] = 99
        m["tablas"]["historial_ventas"]["sumas"]["importe_cop"] = 1
        escribir(d / "manifiesto.json", m)
        r, _ = validar_publicacion(d)
        self.assertEqual(len([e for e in r.errores if "coberturas" in e or "suma" in e]), 2)

    def test_ruta_fuera_del_directorio(self):
        d = self.copia()
        m = leer(d / "manifiesto.json")
        m["tablas"]["coberturas"]["archivo"] = "../fuera.json"
        escribir(d / "manifiesto.json", m)
        r, _ = validar_publicacion(d)
        self.assertFalse(r.valido)


class PruebasCLI(unittest.TestCase):
    def correr(self, *args):
        return subprocess.run([sys.executable, "-m", "contratos.validar", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")

    def test_codigos_de_salida(self):
        self.assertEqual(self.correr(str(EJEMPLOS / "valido.json")).returncode, 0)
        self.assertEqual(self.correr(str(EJEMPLOS / "id_repetido.json")).returncode, 1)
        self.assertEqual(self.correr(str(EJEMPLOS / "incompatible.json")).returncode, 2)
        self.assertEqual(self.correr(str(EJEMPLOS / "no_existe.json")).returncode, 2)
        self.assertEqual(self.correr("--publicacion", str(MUESTRA)).returncode, 0)

    def test_salida_json(self):
        r = self.correr("--json", str(EJEMPLOS / "incompleto.json"))
        self.assertFalse(json.loads(r.stdout)["valido"])


@unittest.skipUnless(shutil.which("node"), "node no disponible")
class PruebasParidadJS(unittest.TestCase):
    def test_mismo_veredicto_que_python(self):
        script = ("import('./app/contrato.js').then(m=>{const fs=require('fs');const e=JSON.parse(fs.readFileSync('contratos/agenda.v1.schema.json'));"
                  "const out={};for(const f of fs.readdirSync('contratos/ejemplos/agenda')){const r=m.validarAgenda(JSON.parse(fs.readFileSync('contratos/ejemplos/agenda/'+f)),e);"
                  "out[f]=r.errores.length===0}console.log(JSON.stringify(out))})")
        r = subprocess.run(["node", "-e", script], cwd=RAIZ, capture_output=True, text=True)
        js = json.loads(r.stdout)
        for f, ok in js.items():
            with self.subTest(f=f):
                self.assertEqual(ok, validar_agenda(leer(EJEMPLOS / f)).valido)


if __name__ == "__main__":
    unittest.main()
