"""B03 · Consultas por cierre y B05 · agenda operativa, avisos y eventos."""
import threading
import unittest

from api import operacion, publicacion, tareas
from api.base import ErrorApi, fijar_hoy

from _apoyo_app import CasoBase


class PruebasConsultas(CasoBase):
    def test_orden_paginacion_y_totales(self):
        _, p1 = self.http("GET", "/api/cierres/activo/agenda?tam=3&pagina=1", como="ventas1")
        _, p2 = self.http("GET", "/api/cierres/activo/agenda?tam=3&pagina=2", como="ventas1")
        _, todo = self.http("GET", "/api/cierres/activo/agenda?tam=50", como="ventas1")
        ids = [c["cliente_id"] for c in todo["items"]]
        self.assertEqual([c["cliente_id"] for c in p1["items"] + p2["items"]], ids[:6])
        self.assertEqual(p1["total"], 8); self.assertEqual(p1["paginas"], 3)

    def test_filtro_con_dos_acciones_iguales_y_totales_del_filtro(self):
        _, r = self.http("GET", "/api/cierres/activo/agenda?accion=Revisar%20cobertura", como="ventas1")
        self.assertEqual([c["cliente_id"] for c in r["items"]], ["DEMO02", "DEMO06"])  # prob 0.55 > 0.48
        self.assertAlmostEqual(r["ingreso_cop_filtrado"], sum(c["ingreso_cop"] for c in r["items"]))

    def test_sin_coincidencias(self):
        _, r = self.http("GET", "/api/cierres/activo/agenda?q=CLI999", como="ventas1")
        self.assertEqual((r["total"], r["estado"]), (0, "sin_coincidencias"))

    def test_ficha_inexistente_y_sin_historial(self):
        self.assertEqual(self.http("GET", "/api/cierres/activo/clientes/CLI999", como="ventas1")[0], 404)
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO04", como="ventas1")
        self.assertTrue(f["cliente"]["sin_historial"]); self.assertEqual(f["historial"], [])
        self.assertIn("Revisar primera compra", f["cliente"]["motivos"])

    def test_api_ficha_y_agenda_coinciden(self):
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO01", como="ventas1")
        _, a = self.http("GET", "/api/cierres/activo/agenda?q=DEMO01", como="ventas1")
        fila = a["items"][0]
        for k in ("dias_sin_compra", "ingreso_cop", "ventas_confirmadas", "accion", "motivos"):
            self.assertEqual(f["cliente"][k], fila[k], k)
        self.assertAlmostEqual(sum(v["importe_cop"] for v in f["historial"]), f["cliente"]["ingreso_cop"], places=2)

    def test_modelo_desactivado_conserva_reglas(self):
        operacion.fijar_bandera(self.db, self.usuario("ops1"), "modelo_compra", False)
        _, a = self.http("GET", "/api/cierres/activo/agenda?tam=50", como="ventas1")
        self.assertTrue(all(c["prob_compra_30d"] is None for c in a["items"]))
        self.assertEqual(a["items"][0]["accion"], "Revisar reactivación")
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO03", como="ventas1")
        self.assertEqual(f["cliente"]["estado_modelo"], "Modelo no disponible")

    def test_tableros_por_rol(self):
        _, g = self.http("GET", "/api/cierres/activo/tableros/gerencia", como="ger1")
        self.assertEqual(g["indicadores"]["clientes"], 8)
        _, o = self.http("GET", "/api/cierres/activo/tableros/operaciones", como="ops1")
        self.assertEqual({c["cliente_id"] for c in o["coberturas_proximas"]}, {"DEMO01", "DEMO02"})
        self.assertEqual([c["cliente_id"] for c in o["coberturas_vencidas"]], ["DEMO06"])

    def test_exportacion_csv_respeta_rol(self):
        st, csv = self.http("GET", "/api/cierres/activo/agenda.csv", como="ger1")
        self.assertEqual(st, 200); self.assertEqual(csv.count("\n"), 9)
        self.assertEqual(self.http("GET", "/api/cierres/activo/agenda.csv", como="ventas1")[0], 403)


