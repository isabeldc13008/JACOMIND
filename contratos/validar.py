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
from datetime import date, timedelta
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


HORIZONTE_MODELO = {"compra_30d": 30, "inactividad_60d": 60, "proxima_compra": 60}
# M3 (proxima_compra) no publica probabilidad escalar: estima cuantiles de tiempo. Estados con estimación de M3:
ESTIMACION_PROXIMA = {"estimado", "estimacion_parcial"}
UMBRAL_FRIO_INACTIVIDAD = 90
# Estados que llevan probabilidad: 'estimado' (modelo) y 'estructural' (0 exacto por definición, solo inactividad_60d).
CON_PROBABILIDAD = {"estimado", "estructural"}


def _fecha_iso(valor) -> bool:
    try:
        return isinstance(valor, str) and len(valor) == 10 and date.fromisoformat(valor) is not None
    except ValueError:
        return False


def validar_predicciones(filas: list, agenda: dict | None, manifiesto: dict) -> list[str]:
    """Reglas semánticas de ``predicciones_clientes`` (tipos, rangos y coherencia con la agenda C1)."""
    errores: list[str] = []
    if not isinstance(filas, list):
        return errores  # validar_tabla ya lo informa
    clientes = {c["cliente_id"]: c for c in (agenda or {}).get("clientes", [])} if isinstance(agenda, dict) else {}
    modelo_agenda = (agenda or {}).get("modelo") if isinstance(agenda, dict) else None
    for i, f in enumerate(filas):
        if not isinstance(f, dict):
            continue
        ruta = f"predicciones_clientes[{i}]"
        p, estado = f.get("probabilidad"), f.get("estado")
        if p is not None and (isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1):
            errores.append(f"{ruta}.probabilidad: {p!r} fuera de [0, 1] o no finita")
        if f.get("modelo_id") == "proxima_compra":
            errores.extend(_reglas_proxima(f, ruta))
        elif (estado in CON_PROBABILIDAD) != (p is not None):
            errores.append(f"{ruta}: el estado '{estado}' no concuerda con probabilidad {p!r} "
                           "(solo 'estimado' y 'estructural' llevan probabilidad)")
        if f.get("modelo_id") == "inactividad_60d":
            errores.extend(_reglas_inactividad(f, ruta))
        elif estado == "estructural":
            errores.append(f"{ruta}: el estado 'estructural' solo existe para inactividad_60d")
        h = HORIZONTE_MODELO.get(f.get("modelo_id"))
        if h is not None and f.get("horizonte_dias") != h:
            errores.append(f"{ruta}.horizonte_dias: {f.get('horizonte_dias')!r} distinto de {h}")
        if not _fecha_iso(f.get("corte")) or f.get("corte") != manifiesto.get("corte"):
            errores.append(f"{ruta}.corte: {f.get('corte')!r} distinto del corte del manifiesto {manifiesto.get('corte')}")
        if f.get("datos_hasta") is not None and (not _fecha_iso(f["datos_hasta"]) or f["datos_hasta"] > manifiesto.get("corte", "")):
            errores.append(f"{ruta}.datos_hasta: usa datos posteriores al corte")
        if not f.get("motivos") or not all(isinstance(m, str) and m for m in f.get("motivos", [])):
            errores.append(f"{ruta}.motivos: se requiere al menos un motivo de texto")
        if f.get("modelo_id") == "compra_30d" and clientes:
            c = clientes.get(f.get("cliente_id"))
            if c is None:
                errores.append(f"{ruta}: cliente {f.get('cliente_id')!r} no está en la agenda")
            elif c.get("prob_compra_30d") != p:
                errores.append(f"{ruta}: probabilidad {p!r} distinta de agenda.prob_compra_30d {c.get('prob_compra_30d')!r}")
            if estado == "estimado" and (not modelo_agenda or modelo_agenda.get("version") != f.get("version_modelo")):
                errores.append(f"{ruta}.version_modelo: {f.get('version_modelo')!r} no coincide con agenda.modelo")
        if len(errores) > 50:
            errores.append("predicciones_clientes: demasiados errores, se detiene la revisión")
            break
    return errores


