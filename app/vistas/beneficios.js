// V19 Portal: inicio y beneficios de la empresa. V22 Catálogo interno: versiones, edición y publicación como acciones distintas.
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, num, plural, puede, ruta } from "../nucleo.js";
import { confirmar, detalleTecnico, encabezado, filtrosActivos, hallazgo, pestanas, tablaHtml, vacio } from "../ui.js";

export async function vistaBeneficios() {
  return S.usuario.externo ? portal() : catalogo();
}

// ---------------------------------------------------------------- V19 · portal de la empresa
async function portal() {
  const titulo = `Hola, ${S.usuario.nombre.replace(/^Usuario externo\s*/i, "")}`;
  const lista = await api("GET", "/api/portal/beneficios").catch(e => e);
  if (lista instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(lista, { reintentar: true })}`; return; }
  const elegibles = lista.filter(b => b.elegibilidad === "elegible").length;
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Aquí ves los beneficios vigentes para tu empresa y puedes pedir uno o consultar tus solicitudes." })}
  <div class="fila" style="margin-bottom:1.5rem">${puede("pqrs.ver_propias") ? '<a class="boton-sec" href="#/pqrs">Ver mis solicitudes</a>' : ""}${puede("pqrs.crear") ? '<a class="boton-sec" href="#/pqrs?crear=1">Nueva solicitud</a>' : ""}${puede("agente.portal") ? '<a class="boton-sec" href="#/asistente">Preguntar al asistente</a>' : ""}</div>
  <h2>Beneficios disponibles para tu empresa</h2>
  ${lista.length ? `<p>${plural(lista.length, "beneficio vigente", "beneficios vigentes")}. ${elegibles === lista.length ? "Puedes solicitarlos todos." : `${plural(elegibles, "puedes solicitarlo", "puedes solicitarlos")} directamente; en ${plural(lista.length - elegibles, "otro", "otros")}, Atención revisará tu caso.`} Solicitar un beneficio no lo aprueba automáticamente.</p>` : ""}
  <div class="tarjetas-beneficio">${lista.map(b => `<article class="panel beneficio" aria-labelledby="ben-${esc(b.id)}">
    <h3 id="ben-${esc(b.id)}" style="margin-top:0">${esc(b.titulo)}</h3>
    <p><span class="sello ${b.elegibilidad === "revision" ? "sello-prueba" : "sello-ok"}">${b.elegibilidad === "revision" ? "Atención debe revisar tu caso" : "Puedes solicitarlo"}</span></p>
    <dl class="cifras"><div><dt>Qué obtiene tu empresa</dt><dd>${esc(b.descripcion)}</dd></div>
      <div><dt>Puedes solicitarlo hasta</dt><dd>${b.vigencia_hasta ? esc(fechaLarga(b.vigencia_hasta)) : "Sin fecha de fin anunciada"}</dd></div>
      <div><dt>Condición</dt><dd>${esc(b.condicion || "Sin condiciones adicionales.")}</dd></div></dl>
    ${b.elegibilidad === "revision" ? '<p class="muted">Falta un dato de tu empresa para confirmar la condición. Al solicitarlo, Atención lo revisará.</p>' : ""}
    <p class="muted">Emitido por ${esc(b.empresa_emisora)} · política ${esc(b.fuente)} · vigente desde el ${esc(fechaLarga(b.vigencia_desde))}</p>
    <div class="fila">${puede("pqrs.crear") ? `<a class="boton" href="#/pqrs?crear=1&beneficio=${encodeURIComponent(b.id)}">Solicitar este beneficio</a>` : ""}
      ${puede("documentos.consultar") ? `<button type="button" class="sec" data-pol="${esc(b.id)}" data-pregunta="${esc(b.titulo)}" aria-expanded="false" aria-controls="pol-${esc(b.id)}">Ver qué dice la política</button>` : ""}</div>
    <div id="pol-${esc(b.id)}" aria-live="polite"></div></article>`).join("")}</div>
  ${lista.length ? "" : vacio("No hay beneficios vigentes para tu empresa en este momento.", "Si necesitas algo, puedes crear una solicitud y Atención te responderá.", puede("pqrs.crear") ? '<a class="boton" href="#/pqrs?crear=1">Nueva solicitud</a>' : "")}`;
  $vista.querySelectorAll("[data-pol]").forEach(btn => btn.addEventListener("click", async () => {
    const dest = document.getElementById(`pol-${btn.dataset.pol}`);
    if (btn.getAttribute("aria-expanded") === "true") { dest.innerHTML = ""; btn.setAttribute("aria-expanded", "false"); btn.textContent = "Ver qué dice la política"; return; }
    dest.innerHTML = estadoHtml("", "Buscando la sección de la política…");
    try {
      const r = await api("POST", "/api/documentos/consultar", { pregunta: btn.dataset.pregunta });
      dest.innerHTML = `<div class="burbuja">${esc(r.texto)}${r.fuentes.length ? `<p class="muted">Sección citada: ${r.fuentes.map(f => `${esc(f.titulo)}, versión ${f.version}, ${esc(f.localizador)}`).join("; ")}</p>` : ""}</div>`;
      btn.setAttribute("aria-expanded", "true"); btn.textContent = "Ocultar la política";
    } catch (e) { dest.innerHTML = errorHtml(e); }
  }));
}

