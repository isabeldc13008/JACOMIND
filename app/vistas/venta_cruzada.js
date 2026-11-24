// Venta cruzada (M4): recomendaciones EXPERIMENTALES para revisión de Ventas. No son ofertas, no cambian la agenda y
// no muestran porcentajes: el modelo publica un puntaje de ranking sin calibrar.
import { $vista, api, errorHtml, esc, estadoHtml, fechaLarga, nuevoTurno, num, plural, puede, ruta, ir, vigente } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

const COMPAT = { confirmada: "Compatibilidad confirmada", pendiente_revision: "Compatibilidad por revisar" };
const EPISODIO = { en_revision: "En revisión", aceptada: "Aceptada", aplazada: "Aplazada", descartada: "Descartada (no se reabre)", cerrada_compra: "Cerrada: compra posterior observada" };
const ESTADOS_REV = { pertinente: "Pertinente", ya_cubierto: "Ya cubierto", incompatible: "Incompatible", sin_necesidad: "Sin necesidad identificada", informacion_insuficiente: "Información insuficiente" };
const COBERTURA = { sin_candidatos: "Sin candidatos", sin_historial: "Sin historial", no_elegible: "No elegible" };

function accionesHtml(i) {
  const cerrado = i.episodio && ["descartada", "cerrada_compra"].includes(i.episodio.estado);
  if (!puede("venta_cruzada.decidir") || cerrado) return "";
  const id = `${i.cliente_id}-${i.producto_id}`;
  return `<form class="vc-decision filtros" data-cliente="${esc(i.cliente_id)}" data-producto="${esc(i.producto_id)}" aria-label="Decisión sobre ${esc(i.producto_nombre)} para ${esc(i.cliente_id)}">
    <label>Acción <select name="accion" id="acc-${esc(id)}"><option value="revisar">Marcar en revisión</option><option value="aceptar">Aceptar</option>
      <option value="aplazar">Aplazar</option><option value="descartar">Descartar</option></select></label>
    <label>Motivo <input name="motivo" required maxlength="300" placeholder="Por qué"></label><button>Guardar</button></form>`;
}