def _reglas_inactividad(f: dict, ruta: str) -> list[str]:
    """Coherencia de estado, recencia, probabilidad y nulos de ``inactividad_60d`` (M2)."""
    e: list[str] = []
    estado, p, r = f.get("estado"), f.get("probabilidad"), f.get("recencia_dias")
    if f.get("umbral_frio_dias") != UMBRAL_FRIO_INACTIVIDAD:
        e.append(f"{ruta}.umbral_frio_dias: {f.get('umbral_frio_dias')!r} distinto de {UMBRAL_FRIO_INACTIVIDAD}")
    if "recencia_dias" not in f or (r is not None and (isinstance(r, bool) or not isinstance(r, int) or r < 0)):
        e.append(f"{ruta}.recencia_dias: se requiere un entero >= 0 o null")
        return e
    aprendible = r is not None and 30 <= r < UMBRAL_FRIO_INACTIVIDAD
    if estado == "estructural" and (p != 0 or r is None or r >= 30):
        e.append(f"{ruta}: 'estructural' exige recencia 0–29 y probabilidad 0 exacta (recencia {r!r}, probabilidad {p!r})")
    if estado in ("estimado", "modelo_no_disponible") and not aprendible:
        e.append(f"{ruta}: '{estado}' solo aplica a la población aprendible (recencia 30–89), no a {r!r}")
    if estado == "sin_historial" and r is not None:
        e.append(f"{ruta}: 'sin_historial' no puede tener recencia ({r!r})")
    if estado == "no_elegible" and r is not None and r < UMBRAL_FRIO_INACTIVIDAD:
        e.append(f"{ruta}: 'no_elegible' con recencia {r} < 90 (solo ya fríos o alta posterior)")
    if r is not None and r >= UMBRAL_FRIO_INACTIVIDAD and estado != "no_elegible":
        e.append(f"{ruta}: recencia {r} >= 90 (ya frío) debe publicarse como 'no_elegible', no '{estado}'")
    if estado == "estimado" and p is not None and not 0 <= p <= 1:
        e.append(f"{ruta}.probabilidad fuera de [0, 1]")
    return e


def _reglas_proxima(f: dict, ruta: str) -> list[str]:
    """Cuantiles, fechas, soporte, nulos y ventana de ``proxima_compra`` (M3)."""
    e: list[str] = []
    estado = f.get("estado")
    if f.get("probabilidad") is not None:
        e.append(f"{ruta}: proxima_compra no publica probabilidad escalar (debe ser null)")
    dias = [f.get(f"dias_{n}") for n in ("p10", "p50", "p90")]
    soporte = f.get("soporte_dias")
    for n, v in zip(("p10", "p50", "p90"), dias):
        fecha = f.get(f"fecha_{n}")
        if v is None:
            if fecha is not None:
                e.append(f"{ruta}.fecha_{n}: fecha sin cuantil")
            continue
        if isinstance(v, bool) or not isinstance(v, int) or v < 1 or not isinstance(soporte, int) or v > soporte:
            e.append(f"{ruta}.dias_{n}: {v!r} fuera del soporte [1, {soporte!r}]")
            continue
        if not _fecha_iso(f.get("corte")) or fecha != (date.fromisoformat(f["corte"]) + timedelta(days=v)).isoformat():
            e.append(f"{ruta}.fecha_{n}: {fecha!r} no es corte + {v} días")
    presentes = [v for v in dias if v is not None]
    if any(b < a for a, b in zip(presentes, presentes[1:])):
        e.append(f"{ruta}: cuantiles desordenados {dias}")
    if any(dias[i] is None and dias[j] is not None for i in range(3) for j in range(i + 1, 3)):
        e.append(f"{ruta}: un cuantil menor no alcanzado no puede preceder a uno mayor alcanzado {dias}")
    if estado == "estimado" and None in dias:
        e.append(f"{ruta}: 'estimado' exige p10, p50 y p90; usa 'estimacion_parcial'")
    if estado == "estimacion_parcial" and None not in dias:
        e.append(f"{ruta}: 'estimacion_parcial' con los tres cuantiles")
    if estado not in ESTIMACION_PROXIMA and presentes:
        e.append(f"{ruta}: '{estado}' no puede publicar cuantiles")
    if estado in ESTIMACION_PROXIMA and f.get("origen_estimacion") not in ("modelo_cox", "poblacional_km"):
        e.append(f"{ruta}.origen_estimacion: {f.get('origen_estimacion')!r} no admitido")
    if estado not in ESTIMACION_PROXIMA and f.get("origen_estimacion") is not None:
        e.append(f"{ruta}.origen_estimacion debe ser null sin estimación")
    ancho_max = f.get("ancho_maximo_ventana_dias")
    tipo_v = f.get("ventana_tipo", "p10_p90")
    if tipo_v not in ("p10_p90", "p10_p50"):
        e.append(f"{ruta}.ventana_tipo: {tipo_v!r} no admitido (p10_p90|p10_p50)")
        tipo_v = "p10_p90"
    sup = dias[2] if tipo_v == "p10_p90" else dias[1]
    ancho = sup - dias[0] if dias[0] is not None and sup is not None else None
    if f.get("ancho_ventana_dias") != ancho:
        e.append(f"{ruta}.ancho_ventana_dias: {f.get('ancho_ventana_dias')!r} distinto de p90 − p10 ({ancho!r})")
    utilizable = ancho is not None and isinstance(ancho_max, int) and ancho <= ancho_max
    if f.get("ventana_utilizable") is not utilizable:
        e.append(f"{ruta}.ventana_utilizable: {f.get('ventana_utilizable')!r} y debería ser {utilizable} (sin sus dos límites no hay ventana)")
    pa = f.get("prob_acumulada")
    if pa is not None:
        try:
            pares = sorted((int(k), v) for k, v in pa.items())
        except (AttributeError, ValueError):
            pares = None
        if not pares or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for _, v in pares) \
                or any(t < 1 or not isinstance(soporte, int) or t > soporte for t, _ in pares) or any(b[1] < a[1] for a, b in zip(pares, pares[1:])):
            e.append(f"{ruta}.prob_acumulada: probabilidades en [0, 1], días dentro del soporte y no decrecientes")
        if estado not in ESTIMACION_PROXIMA:
            e.append(f"{ruta}.prob_acumulada sin estimación")
    fn = f.get("factor_nivel")
    if "factor_nivel" in f and (isinstance(fn, bool) or not isinstance(fn, (int, float)) or not math.isfinite(fn) or fn <= 0):
        e.append(f"{ruta}.factor_nivel: {fn!r} debe ser un número finito > 0")
    ref, rd = f.get("referencia_personal_estado"), f.get("referencia_personal_dias")
    if ref not in (None, "disponible", "vencida", "insuficiente"):
        e.append(f"{ruta}.referencia_personal_estado: {ref!r} no admitido")
    if (ref == "disponible" and not (isinstance(rd, (int, float)) and rd > 0)) or (ref == "vencida" and not (isinstance(rd, (int, float)) and rd <= 0))             or (ref in (None, "insuficiente") and rd is not None):
        e.append(f"{ruta}: referencia personal incoherente ({ref!r}, {rd!r})")
    if estado == "sin_historial" and (f.get("recencia_dias") is not None or ref is not None):
        e.append(f"{ruta}: 'sin_historial' no lleva recencia ni referencia personal")
    return e


