// V05 Seguimientos (lista de trabajo) y V06 Detalle de seguimiento (acción, resultado confirmado y cronología real).
import {
  $vista, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, nuevoTurno, num, pct, plural, puede, ruta, S, vigente,
} from "../nucleo.js";
import { barras, cronologia, detalleTecnico, encabezado, filtrosActivos, hallazgo, vacio } from "../ui.js";

export const TIPOS = { reactivacion: "Reactivación", renovacion: "Cobertura", recompra: "Posible recompra", primera_compra: "Primera compra" };
const ESTADOS = { abierta: "Abierta, sin responsable", asignada: "Asignada", pospuesta: "Pospuesta", atendida: "Atendida", descartada: "Descartada" };
const EVENTOS = {
  expuesta: "Propuesto por el cierre", compra_posterior_observada: "Compra posterior observada (no atribuida)", asignada: "Tarea tomada",
  pospuesta: "Revisión pospuesta", contacto_registrado: "Contacto registrado", atendida: "Cerrada con resultado",
  descartada: "Descartada", resultado_atribuido: "Resultado atribuido al seguimiento", actualizada: "Actualizada con un cierre nuevo",
};
const responsable = id => id ? (id === S.usuario?.id ? `${id} (tú)` : id) : "Sin responsable";
let ultimaLista = "#/tareas";   // para «Volver a la lista» con los mismos filtros

/** Evidencia del cierre en palabras, en lugar del objeto JSON. */
export function evidenciaEnPalabras(ev = {}) {
  const p = [];
  if (ev.ultima_compra) p.push(`última compra el ${fechaLarga(ev.ultima_compra)}`);
  if (ev.dias_sin_compra != null) p.push(`${ev.dias_sin_compra} días sin comprar`);
  if (ev.renovaciones_proximas) p.push(`${plural(ev.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en 45 días`);
  if (ev.coberturas_vencidas) p.push(plural(ev.coberturas_vencidas, "cobertura vencida", "coberturas vencidas"));
  if (ev.prob_compra_30d != null) p.push(`posibilidad estimada de compra en 30 días ${pct(ev.prob_compra_30d)}`);
  return p.join(" · ") || "Sin evidencia cuantitativa";
}

