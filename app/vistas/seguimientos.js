// Seguimientos: lista con cupo y planificación, y detalle de tarea (entradas 7 y 8 del plan).
import {
  $vista, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, nuevoTurno, num, pct, plural, puede, ruta, S, vigente,
} from "../nucleo.js";
import { barras, cronologia, detalleTecnico } from "../ui.js";

export const TIPOS = { reactivacion: "Reactivación", renovacion: "Cobertura", recompra: "Posible recompra", primera_compra: "Primera compra" };
const ESTADOS = { abierta: "Abierta, sin responsable", asignada: "Asignada", pospuesta: "Pospuesta", atendida: "Atendida", descartada: "Descartada" };
const EVENTOS = {
  expuesta: "Propuesto por el cierre", compra_posterior_observada: "Compra posterior observada (no atribuida)", asignada: "Tarea tomada",
  pospuesta: "Revisión pospuesta", contacto_registrado: "Contacto registrado", atendida: "Cerrada con resultado",
  descartada: "Descartada", resultado_atribuido: "Resultado atribuido al seguimiento", actualizada: "Actualizada con un cierre nuevo",
};
const responsable = id => id ? (id === S.usuario?.id ? `${id} (tú)` : id) : "Sin responsable";

/** Evidencia del cierre en palabras, en lugar del objeto JSON. */
export function evidenciaEnPalabras(ev = {}) {
  const p = [];
  if (ev.ultima_compra) p.push(`última compra el ${fechaLarga(ev.ultima_compra)}`);
  if (ev.dias_sin_compra != null) p.push(`${ev.dias_sin_compra} días sin comprar`);
  if (ev.renovaciones_proximas) p.push(`${plural(ev.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en 45 días`);
  if (ev.coberturas_vencidas) p.push(plural(ev.coberturas_vencidas, "cobertura vencida", "coberturas vencidas"));
  if (ev.prob_compra_30d != null) p.push(`estimación de compra a 30 días ${pct(ev.prob_compra_30d)}`);
  return p.join(" · ") || "Sin evidencia cuantitativa";
}

// ---------------------------------------------------------------- lista (entrada 7)
export async function vistaTareas(id) {
  if (id) return vistaTarea(Number(id));
  const { q } = ruta();
  const k = q.get("k") || "10", mias = q.get("mias") === "1";
  const turno = nuevoTurno();
  const [lista, avisos, met] = await Promise.all([api("GET", `/api/tareas?k=${encodeURIComponent(k)}${mias ? "&mias=1" : ""}`), api("GET", "/api/avisos"),
    api("GET", `/api/tareas/metricas${mias ? "?mias=1" : ""}`)]).catch(e => [e]);
  if (!vigente(turno)) return;
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  const pendientes = met.pendientes_seleccion ?? lista.length;
  const sinResp = lista.filter(t => !t.responsable_id).length;
  const tipos = Object.entries(met.por_tipo);
  $vista.innerHTML = `<h1>Seguimientos</h1>
  <form class="filtros" id="f"><label>¿Cuántos seguimientos quieres revisar? <input name="k" type="number" min="1" max="200" value="${esc(k)}"></label>
   <label class="en-linea"><input type="checkbox" name="mias" value="1" ${mias ? "checked" : ""}> Solo los asignados a mí</label><button>Ver prioridades</button></form>
  <div class="respuesta"><p class="frase"><strong>${lista.length ? `Tus ${plural(lista.length, "seguimiento prioritario", "seguimientos prioritarios")}` : "No hay seguimientos pendientes"}${lista.length ? ` de ${num(pendientes)} pendientes${mias ? " asignados a ti" : ""}.` : "."}</strong>${lista.length ? ` ${sinResp ? `${plural(sinResp, "no tiene", "no tienen")} responsable todavía.` : "Todos tienen responsable."}` : ""}</p>
   <p class="contexto">Orden: prioridad de la acción, estimación de compra y cliente. Estado actual de las tareas, no del cierre.</p></div>
  <div class="tabla"><table><tr><th>#</th><th>Cliente</th><th>Motivo</th><th>Responsable</th><th>Próxima revisión</th><th>Estado</th><th><span class="oculto-visual">Tarea</span></th></tr>
  ${lista.map((t, i) => `<tr><td>${i + 1}</td><td>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(t.cliente_id)}">${esc(t.cliente_id)}</a>` : esc(t.cliente_id)}</td>
    <td><strong>${esc(TIPOS[t.tipo] || t.tipo)}</strong><div class="muted">${esc(evidenciaEnPalabras(t.evidencia))}</div></td><td>${esc(responsable(t.responsable_id))}</td>
    <td>${t.fecha_revision ? esc(fechaLarga(t.fecha_revision)) : "Sin fecha"}</td><td>${esc(ESTADOS[t.estado] || t.estado)}</td><td><a href="#/tareas/${t.id}">Abrir tarea</a></td></tr>`).join("") || '<tr><td colspan=7 class="muted">Sin seguimientos pendientes.</td></tr>'}
  </table></div>
  <div class="grid2"><section class="panel"><h2>Medición del equipo</h2>
    <p class="muted">Alcance: todas las tareas del equipo${mias ? ", aunque arriba solo veas las tuyas" : ""}. Cada barra indica cuántas tareas de ese tipo terminaron así, sobre el total del tipo.</p>
    ${tipos.length ? `${barras(tipos.map(([t, v]) => ({ etiqueta: `${TIPOS[t] || t} · atendidas`, valor: v.fraccion_atendida, texto: `${num(v.atendidas ?? Math.round(v.fraccion_atendida * v.total))} de ${num(v.total)} (${pct(v.fraccion_atendida)})` })), { titulo: "Atendidas" })}
    ${barras(tipos.map(([t, v]) => ({ etiqueta: `${TIPOS[t] || t} · descartadas`, valor: v.tasa_descarte, texto: `${num(v.descartadas ?? Math.round(v.tasa_descarte * v.total))} de ${num(v.total)} (${pct(v.tasa_descarte)})` })), { titulo: "Descartadas" })}` : '<p class="muted">Aún no hay tareas para medir.</p>'}
    <p class="muted">${esc(met.nota)} Avisos duplicados: ${num(met.avisos_duplicados)} · episodios con varias tareas: ${num(met.episodios_con_varias_tareas)}.</p></section>
   <section class="panel"><h2>Avisos recientes</h2>${avisos.slice(0, 12).map(a => `<div class="muted">${esc(fechaHora(a.creado_en))} · ${esc(a.mensaje)}</div>`).join("") || '<p class="muted">Sin avisos.</p>'}</section></div>`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const fd = new FormData(e.target); ir(`#/tareas?k=${fd.get("k")}${fd.get("mias") ? "&mias=1" : ""}`); });
}

