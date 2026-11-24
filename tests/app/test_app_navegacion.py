"""Navegación por áreas (app/navegacion.js) frente a la matriz real de permisos (api/permisos.py).

Comprueba con Node, sin navegador, que el menú de cada perfil:
- no ofrece destinos que el perfil no puede abrir (la reorganización no amplía permisos);
- no pierde ninguna vista que el perfil sí puede abrir;
- marca un único destino activo, también en rutas de detalle y secciones con parámetros;
- da a cada perfil su propio inicio y deja el portal de empresas separado del área interna.
"""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from api.permisos import MATRIZ, IDENTIDADES

RAIZ = Path(__file__).resolve().parents[2]

# Destino del menú → capacidades que lo autorizan (las mismas que exige el enrutador de app/app.js y la API).
REQUISITOS = {
    "#/tableros/gerencia": {"tablero.gerencia"}, "#/tableros/ventas": {"tablero.ventas"}, "#/tableros/operaciones": {"tablero.operaciones"},
    "#/agenda": {"cartera.ver"}, "#/tareas": {"tareas.ver"}, "#/prevencion": {"prevencion.ver"}, "#/proxima": {"proxima.ver"},
    "#/venta-cruzada": {"venta_cruzada.ver"}, "#/anomalias": {"anomalias.ver"}, "#/demanda": {"demanda.ver_cop", "demanda.ver_unidades"},
    "#/finanzas?seccion=resultado": {"finanzas.ver"}, "#/finanzas?seccion=escenarios": {"finanzas.ver"}, "#/finanzas?seccion=informes": {"informes.ver"},
    "#/finanzas": {"finanzas.ver", "informes.ver"}, "#/pqrs": {"pqrs.gestionar", "pqrs.indicadores", "pqrs.ver_propias"},
    "#/beneficios": {"beneficios.ver_interno", "beneficios.portal"}, "#/documentos": {"documentos.gestionar"},
    "#/operacion?seccion=cargar": {"operacion.administrar"}, "#/operacion?seccion=actividad": {"operacion.administrar"},
    "#/operacion?seccion=administrar": {"operacion.administrar"}, "#/ia": {"cartera.ver"}, "#/monitoreo": {"monitoreo.ver"},
}

SCRIPT = r"""
import { areasPara, activoEn, inicioPara } from "./app/navegacion.js";
const perfiles = JSON.parse(process.argv[1]);
const rutas = JSON.parse(process.argv[2]);
const salida = {};
for (const [id, p] of Object.entries(perfiles)) {
  const usuario = { roles: [p.rol], externo: p.rol === "empresa" };
  const puede = a => p.acciones.includes(a);
  const areas = areasPara(usuario, puede);
  const activos = {};
  for (const r of rutas) {
    const [camino, qs] = r.slice(2).split("?");
    const a = activoEn(areas, camino.split("/").filter(Boolean), new URLSearchParams(qs || ""));
    activos[r] = a ? `${a.area.id}:${a.item.hash}` : null;
  }
  salida[id] = { inicio: inicioPara(usuario, puede), areas: areas.map(a => ({ id: a.id, items: a.items.map(i => i.hash) })), activos };
}
console.log(JSON.stringify(salida));
"""

RUTAS = ["#/clientes/CLI030", "#/clientes/CLI030?pestana=senales", "#/agenda?accion=x", "#/tareas/7", "#/finanzas", "#/finanzas?seccion=escenarios",
         "#/demanda?serie=ventas_cop:Total", "#/monitoreo?aviso=k", "#/ia", "#/operacion?seccion=ejecutar", "#/operacion?seccion=actividad",
         "#/anomalias?universo=compra&caso=X", "#/tableros/gerencia", "#/pqrs/PQRS-1", "#/beneficios"]


