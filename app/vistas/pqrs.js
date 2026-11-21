// Solicitudes (PQRS): portal de la empresa, bandeja e indicadores, y gestión de un caso (entradas 9 a 12).
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, num, pct, plural, puede, ruta } from "../nucleo.js";
import { barras, cronologia, detalleTecnico, respuesta, verDatos } from "../ui.js";

const ESTADO_EMPRESA = { recibido: "Recibida, pendiente de revisión", en_gestion: "En revisión por nuestro equipo", respondido: "Respondida", cerrado: "Cerrada" };
const ESTADO_INTERNO = { recibido: "Recibido", en_gestion: "En gestión", respondido: "Respondido", cerrado: "Cerrado" };
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

// ---------------------------------------------------------------- empresa · lista y radicación (entrada 9)
async function listaEmpresa() {
  const { q } = ruta();
  const busca = q.get("q") || "", crear = q.get("crear") === "1", bid = q.get("beneficio");
  const [lista, ben] = await Promise.all([api("GET", `/api/pqrs?${new URLSearchParams({ q: busca })}`),
    bid ? api("GET", `/api/portal/beneficios/${encodeURIComponent(bid)}`).catch(() => null) : null]).catch(e => [e]);
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  const asunto = ben ? `Solicitud del beneficio «${ben.titulo}»` : "";
  const descripcion = ben ? `Solicitamos el beneficio «${ben.titulo}» (${ben.id}, versión ${ben.version}), publicado con la fuente ${ben.fuente}. ` : "";
  $vista.innerHTML = `<h1>Solicitudes de mi empresa</h1>
  <p class="muted">${PQRS_EXPLICADO}. Aquí ves las solicitudes de tu empresa, no solo las tuyas.</p>
  <div class="grid2">
    <section class="panel"><h2>Consultar una solicitud</h2><form id="buscar" class="fila"><label style="flex:1">Asunto o número de seguimiento <input name="q" value="${esc(busca)}" placeholder="p. ej. factura o PQRS-20261101-00001"></label><button>Buscar</button></form>
      ${busca ? `<p class="muted">${plural(lista.length, "solicitud coincide", "solicitudes coinciden")} con «${esc(busca)}». <a href="#/pqrs">Ver todas</a></p>` : ""}</section>
    <section class="panel"><h2>Crear solicitud</h2>${puede("pqrs.crear") ? (crear ? `<form id="nueva">
      ${ben ? `<p class="estado">Vas a solicitar <strong>${esc(ben.titulo)}</strong>. Revisa el texto antes de enviarlo; puedes cambiarlo.</p>` : ""}
      <label>Asunto <input name="asunto" required maxlength="200" value="${esc(asunto)}" placeholder="p. ej. Doble cobro en la factura de octubre"></label>
      <label>Descripción <textarea name="descripcion" required maxlength="5000" placeholder="Cuéntanos qué pasó, cuándo y qué necesitas.">${esc(descripcion)}</textarea></label>
      <div class="fila"><button>Enviar solicitud</button><a href="#/pqrs">Cancelar</a></div></form><div id="msg"></div>`
      : `<p class="muted">Al enviarla recibirás un número de seguimiento para consultarla.</p><a class="boton" href="#/pqrs?crear=1">Crear solicitud</a>`) : '<p class="muted">Tu perfil no puede crear solicitudes.</p>'}</section>
  </div>
  <div class="tabla"><table><tr><th>Asunto</th><th>Estado</th><th>Número de seguimiento</th><th>Creada</th></tr>
  ${lista.map(c => `<tr><td><a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a></td><td>${esc(ESTADO_EMPRESA[c.estado] || c.estado)}</td><td><code>${esc(c.radicado)}</code></td><td>${esc(fechaLarga(c.creado_en))}</td></tr>`).join("") || `<tr><td colspan=4 class="muted">${busca ? "Ninguna solicitud coincide." : "Tu empresa aún no tiene solicitudes."}</td></tr>`}
  </table></div>`;
  document.getElementById("buscar").addEventListener("submit", e => { e.preventDefault(); const v = new FormData(e.target).get("q").trim(); ir(v ? `#/pqrs?q=${encodeURIComponent(v)}` : "#/pqrs"); });
  document.getElementById("nueva")?.addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button"); btn.disabled = true;
    const fd = new FormData(e.target);
    e.target.dataset.clave ||= clave();   // reintentos del mismo formulario → mismo número de seguimiento
    try {
      const r = await api("POST", "/api/pqrs", { asunto: fd.get("asunto"), descripcion: fd.get("descripcion"), __clave: e.target.dataset.clave });
      ir(`#/pqrs/${r.radicado}?nuevo=1`);
    } catch (err) { document.getElementById("msg").innerHTML = errorHtml(err); btn.disabled = false; }
  });
}

