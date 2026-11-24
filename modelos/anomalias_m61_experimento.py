"""M6.1 · Protocolo experimental (``m61-protocolo-v1``): reutiliza la preparación, la exportación verificada del bosque, la
congelación y la publicación de M6, y cambia evidencia, catálogo, dirección de la cantidad, cupo máximo, siembra y regla.

La comprobación de M6.1 es EXPLORATORIA y no independiente: los datos y la comprobación de M6 ya se vieron y sirvieron para
diagnosticar M6. La referencia de M6 (cupo obligatorio) se mide sobre los mismos casos solo como contexto.
"""
from __future__ import annotations

import copy
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from . import anomalias as A
from . import anomalias_experimento as E
from . import anomalias_m61 as M
from .ejecucion import ahora_utc, canon, json_bytes, publicar_lote, sha

ProtocoloM6Error = E.ProtocoloM6Error
CONFIG = Path(__file__).resolve().parent / "config" / "anomalias_m61.json"


def cargar_config(ruta=None) -> dict:
    c = E.cargar_config(ruta or CONFIG)
    if not M.es_m61(c):
        raise ProtocoloM6Error("La configuración no es de M6.1")
    return c


def preparar(datos, compras, config) -> dict:
    prep = E.preparar(datos, compras, config)
    prep["contextos"] = {k: (dict(c, variables=dict(c["variables"], z_log_cantidad_alta=max(0.0, c["variables"]["z_log_cantidad"])))
                             if c["estado"] == "puntuada" else c) for k, c in prep["contextos"].items()}
    prep["catalogo"] = M.catalogo(datos)
    return prep


# Casos sembrados M6.1 -------------------------------------------------------------------------------------------------
def casos(prep: Mapping, config: Mapping, bloque: str) -> list[dict]:
    cs = config["casos_sembrados"]
    out = []
    for u in A.UNIVERSOS:
        pob = sorted([o for o in prep["ops"] if o["tipo_operacion"] == u and E.bloque_de(o["fecha"], config) == bloque
                      and prep["contextos"][(u, o["operacion_id"])]["estado"] == "puntuada"], key=lambda o: o["operacion_id"])
        semilla = f"{cs['semilla']}:{u}:{bloque}"
        bases = random.Random(semilla).sample(pob, min(int(cs["bases_por_bloque"][u]), len(pob)))
        for base in sorted(bases, key=lambda o: o["operacion_id"]):
            comun = {"base": {"tipo_operacion": u, "operacion_id": base["operacion_id"]}, "bloque": bloque, "semilla": semilla}
            maximo = max(a[2] for a in prep["historial"].antecedentes(A.grupo(base), base["fecha"]))
            clave_b = "validacion" if bloque == "validacion" else "comprobacion"
            for tipo, por_bloque in cs["tipos"][u].items():
                for inten in por_bloque[clave_b]:
                    op = copy.deepcopy(base)
                    if tipo in ("precio_elevado", "precio_bajo", "costo_alterado"):
                        op["valor_unitario"] = round(base["valor_unitario"] * inten, 6)
                    elif tipo == "cantidad_extrema":
                        op["cantidad"] = float(math.ceil(maximo * inten))
                    else:
                        pf, qf = inten
                        op["valor_unitario"] = round(base["valor_unitario"] * pf, 6)
                        op["cantidad"] = float(max(1, round(base["cantidad"] * qf)))
                    etiqueta = "x".join(f"{x:g}" for x in (inten if isinstance(inten, list) else [inten]))
                    op["operacion_id"] = f"SEM61-{bloque[:4].upper()}-{base['operacion_id']}-{tipo}-{etiqueta}"
                    motivo = f"{tipo} ×{etiqueta}" + (f" del máximo histórico ({maximo:g})" if tipo == "cantidad_extrema" else "") + f" sobre {base['operacion_id']}"
                    out.append(dict(comun, caso_id=op["operacion_id"], clase="anomalia_sembrada", transformacion=tipo, intensidad=inten,
                                    etiqueta_sintetica="anomalia", motivo=motivo, op=E._recalcular(op)))
            for c in E._controles(base, comun, prep, config, bloque):
                c["op"]["operacion_id"] = c["caso_id"] = c["caso_id"].replace("CTL-", "CTL61-", 1)
                out.append(c)
            extra = [("cantidad_baja_habitual", {"cantidad": 1.0}, "Cantidad 1 (habitual en el paquete)")]
            if u == "venta":
                lista = prep["catalogo"].get(base["producto_id"], {})
                if lista.get("moneda_lista") == base["moneda"]:
                    extra.append(("precio_lista_tras_descuentos", {"valor_unitario": lista["precio_lista"]}, "Venta a precio de lista (descuento 0)"))
            for tipo, cambios, motivo in extra:
                op = dict(copy.deepcopy(base), **cambios)
                op["operacion_id"] = f"CTL61-{bloque[:4].upper()}-{base['operacion_id']}-{tipo}"
                out.append(dict(comun, caso_id=op["operacion_id"], clase="control_negativo", transformacion=tipo, intensidad=None,
                                etiqueta_sintetica="normal_construido", motivo=motivo, op=E._recalcular(op)))
    return out


