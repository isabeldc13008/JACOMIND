// Próxima compra (M3): ventana estimada calculada en sombra. No es una fecha contractual y no cambia la agenda.
import { $vista, api, errorHtml, esc, estadoHtml, fechaLarga, nuevoTurno, num, pct, plural, puede, ruta, ir, vigente } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

const ORIGEN = { modelo_cox: "modelo con las variables del cliente", poblacional_km: "curva poblacional (igual para todos)" };
const REF = { disponible: "disponible", vencida: "vencida", insuficiente: "historia insuficiente" };

function textoVentana(s) {
  if (s.estado === "sin_historial") return "Sin compras confirmadas: no hay ritmo de compra del que partir y no se estima fecha.";
  if (!["estimado", "estimacion_parcial"].includes(s.estado)) return esc(s.motivos?.[0] || "Sin estimación");
  if (s.ventana_tipo === "p10_p50") {
    if (s.dias_p10 == null) return `Ni siquiera el 10 % de probabilidad de compra se alcanza en ${num(s.soporte_dias)} días: no hay ventana.`;
    if (s.dias_p50 == null) return `Desde el ${esc(fechaLarga(s.fecha_p10))}; la mitad de probabilidad no se alcanza en ${num(s.soporte_dias)} días: no hay ventana de inicio.`;
    const txt = `Inicio probable entre el <strong>${esc(fechaLarga(s.fecha_p10))}</strong> (10 %) y el <strong>${esc(fechaLarga(s.fecha_p50))}</strong> (50 %).`;
    return s.ventana_utilizable ? txt : `${txt} La ventana es ancha (${num(s.ancho_ventana_dias)} días): orientativa, sin recordatorio.`;
  }
  if (s.ventana_utilizable) return `Entre el <strong>${esc(fechaLarga(s.fecha_p10))}</strong> y el <strong>${esc(fechaLarga(s.fecha_p90))}</strong> (80 % central; mitad de probabilidad hacia el ${esc(fechaLarga(s.fecha_p50))}).`;
  if (s.dias_p10 == null) return `Ni siquiera el 10 % de probabilidad de compra se alcanza en ${num(s.soporte_dias)} días: no hay ventana.`;
  const central = s.dias_p50 != null ? `; mitad de probabilidad hacia el ${esc(fechaLarga(s.fecha_p50))}` : "; la mediana no se alcanza dentro del horizonte";
  return `Desde el ${esc(fechaLarga(s.fecha_p10))}${central}. <strong>El límite superior no se alcanza en ${num(s.soporte_dias)} días</strong>: no hay una ventana utilizable ni una fecha exacta.`;
}

function acumuladaHtml(pa) {
  if (!pa) return "";
  return `<p>Probabilidad estimada de haber comprado: ${Object.entries(pa).map(([d, p]) => `<strong>${esc(pct(p))}</strong> en ${num(Number(d))} días`).join(" · ")}.</p>`;
}

/** Bloque para la ficha: ventana estimada, separada de las fechas contractuales de cobertura. */
export function proximaFichaHtml(s) {
  if (!s) return "";
  const ref = s.referencia_personal_estado ? `Referencia personal (intervalo mediano menos días sin comprar): ${esc(REF[s.referencia_personal_estado] || s.referencia_personal_estado)}${s.referencia_personal_dias != null ? ` (${num(s.referencia_personal_dias)} días)` : ""}.` : "";
  return `<section class="panel"><h2>Próxima compra: ventana estimada <span class="chip">IA · experimental</span></h2>
    <p>${textoVentana(s)}</p>${acumuladaHtml(s.prob_acumulada)}
    <p class="muted">Calculada al corte del ${esc(fechaLarga(s.corte))} con ${esc(ORIGEN[s.origen_estimacion] || "—")}. ${ref}</p>
    <p class="muted">${esc(s.nota)} Las fechas de fin de cobertura se muestran aparte y no cambian.</p>
    <ul class="muted">${(s.limitaciones || []).map(l => `<li>${esc(l)}</li>`).join("")}</ul></section>`;
}

export async function vistaProxima() {
  const { q } = ruta();
  const dias = q.get("dias") || "30";
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando las ventanas estimadas…");
  let d;
  try { d = await api("GET", `/api/proxima?dias=${encodeURIComponent(dias)}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = errorHtml(e); return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `<h1>Próxima compra <span class="chip">IA · experimental</span></h1>${estadoHtml("", d.mensaje)}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  $vista.innerHTML = `<h1>Próxima compra <span class="chip">IA · experimental</span></h1>
  ${respuesta(`<strong>${plural(d.items.length, "cliente", "clientes")} con una ventana estimada que empieza en los próximos ${num(d.dias)} días</strong> desde el corte del ${esc(fechaLarga(s.corte))}.`,
    `${esc(s.estado_experimento)} · ${s.tipo === "cox" ? "modelo con variables del cliente" : "curva poblacional"} · modelo ${esc(s.version_modelo)}.`)}
  <p class="muted">${esc(d.nota)} ${esc(d.precedencia_c1)} Recordatorios automáticos: ${d.recordatorios_automaticos ? "activados" : "desactivados"}.</p>
  <form class="filtros" id="f"><label>Días desde el corte <input name="dias" type="number" min="1" max="60" value="${esc(dias)}"></label><button>Actualizar</button></form>
  <div class="tabla"><table><tr><th>Cliente</th><th>Ventana estimada</th><th class="n">Ancho</th><th>Días sin comprar</th><th>Fin de cobertura (contractual)</th><th>Acción de la agenda</th><th>Episodio</th></tr>
  ${d.items.map(i => `<tr><td>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(i.cliente_id)}">${esc(i.cliente_id)}</a>` : esc(i.cliente_id)}</td>
    <td>${esc(fechaLarga(i.ventana_desde))} – ${esc(fechaLarga(i.ventana_hasta))}${i.ventana_tipo === "p10_p50" ? '<div class="muted">inicio probable (10 %–50 %)</div>' : ""}</td><td class="n">${num(i.ancho_ventana_dias)} días</td><td>${num(i.recencia_dias)}</td>
    <td>${i.proximo_fin_cobertura ? esc(fechaLarga(i.proximo_fin_cobertura)) : '<span class="muted">—</span>'}</td><td>${esc(i.accion_c1 || "—")}</td>
    <td>${i.episodio ? (i.episodio.tarea_id ? `<a href="#/tareas/${i.episodio.tarea_id}">${i.episodio.compartida ? "Motivo añadido" : "Seguimiento"}</a>` : "Abierto") : '<span class="muted">—</span>'}</td></tr>`).join("")
    || '<tr><td colspan=7 class="muted">Ningún cliente tiene una ventana utilizable (sus dos límites dentro de 60 días y ancho de 30 días o menos) que empiece en este plazo. No se inventan fechas.</td></tr>'}
  </table></div>
  <p class="muted">Estado de la cartera en este corte: ${num(c.ventana_utilizable || 0)} con ventana utilizable, ${num((c.estimacion_parcial || 0) + (c.estimado || 0))} con estimación pero sin ventana utilizable (demasiado ancha o con un límite que no se alcanza en 60 días), ${num(c.sin_historial || 0)} sin compras.</p>
  ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación en sombra")}`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); ir(`#/proxima?dias=${new FormData(e.target).get("dias")}`); });
}
