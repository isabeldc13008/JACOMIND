"""Integración: servidor HTTP real, cookies de sesión, estáticos y modo práctica."""
import json
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from api import base  # noqa: E402
from api.base import BaseDatos  # noqa: E402
from api.demo import preparar  # noqa: E402
from api.servidor import Aplicacion, crear_servidor  # noqa: E402


class ServidorReal(unittest.TestCase):
    practica = False

    @classmethod
    def setUpClass(cls):
        base.fijar_hoy("2026-11-21")
        cls.tmp = Path(tempfile.mkdtemp())
        cls.db = BaseDatos(cls.tmp / "s.sqlite3")
        preparar(cls.db)
        cls.srv = crear_servidor(Aplicacion(cls.db, practica=cls.practica), "127.0.0.1", 0)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        base.fijar_hoy(None)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def cliente(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def pedir(self, op, metodo, ruta, cuerpo=None, csrf=True):
        req = urllib.request.Request(self.url + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                     headers={"Content-Type": "application/json", **({"X-Jacomind": "1"} if csrf else {})})
        try:
            with op.open(req) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)


class PruebasServidor(ServidorReal):
    def test_sesion_por_cookie_y_agenda(self):
        op = self.cliente()
        st, cuerpo, cab = self.pedir(op, "POST", "/api/sesion", {"identidad": "ops1"})
        self.assertEqual(st, 200); self.assertIn("HttpOnly", cab["Set-Cookie"]); self.assertIn("SameSite=Strict", cab["Set-Cookie"])
        st, cuerpo, _ = self.pedir(op, "GET", "/api/cierres/activo/agenda")
        self.assertEqual(st, 200); self.assertEqual(json.loads(cuerpo)["total"], 8)
        self.pedir(op, "DELETE", "/api/sesion")
        self.assertEqual(self.pedir(op, "GET", "/api/cierres/activo/agenda")[0], 401)

    def test_csrf(self):
        op = self.cliente()
        self.pedir(op, "POST", "/api/sesion", {"identidad": "cli_a"})
        st, _, _ = self.pedir(op, "POST", "/api/pqrs", {"asunto": "a", "descripcion": "b"}, csrf=False)
        self.assertEqual(st, 403)

    def test_estaticos_y_cabeceras_de_seguridad(self):
        op = self.cliente()
        st, cuerpo, cab = self.pedir(op, "GET", "/app/")
        self.assertEqual(st, 200); self.assertIn(b"JACOMIND", cuerpo)
        self.assertEqual(cab["X-Content-Type-Options"], "nosniff"); self.assertIn("frame-ancestors 'none'", cab["Content-Security-Policy"])
        self.assertEqual(self.pedir(op, "GET", "/contratos/agenda.v1.schema.json")[0], 200)
        self.assertEqual(self.pedir(op, "GET", "/app/../api/base.py")[0], 404)
        self.assertEqual(self.pedir(op, "GET", "/salida/agenda.json")[0], 404)  # fuera del modo práctica

    def test_sesion_expirada(self):
        op = self.cliente()
        self.pedir(op, "POST", "/api/sesion", {"identidad": "ger1"})
        with self.db.conexion() as con:
            con.execute("UPDATE sesiones SET expira_en = '2000-01-01T00:00:00+00:00'")
        self.assertEqual(self.pedir(op, "GET", "/api/cierres")[0], 401)


class PruebasModoPractica(ServidorReal):
    practica = True

    def test_salida_local_solo_en_practica(self):
        salida = RAIZ / "salida" / "agenda.json"
        if not salida.exists():
            self.skipTest("Sin salida/agenda.json local (la genera el pipeline de A)")
        self.assertEqual(self.pedir(self.cliente(), "GET", "/salida/agenda.json")[0], 200)

    def test_ejemplo_de_practica(self):
        st, cuerpo, _ = self.pedir(self.cliente(), "GET", "/app/fixtures/agenda.json")
        self.assertEqual(st, 200); self.assertEqual(json.loads(cuerpo)["version"], 1)


if __name__ == "__main__":
    unittest.main()
