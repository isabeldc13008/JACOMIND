// V08 Cuándo conviene contactar (M3, en uso): ventanas estimadas de próxima compra. No son fechas de contrato ni de compra.
import { $vista, api, errorHtml, esc, estadoHtml, fechaLarga, ir, nuevoTurno, num, pct, plural, puede, ruta, vigente } from "../nucleo.js";
import { activarTooltips, avisoPrueba, ctxDatos, detalleTecnico, encabezado, enPrueba, graficoRangos, hallazgo, vacio } from "../ui.js";

const ORIGEN = { modelo_cox: "modelo con las variables del cliente", poblacional_km: "curva de toda la población (igual para todos)" };
const REF = { disponible: "disponible", vencida: "vencida", insuficiente: "historia insuficiente" };
const TITULO = "Cuándo conviene contactar";

/** Texto de la ventana: qué cuantiles hay y qué significan; nunca inventa un límite que no se alcanza. */
export function textoVentana(s) {
  if (s.estado === "sin_historial") return "Sin compras registradas: no hay ritmo de compra del que partir y no se estima fecha.";
  if (!["estimado", "estimacion_parcial"].includes(s.estado)) return esc(s.motivos?.[0] || "Estimación no disponible.");
  if (s.ventana_tipo === "p10_p50") {
    if (s.dias_p10 == null) return `Ni siquiera el 10 % de posibilidad de compra se alcanza en ${num(s.soporte_dias)} días: no hay ventana.`;
    if (s.dias_p50 == null) return `Desde el ${esc(fechaLarga(s.fecha_p10))}; la mitad de posibilidad no se alcanza en ${num(s.soporte_dias)} días: no hay fecha de fin.`;
    const txt = `Inicio probable entre el <strong>${esc(fechaLarga(s.fecha_p10))}</strong> (10 % de posibilidad acumulada) y el <strong>${esc(fechaLarga(s.fecha_p50))}</strong> (50 %).`;
    return s.ventana_utilizable ? txt : `${txt} La ventana es ancha (${num(s.ancho_ventana_dias)} días): solo orientativa.`;
  }
  if (s.ventana_utilizable) return `Entre el <strong>${esc(fechaLarga(s.fecha_p10))}</strong> y el <strong>${esc(fechaLarga(s.fecha_p90))}</strong> (del 10 % al 90 % de posibilidad acumulada; la mitad hacia el ${esc(fechaLarga(s.fecha_p50))}).`;
  if (s.dias_p10 == null) return `Ni siquiera el 10 % de posibilidad de compra se alcanza en ${num(s.soporte_dias)} días: no hay ventana.`;
  const central = s.dias_p50 != null ? `; la mitad de posibilidad hacia el ${esc(fechaLarga(s.fecha_p50))}` : "; la mitad no se alcanza dentro del horizonte";
  return `Desde el ${esc(fechaLarga(s.fecha_p10))}${central}. <strong>El límite superior no se alcanza en ${num(s.soporte_dias)} días</strong>: no hay una ventana utilizable ni una fecha exacta.`;
}

function acumuladaHtml(pa) {
  if (!pa) return "";
  return `<p>Posibilidad estimada de haber comprado: ${Object.entries(pa).map(([d, p]) => `<strong>${esc(pct(p))}</strong> en ${num(Number(d))} días`).join(" · ")}.</p>`;
}

