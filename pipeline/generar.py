"""Generador del cierre (A → B): publicación C2 con la agenda C1.

Encadena A01 (validación del lote), A02 (importes), A03 (ficha), A04/M1 (inferencia
del modelo de compra registrado), A05 (segmentos), A07 (oportunidades y venta cruzada),
A08 (series y pronóstico evaluado) y A09 (escenarios de TRM). La salida cumple los
contratos de ``contratos/`` y se valida con ``python -m contratos.validar --publicacion``.

Todas las etapas leen la revisión aceptada por A01 (``<salida>/a01/publicado``), nunca
los archivos originales. Un lote fallido aborta; uno pendiente de revisión también, salvo
aceptación parcial explícita (``--aceptar-parcial``), que usa solo las filas aceptadas.

El cierre no entrena: carga la versión operativa de ``compra_30d`` del registro
(``--registro``, ``JACOMIND_MODELOS`` o ``var/modelos``). Sin versión válida, o con un corte
anterior a su disponibilidad, la probabilidad es nula, el motivo queda en
``predicciones_clientes`` y la agenda sigue por reglas.

    python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json
    python -m pipeline.generar --datos ... --corte 2026-10-31 --salida salida/cierres/oct --registro var/modelos
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from contratos.agenda import ORDEN_ACCION, motivos

SOPORTE_MINIMO_CRUZADA = 3
TIPO_POR_ACCION = {"Revisar reactivación": "reactivacion", "Revisar cobertura": "renovacion",
                   "Revisar oportunidad de recompra": "recompra", "Revisar primera compra": "primera_compra"}


def disponible() -> bool:
    return all(importlib.util.find_spec(m) is not None for m in
               ("pipeline", "pipeline.operaciones", "pipeline.ficha", "pipeline.segmentacion", "modelos.inferencia"))


def _f(x) -> float:
    return round(float(x), 2)


def _iso(x):
    return x.isoformat() if isinstance(x, (date, datetime)) else x


def _escribir(ruta: Path, datos) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def generar(datos: str | Path, corte: str, salida: str | Path, *, registro: str | Path | None = None,
            aceptar_parcial: bool = False, observado_hasta: str | None = None, sin_cobertura_verificada: bool = False,
            config_a01: str | Path | None = None) -> dict:
    """Genera ``salida/`` con manifiesto.json, agenda.json y tablas C2. Devuelve el manifiesto.

    Cobertura temporal (política compartida con ``modelos.datos``): el lote debe estar completo hasta
    el corte. Si la cobertura declarada no alcanza el corte, se lanza ``CoberturaInsuficiente`` antes de
    calcular nada y no se escribe ninguna tabla de publicación. Si la cobertura es desconocida, también
    se rechaza, salvo ``sin_cobertura_verificada=True``: entonces se publica marcando
    ``cobertura.estado = no_verificada`` y el modelo se abstiene (sin probabilidades).
    """
    from modelos import registro as registro_modelos
    from modelos.datos import (CoberturaInsuficiente, LoteNoAceptado, resolver_cobertura, resolver_lote,
                               verificar_cobertura_corte, verificar_coherencia)
    from modelos.inferencia import predicciones_corte
    from modelos.variables import historial_compras
    from pipeline.carga import cargar_lote
    from pipeline.ficha import construir_ficha
    from pipeline.operaciones import _load, _rates, calcular_cierre
    from pipeline.segmentacion import segmentar_clientes

    raiz = Path(datos)
    dir_datos = raiz / "01_Datos" if (raiz / "01_Datos").is_dir() else raiz
    cut = date.fromisoformat(corte)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    # A01: validación del lote. Las etapas siguientes leen solo la revisión aceptada.
    calidad: dict = {"notas": []}
    lote = cargar_lote(raiz, salida / "a01", Path(config_a01) if config_a01 else None)
    calidad["a01_estado"] = lote.status
    calidad["a01_tablas"] = lote.inventory
    if lote.status == "fallido":
        raise RuntimeError(f"A01 rechazó el lote ({len(lote.issues)} incidencias); ver {salida / 'a01' / 'incidencias.jsonl'}")
    try:
        dir_lote, manifiesto_a01 = resolver_lote(salida / "a01", aceptar_parcial=aceptar_parcial)
    except LoteNoAceptado as e:
        raise RuntimeError(f"{e} Incidencias en {salida / 'a01' / 'incidencias.jsonl'}") from e
    if dir_lote.name == "lote_actual":
        calidad["notas"].append("Aceptación parcial explícita: se publican solo las filas aceptadas por A01; ver a01/incidencias.jsonl.")
    huellas_lote = {p.name: _sha(p) for p in sorted(dir_lote.glob("*.csv"))}
    calidad["datos_aceptados"] = {"revision": manifiesto_a01.get("revision"), "estado": manifiesto_a01.get("status"),
                                  "aceptacion_parcial": dir_lote.name == "lote_actual",
                                  "huella_datos": hashlib.sha256(json.dumps(huellas_lote, sort_keys=True).encode()).hexdigest()}

    clientes = _load(dir_lote, "clientes.csv", "clientes")
    ventas = _load(dir_lote, "ventas.csv", "ventas")
    compras = _load(dir_lote, "compras.csv", "compras")
    productos = {str(p["producto_id"]): p for p in _load(dir_lote, "productos.csv", "productos")}
    instalaciones = _load(dir_lote, "base_instalada.csv", "instalaciones")
    nombres_proveedor = {str(p["proveedor_id"]): p.get("nombre_prueba") for p in _load(dir_lote, "proveedores.csv", "proveedores")}
    tasas = _rates(dir_lote)

    # Cobertura temporal: datos completos hasta el corte antes de calcular variables o publicar.
    cobertura = resolver_cobertura(manifiesto_a01, explicito=observado_hasta)
    verificar_coherencia(ventas, cobertura)
    abstencion_cobertura = None
    try:
        verificar_cobertura_corte(cut, cobertura)
    except CoberturaInsuficiente as e:
        if cobertura.conocida or not sin_cobertura_verificada:
            raise
        abstencion_cobertura = (f"Cobertura temporal no verificada: el modelo se abstiene en este cierre ({cobertura.fuente}). "
                                "Declara datos_observados_hasta para publicar estimaciones.")
        calidad["notas"].append("Publicación sin cobertura verificada (modo explícito): hechos hasta el corte no garantizados como completos.")
    estado_cobertura = {"corte": corte, **cobertura.como_dict(),
                        "estado": "verificada" if abstencion_cobertura is None else "no_verificada",
                        "publicacion": "completa" if abstencion_cobertura is None else "sin_cobertura_verificada"}
    calidad["cobertura"] = estado_cobertura

    # A02: importes por operación con la política de redondeo de A.
    cierre = calcular_cierre(dir_lote, cut)
    venta_por_id = {str(v["venta_id"]): v for v in ventas}
    compra_por_id = {str(c["compra_id"]): c for c in compras}
    historial = []
    for r in cierre.sales.rows:
        if r.get("status") != "Confirmada":
            continue
        v = venta_por_id[str(r["id"])]
        p = productos.get(str(v["producto_id"]), {})
        historial.append({"venta_id": str(r["id"]), "cliente_id": str(v["cliente_id"]), "producto_id": str(v["producto_id"]),
                          "producto": p.get("nombre_prueba"), "familia": r["family"], "fecha": _iso(v["fecha"]),
                          "cantidad": int(v["cantidad"]), "moneda": v["moneda"],
                          "tasa": _f(tasas[v["fecha"]]) if v["moneda"] == "USD" else None,
                          "importe_cop": _f(r["amount_cop"]), "estado": "Confirmada"})
    compras_prov = []
    for r in cierre.purchases.rows:
        if r.get("status") != "Confirmada":
            continue
        c = compra_por_id[str(r["id"])]
        compras_prov.append({"compra_id": str(r["id"]), "fecha": _iso(c["fecha"]), "proveedor_id": str(c["proveedor_id"]),
                             "proveedor": nombres_proveedor.get(str(c["proveedor_id"])),
                             "producto_id": str(c["producto_id"]), "familia": r["family"], "cantidad": int(c["cantidad"]),
                             "moneda": c["moneda"], "costo_unitario": float(c["costo_unitario"]),
                             "tasa": _f(tasas[c["fecha"]]) if c["moneda"] == "USD" else None, "importe_cop": _f(r["amount_cop"])})
    if cierre.sales.missing_rates:
        calidad["notas"].append(f"Ventas aisladas por TRM faltante: {len(cierre.sales.missing_rates)}")
    calidad["anomalias_a02"] = len(cierre.anomalies)

    # A03: ficha 360° (importe por operación ya redondeado, igual que A02).
    ficha = construir_ficha(clientes, [dict(v, importe_cop=Decimal(str(h["importe_cop"])))
                                       for h in historial for v in [venta_por_id[h["venta_id"]]]], instalaciones, cut)

    # A04/M1: inferencia con la versión operativa registrada (sin entrenar en el cierre).
    modelo_info, probs = None, {}
    try:
        artefacto, puntero = registro_modelos.artefacto_registrado(registro, "compra_30d", "operativo")
        motivo_ausencia = None
    except registro_modelos.ModeloNoDisponible as e:
        artefacto, puntero, motivo_ausencia = None, None, str(e)
    if abstencion_cobertura is not None:
        artefacto, puntero, motivo_ausencia = None, None, abstencion_cobertura
    predicciones = predicciones_corte(artefacto, motivo_ausencia, clientes, historial_compras(ventas, productos, tasas), cut)
    if artefacto is not None and cut >= artefacto.disponible_desde:
        probs = {p["cliente_id"]: p["probabilidad"] for p in predicciones if p["estado"] == "estimado"}
        modelo_info = {"version": artefacto.version, "umbral": artefacto.umbral, "registro": puntero,
                       "evaluacion": artefacto.datos.get("evaluacion") or {}}
        calidad["modelo_compra"] = {"estado": "operativo", "version_registro": puntero["version"], "artefacto_huella": artefacto.huella}
    else:
        motivo = next((p["motivos"][0] for p in predicciones if p["estado"] == "modelo_no_disponible"),
                      motivo_ausencia or "Sin modelo operativo")
        calidad["modelo_compra"] = {"estado": "no_disponible", "motivo": motivo}
        calidad["notas"].append(f"Sin modelo validado para este corte: probabilidad nula y agenda por reglas. {motivo}")

    # M2: inactividad_60d SOLO con una versión OPERATIVA registrada y autorizada. Las variantes experimentales se
    # puntúan en una publicación de sombra separada (modelos.cli puntuar --modelo inactividad_60d), nunca aquí.
    from modelos.inactividad import predicciones_inactividad
    modelo_inactividad = None
    try:
        art_i, puntero_i = registro_modelos.artefacto_registrado(registro, "inactividad_60d", "operativo")
    except registro_modelos.ModeloNoDisponible as e:
        art_i, puntero_i = None, None
        calidad["modelo_inactividad"] = {"estado": "sin_version_operativa", "motivo": str(e),
                                         "nota": "No se publican filas inactividad_60d en el cierre; la regla de recencia sigue en la agenda."}
    if art_i is not None and abstencion_cobertura is not None:
        calidad["modelo_inactividad"] = {"estado": "abstencion", "motivo": abstencion_cobertura}
    elif art_i is not None:
        predicciones = predicciones + predicciones_inactividad(art_i, None, clientes, historial_compras(ventas, productos, tasas), cut)
        modelo_inactividad = {"nombre": "inactividad_60d", "version": art_i.version, "estado_registro": "operativo",
                              "version_registro": puntero_i["version"], "artefacto_huella": art_i.huella, "horizonte_dias": 60,
                              "umbral_frio_dias": 90, "limitaciones": "Riesgo de llegar a 90 días sin compra en 60 días; no es abandono "
                              "ni efecto del seguimiento. No cambia la precedencia de la agenda C1."}
        calidad["modelo_inactividad"] = {"estado": "operativo", "version_registro": puntero_i["version"], "artefacto_huella": art_i.huella}

    # M3: proxima_compra SOLO con una versión OPERATIVA registrada (hoy no existe: se puntúa en sombra aparte).
    from modelos.proxima_compra import predicciones_proxima
    modelo_proxima = None
    try:
        art_p, puntero_p = registro_modelos.artefacto_registrado(registro, "proxima_compra", "operativo")
    except registro_modelos.ModeloNoDisponible as e:
        art_p, puntero_p = None, None
        calidad["modelo_proxima_compra"] = {"estado": "sin_version_operativa", "motivo": str(e),
                                            "nota": "No se publican filas proxima_compra en el cierre; la ventana estimada solo existe en sombra."}
    if art_p is not None and abstencion_cobertura is not None:
        calidad["modelo_proxima_compra"] = {"estado": "abstencion", "motivo": abstencion_cobertura}
    elif art_p is not None:
        predicciones = predicciones + predicciones_proxima(art_p, None, clientes, historial_compras(ventas, productos, tasas), cut)
        modelo_proxima = {"nombre": "proxima_compra", "version": art_p.version, "estado_registro": "operativo", "version_registro": puntero_p["version"],
                          "artefacto_huella": art_p.huella, "horizonte_dias": 60, "limitaciones": "Ventana estimada de próxima compra por "
                          "comportamiento; no es una fecha contractual ni cambia la agenda C1."}
        calidad["modelo_proxima_compra"] = {"estado": "operativo", "version_registro": puntero_p["version"], "artefacto_huella": art_p.huella}

    # A05: segmentación RFM.
    segs = segmentar_clientes([{"cliente_id": f["cliente_id"], "recencia_dias": f["recencia_dias"],
                                "frecuencia": f["frecuencia_operaciones"], "importe": f["valor_monetario_cop"]} for f in ficha])

    # C1: agenda.
    umbral = modelo_info["umbral"] if modelo_info else None
    filas = []
    for f in ficha:
        sin = f["ultima_compra"] is None
        prob = None if sin else probs.get(f["cliente_id"])
        c = {"cliente_id": f["cliente_id"], "ultima_compra": _iso(f["ultima_compra"]), "dias_sin_compra": f["dias_sin_compra"],
             "ventas_confirmadas": f["frecuencia_operaciones"], "ingreso_cop": _f(f["valor_monetario_cop"]),
             "productos": sorted({productos[p]["nombre_prueba"] for p in f["productos_historicos"] if p in productos}),
             "frecuente": f["frecuente"], "frio": f["frio"], "renovaciones_proximas": f["coberturas_proximas"],
             "coberturas_vencidas": f["coberturas_vencidas"], "prob_compra_30d": prob,
             "segmento": segs.get(f["cliente_id"], {}).get("segmento")}
        if c["frio"]:
            c["accion"] = "Revisar reactivación"
        elif c["renovaciones_proximas"] or c["coberturas_vencidas"]:
            c["accion"] = "Revisar cobertura"
        elif prob is not None and umbral is not None and prob >= umbral:
            c["accion"] = "Revisar oportunidad de recompra"
        elif sin:
            c["accion"] = "Revisar primera compra"
        else:
            c["accion"] = "Seguimiento habitual"
        c["motivos"] = motivos(c, umbral)
        filas.append(c)
    agenda = {"version": 1, "corte": corte, "origen": "sintetico", "generado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "modelo": {"version": modelo_info["version"], "umbral": umbral} if modelo_info else None,
              "resumen": {"clientes": len(filas), "ventas_confirmadas": sum(c["ventas_confirmadas"] for c in filas),
                          "ingreso_cop": _f(sum(Decimal(str(c["ingreso_cop"])) for c in filas)),
                          "clientes_frios": sum(c["frio"] for c in filas)},
              "clientes": filas}

    # Coberturas, oportunidades y segmentos.
    coberturas = []
    for f in ficha:
        for cb in f["coberturas"]:
            inst = next(i for i in instalaciones if i["instalacion_id"] == cb["instalacion_id"])
            coberturas.append({"instalacion_id": cb["instalacion_id"], "cliente_id": f["cliente_id"], "producto_id": str(cb["producto_id"]),
                               "producto": productos.get(str(cb["producto_id"]), {}).get("nombre_prueba"),
                               "fecha_inicio": _iso(inst["fecha_inicio"]), "fecha_fin": _iso(cb["fecha_fin"]),
                               "estado": "proxima" if cb["proxima"] else cb["estado"], "dias_para_fin": (cb["fecha_fin"] - cut).days,
                               "unidades": int(inst.get("unidades") or 0)})
    oportunidades = []
    for c in filas:
        if c["accion"] == "Seguimiento habitual":
            continue
        tipo = TIPO_POR_ACCION[c["accion"]]
        oportunidades.append({"oportunidad_id": f"{c['cliente_id']}:{tipo}", "episodio_id": f"{c['cliente_id']}:{tipo}",
                              "cliente_id": c["cliente_id"], "producto_id": None, "tipo": tipo, "motivos": c["motivos"],
                              "prioridad": ORDEN_ACCION[c["accion"]], "probabilidad": c["prob_compra_30d"],
                              "evidencia": {k: c[k] for k in ("dias_sin_compra", "renovaciones_proximas", "coberturas_vencidas", "prob_compra_30d")},
                              "fecha_sugerida": (cut + timedelta(days=7)).isoformat(), "version_regla": "agenda-c1-v1"})
    from pipeline.oportunidades import evaluar_venta_cruzada, familias_por_cliente, recomendar_popular, recomendar_venta_cruzada
    fam_prod = {pid: str(p.get("familia_prueba")) for pid, p in productos.items()}
    hist_fam = familias_por_cliente(ventas, fam_prod, cut)
    cruzadas = recomendar_venta_cruzada(hist_fam, soporte_minimo=SOPORTE_MINIMO_CRUZADA)
    for cliente, sugerencias in sorted(cruzadas.items()):
        s = sugerencias[0]
        oportunidades.append({"oportunidad_id": f"{cliente}:cruzada:{s['familia']}", "episodio_id": f"{cliente}:cruzada:{s['familia']}",
                              "cliente_id": cliente, "producto_id": None, "tipo": "venta_cruzada",
                              "motivos": [f"Venta cruzada: {s['familia']}"], "prioridad": 6, "probabilidad": None,
                              "evidencia": {"familia": s["familia"], "soporte": s["soporte"], "justificacion": s["justificacion"]},
                              "fecha_sugerida": (cut + timedelta(days=14)).isoformat(), "version_regla": f"coocurrencia-soporte{SOPORTE_MINIMO_CRUZADA}"})
    # Comparación temporal con la línea base de popularidad (corte 60 días antes, compras posteriores observadas).
    corte_eval = cut - timedelta(days=60)
    antes = familias_por_cliente(ventas, fam_prod, corte_eval)
    despues = familias_por_cliente(ventas, fam_prod, cut)
    calidad["venta_cruzada"] = {
        "corte_evaluacion": corte_eval.isoformat(), "soporte_minimo": SOPORTE_MINIMO_CRUZADA,
        "coocurrencia": evaluar_venta_cruzada(antes, despues, recomendar_venta_cruzada(antes, soporte_minimo=SOPORTE_MINIMO_CRUZADA)),
        "popularidad": evaluar_venta_cruzada(antes, despues, recomendar_popular(antes)),
        "clientes_con_sugerencia": len(cruzadas)}
    segmentos = [{"cliente_id": k, "segmento": v["segmento"], "version": v["version"]} for k, v in sorted(segs.items())]

    # Series mensuales (A02 agregados) y proyección (A08, media móvil).
    tablas_series = _series(historial, compras_prov, cut)

    # Escenarios de TRM (A09) sobre el último mes con compras en USD.
    escenarios = _escenarios(compras_prov)

    tablas = {"agenda": agenda, "historial_ventas": historial, "coberturas": coberturas, "compras_proveedor": compras_prov,
              "series_mensuales": tablas_series, "escenarios_trm": escenarios, "oportunidades": oportunidades, "segmentos": segmentos,
              "predicciones_clientes": predicciones}
    declaradas = {}
    for nombre, contenido in tablas.items():
        declaradas[nombre] = {"archivo": f"{nombre}.json", "filas": len(contenido["clientes"]) if nombre == "agenda" else len(contenido)}
    declaradas["historial_ventas"]["sumas"] = {"importe_cop": _f(sum(Decimal(str(h["importe_cop"])) for h in historial))}
    huellas = {p.name: _sha(p) for p in sorted(dir_datos.glob("*.csv")) if "OPCIONAL" not in p.name}
    manifiesto = {"version": 1, "tipo": "publicacion_analitica", "cierre_id": f"a-{corte}-{hashlib.sha256(json.dumps(huellas, sort_keys=True).encode()).hexdigest()[:10]}",
                  "corte": corte, "origen": "sintetico", "generado_en": agenda["generado_en"], "huellas_entrada": huellas,
                  "versiones": {"reglas": "agenda-c1-v1", "modelo_compra": modelo_info["version"] if modelo_info else None,
                                "segmentacion": "rfm-v1", "pronostico": "media_movil_3"},
                  "tablas": declaradas, "calidad": calidad, "cobertura": estado_cobertura,
                  "modelos": [{"nombre": "compra_30d", "version": modelo_info["version"], "umbral": umbral,
                               "estado_registro": "operativo", "version_registro": modelo_info["registro"]["version"],
                               "artefacto_huella": modelo_info["registro"]["huella"],
                               "metricas_prueba": modelo_info["evaluacion"].get("prueba_modelo"),
                               "referencia": ({"nombre": "compra en últimos 30 días", **modelo_info["evaluacion"]["prueba_linea_base"]}
                                              if modelo_info["evaluacion"].get("prueba_linea_base") else None),
                               "limitaciones": "Datos sintéticos. Mide propensión de compra, no efecto causal del contacto."}] if modelo_info else []}
    if modelo_inactividad:
        manifiesto["modelos"].append(modelo_inactividad)
    if modelo_proxima:
        manifiesto["modelos"].append(modelo_proxima)
    _publicar_archivos(salida, {**{f"{n}.json": c for n, c in tablas.items()}, "manifiesto.json": manifiesto})
    return manifiesto


MARCA_PUBLICACION = ".publicacion_en_curso.json"


def recuperar_publicacion(salida: str | Path) -> dict | None:
    """Restituye la publicación anterior si una activación quedó interrumpida.

    Lee el diario ``.publicacion_en_curso.json``: cada archivo listado vuelve a su copia del
    respaldo (o se elimina si antes no existía). Devuelve el diario recuperado o ``None``.
    """
    import shutil
    salida = Path(salida)
    marca = salida / MARCA_PUBLICACION
    if not marca.exists():
        return None
    diario = json.loads(marca.read_text(encoding="utf-8"))
    respaldo = salida / diario["respaldo"]
    for nombre in diario["archivos"]:
        origen, destino = respaldo / nombre, salida / nombre
        if origen.exists():
            os.replace(origen, destino)
        elif nombre in diario.get("nuevos", []) and destino.exists():
            destino.unlink()
    marca.unlink()
    shutil.rmtree(respaldo, ignore_errors=True)
    for resto in salida.glob(".publicando-*"):
        shutil.rmtree(resto, ignore_errors=True)
    return diario


def _publicar_archivos(salida: Path, archivos: dict) -> None:
    """Activa una publicación completa con recuperación verificable (no es una operación atómica).

    1. Recupera cualquier activación interrumpida anterior.
    2. Serializa todos los archivos en ``.publicando-*``; si falla, ``salida`` no se toca.
    3. Añade al manifiesto la huella SHA-256 de cada tabla.
    4. Copia la versión visible a ``.respaldo-*`` y escribe el diario ``.publicacion_en_curso.json``.
    5. Sustituye las tablas y, al final, el manifiesto. Ante cualquier fallo se restituye la versión
       anterior desde el respaldo. Si el proceso muere a mitad, el diario permanece: el validador C2
       rechaza el directorio y la siguiente ejecución lo recupera antes de publicar.
    """
    import shutil
    import tempfile
    salida = Path(salida)
    recuperar_publicacion(salida)
    tmp = Path(tempfile.mkdtemp(prefix=".publicando-", dir=salida))
    respaldo = None
    try:
        tablas = [n for n in archivos if n != "manifiesto.json"]
        for nombre in tablas:
            _escribir(tmp / nombre, archivos[nombre])
        manifiesto = archivos["manifiesto.json"]
        por_archivo = {d["archivo"]: d for d in manifiesto["tablas"].values()}
        for nombre in tablas:
            if nombre in por_archivo:
                por_archivo[nombre]["sha256"] = _sha(tmp / nombre)
        _escribir(tmp / "manifiesto.json", manifiesto)
        respaldo = Path(tempfile.mkdtemp(prefix=".respaldo-", dir=salida))
        orden = tablas + ["manifiesto.json"]
        nuevos = [n for n in orden if not (salida / n).exists()]
        for nombre in orden:
            if (salida / nombre).exists():
                shutil.copy2(salida / nombre, respaldo / nombre)
        diario = {"respaldo": respaldo.name, "archivos": orden, "nuevos": nuevos,
                  "iniciado_en": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        _escribir(tmp / MARCA_PUBLICACION, diario)
        os.replace(tmp / MARCA_PUBLICACION, salida / MARCA_PUBLICACION)
        try:
            for nombre in orden:  # el manifiesto se activa el último
                os.replace(tmp / nombre, salida / nombre)
        except BaseException:
            recuperar_publicacion(salida)
            raise
        (salida / MARCA_PUBLICACION).unlink()
        shutil.rmtree(respaldo, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if respaldo is not None and respaldo.exists() and not (salida / MARCA_PUBLICACION).exists():
            shutil.rmtree(respaldo, ignore_errors=True)


def _series(historial: list[dict], compras: list[dict], cut: date) -> list[dict]:
    from pipeline.pronostico import evaluar_origen_creciente, pronosticar_media_movil
    agg: dict = defaultdict(lambda: [Decimal("0"), 0, 0])
    for serie, filas in (("ventas", historial), ("compras", compras)):
        for f in filas:
            for fam in (f["familia"], "Total"):
                a = agg[(f["fecha"][:7], fam, serie)]
                a[0] += Decimal(str(f["importe_cop"])); a[1] += f["cantidad"]; a[2] += 1
    meses = sorted({k[0] for k in agg})
    if not meses:
        return []
    y, m = map(int, meses[0].split("-"))
    calendario = []
    while (y, m) <= (cut.year, cut.month):
        calendario.append(f"{y}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    salida = []
    for serie in ("ventas", "compras"):
        familias = sorted({k[1] for k in agg if k[2] == serie})
        for fam in familias:
            valores = []
            for per in calendario:
                v = agg.get((per, fam, serie))
                valores.append(v[0] if v else Decimal("0"))
                salida.append({"periodo": per, "familia": fam, "serie": serie, "tipo": "historico",
                               "valor_cop": _f(v[0]) if v else 0.0, "unidades": v[1] if v else 0,
                               "operaciones": v[2] if v else 0, "completo": True})
            errores = evaluar_origen_creciente(valores, 3, 3, min_entrenamiento=6)
            y2, m2 = cut.year, cut.month
            for h, valor in enumerate(pronosticar_media_movil(valores, 3, 3), start=1):
                y2, m2 = (y2 + 1, 1) if m2 == 12 else (y2, m2 + 1)
                e = errores.get(h, {})
                mae = e.get("mae_media_movil")
                salida.append({"periodo": f"{y2}-{m2:02d}", "familia": fam, "serie": serie, "tipo": "pronostico",
                               "valor_cop": _f(valor), "metodo": "media_movil_3 (A08)", "horizonte": h,
                               "mae": _f(mae) if mae is not None else None,
                               "mae_ingenuo": _f(e["mae_ingenuo"]) if e.get("mae_ingenuo") is not None else None,
                               "sesgo": _f(e["sesgo_media_movil"]) if e.get("sesgo_media_movil") is not None else None,
                               "n_evaluaciones": e.get("n", 0),
                               "banda_inferior": _f(max(Decimal("0"), valor - mae)) if mae is not None else None,
                               "banda_superior": _f(valor + mae) if mae is not None else None,
                               "calculado_en": cut.isoformat()})
    return salida


def _escenarios(compras: list[dict]) -> list[dict]:
    from pipeline.cambiario import simular_exposicion
    usd = [c for c in compras if c["moneda"] == "USD" and c.get("tasa")]
    if not usd:
        return []
    periodo = max(c["fecha"][:7] for c in usd)
    grupos: dict = defaultdict(list)
    for c in usd:
        if c["fecha"].startswith(periodo):
            grupos[(c["familia"], c["proveedor_id"])].append({"usd": str(c["cantidad"] * c["costo_unitario"]), "trm": str(c["tasa"])})
    salida = []
    for pct in (-8, 0, 8):
        for (fam, prv), filas in sorted(grupos.items()):
            r = simular_exposicion(filas, Decimal(pct) / 100)
            salida.append({"escenario_id": f"trm{pct:+d}", "periodo": periodo, "moneda": "USD", "variacion_pct": pct, "familia": fam,
                           "proveedor_id": prv, "costo_base_cop": _f(r["base_cop"]), "costo_escenario_cop": _f(r["escenario_cop"]),
                           "diferencia_cop": _f(r["diferencia_cop"])})
    return salida


def main(argv=None) -> int:
    import argparse
    import sys
    p = argparse.ArgumentParser(prog="python -m pipeline.generar", description="Genera la publicación C2 (con agenda C1) de un cierre")
    p.add_argument("--datos", help="carpeta del paquete o de 01_Datos")
    p.add_argument("--corte", help="AAAA-MM-DD")
    p.add_argument("--salida", required=True, help="ruta de agenda.json o directorio de publicación")
    p.add_argument("--registro", default=None, help="registro de modelos (por defecto JACOMIND_MODELOS o var/modelos)")
    p.add_argument("--aceptar-parcial", action="store_true", help="publicar un lote pendiente de revisión con sus filas aceptadas")
    p.add_argument("--observado-hasta", default=None, help="cobertura completa declarada para este lote (AAAA-MM-DD)")
    p.add_argument("--sin-cobertura-verificada", action="store_true",
                   help="publicar aunque la cobertura sea desconocida; el modelo se abstiene y la publicación queda marcada")
    p.add_argument("--config-a01", default=None, help="configuración de la carga A01 (mapeo y datos_observados_hasta del lote)")
    p.add_argument("--recuperar", action="store_true", help="solo restituir una publicación interrumpida en --salida")
    a = p.parse_args(argv)
    destino = Path(a.salida)
    directorio = destino.parent if destino.suffix == ".json" else destino
    if a.recuperar:
        diario = recuperar_publicacion(directorio)
        print(json.dumps({"recuperada": diario is not None, "diario": diario}, ensure_ascii=False))
        return 0
    if not a.datos or not a.corte:
        p.error("--datos y --corte son obligatorios salvo con --recuperar")
    try:
        m = generar(a.datos, a.corte, directorio, registro=a.registro, aceptar_parcial=a.aceptar_parcial,
                    observado_hasta=a.observado_hasta, sin_cobertura_verificada=a.sin_cobertura_verificada,
                    config_a01=a.config_a01)
    except Exception as e:  # código ≠ 0 para el cierre programado
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps({"cierre_id": m["cierre_id"], "directorio": str(directorio),
                      "tablas": {k: v["filas"] for k, v in m["tablas"].items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
