"""Integridad y recuperación de los evaluadores experimentales M1.1, M1.2 y M1.3.

Cada prueba entrena en una carpeta temporal y manipula una COPIA: nunca toca las ejecuciones históricas.
Reproduce los tres defectos de la auditoría (A: artefacto principal desvinculado; B: evidencia de desarrollo o selección
sin proteger; C: recuperación incompleta) y los casos complementarios (marcador ausente, archivo alterado, otros datos,
artefacto de otra ejecución, formato antiguo y promoción).
"""
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HAY_SK = importlib.util.find_spec("sklearn") is not None


def _paquete():
    from pipeline.rutas import ruta_paquete
    return ruta_paquete()


def _leer(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _escribir(p, d):
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


@unittest.skipIf(_paquete() is None or not HAY_SK, "Requiere el paquete sintético y scikit-learn")
class IntegridadM1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from modelos.compra import cargar_config
        from modelos.compra_m11 import CONFIG_M11, entrenar_m11
        from modelos.compra_m12 import CONFIG_M12, entrenar_m12
        from modelos.compra_m13 import CONFIG_M13, entrenar_m13
        from modelos.datos import cargar_datos, preparar_lote
        cls.tmp = Path(tempfile.mkdtemp(prefix="m1int-"))
        preparar_lote(_paquete(), cls.tmp / "a01")
        cls.datos = cargar_datos(cls.tmp / "a01")
        cls.base = {}
        for v, (cfg, fn) in {"m11": (CONFIG_M11, entrenar_m11), "m12": (CONFIG_M12, entrenar_m12), "m13": (CONFIG_M13, entrenar_m13)}.items():
            fn(cls.datos, cargar_config(cfg), cls.tmp / v)
            cls.base[v] = cls.tmp / v

    @classmethod
    def tearDownClass(cls):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def tearDown(self):
        from modelos import ejecucion
        ejecucion.FALLO_SIMULADO = None

    def copia(self, v, nombre):
        d = self.tmp / f"{v}-{nombre}"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(self.base[v], d)
        return d

    def evaluar(self, v, d, datos=None):
        from modelos import compra_m11, compra_m12, compra_m13
        fn = {"m11": compra_m11.evaluar_m11, "m12": compra_m12.evaluar_m12, "m13": compra_m13.evaluar_m13}[v]
        return fn(d, datos or self.datos)

    # A. Artefacto principal --------------------------------------------------------------------------------------------
    def test_a_m11_artefacto_principal_sustituido_por_otro_candidato(self):
        from modelos.compra import ProtocoloError
        d = self.copia("m11", "a")
        cong = _leer(d / "congelacion.json")
        usar = cong["artefactos"]["global"]["usar"]
        otro = next(p for p in sorted(d.glob("artefacto_*_*.json")) if p.name != f"artefacto_global_{usar}.json")
        shutil.copy(otro, d / "artefacto.json")  # otro candidato VÁLIDO
        with self.assertRaises(ProtocoloError):
            self.evaluar("m11", d)

    def test_a_artefacto_de_otra_ejecucion(self):
        from modelos.compra import ProtocoloError
        d = self.copia("m11", "otra")
        shutil.copy(self.base["m12"] / "artefacto.json", d / "artefacto.json")
        with self.assertRaises(ProtocoloError):
            self.evaluar("m11", d)
        d = self.copia("m12", "otra")
        shutil.copy(self.base["m11"] / "artefacto.json", d / "artefacto.json")
        with self.assertRaises(ProtocoloError):
            self.evaluar("m12", d)

    # B. Evidencia de desarrollo y selección ----------------------------------------------------------------------------
    def test_b_desarrollo_alterado_invalida_m12_y_m13(self):
        from modelos.compra import ProtocoloError
        d = self.copia("m12", "b")
        dev = _leer(d / "desarrollo.json")
        dev["diferencia_fusion_menos_recencia_top10"] = 0.5
        dev["ic95_bootstrap_clientes"]["p2_5"] = 0.4
        _escribir(d / "desarrollo.json", dev)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m12", d)
        d = self.copia("m13", "b")
        dev = _leer(d / "desarrollo.json")
        dev["S_menos_recencia_top10"] = 0.5
        _escribir(d / "desarrollo.json", dev)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m13", d)

    def test_b_m11_seleccion_evidencia_y_cortes_alterados(self):
        from modelos.compra import ProtocoloError
        d = self.copia("m11", "sel")
        sel = _leer(d / "seleccion.json")
        sel["global"] = "otro_candidato"
        _escribir(d / "seleccion.json", sel)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m11", d)
        d = self.copia("m11", "oos")
        p = d / "predicciones_validacion_temporal.csv"
        lineas = p.read_text(encoding="utf-8").splitlines()
        lineas[1] = lineas[1].rsplit(",", 1)[0] + ",1" if not lineas[1].endswith(",1") else lineas[1].rsplit(",", 1)[0] + ",0"
        p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        with self.assertRaises(ProtocoloError):
            self.evaluar("m11", d)
        d = self.copia("m11", "cortes")
        cong = _leer(d / "congelacion.json")
        cong["cortes_entrenamiento_final"] = cong["cortes_entrenamiento_final"][:1]  # cambia la referencia «constante»
        _escribir(d / "congelacion.json", cong)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m11", d)

    # C. Recuperación -------------------------------------------------------------------------------------------------
    def test_c_decision_ausente_tras_metricas_se_completa(self):
        for v in ("m11", "m12", "m13"):
            with self.subTest(v=v):
                d = self.copia(v, "c")
                self.evaluar(v, d)
                (d / "decision.json").unlink()
                r = self.evaluar(v, d)  # el reintento completa la decisión que faltaba
                self.assertTrue((d / "decision.json").exists())
                self.assertIn("decision" if v != "m13" else "candidatos", r["decision"])

    def test_c_metricas_ausentes_con_decision_existente_conserva_la_decision(self):
        d = self.copia("m12", "c2")
        self.evaluar("m12", d)
        antes = (d / "decision.json").read_bytes()
        (d / "metricas_comprobacion_historica.json").unlink()
        self.evaluar("m12", d)
        self.assertEqual((d / "decision.json").read_bytes(), antes)  # no se reescribe (ni su fecha)
        self.assertTrue((d / "metricas_comprobacion_historica.json").exists())

    # C ampliado: interrupciones, marcador, alteraciones, datos distintos -------------------------------------------------
    def test_c_interrupcion_en_distintos_puntos_y_reintento_identico(self):
        from modelos import ejecucion
        from modelos.compra import ProtocoloError
        from modelos.compra_m1_ejecucion import evaluacion_publicada
        for v in ("m11", "m12", "m13"):
            for punto in ("metricas_comprobacion_historica.json", "decision.json"):
                with self.subTest(v=v, punto=punto):
                    d = self.copia(v, f"int-{punto[:4]}")
                    ejecucion.FALLO_SIMULADO = punto
                    with self.assertRaises(RuntimeError):
                        self.evaluar(v, d)
                    ejecucion.FALLO_SIMULADO = None
                    with self.assertRaises(ProtocoloError):
                        evaluacion_publicada(d)              # incompleta: no se consume
                    a = self.evaluar(v, d)
                    m1 = _leer(d / "evaluacion.json")
                    b = self.evaluar(v, d)                   # reintento idéntico
                    self.assertEqual(a, b)
                    self.assertEqual(_leer(d / "evaluacion.json"), m1)  # conserva la primera fecha real
                    self.assertEqual(evaluacion_publicada(d)["evaluacion"]["sello"], m1["sello"])

    def test_c_marcador_ausente_archivo_alterado_y_resultado_distinto(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m1_ejecucion import evaluacion_publicada
        d = self.copia("m12", "marc")
        self.evaluar("m12", d)
        (d / "evaluacion.json").unlink()
        with self.assertRaises(ProtocoloError):
            evaluacion_publicada(d)
        self.evaluar("m12", d)                                # completa el marcador
        evaluacion_publicada(d)
        dec = _leer(d / "decision.json")
        dec["decision"] = "favorable"
        _escribir(d / "decision.json", dec)                   # archivo publicado alterado
        with self.assertRaises(ProtocoloError):
            evaluacion_publicada(d)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m12", d)                            # no se sobrescribe evidencia distinta
        d = self.copia("m12", "dist")
        met = {"bloque": "otro"}
        _escribir(d / "metricas_comprobacion_historica.json", met)  # resultado distinto sin marcador
        with self.assertRaises(ProtocoloError):
            self.evaluar("m12", d)
        self.assertEqual(_leer(d / "metricas_comprobacion_historica.json"), met)

    def test_c_otros_datos_y_marcador_de_congelacion_manipulado(self):
        import copy
        from modelos.compra import ProtocoloError
        d = self.copia("m13", "datos")
        otro = copy.copy(self.datos)
        otro.huella_datos = "0" * 64
        with self.assertRaises(ProtocoloError):
            self.evaluar("m13", d, otro)
        cong = _leer(d / "congelacion.json")
        cong["volatiles"]["congelacion_real"] = "2020-01-01"      # volátil documentado: no invalida
        _escribir(d / "congelacion.json", cong)
        self.evaluar("m13", d)
        cong["fechas"]["disponibilidad_simulada_desde"] = "2020-01-01"  # sellado: invalida
        _escribir(d / "congelacion.json", cong)
        with self.assertRaises(ProtocoloError):
            self.evaluar("m13", d)

    # Formato antiguo y promoción ----------------------------------------------------------------------------------------
    def test_formato_antiguo_lectura_parcial_sin_reevaluar_ni_promover(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m1_ejecucion import decision_para_registro, huella_directorio, leer_evaluacion
        hist = RAIZ / "salida" / "experimentos" / "compra_30d_m13" / "ejecucion-001"
        if not (hist / "decision.json").exists():
            self.skipTest("Sin la ejecución histórica M1.3")
        antes = huella_directorio(hist)
        d = self.tmp / "hist-m13"
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(hist, d)
        ev = leer_evaluacion(d, "m13")
        self.assertEqual((ev["congelacion"]["verificacion"]["formato"], ev["congelacion"]["verificacion"]["nivel"]), (2, "parcial"))
        self.assertIn("desarrollo.json (decide S y P)", ev["congelacion"]["verificacion"]["no_verificable"])
        with self.assertRaises(ProtocoloError):
            self.evaluar("m13", d)
        with self.assertRaises(ProtocoloError):
            decision_para_registro(d, "P")
        self.assertEqual(huella_directorio(hist), antes)       # la histórica no se tocó
        shutil.copy(d / "artefacto_S.json", d / "artefacto_P.json")  # artefacto sustituido en formato antiguo: también se detecta
        with self.assertRaises(ProtocoloError):
            leer_evaluacion(d, "m13")

    def test_promover_exige_evaluacion_terminada_y_vinculada(self):
        from modelos.compra import ProtocoloError
        from modelos.compra_m1_ejecucion import decision_para_registro
        d = self.copia("m11", "prom")
        with self.assertRaises(ProtocoloError):
            decision_para_registro(d)                            # sin evaluar
        self.evaluar("m11", d)
        ruta, dec = decision_para_registro(d)
        from modelos.inferencia import cargar_artefacto
        self.assertEqual(cargar_artefacto(ruta).huella, dec["artefacto_huella"])
        self.assertEqual(dec["sello_congelacion"], _leer(d / "congelacion.json")["sello"])
        d = self.copia("m13", "prom")
        self.evaluar("m13", d)
        with self.assertRaises(ProtocoloError):
            decision_para_registro(d)                            # M1.3 exige candidato
        ruta, dec = decision_para_registro(d, "P")
        self.assertEqual(cargar_artefacto(ruta).huella, dec["artefacto_huella"])

    def test_reproduccion_en_carpeta_nueva_mismas_predicciones(self):
        from modelos.compra import cargar_config
        from modelos.compra_m12 import CONFIG_M12, entrenar_m12
        d = self.tmp / "m12-repro"
        shutil.rmtree(d, ignore_errors=True)
        r = entrenar_m12(self.datos, cargar_config(CONFIG_M12), d)
        self.assertEqual(r["congelacion"]["artefacto_huella"], _leer(self.base["m12"] / "congelacion.json")["artefacto_huella"])
        a, b = _leer(d / "congelacion.json"), _leer(self.base["m12"] / "congelacion.json")
        # Solo protocolo.json difiere: lleva la fecha real en que se registró el protocolo antes de ajustar.
        self.assertEqual([k for k in a["archivos"] if a["archivos"][k] != b["archivos"][k]], ["protocolo.json"])
        self.assertEqual({k: v for k, v in a.items() if k not in ("archivos", "sello", "volatiles", "escrito_en", "codigo")},
                         {k: v for k, v in b.items() if k not in ("archivos", "sello", "volatiles", "escrito_en", "codigo")})


if __name__ == "__main__":
    unittest.main()
