// V07 Clientes que podrían dejar de comprar (M2, en uso). Separa prevenir de reactivar; no cambia la cartera ni crea tareas.
import { $vista, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, nuevoTurno, num, pct, plural, puede, ruta, vigente } from "../nucleo.js";
import { avisoPrueba, ctxDatos, detalleTecnico, encabezado, enPrueba, hallazgo, vacio } from "../ui.js";

const DECISIONES = { favorable: "favorable", inconcluso: "inconclusa", rechazado: "rechazada" };
const TITULO = "Clientes que podrían dejar de comprar";

/** Bloque para la ficha del cliente: estimación del modelo M2, sin alterar la acción de la cartera. */
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

/** Nivel de riesgo en palabras, siempre junto al porcentaje (nunca solo color). */
const nivelRiesgo = p => p >= 0.6 ? { clase: "alto", texto: "Riesgo alto" } : p >= 0.3 ? { clase: "medio", texto: "Riesgo medio" } : { clase: "bajo", texto: "Riesgo bajo" };

/** Recorrido de la cartera: al día → en riesgo (esta lista) → ya pausados. Una barra apilada con cifras escritas. */
function recorridoHtml(c) {
  const tramos = [
    { key: "estructural", clase: "al-dia", titulo: "Al día", detalle: "Menos de 30 días sin comprar" },
    { key: "aprendible", clase: "riesgo", titulo: "Podrían pausarse", detalle: "Entre 30 y 89 días: esta lista" },
    { key: "ya_frio", clase: "pausado", titulo: "Ya pausados", detalle: "90 días o más: reactivación, en la cartera" },
  ].filter(t => c[t.key] != null);
  const otros = (c.sin_historial || 0) + (c.alta_posterior || 0);
  const total = tramos.reduce((a, t) => a + (c[t.key] || 0), 0) + otros;
  if (!total) return "";
  const ancho = n => `${(n / total * 100).toFixed(2)}%`;
  return `<section class="panel prev-recorrido" aria-labelledby="t-recorrido"><h2 id="t-recorrido">¿Dónde está cada cliente?</h2>
    <p class="muted">Los ${num(total)} clientes, según los días que llevan sin comprar. Cada cliente está en un solo grupo.</p>
    <div class="prev-barra" role="img" aria-label="${esc(tramos.map(t => `${t.titulo}: ${c[t.key] || 0}`).join("; "))}${otros ? `; sin base para estimar: ${otros}` : ""}">
      ${tramos.map(t => c[t.key] ? `<span class="prev-tramo ${t.clase}" style="width:${ancho(c[t.key])}"></span>` : "").join("")}
      ${otros ? `<span class="prev-tramo otros" style="width:${ancho(otros)}"></span>` : ""}
    </div>
    <ol class="prev-etapas">${tramos.map(t => `<li class="${t.clase}">
      ${t.key === "ya_frio" && puede("cartera.ver") ? '<a href="#/agenda?frio=1">' : "<div>"}<span class="prev-muestra" aria-hidden="true"></span>
      <span class="prev-n">${num(c[t.key] || 0)}</span><span><strong>${esc(t.titulo)}</strong><small>${esc(t.detalle)}</small></span>${t.key === "ya_frio" && puede("cartera.ver") ? "</a>" : "</div>"}</li>`).join("")}
      ${otros ? `<li class="otros"><div><span class="prev-muestra" aria-hidden="true"></span><span class="prev-n">${num(otros)}</span><span><strong>Sin base para estimar</strong><small>Sin compras o dados de alta después</small></span></div></li>` : ""}</ol>
  </section>`;
}

