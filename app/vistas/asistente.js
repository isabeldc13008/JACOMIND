// Asistente conversacional (entradas 15 y 16 del plan): chat con memoria, citas, fuentes y pasos visibles.
// La conversación se guarda por identidad, empresa y cierre: al cambiar de sesión no se ve la anterior.
import { $vista, S, api, clave, esc, errorHtml, fechaLarga, puede } from "../nucleo.js";

const conversaciones = new Map();   // clave de sesión → { id, mensajes: [{rol, html}] }
const claveSesion = () => `${S.usuario?.id}|${S.usuario?.organizacion_id}|${S.cierre}`;
function conversacion() {
  const k = claveSesion();
  if (!conversaciones.has(k)) conversaciones.set(k, { id: clave().replace(/[^\w-]/g, "").slice(0, 40), mensajes: [] });
  return conversaciones.get(k);
}
export function olvidarConversaciones() { conversaciones.clear(); capacidades = null; }
let capacidades = null;

// Enlaces que el perfil puede abrir (los permisos se aplican también a los enlaces).
const PERMISO_ENLACE = [["#/clientes/", "cartera.ver"], ["#/agenda", "cartera.ver"], ["#/finanzas", "finanzas.ver"], ["#/tareas", "tareas.ver"],
  ["#/tableros/operaciones", "tablero.operaciones"], ["#/tableros/ventas", "tablero.ventas"], ["#/pqrs/", null], ["#/pqrs", null], ["#/beneficios", null]];
function enlaceAutorizado(h) {
  if (!h || !h.startsWith("#/")) return null;
  const regla = PERMISO_ENLACE.find(([p]) => h.startsWith(p));
  if (!regla || !regla[1]) return h;
  return puede(regla[1]) ? h : null;
}

const HERRAMIENTAS = {
  resumen_cartera: () => "Resumen de la cartera", buscar_clientes: a => `Agenda${a.accion ? ` · ${a.accion}` : ""}`, ficha_cliente: a => `Ficha de ${a.cliente_id || "cliente"}`,
  ventas_o_compras_por_mes: a => `Serie de ${a.serie || "ventas"}${a.familia && a.familia !== "Total" ? ` · ${a.familia}` : ""}`, clientes_que_redujeron_compras: a => `Clientes ${a.mes_base || ""} → ${a.mes_comparado || ""}`,
  simular_tipo_de_cambio: a => `Simulador · ${a.variacion_pct ?? ""} %`, coberturas_por_vencer: () => "Coberturas", oportunidades_prioritarias: () => "Oportunidades",
  seguimientos_pendientes: () => "Seguimientos", indicadores_solicitudes: () => "Indicadores de solicitudes", definicion_de_indicador: a => `Glosario · ${a.nombre || ""}`,
  buscar_en_documentacion: () => "Documentación del proyecto", buscar_politicas: () => "Políticas vigentes", mis_solicitudes: () => "Tus solicitudes", mis_beneficios: () => "Tus beneficios",
};
const TIPO_FUENTE = { datos: "Datos del cierre", politica: "Política", proyecto: "Documentación del proyecto", solicitud: "Solicitud", beneficio: "Beneficios", definicion: "Glosario" };

