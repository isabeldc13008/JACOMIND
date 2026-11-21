"""Clasificación inicial de PQRS con revisión humana (A10)."""
from __future__ import annotations

KEYWORDS = {"peticion": ("solicito", "quiero", "necesito"), "queja": ("queja", "inconforme", "cobro"), "reclamo": ("reclamo", "devolución", "incumpl"), "sugerencia": ("sugiero", "sugerencia", "propon")}

def clasificar_pqrs(texto: str) -> dict[str, object]:
    lower = (texto or "").lower()
    scores = {category: sum(lower.count(token) for token in tokens) for category, tokens in KEYWORDS.items()}
    category, score = max(scores.items(), key=lambda item: item[1]) if lower else ("revision_manual", 0)
    if not score or sum(value > 0 for value in scores.values()) > 1:
        return {"categoria": "revision_manual", "confianza": 0.0, "motivo": "texto vacío o múltiples intenciones", "version": "reglas-v1"}
    return {"categoria": category, "confianza": min(1.0, 0.5 + score * 0.2), "motivo": "palabras clave", "version": "reglas-v1"}