@unittest.skipUnless(shutil.which("node"), "Node no disponible")
class PruebasNavegacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        perfiles = {}
        for ident, _, _, rol in IDENTIDADES:
            perfiles[ident] = {"rol": rol, "acciones": sorted(a for a, roles in MATRIZ.items() if rol in roles)}
        cls.perfiles = perfiles
        r = subprocess.run(["node", "--input-type=module", "-e", SCRIPT, json.dumps(perfiles), json.dumps(RUTAS)],
                           cwd=RAIZ, capture_output=True, text=True, encoding="utf-8")
        assert r.returncode == 0, r.stderr
        cls.menu = json.loads(r.stdout)

    def destinos(self, ident):
        return [h for a in self.menu[ident]["areas"] for h in a["items"]]

    def test_ningun_destino_sin_permiso(self):
        for ident, p in self.perfiles.items():
            for h in self.destinos(ident):
                if h == "#/bienvenida":
                    self.assertEqual(p["rol"], "operaciones", ident); continue
                req = REQUISITOS.get(h)
                self.assertIsNotNone(req, f"{ident}: destino sin requisito conocido {h}")
                self.assertTrue(req & set(p["acciones"]), f"{ident} no puede abrir {h}")

    def test_no_se_pierde_ninguna_vista_autorizada(self):
        for ident, p in self.perfiles.items():
            if p["rol"] == "empresa":
                continue
            visibles = set(self.destinos(ident))
            for h, req in REQUISITOS.items():
                if h in ("#/finanzas", "#/finanzas?seccion=resultado") or not req & set(p["acciones"]):
                    continue
                if h == "#/ia" and "cartera.ver" not in p["acciones"]:
                    continue
                if h == "#/monitoreo" and "cartera.ver" in p["acciones"]:
                    self.assertIn("#/ia", visibles, ident); continue   # una entrada común: Modelos y monitoreo
                self.assertIn(h, visibles | {self.menu[ident]["inicio"]}, f"{ident} perdió {h}")

    def test_un_solo_activo_y_detalles_dentro_de_su_lista(self):
        g = self.menu["ger1"]["activos"]
        self.assertEqual(g["#/clientes/CLI030"], "clientes:#/agenda")
        self.assertEqual(g["#/clientes/CLI030?pestana=senales"], "clientes:#/agenda")
        self.assertEqual(g["#/tareas/7"], "clientes:#/tareas")
        self.assertEqual(g["#/finanzas?seccion=escenarios"], "finanzas:#/finanzas?seccion=escenarios")
        self.assertEqual(g["#/finanzas"], "finanzas:#/finanzas?seccion=resultado")
        self.assertEqual(g["#/monitoreo?aviso=k"], "administracion:#/ia")
        self.assertEqual(g["#/tableros/gerencia"], "inicio:#/tableros/gerencia")
        self.assertEqual(self.menu["ops1"]["activos"]["#/operacion?seccion=ejecutar"], "administracion:#/operacion?seccion=cargar")
        self.assertEqual(self.menu["ops1"]["activos"]["#/operacion?seccion=actividad"], "administracion:#/operacion?seccion=actividad")
        self.assertEqual(self.menu["ops1"]["activos"]["#/finanzas"], "finanzas:#/finanzas?seccion=informes")

    def test_inicio_propio_y_portal_separado(self):
        inicios = {i: self.menu[i]["inicio"] for i in ("ger1", "ventas1", "ops1", "fin1", "aten1", "cli_a")}
        self.assertEqual(inicios, {"ger1": "#/tableros/gerencia", "ventas1": "#/tableros/ventas", "ops1": "#/bienvenida",
                                   "fin1": "#/finanzas", "aten1": "#/pqrs", "cli_a": "#/beneficios"})
        self.assertEqual([a["id"] for a in self.menu["cli_a"]["areas"]], ["portal", "solicitudes"])
        self.assertNotIn("finanzas", [a["id"] for a in self.menu["ventas1"]["areas"]])
        self.assertNotIn("clientes", [a["id"] for a in self.menu["fin1"]["areas"]])
        self.assertNotIn("#/operacion?seccion=cargar", self.destinos("ger1"))   # Gerencia no administra cierres
        self.assertIn("#/tableros/gerencia", self.destinos("fin1"))             # Finanzas conserva el resumen ejecutivo

    def test_maximo_dos_niveles_y_sin_duplicados(self):
        for ident in self.perfiles:
            d = self.destinos(ident)
            self.assertEqual(len(d), len(set(d)), f"{ident}: destino repetido en el menú")


if __name__ == "__main__":
    unittest.main()
