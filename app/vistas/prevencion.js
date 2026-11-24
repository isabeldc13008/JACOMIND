// V07 Clientes que podrían dejar de comprar (M2, en prueba). Separa prevenir de reactivar; no cambia la cartera ni crea tareas.
import { $vista, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, nuevoTurno, num, pct, plural, puede, ruta, vigente } from "../nucleo.js";
import { avisoPrueba, barras, ctxDatos, detalleTecnico, encabezado, enPrueba, hallazgo, vacio } from "../ui.js";

const DECISIONES = { favorable: "favorable (solo permite seguir en prueba)", inconcluso: "inconclusa", rechazado: "rechazada" };
const TITULO = "Clientes que podrían dejar de comprar";

/** Bloque para la ficha del cliente: estimación en prueba, sin alterar la acción de la cartera. */
export function inactividadFichaHtml(s) {
  if (!s) return "";
  const texto = s.estado === "estimado" ? `<strong>${esc(pct(s.probabilidad))}</strong> de riesgo estimado de llegar a 90 días sin comprar en los próximos 60 días. Ocupa el puesto ${num(s.posicion)} de la lista de prevención.`
    : s.estado === "estructural" ? "Riesgo cero por definición: con menos de 30 días sin comprar no puede llegar a 90 días en los próximos 60."
    : esc(s.motivos?.[0] || "Estimación no disponible.");
  return `<section class="panel"><h2>¿Podría dejar de comprar? ${enPrueba()}</h2>
    <p>${texto}</p>${s.estado === "estimado" ? `<p class="muted">Por qué aparece:</p><ul>${s.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}
    <p class="muted">Estimación con datos hasta el ${esc(fechaLarga(s.corte))} · ${esc(s.estado_experimento)} · modelo ${esc(s.version_modelo || "—")}. ${esc(s.nota)}</p></section>`;
}

/** Comprobación histórica (si la publicación la trae): modelo frente a la regla de mayor recencia. Sin conclusiones que los datos no sostienen. */
export function comparacionHtml(r) {
  if (!r) return "";
  const m = r.modelo, rec = r.mayor_recencia;
  const fila = (n, a, b, mejor) => `<tr><th scope="row">${n}</th><td class="n"${mejor === "a" ? ' style="font-weight:700"' : ""}>${a}</td><td class="n"${mejor === "b" ? ' style="font-weight:700"' : ""}>${b}</td></tr>`;
  const cual = (a, b) => a > b ? "a" : b > a ? "b" : "";
  const ic = r.ic95_diferencia_top10 || [];
  const d = x => (x ?? 0).toFixed(3).replace(".", ",");
  return `<h3>¿Qué tan bien funcionó en meses pasados?</h3>
    <p>Se midió con datos de práctica de julio y agosto de 2026: ${num(r.casos)} clientes con 30 a 89 días sin comprar, de los que ${num(r.eventos)} llegaron a 90 días sin compra. Se compara con la regla <strong>«llamar primero a quien lleva más días sin comprar»</strong>.</p>
    <div class="tabla"><table><thead><tr><th scope="col">Medida</th><th scope="col" class="n">Modelo</th><th scope="col" class="n">Regla de más días sin comprar</th></tr></thead><tbody>
    ${fila("Aciertos entre los 10 primeros (por mes)", esc(m.aciertos_top10_por_mes.join(" y ")), esc(rec.aciertos_top10_por_mes.join(" y ")))}
    ${fila("Aciertos medios de cada 10", num(Math.round(m.precision_media_top10 * 100) / 10), num(Math.round(rec.precision_media_top10 * 100) / 10), cual(m.precision_media_top10, rec.precision_media_top10))}
    ${fila("Aciertos entre los 20 primeros (total)", num(m.aciertos_top20), num(rec.aciertos_top20), cual(m.aciertos_top20, rec.aciertos_top20))}
    ${fila("Da un riesgo por cliente", `Sí · media estimada ${esc(pct(m.probabilidad_media))}; real ${esc(pct(r.tasa_observada))}`, "No (solo ordena)")}
    ${fila("Explica cada estimación", "Sí (ritmo de compra, fecha del cruce, renovaciones)", "Días sin comprar")}
    </tbody></table></div>
    <p>Con estos datos <strong>la diferencia frente a la regla no es concluyente</strong>: con un 95 % de confianza, el modelo queda entre ${num(Math.round(ic[0] * 100) / 10)} y +${num(Math.round(ic[1] * 100) / 10)} aciertos de cada 10 respecto de la regla.</p>
    <p class="muted">Error de Brier ${esc(d(m.brier))} frente a ${esc(d(r.constante?.brier))} de una tasa fija igual para todos (menos es mejor); una sola medida no basta para afirmar que el riesgo está bien calibrado${r.modelo_anterior ? `. Versión anterior: ${num(Math.round(r.modelo_anterior.precision_media_top10 * 100) / 10)} aciertos de cada 10` : ""}. Los datos son sintéticos y estos meses se revisaron al diseñar el modelo: la comparación es orientativa. Solo un piloto con datos reales puede confirmar si supera a la regla.</p>`;
}

export async function vistaPrevencion() {
  const { q } = ruta();
  const k = q.get("k") || "10";
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-prev")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando la lista en prueba…")}`;
  let d;
  try { d = await api("GET", `/api/prevencion?k=${encodeURIComponent(k)}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Estimación no disponible: no hay una publicación en prueba de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  const difiere = d.cierre_activo?.coincide_corte === false;
  const cohortes = [
    ["aprendible", "Entre 30 y 89 días sin comprar", "se les estima el riesgo (esta lista)"],
    ["ya_frio", "Ya llevan 90 días o más", "reactivación: están en la cartera, no aquí"],
    ["estructural", "Menos de 30 días sin comprar", "riesgo cero por definición en 60 días"],
    ["sin_historial", "Sin compras registradas", "sin base para estimar"],
    ["alta_posterior", "Dados de alta después de la fecha", "fuera del cálculo"],
  ].filter(([key]) => c[key] != null);
  const total = cohortes.reduce((a, [key]) => a + (c[key] || 0), 0);
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Clientes que todavía compran pero podrían llegar a 90 días sin comprar en los próximos 60 días. Sirve para revisar antes, no para reactivar a quien ya se pausó.",
    contexto: [ctxDatos(s.corte, "Estimación con datos hasta"), { etiqueta: "Horizonte", valor: "próximos 60 días" }, s.importada_en ? { etiqueta: "Publicada", valor: esc(fechaHora(s.importada_en)) } : null] })}
  ${avisoPrueba("No cambia la cartera ni crea seguimientos automáticamente.")}
  ${difiere ? `<p class="aviso-cifras" role="note">Fechas distintas: la cartera usa datos hasta el ${esc(fechaLarga(d.cierre_activo.corte))} y esta estimación, hasta el ${esc(fechaLarga(s.corte))}. La acción de la cartera que ves en cada fila es la vigente; no las compares como si fueran del mismo día.</p>` : ""}
  ${hallazgo({
    que: `<strong>${plural(d.total_aprendibles, "cliente lleva", "clientes llevan")} entre 30 y 89 días sin comprar.</strong> Se listan los ${num(d.items.length)} con mayor riesgo estimado.`,
    porque: `Aún no se han pausado: revisarlos ahora es prevención. ${c.ya_frio != null ? `Otros ${plural(c.ya_frio, "cliente ya lleva", "clientes ya llevan")} 90 días o más; eso es reactivación y se atiende desde la cartera.` : ""}`,
    accion: [d.items[0] && puede("cartera.ver") && `<a class="boton" href="#/clientes/${encodeURIComponent(d.items[0].cliente_id)}">Ver el cliente con más riesgo</a>`, puede("cartera.ver") && '<a class="boton-sec" href="#/agenda?frio=1">Ver quienes ya llevan 90 días</a>'].filter(Boolean).join(""),
  })}
  <div class="grid2 ancho-desigual">
  <section class="panel" aria-labelledby="t-lista-prev"><h2 id="t-lista-prev">Lista para revisar</h2>
    <form class="filtros" id="f-prev"><label>¿A cuántos clientes puede revisar tu equipo? <span class="ayuda">Es la capacidad de revisión, no un umbral de riesgo.</span><input name="k" type="number" min="1" max="200" value="${esc(k)}" inputmode="numeric"></label><button>Mostrar la lista</button></form>
    ${d.items.length ? `<div class="tabla"><table class="apilable"><caption>Orden: mayor riesgo estimado primero. Entre paréntesis, el puesto que tendría con la regla de más días sin comprar.</caption>
    <thead><tr><th scope="col">Puesto</th><th scope="col">Cliente</th><th scope="col" class="n">Riesgo estimado en 60 días</th><th scope="col">Por qué aparece</th><th scope="col">Acción en la cartera</th><th scope="col"><span class="oculto-visual">Abrir</span></th></tr></thead><tbody>
    ${d.items.map(i => `<tr><td data-et="Puesto">${num(i.posicion)} <span class="muted">(regla: ${num(i.posicion_mayor_recencia)})</span></td><td data-et="Cliente"><strong>${esc(i.cliente_id)}</strong><span class="muted">${num(i.recencia_dias)} días sin comprar · última compra el ${esc(fechaLarga(i.ultima_compra))}</span></td>
      <td class="n" data-et="Riesgo estimado en 60 días"><strong>${esc(pct(i.probabilidad))}</strong></td><td data-et="Por qué aparece"><span class="muted">${esc(i.motivos.slice(1).join(" · "))}</span></td>
      <td data-et="Acción en la cartera">${esc(i.accion_c1 || "—")}${i.episodio ? (i.episodio.tarea_id ? `<span class="muted"><a href="#/tareas/${i.episodio.tarea_id}">${i.episodio.compartida ? "Motivo añadido a un seguimiento" : "Seguimiento de comprobación"}</a></span>` : '<span class="muted">Episodio abierto</span>') : ""}</td>
      <td>${puede("cartera.ver") ? `<a class="boton-sec" href="#/clientes/${encodeURIComponent(i.cliente_id)}?pestana=senales">Ver cliente<span class="oculto-visual"> ${esc(i.cliente_id)}</span></a>` : ""}</td></tr>`).join("")}
    </tbody></table></div>` : vacio("No hay clientes entre 30 y 89 días sin comprar en esta fecha.")}
  </section>
  <section class="panel"><h2>¿Dónde está cada cliente?</h2>
    <p class="muted">Grupos que no se solapan, sobre ${plural(total, "cliente", "clientes")}.</p>
    ${barras(cohortes.map(([key, et, nota]) => ({ etiqueta: et, nota, valor: c[key] || 0, texto: `${plural(c[key] || 0, "cliente", "clientes")}`, href: key === "ya_frio" && puede("cartera.ver") ? "#/agenda?frio=1" : null })), { etiquetaAria: "Clientes por días sin comprar" })}
  </section></div>
  <details class="panel"><summary>Cómo se obtuvo esta estimación</summary>
    <p>Estado: ${esc(s.estado_experimento)}${s.decision ? ` · decisión ${esc(DECISIONES[s.decision.decision] || s.decision.decision)}` : ""}. Modelo ${esc(s.version_modelo)}. ${esc(d.nota)} ${esc(d.precedencia_c1)} Seguimientos automáticos: ${d.tareas_automaticas ? "activados" : "desactivados"}.</p>
    ${comparacionHtml(s.decision?.resumen)}
    ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación en prueba (datos originales)")}</details>`;
  document.getElementById("f-prev").addEventListener("submit", e => { e.preventDefault(); ir(`#/prevencion?k=${new FormData(e.target).get("k")}`); });
}
