// V09 Productos que podrías ofrecer (M4, en prueba): sugerencias para revisión de Ventas. No son ofertas ni mensajes, no
// cambian la cartera y no muestran porcentajes: el modelo publica un orden sin calibrar.
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaLarga, ir, nuevoTurno, num, plural, puede, ruta, vigente } from "../nucleo.js";
import { avisoPrueba, ctxDatos, detalleTecnico, encabezado, enPrueba, hallazgo, pestanas, vacio } from "../ui.js";
import { estadoIA, pedirNarrativa, pieIA } from "../ia_textos.js";

const COMPAT = { confirmada: "Compatibilidad confirmada", pendiente_revision: "Compatibilidad por revisar" };
const EPISODIO = { en_revision: "En revisión", aceptada: "Aceptada", aplazada: "Aplazada", descartada: "Descartada (no se reabre)", cerrada_compra: "Cerrada: compra posterior observada" };
const ESTADOS_REV = { pertinente: "Pertinente", ya_cubierto: "Ya cubierto", incompatible: "Incompatible", sin_necesidad: "Sin necesidad identificada", informacion_insuficiente: "Información insuficiente" };
const COBERTURA = { sin_candidatos: "Sin candidatos", sin_historial: "Sin historial", no_elegible: "No elegible" };
const ACCIONES = [["revisar", "Marcar en revisión"], ["aceptar", "Aceptar la sugerencia"], ["aplazar", "Aplazar"], ["descartar", "Descartar"]];
const TITULO = "Productos que podrías ofrecer";

function decisionHtml(i) {
  const cerrado = i.episodio && ["descartada", "cerrada_compra"].includes(i.episodio.estado);
  const estado = i.episodio ? `<p><strong>Decisión registrada:</strong> ${esc(EPISODIO[i.episodio.estado] || i.episodio.estado)}${i.episodio.motivo ? ` · ${esc(i.episodio.motivo)}` : ""}</p>` : '<p class="muted">Sin decisión registrada.</p>';
  if (!puede("venta_cruzada.decidir") || cerrado) return estado + (!puede("venta_cruzada.decidir") ? '<p class="muted">Tu perfil puede consultar, no decidir.</p>' : "");
  const id = `${i.cliente_id}-${i.producto_id}`.replace(/[^\w-]/g, "");
  return `${estado}<form class="vc-decision filtros" data-cliente="${esc(i.cliente_id)}" data-producto="${esc(i.producto_id)}" aria-label="Decisión sobre ${esc(i.producto_nombre)} para ${esc(i.cliente_id)}" novalidate>
    <label for="acc-${id}">Decisión <select name="accion" id="acc-${id}">${ACCIONES.map(([k, t]) => `<option value="${k}">${t}</option>`).join("")}</select></label>
    <label for="mot-${id}">Motivo <span class="ayuda">Obligatorio. Por ejemplo: ya lo usa otro proveedor.</span><input name="motivo" id="mot-${id}" required maxlength="300" aria-describedby="err-mot-${id}"><span class="error-campo" id="err-mot-${id}"></span></label>
    <button>Guardar la decisión</button></form>
    <p class="muted">Aceptar registra tu decisión; no envía una oferta ni un mensaje al cliente, y no cuenta como venta.</p>`;
}

function tarjeta(i) {
  return `<article class="tarjeta-caso"><h3>${num(i.posicion)}. ${esc(i.producto_nombre)} <span class="muted">${esc(i.producto_id)}</span></h3>
    <p><span class="sello ${i.estado_compatibilidad === "confirmada" ? "sello-ok" : "sello-prueba"}">${esc(COMPAT[i.estado_compatibilidad] || i.estado_compatibilidad)}</span></p>
    <div class="ia-producto" data-ia-cliente="${esc(i.cliente_id)}" data-ia-producto="${esc(i.producto_id)}"></div>
    <dl class="comparacion"><div><dt>Cómo se eligió</dt><dd>${esc(i.origen_texto)}</dd></div><div><dt>Clientes que lo compraron</dt><dd>${num(i.soporte)}</dd></div></dl>
    <p class="etiqueta-datos">Datos que lo respaldan</p>
    <ul>${(i.motivos || []).map(m => `<li>${esc(m)}</li>`).join("")}</ul>
    <div class="decision" data-msg>${decisionHtml(i)}</div></article>`;
}

/** Caja donde aparece el enfoque redactado por IA para un cliente. */
const cajaEnfoque = id => `<div class="ia-panel" data-ia-enfoque="${esc(id)}" aria-live="polite"><h3>Cómo plantear la conversación</h3><div class="ia-cuerpo"></div></div>`;