# Evaluación de un método con evidencia y cupo máximo -------------------------------------------------------------------
def _puntaje(metodo, bosque, variables, c):
    if c["estado"] != "puntuada":
        return None
    return M.puntaje_referencia(c["variables"]) if metodo == "mediana_mad" else bosque.rareza([c["variables"][v] for v in variables])


def _evid(op, c, s, metodo, umbral, prep, config) -> bool:
    if M.evidencias(op, c, config, prep["catalogo"], prep["historial"]):
        return True
    return metodo == "isolation_forest" and s is not None and s >= umbral


def evaluar_metodo(prep, config, cs, bloque, u, metodo, bosque=None, variables=None, umbral=None) -> dict:
    pol = config["politica_alertas"]
    pools: dict[str, list] = defaultdict(list)
    for o in prep["ops"]:
        if o["tipo_operacion"] == u and E.bloque_de(o["fecha"], config) == bloque:
            c = prep["contextos"][(u, o["operacion_id"])]
            s = _puntaje(metodo, bosque, variables, c)
            if s is not None:
                pools[A.periodo(o["fecha"])].append((_evid(o, c, s, metodo, umbral, prep, config), s))
    res = []
    for cso in cs:
        if cso["base"]["tipo_operacion"] != u:
            continue
        c = M.contexto(cso["op"], prep["historial"], config)
        s = _puntaje(metodo, bosque, variables, c)
        base_s = _puntaje(metodo, bosque, variables, prep["contextos"][(u, cso["base"]["operacion_id"])])
        ev = _evid(cso["op"], c, s, metodo, umbral, prep, config) if s is not None else False
        pool = pools.get(A.periodo(cso["op"]["fecha"]), [])
        det = None if s is None else (ev and 1 + sum(1 for e, x in pool if e and x >= s) <= A.cupo(len(pool), pol))
        res.append({"caso_id": cso["caso_id"], "base": cso["base"]["operacion_id"], "clase": cso["clase"], "transformacion": cso["transformacion"],
                    "intensidad": cso["intensidad"], "puntaje": s, "puntaje_base": base_s, "evidencia": ev, "estado": c["estado"], "detectado": det})
    sem = [r for r in res if r["clase"] == "anomalia_sembrada" and r["detectado"] is not None]
    neg = [r for r in res if r["clase"] == "control_negativo" and r["detectado"] is not None]

    def tasa(rs):
        n = len(rs)
        k = sum(bool(r["detectado"]) for r in rs)
        return {"numerador": k, "denominador": n, "tasa": round(k / n, 6) if n else None}
    por_tipo, neg_por = defaultdict(list), defaultdict(list)
    for r in sem:
        por_tipo[f"{r['transformacion']}|{json.dumps(r['intensidad'])}"].append(r)
    for r in neg:
        neg_por[r["transformacion"]].append(r)
    n_val = sum(1 for o in prep["ops"] if o["tipo_operacion"] == u and E.bloque_de(o["fecha"], config) == bloque)
    alertas = sum(min(A.cupo(len(p), pol), sum(e for e, _ in p)) for p in pools.values())
    trm = [r for r in res if r["transformacion"] == "cambio_trm"]
    return {"metodo": metodo, "deteccion": tasa(sem), "por_tipo_intensidad": {k: tasa(v) for k, v in sorted(por_tipo.items())},
            "controles_negativos": {"alertas": tasa(neg), "por_tipo": {k: tasa(v) for k, v in sorted(neg_por.items())},
                                    "cambio_trm_puntaje_identico": {"identicos": sum(r["puntaje"] == r["puntaje_base"] for r in trm), "total": len(trm)}},
            "originales": {"validas": n_val, "puntuadas": sum(len(p) for p in pools.values()), "con_evidencia": sum(e for p in pools.values() for e, _ in p),
                           "alertas": alertas, "capacidad": sum(A.cupo(len(p), pol) for p in pools.values()),
                           "alertas_por_100_validas": round(100 * alertas / n_val, 4) if n_val else None}, "casos": res}


