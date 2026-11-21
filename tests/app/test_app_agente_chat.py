"""Asistente conversacional con LangGraph: herramientas por perfil, citas, memoria y respaldo (sin red).

Un modelo simulado sustituye a Gemini/Anthropic: llama herramientas según un guion y responde con texto.
Se omite si LangGraph no está instalado (las pruebas base no requieren dependencias).
"""
import importlib.util
import unittest
from unittest import mock

from api import agente, agente_chat, llm

from _apoyo_app import CasoBase

HAY_LANGGRAPH = importlib.util.find_spec("langgraph") is not None


class ModeloSimulado:
    """Imita un modelo de chat con tool calling: cada turno sigue el guion recibido."""

    def __init__(self, guion):
        self.guion, self.vistos, self.herramientas = list(guion), [], []

    def bind_tools(self, herramientas):
        self.herramientas = [h.name for h in herramientas]
        return self

    def invoke(self, mensajes):
        from langchain_core.messages import AIMessage
        self.vistos.append(mensajes)
        paso = self.guion.pop(0)
        if isinstance(paso, Exception):
            raise paso
        if isinstance(paso, list):
            return AIMessage(content="", tool_calls=[{"name": n, "args": a, "id": f"c{i}"} for i, (n, a) in enumerate(paso)])
        return AIMessage(content=paso, response_metadata={"model_name": "simulado"})


@unittest.skipUnless(HAY_LANGGRAPH, "LangGraph no instalado")
class PruebasAgenteConversacional(CasoBase):
    def preguntar(self, ident, pregunta, guion, conversacion="c1"):
        modelo = ModeloSimulado(guion)
        with mock.patch.object(agente_chat, "disponible", return_value=True), \
                mock.patch.object(llm, "modelo_con_herramientas", side_effect=lambda hs: modelo.bind_tools(hs)):
            with self.db.conexion() as con:
                r = agente.preguntar(con, self.usuario(ident), pregunta, "activo", conversacion)
        return r, modelo

    def test_herramientas_segun_perfil(self):
        _, m = self.preguntar("cli_a", "hola", ["Hola"])
        self.assertEqual(set(m.herramientas), {"mis_solicitudes", "mis_beneficios", "buscar_politicas"})
        _, m = self.preguntar("fin1", "hola", ["Hola"])
        self.assertIn("simular_tipo_de_cambio", m.herramientas)
        self.assertNotIn("ficha_cliente", m.herramientas)  # Finanzas no ve la cartera
        _, m = self.preguntar("ventas1", "hola", ["Hola"])
        self.assertIn("ficha_cliente", m.herramientas); self.assertNotIn("simular_tipo_de_cambio", m.herramientas)

    def test_respuesta_citada_con_fuentes_y_pasos(self):
        r, _ = self.preguntar("ventas1", "¿Qué compró DEMO02?",
                              [[("ficha_cliente", {"cliente_id": "DEMO02"})], "DEMO02 compró Monitoreo de red por 7,80 millones de COP [1]. Ver también [7]."])
        self.assertEqual(r["modo"], "agente")
        self.assertEqual(r["pasos"], [{"herramienta": "ficha_cliente", "argumentos": {"cliente_id": "DEMO02"}}])
        self.assertEqual(r["fuentes"][0]["titulo"], "Ficha de DEMO02"); self.assertTrue(r["fuentes"][0]["citada"])
        self.assertEqual(r["fuentes"][0]["enlace"], "#/clientes/DEMO02")
        self.assertNotIn("[7]", r["texto"])          # cita inexistente eliminada
        self.assertEqual(r["cifras_sin_respaldo"], [])

    def test_cifra_inventada_se_informa(self):
        r, _ = self.preguntar("ventas1", "¿Qué compró DEMO02?", [[("ficha_cliente", {"cliente_id": "DEMO02"})], "Compró por 99.999.999 COP [1]."])
        self.assertEqual(r["cifras_sin_respaldo"], ["99.999.999"])

    def test_memoria_por_conversacion_y_aislada_entre_usuarios(self):
        self.preguntar("ventas1", "Recuerda DEMO03", ["Anotado."], conversacion="mem")
        _, m = self.preguntar("ventas1", "¿Qué cliente te dije?", ["DEMO03."], conversacion="mem")
        self.assertIn("Recuerda DEMO03", " ".join(str(x.content) for x in m.vistos[0]))
        _, otro = self.preguntar("ventas2", "¿Qué cliente te dije?", ["No lo sé."], conversacion="mem")
        self.assertNotIn("Recuerda DEMO03", " ".join(str(x.content) for x in otro.vistos[0]))

    def test_empresa_solo_ve_sus_solicitudes(self):
        r, _ = self.preguntar("cli_b", "Mis solicitudes", [[("mis_solicitudes", {})], "Tienes solicitudes [1]."])
        with self.db.conexion() as con:
            ajenos = [x[0] for x in con.execute("SELECT radicado FROM pqrs WHERE organizacion_id <> 'EMP-B'")]
        self.assertTrue(ajenos)
        self.assertFalse(any(a in r["texto"] for a in ajenos))

    def test_si_el_modelo_falla_responde_en_modo_basico(self):
        r, _ = self.preguntar("ventas1", "¿Qué significa frío?", [RuntimeError("503")])
        self.assertEqual(r["modo"], "basico")
        self.assertIn("modo básico", r["aviso"])
        self.assertIn("90 días", r["texto"])

    def test_documentacion_del_proyecto_es_citable(self):
        from api import conocimiento
        res = conocimiento.buscar("probabilidad de compra a 30 días")
        self.assertTrue(res); self.assertTrue(res[0]["archivo"].endswith(".md"))


class PruebasSinModelo(CasoBase):
    def test_sin_modelo_se_usa_el_grafo_de_reglas(self):
        with mock.patch.object(agente_chat, "disponible", return_value=False):
            _, r = self.http("POST", "/api/asistente", {"pregunta": "¿Qué significa frío?"}, como="ventas1")
        self.assertEqual(r["modo"], "basico")
        _, cap = self.http("GET", "/api/asistente/capacidades", como="ventas1")
        self.assertIn(cap["modo"], ("agente", "basico"))
