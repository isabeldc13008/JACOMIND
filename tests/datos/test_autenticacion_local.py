"""Pruebas del esquema y bootstrap de autenticación local."""
import shutil
import tempfile
import unittest
from pathlib import Path

from api.base import BaseDatos
from api.demo import preparar


class PruebasAutenticacionLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = BaseDatos(self.tmp / "auth.sqlite3")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_preparar_crea_admin_y_tablas_de_autenticacion(self):
        preparar(self.db, publicar_muestra=False)
        with self.db.conexion() as con:
            tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            self.assertTrue({"usuarios_locales", "roles", "roles_permisos"} <= tablas)
            admin = con.execute("SELECT id, nombre, activo FROM identidades WHERE id = 'admin'").fetchone()
            self.assertIsNotNone(admin)
            self.assertEqual(admin["nombre"], "Administrador JACOMIND")
            self.assertEqual(admin["activo"], 1)
            cred = con.execute("SELECT password_hash, requiere_cambio_clave FROM usuarios_locales WHERE identidad_id = 'admin'").fetchone()
            self.assertIsNotNone(cred)
            self.assertNotEqual(cred["password_hash"], "admin123")
            self.assertEqual(cred["requiere_cambio_clave"], 1)

    def test_bootstrap_es_idempotente_y_no_reemplaza_clave(self):
        preparar(self.db, publicar_muestra=False)
        with self.db.transaccion() as con:
            con.execute("UPDATE usuarios_locales SET password_hash = 'hash-cambiado', requiere_cambio_clave = 0 WHERE identidad_id = 'admin'")
        preparar(self.db, publicar_muestra=False)
        with self.db.conexion() as con:
            cred = con.execute("SELECT password_hash, requiere_cambio_clave FROM usuarios_locales WHERE identidad_id = 'admin'").fetchone()
            self.assertEqual(cred["password_hash"], "hash-cambiado")
            self.assertEqual(cred["requiere_cambio_clave"], 0)


if __name__ == "__main__":
    unittest.main()