def bootstrap(cand: list[dict], ref: list[dict], config: Mapping) -> dict:
    """IC por operación base de (candidato − referencia) en detección sembrada y en alertas de controles negativos."""
    b = config["evaluacion"]["bootstrap"]
    rmap = {r["caso_id"]: r for r in ref}
    porb: dict[str, dict] = defaultdict(lambda: {"s": [], "n": []})
    for c in cand:
        r = rmap.get(c["caso_id"])
        if c["detectado"] is None or not r or r["detectado"] is None:
            continue
        porb[c["base"]]["s" if c["clase"] == "anomalia_sembrada" else "n"].append((bool(c["detectado"]), bool(r["detectado"])))
    bases = sorted(porb)

    def dif(bs, k):
        xs = [x for bb in bs for x in porb[bb][k]]
        return (sum(a for a, _ in xs) - sum(r for _, r in xs)) / len(xs) if xs else 0.0
    rng = random.Random(b["semilla"])
    reps = [[rng.choice(bases) for _ in bases] for _ in range(int(b["replicas"]))]
    a = (1 - b["nivel"]) / 2
    out = {"bases": len(bases), "replicas": int(b["replicas"]), "agrupacion": b["agrupacion"]}
    for k, nombre in (("s", "deteccion"), ("n", "controles")):
        rs = sorted(dif(x, k) for x in reps)
        out[nombre] = {"diferencia": round(dif(bases, k), 6), "ic95": [round(rs[int(a * len(rs))], 6), round(rs[min(len(rs) - 1, int((1 - a) * len(rs)))], 6)]}
    return out