def validar_cobertura(manifiesto: dict, predicciones) -> list[str]:
    """Coherencia entre corte, cobertura declarada y estimaciones publicadas.

    Una estimación (``estado = estimado``) exige ``manifiesto.cobertura`` verificada con
    ``datos_observados_hasta >= corte``. Con cobertura no verificada no se publican estimaciones.
    """
    errores: list[str] = []
    cob = manifiesto.get("cobertura")
    estimadas = [f for f in (predicciones or []) if isinstance(f, dict) and (f.get("estado") in CON_PROBABILIDAD
                                                                          or (f.get("modelo_id") == "proxima_compra" and f.get("estado") in ESTIMACION_PROXIMA))]
    corte = manifiesto.get("corte")
    if cob is None:
        if estimadas:
            errores.append("cobertura: hay predicciones estimadas pero el manifiesto no declara la cobertura temporal del lote")
        return errores
    if not isinstance(cob, dict):
        return ["cobertura: debe ser un objeto"]
    hasta, estado = cob.get("datos_observados_hasta"), cob.get("estado")
    if cob.get("corte") not in (None, corte):
        errores.append(f"cobertura.corte {cob.get('corte')!r} distinto del corte del manifiesto {corte!r}")
    if estado not in ("verificada", "no_verificada"):
        errores.append(f"cobertura.estado {estado!r} no admitido (verificada|no_verificada)")
    if hasta is not None and not _fecha_iso(hasta):
        errores.append(f"cobertura.datos_observados_hasta {hasta!r} no es una fecha ISO")
    elif estado == "verificada" and (hasta is None or hasta < corte):
        errores.append(f"cobertura: se declara verificada pero los datos solo llegan a {hasta!r}, antes del corte {corte}")
    if not cob.get("fuente"):
        errores.append("cobertura.fuente: falta la procedencia de la cobertura")
    if estimadas and estado != "verificada":
        errores.append(f"cobertura: {len(estimadas)} predicciones estimadas con cobertura '{estado}'; el modelo debe abstenerse")
    for f in estimadas:
        if hasta and _fecha_iso(hasta) and f.get("datos_hasta") and f["datos_hasta"] > hasta:
            errores.append(f"predicciones_clientes[{f.get('cliente_id')}]: datos_hasta {f['datos_hasta']} posterior a la cobertura {hasta}")
            break
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
    if (d / ".publicacion_en_curso.json").exists():
        r.errores.append("La publicación está en curso o quedó interrumpida (.publicacion_en_curso.json); no se lee. "
                         "Vuelve a ejecutar el generador, que restituye la versión anterior, o usa "
                         "'python -m pipeline.generar --recuperar --salida <dir>'.")
        return r, datos
    datos["manifiesto"] = manifiesto
    for nombre, declarada in manifiesto["tablas"].items():
        archivo = d / declarada["archivo"]
        if not archivo.resolve().is_relative_to(d.resolve()):
            r.errores.append(f"{nombre}: ruta fuera del directorio de publicación")
            continue
        if declarada.get("sha256"):
            import hashlib
            try:
                real = hashlib.sha256(archivo.read_bytes()).hexdigest()
            except FileNotFoundError:
                real = None
            if real is not None and real != declarada["sha256"]:
                r.errores.append(f"{nombre}: el contenido no coincide con la huella del manifiesto (publicación incompleta o alterada)")
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
    if "predicciones_clientes" in datos:
        r.errores.extend(validar_predicciones(datos["predicciones_clientes"], datos.get("agenda"), manifiesto))
    r.errores.extend(validar_cobertura(manifiesto, datos.get("predicciones_clientes")))
    return r, datos