// ---------------------------------------------------------------- Markdown seguro (subconjunto)
function enLinea(t, id) {
  return t.replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[(\d+)\]/g, (_, n) => `<button type="button" class="cita" data-msg="${id}" data-n="${n}" aria-label="Ver fuente ${n}">${n}</button>`);
}
export function markdown(texto, id = "m") {
  const lineas = esc(texto).split(/\r?\n/);
  const html = [];
  let lista = null, tabla = null, parrafo = [];
  const cerrarParrafo = () => { if (parrafo.length) { html.push(`<p>${enLinea(parrafo.join(" "), id)}</p>`); parrafo = []; } };
  const cerrarLista = () => { if (lista) { html.push(`<${lista.tipo}>${lista.items.map(i => `<li>${enLinea(i, id)}</li>`).join("")}</${lista.tipo}>`); lista = null; } };
  const cerrarTabla = () => {
    if (!tabla) return;
    const filas = tabla.filter(f => !/^\|?\s*:?-{2,}/.test(f)).map(f => f.replace(/^\||\|$/g, "").split("|").map(c => enLinea(c.trim(), id)));
    html.push(`<div class="tabla"><table><thead><tr>${filas[0].map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${filas.slice(1).map(f => `<tr>${f.map(c => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
    tabla = null;
  };
  for (const l of lineas) {
    const t = l.trim();
    if (/^\|.*\|$/.test(t)) { cerrarParrafo(); cerrarLista(); (tabla ||= []).push(t); continue; }
    cerrarTabla();
    let m;
    if (!t) { cerrarParrafo(); cerrarLista(); }
    else if (/^(-{3,}|\*{3,})$/.test(t)) { cerrarParrafo(); cerrarLista(); html.push("<hr>"); }
    else if ((m = t.match(/^#{1,4}\s+(.*)$/))) { cerrarParrafo(); cerrarLista(); html.push(`<h3>${enLinea(m[1], id)}</h3>`); }
    else if ((m = t.match(/^[-*•]\s+(.*)$/))) { cerrarParrafo(); if (!lista || lista.tipo !== "ul") { cerrarLista(); lista = { tipo: "ul", items: [] }; } lista.items.push(m[1]); }
    else if ((m = t.match(/^\d+[.)]\s+(.*)$/))) { cerrarParrafo(); if (!lista || lista.tipo !== "ol") { cerrarLista(); lista = { tipo: "ol", items: [] }; } lista.items.push(m[1]); }
    else { cerrarLista(); parrafo.push(t); }
  }
  cerrarParrafo(); cerrarLista(); cerrarTabla();
  return html.join("");
}

// ---------------------------------------------------------------- mensajes
function fuentesHtml(r, id) {
  const fs = [...(r.fuentes || [])].sort((a, b) => (b.citada - a.citada) || a.n - b.n);
  if (!fs.length) return "";
  const citadas = fs.filter(f => f.citada).length;
  return `<details class="chat-fuentes"><summary>${fs.length === 1 ? "1 fuente" : `${fs.length} fuentes`}${citadas && citadas < fs.length ? ` · ${citadas} citadas` : ""}</summary><ol>
    ${fs.map(f => {
      const enlace = enlaceAutorizado(f.enlace);
      return `<li id="fuente-${id}-${f.n}" class="${f.citada ? "" : "no-citada"}"><span class="cita-num">${f.n}</span><div><strong>${esc(f.titulo)}</strong>
        <div class="muted">${esc(TIPO_FUENTE[f.tipo] || f.tipo)}${f.localizador ? ` · ${esc(f.localizador)}` : ""}</div>
        ${f.extracto ? `<details><summary>Ver extracto</summary><blockquote>${esc(f.extracto)}</blockquote></details>` : ""}
        ${enlace ? `<a href="${esc(enlace)}">Abrir en la aplicación</a>` : f.enlace?.startsWith("/api/documentos/") ? `<button type="button" class="enlace" data-frag="${esc(f.enlace)}">Ver la sección citada</button><div class="frag"></div>` : ""}</div></li>`;
    }).join("")}</ol></details>`;
}

function respuestaAgente(r, id) {
  const pasos = r.pasos || [];
  return `<div class="chat-msg asistente" data-id="${id}"><div class="avatar" aria-hidden="true">J</div><div class="chat-cuerpo">
    ${pasos.length ? `<div class="chat-pasos" aria-label="Datos consultados">Consultó: ${pasos.map(p => `<span class="chip">${esc((HERRAMIENTAS[p.herramienta] || (() => p.herramienta))(p.argumentos || {}))}</span>`).join("")}</div>` : ""}
    <div class="chat-texto">${markdown(r.texto, id)}</div>
    ${r.cifras_sin_respaldo?.length ? `<p class="aviso-cifras">Revisa estas cifras: no aparecen tal cual en los datos consultados (${esc(r.cifras_sin_respaldo.join(", "))}). Pueden ser cálculos del asistente.</p>` : ""}
    ${fuentesHtml(r, id)}
    <div class="chat-acciones"><span class="muted">${r.corte ? `Datos hasta el ${esc(fechaLarga(r.corte))}` : ""}</span>
      ${r.registro_id ? `<button type="button" class="icono" data-calif="1" data-reg="${r.registro_id}" aria-label="Respuesta útil" title="Respuesta útil">👍</button><button type="button" class="icono" data-calif="0" data-reg="${r.registro_id}" aria-label="Respuesta incorrecta" title="Respuesta incorrecta">👎</button>` : ""}
      <button type="button" class="icono" data-copiar aria-label="Copiar respuesta" title="Copiar">⧉</button></div>
    ${!S.usuario.externo ? `<details class="tecnico"><summary>Detalle técnico</summary><p class="muted">${esc(r.version || "")} · ${esc(r.motor || "")} · ${r.latencia_ms ?? "—"} ms${pasos.length ? ` · ${esc(JSON.stringify(pasos))}` : ""}</p></details>` : ""}
  </div></div>`;
}

// Respuesta del modo básico (sin modelo de lenguaje): mismo formato de burbuja.
function respuestaBasica(r, id) {
  const ev = r.evidencia || {};
  const fuentes = (ev.fuentes || []).map((f, i) => ({ n: i + 1, tipo: f.titulo ? "politica" : "beneficio", titulo: f.titulo || f.beneficio_id, localizador: f.localizador || f.fuente || "", enlace: f.enlace, citada: true }));
  if (ev.detalle) fuentes.push({ n: fuentes.length + 1, tipo: "datos", titulo: "Detalle en la aplicación", localizador: ev.corte ? `datos hasta el ${fechaLarga(ev.corte)}` : "", enlace: ev.detalle, citada: true });
  return respuestaAgente({ ...r, fuentes, pasos: r.herramienta ? [{ herramienta: r.herramienta, argumentos: r.parametros || {} }] : [], corte: ev.corte }, id);
}

const burbujaUsuario = t => `<div class="chat-msg usuario"><div class="chat-cuerpo"><div class="chat-texto">${esc(t).replace(/\n/g, "<br>")}</div></div></div>`;

// ---------------------------------------------------------------- sugerencias por perfil
function sugerencias() {
  if (S.usuario.externo) return [["Tus solicitudes", ["¿En qué estado están mis solicitudes?", "¿Qué necesito para consultar un caso?"]],
    ["Tus beneficios", ["¿Qué beneficios tengo disponibles?", "¿Cómo pido el descuento por renovación anticipada?"]]];
  const g = [["Sobre el proyecto", ["¿Cómo calcula JACOMIND la probabilidad de compra y qué limitaciones tiene?", "¿Qué significa que un cliente esté «frío»?", "¿Cómo se publica un cierre mensual?"]]];
  if (puede("agente.datos")) {
    const datos = [];
    if (puede("cartera.ver")) datos.push("¿Qué clientes requieren revisión de cobertura y por qué?", "¿Qué compró DEMO01?");
    if (puede("finanzas.ver") || puede("tablero.gerencia")) datos.push("¿Por qué cayeron las ventas en el último mes?");
    if (puede("finanzas.ver")) datos.push("¿Cuánto costarían las compras en dólares si el dólar sube 8 %?");
    if (datos.length) g.push(["Analizar datos", datos]);
    const rec = [];
    if (puede("cartera.ver")) rec.push("¿Con qué clientes debería hablar primero esta semana?");
    if (puede("tablero.operaciones")) rec.push("¿Qué coberturas debo atender antes y qué recomiendas?");
    if (puede("finanzas.ver")) rec.push("Analiza las ventas por familia y recomienda acciones");
    if (rec.length) g.push(["Recomendaciones", rec]);
  } else if (puede("documentos.consultar")) g.push(["Políticas", ["¿Cuál es el descuento por renovación anticipada?", "¿Qué dice el manual sobre el plazo de respuesta?"]]);
  return g;
}

// ---------------------------------------------------------------- vista
export async function vistaAsistente() {
  const externo = S.usuario.externo;
  if (!capacidades) capacidades = await api("GET", "/api/asistente/capacidades").catch(() => ({ modo: "basico" }));
  const conv = conversacion();
  const modoAgente = capacidades.modo === "agente";
  $vista.innerHTML = `<section class="chat">
    <header class="chat-cabecera"><div><h1>${externo ? "Consulta tus beneficios o el estado de una solicitud" : "Asistente"}</h1>
      <p class="muted">${modoAgente ? (externo ? "Responde con la información de tu empresa y las políticas vigentes, y cita de dónde sale cada dato." : "Pregunta sobre el proyecto, analiza datos del cierre o pide recomendaciones. Cada dato lleva su fuente.")
        : "Modo básico: responde preguntas concretas con reglas (cliente, periodo o definición). El análisis libre necesita el modelo de lenguaje."}</p></div>
      <div class="fila"><span class="chip ${modoAgente ? "fuerte" : ""}" title="${esc(capacidades.llm || "")}">${modoAgente ? "Agente con IA" : "Modo básico"}</span>
      ${conv.mensajes.length ? '<button type="button" class="sec" id="nueva">Nueva conversación</button>' : ""}</div></header>
    <div class="chat-mensajes" id="chat" aria-live="polite">${conv.mensajes.length ? conv.mensajes.map(m => m.html).join("") : `<div class="chat-vacio">
      <div class="avatar grande" aria-hidden="true">J</div><p class="frase">¿En qué te ayudo?</p>
      <div class="chat-sugerencias">${sugerencias().map(([t, ps]) => `<div><h2>${esc(t)}</h2>${ps.map(p => `<button type="button" class="sugerencia" data-e="${esc(p)}">${esc(p)}</button>`).join("")}</div>`).join("")}</div></div>`}</div>
    <form id="f" class="chat-entrada"><label class="oculto-visual" for="p">Escribe tu pregunta</label>
      <textarea id="p" rows="1" maxlength="1000" placeholder="${externo ? "Pregunta por tus solicitudes o beneficios…" : "Pregunta, pide un análisis o una recomendación…"}"></textarea>
      <button id="enviar" aria-label="Enviar pregunta">Enviar</button></form>
    <p class="muted chat-nota">Enter envía · Mayús + Enter salta de línea · ${externo ? "Solo ve información de tu empresa." : "Las recomendaciones requieren decisión humana."}</p></section>`;
  const chat = document.getElementById("chat"), ta = document.getElementById("p");
  chat.scrollTop = chat.scrollHeight;
  enlazarMensajes(chat);
  const k = claveSesion();
  const enviar = async pregunta => {
    if (!pregunta.trim() || ta.disabled) return;
    const c = conversacion();
    if (!c.mensajes.length) chat.innerHTML = "";
    c.mensajes.push({ rol: "usuario", html: burbujaUsuario(pregunta) });
    chat.insertAdjacentHTML("beforeend", burbujaUsuario(pregunta) + `<div class="chat-msg asistente pensando" id="pensando"><div class="avatar" aria-hidden="true">J</div><div class="chat-cuerpo"><span class="puntos" aria-label="Consultando"><i></i><i></i><i></i></span> <span class="muted">Consultando datos y fuentes…</span></div></div>`);
    chat.scrollTop = chat.scrollHeight; ta.value = ""; ta.style.height = ""; ta.disabled = true; document.getElementById("enviar").disabled = true;
    const id = `m${c.mensajes.length}`;
    let html;
    try {
      const r = await api("POST", "/api/asistente", { pregunta, cierre: S.cierre, conversacion: c.id });
      html = r.modo === "agente" ? respuestaAgente(r, id) : respuestaBasica(r, id);
      if (r.aviso) html = `<p class="estado">${esc(r.aviso)}</p>` + html;
    } catch (e) { html = `<div class="chat-msg asistente"><div class="avatar" aria-hidden="true">J</div><div class="chat-cuerpo">${errorHtml(e)}</div></div>`; }
    (conversaciones.get(k) || c).mensajes.push({ rol: "asistente", html });
    if (location.hash.startsWith("#/asistente") && claveSesion() === k) vistaAsistente().then(() => document.getElementById("p")?.focus());
  };
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); enviar(ta.value); });
  ta.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(ta.value); } });
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`; });
  $vista.querySelectorAll("[data-e]").forEach(b => b.addEventListener("click", () => enviar(b.dataset.e)));
  document.getElementById("nueva")?.addEventListener("click", async () => {
    const c = conversacion();
    await api("DELETE", `/api/asistente/conversaciones/${encodeURIComponent(c.id)}?cierre=${encodeURIComponent(S.cierre)}`).catch(() => {});
    conversaciones.delete(k); vistaAsistente();
  });
  ta.focus();
}

function enlazarMensajes(chat) {
  chat.addEventListener("click", async e => {
    const cita = e.target.closest(".cita");
    if (cita) {
      const li = document.getElementById(`fuente-${cita.dataset.msg}-${cita.dataset.n}`);
      if (li) { li.closest("details").open = true; li.scrollIntoView({ block: "nearest", behavior: "smooth" }); li.classList.add("resaltada"); setTimeout(() => li.classList.remove("resaltada"), 1600); }
      return;
    }
    const frag = e.target.closest("[data-frag]");
    if (frag) {
      const dest = frag.nextElementSibling;
      try { const f = await api("GET", frag.dataset.frag); dest.innerHTML = `<blockquote>${esc(f.texto)}</blockquote>`; } catch (err) { dest.innerHTML = errorHtml(err); }
      return;
    }
    const calif = e.target.closest("[data-calif]");
    if (calif) {
      await api("POST", `/api/asistente/${calif.dataset.reg}/calificar`, { correcta: calif.dataset.calif === "1" }).catch(() => {});
      calif.parentElement.querySelectorAll("[data-calif]").forEach(b => b.classList.toggle("elegido", b === calif));
      return;
    }
    if (e.target.closest("[data-copiar]")) {
      const texto = e.target.closest(".chat-cuerpo").querySelector(".chat-texto").innerText;
      navigator.clipboard?.writeText(texto);
      e.target.textContent = "✓"; setTimeout(() => { e.target.textContent = "⧉"; }, 1200);
    }
  });
}
