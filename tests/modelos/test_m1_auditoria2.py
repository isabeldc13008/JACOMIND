"""Regresión de los hallazgos de la segunda auditoría M1 (2026-11-23).

1. Publicación parcial del cierre. 2. Excepción de la referencia histórica. 3. Identidad de selección.
4. Cobertura al reutilizar un lote. 5. Evaluación rechazada que reescribía métricas.
Las coberturas hipotéticas (hasta 2026-11-30) son fixtures, no datos comerciales.
"""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest import mock

from tests.modelos.test_m1_correcciones import _ConPuntuaciones, _artefacto, _datos, _escribir_csv, _leer_csv

RAIZ = Path(__file__).resolve().parents[2]
HAY_SKLEARN = importlib.util.find_spec("sklearn") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _huellas(d: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(d).glob("*.json"))}


# 1. Publicación del cierre ------------------------------------------------------------------
@unittest.skipIf(_paquete() is None, "Paquete de datos no disponible")
class PublicacionCierreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.cli import main
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1-pub-"))
        cls.registro = cls.tmp / "registro"
        with contextlib.redirect_stdout(io.StringIO()):
            assert main(["preparar", "--datos", str(_paquete()), "--salida", str(cls.tmp / "a01")]) == 0
            assert main(["inicializar-referencia", "--datos", str(cls.tmp / "a01"), "--registro", str(cls.registro)]) == 0

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        from pipeline.generar import generar
        self.salida = Path(tempfile.mkdtemp(prefix="pub-", dir=self.tmp))
        generar(_paquete(), "2026-10-31", self.salida, registro=self.registro)  # publicación anterior (con modelo)
        self.antes = _huellas(self.salida)

    def nueva(self):
        """Publicación distinta del mismo corte (sin modelo) para distinguir lo nuevo de lo anterior."""
        from pipeline.generar import generar
        return generar(_paquete(), "2026-10-31", self.salida, registro=self.tmp / "vacio")

    def assert_anterior_completa(self):
        from contratos.validar import validar_publicacion
        self.assertEqual(_huellas(self.salida), self.antes)
        r, datos = validar_publicacion(self.salida)
        self.assertTrue(r.valido, r.errores)
        self.assertEqual(datos["agenda"]["modelo"]["version"], "A04-logistica-reglas-v1")
        self.assertEqual([p.name for p in self.salida.iterdir() if p.name.startswith(".")], [])

    def fallar_en(self, n_llamada, objetivo=None):
        real = os.replace
        llamadas = {"n": 0}

        def falso(src, dst):
            if objetivo is None or Path(dst).name == objetivo or (objetivo == "*" and Path(dst).suffix == ".json"):
                if Path(dst).parent == self.salida and Path(dst).name != ".publicacion_en_curso.json":
                    llamadas["n"] += 1
                    if llamadas["n"] == n_llamada:
                        raise PermissionError("fallo simulado al reemplazar")
            return real(src, dst)
        return mock.patch("os.replace", side_effect=falso)

    def test_fallo_durante_la_serializacion(self):
        import pipeline.generar as g
        real = g._escribir
        cuenta = {"n": 0}

        def falso(ruta, datos):
            cuenta["n"] += 1
            if cuenta["n"] == 2:
                raise OSError("disco lleno (simulado)")
            return real(ruta, datos)
        with mock.patch.object(g, "_escribir", side_effect=falso), self.assertRaises(OSError):
            self.nueva()
        self.assert_anterior_completa()

    def test_fallo_al_sustituir_el_segundo_archivo(self):
        with self.fallar_en(2, "*"), self.assertRaises(PermissionError):
            self.nueva()
        self.assert_anterior_completa()

    def test_fallo_antes_de_activar_el_manifiesto(self):
        with self.fallar_en(1, "manifiesto.json"), self.assertRaises(PermissionError):
            self.nueva()
        self.assert_anterior_completa()

    def test_interrupcion_sin_recuperacion_se_detecta_y_el_reintento_la_repara(self):
        import pipeline.generar as g
        from contratos.validar import validar_publicacion
        # El proceso "muere" tras sustituir dos archivos: la recuperación en línea tampoco se ejecuta.
        with self.fallar_en(3, "*"), mock.patch.object(g, "recuperar_publicacion", side_effect=[None, RuntimeError("proceso detenido")]), \
                self.assertRaises(RuntimeError):
            self.nueva()
        self.assertTrue((self.salida / ".publicacion_en_curso.json").exists())
        r, _ = validar_publicacion(self.salida)
        self.assertFalse(r.valido)
        self.assertIn("interrumpida", r.errores[0])
        # Recuperación explícita: vuelve a la publicación anterior completa.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(g.main(["--recuperar", "--salida", str(self.salida)]), 0)
        self.assert_anterior_completa()
        # Reintento después del fallo: publica completa la versión nueva.
        m = self.nueva()
        r, datos = validar_publicacion(self.salida)
        self.assertTrue(r.valido, r.errores)
        self.assertIsNone(datos["agenda"]["modelo"])
        self.assertTrue(all("sha256" in t for t in m["tablas"].values()))

    def test_reintento_tras_crash_recupera_y_publica(self):
        import pipeline.generar as g
        from contratos.validar import validar_publicacion
        with self.fallar_en(2, "*"), mock.patch.object(g, "recuperar_publicacion", side_effect=[None, RuntimeError("detenido")]), \
                self.assertRaises(RuntimeError):
            self.nueva()
        self.nueva()  # el generador recupera el diario antes de publicar
        r, datos = validar_publicacion(self.salida)
        self.assertTrue(r.valido, r.errores)
        self.assertEqual(datos["agenda"]["corte"], datos["manifiesto"]["corte"])
        self.assertEqual([p.name for p in self.salida.iterdir() if p.name.startswith(".")], [])

    def test_contenido_que_no_coincide_con_el_manifiesto_se_rechaza(self):
        from contratos.validar import validar_publicacion
        agenda = json.loads((self.salida / "agenda.json").read_text(encoding="utf-8"))
        agenda["clientes"][0]["prob_compra_30d"] = 0.99
        (self.salida / "agenda.json").write_text(json.dumps(agenda), encoding="utf-8")
        r, _ = validar_publicacion(self.salida)
        self.assertFalse(r.valido)
        self.assertTrue(any("huella del manifiesto" in e for e in r.errores))


