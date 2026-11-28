"""Contrato de los gráficos y transformaciones de presentación (app/ui.js, app/vistas/*), ejecutados con Node.

No reproduce el HTML: comprueba reglas que una mejora visual no puede romper.
- Un dato nulo es un hueco con texto, nunca un punto en cero.
- La banda solo aparece donde la publicación trae límite inferior y superior.
- Una ventana sin fin dentro del horizonte no recibe una fecha inventada.
- La variación porcentual exige una base mayor que cero.
- Los identificadores de segmento se muestran sin inventar perfiles.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

SCRIPT = r"""
// DOM mínimo: los módulos solo lo consultan al cargarse.
globalThis.document = { getElementById: () => null, documentElement: { dataset: {} }, querySelector: () => null };
globalThis.localStorage = { getItem: () => null, setItem: () => {} };
globalThis.location = { hash: "" };
const ui = await import("./app/ui.js");
const nucleo = await import("./app/nucleo.js");
const tab = await import("./app/vistas/tableros.js");
const dem = await import("./app/vistas/demanda.js");
const ia = await import("./app/vistas/ia.js");
const r = {};
const hist = [{ periodo: "2026-08", valor: 10 }, { periodo: "2026-09", valor: null }, { periodo: "2026-10", valor: 30 }];
const sinBanda = ui.graficoLinea(hist, [{ periodo: "2026-11", valor: 25 }], { titulo: "t" });
const conBanda = ui.graficoLinea(hist, [{ periodo: "2026-11", valor: 25, inferior: 20, superior: 31 }, { periodo: "2026-12", valor: 26 }], { titulo: "t" });
r.hueco = sinBanda.includes("sin dato") && sinBanda.includes("Sin dato (no se rellena con cero)");
r.circulosObservados = (sinBanda.match(/fill="var\(--serie-obs\)"/g) || []).length;
r.bandaSinDatos = sinBanda.includes("var(--estimado-suave)");
r.bandasConDatos = (conBanda.match(/fill="var\(--estimado-suave\)"/g) || []).length;
r.leyendaParcial = conBanda.includes("solo en los meses que lo tienen");
r.estimadoDistinto = sinBanda.includes('stroke-dasharray="8 6"') && sinBanda.includes("Estimado (línea discontinua");
const rangos = ui.graficoRangos([{ etiqueta: "A", desde: "2026-11-03", hasta: null }, { etiqueta: "B", desde: "2026-11-05", hasta: "2026-11-20", contractual: "2027-06-08" }], { corte: "2026-10-31", titulo: "t" });
r.sinFin = rangos.includes("sin fin en el horizonte");
r.contractualFuera = rangos.includes("fin de cobertura 8 jun 2027");
r.varBaseCero = tab.variacion(5, 0);
r.varNormal = tab.variacion(110, 100);
r.varNula = tab.variacion(null, 100);
r.segmentos = [nucleo.nombreSegmento("seg_2"), nucleo.nombreSegmento("Recurrente activo"), nucleo.nombreSegmento(null)];
r.series = [dem.nombreSerie("ventas_cop:Total"), dem.nombreSerie("ventas_cop:Software"), dem.nombreSerie("ventas_unidades:PRO01")];
r.estimacion = [nucleo.textoEstimacion({ sin_historial: true }), nucleo.textoEstimacion({ ultima_compra: "2026-01-01", prob_compra_30d: null }), nucleo.textoEstimacion({ ultima_compra: "2026-01-01", prob_compra_30d: 0 })];
r.disponibilidad = [ia.disponibilidad("operativo (modo demostración)"), ia.disponibilidad("experimental (sombra) · decisión inconcluso"), ia.disponibilidad("")];
r.validacion = [ia.validacion("experimental (sombra) · decisión inconcluso"), ia.validacion("")];
r.horaNegocio = nucleo.fechaHora("2026-11-24T05:07:58+00:00");
r.fechaCalendario = nucleo.fechaHora("2026-10-31");
console.log(JSON.stringify(r));
"""


@unittest.skipUnless(shutil.which("node"), "Node no disponible")
class PruebasGraficos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = subprocess.run(["node", "--input-type=module", "-e", SCRIPT], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        assert p.returncode == 0, p.stderr
        cls.r = json.loads(p.stdout)

    def test_nulo_es_hueco_y_no_cero(self):
        self.assertTrue(self.r["hueco"])
        self.assertEqual(self.r["circulosObservados"], 2)   # solo los dos meses con dato

    def test_banda_solo_donde_existe(self):
        self.assertFalse(self.r["bandaSinDatos"])
        self.assertEqual(self.r["bandasConDatos"], 1)
        self.assertTrue(self.r["leyendaParcial"])
        self.assertTrue(self.r["estimadoDistinto"])

    def test_ventanas_sin_fechas_inventadas(self):
        self.assertTrue(self.r["sinFin"])
        self.assertTrue(self.r["contractualFuera"])

    def test_variacion_con_base_valida(self):
        self.assertEqual(self.r["varBaseCero"], {"diferencia": 5, "porcentaje": None})
        self.assertEqual(self.r["varNormal"], {"diferencia": 10, "porcentaje": 10})
        self.assertEqual(self.r["varNula"], {"diferencia": None, "porcentaje": None})

    def test_etiquetas_legibles_sin_inventar(self):
        self.assertEqual(self.r["segmentos"], ["Segmento 2", "Recurrente activo", ""])
        self.assertEqual(self.r["series"], ["Ventas totales (en pesos)", "Ventas de la familia Software (en pesos)", "Unidades vendidas del producto PRO01"])
        self.assertEqual(self.r["estimacion"], ["Sin compras registradas", "Hay compras, pero falta la estimación", "El modelo estimó 0 %"])

    def test_estado_de_modelos_nunca_verde_por_omision(self):
        self.assertEqual(self.r["disponibilidad"], ["En uso (modo demostración)", "En uso", "No publicado"])
        self.assertTrue(self.r["validacion"][0].startswith("Validación inconclusa"))
        self.assertEqual(self.r["validacion"][1], "Sin evaluación publicada")

    def test_horas_en_zona_del_negocio_y_fechas_sin_desplazar(self):
        self.assertEqual(self.r["horaNegocio"], "24 de noviembre de 2026, 00:07")   # 05:07 UTC = 00:07 en Bogotá
        self.assertEqual(self.r["fechaCalendario"], "31 de octubre de 2026")


if __name__ == "__main__":
    unittest.main()
