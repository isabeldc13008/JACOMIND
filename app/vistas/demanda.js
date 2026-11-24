// Pronóstico de demanda (M5): proyección EXPERIMENTAL en sombra. Distingue histórico observado, meses incompletos o no
// observables, proyección, método (referencia o candidato), resultados pendientes y bandas no disponibles.
import { $vista, api, cop, errorHtml, esc, estadoHtml, nuevoTurno, num, ruta, ir, vigente } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const mes = p => `${MESES[Number(p.slice(5, 7)) - 1]} de ${p.slice(0, 4)}`;
const METODO = { ultimo: "Último mes (referencia)", media_movil_3: "Media móvil de 3 meses (referencia A08)", ses: "Suavizamiento exponencial (candidato)",
  holt_amortiguado: "Holt amortiguado (candidato)", suma_de_familias: "Suma de las familias", sin_historia: "Sin historia suficiente" };
const DECISION = { referencia_conservada: "Referencia conservada", candidato_exploratorio_favorable: "Candidato con resultado exploratorio favorable",
  rechazado: "Candidato rechazado", inconcluso: "Inconcluso", sin_historia: "Sin historia o datos suficientes" };
const ESTADO_MES = { completo: "Observado", incompleto: "Mes incompleto", no_observable: "No observable", sin_cobertura: "Sin cobertura" };

export async function vistaDemanda() {
  const { q } = ruta();
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando el pronóstico…");
  let d;
  try { d = await api("GET", `/api/demanda${q.get("serie") ? `?serie=${encodeURIComponent(q.get("serie"))}` : ""}`); }
  catch (e) { if (vigente(turno)) $vista.innerHTML = `<h1>Pronóstico de demanda <span class="chip">IA · experimental</span></h1>${errorHtml(e)}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `<h1>Pronóstico de demanda <span class="chip">IA · experimental</span></h1>${estadoHtml("", d.mensaje)}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const esCop = d.serie_id.startsWith("ventas_cop") || d.serie_id.startsWith("compras");
  const fmt = v => v == null ? "—" : esCop ? cop(v) : num(v);
  const ult = d.calendario.slice(-12);
  const filasHist = ult.map(c => `<tr><td>${esc(mes(c.periodo))}</td><td><span class="chip${c.estado === "completo" ? "" : " fuerte"}">${esc(ESTADO_MES[c.estado] || c.estado)}</span></td>
    <td class="n">${c.estado === "completo" ? fmt(c.valor) : `<span class="muted" title="${esc(c.motivo || "")}">sin dato</span>`}</td>
    <td colspan="3" class="muted">${c.estado === "completo" ? "Dato observado del cierre" : esc(c.motivo || "")}</td></tr>`).join("");
  const filasPron = d.pronosticos.map(p => {
    const dec = d.decisiones?.[String(p.horizonte_meses)];
    const banda = p.banda_inferior != null ? `${fmt(p.banda_inferior)} – ${fmt(p.banda_superior)}<div class="muted">${esc(p.banda_metodo)}</div>`
      : `<span class="muted">Banda no disponible: ${esc(p.banda_motivo === "historia_insuficiente" ? "historia insuficiente" : p.banda_motivo || "—")} (${num(p.banda_soporte)} errores; se exigen 12)</span>`;
    const error = p.mae != null ? `MAE ${fmt(p.mae)} en ${num(p.n_evaluaciones)} ${p.n_evaluaciones === 1 ? "evaluación" : "evaluaciones"}<div class="muted">${esc(p.periodo_evaluacion || "")} · ${esc(p.alcance_evaluacion || "")}</div>`
      : '<span class="muted">Sin error histórico de esta serie y horizonte</span>';
    return `<tr class="proyeccion"><td>${esc(mes(p.periodo_objetivo))}<div class="muted">a ${num(p.horizonte_meses)} ${p.horizonte_meses === 1 ? "mes" : "meses"} del origen</div></td>
      <td><span class="chip fuerte">Proyección</span> <span class="chip">Resultado pendiente</span></td>
      <td class="n">${p.valor == null ? `<span class="muted">sin pronóstico</span>` : `<strong>${fmt(p.valor)}</strong>`}</td>
      <td>${esc(METODO[p.metodo] || p.metodo)}${dec ? `<div class="muted">${esc(DECISION[dec.decision] || dec.decision)}${dec.motivo ? ` · ${esc(dec.motivo)}` : ""}</div>` : ""}</td>
      <td>${error}</td><td>${banda}</td></tr>`;
  }).join("");
  const sinValor = d.pronosticos.filter(p => p.valor == null);
  $vista.innerHTML = `<h1>Pronóstico de demanda <span class="chip">IA · experimental</span></h1>
  ${respuesta(`<strong>Proyección a 1, 2 y 3 meses</strong> de ${esc(d.serie_id)} desde ${esc(mes(d.origen))} (último mes completo).`,
    `${esc(d.estado_experimento)} · modelo ${esc(d.version)} · unidad ${esc(d.pronosticos[0]?.unidad || "")}.`)}
  <p class="muted">${esc(d.nota)}</p>
  <form class="filtros" id="f"><label>Serie <select name="serie">${d.series.map(s => `<option value="${esc(s)}"${s === d.serie_id ? " selected" : ""}>${esc(s)}</option>`).join("")}</select></label><button>Ver</button></form>
  ${sinValor.length ? `<div class="aviso-cifras" role="status">${esc(sinValor[0].motivos?.[0] || "Sin pronóstico para esta serie")}</div>` : ""}
  <div class="tabla"><table><caption class="muted">Últimos 12 meses observados y proyección (la proyección no es un ingreso realizado)</caption>
    <tr><th>Mes</th><th>Tipo</th><th class="n">Valor</th><th>Método</th><th>Error histórico (misma serie y horizonte)</th><th>Banda</th></tr>
    ${filasHist}${filasPron}</table></div>
  ${d.pronosticos[0]?.unidad && !esCop ? `<p class="muted">Unidad: ${esc(d.pronosticos[0].unidad)}. No se suman cantidades de productos distintos.</p>` : ""}
  ${detalleTecnico(`<pre>${esc(JSON.stringify(d.pronosticos, null, 2))}</pre>`, "Filas publicadas")}`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); ir(`#/demanda?serie=${encodeURIComponent(new FormData(e.target).get("serie"))}`); });
}
