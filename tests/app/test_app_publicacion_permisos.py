"""B02 · Publicación transaccional, concurrencia y matriz de acceso rol × acción."""
import threading
import unittest

from api import publicacion
from api.base import ErrorApi
from api.permisos import MATRIZ, ROLES

from _apoyo_app import CasoBase, EJEMPLOS, MUESTRA, escribir


class PruebasPublicacion(CasoBase):
    publicar_muestra = False

    def activo(self):
        with self.db.conexion() as con:
            return publicacion.cierre_activo(con)

    def test_publicaciones_identicas_simultaneas_una_revision(self):
        resultados, errores = [], []

        def publicar():
            try:
                resultados.append(publicacion.publicar_ruta(self.db, MUESTRA, "ops1"))
            except Exception as e:  # pragma: no cover
                errores.append(e)
        hilos = [threading.Thread(target=publicar) for _ in range(4)]
        [h.start() for h in hilos]; [h.join() for h in hilos]
        self.assertFalse(errores)
        self.assertEqual(len({r["cierre_id"] for r in resultados}), 1)
        self.assertEqual(sum(not r["ya_publicado"] for r in resultados), 1)
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM cierres").fetchone()[0], 1)

    def test_importacion_interrumpida_conserva_cierre_anterior(self):
        primero = publicacion.publicar_ruta(self.db, MUESTRA, "ops1")["cierre_id"]

        def cambiar(t):
            t["manifiesto"]["versiones"]["reglas"] = "reglas-demo-2"
        d = self.publicacion_modificada("v2", cambiar)
        for etapa in ("staging", "mover", "activar"):
            with self.subTest(etapa=etapa):
                publicacion.FALLO_SIMULADO = etapa
                with self.assertRaises(ErrorApi):
                    publicacion.publicar_ruta(self.db, d, "ops1")
                self.assertEqual(self.activo(), primero)
                with self.db.conexion() as con:
                    self.assertEqual(con.execute("SELECT count(*) FROM cierres").fetchone()[0], 1)
                    self.assertEqual(con.execute("SELECT count(*) FROM stg_filas").fetchone()[0], 0)
        publicacion.FALLO_SIMULADO = None
        segundo = publicacion.publicar_ruta(self.db, d, "ops1")
        self.assertEqual(segundo["revision"], 2)
        self.assertEqual(self.activo(), segundo["cierre_id"])

    def test_version_incompatible_rechazada(self):
        primero = publicacion.publicar_ruta(self.db, MUESTRA, "ops1")["cierre_id"]
        with self.assertRaises(ErrorApi) as cm:
            publicacion.publicar_ruta(self.db, EJEMPLOS / "incompatible.json", "ops1")
        self.assertEqual(cm.exception.status, 409)
        self.assertEqual(self.activo(), primero)
        with self.db.conexion() as con:
            fila = con.execute("SELECT resultado FROM auditoria WHERE accion = 'cierre.publicar' ORDER BY id DESC").fetchone()
        self.assertEqual(fila[0], "rechazado")

    def test_agenda_suelta_se_envuelve_en_c2(self):
        r = publicacion.publicar_ruta(self.db, EJEMPLOS / "valido.json", "ops1")
        self.assertFalse(r["ya_publicado"])
        st, res = self.http("GET", "/api/cierres/activo/resumen", como="ops1")
        self.assertEqual(res["resumen"]["clientes"], 8)

    def test_regenerar_con_mismos_insumos_no_crea_revision(self):
        a = publicacion.publicar_ruta(self.db, MUESTRA, "ops1")

        def solo_hora(t):
            t["agenda"]["generado_en"] = "2026-11-02T08:00:00+00:00"
            t["manifiesto"]["generado_en"] = "2026-11-02T08:00:00+00:00"
        b = publicacion.publicar_ruta(self.db, self.publicacion_modificada("otra_hora", solo_hora), "ops1")
        self.assertEqual((b["cierre_id"], b["ya_publicado"]), (a["cierre_id"], True))

    def test_metricas_en_base_coinciden_con_manifiesto(self):
        publicacion.publicar_ruta(self.db, MUESTRA, "ops1")
        with self.db.conexion() as con:
            c = publicacion.resolver_cierre(con, "activo")
            for t, decl in c["manifiesto"]["tablas"].items():
                n = (con.execute("SELECT count(*) FROM an_agenda WHERE cierre_id = ?", (c["id"],)) if t == "agenda" else
                     con.execute("SELECT count(*) FROM an_filas WHERE cierre_id = ? AND tabla = ?", (c["id"], t))).fetchone()[0]
                self.assertEqual(n, decl["filas"], t)

    def test_cambio_atomico_visible_desde_dos_sesiones(self):
        publicacion.publicar_ruta(self.db, MUESTRA, "ops1")
        d = self.publicacion_modificada("v2", lambda t: t["manifiesto"]["versiones"].update(reglas="x"))
        publicacion.publicar_ruta(self.db, d, "ops1")
        _, a = self.http("GET", "/api/cierres/activo/resumen", como="ops1")
        _, b = self.http("GET", "/api/cierres/activo/resumen", como="ger1")
        self.assertEqual(a["cierre"]["id"], b["cierre"]["id"])
        self.assertEqual(a["cierre"]["revision"], 2)