// ---------------------------------------------------------------- detalle (entrada 8)
const INTENCIONES = [
  { a: "asignar", t: "Tomar la tarea", d: "Pasas a ser responsable. No cambia el resultado." },
  { a: "contacto", t: "Registrar un contacto", d: "Anota la llamada o reunión y el siguiente paso. La tarea sigue abierta." },
  { a: "atender", t: "Cerrar con resultado", d: "Declara el resultado del seguimiento y lo da por atendido." },
  { a: "posponer", t: "Posponer", d: "Mueve la próxima revisión a una fecha futura." },
  { a: "descartar", t: "Descartar", d: "Cierra la tarea sin contacto, con un motivo." },
];

function camposIntencion(a) {
  switch (a) {
    case "asignar": return '<p class="muted">Quedarás como responsable de este seguimiento.</p>';
    case "contacto": return `<label>¿Qué pasó en el contacto? <input id="nota" placeholder="p. ej. llamada; pide propuesta de renovación" maxlength="300"></label>
      <label>Siguiente paso <input id="siguiente" placeholder="p. ej. enviar propuesta el lunes" maxlength="300"></label>`;
    case "atender": return `<label>Resultado <input id="resultado" placeholder="p. ej. renovó la cobertura" required maxlength="300"></label>
      <label>Siguiente paso (opcional) <input id="siguiente" maxlength="300"></label>
      <label class="en-linea"><input type="checkbox" id="atribuido"> El resultado se debe a este seguimiento</label>`;
    case "posponer": return '<label>Nueva fecha de revisión <input type="date" id="hasta" required></label>';
    case "descartar": return '<label>Motivo del descarte <input id="motivo" required maxlength="300" placeholder="p. ej. el cliente cerró operaciones"></label>';
    default: return "";
  }
}