// ---------------------------------------------------------------- V05 · lista
export async function vistaTareas(id) {
  if (id) return vistaTarea(Number(id));
  const { q } = ruta();
  const k = q.get("k") || "25", mias = q.get("mias") === "1", estado = q.get("estado") || "", tipo = q.get("tipo") || "";
  ultimaLista = location.hash;
  const turno = nuevoTurno();
  const titulo = "Seguimientos";
  if (!$vista.querySelector("#f-tareas")) $vista.innerHTML = `${encabezado({ titulo })}${estadoHtml("", "Cargando los seguimientos…")}`;
  const p = new URLSearchParams({ k }); if (mias) p.set("mias", "1"); if (estado) p.set("estado", estado);
  const [lista, avisos, met] = await Promise.all([api("GET", `/api/tareas?${p}`), api("GET", "/api/avisos").catch(() => []),
    api("GET", `/api/tareas/metricas${mias ? "?mias=1" : ""}`).catch(() => null)]).catch(e => [e]);
  if (!vigente(turno)) return;
  if (lista instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(lista, { reintentar: true })}`; return; }
  const filas = tipo ? lista.filter(t => t.tipo === tipo) : lista;
  const pendientes = met?.pendientes_seleccion ?? lista.length;
  const sinResp = filas.filter(t => !t.responsable_id && !["atendida", "descartada"].includes(t.estado)).length;
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/tareas${n.toString() ? `?${n}` : ""}`; };
  const activos = [mias && { texto: "Solo los míos", quitar: enlace({ mias: "" }) }, estado && { texto: `Estado: ${ESTADOS[estado] || estado}`, quitar: enlace({ estado: "" }) },
    tipo && { texto: `Tipo: ${TIPOS[tipo] || tipo}`, quitar: enlace({ tipo: "" }) }].filter(Boolean);
  const porEstado = Object.entries(filas.reduce((a, t) => ({ ...a, [t.estado]: (a[t.estado] || 0) + 1 }), {}));
  const tipos = met ? Object.entries(met.por_tipo) : [];
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "El trabajo registrado con cada cliente: qué hay pendiente, quién lo atiende y qué se hizo.",
    contexto: [{ etiqueta: "Estado", valor: "actual, no el del cierre" }, puede("tareas.gestionar") ? null : { etiqueta: "Tu perfil", valor: "puede consultar, no modificar" }] })}
  ${hallazgo({
    que: filas.length ? `<strong>${plural(filas.length, "seguimiento", "seguimientos")}</strong> en esta lista${estado ? "" : `, de ${plural(pendientes, "pendiente", "pendientes")}${mias ? " asignados a ti" : " del equipo"}`}.` : "No hay seguimientos con estos filtros.",
    porque: sinResp ? `${plural(sinResp, "seguimiento no tiene", "seguimientos no tienen")} responsable todavía.` : filas.length ? "Todos los seguimientos pendientes de la lista tienen responsable." : "",
    accion: filas[0] ? `<a class="boton" href="#/tareas/${filas[0].id}">Abrir el primero de la lista</a>` : "",
  })}
  <section class="panel"><h2>Filtrar la lista</h2>
  <form class="filtros" id="f-tareas">
    <label>Mostrar <select name="mias"><option value="">Todos los del equipo</option><option value="1" ${mias ? "selected" : ""}>Solo los asignados a mí</option></select></label>
    <label>Estado <select name="estado"><option value="">Pendientes</option>${Object.entries(ESTADOS).map(([a, b]) => `<option value="${a}" ${estado === a ? "selected" : ""}>${esc(b)}</option>`).join("")}</select></label>
    <label>Tipo <select name="tipo"><option value="">Todos</option>${Object.entries(TIPOS).map(([a, b]) => `<option value="${a}" ${tipo === a ? "selected" : ""}>${esc(b)}</option>`).join("")}</select></label>
    <label>Cuántos mostrar <input name="k" type="number" min="1" max="200" value="${esc(k)}" inputmode="numeric"></label>
    <button>Ver seguimientos</button></form>
  ${filtrosActivos(activos, "#/tareas")}</section>
  ${filas.length ? `<div class="tabla"><table class="apilable"><caption>Orden: prioridad de la acción, posibilidad estimada de compra y cliente. Se muestran hasta ${num(Number(k))}.</caption>
    <thead><tr><th scope="col">Cliente</th><th scope="col">Motivo</th><th scope="col">Estado</th><th scope="col">Responsable</th><th scope="col">Próxima revisión</th><th scope="col"><span class="oculto-visual">Abrir</span></th></tr></thead><tbody>
  ${filas.map(t => `<tr><td data-et="Cliente"><strong>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(t.cliente_id)}">${esc(t.cliente_id)}</a>` : esc(t.cliente_id)}</strong></td>
    <td data-et="Motivo"><strong>${esc(TIPOS[t.tipo] || t.tipo)}</strong><span class="muted">${esc(evidenciaEnPalabras(t.evidencia))}</span></td>
    <td data-et="Estado">${esc(ESTADOS[t.estado] || t.estado)}</td><td data-et="Responsable">${esc(responsable(t.responsable_id))}</td>
    <td data-et="Próxima revisión">${t.fecha_revision ? esc(fechaLarga(t.fecha_revision)) : "Sin fecha registrada"}</td>
    <td><a class="boton-sec" href="#/tareas/${t.id}">Abrir seguimiento<span class="oculto-visual"> de ${esc(t.cliente_id)}</span></a></td></tr>`).join("")}
  </tbody></table></div>` : vacio("No hay seguimientos con estos filtros.", "Quita algún filtro para ver más.", '<a class="boton-sec" href="#/tareas">Quitar filtros</a>')}
  <div class="grid2">
   <section class="panel"><h2>¿En qué estado están?</h2>
    ${porEstado.length ? barras(porEstado.map(([e, n]) => ({ etiqueta: ESTADOS[e] || e, valor: n, texto: plural(n, "seguimiento", "seguimientos"), href: enlace({ estado: estado === e ? "" : e }), activo: estado === e })), { etiquetaAria: "Seguimientos de esta lista por estado; pulsa uno para filtrar" }) : '<p class="muted">Sin datos para esta lista.</p>'}
    <p class="muted">Población: los ${plural(filas.length, "seguimiento", "seguimientos")} de esta lista. No es un embudo de ventas: atender un seguimiento no demuestra una venta.</p>
    ${tipos.length ? `<details class="ver-datos"><summary>Ver cómo terminaron, por tipo (todo el equipo)</summary>
      ${barras(tipos.map(([t, v]) => ({ etiqueta: `${TIPOS[t] || t} · atendidos`, valor: v.fraccion_atendida, texto: `${num(v.atendidas ?? Math.round(v.fraccion_atendida * v.total))} de ${num(v.total)} (${pct(v.fraccion_atendida)})` })), { titulo: "Atendidos" })}
      ${barras(tipos.map(([t, v]) => ({ etiqueta: `${TIPOS[t] || t} · descartados`, valor: v.tasa_descarte, texto: `${num(v.descartadas ?? Math.round(v.tasa_descarte * v.total))} de ${num(v.total)} (${pct(v.tasa_descarte)})` })), { titulo: "Descartados" })}
      <p class="muted">${esc(met.nota)} Avisos duplicados: ${num(met.avisos_duplicados)} · episodios con varias tareas: ${num(met.episodios_con_varias_tareas)}.</p></details>` : ""}</section>
   <section class="panel"><h2>Avisos recientes</h2>${avisos.length ? `<ul class="lista-simple">${avisos.slice(0, 12).map(a => `<li><span class="crono-fecha">${esc(fechaHora(a.creado_en))}</span><br>${esc(a.mensaje)}</li>`).join("")}</ul>` : '<p class="muted">Sin avisos.</p>'}</section></div>`;
  document.getElementById("f-tareas").addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target), n = new URLSearchParams();
    for (const [a, b] of fd) if (b && !(a === "k" && b === "25")) n.set(a, b);
    ir(`#/tareas${n.toString() ? `?${n}` : ""}`);
  });
}

