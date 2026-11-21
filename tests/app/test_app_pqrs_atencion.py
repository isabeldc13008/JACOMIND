"""B04 · PQRS y B10 · atención asistida (clasificación, borradores, aprobación)."""
import os
import threading
import unittest

from api import atencion, documentos, pqrs
from api.base import ErrorApi

from _apoyo_app import CasoBase


class PruebasPqrs(CasoBase):
    def crear(self, como="cli_a", clave=None, asunto="Doble cobro", desc="Nos cobraron dos veces la factura de octubre"):
        return self.http("POST", "/api/pqrs", {"asunto": asunto, "descripcion": desc}, como=como,
                         cabeceras={"Idempotency-Key": clave} if clave else None)

    def test_doble_envio_mismo_radicado(self):
        st1, a = self.crear(clave="form-1")
        st2, b = self.crear(clave="form-1")
        self.assertEqual((st1, st2), (201, 201))
        self.assertEqual(a["radicado"], b["radicado"]); self.assertTrue(b["repetida"])

    def test_envios_simultaneos_con_misma_clave(self):
        rads = []
        hs = [threading.Thread(target=lambda: rads.append(pqrs.crear(self.db, self.usuario("cli_b"), "A", "Solicito información", "k-sim")["radicado"])) for _ in range(3)]
        [h.start() for h in hs]; [h.join() for h in hs]
        self.assertEqual(len(set(rads)), 1)

    def test_edicion_concurrente_conflicto(self):
        _, c = self.crear()
        _, d = self.http("GET", f"/api/pqrs/{c['radicado']}", como="aten1")
        st1, _ = self.http("POST", f"/api/pqrs/{c['radicado']}/categorizar", {"version": d["version"], "categoria": "reclamo"}, como="aten1")
        st2, e = self.http("POST", f"/api/pqrs/{c['radicado']}/asignar", {"version": d["version"]}, como="aten1")
        self.assertEqual((st1, st2), (200, 409)); self.assertEqual(e["error"], "conflicto_version")

    def test_transicion_invalida_y_reapertura_con_historial(self):
        _, c = self.crear()
        rad = c["radicado"]
        _, d = self.http("GET", f"/api/pqrs/{rad}", como="aten1")
        st, e = self.http("POST", f"/api/pqrs/{rad}/cerrar", {"version": d["version"]}, como="aten1")
        self.assertEqual((st, e["error"]), (409, "transicion_invalida"))
        _, d = self.http("POST", f"/api/pqrs/{rad}/responder", {"version": d["version"], "respuesta": "Revisamos y anulamos el cobro duplicado."}, como="aten1")
        _, d = self.http("POST", f"/api/pqrs/{rad}/cerrar", {"version": d["version"]}, como="aten1")
        _, d = self.http("POST", f"/api/pqrs/{rad}/reabrir", {"version": d["version"], "nota": "El cliente aporta otra factura"}, como="aten1")
        self.assertEqual(d["estado"], "en_gestion")
        self.assertEqual([b["a_estado"] for b in d["bitacora"]], ["recibido", "en_gestion", "respondido", "cerrado", "en_gestion"])

    def test_aislamiento_entre_empresas(self):
        _, c = self.crear(como="cli_a")
        st, e = self.http("GET", f"/api/pqrs/{c['radicado']}", como="cli_b")
        st_inexistente, e2 = self.http("GET", "/api/pqrs/PQRS-20990101-99999", como="cli_b")
        self.assertEqual((st, st_inexistente), (404, 404))
        self.assertEqual(e["mensaje"], e2["mensaje"])  # no se puede inferir existencia
        _, lista = self.http("GET", "/api/pqrs", como="cli_b")
        self.assertNotIn(c["radicado"], [x["radicado"] for x in lista])
        self.assertEqual(self.http("POST", f"/api/pqrs/{c['radicado']}/cerrar", {"version": 1}, como="cli_a")[0], 403)
        self.assertEqual(self.http("GET", "/api/exportes/pqrs", como="cli_a")[0], 403)

    def test_cliente_no_ve_datos_internos(self):
        _, c = self.crear()
        _, d = self.http("GET", f"/api/pqrs/{c['radicado']}", como="cli_a")
        for k in ("categoria_propuesta", "sugerencias", "borradores", "bitacora", "responsable_id"):
            self.assertNotIn(k, d)

    def test_indicadores_concilian_con_estados(self):
        _, ind = self.http("GET", "/api/pqrs-indicadores", como="ger1")
        _, lista = self.http("GET", "/api/pqrs", como="aten1")
        self.assertEqual(sum(ind["por_estado"].values()), len(lista))
        self.assertEqual(ind["pendientes"], sum(1 for x in lista if x["estado"] in ("recibido", "en_gestion")))

    def test_exportacion_anonimizada_solo_autorizada(self):
        _, c = self.crear(desc="Mi correo es ana@example.com y mi teléfono 300 123 4567; cobro doble")
        _, d = self.http("GET", f"/api/pqrs/{c['radicado']}", como="aten1")
        _, d = self.http("POST", f"/api/pqrs/{c['radicado']}/categorizar", {"version": d["version"], "categoria": "reclamo"}, como="aten1")
        _, ex = self.http("GET", "/api/exportes/pqrs", como="aten1")
        self.assertEqual(ex["eventos"], [])
        self.http("POST", f"/api/pqrs/{c['radicado']}/autorizar_uso", {"version": d["version"], "autorizado": True}, como="aten1")
        _, ex = self.http("GET", "/api/exportes/pqrs", como="aten1")
        texto = ex["eventos"][0]["texto"]
        self.assertNotIn("ana@example.com", texto); self.assertNotIn("4567", texto)
        self.assertEqual(ex["eventos"][0]["categoria_revisada"], "reclamo")