// ---------------------------------------------------------------- empresa · detalle (entrada 10)
async function detalleEmpresa(rad) {
  let c;
  try { c = await api("GET", `/api/pqrs/${encodeURIComponent(rad)}`); } catch (e) { $vista.innerHTML = `<a href="#/pqrs">← Solicitudes de mi empresa</a>${errorHtml(e)}`; return; }
  const nuevo = ruta().q.get("nuevo") === "1";
  const eventos = c.historial.filter(h => ACCION_PUBLICA[h.accion]).map(h => ({ fecha: h.ts, etiquetaFecha: fechaHora(h.ts), tipo: h.accion === "reabrir" ? "vencimiento" : "evento", titulo: ACCION_PUBLICA[h.accion] }));
  $vista.innerHTML = `<a href="#/pqrs">← Solicitudes de mi empresa</a>
  ${nuevo ? `<div class="estado ok" role="status">Recibimos tu solicitud. Guarda este número de seguimiento: <strong><code>${esc(c.radicado)}</code></strong>. Con él podrás volver a consultarla aquí.</div>` : ""}
  <h1>${esc(c.asunto)}</h1>
  ${respuesta(`<strong>${esc(ESTADO_EMPRESA[c.estado] || c.estado)}.</strong> ${c.respuesta_publicada ? "Ya tienes una respuesta publicada." : "Recibimos tu solicitud. Podrás consultar la respuesta aquí."}`,
    `Número de seguimiento <code>${esc(c.radicado)}</code> · última actualización ${esc(fechaHora(c.actualizado_en || c.creado_en))}`)}
  <section class="panel"><h2>Respuesta</h2>${c.respuesta_publicada ? `<div class="burbuja yo">${esc(c.respuesta_publicada)}</div><p class="muted">Publicada el ${esc(fechaHora(c.respondido_en))}.</p>` : '<p class="muted">Aún no hay una respuesta publicada.</p>'}</section>
  <section class="panel"><h2>Lo que nos contaste</h2><div class="burbuja">${esc(c.descripcion)}</div></section>
  <section class="panel"><h2>Cambios en tu solicitud</h2>${cronologia(eventos, { vacio: "Sin cambios públicos todavía." })}</section>`;
}