class PruebasMatrizAcceso(CasoBase):
    # Una ruta representativa por acción (GET salvo indicación).
    RUTAS = {
        "cartera.ver": ("GET", "/api/cierres/activo/agenda"),
        "cartera.exportar": ("GET", "/api/cierres/activo/agenda.csv"),
        "tablero.ventas": ("GET", "/api/cierres/activo/tableros/ventas"),
        "tablero.operaciones": ("GET", "/api/cierres/activo/tableros/operaciones"),
        "tablero.gerencia": ("GET", "/api/cierres/activo/tableros/gerencia"),
        "tareas.ver": ("GET", "/api/tareas"),
        "finanzas.ver": ("GET", "/api/finanzas/activo/panel"),
        "informes.ver": ("GET", "/api/informes"),
        "pqrs.indicadores": ("GET", "/api/pqrs-indicadores"),
        "pqrs.exportar": ("GET", "/api/exportes/pqrs"),
        "beneficios.portal": ("GET", "/api/portal/beneficios"),
        "beneficios.ver_interno": ("GET", "/api/beneficios"),
        "documentos.gestionar": ("GET", "/api/documentos"),
        "operacion.administrar": ("GET", "/api/operacion"),
        "auditoria.ver": ("GET", "/api/auditoria"),
        "eventos.exportar": ("GET", "/api/exportes/eventos"),
    }
    IDENT = {"operaciones": "ops1", "ventas": "ventas1", "finanzas": "fin1", "atencion": "aten1", "gerencia": "ger1", "empresa": "cli_a"}

    def test_cada_combinacion_rol_accion(self):
        for accion, (metodo, ruta) in self.RUTAS.items():
            for rol in ROLES:
                with self.subTest(accion=accion, rol=rol):
                    st, _ = self.http(metodo, ruta, como=self.IDENT[rol])
                    esperado_ok = rol in MATRIZ[accion]
                    self.assertEqual(st == 200, esperado_ok, f"{rol} {accion} → {st}")
                    if not esperado_ok:
                        self.assertEqual(st, 403)

    def test_sin_sesion(self):
        for _, (metodo, ruta) in self.RUTAS.items():
            self.assertEqual(self.http(metodo, ruta)[0], 401)

    def test_cookie_secure_detras_de_https(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"JACOMIND_COOKIE_SEGURA": "1"}):
            r = self.app.despachar("POST", "/api/sesion", {"X-Jacomind": "1"}, b'{"identidad": "ops1"}')
        self.assertTrue(r.cabeceras["Set-Cookie"].endswith("; Secure"))
        r = self.app.despachar("POST", "/api/sesion", {"X-Jacomind": "1"}, b'{"identidad": "ops1"}')
        self.assertNotIn("Secure", r.cabeceras["Set-Cookie"])

    def test_csrf_en_escrituras(self):
        r = self.app.despachar("POST", "/api/pqrs", {}, b"{}")
        self.assertEqual(r.status, 403)

    def test_cartera_no_es_estatica_en_portal(self):
        escribir(self.tmp / "dummy.json", {})
        self.assertEqual(self.app.despachar("GET", "/salida/agenda.json", {}, b"").status, 404)

    def test_publicar_solo_rutas_permitidas(self):
        st, d = self.http("POST", "/api/cierres/publicar", {"ruta": "C:/Windows/win.ini"}, como="ops1")
        self.assertEqual(st, 400)
        st, d = self.http("POST", "/api/cierres/publicar", {"ruta": "../../etc"}, como="ops1")
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
