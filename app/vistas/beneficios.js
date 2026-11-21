// Beneficios: portal de la empresa y catálogo interno con retención (entradas 13 y 14 del plan).
import { $vista, S, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, num, plural, puede } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

export async function vistaBeneficios() {
  return S.usuario.externo ? portal() : catalogo();
}

// ---------------------------------------------------------------- empresa (entrada 13)
async function portal() {
  const lista = await api("GET", "/api/portal/beneficios").catch(e => e);
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  const elegibles = lista.filter(b => b.elegibilidad === "elegible").length;
  $vista.innerHTML = `<h1>Beneficios disponibles para tu empresa</h1>
  ${lista.length ? respuesta(`<strong>${plural(lista.length, "beneficio vigente", "beneficios vigentes")} para tu empresa.</strong> ${elegibles === lista.length ? "Puedes solicitarlos todos." : `${plural(elegibles, "puedes solicitarlo", "puedes solicitarlos")} directamente; ${plural(lista.length - elegibles, "requiere", "requieren")} que Atención revise tu caso.`}`, "Solo se muestran los beneficios que aplican a tu empresa.") : ""}
  <div class="tarjetas-beneficio">${lista.map(b => `<article class="panel beneficio">
    <h2>${esc(b.titulo)}</h2>
    <p class="${b.elegibilidad === "revision" ? "chip" : "chip fuerte"}">${b.elegibilidad === "revision" ? "Atención debe revisar tu caso" : "Puedes solicitarlo"}</p>
    <dl class="cifras"><div><dt>Qué obtiene tu empresa</dt><dd>${esc(b.descripcion)}</dd></div>
      <div><dt>Hasta cuándo puedes solicitarlo</dt><dd>${b.vigencia_hasta ? esc(fechaLarga(b.vigencia_hasta)) : "Sin fecha de fin anunciada"}</dd></div>
      <div><dt>Condición</dt><dd>${esc(b.condicion || "Sin condiciones adicionales.")}</dd></div></dl>
    ${b.elegibilidad === "revision" ? '<p class="muted">Falta un dato de tu empresa para confirmar la condición. Al solicitarlo, Atención lo revisará.</p>' : ""}
    <p class="muted">Emitido por ${esc(b.empresa_emisora)} · política: ${esc(b.fuente)} · vigente desde ${esc(fechaLarga(b.vigencia_desde))}</p>
    <div class="fila">${puede("pqrs.crear") ? `<a class="boton" href="#/pqrs?crear=1&beneficio=${encodeURIComponent(b.id)}">Solicitar este beneficio</a>` : ""}
      ${puede("documentos.consultar") ? `<button type="button" class="sec" data-pol="${esc(b.id)}" data-pregunta="${esc(b.titulo)}">Ver qué dice la política</button>` : ""}</div>
    <div id="pol-${esc(b.id)}"></div></article>`).join("") || estadoHtml("", "No hay beneficios vigentes para tu empresa en este momento.")}</div>`;
  $vista.querySelectorAll("[data-pol]").forEach(btn => btn.addEventListener("click", async () => {
    const dest = document.getElementById(`pol-${btn.dataset.pol}`);
    try {
      const r = await api("POST", "/api/documentos/consultar", { pregunta: btn.dataset.pregunta });
      dest.innerHTML = `<div class="burbuja">${esc(r.texto)}${r.fuentes.length ? `<div class="muted">Sección citada: ${r.fuentes.map(f => `${esc(f.titulo)}, versión ${f.version}, ${esc(f.localizador)}`).join("; ")}</div>` : ""}</div>`;
    } catch (e) { dest.innerHTML = errorHtml(e); }
  }));
}

// ---------------------------------------------------------------- equipo interno (entrada 14)
const EDITORIAL = { borrador: "Borrador", revision: "En revisión", publicado: "Publicado", retirado: "Retirado" };
const DISPONIBILIDAD = { programado: "Aún no empieza", disponible: "Dentro de fechas", vencido: "Fechas vencidas" };
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