# 2. Excepción de la referencia histórica ----------------------------------------------------
class ReferenciaHistoricaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-ref-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bytes_reg(self):
        p = self.tmp / "compra_30d" / "registro.json"
        return p.read_bytes() if p.exists() else None

    def test_v1_legitima_sigue_funcionando(self):
        from modelos import registro as R
        from modelos.inferencia import cargar_artefacto
        v1_dir = RAIZ / "var" / "modelos" / "compra_30d" / "v1"
        if not v1_dir.exists():
            self.skipTest("Sin registro local")
        art = cargar_artefacto(v1_dir)  # solo lectura
        self.assertIsNotNone(R.referencia_historica_verificada(art))
        decision = json.loads((v1_dir / "decision.json").read_text(encoding="utf-8"))
        R.promover(self.tmp, "compra_30d", "v1", art, decision, {}, "operativo")
        self.assertEqual(R.artefacto_registrado(self.tmp, "compra_30d", "operativo")[0].version, "A04-logistica-reglas-v1")
        real = R.artefacto_registrado(RAIZ / "var" / "modelos", "compra_30d", "operativo")[1]
        reg = R.leer_registro(RAIZ / "var" / "modelos", "compra_30d")
        # v1 operativa, o v2 en modo demostración autorizado (en ese caso v1 sigue recuperable por revertir).
        self.assertTrue(real["version"] == "v1" or (real["decision"] == "demostracion" and R.modo_demostracion(reg)), real)

    def test_candidato_con_texto_de_referencia_es_rechazado(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        cand = desde_dict(_artefacto(version="compra_30d-m1-a-c10-b8799da6"))
        engano = {"decision": "referencia_vigente", "estado_maximo": "operativo", "artefacto_huella": cand.huella, "origen_datos": "sintetico"}
        with self.assertRaisesRegex(R.RegistroError, "verificados por huella"):
            R.promover(self.tmp, "compra_30d", "v2", cand, engano, {}, "operativo")
        self.assertIsNone(self.bytes_reg())
        self.assertFalse((self.tmp / "compra_30d" / "v2").exists())

    def test_cambiar_nombre_o_etiquetas_no_concede_autorizacion(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        disfrazado = desde_dict(_artefacto(version="A04-logistica-reglas-v1"))  # mismo nombre, otra huella
        for decision in ({"decision": "referencia_vigente", "estado_maximo": "operativo", "artefacto_huella": disfrazado.huella,
                          "origen_datos": "sintetico", "controles_reproducidos": True, "procedimiento": "inicializar-referencia"},):
            with self.assertRaises(R.RegistroError):
                R.promover(self.tmp, "compra_30d", "v1", disfrazado, decision, {}, "operativo")

    def test_autorizacion_de_otra_huella_y_rechazo_sin_cambios(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        a, b = desde_dict(_artefacto(version="a")), desde_dict(_artefacto(version="b", intercepto=0.3))
        ok = {"decision": "favorable", "estado_maximo": "operativo", "artefacto_huella": a.huella,
              "origen_datos": "fixture_empresarial", "aprobado_por": "fixture"}
        R.promover(self.tmp, "compra_30d", "v1", a, ok, {}, "operativo")
        R.promover(self.tmp, "compra_30d", "v2", b, dict(ok, artefacto_huella=b.huella, estado_maximo="sombra"), {}, "sombra")
        antes = self.bytes_reg()
        for d in (dict(ok, artefacto_huella=a.huella), dict(ok, artefacto_huella=b.huella, decision="referencia_vigente",
                                                             origen_datos="sintetico", aprobado_por=None)):
            with self.assertRaises(R.RegistroError):
                R.promover(self.tmp, "compra_30d", "v2", b, d, {}, "operativo")
        self.assertEqual(self.bytes_reg(), antes)
        # La promoción y reversión legítimas siguen funcionando.
        R.promover(self.tmp, "compra_30d", "v2", b, dict(ok, artefacto_huella=b.huella), {}, "operativo")
        self.assertEqual(R.revertir(self.tmp, "compra_30d", "operativo")["operativo"]["version"], "v1")

    def test_registro_editado_a_mano_no_activa_el_candidato(self):
        from modelos import registro as R
        from modelos.inferencia import desde_dict
        cand = desde_dict(_artefacto(version="cand"))
        R.promover(self.tmp, "compra_30d", "v2", cand, {"decision": "inconcluso", "estado_maximo": "sombra",
                                                         "artefacto_huella": cand.huella, "origen_datos": "sintetico"}, {}, "sombra")
        base = self.tmp / "compra_30d"
        (base / "v2" / "decision.json").write_text(json.dumps({"decision": "referencia_vigente", "estado_maximo": "operativo",
                                                                "artefacto_huella": cand.huella, "origen_datos": "sintetico"}), encoding="utf-8")
        reg = json.loads((base / "registro.json").read_text(encoding="utf-8"))
        reg["operativo"], reg["sombra"] = dict(reg["sombra"]), None
        (base / "registro.json").write_text(json.dumps(reg), encoding="utf-8")
        with self.assertRaisesRegex(R.ModeloNoDisponible, "no es válida"):
            R.artefacto_registrado(self.tmp, "compra_30d", "operativo")


# 3. Identidad de selección ------------------------------------------------------------------
class IdentidadSeleccionTests(_ConPuntuaciones):
    def puntuar(self, nombre, art=None, datos=None):
        self.compra.puntuar(art or self.sb, datos or self.datos, self.corte, self.tmp / nombre)
        return self.tmp / nombre

    def test_otra_revision_de_datos_con_los_mismos_modelos_no_colisiona(self):
        from modelos.compra import PilotoError
        r1 = self.comparar(self.datos)
        humano = self.registrar_contacto()
        corregido = replace(self.datos, huella_datos="lote-corregido")
        op2 = self.tmp / "op-rev"
        self.compra.puntuar(self.op, corregido, self.corte, op2)
        sb2 = self.puntuar("sb-rev", datos=corregido)
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        with self.assertRaisesRegex(PilotoError, "nueva-seleccion"):
            self.compra.comparar(op2, sb2, self.salida, corregido, 10)
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)
        r2 = self.compra.comparar(op2, sb2, self.salida, corregido, 10, nueva_seleccion=True)
        self.assertNotEqual(r1["piloto"]["seleccion_id"], r2["piloto"]["seleccion_id"])
        self.assertEqual(len(r2["piloto"]["selecciones_del_corte"]), 2)
        self.assertEqual({k: self.fila(seleccion=r1["piloto"]["seleccion_id"])[k] for k in humano}, humano)
        self.assertEqual(self.fila(seleccion=r2["piloto"]["seleccion_id"])["contacto_realizado"], "")

    def test_cambio_de_cohorte_o_de_modelo_cambia_la_identidad(self):
        from modelos.compra import identidad_seleccion
        from modelos.inferencia import desde_dict
        base = self.comparar(self.datos)["piloto"]["seleccion_id"]
        r_o = json.loads((self.tmp / "op" / "resumen.json").read_text(encoding="utf-8"))
        r_s = json.loads((self.tmp / "sb" / "resumen.json").read_text(encoding="utf-8"))
        cohorte = [f"C{i:02d}" for i in range(1, 13)]
        self.assertEqual(identidad_seleccion("2026-10-31", r_o, r_s, cohorte, 10, [])[0], base)
        self.assertNotEqual(identidad_seleccion("2026-10-31", r_o, r_s, cohorte[:-1], 10, [])[0], base)  # cohorte
        self.assertNotEqual(identidad_seleccion("2026-10-31", r_o, r_s, cohorte, 20, [])[0], base)  # cupo
        self.assertNotEqual(identidad_seleccion("2026-10-31", r_o, r_s, cohorte, 10, ["interseccion"])[0], base)  # reconciliación
        otro = self.puntuar("sb-otro", art=desde_dict(_artefacto(version="otro", pesos=[0.9, 0.1])))
        r = self.compra.comparar(self.tmp / "op", otro, self.salida, self.datos, 10, nueva_seleccion=True)
        self.assertNotEqual(r["piloto"]["seleccion_id"], base)  # modelo

    def test_repeticion_exacta_es_idempotente(self):
        r1 = self.comparar(self.datos)
        antes = (self.salida / "piloto_registro.csv").read_bytes()
        r2 = self.comparar(self.datos)
        self.assertEqual(r1["piloto"]["seleccion_id"], r2["piloto"]["seleccion_id"])
        self.assertEqual((self.salida / "piloto_registro.csv").read_bytes(), antes)

    def test_lote_posterior_actualiza_resultados_sin_nueva_seleccion_aunque_haya_otras(self):
        from modelos.inferencia import desde_dict
        r1 = self.comparar(self.datos)
        humano = self.registrar_contacto()
        otro = self.puntuar("sb-otro", art=desde_dict(_artefacto(version="otro", pesos=[0.9, 0.1])))
        self.compra.comparar(self.tmp / "op", otro, self.salida, self.datos, 10, nueva_seleccion=True)
        r3 = self.comparar(self.maduro)  # selección original + lote posterior: sin --nueva-seleccion
        self.assertEqual(r3["piloto"]["seleccion_id"], r1["piloto"]["seleccion_id"])
        self.assertEqual(r3["estado_etiquetas"], "madura")
        for f in _leer_csv(self.salida / "piloto_registro.csv"):
            if f["cliente_id"] == "C01":
                self.assertEqual((f["estado_etiqueta"], f["compra_30d"]), ("madura", "1"))  # en ambas selecciones
        self.assertEqual({k: self.fila(seleccion=r1["piloto"]["seleccion_id"])[k] for k in humano}, humano)

    def test_migracion_de_identificadores_anteriores(self):
        from modelos.compra import COLUMNAS_PILOTO
        r = self.comparar(self.datos)
        filas = _leer_csv(self.salida / "piloto_registro.csv")
        antiguo = "2026-10-31|fixture-op|fixture-sombra|k10"
        sin_nuevas = COLUMNAS_PILOTO[:COLUMNAS_PILOTO.index("huella_operativa")]
        # Formato intermedio: identificador "corte|versiones|k" y sin huellas.
        legado = [{c: (antiguo if c == "seleccion_id" else f[c]) for c in sin_nuevas} for f in filas]
        legado[0].update(contacto_realizado="si", fecha_contacto="2026-11-10", tiempo_minutos="4", resultado_contacto="Llamada")
        _escribir_csv(self.salida / "piloto_registro.csv", legado)
        r2 = self.comparar(self.maduro)
        self.assertEqual(r2["seleccion"]["filas_migradas_de_formato_anterior"], 12)
        f = self.fila(legado[0]["cliente_id"])
        self.assertEqual((f["seleccion_id"], f["seleccion_id_anterior"], f["resultado_contacto"]), (r["piloto"]["seleccion_id"], antiguo, "Llamada"))
        # Si las filas antiguas no coinciden con lo recalculado, no se reidentifican: quedan como selección aparte.
        legado[1]["posicion_operativa"] = "99"
        _escribir_csv(self.salida / "piloto_registro.csv", legado)
        from modelos.compra import PilotoError
        with self.assertRaisesRegex(PilotoError, "nueva-seleccion"):
            self.comparar(self.maduro)
        r3 = self.comparar(self.maduro, nueva_seleccion=True)
        ids = {x["seleccion_id"] for x in _leer_csv(self.salida / "piloto_registro.csv")}
        self.assertEqual(ids, {antiguo, r3["piloto"]["seleccion_id"]})
        self.assertEqual(self.fila(legado[0]["cliente_id"], seleccion=antiguo)["resultado_contacto"], "Llamada")


# 4. Cobertura al reutilizar un lote ---------------------------------------------------------
@unittest.skipIf(_paquete() is None, "Paquete de datos no disponible")
class CoberturaReutilizadaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m1-cobr-"))
        self.config = self.tmp / "config.json"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cargar(self, declaracion, paquete=None):
        from pipeline.carga import cargar_lote
        self.config.write_text(json.dumps({"datos_observados_hasta": declaracion} if declaracion else {}), encoding="utf-8")
        return cargar_lote(Path(paquete or _paquete()), self.tmp / "a01", self.config)

    def test_mismos_csv_y_cobertura_actualizada_crean_revision_trazable(self):
        from modelos.datos import cargar_datos
        r1 = self.cargar({"ventas": "2026-10-31"})
        r2 = self.cargar({"ventas": "2026-11-30"})
        self.assertEqual((r1.status, r2.status, r2.manifest["revision"]), ("publicable", "reutilizado", 2))
        self.assertEqual(r2.manifest["contenido_de_revision"], 1)
        self.assertEqual(r2.manifest["cobertura_historial"][-1]["motivo"], "declaracion_actualizada")
        self.assertEqual(cargar_datos(self.tmp / "a01").observado_hasta, date(2026, 11, 30))
        self.assertTrue((self.tmp / "a01" / "historial_lotes.jsonl").read_text(encoding="utf-8").strip())
        r3 = self.cargar({"ventas": "2026-11-30"})  # misma declaración: reutilización simple
        self.assertEqual(r3.manifest["revision"], 2)

    def test_primera_declaracion_y_retirada(self):
        from modelos.datos import cargar_datos
        copia = self.tmp / "lote"
        shutil.copytree(_paquete() / "01_Datos", copia / "01_Datos")
        with (copia / "01_Datos" / "ventas.csv").open("a", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["VEN77777", "2026-10-20", "CLI001", "PRO01", "1", "COP", "100", "0", "Confirmada", "Prueba"])
        self.cargar(None, copia)
        from modelos.datos import CoberturaInsuficiente
        with self.assertRaises(CoberturaInsuficiente):  # desconocida: no es "sin compras"
            cargar_datos(self.tmp / "a01")
        r = self.cargar({"ventas": "2026-10-31"}, copia)
        self.assertEqual(r.manifest["cobertura_historial"][-1]["motivo"], "primera_declaracion")
        self.assertEqual(cargar_datos(self.tmp / "a01").observado_hasta, date(2026, 10, 31))
        r = self.cargar(None, copia)
        self.assertEqual(r.manifest["cobertura_historial"][-1]["motivo"], "declaracion_retirada")
        self.assertNotIn("datos_observados_hasta", r.manifest)
        with self.assertRaises(CoberturaInsuficiente):  # no conserva la cobertura retirada
            cargar_datos(self.tmp / "a01")

    def test_declaracion_incoherente_se_rechaza_y_conserva_la_revision(self):
        self.cargar({"ventas": "2026-10-31"})
        antes = (self.tmp / "a01" / "manifiesto.json").read_bytes()
        r = self.cargar({"ventas": "2026-09-30"})
        self.assertEqual(r.status, "fallido")
        self.assertEqual(r.issues[0].code, "COBERTURA_INCOHERENTE")
        self.assertEqual((self.tmp / "a01" / "manifiesto.json").read_bytes(), antes)
        nuevo = self.tmp / "otro"
        from pipeline.carga import cargar_lote
        self.config.write_text(json.dumps({"datos_observados_hasta": {"ventas": "2026-09-30"}}), encoding="utf-8")
        self.assertEqual(cargar_lote(_paquete(), nuevo, self.config).status, "fallido")  # también en carga nueva

    def test_cobertura_nueva_madura_etiquetas_sin_inventar_compras(self):
        from modelos import compra
        from modelos.datos import cargar_datos
        from modelos.inferencia import desde_dict
        self.cargar({"ventas": "2026-10-31"})
        datos_oct = cargar_datos(self.tmp / "a01")
        art = desde_dict(_artefacto())
        compra.puntuar(art, datos_oct, date(2026, 10, 31), self.tmp / "op")
        compra.puntuar(desde_dict(_artefacto(version="s", pesos=[0.1, 0.2])), datos_oct, date(2026, 10, 31), self.tmp / "sb")
        r = compra.comparar(self.tmp / "op", self.tmp / "sb", self.tmp / "cmp", datos_oct)
        self.assertEqual(r["estado_etiquetas"], "pendiente")
        self.cargar({"ventas": "2026-11-30"})  # fixture: sin transacciones nuevas
        datos_nov = cargar_datos(self.tmp / "a01")
        r = compra.comparar(self.tmp / "op", self.tmp / "sb", self.tmp / "cmp", datos_nov)
        self.assertEqual(r["estado_etiquetas"], "madura")
        positivos = sum(int(f["compra_30d"]) for f in _leer_csv(self.tmp / "cmp" / "piloto_registro.csv") if f["compra_30d"])
        reales = len({v["cliente_id"] for v in datos_nov.ventas if date(2026, 10, 31) < v["fecha"] <= date(2026, 11, 30)})
        self.assertEqual(positivos, reales)  # 0: no hay ventas de noviembre en el lote; no se inventan


# 5. Evaluación rechazada sin efectos --------------------------------------------------------
@unittest.skipIf(_paquete() is None or not HAY_SKLEARN, "Requiere el paquete y requirements-modelos.txt")
class EvaluacionRechazadaTests(unittest.TestCase):
    def test_conflicto_de_decision_no_reescribe_metricas_ni_predicciones(self):
        from modelos.compra import ProtocoloError, cargar_config, cargar_datos_config, entrenar, evaluar
        from modelos.datos import preparar_lote
        tmp = Path(tempfile.mkdtemp(prefix="m1-evr-"))
        try:
            preparar_lote(_paquete(), tmp / "a01")
            config = cargar_config()
            datos = cargar_datos_config(tmp / "a01", config)
            entrenar(datos, config, tmp / "e" / "e1")
            evaluar(tmp / "e" / "e1", datos)
            d = json.loads((tmp / "e" / "e1" / "decision.json").read_text(encoding="utf-8"))
            (tmp / "e" / "e1" / "decision.json").write_text(json.dumps(dict(d, decision="inconsistente_fixture")), encoding="utf-8")
            antes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp / "e" / "e1").iterdir()}
            with mock.patch("modelos.compra._hoy_utc", return_value="2099-01-01T00:00:00+00:00"), self.assertRaises(ProtocoloError):
                evaluar(tmp / "e" / "e1", datos)
            self.assertEqual({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (tmp / "e" / "e1").iterdir()}, antes)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