/** Pide el texto de IA del cliente y lo coloca en el enfoque y en cada producto. Sin IA, deja los textos originales. */
export function pintarVentaCruzadaIA(raiz, clienteId, turno) {
  const caja = raiz.querySelector(`[data-ia-enfoque="${clienteId}"] .ia-cuerpo`);
  if (!caja) return;
  pedirNarrativa(`/api/narrativas/venta-cruzada/${encodeURIComponent(clienteId)}`, turno, r => {
    if (r.estado === "no_aplica" || r.estado === "desactivada") { caja.parentElement.hidden = true; return; }
    if (r.estado !== "ok") { caja.innerHTML = estadoIA(r); return; }
    caja.innerHTML = `<p>${esc(r.texto.enfoque)}</p>${pieIA(r)}`;
    raiz.querySelectorAll(`[data-ia-cliente="${clienteId}"]`).forEach(el => {
      const t = r.texto.productos?.[el.dataset.iaProducto];
      el.innerHTML = t ? `<p class="ia-texto"><span class="sello sello-ia">IA</span> ${esc(t)}</p>` : "";
    });
  });
}

/** Bloque para la ficha: productos sugeridos con evidencia y compatibilidad; separado de recompra y renovación. */
export function ventaCruzadaFichaHtml(s) {
  if (!s) return "";
  const vacioTxt = s.cobertura && s.cobertura.estado !== "con_recomendaciones" ? `${esc(COBERTURA[s.cobertura.estado] || s.cobertura.estado)}: ${esc(s.cobertura.motivo || "")}` : "Sin sugerencias para este cliente.";
  return `<section class="panel"><h2>Productos que podrías ofrecer ${enPrueba()}</h2><div id="msg-vc" role="status"></div>
    ${s.items.length ? cajaEnfoque(s.items[0].cliente_id) + s.items.map(tarjeta).join("") : vacio(vacioTxt)}
    <p class="muted">Datos hasta el ${esc(fechaLarga(s.corte))} · ${esc(s.estado_experimento)}. ${esc(s.nota)} Los productos que ya tiene se atienden como recompra o renovación en la cartera.</p></section>`;
}

function revisionHtml(r) {
  if (!r || r.estado !== "ok") return vacio("La publicación no incluye una muestra para la evaluación comercial.");
  const res = r.resumen;
  const pc = x => x == null ? "no estimable" : `${Math.round(x * 100)} %`;
  const puedeRevisar = puede("venta_cruzada.revisar");
  return `<p>${num(res.revisados)} de ${num(res.total_muestra)} sugerencias revisadas (${num(res.pendientes)} pendientes). Pertinentes entre las que se pudieron evaluar: <strong>${pc(res.pertinencia_entre_evaluables)}</strong>
      (${num(res.por_estado.pertinente)} de ${num(res.evaluables)}; la meta acordada es 80 %). Información insuficiente: ${num(res.por_estado.informacion_insuficiente)}.</p>
    <p class="muted">${esc(res.nota)} Muestra: ${esc(r.criterio.criterio || "")} · semilla ${esc(String(r.criterio.semilla))} · ${esc(r.criterio.universo || "")}.</p>
    <div class="tabla"><table class="apilable"><thead><tr><th scope="col">Cliente</th><th scope="col">Producto</th><th scope="col">Familia</th><th scope="col" class="n">Grupo de puntaje</th><th scope="col">Revisión</th></tr></thead><tbody>
    ${r.pares.map(p => `<tr><td data-et="Cliente">${esc(p.cliente_id)}</td><td data-et="Producto">${esc(p.producto_id)}</td><td data-et="Familia">${esc(p.familia)}</td><td class="n" data-et="Grupo de puntaje">${num(p.tercil_puntaje)} de 3</td>
      <td data-et="Revisión">${p.revision ? `${esc(ESTADOS_REV[p.revision.estado_revision])} · ${esc(p.revision.revisor)} · ${esc(fechaLarga(p.revision.fecha.slice(0, 10)))}<span class="muted">${esc(p.revision.motivo)}</span>` : '<span class="muted">Pendiente</span>'}
      ${puedeRevisar ? `<form class="vc-revision filtros" data-cliente="${esc(p.cliente_id)}" data-producto="${esc(p.producto_id)}" aria-label="Revisar ${esc(p.producto_id)} para ${esc(p.cliente_id)}" novalidate>
        <label>Resultado <select name="estado">${Object.entries(ESTADOS_REV).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></label>
        <label>Motivo <input name="motivo" required maxlength="300"><span class="error-campo"></span></label><label>Evidencia (opcional) <input name="evidencia" maxlength="300"></label><button>Registrar revisión</button></form>` : ""}</td></tr>`).join("")
      || '<tr><td colspan=5 class="muted">La publicación no incluye muestra de revisión.</td></tr>'}</tbody></table></div>`;
}

