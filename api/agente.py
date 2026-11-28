"""Agente de consultas sobre datos, documentos y PQRS como grafo LangGraph (B07/B10).

    interpretar ──► aclarar ──────────────┐
         │      └─► denegar ──────────────┤
         └────────► ejecutar ─► redactar ─┴─► registrar ─► FIN

* ``interpretar``: reglas deterministas (y, si fallan, el modelo LangChain limitado a
  intenciones permitidas) traducen la pregunta a intención y parámetros tipados.
* ``ejecutar``: herramientas de SOLO LECTURA; el servicio calcula cifras y variaciones.
  Identidad y alcance proceden de la sesión, nunca de la pregunta.
* ``redactar``: plantilla determinista + redacción opcional (Gemini → Anthropic).
* ``registrar``: herramienta, latencia, estado y versión con contenido mínimo.

Si ``langgraph`` no está instalado se ejecutan los mismos nodos en secuencia.
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from typing import Any, Optional, TypedDict

from . import atencion, consultas, documentos, llm
from .base import ErrorApi, ahora, bandera, dumps
from .publicacion import filas, resolver_cierre

LIMITE_FILAS = 50
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
INDICADORES = {
    "frio": "Cliente frío: 90 días o más sin compra confirmada al corte (parámetro editable). Puede coincidir con frecuente.",
    "frecuente": "Cliente frecuente: al menos 8 operaciones confirmadas acumuladas al corte.",
    "ingreso": "Ingreso COP: suma de cantidad × precio × (1 − descuento/100) de ventas confirmadas; USD convertido con la tasa de su fecha.",
    "probabilidad": "Probabilidad de compra a 30 días: estimación de un modelo evaluado temporalmente; mide propensión, no garantiza una venta.",
    "cobertura": "Renovación próxima: fin de cobertura entre el corte y los 45 días siguientes, ambos incluidos. Vencida: fin anterior al corte.",
    "recencia": "Recencia: días entre la última compra confirmada y la fecha de corte.",
}
INTENCIONES_MODELOS = {"modelo_inactividad", "modelo_proxima", "modelo_venta_cruzada", "modelo_demanda", "modelo_anomalias",
                       "modelo_monitoreo", "modelo_resultados"}
INTENCIONES_DATOS = {"historial_cliente", "productos_cliente", "ventas_periodo", "compras_proveedor", "oportunidades",
                     "explicar_indicador", "clientes_reducen"} | INTENCIONES_MODELOS
INTENCIONES_PORTAL = {"portal"}


class Estado(TypedDict, total=False):
    pregunta: str
    ctx: Any                      # {"con": sqlite3.Connection, "usuario": Usuario, "cierre": str}
    inicio: float
    intencion: Optional[str]
    parametros: dict
    aclaracion: Optional[str]
    respuesta: dict
    version: str


# ---------------------------------------------------------------- interpretación
def _periodos(t: str, anio_defecto: int) -> list[str]:
    encontrados: list[tuple[int, str]] = []
    for m in re.finditer(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", t):
        encontrados.append((m.start(), f"{m.group(1)}-{m.group(2)}"))
    for m in re.finditer(r"\b(" + "|".join(MESES) + r")\b(?:\s+(?:de|del)?\s*(20\d{2}))?", t):
        encontrados.append((m.start(), f"{m.group(2) or anio_defecto}-{MESES[m.group(1)]:02d}"))
    return [p for _, p in sorted(encontrados)]


def interpretar_reglas(pregunta: str, anio_defecto: int, externo: bool) -> tuple[str | None, dict, str | None]:
    """Devuelve (intencion, parametros, aclaracion)."""
    t = documentos.normalizar(pregunta)
    if externo:
        return "portal", {"pregunta": pregunta}, None
    if re.search(r"pqrs-\d{8}-\d{5}|\bmi caso\b|\bbeneficio|\bpolitica|\bgarantia", t):
        return "portal", {"pregunta": pregunta}, None
    cliente = re.search(r"\b(cli\d{3}|demo\d{2})\b", t)
    periodos = _periodos(t, anio_defecto)
    modelo = interpretar_modelos(t, cliente)
    if modelo:
        return modelo[0], modelo[1], None
    for clave, _ in INDICADORES.items():
        if re.search(r"que (significa|es)|explica|definicion|como se calcula", t) and clave in t:
            return "explicar_indicador", {"indicador": clave}, None
    if re.search(r"redujeron|disminuyeron|bajaron|redujo|cayeron", t):
        if len(periodos) < 2:
            return None, {}, "Indica los dos periodos comparables, por ejemplo «entre agosto y septiembre de 2026»."
        return "clientes_reducen", {"base": periodos[0], "comparado": periodos[1]}, None
    if re.search(r"oportunidad|prioridad|seguimiento|agenda", t):
        return "oportunidades", {"cliente_id": cliente.group(1).upper() if cliente else None}, None
    if cliente:
        if re.search(r"compr|producto|adquiri", t):
            return "productos_cliente", {"cliente_id": cliente.group(1).upper()}, None
        return "historial_cliente", {"cliente_id": cliente.group(1).upper()}, None
    if "proveedor" in t:
        if not periodos:
            return None, {}, "¿De qué periodo? Por ejemplo «compras a proveedores en agosto de 2026»."
        return "compras_proveedor", {"desde": periodos[0], "hasta": periodos[-1]}, None
    if re.search(r"\bventa|\bvendi|\bingreso|\bfactur", t):
        if not periodos:
            return None, {}, "¿De qué periodo? Por ejemplo «ventas de septiembre de 2026»."
        fam = re.search(r"familia\s+(\w+)", t)
        return "ventas_periodo", {"desde": periodos[0], "hasta": periodos[-1], "familia": fam.group(1).capitalize() if fam else "Total"}, None
    if re.search(r"\bcompra", t):
        return None, {}, ("«Compras» puede referirse a ventas a clientes o a adquisiciones a proveedores. "
                          "¿Cuál necesitas? Indica también el periodo.")
    return None, {}, None


def interpretar_modelos(t: str, cliente) -> tuple[str, dict] | None:
    """Preguntas sobre los modelos de IA (se evalúan antes que «compras» y «ventas»)."""
    if re.search(r"monitoreo|avisos? de (los )?modelos?|estado de (los )?modelos?|salud de(l| los) modelos?", t):
        return "modelo_monitoreo", {}
    if re.search(r"(que|cuales) modelos|resultados de (los )?modelos|modelos de ia|como (les )?(va|fue) a (los )?modelos", t):
        return "modelo_resultados", {}
    if re.search(r"inactividad|dejar de comprar|dejen de comprar|riesgo de (perder|abandono)|abandon", t):
        return "modelo_inactividad", {}
    if re.search(r"proxima compra|cuando (va a|volvera a|podria) comprar|ventana de compra", t):
        return "modelo_proxima", {}
    if re.search(r"venta cruzada|recomendaci|productos? complementari|que (mas|otro producto) (le )?(podria|puedo) (venderle|ofrecer)", t):
        return "modelo_venta_cruzada", {"cliente_id": cliente.group(1).upper() if cliente else None}
    if re.search(r"pronostico|proyeccion|demanda", t):
        return "modelo_demanda", {"serie": "ventas_unidades:" + m.group(1).upper() if (m := re.search(r"\b(pro\d{2})\b", t)) else None}
    if re.search(r"atipic|anomal|inusual", t):
        return "modelo_anomalias", {"universo": "compra" if re.search(r"compras? (a )?proveedor|\bcompras atipic|proveedor", t) else "venta"}
    return None


def _interpretar_llm(pregunta: str) -> tuple[str | None, dict]:
    modelo = llm.modelo_chat()
    if modelo is None:
        return None, {}
    from langchain_core.messages import HumanMessage, SystemMessage
    instr = ("Clasifica la pregunta en UNA intención de esta lista y extrae parámetros. Responde solo JSON "
             '{"intencion": ..., "parametros": {...}}. Intenciones: historial_cliente{cliente_id}, productos_cliente{cliente_id}, '
             "ventas_periodo{desde:YYYY-MM,hasta:YYYY-MM,familia}, compras_proveedor{desde,hasta}, oportunidades{cliente_id?}, "
             "explicar_indicador{indicador: frio|frecuente|ingreso|probabilidad|cobertura|recencia}, "
             'clientes_reducen{base,comparado}, ninguna{}. Si falta un dato obligatorio usa "ninguna".')
    try:
        r = modelo.invoke([SystemMessage(content=instr), HumanMessage(content=pregunta)])
        crudo = llm._texto(r)
        datos = json.loads(crudo[crudo.find("{"): crudo.rfind("}") + 1])
    except Exception:
        return None, {}
    intencion = datos.get("intencion")
    if intencion not in INTENCIONES_DATOS or not isinstance(datos.get("parametros"), dict):
        return None, {}
    return intencion, datos["parametros"]


def nodo_interpretar(s: Estado) -> Estado:
    ctx = s["ctx"]
    u = ctx["usuario"]
    try:
        anio = int(resolver_cierre(ctx["con"], ctx.get("cierre") or "activo")["corte"][:4])
    except ErrorApi:
        anio = 2026
    intencion, params, aclaracion = interpretar_reglas(s["pregunta"], anio, u.externo)
    if intencion is None and aclaracion is None:
        intencion, params = _interpretar_llm(s["pregunta"])
    return {"intencion": intencion, "parametros": params or {}, "aclaracion": aclaracion}


def ruta(s: Estado) -> str:
    u = s["ctx"]["usuario"]
    if s.get("aclaracion"):
        return "aclarar"
    if s.get("intencion") is None:
        return "aclarar"
    if s["intencion"] in INTENCIONES_DATOS and not u.puede("agente.datos"):
        return "denegar"
    if s["intencion"] in INTENCIONES_PORTAL and not (u.puede("agente.portal") or u.puede("documentos.consultar")):
        return "denegar"
    return "ejecutar"


def _resp(estado: str, herramienta, parametros, resultado=None, evidencia=None, texto="") -> dict:
    return {"estado": estado, "herramienta": herramienta, "parametros": parametros or {}, "resultado": resultado,
            "evidencia": evidencia or {"filtros": {}, "fuentes": []}, "texto": texto}


def nodo_aclarar(s: Estado) -> Estado:
    texto = s.get("aclaracion") or ("No pude identificar la consulta. Prueba con un ID de cliente, un periodo "
                                    "(«ventas de septiembre de 2026») o usa los filtros de la agenda.")
    return {"respuesta": _resp("aclaracion", None, s.get("parametros"), texto=texto)}


def nodo_denegar(s: Estado) -> Estado:
    return {"respuesta": _resp("no_autorizado", s.get("intencion"), {}, texto="Tu rol no tiene acceso a esa consulta.")}


# ---------------------------------------------------------------- herramientas
def _evid(cierre, unidad, filtros, detalle=None, fuentes=None) -> dict:
    return {"cierre_id": cierre["id"], "corte": cierre["corte"], "unidad": unidad, "filtros": filtros,
            "detalle": detalle, "fuentes": fuentes or []}


def _cop(x) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " COP"


def herramienta_historial(con, cierre, p) -> dict:
    try:
        f = consultas.ficha(con, cierre["id"], p["cliente_id"])
    except ErrorApi:
        return _resp("no_encontrado", "historial_cliente", p, evidencia=_evid(cierre, None, p),
                     texto=f"Cliente {p['cliente_id']} no encontrado en el cierre {cierre['corte']}; no se inventa historial.")
    c = f["cliente"]
    res = {k: c.get(k) for k in ("cliente_id", "ultima_compra", "dias_sin_compra", "ventas_confirmadas", "ingreso_cop",
                                 "frecuente", "frio", "prob_compra_30d", "accion", "motivos", "prediccion")}
    if c["sin_historial"]:
        texto = f"{c['cliente_id']} existe en el cierre {cierre['corte']} pero no tiene compras confirmadas (sin historial)."
    else:
        texto = (f"{c['cliente_id']} al corte {cierre['corte']}: {c['ventas_confirmadas']} ventas confirmadas por {_cop(c['ingreso_cop'])}, "
                 f"última compra {c['ultima_compra']} ({c['dias_sin_compra']} días). Acción sugerida: {c['accion']}.")
    return _resp("ok", "historial_cliente", p, res, _evid(cierre, "COP", p, f"#/clientes/{c['cliente_id']}"), texto)


def herramienta_productos(con, cierre, p) -> dict:
    try:
        f = consultas.ficha(con, cierre["id"], p["cliente_id"])
    except ErrorApi:
        return _resp("no_encontrado", "productos_cliente", p, evidencia=_evid(cierre, None, p),
                     texto=f"Cliente {p['cliente_id']} no encontrado en el cierre {cierre['corte']}.")
    prods = f["productos"] or [{"producto": n, "operaciones": None, "importe_cop": None} for n in f["cliente"]["productos"]]
    if not prods:
        return _resp("sin_datos", "productos_cliente", p, [], _evid(cierre, "COP", p, f"#/clientes/{p['cliente_id']}"),
                     f"{p['cliente_id']} no registra compras confirmadas al corte {cierre['corte']}.")
    det = "; ".join(f"{x['producto']}" + (f" ({x['operaciones']} op., {_cop(x['importe_cop'])})" if x.get("operaciones") else "") for x in prods[:LIMITE_FILAS])
    return _resp("ok", "productos_cliente", p, prods[:LIMITE_FILAS], _evid(cierre, "COP", p, f"#/clientes/{p['cliente_id']}"),
                 f"Hasta el corte {cierre['corte']}, {p['cliente_id']} compró: {det}.")


def _serie(con, cierre, serie, familia, desde, hasta) -> tuple[list[dict], list[str]]:
    datos = [s for s in filas(con, cierre["id"], "series_mensuales")
             if s["serie"] == serie and s["tipo"] == "historico" and s["familia"] == familia and desde <= s["periodo"] <= hasta]
    incompletos = [s["periodo"] for s in datos if s.get("completo") is False or s["valor_cop"] is None]
    return sorted(datos, key=lambda s: s["periodo"]), incompletos


def herramienta_ventas(con, cierre, p) -> dict:
    datos, incompletos = _serie(con, cierre, "ventas", p.get("familia") or "Total", p["desde"], p["hasta"])
    filtros = {"periodo": f"{p['desde']}..{p['hasta']}", "familia": p.get("familia") or "Total", "estado": "Confirmada"}
    if not datos:
        return _resp("sin_datos", "ventas_periodo", p, evidencia=_evid(cierre, "COP", filtros),
                     texto=f"No hay datos de ventas publicados para {filtros['periodo']} en el cierre {cierre['corte']}.")
    total = round(sum(s["valor_cop"] or 0 for s in datos), 2)
    texto = f"Ventas confirmadas {filtros['familia']} {filtros['periodo']}: {_cop(total)} en {sum(s.get('operaciones') or 0 for s in datos)} operaciones."
    if incompletos:
        texto += f" Atención: periodo incompleto en {', '.join(incompletos)}; el total no lo incluye."
    return _resp("ok" if not incompletos else "sin_datos" if len(incompletos) == len(datos) else "ok", "ventas_periodo", p,
                 {"total_cop": total, "meses": datos, "incompletos": incompletos}, _evid(cierre, "COP", filtros, "#/finanzas"), texto)


def herramienta_compras(con, cierre, p) -> dict:
    filtros = {"periodo": f"{p['desde']}..{p['hasta']}", "tipo": "adquisiciones a proveedores"}
    sel = [c for c in filas(con, cierre["id"], "compras_proveedor") if p["desde"] <= c["fecha"][:7] <= p["hasta"]]
    if not sel:
        return _resp("sin_datos", "compras_proveedor", p, [], _evid(cierre, "COP", filtros),
                     f"No hay compras a proveedores publicadas para {filtros['periodo']}.")
    por = defaultdict(lambda: {"operaciones": 0, "importe_cop": 0.0})
    for c in sel:
        k = c.get("proveedor") or c["proveedor_id"]
        por[k]["operaciones"] += 1; por[k]["importe_cop"] += c["importe_cop"]
    lista = [{"proveedor": k, "operaciones": v["operaciones"], "importe_cop": round(v["importe_cop"], 2)} for k, v in sorted(por.items())]
    texto = f"Compras a proveedores {filtros['periodo']}: " + "; ".join(f"{x['proveedor']} ({x['operaciones']} op., {_cop(x['importe_cop'])})" for x in lista) + "."
    return _resp("ok", "compras_proveedor", p, lista[:LIMITE_FILAS], _evid(cierre, "COP", filtros, "#/finanzas"), texto)


def herramienta_oportunidades(con, cierre, p) -> dict:
    opps = filas(con, cierre["id"], "oportunidades", p.get("cliente_id")) if p.get("cliente_id") else filas(con, cierre["id"], "oportunidades")
    if not opps:
        ag = consultas.agenda(con, cierre["id"], q=p.get("cliente_id"), tam=10)
        opps = [{"cliente_id": c["cliente_id"], "tipo": c["accion"], "motivos": c["motivos"], "probabilidad": c["prob_compra_30d"]}
                for c in ag["items"] if c["accion"] != "Seguimiento habitual"]
    opps = sorted(opps, key=lambda o: (o.get("prioridad", 9), -(o.get("probabilidad") or -1), o["cliente_id"]))[:LIMITE_FILAS]
    if not opps:
        return _resp("sin_datos", "oportunidades", p, [], _evid(cierre, None, p), "No hay oportunidades abiertas para esa consulta.")
    texto = "Oportunidades al corte " + cierre["corte"] + ": " + "; ".join(
        f"{o['cliente_id']} – {', '.join(o['motivos'])}" for o in opps[:5]) + ". Son recomendaciones para revisar, no ventas confirmadas."
    return _resp("ok", "oportunidades", p, opps, _evid(cierre, None, p, "#/tareas"), texto)


def herramienta_reducen(con, cierre, p) -> dict:
    base, comp = p["base"], p["comparado"]
    filtros = {"base": base, "comparado": comp, "unidad": "COP ventas confirmadas"}
    ventas = filas(con, cierre["id"], "historial_ventas")
    if not ventas:
        return _resp("sin_datos", "clientes_reducen", p, evidencia=_evid(cierre, "COP", filtros),
                     texto="El cierre no publica el historial de ventas necesario para comparar periodos.")
    tot = defaultdict(lambda: [0.0, 0.0])
    for v in ventas:
        if v["fecha"][:7] == base:
            tot[v["cliente_id"]][0] += v["importe_cop"]
        elif v["fecha"][:7] == comp:
            tot[v["cliente_id"]][1] += v["importe_cop"]
    lista = []
    for cid, (b, c) in sorted(tot.items()):
        if c < b:
            lista.append({"cliente_id": cid, "base_cop": round(b, 2), "comparado_cop": round(c, 2), "cambio_cop": round(c - b, 2),
                          "cambio_pct": round((c - b) / b * 100, 2) if b else None})
    if not lista:
        return _resp("sin_datos", "clientes_reducen", p, [], _evid(cierre, "COP", filtros),
                     f"Ningún cliente redujo sus compras entre {base} y {comp}.")
    texto = f"Clientes que redujeron compras de {base} a {comp}: " + "; ".join(
        f"{x['cliente_id']} ({_cop(x['cambio_cop'])}" + (f", {x['cambio_pct']} %" if x["cambio_pct"] is not None else "") + ")" for x in lista[:10]) + "."
    return _resp("ok", "clientes_reducen", p, lista[:LIMITE_FILAS], _evid(cierre, "COP", filtros, "#/agenda"), texto)


def herramienta_indicador(con, cierre, p) -> dict:
    d = INDICADORES.get(p.get("indicador"))
    if not d:
        return _resp("no_encontrado", "explicar_indicador", p, texto="No tengo una definición aprobada para ese indicador.")
    return _resp("ok", "explicar_indicador", p, {"definicion": d}, _evid(cierre, None, p), d)


# ---------------------------------------------------------------- modelos de IA (lectura; mismos permisos que sus vistas)
def _pct(x) -> str:
    return "—" if x is None else f"{round(x * 100)} %"


EXPERIMENTAL = "Estimación de un modelo en uso (datos de práctica): apoya la decisión de una persona; no es un hecho ni una tarea."


def herramienta_modelos(con, usuario, cierre, intencion: str, p: dict) -> dict:
    from . import anomalias, demanda, monitoreo, prevencion, proxima, venta_cruzada
    permiso = {"modelo_inactividad": ("prevencion.ver",), "modelo_proxima": ("proxima.ver",), "modelo_venta_cruzada": ("venta_cruzada.ver",),
               "modelo_demanda": ("demanda.ver_cop", "demanda.ver_unidades"), "modelo_anomalias": ("anomalias.ver",),
               "modelo_monitoreo": ("monitoreo.ver",), "modelo_resultados": ("cartera.ver",)}[intencion]
    if not any(usuario.puede(x) for x in permiso):
        return _resp("no_autorizado", intencion, p, texto="Tu rol no tiene acceso a ese modelo.")
    ev = lambda enlace: _evid(cierre, None, p, None, [{"tipo": "vista", "enlace": enlace}])  # noqa: E731
    sin = lambda d: _resp("sin_datos", intencion, p, texto=d.get("mensaje") or "No hay publicación importada de este modelo.")  # noqa: E731
    if intencion == "modelo_inactividad":
        d = prevencion.lista(con)
        if d.get("estado") == "sin_sombra":
            return sin(d)
        top = "; ".join(f"{x['cliente_id']} ({_pct(x.get('probabilidad'))}, {x.get('recencia_dias')} días sin comprar)" for x in d["items"][:5])
        return _resp("ok", intencion, p, {"items": d["items"][:10]}, ev("#/prevencion"),
                     f"{EXPERIMENTAL} Mayor riesgo de inactividad a 60 días al {d['sombra'].get('corte')}: {top}. Lista completa en Prevención (IA).")
    if intencion == "modelo_proxima":
        d = proxima.lista(con)
        if d.get("estado") == "sin_sombra":
            return sin(d)
        top = "; ".join(f"{x['cliente_id']} (inicio probable {x.get('fecha_p10')} a {x.get('fecha_p50')})" for x in d["items"][:5])
        return _resp("ok", intencion, p, {"items": d["items"][:10]}, ev("#/proxima"),
                     f"{EXPERIMENTAL} Ventanas de inicio probable de la próxima compra (no son fechas de compra): {top}.")
    if intencion == "modelo_venta_cruzada":
        if p.get("cliente_id"):
            d = venta_cruzada.para_ficha(con, p["cliente_id"])
            if not d:
                return _resp("sin_datos", intencion, p, texto=f"No hay propuestas de venta cruzada para {p['cliente_id']}.")
            items = d["items"]
        else:
            d = venta_cruzada.lista(con)
            if d.get("estado") == "sin_sombra":
                return sin(d)
            items = [x for x in d["items"] if x["posicion"] == 1][:5]
        top = "; ".join(f"{x['cliente_id']}: {x.get('producto_nombre') or x['producto_id']} (compatibilidad {x.get('estado_compatibilidad')})" for x in items)
        return _resp("ok", intencion, p, {"items": items}, ev("#/venta-cruzada"),
                     f"{EXPERIMENTAL} Propuestas de venta cruzada (popularidad filtrada, para revisión de Ventas; no son ofertas): {top}.")
    if intencion == "modelo_demanda":
        d = demanda.panel(con, usuario, p.get("serie"))
        if d.get("estado") == "sin_sombra":
            return sin(d)
        cop = d["serie_id"].startswith(("ventas_cop", "compras"))
        val = lambda v: "sin pronóstico" if v is None else (_cop(v) if cop else f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", "."))  # noqa: E731
        proy = "; ".join(f"{x['periodo_objetivo']}: {val(x['valor'])}" for x in d["pronosticos"])
        return _resp("ok", intencion, p, {"serie": d["serie_id"], "pronosticos": d["pronosticos"]}, ev(f"#/demanda?serie={d['serie_id']}"),
                     f"{EXPERIMENTAL} Proyección de {d['serie_id']} desde {d['origen']} (no es ingreso realizado): {proy}.")
    if intencion == "modelo_anomalias":
        d = anomalias.lista(con, usuario, p.get("universo") or "venta")
        if d.get("estado") == "sin_sombra":
            return sin(d)
        r = d["resumen"]
        top = "; ".join(f"{x['operacion_id']} ({'; '.join(x['motivos'][:1])})" for x in d["items"] if x["alerta"])[:900]
        return _resp("ok", intencion, p, {"resumen": r}, ev(f"#/anomalias?universo={d['universo']}"),
                     f"{EXPERIMENTAL} La rareza no es fraude ni un error confirmado. {d['universo'].capitalize()}s: {r['alertas']} alertas de "
                     f"{r['validas']} operaciones, {r['casos_pendientes']} casos pendientes de revisión. {top}")
    if intencion == "modelo_monitoreo":
        d = monitoreo.panel(con, usuario)
        estado = "; ".join(f"{m['nombre']}: {m['estado_texto']}" + (f" ({len(m['avisos_activos'])} avisos)" if m["avisos_activos"] else "") for m in d["modelos"])
        return _resp("ok", intencion, p, {"modelos": [{k: m[k] for k in ("modelo_id", "estado", "ultimo_corte")} for m in d["modelos"]]}, ev("#/monitoreo"),
                     f"Estado del monitoreo (reglas iniciales): {estado}. Ningún aviso promueve ni revierte modelos.")
    from .base import DIR_SALIDA
    ruta_r = DIR_SALIDA / "ia" / "resumen.json"   # misma carpeta que /api/ia (JACOMIND_SALIDA en el servidor)
    if not ruta_r.is_file():
        return _resp("sin_datos", intencion, p, texto="Aún no se ha generado el resumen de los modelos de IA.")
    rs = json.loads(ruta_r.read_text(encoding="utf-8"))
    txt = " ".join(f"{m['titulo']} ({m['estado']}): {m['lectura'][0]}" for m in rs["modelos"])
    return _resp("ok", intencion, p, {"modelos": [m["titulo"] for m in rs["modelos"]]}, ev("#/ia"), f"{rs.get('advertencia', '')} {txt}")


HERRAMIENTAS = {"historial_cliente": herramienta_historial, "productos_cliente": herramienta_productos,
                "ventas_periodo": herramienta_ventas, "compras_proveedor": herramienta_compras,
                "oportunidades": herramienta_oportunidades, "clientes_reducen": herramienta_reducen,
                "explicar_indicador": herramienta_indicador}


def nodo_ejecutar(s: Estado) -> Estado:
    ctx = s["ctx"]
    con, u = ctx["con"], ctx["usuario"]
    if s["intencion"] == "portal":
        return {"respuesta": atencion.asistente_portal(con, u, s["pregunta"])}
    try:
        cierre = resolver_cierre(con, ctx.get("cierre") or "activo")
    except ErrorApi as e:
        return {"respuesta": _resp("sin_datos", s["intencion"], s["parametros"], texto=e.mensaje)}
    try:
        if s["intencion"] in INTENCIONES_MODELOS:
            return {"respuesta": herramienta_modelos(con, u, cierre, s["intencion"], s["parametros"])}
        return {"respuesta": HERRAMIENTAS[s["intencion"]](con, cierre, s["parametros"])}
    except (KeyError, TypeError, ValueError) as e:
        return {"respuesta": _resp("error", s["intencion"], s["parametros"], texto=f"Parámetros inválidos: {e}")}


def nodo_redactar(s: Estado) -> Estado:
    r = dict(s["respuesta"])
    if r["estado"] != "ok":
        return {"respuesta": r, "version": llm.PLANTILLA}
    contexto = dumps({"resultado": r.get("resultado"), "evidencia": r.get("evidencia")})[:6000]
    texto, version = llm.redactar(r["texto"], contexto)
    r["texto_determinista"] = r["texto"]
    r["texto"] = texto
    return {"respuesta": r, "version": version}


def nodo_registrar(s: Estado) -> Estado:
    ctx = s["ctx"]
    r = s["respuesta"]
    latencia = int((time.perf_counter() - s["inicio"]) * 1000)
    ctx["con"].execute("""INSERT INTO asistente_registro (ts, actor, herramienta, intencion, parametros_json, estado, latencia_ms, version_componente)
                          VALUES (?,?,?,?,?,?,?,?)""",
                       (ahora(), ctx["usuario"].id, r.get("herramienta"), s.get("intencion"), dumps(r.get("parametros") or {}),
                        r["estado"], latencia, s.get("version") or llm.PLANTILLA))
    r = dict(r, intencion=s.get("intencion"), version=s.get("version") or llm.PLANTILLA, latencia_ms=latencia,
             registro_id=ctx["con"].execute("SELECT last_insert_rowid()").fetchone()[0])
    return {"respuesta": r}


# ---------------------------------------------------------------- grafo
class _GrafoSecuencial:
    """Equivalente mínimo cuando langgraph no está instalado (mismos nodos y rutas)."""

    def invoke(self, s: Estado) -> Estado:
        s = dict(s)
        s.update(nodo_interpretar(s))
        destino = ruta(s)
        s.update({"aclarar": nodo_aclarar, "denegar": nodo_denegar, "ejecutar": nodo_ejecutar}[destino](s))
        if destino == "ejecutar":
            s.update(nodo_redactar(s))
        s.update(nodo_registrar(s))
        return s


def construir_grafo():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return _GrafoSecuencial()
    g = StateGraph(Estado)
    g.add_node("interpretar", nodo_interpretar)
    g.add_node("aclarar", nodo_aclarar)
    g.add_node("denegar", nodo_denegar)
    g.add_node("ejecutar", nodo_ejecutar)
    g.add_node("redactar", nodo_redactar)
    g.add_node("registrar", nodo_registrar)
    g.add_edge(START, "interpretar")
    g.add_conditional_edges("interpretar", ruta, {"aclarar": "aclarar", "denegar": "denegar", "ejecutar": "ejecutar"})
    g.add_edge("ejecutar", "redactar")
    g.add_edge("redactar", "registrar")
    g.add_edge("aclarar", "registrar")
    g.add_edge("denegar", "registrar")
    g.add_edge("registrar", END)
    return g.compile()


_GRAFO = None


def grafo():
    global _GRAFO
    if _GRAFO is None:
        _GRAFO = construir_grafo()
    return _GRAFO


def motor() -> str:
    return "langgraph" if not isinstance(grafo(), _GrafoSecuencial) else "secuencial (langgraph no instalado)"


def preguntar(con, usuario, pregunta: str, cierre: str | None = None, conversacion: str | None = None) -> dict:
    pregunta = (pregunta or "").strip()
    if not pregunta:
        raise ErrorApi(400, "pregunta_vacia", "Escribe una pregunta")
    if len(pregunta) > 1000:
        raise ErrorApi(400, "pregunta_larga", "La pregunta supera 1.000 caracteres")
    if not bandera(con, "asistente"):
        return _resp("fuera_de_alcance", None, {}, texto="El asistente está desactivado. Usa los filtros de la agenda y las fichas.") | {"version": None}
    aviso = None
    from . import agente_chat
    if agente_chat.disponible():
        try:
            return agente_chat.preguntar(con, usuario, pregunta, cierre, conversacion)
        except ErrorApi:
            raise
        except Exception as e:  # modelo caído o respuesta inválida: el servicio sigue con las reglas
            aviso = f"El modelo de lenguaje no respondió ({type(e).__name__}); respuesta en modo básico."
    final = grafo().invoke({"pregunta": pregunta, "ctx": {"con": con, "usuario": usuario, "cierre": cierre},
                            "inicio": time.perf_counter(), "parametros": {}})
    return final["respuesta"] | {"motor": motor(), "modo": "basico", "aviso": aviso}


def calificar(con, registro_id: int, correcta: bool, usuario) -> None:
    con.execute("UPDATE asistente_registro SET correcta = ? WHERE id = ? AND actor = ?", (int(correcta), registro_id, usuario.id))


def metricas(con) -> dict:
    filas_ = con.execute("""SELECT herramienta, estado, count(*) n, avg(latencia_ms) lat, sum(correcta = 1) ok, sum(correcta = 0) mal
                            FROM asistente_registro GROUP BY herramienta, estado""").fetchall()
    return {"por_herramienta": [dict(r) for r in filas_], "motor": motor(), "llm": llm.estado()}
