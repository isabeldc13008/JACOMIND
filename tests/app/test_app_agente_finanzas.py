"""B07 · agente de consultas (LangGraph) y B09 · panel financiero e informe."""
import unittest
from unittest import mock

from api import agente, consultas, finanzas, llm, operacion, publicacion

from _apoyo_app import CasoBase


class PruebasAgente(CasoBase):
    def preguntar(self, como, q):
        return self.http("POST", "/api/asistente", {"pregunta": q}, como=como)[1]

    def test_herramienta_y_cifras_coinciden_con_consulta_directa(self):
        r = self.preguntar("ventas1", "¿Qué compró DEMO01?")
        self.assertEqual((r["estado"], r["herramienta"]), ("ok", "productos_cliente"))
        _, f = self.http("GET", "/api/cierres/activo/clientes/DEMO01", como="ventas1")
        self.assertEqual({p["producto"]: p["importe_cop"] for p in r["resultado"]}, {p["producto"]: p["importe_cop"] for p in f["productos"]})
        self.assertEqual(r["evidencia"]["corte"], "2026-10-31"); self.assertEqual(r["evidencia"]["unidad"], "COP")

    def test_proveedores_de_un_mes(self):
        r = self.preguntar("fin1", "¿A qué proveedores compramos en agosto de 2026?")
        self.assertEqual(r["herramienta"], "compras_proveedor")
        self.assertEqual([(x["proveedor"], x["importe_cop"]) for x in r["resultado"]], [("Proveedor ficticio 01", 2100000.0)])

    def test_clientes_que_redujeron_compras(self):
        r = self.preguntar("ventas1", "¿Qué clientes redujeron compras entre agosto y septiembre de 2026?")
        with self.db.conexion() as con:
            ventas = publicacion.filas(con, publicacion.cierre_activo(con), "historial_ventas")
        tot = {}
        for v in ventas:
            if v["fecha"][:7] in ("2026-08", "2026-09"):
                tot.setdefault(v["cliente_id"], {"2026-08": 0, "2026-09": 0})[v["fecha"][:7]] += v["importe_cop"]
        esperado = sorted(c for c, t in tot.items() if t["2026-09"] < t["2026-08"])
        self.assertEqual([x["cliente_id"] for x in r["resultado"]], esperado)

    def test_ambigua_pide_aclaracion(self):
        r = self.preguntar("ventas1", "¿Cuántas compras hubo?")
        self.assertEqual(r["estado"], "aclaracion"); self.assertIn("proveedores", r["texto"])
        self.assertEqual(self.preguntar("ventas1", "ventas del periodo")["estado"], "aclaracion")

    def test_periodo_sin_datos_y_cliente_desconocido(self):
        self.assertEqual(self.preguntar("ventas1", "ventas de enero de 2020")["estado"], "sin_datos")
        self.assertEqual(self.preguntar("ventas1", "historial de CLI999")["estado"], "no_encontrado")

    def test_mes_incompleto_se_declara(self):
        r = self.preguntar("fin1", "¿A qué proveedores compramos en mayo de 2026?")
        self.assertEqual(r["estado"], "sin_datos")

    def test_comparacion_con_base_cero(self):
        with self.db.conexion() as con:
            cid = publicacion.cierre_activo(con)
            r = agente.herramienta_reducen(con, publicacion.resolver_cierre(con, cid), {"base": "2026-06", "comparado": "2026-07"})
        for x in r["resultado"] or []:
            if x["base_cop"] == 0:
                self.assertIsNone(x["cambio_pct"])

    def test_permisos_del_rol(self):
        self.assertEqual(self.http("POST", "/api/asistente", {"pregunta": "¿qué compró DEMO01?"}, como="aten1")[1]["estado"], "no_autorizado")
        r = self.preguntar("cli_a", "¿Qué compró DEMO02?")  # el externo nunca accede a cartera
        self.assertEqual(r["herramienta"], "documentos")
        r = self.preguntar("cli_b", "¿Cuál es el estado de mi caso?")
        self.assertEqual(r["herramienta"], "pqrs")
        self.assertTrue(all(x["radicado"] for x in r["resultado"]))

    def test_portal_no_consulta_casos_ajenos(self):
        with self.db.conexion() as con:
            rad_a = con.execute("SELECT radicado FROM pqrs WHERE organizacion_id = 'EMP-A' LIMIT 1").fetchone()[0]
        r = self.preguntar("cli_b", f"estado de {rad_a}")
        self.assertEqual(r["estado"], "no_encontrado")

    def test_asistente_desactivado(self):
        operacion.fijar_bandera(self.db, self.usuario("ops1"), "asistente", False)
        self.assertEqual(self.preguntar("ventas1", "¿qué compró DEMO01?")["estado"], "fuera_de_alcance")
        self.assertEqual(self.http("GET", "/api/tareas", como="ventas1")[0], 200)  # tareas siguen disponibles

    def test_registro_de_herramienta_y_latencia(self):
        self.preguntar("ventas1", "¿qué compró DEMO03?")
        with self.db.conexion() as con:
            r = con.execute("SELECT herramienta, estado, latencia_ms, version_componente FROM asistente_registro ORDER BY id DESC").fetchone()
        self.assertEqual((r[0], r[1]), ("productos_cliente", "ok")); self.assertIsNotNone(r[3])

    def test_redaccion_con_cifras_nuevas_se_descarta(self):
        class Falso:
            def __init__(self, texto): self.texto = texto
            def invoke(self, _):
                return type("R", (), {"content": self.texto, "response_metadata": {"model_name": "falso"}})()
        with mock.patch.object(llm, "modelo_chat", return_value=Falso("DEMO03 compró por 99.999.999 COP")), \
             mock.patch.dict("sys.modules", {"langchain_core.messages": _mensajes_falsos()}):
            texto, version = llm.redactar("DEMO03 compró por 5.040.000,00 COP", "")
            self.assertIn("5.040.000", texto); self.assertIn("descartada", version)
        with mock.patch.object(llm, "modelo_chat", return_value=Falso("En resumen, DEMO03 compró 5.040.000,00 COP.")), \
             mock.patch.dict("sys.modules", {"langchain_core.messages": _mensajes_falsos()}):
            texto, version = llm.redactar("DEMO03 compró por 5.040.000,00 COP", "")
            self.assertTrue(texto.startswith("En resumen")); self.assertEqual(version, "langchain:falso")

    def test_proveedor_caido_responde_con_plantilla(self):
        class Caido:
            def invoke(self, _): raise ConnectionError("sin red")
        with mock.patch.object(llm, "modelo_chat", return_value=Caido()), \
             mock.patch.dict("sys.modules", {"langchain_core.messages": _mensajes_falsos()}):
            texto, version = llm.redactar("Texto base 10", "")
        self.assertEqual(texto, "Texto base 10"); self.assertIn("no disponibles", version)


