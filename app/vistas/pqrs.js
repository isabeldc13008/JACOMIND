// Solicitudes: V17 bandeja de Atención, V18 resolver una solicitud, V20 mis solicitudes y nueva solicitud (portal),
// V21 detalle de una solicitud propia. El portal solo ve su empresa y las respuestas aprobadas.
import { $vista, S, api, clave, errorHtml, esc, fechaHora, fechaLarga, ir, num, pct, plural, puede, ruta } from "../nucleo.js";
import { barras, confirmar, cronologia, detalleTecnico, encabezado, filtrosActivos, hallazgo, indicadores, tablaHtml, vacio, verDatos } from "../ui.js";

const ESTADO_EMPRESA = { recibido: "Recibida, pendiente de revisión", en_gestion: "En revisión por nuestro equipo", respondido: "Respondida", cerrado: "Cerrada" };
const ESTADO_INTERNO = { recibido: "Recibida", en_gestion: "En gestión", respondido: "Respondida", cerrado: "Cerrada" };
const CATEGORIAS = { peticion: "Petición", queja: "Queja", reclamo: "Reclamo", sugerencia: "Sugerencia", sin_categoria: "Sin categoría" };
const ACCION_PUBLICA = {
  radicar: "Recibimos tu solicitud", asignar: "Nuestro equipo empezó a revisarla", iniciar_gestion: "Nuestro equipo empezó a revisarla",
  responder: "Publicamos una respuesta", publicar_respuesta: "Publicamos una respuesta", cerrar: "Cerramos la solicitud", reabrir: "Reabrimos la solicitud",
};
const PQRS_EXPLICADO = "Peticiones, quejas, reclamos y sugerencias (PQRS)";

export async function vistaPqrs(rad) {
  if (rad) return S.usuario.externo ? detalleEmpresa(rad) : puede("pqrs.gestionar") ? gestionCaso(rad) : ir("#/pqrs");
  return S.usuario.externo ? listaEmpresa() : bandejaInterna();
}

// ---------------------------------------------------------------- V20 · portal: mis solicitudes y nueva solicitud
async function listaEmpresa() {
  const { q } = ruta();
  const busca = q.get("q") || "", crear = q.get("crear") === "1", bid = q.get("beneficio");
  if (crear) return nuevaSolicitud(bid);
  const lista = await api("GET", `/api/pqrs?${new URLSearchParams({ q: busca })}`).catch(e => e);
  const titulo = "Mis solicitudes";
  if (lista instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(lista, { reintentar: true })}`; return; }
  const abiertas = lista.filter(c => ["recibido", "en_gestion"].includes(c.estado)), cerradas = lista.filter(c => !["recibido", "en_gestion"].includes(c.estado));
  const tabla = (l, t) => l.length ? `<h3>${t} (${num(l.length)})</h3>${tablaHtml({ cabeceras: ["Asunto", "Estado", "Número de seguimiento", "Creada"],
    filas: l.map(c => [`<a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a>`, esc(ESTADO_EMPRESA[c.estado] || c.estado), `<code>${esc(c.radicado)}</code>`, esc(fechaLarga(c.creado_en))]) })}` : "";
  $vista.innerHTML = `${encabezado({ titulo, descripcion: `${PQRS_EXPLICADO} de tu empresa. Aquí ves las de toda tu empresa, no solo las tuyas.`,
    acciones: puede("pqrs.crear") ? '<a class="boton" href="#/pqrs?crear=1">Nueva solicitud</a>' : "" })}
  <section class="panel"><h2>Buscar una solicitud</h2><form id="buscar" class="filtros" role="search"><label>Asunto o número de seguimiento <span class="ayuda">Por ejemplo: factura, o el número que recibiste al crearla.</span><input name="q" value="${esc(busca)}"></label>
    <div class="fila"><button>Buscar</button>${busca ? '<a class="boton-sec" href="#/pqrs">Limpiar búsqueda</a>' : ""}</div></form>
    ${busca ? `<p role="status">${plural(lista.length, "solicitud coincide", "solicitudes coinciden")} con «${esc(busca)}».</p>` : ""}</section>
  ${lista.length ? `${tabla(abiertas, "En curso")}${tabla(cerradas, "Respondidas o cerradas")}` : busca ? vacio("Ninguna solicitud coincide con la búsqueda.", "Revisa el número o prueba con otra palabra del asunto.", '<a class="boton-sec" href="#/pqrs">Ver todas</a>')
    : vacio("Tu empresa aún no tiene solicitudes.", "Cuando necesites algo, crea una solicitud y recibirás un número para seguirla.", puede("pqrs.crear") ? '<a class="boton" href="#/pqrs?crear=1">Nueva solicitud</a>' : "")}`;
  document.getElementById("buscar").addEventListener("submit", e => { e.preventDefault(); const v = new FormData(e.target).get("q").trim(); ir(v ? `#/pqrs?q=${encodeURIComponent(v)}` : "#/pqrs"); });
}

