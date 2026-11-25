// Textos redactados por IA (api/narrativas.py): se piden después de pintar la pantalla y nunca la bloquean.
// Si la IA no está disponible o no tiene cupo, la pantalla conserva el texto original y lo dice en una línea.
import { api, esc, vigente } from "./nucleo.js";

const ESPERA_MS = 6000, INTENTOS = 25;

/** Pide el texto y vuelve a preguntar mientras se redacta. ``pintar(r)`` recibe {estado, texto?, motivo?}. */
export async function pedirNarrativa(ruta, turno, pintar) {
  for (let i = 0; i < INTENTOS; i++) {
    let r;
    try { r = await api("GET", ruta); } catch { if (vigente(turno)) pintar({ estado: "no_disponible", motivo: "No se pudo pedir el texto redactado." }); return; }
    if (!vigente(turno)) return;
    pintar(r);
    if (r.estado !== "generando") return;
    await new Promise(ok => setTimeout(ok, ESPERA_MS));
    if (!vigente(turno)) return;
  }
  pintar({ estado: "no_disponible", motivo: "La redacción tardó demasiado; se muestra el texto original." });
}

/** Pie común: qué modelo lo redactó y que hay que revisarlo. */
export const pieIA = r => `<p class="ia-pie"><span class="sello sello-ia">Redactado por IA</span> ${esc(r.nombre_modelo || r.modelo || "")} · a partir de los datos de esta pantalla. Revísalo antes de usarlo; no es un dato nuevo.</p>`;

/** Estado mientras no hay texto (redactando, sin cupo o desactivado). */
export const estadoIA = r => r.estado === "generando"
  ? `<p class="ia-estado" role="status"><span class="ia-pulso" aria-hidden="true"></span>Redactando con IA… Puedes seguir usando la pantalla.</p>`
  : r.estado === "no_aplica" ? "" : `<p class="ia-estado muted">${esc(r.motivo || "Texto de IA no disponible.")}</p>`;