def decidir(u, sel, cand, ref, boot, config) -> dict:
    rd = config["regla_decision"]
    meta, margen = float(rd["meta_deteccion"]), float(rd["margen_no_inferioridad_controles"])
    base = {"universo": u, "regla": rd["id"], "estado_maximo": "favorable_demostracion_sombra (sin promoción operativa)", "origen_datos": config["origen_datos"]}
    if cand is None:
        return dict(base, decision="referencia_conservada", sistema_conservado="mediana_mad", motivos=[sel.get("motivo", "candidato en abstención")], cumple={})
    dc, dr = cand["deteccion"]["tasa"], ref["deteccion"]["tasa"]
    trm = cand["controles_negativos"]["cambio_trm_puntaje_identico"]
    cumple = {"meta_deteccion_candidato": dc is not None and dc >= meta, "meta_deteccion_referencia": dr is not None and dr >= meta,
              "supera_referencia_ic": boot["deteccion"]["ic95"][0] > 0, "controles_negativos_no_peores": boot["controles"]["ic95"][1] <= margen,
              "trm_sin_cambio": trm["identicos"] == trm["total"]}
    valores = {"deteccion_candidato": dc, "deteccion_referencia": dr, "diferencia": boot["deteccion"]["diferencia"], "ic95": boot["deteccion"]["ic95"],
               "diferencia_controles": boot["controles"]["diferencia"], "ic95_controles": boot["controles"]["ic95"], "margen_controles": margen,
               "alertas_controles_candidato": cand["controles_negativos"]["alertas"]["tasa"], "alertas_controles_referencia": ref["controles_negativos"]["alertas"]["tasa"]}
    if all(cumple[k] for k in ("meta_deteccion_candidato", "supera_referencia_ic", "controles_negativos_no_peores", "trm_sin_cambio")):
        return dict(base, decision="favorable_demostracion_sombra", sistema_conservado="isolation_forest", cumple=cumple, valores=valores,
                    motivos=["El candidato supera a la referencia a igual cupo con evidencia y es no inferior en controles negativos; solo evidencia sintética"])
    if not cumple["meta_deteccion_candidato"] and not cumple["meta_deteccion_referencia"]:
        return dict(base, decision="inconcluso", sistema_conservado="mediana_mad", cumple=cumple, valores=valores,
                    motivos=[f"Ni candidato ({dc}) ni referencia ({dr}) alcanzan la meta de detección {meta}"])
    mot = [m for k, m in (("supera_referencia_ic", "La mejora de detección no tiene un IC95 por encima de 0"),
                          ("meta_deteccion_candidato", f"Detección del candidato {dc} < meta {meta}"),
                          ("controles_negativos_no_peores", f"El IC95 de alertas en controles negativos supera el margen de {margen}"),
                          ("trm_sin_cambio", "Un cambio exclusivo de TRM modificó el puntaje")) if not cumple[k]]
    return dict(base, decision="referencia_conservada", sistema_conservado="mediana_mad", cumple=cumple, valores=valores, motivos=mot)


