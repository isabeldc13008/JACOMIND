import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class AzureStagingConfigTests(unittest.TestCase):
    def test_bicep_configura_python_https_y_datos_persistentes(self):
        bicep = (ROOT / "despliegue" / "azure" / "main.bicep").read_text(encoding="utf-8")
        for expected in ("PYTHON|3.12", "httpsOnly: true", "/home/data/jacomind.sqlite3", "JACOMIND_COOKIE_SEGURA"):
            self.assertIn(expected, bicep)

    def test_workflow_prueba_antes_de_desplegar_y_verifica_salud(self):
        workflow = (ROOT / ".github" / "workflows" / "azure-staging.yml").read_text(encoding="utf-8")
        self.assertLess(workflow.index("python -m unittest"), workflow.index("azure/webapps-deploy"))
        self.assertIn("/api/estado", workflow)


if __name__ == "__main__":
    unittest.main()