function itemHtml(i, conCliente = true) {
  return `<tr>${conCliente ? `<td>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(i.cliente_id)}">${esc(i.cliente_id)}</a>` : esc(i.cliente_id)}</td>` : ""}
    <td class="n">${num(i.posicion)}</td><td><strong>${esc(i.producto_nombre)}</strong><div class="muted">${esc(i.producto_id)}</div></td>
    <td>${esc(i.origen_texto)}</td>
    <td><span class="chip${i.estado_compatibilidad === "confirmada" ? " fuerte" : ""}">${esc(COMPAT[i.estado_compatibilidad] || i.estado_compatibilidad)}</span></td>
    <td class="muted">${(i.motivos || []).map(esc).join("<br>")}</td>
    <td>${i.episodio ? esc(EPISODIO[i.episodio.estado] || i.episodio.estado) + (i.episodio.motivo ? `<div class="muted">${esc(i.episodio.motivo)}</div>` : "") : '<span class="muted">Sin decisión</span>'}
      ${accionesHtml(i)}</td></tr>`;
}

/** Bloque para la ficha: productos sugeridos con evidencia y compatibilidad; separado de recompra y renovación. */
export function ventaCruzadaFichaHtml(s) {
  if (!s) return "";
  const vacio = s.cobertura && s.cobertura.estado !== "con_recomendaciones"
    ? `<p>${esc(COBERTURA[s.cobertura.estado] || s.cobertura.estado)}: ${esc(s.cobertura.motivo || "")}</p>` : "";
  return `<section class="panel"><h2>Venta cruzada <span class="chip">IA · experimental</span></h2><div id="msg-vc" role="status"></div>
    ${s.items.length ? `<div class="tabla"><table><tr><th class="n">#</th><th>Producto sugerido</th><th>Origen</th><th>Compatibilidad</th><th>Evidencia</th><th>Decisión</th></tr>
      ${s.items.map(i => itemHtml(i, false)).join("")}</table></div>` : vacio || '<p class="muted">Sin recomendaciones para este cliente.</p>'}
    <p class="muted">Corte del ${esc(fechaLarga(s.corte))} · ${esc(s.estado_experimento)}. ${esc(s.nota)} Los productos ya adquiridos se atienden como recompra o renovación en la agenda.</p></section>`;
}

function revisionHtml(r) {
  if (!r || r.estado !== "ok") return "";
  const res = r.resumen;
  const pct = x => x == null ? "—" : `${Math.round(x * 100)} %`;
  const puedeRevisar = puede("venta_cruzada.revisar");
  return `<section class="panel"><h2>Revisión comercial de la muestra</h2>
    <p>${num(res.revisados)} de ${num(res.total_muestra)} pares revisados (${num(res.pendientes)} pendientes). Pertinencia entre casos evaluables: <strong>${pct(res.pertinencia_entre_evaluables)}</strong>
      (${num(res.por_estado.pertinente)} de ${num(res.evaluables)}; meta 80 %). Información insuficiente: ${num(res.por_estado.informacion_insuficiente)}.</p>
    <p class="muted">${esc(res.nota)} Muestra: ${esc(r.criterio.criterio || "")} · semilla ${esc(String(r.criterio.semilla))} · ${esc(r.criterio.universo || "")}.</p>
    <div class="tabla"><table><tr><th>Cliente</th><th>Producto</th><th>Familia</th><th class="n">Tercil</th><th>Revisión</th></tr>
    ${r.pares.map(p => `<tr><td>${esc(p.cliente_id)}</td><td>${esc(p.producto_id)}</td><td>${esc(p.familia)}</td><td class="n">${num(p.tercil_puntaje)}</td>
      <td>${p.revision ? `${esc(ESTADOS_REV[p.revision.estado_revision])} · ${esc(p.revision.revisor)} · ${esc(fechaLarga(p.revision.fecha.slice(0, 10)))}<div class="muted">${esc(p.revision.motivo)}</div>` : '<span class="muted">Pendiente</span>'}
      ${puedeRevisar ? `<form class="vc-revision filtros" data-cliente="${esc(p.cliente_id)}" data-producto="${esc(p.producto_id)}" aria-label="Revisar ${esc(p.producto_id)} para ${esc(p.cliente_id)}">
        <label>Estado <select name="estado">${Object.entries(ESTADOS_REV).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
        <label>Motivo <input name="motivo" required maxlength="300"></label><label>Evidencia <input name="evidencia" maxlength="300"></label><button>Registrar</button></form>` : ""}</td></tr>`).join("")
      || '<tr><td colspan=5 class="muted">La publicación no incluye muestra de revisión.</td></tr>'}</table></div></section>`;
}

/** Activa los formularios de decisión y revisión dentro de ``raiz``; ``alTerminar`` vuelve a pintar la vista. */
export function activarVentaCruzada(raiz, alTerminar) {
  const msg = () => raiz.querySelector("#msg-vc");
  const enviar = (fm, ruta, cuerpo) => fm.addEventListener("submit", async e => {
    e.preventDefault();
    try { await api("POST", ruta, cuerpo(new FormData(fm))); alTerminar(); }
    catch (err) { const m = msg(); if (m) m.innerHTML = errorHtml(err); }
  });
  raiz.querySelectorAll("form.vc-decision").forEach(fm => enviar(fm, "/api/venta-cruzada/decision",
    fd => ({ cliente_id: fm.dataset.cliente, producto_id: fm.dataset.producto, accion: fd.get("accion"), motivo: fd.get("motivo") })));
  raiz.querySelectorAll("form.vc-revision").forEach(fm => enviar(fm, "/api/venta-cruzada/revision",
    fd => ({ cliente_id: fm.dataset.cliente, producto_id: fm.dataset.producto, estado: fd.get("estado"), motivo: fd.get("motivo"), evidencia: fd.get("evidencia") || null })));
}

export async function vistaVentaCruzada() {
  const { q } = ruta();
  const filtro = q.get("compatibilidad") || "";
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando recomendaciones…");
  let d, r;
  try {
    [d, r] = await Promise.all([api("GET", `/api/venta-cruzada${filtro ? `?compatibilidad=${encodeURIComponent(filtro)}` : ""}`), api("GET", "/api/venta-cruzada/revision")]);
  } catch (e) { if (vigente(turno)) $vista.innerHTML = errorHtml(e); return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `<h1>Venta cruzada <span class="chip">IA · experimental</span></h1>${estadoHtml("", d.mensaje)}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  $vista.innerHTML = `<h1>Venta cruzada <span class="chip">IA · experimental</span></h1>
  ${respuesta(`<strong>${plural(d.items.length, "propuesta", "propuestas")} de producto complementario</strong> para revisión de Ventas, al corte del ${esc(fechaLarga(s.corte))}.`,
    `${esc(s.estado_experimento)} · ${plural(d.compatibilidad_pendiente, "propuesta", "propuestas")} con compatibilidad por revisar.`)}
  <p class="muted">${esc(d.nota)} ${esc(d.separacion)} Seguimientos automáticos: ${d.tareas_automaticas ? "activados" : "desactivados"}.</p>
  <form class="filtros" id="f"><label>Compatibilidad <select name="compatibilidad"><option value="">Todas</option>
    <option value="pendiente_revision"${filtro === "pendiente_revision" ? " selected" : ""}>Por revisar</option><option value="confirmada"${filtro === "confirmada" ? " selected" : ""}>Confirmada</option></select></label><button>Filtrar</button></form>
  <div id="msg-vc" role="status"></div>
  <div class="tabla"><table><caption class="muted">Hasta tres productos por cliente, en orden de posición</caption>
  <tr><th>Cliente</th><th class="n">#</th><th>Producto sugerido</th><th>Origen</th><th>Compatibilidad</th><th>Evidencia</th><th>Decisión</th></tr>
  ${d.items.map(i => itemHtml(i)).join("") || '<tr><td colspan=7 class="muted">No hay propuestas con este filtro.</td></tr>'}</table></div>
  <section class="panel"><h2>Clientes sin recomendación</h2><p>${num(c.con_recomendaciones || 0)} con propuestas, ${num(c.sin_candidatos || 0)} sin candidatos, ${num(c.sin_historial || 0)} sin historial, ${num(c.no_elegible || 0)} no elegibles. No se inventan productos para completar tres posiciones.</p>
    ${d.sin_recomendacion.length ? `<ul>${d.sin_recomendacion.map(x => `<li>${esc(x.cliente_id)}: ${esc(COBERTURA[x.estado] || x.estado)} — ${esc(x.motivo || "")}</li>`).join("")}</ul>` : ""}</section>
  ${revisionHtml(r)}
  ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación en sombra")}`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const v = new FormData(e.target).get("compatibilidad"); ir(`#/venta-cruzada${v ? `?compatibilidad=${v}` : ""}`); });
  activarVentaCruzada($vista, vistaVentaCruzada);
}