/** Activa los formularios de decisión y revisión dentro de ``raiz``; ``alTerminar`` vuelve a pintar con el estado confirmado. */
export function activarVentaCruzada(raiz, alTerminar) {
  const enviar = (fm, ruta, cuerpo, ok) => fm.addEventListener("submit", async e => {
    e.preventDefault();
    const motivo = fm.querySelector("[name=motivo]"), err = fm.querySelector(".error-campo");
    if (!motivo.value.trim()) { motivo.setAttribute("aria-invalid", "true"); if (err) err.textContent = "Escribe el motivo."; motivo.focus(); return; }
    motivo.setAttribute("aria-invalid", "false"); if (err) err.textContent = "";
    const btn = fm.querySelector("button"); btn.disabled = true; btn.textContent = "Guardando…";
    const msg = fm.closest("[data-msg]") || raiz.querySelector("#msg-vc");
    try {
      await api("POST", ruta, { ...cuerpo(new FormData(fm)), __clave: fm.dataset.clave ||= clave() });
      await alTerminar();
      const m = raiz.querySelector("#msg-vc"); if (m) { m.innerHTML = `<div class="estado ok"><strong>${esc(ok)}</strong> Queda registrada con tu nombre y la hora.</div>`; m.scrollIntoView({ block: "nearest" }); }
    } catch (er) {
      msg?.insertAdjacentHTML("afterbegin", errorHtml(er));
      btn.disabled = false; btn.textContent = "Volver a intentar";
    }
  });
  raiz.querySelectorAll("form.vc-decision").forEach(fm => enviar(fm, "/api/venta-cruzada/decision",
    fd => ({ cliente_id: fm.dataset.cliente, producto_id: fm.dataset.producto, accion: fd.get("accion"), motivo: fd.get("motivo").trim() }), "Decisión guardada."));
  raiz.querySelectorAll("form.vc-revision").forEach(fm => enviar(fm, "/api/venta-cruzada/revision",
    fd => ({ cliente_id: fm.dataset.cliente, producto_id: fm.dataset.producto, estado: fd.get("estado"), motivo: fd.get("motivo").trim(), evidencia: fd.get("evidencia") || null }), "Revisión registrada."));
}

