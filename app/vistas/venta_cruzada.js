// V09 Productos que podrías ofrecer (M4): sugerencias para revisión de Ventas. No son ofertas ni mensajes, no
// cambian la cartera y no muestran porcentajes: el modelo publica un orden sin calibrar.
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaLarga, ir, nuevoTurno, num, plural, puede, ruta, vigente } from "../nucleo.js";
import { avisoPrueba, barras, ctxDatos, detalleTecnico, encabezado, enPrueba, hallazgo, pestanas, vacio } from "../ui.js";
import { estadoIA, pedirNarrativa, pieIA } from "../ia_textos.js";

const COMPAT = { confirmada: "Compatible", pendiente_revision: "Confirma que sea compatible" };
const COMPAT_AYUDA = { confirmada: "La empresa confirmó que funciona con lo que el cliente ya tiene.", pendiente_revision: "Aún no hay una regla de la empresa que lo confirme: revísalo antes de proponerlo." };
const EPISODIO = { en_revision: "En revisión", aceptada: "Aceptada", aplazada: "Aplazada", descartada: "Descartada (no se reabre)", cerrada_compra: "Cerrada: compra posterior observada" };
const ESTADOS_REV = { pertinente: "Pertinente", ya_cubierto: "Ya cubierto", incompatible: "Incompatible", sin_necesidad: "Sin necesidad identificada", informacion_insuficiente: "Información insuficiente" };
const COBERTURA = { sin_candidatos: "Sin candidatos", sin_historial: "Sin historial", no_elegible: "No elegible" };
const ACCIONES = [["aceptar", "Aceptar", "La propondré"], ["revisar", "En revisión", "Lo estoy evaluando"], ["aplazar", "Aplazar", "Ahora no es el momento"], ["descartar", "Descartar", "No tiene sentido"]];
// Cómo se eligió, en palabras de todos los días (el texto técnico queda en el detalle).
const ORIGEN_LLANO = {
  coocurrencia: "Clientes con compras parecidas a las suyas también lo tienen",
  popularidad: "Es de lo más comprado por clientes como este",
  popularidad_sin_soporte: "Es de lo más comprado por clientes como este",
  modelo: "El modelo lo priorizó según su historial de compras",
};
const ORDINAL = ["Primera", "Segunda", "Tercera"];
const TITULO = "Productos que podrías ofrecer";

const idSeguro = i => `${i.cliente_id}-${i.producto_id}`.replace(/[^\w-]/g, "");

function decisionHtml(i) {
  const cerrado = i.episodio && ["descartada", "cerrada_compra"].includes(i.episodio.estado);
  const estado = i.episodio
    ? `<p class="vc-decidido"><span class="sello ${i.episodio.estado === "aceptada" ? "sello-ok" : ""}">${esc(EPISODIO[i.episodio.estado] || i.episodio.estado)}</span>${i.episodio.motivo ? ` <span class="muted">${esc(i.episodio.motivo)}</span>` : ""}</p>`
    : "";
  if (!puede("venta_cruzada.decidir")) return estado || '<p class="muted">Tu perfil puede consultar, no decidir.</p>';
  if (cerrado) return estado;
  const id = idSeguro(i);
  const abrir = i.episodio ? '<details class="vc-cambiar"><summary>Cambiar mi decisión</summary>' : "", cerrar = i.episodio ? "</details>" : "";
  return `${estado}${abrir}<form class="vc-decision" data-cliente="${esc(i.cliente_id)}" data-producto="${esc(i.producto_id)}" aria-label="Decisión sobre ${esc(i.producto_nombre)} para ${esc(i.cliente_id)}" novalidate>
    <fieldset class="vc-opciones"><legend>${i.episodio ? "Nueva decisión" : "¿Qué harás con esta sugerencia?"}</legend>
      ${ACCIONES.map(([k, t, ayuda]) => `<label class="vc-opcion vc-${k}"><input type="radio" name="accion" value="${k}"><span><strong>${t}</strong><small>${ayuda}</small></span></label>`).join("")}
      <span class="error-campo" data-error-accion></span></fieldset>
    <div class="vc-motivo"><label for="mot-${id}">Motivo <span class="ayuda">Obligatorio. Por ejemplo: ya lo usa con otro proveedor.</span></label>
      <div class="vc-motivo-fila"><input name="motivo" id="mot-${id}" required maxlength="300" aria-describedby="err-mot-${id}"><button>Guardar</button></div>
      <span class="error-campo" id="err-mot-${id}"></span></div>
    <p class="muted vc-aclaracion">Guardar registra tu decisión: no envía nada al cliente y no cuenta como venta.</p></form>${cerrar}`;
}