# Entrenamiento y comprobación --------------------------------------------------------------------------------------------
def entrenar(datos, config: Mapping, salida, compras=None) -> dict:
    compras = A.cargar_compras(datos) if compras is None else compras
    prep = preparar(datos, compras, config)
    cc = config["candidato"]
    pol = config["politica_alertas"]
    cs_val = casos(prep, config, "validacion")
    universos, equivalencias, validacion, seleccion = {}, {}, {}, {}
    for u in A.UNIVERSOS:
        tr = [o for o in prep["ops"] if o["tipo_operacion"] == u and E.bloque_de(o["fecha"], config) == "entrenamiento"]
        validacion[u] = {"referencia": E._sin_casos(evaluar_metodo(prep, config, cs_val, "validacion", u, "mediana_mad"))}
        X0, _ = E.matriz(tr, prep["contextos"], list(M.VARIABLES))
        if len(X0) < int(cc["min_entrenamiento"]):
            seleccion[u] = {"estado": "candidato_en_abstencion", "elegido": None, "filas_entrenamiento": len(X0),
                            "motivo": f"{len(X0)} filas utilizables (< {cc['min_entrenamiento']}): se conserva la referencia"}
            universos[u] = {"metodo": "mediana_mad", "config_id": None, "soporte_entrenamiento": len(X0)}
            continue
        res, exps = {}, {}
        for conf in cc["configuraciones"]:
            vs = config["variables"]["conjuntos"][conf["variables"]]
            X, _ = E.matriz(tr, prep["contextos"], vs)
            m = E.ajustar(X, conf, cc)
            exp = E.exportar(m, vs, len(vs))
            eq = E.equivalencia(m, exp, E.puntos_equivalencia(X, exp, float(config["contexto"]["z_max"]), cc["semilla"]), cc["equivalencia"]["tolerancia_absoluta"], pol)
            Xv, _ = E.matriz([o for o in prep["ops"] if o["tipo_operacion"] == u and E.bloque_de(o["fecha"], config) == "validacion"], prep["contextos"], vs)
            eqv = E.equivalencia(m, exp, {"validacion": Xv}, cc["equivalencia"]["tolerancia_absoluta"], pol)
            eq["equivalente"] = eq["equivalente"] and eqv["equivalente"]
            eq["conjuntos"].update(eqv["conjuntos"])
            equivalencias[f"{u}:{conf['id']}"] = eq
            if not eq["equivalente"]:
                raise ProtocoloM6Error(f"{u}:{conf['id']}: la inferencia JSON no es equivalente a scikit-learn")
            b = A.Bosque(exp)
            umbral = round(A._percentil([b.rareza(x) for x in X], float(conf["cuantil_evidencia"])), 12)  # solo entrenamiento
            res[conf["id"]] = evaluar_metodo(prep, config, cs_val, "validacion", u, "isolation_forest", b, vs, umbral)
            exps[conf["id"]] = (exp, len(X), umbral)
        orden = {c["id"]: c["orden"] for c in cc["configuraciones"]}
        elegido = sorted(res, key=lambda k: (-(res[k]["deteccion"]["tasa"] or 0), res[k]["controles_negativos"]["alertas"]["tasa"] or 0,
                                             res[k]["originales"]["alertas_por_100_validas"] or 0, orden[k]))[0]
        exp, n, umbral = exps[elegido]
        validacion[u]["candidatos"] = {k: E._sin_casos(v) for k, v in res.items()}
        seleccion[u] = {"estado": "seleccionada", "elegido": elegido, "filas_entrenamiento": n, "criterio": config["seleccion"],
                        "umbral_evidencia_rareza": umbral, "validacion_deteccion": {k: v["deteccion"] for k, v in res.items()}}
        universos[u] = dict(exp, metodo="isolation_forest", config_id=elegido, semilla=cc["semilla"], soporte_entrenamiento=n, umbral_evidencia_rareza=umbral)
    art = {"formato": M.FORMATO, "modelo_id": A.MODELO_ID, "version_protocolo": config["version_protocolo"], "umbral": None,
           "disponible_desde": config["fijado_en"], "origen_datos": config["origen_datos"], "contexto": config["contexto"], "referencia": config["referencia"],
           "politica_alertas": pol, "catalogo": config["catalogo"], "direcciones": config["direcciones"], "evidencia": config["evidencia"],
           "etiquetas_universos": config["universos"], "unidades": config["unidades"], "universos": universos,
           "datos": {"revision": datos.revision, "huella_datos": datos.huella_datos},
           "puntaje": "rareza = 2^(−E[h(x)]/c(max_muestras)); mayor = más raro; no es probabilidad",
           "convenciones_numericas": {"entrada": "float32 antes de recorrer los árboles (como scikit-learn)", "division": "x[var] <= umbral va a la izquierda",
                                      "hoja": "profundidad (raíz = 1) + c(n_hoja) − 1"}}
    art["version"] = "m61-" + sha(canon(art).encode())[:10]
    from .inferencia import huella_artefacto
    art["huella"] = huella_artefacto(art)
    errores = M.validar_artefacto_m61(art)
    if errores:
        raise ProtocoloM6Error("Artefacto inválido: " + "; ".join(errores))
    diag = E.diagnostico(datos, compras, prep, config)
    archivos = {"config.json": json_bytes(config), "datos.json": json_bytes(dict(datos.descripcion(), compras=len(compras))),
                "preparacion.json": json_bytes(diag), "control_a02.json": json_bytes(E.control_a02(datos)),
                "casos_validacion.json": json_bytes([E._caso_pub(c) for c in cs_val]), "validacion.json": json_bytes(validacion),
                "equivalencia.json": json_bytes(equivalencias), "seleccion.json": json_bytes(seleccion), "artefacto.json": json_bytes(art)}
    meta = {"modelo_id": A.MODELO_ID, "version_protocolo": config["version_protocolo"], "artefacto_version": art["version"], "artefacto_huella": art["huella"],
            "huella_seleccion": sha(archivos["seleccion.json"]), "huella_datos": datos.huella_datos, "revision_datos": datos.revision,
            "versiones": E._versiones(), "codigo": dict(E._codigo(), **{n: E.sha_archivo(Path(__file__).parent / n) for n in ("anomalias_m61.py", "anomalias_m61_experimento.py")}),
            "estado": "congelado_antes_de_la_comprobacion"}
    marc = publicar_lote(salida, archivos, "congelacion.json", meta, volatiles={"fecha_congelacion": ahora_utc()})
    return {"seleccion": seleccion, "validacion": validacion, "equivalencia": equivalencias, "artefacto": art, "congelacion": marc, "diagnostico": diag}