def validar_recomendaciones(filas: list, cobertura: list, manifiesto: dict) -> list[str]:
    """Semántica de ``recomendaciones_productos`` (M4) frente a su informe ``cobertura_recomendaciones`` y al manifiesto."""
    e: list[str] = []
    if not isinstance(filas, list) or not isinstance(cobertura, list):
        return ["recomendaciones_productos y cobertura_recomendaciones deben ser listas"]
    mod = manifiesto.get("modelo") or {}
    vers = manifiesto.get("versiones") or {}
    cob = {c.get("cliente_id"): c for c in cobertura if isinstance(c, dict)}
    por_cliente: dict = {}
    for i, f in enumerate(filas):
        if not isinstance(f, dict):
            continue
        r = f"recomendaciones_productos[{i}]"
        por_cliente.setdefault(f.get("cliente_id"), []).append(f)
        if f.get("modelo_id") != "venta_cruzada" or f.get("horizonte_dias") != 60:
            e.append(f"{r}: modelo_id venta_cruzada y horizonte_dias 60 obligatorios")
        if f.get("corte") != manifiesto.get("corte"):
            e.append(f"{r}.corte distinto del manifiesto")
        if f.get("version_modelo") != mod.get("version"):
            e.append(f"{r}.version_modelo {f.get('version_modelo')!r} distinta de la del manifiesto")
        if f.get("version_reglas") != vers.get("reglas") or f.get("version_catalogo") != vers.get("catalogo"):
            e.append(f"{r}: versiones de reglas o catálogo distintas del manifiesto")
        pt, pr = f.get("puntaje"), f.get("probabilidad")
        if isinstance(pt, bool) or not isinstance(pt, (int, float)) or not math.isfinite(pt):
            e.append(f"{r}.puntaje no finito")
        if pr is not None and (isinstance(pr, bool) or not isinstance(pr, (int, float)) or not 0 <= pr <= 1):
            e.append(f"{r}.probabilidad fuera de [0, 1]")
        if not isinstance(f.get("soporte"), int) or f["soporte"] < 0:
            e.append(f"{r}.soporte entero >= 0")
        if not f.get("motivos"):
            e.append(f"{r}.motivos vacío")
        c = cob.get(f.get("cliente_id"))
        if c is None or c.get("estado") != "con_recomendaciones":
            e.append(f"{r}: el cliente no figura con recomendaciones en cobertura_recomendaciones")
        elif any(x.get("producto_id") == f.get("producto_id") for x in c.get("exclusiones") or []):
            e.append(f"{r}: recomienda {f.get('producto_id')}, que está excluido para el cliente")
    orden_origen = {"modelo": 0, "popularidad": 0, "coocurrencia": 0, "popularidad_sin_soporte": 1}
    for cid, fs in por_cliente.items():
        fs = sorted(fs, key=lambda f: f.get("posicion") if isinstance(f.get("posicion"), int) else 99)
        if len(fs) > 3 or len({f.get("producto_id") for f in fs}) != len(fs):
            e.append(f"{cid}: más de tres productos o productos repetidos")
        if [f.get("posicion") for f in fs] != list(range(1, len(fs) + 1)):
            e.append(f"{cid}: posiciones {[f.get('posicion') for f in fs]} no son 1..n")
        for a, b in zip(fs, fs[1:]):
            oa, ob = orden_origen.get(a.get("origen_recomendacion"), 9), orden_origen.get(b.get("origen_recomendacion"), 9)
            if oa > ob or (oa == ob and isinstance(a.get("puntaje"), (int, float)) and isinstance(b.get("puntaje"), (int, float))
                           and (a["puntaje"] < b["puntaje"] or (a["puntaje"] == b["puntaje"] and str(a.get("producto_id")) > str(b.get("producto_id"))))):
                e.append(f"{cid}: posiciones incoherentes con el ranking ({a.get('producto_id')} antes que {b.get('producto_id')})")
        c = cob.get(cid)
        if c is not None and c.get("n_recomendaciones") != len(fs):
            e.append(f"{cid}: cobertura declara {c.get('n_recomendaciones')} recomendaciones y hay {len(fs)}")
    for cid, c in cob.items():
        if c.get("estado") == "con_recomendaciones" and cid not in por_cliente:
            e.append(f"{cid}: cobertura con recomendaciones sin filas")
        if c.get("estado") != "con_recomendaciones" and (c.get("n_recomendaciones") or not c.get("motivo")):
            e.append(f"{cid}: estado {c.get('estado')!r} exige 0 recomendaciones y un motivo")
        if c.get("corte") != manifiesto.get("corte"):
            e.append(f"cobertura_recomendaciones[{cid}].corte distinto del manifiesto")
    return e[:60]


def _sumar_meses(p: str, n: int) -> str:
    t = int(p[:4]) * 12 + int(p[5:7]) - 1 + n
    return f"{t // 12}-{t % 12 + 1:02d}"