class PruebasAtencion(CasoBase):
    def test_clasificador_simulado(self):
        self.assertFalse(atencion._simulado("Nos cobraron dos veces la factura, solicito reembolso por el cobro")["revisar"])
        self.assertTrue(atencion._simulado("")["revisar"])
        self.assertTrue(atencion._simulado("Hola, escribo por lo del mes pasado")["revisar"])
        self.assertTrue(atencion._simulado("Solicito información y sugiero mejorar")["revisar"])

    def test_cualquier_clasificador_activo_cumple_c4(self):
        from contratos.esquema import validar
        for texto in ("Solicito información del contrato", "Tengo una queja y sugiero mejorar", ""):
            r = atencion.clasificar(texto)
            self.assertEqual(validar(r, atencion.ESQUEMA_CLASIF), [], r)
            if r["categoria"] is None:
                self.assertTrue(r["revisar"])

    def test_forma_de_pipeline_pqrs_se_normaliza(self):
        r = atencion._normalizar_salida_a({"categoria": "revision_manual", "confianza": 0.0, "motivo": "múltiples intenciones", "version": "reglas-v1"})
        self.assertEqual((r["categoria"], r["revisar"]), (None, True))

    def test_clasificador_de_a_fuera_de_contrato_cae_a_revision(self):
        import sys, types
        m = types.ModuleType("clasif_falso")
        m.clasificar = lambda t: {"categoria": "otra", "confianza": 2}
        sys.modules["clasif_falso"] = m
        anterior = atencion.CLASIFICADOR_A
        atencion.CLASIFICADOR_A = "clasif_falso:clasificar"
        try:
            r = atencion.clasificar("Nos cobraron dos veces")
            self.assertTrue(r["revisar"]); self.assertIn("fuera de contrato", r["motivo"])
            m.clasificar = lambda t: {"categoria": "reclamo", "confianza": 0.95, "version": "A10-v1", "revisar": False}
            self.assertEqual(atencion.clasificar("x")["version"], "A10-v1")
        finally:
            atencion.CLASIFICADOR_A = anterior

    def test_baja_confianza_queda_en_bandeja_y_correccion_humana_prevalece(self):
        _, c = self.http("POST", "/api/pqrs", {"asunto": "Comentario", "descripcion": "Hola, escribo por lo del mes pasado"}, como="cli_b")
        _, b = self.http("GET", "/api/atencion/bandeja", como="aten1")
        self.assertIn(c["radicado"], [x["radicado"] for x in b["casos_sin_clasificar"]])
        _, d = self.http("GET", f"/api/pqrs/{c['radicado']}", como="aten1")
        self.http("POST", f"/api/pqrs/{c['radicado']}/categorizar", {"version": d["version"], "categoria": "queja"}, como="aten1")
        self.http("POST", f"/api/pqrs/{c['radicado']}/reclasificar", {}, como="aten1")
        _, d = self.http("GET", f"/api/pqrs/{c['radicado']}", como="aten1")
        self.assertEqual(d["categoria_revisada"], "queja"); self.assertEqual(len(d["sugerencias"]), 2)

    def _caso_beneficio(self):
        _, c = self.http("POST", "/api/pqrs", {"asunto": "Descuento por renovación", "descripcion": "Quisiera saber el descuento por renovación anticipada del contrato recurrente"}, como="cli_b")
        return c["radicado"]

    def test_borrador_con_fuentes_y_doble_aprobacion(self):
        rad = self._caso_beneficio()
        st, b = self.http("POST", f"/api/pqrs/{rad}/borradores", {}, como="aten1")
        self.assertEqual((st, b["estado"]), (201, "pendiente"))
        self.assertEqual(b["fuentes"][0]["documento_id"], "POL-BENEF"); self.assertEqual(b["fuentes"][0]["version"], 2)
        _, cli = self.http("GET", f"/api/pqrs/{rad}", como="cli_b")
        self.assertIsNone(cli["respuesta_publicada"])  # borrador pendiente permanece interno
        r1 = self.http("POST", f"/api/borradores/{b['id']}/aprobar", {}, como="aten1")
        r2 = self.http("POST", f"/api/borradores/{b['id']}/aprobar", {}, como="aten1")
        self.assertEqual((r1[0], r2[0]), (200, 200)); self.assertTrue(r2[1]["repetida"])
        _, d = self.http("GET", f"/api/pqrs/{rad}", como="aten1")
        self.assertEqual(sum(1 for x in d["bitacora"] if x["accion"] == "publicar_respuesta"), 1)
        _, cli = self.http("GET", f"/api/pqrs/{rad}", como="cli_b")
        self.assertIn("8 %", cli["respuesta_publicada"]); self.assertEqual(cli["estado"], "respondido")

    def test_politica_retirada_marca_borrador(self):
        rad = self._caso_beneficio()
        _, b = self.http("POST", f"/api/pqrs/{rad}/borradores", {}, como="aten1")
        documentos.retirar(self.db, "aten1", "POL-BENEF")
        st, e = self.http("POST", f"/api/borradores/{b['id']}/aprobar", {}, como="aten1")
        self.assertEqual(st, 409)
        _, d = self.http("GET", f"/api/pqrs/{rad}", como="aten1")
        self.assertEqual(d["borradores"][0]["estado"], "requiere_revision")
        self.assertIsNone(d["respuesta_publicada"])

    def test_caso_modificado_marca_borrador(self):
        rad = self._caso_beneficio()
        _, b = self.http("POST", f"/api/pqrs/{rad}/borradores", {}, como="aten1")
        _, d = self.http("GET", f"/api/pqrs/{rad}", como="aten1")
        self.http("POST", f"/api/pqrs/{rad}/categorizar", {"version": d["version"], "categoria": "peticion"}, como="aten1")
        st, e = self.http("POST", f"/api/borradores/{b['id']}/aprobar", {}, como="aten1")
        self.assertEqual((st, e["error"]), (409, "borrador_desactualizado"))

    def test_sin_evidencia_solicita_revision(self):
        _, c = self.http("POST", "/api/pqrs", {"asunto": "Pregunta", "descripcion": "¿Venden paneles solares para barcos?"}, como="cli_a")
        _, b = self.http("POST", f"/api/pqrs/{c['radicado']}/borradores", {}, como="aten1")
        self.assertEqual(b["estado"], "requiere_revision"); self.assertEqual(b["fuentes"], [])
        st, _ = self.http("POST", f"/api/borradores/{b['id']}/aprobar", {"confirmar_revision": True}, como="aten1")
        self.assertEqual(st, 409)  # el texto aún contiene la marca de revisión

    def test_borrador_respeta_documentos_de_la_empresa_del_caso(self):
        _, c = self.http("POST", "/api/pqrs", {"asunto": "Garantía", "descripcion": "¿La garantía extendida cubre el reemplazo de equipos de monitoreo?"}, como="cli_a")
        _, b = self.http("POST", f"/api/pqrs/{c['radicado']}/borradores", {}, como="aten1")
        self.assertNotIn("POL-GARANTIA-B", [f["documento_id"] for f in b["fuentes"]])


if __name__ == "__main__":
    unittest.main()
