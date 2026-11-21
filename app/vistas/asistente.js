// Asistente del equipo interno y de la empresa (entradas 15 y 16 del plan).
// La conversación se guarda por identidad, organización y cierre: al cambiar de sesión no se ve la anterior.
import { $vista, MESES, S, api, cop, esc, errorHtml, fechaLarga, millones, num, puede } from "../nucleo.js";
import { barras, detalleTecnico, verDatos } from "../ui.js";

const conversaciones = new Map();
const claveConversacion = () => `${S.usuario?.id}|${S.usuario?.organizacion_id}|${S.cierre}`;
const conversacion = () => { const k = claveConversacion(); if (!conversaciones.has(k)) conversaciones.set(k, []); return conversaciones.get(k); };
export function olvidarConversaciones() { conversaciones.clear(); contextoEjemplos = null; }

// Enlaces de detalle que el perfil puede abrir (los permisos se aplican también a los enlaces).
const PERMISO_ENLACE = [["#/clientes/", "cartera.ver"], ["#/agenda", "cartera.ver"], ["#/finanzas", "finanzas.ver"], ["#/tareas", "tareas.ver"], ["#/pqrs/", "pqrs.ver_propias"]];
function enlaceAutorizado(h) {
  if (!h || !h.startsWith("#/")) return null;
  const regla = PERMISO_ENLACE.find(([p]) => h.startsWith(p));
  if (!regla) return h;
  return puede(regla[1]) || (regla[0] === "#/pqrs/" && puede("pqrs.gestionar")) ? h : null;
}

let contextoEjemplos = null;
async function ejemplos() {
  if (S.usuario.externo) return ["¿Cuál es el estado de mi caso?", "¿Qué beneficios tengo disponibles?", "¿Cómo solicito el descuento por renovación anticipada?"];
  if (!puede("agente.datos")) return ["¿Cuál es el descuento por renovación anticipada?", "¿Qué dice el manual sobre el plazo de respuesta de una PQRS?", "¿Qué beneficios hay para clientes recurrentes?"];
  if (!contextoEjemplos || contextoEjemplos.clave !== claveConversacion()) {
    const ctx = { clave: claveConversacion(), cliente: null, corte: null };
    try {
      if (puede("cartera.ver")) {
        const a = await api("GET", `/api/cierres/${S.cierre}/agenda?tam=1`);
        ctx.cliente = a.items[0]?.cliente_id || null; ctx.corte = a.corte;
      } else if (puede("finanzas.ver")) ctx.corte = (await api("GET", `/api/cierres/${S.cierre}/resumen`)).cierre.corte;
    } catch { /* sin cierre publicado: ejemplos genéricos */ }
    contextoEjemplos = ctx;
  }
  const { cliente, corte } = contextoEjemplos;
  const ej = [];
  if (cliente) ej.push(`¿Qué compró ${cliente}?`);
  if (corte) {
    const anio = Number(corte.slice(0, 4)), mes = Number(corte.slice(5, 7));
    const ant = mes === 1 ? [12, anio - 1] : [mes - 1, anio];
    const ant2 = ant[0] === 1 ? [12, ant[1] - 1] : [ant[0] - 1, ant[1]];
    ej.push(`Ventas de ${MESES[mes - 1]} de ${anio}`);
    if (puede("finanzas.ver")) ej.push(`¿A qué proveedores compramos en ${MESES[ant[0] - 1]} de ${ant[1]}?`);
    if (puede("cartera.ver")) ej.push(`¿Qué clientes redujeron compras entre ${MESES[ant2[0] - 1]} de ${ant2[1]} y ${MESES[ant[0] - 1]} de ${ant[1]}?`);
  }
  ej.push("¿Qué significa frío?");
  return ej;
}

// ---------------------------------------------------------------- presentación de respuestas
const ETIQUETA_ESTADO = { aclaracion: "Necesito un dato más", no_autorizado: "Fuera de tu acceso", sin_datos: "Sin datos suficientes", no_encontrado: "No encontrado", incertidumbre: "Requiere revisión de Atención", fuera_de_alcance: "No disponible" };
const COLUMNAS = { cliente_id: "Cliente", proveedor: "Proveedor", operaciones: "Operaciones", importe_cop: "Importe", base_cop: "Mes base", comparado_cop: "Mes comparado", cambio_cop: "Cambio", cambio_pct: "Cambio %", periodo: "Mes", valor_cop: "Valor", producto: "Producto", tipo: "Tipo", motivos: "Motivos", probabilidad: "Estimación", ultima: "Última", radicado: "Número", estado: "Estado", titulo: "Beneficio", vigencia_hasta: "Hasta" };
const celda = (k, v) => v == null ? "—" : Array.isArray(v) ? esc(v.join(", ")) : /_cop$/.test(k) ? cop(v) : k === "probabilidad" ? `${num(v * 100)} %` : typeof v === "number" ? num(v) : esc(v);

