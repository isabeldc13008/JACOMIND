import unittest
from decimal import Decimal


class ValidacionTests(unittest.TestCase):
    def test_incidencia_de_referencia_desconocida_tiene_ubicacion_y_accion(self):
        from pipeline.esquemas import TABLAS
        from pipeline.validacion import validar_fila

        issues = validar_fila({"venta_id": "VEN001", "fecha": "2026-01-02", "cliente_id": "NO_EXISTE", "producto_id": "PR001", "cantidad": 1, "moneda": "COP", "precio_unitario": Decimal("10"), "descuento_pct": Decimal("0"), "estado": "Confirmada", "origen_datos": "prueba"}, TABLAS["ventas"], {"clientes": {"CLI001"}, "productos": {"PR001"}} , archivo="ventas.csv", fila=2)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].field, "cliente_id")
        self.assertEqual(issues[0].row, 2)
        self.assertEqual(issues[0].action, "aislar")

    def test_clave_duplicada_identica_se_clasifica_aparte(self):
        from pipeline.esquemas import TABLAS
        from pipeline.validacion import validar_tabla

        rows = [{"cliente_id": "CLI001", "nombre_prueba": "A", "sector_prueba": "S", "ciudad_prueba": "C", "fecha_alta": "2026-01-01", "canal_preferido_prueba": "X", "origen_datos": "p"}, {"cliente_id": "CLI001", "nombre_prueba": "A", "sector_prueba": "S", "ciudad_prueba": "C", "fecha_alta": "2026-01-01", "canal_preferido_prueba": "X", "origen_datos": "p"}]
        result = validar_tabla(rows, TABLAS["clientes"], {}, archivo="clientes.csv")
        self.assertEqual(len(result.accepted), 1)
        self.assertEqual(result.duplicate_count, 1)
        self.assertEqual(result.issues[0].code, "DUPLICADO_IDENTICO")


if __name__ == "__main__":
    unittest.main()