async function nuevaSolicitud(bid) {
  const volver = { href: bid ? "#/beneficios" : "#/pqrs", texto: bid ? "Volver a los beneficios" : "Volver a mis solicitudes" };
  if (!puede("pqrs.crear")) { $vista.innerHTML = `${encabezado({ titulo: "Nueva solicitud", volver })}${vacio("Tu perfil no puede crear solicitudes.")}`; return; }
  const ben = bid ? await api("GET", `/api/portal/beneficios/${encodeURIComponent(bid)}`).catch(() => null) : null;
  const asunto = ben ? `Solicitud del beneficio «${ben.titulo}»` : "";
  const descripcion = ben ? `Solicitamos el beneficio «${ben.titulo}» (${ben.id}, versión ${ben.version}), publicado con la fuente ${ben.fuente}. ` : "";
  $vista.innerHTML = `${encabezado({ titulo: "Nueva solicitud", volver, descripcion: "Cuéntanos qué necesitas. Al enviarla recibirás un número de seguimiento." })}
  ${bid && !ben ? '<p class="aviso-cifras" role="note">No encontramos ese beneficio o ya no está disponible. Puedes escribir la solicitud igualmente.</p>' : ""}
  ${ben ? `<section class="panel"><h2>Beneficio que solicitas</h2><p><strong>${esc(ben.titulo)}</strong></p><p>${esc(ben.descripcion || "")}</p><p class="muted">Condición: ${esc(ben.condicion || "Sin condiciones adicionales.")} · Puedes solicitarlo hasta: ${ben.vigencia_hasta ? esc(fechaLarga(ben.vigencia_hasta)) : "sin fecha de fin anunciada"}. Solicitarlo no significa que quede aprobado: Atención lo revisa.</p></section>` : ""}
  <section class="panel"><form id="nueva" class="campos" novalidate>
    <div id="resumen-errores" tabindex="-1"></div>
    <label for="asunto">Asunto <span class="ayuda">Una frase corta. Por ejemplo: doble cobro en la factura de octubre.</span><input id="asunto" name="asunto" required maxlength="200" value="${esc(asunto)}" aria-describedby="err-asunto"><span class="error-campo" id="err-asunto"></span></label>
    <label for="descripcion">Qué pasó y qué necesitas <span class="ayuda">Incluye fechas y números de factura si los tienes. No incluyas contraseñas ni datos de tarjetas.</span><textarea id="descripcion" name="descripcion" required maxlength="5000" aria-describedby="err-descripcion">${esc(descripcion)}</textarea><span class="error-campo" id="err-descripcion"></span></label>
    <div class="fila"><button>Enviar la solicitud</button><a class="boton-sec" href="${esc(volver.href)}">Cancelar</a></div></form>
    <div id="msg" aria-live="polite"></div>
    <p class="muted">Por ahora no se pueden adjuntar archivos desde aquí.</p></section>`;
  const form = document.getElementById("nueva");
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const errores = [];
    for (const [id, txt] of [["asunto", "Escribe el asunto."], ["descripcion", "Cuéntanos qué pasó."]]) {
      const el = document.getElementById(id), mal = !el.value.trim();
      el.setAttribute("aria-invalid", String(mal)); document.getElementById(`err-${id}`).textContent = mal ? txt : "";
      if (mal) errores.push([id, txt]);
    }
    if (errores.length) {
      document.getElementById("resumen-errores").innerHTML = `<div class="estado error" role="alert"><p><strong>Falta información:</strong></p><ul>${errores.map(([id, t]) => `<li>${esc(t)}</li>`).join("")}</ul></div>`;
      return document.getElementById(errores[0][0]).focus();
    }
    document.getElementById("resumen-errores").innerHTML = "";
    const btn = form.querySelector("button"); btn.disabled = true; btn.textContent = "Enviando…";
    const fd = new FormData(form);
    form.dataset.clave ||= clave();   // reintentos del mismo formulario → mismo número de seguimiento, sin duplicar
    try {
      const r = await api("POST", "/api/pqrs", { asunto: fd.get("asunto").trim(), descripcion: fd.get("descripcion").trim(), __clave: form.dataset.clave });
      ir(`#/pqrs/${r.radicado}?nuevo=1`);
    } catch (err) {
      const incierto = err instanceof TypeError || err.status === undefined || err.status >= 500;
      document.getElementById("msg").innerHTML = `${errorHtml(err)}${incierto ? '<p class="estado">No sabemos si la solicitud llegó. Pulsa de nuevo «Enviar la solicitud»: si ya llegó, no se creará otra y verás su número.</p>' : ""}`;
      btn.disabled = false; btn.textContent = "Enviar la solicitud";
    }
  });
}

