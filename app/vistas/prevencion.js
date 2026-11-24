// Prevención de inactividad (M2): lista interna EXPERIMENTAL calculada en sombra. No cambia la agenda ni sus prioridades.
import { $vista, api, errorHtml, esc, estadoHtml, fechaLarga, nuevoTurno, num, pct, plural, puede, ruta, ir, vigente } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

const DECISIONES = { favorable: "favorable (solo habilita sombra)", inconcluso: "inconclusa", rechazado: "rechazada" };

/** Bloque para la ficha del cliente: resultado de sombra, sin alterar la acción C1. */
export function inactividadFichaHtml(s) {
  if (!s) return "";
  const texto = s.estado === "estimado" ? `<strong>${esc(pct(s.probabilidad))}</strong> de riesgo experimental de llegar a 90 días sin compra en los próximos 60 días (posición ${num(s.posicion)} de la lista de prevención).`
    : s.estado === "estructural" ? "Riesgo estructural cero: con menos de 30 días sin compra no puede llegar a 90 días en 60 días."
    : esc(s.motivos?.[0] || "Sin estimación");
  return `<section class="panel"><h2>Riesgo de inactividad <span class="chip">IA · experimental</span></h2>
    <p>${texto}</p><p class="muted">${esc(s.estado_experimento)} · modelo ${esc(s.version_modelo || "—")} · corte ${esc(fechaLarga(s.corte))}. ${esc(s.nota)}</p>
    ${s.estado === "estimado" ? `<ul>${s.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}</section>`;
}

/** Resumen de la comprobación histórica (si la publicación en sombra lo trae): modelo frente a mayor recencia. */
export function comparacionHtml(r) {
  if (!r) return "";
  const m = r.modelo, rec = r.mayor_recencia;
  const fila = (n, a, b, mejor) => `<tr><th>${n}</th><td class="n"${mejor === "a" ? ' style="font-weight:600"' : ""}>${a}</td><td class="n"${mejor === "b" ? ' style="font-weight:600"' : ""}>${b}</td></tr>`;
  const cual = (a, b) => a > b ? "a" : b > a ? "b" : "";
  const ic = r.ic95_diferencia_top10 || [];
  return `<section class="panel"><h2>¿Qué tan bien funciona? <span class="chip">Comprobación histórica</span></h2>
    <p>Se midió en los datos de práctica de julio y agosto de 2026: ${num(r.casos)} clientes con 30 a 89 días sin comprar, de los que ${num(r.eventos)} llegaron a 90 días sin compra. El modelo se compara con la regla de <strong>mayor recencia</strong>: llamar primero a quien lleva más días sin comprar.</p>
    <div class="tabla"><table><tr><th></th><th class="n">Modelo de IA</th><th class="n">Mayor recencia</th></tr>
    ${fila("Aciertos entre los 10 primeros (por mes)", esc(m.aciertos_top10_por_mes.join(" y ")), esc(rec.aciertos_top10_por_mes.join(" y ")))}
    ${fila("Aciertos medios de cada 10", num(Math.round(m.precision_media_top10 * 100) / 10), num(Math.round(rec.precision_media_top10 * 100) / 10), cual(m.precision_media_top10, rec.precision_media_top10))}
    ${fila("Aciertos entre los 20 primeros (total)", num(m.aciertos_top20), num(rec.aciertos_top20), cual(m.aciertos_top20, rec.aciertos_top20))}
    ${fila("Probabilidad de riesgo por cliente", `Sí · media estimada ${esc(pct(m.probabilidad_media))} frente a ${esc(pct(r.tasa_observada))} real`, "No (solo ordena)", "a")}
    ${fila("Explica cada estimación", "Sí (ritmo de compra, fecha del cruce, renovaciones)", "Días sin comprar", "a")}
    </table></div>
    <p class="muted">Entre los 10 primeros la regla acierta algo más; la diferencia no es concluyente con estos datos (con un 95 % de confianza, el modelo queda entre ${num(Math.round(ic[0] * 100) / 10)} y +${num(Math.round(ic[1] * 100) / 10)} aciertos de cada 10 respecto de la regla). La probabilidad del modelo está bien calibrada (error de Brier ${esc((m.brier ?? 0).toFixed(3).replace(".", ","))} frente a ${esc((r.constante?.brier ?? 0).toFixed(3).replace(".", ","))} de una tasa fija; menos es mejor)${r.modelo_anterior ? ` y mejora a la versión anterior (${num(Math.round(r.modelo_anterior.precision_media_top10 * 100) / 10)} de cada 10)` : ""}. Los datos son sintéticos y estos meses ya se habían revisado al diseñar el modelo, así que la comparación es orientativa. Solo el piloto con datos reales puede confirmar si supera a la regla.</p></section>`;
}

export async function vistaPrevencion() {
  const { q } = ruta();
  const k = q.get("k") || "10";
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando la lista experimental…");
  let d;
  try { d = await api("GET", `/api/prevencion?k=${encodeURIComponent(k)}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = errorHtml(e); return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `<h1>Prevención de inactividad <span class="chip">Experimental</span></h1>${estadoHtml("", d.mensaje)}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra;
  const aviso = d.cierre_activo?.coincide_corte === false ? `<p class="muted">El cierre activo es del ${esc(fechaLarga(d.cierre_activo.corte))} y la puntuación en sombra del ${esc(fechaLarga(s.corte))}: la acción de agenda mostrada es la del cierre activo.</p>` : "";
  $vista.innerHTML = `<h1>Prevención de inactividad <span class="chip">Experimental · sombra</span></h1>
  ${respuesta(`<strong>${plural(d.items.length, "cliente activo", "clientes activos")} con mayor riesgo experimental de llegar a 90 días sin compra</strong> entre ${num(d.total_aprendibles)} con 30 a 89 días sin comprar.`,
    `Estado del experimento: ${esc(s.estado_experimento)}${s.decision ? ` · decisión ${esc(DECISIONES[s.decision.decision] || s.decision.decision)}` : ""} · corte ${esc(fechaLarga(s.corte))} · modelo ${esc(s.version_modelo)}.`)}
  <p class="muted">${esc(d.nota)} ${esc(d.precedencia_c1)} Tareas automáticas: ${d.tareas_automaticas ? "activadas" : "desactivadas"}.</p>${aviso}
  ${comparacionHtml(s.decision?.resumen)}
  <form class="filtros" id="f"><label>Tamaño de la lista <input name="k" type="number" min="1" max="200" value="${esc(k)}"></label><button>Actualizar</button></form>
  <div class="tabla"><table><tr><th>#</th><th>Cliente</th><th class="n">Riesgo (sombra)</th><th class="n">Puesto por mayor recencia</th><th>Días sin comprar</th><th>Acción de la agenda</th><th>Señales</th><th>Episodio</th></tr>
  ${d.items.map(i => `<tr><td>${i.posicion}</td><td>${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(i.cliente_id)}">${esc(i.cliente_id)}</a>` : esc(i.cliente_id)}</td>
    <td class="n">${esc(pct(i.probabilidad))}</td><td class="n">${i.posicion_mayor_recencia}</td><td>${i.recencia_dias} (última compra ${esc(fechaLarga(i.ultima_compra))})</td>
    <td>${esc(i.accion_c1 || "—")}</td><td class="muted">${esc(i.motivos.slice(1).join(" · "))}</td>
    <td>${i.episodio ? (i.episodio.tarea_id ? `<a href="#/tareas/${i.episodio.tarea_id}">${i.episodio.compartida ? "Motivo añadido a un seguimiento" : "Seguimiento de comprobación"}</a>` : "Abierto") : '<span class="muted">—</span>'}</td></tr>`).join("") || '<tr><td colspan=8 class="muted">No hay clientes en la población aprendible.</td></tr>'}
  </table></div>
  <p class="muted">Cobertura del corte: ${num(d.conteos.aprendible)} con estimación (30–89 días), ${num(d.conteos.estructural)} con riesgo estructural cero (menos de 30 días), ${num(d.conteos.ya_frio)} ya fríos (reactivación, fuera de esta lista), ${num(d.conteos.sin_historial)} sin compras.</p>
  ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación en sombra")}`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); ir(`#/prevencion?k=${new FormData(e.target).get("k")}`); });
}