def validar_pronosticos(filas: list, calendario: list, manifiesto: dict) -> list[str]:
    """Semántica de ``pronosticos_demanda`` (M5) y su ``calendario_demanda``."""
    e: list[str] = []
    if not isinstance(filas, list) or not isinstance(calendario, list):
        return ["pronosticos_demanda y calendario_demanda deben ser listas"]
    mod = manifiesto.get("modelo") or {}
    unidades = {}
    for c in calendario:
        if not isinstance(c, dict):
            continue
        unidades.setdefault(c.get("serie_id"), set()).add(c.get("unidad"))
        if c.get("estado") == "completo" and not (isinstance(c.get("valor"), (int, float)) and math.isfinite(c["valor"]) and c["valor"] >= 0):
            e.append(f"calendario[{c.get('serie_id')} {c.get('periodo')}]: mes completo con valor no finito, negativo o nulo")
        if c.get("estado") != "completo" and (c.get("valor") is not None or not c.get("motivo")):
            e.append(f"calendario[{c.get('serie_id')} {c.get('periodo')}]: estado {c.get('estado')!r} exige valor null y motivo (no se imputan ceros)")
    totales: dict = {}
    for i, f in enumerate(filas):
        if not isinstance(f, dict):
            continue
        r = f"pronosticos_demanda[{i}]"
        h, o, obj = f.get("horizonte_meses"), str(f.get("origen")), str(f.get("periodo_objetivo"))
        if h not in (1, 2, 3) or len(o) != 7 or obj != _sumar_meses(o, h if isinstance(h, int) else 0):
            e.append(f"{r}: periodo_objetivo {obj} no es origen {o} + {h} meses calendario")
        if o != manifiesto.get("origen"):
            e.append(f"{r}.origen distinto del manifiesto")
        if f.get("version_modelo") != mod.get("version"):
            e.append(f"{r}.version_modelo distinta del manifiesto")
        v = f.get("valor")
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0):
            e.append(f"{r}.valor no finito o negativo")
        if (v is None) != (f.get("estado") in ("sin_historia", "total_incompleto")) or (v is None and not f.get("motivos")):
            e.append(f"{r}: estado {f.get('estado')!r} incoherente con valor {v!r} o nulo sin motivo")
        sid = str(f.get("serie_id", ""))
        medida_ok = (sid.startswith("ventas_cop:") and f.get("unidad") == "COP") or (sid.startswith("ventas_unidades:") and f.get("unidad") != "COP") \
            or (sid.startswith("compras_proveedores_cop:") and f.get("unidad") == "COP")
        if not medida_ok or (sid in unidades and f.get("unidad") not in unidades[sid]):
            e.append(f"{r}: unidad {f.get('unidad')!r} incoherente con la serie {sid}")
        lo, hi = f.get("banda_inferior"), f.get("banda_superior")
        if (lo is None) != (hi is None):
            e.append(f"{r}: banda incompleta")
        elif lo is not None and not (isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 0 <= lo <= hi and f.get("banda_soporte", 0) >= 12 and f.get("banda_metodo")):
            e.append(f"{r}: banda desordenada, negativa o sin soporte (>= 12 errores) y método")
        elif lo is None and not f.get("banda_motivo"):
            e.append(f"{r}: banda nula sin motivo")
        if sid.startswith("ventas_cop:") and sid != "ventas_cop:Total":
            totales.setdefault(h, []).append(v)
    for f in filas:
        if isinstance(f, dict) and f.get("serie_id") == "ventas_cop:Total":
            partes = totales.get(f.get("horizonte_meses"), [])
            if f.get("valor") is not None and (None in partes or abs(round(sum(partes), 2) - f["valor"]) > 0.005):
                e.append(f"Total h{f.get('horizonte_meses')}: {f['valor']} no es la suma de las familias publicadas")
            if f.get("valor") is None and partes and None not in partes:
                e.append(f"Total h{f.get('horizonte_meses')}: nulo aunque todas las familias tienen valor")
    return e[:60]