// ---------------------------------------------------------------- bandeja e indicadores (entrada 11)
function bloqueIndicadores(ind, enlaces) {
  const cats = Object.entries(ind.abiertos_por_categoria || {}).sort((a, b) => b[1] - a[1]);
  const prim = ind.horas_primera_gestion_mediana_total, resp = ind.horas_resolucion_mediana_total;
  const nPrim = Object.values(ind.casos_medidos_primera_gestion || {}).reduce((s, x) => s + x, 0);
  const nResp = Object.values(ind.casos_medidos_resolucion || {}).reduce((s, x) => s + x, 0);
  const todas = [...new Set([...Object.keys(ind.abiertos_por_categoria || {}), ...Object.keys(ind.horas_primera_gestion_mediana || {}), ...Object.keys(ind.horas_resolucion_mediana || {})])];
  const horas = (h, n) => h == null ? "—" : `${num(h)} h (${plural(n || 0, "caso", "casos")})`;
  return `<div class="grid2 ancho-desigual">
    <section class="panel"><h2>Pendientes por categoría</h2>
      ${barras(cats.map(([k, v]) => ({ etiqueta: CATEGORIAS[k] || k, valor: v, texto: plural(v, "caso", "casos"), href: enlaces ? `#/pqrs?categoria=${encodeURIComponent(k)}` : null })), { etiquetaAria: "Casos pendientes por categoría", vacio: "No hay casos pendientes." })}
      <p class="muted">Pendiente = recibido o en gestión. Total: ${plural(ind.pendientes ?? 0, "caso", "casos")}.</p></section>
    <section class="panel"><h2>Tiempos habituales</h2>
      <p><strong>Hasta la primera atención:</strong> ${prim == null ? "Aún no hay casos atendidos para calcular el tiempo." : `${num(prim)} horas de mediana (${plural(nPrim, "caso medido", "casos medidos")}).`}</p>
      <p><strong>Hasta la respuesta:</strong> ${resp == null ? "Aún no hay respuestas para calcular el tiempo." : `${num(resp)} horas de mediana (${plural(nResp, "caso medido", "casos medidos")}).`}</p>
      ${verDatos({ tabla: { cabeceras: ["Categoría", "Pendientes", "Mediana hasta primera atención", "Mediana hasta respuesta"], numericas: new Set([1]),
        filas: todas.map(k => [esc(CATEGORIAS[k] || k), num(ind.abiertos_por_categoria?.[k] || 0), esc(horas(ind.horas_primera_gestion_mediana?.[k], ind.casos_medidos_primera_gestion?.[k])), esc(horas(ind.horas_resolucion_mediana?.[k], ind.casos_medidos_resolucion?.[k]))]) },
        fuente: "Registro de solicitudes (estado actual, no corresponde al cierre)", regla: `${esc(ind.definicion_mediana || "")} ${esc(ind.nota)}` })}</section>
  </div>`;
}

async function bandejaInterna() {
  const { q } = ruta();
  const gestiona = puede("pqrs.gestionar");
  const [lista, ind, bandeja] = await Promise.all([
    api("GET", `/api/pqrs?${new URLSearchParams({ estado: q.get("estado") || "", revision: q.get("revision") || "", q: q.get("q") || "" })}`),
    puede("pqrs.indicadores") ? api("GET", "/api/pqrs-indicadores") : null,
    gestiona ? api("GET", "/api/atencion/bandeja") : null]).catch(e => [e]);
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  const cat = q.get("categoria");
  const filas = cat ? lista.filter(c => (c.categoria || "sin_categoria") === cat && ["recibido", "en_gestion"].includes(c.estado)) : lista;
  const enlace = c => gestiona ? `<a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a>` : esc(c.asunto);
  const filtro = (h, t, activo) => `<a class="chip ${activo ? "fuerte" : ""}" href="${h}">${t}</a>`;
  $vista.innerHTML = `<h1>${gestiona ? "Bandeja de solicitudes" : "Solicitudes · indicadores"}</h1><p class="muted">${PQRS_EXPLICADO}.</p>
  ${bandeja ? `<div class="grid2">
    <section class="panel"><h2>Requieren clasificación (${bandeja.casos_sin_clasificar.length})</h2>${bandeja.casos_sin_clasificar.length ? `<ul class="lista-casos">${bandeja.casos_sin_clasificar.map(c => `<li><a href="#/pqrs/${esc(c.radicado)}">${esc(c.asunto)}</a><span class="muted"> · ${esc(c.radicado)} · recibido ${esc(fechaLarga(c.creado_en))}</span></li>`).join("")}</ul>` : '<p class="muted">Ningún caso pendiente de clasificar.</p>'}</section>
    <section class="panel"><h2>Borradores por aprobar (${bandeja.borradores.length})</h2>${bandeja.borradores.length ? `<ul class="lista-casos">${bandeja.borradores.map(b => `<li><a href="#/pqrs/${esc(b.radicado)}">${esc(b.radicado)}</a><span class="muted"> · ${b.estado === "requiere_revision" ? `requiere revisión: ${esc(b.motivo_revision || "")}` : "listo para revisar"}</span></li>`).join("")}</ul>` : '<p class="muted">Ningún borrador pendiente.</p>'}</section>
  </div>` : ""}
  ${ind ? (gestiona ? `<details class="panel"><summary><strong>Indicadores del área</strong> · ${plural(ind.pendientes ?? 0, "caso pendiente", "casos pendientes")}</summary>${bloqueIndicadores(ind, true)}</details>`
    : `${respuesta(`<strong>${plural(ind.pendientes ?? 0, "solicitud pendiente", "solicitudes pendientes")}.</strong> ${(() => { const top = Object.entries(ind.abiertos_por_categoria || {}).sort((a, b) => b[1] - a[1])[0]; return top ? `La categoría con más pendientes es ${esc((CATEGORIAS[top[0]] || top[0]).toLowerCase())} (${plural(top[1], "caso", "casos")}).` : ""; })()}`, "Estado actual del registro de solicitudes")}${bloqueIndicadores(ind, false)}`) : ""}
  <h2>Todos los casos</h2>
  <div class="filtros">${filtro("#/pqrs", "Todos", !q.toString())}${["recibido", "en_gestion", "respondido", "cerrado"].map(e => filtro(`#/pqrs?estado=${e}`, ESTADO_INTERNO[e], q.get("estado") === e)).join("")}${filtro("#/pqrs?revision=1", "Requieren clasificación", q.get("revision") === "1")}
    ${cat ? `<span class="chip fuerte">Pendientes de ${esc(CATEGORIAS[cat] || cat)}</span>` : ""}
    <form id="buscar" class="fila"><input name="q" value="${esc(q.get("q") || "")}" placeholder="Asunto o número" aria-label="Buscar por asunto o número"><button class="sec">Buscar</button></form></div>
  ${!gestiona ? '<p class="muted">Tu perfil consulta indicadores; el detalle de cada caso lo gestiona Atención.</p>' : ""}
  <div class="tabla"><table><tr><th>Asunto</th><th>Número</th><th>Estado</th><th>Categoría</th><th class="n">Antigüedad</th><th>Responsable</th></tr>
  ${filas.map(c => `<tr><td>${enlace(c)}</td><td><code>${esc(c.radicado)}</code></td><td>${esc(ESTADO_INTERNO[c.estado] || c.estado)}</td>
    <td>${esc(CATEGORIAS[c.categoria] || "Sin categoría")}${c.requiere_revision ? ' <span class="chip">por clasificar</span>' : ""}</td><td class="n">${c.antiguedad_dias} d${c.vencido ? ' <span class="chip">fuera de plazo</span>' : ""}</td><td>${esc(c.responsable_id || "Sin responsable")}</td></tr>`).join("") || '<tr><td colspan=6 class="muted">Sin casos.</td></tr>'}
  </table></div>`;
  document.getElementById("buscar").addEventListener("submit", e => { e.preventDefault(); const v = new FormData(e.target).get("q").trim(); ir(v ? `#/pqrs?q=${encodeURIComponent(v)}` : "#/pqrs"); });
}

