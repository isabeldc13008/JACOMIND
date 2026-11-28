"""Orquestador de cuotas de Gemini y textos redactados por IA (sin red ni LangChain).

- Respeta solicitudes por minuto y por día con margen, por clave y modelo, y reparte entre claves.
- La redacción no puede gastar más de su fracción del cupo de los Flash Lite (reservados para el asistente).
- Un 429 bloquea la combinación (minuto o día) y el modelo orquestado pasa al siguiente candidato.
- Los textos con cifras que no están en los datos se descartan; los válidos se guardan y no se vuelven a pedir.
- Permisos: el portal no ve textos internos y el uso de cuota no expone las claves.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from api import cuota_llm, llm, narrativas

from _apoyo_app import CasoBase

CLAVES = {"GEMINI_API_KEY": "clave-falsa-uno", "GEMINI_API_KEY2": "clave-falsa-dos"}


class ConCuotaTemporal(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="cuota-"))
        self.env = mock.patch.dict(os.environ, CLAVES | {"JACOMIND_LLM_CUOTA_DB": str(self.dir / "c.sqlite3")}, clear=False)
        self.env.start()
        for v in ("GOOGLE_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY3", "GEMINI_API_KEY_3", "JACOMIND_GEMINI_MODELO"):
            os.environ.pop(v, None)

    def tearDown(self):
        self.env.stop()


class PruebasCuota(ConCuotaTemporal):
    def test_crea_la_carpeta_de_la_base_de_cuota(self):
        ruta = self.dir / "no-existe" / "anidada" / "c.sqlite3"
        with mock.patch.dict(os.environ, {"JACOMIND_LLM_CUOTA_DB": str(ruta)}):
            estado = cuota_llm.estado()
        self.assertIn("uso", estado)
        self.assertTrue(ruta.exists())

    def test_dos_claves_sin_exponerlas(self):
        huellas = [h for h, _ in cuota_llm.claves()]
        self.assertEqual(len(huellas), 2)
        texto = json.dumps(cuota_llm.estado())
        self.assertNotIn("clave-falsa", texto)

    def test_chat_prioriza_flash_lite_y_reparte_entre_claves(self):
        c = cuota_llm.candidatos("chat")
        self.assertEqual([x[2] for x in c[:4]], ["gemini-3.5-flash-lite"] * 2 + ["gemini-3.1-flash-lite"] * 2)
        h1 = c[0][0]
        self.assertIsNotNone(cuota_llm.reservar(h1, "gemini-3.5-flash-lite", "chat", 1000))
        self.assertNotEqual(cuota_llm.candidatos("chat")[0][0], h1)            # la otra clave, menos usada hoy, va primero

    def test_limite_por_minuto_con_margen(self):
        h = cuota_llm.claves()[0][0]
        efectivo = int(15 * cuota_llm.MARGEN)
        for _ in range(efectivo):
            self.assertIsNotNone(cuota_llm.reservar(h, "gemini-3.5-flash-lite", "chat", 100))
        self.assertIsNone(cuota_llm.reservar(h, "gemini-3.5-flash-lite", "chat", 100))
        self.assertIsNotNone(cuota_llm.reservar(h, "gemini-3.1-flash-lite", "chat", 100))   # otro modelo, otro cupo

    def test_limite_de_tokens_por_minuto_de_gemma(self):
        h = cuota_llm.claves()[0][0]
        self.assertIsNone(cuota_llm.reservar(h, "gemma-4-31b-it", "chat", 15_000))         # 16 000 × 0,9
        self.assertIsNotNone(cuota_llm.reservar(h, "gemma-4-31b-it", "chat", 5_000))

    def _llenar_dia(self, h, modelo, tarea, n):
        con = cuota_llm._con()
        hace = time.time() - 120            # fuera de la ventana de un minuto
        con.executemany("INSERT INTO solicitudes (ts, dia, clave, modelo, tarea, tokens, estado) VALUES (?,?,?,?,?,?, 'ok')",
                        [(hace, cuota_llm.dia(), h, modelo, tarea, 10)] * n)
        con.close()

    def test_limite_diario_y_reserva_del_asistente(self):
        h = cuota_llm.claves()[0][0]
        tope_red = int(500 * cuota_llm.MARGEN * 0.3)
        self._llenar_dia(h, "gemini-3.5-flash-lite", "redaccion", tope_red)
        self.assertIsNone(cuota_llm.reservar(h, "gemini-3.5-flash-lite", "redaccion", 100, 0.3))   # la redacción ya gastó su parte
        self.assertIsNotNone(cuota_llm.reservar(h, "gemini-3.5-flash-lite", "chat", 100, 1.0))     # el asistente conserva el resto
        self._llenar_dia(h, "gemini-3.5-flash-lite", "chat", int(500 * cuota_llm.MARGEN) - tope_red)
        self.assertIsNone(cuota_llm.reservar(h, "gemini-3.5-flash-lite", "chat", 100, 1.0))

    def test_errores_bloquean_lo_justo(self):
        tipo, s = cuota_llm.clasificar_error(Exception("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        self.assertEqual(tipo, "cuota_dia"); self.assertGreater(s, 59)
        tipo, s = cuota_llm.clasificar_error(Exception("429 quota exceeded, retryDelay: 17s"))
        self.assertEqual((tipo, s), ("cuota_minuto", 22.0))
        self.assertEqual(cuota_llm.clasificar_error(Exception("503 UNAVAILABLE high demand"))[0], "saturado")
        h = cuota_llm.claves()[0][0]
        r = cuota_llm.reservar(h, "gemini-3.8-flash", "redaccion", 100)
        cuota_llm.fallo(r, h, "gemini-3.8-flash", Exception("429 per day"))
        self.assertIsNone(cuota_llm.reservar(h, "gemini-3.8-flash", "redaccion", 100))
        uso = {(u["huella"], u["modelo"]): u for u in cuota_llm.estado()["uso"]}
        self.assertEqual(uso[(h, "gemini-3.8-flash")]["motivo_bloqueo"], "cuota_dia")
        self.assertEqual(uso[(h, "gemini-3.8-flash")]["hoy"], 0)                # un 429 no cuenta como solicitud atendida

    def test_dia_del_pacifico(self):
        # 2026-11-25 07:30 UTC = 2026-11-24 23:30 en Los Ángeles (UTC-8)
        ts = 1795591800.0
        self.assertEqual(cuota_llm.dia(ts), "2026-11-24")
        self.assertEqual(cuota_llm.dia(ts + 3600), "2026-11-25")


class Respuesta:
    def __init__(self, texto):
        self.content, self.response_metadata, self.usage_metadata = texto, {}, {"total_tokens": 321}


class ModeloFalso:
    def __init__(self, modelo, falla):
        self.modelo, self.falla = modelo, falla

    def bind_tools(self, _):
        return self

    def invoke(self, _):
        if self.falla:
            raise Exception(self.falla)
        return Respuesta(f"hola desde {self.modelo}")


class PruebasModeloOrquestado(ConCuotaTemporal):
    def test_salta_al_siguiente_ante_429_y_anota_tokens(self):
        fallos = {"gemini-3.5-flash-lite": "429 RESOURCE_EXHAUSTED per minute"}
        with mock.patch.object(llm, "proveedores", return_value=["gemini"]), \
                mock.patch.object(llm, "_gemini", side_effect=lambda m, h, c, mt, t=None: ModeloFalso(m, fallos.get(m))):
            r = llm.ModeloOrquestado("chat").invoke(["pregunta"])
        self.assertEqual(r.content, "hola desde gemini-3.1-flash-lite")
        self.assertEqual(r.response_metadata["model_name"], "gemini-3.1-flash-lite")
        bloqueados = [u for u in cuota_llm.estado()["uso"] if u["bloqueado_hasta"]]
        self.assertEqual({u["modelo"] for u in bloqueados}, {"gemini-3.5-flash-lite"})
        self.assertEqual(len(bloqueados), 2)                                  # probó las dos claves
        con = cuota_llm._con()
        self.assertEqual(con.execute("SELECT tokens FROM solicitudes WHERE estado='ok'").fetchone()[0], 321)
        con.close()

    def test_sin_cupo_lanza_sin_cuota(self):
        with mock.patch.object(llm, "proveedores", return_value=["gemini"]), \
                mock.patch.object(llm, "_gemini", side_effect=lambda m, h, c, mt, t=None: ModeloFalso(m, "429 per day")):
            with self.assertRaises(llm.SinCuota):
                llm.ModeloOrquestado("redaccion").invoke(["x"])

    def test_redaccion_usa_primero_los_mejores_modelos(self):
        usados = []
        with mock.patch.object(llm, "proveedores", return_value=["gemini"]), \
                mock.patch.object(llm, "_gemini", side_effect=lambda m, h, c, mt, t=None: usados.append(m) or ModeloFalso(m, None)):
            llm.ModeloOrquestado("redaccion").invoke(["x"])
        self.assertEqual(usados, ["gemini-3.8-flash"])


HECHOS = {"cliente_id": "DEMO01", "fecha_de_los_datos": "2026-10-31", "ya_tiene": [{"producto": "Soporte", "ultima_compra": "2026-10-08"}],
          "sugerencias_en_prueba": [{"producto_id": "PRO02", "producto": "Respaldo", "orden": 1, "compatibilidad": "por revisar",
                                     "motivos": ["80 de 120 clientes lo compraron"]}]}


class PruebasNarrativas(CasoBase):
    def test_valida_forma_y_cifras(self):
        ok = {"enfoque": "Conviene abrir hablando del soporte que usa desde octubre.", "productos": {"PRO02": "Lo compraron 80 de 120 clientes; compatibilidad por revisar.", "PRO99": "inventado"}}
        v = narrativas.validar("venta_cruzada", HECHOS, ok)
        self.assertEqual(set(v["productos"]), {"PRO02"})                        # productos que no se sugirieron se ignoran
        malo = dict(ok, enfoque="Puede ahorrar 35 % al año si renueva hoy mismo.")
        self.assertIsNone(narrativas.validar("venta_cruzada", HECHOS, malo))    # cifra que no está en los datos
        self.assertIsNone(narrativas.validar("venta_cruzada", HECHOS, {"productos": {}}))

    def test_guarda_y_no_vuelve_a_pedir(self):
        llamadas = []

        def pedir(tipo, lote):
            llamadas.append([c for c, _, _ in lote])
            return {"DEMO01": {"enfoque": "Conviene abrir hablando del soporte que ya usa.", "productos": {"PRO02": "Podría complementar lo que tiene."}}}, "gemini-3.8-flash"

        with mock.patch.object(narrativas, "hechos", side_effect=lambda con, t, c: HECHOS if c == "DEMO01" else None), \
                mock.patch.object(narrativas, "_pedir", side_effect=pedir), \
                mock.patch.object(llm, "disponible", return_value=True):
            self.assertTrue(narrativas._tomar("venta_cruzada"))
            try:
                narrativas._redactar_lote(self.db, "venta_cruzada", "DEMO01")
            finally:
                narrativas._soltar("venta_cruzada")
            r = narrativas.obtener(self.db, "venta_cruzada", "DEMO01")
            self.assertEqual(r["estado"], "ok")
            self.assertEqual(r["nombre_modelo"], "Gemini 3.8 Flash")
            narrativas.obtener(self.db, "venta_cruzada", "DEMO01")
        self.assertEqual(len(llamadas), 1)

    def test_sin_ia_conserva_el_texto_original(self):
        with mock.patch.object(narrativas, "hechos", return_value=HECHOS), mock.patch.object(llm, "disponible", return_value=False):
            self.assertEqual(narrativas.obtener(self.db, "venta_cruzada", "DEMO01")["estado"], "desactivada")

    def test_permisos(self):
        with mock.patch.object(llm, "disponible", return_value=False):
            self.assertEqual(self.http("GET", "/api/narrativas/ficha/DEMO01", como="cli_a")[0], 403)
            self.assertEqual(self.http("GET", "/api/narrativas/ficha/DEMO01", como="ventas1")[0], 200)
        self.assertEqual(self.http("GET", "/api/llm/cuota", como="ventas1")[0], 403)
        st, d = self.http("GET", "/api/llm/cuota", como="ops1")
        self.assertEqual(st, 200)
        self.assertIn("uso", d)


if __name__ == "__main__":
    unittest.main()
