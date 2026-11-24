"""Congelación, evaluación y lectura verificables de las ejecuciones experimentales M1.1, M1.2 y M1.3 (``compra_30d``).

Corrige los tres defectos confirmados en la auditoría (pruebas en ``tests/modelos/test_m1_integridad.py``):

A. Artefacto principal desvinculado: M1.1 evaluaba y la decisión registraba la huella de ``artefacto.json`` sin compararla
   con la congelada. Ahora el candidato seleccionado, ``artefacto.json`` y la huella sellada deben coincidir (y M1.3, que no
   tiene artefacto principal, liga cada candidato por nombre).
B. Evidencia sin proteger: ``desarrollo.json`` (decide M1.2 y M1.3), ``seleccion.json`` y las predicciones de validación
   temporal (M1.1) y los cortes de entrenamiento final (definen la referencia «constante») no estaban sellados. Ahora todos
   los archivos que consume cada evaluador están en el marcador ``congelacion.json`` (huella SHA-256 por archivo) y los
   metadatos que influyen en la evaluación están dentro del sello.
C. Recuperación incompleta: si la evaluación se interrumpía después de las métricas, el reintento fallaba. Ahora métricas y
   decisión se publican con ``ejecucion.publicar_lote`` (escritura atómica, marcador ``evaluacion.json`` al final; un
   reintento conserva lo idéntico, completa lo que falta y rechaza lo distinto).

Formato 3 (ejecuciones nuevas). Campos volátiles (fuera del sello, documentados): fechas reales de congelación y evaluación y
fechas derivadas de ellas (primer corte prospectivo). No influyen en selección, artefacto, periodos, decisión ni promoción.

Formato 2 (ejecuciones históricas, anteriores a esta corrección): NO se resellan. Se verifica todo lo que su formato permite
(sello parcial, artefactos por papel, referencias, protocolo y, en M1.1, que ``artefacto.json`` sea el candidato del papel
sellado) y se declara lo que no puede verificarse. Siguen legibles; no pueden volver a evaluarse ni promoverse con ``promover``:
para una evaluación verificable se reproduce en una ejecución nueva.

Los hashes prueban integridad respecto del marcador, no autenticidad frente a quien puede reemplazar todos los archivos.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .compra import ProtocoloError, _canon, huella_protocolo
from .ejecucion import EjecucionError, ahora_utc, json_bytes, publicar_lote, sha_archivo, verificar_lote

FORMATO_EJECUCION = 3
MARCADOR_CONGELACION = "congelacion.json"
MARCADOR_EVALUACION = "evaluacion.json"
METRICAS = "metricas_comprobacion_historica.json"
DECISION = "decision.json"
PREFIJOS = {"m1.1-": "m11", "m1.2-": "m12", "m1.3-": "m13"}
# Archivos que consume cada evaluador (además de los artefactos y referencias que nombra el marcador).
FIJOS = {
    "m11": ("config.json", "protocolo.json", "datos.json", "entorno.json", "seleccion.json", "artefacto.json", "predicciones_validacion_temporal.csv"),
    "m12": ("config.json", "protocolo.json", "datos.json", "entorno.json", "desarrollo.json", "artefacto.json"),
    "m13": ("config.json", "protocolo.json", "datos.json", "entorno.json", "desarrollo.json"),
}
VOLATILES = ("congelacion_real", "primer_corte_prospectivo", "primer_corte_prospectivo_madura_el")
NO_VERIFICABLE_HEREDADO = {
    "m11": ["seleccion.json", "predicciones_validacion_temporal.csv", "datos.json", "cortes_entrenamiento_final", "fechas", "artefacto_huella del marcador (fuera del sello)"],
    "m12": ["desarrollo.json (decide la comparación)", "datos.json", "cortes_entrenamiento_final", "fechas"],
    "m13": ["desarrollo.json (decide S y P)", "datos.json", "cortes_entrenamiento_final", "fechas"],
}


def variante_de(config: dict) -> str:
    v = str(config.get("version_protocolo", ""))
    for p, nombre in PREFIJOS.items():
        if v.startswith(p):
            return nombre
    raise ProtocoloError(f"version_protocolo {v!r} no corresponde a M1.1, M1.2 ni M1.3")


def _leer(p: Path) -> Any:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _huella_artefacto(p: Path) -> str:
    from .inferencia import ArtefactoInvalido, cargar_artefacto
    try:
        a = cargar_artefacto(p)
    except ArtefactoInvalido as exc:
        raise ProtocoloError(f"{p.name}: artefacto inválido ({exc})") from exc
    if a.datos.get("modelo_id", "compra_30d") != "compra_30d" or a.datos.get("horizonte_dias", 30) != 30:
        raise ProtocoloError(f"{p.name}: no es un artefacto de compra_30d a 30 días")
    return a.huella


def nombres_artefactos(variante: str, meta: dict) -> dict[str, str]:
    """Archivo → huella esperada de todos los artefactos que nombra el marcador."""
    out = {f"referencia_{n}.json": r["huella"] for n, r in meta["referencias"].items()}
    if variante == "m11":
        for papel, e in meta["artefactos"].items():
            for v in ("sin_calibrar", "calibrado"):
                if v in e:
                    out[f"artefacto_{papel}_{v}.json"] = e[v]
        out["artefacto.json"] = meta["artefacto_huella"]
    elif variante == "m12":
        out["artefacto.json"] = meta["artefacto_huella"]
    else:
        out.update({f"artefacto_{n}.json": h for n, h in meta["artefactos"].items()})
    return out


def requeridos(variante: str, meta: dict) -> set[str]:
    return set(FIJOS[variante]) | set(nombres_artefactos(variante, meta))


def guardar_protocolo_inicial(salida: Path, config: dict, protocolo: dict) -> dict[str, bytes]:
    """Escribe config y protocolo ANTES de ajustar. En un reintento tras una interrupción reutiliza los existentes si
    corresponden al mismo protocolo (conserva su fecha de registro); si son de otro protocolo, rechaza."""
    from .ejecucion import escribir_atomico
    out = {}
    for nombre, doc in (("config.json", config), ("protocolo.json", protocolo)):
        ruta = salida / nombre
        if ruta.exists():
            previo = _leer(ruta)
            mismo = huella_protocolo(previo) == huella_protocolo(config) if nombre == "config.json" else previo.get("huella") == protocolo["huella"]
            if not mismo:
                raise ProtocoloError(f"{ruta} pertenece a otro protocolo; usa otra carpeta de ejecución")
            out[nombre] = ruta.read_bytes()
        else:
            out[nombre] = json_bytes(doc)
            escribir_atomico(ruta, out[nombre])
    return out


def metadatos_comunes(config: dict, protocolo: dict, refs: dict, datos, cortes_final, h: int) -> tuple[dict, dict]:
    """(metadatos sellados, fechas volátiles). Las fechas reales y sus derivadas quedan FUERA del sello: no influyen en nada."""
    from datetime import datetime, timedelta, timezone
    from .compra import _primer_fin_de_mes_posterior
    hoy = datetime.now(timezone.utc).date()
    primer = _primer_fin_de_mes_posterior(hoy)
    meta = {"protocolo": {k: protocolo[k] for k in ("version", "huella")}, "referencias": refs, "huella_datos": datos.huella_datos,
            "revision_datos": datos.revision, "cortes_entrenamiento_final": [c.isoformat() for c in cortes_final],
            "bloques_usados": ["desarrollo"], "bloque_reservado": "comprobacion_historica",
            "fechas": {"disponibilidad_simulada_desde": config["disponible_desde"], "datos_observados_hasta": datos.observado_hasta.isoformat(),
                       "nota": "julio–septiembre y octubre de 2026 son comprobaciones retrospectivas; las fechas reales están en 'volatiles'"}}
    volatiles = {"congelacion_real": hoy.isoformat(), "primer_corte_prospectivo": primer.isoformat(),
                 "primer_corte_prospectivo_madura_el": (primer + timedelta(days=h)).isoformat()}
    return meta, volatiles


def huellas_codigo(*modulos: str) -> dict[str, str]:
    """Versión del código que entrena y evalúa (SHA-256 de los módulos), dentro del sello."""
    base = Path(__file__).resolve().parent
    return {m: sha_archivo(base / m) for m in ("compra.py", "compra_m11.py", "compra_m1_ejecucion.py", "ejecucion.py", "inferencia.py",
                                                "metricas.py", "variables.py", *modulos)}


def congelar(salida: Path, variante: str, archivos: dict[str, bytes], meta: dict, fechas_volatiles: dict) -> dict:
    """Publica la ejecución congelada (formato 3). ``meta`` queda dentro del sello; solo ``fechas_volatiles`` fuera."""
    from .compra import _hoy_utc
    meta = dict(meta, formato=FORMATO_EJECUCION, modelo_id="compra_30d", variante=variante)
    faltan = requeridos(variante, meta) - set(archivos)
    if faltan:
        raise ProtocoloError(f"Faltan archivos obligatorios de {variante} en la congelación: {sorted(faltan)}")
    try:
        marcador = publicar_lote(salida, archivos, MARCADOR_CONGELACION, meta, volatiles=dict(fechas_volatiles, congelado_en=_hoy_utc()))
    except EjecucionError as exc:
        raise ProtocoloError(str(exc)) from exc
    return verificar(salida, variante) and marcador


def es_formato_nuevo(cong: dict) -> bool:
    return cong.get("formato") == FORMATO_EJECUCION and isinstance(cong.get("archivos"), dict)


def _coherencia(d: Path, variante: str, m: dict) -> None:
    config = _leer(d / "config.json")
    if variante_de(config) != variante or m.get("variante") != variante or m.get("modelo_id") != "compra_30d":
        raise ProtocoloError(f"La ejecución no es de {variante} (config {config.get('version_protocolo')!r}, marcador {m.get('variante')!r})")
    if huella_protocolo(config) != m["protocolo"]["huella"] or config["version_protocolo"] != m["protocolo"]["version"]:
        raise ProtocoloError("El protocolo de la ejecución no coincide con el congelado")
    if _leer(d / "protocolo.json").get("huella") != m["protocolo"]["huella"]:
        raise ProtocoloError("protocolo.json no corresponde al protocolo congelado")
    if _leer(d / "datos.json").get("huella_datos") != m["huella_datos"]:
        raise ProtocoloError("datos.json no corresponde a los datos congelados")
    for nombre, h in nombres_artefactos(variante, m).items():
        if _huella_artefacto(d / nombre) != h:
            raise ProtocoloError(f"{nombre} no coincide con la huella congelada (otro candidato u otra ejecución)")
    if variante == "m11":
        g = m["artefactos"]["global"]
        if g.get(g["usar"]) != m["artefacto_huella"]:
            raise ProtocoloError("El artefacto principal no es el candidato global seleccionado")
        if _leer(d / "seleccion.json").get("global") != g["id"]:
            raise ProtocoloError("seleccion.json no coincide con el candidato congelado")


def _verificar_heredado(d: Path, variante: str, cong: dict) -> dict:
    """Formato 2: lo que su propio sello permite verificar, sin resellar."""
    config = _leer(d / "config.json")
    if huella_protocolo(config) != cong["protocolo"]["huella"]:
        raise ProtocoloError(f"El protocolo de {d} cambió después de congelarse")
    sellados = ("protocolo", "artefactos", "referencias", "huella_datos") if variante != "m12" else ("protocolo", "artefacto_huella", "referencias", "huella_datos")
    if hashlib.sha256(_canon({k: cong[k] for k in sellados}).encode()).hexdigest() != cong.get("sello"):
        raise ProtocoloError("congelacion.json fue alterado (el sello no coincide)")
    for nombre, r in cong["referencias"].items():
        if _huella_artefacto(d / f"referencia_{nombre}.json") != r["huella"]:
            raise ProtocoloError(f"La referencia {nombre} no coincide con la congelada")
    if variante == "m11":
        for papel, e in cong["artefactos"].items():
            for v in ("sin_calibrar", "calibrado"):
                if v in e and _huella_artefacto(d / f"artefacto_{papel}_{v}.json") != e[v]:
                    raise ProtocoloError(f"artefacto_{papel}_{v}.json no coincide con el congelado")
        g = cong["artefactos"]["global"]
        if _huella_artefacto(d / "artefacto.json") != g[g["usar"]]:  # verificable con el sello antiguo
            raise ProtocoloError("artefacto.json no es el candidato global sellado")
    elif variante == "m12":
        if _huella_artefacto(d / "artefacto.json") != cong["artefacto_huella"]:
            raise ProtocoloError("El artefacto no coincide con el congelado")
    else:
        for n, h in cong["artefactos"].items():
            if _huella_artefacto(d / f"artefacto_{n}.json") != h:
                raise ProtocoloError(f"artefacto_{n}.json no coincide con el congelado")
    return dict(cong, verificacion={"formato": 2, "nivel": "parcial", "no_verificable": NO_VERIFICABLE_HEREDADO[variante],
                                    "politica": "formato antiguo: legible, no reevaluable ni promovible con 'promover'; reproducir en una ejecución nueva"})


def verificar(ejecucion: str | Path, variante: str | None = None) -> dict:
    """Congelación verificada (formato 3 completo o formato 2 parcial, con ``verificacion`` que lo indica)."""
    d = Path(ejecucion)
    if not (d / MARCADOR_CONGELACION).exists():
        raise ProtocoloError(f"{d} no tiene {MARCADOR_CONGELACION}: la ejecución no terminó de congelarse")
    variante = variante or variante_de(_leer(d / "config.json"))
    cong = _leer(d / MARCADOR_CONGELACION)
    if not es_formato_nuevo(cong):
        return _verificar_heredado(d, variante, cong)
    m = verificar_lote(d, MARCADOR_CONGELACION, ProtocoloError)
    faltan = requeridos(variante, m) - set(m["archivos"])
    if faltan:
        raise ProtocoloError(f"El marcador no protege archivos obligatorios: {sorted(faltan)}")
    _coherencia(d, variante, m)
    return dict(m, verificacion={"formato": FORMATO_EJECUCION, "nivel": "completo", "no_verificable": []})


def exigir_formato_nuevo(cong: dict) -> None:
    if cong["verificacion"]["formato"] != FORMATO_EJECUCION:
        raise ProtocoloError("Ejecución en formato antiguo (2): sus evidencias de desarrollo no están protegidas. Se puede leer, pero no "
                             "volver a evaluar ni promover; reproduce el protocolo en una ejecución nueva.")


def vinculos_decision(variante: str, cong: dict) -> dict:
    v = {"sello_congelacion": cong["sello"], "huella_datos": cong["huella_datos"], "protocolo_huella": cong["protocolo"]["huella"], "variante": variante}
    if variante == "m13":
        v["artefactos"] = dict(cong["artefactos"])
    else:
        v["artefacto_huella"] = cong["artefacto_huella"]
    return v


def publicar_evaluacion(ejecucion: Path, variante: str, cong: dict, metricas: dict, decision: dict) -> dict:
    """Métricas y decisión atómicas; ``evaluacion.json`` al final. Fecha real de la primera evaluación fuera del sello."""
    vinc = vinculos_decision(variante, cong)
    decision = dict(decision, **vinc)
    try:
        publicar_lote(ejecucion, {METRICAS: json_bytes(metricas), DECISION: json_bytes(decision)}, MARCADOR_EVALUACION,
                      dict(vinc, modelo_id="compra_30d"), volatiles={"fecha_evaluacion": ahora_utc()})
    except EjecucionError as exc:
        raise ProtocoloError(str(exc)) from exc
    return evaluacion_publicada(ejecucion, variante)


def evaluacion_publicada(ejecucion: str | Path, variante: str | None = None) -> dict:
    """Evaluación TERMINADA y vinculada a la congelación vigente (formato 3). Una evaluación incompleta no se consume."""
    d = Path(ejecucion)
    cong = verificar(d, variante)
    variante = cong.get("variante") or variante or variante_de(_leer(d / "config.json"))
    exigir_formato_nuevo(cong)
    if not (d / MARCADOR_EVALUACION).exists():
        raise ProtocoloError(f"{d} no tiene {MARCADOR_EVALUACION}: la evaluación no terminó (reintenta 'evaluar' para completarla)")
    ev = verificar_lote(d, MARCADOR_EVALUACION, ProtocoloError)
    dec = _leer(d / DECISION)
    for k, v in vinculos_decision(variante, cong).items():
        if ev.get(k) != v or dec.get(k) != v:
            raise ProtocoloError(f"La evaluación o la decisión no corresponden a la congelación vigente ({k})")
    return {"congelacion": cong, "evaluacion": ev, "decision": dec, "metricas": _leer(d / METRICAS)}


def leer_evaluacion(ejecucion: str | Path, variante: str | None = None) -> dict:
    """Lectura para informes: formato 3 verificado; formato 2 en solo lectura con su verificación parcial declarada."""
    d = Path(ejecucion)
    cong = verificar(d, variante)
    if cong["verificacion"]["formato"] == FORMATO_EJECUCION:
        return evaluacion_publicada(d, variante)
    return {"congelacion": cong, "evaluacion": None, "decision": _leer(d / DECISION), "metricas": _leer(d / METRICAS),
            "verificacion": dict(cong["verificacion"], evaluacion="métricas y decisión no selladas (formato 2)")}


def decision_para_registro(ejecucion: str | Path, candidato: str | None = None) -> tuple[Path, dict]:
    """(artefacto, decisión) de una evaluación terminada y verificada, para ``promover``. M1.3 exige el candidato."""
    pub = evaluacion_publicada(ejecucion)
    d, cong, dec = Path(ejecucion), pub["congelacion"], pub["decision"]
    if cong["variante"] == "m13":
        if candidato not in cong["artefactos"]:
            raise ProtocoloError(f"M1.3 requiere --candidato entre {sorted(cong['artefactos'])}")
        c = (dec.get("candidatos") or {}).get(candidato)
        if c is None:
            raise ProtocoloError(f"La decisión no evalúa el candidato {candidato}")
        doc = dict(c, artefacto_huella=cong["artefactos"][candidato], origen_datos=dec["origen_datos"], version_protocolo=dec["version_protocolo"],
                   sello_congelacion=cong["sello"], candidato=candidato)
        return d / f"artefacto_{candidato}.json", doc
    if candidato:
        raise ProtocoloError(f"{cong['variante']} tiene un único artefacto principal; no uses --candidato")
    return d / "artefacto.json", dec


def huella_directorio(d: str | Path) -> dict[str, str]:
    """Huellas de todos los archivos (evidencia de que una ejecución histórica no cambió)."""
    d = Path(d)
    return {str(p.relative_to(d)).replace("\\", "/"): sha_archivo(p) for p in sorted(d.rglob("*")) if p.is_file()}
