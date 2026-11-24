// Núcleo compartido: estado de la sesión, acceso a la API, enrutado, preferencias de lectura y formatos en lenguaje de negocio.
import { inicioPara } from "./navegacion.js";

export const $vista = document.getElementById("vista");
export const S = { fuente: null, usuario: null, apiDisponible: false, estadoApi: null, local: null, cierre: "activo", seq: 0, ubicacion: null, aviso: null };
try { S.fuente = localStorage.getItem("jacomind.fuente"); } catch { /* sin almacenamiento */ }

export const FUENTES = {
  servidor: { titulo: "Entrar con mi perfil", corto: "Información publicada", explica: "Clientes, seguimientos, finanzas, solicitudes y modelos con los permisos de tu perfil. Requiere iniciar sesión." },
  salida: { titulo: "Consultar una agenda guardada en este equipo", corto: "Agenda local", explica: "Solo la lista de clientes y su resumen. Sin historial detallado ni inicio de sesión." },
  ejemplo: { titulo: "Practicar con un ejemplo de ocho clientes", corto: "Ejemplo de práctica (8 clientes)", explica: "Ejemplo ficticio y reducido para aprender a leer la pantalla. Es distinto de la demostración completa." },
};

// ---------------------------------------------------------------- preferencias de lectura (persistentes, sin datos sensibles)
export const TAMANOS = { normal: "Normal", grande: "Grande", "muy-grande": "Muy grande" };
export const TEMAS = { claro: "Claro", oscuro: "Oscuro", sistema: "Según el equipo" };
const leer = (k, def) => { try { return localStorage.getItem(k) || def; } catch { return def; } };
const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch { /* sin almacenamiento */ } };
export const preferencias = () => ({ tamano: leer("jacomind.tamano", "normal"), tema: leer("jacomind.tema", "claro") });
export function aplicarPreferencias({ tamano, tema } = preferencias()) {
  const raiz = document.documentElement;
  raiz.dataset.tamano = TAMANOS[tamano] ? tamano : "normal";
  if (tema === "oscuro") raiz.dataset.theme = "dark";
  else if (tema === "sistema") delete raiz.dataset.theme;
  else raiz.dataset.theme = "light";
}
export function cambiarPreferencia(k, v) { guardar(`jacomind.${k}`, v); aplicarPreferencias(); }
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

// Inicio propio de cada perfil (V01): se calcula desde capacidades en navegacion.js.
export const inicioDePerfil = () => inicioPara(S.usuario, puede);

// ---------------------------------------------------------------- texto seguro y estados
export const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function estadoHtml(tipo, texto) {
  const cargando = tipo === "" && /^Cargando|…$/.test(String(texto));
  return `<div class="estado ${tipo}${cargando ? " cargando" : ""}" role="${tipo === "error" ? "alert" : "status"}">${cargando ? '<span class="girando" aria-hidden="true"></span>' : ""}${esc(texto)}</div>`;
}
/** Explica qué no se pudo hacer y cómo seguir. `reintentar` añade un botón que vuelve a pedir la pantalla. */
export function errorHtml(e, { reintentar = false } = {}) {
  const det = e.datos?.detalle?.errores ? `<ul>${e.datos.detalle.errores.slice(0, 8).map(x => `<li><code>${esc(x)}</code></li>`).join("")}</ul>` : "";
  const red = e instanceof TypeError || e.status === undefined && /fetch|network/i.test(e.message || "");
  const titulo = e.status === 403 ? "Tu perfil no tiene permiso para esta información."
    : e.status === 404 ? "No encontramos lo que buscas."
    : e.status === 409 && /conflicto/.test(e.datos?.error || "") ? "Otra persona cambió esta información mientras la tenías abierta."
    : e.status === 409 ? "Todavía no se puede hacer este paso."
    : red ? "No hay conexión con el servidor de JACOMIND." : "No se pudo completar la acción.";
  const msg = e.message && !red && e.message !== titulo ? `<p>${esc(e.message)}</p>` : "";
  const ayuda = red ? "<p>Revisa que la aplicación siga abierta en este equipo y vuelve a intentarlo. Lo que escribiste se conserva.</p>" : "";
  return `<div class="estado error" role="alert"><p><strong>${esc(titulo)}</strong></p>${msg}${det}${ayuda}${reintentar ? '<p><button type="button" class="sec" data-reintentar>Volver a intentar</button></p>' : ""}</div>`;
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
const ZONA = "America/Bogota";
/** Instante en la zona horaria del negocio (Colombia). Las fechas de calendario (AAAA-MM-DD) no se convierten. */
export function fechaHora(ts) {
  if (!ts) return "—";
  const t = String(ts);
  if (!/T|\s\d{2}:/.test(t) || !/[zZ]|[+-]\d{2}:?\d{2}$/.test(t)) return `${fechaLarga(t)}${t.length > 10 ? `, ${t.slice(11, 16)}` : ""}`;
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return fechaLarga(t);
  const p = Object.fromEntries(new Intl.DateTimeFormat("es-CO", { timeZone: ZONA, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(d).map(x => [x.type, x.value]));
  return `${fechaLarga(`${p.year}-${p.month}-${p.day}`)}, ${p.hour}:${p.minute}`;
}
/** «Incluye información hasta el …»: sustituye al término «corte». */
export const incluye = corte => corte ? `Datos hasta el ${fechaLarga(corte)}` : "Sin fecha de los datos";
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
/** Nombre legible de un segmento sin diccionario autorizado: «seg_2» → «Segmento 2». No inventa perfiles. */
export const nombreSegmento = s => { const m = /^seg_(\d+)$/i.exec(String(s ?? "")); return m ? `Segmento ${m[1]}` : (s ?? ""); };
export const plural = (n, uno, varios) => `${num(n)} ${n === 1 ? uno : varios}`;

// ---------------------------------------------------------------- glosario visible junto al dato
export const GLOSARIO = {
  frio: "Han pasado al menos 90 días desde su última compra, contados hasta la fecha de los datos. Pudo haber comprado con frecuencia antes de esa pausa.",
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