// ---------------------------------------------------------------- V06 · detalle
const INTENCIONES = [
  { a: "asignar", t: "Tomar el seguimiento", d: "Pasas a ser responsable. No cambia el resultado." },
  { a: "contacto", t: "Registrar un contacto", d: "Anota la llamada o reunión y el siguiente paso. Sigue abierto." },
  { a: "atender", t: "Cerrar con resultado", d: "Escribe el resultado y lo das por atendido." },
  { a: "posponer", t: "Posponer", d: "Mueve la próxima revisión a una fecha futura." },
  { a: "descartar", t: "Descartar", d: "Lo cierras sin contacto, explicando el motivo." },
];
const BOTON = { asignar: "Tomar este seguimiento", contacto: "Guardar el contacto", atender: "Guardar el resultado y cerrar", posponer: "Guardar la nueva fecha", descartar: "Descartar el seguimiento" };

function camposIntencion(a) {
  const campo = (id, etiqueta, ayuda, extra = "") => `<label for="${id}">${etiqueta}${ayuda ? `<span class="ayuda">${ayuda}</span>` : ""}<input id="${id}" ${extra} maxlength="300" aria-describedby="err-${id}"><span class="error-campo" id="err-${id}" aria-live="polite"></span></label>`;
  switch (a) {
    case "asignar": return '<p>Quedarás como responsable de este seguimiento.</p>';
    case "contacto": return `${campo("nota", "¿Qué pasó en el contacto?", "Por ejemplo: llamada; pide propuesta de renovación.", "required")}${campo("siguiente", "Siguiente paso (opcional)", "Por ejemplo: enviar la propuesta el lunes.")}`;
    case "atender": return `${campo("resultado", "Resultado", "Por ejemplo: renovó la cobertura.", "required")}${campo("siguiente", "Siguiente paso (opcional)", "")}
      <label class="en-linea"><input type="checkbox" id="atribuido"> El resultado se debe a este seguimiento</label>`;
    case "posponer": return `<label for="hasta">Nueva fecha de revisión<span class="ayuda">Debe ser una fecha futura.</span><input type="date" id="hasta" required min="${new Date().toISOString().slice(0, 10)}" aria-describedby="err-hasta"><span class="error-campo" id="err-hasta" aria-live="polite"></span></label>`;
    case "descartar": return campo("motivo", "Motivo del descarte", "Por ejemplo: el cliente cerró operaciones.", "required");
    default: return "";
  }
}

