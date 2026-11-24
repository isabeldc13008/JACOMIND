// V23 Base de conocimiento: políticas que respaldan respuestas, sus versiones y vigencia; importar y retirar son acciones
// separadas de la consulta, con su consecuencia explicada antes de confirmar.
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, plural, ruta } from "../nucleo.js";
import { confirmar, cronologia, detalleTecnico, encabezado, filtrosActivos, hallazgo, pestanas, vacio } from "../ui.js";

const ROLES = { atencion: "Atención", empresa: "Empresas", ventas: "Ventas", operaciones: "Operaciones", gerencia: "Gerencia", finanzas: "Finanzas" };
const ESTADO = { vigente: "Vigente", reemplazado: "Reemplazada por una versión posterior", retirado: "Retirada" };
const audiencia = (roles, org) => `${roles.map(r => ROLES[r] || r).join(", ")}${roles.includes("empresa") ? (org ? ` (solo la empresa ${org})` : " (todas las empresas)") : ""}`;
let avisoPendiente = "";

export async function vistaDocumentos(aviso = "") {
  if (!aviso && avisoPendiente) { aviso = avisoPendiente; avisoPendiente = ""; }
  const { q } = ruta();
  const seccion = ["importar", "probar"].includes(q.get("seccion")) ? q.get("seccion") : "biblioteca";
  const busca = (q.get("q") || "").toLowerCase(), soloVigentes = q.get("vigentes") === "1";
  const titulo = "Base de conocimiento";
  if (!$vista.querySelector("#f-doc, #imp, #con")) $vista.innerHTML = `${encabezado({ titulo })}${estadoHtml("", "Cargando los documentos…")}`;
  const inv = await api("GET", "/api/documentos").catch(e => e);
  if (inv instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(inv, { reintentar: true })}`; return; }
  const grupos = new Map();
  for (const d of inv) { if (!grupos.has(d.id)) grupos.set(d.id, []); grupos.get(d.id).push(d); }
  const politicas = [...grupos.entries()].map(([id, versiones]) => {
    versiones.sort((a, b) => b.version - a.version);
    return { id, versiones, actual: versiones.find(v => v.estado === "vigente") || null, ultima: versiones[0] };
  }).sort((a, b) => (a.actual ? 0 : 1) - (b.actual ? 0 : 1) || a.ultima.titulo.localeCompare(b.ultima.titulo));
  const vigentes = politicas.filter(p => p.actual).length;
  const visibles = politicas.filter(p => (!soloVigentes || p.actual) && (!busca || `${p.ultima.titulo} ${p.id} ${p.ultima.tema || ""}`.toLowerCase().includes(busca)));
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/documentos${n.toString() ? `?${n}` : ""}`; };
  const tarjeta = p => {
    const d = p.actual || p.ultima;
    return `<article class="panel"><h3 style="margin-top:0">${esc(d.titulo)} ${p.actual ? '<span class="sello sello-ok">Vigente</span>' : `<span class="sello sello-practica">${esc(ESTADO[p.ultima.estado] || p.ultima.estado)}</span>`}</h3>
    <dl class="cifras"><div><dt>Quién puede consultarla</dt><dd>${esc(audiencia(d.roles, d.organizacion_id))}</dd></div>
      <div><dt>Vigencia</dt><dd>${esc(fechaLarga(d.vigencia_desde))} a ${d.vigencia_hasta ? esc(fechaLarga(d.vigencia_hasta)) : "sin fecha de fin"}</dd></div>
      <div><dt>Versión</dt><dd>${p.actual ? `Versión ${p.actual.version}` : `Ninguna vigente (última: versión ${p.ultima.version})`}</dd></div></dl>
    <details><summary>Ver versiones (${p.versiones.length})</summary>${cronologia([...p.versiones].reverse().map(v => ({ fecha: v.importado_en, etiquetaFecha: `Versión ${v.version}`, tipo: v.estado === "vigente" ? "compra" : "evento", titulo: ESTADO[v.estado] || v.estado,
      detalle: esc(`${fechaLarga(v.vigencia_desde)} a ${v.vigencia_hasta ? fechaLarga(v.vigencia_hasta) : "sin fin"} · importada el ${fechaHora(v.importado_en)} por ${v.importado_por}`) })))}</details>
    ${detalleTecnico(`<p class="muted">Código ${esc(p.id)} · tema ${esc(d.tema || "—")} · ${plural(d.fragmentos, "sección indexada", "secciones indexadas")} · huella <code>${esc((d.huella || "").slice(0, 16))}</code></p>`)}
    ${p.actual ? `<div class="fila"><button class="sec" data-retirar="${esc(p.id)}">Retirar esta política<span class="oculto-visual"> ${esc(d.titulo)}</span></button></div>` : ""}</article>`;
  };
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Políticas y manuales que el asistente y las respuestas a clientes pueden citar. Solo se citan versiones vigentes y autorizadas para cada perfil." })}
  <div id="msg" tabindex="-1">${aviso}</div>
  ${pestanas([["biblioteca", "Documentos", enlace({ seccion: "" })], ["importar", "Importar documento o versión", enlace({ seccion: "importar" })], ["probar", "Probar una consulta", enlace({ seccion: "probar" })]], seccion, "Secciones de la base de conocimiento")}
  ${seccion === "biblioteca" ? `${hallazgo({ que: `<strong>${plural(vigentes, "política vigente", "políticas vigentes")}</strong> de ${plural(politicas.length, "documento", "documentos")}.`, porque: "Retirar o reemplazar una política hace que los borradores que la citan vuelvan a revisión humana.", accion: "" })}
    <form class="filtros" id="f-doc" role="search"><label>Buscar por título, código o tema <input name="q" value="${esc(q.get("q") || "")}"></label>
      <label class="en-linea"><input type="checkbox" name="vigentes" value="1" ${soloVigentes ? "checked" : ""}> Solo vigentes</label><button>Buscar</button></form>
    ${filtrosActivos([busca && { texto: `Búsqueda: «${q.get("q")}»`, quitar: enlace({ q: "" }) }, soloVigentes && { texto: "Solo vigentes", quitar: enlace({ vigentes: "" }) }].filter(Boolean), "#/documentos")}
    ${visibles.length ? `<div class="tarjetas-beneficio">${visibles.map(tarjeta).join("")}</div>` : vacio("Ningún documento coincide.", "", '<a class="boton-sec" href="#/documentos">Quitar filtros</a>')}`
  : seccion === "importar" ? `<section class="panel"><h2>Importar un documento o una versión nueva</h2>
    <p class="muted">Si el código ya existe, se crea una versión nueva y la vigente queda reemplazada. Si el texto es idéntico, no se crea otra.</p>
    <form id="imp" class="campos" novalidate><div id="resumen-errores" tabindex="-1"></div>
    <div class="filtros"><label>Código <span class="ayuda">Por ejemplo POL-BENEF.</span><input name="id" required list="ids"></label><datalist id="ids">${politicas.map(p => `<option value="${esc(p.id)}">`).join("")}</datalist>
    <label>Título <input name="titulo" required></label><label>Tema (opcional) <input name="tema"></label></div>
    <div class="filtros"><label>Vigente desde <input type="date" name="vigencia_desde" required></label><label>Hasta (opcional) <input type="date" name="vigencia_hasta"></label>
    <label>Solo para la empresa <span class="ayuda">Código; vacío = todas.</span><input name="organizacion_id"></label></div>
    <fieldset><legend>Perfiles que podrán consultarla</legend><div class="fila">${Object.entries(ROLES).map(([k, t]) => `<label class="en-linea"><input type="checkbox" name="roles" value="${k}" checked> ${t}</label>`).join("")}</div></fieldset>
    <label>Texto <span class="ayuda">Markdown con secciones «##», o páginas separadas por salto de página.</span><textarea name="texto" required></textarea></label>
    <p class="estado" id="previa-imp" aria-live="polite"></p><div class="fila"><button>Importar</button></div></form></section>`
  : `<section class="panel"><h2>Probar una consulta</h2><p class="muted">Responde con tu acceso actual (${esc(S.usuario.roles.map(r => ROLES[r] || r).join(", "))}), igual que lo haría el asistente.</p>
    <form id="con" class="filtros"><label style="flex:1">Pregunta <span class="ayuda">Por ejemplo: ¿cuál es el descuento por renovación?</span><input name="p" required></label><button>Consultar</button></form><div id="resp" aria-live="polite"></div></section>`}`;
  if (aviso) document.getElementById("msg").focus();
  const msg = html => { const m = document.getElementById("msg"); m.innerHTML = html; m.focus(); };
  document.getElementById("f-doc")?.addEventListener("submit", e => { e.preventDefault(); const fd = new FormData(e.target); ir(enlace({ q: fd.get("q").trim(), vigentes: fd.get("vigentes") || "" })); });
  $vista.querySelectorAll("[data-retirar]").forEach(b => b.addEventListener("click", async () => {
    const id = b.dataset.retirar, p = politicas.find(x => x.id === id);
    const ok = await confirmar({ titulo: `¿Retirar «${p.actual.titulo}», versión ${p.actual.version}?`,
      mensaje: `<p>Dejará de estar disponible para ${esc(audiencia(p.actual.roles, p.actual.organizacion_id))}. El asistente ya no la citará y los borradores pendientes que la citan volverán a revisión humana.</p><p>No hay otra versión vigente que la sustituya. Su historia se conserva.</p>`, confirmar: "Retirar la política" });
    if (!ok) return;
    b.disabled = true; b.textContent = "Retirando…";
    try { await api("POST", `/api/documentos/${encodeURIComponent(id)}/retirar`, {}); vistaDocumentos(`<div class="estado ok" role="status"><strong>${esc(p.actual.titulo)} retirada.</strong> Los borradores que la citaban quedaron para revisión.</div>`); }
    catch (e) { msg(errorHtml(e)); b.disabled = false; b.textContent = "Retirar esta política"; }
  }));
  const form = document.getElementById("imp");
  if (form) {
    const previa = () => {
      const fd = new FormData(form), id = (fd.get("id") || "").trim(), roles = fd.getAll("roles"), org = (fd.get("organizacion_id") || "").trim();
      const existente = politicas.find(p => p.id === id);
      document.getElementById("previa-imp").innerHTML = !roles.length ? "Elige al menos un perfil." :
        `Quién podrá consultarla: <strong>${esc(audiencia(roles, org))}</strong>. ${existente ? `Será la versión ${existente.ultima.version + 1} de «${esc(existente.ultima.titulo)}»${existente.actual ? `; la versión ${existente.actual.version} quedará reemplazada y los borradores que la citan pasarán a revisión` : ""}.` : "Será un documento nuevo (versión 1)."}`;
    };
    form.addEventListener("input", previa); form.addEventListener("change", previa); previa();
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const fd = new FormData(form);
      const faltan = [...form.querySelectorAll("[required]")].filter(i => !i.value.trim());
      form.querySelectorAll("[required]").forEach(i => i.setAttribute("aria-invalid", String(!i.value.trim())));
      const sinRoles = !fd.getAll("roles").length;
      if (faltan.length || sinRoles) {
        document.getElementById("resumen-errores").innerHTML = `<div class="estado error" role="alert"><p><strong>Revisa el formulario:</strong></p><ul>${faltan.map(i => `<li>Falta: ${esc(i.closest("label").childNodes[0].textContent.trim())}</li>`).join("")}${sinRoles ? "<li>Elige al menos un perfil que pueda consultarla.</li>" : ""}</ul></div>`;
        return (faltan[0] || form.querySelector("[name=roles]")).focus();
      }
      document.getElementById("resumen-errores").innerHTML = "";
      const meta = { id: fd.get("id").trim(), titulo: fd.get("titulo").trim(), vigencia_desde: fd.get("vigencia_desde"), propietario: S.usuario.id, roles: fd.getAll("roles") };
      for (const k of ["vigencia_hasta", "organizacion_id", "tema"]) if (fd.get(k)) meta[k] = fd.get(k);
      const b = form.querySelector("button"); b.disabled = true; b.textContent = "Importando…";
      try {
        const r = await api("POST", "/api/documentos", { meta, texto: fd.get("texto"), __clave: form.dataset.clave ||= clave() });
        avisoPendiente = `<div class="estado ok" role="status"><strong>${r.sin_cambios ? `El texto es idéntico a la versión ${r.version}: no se creó otra.` : `${esc(meta.titulo)}: versión ${r.version} importada con ${plural(r.fragmentos, "sección", "secciones")}.`}</strong></div>`;
        ir("#/documentos");
      } catch (err) { msg(errorHtml(err)); b.disabled = false; b.textContent = "Importar"; }
    });
  }
  document.getElementById("con")?.addEventListener("submit", async e => {
    e.preventDefault();
    const p = new FormData(e.target).get("p").trim(), resp = document.getElementById("resp");
    if (!p) { e.target.querySelector("input").setAttribute("aria-invalid", "true"); return e.target.querySelector("input").focus(); }
    resp.innerHTML = estadoHtml("", "Consultando…");
    try {
      const r = await api("POST", "/api/documentos/consultar", { pregunta: p });
      resp.innerHTML = `<div class="burbuja"><div>${esc(r.texto)}</div>
        ${r.fuentes.length ? `<p class="muted">Sección citada:</p><ul class="fuentes">${r.fuentes.map((f, i) => `<li>${esc(f.titulo)}, versión ${f.version}, ${esc(f.localizador)} <button type="button" class="enlace" data-frag="${esc(f.enlace)}" data-dest="cf-${i}">Ver la sección</button><div id="cf-${i}"></div></li>`).join("")}</ul>` : '<p class="muted">Sin fuente vigente y autorizada: se remite a Atención.</p>'}</div>`;
      resp.querySelectorAll("[data-frag]").forEach(b => b.addEventListener("click", async () => {
        try { const f = await api("GET", b.dataset.frag); document.getElementById(b.dataset.dest).innerHTML = `<blockquote>${esc(f.texto)}</blockquote>`; } catch (err) { document.getElementById(b.dataset.dest).innerHTML = errorHtml(err); }
      }));
    } catch (err) { resp.innerHTML = errorHtml(err); }
  });
}