// ---------------------------------------------------------------- V21 · portal: detalle de una solicitud
async function detalleEmpresa(rad) {
  const volver = { href: "#/pqrs", texto: "Volver a mis solicitudes" };
  let c;
  try { c = await api("GET", `/api/pqrs/${encodeURIComponent(rad)}`); }
  catch (e) { $vista.innerHTML = `${encabezado({ titulo: "Solicitud", volver })}${e.status === 404 || e.status === 403 ? vacio("No encontramos esa solicitud en tu empresa.", "Revisa el número de seguimiento.") : errorHtml(e, { reintentar: true })}`; return; }
  const nuevo = ruta().q.get("nuevo") === "1";
  const eventos = c.historial.filter(h => ACCION_PUBLICA[h.accion]).map(h => ({ fecha: h.ts, etiquetaFecha: fechaHora(h.ts), tipo: h.accion === "reabrir" ? "vencimiento" : h.accion.includes("respon") ? "resultado" : "evento", titulo: ACCION_PUBLICA[h.accion] }));
  $vista.innerHTML = `${encabezado({ titulo: c.asunto, volver, descripcion: `Estado: <strong>${esc(ESTADO_EMPRESA[c.estado] || c.estado)}</strong>`,
    contexto: [{ etiqueta: "Número de seguimiento", valor: `<code>${esc(c.radicado)}</code>` }, { etiqueta: "Última actualización", valor: esc(fechaHora(c.actualizado_en || c.creado_en)) }] })}
  ${nuevo ? `<div class="estado ok" role="status" tabindex="-1" id="confirmacion"><p><strong>Recibimos tu solicitud.</strong></p><p>Tu número de seguimiento es <strong><code>${esc(c.radicado)}</code></strong>. Guárdalo: con él puedes volver a consultarla aquí, en «Mis solicitudes».</p></div>` : ""}
  <section class="panel"><h2>Respuesta</h2>${c.respuesta_publicada ? `<div class="burbuja yo">${esc(c.respuesta_publicada)}</div><p class="muted">Publicada el ${esc(fechaHora(c.respondido_en))}.</p>` : `<p>${c.estado === "recibido" ? "Recibimos tu solicitud; todavía no hay respuesta." : "Nuestro equipo la está revisando; todavía no hay respuesta."} Aquí la verás cuando se publique.</p>`}</section>
  <section class="panel"><h2>Lo que nos contaste</h2><div class="burbuja">${esc(c.descripcion)}</div></section>
  <section class="panel"><h2>Qué ha pasado con tu solicitud</h2>${cronologia(eventos, { vacio: "Sin cambios públicos todavía." })}</section>
  <p>${puede("beneficios.portal") ? '<a href="#/beneficios">Ver los beneficios de tu empresa</a>' : ""}</p>`;
  document.getElementById("confirmacion")?.focus();
}

