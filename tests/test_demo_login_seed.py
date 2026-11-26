import tempfile
import unittest
from pathlib import Path

from api.auth import crear_sesion
from api.base import BaseDatos
from api.demo import solo_permisos


class DemoLoginSeedTests(unittest.TestCase):
    def test_solo_permisos_sembra_identidades_para_login_demo(self):
        with tempfile.TemporaryDirectory(prefix="jacomind-login-") as tmp:
            db = BaseDatos(Path(tmp) / "jacomind.sqlite3")
            solo_permisos(db)

            token, usuario = crear_sesion(db, "ops1")

            self.assertTrue(token)
            self.assertEqual(usuario.id, "ops1")
            self.assertIn("operaciones", usuario.roles)


if __name__ == "__main__":
    unittest.main()
