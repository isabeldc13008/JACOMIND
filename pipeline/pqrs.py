"""Clasificación inicial de PQRS con revisión humana (A10).

La salida cumple el contrato C4 (``contratos/asistencia.v1.schema.json``):
``categoria`` (o ``None`` si se deriva a revisión), ``confianza``, ``version``,
``revisar`` y ``motivo``. La etiqueta corregida por Atención prevalece siempre.
"""
from __future__ import annotations

import unicodedata

VERSION = "reglas-v2"
UMBRAL_CONFIANZA = 0.6
KEYWORDS = {
    "peticion": ("solicito", "quiero", "necesito", "quisiera", "informacion", "certificado"),
    "queja": ("queja", "inconforme", "cobro", "demora", "mal servicio"),
    "reclamo": ("reclamo", "devolucion", "incumpl", "reembolso", "garantia"),
    "sugerencia": ("sugiero", "sugerencia", "propon", "recomiendo"),
}


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


def clasificar_pqrs(texto: str) -> dict[str, object]:
    lower = _normalizar(texto)
    scores = {category: sum(lower.count(token) for token in tokens) for category, tokens in KEYWORDS.items()}
    activas = [c for c, s in scores.items() if s > 0]
    if not lower.strip() or not activas:
        return {"categoria": None, "confianza": 0.0, "revisar": True, "motivo": "texto vacío o sin señales reconocibles", "version": VERSION}
    if len(activas) > 1:
        return {"categoria": None, "confianza": 0.0, "revisar": True, "motivo": "múltiples intenciones", "version": VERSION}
    category = activas[0]
    confianza = min(1.0, 0.5 + scores[category] * 0.2)
    return {"categoria": category, "confianza": confianza, "revisar": confianza < UMBRAL_CONFIANZA,
            "motivo": "palabras clave", "version": VERSION}


# Nombre esperado por la aplicación (punto de enganche C4).
clasificar = clasificar_pqrs