function cronologiaTarea(t) {
  const ev = [
    ...t.historial_evidencia.map(e => ({ fecha: e.ts, etiquetaFecha: fechaHora(e.ts), tipo: "evidencia", titulo: `Evidencia del cierre ${e.cierre_id}`, chip: "Cierre",
      detalle: `${esc(e.motivos.join(" · "))}<br>${esc(evidenciaEnPalabras(e.evidencia))}${e.version_modelo ? ` · modelo ${esc(e.version_modelo)}` : ""}` })),
    ...t.eventos.map(e => {
      const d = e.datos || {};
      const partes = [d.nota && `Contacto: ${d.nota}`, d.resultado && `Resultado declarado: ${d.resultado}`, d.siguiente_paso && `Siguiente paso: ${d.siguiente_paso}`, d.hasta && `Hasta ${fechaLarga(d.hasta)}`, d.motivo && `Motivo: ${d.motivo}`].filter(Boolean);
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

export async function vistaTarea(id, intencion = null, aviso = "") {
  let t;
  try { t = await api("GET", `/api/tareas/${id}`); } catch (e) { $vista.innerHTML = `<a href="#/tareas">← Seguimientos</a>${errorHtml(e)}`; return; }
  const editable = puede("tareas.gestionar") && !["atendida", "descartada"].includes(t.estado);
  const opciones = INTENCIONES.filter(o => !(o.a === "asignar" && t.responsable_id === S.usuario.id));
  const sel = opciones.find(o => o.a === intencion) ? intencion : null;
  $vista.innerHTML = `<a href="#/tareas">← Seguimientos</a>
  <h1>${esc(TIPOS[t.tipo] || t.tipo)} · ${esc(t.cliente_id)}</h1>
  <dl class="cifras encabezado-tarea"><div><dt>Cliente</dt><dd>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(t.cliente_id)}">${esc(t.cliente_id)}</a>` : esc(t.cliente_id)}</dd></div>
    <div><dt>Motivo</dt><dd>${esc(t.motivos.join(" · "))}</dd></div><div><dt>Responsable</dt><dd>${esc(responsable(t.responsable_id))}</dd></div>
    <div><dt>Próxima revisión</dt><dd>${t.fecha_revision ? esc(fechaLarga(t.fecha_revision)) : "Sin fecha"}</dd></div><div><dt>Estado</dt><dd>${esc(ESTADOS[t.estado] || t.estado)}</dd></div><div><dt>Última actualización</dt><dd>${esc(fechaHora(t.actualizada_en))}</dd></div></dl>
  ${t.resultado ? `<p><strong>Resultado declarado:</strong> ${esc(t.resultado)}${t.siguiente_paso ? ` · siguiente paso: ${esc(t.siguiente_paso)}` : ""}</p>` : t.siguiente_paso ? `<p><strong>Siguiente paso:</strong> ${esc(t.siguiente_paso)}</p>` : ""}
  ${t.motivo_descarte ? `<p><strong>Descartada:</strong> ${esc(t.motivo_descarte)}</p>` : ""}
  <div id="msg">${aviso}</div>
  ${editable ? `<section class="panel"><h2>¿Qué quieres hacer?</h2>
    <div class="intenciones" role="radiogroup" aria-label="Acción sobre la tarea">${opciones.map(o => `<label class="intencion ${sel === o.a ? "activa" : ""}"><input type="radio" name="int" value="${o.a}" ${sel === o.a ? "checked" : ""}><strong>${esc(o.t)}</strong><span class="muted">${esc(o.d)}</span></label>`).join("")}</div>
    ${sel ? `<form id="accion" class="campos-accion">${camposIntencion(sel)}<div class="fila"><button>${esc(opciones.find(o => o.a === sel).t)}</button></div></form>` : ""}
    <p class="muted">La decisión humana se registra antes de cualquier contacto con la empresa.</p></section>` : !puede("tareas.gestionar") ? '<p class="muted">Tu perfil puede consultar esta tarea, pero no modificarla.</p>' : ""}
  <section class="panel"><h2>Cronología</h2><p class="muted">Distingue la evidencia de cada cierre, los contactos registrados y el resultado que declara Ventas.</p>${cronologiaTarea(t)}</section>
  ${detalleTecnico(`<p class="muted">Versión ${t.version} · episodio ${esc(t.episodio_id)} · oportunidad ${esc(t.oportunidad_id)}</p><pre>${esc(JSON.stringify({ evidencia: t.evidencia, historial_evidencia: t.historial_evidencia }, null, 2))}</pre>`, "Versión y datos originales")}`;
  $vista.querySelectorAll("input[name=int]").forEach(r => r.addEventListener("change", () => vistaTarea(id, r.value)));
  document.getElementById("accion")?.addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button"); btn.disabled = true;
    const v = s => document.getElementById(s)?.value?.trim();
    const cuerpo = { version: t.version, __clave: clave() };
    if (sel === "posponer") cuerpo.hasta = v("hasta");
    if (sel === "descartar") cuerpo.motivo = v("motivo");
    if (sel === "atender") Object.assign(cuerpo, { resultado: v("resultado"), siguiente_paso: v("siguiente") || null, atribuido: document.getElementById("atribuido").checked });
    if (sel === "contacto") Object.assign(cuerpo, { siguiente_paso: v("siguiente") || null, nota: v("nota") || null });
    try {
      await api("POST", `/api/tareas/${t.id}/${sel}`, cuerpo);
      vistaTarea(t.id, null, estadoHtml("ok", sel === "contacto" ? "Contacto registrado. La tarea sigue abierta." : "Cambios guardados."));
    } catch (err) {
      if (err.status === 409 && err.datos?.error === "conflicto_version") {
        const actual = await api("GET", `/api/tareas/${t.id}`).catch(() => null);
        const cambios = actual ? diferencias(t, actual) : [];
        $vista.querySelector("#msg").innerHTML = `<div class="estado error" role="alert">Otra persona actualizó esta tarea mientras la tenías abierta.${cambios.length ? `<ul>${cambios.map(c => `<li>${esc(c)}</li>`).join("")}</ul>` : ""}
          <button type="button" class="sec" id="recargar">Ver la versión actual y decidir de nuevo</button></div>`;
        document.getElementById("recargar").addEventListener("click", () => vistaTarea(t.id, sel));
      } else { $vista.querySelector("#msg").innerHTML = errorHtml(err); btn.disabled = false; }
    }
  });
}
