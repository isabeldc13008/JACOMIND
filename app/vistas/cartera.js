// V03 Cartera de clientes (lista con filtros persistentes) y V04 Cliente 360 (ficha por pestañas).
import { ACCIONES, motivos, ordenar, validarAgenda } from "../contrato.js";
import {
  $vista, GLOSARIO, S, URL_FUENTE, api, cop, enServidor, errorHtml, esc, estadoHtml, fechaLarga, ir, millones,
  nombreSegmento, nuevoTurno, num, pct, plural, puede, relativoVencimiento, ruta, textoEstimacion, vigente,
} from "../nucleo.js";
import {
  barras, cronologia, ctxDatos, ctxOrigen, detalleTecnico, encabezado, filtrosActivos, fuenteCierre, hallazgo, indicadores,
  paginacion, pestanas, vacio, verDatos,
} from "../ui.js";
import { inactividadFichaHtml } from "./prevencion.js";
import { proximaFichaHtml } from "./proxima.js";
import { activarVentaCruzada, pintarVentaCruzadaIA, ventaCruzadaFichaHtml } from "./venta_cruzada.js";
import { estadoIA, pedirNarrativa, pieIA } from "../ia_textos.js";

export async function cargarLocal() {
  const url = URL_FUENTE[S.fuente];
  const [rEsq, rDat] = await Promise.all([fetch("/contratos/agenda.v1.schema.json", { cache: "no-store" }), fetch(url, { cache: "no-store" })]);
  if (!rDat.ok) {
    const ayuda = S.fuente === "salida"
      ? "Todavía no hay una agenda guardada en este equipo. La ayuda de la pantalla de entrada explica cómo generarla."
      : "No se encontró el archivo del ejemplo de práctica.";
    throw Object.assign(new Error(ayuda), { datos: {} });
  }
  if (!rEsq.ok) throw new Error("No se pudo leer el esquema de la agenda (sirve la raíz del clon).");
  let datos;
  try { datos = await rDat.json(); } catch { throw new Error(`${url} no contiene JSON válido`); }
  const res = validarAgenda(datos, await rEsq.json());
  if (res.errores.length) {
    throw Object.assign(new Error(res.incompatible ? "Versión de agenda incompatible: se conserva la vista anterior." : "La agenda no cumple el contrato C1."),
      { datos: { detalle: { errores: res.errores } } });
  }
  S.local = { datos, url, cargado: new Date().toLocaleTimeString("es-CO") };
}

function filtrosDesdeQuery(q) {
  return { accion: q.get("accion") || "", segmento: q.get("segmento") || "", q: q.get("q") || "", frio: q.get("frio") || "", pagina: Math.max(1, Number(q.get("pagina") || 1)) };
}
export function queryDeFiltros(f) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v && !(k === "pagina" && v === 1)) p.set(k, v);
  return p.toString();
}
const hayFiltros = f => !!(f.accion || f.segmento || f.q || f.frio);

