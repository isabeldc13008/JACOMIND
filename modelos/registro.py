"""Registro de versiones (``var/modelos/<modelo>/``): sombra, operativo, autorizaciones, promoción y reversión.

Estructura::

    var/modelos/compra_30d/registro.json      punteros operativo/sombra, historial y autorizaciones posteriores
    var/modelos/compra_30d/v1/artefacto.json  inmutable una vez registrado
    var/modelos/compra_30d/v1/decision.json   decisión inicial con la que se registró (inmutable)
    var/modelos/compra_30d/v1/origen.json     ejecución, revisión de datos, código y entorno

Reglas:

* El artefacto es inmutable; sus **autorizaciones evolucionan como eventos**. La decisión inicial
  (``decision.json``) es la primera; cada aprobación posterior se añade a
  ``registro.json["autorizaciones"]`` con huella exacta del artefacto, estado máximo, actor, fecha y
  procedencia. Ninguna autorización anterior se borra. La **vigente** es la última que corresponde a
  la huella del artefacto.
* ``sombra`` exige una autorización con ``estado_maximo`` ``sombra`` u ``operativo``. ``operativo``
  exige ``estado_maximo = operativo``, datos no sintéticos y ``aprobado_por``. La única excepción
  (``referencia_vigente``) se concede por la huella exacta de un artefacto del catálogo versionado
  ``config/referencias_historicas.json`` (verificado con ``inicializar-referencia``); el texto de la
  decisión o el nombre de versión no bastan. Se comprueba al promover, revertir y leer.
* **Modo demostración** (``registro.json["modo_demostracion"]``, apagado por defecto): en un entorno de práctica
  activado de forma explícita (``modelos.cli modo-demo --activar``, con actor y motivo), una autorización
  operativa puede basarse en datos sintéticos si su ``decision`` es ``demostracion`` y tiene ``aprobado_por``.
  El puntero conserva ``origen_datos = sintetico``. Con el modo apagado se vuelve a exigir datos empresariales,
  también al leer: una versión de demostración deja de servirse (revierte antes a la anterior).
* Promover otra vez la misma versión con la misma autorización no cambia nada (idempotente) y no
  crea una transición hacia sí misma. Una autorización nueva queda como evento ``autorizar`` sin
  fingir un cambio de versión.
* ``revertir`` sin destino deshace la última promoción del puntero: busca la versión anterior
  **distinta**, cuyo artefacto siga íntegro y con autorización vigente para ese estado.
* Todas las comprobaciones ocurren antes de escribir; ``registro.json`` se reescribe de forma
  atómica (archivo temporal + ``os.replace``).
* Compatibilidad: un ``registro.json`` sin ``autorizaciones`` se lee igual (cada versión conserva su
  ``decision.json`` como autorización inicial); no requiere migración.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .inferencia import Artefacto, ArtefactoInvalido, cargar_artefacto

ESTADOS = ("sombra", "operativo")
REFERENCIAS_HISTORICAS = Path(__file__).resolve().parent / "config" / "referencias_historicas.json"


def referencia_historica_verificada(artefacto: Artefacto, modelo_id: str = "compra_30d") -> dict | None:
    """Entrada del catálogo versionado de referencias históricas cuya huella coincide EXACTAMENTE."""
    if not REFERENCIAS_HISTORICAS.is_file():
        return None
    for ref in json.loads(REFERENCIAS_HISTORICAS.read_text(encoding="utf-8")).get("referencias", []):
        if (ref.get("modelo_id") == modelo_id and ref.get("artefacto_huella") == artefacto.huella
                and ref.get("artefacto_version") == artefacto.version):
            return ref
    return None
MAXIMOS = ("ninguno", "sombra", "operativo")
RAIZ = Path(__file__).resolve().parents[1]


class RegistroError(RuntimeError):
    """Operación de registro no permitida o inconsistente."""


class ModeloNoDisponible(RuntimeError):
    """No hay versión registrada utilizable para el estado pedido."""


def ruta_registro(registro: str | Path | None = None) -> Path:
    """Registro explícito, ``JACOMIND_MODELOS`` o ``var/modelos`` del proyecto."""
    return Path(registro or os.environ.get("JACOMIND_MODELOS") or RAIZ / "var" / "modelos")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _escribir_atomico(ruta: Path, datos: Any) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{ruta.name}.", dir=ruta.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def leer_registro(registro: str | Path | None, modelo_id: str) -> dict[str, Any]:
    archivo = ruta_registro(registro) / modelo_id / "registro.json"
    if not archivo.exists():
        return {"modelo_id": modelo_id, "operativo": None, "sombra": None, "historial": [], "autorizaciones": []}
    reg = json.loads(archivo.read_text(encoding="utf-8"))
    reg.setdefault("autorizaciones", [])
    return reg


# Autorizaciones ---------------------------------------------------------------------------
def modo_demostracion(reg: dict | None) -> bool:
    return bool(((reg or {}).get("modo_demostracion") or {}).get("activo"))


def validar_autorizacion(decision: Any, artefacto: Artefacto, demostracion: bool = False) -> None:
    """Rechaza autorizaciones mal formadas, de otra huella o que conviertan lo sintético en operativo.

    Con ``demostracion`` (modo activado en el registro) se admite lo sintético como operativo solo si la decisión es
    ``demostracion`` y tiene ``aprobado_por``."""
    if not isinstance(decision, dict):
        raise RegistroError("La autorización debe ser un objeto JSON")
    if decision.get("artefacto_huella") != artefacto.huella:
        raise RegistroError(f"La autorización corresponde a otra huella ({str(decision.get('artefacto_huella'))[:12]}…), "
                            f"no al artefacto {artefacto.version} ({artefacto.huella[:12]}…)")
    if decision.get("estado_maximo") not in MAXIMOS:
        raise RegistroError(f"estado_maximo {decision.get('estado_maximo')!r} no admitido ({', '.join(MAXIMOS)})")
    if decision.get("estado_maximo") == "operativo" and decision.get("decision") == "referencia_vigente":
        # La excepción no depende del texto de la decisión: exige la huella de una referencia verificada.
        if referencia_historica_verificada(artefacto) is None:
            raise RegistroError(f"La excepción 'referencia_vigente' solo aplica a artefactos históricos verificados por huella "
                                f"(config/referencias_historicas.json); {artefacto.version} ({artefacto.huella[:12]}…) no lo es. "
                                "Una versión nueva necesita datos no sintéticos y 'aprobado_por'.")
    elif decision.get("estado_maximo") == "operativo":
        if decision.get("origen_datos") in (None, "sintetico") and not (demostracion and decision.get("decision") == "demostracion"):
            raise RegistroError("Una autorización operativa no puede basarse en datos sintéticos: requiere evaluación con datos "
                                "empresariales posteriores a la congelación")
        if not str(decision.get("aprobado_por") or "").strip():
            raise RegistroError("Una autorización operativa requiere 'aprobado_por' (aprobación registrada)")


def permite(decision: dict | None, estado: str) -> bool:
    maximo = (decision or {}).get("estado_maximo")
    if estado == "sombra":
        return maximo in ("sombra", "operativo")
    if estado == "operativo":
        return maximo == "operativo"
    return False


def _evento_autorizacion(version: str, decision: dict, actor: str, procedencia: str) -> dict:
    return {"id": hashlib.sha256(_canon(decision).encode()).hexdigest()[:16], "version": version,
            "artefacto_huella": decision["artefacto_huella"], "estado_maximo": decision["estado_maximo"],
            "decision": decision.get("decision"), "origen_datos": decision.get("origen_datos"),
            "aprobado_por": decision.get("aprobado_por"), "actor": actor, "procedencia": procedencia, "ts": _ahora(),
            "documento": decision}


def autorizaciones(registro: str | Path | None, modelo_id: str, version: str, reg: dict | None = None) -> list[dict]:
    """Todas las autorizaciones de una versión, de la inicial a la más reciente (sin borrar ninguna)."""
    reg = reg if reg is not None else leer_registro(registro, modelo_id)
    base = ruta_registro(registro) / modelo_id / version
    salida = []
    if (base / "decision.json").is_file():
        d = json.loads((base / "decision.json").read_text(encoding="utf-8"))
        salida.append({"id": hashlib.sha256(_canon(d).encode()).hexdigest()[:16], "version": version,
                       "artefacto_huella": d.get("artefacto_huella"), "estado_maximo": d.get("estado_maximo"),
                       "decision": d.get("decision"), "origen_datos": d.get("origen_datos"), "aprobado_por": d.get("aprobado_por"),
                       "actor": None, "procedencia": "decision_inicial (decision.json)", "ts": None, "documento": d})
    salida.extend(a for a in reg.get("autorizaciones", []) if a.get("version") == version)
    return salida


def autorizacion_vigente(registro, modelo_id: str, version: str, huella: str, reg: dict | None = None) -> dict | None:
    validas = [a for a in autorizaciones(registro, modelo_id, version, reg) if a.get("artefacto_huella") == huella]
    return validas[-1] if validas else None


def _cargar_version(registro, modelo_id: str, version: str) -> Artefacto:
    ruta = ruta_registro(registro) / modelo_id / version
    if not (ruta / "artefacto.json").is_file():
        raise RegistroError(f"La versión {version} no existe en el registro de {modelo_id}")
    try:
        return cargar_artefacto(ruta, modelo_id=modelo_id)
    except ArtefactoInvalido as exc:
        raise RegistroError(f"La versión {version} está alterada o es incompatible: {exc}") from exc


def artefacto_registrado(registro: str | Path | None, modelo_id: str, estado: str = "operativo") -> tuple[Artefacto, dict]:
    """Artefacto del puntero ``estado``, validado, con la huella registrada y autorización vigente."""
    reg = leer_registro(registro, modelo_id)
    puntero = reg.get(estado)
    if not puntero:
        etiqueta = "operativa" if estado == "operativo" else "en sombra"
        raise ModeloNoDisponible(f"No hay versión {etiqueta} registrada del modelo {modelo_id}; se aplican solo las reglas.")
    try:
        art = cargar_artefacto(ruta_registro(registro) / modelo_id / puntero["version"], modelo_id=modelo_id)
    except ArtefactoInvalido as exc:
        raise ModeloNoDisponible(f"Versión {estado} {puntero['version']} incompatible: {exc}") from exc
    if art.huella != puntero.get("huella"):
        raise ModeloNoDisponible(f"La huella de {puntero['version']} no coincide con el registro")
    vigente = autorizacion_vigente(registro, modelo_id, puntero["version"], art.huella, reg)
    if not permite(vigente, estado):
        raise ModeloNoDisponible(f"La versión {puntero['version']} ya no tiene autorización vigente para '{estado}'")
    try:  # también al leer: una autorización editada a mano no concede el estado
        validar_autorizacion(vigente["documento"], art, modo_demostracion(reg))
    except RegistroError as exc:
        raise ModeloNoDisponible(f"La autorización vigente de {puntero['version']} no es válida: {exc}") from exc
    return art, dict(puntero, estado=estado)


# Escritura de versiones y punteros --------------------------------------------------------
def _registrar_version(base: Path, version: str, art: Artefacto, decision: dict, origen: dict) -> None:
    destino = base / version
    if destino.exists():
        return
    base.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".{version}.", dir=base))
    try:
        for nombre, datos in (("artefacto.json", art.datos), ("decision.json", decision), ("origen.json", origen)):
            (tmp / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.rename(destino)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def _puntero(version: str, art: Artefacto, aut: dict) -> dict:
    return {"version": version, "huella": art.huella, "artefacto_version": art.version, "desde": _ahora(),
            "decision": aut.get("decision"), "origen_datos": aut.get("origen_datos"), "autorizacion_id": aut.get("id")}


def _mover(reg: dict, estado: str, version: str | None, puntero: dict | None, accion: str, actor: str, **extra) -> None:
    anterior = reg.get(estado)
    reg[estado] = puntero
    reg.setdefault("historial", []).append({"ts": _ahora(), "accion": accion, "estado": estado, "version": version,
                                            "anterior": anterior["version"] if anterior else None, "actor": actor, **extra})
    if estado == "operativo" and version and reg.get("sombra") and reg["sombra"]["version"] == version:
        _mover(reg, "sombra", None, None, "retirar", actor, motivo=f"{version} pasa a operativo")


def autorizar(registro: str | Path | None, modelo_id: str, version: str, decision: dict, actor: str,
              procedencia: str) -> dict[str, Any]:
    """Añade una autorización a una versión registrada sin mover punteros."""
    art = _cargar_version(registro, modelo_id, version)
    reg = leer_registro(registro, modelo_id)
    validar_autorizacion(decision, art, modo_demostracion(reg))
    if any(_canon(a["documento"]) == _canon(decision) for a in autorizaciones(registro, modelo_id, version, reg)):
        return reg  # ya registrada: idempotente
    reg["autorizaciones"].append(_evento_autorizacion(version, decision, actor, procedencia))
    reg["historial"].append({"ts": _ahora(), "accion": "autorizar", "estado": None, "version": version,
                             "estado_maximo": decision["estado_maximo"], "actor": actor})
    _escribir_atomico(ruta_registro(registro) / modelo_id / "registro.json", reg)
    return reg


def promover(registro: str | Path | None, modelo_id: str, version: str, artefacto: Artefacto, decision: dict,
             origen: dict, estado: str, actor: str = "cli", procedencia: str = "promover") -> dict[str, Any]:
    """Registra la versión (si no existe), añade la autorización si es nueva y mueve el puntero.

    Todas las comprobaciones se hacen antes de escribir; un rechazo deja el registro intacto.
    """
    if estado not in ESTADOS:
        raise RegistroError(f"Estado desconocido: {estado}")
    if artefacto.datos.get("modelo_id", "compra_30d") != modelo_id:
        raise RegistroError(f"El artefacto {artefacto.version} es de {artefacto.datos.get('modelo_id')!r}; no se registra en {modelo_id}")
    base = ruta_registro(registro) / modelo_id
    reg = leer_registro(registro, modelo_id)
    validar_autorizacion(decision, artefacto, modo_demostracion(reg))
    existe = (base / version / "artefacto.json").is_file()
    nueva = None
    if existe:
        actual = _cargar_version(registro, modelo_id, version)
        if actual.huella != artefacto.huella:
            raise RegistroError(f"La versión {version} ya existe con otro contenido; usa una versión nueva")
        if not any(_canon(a["documento"]) == _canon(decision) for a in autorizaciones(registro, modelo_id, version, reg)):
            nueva = _evento_autorizacion(version, decision, actor, procedencia)
        vigente = nueva or autorizacion_vigente(registro, modelo_id, version, artefacto.huella, reg)
    else:
        vigente = _evento_autorizacion(version, decision, actor, "decision_inicial (decision.json)")
    if not permite(vigente, estado):
        raise RegistroError(f"La autorización vigente de {version} ('{(vigente or {}).get('decision')}', estado máximo "
                            f"'{(vigente or {}).get('estado_maximo')}') no autoriza el estado '{estado}'")
    if estado == "sombra" and reg.get("operativo") and reg["operativo"]["version"] == version:
        raise RegistroError(f"{version} ya es la versión operativa; no puede estar también en sombra")
    if not existe:
        _registrar_version(base, version, artefacto, decision, origen)
    cambio = False
    if nueva:
        reg["autorizaciones"].append(nueva)
        reg["historial"].append({"ts": _ahora(), "accion": "autorizar", "estado": None, "version": version,
                                 "estado_maximo": nueva["estado_maximo"], "actor": actor})
        cambio = True
    actual_ptr = reg.get(estado)
    if not (actual_ptr and actual_ptr["version"] == version and actual_ptr.get("huella") == artefacto.huella):
        _mover(reg, estado, version, _puntero(version, artefacto, vigente), "promover", actor)
        cambio = True
    if cambio:
        _escribir_atomico(base / "registro.json", reg)
    return reg


def _pila(reg: dict, estado: str) -> list[str]:
    """Secuencia efectiva de versiones del puntero: promover apila, revertir/retirar desapila."""
    pila: list[str] = []
    for h in reg.get("historial", []):
        if h.get("estado") != estado:
            continue
        v = h.get("version")
        if h.get("accion") == "promover":
            if not pila or pila[-1] != v:
                pila.append(v)
        elif h.get("accion") in ("revertir", "retirar"):
            if v is None:
                pila = []
            elif v in pila:
                pila = pila[:pila.index(v) + 1]
            else:
                pila.append(v)
    return pila


def revertir(registro: str | Path | None, modelo_id: str, estado: str = "operativo", a: str | None = None,
             actor: str = "cli") -> dict[str, Any]:
    """Restituye la versión anterior distinta y autorizada del puntero (o ``a``) sin borrar versiones."""
    if estado not in ESTADOS:
        raise RegistroError(f"Estado desconocido: {estado}")
    reg = leer_registro(registro, modelo_id)
    actual = reg.get(estado)
    actual_v = actual["version"] if actual else None

    def utilizable(v: str) -> tuple[Artefacto, dict] | None:
        art = _cargar_version(registro, modelo_id, v)
        aut = autorizacion_vigente(registro, modelo_id, v, art.huella, reg)
        if not permite(aut, estado):
            return None
        validar_autorizacion(aut["documento"], art, modo_demostracion(reg))
        return art, aut

    omitidas = []
    destino = None
    if a is not None:
        r = utilizable(a)
        if r is None:
            raise RegistroError(f"{a} no tiene autorización vigente para '{estado}'")
        destino = (a, *r)
    else:
        for v in reversed(_pila(reg, estado)):
            if v == actual_v:
                continue
            try:
                r = utilizable(v)
            except RegistroError as exc:
                omitidas.append({"version": v, "motivo": str(exc)})
                continue
            if r is None:
                omitidas.append({"version": v, "motivo": f"sin autorización vigente para '{estado}'"})
                continue
            destino = (v, *r)
            break
        if destino is None and estado == "operativo":
            raise RegistroError("No hay una versión operativa anterior distinta y autorizada a la que volver"
                                + (f" (omitidas: {omitidas})" if omitidas else ""))
    if destino is not None:
        v, art, aut = destino
        if estado == "sombra" and reg.get("operativo") and reg["operativo"]["version"] == v:
            raise RegistroError(f"{v} es la versión operativa; no puede pasar a sombra")
        _mover(reg, estado, v, _puntero(v, art, aut), "revertir", actor, **({"omitidas": omitidas} if omitidas else {}))
    else:
        _mover(reg, estado, None, None, "revertir", actor)
    _escribir_atomico(ruta_registro(registro) / modelo_id / "registro.json", reg)
    return reg


def fijar_modo_demostracion(registro: str | Path | None, modelo_id: str, activo: bool, actor: str, motivo: str) -> dict[str, Any]:
    """Activa o apaga el modo demostración (evento en el historial; no mueve punteros)."""
    if not str(actor or "").strip() or not str(motivo or "").strip():
        raise RegistroError("El modo demostración requiere actor y motivo")
    reg = leer_registro(registro, modelo_id)
    if not activo and reg.get("operativo") and reg["operativo"].get("origen_datos") in (None, "sintetico"):
        art = _cargar_version(registro, modelo_id, reg["operativo"]["version"])
        aut = autorizacion_vigente(registro, modelo_id, reg["operativo"]["version"], art.huella, reg)
        if aut and aut["documento"].get("decision") == "demostracion":
            raise RegistroError(f"La versión operativa {reg['operativo']['version']} es de demostración: revierte primero el puntero operativo")
    if modo_demostracion(reg) == activo:
        return reg
    reg["modo_demostracion"] = {"activo": activo, "actor": actor, "motivo": motivo, "ts": _ahora()}
    reg["historial"].append({"ts": _ahora(), "accion": "modo_demostracion", "estado": None, "version": None, "activo": activo,
                             "actor": actor, "motivo": motivo})
    base = ruta_registro(registro) / modelo_id
    base.mkdir(parents=True, exist_ok=True)
    _escribir_atomico(base / "registro.json", reg)
    return reg