def validar_anomalias(filas: list, cobertura: list, manifiesto: dict) -> list[str]:
    """Semántica de ``anomalias_operaciones`` (M6) y ``cobertura_anomalias``: identidades, finitud, abstención, ranking,
    cupo, conteos reconciliados, universo, versión y corte."""
    e: list[str] = []
    if not isinstance(filas, list) or not isinstance(cobertura, list):
        return ["anomalias_operaciones y cobertura_anomalias deben ser listas"]
    mod = manifiesto.get("modelo") or {}
    metodos = mod.get("metodos_publicados") or {}
    # M6: ranking con cupo (el cupo siempre se llena). M6.1: cupo MÁXIMO, solo operaciones con evidencia (señaladas) y primero.
    con_evidencia = (manifiesto.get("politica_alertas") or {}).get("tipo") == "cupo_maximo_con_evidencia"
    orden = (lambda f: (not f.get("senalada_por_reglas"), -f["puntaje"], f["fecha"], f["operacion_id"])) if con_evidencia else         (lambda f: (-f["puntaje"], f["fecha"], f["operacion_id"]))
    por: dict = {}
    for i, f in enumerate(filas):
        if not isinstance(f, dict):
            continue
        r = f"anomalias_operaciones[{i}]"
        u = f.get("tipo_operacion")
        if f.get("version_modelo") != mod.get("version") or f.get("corte") != manifiesto.get("corte"):
            e.append(f"{r}: versión o corte distintos del manifiesto")
        if not (isinstance(f.get("fecha"), str) and f["fecha"] <= str(manifiesto.get("corte")) and f["fecha"][:7] == f.get("periodo")):
            e.append(f"{r}: fecha posterior al corte o periodo incoherente")
        for k in ("cantidad", "valor_unitario", "importe_origen", "importe_cop", "trm", "puntaje", "puntaje_referencia", "puntaje_candidato",
                  "referencia_cantidad", "referencia_valor_unitario", "razon_cantidad", "razon_valor_unitario"):
            v = f.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)):
                e.append(f"{r}.{k} no finito")
        if not (isinstance(f.get("cantidad"), (int, float)) and f["cantidad"] > 0 and isinstance(f.get("valor_unitario"), (int, float)) and f["valor_unitario"] > 0):
            e.append(f"{r}: cantidad y valor unitario deben ser > 0")
        if u == "compra" and f.get("cliente_id") is not None:
            e.append(f"{r}: una compra no lleva cliente_id")
        if f.get("estado_trm") == "ausente" and f.get("importe_cop") is not None:
            e.append(f"{r}: TRM ausente con importe COP (no se sustituye la TRM)")
        punt = f.get("estado_puntuacion") == "puntuada"
        if punt != (f.get("puntaje") is not None) or (not punt and (f.get("alerta") or f.get("prioridad") is not None or f.get("metodo") is not None)):
            e.append(f"{r}: estado {f.get('estado_puntuacion')!r} incoherente con puntaje, prioridad, alerta o método (abstención = nulos)")
        if punt and (f.get("puntaje") < 0 or f.get("metodo") != metodos.get(u)):
            e.append(f"{r}: puntaje negativo o método distinto del publicado para {u}")
        if punt and not f.get("motivos"):
            e.append(f"{r}: puntuada sin motivos")
        por.setdefault((u, f.get("periodo")), []).append(f)
    for (u, p), fs in por.items():
        punt = sorted((f for f in fs if f.get("estado_puntuacion") == "puntuada"), key=lambda f: f.get("prioridad") or 0)
        if [f.get("prioridad") for f in punt] != list(range(1, len(punt) + 1)):
            e.append(f"{u} {p}: prioridades no consecutivas desde 1")
        elif any(orden(a) > orden(b) for a, b in zip(punt, punt[1:])):
            e.append(f"{u} {p}: el orden no sigue {'evidencia y ' if con_evidencia else ''}puntaje descendente con desempate estable (fecha, operacion_id)")
        k = {f.get("cupo_periodo") for f in fs}
        if len(k) != 1:
            e.append(f"{u} {p}: cupo_periodo distinto entre filas")
            continue
        k = k.pop()
        if any(f.get("alerta") != (f.get("prioridad") is not None and f["prioridad"] <= k and (f.get("senalada_por_reglas") or not con_evidencia)) for f in fs):
            e.append(f"{u} {p}: alerta incoherente con prioridad <= cupo {k}{' y evidencia' if con_evidencia else ''}")
    vistos = set()
    for c in cobertura:
        if not isinstance(c, dict):
            continue
        key = (c.get("tipo_operacion"), c.get("periodo"))
        vistos.add(key)
        fs = por.get(key, [])
        punt = sum(f.get("estado_puntuacion") == "puntuada" for f in fs)
        abst = sum((c.get("abstenciones") or {}).values()) if isinstance(c.get("abstenciones"), dict) else -1
        if c.get("validas") != len(fs) or c.get("puntuadas") != punt or punt + abst != c.get("validas") or c.get("alertas") != sum(bool(f.get("alerta")) for f in fs):
            e.append(f"cobertura_anomalias[{key}]: conteos no reconciliados con las filas")
        elegibles = sum(f.get("estado_puntuacion") == "puntuada" and (f.get("senalada_por_reglas") or not con_evidencia) for f in fs)
        if c.get("alertas", 0) > c.get("cupo", 0) or (punt and c.get("alertas") != min(c.get("cupo", 0), elegibles)):
            e.append(f"cobertura_anomalias[{key}]: alertas distintas de min(cupo, {'puntuadas con evidencia' if con_evidencia else 'puntuadas'})")
        if c.get("exceso_sobre_cupo") != sum(1 for f in fs if f.get("senalada_por_reglas") and not f.get("alerta")):
            e.append(f"cobertura_anomalias[{key}]: exceso_sobre_cupo no coincide con las señaladas fuera del cupo")
        if (c.get("tipo_operacion") == "compra") != (c.get("cobertura_temporal") == "no_declarada"):
            e.append(f"cobertura_anomalias[{key}]: cobertura temporal mal declarada (ventas declarada, compras no declarada)")
    if set(por) - vistos:
        e.append(f"cobertura_anomalias: faltan universos/meses {sorted(set(por) - vistos)[:3]}")
    conteos = manifiesto.get("conteos") or {}
    if conteos and any(conteos.get(u, 0) != sum(1 for f in filas if isinstance(f, dict) and f.get("tipo_operacion") == u) for u in ("venta", "compra")):
        e.append("manifiesto de sombra: conteos por universo distintos de las filas")
    if set(metodos) != {"venta", "compra"} or not set(metodos.values()) <= {"isolation_forest", "mediana_mad"}:
        e.append("manifiesto de sombra: modelo.metodos_publicados debe declarar el método de venta y de compra")
    return e[:60]


