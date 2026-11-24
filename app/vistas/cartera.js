// Agenda de seguimiento y ficha de cliente (entradas 2 y 3 del plan de mejora de vistas).
import { ACCIONES, motivos, ordenar, validarAgenda } from "../contrato.js";
import {
  $vista, GLOSARIO, S, URL_FUENTE, api, cop, enServidor, errorHtml, esc, estadoHtml, fechaLarga, incluye, ir, millones,
  nuevoTurno, num, pct, plural, puede, relativoVencimiento, ruta, textoEstimacion, vigente,
} from "../nucleo.js";
import { barras, cronologia, detalleTecnico, fuenteCierre, respuesta, verDatos } from "../ui.js";
import { inactividadFichaHtml } from "./prevencion.js";
import { proximaFichaHtml } from "./proxima.js";
import { activarVentaCruzada, ventaCruzadaFichaHtml } from "./venta_cruzada.js";

export async function cargarLocal() {
  const url = URL_FUENTE[S.fuente];
  const [rEsq, rDat] = await Promise.all([fetch("/contratos/agenda.v1.schema.json", { cache: "no-store" }), fetch(url, { cache: "no-store" })]);
  if (!rDat.ok) {
    const ayuda = S.fuente === "salida"
      ? "Todavía no hay una agenda local en este equipo. La ayuda técnica de «Cambiar origen» explica cómo generarla."
      : "No se encontró el archivo de la demostración.";
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
  return { accion: q.get("accion") || "", segmento: q.get("segmento") || "", q: q.get("q") || "", frio: q.get("frio") || "", pagina: Number(q.get("pagina") || 1) };
}
export function queryDeFiltros(f) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v && !(k === "pagina" && v === 1)) p.set(k, v);
  return p.toString();
}
const hayFiltros = f => !!(f.accion || f.segmento || f.q || f.frio);
function describirFiltros(f) {
  const p = [];
  if (f.accion) p.push(`acción «${f.accion}»`);
  if (f.segmento) p.push(`segmento «${f.segmento}»`);
  if (f.q) p.push(`ID que contiene «${f.q}»`);
  if (f.frio) p.push("solo con 90 días o más sin comprar");
  return p.join(" · ");
}