/** Una fila de la lista: quién, cuánto riesgo, cuánto le falta para 90 días y por qué. */
function filaRiesgo(i) {
  const n = nivelRiesgo(i.probabilidad), p = Math.round(i.probabilidad * 1000) / 10;
  const faltan = Math.max(0, 90 - i.recencia_dias);
  const avance = Math.min(100, i.recencia_dias / 90 * 100).toFixed(1);
  const motivos = (i.motivos || []).slice(1);
  return `<li class="prev-fila">
    <div class="prev-quien"><span class="prev-puesto" aria-label="Puesto ${num(i.posicion)}">${num(i.posicion)}</span>
      <div><strong class="prev-id">${esc(i.cliente_id)}</strong><small>Última compra el ${esc(fechaLarga(i.ultima_compra))}</small></div></div>
    <div class="prev-riesgo ${n.clase}"><div class="prev-riesgo-cab"><span class="prev-pct">${esc(pct(i.probabilidad))}</span><span class="prev-nivel">${n.texto}</span></div>
      <span class="prev-medidor" aria-hidden="true"><span style="width:${p}%"></span></span></div>
    <div class="prev-reloj"><div class="prev-riesgo-cab"><span><strong>${num(i.recencia_dias)}</strong> días sin comprar</span></div>
      <span class="prev-camino" aria-hidden="true"><span style="width:${avance}%"></span><i style="left:${(30 / 90 * 100).toFixed(1)}%"></i></span>
      <small>${faltan ? `Le ${faltan === 1 ? "falta 1 día" : `faltan ${num(faltan)} días`} para llegar a 90` : "Llega a 90 días hoy"}</small></div>
    <div class="prev-porque">${motivos.length ? `<ul>${motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>` : '<span class="muted">Sin motivos adicionales.</span>'}
      <small class="muted">Por días sin comprar estaría en el puesto ${num(i.posicion_mayor_recencia)}.</small></div>
    <div class="prev-accion"><small>En la cartera</small><span>${esc(i.accion_c1 || "Sin acción")}</span>
      ${i.episodio ? (i.episodio.tarea_id ? `<a href="#/tareas/${i.episodio.tarea_id}">${i.episodio.compartida ? "Motivo añadido a un seguimiento" : "Seguimiento de comprobación"}</a>` : '<small class="muted">Revisión abierta</small>') : ""}
      ${puede("cartera.ver") ? `<a class="boton-sec" href="#/clientes/${encodeURIComponent(i.cliente_id)}?pestana=senales">Ver cliente<span class="oculto-visual"> ${esc(i.cliente_id)}</span></a>` : ""}</div>
  </li>`;
}

export async function vistaPrevencion() {
  const { q } = ruta();
  const k = q.get("k") || "10";
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-prev")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando la lista…")}`;
  let d;
  try { d = await api("GET", `/api/prevencion?k=${encodeURIComponent(k)}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Estimación no disponible: no hay una publicación de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  const difiere = d.cierre_activo?.coincide_corte === false;
  const niveles = { alto: 0, medio: 0, bajo: 0 };
  d.items.forEach(i => niveles[nivelRiesgo(i.probabilidad).clase]++);
  const urgentes = d.items.filter(i => 90 - i.recencia_dias <= 15).length;
  const opciones = [10, 20, 50].filter(n => n <= Math.max(10, d.total_aprendibles));
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Clientes que todavía compran pero podrían llegar a 90 días sin comprar en los próximos 60 días. Sirve para actuar antes, no para reactivar a quien ya se pausó.",
    contexto: [ctxDatos(s.corte, "Estimación con datos hasta"), { etiqueta: "Horizonte", valor: "próximos 60 días" }, s.importada_en ? { etiqueta: "Publicada", valor: esc(fechaHora(s.importada_en)) } : null] })}
  ${avisoPrueba("No cambia la cartera ni crea seguimientos automáticamente.")}
  ${difiere ? `<p class="aviso-cifras" role="note">Fechas distintas: la cartera usa datos hasta el ${esc(fechaLarga(d.cierre_activo.corte))} y esta estimación, hasta el ${esc(fechaLarga(s.corte))}. La acción de la cartera que ves en cada fila es la vigente; no las compares como si fueran del mismo día.</p>` : ""}
  ${hallazgo({
    que: `<strong>${plural(d.total_aprendibles, "cliente lleva", "clientes llevan")} entre 30 y 89 días sin comprar.</strong> Abajo están los ${num(d.items.length)} con más riesgo de pausarse${urgentes ? `; ${plural(urgentes, "llega", "llegan")} a 90 días en dos semanas o menos` : ""}.`,
    porque: `Aún no se han pausado: hablar con ellos ahora es prevención. ${c.ya_frio != null ? `Otros ${plural(c.ya_frio, "cliente ya lleva", "clientes ya llevan")} 90 días o más; eso es reactivación y se atiende desde la cartera.` : ""}`,
    accion: [d.items[0] && puede("cartera.ver") && `<a class="boton" href="#/clientes/${encodeURIComponent(d.items[0].cliente_id)}?pestana=senales">Ver el cliente con más riesgo</a>`, puede("cartera.ver") && '<a class="boton-sec" href="#/agenda?frio=1">Ver quienes ya llevan 90 días</a>'].filter(Boolean).join(""),
  })}
  ${recorridoHtml(c)}
  <section class="panel" aria-labelledby="t-lista-prev">
    <div class="prev-lista-cab"><div><h2 id="t-lista-prev">Lista para revisar</h2>
      <p class="muted">Ordenada de mayor a menor riesgo estimado. ${d.items.length ? `${niveles.alto ? `<span class="prev-chip alto">${num(niveles.alto)} con riesgo alto</span>` : ""}${niveles.medio ? `<span class="prev-chip medio">${num(niveles.medio)} con riesgo medio</span>` : ""}${niveles.bajo ? `<span class="prev-chip bajo">${num(niveles.bajo)} con riesgo bajo</span>` : ""}` : ""}</p></div>
      <form class="prev-capacidad" id="f-prev"><label for="k-prev">¿A cuántos puede revisar tu equipo?</label>
        <div class="prev-capacidad-fila">${opciones.map(n => `<a class="prev-opcion${String(n) === String(d.k) ? " activo" : ""}" href="#/prevencion?k=${n}" ${String(n) === String(d.k) ? 'aria-current="true"' : ""}>${n}</a>`).join("")}
          <input id="k-prev" name="k" type="number" min="1" max="200" value="${opciones.map(String).includes(String(d.k)) ? "" : esc(k)}" placeholder="Otro" inputmode="numeric" aria-describedby="k-ayuda"><button class="sec">Mostrar</button></div>
        <small id="k-ayuda" class="muted">Es tu capacidad de revisión, no un límite de riesgo.</small></form></div>
    ${d.items.length ? `<div class="prev-encabezados" aria-hidden="true"><span>Cliente</span><span>Riesgo en 60 días</span><span>Camino a 90 días</span><span>Por qué aparece</span><span>Qué hacer</span></div>
      <ol class="prev-lista">${d.items.map(filaRiesgo).join("")}</ol>
      <p class="muted prev-nota"><strong>Cómo leerlo:</strong> el porcentaje es la posibilidad estimada de que el cliente llegue a 90 días sin comprar en los próximos 60 días (alto desde 60 %, medio desde 30 %). La barra gris muestra cuánto camino lleva hacia los 90 días. Es una estimación para decidir a quién llamar primero, no una certeza.</p>`
      : vacio("No hay clientes entre 30 y 89 días sin comprar en esta fecha.")}
  </section>
  <details class="panel"><summary>Cómo se obtuvo esta estimación</summary>
    <p>Estado: ${esc(s.estado_experimento)}${s.decision ? ` · decisión ${esc(DECISIONES[s.decision.decision] || s.decision.decision)}` : ""}. Modelo ${esc(s.version_modelo)}. ${esc(d.nota)} ${esc(d.precedencia_c1)} Seguimientos automáticos: ${d.tareas_automaticas ? "activados" : "desactivados"}.</p>
    ${comparacionHtml(s.decision?.resumen)}
    ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación (datos originales)")}</details>`;
  document.getElementById("f-prev").addEventListener("submit", e => { e.preventDefault(); const n = new FormData(e.target).get("k"); if (n) ir(`#/prevencion?k=${n}`); else e.target.k.focus(); });
}