async function catalogo() {
  const [cat, ret] = await Promise.all([api("GET", "/api/beneficios"), api("GET", "/api/beneficios-retencion")]).catch(e => [e]);
  if (cat instanceof Error) { $vista.innerHTML = errorHtml(cat); return; }
  const visibles = cat.filter(b => b.visible_en_portal).length;
  const segmentosConocidos = [...new Set(cat.flatMap(b => b.criterio.segmentos || []))];
  $vista.innerHTML = `<h1>Catálogo de beneficios</h1><div id="msg"></div>
  ${respuesta(`<strong>${plural(visibles, "beneficio visible", "beneficios visibles")} hoy en el portal de las empresas</strong> de ${plural(cat.length, "versión registrada", "versiones registradas")}.`, "Un beneficio solo es visible si está publicado y dentro de sus fechas.")}
  <div class="tabla"><table><tr><th>Beneficio</th><th>Para quién</th><th>Fechas de disponibilidad</th><th>Estado editorial</th><th>¿Visible en el portal?</th><th><span class="oculto-visual">Acciones</span></th></tr>
  ${cat.map(b => `<tr><td><strong>${esc(b.titulo)}</strong><div class="muted">${esc(b.id)} · versión ${b.version}${b.politica ? ` · ${esc(b.politica)}` : ""}</div></td>
   <td>${esc(b.condicion)}</td>
   <td>${esc(fechaLarga(b.vigencia_desde))} – ${b.vigencia_hasta ? esc(fechaLarga(b.vigencia_hasta)) : "sin fecha de fin"}<div><span class="chip">${esc(DISPONIBILIDAD[b.disponibilidad] || b.disponibilidad)}</span></div></td>
   <td>${esc(EDITORIAL[b.estado] || b.estado)}</td>
   <td>${b.visible_en_portal ? "Sí" : b.estado === "publicado" && b.disponibilidad === "programado" ? `No, hasta el ${esc(fechaLarga(b.vigencia_desde))}` : "No"}</td>
   <td>${b.estado === "borrador" ? `<button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="enviar_revision">Enviar a revisión</button>` : ""}
   ${b.estado === "revision" && puede("beneficios.publicar") ? `<button data-b="${esc(b.id)}" data-v="${b.version}" data-a="publicar">Publicar</button><button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="devolver">Devolver</button>` : ""}
   ${b.estado === "publicado" && puede("beneficios.publicar") ? `<button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="retirar">Retirar</button>` : ""}</td></tr>`).join("")}</table></div>
  ${puede("beneficios.editar") ? `<section class="panel"><h2>Nuevo borrador o nueva versión</h2><form id="nb">
    <div class="filtros"><label>ID <input name="id" required placeholder="BEN-..."></label><label>Título <input name="titulo" required></label>
    <label>Qué obtiene la empresa <input name="descripcion" required></label><label>Fuente aprobada <input name="fuente" required placeholder="POL-BENEF v2"></label>
    <label>Disponible desde <input type="date" name="vigencia_desde" required></label><label>Hasta <input type="date" name="vigencia_hasta"></label><label>Política <input name="politica"></label></div>
    <fieldset><legend>¿Quién puede verlo?</legend><div class="filtros">
      <label>Solo estas empresas (IDs separados por coma; vacío = todas) <input name="organizaciones" placeholder="EMP-B"></label>
      <label>Solo estos segmentos (separados por coma; vacío = todos) <input name="segmentos" list="segs" placeholder="Recurrente en pausa"></label>
      <datalist id="segs">${segmentosConocidos.map(s => `<option value="${esc(s)}">`).join("")}</datalist>
      <label class="en-linea"><input type="checkbox" name="requiere" value="segmento"> La empresa debe tener segmento registrado</label>
      <label class="en-linea"><input type="checkbox" name="requiere" value="cliente_id"> La empresa debe estar vinculada a un cliente</label></div>
      <p class="estado" id="previa" aria-live="polite">Aplica a todas las empresas.</p></fieldset>
    <button>Guardar borrador</button></form></section>` : ""}
  <section class="panel"><h2>Seguimiento de retención</h2>
    <dl class="cifras"><div><dt>Tareas de reactivación</dt><dd>${num(ret.tareas_reactivacion ?? ret.elegibles_reactivacion)}</dd></div><div><dt>Clientes únicos con esas tareas</dt><dd>${num(ret.clientes_con_tarea_reactivacion ?? "—")}</dd></div></dl>
    <p class="muted">Se cuentan tareas, no empresas: un cliente puede tener varias.</p>
    ${ret.por_beneficio.length ? `<div class="tabla"><table><tr><th>Beneficio</th><th class="n">Seguimientos</th><th class="n">Atendidos</th><th class="n">Recuperaciones observadas</th></tr>${ret.por_beneficio.map(r => `<tr><td>${esc(r.beneficio_id)}</td><td class="n">${num(r.seguimientos)}</td><td class="n">${num(r.atendidos)}</td><td class="n">${num(r.recuperaciones)}</td></tr>`).join("")}</table></div>` : '<p class="muted">Aún no hay seguimientos vinculados a un beneficio.</p>'}
    <p class="muted">Una recuperación observada no prueba que el beneficio la haya causado. No se calculan tasas hasta acordar con Ventas la definición de recuperación y su ventana de observación. ${esc(ret.nota)}</p></section>
  ${detalleTecnico(`<pre>${esc(JSON.stringify(cat.map(b => ({ id: b.id, version: b.version, criterio: b.criterio, actualizado_por: b.actualizado_por, actualizado_en: b.actualizado_en })), null, 2))}</pre>`, "Criterios originales")}`;
  const msg = (e, ok) => { document.getElementById("msg").innerHTML = ok ? estadoHtml("ok", ok) : errorHtml(e); window.scrollTo(0, 0); };
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    try { await api("POST", `/api/beneficios/${encodeURIComponent(b.dataset.b)}/${b.dataset.v}/${b.dataset.a}`, {}); await catalogo(); msg(null, "Estado actualizado."); } catch (e) { msg(e); }
  }));
  const form = document.getElementById("nb");
  if (form) {
    const previa = () => { document.getElementById("previa").textContent = condicionTexto(criterioDesdeFormulario(new FormData(form))); };
    form.addEventListener("input", previa); form.addEventListener("change", previa);
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(form);
      const d = { id: fd.get("id"), titulo: fd.get("titulo"), descripcion: fd.get("descripcion"), fuente: fd.get("fuente"), vigencia_desde: fd.get("vigencia_desde"),
        politica: fd.get("politica") || null, criterio: criterioDesdeFormulario(fd), empresa_emisora: "Green Services (ficticio)" };
      if (fd.get("vigencia_hasta")) d.vigencia_hasta = fd.get("vigencia_hasta");
      try { const r = await api("POST", "/api/beneficios", d); await catalogo(); msg(null, `Borrador ${r.id} versión ${r.version} guardado (${fechaHora(r.actualizado_en)}).`); } catch (err) { msg(err); }
    });
  }
}