function tarjeta(i) {
  const compat = i.estado_compatibilidad === "confirmada";
  const orden = ORDINAL[i.posicion - 1] ? `${ORDINAL[i.posicion - 1]} opción` : `Opción ${num(i.posicion)}`;
  return `<article class="tarjeta-caso vc-tarjeta${i.episodio ? " vc-con-decision" : ""}">
    <header class="vc-cabeza"><span class="vc-rango" aria-hidden="true">${num(i.posicion)}</span>
      <div><p class="vc-orden">${orden}</p><h3>${esc(i.producto_nombre)}</h3></div>
      <span class="sello ${compat ? "sello-ok" : "sello-revisar"}" title="${esc(COMPAT_AYUDA[i.estado_compatibilidad] || "")}">${compat ? "✓" : "!"} ${esc(COMPAT[i.estado_compatibilidad] || i.estado_compatibilidad)}</span></header>
    <div class="ia-producto" data-ia-cliente="${esc(i.cliente_id)}" data-ia-producto="${esc(i.producto_id)}"></div>
    <div class="vc-porque"><p class="etiqueta-datos">Por qué se sugiere</p>
      <ul>${(i.motivos || []).map(m => `<li>${esc(m)}</li>`).join("")}<li>${esc(ORIGEN_LLANO[i.origen_recomendacion] || i.origen_texto)}.</li></ul>
      ${i.soporte != null ? `<p class="vc-respaldo"><strong>${num(i.soporte)}</strong> ${i.soporte === 1 ? "cliente parecido ya lo compró" : "clientes parecidos ya lo compraron"}</p>` : ""}
      ${compat ? "" : `<p class="vc-alerta">${esc(COMPAT_AYUDA.pendiente_revision)}</p>`}</div>
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
    ${s.items.length ? cajaEnfoque(s.items[0].cliente_id) + `<div class="vc-tarjetas">${s.items.map(tarjeta).join("")}</div>` : vacio(vacioTxt)}
    <p class="muted">Datos hasta el ${esc(fechaLarga(s.corte))}. Los productos que ya tiene se atienden como recompra o renovación en la cartera.</p></section>`;
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
    const errAcc = fm.querySelector("[data-error-accion]");
    if (errAcc) {
      const marcada = fm.querySelector("[name=accion]:checked");
      errAcc.textContent = marcada ? "" : "Elige qué harás con la sugerencia.";
      if (!marcada) { fm.querySelector("[name=accion]").focus(); return; }
    }
    const motivo = fm.querySelector("[name=motivo]"), err = motivo.closest("label, .vc-motivo")?.querySelector(".error-campo") || fm.querySelector(".error-campo:not([data-error-accion])");
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

/** Resumen de un cliente para la lista: cuántas sugerencias, cuántas por revisar y cuántas ya decididas. */
function resumenCliente(items) {
  const revisar = items.filter(i => i.estado_compatibilidad !== "confirmada").length;
  const decididas = items.filter(i => i.episodio).length;
  return { n: items.length, revisar, decididas, completo: decididas === items.length };
}

function itemLista(id, items, sel, href) {
  const r = resumenCliente(items);
  const estado = r.completo ? '<span class="vc-li-estado ok">✓ Revisado</span>'
    : r.decididas ? `<span class="vc-li-estado">${num(r.decididas)} de ${num(r.n)} decididas</span>`
    : r.revisar ? `<span class="vc-li-estado aviso">${plural(r.revisar, "por confirmar", "por confirmar")}</span>` : '<span class="vc-li-estado ok">Compatibles</span>';
  return `<li><a class="vc-li${id === sel ? " activo" : ""}" href="${esc(href)}" ${id === sel ? 'aria-current="true"' : ""}>
    <span class="vc-li-id">${esc(id)}</span><span class="vc-li-n">${plural(r.n, "producto", "productos")}</span>${estado}</a></li>`;
}

export async function vistaVentaCruzada() {
  const { q } = ruta();
  const filtro = q.get("compatibilidad") || "", seccion = q.get("seccion") === "evaluacion" ? "evaluacion" : "propuestas";
  const busca = (q.get("buscar") || "").toUpperCase(), producto = q.get("producto") || "";
  const turno = nuevoTurno();
  if (!$vista.querySelector("#lista-clientes-vc")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando sugerencias…")}`;
  let d, r;
  try {
    [d, r] = await Promise.all([api("GET", `/api/venta-cruzada${filtro ? `?compatibilidad=${encodeURIComponent(filtro)}` : ""}`), api("GET", "/api/venta-cruzada/revision").catch(() => null)]);
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Sugerencias no disponibles: no hay una publicación de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  const porCliente = new Map(), porProducto = new Map();
  for (const i of d.items) {
    if (!porCliente.has(i.cliente_id)) porCliente.set(i.cliente_id, []);
    porCliente.get(i.cliente_id).push(i);
    const p = porProducto.get(i.producto_id) || { nombre: i.producto_nombre, clientes: 0, compatibles: 0 };
    p.clientes++; if (i.estado_compatibilidad === "confirmada") p.compatibles++;
    porProducto.set(i.producto_id, p);
  }
  const clientes = [...porCliente.keys()].filter(id => (!busca || id.toUpperCase().includes(busca)) && (!producto || porCliente.get(id).some(i => i.producto_id === producto)));
  const sel = porCliente.has(q.get("cliente")) && clientes.includes(q.get("cliente")) ? q.get("cliente") : clientes[0];
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/venta-cruzada${n.toString() ? `?${n}` : ""}`; };
  let ficha = null;
  if (sel && puede("cartera.ver") && seccion === "propuestas") ficha = await api("GET", `/api/cierres/${S.cierre}/clientes/${encodeURIComponent(sel)}`).catch(() => null);
  if (!vigente(turno)) return;
  const items = sel ? porCliente.get(sel) || [] : [];
  const yaTiene = ficha?.productos?.map(p => p.producto) || [];
  const decididas = d.items.filter(i => i.episodio).length;
  const ranking = [...porProducto.entries()].sort((a, b) => b[1].clientes - a[1].clientes || a[1].nombre.localeCompare(b[1].nombre));
  const prodNombre = producto && porProducto.get(producto)?.nombre;
  const filtrosActivos = busca || filtro || producto;

  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Productos que el cliente aún no tiene y que podrías proponerle, con el motivo de cada uno. Tú decides si tiene sentido.",
    contexto: [ctxDatos(s.corte, "Sugerencias con datos hasta")] })}
  ${avisoPrueba("No crea seguimientos ni envía ofertas.")}
  ${pestanas([["propuestas", "Sugerencias por cliente", enlace({ seccion: "" })], ["evaluacion", "Evaluación comercial de la muestra", enlace({ seccion: "evaluacion" })]], seccion, "Secciones de productos sugeridos")}
  <div id="msg-vc" role="status" tabindex="-1"></div>
  ${seccion === "evaluacion" ? `<section class="panel"><h2>Evaluación comercial de la muestra</h2>${revisionHtml(r)}</section>` : `
  <div class="vc-cifras" role="list">
    <div role="listitem"><span class="vc-cifra">${num(porCliente.size)}</span><span>clientes con sugerencias</span></div>
    <div role="listitem"><span class="vc-cifra">${num(d.items.length)}</span><span>productos sugeridos en total</span></div>
    <div role="listitem"><span class="vc-cifra aviso">${num(d.compatibilidad_pendiente)}</span><span>por confirmar compatibilidad</span></div>
    <div role="listitem"><span class="vc-cifra ok">${num(decididas)}</span><span>con decisión registrada</span></div>
  </div>
  ${hallazgo({
    que: `<strong>${esc(ranking[0]?.[1].nombre || "—")}</strong> es el producto que más se sugiere: aparece en ${plural(ranking[0]?.[1].clientes || 0, "cliente", "clientes")}.`,
    porque: `Cada sugerencia es un producto que el cliente todavía no tiene. ${plural(d.compatibilidad_pendiente, "necesita", "necesitan")} que confirmes la compatibilidad antes de proponerlo${d.compatibilidad_pendiente === 1 ? "" : "s"}.`,
    accion: sel ? `<button class="boton" type="button" data-ir-detalle>Revisar ${esc(sel)}</button>` : "",
  })}
  <section class="panel"><h2>Qué productos se sugieren más</h2>
    <p class="muted">Número de clientes a los que se les sugiere cada producto. Pulsa uno para ver solo esos clientes.</p>
    ${barras(ranking.map(([id, p]) => ({ etiqueta: p.nombre, nota: p.compatibles ? `${num(p.compatibles)} ${p.compatibles === 1 ? "compatible confirmada" : "compatibles confirmadas"}` : "compatibilidad por confirmar", valor: p.clientes, texto: plural(p.clientes, "cliente", "clientes"), href: enlace({ producto: producto === id ? "" : id, cliente: "" }), activo: producto === id })), { etiquetaAria: "Productos más sugeridos" })}
  </section>
  <div class="grid-maestro">
    <section class="panel" id="lista-clientes-vc" aria-labelledby="t-clientes-vc"><h2 id="t-clientes-vc">Elige un cliente</h2>
      <form class="vc-filtros" id="f-vc" role="search">
        <label>Buscar cliente <input name="buscar" value="${esc(q.get("buscar") || "")}" autocomplete="off" placeholder="Ej.: CLI001"></label>
        <label>Compatibilidad <select name="compatibilidad"><option value="">Todas</option><option value="pendiente_revision"${filtro === "pendiente_revision" ? " selected" : ""}>Por confirmar</option><option value="confirmada"${filtro === "confirmada" ? " selected" : ""}>Compatibles</option></select></label>
        <button class="sec">Filtrar</button></form>
      <p class="muted vc-cuantos">${plural(clientes.length, "cliente", "clientes")}${prodNombre ? ` con «${esc(prodNombre)}»` : ""}${filtrosActivos ? ` · <a href="#/venta-cruzada">Quitar filtros</a>` : ""}</p>
      ${clientes.length ? `<ul class="vc-lista">${clientes.map(id => itemLista(id, porCliente.get(id), sel, enlace({ cliente: id }))).join("")}</ul>` : vacio("Ningún cliente coincide.")}
    </section>
    <section class="panel vc-detalle" id="vc-detalle" aria-labelledby="t-sel-vc" tabindex="-1">${sel ? `
      <div class="vc-detalle-cabeza"><h2 id="t-sel-vc">${esc(sel)}</h2>${puede("cartera.ver") ? `<a class="boton-sec" href="#/clientes/${encodeURIComponent(sel)}">Ver ficha del cliente</a>` : ""}</div>
      <div class="vc-resumen">
        <div><p class="etiqueta-datos">Ya tiene</p>${yaTiene.length ? `<p class="vc-chips">${yaTiene.map(p => `<span class="chip">${esc(p)}</span>`).join("")}</p>` : `<p class="muted">${puede("cartera.ver") ? "Sin compras registradas" : "Dato no disponible para tu perfil"}</p>`}</div>
        <div><p class="etiqueta-datos">Podrías ofrecerle</p><p class="vc-chips">${items.map(i => `<span class="chip chip-sugerido">${num(i.posicion)}. ${esc(i.producto_nombre)}</span>`).join("")}</p></div>
      </div>
      <p class="muted">Las opciones van en orden de prioridad: la primera es la que más encaja. El orden no es una probabilidad de venta.</p>
      ${cajaEnfoque(sel)}
      <div class="vc-tarjetas">${items.map(tarjeta).join("")}</div>` : vacio("Elige un cliente de la lista para ver sus sugerencias.")}
    </section>
  </div>
  <section class="panel"><h2>Clientes sin sugerencias</h2><p>${plural(c.con_recomendaciones || 0, "cliente tiene", "clientes tienen")} sugerencias; ${num(c.sin_candidatos || 0)} sin candidatos, ${num(c.sin_historial || 0)} sin historial, ${num(c.no_elegible || 0)} no elegibles. No se inventan productos para completar tres.</p>
    ${d.sin_recomendacion.length ? `<ul>${d.sin_recomendacion.map(x => `<li>${esc(x.cliente_id)}: ${esc(COBERTURA[x.estado] || x.estado)}. ${esc(x.motivo || "")}</li>`).join("")}</ul>` : ""}</section>`}
  <details class="panel"><summary>Cómo se obtuvieron las sugerencias</summary><p>${esc(s.estado_experimento)}. ${esc(d.nota)} ${esc(d.separacion)} Seguimientos automáticos: ${d.tareas_automaticas ? "activados" : "desactivados"}.</p>
    ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación (datos originales)")}</details>`;
  document.getElementById("f-vc")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    ir(enlace({ buscar: fd.get("buscar").trim(), compatibilidad: fd.get("compatibilidad"), cliente: "" }));
  });
  $vista.querySelector("[data-ir-detalle]")?.addEventListener("click", () => { const el = document.getElementById("vc-detalle"); el.scrollIntoView({ behavior: "smooth", block: "start" }); el.focus({ preventScroll: true }); });
  activarVentaCruzada($vista, vistaVentaCruzada);
  if (sel && seccion === "propuestas") pintarVentaCruzadaIA($vista, sel, turno);
}