function cronologiaTarea(t) {
  const ev = [
    ...t.historial_evidencia.map(e => ({ fecha: e.ts, etiquetaFecha: fechaHora(e.ts), tipo: "evidencia", titulo: `Evidencia del cierre ${e.cierre_id}`, chip: "Cierre",
      detalle: `${esc(e.motivos.join(" · "))}<br>${esc(evidenciaEnPalabras(e.evidencia))}${e.version_modelo ? ` · modelo ${esc(e.version_modelo)}` : ""}` })),
    ...t.eventos.map(e => {
      const d = e.datos || {};
      const partes = [d.nota && `Contacto: ${d.nota}`, d.resultado && `Resultado declarado: ${d.resultado}`, d.siguiente_paso && `Siguiente paso: ${d.siguiente_paso}`, d.hasta && `Hasta el ${fechaLarga(d.hasta)}`, d.motivo && `Motivo: ${d.motivo}`].filter(Boolean);
      return { fecha: e.fecha, etiquetaFecha: fechaHora(e.fecha), tipo: e.tipo === "contacto_registrado" ? "contacto" : e.tipo === "atendida" || e.tipo === "resultado_atribuido" ? "resultado" : "evento",
        titulo: EVENTOS[e.tipo] || e.tipo, chip: e.tipo === "contacto_registrado" ? "Contacto" : e.tipo === "atendida" ? "Resultado de Ventas" : "", detalle: esc(`${e.actor}${partes.length ? ` · ${partes.join(" · ")}` : ""}`) };
    }),
  ].sort((a, b) => a.fecha.localeCompare(b.fecha));
  return cronologia(ev, { vacio: "Sin movimientos." });
}

function diferencias(antes, ahora) {
  const c = [];
  if (antes.estado !== ahora.estado) c.push(`estado: ${ESTADOS[antes.estado] || antes.estado} → ${ESTADOS[ahora.estado] || ahora.estado}`);
  if (antes.responsable_id !== ahora.responsable_id) c.push(`responsable: ${responsable(antes.responsable_id)} → ${responsable(ahora.responsable_id)}`);
  if (antes.fecha_revision !== ahora.fecha_revision) c.push(`próxima revisión: ${antes.fecha_revision || "—"} → ${ahora.fecha_revision || "—"}`);
  if (antes.siguiente_paso !== ahora.siguiente_paso) c.push(`siguiente paso: «${antes.siguiente_paso || "—"}» → «${ahora.siguiente_paso || "—"}»`);
  if (antes.resultado !== ahora.resultado) c.push(`resultado: «${ahora.resultado || "—"}»`);
  return c;
}

const CONFIRMACION = {
  asignar: "Ahora eres responsable de este seguimiento.", contacto: "Contacto guardado. El seguimiento sigue abierto.",
  atender: "Resultado guardado. El seguimiento quedó atendido.", posponer: "Nueva fecha de revisión guardada.", descartar: "Seguimiento descartado con su motivo.",
};

