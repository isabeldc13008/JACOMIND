// Núcleo compartido: estado de la sesión, acceso a la API, enrutado y formatos en lenguaje de negocio.

export const $vista = document.getElementById("vista");
export const S = { fuente: null, usuario: null, apiDisponible: false, estadoApi: null, local: null, cierre: "activo", seq: 0 };
try { S.fuente = localStorage.getItem("jacomind.fuente"); } catch { /* sin almacenamiento */ }

export const FUENTES = {
  servidor: { titulo: "Trabajar con el cierre publicado", corto: "Cierre publicado", explica: "Agenda, fichas, tableros, seguimientos, solicitudes y finanzas con tu perfil. Requiere iniciar sesión." },
  salida: { titulo: "Consultar una agenda local", corto: "Agenda local", explica: "Lee la agenda que generaste en este equipo. Solo agenda y resumen de cada cliente; sin historial detallado ni sesión." },
  ejemplo: { titulo: "Explorar una demostración", corto: "Demostración (datos de práctica)", explica: "Agenda ficticia de ocho clientes para aprender a leer la pantalla. Nada de lo que veas corresponde a clientes reales." },
};
export const URL_FUENTE = { salida: "/salida/agenda.json", ejemplo: "/app/fixtures/agenda.json" };

// ---------------------------------------------------------------- API y sesión
export async function api(metodo, ruta, cuerpo) {
  const r = await fetch(ruta, {
    method: metodo, credentials: "same-origin",
    headers: { "X-Jacomind": "1", ...(cuerpo ? { "Content-Type": "application/json" } : {}), ...(cuerpo && cuerpo.__clave ? { "Idempotency-Key": cuerpo.__clave } : {}) },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const tipo = r.headers.get("content-type") || "";
  const datos = tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw Object.assign(new Error(datos.mensaje || `Error ${r.status}`), { status: r.status, datos });
  return datos;
}
export const puede = a => !!S.usuario && S.usuario.acciones.includes(a);
export const enServidor = () => S.fuente === "servidor";
export const tieneRol = r => !!S.usuario && S.usuario.roles.includes(r);

export function ruta() {
  const [camino, qs] = (location.hash.slice(1) || "/agenda").split("?");
  return { partes: camino.split("/").filter(Boolean).map(decodeURIComponent), q: new URLSearchParams(qs || "") };
}
let renderizar = () => {};
export function alRenderizar(fn) { renderizar = fn; }
export function ir(hash) { if (location.hash !== hash) location.hash = hash; else renderizar(); }
export const nuevoTurno = () => ++S.seq;           // evita que una respuesta antigua reemplace una nueva
export const vigente = t => t === S.seq;
export const clave = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

// Entrada propuesta por perfil (entrada 1 del plan).
export function inicioDePerfil() {
  if (!S.usuario) return "#/inicio";
  if (S.usuario.externo) return "#/beneficios";
  if (tieneRol("gerencia")) return "#/tableros/gerencia";
  if (tieneRol("ventas")) return "#/agenda";
  if (tieneRol("finanzas")) return "#/finanzas";
  if (tieneRol("atencion")) return "#/pqrs";
  if (tieneRol("operaciones")) return "#/bienvenida";
  return puede("cartera.ver") ? "#/agenda" : "#/inicio";
}

// ---------------------------------------------------------------- texto seguro y estados
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function estadoHtml(tipo, texto) { return `<div class="estado ${tipo}" role="${tipo === "error" ? "alert" : "status"}">${esc(texto)}</div>`; }
export function errorHtml(e) {
  const det = e.datos?.detalle?.errores ? `<ul>${e.datos.detalle.errores.slice(0, 8).map(x => `<li><code>${esc(x)}</code></li>`).join("")}</ul>` : "";
  return `<div class="estado error" role="alert">${esc(e.message)}${det}</div>`;
}

// ---------------------------------------------------------------- formatos
const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const fmtCop = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const fmtEntero = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 });
export const num = x => x == null ? "—" : fmt.format(x);
/** Importe exacto con decimales (tablas y verificación). */
export const cop = x => x == null ? "—" : `${fmtCop.format(x)} COP`;
/** Importe legible: millones con dos decimales desde 1 millón; importe completo por debajo. */
export function millones(x, { unidad = true } = {}) {
  if (x == null) return "—";
  if (Math.abs(x) >= 1e6) return `${fmtCop.format(x / 1e6)} millones${unidad ? " de COP" : ""}`;
  return `${fmtEntero.format(x)}${unidad ? " COP" : ""}`;
}
export const conSigno = x => x == null ? "—" : `${x < 0 ? "−" : "+"}${millones(Math.abs(x))}`;
export const pct = p => { if (p == null) return null; const v = Math.round(p * 1000) / 10; return `${(Number.isInteger(v) ? v.toFixed(0) : v.toFixed(1)).replace(".", ",")} %`; };
export const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
export function mesLargo(periodo) {
  if (!periodo) return "—";
  const [a, m] = String(periodo).slice(0, 7).split("-");
  return `${MESES[Number(m) - 1]} de ${a}`;
}
export function mesCorto(periodo) {
  const [a, m] = String(periodo).slice(0, 7).split("-");
  return `${MESES[Number(m) - 1].slice(0, 3)} ${a.slice(2)}`;
}
export function fechaLarga(f) {
  if (!f) return "—";
  const [a, m, d] = String(f).slice(0, 10).split("-");
  return `${Number(d)} de ${MESES[Number(m) - 1]} de ${a}`;
}
export const fechaHora = ts => ts ? `${fechaLarga(ts)}, ${String(ts).slice(11, 16)}` : "—";
/** «Incluye información hasta el …»: sustituye al término «corte». */
export const incluye = corte => corte ? `Incluye información hasta el ${fechaLarga(corte)}` : "Sin fecha de corte";
export function diasEntre(desde, hasta) {
  return Math.round((new Date(hasta + "T00:00:00Z") - new Date(desde + "T00:00:00Z")) / 86400000);
}
/** «vence en 20 días» / «venció hace 60 días» / «vence el día del cierre», siempre relativo al cierre. */
export function relativoVencimiento(dias) {
  if (dias == null) return "—";
  if (dias === 0) return "vence el día del cierre";
  if (dias > 0) return `vence en ${dias} ${dias === 1 ? "día" : "días"}`;
  return `venció hace ${-dias} ${dias === -1 ? "día" : "días"}`;
}
export const plural = (n, uno, varios) => `${num(n)} ${n === 1 ? uno : varios}`;

// ---------------------------------------------------------------- glosario visible junto al dato
export const GLOSARIO = {
  frio: "Han pasado al menos 90 días desde su última compra al cierre. Pudo haber comprado con frecuencia antes de esa pausa.",
  umbral: "Nivel de probabilidad a partir del cual se sugiere revisar una posible recompra.",
  frecuente: "Compra con regularidad según su historial. Puede coincidir con 90 días o más sin comprar.",
};
/** Texto de la estimación: distingue sin compras, falta de estimación y 0 % estimado. */
export function textoEstimacion(c) {
  if (c.sin_historial || c.ultima_compra === null) return "Sin compras registradas";
  if (c.prob_compra_30d == null) return "Hay compras, pero falta la estimación";
  if (c.prob_compra_30d === 0) return "El modelo estimó 0 %";
  return pct(c.prob_compra_30d);
}
