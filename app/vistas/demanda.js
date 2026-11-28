// V14 Pronóstico de demanda (M5, en uso): histórico observado y estimación de los próximos meses, con banda solo cuando
// la publicación la trae. Distingue meses incompletos o no observables (huecos, nunca cero) y no presenta MAE como confianza.
import { $vista, cop, api, errorHtml, esc, estadoHtml, ir, mesLargo, millones, nuevoTurno, num, plural, puede, ruta, vigente } from "../nucleo.js";
import { pestanasFinanzas } from "./finanzas.js";
import { activarTooltips, avisoPrueba, ctxDatos, detalleTecnico, encabezado, enPrueba, graficoLinea, hallazgo, indicadores, tablaHtml, vacio } from "../ui.js";

const METODO = { ultimo: "Repetir el último mes (referencia)", media_movil_3: "Promedio de los últimos 3 meses (referencia)", ses: "Suavizamiento exponencial (candidato)",
  holt_amortiguado: "Holt amortiguado (candidato)", suma_de_familias: "Suma de las familias", sin_historia: "Sin historia suficiente" };
const DECISION = { referencia_conservada: "Se mantiene la referencia", candidato_exploratorio_favorable: "Candidato con resultado exploratorio favorable",
  rechazado: "Candidato rechazado", inconcluso: "Inconcluso", sin_historia: "Sin historia o datos suficientes" };
const ESTADO_MES = { completo: "Observado", incompleto: "Mes incompleto", no_observable: "No observable", sin_cobertura: "Sin cobertura" };
const TITULO = "Pronóstico de demanda";

/** Nombre comprensible de una serie; el identificador técnico queda en el detalle. */
export function nombreSerie(id) {
  const [tipo, cual] = String(id).split(":");
  if (tipo === "ventas_cop") return cual === "Total" ? "Ventas totales (en pesos)" : `Ventas de la familia ${cual} (en pesos)`;
  if (tipo === "ventas_unidades") return `Unidades vendidas del producto ${cual}`;
  if (tipo?.startsWith("compras")) return cual === "Total" ? "Compras totales (en pesos)" : `Compras de ${cual} (en pesos)`;
  return id;
}

