"""Servidor HTTP (biblioteca estándar): API JSON + archivos estáticos de ``app/``.

Cada ruta declara los permisos que exige; rol y empresa se resuelven en el
servidor en cada solicitud (búsquedas, exportaciones y documentos incluidos).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import (__version__, agente, atencion, auth, beneficios, consultas, documentos, finanzas, llm, operacion,
               pqrs, prevencion, proxima, publicacion, tareas, venta_cruzada, demanda, anomalias, monitoreo, narrativas, cuota_llm)
from .base import DIR_SALIDA, DIR_VAR, RAIZ, BaseDatos, ErrorApi
from .permisos import IDENTIDADES

COOKIE = "jacomind_sesion"
DIR_APP = RAIZ / "app"
DIR_CONTRATOS = RAIZ / "contratos"
RUTAS_PUBLICABLES = [DIR_SALIDA, RAIZ / "contratos" / "ejemplos", DIR_VAR]


@dataclass
class Ctx:
    app: "Aplicacion"
    usuario: auth.Usuario | None
    params: dict
    query: dict
    body: dict
    headers: dict = field(default_factory=dict)

    @property
    def db(self) -> BaseDatos:
        return self.app.db

    def q(self, nombre, defecto=None):
        return self.query.get(nombre, [defecto])[0]


@dataclass
class Respuesta:
    status: int
    cuerpo: bytes
    tipo: str = "application/json; charset=utf-8"
    cabeceras: dict = field(default_factory=dict)


def _json(datos, status=200, cabeceras=None) -> Respuesta:
    return Respuesta(status, json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8"), cabeceras=cabeceras or {})


RUTAS: list[tuple[str, re.Pattern, object, tuple[str, ...]]] = []


def ruta(metodo: str, patron: str, *permisos: str):
    """Registra una ruta. ``permisos`` = alguno basta; vacío = pública; '*' = cualquier sesión."""
    rx = re.compile("^" + re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", patron) + "$")

    def deco(fn):
        RUTAS.append((metodo, rx, fn, permisos))
        return fn
    return deco


def _seguro() -> str:
    """Con HTTPS delante (Caddy en Lightsail), la cookie de sesión solo viaja cifrada."""
    return "; Secure" if os.environ.get("JACOMIND_COOKIE_SEGURA") == "1" else ""


def _ruta_publicable(texto: str) -> Path:
    p = (RAIZ / texto).resolve() if not Path(texto).is_absolute() else Path(texto).resolve()
    if not any(p.is_relative_to(b.resolve()) for b in RUTAS_PUBLICABLES):
        raise ErrorApi(400, "ruta_no_permitida", "Solo se publican rutas dentro de salida/, var/ o contratos/ejemplos/")
    return p


# ------------------------------------------------------------------ sesión y estado
@ruta("GET", "/api/estado")
def r_estado(c: Ctx):
    with c.db.conexion() as con:
        act = publicacion.cierre_activo(con)
        fila = con.execute("SELECT corte, origen FROM cierres WHERE id = ?", (act,)).fetchone() if act else None
    return {"version": __version__, "esquema": c.db.version_esquema(), "cierre_activo": act,
            "corte_activo": fila["corte"] if fila else None, "origen_activo": fila["origen"] if fila else None, "modo_practica": c.app.practica,
            "login_demo": c.app.login_demo, "login_local": c.app.login_local,
            "asistente": {"motor": agente.motor(), "llm": llm.version()}}


@ruta("GET", "/api/identidades")
def r_identidades(c: Ctx):
    if not c.app.login_demo:
        raise ErrorApi(404, "no_disponible", "El inicio de sesión de demostración está desactivado")
    return [{"id": i, "nombre": n, "organizacion": o, "rol": r} for i, n, o, r in IDENTIDADES]


@ruta("POST", "/api/sesion")
def r_login(c: Ctx):
    if c.body.get("usuario") is not None:
        if not c.app.login_local:
            raise ErrorApi(403, "login_local", "El inicio de sesión local está desactivado")
        u = auth.autenticar_local(c.db, str(c.body.get("usuario", "")), str(c.body.get("password", "")))
        token, u = auth.crear_sesion(c.db, u.id)
    else:
        if not c.app.login_demo:
            raise ErrorApi(403, "login_externo", "Usa el proveedor de identidad aprobado")
        token, u = auth.crear_sesion(c.db, str(c.body.get("identidad", "")))
    cookie = f"{COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={auth.DURACION_SESION_MIN * 60}{_seguro()}"
    return _json({"usuario": u.como_dict()}, cabeceras={"Set-Cookie": cookie})


@ruta("DELETE", "/api/sesion", "*")
def r_logout(c: Ctx):
    auth.cerrar_sesion(c.db, c.headers.get("token") or "")
    return _json({"ok": True}, cabeceras={"Set-Cookie": f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{_seguro()}"})


@ruta("GET", "/api/sesion", "*")
def r_yo(c: Ctx):
    return {"usuario": c.usuario.como_dict()}


@ruta("GET", "/api/usuarios", "usuarios.gestionar")
def r_usuarios(c: Ctx):
    return auth.listar_usuarios(c.db)


@ruta("POST", "/api/usuarios", "usuarios.gestionar")
def r_crear_usuario(c: Ctx):
    resultado = auth.crear_usuario_local(c.db, str(c.body.get("usuario", "")), str(c.body.get("nombre", "")),
                                         str(c.body.get("rol", "")), str(c.body.get("password", "")),
                                         str(c.body.get("organizacion_id", "GREEN")))
    return resultado


@ruta("PATCH", "/api/usuarios/{identidad}", "usuarios.gestionar")
def r_actualizar_usuario(c: Ctx):
    return auth.actualizar_usuario_local(c.db, c.params["identidad"], activo=c.body.get("activo"),
                                         rol=c.body.get("rol"), password=c.body.get("password"))


# ------------------------------------------------------------------ cierres y cartera (B02/B03)
@ruta("GET", "/api/cierres", "cartera.ver", "finanzas.ver", "informes.ver", "operacion.administrar")
def r_cierres(c: Ctx):
    with c.db.conexion() as con:
        return publicacion.listar_cierres(con)


@ruta("POST", "/api/cierres/publicar", "cierres.publicar")
def r_publicar(c: Ctx):
    return publicacion.publicar_ruta(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


@ruta("POST", "/api/cierres/ejecutar", "cierres.publicar")
def r_ejecutar(c: Ctx):
    corte = str(c.body.get("corte", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", corte):
        raise ErrorApi(400, "corte_invalido", "Indica el corte como AAAA-MM-DD")
    desde = str(_ruta_publicable(c.body["desde"])) if c.body.get("desde") else None
    return operacion.ejecutar_cierre(c.db, c.usuario.id, corte, datos=c.body.get("datos"), desde=desde,
                                     reintentos=int(c.body.get("reintentos", 1)))


@ruta("GET", "/api/cierres/{cierre}/resumen", "cartera.ver", "finanzas.ver")
def r_resumen(c: Ctx):
    with c.db.conexion() as con:
        return consultas.resumen(con, c.params["cierre"])


@ruta("GET", "/api/cierres/{cierre}/agenda", "cartera.ver")
def r_agenda(c: Ctx):
    with c.db.conexion() as con:
        return consultas.agenda(con, c.params["cierre"], accion=c.q("accion"), segmento=c.q("segmento"), q=c.q("q"),
                                frio=c.q("frio"), pagina=c.q("pagina", 1), tam=c.q("tam", 25))


@ruta("GET", "/api/cierres/{cierre}/agenda.csv", "cartera.exportar")
def r_agenda_csv(c: Ctx):
    with c.db.conexion() as con:
        texto = consultas.exportar_csv(con, c.params["cierre"], accion=c.q("accion"), segmento=c.q("segmento"),
                                       q=c.q("q"), frio=c.q("frio"))
    return Respuesta(200, ("﻿" + texto).encode("utf-8"), "text/csv; charset=utf-8",
                     {"Content-Disposition": f'attachment; filename="agenda-{c.params["cierre"]}.csv"'})


@ruta("GET", "/api/cierres/{cierre}/clientes/{cliente}", "cartera.ver")
def r_ficha(c: Ctx):
    with c.db.conexion() as con:
        f = consultas.ficha(con, c.params["cierre"], unquote(c.params["cliente"]))
        # M2 experimental: se añade aparte; la acción, los motivos y la estimación de compra no cambian.
        f["inactividad_sombra"] = prevencion.para_ficha(con, unquote(c.params["cliente"])) if c.usuario.puede("prevencion.ver") else None
        f["proxima_sombra"] = proxima.para_ficha(con, unquote(c.params["cliente"])) if c.usuario.puede("proxima.ver") else None
        f["venta_cruzada_sombra"] = venta_cruzada.para_ficha(con, unquote(c.params["cliente"])) if c.usuario.puede("venta_cruzada.ver") else None
        return f


# ------------------------------------------------------------------ guía del equipo (docs/guia-del-equipo.md, solo lectura)
@ruta("GET", "/api/guia", "guia.ver")
def r_guia(c: Ctx):
    archivo = RAIZ / "docs" / "guia-del-equipo.md"
    if not archivo.is_file():
        raise ErrorApi(404, "guia_no_disponible", "La guía del equipo no está en este despliegue")
    from datetime import datetime, timezone
    return {"markdown": archivo.read_text(encoding="utf-8"), "archivo": "docs/guia-del-equipo.md",
            "actualizado": datetime.fromtimestamp(archivo.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}


# ------------------------------------------------------------------ resultados de los modelos de IA (solo lectura)
@ruta("GET", "/api/ia", "cartera.ver")
def r_ia(c: Ctx):
    ruta_resumen = DIR_SALIDA / "ia" / "resumen.json"
    if not ruta_resumen.is_file():
        return {"estado": "sin_resumen", "mensaje": "Aún no se ha generado el resumen de resultados de los modelos.",
                "comando": "python -m modelos.cli resumen-ia"}
    try:
        doc = json.loads(ruta_resumen.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ErrorApi(500, "resumen_ia_invalido", "El resumen de resultados de los modelos no se pudo leer")
    if doc.get("version") != 1 or not isinstance(doc.get("modelos"), list):
        raise ErrorApi(500, "resumen_ia_invalido", "El resumen de resultados de los modelos tiene un formato desconocido")
    return {"estado": "ok", **doc}


# ------------------------------------------------------------------ prevención de inactividad (M2, en sombra)
@ruta("GET", "/api/prevencion", "prevencion.ver")
def r_prevencion(c: Ctx):
    with c.db.conexion() as con:
        return prevencion.lista(con, k=int(c.q("k", prevencion.K_POLITICA)))


@ruta("GET", "/api/prevencion/episodios", "prevencion.ver")
def r_prevencion_episodios(c: Ctx):
    with c.db.conexion() as con:
        return {"episodios": prevencion.episodios(con, c.q("cliente"))}


@ruta("POST", "/api/prevencion/sombra", "operacion.administrar")
def r_prevencion_sombra(c: Ctx):
    return prevencion.importar_sombra(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


@ruta("POST", "/api/prevencion/sincronizar", "prevencion.sincronizar")
def r_prevencion_sincronizar(c: Ctx):
    return prevencion.sincronizar(c.db, c.usuario.id)


# ------------------------------------------------------------------ monitoreo de modelos (M1–M6)
@ruta("GET", "/api/monitoreo", "monitoreo.ver")
def r_monitoreo(c: Ctx):
    with c.db.conexion() as con:
        return monitoreo.panel(con, c.usuario, modelo=c.q("modelo") or None, variante=c.q("variante") or None, periodo=c.q("periodo") or None,
                               estado=c.q("estado") or None, severidad=c.q("severidad") or None, tipo=c.q("tipo") or None)


@ruta("GET", "/api/monitoreo/aviso", "monitoreo.ver")
def r_monitoreo_aviso(c: Ctx):
    with c.db.conexion() as con:
        return monitoreo.detalle_aviso(con, c.usuario, str(c.q("clave") or ""))


@ruta("POST", "/api/monitoreo/aviso", "monitoreo.reconocer")
def r_monitoreo_aviso_estado(c: Ctx):
    b = c.body
    return monitoreo.cambiar_estado_aviso(c.db, c.usuario, str(b.get("clave", "")), str(b.get("accion", "")), str(b.get("motivo", "")))


@ruta("GET", "/api/monitoreo/exportar.csv", "monitoreo.ver")
def r_monitoreo_csv(c: Ctx):
    with c.db.conexion() as con:
        texto = monitoreo.exportar_csv(con, c.usuario, c.q("modelo") or None)
    return Respuesta(200, ("\ufeff" + texto).encode("utf-8"), "text/csv; charset=utf-8", {"Content-Disposition": 'attachment; filename="monitoreo.csv"'})


# ------------------------------------------------------------------ operaciones atípicas (M6, en sombra)
@ruta("GET", "/api/anomalias", "anomalias.ver")
def r_anomalias(c: Ctx):
    with c.db.conexion() as con:
        return anomalias.lista(con, c.usuario, c.q("universo") or "venta", c.q("periodo") or None, c.q("producto") or None, c.q("moneda") or None,
                               c.q("estado") or None, c.q("vista") or "cola")


@ruta("GET", "/api/anomalias/caso", "anomalias.ver")
def r_anomalias_caso(c: Ctx):
    with c.db.conexion() as con:
        return anomalias.detalle(con, c.usuario, str(c.q("tipo") or ""), str(c.q("id") or ""))


@ruta("POST", "/api/anomalias/revision", "anomalias.revisar")
def r_anomalias_revision(c: Ctx):
    b = c.body
    return anomalias.revisar(c.db, c.usuario, str(b.get("tipo_operacion", "")), str(b.get("operacion_id", "")), str(b.get("estado", "")),
                             str(b.get("motivo", "")), b.get("evidencia"))


@ruta("GET", "/api/anomalias/exportar.csv", "anomalias.exportar")
def r_anomalias_csv(c: Ctx):
    universo = c.q("universo") or "venta"
    with c.db.conexion() as con:
        texto = anomalias.exportar_csv(con, c.usuario, universo)
    return Respuesta(200, ("\ufeff" + texto).encode("utf-8"), "text/csv; charset=utf-8",
                     {"Content-Disposition": f'attachment; filename="anomalias-{universo}.csv"'})


@ruta("GET", "/api/anomalias/monitoreo", "anomalias.ver")
def r_anomalias_monitoreo(c: Ctx):
    with c.db.conexion() as con:
        return anomalias.panel_monitoreo(con)


@ruta("POST", "/api/anomalias/sombra", "operacion.administrar")
def r_anomalias_sombra(c: Ctx):
    return anomalias.importar_sombra(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


# ------------------------------------------------------------------ pronóstico de demanda (M5, en sombra)
@ruta("GET", "/api/demanda", "*")
def r_demanda(c: Ctx):
    if not (c.usuario.puede("demanda.ver_cop") or c.usuario.puede("demanda.ver_unidades")):
        raise ErrorApi(403, "sin_permiso", "Tu perfil no tiene acceso al pronóstico de demanda")
    with c.db.conexion() as con:
        return demanda.panel(con, c.usuario, c.q("serie"))


@ruta("POST", "/api/demanda/sombra", "operacion.administrar")
def r_demanda_sombra(c: Ctx):
    return demanda.importar_sombra(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


# ------------------------------------------------------------------ textos redactados por IA (api/narrativas.py)
@ruta("GET", "/api/narrativas/venta-cruzada/{cliente}", "venta_cruzada.ver")
def r_narrativa_vc(c: Ctx):
    return narrativas.obtener(c.db, "venta_cruzada", unquote(c.params["cliente"]))


@ruta("GET", "/api/narrativas/ficha/{cliente}", "cartera.ver")
def r_narrativa_ficha(c: Ctx):
    return narrativas.obtener(c.db, "ficha", unquote(c.params["cliente"]))


@ruta("GET", "/api/llm/cuota", "operacion.administrar", "monitoreo.ver")
def r_llm_cuota(c: Ctx):
    return cuota_llm.estado() | {"llm": llm.estado()}


# ------------------------------------------------------------------ venta cruzada (M4, en sombra)
@ruta("GET", "/api/venta-cruzada", "venta_cruzada.ver")
def r_vc(c: Ctx):
    with c.db.conexion() as con:
        return venta_cruzada.lista(con, c.q("compatibilidad") or None)


@ruta("POST", "/api/venta-cruzada/sombra", "operacion.administrar")
def r_vc_sombra(c: Ctx):
    return venta_cruzada.importar_sombra(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


@ruta("POST", "/api/venta-cruzada/decision", "venta_cruzada.decidir")
def r_vc_decision(c: Ctx):
    b = c.body
    return venta_cruzada.decidir(c.db, c.usuario, str(b.get("cliente_id", "")), str(b.get("producto_id", "")), str(b.get("accion", "")), str(b.get("motivo", "")))


@ruta("GET", "/api/venta-cruzada/revision", "venta_cruzada.ver")
def r_vc_revision(c: Ctx):
    with c.db.conexion() as con:
        return venta_cruzada.revision(con)


@ruta("POST", "/api/venta-cruzada/revision", "venta_cruzada.revisar")
def r_vc_revisar(c: Ctx):
    b = c.body
    return venta_cruzada.registrar_revision(c.db, c.usuario, str(b.get("cliente_id", "")), str(b.get("producto_id", "")), str(b.get("estado", "")),
                                            str(b.get("motivo", "")), b.get("evidencia"))


@ruta("GET", "/api/venta-cruzada/episodios", "venta_cruzada.ver")
def r_vc_episodios(c: Ctx):
    with c.db.conexion() as con:
        return {"episodios": venta_cruzada.episodios(con, c.q("cliente"))}


@ruta("POST", "/api/venta-cruzada/sincronizar", "venta_cruzada.sincronizar")
def r_vc_sincronizar(c: Ctx):
    return venta_cruzada.sincronizar(c.db, c.usuario.id)


# ------------------------------------------------------------------ próxima compra (M3, en sombra)
@ruta("GET", "/api/proxima", "proxima.ver")
def r_proxima(c: Ctx):
    with c.db.conexion() as con:
        return proxima.lista(con, dias=int(c.q("dias", 30)))


@ruta("GET", "/api/proxima/episodios", "proxima.ver")
def r_proxima_episodios(c: Ctx):
    with c.db.conexion() as con:
        return {"episodios": proxima.episodios(con, c.q("cliente"))}


@ruta("POST", "/api/proxima/sombra", "operacion.administrar")
def r_proxima_sombra(c: Ctx):
    return proxima.importar_sombra(c.db, _ruta_publicable(str(c.body.get("ruta", ""))), c.usuario.id)


@ruta("POST", "/api/proxima/sincronizar", "proxima.sincronizar")
def r_proxima_sincronizar(c: Ctx):
    return proxima.sincronizar(c.db, c.usuario.id)


@ruta("GET", "/api/cierres/{cierre}/tableros/{rol}", "*")
def r_tablero(c: Ctx):
    auth.exigir(c.usuario, f"tablero.{c.params['rol']}")
    with c.db.conexion() as con:
        return consultas.tablero(con, c.params["cierre"], c.params["rol"])


# ------------------------------------------------------------------ tareas (B05)
@ruta("GET", "/api/tareas", "tareas.ver")
def r_tareas(c: Ctx):
    resp = c.usuario.id if c.q("mias") == "1" else c.q("responsable")
    with c.db.conexion() as con:
        return tareas.listar(con, responsable=resp, estado=c.q("estado"), k=c.q("k"), cliente_id=c.q("cliente"))


@ruta("GET", "/api/tareas/metricas", "tareas.ver")
def r_tareas_metricas(c: Ctx):
    with c.db.conexion() as con:
        return tareas.metricas(con, responsable=c.usuario.id if c.q("mias") == "1" else c.q("responsable"))


@ruta("GET", "/api/tareas/{id}", "tareas.ver")
def r_tarea(c: Ctx):
    with c.db.conexion() as con:
        return tareas.detalle(con, int(c.params["id"]))


@ruta("POST", "/api/tareas/{id}/{accion}", "tareas.gestionar")
def r_tarea_accion(c: Ctx):
    return tareas.accion(c.db, c.usuario, int(c.params["id"]), c.params["accion"], c.body, c.headers.get("idempotency-key"))


@ruta("GET", "/api/avisos", "tareas.ver")
def r_avisos(c: Ctx):
    with c.db.conexion() as con:
        return tareas.avisos(con, c.usuario.id if "ventas" in c.usuario.roles else None)


# ------------------------------------------------------------------ PQRS y atención (B04/B10)
@ruta("GET", "/api/pqrs", "pqrs.ver_propias", "pqrs.gestionar", "pqrs.indicadores")
def r_pqrs(c: Ctx):
    with c.db.conexion() as con:
        return pqrs.listar(con, c.usuario, estado=c.q("estado"), revision=c.q("revision"), q=c.q("q"))


@ruta("POST", "/api/pqrs", "pqrs.crear")
def r_pqrs_crear(c: Ctx):
    return _json(pqrs.crear(c.db, c.usuario, c.body.get("asunto"), c.body.get("descripcion"),
                            c.headers.get("idempotency-key") or c.body.get("clave_idempotencia")), 201)


@ruta("GET", "/api/pqrs-indicadores", "pqrs.indicadores")
def r_pqrs_ind(c: Ctx):
    with c.db.conexion() as con:
        return pqrs.indicadores(con)


@ruta("GET", "/api/atencion/bandeja", "pqrs.gestionar")
def r_bandeja(c: Ctx):
    with c.db.conexion() as con:
        return atencion.bandeja_revision(con)


@ruta("GET", "/api/pqrs/{radicado}", "pqrs.ver_propias", "pqrs.gestionar")
def r_pqrs_detalle(c: Ctx):
    with c.db.conexion() as con:
        return pqrs.detalle(con, c.usuario, c.params["radicado"])


@ruta("POST", "/api/pqrs/{radicado}/borradores", "pqrs.gestionar")
def r_borrador(c: Ctx):
    return _json(atencion.generar_borrador(c.db, c.usuario, c.params["radicado"]), 201)


@ruta("POST", "/api/pqrs/{radicado}/reclasificar", "pqrs.gestionar")
def r_reclasificar(c: Ctx):
    return atencion.reclasificar(c.db, c.usuario, c.params["radicado"])


@ruta("POST", "/api/pqrs/{radicado}/{accion}", "pqrs.gestionar")
def r_pqrs_accion(c: Ctx):
    return pqrs.gestionar(c.db, c.usuario, c.params["radicado"], c.params["accion"], c.body)


@ruta("POST", "/api/borradores/{id}/editar", "pqrs.gestionar")
def r_borrador_editar(c: Ctx):
    return atencion.editar_borrador(c.db, c.usuario, int(c.params["id"]), str(c.body.get("texto", "")))


@ruta("POST", "/api/borradores/{id}/aprobar", "pqrs.gestionar")
def r_borrador_aprobar(c: Ctx):
    return atencion.aprobar_borrador(c.db, c.usuario, int(c.params["id"]), bool(c.body.get("confirmar_revision")))


# ------------------------------------------------------------------ beneficios (B06)
@ruta("GET", "/api/portal/beneficios", "beneficios.portal")
def r_portal(c: Ctx):
    with c.db.conexion() as con:
        return beneficios.portal(con, c.usuario)


@ruta("GET", "/api/portal/beneficios/{id}", "beneficios.portal")
def r_portal_det(c: Ctx):
    with c.db.conexion() as con:
        return beneficios.portal_detalle(con, c.usuario, c.params["id"])


@ruta("GET", "/api/beneficios", "beneficios.ver_interno")
def r_beneficios(c: Ctx):
    with c.db.conexion() as con:
        return beneficios.catalogo(con)


@ruta("GET", "/api/beneficios-retencion", "beneficios.ver_interno")
def r_retencion(c: Ctx):
    with c.db.conexion() as con:
        return beneficios.retencion(con)


@ruta("POST", "/api/beneficios", "beneficios.editar")
def r_beneficio_guardar(c: Ctx):
    return _json(beneficios.guardar(c.db, c.usuario, c.body), 201)


@ruta("POST", "/api/beneficios/{id}/{version}/{accion}", "beneficios.editar")
def r_beneficio_accion(c: Ctx):
    return beneficios.transicion(c.db, c.usuario, c.params["id"], int(c.params["version"]), c.params["accion"])


# ------------------------------------------------------------------ documentos y asistente (B07/B08)
@ruta("GET", "/api/documentos", "documentos.gestionar")
def r_docs(c: Ctx):
    with c.db.conexion() as con:
        return documentos.inventario(con)


@ruta("POST", "/api/documentos", "documentos.gestionar")
def r_doc_importar(c: Ctx):
    return _json(documentos.importar(c.db, c.usuario.id, c.body.get("meta") or {}, str(c.body.get("texto", ""))), 201)


@ruta("POST", "/api/documentos/consultar", "documentos.consultar")
def r_doc_consultar(c: Ctx):
    with c.db.conexion() as con:
        return documentos.responder(con, documentos.alcance_de(c.usuario), str(c.body.get("pregunta", "")))


@ruta("POST", "/api/documentos/{id}/retirar", "documentos.gestionar")
def r_doc_retirar(c: Ctx):
    return documentos.retirar(c.db, c.usuario.id, c.params["id"])


@ruta("POST", "/api/documentos/{id}/permisos", "documentos.gestionar")
def r_doc_permisos(c: Ctx):
    return documentos.cambiar_permisos(c.db, c.usuario.id, c.params["id"], list(c.body.get("roles") or []), c.body.get("organizacion_id"))


@ruta("GET", "/api/documentos/{id}/{version}/fragmentos/{fid}", "documentos.consultar")
def r_fragmento(c: Ctx):
    with c.db.conexion() as con:
        return documentos.fragmento(con, documentos.alcance_de(c.usuario), c.params["id"], int(c.params["version"]), int(c.params["fid"]))


@ruta("POST", "/api/asistente", "agente.datos", "agente.portal")
def r_asistente(c: Ctx):
    with c.db.conexion() as con:
        return agente.preguntar(con, c.usuario, str(c.body.get("pregunta", "")), c.body.get("cierre"), c.body.get("conversacion"))


@ruta("DELETE", "/api/asistente/conversaciones/{conversacion}", "agente.datos", "agente.portal")
def r_olvidar(c: Ctx):
    from . import agente_chat
    with c.db.conexion() as con:
        cierre = publicacion.resolver_cierre(con, c.q("cierre", "activo"))
    agente_chat.olvidar(c.usuario, cierre["id"], c.params["conversacion"])
    return {"ok": True}


@ruta("GET", "/api/asistente/capacidades", "agente.datos", "agente.portal")
def r_capacidades(c: Ctx):
    from . import agente_chat
    return {"modo": "agente" if agente_chat.disponible() else "basico", "llm": llm.version(), "motor": agente.motor()}


@ruta("POST", "/api/asistente/{id}/calificar", "agente.datos", "agente.portal")
def r_calificar(c: Ctx):
    with c.db.conexion() as con:
        agente.calificar(con, int(c.params["id"]), bool(c.body.get("correcta")), c.usuario)
    return {"ok": True}


@ruta("GET", "/api/asistente/metricas", "operacion.administrar", "auditoria.ver")
def r_asistente_metricas(c: Ctx):
    with c.db.conexion() as con:
        return agente.metricas(con)


# ------------------------------------------------------------------ finanzas e informes (B09)
@ruta("GET", "/api/finanzas/{cierre}/panel", "finanzas.ver")
def r_panel(c: Ctx):
    with c.db.conexion() as con:
        return finanzas.panel(con, c.params["cierre"], c.q("serie", "ventas"))


@ruta("GET", "/api/finanzas/{cierre}/simular", "finanzas.ver")
def r_simular(c: Ctx):
    with c.db.conexion() as con:
        return finanzas.simular(con, c.params["cierre"], c.q("periodo", ""), c.q("variacion", "0"), c.q("moneda", "USD"))


@ruta("GET", "/api/informes", "informes.ver")
def r_informes(c: Ctx):
    with c.db.conexion() as con:
        return finanzas.listar_informes(con)


@ruta("POST", "/api/informes", "informes.generar")
def r_informe_generar(c: Ctx):
    return _json(finanzas.generar_informe(c.db, c.usuario, str(c.body.get("cierre") or "activo")), 201)


@ruta("GET", "/api/informes/{cierre}/{revision}", "informes.ver")
def r_informe_html(c: Ctx):
    with c.db.conexion() as con:
        h = finanzas.html_informe(con, c.params["cierre"], int(c.params["revision"]))
    return Respuesta(200, h.encode("utf-8"), "text/html; charset=utf-8")


# ------------------------------------------------------------------ operación (B02.4/B11)
@ruta("GET", "/api/cargas", "cargas.ejecutar")
def r_cargas(c: Ctx):
    with c.db.conexion() as con:
        return operacion.listar_lotes(con)


@ruta("POST", "/api/cargas", "cargas.ejecutar")
def r_carga(c: Ctx):
    try:
        contenido = base64.b64decode(str(c.body.get("contenido_b64", "")), validate=True)
    except ValueError:
        raise ErrorApi(400, "contenido_invalido", "Contenido del archivo mal codificado")
    return operacion.previsualizar_carga(c.db, c.usuario, str(c.body.get("nombre", "archivo.csv")), contenido,
                                         str(c.body.get("tabla", "")), c.body.get("periodo"), c.body.get("hoja") or None,
                                         c.body.get("mapeo") or None)


@ruta("POST", "/api/cargas/{id}/confirmar", "cargas.ejecutar")
def r_carga_confirmar(c: Ctx):
    return operacion.confirmar_carga(c.db, c.usuario, int(c.params["id"]))


@ruta("GET", "/api/operacion", "operacion.administrar")
def r_operacion(c: Ctx):
    with c.db.conexion() as con:
        return operacion.estado_operacion(con)


@ruta("POST", "/api/operacion/banderas", "operacion.administrar")
def r_bandera(c: Ctx):
    return operacion.fijar_bandera(c.db, c.usuario, str(c.body.get("nombre")), bool(c.body.get("activo")))


@ruta("POST", "/api/operacion/respaldo", "operacion.administrar")
def r_respaldo(c: Ctx):
    return operacion.respaldar(c.db)


@ruta("GET", "/api/auditoria", "auditoria.ver")
def r_auditoria(c: Ctx):
    with c.db.conexion() as con:
        return [dict(r) for r in con.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT 200")]


@ruta("GET", "/api/exportes/eventos", "eventos.exportar")
def r_export_eventos(c: Ctx):
    with c.db.conexion() as con:
        return tareas.exportar_eventos(con)


@ruta("GET", "/api/exportes/pqrs", "pqrs.exportar")
def r_export_pqrs(c: Ctx):
    with c.db.conexion() as con:
        return pqrs.exportar_anonimizado(con)


# ------------------------------------------------------------------ aplicación
class Aplicacion:
    def __init__(self, db: BaseDatos, practica: bool = False, login_demo: bool = True):
        self.db, self.practica, self.login_demo = db, practica, login_demo
        self.login_local = os.environ.get("JACOMIND_LOGIN_LOCAL", "1") == "1"

    def despachar(self, metodo: str, ruta_url: str, cabeceras: dict, cuerpo: bytes) -> Respuesta:
        url = urlparse(ruta_url)
        camino = url.path
        if not camino.startswith("/api/"):
            return self.estatico(camino) if metodo in ("GET", "HEAD") else _json({"error": "metodo"}, 405)
        cab = {k.lower(): v for k, v in cabeceras.items()}
        token = None
        if cab.get("cookie"):
            ck = SimpleCookie(); ck.load(cab["cookie"])
            if COOKIE in ck:
                token = ck[COOKIE].value
        cab["token"] = token
        try:
            if metodo not in ("GET", "HEAD") and cab.get("x-jacomind") != "1":
                raise ErrorApi(403, "csrf", "Falta la cabecera X-Jacomind")
            for m, rx, fn, permisos in RUTAS:
                if m != metodo:
                    continue
                mt = rx.match(camino)
                if not mt:
                    continue
                usuario = auth.resolver(self.db, token, cab.get("x-usuario-autenticado")) if permisos else None
                if permisos:
                    auth.exigir(usuario)
                    if "*" not in permisos and not any(usuario.puede(p) for p in permisos):
                        raise ErrorApi(403, "sin_permiso", "Tu rol no permite esta operación")
                body = {}
                if cuerpo:
                    try:
                        body = json.loads(cuerpo.decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        raise ErrorApi(400, "json_invalido", "El cuerpo debe ser JSON")
                    if not isinstance(body, dict):
                        raise ErrorApi(400, "json_invalido", "El cuerpo debe ser un objeto JSON")
                r = fn(Ctx(self, usuario, mt.groupdict(), parse_qs(url.query), body, cab))
                return r if isinstance(r, Respuesta) else _json(r)
            raise ErrorApi(404, "ruta_desconocida", f"No existe {metodo} {camino}")
        except ErrorApi as e:
            return _json(e.como_dict(), e.status)
        except Exception as e:  # nunca filtrar trazas al cliente
            traceback.print_exc()
            return _json({"error": "interno", "mensaje": f"Error interno ({type(e).__name__})"}, 500)

    def estatico(self, camino: str) -> Respuesta:
        if camino in ("/", ""):
            return Respuesta(302, b"", "text/plain", {"Location": "/app/"})
        if camino.startswith("/app"):
            base, rel = DIR_APP, camino[len("/app"):].lstrip("/") or "index.html"
        elif camino.startswith("/contratos/") and camino.endswith(".json"):
            base, rel = DIR_CONTRATOS, camino[len("/contratos/"):]
        elif camino == "/salida/agenda.json" and self.practica:
            # Solo en modo práctica local: el portal multiusuario nunca expone la cartera como estático.
            base, rel = DIR_SALIDA, "agenda.json"
        else:
            return _json({"error": "no_encontrado"}, 404)
        p = (base / unquote(rel)).resolve()
        if not p.is_relative_to(base.resolve()) or not p.is_file():
            return _json({"error": "no_encontrado", "mensaje": f"No existe {camino}"}, 404)
        tipo = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript", "application/json"):
            tipo += "; charset=utf-8"
        return Respuesta(200, p.read_bytes(), tipo, {"Cache-Control": "no-store"})


class Manejador(BaseHTTPRequestHandler):
    app: Aplicacion = None  # asignado al crear el servidor
    server_version = "JACOMIND"

    def _atender(self):
        largo = int(self.headers.get("Content-Length") or 0)
        if largo > 30 * 1024 * 1024:
            r = _json({"error": "demasiado_grande"}, 413)
        else:
            cuerpo = self.rfile.read(largo) if largo else b""
            r = self.app.despachar(self.command, self.path, dict(self.headers.items()), cuerpo)
        self.send_response(r.status)
        self.send_header("Content-Type", r.tipo)
        self.send_header("Content-Length", str(len(r.cuerpo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        for k, v in r.cabeceras.items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(r.cuerpo)

    do_GET = do_POST = do_DELETE = do_HEAD = _atender

    def log_message(self, fmt, *args):
        if os.environ.get("JACOMIND_LOG_HTTP") == "1":
            super().log_message(fmt, *args)


def crear_servidor(app: Aplicacion, host: str = "127.0.0.1", puerto: int = 8000) -> ThreadingHTTPServer:
    manejador = type("ManejadorApp", (Manejador,), {"app": app})
    return ThreadingHTTPServer((host, puerto), manejador)
