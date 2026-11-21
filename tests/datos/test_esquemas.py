import unittest


class EsquemasTests(unittest.TestCase):
    def test_tablas_principales_definen_claves_y_columnas(self):
        from pipeline.esquemas import TABLAS

        self.assertEqual(set(TABLAS), {"clientes", "productos", "proveedores", "trm", "ventas", "compras", "instalaciones"})
        self.assertEqual(TABLAS["clientes"].primary_key, ("cliente_id",))
        self.assertIn("cliente_id", TABLAS["ventas"].columns)
        self.assertEqual(TABLAS["ventas"].references["cliente_id"], ("clientes", "cliente_id"))


if __name__ == "__main__":
    unittest.main()