/** Bloque para la ficha: ventana estimada, separada de las fechas de contrato de las coberturas. */
export function proximaFichaHtml(s) {
  if (!s) return "";
  const ref = s.referencia_personal_estado ? `Referencia personal (intervalo habitual entre compras menos días sin comprar): ${esc(REF[s.referencia_personal_estado] || s.referencia_personal_estado)}${s.referencia_personal_dias != null ? ` (${num(s.referencia_personal_dias)} días)` : ""}.` : "";
  return `<section class="panel"><h2>¿Cuándo conviene contactar? ${enPrueba()}</h2>
    <p>${textoVentana(s)}</p>${acumuladaHtml(s.prob_acumulada)}
    <p class="muted">Estimada con datos hasta el ${esc(fechaLarga(s.corte))} con ${esc(ORIGEN[s.origen_estimacion] || "—")}. ${ref}</p>
    <p class="muted">${esc(s.nota)} Las fechas de fin de cobertura son de contrato y se muestran aparte.</p>
    ${(s.limitaciones || []).length ? `<ul class="muted">${s.limitaciones.map(l => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}</section>`;
}

export async function vistaProxima() {
  const { q } = ruta();
  const dias = q.get("dias") || "30";
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-prox")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando las ventanas estimadas…")}`;
  let d;
  try { d = await api("GET", `/api/proxima?dias=${encodeURIComponent(dias)}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("Estimación no disponible: no hay una publicación de este modelo.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const s = d.sombra, c = d.conteos || {};
  const tipos = new Set(d.items.map(i => i.ventana_tipo));
  const nivel = tipos.size !== 1 ? "" : tipos.has("p10_p50") ? "solo del inicio probable (10 % de posibilidad) a la mitad de posibilidad (50 %); no marca un final" : "desde que la compra empieza a ser posible (10 % de posibilidad) hasta que es muy probable (90 %)";
  d.items.sort((a, b) => a.ventana_desde.localeCompare(b.ventana_desde) || a.ventana_hasta.localeCompare(b.ventana_hasta) || a.cliente_id.localeCompare(b.cliente_id));
  const visibles = d.items.slice(0, 15);
  const sinVentana = (c.estimacion_parcial || 0) + (c.estimado || 0);
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Ventanas en las que es probable que cada cliente vuelva a comprar, según su ritmo. Ayudan a preparar el contacto; no son fechas de compra ni de contrato.",
    contexto: [ctxDatos(s.corte, "Estimación con datos hasta"), { etiqueta: "Horizonte", valor: "hasta 60 días" }, { etiqueta: "Ventanas que empiezan en", valor: `${esc(dias)} días` }] })}
  ${avisoPrueba(`No crea recordatorios${d.recordatorios_automaticos ? "" : " (desactivados)"} ni cambia la cartera.`)}
  ${hallazgo({
    que: `<strong>${plural(d.items.length, "cliente tiene", "clientes tienen")}</strong> una ventana estimada que empieza en los próximos ${num(d.dias)} días desde el ${esc(fechaLarga(s.corte))}.`,
    porque: "Es una estimación con incertidumbre: la ventana marca desde cuándo y hasta cuándo es más probable el inicio de la compra. Un vencimiento de cobertura es otra cosa: una fecha de contrato.",
    accion: visibles[0] && puede("cartera.ver") ? `<a class="boton" href="#/clientes/${encodeURIComponent(visibles[0].cliente_id)}?pestana=senales">Ver el primer cliente</a>` : "",
  })}
  <section class="panel"><h2>Ventanas de los primeros ${num(visibles.length)} clientes</h2>
    <form class="filtros" id="f-prox"><label>Ventanas que empiezan en los próximos <span class="ayuda">Días contados desde la fecha de los datos (1 a 60).</span><input name="dias" type="number" min="1" max="60" value="${esc(dias)}" inputmode="numeric"></label><button>Actualizar la lista</button></form>
    ${visibles.length ? graficoRangos(visibles.map(i => ({ etiqueta: i.cliente_id, desde: i.ventana_desde, hasta: i.ventana_hasta, probable: i.ventana_tipo === "p10_p90" ? i.fecha_p50 : null, recencia: i.recencia_dias, contractual: i.proximo_fin_cobertura })), { corte: s.corte, titulo: `Cuándo es probable que cada cliente vuelva a comprar (${num(visibles.length)} de ${num(d.items.length)}, el más próximo arriba)`, nivel, horizonteDias: 60 })
      : vacio("Ningún cliente tiene una ventana utilizable que empiece en este plazo.", "Una ventana utilizable tiene sus dos límites dentro de 60 días y mide 30 días o menos. No se inventan fechas.")}
  </section>
  ${d.items.length ? `<section class="panel"><h2>Lista completa (${num(d.items.length)})</h2>
  <div class="tabla"><table class="apilable"><caption>Orden: inicio de la ventana, el más próximo primero. Mismas fechas que el gráfico. La columna «Fin de cobertura» es de contrato, no estimada.</caption><thead><tr><th scope="col">Cliente</th><th scope="col">Ventana estimada</th><th scope="col" class="n">Ancho</th><th scope="col">Días sin comprar</th><th scope="col">Fin de cobertura (contrato)</th><th scope="col">Acción en la cartera</th><th scope="col"><span class="oculto-visual">Abrir</span></th></tr></thead><tbody>
  ${d.items.map(i => `<tr><td data-et="Cliente"><strong>${esc(i.cliente_id)}</strong></td>
    <td data-et="Ventana estimada">${esc(fechaLarga(i.ventana_desde))} a ${esc(fechaLarga(i.ventana_hasta))}${i.ventana_tipo === "p10_p50" ? '<span class="muted">inicio probable (10 % a 50 %)</span>' : ""}</td><td class="n" data-et="Ancho">${num(i.ancho_ventana_dias)} días</td><td data-et="Días sin comprar">${num(i.recencia_dias)}</td>
    <td data-et="Fin de cobertura (contrato)">${i.proximo_fin_cobertura ? esc(fechaLarga(i.proximo_fin_cobertura)) : '<span class="muted">Sin cobertura próxima</span>'}</td><td data-et="Acción en la cartera">${esc(i.accion_c1 || "—")}${i.episodio ? (i.episodio.tarea_id ? `<span class="muted"><a href="#/tareas/${i.episodio.tarea_id}">${i.episodio.compartida ? "Motivo añadido a un seguimiento" : "Seguimiento"}</a></span>` : '<span class="muted">Episodio abierto</span>') : ""}</td>
    <td>${puede("cartera.ver") ? `<a class="boton-sec" href="#/clientes/${encodeURIComponent(i.cliente_id)}?pestana=senales">Ver cliente<span class="oculto-visual"> ${esc(i.cliente_id)}</span></a>` : ""}</td></tr>`).join("")}
  </tbody></table></div></section>` : ""}
  <section class="panel"><h2>Clientes sin ventana utilizable</h2>
    <p>${plural(c.ventana_utilizable || 0, "cliente tiene", "clientes tienen")} ventana utilizable en este corte; ${plural(sinVentana, "cliente tiene", "clientes tienen")} estimación pero sin ventana utilizable (demasiado ancha o con un límite que no se alcanza en 60 días)${c.sin_historial ? `; ${plural(c.sin_historial, "cliente no tiene", "clientes no tienen")} compras` : ""}. Para ellos no se muestra una fecha.</p></section>
  <details class="panel"><summary>Cómo se obtuvo esta estimación</summary>
    <p>${esc(s.estado_experimento)} · ${s.tipo === "cox" ? "modelo con las variables del cliente" : "curva de toda la población"} · modelo ${esc(s.version_modelo)}. ${esc(d.nota)} ${esc(d.precedencia_c1)}</p>
    ${(d.limitaciones || []).length ? `<ul>${d.limitaciones.map(l => `<li>${esc(l)}</li>`).join("")}</ul>` : ""}
    ${detalleTecnico(`<pre>${esc(JSON.stringify(s, null, 2))}</pre>`, "Publicación (datos originales)")}</details>`;
  activarTooltips();
  document.getElementById("f-prox").addEventListener("submit", e => { e.preventDefault(); ir(`#/proxima?dias=${new FormData(e.target).get("dias")}`); });
}
