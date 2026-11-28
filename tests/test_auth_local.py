import os
import tempfile
import unittest
from pathlib import Path

from api.auth import crear_usuario_local, autenticar_local, verificar_password, listar_usuarios, crear_sesion, resolver, actualizar_usuario_local
from api.base import BaseDatos
from api.demo import solo_permisos


class AuthLocalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="jacomind-auth-")
        self.db = BaseDatos(Path(self.tmp.name) / "jacomind.sqlite3")
        solo_permisos(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_crea_y_autentica_usuario_con_hash(self):
        crear_usuario_local(self.db, "olga", "Olga", "operaciones", "Clave-Segura-1")
        usuario = autenticar_local(self.db, "olga", "Clave-Segura-1")
        self.assertEqual(usuario.id, "olga")
        self.assertIn("operaciones", usuario.roles)
        with self.db.conexion() as con:
            fila = con.execute("SELECT password_hash, password_salt FROM usuarios_locales WHERE usuario = 'olga'").fetchone()
        self.assertNotEqual(fila[0], "Clave-Segura-1")
        self.assertTrue(verificar_password("Clave-Segura-1", fila[1], fila[0]))

    def test_rechaza_clave_incorrecta_y_usuario_inactivo(self):
        crear_usuario_local(self.db, "ventas", "Ventas", "ventas", "Clave-1-segura")
        with self.assertRaisesRegex(Exception, "Credenciales"):
            autenticar_local(self.db, "ventas", "otra")
        with self.db.transaccion() as con:
            con.execute("UPDATE usuarios_locales SET activo = 0 WHERE usuario = 'ventas'")
        with self.assertRaisesRegex(Exception, "Credenciales"):
            autenticar_local(self.db, "ventas", "Clave-1-segura")

    def test_lista_no_expone_hash(self):
        crear_usuario_local(self.db, "fin", "Finanzas", "finanzas", "Clave-1-segura")
        fila = listar_usuarios(self.db)[-1]
        self.assertNotIn("password_hash", fila)
        self.assertEqual(fila["rol"], "finanzas")

    def test_desactivar_cuenta_invalida_susiones_existentes(self):
        crear_usuario_local(self.db, "atencion", "Atención", "atencion", "Clave-1-segura")
        token, _ = crear_sesion(self.db, "atencion")
        actualizar_usuario_local(self.db, "atencion", activo=False)
        self.assertIsNone(resolver(self.db, token))


if __name__ == "__main__":
    unittest.main()