export async function vistaDemanda() {
  const { q } = ruta();
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-dem")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando el pronóstico…")}`;
  let d;
  try { d = await api("GET", `/api/demanda${q.get("serie") ? `?serie=${encodeURIComponent(q.get("serie"))}` : ""}`); }
  catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Pronóstico no disponible: no hay una publicación de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const esCop = d.serie_id.startsWith("ventas_cop") || d.serie_id.startsWith("compras");
  const unidad = d.pronosticos[0]?.unidad || (esCop ? "COP" : "unidades");
  const corto = v => v == null ? "—" : esCop ? millones(v) : `${num(Math.round(v * 10) / 10)} ${unidad === "unidades" ? "unidades" : esc(unidad)}`;
  const exacto = v => v == null ? "—" : esCop ? cop(v) : `${num(v)} ${unidad === "unidades" ? "unidades" : esc(unidad)}`;
  const todo = q.get("historico") === "todo";
  const cal = todo ? d.calendario : d.calendario.slice(-12);
  const hist = cal.map(c => ({ periodo: c.periodo, valor: c.estado === "completo" ? c.valor : null }));
  const conValor = d.pronosticos.filter(p => p.valor != null);
  const proy = d.pronosticos.map(p => ({ periodo: p.periodo_objetivo, valor: p.valor, inferior: p.banda_inferior, superior: p.banda_superior }));
  const huecos = cal.filter(c => c.estado !== "completo");
  const ultimo = [...d.calendario].reverse().find(c => c.estado === "completo");
  const p1 = conValor[0];
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/demanda${n.toString() ? `?${n}` : ""}`; };
  const grupos = [["Ventas en pesos", d.series.filter(s => s.startsWith("ventas_cop"))], ["Unidades por producto", d.series.filter(s => s.startsWith("ventas_unidades"))], ["Compras", d.series.filter(s => s.startsWith("compras"))]].filter(([, l]) => l.length);
  const tabla = {
    cabeceras: ["Mes", "Tipo", `Valor (${esCop ? "COP" : unidad})`, "Método", "Error medio en meses ya conocidos", "Banda"], numericas: new Set([2]),
    filas: [
      ...cal.map(c => [esc(mesLargo(c.periodo)), esc(ESTADO_MES[c.estado] || c.estado), c.estado === "completo" ? exacto(c.valor) : `Sin dato: ${esc(c.motivo || "no observable")}`, "Dato observado", "—", "—"]),
      ...d.pronosticos.map(p => {
        const dec = d.decisiones?.[String(p.horizonte_meses)];
        return [`${esc(mesLargo(p.periodo_objetivo))}<span class="muted">a ${plural(p.horizonte_meses, "mes", "meses")} del último mes completo</span>`, "Estimado (resultado pendiente)",
          p.valor == null ? "Sin pronóstico" : `<strong>${exacto(p.valor)}</strong>`,
          `${esc(METODO[p.metodo] || p.metodo)}${dec ? `<span class="muted">${esc(DECISION[dec.decision] || dec.decision)}${dec.motivo ? `: ${esc(dec.motivo)}` : ""}</span>` : ""}`,
          p.mae != null ? `${exacto(p.mae)}<span class="muted">en ${plural(p.n_evaluaciones, "comprobación", "comprobaciones")} · ${esc(p.periodo_evaluacion || "")} · ${esc(p.alcance_evaluacion || "")}</span>` : "Sin comprobaciones de esta serie y horizonte",
          p.banda_inferior != null ? `${exacto(p.banda_inferior)} a ${exacto(p.banda_superior)}<span class="muted">${esc(p.banda_metodo)}</span>` : `Banda no disponible: ${esc(p.banda_motivo === "historia_insuficiente" ? "historia insuficiente" : p.banda_motivo || "—")} (${num(p.banda_soporte)} errores; se exigen 12)`];
      }),
    ],
  };
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Lo que se vendió cada mes y una estimación para los próximos tres meses. Sirve para planificar; no es un ingreso realizado ni una orden de compra.",
    contexto: [ctxDatos(d.corte), { etiqueta: "Último mes completo", valor: esc(mesLargo(d.origen)) }, { etiqueta: "Horizonte", valor: "1 a 3 meses" }] })}
  ${puede("finanzas.ver") ? pestanasFinanzas("pronostico") : ""}
  ${avisoPrueba("No convierte el pronóstico en pedidos ni cambia las cifras de Finanzas.")}
  <form class="filtros" id="f-dem"><label>¿Qué quieres ver? <select name="serie">${grupos.map(([g, l]) => `<optgroup label="${esc(g)}">${l.map(s => `<option value="${esc(s)}"${s === d.serie_id ? " selected" : ""}>${esc(nombreSerie(s))}</option>`).join("")}</optgroup>`).join("")}</select></label><button>Ver esta serie</button></form>
  ${!puede("demanda.ver_cop") ? '<p class="muted">Tu perfil ve las series en unidades; las series en pesos son de Finanzas y Gerencia.</p>' : ""}
  ${hallazgo({
    que: p1 ? `Para <strong>${esc(mesLargo(p1.periodo_objetivo))}</strong> se estima <strong>${esc(corto(p1.valor))}</strong>${ultimo ? `; en ${esc(mesLargo(ultimo.periodo))} se observaron ${esc(corto(ultimo.valor))}` : ""}.` : esc(d.pronosticos[0]?.motivos?.[0] || "No hay pronóstico para esta serie."),
    porque: p1?.mae != null ? `En meses ya conocidos, la estimación a un mes se desvió en promedio ${esc(corto(p1.mae))} (${plural(p1.n_evaluaciones, "comprobación", "comprobaciones")}). Es un error medio, no un porcentaje de confianza.` : "No hay comprobaciones suficientes para decir cuánto se desvía esta estimación.",
    accion: '<button type="button" class="sec" data-ir-a="respaldo-demanda">Ver la tabla completa</button>',
  })}
  ${huecos.length ? `<p class="aviso-cifras" role="note">Meses sin dato (hueco en la línea, no cero): ${esc(huecos.map(c => `${mesLargo(c.periodo)} (${ESTADO_MES[c.estado] || c.estado})`).join(", "))}.</p>` : ""}
  <section class="panel"><h2>${esc(nombreSerie(d.serie_id))}: observado y estimado</h2>
    ${graficoLinea(hist, proy, { titulo: `${nombreSerie(d.serie_id)}${todo ? ", todo el histórico" : ", últimos 12 meses"} y estimación a 3 meses`, unidad: esCop ? "COP" : unidad, formato: esCop ? null : v => `${num(Math.round(v * 10) / 10)}`, etiquetaEstimado: "Estimado", nivelBanda: "empírico del 10 % al 90 % de los errores pasados (sin garantía)" })}
    <p class="muted">${d.calendario.length > 12 ? `<a href="${esc(enlace({ historico: todo ? "" : "todo" }))}">${todo ? "Ver solo los últimos 12 meses" : `Ver todo el histórico (${d.calendario.length} meses)`}</a>` : ""}</p>
  </section>
  ${indicadores(d.pronosticos.map(p => ({ etiqueta: `${mesLargo(p.periodo_objetivo)} (estimado)`, valor: p.valor == null ? "Sin pronóstico" : esc(corto(p.valor)),
    detalle: p.banda_inferior != null ? `banda ${esc(corto(p.banda_inferior))} a ${esc(corto(p.banda_superior))} · ${esc(METODO[p.metodo] || p.metodo)}` : `sin banda publicada · ${esc(METODO[p.metodo] || p.metodo)}` })))}
  <section class="panel" id="respaldo-demanda" tabindex="-1"><h2>Tabla de respaldo</h2>
    <p class="muted">Los mismos valores del gráfico, con el método, el error en meses ya conocidos y la banda de cada estimación.</p>
    ${tablaHtml(tabla)}
    ${!esCop ? `<p class="muted">Unidad: ${esc(unidad)}. No se suman cantidades de productos distintos.</p>` : ""}</section>
  <details class="panel"><summary>Cómo se obtuvo el pronóstico</summary><p>${esc(d.estado_experimento)} · modelo ${esc(d.version)} · serie <code>${esc(d.serie_id)}</code>. ${esc(d.nota)}</p>
    ${detalleTecnico(`<pre>${esc(JSON.stringify(d.pronosticos, null, 2))}</pre>`, "Filas publicadas (datos originales)")}</details>`;
  activarTooltips();
  document.getElementById("f-dem").addEventListener("submit", e => { e.preventDefault(); ir(enlace({ serie: new FormData(e.target).get("serie") })); });
}