// ---------------------------------------------------------------- V17 · bandeja e indicadores
function bloqueIndicadores(ind, enlaces) {
  const cats = Object.entries(ind.abiertos_por_categoria || {}).sort((a, b) => b[1] - a[1]);
  const prim = ind.horas_primera_gestion_mediana_total, resp = ind.horas_resolucion_mediana_total;
  const nPrim = Object.values(ind.casos_medidos_primera_gestion || {}).reduce((s, x) => s + x, 0);
  const nResp = Object.values(ind.casos_medidos_resolucion || {}).reduce((s, x) => s + x, 0);
  const todas = [...new Set([...Object.keys(ind.abiertos_por_categoria || {}), ...Object.keys(ind.horas_primera_gestion_mediana || {}), ...Object.keys(ind.horas_resolucion_mediana || {})])];
  const horas = (h, n) => h == null ? "—" : `${num(h)} h (${plural(n || 0, "caso", "casos")})`;
  return `<div class="grid2">
    <section class="panel"><h2>Pendientes por categoría</h2>
      ${barras(cats.map(([k, v]) => ({ etiqueta: CATEGORIAS[k] || k, valor: v, texto: plural(v, "caso", "casos"), href: enlaces ? `#/pqrs?categoria=${encodeURIComponent(k)}` : null })), { etiquetaAria: "Casos pendientes por categoría", vacio: "No hay casos pendientes." })}
      <p class="muted">Pendiente = recibido o en gestión. Total: ${plural(ind.pendientes ?? 0, "caso", "casos")}. Estado actual del registro, no del cierre.</p></section>
    <section class="panel"><h2>Tiempos habituales</h2>
      <p><strong>Hasta la primera atención:</strong> ${prim == null ? "Aún no hay casos atendidos para calcularlo." : `${num(prim)} horas de mediana (${plural(nPrim, "caso medido", "casos medidos")}).`}</p>
      <p><strong>Hasta la respuesta:</strong> ${resp == null ? "Aún no hay respuestas para calcularlo." : `${num(resp)} horas de mediana (${plural(nResp, "caso medido", "casos medidos")}).`}</p>
      ${verDatos({ tabla: { cabeceras: ["Categoría", "Pendientes", "Mediana hasta primera atención", "Mediana hasta respuesta"], numericas: new Set([1]),
        filas: todas.map(k => [esc(CATEGORIAS[k] || k), num(ind.abiertos_por_categoria?.[k] || 0), esc(horas(ind.horas_primera_gestion_mediana?.[k], ind.casos_medidos_primera_gestion?.[k])), esc(horas(ind.horas_resolucion_mediana?.[k], ind.casos_medidos_resolucion?.[k]))]) },
        fuente: "Registro de solicitudes (estado actual)", regla: `${esc(ind.definicion_mediana || "")} ${esc(ind.nota)}` })}</section>
  </div>`;
}

const siguientePaso = c => c.estado === "recibido" && c.requiere_revision ? "Clasificar" : c.estado === "recibido" ? "Iniciar la gestión" : c.estado === "en_gestion" ? "Preparar y publicar la respuesta" : c.estado === "respondido" ? "Cerrar o reabrir" : "—";

async function bandejaInterna() {
  const { q } = ruta();
  const gestiona = puede("pqrs.gestionar");
  const titulo = gestiona ? "Solicitudes de clientes" : "Indicadores de solicitudes";
  const [lista, ind, bandeja] = await Promise.all([
    api("GET", `/api/pqrs?${new URLSearchParams({ estado: q.get("estado") || "", revision: q.get("revision") || "", q: q.get("q") || "" })}`),
    puede("pqrs.indicadores") ? api("GET", "/api/pqrs-indicadores").catch(() => null) : null,
    gestiona ? api("GET", "/api/atencion/bandeja").catch(() => null) : null]).catch(e => [e]);
  if (lista instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(lista, { reintentar: true })}`; return; }
  const cat = q.get("categoria");
  const filas = cat ? lista.filter(c => (c.categoria || "sin_categoria") === cat && ["recibido", "en_gestion"].includes(c.estado)) : lista;
  const enlace = c => gestiona ? `<a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a>` : esc(c.asunto);
  const activos = [q.get("estado") && { texto: `Estado: ${ESTADO_INTERNO[q.get("estado")] || q.get("estado")}`, quitar: "#/pqrs" }, q.get("revision") && { texto: "Requieren clasificación", quitar: "#/pqrs" },
    cat && { texto: `Pendientes de ${CATEGORIAS[cat] || cat}`, quitar: "#/pqrs" }, q.get("q") && { texto: `Búsqueda: «${q.get("q")}»`, quitar: "#/pqrs" }].filter(Boolean);
  const pendientes = lista.filter(c => ["recibido", "en_gestion"].includes(c.estado)).length;
  $vista.innerHTML = `${encabezado({ titulo, descripcion: `${PQRS_EXPLICADO} de las empresas clientes.${gestiona ? " Clasifica, prepara la respuesta con las políticas vigentes y publícala después de revisarla." : " Tu perfil consulta los indicadores; Atención gestiona cada caso."}`,
    contexto: [{ etiqueta: "Estado", valor: "actual, no el del cierre" }] })}
  ${bandeja ? `${indicadores([
    { etiqueta: "Por clasificar", valor: num(bandeja.casos_sin_clasificar.length), detalle: "falta confirmar su categoría" },
    { etiqueta: "Borradores por revisar", valor: num(bandeja.borradores.length), detalle: "preparados, aún no publicados" },
    { etiqueta: "Pendientes en total", valor: num(ind?.pendientes ?? pendientes), detalle: "recibidas o en gestión" }])}
  <div class="grid2">
    <section class="panel"><h2>1. Requieren clasificación</h2>${bandeja.casos_sin_clasificar.length ? `<ul class="lista-casos">${bandeja.casos_sin_clasificar.map(c => `<li><a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a><span class="muted">${esc(c.radicado)} · recibida el ${esc(fechaLarga(c.creado_en))}</span></li>`).join("")}</ul>` : '<p class="muted">Ninguna solicitud pendiente de clasificar.</p>'}</section>
    <section class="panel"><h2>2. Borradores por revisar y publicar</h2>${bandeja.borradores.length ? `<ul class="lista-casos">${bandeja.borradores.map(b => `<li><a href="#/pqrs/${esc(b.radicado)}">${esc(b.radicado)}</a><span class="muted">${b.estado === "requiere_revision" ? `Requiere revisión: ${esc(b.motivo_revision || "")}` : "Listo para revisar"} · todavía no lo ve la empresa</span></li>`).join("")}</ul>` : '<p class="muted">Ningún borrador pendiente.</p>'}</section>
  </div>` : ""}
  ${ind ? (gestiona ? `<details class="panel"><summary>Ver indicadores del área (${plural(ind.pendientes ?? 0, "caso pendiente", "casos pendientes")})</summary>${bloqueIndicadores(ind, true)}</details>`
    : `${hallazgo({ que: `<strong>${plural(ind.pendientes ?? 0, "solicitud pendiente", "solicitudes pendientes")}.</strong>`, porque: (() => { const top = Object.entries(ind.abiertos_por_categoria || {}).sort((a, b) => b[1] - a[1])[0]; return top ? `La categoría con más pendientes es ${esc((CATEGORIAS[top[0]] || top[0]).toLowerCase())} (${plural(top[1], "caso", "casos")}).` : "No hay pendientes por categoría."; })() })}${bloqueIndicadores(ind, false)}`) : ""}
  <section class="panel"><h2>Todas las solicitudes</h2>
    <div class="fila" role="group" aria-label="Filtrar por estado">${[["#/pqrs", "Todas", !q.toString()], ...["recibido", "en_gestion", "respondido", "cerrado"].map(e => [`#/pqrs?estado=${e}`, ESTADO_INTERNO[e], q.get("estado") === e]), ["#/pqrs?revision=1", "Requieren clasificación", q.get("revision") === "1"]].map(([h, t, a]) => `<a class="chip ${a ? "fuerte" : ""}" href="${h}" ${a ? 'aria-current="true"' : ""}>${t}</a>`).join("")}</div>
    <form id="buscar" class="filtros" role="search"><label>Buscar por asunto o número <input name="q" value="${esc(q.get("q") || "")}"></label><button class="sec">Buscar</button></form>
    ${filtrosActivos(activos, "#/pqrs")}
    ${filas.length ? `<div class="tabla"><table class="apilable"><thead><tr><th scope="col">Asunto</th><th scope="col">Empresa y número</th><th scope="col">Estado</th><th scope="col">Categoría</th><th scope="col" class="n">Antigüedad</th><th scope="col">Responsable</th><th scope="col">Siguiente paso</th></tr></thead><tbody>
    ${filas.map(c => `<tr><td data-et="Asunto"><strong>${enlace(c)}</strong></td><td data-et="Empresa y número">${esc(c.organizacion || c.organizacion_id || "")}<span class="muted"><code>${esc(c.radicado)}</code></span></td><td data-et="Estado">${esc(ESTADO_INTERNO[c.estado] || c.estado)}</td>
      <td data-et="Categoría">${esc(CATEGORIAS[c.categoria] || "Sin categoría")}${c.requiere_revision ? '<span class="muted">por clasificar</span>' : ""}</td><td class="n" data-et="Antigüedad">${plural(c.antiguedad_dias, "día", "días")}${c.vencido ? '<span class="muted">supera el plazo configurado</span>' : ""}</td>
      <td data-et="Responsable">${esc(c.responsable_id || "Sin responsable")}</td><td data-et="Siguiente paso">${gestiona ? `<a class="boton-sec" href="#/pqrs/${esc(c.radicado)}">${esc(siguientePaso(c))}</a>` : esc(siguientePaso(c))}</td></tr>`).join("")}</tbody></table></div>` : vacio("No hay solicitudes con este filtro.", "", '<a class="boton-sec" href="#/pqrs">Quitar filtros</a>')}
  </section>`;
  document.getElementById("buscar").addEventListener("submit", e => { e.preventDefault(); const v = new FormData(e.target).get("q").trim(); ir(v ? `#/pqrs?q=${encodeURIComponent(v)}` : "#/pqrs"); });
}