def validar_publicacion_sombra(manifiesto: dict, filas) -> list[str]:
    """Publicación EN SOMBRA de un modelo experimental (no es un cierre C2 operativo ni contiene agenda).

    Exige ``tipo = publicacion_sombra``, ``operativa = false``, un único ``modelo_id`` y las mismas reglas de tabla,
    predicciones y cobertura que ``predicciones_clientes`` en C2."""
    errores: list[str] = []
    if not isinstance(manifiesto, dict):
        return ["manifiesto de sombra: debe ser un objeto"]
    if manifiesto.get("tipo") != "publicacion_sombra" or manifiesto.get("version") != 1:
        errores.append("manifiesto de sombra: tipo/version distintos de publicacion_sombra v1")
    if manifiesto.get("operativa") is not False:
        errores.append("manifiesto de sombra: 'operativa' debe ser false (las variantes experimentales no se mezclan con el cierre)")
    if not manifiesto.get("estado_experimento"):
        errores.append("manifiesto de sombra: falta estado_experimento")
    modelo = manifiesto.get("modelo_id")
    if modelo not in HORIZONTE_MODELO and modelo not in ("venta_cruzada", "demanda", "anomalias"):
        errores.append(f"manifiesto de sombra: modelo_id {modelo!r} desconocido")
    if not _fecha_iso(manifiesto.get("corte")):
        errores.append("manifiesto de sombra: corte no es una fecha ISO")
    if modelo == "anomalias":  # M6: cola de operaciones atípicas y cobertura por universo y mes
        if not isinstance(filas, dict):
            return errores + ["anomalias: se esperan las tablas anomalias_operaciones y cobertura_anomalias"]
        esquema = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]
        for t in ("anomalias_operaciones", "cobertura_anomalias"):
            errores.extend(validar_tabla(t, filas.get(t), esquema[t], (manifiesto.get("tablas") or {}).get(t) or {"filas": None}))
        errores.extend(validar_anomalias(filas.get("anomalias_operaciones"), filas.get("cobertura_anomalias"), manifiesto))
        mod = manifiesto.get("modelo") or {}
        if not mod.get("version") or not mod.get("artefacto_huella"):
            errores.append("manifiesto de sombra: modelo.version y modelo.artefacto_huella son obligatorios")
        dec = mod.get("decision")
        if isinstance(dec, dict) and dec.get("artefacto_huella") not in (None, mod.get("artefacto_huella")):
            errores.append("manifiesto de sombra: la decisión corresponde a otro artefacto")
        if not isinstance((manifiesto.get("datos") or {}).get("huella_datos"), str):
            errores.append("manifiesto de sombra: falta la huella de datos")
        errores.extend(validar_cobertura(manifiesto, []))
        return errores
    if modelo == "demanda":  # M5: pronósticos por serie y calendario
        if not isinstance(filas, dict):
            return errores + ["demanda: se esperan las tablas pronosticos_demanda y calendario_demanda"]
        esquema = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]
        for t in ("pronosticos_demanda", "calendario_demanda"):
            errores.extend(validar_tabla(t, filas.get(t), esquema[t], (manifiesto.get("tablas") or {}).get(t) or {"filas": None}))
        errores.extend(validar_pronosticos(filas.get("pronosticos_demanda"), filas.get("calendario_demanda"), manifiesto))
        mod = manifiesto.get("modelo") or {}
        if not mod.get("version") or not mod.get("artefacto_huella"):
            errores.append("manifiesto de sombra: modelo.version y modelo.artefacto_huella son obligatorios")
        errores.extend(validar_cobertura(manifiesto, []))
        return errores
    if modelo == "venta_cruzada":  # M4: tablas de recomendaciones y cobertura (no predicciones_clientes)
        if not isinstance(filas, dict):
            return errores + ["venta_cruzada: se esperan las tablas recomendaciones_productos y cobertura_recomendaciones"]
        esquema = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]
        for t in ("recomendaciones_productos", "cobertura_recomendaciones"):
            errores.extend(validar_tabla(t, filas.get(t), esquema[t], (manifiesto.get("tablas") or {}).get(t) or {"filas": None}))
        errores.extend(validar_recomendaciones(filas.get("recomendaciones_productos"), filas.get("cobertura_recomendaciones"), manifiesto))
        conteos = manifiesto.get("conteos") or {}
        if conteos and isinstance(filas.get("cobertura_recomendaciones"), list) and sum(conteos.values()) != len(filas["cobertura_recomendaciones"]):
            errores.append("manifiesto de sombra: conteos distintos del informe de cobertura")
        mod = manifiesto.get("modelo") or {}
        if not mod.get("version") or not mod.get("artefacto_huella"):
            errores.append("manifiesto de sombra: modelo.version y modelo.artefacto_huella son obligatorios")
        dec = mod.get("decision")
        if isinstance(dec, dict) and dec.get("artefacto_huella") not in (None, mod.get("artefacto_huella")):
            errores.append("manifiesto de sombra: la decisión corresponde a otro artefacto")
        errores.extend(validar_cobertura(manifiesto, []))
        return errores
    definicion = cargar_esquema("publicacion.v1.schema.json")["tablas_conocidas"]["predicciones_clientes"]
    declarada = (manifiesto.get("tablas") or {}).get("predicciones_clientes") or {"filas": None}
    errores.extend(validar_tabla("predicciones_clientes", filas, definicion, declarada))
    if isinstance(filas, list):
        if any(isinstance(f, dict) and f.get("modelo_id") != modelo for f in filas):
            errores.append(f"predicciones_clientes: todas las filas deben ser de {modelo}")
        errores.extend(validar_predicciones(filas, None, manifiesto))
        errores.extend(_coherencia_sombra(manifiesto, filas))
    errores.extend(validar_cobertura(manifiesto, filas))
    return errores