class PruebasTareas(CasoBase):
    def cierre(self):
        with self.db.conexion() as con:
            return publicacion.cierre_activo(con)

    def tarea(self, cliente):
        with self.db.conexion() as con:
            return tareas.listar(con, cliente_id=cliente)[0]

    def test_una_tarea_por_episodio_y_motivos_coexistentes(self):
        t = self.tarea("DEMO01")
        self.assertEqual(t["motivos"], ["Revisar reactivación", "Revisar cobertura"])
        with self.db.conexion() as con:
            self.assertEqual(tareas.metricas(con)["episodios_con_varias_tareas"], 0)

    def test_reprocesar_lote_no_duplica_tareas_ni_avisos(self):
        with self.db.conexion() as con:
            antes = (con.execute("SELECT count(*) FROM tareas").fetchone()[0], con.execute("SELECT count(*) FROM avisos").fetchone()[0],
                     con.execute("SELECT count(*) FROM eventos").fetchone()[0])
        tareas.sincronizar(self.db, self.cierre()); tareas.sincronizar(self.db, self.cierre())
        with self.db.conexion() as con:
            despues = (con.execute("SELECT count(*) FROM tareas").fetchone()[0], con.execute("SELECT count(*) FROM avisos").fetchone()[0],
                       con.execute("SELECT count(*) FROM eventos").fetchone()[0])
            self.assertEqual(antes, despues)
            self.assertEqual(tareas.metricas(con)["avisos_duplicados"], 0)

    def test_posponer_hasta_otro_mes_se_respeta_al_regenerar(self):
        t = self.tarea("DEMO03")
        r = tareas.accion(self.db, self.usuario("ventas1"), t["id"], "posponer", {"version": t["version"], "hasta": "2026-12-15"})
        self.assertEqual(r["estado"], "pospuesta")
        # Nuevo cierre de noviembre con la misma oportunidad: sigue pospuesta.
        d = self.publicacion_modificada("nov", lambda tb: _mover_corte(tb, "2026-11-30"))
        publicacion.publicar_ruta(self.db, d, "ops1")
        self.assertEqual(self.tarea("DEMO03")["estado"], "pospuesta")
        # Cierre de diciembre posterior al aplazamiento: vuelve a abrirse con aviso.
        d2 = self.publicacion_modificada("dic", lambda tb: _mover_corte(tb, "2026-12-31"))
        publicacion.publicar_ruta(self.db, d2, "ops1")
        self.assertEqual(self.tarea("DEMO03")["estado"], "abierta")
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM avisos WHERE tipo = 'fin_aplazamiento'").fetchone()[0], 1)

    def test_cierre_manual_no_se_reabre_y_evidencia_historica_se_conserva(self):
        t = self.tarea("DEMO01")
        tareas.accion(self.db, self.usuario("ventas1"), t["id"], "descartar", {"version": t["version"], "motivo": "Cliente en proceso de baja"})

        def cambiar(tb):
            _mover_corte(tb, "2026-11-30")
            tb["manifiesto"]["versiones"]["modelo_compra"] = None  # se retira el modelo
            for o in tb["oportunidades"]:
                if o["cliente_id"] == "DEMO01":
                    o["evidencia"]["dias_sin_compra"] = 120
        publicacion.publicar_ruta(self.db, self.publicacion_modificada("nov", cambiar), "ops1")
        with self.db.conexion() as con:
            det = tareas.detalle(con, t["id"])
        self.assertEqual(det["estado"], "descartada")
        self.assertEqual([e["version_modelo"] for e in det["historial_evidencia"]], ["demo-logistica-0", None])
        self.assertEqual(det["historial_evidencia"][0]["evidencia"]["dias_sin_compra"], 90)

    def test_cerrar_desde_dos_sesiones(self):
        t = self.tarea("DEMO02")
        resultados = []

        def atender(u):
            try:
                tareas.accion(self.db, self.usuario(u), t["id"], "atender", {"version": t["version"], "resultado": f"hecho por {u}"})
                resultados.append("ok")
            except ErrorApi as e:
                resultados.append(e.status)
        hs = [threading.Thread(target=atender, args=(u,)) for u in ("ventas1", "ventas2")]
        [h.start() for h in hs]; [h.join() for h in hs]
        self.assertEqual(sorted(map(str, resultados)), ["409", "ok"])

    def test_reintento_con_clave_de_idempotencia(self):
        t = self.tarea("DEMO06")
        st1, r1 = self.http("POST", f"/api/tareas/{t['id']}/asignar", {"version": t["version"]}, como="ventas1", cabeceras={"Idempotency-Key": "k1"})
        st2, r2 = self.http("POST", f"/api/tareas/{t['id']}/asignar", {"version": t["version"]}, como="ventas1", cabeceras={"Idempotency-Key": "k1"})
        self.assertEqual((st1, st2), (200, 200)); self.assertTrue(r2.get("repetida"))
        with self.db.conexion() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM eventos WHERE tipo = 'asignada'").fetchone()[0], 1)

    def test_cupo_k_y_eventos_reconstruyen_denominador(self):
        _, lista = self.http("GET", "/api/tareas?k=3", como="ventas1")
        self.assertEqual(len(lista), 3)
        self.assertEqual(lista[0]["cliente_id"], "DEMO01")
        _, ev = self.http("GET", "/api/exportes/eventos", como="ops1")
        expuestas = {e["episodio_id"] for e in ev["eventos"] if e["tipo"] == "expuesta"}
        with self.db.conexion() as con:
            self.assertEqual(len(expuestas), con.execute("SELECT count(*) FROM tareas").fetchone()[0])

    def test_compra_posterior_observada_separada_de_resultado(self):
        # La tarea guarda su creación con la hora real: la compra «posterior» se fecha después de ese día,
        # para que la prueba no dependa del día en que se ejecuta.
        from datetime import date, timedelta
        with self.db.conexion() as con:
            creada = con.execute("SELECT creada_en FROM tareas WHERE cliente_id = 'DEMO03'").fetchone()[0][:10]
        compra = date.fromisoformat(creada) + timedelta(days=1)
        corte = max(date(2026, 11, 30), compra + timedelta(days=5))

        def cambiar(tb):
            _mover_corte(tb, corte.isoformat())
            for c in tb["agenda"]["clientes"]:
                if c["cliente_id"] == "DEMO03":
                    c["ultima_compra"] = compra.isoformat(); c["dias_sin_compra"] = (corte - compra).days
        fijar_hoy("2026-11-02")
        d = self.publicacion_modificada("nov", cambiar)
        publicacion.publicar_ruta(self.db, d, "ops1")
        with self.db.conexion() as con:
            tipos = [r[0] for r in con.execute("SELECT tipo FROM eventos WHERE cliente_id = 'DEMO03'")]
        self.assertIn("compra_posterior_observada", tipos)
        self.assertNotIn("resultado_atribuido", tipos)

    def test_descartar_requiere_motivo(self):
        t = self.tarea("DEMO04")
        with self.assertRaises(ErrorApi):
            tareas.accion(self.db, self.usuario("ventas1"), t["id"], "descartar", {"version": t["version"]})


def _mover_corte(tb, corte):
    tb["manifiesto"]["corte"] = corte
    tb["agenda"]["corte"] = corte


if __name__ == "__main__":
    unittest.main()