/** Hecho comprobable que justifica cada motivo de la fila. */
export function porQue(c, umbral) {
  const h = [];
  for (const m of c.motivos || []) {
    if (m === "Revisar reactivación") h.push(`${num(c.dias_sin_compra)} días desde su última compra (90 o más se considera pausa)`);
    else if (m === "Revisar cobertura") {
      if (c.coberturas_vencidas) h.push(`${plural(c.coberturas_vencidas, "cobertura vencida", "coberturas vencidas")} al cierre`);
      if (c.renovaciones_proximas) h.push(`${plural(c.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en los próximos 45 días`);
    } else if (m === "Revisar oportunidad de recompra") h.push(`estimación de compra a 30 días de ${pct(c.prob_compra_30d)}${umbral != null ? `, umbral ${pct(umbral)}` : ""}${c.prediccion?.motivos?.[1] ? ` (señal observada: ${c.prediccion.motivos[1]})` : ""}`);
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
  return `<p class="muted">Señales observadas al corte del ${esc(fechaLarga(p.corte))} (describen el historial, no causas de compra):</p><ul class="muted">${p.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>`;
}

function etiquetas(c) {
  return `${c.frecuente ? `<span class="chip" title="${esc(GLOSARIO.frecuente)}">Frecuente</span>` : ""}${c.frio ? `<span class="chip" title="${esc(GLOSARIO.frio)}">90 días o más sin comprar</span>` : ""}`;
}

function csvLocal(items) {
  const campos = ["cliente_id", "accion", "motivos", "prob_compra_30d", "dias_sin_compra", "ventas_confirmadas", "ingreso_cop", "frecuente", "frio", "renovaciones_proximas", "coberturas_vencidas", "segmento"];
  const celda = v => { const s = Array.isArray(v) ? v.join(" | ") : v == null ? "" : String(v); return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  return "﻿" + [campos.join(","), ...items.map(c => campos.map(k => celda(c[k])).join(","))].join("\n");
}

// ---------------------------------------------------------------- agenda
export async function vistaAgenda() {
  if (!S.fuente || (enServidor() && !S.usuario)) return ir("#/inicio");
  const { q } = ruta();
  const f = filtrosDesdeQuery(q);
  const turno = nuevoTurno();
  $vista.innerHTML = `<h1>Agenda de seguimiento</h1>${estadoHtml("", "Cargando agenda…")}`;
  let datos, todosFiltrados = null;
  try {
    if (enServidor()) {
      const p = new URLSearchParams({ ...f, tam: 25 });
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
      const tam = 25, paginas = Math.max(1, Math.ceil(items.length / tam));
      datos = { resumen: a.resumen, frecuentes: a.clientes.filter(c => c.frecuente).length,
        por_accion: ACCIONES.map(x => ({ accion: x, clientes: a.clientes.filter(c => c.accion === x).length })), modelo: a.modelo, modeloActivo: !!a.modelo,
        items: items.slice((f.pagina - 1) * tam, f.pagina * tam), total: items.length, paginas, pagina: f.pagina,
        segmentos: [...new Set(a.clientes.map(c => c.segmento).filter(Boolean))], ingreso_filtrado: items.reduce((s, c) => s + c.ingreso_cop, 0), corte: a.corte,
        cierre: { id: S.local.url, origen: a.origen } };
    }
  } catch (e) {
    if (!vigente(turno)) return;
    $vista.innerHTML = `<h1>Agenda de seguimiento</h1>${errorHtml(e)}<p><a href="#/inicio">Cambiar origen</a></p>`;
    return;
  }
  if (!vigente(turno)) return;
  const r = datos.resumen;
  const revisar = datos.por_accion.filter(x => x.accion !== "Seguimiento habitual").reduce((s, x) => s + x.clientes, 0);
  const umbral = datos.modelo?.umbral ?? null;
  const conFiltro = (cambio) => `#/agenda?${queryDeFiltros({ ...f, ...cambio, pagina: 1 })}`;
  const barrasAccion = barras(datos.por_accion.map(x => ({
    etiqueta: x.accion, valor: x.clientes, texto: plural(x.clientes, "cliente", "clientes"),
    href: conFiltro({ accion: f.accion === x.accion ? "" : x.accion }), activo: f.accion === x.accion,
  })), { etiquetaAria: "Clientes por acción principal en toda la cartera; pulsa una barra para filtrar la lista" });
  const ordenTexto = datos.modeloActivo
    ? "Orden aplicado: acción principal; dentro de cada acción, mayor estimación de compra primero (sin estimación al final); después, ID."
    : "Orden aplicado: acción principal y después ID. La estimación de compra está desactivada, así que no interviene en el orden.";
  const csvHref = enServidor() && puede("cartera.exportar") ? `/api/cierres/${esc(S.cierre)}/agenda.csv${hayFiltros(f) ? `?${esc(queryDeFiltros({ ...f, pagina: 1 }))}` : ""}` : null;
  const alcanceExport = hayFiltros(f) ? `${plural(datos.total, "fila", "filas")}: los clientes seleccionados con los filtros actuales` : `${plural(r.clientes, "fila", "filas")}: toda la cartera`;
  const exportar = csvHref ? `<a class="boton-sec" href="${csvHref}">Exportar CSV</a> <span class="muted">${esc(alcanceExport)}</span>`
    : !enServidor() ? `<button type="button" class="sec" id="csv-local">Exportar CSV</button> <span class="muted">${esc(alcanceExport)}</span>` : "";

  $vista.innerHTML = `<h1>Agenda de seguimiento</h1>
  ${respuesta(`<strong>${num(revisar)} de ${num(r.clientes)} clientes requieren revisión.</strong>`,
    `${esc(incluye(datos.corte))} · ${esc(enServidor() ? "Cierre publicado" : S.fuente === "ejemplo" ? "Demostración con datos de práctica" : "Agenda local")} · conteos sobre toda la cartera`)}
  ${enServidor() && datos.cierres?.length > 1 ? `<label class="en-linea">Ver otro cierre <select id="cierre">${datos.cierres.map(c => `<option value="${esc(c.id)}" ${(S.cierre === c.id || (S.cierre === "activo" && c.activo)) ? "selected" : ""}>${esc(fechaLarga(c.corte))} · revisión ${c.revision}${c.activo ? " (vigente)" : ""}</option>`).join("")}</select></label>` : ""}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>¿Qué acción necesita cada cliente?</h2>${barrasAccion}
      <p class="muted">Cada cliente cuenta una vez, en su acción principal. ${f.accion ? `<a href="${esc(conFiltro({ accion: "" }))}">Quitar el filtro de acción</a>` : "Pulsa una barra para ver esos clientes."}</p>
      ${verDatos({ tabla: { cabeceras: ["Acción principal", "Clientes"], numericas: new Set([1]), filas: datos.por_accion.map(x => [esc(x.accion), num(x.clientes)]) },
        fuente: fuenteCierre(datos.cierre), actualizado: esc(incluye(datos.corte)),
        regla: datos.modelo ? `Reglas de la agenda y modelo ${esc(datos.modelo.version || "")}. ${esc(GLOSARIO.umbral)} Umbral aplicado: ${esc(pct(umbral) ?? "—")}.` : "Reglas de la agenda (sin modelo de compra)." })}
    </section>
    <section class="panel"><h2>Toda la cartera</h2>
      <dl class="cifras"><div><dt>Clientes</dt><dd>${num(r.clientes)}</dd></div><div><dt>Ventas confirmadas acumuladas</dt><dd>${num(r.ventas_confirmadas)}</dd></div>
      <div><dt>Ingreso confirmado acumulado</dt><dd>${esc(millones(r.ingreso_cop))}</dd></div>
      <div><dt title="${esc(GLOSARIO.frio)}">Con 90 días o más sin comprar</dt><dd>${num(r.clientes_frios)}</dd></div><div><dt title="${esc(GLOSARIO.frecuente)}">Frecuentes</dt><dd>${num(datos.frecuentes)}</dd></div></dl>
      <p class="muted">«Frecuente» y «90 días o más sin comprar» pueden coincidir en un mismo cliente; no se suman.</p></section>
  </div>
  <form class="filtros" id="filtros">
    <label>Acción principal <select name="accion"><option value="">Todas</option>${ACCIONES.map(a => `<option ${f.accion === a ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>
    <label>Segmento <select name="segmento"><option value="">Todos</option>${(datos.segmentos || []).map(s => `<option ${f.segmento === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
    <label>Buscar cliente <input name="q" value="${esc(f.q)}" placeholder="DEMO02" autocomplete="off"></label>
    <label class="en-linea"><input type="checkbox" name="frio" value="1" ${f.frio ? "checked" : ""}> Solo con 90 días o más sin comprar</label>
    <button>Aplicar filtros</button>${hayFiltros(f) ? '<a href="#/agenda">Quitar filtros</a>' : ""}
  </form>
  <p class="seleccion" aria-live="polite"><strong>${plural(datos.total, "cliente seleccionado", "clientes seleccionados")} · ${esc(millones(datos.ingreso_filtrado))} de ingreso acumulado</strong>${hayFiltros(f) ? ` <span class="muted">(${esc(describirFiltros(f))})</span>` : ' <span class="muted">(sin filtros)</span>'}</p>
  <p class="fila">${exportar}</p>
  ${datos.total === 0 ? estadoHtml("", "Ningún cliente coincide con estos filtros.") : `
  <div class="tabla"><table class="apilable"><thead><tr><th>Cliente</th><th>Acción principal</th><th>Por qué</th><th class="n">Estimación de compra a 30 días</th><th>Última compra</th><th class="n">Ingreso acumulado</th><th><span class="oculto-visual">Ficha</span></th></tr></thead><tbody>
  ${datos.items.map(c => `<tr class="fila-enlace"><td><strong>${esc(c.cliente_id)}</strong>${c.segmento ? `<div class="muted">${esc(c.segmento)}</div>` : ""}<div>${etiquetas(c)}</div></td>
    <td data-et="Acción principal">${esc(c.accion)}${c.motivos.filter(m => m !== c.accion && m !== "Seguimiento habitual").map(m => `<div class="muted">También: ${esc(m)}</div>`).join("")}</td>
    <td data-et="Por qué">${esc(porQue(c, umbral))}</td>
    <td class="n" data-et="Estimación de compra a 30 días">${esc(textoEstimacion(c))}</td>
    <td data-et="Última compra">${c.ultima_compra ? `${esc(fechaLarga(c.ultima_compra))}<div class="muted">hace ${num(c.dias_sin_compra)} días al cierre</div>` : "Sin compras registradas"}</td>
    <td class="n" data-et="Ingreso acumulado">${esc(millones(c.ingreso_cop))}</td>
    <td><a href="#/clientes/${encodeURIComponent(c.cliente_id)}?${queryDeFiltros(f)}">Abrir ficha<span class="oculto-visual"> de ${esc(c.cliente_id)}</span></a></td></tr>`).join("")}
  </tbody></table></div>
  <div class="fila" style="margin-top:8px">${datos.pagina > 1 ? `<a href="#/agenda?${queryDeFiltros({ ...f, pagina: datos.pagina - 1 })}">← Anterior</a>` : ""}
    <span class="muted">Página ${datos.pagina} de ${datos.paginas}</span>
    ${datos.pagina < datos.paginas ? `<a href="#/agenda?${queryDeFiltros({ ...f, pagina: datos.pagina + 1 })}">Siguiente →</a>` : ""}</div>`}
  <p class="muted">${esc(ordenTexto)} La estimación de compra es una propensión calculada por un modelo; una alerta no es una venta confirmada.</p>`;
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

// ---------------------------------------------------------------- ficha
function recomendacion(c, f, corte) {
  const ultima = c.ultima_compra ? ` La última compra fue el ${fechaLarga(c.ultima_compra)}.` : "";
  const alCierre = `Al cierre del ${fechaLarga(corte)}`;
  switch (c.accion) {
    case "Revisar cobertura": {
      const prox = f.coberturas.filter(x => x.estado === "proxima").sort((a, b) => a.dias_para_fin - b.dias_para_fin)[0];
      const venc = f.coberturas.filter(x => x.estado === "vencida").sort((a, b) => b.dias_para_fin - a.dias_para_fin)[0];
      if (prox) return `Revisa la cobertura de ${prox.producto || prox.producto_id}. ${alCierre} faltaban ${prox.dias_para_fin} días para su vencimiento (${fechaLarga(prox.fecha_fin)}).${ultima}`;
      if (venc) return `Revisa la cobertura de ${venc.producto || venc.producto_id}. ${alCierre} había vencido hace ${-venc.dias_para_fin} días (${fechaLarga(venc.fecha_fin)}).${ultima}`;
      return `Revisa sus coberturas: ${c.coberturas_vencidas ? `${plural(c.coberturas_vencidas, "vencida", "vencidas")}` : ""}${c.coberturas_vencidas && c.renovaciones_proximas ? " y " : ""}${c.renovaciones_proximas ? `${plural(c.renovaciones_proximas, "vence", "vencen")} en los próximos 45 días` : ""} al cierre.${ultima}`;
    }
    case "Revisar reactivación": return `Revisa la reactivación. ${alCierre} habían pasado ${c.dias_sin_compra} días desde su última compra (90 o más se considera pausa).${ultima}`;
    case "Revisar oportunidad de recompra": return `Revisa una posible recompra. La estimación de compra a 30 días es ${pct(c.prob_compra_30d)}, por encima del nivel a partir del cual se sugiere revisar.${ultima}`;
    case "Revisar primera compra": return "Revisa una primera compra. No tiene compras registradas al cierre.";
    default: return `Seguimiento habitual: no hay alertas al cierre.${ultima}`;
  }
}

export async function vistaFicha(id, q) {
  const volver = `<a href="#/agenda?${q.toString()}">← Volver a la agenda</a>`;
  const turno = nuevoTurno();
  $vista.innerHTML = `${volver}${estadoHtml("", "Cargando ficha…")}`;
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
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${volver}${errorHtml(e)}`; return; }
  if (!vigente(turno)) return;
  const c = f.cliente, corte = f.cierre.corte, modelo = f.modelo;
  const umbral = modelo?.umbral ?? null;
  const estimacion = c.sin_historial ? "Sin compras registradas: no hay base para estimar una recompra."
    : c.prob_compra_30d == null ? "Hay compras, pero falta la estimación (modelo no disponible). Se aplican solo las reglas."
    : `<strong>${esc(pct(c.prob_compra_30d))}</strong> de probabilidad estimada de compra en los 30 días siguientes al cierre${modelo ? ` (modelo ${esc(modelo.version || "")}; se sugiere revisar desde ${esc(pct(umbral))})` : ""}. ${c.prob_compra_30d === 0 ? "El modelo estimó 0 %; no es un dato ausente." : "Es una estimación, no una venta."}`;
  const eventos = [
    ...f.historial.slice(0, 6).map(v => ({ fecha: v.fecha, etiquetaFecha: fechaLarga(v.fecha), tipo: "compra", titulo: `Compra confirmada · ${v.producto || v.producto_id}`, chip: "Hecho", detalle: esc(millones(v.importe_cop)) })),
    ...f.coberturas.map(x => ({ fecha: x.fecha_fin, etiquetaFecha: fechaLarga(x.fecha_fin), tipo: "vencimiento", titulo: `Fin de cobertura · ${x.producto || x.producto_id}`, chip: "Fecha contractual", detalle: esc(`${relativoVencimiento(x.dias_para_fin)} respecto al cierre`) })),
    ...f.oportunidades.filter(o => o.fecha_sugerida).map(o => ({ fecha: o.fecha_sugerida, etiquetaFecha: fechaLarga(o.fecha_sugerida), tipo: "sugerida", titulo: `Revisión sugerida · ${o.accion || o.tipo}`, chip: "Recomendación", detalle: esc(o.motivos.join(" · ")) })),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha));
  const recientes = f.historial.slice(0, 20);
  $vista.innerHTML = `${volver}<h1>${esc(c.cliente_id)}${c.segmento || f.segmento?.segmento ? ` <span class="muted">· ${esc(f.segmento?.segmento || c.segmento)}</span>` : ""}</h1>
  ${respuesta(`<strong>${esc(recomendacion(c, f, corte))}</strong>`, `${esc(incluye(corte))}${c.motivos.length > 1 ? ` · otros motivos: ${esc(c.motivos.filter(m => m !== c.accion).join(", "))}` : ""}`)}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>Estimación de compra <span class="chip">IA</span></h2><p>${estimacion}</p>${senalesHtml(c.prediccion)}
      ${enServidor() && puede("cartera.ver") ? '<p class="muted"><a href="#/ia">Cómo se mide este modelo y cómo se compara con las reglas</a></p>' : ""}
      ${f.tarea ? `<p><strong>Seguimiento:</strong> ${esc(f.tarea.estado)} · ${f.tarea.responsable_id ? `responsable ${esc(f.tarea.responsable_id)}` : "sin responsable"} · <a href="#/tareas/${f.tarea.id}">Abrir tarea</a></p>` : enServidor() ? '<p class="muted">No hay un seguimiento abierto para este cliente.</p>' : ""}
      ${f.oportunidades.length ? `<p><strong>Oportunidades del cierre:</strong></p><ul>${f.oportunidades.map(o => `<li>${esc(o.accion || o.tipo)}${o.fecha_sugerida ? ` · revisión sugerida el ${esc(fechaLarga(o.fecha_sugerida))}` : ""}</li>`).join("")}</ul>` : ""}
      <p>${etiquetas(c) || '<span class="muted">Sin etiquetas de frecuencia o pausa.</span>'}</p>
      ${c.frio ? `<p class="muted">${esc(GLOSARIO.frio)}</p>` : ""}</section>
    <section class="panel"><h2>Cifras al cierre</h2><dl class="cifras">
      <div><dt>Última compra</dt><dd>${c.ultima_compra ? esc(fechaLarga(c.ultima_compra)) : "Sin compras registradas"}</dd></div>
      <div><dt>Días sin comprar al cierre</dt><dd>${c.dias_sin_compra ?? "—"}</dd></div>
      <div><dt>Ventas confirmadas</dt><dd>${num(c.ventas_confirmadas)}</dd></div>
      <div><dt>Ingreso acumulado</dt><dd>${esc(millones(c.ingreso_cop))}</dd></div>
      <div><dt>Coberturas</dt><dd>${num(c.renovaciones_proximas)} vencen en 45 días · ${num(c.coberturas_vencidas)} vencidas</dd></div></dl></section>
  </div>
  ${inactividadFichaHtml(f.inactividad_sombra)}
  ${proximaFichaHtml(f.proxima_sombra)}
  ${ventaCruzadaFichaHtml(f.venta_cruzada_sombra)}
  <section class="panel"><h2>Línea de tiempo</h2>
    <p class="muted">Distingue compras confirmadas (hechos), fechas contractuales de cobertura y revisiones sugeridas. Lo que aparece después de la marca del cierre era futuro en esa fecha.</p>
    ${local ? estadoHtml("", "La agenda local trae solo el resumen de compras (productos y totales). El historial, las coberturas y la fecha sugerida requieren el cierre publicado completo.") : cronologia(eventos, { corte, vacio: "Sin compras, coberturas ni revisiones sugeridas." })}</section>
  <div class="grid2">
   <section class="panel"><h2>Productos adquiridos</h2>${f.productos.length ? `<div class="tabla"><table><tr><th>Producto</th><th class="n">Operaciones</th><th class="n">Importe</th><th>Última</th></tr>${f.productos.map(p => `<tr><td>${esc(p.producto)}</td><td class="n">${p.operaciones ?? "—"}</td><td class="n">${p.importe_cop != null ? cop(p.importe_cop) : "—"}</td><td>${p.ultima ? esc(fechaLarga(p.ultima)) : "—"}</td></tr>`).join("")}</table></div>${local ? '<p class="muted">Solo nombres de producto: el detalle por operación requiere el cierre completo.</p>' : '<p class="muted">Importes en COP.</p>'}` : '<p class="muted">Sin compras registradas.</p>'}</section>
   <section class="panel"><h2>Coberturas instaladas</h2>${f.coberturas.length ? `<div class="tabla"><table><tr><th>Producto</th><th>Fin</th><th>Situación al cierre</th></tr>${f.coberturas.map(x => `<tr><td>${esc(x.producto || x.producto_id)}<div class="muted">${esc(x.instalacion_id)}</div></td><td>${esc(fechaLarga(x.fecha_fin))}</td><td>${esc(relativoVencimiento(x.dias_para_fin))}</td></tr>`).join("")}</table></div><p class="muted">Fecha contractual, no compra confirmada.</p>` : `<p class="muted">${local ? "Detalle no incluido en la agenda local." : "Sin coberturas publicadas."}</p>`}</section>
  </div>
  ${recientes.length ? `<section class="panel"><h2>Operaciones recientes</h2><p class="muted">Se muestran las ${recientes.length} operaciones más recientes de ${num(f.historial_total ?? f.historial.length)} registradas.</p><div class="tabla"><table><tr><th>Fecha</th><th>Producto</th><th class="n">Cantidad</th><th>Moneda de origen</th><th class="n">Importe COP</th><th>Fuente</th></tr>${recientes.map(v => `<tr><td>${esc(fechaLarga(v.fecha))}</td><td>${esc(v.producto || v.producto_id)}</td><td class="n">${v.cantidad}</td><td>${esc(v.moneda)}${v.tasa ? ` · tasa ${num(v.tasa)}` : ""}</td><td class="n">${cop(v.importe_cop)}</td><td>${esc(v.venta_id)}</td></tr>`).join("")}</table></div></section>` : ""}
  ${detalleTecnico(`<pre>${esc(JSON.stringify(c, null, 2))}</pre>`, "Registro original del cliente")}`;
  activarVentaCruzada($vista, () => vistaFicha(id, q));
  $vista.focus();
}