def _coherencia_sombra(manifiesto: dict, filas: list) -> list[str]:
    """Versión, modelo, corte, conteos y decisión del manifiesto deben concordar con las filas y el artefacto."""
    e: list[str] = []
    mod = manifiesto.get("modelo") or {}
    if not mod.get("version") or not mod.get("artefacto_huella"):
        e.append("manifiesto de sombra: modelo.version y modelo.artefacto_huella son obligatorios")
    versiones = {f.get("version_modelo") for f in filas if isinstance(f, dict) and f.get("version_modelo") is not None}
    if versiones - {mod.get("version")}:
        e.append(f"predicciones_clientes: versiones {sorted(versiones - {mod.get('version')})} distintas de la del manifiesto {mod.get('version')!r}")
    dec = mod.get("decision")
    if isinstance(dec, dict) and dec.get("artefacto_huella") not in (None, mod.get("artefacto_huella")):
        e.append("manifiesto de sombra: la decisión corresponde a otro artefacto")
    conteos = manifiesto.get("conteos")
    if isinstance(conteos, dict) and conteos and all(isinstance(v, int) for v in conteos.values()) and sum(conteos.values()) != len(filas):
        e.append(f"manifiesto de sombra: los conteos suman {sum(conteos.values())} y hay {len(filas)} filas")
    return e


def leer_publicacion_sombra(directorio) -> tuple[list[str], dict, list]:
    """Lee y valida un directorio de sombra: huellas del marcador, contrato y coherencia. (errores, manifiesto, filas)."""
    import hashlib
    d = Path(directorio)
    try:
        manifiesto = leer_json(d / "manifiesto.json")
    except (OSError, json.JSONDecodeError) as e:
        return [f"manifiesto de sombra ilegible o ausente: {e}"], {}, []
    errores = []
    from modelos.ejecucion import sello as _sello  # biblioteca estándar: mismo cálculo que el publicador
    if not isinstance(manifiesto, dict) or not manifiesto.get("sello") or _sello(manifiesto) != manifiesto.get("sello"):
        return ["manifiesto de sombra: el sello no coincide con su contenido (manifiesto alterado o sin sellar)"], manifiesto if isinstance(manifiesto, dict) else {}, []
    for nombre, h in (manifiesto.get("archivos") or {}).items():
        archivo = d / nombre
        if not archivo.resolve().is_relative_to(d.resolve()) or not archivo.exists():
            errores.append(f"{nombre}: falta o está fuera del directorio de sombra")
        elif hashlib.sha256(archivo.read_bytes()).hexdigest() != h:
            errores.append(f"{nombre}: el contenido no coincide con la huella del manifiesto de sombra (alterado)")
    venta_cruzada = manifiesto.get("modelo_id") in ("venta_cruzada", "demanda", "anomalias")
    requeridos = {"venta_cruzada": ("recomendaciones_productos.json", "cobertura_recomendaciones.json"),
                  "demanda": ("pronosticos_demanda.json", "calendario_demanda.json"),
                  "anomalias": ("anomalias_operaciones.json", "cobertura_anomalias.json")}.get(manifiesto.get("modelo_id"), ("predicciones_clientes.json",))
    for nombre in requeridos:
        if nombre not in (manifiesto.get("archivos") or {}):
            errores.append(f"manifiesto de sombra: no registra la huella de {nombre}")
    if errores:
        return errores, manifiesto, []
    if venta_cruzada:
        filas = {n[:-5]: leer_json(d / n) for n in requeridos}
        if "muestra_revision.json" in (manifiesto.get("archivos") or {}):
            filas["muestra_revision"] = leer_json(d / "muestra_revision.json")
        return validar_publicacion_sombra(manifiesto, filas), manifiesto, filas
    filas = leer_json(d / "predicciones_clientes.json")
    return validar_publicacion_sombra(manifiesto, filas), manifiesto, filas


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