// ---------------------------------------------------------------- V22 · catálogo interno
const EDITORIAL = { borrador: "Borrador", revision: "En revisión", publicado: "Publicado", retirado: "Retirado" };
const DISPONIBILIDAD = { programado: "Aún no empieza", disponible: "Dentro de fechas", vencido: "Fechas vencidas" };
const ACCION = { enviar_revision: "Enviar a revisión", publicar: "Publicar en el portal", devolver: "Devolver a borrador", retirar: "Retirar del portal" };
const listaComas = s => (s || "").split(",").map(x => x.trim()).filter(Boolean);

function criterioDesdeFormulario(fd) {
  const c = {};
  const orgs = listaComas(fd.get("organizaciones")), segs = listaComas(fd.get("segmentos")), req = fd.getAll("requiere");
  if (orgs.length) c.organizaciones = orgs;
  if (segs.length) c.segmentos = segs;
  if (req.length) c.requiere = req;
  return c;
}
/** Misma traducción que el servidor (beneficios.condicion_texto) para la vista previa antes de guardar. */
function condicionTexto(c) {
  const p = [];
  if (c.organizaciones?.length) p.push(`empresas ${c.organizaciones.join(", ")}`);
  if (c.segmentos?.length) p.push(`${c.segmentos.length === 1 ? "empresas del segmento" : "empresas de los segmentos"} ${c.segmentos.join(" o ")}`);
  let t = p.length ? `Aplica a ${p.join(" y ")}` : "Aplica a todas las empresas";
  if (c.requiere?.length) t += `; requiere tener registrado: ${c.requiere.join(", ")}`;
  return `${t}.`;
}