def evaluar(ejecucion, datos, compras=None, m6: str | Path | None = None) -> dict:
    d = Path(ejecucion)
    cong = E.verificar_congelacion(d)
    if datos.huella_datos != cong["huella_datos"]:
        raise ProtocoloM6Error("Los datos no son la revisión congelada (huella distinta): no se evalúa")
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    art = json.loads((d / "artefacto.json").read_text(encoding="utf-8"))
    sel = json.loads((d / "seleccion.json").read_text(encoding="utf-8"))
    compras = A.cargar_compras(datos) if compras is None else compras
    prep = preparar(datos, compras, config)
    cs = casos(prep, config, "comprobacion_historica")
    contexto_m6 = None
    if m6:  # SOLO contexto: referencia de M6 congelada (cupo obligatorio, cantidad en ambas direcciones) sobre los casos M6.1
        E.evaluacion_publicada(m6)
        cfg6 = json.loads((Path(m6) / "config.json").read_text(encoding="utf-8"))
        prep6 = E.preparar(datos, compras, cfg6)
        contexto_m6 = {u: E._sin_casos(E.evaluar_metodo(prep6, cfg6, cs, "comprobacion_historica", u, "mediana_mad")) for u in A.UNIVERSOS}
    metricas, decisiones, detalle = {}, {}, {}
    for u in A.UNIVERSOS:
        ref = evaluar_metodo(prep, config, cs, "comprobacion_historica", u, "mediana_mad")
        s = art["universos"][u]
        cand = evaluar_metodo(prep, config, cs, "comprobacion_historica", u, "isolation_forest", A.Bosque(s), s["variables"], s["umbral_evidencia_rareza"]) \
            if s["metodo"] == "isolation_forest" else None
        boot = bootstrap(cand["casos"], ref["casos"], config) if cand else None
        metricas[u] = {"referencia": E._sin_casos(ref), "candidato": E._sin_casos(cand) if cand else None, "bootstrap": boot,
                       "contexto_m6_referencia": contexto_m6[u] if contexto_m6 else None,
                       "revision_humana": {"originales_revisadas": 0, "precision_primeras_n": None, "falsas_alertas_por_100_normales": None,
                                           "motivo": "0 revisiones humanas reales: precisión comercial y falsas alertas no son estimables"}}
        decisiones[u] = decidir(u, sel[u], cand, ref, boot, config)
        detalle[u] = {"referencia": ref["casos"], "candidato": cand["casos"] if cand else None}
    decision = {"decisiones": decisiones, "artefacto_huella": cong["artefacto_huella"], "version_protocolo": config["version_protocolo"],
                "sello_congelacion": cong["sello"], "origen_datos": config["origen_datos"],
                "alcance": "comprobación histórica EXPLORATORIA y NO independiente (datos y comprobación de M6 ya vistos al diagnosticar)"}
    archivos = {"casos_comprobacion.json": json_bytes([E._caso_pub(c) for c in cs]), "comprobacion.json": json_bytes(metricas),
                "detalle_casos.json": json_bytes(detalle), "decision.json": json_bytes(decision)}
    marc = publicar_lote(d, archivos, "evaluacion.json", {"modelo_id": A.MODELO_ID, "sello_congelacion": cong["sello"], "artefacto_huella": cong["artefacto_huella"]},
                         volatiles={"fecha_evaluacion": ahora_utc()})
    return {"metricas": metricas, "decision": decision, "evaluacion": marc}


evaluacion_publicada = E.evaluacion_publicada
verificar_congelacion = E.verificar_congelacion