// ---------------------------------------------------------------- Atención · gestión de un caso (entrada 12)
async function gestionCaso(rad, aviso = "") {
  let c;
  try { c = await api("GET", `/api/pqrs/${encodeURIComponent(rad)}`); } catch (e) { $vista.innerHTML = `<a href="#/pqrs">← Bandeja</a>${errorHtml(e)}`; return; }
  const sug = c.sugerencias.at(-1);
  const activos = c.borradores.filter(b => ["pendiente", "requiere_revision"].includes(b.estado));
  const anteriores = c.borradores.filter(b => !["pendiente", "requiere_revision"].includes(b.estado));
  const categoriaOk = !!c.categoria_revisada;
  const puedeAsignar = c.responsable_id !== S.usuario.id && c.estado !== "cerrado";
  const fuentes = b => b.fuentes.length ? `<ul class="fuentes">${b.fuentes.map((f, i) => `<li><strong>${esc(f.titulo)}</strong> · versión ${f.version} · ${esc(f.localizador)}${f.vigencia_hasta ? ` · vigente hasta ${esc(fechaLarga(f.vigencia_hasta))}` : ""}
     <button type="button" class="enlace" data-frag="${esc(f.enlace || "")}" data-dest="frag-${b.id}-${i}">Ver la sección citada</button><div id="frag-${b.id}-${i}"></div></li>`).join("")}</ul>`
    : '<p class="estado error">Ninguna política respalda este borrador: requiere revisión humana antes de publicar.</p>';
  $vista.innerHTML = `<a href="#/pqrs">← Bandeja</a><h1>${esc(c.asunto)}</h1>
  <dl class="cifras encabezado-tarea"><div><dt>Número</dt><dd><code>${esc(c.radicado)}</code></dd></div><div><dt>Empresa</dt><dd>${esc(c.organizacion)}</dd></div>
    <div><dt>Estado</dt><dd>${esc(ESTADO_INTERNO[c.estado] || c.estado)}</dd></div><div><dt>Responsable</dt><dd>${esc(c.responsable_id || "Sin responsable")}</dd></div><div><dt>Recibido</dt><dd>${esc(fechaHora(c.creado_en))}</dd></div></dl>
  <div class="burbuja">${esc(c.descripcion)}</div><div id="msg">${aviso}</div>
  <section class="panel paso ${categoriaOk ? "hecho" : ""}"><h2><span class="num-paso">1</span> Revisa la categoría</h2>
    <p>Sugerida por el clasificador: <strong>${esc(CATEGORIAS[sug?.categoria] || "sin sugerencia")}</strong>${sug?.confianza != null ? ` con ${esc(pct(sug.confianza))} de confianza` : ""}${sug?.revisar ? ` · <span class="chip">requiere revisión: ${esc(sug.motivo || "baja confianza")}</span>` : ""}.
      ${categoriaOk ? `Confirmada: <strong>${esc(CATEGORIAS[c.categoria_revisada] || c.categoria_revisada)}</strong>.` : "Aún no confirmada."}</p>
    <div class="fila"><label>Categoría <select id="cat">${Object.entries(CATEGORIAS).filter(([k]) => k !== "sin_categoria").map(([k, t]) => `<option value="${k}" ${k === (c.categoria_revisada || sug?.categoria) ? "selected" : ""}>${t}</option>`).join("")}</select></label>
    <button data-a="categorizar">${categoriaOk ? "Cambiar categoría" : "Confirmar categoría"}</button><button class="sec" data-r="reclasificar">Pedir otra sugerencia</button></div>
    ${detalleTecnico(`<p class="muted">Versión del clasificador: ${esc(sug?.version || "—")}</p>`)}</section>
  <section class="panel paso"><h2><span class="num-paso">2</span> Prepara la respuesta</h2>
    ${c.respuesta_publicada ? `<p class="estado ok">Ya hay una respuesta publicada. Si generas otra, revisa por qué antes de publicarla.</p>` : ""}
    <button id="gen" class="${activos.length ? "sec" : ""}">${activos.length ? "Generar otro borrador" : "Generar borrador con las políticas vigentes"}</button>
    ${activos.map(b => `<div class="borrador" data-borrador="${b.id}">
      <p><strong>Borrador ${b.id}</strong> · ${b.estado === "requiere_revision" ? `<span class="chip">requiere revisión: ${esc(b.motivo_revision || "")}</span>` : "pendiente de tu revisión"}</p>
      <label>Texto de la respuesta <textarea data-b="${b.id}">${esc(b.texto)}</textarea></label>
      <div class="fila"><button class="sec" data-ed="${b.id}">Guardar edición</button><span class="muted" data-cambios="${b.id}"></span></div>
      <h3>Qué política sustenta la respuesta</h3>${fuentes(b)}
      <h3><span class="num-paso">3</span> Revisa lo que verá la empresa</h3>
      <p class="muted">Esta es la versión guardada: es exactamente la que se publicará.</p><div class="burbuja yo vista-previa">${esc(b.texto)}</div>
      ${b.estado === "requiere_revision" ? `<label class="en-linea"><input type="checkbox" data-conf="${b.id}"> Revisé los puntos marcados y el texto es correcto</label>` : ""}
      <div class="fila"><button data-ap="${b.id}" data-rev="${b.estado === "requiere_revision" ? 1 : 0}">Publicar esta respuesta a la empresa</button></div></div>`).join("") || '<p class="muted">Sin borradores pendientes.</p>'}
  </section>
  <section class="panel"><h2>Gestión del caso</h2><div class="fila">
    ${puedeAsignar ? '<button class="sec" data-a="asignar">Asignármelo</button>' : ""}
    ${c.estado === "respondido" ? '<button class="sec" data-a="cerrar">Cerrar el caso</button>' : ""}
    ${["respondido", "cerrado"].includes(c.estado) ? '<label>Motivo de reapertura <input id="nota"></label><button class="sec" data-a="reabrir">Reabrir</button>' : ""}
    ${!puedeAsignar && c.estado !== "respondido" && c.estado !== "cerrado" ? '<span class="muted">Responde el caso para poder cerrarlo.</span>' : ""}</div>
    ${c.respuesta_publicada ? `<p class="muted">Respuesta publicada: ${esc(c.respuesta_publicada)}</p>` : ""}</section>
  ${anteriores.length ? `<details class="panel"><summary>Borradores anteriores (${anteriores.length})</summary>${anteriores.map(b => `<p>Borrador ${b.id} · ${esc(b.estado)}${b.aprobado_por ? ` · aprobado por ${esc(b.aprobado_por)}` : ""}</p><div class="burbuja">${esc(b.texto)}</div>`).join("")}</details>` : ""}
  <details class="panel"><summary>Bitácora (${c.bitacora.length})</summary>${c.bitacora.map(h => `<div class="muted">${esc(fechaHora(h.ts))} · ${esc(h.actor)} · ${esc(h.accion)} ${esc(h.de_estado || "")} → ${esc(h.a_estado || "")}${h.nota ? ` · ${esc(h.nota)}` : ""}${h.interna ? " · interna" : ""}</div>`).join("")}</details>`;
  const msg = e => { document.getElementById("msg").innerHTML = errorHtml(e); window.scrollTo(0, 0); };
  const recargar = t => gestionCaso(c.radicado, t ? estadoHtml("ok", t) : "");
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    const a = b.dataset.a, cuerpo = { version: c.version };
    if (a === "categorizar") cuerpo.categoria = document.getElementById("cat").value;
    if (a === "reabrir") cuerpo.nota = document.getElementById("nota").value;
    try { await api("POST", `/api/pqrs/${c.radicado}/${a}`, cuerpo); recargar(); } catch (e) { msg(e); }
  }));
  $vista.querySelector("[data-r]").addEventListener("click", async () => { try { await api("POST", `/api/pqrs/${c.radicado}/reclasificar`, {}); recargar("Nueva sugerencia registrada."); } catch (e) { msg(e); } });
  document.getElementById("gen").addEventListener("click", async () => { try { await api("POST", `/api/pqrs/${c.radicado}/borradores`, {}); recargar("Borrador generado: revísalo antes de publicar."); } catch (e) { msg(e); } });
  // La aprobación publica la versión guardada: si el texto en edición difiere, se bloquea hasta guardarlo.
  for (const b of activos) {
    const ta = $vista.querySelector(`textarea[data-b="${b.id}"]`), ap = $vista.querySelector(`[data-ap="${b.id}"]`), aviso = $vista.querySelector(`[data-cambios="${b.id}"]`);
    const conf = $vista.querySelector(`[data-conf="${b.id}"]`);
    const sincronizar = () => {
      const sucio = ta.value.trim() !== b.texto.trim();
      aviso.textContent = sucio ? "Tienes cambios sin guardar: guárdalos para revisar la versión final." : "";
      ap.disabled = sucio || (conf && !conf.checked);
    };
    ta.addEventListener("input", sincronizar); conf?.addEventListener("change", sincronizar); sincronizar();
  }
  $vista.querySelectorAll("[data-ed]").forEach(b => b.addEventListener("click", async () => {
    try { await api("POST", `/api/borradores/${b.dataset.ed}/editar`, { texto: $vista.querySelector(`textarea[data-b="${b.dataset.ed}"]`).value }); recargar("Edición guardada. Revisa la vista previa antes de publicar."); } catch (e) { msg(e); }
  }));
  $vista.querySelectorAll("[data-ap]").forEach(b => b.addEventListener("click", async () => {
    const id = b.dataset.ap, guardado = activos.find(x => String(x.id) === id);
    if ($vista.querySelector(`textarea[data-b="${id}"]`).value.trim() !== guardado.texto.trim()) return msg(new Error("El texto en edición no coincide con la vista previa. Guarda la edición antes de publicar."));
    b.disabled = true;
    try { await api("POST", `/api/borradores/${id}/aprobar`, { confirmar_revision: b.dataset.rev === "1" }); recargar("Respuesta publicada. La empresa ya puede verla."); } catch (e) { msg(e); b.disabled = false; }
  }));
  $vista.querySelectorAll("[data-frag]").forEach(b => b.addEventListener("click", async () => {
    const dest = document.getElementById(b.dataset.dest);
    if (!b.dataset.frag) { dest.innerHTML = '<p class="muted">Sin enlace al fragmento.</p>'; return; }
    try { const f = await api("GET", b.dataset.frag); dest.innerHTML = `<blockquote>${esc(f.texto)}</blockquote>`; } catch (e) { dest.innerHTML = errorHtml(e); }
  }));
}
