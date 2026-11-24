// Modelos de IA: qué predice cada modelo, cómo se usa en la aplicación y cómo se compara con las reglas.
import { $vista, api, errorHtml, esc, estadoHtml, nuevoTurno, num, pct, puede, vigente } from "../nucleo.js";
import { respuesta } from "../ui.js";

const ENLACES = {
  compra_30d: () => puede("cartera.ver") ? `<a class="boton" href="#/agenda">Abrir la agenda</a>` : "",
  inactividad_60d: () => puede("prevencion.ver") ? `<a class="boton" href="#/prevencion">Abrir la lista de prevención</a>` : "",
  proxima_compra: () => puede("proxima.ver") ? `<a class="boton" href="#/proxima">Abrir la próxima compra</a>` : "",
  venta_cruzada: () => puede("venta_cruzada.ver") ? `<a class="boton" href="#/venta-cruzada">Abrir la venta cruzada</a>` : "",
  anomalias: () => puede("anomalias.ver") ? `<a class="boton" href="#/anomalias">Abrir la cola de operaciones atípicas</a>` : "",
};
const TIPO = { ia: "IA", regla: "Regla", referencia: "Referencia" };
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const periodo = cortes => {
  const ms = cortes.map(c => MESES[Number(c.slice(5, 7)) - 1]);
  return `${ms.length > 1 ? `${ms.slice(0, -1).join(", ")} y ${ms.at(-1)}` : ms[0]} de ${cortes.at(-1).slice(0, 4)}`;
};
const dec3 = x => x == null ? "—" : x.toFixed(3).replace(".", ",");

function tablaGenericaHtml(t) {
  return `<div class="tabla"><table><tr>${t.columnas.map((c, i) => `<th${i ? ' class="n"' : ""}>${esc(c)}</th>`).join("")}</tr>
  ${t.filas.map(f => `<tr>${f.map((v, i) => i ? `<td class="n">${esc(v)}</td>` : `<th>${esc(v)}</th>`).join("")}</tr>`).join("")}</table></div>`;
}

function tablaHtml(m) {
  if (m.tabla) return tablaGenericaHtml(m.tabla);
  const mejorTop10 = Math.max(...m.filas.map(f => f.aciertos_top10 ?? -1));
  const mejorTop20 = Math.max(...m.filas.map(f => f.aciertos_top20 ?? -1));
  const briers = m.filas.map(f => f.brier).filter(b => b != null);
  const mejorBrier = briers.length ? Math.min(...briers) : null;
  const b = (cond, txt) => cond ? `<strong>${txt}</strong>` : txt;
  return `<div class="tabla"><table><tr><th>Método</th><th>Tipo</th><th class="n">Aciertos entre los 10 primeros</th><th class="n">Entre los 20 primeros</th>
    <th class="n">Probabilidad media (real ${esc(pct(m.tasa_observada))})</th><th class="n">Error de Brier (menos es mejor)</th></tr>
  ${m.filas.map(f => `<tr${f.actual ? ' aria-current="true"' : ""}><td>${f.actual ? "<strong>" : ""}${esc(f.metodo)}${f.actual ? "</strong> <span class=\"chip fuerte\">en uso</span>" : ""}<div class="muted">${esc(f.descripcion)}</div></td>
    <td>${esc(TIPO[f.tipo] || f.tipo)}</td>
    <td class="n">${f.aciertos_top10 == null ? "—" : b(f.aciertos_top10 === mejorTop10, `${num(f.aciertos_top10)} de ${num(f.de_top10)}`)}</td>
    <td class="n">${f.aciertos_top20 == null ? "—" : b(f.aciertos_top20 === mejorTop20, num(f.aciertos_top20))}</td>
    <td class="n">${f.probabilidad_media == null ? (f.tipo === "regla" ? "No da probabilidad" : "—") : esc(pct(f.probabilidad_media))}</td>
    <td class="n">${f.brier == null ? "—" : b(f.brier === mejorBrier, dec3(f.brier))}</td></tr>`).join("")}
  </table></div>`;
}

function modeloHtml(m) {
  const enlace = (ENLACES[m.modelo_id] || (() => ""))();
  return `<section class="panel"><h2>${esc(m.titulo)} <span class="chip">${esc(m.estado)}</span></h2>
    <p><strong>Pregunta:</strong> ${esc(m.pregunta)}</p>
    <p><strong>Dónde se usa:</strong> ${esc(m.uso)} ${enlace}</p>
    <ul>${m.lectura.map(l => `<li>${esc(l)}</li>`).join("")}</ul>
    ${tablaHtml(m)}
    <p class="muted">Medido en ${num(m.casos)} casos de ${esc(periodo(m.periodo))} (${num(m.eventos)} con el resultado buscado). Modelo ${esc(m.version)}.</p></section>`;
}

export async function vistaIA() {
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando los resultados de los modelos…");
  let d;
  try { d = await api("GET", "/api/ia"); } catch (e) { if (vigente(turno)) $vista.innerHTML = errorHtml(e); return; }
  if (!vigente(turno)) return;
  if (d.estado !== "ok") {
    $vista.innerHTML = `<h1>Modelos de IA</h1>${estadoHtml("", d.mensaje)}<p class="muted">Se genera con <code>${esc(d.comando)}</code>.</p>`;
    return;
  }
  $vista.innerHTML = `<h1>Modelos de IA</h1>
  ${respuesta(`<strong>${num(d.modelos.length)} modelos</strong> estiman para cada cliente la probabilidad de comprar, el riesgo de quedar inactivo${d.modelos.length > 2 ? ", cuándo es probable su próxima compra" : ""}${d.modelos.length > 3 ? " y qué productos complementarios proponer" : ""}.`,
    "Cada modelo se compara con la regla simple que usaría una persona y con una probabilidad fija para todos.")}
  ${d.modelos.map(modeloHtml).join("")}
  <p class="muted">${esc(d.advertencia)}</p>`;
}
