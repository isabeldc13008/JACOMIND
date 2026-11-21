"""Documentación del proyecto como fuente citable del asistente interno.

Indexa ``README.md``, ``docs/*.md`` y ``docs/plan/*.md`` por secciones («##» y «###») y
recupera las más parecidas a una consulta con BM25 sobre las mismas palabras normalizadas que
usa el buscador de políticas. Cada resultado se cita como «archivo › sección».
"""
from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache

from .base import RAIZ
from .documentos import tokens

FUENTES = ["README.md", "docs/*.md", "docs/plan/*.md"]
K1, B = 1.4, 0.75


@lru_cache(maxsize=1)
def _indice() -> tuple[list[dict], dict[str, int], float]:
    secciones: list[dict] = []
    for patron in FUENTES:
        for ruta in sorted(RAIZ.glob(patron)):
            texto = ruta.read_text(encoding="utf-8", errors="replace")
            rel = ruta.relative_to(RAIZ).as_posix()
            titulo_doc = next((l.lstrip("# ").strip() for l in texto.splitlines() if l.startswith("# ")), rel)
            partes = re.split(r"(?m)^(#{2,3} .+)$", texto)
            bloques = [("Introducción", partes[0])] + [(partes[i].lstrip("# ").strip(), partes[i + 1]) for i in range(1, len(partes) - 1, 2)]
            for seccion, cuerpo in bloques:
                cuerpo = cuerpo.strip()
                if len(cuerpo) < 40:
                    continue
                toks = tokens(f"{seccion} {cuerpo}")
                secciones.append({"archivo": rel, "documento": titulo_doc, "seccion": seccion, "texto": cuerpo,
                                  "tf": Counter(toks), "largo": len(toks)})
    df: Counter = Counter()
    for s in secciones:
        df.update(set(s["tf"]))
    promedio = sum(s["largo"] for s in secciones) / max(1, len(secciones))
    return secciones, dict(df), promedio


def buscar(consulta: str, k: int = 4) -> list[dict]:
    secciones, df, promedio = _indice()
    q = set(tokens(consulta))
    n = len(secciones)
    puntuadas = []
    for s in secciones:
        p = 0.0
        for t in q:
            f = s["tf"].get(t)
            if not f:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            p += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * s["largo"] / promedio))
        if p > 0:
            puntuadas.append((p, s))
    puntuadas.sort(key=lambda x: -x[0])
    return [{"archivo": s["archivo"], "documento": s["documento"], "seccion": s["seccion"],
             "texto": s["texto"][:1800], "puntuacion": round(p, 3)} for p, s in puntuadas[:k]]