export async function vistaTarea(id, intencion = null, aviso = "") {
  const volver = { href: ultimaLista, texto: ultimaLista === "#/tareas" ? "Volver a la lista de seguimientos" : "Volver a la lista filtrada" };
  let t;
  try { t = await api("GET", `/api/tareas/${id}`); } catch (e) { $vista.innerHTML = `${encabezado({ titulo: "Seguimiento", volver })}${errorHtml(e, { reintentar: e.status !== 404 })}`; return; }
  const editable = puede("tareas.gestionar") && !["atendida", "descartada"].includes(t.estado);
  const opciones = INTENCIONES.filter(o => !(o.a === "asignar" && t.responsable_id === S.usuario.id));
  const sel = opciones.find(o => o.a === intencion) ? intencion : null;
  $vista.innerHTML = `${encabezado({ titulo: `${TIPOS[t.tipo] || t.tipo} · cliente ${t.cliente_id}`, volver,
    descripcion: `Estado actual: <strong>${esc(ESTADOS[t.estado] || t.estado)}</strong>.`,
    contexto: [{ etiqueta: "Última actualización", valor: esc(fechaHora(t.actualizada_en)) }, { etiqueta: "Evidencia del cierre", valor: esc(t.historial_evidencia.at(-1)?.cierre_id || "—") }] })}
  <div id="msg" tabindex="-1">${aviso}</div>
  <dl class="cifras encabezado-tarea"><div><dt>Cliente</dt><dd>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(t.cliente_id)}">${esc(t.cliente_id)}</a>` : esc(t.cliente_id)}</dd></div>
    <div><dt>Por qué existe</dt><dd>${esc(t.motivos.join(" · "))}</dd></div><div><dt>Responsable</dt><dd>${esc(responsable(t.responsable_id))}</dd></div>
    <div><dt>Próxima revisión</dt><dd>${t.fecha_revision ? esc(fechaLarga(t.fecha_revision)) : "Sin fecha registrada"}</dd></div></dl>
  <p class="muted">Evidencia: ${esc(evidenciaEnPalabras(t.evidencia))}.</p>
  ${t.resultado ? `<p><strong>Resultado declarado:</strong> ${esc(t.resultado)}${t.siguiente_paso ? ` · siguiente paso: ${esc(t.siguiente_paso)}` : ""}</p>` : t.siguiente_paso ? `<p><strong>Siguiente paso:</strong> ${esc(t.siguiente_paso)}</p>` : ""}
  ${t.motivo_descarte ? `<p><strong>Descartado:</strong> ${esc(t.motivo_descarte)}</p>` : ""}
  ${editable ? `<section class="panel"><h2>¿Qué quieres hacer?</h2>
    <div class="intenciones" role="radiogroup" aria-label="Acción sobre el seguimiento">${opciones.map(o => `<label class="intencion ${sel === o.a ? "activa" : ""}"><input type="radio" name="int" value="${o.a}" ${sel === o.a ? "checked" : ""}><strong>${esc(o.t)}</strong><span class="muted">${esc(o.d)}</span></label>`).join("")}</div>
    ${sel ? `<form id="accion" class="campos-accion" novalidate>${camposIntencion(sel)}<div class="fila"><button>${esc(BOTON[sel])}</button><button type="button" class="sec" id="cancelar">Cancelar</button></div></form>` : '<p class="muted">Elige una opción para ver qué datos hacen falta.</p>'}
    <p class="muted">La decisión queda registrada con tu nombre y la hora. Ningún mensaje se envía al cliente desde aquí.</p></section>`
    : !puede("tareas.gestionar") ? '<p class="estado">Tu perfil puede consultar este seguimiento, pero no modificarlo.</p>' : '<p class="estado">Este seguimiento está cerrado. Su historia se conserva abajo.</p>'}
  <section class="panel" id="cronologia" tabindex="-1"><h2>Qué ha pasado</h2><p class="muted">Evidencia de cada cierre, contactos registrados y resultado que declara Ventas, en orden de fecha.</p>${cronologiaTarea(t)}</section>
  ${detalleTecnico(`<p class="muted">Versión ${t.version} · episodio ${esc(t.episodio_id)} · oportunidad ${esc(t.oportunidad_id)}</p><pre>${esc(JSON.stringify({ evidencia: t.evidencia, historial_evidencia: t.historial_evidencia }, null, 2))}</pre>`, "Versión y datos originales")}`;
  $vista.querySelectorAll("input[name=int]").forEach(r => r.addEventListener("change", () => vistaTarea(id, r.value).then(() => document.querySelector("#accion input, #accion button")?.focus())));
  document.getElementById("cancelar")?.addEventListener("click", () => vistaTarea(id));
  const form = document.getElementById("accion");
  form?.addEventListener("submit", async e => {
    e.preventDefault();
    // Validación junto al campo y foco en el primer error; el texto escrito se conserva.
    let primero = null;
    form.querySelectorAll("input[required]").forEach(i => {
      const v = i.value.trim(), err = document.getElementById(`err-${i.id}`);
      const mal = !v || (i.type === "date" && i.min && v < i.min);
      i.setAttribute("aria-invalid", mal ? "true" : "false");
      if (err) err.textContent = mal ? (i.type === "date" ? "Elige una fecha a partir de hoy." : "Este dato es obligatorio.") : "";
      if (mal && !primero) primero = i;
    });
    if (primero) return primero.focus();
    const btn = form.querySelector("button"); btn.disabled = true; btn.textContent = "Guardando…";
    const v = s => document.getElementById(s)?.value?.trim();
    const cuerpo = { version: t.version, __clave: form.dataset.clave ||= clave() };
    if (sel === "posponer") cuerpo.hasta = v("hasta");
    if (sel === "descartar") cuerpo.motivo = v("motivo");
    if (sel === "atender") Object.assign(cuerpo, { resultado: v("resultado"), siguiente_paso: v("siguiente") || null, atribuido: document.getElementById("atribuido").checked });
    if (sel === "contacto") Object.assign(cuerpo, { siguiente_paso: v("siguiente") || null, nota: v("nota") || null });
    try {
      await api("POST", `/api/tareas/${t.id}/${sel}`, cuerpo);
      await vistaTarea(t.id, null, `<div class="estado ok" role="status"><strong>${esc(CONFIRMACION[sel])}</strong> Lo ves al final de «Qué ha pasado». <button type="button" class="enlace" data-ir-a="cronologia">Ver en la historia</button></div>`);
      document.getElementById("msg").focus();
    } catch (err) {
      if (err.status === 409 && err.datos?.error === "conflicto_version") {
        const actual = await api("GET", `/api/tareas/${t.id}`).catch(() => null);
        const cambios = actual ? diferencias(t, actual) : [];
        document.getElementById("msg").innerHTML = `<div class="estado error" role="alert"><p><strong>Otra persona actualizó este seguimiento mientras lo tenías abierto.</strong> Tu cambio no se guardó para no sobrescribir el suyo. Lo que escribiste sigue en el formulario.</p>${cambios.length ? `<ul>${cambios.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
          <button type="button" class="sec" id="recargar">Ver la versión actual y decidir de nuevo</button></div>`;
        document.getElementById("recargar").addEventListener("click", () => vistaTarea(t.id, sel));
      } else if (err.status === undefined || err instanceof TypeError) {
        document.getElementById("msg").innerHTML = `${errorHtml(err)}<p class="muted">No sabemos si el cambio llegó al servidor. Antes de repetir, <button type="button" class="enlace" id="comprobar">comprueba el estado actual</button>.</p>`;
        document.getElementById("comprobar")?.addEventListener("click", () => vistaTarea(t.id, sel));
      } else document.getElementById("msg").innerHTML = errorHtml(err);
      btn.disabled = false; btn.textContent = BOTON[sel];
      document.getElementById("msg").focus();
    }
  });
}
