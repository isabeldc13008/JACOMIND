// Documentos y políticas: inventario por política, audiencia efectiva y prueba de consulta (entrada 21).
import { $vista, S, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, plural } from "../nucleo.js";
import { cronologia, detalleTecnico, respuesta } from "../ui.js";

const ROLES = { atencion: "Atención", empresa: "Empresas", ventas: "Ventas", operaciones: "Operaciones", gerencia: "Gerencia", finanzas: "Finanzas" };
const ESTADO = { vigente: "Vigente", reemplazado: "Reemplazada por una versión posterior", retirado: "Retirada" };
const audiencia = (roles, org) => `${roles.map(r => ROLES[r] || r).join(", ")}${roles.includes("empresa") ? (org ? ` (solo la empresa ${org})` : " (todas las empresas)") : ""}`;

export async function vistaDocumentos(aviso = "") {
  const inv = await api("GET", "/api/documentos").catch(e => e);
  if (inv instanceof Error) { $vista.innerHTML = errorHtml(inv); return; }
  const grupos = new Map();
  for (const d of inv) { if (!grupos.has(d.id)) grupos.set(d.id, []); grupos.get(d.id).push(d); }
  const politicas = [...grupos.entries()].map(([id, versiones]) => {
    versiones.sort((a, b) => b.version - a.version);
    return { id, versiones, actual: versiones.find(v => v.estado === "vigente") || null, ultima: versiones[0] };
  }).sort((a, b) => (a.actual ? 0 : 1) - (b.actual ? 0 : 1) || a.ultima.titulo.localeCompare(b.ultima.titulo));
  const vigentes = politicas.filter(p => p.actual).length;
  $vista.innerHTML = `<h1>Documentos y políticas</h1><div id="msg">${aviso}</div>
  ${respuesta(`<strong>${plural(vigentes, "política vigente", "políticas vigentes")} de ${plural(politicas.length, "documento", "documentos")}.</strong>`, "El asistente y los borradores de respuesta solo citan versiones vigentes y autorizadas para cada perfil.")}
  <div class="tarjetas-beneficio">${politicas.map(p => {
    const d = p.actual || p.ultima;
    return `<article class="panel"><h2>${esc(d.titulo)}</h2>
    <dl class="cifras"><div><dt>A quién aplica</dt><dd>${esc(audiencia(d.roles, d.organizacion_id))}</dd></div>
      <div><dt>Vigencia</dt><dd>${esc(fechaLarga(d.vigencia_desde))} – ${d.vigencia_hasta ? esc(fechaLarga(d.vigencia_hasta)) : "sin fecha de fin"}</dd></div>
      <div><dt>Versión actual</dt><dd>${p.actual ? `Versión ${p.actual.version}` : `Ninguna vigente (última: versión ${p.ultima.version}, ${esc(ESTADO[p.ultima.estado] || p.ultima.estado).toLowerCase()})`}</dd></div></dl>
    <details><summary>Versiones (${p.versiones.length})</summary>${cronologia([...p.versiones].reverse().map(v => ({ fecha: v.importado_en, etiquetaFecha: `Versión ${v.version}`, tipo: v.estado === "vigente" ? "compra" : "evento", titulo: ESTADO[v.estado] || v.estado,
      detalle: esc(`${fechaLarga(v.vigencia_desde)} – ${v.vigencia_hasta ? fechaLarga(v.vigencia_hasta) : "sin fin"} · importada ${fechaHora(v.importado_en)} por ${v.importado_por}`) })))}</details>
    ${detalleTecnico(`<p class="muted">ID ${esc(p.id)} · tema ${esc(d.tema || "—")} · ${plural(d.fragmentos, "fragmento", "fragmentos")} indexados · huella <code>${esc((d.huella || "").slice(0, 16))}</code></p>`)}
    ${p.actual ? `<div class="fila"><button class="sec" data-retirar="${esc(p.id)}">Retirar…</button></div><div id="ret-${esc(p.id)}"></div>` : ""}</article>`;
  }).join("")}</div>
  <div class="grid2">
   <section class="panel"><h2>Importar documento o nueva versión</h2><form id="imp">
    <div class="filtros"><label>ID <input name="id" required placeholder="POL-BENEF" list="ids"></label><datalist id="ids">${politicas.map(p => `<option value="${esc(p.id)}">`).join("")}</datalist>
    <label>Título <input name="titulo" required></label><label>Tema <input name="tema"></label>
    <label>Vigente desde <input type="date" name="vigencia_desde" required></label><label>Hasta <input type="date" name="vigencia_hasta"></label>
    <label>Solo para la empresa (vacío = todas) <input name="organizacion_id" placeholder="EMP-B"></label></div>
    <fieldset><legend>Perfiles que podrán consultarla</legend><div class="fila">${Object.entries(ROLES).map(([k, t]) => `<label class="en-linea"><input type="checkbox" name="roles" value="${k}" checked> ${t}</label>`).join("")}</div></fieldset>
    <label>Texto (Markdown con secciones «##» o páginas separadas por salto de página) <textarea name="texto" required></textarea></label>
    <p class="estado" id="previa-imp" aria-live="polite"></p><button>Importar</button></form></section>
   <section class="panel"><h2>Probar una consulta</h2><p class="muted">Responde con tu acceso actual (${esc(S.usuario.roles.map(r => ROLES[r] || r).join(", "))}).</p>
    <form id="con" class="fila"><input name="p" style="flex:1" placeholder="¿Cuál es el descuento por renovación?" aria-label="Pregunta"><button>Consultar</button></form><div id="resp"></div></section></div>`;
  const msg = (e, ok) => { document.getElementById("msg").innerHTML = ok ? estadoHtml("ok", ok) : errorHtml(e); window.scrollTo(0, 0); };
  // Retirar: confirmación en la página con la consecuencia para el asistente y los borradores.
  $vista.querySelectorAll("[data-retirar]").forEach(b => b.addEventListener("click", () => {
    const id = b.dataset.retirar, p = politicas.find(x => x.id === id);
    document.getElementById(`ret-${id}`).innerHTML = `<div class="estado error"><p><strong>¿Retirar la versión ${p.actual.version}?</strong> Dejará de estar disponible para ${esc(audiencia(p.actual.roles, p.actual.organizacion_id))}.
      El asistente ya no la citará y los borradores pendientes que la citan pasarán a revisión humana. No hay otra versión vigente que la sustituya.</p>
      <div class="fila"><button data-conf="${esc(id)}">Sí, retirar</button><button class="sec" data-cancel="${esc(id)}">Cancelar</button></div></div>`;
    $vista.querySelector(`[data-cancel="${id}"]`).addEventListener("click", () => { document.getElementById(`ret-${id}`).innerHTML = ""; });
    $vista.querySelector(`[data-conf="${id}"]`).addEventListener("click", async () => {
      try { await api("POST", `/api/documentos/${encodeURIComponent(id)}/retirar`, {}); vistaDocumentos(estadoHtml("ok", `${p.actual.titulo} retirada. Los borradores que la citaban quedaron para revisión.`)); } catch (e) { msg(e); }
    });
  }));
  const form = document.getElementById("imp");
  const previa = () => {
    const fd = new FormData(form), id = (fd.get("id") || "").trim(), roles = fd.getAll("roles"), org = (fd.get("organizacion_id") || "").trim();
    const existente = politicas.find(p => p.id === id);
    document.getElementById("previa-imp").innerHTML = !roles.length ? "Elige al menos un perfil." :
      `Audiencia efectiva: <strong>${esc(audiencia(roles, org))}</strong>. ${existente ? `Será la versión ${existente.ultima.version + 1} de «${esc(existente.ultima.titulo)}»${existente.actual ? `; la versión ${existente.actual.version} quedará reemplazada y los borradores pendientes que la citan pasarán a revisión` : ""}.` : "Será un documento nuevo (versión 1)."}`;
  };
  form.addEventListener("input", previa); form.addEventListener("change", previa); previa();
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(form);
    const meta = { id: fd.get("id"), titulo: fd.get("titulo"), vigencia_desde: fd.get("vigencia_desde"), propietario: S.usuario.id, roles: fd.getAll("roles") };
    for (const k of ["vigencia_hasta", "organizacion_id", "tema"]) if (fd.get(k)) meta[k] = fd.get(k);
    if (!meta.roles.length) return msg(new Error("Elige al menos un perfil que pueda consultar el documento."));
    try {
      const r = await api("POST", "/api/documentos", { meta, texto: fd.get("texto") });
      vistaDocumentos(estadoHtml("ok", r.sin_cambios ? `El texto es idéntico a la versión ${r.version}: no se creó otra.` : `${meta.titulo}: versión ${r.version} importada con ${plural(r.fragmentos, "sección", "secciones")}.`));
    } catch (err) { msg(err); }
  });
  document.getElementById("con").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const r = await api("POST", "/api/documentos/consultar", { pregunta: new FormData(e.target).get("p") });
      document.getElementById("resp").innerHTML = `<div class="burbuja"><div>${esc(r.texto)}</div>
        ${r.fuentes.length ? `<p class="muted">Sección citada:</p><ul class="fuentes">${r.fuentes.map((f, i) => `<li>${esc(f.titulo)}, versión ${f.version}, ${esc(f.localizador)} <button type="button" class="enlace" data-frag="${esc(f.enlace)}" data-dest="cf-${i}">Ver el fragmento</button><div id="cf-${i}"></div></li>`).join("")}</ul>` : '<p class="muted">Sin fuente vigente y autorizada: se remite a Atención.</p>'}</div>`;
      document.querySelectorAll("#resp [data-frag]").forEach(b => b.addEventListener("click", async () => {
        try { const f = await api("GET", b.dataset.frag); document.getElementById(b.dataset.dest).innerHTML = `<blockquote>${esc(f.texto)}</blockquote>`; } catch (err) { document.getElementById(b.dataset.dest).innerHTML = errorHtml(err); }
      }));
    } catch (err) { msg(err); }
  });
}
