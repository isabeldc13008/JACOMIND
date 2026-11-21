"""Utilidades comunes para las pruebas de B (sin dependencias)."""
from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from api import base
from api.auth import cargar_usuario
from api.base import BaseDatos
from api.demo import preparar
from api.servidor import Aplicacion

RAIZ = Path(__file__).resolve().parents[2]
MUESTRA = RAIZ / "contratos" / "ejemplos" / "publicacion" / "demo-2026-10"
EJEMPLOS = RAIZ / "contratos" / "ejemplos" / "agenda"
HOY = "2026-11-21"


def leer(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def escribir(p, datos):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")


class CasoBase(unittest.TestCase):
    """Base de datos temporal con la demo ficticia publicada."""
    publicar_muestra = True

    def setUp(self):
        base.fijar_hoy(HOY)
        self.tmp = Path(tempfile.mkdtemp(prefix="jacomind-"))
        self.db = BaseDatos(self.tmp / "t.sqlite3")
        preparar(self.db, publicar_muestra=self.publicar_muestra)
        self.app = Aplicacion(self.db, practica=False)
        self._cookies = {}

    def tearDown(self):
        base.fijar_hoy(None)
        from api import publicacion
        publicacion.FALLO_SIMULADO = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def usuario(self, ident):
        with self.db.conexion() as con:
            return cargar_usuario(con, ident)

    def http(self, metodo, ruta, cuerpo=None, como=None, cabeceras=None):
        h = {"X-Jacomind": "1"} | (cabeceras or {})
        if como:
            if como not in self._cookies:
                r = self.app.despachar("POST", "/api/sesion", {"X-Jacomind": "1"}, json.dumps({"identidad": como}).encode())
                self._cookies[como] = r.cabeceras["Set-Cookie"].split(";")[0]
            h["Cookie"] = self._cookies[como]
        r = self.app.despachar(metodo, ruta, h, json.dumps(cuerpo).encode() if cuerpo is not None else b"")
        datos = json.loads(r.cuerpo) if r.tipo.startswith("application/json") else r.cuerpo.decode("utf-8")
        return r.status, datos

    def publicacion_modificada(self, nombre, cambiar):
        """Copia la muestra C2 a un directorio temporal y aplica ``cambiar(tablas)``."""
        d = self.tmp / nombre
        shutil.copytree(MUESTRA, d)
        tablas = {p.stem: leer(p) for p in d.glob("*.json")}
        cambiar(tablas)
        man = tablas["manifiesto"]
        for t, decl in man["tablas"].items():
            contenido = tablas[t]
            decl["filas"] = len(contenido["clientes"]) if t == "agenda" else len(contenido)
            if t == "historial_ventas":
                decl["sumas"] = {"importe_cop": round(sum(v["importe_cop"] for v in contenido), 2)}
        for t, contenido in tablas.items():
            escribir(d / f"{t}.json", contenido)
        return d


def agenda_valida():
    return copy.deepcopy(leer(EJEMPLOS / "valido.json"))
