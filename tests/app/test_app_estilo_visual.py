from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "app" / "estilos.css").read_text(encoding="utf-8")
APP = (ROOT / "app" / "app.js").read_text(encoding="utf-8")
TABLEROS = (ROOT / "app" / "vistas" / "tableros.js").read_text(encoding="utf-8")


class ContratoVisualGlobal(unittest.TestCase):
    def test_paleta_corporativa_y_espaciado_estan_centralizados(self):
        required = {
            "--acento: #512DA8",
            "--azul-tech: #243B80",
            "--azul-profundo: #17152F",
            "--morado-secundario: #8564DC",
            "--lavanda: #C4B5FD",
            "--fondo: #F5F6FA",
            "--superficie: #FFFFFF",
            "--texto: #17152F",
            "--texto-2: #737082",
            "--borde: #E6E4EC",
            "--gradiente-corporativo: linear-gradient(135deg, #17152F 0%, #343080 52%, #633AB5 100%)",
        }
        for token in required:
            self.assertIn(token, CSS)
        self.assertIn("--e1: .5rem", CSS)
        self.assertNotIn("--acento: #6fd19a", CSS)

    def test_toda_la_navegacion_usa_la_identidad_azul_morada(self):
        self.assertIn(".lateral { background: var(--azul-profundo)", CSS)
        self.assertIn(".lateral a[aria-current=\"page\"] { background: var(--morado-secundario)", CSS)
        self.assertIn(".barra { background: var(--superficie)", CSS)
        self.assertIn(".panel { background: var(--superficie)", CSS)
        self.assertIn("height: calc(100vh - 4.5rem)", CSS)

    def test_acceso_conserva_modalidades_y_recupera_errores_de_carga(self):
        for text in (
            "De los datos a la acción.",
            "Inteligencia que anticipa oportunidades.",
            "Ingresar a JACOMIND",
            "Consultar agenda guardada",
            "Explorar ejemplo de práctica",
        ):
            self.assertIn(text, APP)
        self.assertIn("Promise.race", APP)
        self.assertIn("b.disabled = false", APP)
        self.assertIn("b.innerHTML = `Ingresar a JACOMIND", APP)

    def test_tema_oscuro_y_movimiento_reducido_siguen_soportados(self):
        self.assertIn(':root[data-theme="dark"]', CSS)
        self.assertIn("--acento: #8564DC", CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        self.assertIn("@media (max-width: 800px)", CSS)
        self.assertIn("@media (max-width: 640px)", CSS)

    def test_layout_movil_reinicia_menu_y_evitat_desbordamiento_horizontal(self):
        self.assertIn(".lateral.abierto { max-height: calc(100vh - 4rem); overflow-y: auto", CSS)
        self.assertIn("body { overflow-x: hidden; }", CSS)
        self.assertIn(".cabecera-acciones { width: 100%; margin-left: 0", CSS)

    def test_accesibilidad_ofrece_tamanos_de_letra_pequenos_y_grandes(self):
        nucleo = (ROOT / "app" / "nucleo.js").read_text(encoding="utf-8")
        for size in ('"muy-pequena": "Muy pequeña"', 'pequena: "Pequeña"', 'normal: "Normal"', '"muy-grande": "Muy grande"'):
            self.assertIn(size, nucleo)
        self.assertIn('html[data-tamano="muy-pequena"] { font-size: 87.5%; }', CSS)
        self.assertIn('html[data-tamano="pequena"] { font-size: 100%; }', CSS)

    def test_tamano_muy_grande_reorganiza_sin_ocultar_contenido(self):
        self.assertIn('html[data-tamano="muy-grande"] .marco { grid-template-columns: minmax(0, 1fr); }', CSS)
        self.assertIn('html[data-tamano="muy-grande"] .lateral {', CSS)
        self.assertIn('html[data-tamano="muy-grande"] .pantalla-acceso-grid { grid-template-columns: minmax(0, 1fr); min-height: auto; }', CSS)

    def test_movil_prioriza_formulario_y_reduce_la_base_normal(self):
        self.assertIn('grid-template-areas: "panel" "hero"', CSS)
        self.assertIn('html[data-tamano="normal"] { font-size: 100%; }', CSS)
        self.assertIn('.acceso-panel { padding-inline: 1rem; }', CSS)

    def test_tableros_tienen_capa_visual_responsive_sin_cambiar_sus_datos(self):
        self.assertIn('class="tablero-dashboard tablero-${rol}"', TABLEROS)
        for selector in (
            ".tablero-dashboard .hallazgo",
            ".tablero-dashboard .indicadores",
            ".tablero-dashboard .panel > h2",
            ".tablero-dashboard .tabla tbody tr:hover",
            ".tablero-dashboard .b-relleno",
        ):
            self.assertIn(selector, CSS)


if __name__ == "__main__":
    unittest.main()
