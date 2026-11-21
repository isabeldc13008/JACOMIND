"""Datos que sostienen el plan de mejora de vistas (docs/plan/mejora-de-vistas.md).

Comprueban con la demo las cifras que las pantallas muestran y que el plan cita como ejemplo.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

from api import consultas

from _apoyo_app import CasoBase, RAIZ


class PruebasLecturaDelNegocio(CasoBase):
    def test_gerencia_compara_ultimo_mes_completo_y_familia(self):
        _, t = self.http("GET", "/api/cierres/activo/tableros/gerencia", como="ger1")
        c = t["comparacion"]
        self.assertEqual((c["mes_anterior"], c["mes"]), ("2026-09", "2026-10"))
        self.assertEqual((c["valor_anterior"], c["valor"], c["diferencia"]), (21020000.0, 4560000.0, -16460000.0))
        fams = [f for f in c["familias"] if f["familia"] != "Total"]
        self.assertEqual((fams[0]["familia"], fams[0]["diferencia"]), ("Infraestructura", -16440000.0))
        # Las familias explican aritméticamente la variación del total.
        self.assertAlmostEqual(sum(f["diferencia"] for f in fams), c["diferencia"])
        self.assertEqual(t["indicadores"]["ingreso_cop"], 51150000.0)
        self.assertEqual(t["fuente"]["cierre_id"], t["cierre"]["id"])

    def test_mes_incompleto_no_se_compara(self):
        series = [{"familia": "Total", "tipo": "historico", "periodo": p, "valor_cop": v, "completo": c}
                  for p, v, c in [("2026-08", 10.0, True), ("2026-09", 20.0, True), ("2026-10", None, False)]]
        c = consultas.comparacion_mensual(series)
        self.assertEqual((c["mes_anterior"], c["mes"]), ("2026-08", "2026-09"))
        self.assertEqual(c["meses_incompletos"], ["2026-10"])
        self.assertEqual(consultas.comparacion_mensual(series[:1])["estado"], "sin_comparacion")

    def test_agenda_seleccion_de_cobertura_y_csv_filtrado(self):
        _, a = self.http("GET", "/api/cierres/activo/agenda?accion=Revisar%20cobertura", como="ger1")
        self.assertEqual([c["cliente_id"] for c in a["items"]], ["DEMO02", "DEMO06"])
        self.assertEqual(a["ingreso_cop_filtrado"], 12560000.0)
        _, csv = self.http("GET", "/api/cierres/activo/agenda.csv?accion=Revisar%20cobertura", como="ger1")
        filas = [l for l in csv.strip().splitlines()[1:] if l]
        self.assertEqual([f.split(",")[0] for f in filas], ["DEMO02", "DEMO06"])
        _, todo = self.http("GET", "/api/cierres/activo/agenda.csv", como="ger1")
        self.assertEqual(len(todo.strip().splitlines()) - 1, 8)

    def test_ficha_trae_oportunidad_fecha_sugerida_y_conteo(self):
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO02", como="ventas1")
        self.assertEqual(f["oportunidades"][0]["accion"], "Revisar cobertura")
        self.assertEqual(f["oportunidades"][0]["fecha_sugerida"], "2026-11-07")
        self.assertEqual(f["historial_total"], len(f["historial"]))
        self.assertEqual(f["modelo"]["umbral"], 0.4)


class PruebasTableros(CasoBase):
    def test_operaciones_ordena_por_fecha_e_intervalos_cuentan_coberturas(self):
        _, t = self.http("GET", "/api/cierres/activo/tableros/operaciones", como="ops1")
        self.assertEqual([c["cliente_id"] for c in t["coberturas_proximas"]], ["DEMO02", "DEMO01"])
        self.assertEqual([c["cliente_id"] for c in t["coberturas_vencidas"]], ["DEMO06"])
        n = {i["clave"]: i["coberturas"] for i in t["intervalos"]}
        self.assertEqual(n, {"vencidas": 1, "0-15": 0, "16-30": 1, "31-45": 1})
        self.assertTrue(t["detalle_disponible"])

    def test_ventas_segmentos_ordenados_y_limite_de_oportunidades(self):
        _, t = self.http("GET", "/api/cierres/activo/tableros/ventas", como="ventas1")
        conteos = [s["clientes"] for s in t["segmentos"]]
        self.assertEqual(conteos, sorted(conteos, reverse=True))
        self.assertEqual(sum(conteos), t["total_clientes"])
        self.assertEqual(t["limite_oportunidades"], 20)
        self.assertEqual(t["etiquetas"]["ambas"], 2)  # DEMO01 y DEMO08: frecuentes y fríos
        self.assertTrue(all("accion" in o for o in t["oportunidades"]))


class PruebasServicio(CasoBase):
    def test_metricas_separan_alcance_del_equipo_y_pendientes_de_la_seleccion(self):
        _, todas = self.http("GET", "/api/tareas/metricas", como="ventas1")
        _, mias = self.http("GET", "/api/tareas/metricas?mias=1", como="ventas1")
        self.assertEqual(todas["por_tipo"], mias["por_tipo"])
        self.assertGreater(todas["pendientes_seleccion"], mias["pendientes_seleccion"])

    def test_contacto_queda_en_la_cronologia_sin_cerrar_la_tarea(self):
        _, lista = self.http("GET", "/api/tareas?k=1", como="ventas1")
        t = lista[0]
        _, d = self.http("POST", f"/api/tareas/{t['id']}/contacto",
                         {"version": t["version"], "nota": "Llamada", "siguiente_paso": "Enviar propuesta"}, como="ventas1")
        self.assertNotIn(d["estado"], ("atendida", "descartada"))
        ev = [e for e in d["eventos"] if e["tipo"] == "contacto_registrado"][0]
        self.assertEqual(ev["datos"]["nota"], "Llamada")

    def test_historial_publico_omite_acciones_internas(self):
        _, lista = self.http("GET", "/api/pqrs", como="aten1")
        c = lista[0]
        _, det = self.http("GET", f"/api/pqrs/{c['radicado']}", como="aten1")
        self.http("POST", f"/api/pqrs/{c['radicado']}/categorizar", {"version": det["version"], "categoria": "peticion"}, como="aten1")
        dueno = "cli_a" if det["organizacion_id"] == "EMP-A" else "cli_b"
        _, pub = self.http("GET", f"/api/pqrs/{c['radicado']}", como=dueno)
        self.assertNotIn("categorizar", [h["accion"] for h in pub["historial"]])
        self.assertIn("actualizado_en", pub)

    def test_indicadores_informan_casos_medidos(self):
        _, ind = self.http("GET", "/api/pqrs-indicadores", como="ger1")
        self.assertIn("casos_medidos_primera_gestion", ind)
        self.assertIsNone(ind["horas_resolucion_mediana_total"])  # aún no hay respuestas

    def test_beneficios_condicion_y_disponibilidad(self):
        _, cat = self.http("GET", "/api/beneficios", como="aten1")
        futuro = next(b for b in cat if b["id"] == "BEN-FUTURO")
        self.assertEqual((futuro["estado"], futuro["disponibilidad"], futuro["visible_en_portal"]), ("publicado", "programado", False))
        soporte = next(b for b in cat if b["id"] == "BEN-SOPORTE")
        self.assertIn("segmentos Recurrente activo o Recurrente en pausa", soporte["condicion"])
        _, portal = self.http("GET", "/api/portal/beneficios", como="cli_a")
        self.assertTrue(all("condicion" in b for b in portal))

    def test_simulador_detalla_operaciones_y_estado(self):
        _, r = self.http("GET", "/api/finanzas/activo/simular?periodo=2026-10&variacion=8", como="fin1")
        self.assertEqual((r["estado"], r["diferencia_cop"]), ("ok", 96000.0))
        self.assertEqual([o["compra_id"] for o in r["operaciones_incluidas"]], ["CD03"])
        self.assertEqual([o["compra_id"] for o in r["compras_en_pesos"]], ["CD04"])

    def test_informe_abre_con_lo_que_cambio_y_guarda_la_serie(self):
        _, a = self.http("POST", "/api/informes", {"cierre": "activo"}, como="ger1")
        _, html = self.http("GET", f"/api/informes/{a['cierre_id']}/{a['revision']}", como="ger1")
        self.assertLess(html.index("Qué cambió"), html.index("Anexo"))
        self.assertIn("4,56 millones de COP", html)
        self.assertIn("Infraestructura", html)
        self.assertIn("51.150.000,00", html)
        _, lista = self.http("GET", "/api/informes", como="ops1")
        self.assertEqual(lista[0]["corte"], "2026-10-31")


@unittest.skipUnless(shutil.which("node"), "Node no disponible")
class PruebasInterfaz(unittest.TestCase):
    def test_modulos_de_la_interfaz_son_validos(self):
        for f in sorted(Path(RAIZ / "app").rglob("*.js")):
            r = subprocess.run(["node", "--input-type=module", "--check"], input=f.read_bytes(), capture_output=True)
            self.assertEqual(r.returncode, 0, f"{f.name}: {r.stderr.decode(errors='replace')}")


class PruebasRevisionDelPlan(CasoBase):
    def test_estado_informa_fecha_y_origen_del_cierre(self):
        _, e = self.http("GET", "/api/estado")
        self.assertEqual((e["corte_activo"], e["origen_activo"]), ("2026-10-31", "sintetico"))

    def test_modelo_desactivado_conserva_reglas_y_orden_por_id(self):
        self.http("POST", "/api/operacion/banderas", {"nombre": "modelo_compra", "activo": False}, como="ops1")
        _, r = self.http("GET", "/api/cierres/activo/resumen", como="ventas1")
        self.assertFalse(r["modelo_activo"])
        _, a = self.http("GET", "/api/cierres/activo/agenda?accion=Revisar%20cobertura", como="ventas1")
        self.assertEqual([c["cliente_id"] for c in a["items"]], ["DEMO02", "DEMO06"])
        self.assertTrue(all(c["prob_compra_30d"] is None for c in a["items"]))

    def test_asistente_de_empresa_resume_condicion_y_politica(self):
        _, r = self.http("POST", "/api/asistente", {"pregunta": "¿Qué beneficios tengo disponibles?"}, como="cli_a")
        self.assertIn("Aplica a", r["texto"]); self.assertIn("política POL-BENEF v2", r["texto"])
        self.assertNotIn("filtros", r["texto"])

    def test_reapertura_visible_en_el_historial_publico(self):
        _, lista = self.http("GET", "/api/pqrs", como="cli_a")
        rad = lista[0]["radicado"]
        _, d = self.http("GET", f"/api/pqrs/{rad}", como="aten1")
        _, d = self.http("POST", f"/api/pqrs/{rad}/responder", {"version": d["version"], "respuesta": "Revisado."}, como="aten1")
        self.http("POST", f"/api/pqrs/{rad}/reabrir", {"version": d["version"], "nota": "Nueva evidencia"}, como="aten1")
        _, pub = self.http("GET", f"/api/pqrs/{rad}", como="cli_a")
        self.assertEqual([h["accion"] for h in pub["historial"]][-1], "reabrir")

    def test_conflicto_de_version_en_tarea_informa_el_estado_actual(self):
        _, lista = self.http("GET", "/api/tareas?k=1", como="ventas1")
        t = lista[0]
        self.http("POST", f"/api/tareas/{t['id']}/asignar", {"version": t["version"]}, como="ventas2")
        st, e = self.http("POST", f"/api/tareas/{t['id']}/contacto", {"version": t["version"], "nota": "x"}, como="ventas1")
        self.assertEqual((st, e["error"]), (409, "conflicto_version"))
        self.assertEqual(e["detalle"]["estado_actual"], "asignada")
        _, actual = self.http("GET", f"/api/tareas/{t['id']}", como="ventas1")
        self.assertEqual(actual["responsable_id"], "ventas2")
        self.assertIn("actualizada_en", actual)