// ---------------------------------------------------------------- V18 · Atención resuelve una solicitud
async function gestionCaso(rad, aviso = "") {
  const volver = { href: "#/pqrs", texto: "Volver a las solicitudes" };
  let c;
  try { c = await api("GET", `/api/pqrs/${encodeURIComponent(rad)}`); } catch (e) { $vista.innerHTML = `${encabezado({ titulo: "Solicitud", volver })}${errorHtml(e, { reintentar: e.status !== 404 })}`; return; }
  const sug = c.sugerencias.at(-1);
  const activos = c.borradores.filter(b => ["pendiente", "requiere_revision"].includes(b.estado));
  const anteriores = c.borradores.filter(b => !["pendiente", "requiere_revision"].includes(b.estado));
  const categoriaOk = !!c.categoria_revisada;
  const puedeAsignar = c.responsable_id !== S.usuario.id && c.estado !== "cerrado";
  const publicada = !!c.respuesta_publicada;
  const paso = !categoriaOk ? 1 : !activos.length && !publicada ? 2 : !publicada ? 3 : 4;
  const fuentes = b => b.fuentes.length ? `<ul class="fuentes">${b.fuentes.map((f, i) => `<li><strong>${esc(f.titulo)}</strong> · versión ${f.version} · ${esc(f.localizador)}${f.vigencia_hasta ? ` · vigente hasta el ${esc(fechaLarga(f.vigencia_hasta))}` : ""}
     <button type="button" class="enlace" data-frag="${esc(f.enlace || "")}" data-dest="frag-${b.id}-${i}">Ver la sección citada</button><div id="frag-${b.id}-${i}"></div></li>`).join("")}</ul>`
    : '<p class="estado error"><strong>Ninguna política respalda este borrador.</strong> Requiere revisión humana antes de publicar.</p>';
  $vista.innerHTML = `${encabezado({ titulo: c.asunto, volver, descripcion: `Estado: <strong>${esc(ESTADO_INTERNO[c.estado] || c.estado)}</strong> · empresa ${esc(c.organizacion)}`,
    contexto: [{ etiqueta: "Número", valor: `<code>${esc(c.radicado)}</code>` }, { etiqueta: "Recibida", valor: esc(fechaHora(c.creado_en)) }, { etiqueta: "Última actualización", valor: esc(fechaHora(c.bitacora.at(-1)?.ts || c.creado_en)) }, { etiqueta: "Responsable", valor: esc(c.responsable_id || "Sin responsable") }] })}
  <ol class="pasos" aria-label="Pasos para resolver">${["Clasificar", "Preparar la respuesta", "Revisar y publicar"].map((t, i) => `<li class="${paso > i + 1 ? "hecho" : ""}" ${paso === i + 1 ? 'aria-current="step"' : ""}>${t}</li>`).join("")}</ol>
  <div id="msg" tabindex="-1">${aviso}</div>
  <div class="grid2">
  <div>
    <section class="panel"><h2>Lo que pidió la empresa</h2><div class="burbuja">${esc(c.descripcion)}</div></section>
    <details class="panel"><summary>Ver historial interno (${c.bitacora.length})</summary>${c.bitacora.map(h => `<p class="muted">${esc(fechaHora(h.ts))} · ${esc(h.actor)} · ${esc(h.accion)} ${esc(h.de_estado || "")} → ${esc(h.a_estado || "")}${h.nota ? ` · ${esc(h.nota)}` : ""}${h.interna ? " · interna" : ""}</p>`).join("")}</details>
    ${anteriores.length ? `<details class="panel"><summary>Ver borradores anteriores (${anteriores.length})</summary>${anteriores.map(b => `<p>Borrador ${b.id} · ${esc(b.estado)}${b.aprobado_por ? ` · aprobado por ${esc(b.aprobado_por)}` : ""}</p><div class="burbuja">${esc(b.texto)}</div>`).join("")}</details>` : ""}
    <section class="panel"><h2>Gestión del caso</h2><div class="fila">
      ${puedeAsignar ? '<button class="sec" data-a="asignar">Asignármela</button>' : ""}
      ${c.estado === "respondido" ? '<button class="sec" data-a="cerrar">Cerrar la solicitud</button>' : ""}</div>
      ${["respondido", "cerrado"].includes(c.estado) ? '<div class="campos"><label for="nota">Motivo para reabrir <input id="nota"></label><div><button class="sec" data-a="reabrir">Reabrir la solicitud</button></div></div>' : ""}
      ${!["respondido", "cerrado"].includes(c.estado) ? '<p class="muted">Para cerrarla, primero publica una respuesta.</p>' : ""}
      ${publicada ? `<p><strong>Respuesta publicada:</strong></p><div class="burbuja yo">${esc(c.respuesta_publicada)}</div>` : ""}</section>
  </div>
  <div>
    <section class="panel paso ${categoriaOk ? "hecho" : ""}"><h2><span class="num-paso" aria-hidden="true">1</span>Clasificar</h2>
      <p>Sugerencia del clasificador: <strong>${esc(CATEGORIAS[sug?.categoria] || "sin sugerencia")}</strong>${sug?.confianza != null ? ` (puntaje del clasificador ${esc(pct(sug.confianza))})` : ""}${sug?.revisar ? ` · <span class="chip">requiere revisión: ${esc(sug.motivo || "puntaje bajo")}</span>` : ""}.
        ${categoriaOk ? `Confirmada: <strong>${esc(CATEGORIAS[c.categoria_revisada] || c.categoria_revisada)}</strong>.` : "Aún no confirmada."}</p>
      <div class="filtros"><label for="cat">Categoría <select id="cat">${Object.entries(CATEGORIAS).filter(([k]) => k !== "sin_categoria").map(([k, t]) => `<option value="${k}" ${k === (c.categoria_revisada || sug?.categoria) ? "selected" : ""}>${t}</option>`).join("")}</select></label>
      <button data-a="categorizar">${categoriaOk ? "Cambiar la categoría" : "Confirmar la categoría"}</button><button class="sec" data-r="reclasificar">Pedir otra sugerencia</button></div>
      ${detalleTecnico(`<p class="muted">Versión del clasificador: ${esc(sug?.version || "—")}</p>`)}</section>
    <section class="panel paso"><h2><span class="num-paso" aria-hidden="true">2</span>Preparar la respuesta</h2>
      ${publicada ? '<p class="estado ok">Ya hay una respuesta publicada. Si preparas otra, revisa antes por qué.</p>' : ""}
      <p class="muted">Preparar crea un borrador con las políticas vigentes. No se publica nada hasta el paso 3.</p>
      <button id="gen" class="${activos.length ? "sec" : ""}">${activos.length ? "Preparar otro borrador" : "Preparar un borrador con las políticas vigentes"}</button>
      ${activos.map(b => `<div class="borrador" data-borrador="${b.id}">
        <p><strong>Borrador ${b.id}</strong> · ${b.estado === "requiere_revision" ? `<span class="chip">requiere revisión: ${esc(b.motivo_revision || "")}</span>` : "pendiente de tu revisión"} · todavía no lo ve la empresa</p>
        <label>Texto de la respuesta <textarea data-b="${b.id}">${esc(b.texto)}</textarea></label>
        <div class="fila"><button class="sec" data-ed="${b.id}">Guardar los cambios del texto</button><span class="muted" data-cambios="${b.id}" aria-live="polite"></span></div>
        <h3>Qué política respalda la respuesta</h3>${fuentes(b)}
        <h3><span class="num-paso" aria-hidden="true">3</span>Revisar y publicar</h3>
        <p class="muted">Esta es la versión guardada: es exactamente la que verá la empresa ${esc(c.organizacion)}.</p><div class="burbuja yo vista-previa">${esc(b.texto)}</div>
        ${b.estado === "requiere_revision" ? `<label class="en-linea"><input type="checkbox" data-conf="${b.id}"> Revisé los puntos marcados y el texto es correcto</label>` : ""}
        <div class="fila"><button data-ap="${b.id}" data-rev="${b.estado === "requiere_revision" ? 1 : 0}">Publicar esta respuesta a ${esc(c.organizacion)}</button></div></div>`).join("") || '<p class="muted">Sin borradores pendientes.</p>'}
    </section>
  </div></div>`;
  const msg = e => { const m = document.getElementById("msg"); m.innerHTML = errorHtml(e); m.focus(); };
  const recargar = async t => { await gestionCaso(c.radicado, t ? `<div class="estado ok" role="status"><strong>${esc(t)}</strong></div>` : ""); document.getElementById("msg").focus(); };
  const ocupado = (b, t) => { b.disabled = true; b.dataset.texto = b.textContent; b.textContent = t; };
  const libre = b => { b.disabled = false; b.textContent = b.dataset.texto || b.textContent; };
  const TEXTO = { asignar: "Ahora eres responsable de esta solicitud.", categorizar: "Categoría confirmada.", cerrar: "Solicitud cerrada.", reabrir: "Solicitud reabierta." };
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    const a = b.dataset.a, cuerpo = { version: c.version };
    if (a === "categorizar") cuerpo.categoria = document.getElementById("cat").value;
    if (a === "reabrir") { cuerpo.nota = document.getElementById("nota").value.trim(); if (!cuerpo.nota) { document.getElementById("nota").setAttribute("aria-invalid", "true"); return msg(new Error("Escribe el motivo para reabrir.")); } }
    ocupado(b, "Guardando…");
    try { await api("POST", `/api/pqrs/${c.radicado}/${a}`, cuerpo); recargar(TEXTO[a]); } catch (e) { msg(e); libre(b); }
  }));
  $vista.querySelector("[data-r]").addEventListener("click", async e => { const b = e.currentTarget; ocupado(b, "Pidiendo…"); try { await api("POST", `/api/pqrs/${c.radicado}/reclasificar`, {}); recargar("Nueva sugerencia registrada."); } catch (er) { msg(er); libre(b); } });
  document.getElementById("gen").addEventListener("click", async e => { const b = e.currentTarget; ocupado(b, "Preparando…"); try { await api("POST", `/api/pqrs/${c.radicado}/borradores`, {}); recargar("Borrador preparado. Revísalo antes de publicar: la empresa todavía no lo ve."); } catch (er) { msg(er); libre(b); } });
  // La publicación usa la versión guardada: si el texto en edición difiere, se bloquea hasta guardarlo.
  for (const b of activos) {
    const ta = $vista.querySelector(`textarea[data-b="${b.id}"]`), ap = $vista.querySelector(`[data-ap="${b.id}"]`), aviso = $vista.querySelector(`[data-cambios="${b.id}"]`);
    const conf = $vista.querySelector(`[data-conf="${b.id}"]`);
    const sincronizar = () => {
      const sucio = ta.value.trim() !== b.texto.trim();
      const marcas = /\[REVISI[ÓO]N REQUERIDA/i.test(b.texto);   // condiciones que el servidor exige completar antes de aprobar
      aviso.textContent = sucio ? "Tienes cambios sin guardar: guárdalos para poder publicar."
        : marcas ? "El texto tiene partes marcadas «[REVISIÓN REQUERIDA…]». Complétalas, guarda los cambios y después podrás publicar." : "";
      ap.disabled = sucio || marcas || (conf && !conf.checked);
    };
    ta.addEventListener("input", sincronizar); conf?.addEventListener("change", sincronizar); sincronizar();
  }
  $vista.querySelectorAll("[data-ed]").forEach(b => b.addEventListener("click", async () => {
    ocupado(b, "Guardando…");
    try { await api("POST", `/api/borradores/${b.dataset.ed}/editar`, { texto: $vista.querySelector(`textarea[data-b="${b.dataset.ed}"]`).value }); recargar("Texto guardado. Revisa la vista previa antes de publicar."); } catch (e) { msg(e); libre(b); }
  }));
  $vista.querySelectorAll("[data-ap]").forEach(b => b.addEventListener("click", async () => {
    const id = b.dataset.ap, guardado = activos.find(x => String(x.id) === id);
    if ($vista.querySelector(`textarea[data-b="${id}"]`).value.trim() !== guardado.texto.trim()) return msg(new Error("El texto en edición no coincide con la vista previa. Guarda los cambios antes de publicar."));
    const ok = await confirmar({ titulo: `¿Publicar la respuesta a ${c.organizacion}?`, mensaje: `<p>La empresa <strong>${esc(c.organizacion)}</strong> verá este texto en su portal, en la solicitud <code>${esc(c.radicado)}</code>:</p><div class="burbuja yo">${esc(guardado.texto)}</div><p>Después de publicar, el texto queda en su historial.</p>`, confirmar: "Publicar la respuesta" });
    if (!ok) return;
    ocupado(b, "Publicando…");
    try { await api("POST", `/api/borradores/${id}/aprobar`, { confirmar_revision: b.dataset.rev === "1" }); recargar(`Respuesta publicada. ${c.organizacion} ya puede verla en su portal.`); } catch (e) { msg(e); libre(b); }
  }));
  $vista.querySelectorAll("[data-frag]").forEach(b => b.addEventListener("click", async () => {
    const dest = document.getElementById(b.dataset.dest);
    if (!b.dataset.frag) { dest.innerHTML = '<p class="muted">Sin enlace a la sección.</p>'; return; }
    try { const f = await api("GET", b.dataset.frag); dest.innerHTML = `<blockquote>${esc(f.texto)}</blockquote>`; } catch (e) { dest.innerHTML = errorHtml(e); }
  }));
}