let avisoPendiente = "";   // confirmación que sobrevive al cambio de sección tras guardar
async function catalogo(aviso = "") {
  if (!aviso && avisoPendiente) { aviso = avisoPendiente; avisoPendiente = ""; }
  const { q } = ruta();
  const seccion = q.get("seccion") === "retencion" ? "retencion" : q.get("seccion") === "nuevo" && puede("beneficios.editar") ? "nuevo" : "catalogo";
  const estado = q.get("estado") || "", busca = (q.get("q") || "").toLowerCase();
  const titulo = "Catálogo de beneficios";
  const [cat, ret] = await Promise.all([api("GET", "/api/beneficios"), api("GET", "/api/beneficios-retencion").catch(() => null)]).catch(e => [e]);
  if (cat instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(cat, { reintentar: true })}`; return; }
  const visibles = cat.filter(b => b.visible_en_portal).length;
  const filas = cat.filter(b => (!estado || b.estado === estado) && (!busca || `${b.titulo} ${b.id}`.toLowerCase().includes(busca)));
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/beneficios${n.toString() ? `?${n}` : ""}`; };
  const acciones = b => [
    b.estado === "borrador" && puede("beneficios.editar") && ["enviar_revision", "sec"],
    b.estado === "revision" && puede("beneficios.publicar") && ["publicar", ""], b.estado === "revision" && puede("beneficios.publicar") && ["devolver", "sec"],
    b.estado === "publicado" && puede("beneficios.publicar") && ["retirar", "sec"],
  ].filter(Boolean).map(([a, cls]) => `<button class="${cls}" data-b="${esc(b.id)}" data-v="${b.version}" data-a="${a}">${ACCION[a]}<span class="oculto-visual"> · ${esc(b.titulo)} versión ${b.version}</span></button>`).join("");
  const segmentosConocidos = [...new Set(cat.flatMap(b => b.criterio.segmentos || []))];
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Beneficios que las empresas ven en su portal. Editar crea un borrador; publicar es un paso aparte que hace Atención." })}
  <div id="msg" tabindex="-1">${aviso}</div>
  ${pestanas([["catalogo", "Beneficios y versiones", enlace({ seccion: "" })], ...(puede("beneficios.editar") ? [["nuevo", "Nuevo borrador", enlace({ seccion: "nuevo" })]] : []), ["retencion", "Seguimiento de retención", enlace({ seccion: "retencion" })]], seccion, "Secciones del catálogo")}
  ${seccion === "catalogo" ? `
  ${hallazgo({ que: `<strong>${plural(visibles, "beneficio visible", "beneficios visibles")} hoy en el portal</strong> de ${plural(cat.length, "versión registrada", "versiones registradas")}.`, porque: "Un beneficio solo es visible si está publicado y dentro de sus fechas.", accion: "" })}
  <form class="filtros" id="f-ben" role="search"><label>Buscar por nombre o código <input name="q" value="${esc(q.get("q") || "")}"></label>
    <label>Estado <select name="estado"><option value="">Todos</option>${Object.entries(EDITORIAL).map(([k, v]) => `<option value="${k}" ${estado === k ? "selected" : ""}>${v}</option>`).join("")}</select></label><button>Buscar</button></form>
  ${filtrosActivos([estado && { texto: `Estado: ${EDITORIAL[estado]}`, quitar: enlace({ estado: "" }) }, busca && { texto: `Búsqueda: «${q.get("q")}»`, quitar: enlace({ q: "" }) }].filter(Boolean), "#/beneficios")}
  ${filas.length ? `<div class="tabla"><table class="apilable"><thead><tr><th scope="col">Beneficio</th><th scope="col">Para quién</th><th scope="col">Fechas</th><th scope="col">Estado</th><th scope="col">¿Visible en el portal?</th><th scope="col">Acciones</th></tr></thead><tbody>
  ${filas.map(b => `<tr><td data-et="Beneficio"><strong>${esc(b.titulo)}</strong><span class="muted">${esc(b.id)} · versión ${b.version}${b.politica ? ` · ${esc(b.politica)}` : ""} · fuente ${esc(b.fuente || "—")}</span></td>
   <td data-et="Para quién">${esc(b.condicion)}</td>
   <td data-et="Fechas">${esc(fechaLarga(b.vigencia_desde))} a ${b.vigencia_hasta ? esc(fechaLarga(b.vigencia_hasta)) : "sin fecha de fin"}<span class="muted">${esc(DISPONIBILIDAD[b.disponibilidad] || b.disponibilidad)}</span></td>
   <td data-et="Estado">${esc(EDITORIAL[b.estado] || b.estado)}<span class="muted">${esc(b.actualizado_por || "")}${b.actualizado_en ? ` · ${esc(fechaHora(b.actualizado_en))}` : ""}</span></td>
   <td data-et="¿Visible en el portal?">${b.visible_en_portal ? "Sí" : b.estado === "publicado" && b.disponibilidad === "programado" ? `No, desde el ${esc(fechaLarga(b.vigencia_desde))}` : "No"}</td>
   <td data-et="Acciones"><div class="fila">${acciones(b) || '<span class="muted">Sin acciones para tu perfil</span>'}</div></td></tr>`).join("")}</tbody></table></div>` : vacio("Ningún beneficio coincide.", "", '<a class="boton-sec" href="#/beneficios">Quitar filtros</a>')}
  ${detalleTecnico(`<pre>${esc(JSON.stringify(cat.map(b => ({ id: b.id, version: b.version, criterio: b.criterio, actualizado_por: b.actualizado_por, actualizado_en: b.actualizado_en })), null, 2))}</pre>`, "Criterios originales")}`
  : seccion === "nuevo" ? `<section class="panel"><h2>Nuevo borrador o nueva versión</h2>
    <p class="muted">Guardar crea un borrador: no aparece en el portal hasta que Atención lo publique. Si el código ya existe, se crea una versión nueva y la anterior se conserva.</p>
    <form id="nb" class="campos" novalidate><div id="resumen-errores" tabindex="-1"></div>
    <div class="filtros"><label>Código <span class="ayuda">Por ejemplo BEN-RENOVA.</span><input name="id" required></label><label>Título <input name="titulo" required></label></div>
    <label>Qué obtiene la empresa <input name="descripcion" required></label>
    <div class="filtros"><label>Fuente aprobada <span class="ayuda">Política que lo respalda, por ejemplo POL-BENEF v2.</span><input name="fuente" required></label><label>Política (opcional) <input name="politica"></label></div>
    <div class="filtros"><label>Disponible desde <input type="date" name="vigencia_desde" required></label><label>Hasta (opcional) <input type="date" name="vigencia_hasta"></label></div>
    <fieldset><legend>¿Quién puede verlo?</legend>
      <label>Solo estas empresas <span class="ayuda">Códigos separados por coma; vacío = todas.</span><input name="organizaciones"></label>
      <label>Solo estos segmentos <span class="ayuda">Separados por coma; vacío = todos.</span><input name="segmentos" list="segs"></label>
      <datalist id="segs">${segmentosConocidos.map(s => `<option value="${esc(s)}">`).join("")}</datalist>
      <label class="en-linea"><input type="checkbox" name="requiere" value="segmento"> La empresa debe tener segmento registrado</label>
      <label class="en-linea"><input type="checkbox" name="requiere" value="cliente_id"> La empresa debe estar vinculada a un cliente</label>
      <p class="estado" id="previa" aria-live="polite">Aplica a todas las empresas.</p></fieldset>
    <div class="fila"><button>Guardar el borrador</button><a class="boton-sec" href="#/beneficios">Cancelar</a></div></form></section>`
  : `<section class="panel"><h2>Seguimiento de retención</h2>${ret ? `
    <dl class="cifras"><div><dt>Seguimientos de reactivación</dt><dd>${num(ret.tareas_reactivacion ?? ret.elegibles_reactivacion)}</dd></div><div><dt>Clientes distintos con esos seguimientos</dt><dd>${num(ret.clientes_con_tarea_reactivacion ?? null)}</dd></div></dl>
    <p class="muted">Se cuentan seguimientos, no empresas: un cliente puede tener varios.</p>
    ${ret.por_beneficio.length ? tablaHtml({ cabeceras: ["Beneficio", "Seguimientos", "Atendidos", "Recuperaciones observadas"], numericas: new Set([1, 2, 3]), filas: ret.por_beneficio.map(r => [esc(r.beneficio_id), num(r.seguimientos), num(r.atendidos), num(r.recuperaciones)]) }) : vacio("Aún no hay seguimientos vinculados a un beneficio.")}
    <p class="muted">Una recuperación observada no prueba que el beneficio la causó. No se calculan tasas hasta acordar con Ventas qué es una recuperación y en qué plazo. ${esc(ret.nota)}</p>` : errorHtml(new Error("No se pudo cargar el seguimiento de retención."), { reintentar: true })}</section>`}`;
  document.getElementById("f-ben")?.addEventListener("submit", e => { e.preventDefault(); const fd = new FormData(e.target); ir(enlace({ q: fd.get("q").trim(), estado: fd.get("estado") })); });
  const mostrar = (html) => { const m = document.getElementById("msg"); m.innerHTML = html; m.focus(); };
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    const ben = cat.find(x => x.id === b.dataset.b && String(x.version) === b.dataset.v);
    if (["publicar", "retirar"].includes(b.dataset.a)) {
      const ok = await confirmar({ titulo: `¿${ACCION[b.dataset.a]} «${ben.titulo}»?`,
        mensaje: b.dataset.a === "publicar" ? `<p>La versión ${num(ben.version)} quedará visible para: <strong>${esc(ben.condicion)}</strong>, ${ben.disponibilidad === "programado" ? `a partir del ${esc(fechaLarga(ben.vigencia_desde))}` : "desde ahora"}${ben.vigencia_hasta ? ` y hasta el ${esc(fechaLarga(ben.vigencia_hasta))}` : ""}.</p>` : `<p>Dejará de verse en el portal. Las respuestas que ya lo citaron conservan su historia.</p>`,
        confirmar: ACCION[b.dataset.a] });
      if (!ok) return;
    }
    b.disabled = true; b.textContent = "Guardando…";
    try { await api("POST", `/api/beneficios/${encodeURIComponent(b.dataset.b)}/${b.dataset.v}/${b.dataset.a}`, {}); await catalogo(`<div class="estado ok" role="status"><strong>${esc(ben.titulo)}: ${esc(ACCION[b.dataset.a].toLowerCase())} hecho.</strong></div>`); document.getElementById("msg").focus(); }
    catch (e) { mostrar(errorHtml(e)); b.disabled = false; b.textContent = ACCION[b.dataset.a]; }
  }));
  const form = document.getElementById("nb");
  if (form) {
    const previa = () => { document.getElementById("previa").textContent = condicionTexto(criterioDesdeFormulario(new FormData(form))); };
    form.addEventListener("input", previa); form.addEventListener("change", previa);
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const faltan = [...form.querySelectorAll("[required]")].filter(i => !i.value.trim());
      form.querySelectorAll("[required]").forEach(i => i.setAttribute("aria-invalid", String(!i.value.trim())));
      if (faltan.length) {
        document.getElementById("resumen-errores").innerHTML = `<div class="estado error" role="alert"><p><strong>Faltan datos obligatorios:</strong> ${faltan.map(i => esc(i.closest("label").childNodes[0].textContent.trim())).join(", ")}.</p></div>`;
        return faltan[0].focus();
      }
      document.getElementById("resumen-errores").innerHTML = "";
      const fd = new FormData(form);
      const d = { id: fd.get("id").trim(), titulo: fd.get("titulo").trim(), descripcion: fd.get("descripcion").trim(), fuente: fd.get("fuente").trim(), vigencia_desde: fd.get("vigencia_desde"),
        politica: fd.get("politica") || null, criterio: criterioDesdeFormulario(fd), empresa_emisora: "Green Services (ficticio)", __clave: form.dataset.clave ||= clave() };
      if (fd.get("vigencia_hasta")) d.vigencia_hasta = fd.get("vigencia_hasta");
      const b = form.querySelector("button"); b.disabled = true; b.textContent = "Guardando…";
      try {
        const r = await api("POST", "/api/beneficios", d);
        avisoPendiente = `<div class="estado ok" role="status"><strong>Borrador ${esc(r.id)} versión ${num(r.version)} guardado</strong> (${esc(fechaHora(r.actualizado_en))}). Todavía no aparece en el portal: falta enviarlo a revisión y que Atención lo publique.</div>`;
        ir("#/beneficios");
      } catch (err) { mostrar(errorHtml(err)); b.disabled = false; b.textContent = "Guardar el borrador"; }
    });
  }
}
