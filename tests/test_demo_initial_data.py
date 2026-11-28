import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api import base, demo


class DatosInicialesTests(unittest.TestCase):
    def test_base_nueva_publica_el_paquete_inicial(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = base.BaseDatos(Path(tmp) / "jacomind.sqlite3")
            demo.solo_permisos(db)
            with mock.patch("api.operacion.ejecutar_cierre", return_value={"estado": "publicado", "ultimo_cierre_valido": "2026-10-31-r1"}) as cierre:
                resultado = demo.inicializar_datos_iniciales(db)

            self.assertEqual(resultado["estado"], "publicado")
            cierre.assert_called_once_with(db, "programador", "2026-10-31", datos=str(demo.DATOS_INICIALES), reintentos=0)

    def test_cierre_real_existente_no_se_reemplaza(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = base.BaseDatos(Path(tmp) / "jacomind.sqlite3")
            demo.solo_permisos(db)
            db.migrar()
            with db.transaccion() as con:
                con.execute("""INSERT INTO cierres
                    (id, corte, revision, huella, version_contrato, origen, manifiesto_json, estado, publicado_por, publicado_en)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            ("real-1", "2026-10-31", 1, "huella-real-1", 1, "produccion",
                             '{"cierre_id":"real-1","origen":"produccion"}', "publicado", "ops1", "2026-11-01T00:00:00Z"))
                con.execute("INSERT INTO cierre_activo (id, cierre_id, activado_en) VALUES (1, ?, ?)", ("real-1", "2026-11-01T00:00:00Z"))
            with mock.patch("api.operacion.ejecutar_cierre") as cierre:
                resultado = demo.inicializar_datos_iniciales(db)

            self.assertEqual(resultado, {"estado": "existente", "cierre": "real-1"})
            cierre.assert_not_called()


if __name__ == "__main__":
    unittest.main()