function tablaResultado(res) {
  const filas = Array.isArray(res) ? res : Array.isArray(res?.meses) ? res.meses : null;
  if (!filas?.length || typeof filas[0] !== "object") return null;
  const claves = Object.keys(COLUMNAS).filter(k => filas.some(f => k in f));
  if (!claves.length) return null;
  return { cabeceras: claves.map(k => COLUMNAS[k]), numericas: new Set(claves.map((k, i) => /_cop$|operaciones|pct/.test(k) ? i : -1).filter(i => i >= 0)), filas: filas.slice(0, 20).map(f => claves.map(k => celda(k, f[k]))) };
}

/** Comparación de dos valores verificables → dos barras. */
function comparacion(r) {
  const res = r.resultado;
  if (r.herramienta === "clientes_reducen" && Array.isArray(res) && res.length === 1) {
    const x = res[0], f = r.evidencia?.filtros || {};
    return barras([{ etiqueta: f.base || "Mes base", valor: x.base_cop, texto: millones(x.base_cop) }, { etiqueta: f.comparado || "Mes comparado", valor: x.comparado_cop, texto: millones(x.comparado_cop) }], { etiquetaAria: `Compras de ${x.cliente_id} en los dos meses` });
  }
  if (r.herramienta === "ventas_periodo" && res?.meses?.length === 2) {
    return barras(res.meses.map(m => ({ etiqueta: m.periodo, valor: m.valor_cop || 0, texto: m.valor_cop == null ? "sin dato" : millones(m.valor_cop) })), { etiquetaAria: "Ventas de los dos meses" });
  }
  return "";
}

function alcance(ev) {
  const f = ev.filtros || {};
  const p = [];
  if (f.periodo) p.push(`periodo ${String(f.periodo).replace("..", " a ")}`);
  if (f.base && f.comparado) p.push(`${f.base} frente a ${f.comparado}`);
  if (f.familia && f.familia !== "Total") p.push(`familia ${f.familia}`);
  if (ev.corte) p.push(`datos hasta el ${fechaLarga(ev.corte)}`);
  if (ev.unidad) p.push(`unidad: ${ev.unidad}`);
  return p.join(" · ");
}

function fuentesTexto(ev) {
  return (ev.fuentes || []).map(f => f.titulo ? `${esc(f.titulo)}, versión ${f.version}, ${esc(f.localizador)}` : f.beneficio_id ? `${esc(f.beneficio_id)} · política ${esc(f.fuente)}` : "").filter(Boolean).join("; ");
}

function respuestaInterna(r) {
  const ev = r.evidencia || {};
  const tabla = tablaResultado(r.resultado);
  const enlace = enlaceAutorizado(ev.detalle);
  const fuentes = fuentesTexto(ev);
  const sustento = tabla || enlace || fuentes ? verDatos({ titulo: "Ver los datos que sustentan esta respuesta", tabla,
    fuente: fuentes || (ev.cierre_id ? `Cierre ${esc(ev.cierre_id)}` : ""), filtros: esc(alcance(ev)),
    extra: enlace ? `<p><a href="${esc(enlace)}">Abrir el detalle en la aplicación</a></p>` : "" }) : "";
  return `<div class="burbuja">${r.estado !== "ok" && ETIQUETA_ESTADO[r.estado] ? `<span class="chip">${esc(ETIQUETA_ESTADO[r.estado])}</span> ` : ""}<div>${esc(r.texto)}</div>
    ${alcance(ev) ? `<div class="muted">${esc(alcance(ev))}</div>` : ""}${comparacion(r)}${sustento}
    ${detalleTecnico(`<dl class="meta-datos"><dt>Herramienta</dt><dd>${esc(r.herramienta || "—")}</dd><dt>Motor</dt><dd>${esc(r.motor || "—")}</dd><dt>Versión</dt><dd>${esc(r.version || "—")}</dd>
      <dt>Filtros originales</dt><dd><code>${esc(JSON.stringify(ev.filtros || {}))}</code></dd><dt>Parámetros</dt><dd><code>${esc(JSON.stringify(r.parametros || {}))}</code></dd></dl>`)}</div>`;
}