/** Hecho comprobable que justifica cada motivo de la fila. */
export function porQue(c, umbral) {
  const h = [];
  for (const m of c.motivos || []) {
    if (m === "Revisar reactivación") h.push(`${num(c.dias_sin_compra)} días desde su última compra (90 o más se considera pausa)`);
    else if (m === "Revisar cobertura") {
      if (c.coberturas_vencidas) h.push(`${plural(c.coberturas_vencidas, "cobertura vencida", "coberturas vencidas")} a la fecha de los datos`);
      if (c.renovaciones_proximas) h.push(`${plural(c.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en los próximos 45 días`);
    } else if (m === "Revisar oportunidad de recompra") h.push(`posibilidad estimada de compra en 30 días: ${pct(c.prob_compra_30d)}${umbral != null ? ` (se revisa desde ${pct(umbral)})` : ""}${c.prediccion?.motivos?.[1] ? `; señal observada: ${c.prediccion.motivos[1]}` : ""}`);
    else if (m === "Revisar primera compra") h.push("sin compras registradas");
  }
  if (!h.length) return c.dias_sin_compra != null ? `Sin alertas; última compra hace ${num(c.dias_sin_compra)} días` : "Sin alertas";
  const t = h.join(" · ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** Señales observadas que acompañan la predicción persistida (C2 predicciones_clientes); no son causas. */
function senalesHtml(p) {
  if (!p || !p.motivos?.length) return "";
  if (p.estado !== "estimado") return `<p class="muted">${esc(p.motivos[0])}</p>`;
  return `<p class="muted">Señales observadas en el historial hasta el ${esc(fechaLarga(p.corte))}. Describen el historial; no son causas de compra:</p><ul>${p.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>`;
}

function etiquetas(c) {
  return `${c.frecuente ? `<span class="chip">Compra con frecuencia</span>` : ""}${c.frio ? `<span class="chip">90 días o más sin comprar</span>` : ""}`;
}

function csvLocal(items) {
  const campos = ["cliente_id", "accion", "motivos", "prob_compra_30d", "dias_sin_compra", "ventas_confirmadas", "ingreso_cop", "frecuente", "frio", "renovaciones_proximas", "coberturas_vencidas", "segmento"];
  const celda = v => { const s = Array.isArray(v) ? v.join(" | ") : v == null ? "" : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return "﻿" + [campos.join(","), ...items.map(c => campos.map(k => celda(c[k])).join(","))].join("\n");
}

// ---------------------------------------------------------------- V03 · cartera
export async function vistaAgenda() {
  if (!S.fuente || (enServidor() && !S.usuario)) return ir("#/inicio");
  const { q } = ruta();
  const f = filtrosDesdeQuery(q);
  const turno = nuevoTurno();
  const titulo = "Cartera de clientes";
  if (!$vista.querySelector("#filtros")) $vista.innerHTML = `${encabezado({ titulo })}${estadoHtml("", "Cargando la cartera…")}`;
  else $vista.querySelector("#resultado-cartera")?.setAttribute("aria-busy", "true");
  let datos, todosFiltrados = null;
  const tam = 25;
  try {
    if (enServidor()) {
      const p = new URLSearchParams({ ...f, tam });
      const [res, ag, cierres] = await Promise.all([api("GET", `/api/cierres/${S.cierre}/resumen`), api("GET", `/api/cierres/${S.cierre}/agenda?${p}`), api("GET", "/api/cierres")]);
      datos = { resumen: res.resumen, frecuentes: res.frecuentes, por_accion: res.por_accion, modelo: res.modelo, modeloActivo: res.modelo_activo, items: ag.items, total: ag.total,
        paginas: ag.paginas, pagina: ag.pagina, segmentos: ag.segmentos_disponibles, ingreso_filtrado: ag.ingreso_cop_filtrado, corte: ag.corte, cierre: res.cierre, cierres };
    } else {
      if (!S.local) await cargarLocal();
      const a = S.local.datos, umbral = a.modelo?.umbral ?? null;
      let items = ordenar(a.clientes).map(c => ({ ...c, motivos: motivos(c, umbral), sin_historial: c.ultima_compra === null }));
      if (f.accion) items = items.filter(c => c.accion === f.accion);
      if (f.segmento) items = items.filter(c => c.segmento === f.segmento);
      if (f.q) items = items.filter(c => c.cliente_id.toUpperCase().includes(f.q.toUpperCase()));
      if (f.frio) items = items.filter(c => c.frio);
      todosFiltrados = items;
      const paginas = Math.max(1, Math.ceil(items.length / tam));
      datos = { resumen: a.resumen, frecuentes: a.clientes.filter(c => c.frecuente).length,
        por_accion: ACCIONES.map(x => ({ accion: x, clientes: a.clientes.filter(c => c.accion === x).length })), modelo: a.modelo, modeloActivo: !!a.modelo,
        items: items.slice((f.pagina - 1) * tam, f.pagina * tam), total: items.length, paginas, pagina: f.pagina,
        segmentos: [...new Set(a.clientes.map(c => c.segmento).filter(Boolean))], ingreso_filtrado: items.reduce((s, c) => s + c.ingreso_cop, 0), corte: a.corte,
        cierre: { id: S.local.url, origen: a.origen } };
    }
  } catch (e) {
    if (!vigente(turno)) return;
    $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(e, { reintentar: true })}<p><a href="#/inicio">Cambiar la forma de entrar</a></p>`;
    return;
  }
  if (!vigente(turno)) return;
  const r = datos.resumen;
  const revisar = datos.por_accion.filter(x => x.accion !== "Seguimiento habitual").reduce((s, x) => s + x.clientes, 0);
  const umbral = datos.modelo?.umbral ?? null;
  const conFiltro = cambio => `#/agenda?${queryDeFiltros({ ...f, ...cambio, pagina: 1 })}`;
  const barrasAccion = barras(datos.por_accion.map(x => ({
    etiqueta: x.accion, valor: x.clientes, texto: plural(x.clientes, "cliente", "clientes"),
    href: conFiltro({ accion: f.accion === x.accion ? "" : x.accion }), activo: f.accion === x.accion,
  })), { etiquetaAria: "Clientes por acción principal en toda la cartera; pulsa una barra para filtrar la lista" });
  const ordenTexto = datos.modeloActivo
    ? "Orden: primero la acción más urgente; dentro de cada acción, mayor posibilidad estimada de compra (sin estimación al final); después, identificador."
    : "Orden: acción principal y después identificador. La estimación de compra está desactivada, así que no interviene en el orden.";
  const csvHref = enServidor() && puede("cartera.exportar") ? `/api/cierres/${esc(S.cierre)}/agenda.csv${hayFiltros(f) ? `?${esc(queryDeFiltros({ ...f, pagina: 1 }))}` : ""}` : null;
  const alcanceExport = hayFiltros(f) ? `${plural(datos.total, "fila", "filas")}: solo los clientes de la selección actual` : `${plural(r.clientes, "fila", "filas")}: toda la cartera`;
  const exportar = csvHref ? `<a class="boton-sec" href="${csvHref}">Descargar la lista (CSV)</a> <span class="muted">${esc(alcanceExport)}</span>`
    : !enServidor() ? `<button type="button" class="sec" id="csv-local">Descargar la lista (CSV)</button> <span class="muted">${esc(alcanceExport)}</span>` : "";
  const activos = [
    f.accion && { texto: `Acción: ${f.accion}`, quitar: conFiltro({ accion: "" }) },
    f.segmento && { texto: `Segmento: ${nombreSegmento(f.segmento)}`, quitar: conFiltro({ segmento: "" }) },
    f.q && { texto: `Búsqueda: «${f.q}»`, quitar: conFiltro({ q: "" }) },
    f.frio && { texto: "Solo 90 días o más sin comprar", quitar: conFiltro({ frio: "" }) },
  ].filter(Boolean);
  const ejemplo = datos.items[0]?.cliente_id || "";
  const origenTxt = enServidor() ? null : { etiqueta: "Origen", valor: S.fuente === "ejemplo" ? "Ejemplo de práctica de 8 clientes" : "Agenda guardada en este equipo" };

  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Busca un cliente, filtra por lo que necesita y abre su ficha para ver el motivo y el siguiente paso.",
    contexto: [ctxDatos(datos.corte), enServidor() ? ctxOrigen(datos.cierre?.origen) : origenTxt] })}
  ${enServidor() && puede("tablero.ventas") ? pestanas([["resumen", "Resumen", "#/tableros/ventas"], ["cartera", "Cartera completa", "#/agenda"]], "cartera", "Vista comercial") : ""}
  ${enServidor() && datos.cierres?.length > 1 ? `<label class="en-linea">Mes de los datos <select id="cierre">${datos.cierres.map(c => `<option value="${esc(c.id)}" ${(S.cierre === c.id || (S.cierre === "activo" && c.activo)) ? "selected" : ""}>${esc(fechaLarga(c.corte))} · revisión ${c.revision}${c.activo ? " (el vigente)" : ""}</option>`).join("")}</select></label>` : ""}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>¿Qué acción necesita cada cliente?</h2>
      <p><strong>${plural(revisar, "cliente necesita", "clientes necesitan")} revisión</strong> de ${plural(r.clientes, "cliente", "clientes")} en total. Cada cliente cuenta una vez, en su acción principal.</p>
      ${barrasAccion}
      ${verDatos({ tabla: { cabeceras: ["Acción principal", "Clientes"], numericas: new Set([1]), filas: datos.por_accion.map(x => [esc(x.accion), num(x.clientes)]) },
        fuente: fuenteCierre(datos.cierre), actualizado: esc(`Datos hasta el ${fechaLarga(datos.corte)}`),
        regla: datos.modelo ? `Reglas de la agenda y modelo ${esc(datos.modelo.version || "")}. ${esc(GLOSARIO.umbral)} Nivel aplicado: ${esc(pct(umbral) ?? "—")}.` : "Reglas de la agenda (sin modelo de compra)." })}
    </section>
    <section class="panel"><h2>Toda la cartera</h2>
      <dl class="cifras"><div><dt>Clientes</dt><dd>${num(r.clientes)}</dd></div>
      <div><dt>Llevan 90 días o más sin comprar</dt><dd>${num(r.clientes_frios)}</dd></div><div><dt>Compran con frecuencia</dt><dd>${num(datos.frecuentes)}</dd></div>
      <div><dt>Ventas confirmadas (toda la historia)</dt><dd>${num(r.ventas_confirmadas)}</dd></div>
      <div><dt>Ingreso confirmado (toda la historia)</dt><dd>${esc(millones(r.ingreso_cop))}</dd></div></dl>
      <p class="muted">«Compra con frecuencia» y «90 días o más sin comprar» pueden coincidir en un cliente; no se suman. ${esc(GLOSARIO.frio)}</p></section>
  </div>
  <section class="panel" aria-labelledby="t-buscar"><h2 id="t-buscar">Buscar y filtrar</h2>
  <form class="filtros" id="filtros" role="search">
    <label>Buscar cliente por identificador <input name="q" value="${esc(f.q)}" ${ejemplo ? `placeholder="por ejemplo ${esc(ejemplo)}"` : ""} autocomplete="off"></label>
    <label>Acción principal <select name="accion"><option value="">Todas</option>${ACCIONES.map(a => `<option ${f.accion === a ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>
    <label>Segmento <select name="segmento"><option value="">Todos</option>${(datos.segmentos || []).map(s => `<option value="${esc(s)}" ${f.segmento === s ? "selected" : ""}>${esc(nombreSegmento(s))}</option>`).join("")}</select></label>
    <label class="en-linea"><input type="checkbox" name="frio" value="1" ${f.frio ? "checked" : ""}> Solo los que llevan 90 días o más sin comprar</label>
    <div class="fila"><button>Buscar clientes</button>${f.q ? `<a class="boton-sec" href="${esc(conFiltro({ q: "" }))}">Limpiar búsqueda</a>` : ""}</div>
  </form>
  ${filtrosActivos(activos, "#/agenda")}</section>
  <section id="resultado-cartera" aria-labelledby="t-lista">
  <h2 id="t-lista">${hayFiltros(f) ? `${plural(datos.total, "cliente coincide", "clientes coinciden")} con los filtros` : `Todos los clientes (${num(datos.total)})`}</h2>
  <p class="seleccion" aria-live="polite">${esc(millones(datos.ingreso_filtrado))} de ingreso acumulado en esta selección. ${exportar}</p>
  ${datos.total === 0 ? vacio("Ningún cliente coincide con estos filtros.", "Prueba con otra búsqueda o quita algún filtro.", '<a class="boton-sec" href="#/agenda">Quitar filtros</a>') : `
  <div class="tabla"><table class="apilable"><caption>${esc(ordenTexto)}</caption><thead><tr><th scope="col">Cliente</th><th scope="col">Qué hacer y por qué</th><th scope="col" class="n">Posibilidad estimada de compra en 30 días</th><th scope="col">Última compra</th><th scope="col" class="n">Ingreso acumulado</th><th scope="col"><span class="oculto-visual">Ficha</span></th></tr></thead><tbody>
  ${datos.items.map(c => `<tr><td data-et="Cliente"><strong>${esc(c.cliente_id)}</strong>${c.segmento ? `<span class="muted">${esc(nombreSegmento(c.segmento))}</span>` : ""}<div>${etiquetas(c)}</div></td>
    <td data-et="Qué hacer y por qué"><strong>${esc(c.accion)}</strong><span class="muted">${esc(porQue(c, umbral))}</span>${c.motivos.filter(m => m !== c.accion && m !== "Seguimiento habitual").map(m => `<span class="muted">También: ${esc(m)}</span>`).join("")}</td>
    <td class="n" data-et="Posibilidad estimada de compra en 30 días">${esc(textoEstimacion(c))}</td>
    <td data-et="Última compra">${c.ultima_compra ? `${esc(fechaLarga(c.ultima_compra))}<span class="muted">hace ${num(c.dias_sin_compra)} días a la fecha de los datos</span>` : "Sin compras registradas"}</td>
    <td class="n" data-et="Ingreso acumulado">${esc(millones(c.ingreso_cop))}</td>
    <td><a class="boton-sec" href="#/clientes/${encodeURIComponent(c.cliente_id)}?${queryDeFiltros(f)}">Ver cliente<span class="oculto-visual"> ${esc(c.cliente_id)}</span></a></td></tr>`).join("")}
  </tbody></table></div>
  ${paginacion({ pagina: datos.pagina, tam, total: datos.total, href: p => `#/agenda?${queryDeFiltros({ ...f, pagina: p })}` })}`}
  <p class="muted">La posibilidad de compra es una estimación de un modelo, no una venta. «Sin compras registradas», «falta la estimación» y «0 %» significan cosas distintas.</p></section>`;
  document.getElementById("filtros").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    ir(`#/agenda?${queryDeFiltros({ accion: fd.get("accion"), segmento: fd.get("segmento"), q: fd.get("q").trim(), frio: fd.get("frio") || "", pagina: 1 })}`);
  });
  document.getElementById("cierre")?.addEventListener("change", e => { S.cierre = e.target.value; ir(location.hash); });
  document.getElementById("csv-local")?.addEventListener("click", () => {
    const url = URL.createObjectURL(new Blob([csvLocal(todosFiltrados)], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `agenda-${datos.corte}${hayFiltros(f) ? "-filtrada" : ""}.csv` });
    a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

// ---------------------------------------------------------------- V04 · Cliente 360
function recomendacion(c, f, corte) {
  const ultima = c.ultima_compra ? ` La última compra fue el ${fechaLarga(c.ultima_compra)}.` : "";
  const alCierre = `Al ${fechaLarga(corte)}`;
  switch (c.accion) {
    case "Revisar cobertura": {
      const prox = f.coberturas.filter(x => x.estado === "proxima").sort((a, b) => a.dias_para_fin - b.dias_para_fin)[0];
      const venc = f.coberturas.filter(x => x.estado === "vencida").sort((a, b) => b.dias_para_fin - a.dias_para_fin)[0];
      if (prox) return `Revisa la cobertura de ${prox.producto || prox.producto_id}. ${alCierre} faltaban ${prox.dias_para_fin} días para su vencimiento (${fechaLarga(prox.fecha_fin)}).${ultima}`;
      if (venc) return `Revisa la cobertura de ${venc.producto || venc.producto_id}. ${alCierre} había vencido hace ${-venc.dias_para_fin} días (${fechaLarga(venc.fecha_fin)}).${ultima}`;
      return `Revisa sus coberturas: ${c.coberturas_vencidas ? `${plural(c.coberturas_vencidas, "vencida", "vencidas")}` : ""}${c.coberturas_vencidas && c.renovaciones_proximas ? " y " : ""}${c.renovaciones_proximas ? `${plural(c.renovaciones_proximas, "vence", "vencen")} en los próximos 45 días` : ""}.${ultima}`;
    }
    case "Revisar reactivación": return `Revisa la reactivación. ${alCierre} habían pasado ${c.dias_sin_compra} días desde su última compra (90 o más se considera pausa).${ultima}`;
    case "Revisar oportunidad de recompra": return `Revisa una posible recompra. La posibilidad estimada de compra en 30 días es ${pct(c.prob_compra_30d)}, por encima del nivel a partir del cual se sugiere revisar.${ultima}`;
    case "Revisar primera compra": return "Revisa una primera compra. No tiene compras registradas.";
    default: return `Seguimiento habitual: no hay alertas.${ultima}`;
  }
}

const PESTANAS_FICHA = [["resumen", "Resumen"], ["compras", "Compras y coberturas"], ["senales", "Estimaciones de los modelos"], ["seguimientos", "Seguimiento"]];

export async function vistaFicha(id, q) {
  const filtros = new URLSearchParams(q); filtros.delete("pestana");
  const pestana = PESTANAS_FICHA.some(([k]) => k === q.get("pestana")) ? q.get("pestana") : "resumen";
  const volver = { href: `#/agenda${filtros.toString() ? `?${filtros}` : ""}`, texto: filtros.toString() ? "Volver a la cartera filtrada" : "Volver a la cartera" };
  const turno = nuevoTurno();
  if (!$vista.querySelector(`[data-ficha="${CSS.escape(id || "")}"]`)) $vista.innerHTML = `${encabezado({ titulo: id || "Cliente", volver })}${estadoHtml("", "Cargando la ficha del cliente…")}`;
  let f, local = false;
  try {
    if (enServidor()) f = await api("GET", `/api/cierres/${S.cierre}/clientes/${encodeURIComponent(id)}`);
    else {
      if (!S.local) await cargarLocal();
      local = true;
      const c = S.local.datos.clientes.find(x => x.cliente_id === id);
      if (!c) throw Object.assign(new Error(`El cliente ${id} no está en esta agenda; no se inventa historial.`), { status: 404 });
      f = { cierre: { corte: S.local.datos.corte }, cliente: { ...c, motivos: motivos(c, S.local.datos.modelo?.umbral ?? null), sin_historial: c.ultima_compra === null },
        productos: c.productos.map(p => ({ producto: p })), historial: [], historial_total: 0, coberturas: [], oportunidades: [], modelo: S.local.datos.modelo };
    }
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: id || "Cliente", volver })}${errorHtml(e, { reintentar: e.status !== 404 })}`; return; }
  if (!vigente(turno)) return;
  const c = f.cliente, corte = f.cierre.corte, modelo = f.modelo;
  const segmento = f.segmento?.segmento || c.segmento;
  const enlacePestana = k => { const p = new URLSearchParams(filtros); if (k !== "resumen") p.set("pestana", k); return `#/clientes/${encodeURIComponent(id)}${p.toString() ? `?${p}` : ""}`; };
  const proxCob = f.coberturas.filter(x => x.estado === "proxima").sort((a, b) => a.dias_para_fin - b.dias_para_fin)[0] || f.coberturas.filter(x => x.estado === "vencida").sort((a, b) => b.dias_para_fin - a.dias_para_fin)[0];
  const accionPrincipal = f.tarea ? `<a class="boton" href="#/tareas/${f.tarea.id}">Abrir el seguimiento</a>`
    : enServidor() && puede("tareas.ver") ? `<a class="boton-sec" href="#/tareas">Ver seguimientos</a>` : "";
  const cuerpo = pestana === "compras" ? pestanaCompras(f, local) : pestana === "senales" ? pestanaSenales(f, c, modelo) : pestana === "seguimientos" ? pestanaSeguimientos(f) : pestanaResumen(f, c, corte, local);
  $vista.innerHTML = `<div data-ficha="${esc(id)}">${encabezado({ titulo: `Cliente ${c.cliente_id}`, volver,
    descripcion: [segmento && `${esc(nombreSegmento(segmento))}`, etiquetas(c)].filter(Boolean).join(" · "),
    contexto: [ctxDatos(corte), enServidor() ? ctxOrigen() : null] })}
  ${hallazgo({
    que: `<strong>${esc(c.accion)}.</strong> ${esc(recomendacion(c, f, corte))}`,
    porque: c.accion === "Seguimiento habitual" ? "No hay alertas: basta el seguimiento normal." : `El motivo sale de sus compras y coberturas registradas, no de una suposición.${c.motivos.length > 1 ? ` También aparece por: ${esc(c.motivos.filter(m => m !== c.accion).join(", ").toLowerCase())}.` : ""}`,
    accion: accionPrincipal || '<span class="muted">Los seguimientos se crean con el cierre mensual; aún no hay uno para este cliente.</span>',
  })}
  ${indicadores([
    { etiqueta: "Última compra", valor: c.ultima_compra ? esc(fechaLarga(c.ultima_compra)) : "Sin compras", detalle: c.dias_sin_compra != null ? `hace ${num(c.dias_sin_compra)} días a la fecha de los datos` : "no hay compras registradas" },
    { etiqueta: "Cobertura más relevante", valor: proxCob ? esc(fechaLarga(proxCob.fecha_fin)) : "Ninguna", detalle: proxCob ? `${esc(proxCob.producto || proxCob.producto_id)} · ${esc(relativoVencimiento(proxCob.dias_para_fin).replace("del cierre", "de los datos"))}` : local ? "no incluida en la agenda local" : "sin coberturas por vencer ni vencidas" },
    enServidor() && { etiqueta: "Seguimiento", valor: f.tarea ? esc({ abierta: "Abierto", asignada: "Asignado", pospuesta: "Pospuesto", atendida: "Atendido", descartada: "Descartado" }[f.tarea.estado] || f.tarea.estado) : "Sin seguimiento", detalle: f.tarea ? (f.tarea.responsable_id ? `responsable ${esc(f.tarea.responsable_id)} · estado actual` : "sin responsable · estado actual") : "no hay un seguimiento abierto" },
  ])}
  ${pestanas(PESTANAS_FICHA.map(([k, t]) => [k, t, enlacePestana(k)]), pestana, `Información del cliente ${c.cliente_id}`)}
  <div id="contenido-ficha">${cuerpo}</div>
  ${detalleTecnico(`<pre>${esc(JSON.stringify(c, null, 2))}</pre>`, "Registro original del cliente")}</div>`;
  activarVentaCruzada($vista, () => vistaFicha(id, q));
  pintarFichaIA(id, turno);
  if (f.venta_cruzada_sombra?.items?.length) pintarVentaCruzadaIA($vista, id, turno);
}

/** «Para preparar la conversación», redactado por IA con los datos de la ficha. */
function pintarFichaIA(id, turno) {
  const caja = document.getElementById("ia-ficha");
  if (!caja) return;
  const cuerpo = caja.querySelector(".ia-cuerpo");
  pedirNarrativa(`/api/narrativas/ficha/${encodeURIComponent(id)}`, turno, r => {
    if (r.estado === "no_aplica" || r.estado === "desactivada") { caja.hidden = true; return; }   // sin IA: la ficha queda como antes
    if (r.estado !== "ok") { cuerpo.innerHTML = estadoIA(r); return; }
    const t = r.texto;
    cuerpo.innerHTML = `<p>${esc(t.situacion)}</p><p><strong>Qué atender primero:</strong> ${esc(t.primero)}</p>
      ${t.preguntas?.length ? `<p><strong>Preguntas para la llamada</strong></p><ul>${t.preguntas.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}${pieIA(r)}`;
  });
}

function pestanaResumen(f, c, corte, local) {
  const vp = f.proxima_sombra;
  const eventos = [
    ...f.historial.slice(0, 6).map(v => ({ fecha: v.fecha, etiquetaFecha: fechaLarga(v.fecha), tipo: "compra", titulo: `Compra registrada · ${v.producto || v.producto_id}`, chip: "Hecho", detalle: esc(millones(v.importe_cop)) })),
    ...f.coberturas.map(x => ({ fecha: x.fecha_fin, etiquetaFecha: fechaLarga(x.fecha_fin), tipo: "vencimiento", titulo: `Fin de cobertura · ${x.producto || x.producto_id}`, chip: "Fecha de contrato", detalle: esc(`${relativoVencimiento(x.dias_para_fin).replace("del cierre", "de los datos")}`) })),
    ...f.oportunidades.filter(o => o.fecha_sugerida).map(o => ({ fecha: o.fecha_sugerida, etiquetaFecha: fechaLarga(o.fecha_sugerida), tipo: "sugerida", titulo: `Revisión sugerida · ${o.accion || o.tipo}`, chip: "Sugerencia", detalle: esc(o.motivos.join(" · ")) })),
    ...(vp && vp.fecha_p10 ? [{ fecha: vp.fecha_p10, etiquetaFecha: `${fechaLarga(vp.fecha_p10)}${vp.fecha_p50 ? ` a ${fechaLarga(vp.fecha_p50)}` : ""}`, tipo: "sugerida", titulo: "Ventana estimada de próxima compra", chip: "Estimación", detalle: esc(vp.fecha_p50 ? "Entre el 10 % y el 50 % de posibilidad estimada; no es una fecha de compra." : "La mitad de posibilidad no se alcanza dentro del horizonte; no hay fecha de fin.") }] : []),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha));
  const ia = !local && enServidor() ? `<section class="panel ia-panel" id="ia-ficha" aria-live="polite"><h2>Para preparar la conversación</h2><div class="ia-cuerpo"></div></section>` : "";
  return `${ia}<section class="panel"><h2>Compras, vencimientos y estimaciones en el tiempo</h2>
    <p class="muted">Cada tipo tiene su marca: círculo azul = compra registrada (hecho); rombo = fin de cobertura (fecha de contrato); círculo punteado = sugerencia o ventana estimada. Se muestran las 6 compras más recientes de ${num(f.historial_total ?? f.historial.length)}.</p>
    ${local ? vacio("La agenda local trae solo el resumen de compras.", "El historial, las coberturas y las fechas sugeridas requieren entrar con el perfil a la información publicada.") : cronologia(eventos, { corte, vacio: "Sin compras, coberturas ni revisiones sugeridas." })}</section>
  <section class="panel"><h2>Cifras del cliente</h2><dl class="cifras">
    <div><dt>Ventas confirmadas</dt><dd>${num(c.ventas_confirmadas)}</dd></div>
    <div><dt>Ingreso acumulado (toda la historia)</dt><dd>${esc(millones(c.ingreso_cop))}</dd></div>
    <div><dt>Coberturas</dt><dd>${num(c.renovaciones_proximas)} vencen en 45 días · ${num(c.coberturas_vencidas)} vencidas</dd></div>
    <div><dt>Posibilidad estimada de compra en 30 días</dt><dd>${esc(textoEstimacion(c))}</dd></div></dl>
    ${c.frio ? `<p class="muted">${esc(GLOSARIO.frio)}</p>` : ""}</section>`;
}

function pestanaCompras(f, local) {
  const recientes = f.historial.slice(0, 30);
  return `<div class="grid2">
   <section class="panel"><h2>Productos comprados</h2>${f.productos.length ? `<div class="tabla"><table><thead><tr><th scope="col">Producto</th><th scope="col" class="n">Compras</th><th scope="col" class="n">Importe</th><th scope="col">Última</th></tr></thead><tbody>${f.productos.map(p => `<tr><td>${esc(p.producto)}</td><td class="n">${p.operaciones ?? "—"}</td><td class="n">${p.importe_cop != null ? cop(p.importe_cop) : "—"}</td><td>${p.ultima ? esc(fechaLarga(p.ultima)) : "—"}</td></tr>`).join("")}</tbody></table></div>${local ? '<p class="muted">Solo nombres de producto: el detalle por compra requiere la información publicada.</p>' : '<p class="muted">Importes en pesos colombianos (COP).</p>'}` : vacio("Sin compras registradas.")}</section>
   <section class="panel"><h2>Coberturas instaladas</h2>${f.coberturas.length ? `<div class="tabla"><table><thead><tr><th scope="col">Producto</th><th scope="col">Fin (contrato)</th><th scope="col">Situación</th></tr></thead><tbody>${f.coberturas.map(x => `<tr><td>${esc(x.producto || x.producto_id)}<span class="muted">${esc(x.instalacion_id)}</span></td><td>${esc(fechaLarga(x.fecha_fin))}</td><td>${esc(relativoVencimiento(x.dias_para_fin).replace("del cierre", "de los datos"))}</td></tr>`).join("")}</tbody></table></div><p class="muted">Fecha de contrato, no una compra.</p>` : vacio(local ? "Detalle no incluido en la agenda local." : "Sin coberturas publicadas.")}</section>
  </div>
  ${recientes.length ? `<section class="panel"><h2>Compras recientes</h2><p class="muted">Se muestran las ${num(recientes.length)} compras más recientes de ${num(f.historial_total ?? f.historial.length)} registradas.</p><div class="tabla"><table><thead><tr><th scope="col">Fecha</th><th scope="col">Producto</th><th scope="col" class="n">Cantidad</th><th scope="col">Moneda de origen</th><th scope="col" class="n">Importe COP</th><th scope="col">Referencia</th></tr></thead><tbody>${recientes.map(v => `<tr><td>${esc(fechaLarga(v.fecha))}</td><td>${esc(v.producto || v.producto_id)}</td><td class="n">${num(v.cantidad)}</td><td>${esc(v.moneda)}${v.tasa ? ` · tasa ${num(v.tasa)}` : ""}</td><td class="n">${cop(v.importe_cop)}</td><td>${esc(v.venta_id)}</td></tr>`).join("")}</tbody></table></div></section>` : ""}`;
}

function pestanaSenales(f, c, modelo) {
  const umbral = modelo?.umbral ?? null;
  const estimacion = c.sin_historial ? "Sin compras registradas: no hay base para estimar una recompra."
    : c.prob_compra_30d == null ? "Hay compras, pero falta la estimación (modelo no disponible para esta fecha). Se aplican solo las reglas."
    : `<strong>${esc(pct(c.prob_compra_30d))}</strong> de posibilidad estimada de compra en los 30 días siguientes al ${esc(fechaLarga(f.cierre.corte))}${modelo ? `. Se sugiere revisar desde ${esc(pct(umbral))}` : ""}. ${c.prob_compra_30d === 0 ? "El modelo estimó 0 %; no es un dato ausente." : "Es una estimación, no una venta."}`;
  return `<p class="muted">Cada modelo responde una pregunta distinta y tiene su propia fecha. No se combinan en una sola puntuación.</p>
  <section class="panel"><h2>¿Es probable que compre en 30 días?</h2><p>${estimacion}</p>${senalesHtml(c.prediccion)}
    ${modelo ? `<p class="muted">Modelo ${esc(modelo.version || "")} · publicado con el cierre.</p>` : ""}
    ${enServidor() && puede("cartera.ver") ? '<p><a href="#/ia">Cómo se mide este modelo</a></p>' : ""}</section>
  ${inactividadFichaHtml(f.inactividad_sombra) || (enServidor() && puede("prevencion.ver") ? `<section class="panel"><h2>¿Podría dejar de comprar?</h2>${vacio("Sin estimación de riesgo para este cliente.", "No hay una publicación que lo incluya.")}</section>` : "")}
  ${proximaFichaHtml(f.proxima_sombra) || (enServidor() && puede("proxima.ver") ? `<section class="panel"><h2>¿Cuándo conviene contactar?</h2>${vacio("Sin ventana estimada para este cliente.")}</section>` : "")}
  ${ventaCruzadaFichaHtml(f.venta_cruzada_sombra) || (enServidor() && puede("venta_cruzada.ver") ? `<section class="panel"><h2>Productos que podrías ofrecer</h2>${vacio("Sin sugerencias para este cliente.")}</section>` : "")}`;
}

function pestanaSeguimientos(f) {
  return `<section class="panel"><h2>Seguimiento del cliente</h2>
    ${f.tarea ? `<dl class="cifras"><div><dt>Estado actual</dt><dd>${esc(f.tarea.estado)}</dd></div><div><dt>Responsable</dt><dd>${esc(f.tarea.responsable_id || "Sin responsable")}</dd></div><div><dt>Motivo</dt><dd>${esc((f.tarea.motivos || []).join(" · ") || "—")}</dd></div></dl>
      <a class="boton" href="#/tareas/${f.tarea.id}">Abrir el seguimiento</a>`
      : enServidor() ? vacio("No hay un seguimiento abierto para este cliente.", "Los seguimientos los crea el cierre mensual a partir de las alertas. Las sugerencias de los modelos no crean seguimientos.", puede("tareas.ver") ? '<a class="boton-sec" href="#/tareas">Ver todos los seguimientos</a>' : "") : vacio("Los seguimientos requieren entrar con tu perfil.")}</section>
  <section class="panel"><h2>Oportunidades del cierre</h2>${f.oportunidades.length ? `<ul>${f.oportunidades.map(o => `<li><strong>${esc(o.accion || o.tipo)}</strong>${o.fecha_sugerida ? ` · revisar desde el ${esc(fechaLarga(o.fecha_sugerida))}` : ""}${o.motivos?.length ? `<span class="muted">${esc(o.motivos.join(" · "))}</span>` : ""}</li>`).join("")}</ul>` : '<p class="muted">Sin oportunidades publicadas para este cliente.</p>'}</section>`;
}
