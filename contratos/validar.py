"""Validación de contratos C1 (agenda) y C2 (publicación analítica).

Uso independiente de la pantalla (para A):

    python -m contratos.validar salida/agenda.json
    python -m contratos.validar --publicacion salida/cierres/<cierre_id>

Código de salida 0 = válido, 1 = inválido, 2 = versión incompatible o archivo ausente.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .esquema import validar as validar_esquema

DIR = Path(__file__).resolve().parent
VERSIONES_AGENDA = {1}
VERSIONES_PUBLICACION = {1}


def cargar_esquema(nombre: str) -> dict:
    return json.loads((DIR / nombre).read_text(encoding="utf-8"))


@dataclass
class Resultado:
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    incompatible: bool = False

    @property
    def valido(self) -> bool:
        return not self.errores

    def como_dict(self) -> dict:
        return {"valido": self.valido, "incompatible": self.incompatible,
                "errores": self.errores, "advertencias": self.advertencias}


def validar_agenda(datos) -> Resultado:
    r = Resultado()
    if not isinstance(datos, dict):
        r.errores.append("$: la agenda debe ser un objeto JSON")
        return r
    version = datos.get("version")
    if version not in VERSIONES_AGENDA:
        r.incompatible = True
        r.errores.append(f"$.version: versión {version!r} no soportada (soportadas: {sorted(VERSIONES_AGENDA)})")
        return r
    r.errores.extend(validar_esquema(datos, cargar_esquema("agenda.v1.schema.json")))
    if r.errores:
        return r
    clientes = datos["clientes"]
    vistos: set[str] = set()
    for i, c in enumerate(clientes):
        ruta = f"$.clientes[{i}]"
        cid = c["cliente_id"]
        if cid in vistos:
            r.errores.append(f"{ruta}.cliente_id: ID repetido {cid!r}")
        vistos.add(cid)
        if (c["ultima_compra"] is None) != (c["dias_sin_compra"] is None):
            r.errores.append(f"{ruta}: ultima_compra y dias_sin_compra deben ser ambos null o ambos informados")
        if c["ultima_compra"] is None:
            if c["frio"]:
                r.errores.append(f"{ruta}.frio: un cliente sin compras no puede estar frío")
            if c["ventas_confirmadas"] != 0:
                r.errores.append(f"{ruta}: sin última compra pero con ventas confirmadas")
            if c["prob_compra_30d"] is not None:
                r.advertencias.append(f"{ruta}: cliente sin historial con probabilidad informada")
        elif c["ventas_confirmadas"] == 0:
            r.errores.append(f"{ruta}: tiene última compra pero 0 ventas confirmadas")
        if isinstance(c["ingreso_cop"], float) and not math.isfinite(c["ingreso_cop"]):
            r.errores.append(f"{ruta}.ingreso_cop: importe no finito")
    res = datos["resumen"]
    if res["clientes"] != len(clientes):
        r.errores.append(f"$.resumen.clientes={res['clientes']} no coincide con {len(clientes)} filas")
    frios = sum(1 for c in clientes if c["frio"])
    if res["clientes_frios"] != frios:
        r.errores.append(f"$.resumen.clientes_frios={res['clientes_frios']} no coincide con {frios}")
    ventas = sum(c["ventas_confirmadas"] for c in clientes)
    if res["ventas_confirmadas"] != ventas:
        r.errores.append(f"$.resumen.ventas_confirmadas={res['ventas_confirmadas']} no coincide con {ventas}")
    ingreso = sum(c["ingreso_cop"] for c in clientes)
    tolerancia = 0.01 * (len(clientes) + 1)
    if abs(res["ingreso_cop"] - ingreso) > tolerancia:
        r.errores.append(f"$.resumen.ingreso_cop={res['ingreso_cop']} no coincide con la suma {round(ingreso, 2)}")
    return r


def leer_json(ruta: Path):
    with Path(ruta).open(encoding="utf-8-sig") as f:
        return json.load(f)


def _tipo_ok(valor, tipo: str) -> bool:
    opciones = tipo.split(" ")[0].split("|")
    for t in opciones:
        if t == "null" and valor is None:
            return True
        if t in ("string", "date", "YYYY-MM") and isinstance(valor, str):
            return True
        if t == "integer" and isinstance(valor, int) and not isinstance(valor, bool):
            return True
        if t == "number" and isinstance(valor, (int, float)) and not isinstance(valor, bool):
            return True
        if t == "boolean" and isinstance(valor, bool):
            return True
        if t.startswith("array") and isinstance(valor, list):
            return True
        if t == "object" and isinstance(valor, dict):
            return True
        if t not in ("string", "date", "YYYY-MM", "integer", "number", "boolean", "object", "null") and not t.startswith("array") and valor == t:
            return True  # enumeración literal (p. ej. vigente|proxima|vencida)
    return False


def validar_tabla(nombre: str, filas, definicion: dict | None, declarada: dict) -> list[str]:
    errores: list[str] = []
    if not isinstance(filas, list):
        return [f"{nombre}: el archivo debe contener una lista de filas"]
    if declarada["filas"] != len(filas):
        errores.append(f"{nombre}: el manifiesto declara {declarada['filas']} filas y hay {len(filas)}")
    if definicion is None:
        return errores  # tabla opcional desconocida: se admite y se conserva
    clave = definicion["clave"]
    vistos = set()
    for i, fila in enumerate(filas):
        if not isinstance(fila, dict):
            errores.append(f"{nombre}[{i}]: fila no es objeto")
            continue
        for campo, tipo in definicion.get("requeridos", {}).items():
            if campo not in fila:
                errores.append(f"{nombre}[{i}]: falta '{campo}'")
            elif not _tipo_ok(fila[campo], tipo):
                errores.append(f"{nombre}[{i}].{campo}: valor {fila[campo]!r} no cumple '{tipo}'")
        k = tuple(fila.get(c) for c in clave)
        if k in vistos:
            errores.append(f"{nombre}[{i}]: clave duplicada {dict(zip(clave, k))}")
        vistos.add(k)
        if len(errores) > 50:
            errores.append(f"{nombre}: demasiados errores, se detiene la revisión")
            break
    for campo, esperado in (declarada.get("sumas") or {}).items():
        total = sum((f.get(campo) or 0) for f in filas if isinstance(f, dict))
        if abs(total - esperado) > 0.01 * (len(filas) + 1):
            errores.append(f"{nombre}: suma de {campo}={round(total, 2)} difiere de la declarada {esperado}")
    return errores


def validar_publicacion(directorio) -> tuple[Resultado, dict]:
    """Valida un directorio C2. Devuelve (resultado, {tabla: filas}) para el importador."""
    d = Path(directorio)
    r = Resultado()
    datos: dict = {}
    mpath = d / "manifiesto.json"
    if not mpath.exists():
        r.incompatible = True
        r.errores.append(f"No existe {mpath}")
        return r, datos
    try:
        manifiesto = leer_json(mpath)
    except (OSError, json.JSONDecodeError) as e:
        r.errores.append(f"manifiesto.json ilegible: {e}")
        return r, datos
    if not isinstance(manifiesto, dict) or manifiesto.get("version") not in VERSIONES_PUBLICACION:
        r.incompatible = True
        r.errores.append(f"manifiesto.version {manifiesto.get('version') if isinstance(manifiesto, dict) else None!r} no soportada")
        return r, datos
    esquema = cargar_esquema("publicacion.v1.schema.json")
    r.errores.extend(validar_esquema(manifiesto, esquema))
    if r.errores:
        return r, datos
    conocidas = esquema["tablas_conocidas"]
    datos["manifiesto"] = manifiesto
    for nombre, declarada in manifiesto["tablas"].items():
        archivo = d / declarada["archivo"]
        if not archivo.resolve().is_relative_to(d.resolve()):
            r.errores.append(f"{nombre}: ruta fuera del directorio de publicación")
            continue
        try:
            contenido = leer_json(archivo)
        except FileNotFoundError:
            r.errores.append(f"{nombre}: falta el archivo {declarada['archivo']}")
            continue
        except json.JSONDecodeError as e:
            r.errores.append(f"{nombre}: JSON inválido ({e})")
            continue
        if nombre == "agenda":
            ra = validar_agenda(contenido)
            r.errores.extend(f"agenda {e}" for e in ra.errores)
            r.advertencias.extend(f"agenda {a}" for a in ra.advertencias)
            r.incompatible |= ra.incompatible
            if ra.valido:
                if declarada["filas"] != len(contenido["clientes"]):
                    r.errores.append(f"agenda: el manifiesto declara {declarada['filas']} filas y hay {len(contenido['clientes'])}")
                if contenido["corte"] != manifiesto["corte"]:
                    r.errores.append(f"agenda: corte {contenido['corte']} distinto del manifiesto {manifiesto['corte']}")
        else:
            if nombre not in conocidas:
                r.advertencias.append(f"{nombre}: tabla no definida en C2 v1; se conserva sin validar campos")
            r.errores.extend(validar_tabla(nombre, contenido, conocidas.get(nombre), declarada))
        datos[nombre] = contenido
    return r, datos


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Valida salidas de A contra los contratos C1/C2.")
    p.add_argument("ruta", help="agenda.json (C1) o directorio de publicación (C2)")
    p.add_argument("--publicacion", action="store_true", help="validar un directorio C2")
    p.add_argument("--json", action="store_true", help="imprimir el resultado como JSON")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ruta = Path(a.ruta)
    if a.publicacion or ruta.is_dir():
        res, _ = validar_publicacion(ruta)
    else:
        try:
            res = validar_agenda(leer_json(ruta))
        except FileNotFoundError:
            res = Resultado(errores=[f"No existe {ruta}"], incompatible=True)
        except json.JSONDecodeError as e:
            res = Resultado(errores=[f"JSON inválido: {e}"])
    if a.json:
        print(json.dumps(res.como_dict(), ensure_ascii=False, indent=2))
    else:
        print("VÁLIDO" if res.valido else ("INCOMPATIBLE" if res.incompatible else "INVÁLIDO"), ruta)
        for e in res.errores:
            print("  error:", e)
        for w in res.advertencias:
            print("  aviso:", w)
    return 0 if res.valido else (2 if res.incompatible else 1)


if __name__ == "__main__":
    sys.exit(main())