def _mensajes_falsos():
    import types
    m = types.ModuleType("langchain_core.messages")
    m.SystemMessage = m.HumanMessage = lambda content: content
    return m


class PruebasFinanzas(CasoBase):
    def test_caso_a09_96000(self):
        _, r = self.http("GET", "/api/finanzas/activo/simular?periodo=2026-10&variacion=8", como="fin1")
        self.assertEqual((r["base_cop"], r["simulado_cop"], r["diferencia_cop"]), (1200000.0, 1296000.0, 96000.0))
        self.assertEqual(r["componente_cop_sin_cambio"], 860000.0)
        self.assertEqual(r["total_simulado_cop"] - r["total_base_cop"], 96000.0)

    def test_escenario_cero_y_sin_exposicion(self):
        _, r = self.http("GET", "/api/finanzas/activo/simular?periodo=2026-10&variacion=0", como="fin1")
        self.assertEqual(r["diferencia_cop"], 0.0)
        _, r = self.http("GET", "/api/finanzas/activo/simular?periodo=2026-08&variacion=8", como="fin1")
        self.assertEqual(r["estado"], "sin_exposicion")
        self.assertEqual(self.http("GET", "/api/finanzas/activo/simular?periodo=2026-10&variacion=abc", como="fin1")[0], 400)

    def test_simulacion_preserva_el_cierre(self):
        _, antes = self.http("GET", "/api/cierres/activo/resumen", como="fin1")
        self.http("GET", "/api/finanzas/activo/simular?periodo=2026-10&variacion=8", como="fin1")
        _, despues = self.http("GET", "/api/cierres/activo/resumen", como="fin1")
        self.assertEqual(antes["resumen"], despues["resumen"])

    def test_faltante_distinto_de_cero(self):
        _, p = self.http("GET", "/api/finanzas/activo/panel?serie=compras", como="fin1")
        total = next(f for f in p["familias"] if f["familia"] == "Total")
        mayo = next(s for s in total["historico"] if s["periodo"] == "2026-05")
        self.assertIsNone(mayo["valor_cop"]); self.assertFalse(mayo["completo"])
        soft = next(f for f in p["familias"] if f["familia"] == "Software")
        self.assertIn(0.0, [s["valor_cop"] for s in soft["historico"]])

    def test_informe_reproducible_y_sensible_al_corte(self):
        _, a = self.http("POST", "/api/informes", {"cierre": "activo"}, como="ger1")
        _, b = self.http("POST", "/api/informes", {"cierre": "activo"}, como="ger1")
        self.assertEqual((a["revision"], b["revision"]), (1, 1)); self.assertTrue(b["reutilizado"])
        st, html = self.http("GET", f"/api/informes/{a['cierre_id']}/1", como="fin1")
        self.assertEqual(st, 200); self.assertIn("51.150.000,00", html)
        self.assertEqual(self.http("GET", f"/api/informes/{a['cierre_id']}/1", como="ventas1")[0], 403)
        d = self.publicacion_modificada("sep", lambda t: (t["manifiesto"].update(corte="2026-09-30"), t["agenda"].update(corte="2026-09-30")))
        nuevo = publicacion.publicar_ruta(self.db, d, "ops1")["cierre_id"]
        _, c = self.http("POST", "/api/informes", {"cierre": nuevo}, como="ger1")
        self.assertNotEqual(c["huella"], a["huella"])
        _, html2 = self.http("GET", f"/api/informes/{nuevo}/1", como="ger1")
        self.assertIn("2026-09-30", html2)

    def test_tarjeta_grafica_e_informe_concilian(self):
        with self.db.conexion() as con:
            res = consultas.resumen(con, "activo")
            pan = finanzas.panel(con, "activo")
            tab = consultas.tablero(con, "activo", "gerencia")
            ventas = publicacion.filas(con, publicacion.cierre_activo(con), "historial_ventas")
        total_series = sum(s["valor_cop"] for s in next(f for f in pan["familias"] if f["familia"] == "Total")["historico"])
        en_ventana = sum(v["importe_cop"] for v in ventas if "2026-05" <= v["fecha"][:7] <= "2026-10")
        self.assertAlmostEqual(total_series, en_ventana, places=2)  # el panel cubre mayo–octubre
        self.assertAlmostEqual(sum(v["importe_cop"] for v in ventas), res["resumen"]["ingreso_cop"], places=2)
        self.assertEqual(tab["indicadores"]["ingreso_cop"], res["resumen"]["ingreso_cop"])


if __name__ == "__main__":
    unittest.main()