export async function vistaVentaCruzada() {
  const { q } = ruta();
  const filtro = q.get("compatibilidad") || "", seccion = q.get("seccion") === "evaluacion" ? "evaluacion" : "propuestas";
  const busca = (q.get("buscar") || "").toUpperCase();
  const turno = nuevoTurno();
  if (!$vista.querySelector("#lista-clientes-vc")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando sugerencias…")}`;
  let d, r;
  try {
    [d, r] = await Promise.all([api("GET", `/api/venta-cruzada${filtro ? `?compatibilidad=${encodeURIComponent(filtro)}` : ""}`), api("GET", "/api/venta-cruzada/revision").catch(() => null)]);
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Sugerencias no disponibles: no hay una publicación en prueba de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  const porCliente = new Map();
  for (const i of d.items) { if (!porCliente.has(i.cliente_id)) porCliente.set(i.cliente_id, []); porCliente.get(i.cliente_id).push(i); }
  const clientes = [...porCliente.keys()].filter(id => !busca || id.toUpperCase().includes(busca));
  const sel = porCliente.has(q.get("cliente")) ? q.get("cliente") : clientes[0];
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/venta-cruzada${n.toString() ? `?${n}` : ""}`; };
  let ficha = null;
  if (sel && puede("cartera.ver") && seccion === "propuestas") ficha = await api("GET", `/api/cierres/${S.cierre}/clientes/${encodeURIComponent(sel)}`).catch(() => null);
  if (!vigente(turno)) return;
  const items = sel ? porCliente.get(sel) || [] : [];
  const yaTiene = ficha?.productos?.length ? ficha.productos.map(p => p.producto).join(", ") : null;
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Hasta tres productos que el cliente aún no tiene y que podrías proponerle, con el motivo de cada uno. Tú decides si tiene sentido.",
    contexto: [ctxDatos(s.corte, "Sugerencias con datos hasta"), { etiqueta: "Compatibilidad por revisar", valor: plural(d.compatibilidad_pendiente, "sugerencia", "sugerencias") }] })}
  ${avisoPrueba("No crea seguimientos ni envía ofertas.")}
  ${pestanas([["propuestas", "Sugerencias por cliente", enlace({ seccion: "" })], ["evaluacion", "Evaluación comercial de la muestra", enlace({ seccion: "evaluacion" })]], seccion, "Secciones de productos sugeridos")}
  <div id="msg-vc" role="status" tabindex="-1"></div>
  ${seccion === "evaluacion" ? `<section class="panel"><h2>Evaluación comercial de la muestra</h2>${revisionHtml(r)}</section>` : `
  ${hallazgo({
    que: `<strong>${plural(porCliente.size, "cliente tiene", "clientes tienen")} sugerencias</strong> (${plural(d.items.length, "producto sugerido", "productos sugeridos")} en total).`,
    porque: `${plural(d.compatibilidad_pendiente, "sugerencia tiene", "sugerencias tienen")} la compatibilidad por revisar: no hay reglas de la empresa para confirmarla. Revísala antes de proponer el producto.`,
    accion: "",
  })}
  <div class="grid-maestro">
    <section class="panel" id="lista-clientes-vc" aria-labelledby="t-clientes-vc"><h2 id="t-clientes-vc">Elige un cliente</h2>
      <form class="filtros" id="f-vc" role="search"><label>Buscar cliente <input name="buscar" value="${esc(q.get("buscar") || "")}" autocomplete="off"></label>
        <label>Compatibilidad <select name="compatibilidad"><option value="">Todas</option><option value="pendiente_revision"${filtro === "pendiente_revision" ? " selected" : ""}>Por revisar</option><option value="confirmada"${filtro === "confirmada" ? " selected" : ""}>Confirmada</option></select></label>
        <button>Buscar</button>${busca || filtro ? '<a class="boton-sec" href="#/venta-cruzada">Quitar filtros</a>' : ""}</form>
      <p class="muted">${plural(clientes.length, "cliente", "clientes")} en la lista.</p>
      ${clientes.length ? `<ul class="lista-simple" style="max-height:28rem;overflow:auto">${clientes.map(id => `<li><a class="${id === sel ? "boton" : "boton-sec"}" style="width:100%;justify-content:space-between" href="${esc(enlace({ cliente: id }))}" ${id === sel ? 'aria-current="true"' : ""}>${esc(id)} <span>${plural(porCliente.get(id).length, "producto", "productos")}</span></a></li>`).join("")}</ul>` : vacio("Ningún cliente coincide.")}
    </section>
    <section class="panel" aria-labelledby="t-sel-vc">${sel ? `<h2 id="t-sel-vc">Cliente ${esc(sel)}</h2>
      <dl class="comparacion"><div><dt>Ya tiene</dt><dd>${yaTiene ? esc(yaTiene) : puede("cartera.ver") ? "Sin compras registradas" : "Dato no disponible para tu perfil"}</dd></div><div><dt>Se sugiere</dt><dd>${esc(items.map(i => i.producto_nombre).join(", "))}</dd></div></dl>
      <p class="muted">El número indica el orden de la sugerencia, no una probabilidad. ${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(sel)}">Ver la ficha del cliente</a>` : ""}</p>
      ${cajaEnfoque(sel)}
      ${items.map(tarjeta).join("")}` : vacio("Elige un cliente de la lista para ver sus sugerencias.")}
    </section>
  </div>
  <section class="panel"><h2>Clientes sin sugerencias</h2><p>${plural(c.con_recomendaciones || 0, "cliente tiene", "clientes tienen")} sugerencias; ${num(c.sin_candidatos || 0)} sin candidatos, ${num(c.sin_historial || 0)} sin historial, ${num(c.no_elegible || 0)} no elegibles. No se inventan productos para completar tres.</p>
    ${d.sin_recomendacion.length ? `<ul>${d.sin_recomendacion.map(x => `<li>${esc(x.cliente_id)}: ${esc(COBERTURA[x.estado] || x.estado)}. ${esc(x.motivo || "")}</li>`).join("")}</ul>` : ""}</section>`}
  <details class="panel"><summary>Cómo se obtuvieron las sugerencias</summary><p>${esc(s.estado_experimento)}. ${esc(d.nota)} ${esc(d.separacion)} Seguimientos automáticos: ${d.tareas_automaticas ? "activados" : "desactivados"}.</p>
    ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación en prueba (datos originales)")}</details>`;
  document.getElementById("f-vc")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    ir(enlace({ buscar: fd.get("buscar").trim(), compatibilidad: fd.get("compatibilidad"), cliente: "" }));
  });
  activarVentaCruzada($vista, vistaVentaCruzada);
  if (sel && seccion === "propuestas") pintarVentaCruzadaIA($vista, sel, turno);
}
