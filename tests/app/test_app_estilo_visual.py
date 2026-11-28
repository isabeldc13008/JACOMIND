from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "app" / "estilos.css").read_text(encoding="utf-8")
APP = (ROOT / "app" / "app.js").read_text(encoding="utf-8")


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

    def test_acceso_conserva_modalidades_y_recupera_errores_de_carga(self):
        for text in (
            "De los datos a la acción.",
            "Inteligencia que anticipa oportunidades.",
            "Ingresar a JACOMIND →",
            "Consultar agenda guardada",
            "Explorar ejemplo de práctica",
        ):
            self.assertIn(text, APP)
        self.assertIn("Promise.race", APP)
        self.assertIn("b.disabled = false", APP)
        self.assertIn("b.textContent = \"Ingresar a JACOMIND →\"", APP)

    def test_tema_oscuro_y_movimiento_reducido_siguen_soportados(self):
        self.assertIn(':root[data-theme="dark"]', CSS)
        self.assertIn("--acento: #8564DC", CSS)
        self.assertIn("@media (prefers-reduced-motion: reduce)", CSS)
        self.assertIn("@media (max-width: 800px)", CSS)


if __name__ == "__main__":
    unittest.main()
