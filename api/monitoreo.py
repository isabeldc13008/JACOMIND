"""Monitoreo reutilizable de publicaciones de modelos (M6 en adelante): avisos persistentes e idempotentes.

* Integridad: una publicación que no cumple el contrato no se importa; el rechazo queda como aviso ``integridad``.
* Estadísticos: caída de cobertura y cambio de la tasa de alertas frente a la publicación activa anterior, con umbrales
  configurados en el protocolo del modelo (copiados en el manifiesto) y el soporte de cada comparación. Un cambio de
  distribución NO prueba deterioro predictivo; ningún aviso promociona ni revierte modelos.
"""
from __future__ import annotations

import hashlib

from .base import BaseDatos, ahora, dumps, loads


def registrar_aviso(con, clave: str, modelo_id: str, tipo: str, severidad: str, mensaje: str, datos=None, sombra_id: str | None = None) -> bool:
    """Inserta el aviso una sola vez por clave. Devuelve True si es nuevo."""
    cur = con.execute("""INSERT OR IGNORE INTO avisos_modelos (clave, modelo_id, sombra_id, tipo, severidad, mensaje, datos_json, creado_en)
                         VALUES (?,?,?,?,?,?,?,?)""", (clave, modelo_id, sombra_id, tipo, severidad, mensaje, dumps(datos) if datos is not None else None, ahora()))
    return cur.rowcount == 1


def registrar_integridad(db: BaseDatos, modelo_id: str, errores: list[str], origen: str) -> None:
    """Aviso de integridad en una transacción propia (la importación rechazada no deja filas)."""
    huella = hashlib.sha256(("\n".join(errores) + origen).encode()).hexdigest()[:16]
    with db.transaccion() as con:
        registrar_aviso(con, f"integridad:{modelo_id}:{huella}", modelo_id, "publicacion_rechazada", "integridad",
                        f"Publicación rechazada por integridad ({len(errores)} errores): no se importó.", {"origen": origen, "errores": errores[:10]})


def comparar(actual: dict, previo: dict | None, umbrales: dict) -> list[dict]:
    """Avisos estadísticos entre dos bloques ``monitoreo.universos`` (actual frente a la publicación activa anterior)."""
    if not previo:
        return []
    out = []
    for u, a in (actual or {}).items():
        p = (previo or {}).get(u)
        if not p or not a.get("validas") or not p.get("validas"):
            continue
        if a.get("cobertura") is not None and p.get("cobertura") is not None:
            caida = round(100 * (p["cobertura"] - a["cobertura"]), 4)
            if caida >= float(umbrales["caida_cobertura_pp"]):
                out.append({"tipo": "caida_cobertura", "universo": u, "datos": {"previa": p["cobertura"], "actual": a["cobertura"], "caida_pp": caida,
                                                                                "umbral_pp": umbrales["caida_cobertura_pp"], "validas": [p["validas"], a["validas"]]},
                            "mensaje": f"{u}: la cobertura de puntuación bajó {caida} pp ({p['cobertura']:.1%} → {a['cobertura']:.1%}); revisar historia o datos."})
        n_min = int(umbrales["min_operaciones_comparacion"])
        ta, tp = a.get("alertas_por_100_validas"), p.get("alertas_por_100_validas")
        if ta is not None and tp and a["validas"] >= n_min and p["validas"] >= n_min:
            rel = abs(ta - tp) / tp
            if rel >= float(umbrales["cambio_relativo_tasa_alertas"]):
                out.append({"tipo": "cambio_tasa_alertas", "universo": u,
                            "datos": {"previa_por_100": tp, "actual_por_100": ta, "cambio_relativo": round(rel, 4), "umbral": umbrales["cambio_relativo_tasa_alertas"],
                                      "validas": [p["validas"], a["validas"]]},
                            "mensaje": f"{u}: alertas por 100 válidas {tp} → {ta} (cambio relativo {rel:.0%}, n={p['validas']}→{a['validas']}). "
                                       "Con política de cupo la tasa depende del cupo y de la cobertura: no indica deterioro predictivo sin revisiones comparables."})
    return out


def avisos(con, modelo_id: str) -> list[dict]:
    return [dict(r, datos=loads(r["datos_json"]) if r["datos_json"] else None) | {"datos_json": None}
            for r in (dict(x) for x in con.execute("SELECT * FROM avisos_modelos WHERE modelo_id = ? ORDER BY creado_en DESC, clave", (modelo_id,)))]