function respuestaEmpresa(r) {
  const ev = r.evidencia || {};
  const enlace = enlaceAutorizado(ev.detalle);
  const fuentes = fuentesTexto(ev);
  let ayuda = "";
  if (r.estado === "no_encontrado" && r.herramienta === "pqrs") ayuda = '<p class="muted">Revisa el número de seguimiento (tiene la forma PQRS-AAAAMMDD-NNNNN) o búscalo en <a href="#/pqrs">Solicitudes de mi empresa</a>.</p>';
  else if (["sin_datos", "incertidumbre", "aclaracion"].includes(r.estado)) ayuda = '<p class="muted">Si necesitas una respuesta sobre tu caso, <a href="#/pqrs?crear=1">crea una solicitud</a> y Atención la revisará.</p>';
  else if (r.herramienta === "pqrs" && !r.parametros?.radicado && r.estado === "ok") ayuda = '<p class="muted">Para ver el detalle, escribe el número de seguimiento del caso.</p>';
  return `<div class="burbuja"><div>${esc(r.texto)}</div>${enlace ? `<p><a href="${esc(enlace)}">Abrir la solicitud</a></p>` : ""}${fuentes ? `<p class="muted">Fuente: ${fuentes}</p>` : ""}${ayuda}</div>`;
}

// ---------------------------------------------------------------- vista
export async function vistaAsistente() {
  const externo = S.usuario.externo;
  const lista = await ejemplos();
  const conv = conversacion();
  $vista.innerHTML = externo
    ? `<h1>Consulta tus beneficios o el estado de una solicitud</h1><p class="muted">Responde con la información de tu empresa y las políticas vigentes. Si no encuentra el dato, te dirá qué necesita o te remitirá a Atención.</p>`
    : `<h1>Asistente</h1><p class="muted">Respuestas breves con su periodo y alcance. Las cifras salen de consultas de solo lectura sobre el cierre; comprueba siempre los datos que las sustentan.</p>`;
  $vista.innerHTML += `<div id="chat" aria-live="polite">${conv.map(m => m.html).join("")}</div>
  <form id="f" class="fila"><label class="oculto-visual" for="p">Pregunta</label><input id="p" style="flex:1;min-width:220px" maxlength="1000" placeholder="${externo ? "p. ej. ¿Cuál es el estado de PQRS-20261101-00001?" : "Escribe tu pregunta"}" autocomplete="off"><button>Preguntar</button></form>
  <p class="muted" style="margin-top:8px">Puedes preguntar, por ejemplo:</p><div class="fila">${lista.map(e => `<button class="sec" type="button" data-e="${esc(e)}">${esc(e)}</button>`).join("")}</div>
  ${conv.length ? '<p><button type="button" class="enlace" id="limpiar">Borrar esta conversación</button></p>' : ""}`;
  const k = claveConversacion();
  const enviar = async pregunta => {
    conv.push({ html: `<div class="burbuja yo">${esc(pregunta)}</div>` });
    vistaAsistenteParcial();
    let html;
    try {
      const r = await api("POST", "/api/asistente", { pregunta, cierre: S.cierre });
      html = externo ? respuestaEmpresa(r) : respuestaInterna(r);
    } catch (e) { html = errorHtml(e); }
    (conversaciones.get(k) || []).push({ html });
    if (location.hash.startsWith("#/asistente") && claveConversacion() === k) vistaAsistente();
  };
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const p = document.getElementById("p").value.trim(); if (p) enviar(p); });
  $vista.querySelectorAll("[data-e]").forEach(b => b.addEventListener("click", () => enviar(b.dataset.e)));
  document.getElementById("limpiar")?.addEventListener("click", () => { conversaciones.delete(k); vistaAsistente(); });
  document.getElementById("p").focus();
}
function vistaAsistenteParcial() {
  const chat = document.getElementById("chat");
  if (chat) chat.innerHTML = conversacion().map(m => m.html).join("") + '<div class="burbuja muted">Consultando…</div>';
}
