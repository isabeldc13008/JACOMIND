// V11 Operaciones por revisar (M6, en uso) y V12 Detalle del caso. Compara el valor observado con su referencia;
// el puntaje es rareza: no es probabilidad de fraude ni porcentaje de error, y revisar un caso no cambia importes.
import { $vista, api, clave, cop, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, mesLargo, nuevoTurno, num, plural, ruta, vigente } from "../nucleo.js";
import { avisoPrueba, barras, ctxDatos, detalleTecnico, encabezado, enPrueba, filtrosActivos, hallazgo, pestanas, tablaHtml, vacio } from "../ui.js";

const UNIVERSO = { venta: "Ventas confirmadas", compra: "Compras a proveedores" };
const ESTADO = { pendiente: "Pendiente de revisar", error_confirmado: "Error confirmado", cambio_legitimo: "Cambio legítimo",
  informacion_insuficiente: "Información insuficiente", sin_caso: "Sin caso" };
const DECISION = { favorable_demostracion_sombra: "Favorable solo para demostración", referencia_conservada: "Se mantiene el método de referencia", inconcluso: "Inconclusa" };
const METODO = { isolation_forest: "Isolation Forest (IA)", mediana_mad: "Mediana y desviación habitual del producto (referencia)" };
const EVENTO = { apertura: "Se abrió el caso", correccion_datos: "Corrección de datos", revision: "Revisión registrada", evidencia_actualizada: "Nueva publicación" };
const TITULO = "Operaciones por revisar";
const valor = (x, moneda) => x == null ? "—" : moneda === "COP" ? cop(x) : `${num(Math.round(x * 100) / 100)} ${esc(moneda)}`;
/** Cuánto se aparta de lo habitual, en palabras: «3,4 veces lo habitual», «78 % menos que lo habitual» o «Similar a lo habitual». */
const desvioTexto = r => r == null ? "Sin referencia" : r >= 1.5 ? `${num(Math.round(r * 10) / 10)} veces lo habitual` : r <= 0.67 ? `${num(Math.round((1 - r) * 100))} % menos que lo habitual` : "Similar a lo habitual";
const desvioCorto = r => r == null ? "—" : r >= 1.5 ? `×${num(Math.round(r * 10) / 10)}` : r <= 0.67 ? `−${num(Math.round((1 - r) * 100))} %` : "≈";
/** Medidor en escala logarítmica de 1/10 a 10 veces: el centro es lo habitual. Siempre acompañado de texto. */
function medidorDesvio(r) {
  if (r == null) return "";
  const pos = Math.min(100, Math.max(0, (Math.log10(r) + 1) / 2 * 100));
  const lado = r >= 1.5 ? "mas" : r <= 0.67 ? "menos" : "igual";
  return `<span class="an-medidor" aria-hidden="true"><span class="an-medidor-centro"></span>
    <span class="an-medidor-tramo ${lado}" style="left:${Math.min(50, pos)}%;width:${Math.abs(pos - 50)}%"></span><span class="an-medidor-punto ${lado}" style="left:${pos}%"></span></span>
    <span class="an-medidor-escala" aria-hidden="true"><span>Mucho menos</span><span>Lo habitual</span><span>Mucho más</span></span>`;
}
/** La medida que más se aparta (precio o cantidad), para mostrarla primero. */
const principal = i => {
  const d = x => x == null ? -1 : Math.abs(Math.log(x));
  return d(i.razon_valor_unitario) >= d(i.razon_cantidad) ? { que: "Precio por unidad", r: i.razon_valor_unitario, obs: valor(i.valor_unitario, i.moneda), ref: valor(i.referencia_valor_unitario, i.moneda), otra: { que: "Cantidad", r: i.razon_cantidad } }
    : { que: "Cantidad", r: i.razon_cantidad, obs: `${num(i.cantidad)} ${esc(i.unidad || "")}`, ref: `${num(i.referencia_cantidad == null ? null : Math.round(i.referencia_cantidad * 100) / 100)} ${esc(i.unidad || "")}`, otra: { que: "Precio por unidad", r: i.razon_valor_unitario } };
};

const pp = x => `${x >= 0 ? "+" : "−"}${num(Math.round(Math.abs(x) * 1000) / 10)} puntos`;
function motivoDecision(dc) {
  const c = dc.cumple || {}, v = dc.valores || {};
  if (!dc.valores) return dc.motivos?.length ? ` ${esc(dc.motivos.join(" "))}` : "";
  const por = [];
  if (!c.supera_referencia_ic && v.diferencia != null) por.push(`la mejora de la IA en casos de prueba (${pp(v.diferencia)}, intervalo del 95 % de ${pp(v.ic95[0])} a ${pp(v.ic95[1])}) no es concluyente`);
  if (c.controles_negativos_no_peores === false) por.push(`la IA alertó en más casos normales de control que la referencia (${num(Math.round(v.alertas_controles_candidato * 1000) / 10)} % frente a ${num(Math.round(v.alertas_controles_referencia * 1000) / 10)} %)`);
  if (c.meta_deteccion_candidato === false) por.push("la IA no alcanza la meta de detección del 80 %");
  if (c.trm_sin_cambio === false) por.push("un cambio solo de TRM alteró el puntaje");
  return por.length ? `, porque ${esc(por.join(" y "))}` : "";
}

function filtros(d, q) {
  const f = d.filtros, o = d.opciones;
  const sel = (n, etiqueta, ops, actual, txt = x => x) => `<label>${etiqueta} <select name="${n}"><option value="">Todos</option>${ops.map(x => `<option value="${esc(x)}"${x === actual ? " selected" : ""}>${esc(txt(x))}</option>`).join("")}</select></label>`;
  const enlace = cambio => { const n = new URLSearchParams(q); n.delete("caso"); n.delete("guardado"); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/anomalias?${n}`; };
  const activos = [f.periodo && { texto: `Mes: ${mesLargo(f.periodo)}`, quitar: enlace({ periodo: "" }) }, f.producto && { texto: `Producto: ${f.producto}`, quitar: enlace({ producto: "" }) },
    f.moneda && { texto: `Moneda: ${f.moneda}`, quitar: enlace({ moneda: "" }) }, f.estado && { texto: `Estado: ${ESTADO[f.estado] || f.estado}`, quitar: enlace({ estado: "" }) },
    f.vista && f.vista !== "cola" && { texto: f.vista === "todas" ? "Todas las operaciones" : "Sin historia suficiente", quitar: enlace({ vista: "" }) }].filter(Boolean);
  const rapidos = [["", "Todos"], ["pendiente", "Pendientes"], ["error_confirmado", "Errores"], ["cambio_legitimo", "Legítimos"], ["informacion_insuficiente", "Sin datos suficientes"]];
  return `<section class="panel an-filtros"><div class="an-rapidos" role="group" aria-label="Mostrar por estado de revisión">
      ${rapidos.map(([k, t]) => `<a class="an-rapido${(f.estado || "") === k ? " activo" : ""}" href="${esc(enlace({ estado: k }))}" ${(f.estado || "") === k ? 'aria-current="true"' : ""}>${t}</a>`).join("")}</div>
    <details${f.periodo || f.producto || f.moneda || (f.vista && f.vista !== "cola") ? " open" : ""}><summary>Más filtros</summary>
    <form class="filtros" id="f-an"><input type="hidden" name="universo" value="${esc(d.universo)}"><input type="hidden" name="estado" value="${esc(f.estado || "")}">
    ${sel("periodo", "Mes", o.periodos, f.periodo, mesLargo)}${sel("producto", "Producto", o.productos, f.producto)}${sel("moneda", "Moneda", o.monedas, f.moneda)}
    <label>Qué mostrar <select name="vista">${[["cola", "Cola para revisar"], ["todas", "Todas las operaciones"], ["sin_historia", "Sin historia suficiente"]].map(([k, v]) => `<option value="${k}"${k === f.vista ? " selected" : ""}>${v}</option>`).join("")}</select></label>
    <button class="sec">Aplicar</button></form>
    ${d.puede_exportar ? `<p class="muted"><a href="/api/anomalias/exportar.csv?universo=${esc(d.universo)}" download>Descargar todas las operaciones publicadas (CSV)</a>; no aplica los filtros de pantalla.</p>` : ""}</details>
    ${activos.length ? filtrosActivos(activos, `#/anomalias?universo=${esc(d.universo)}`) : ""}</section>`;
}

function senal(i) {
  return i.estado_puntuacion !== "puntuada" ? '<span class="an-senal">Sin historia suficiente</span>'
    : i.alerta ? `<span class="an-senal alerta">Prioridad ${num(i.prioridad)} de ${num(i.cupo_periodo)} en ${esc(mesLargo(i.periodo || i.fecha.slice(0, 7)))}</span>`
      : i.fuera_de_cupo ? '<span class="an-senal">Señalada por reglas, fuera de la capacidad</span>' : '<span class="an-senal">Muestra de control</span>';
}

function fila(i, q) {
  const n = new URLSearchParams(q); n.delete("guardado"); n.set("universo", i.tipo_operacion); n.set("caso", i.operacion_id);
  const contraparte = i.tipo_operacion === "venta" ? `Cliente ${esc(i.cliente_id)}` : `Proveedor ${esc(i.proveedor_id)}`;
  const pendiente = !i.estado_revision || i.estado_revision === "pendiente";
  const puntuada = i.estado_puntuacion === "puntuada";
  const m = puntuada ? principal(i) : null;
  return `<li class="an-caso${i.alerta ? " alerta" : ""}${pendiente ? "" : " revisado"}">
    <div class="an-prioridad">${i.alerta ? `<span class="an-num" aria-hidden="true">${num(i.prioridad)}</span>` : '<span class="an-num sec" aria-hidden="true">·</span>'}${senal(i)}</div>
    <div class="an-quien"><strong>${esc(i.operacion_id)}</strong><span>${esc(fechaLarga(i.fecha))}</span><span class="muted">${contraparte} · ${esc(i.producto_id)}</span></div>
    ${m ? `<div class="an-desvio"><p class="an-que">${m.que}: <strong>${esc(desvioTexto(m.r))}</strong></p>${medidorDesvio(m.r)}
      <p class="muted an-valores">${m.obs} <span>frente a</span> ${m.ref} habitual${m.otra.r != null && desvioTexto(m.otra.r) !== "Similar a lo habitual" ? ` · ${m.otra.que}: ${esc(desvioTexto(m.otra.r).toLowerCase())}` : ""}</p></div>`
      : `<div class="an-desvio"><p class="an-que"><strong>No se pudo comparar</strong></p><p class="muted">${esc((i.motivos || [])[0] || "Pocas operaciones anteriores del producto.")}</p></div>`}
    <div class="an-estado"><span class="an-estado-chip ${esc(i.estado_revision || "pendiente")}">${esc(ESTADO[i.estado_revision] || i.estado_revision || "Pendiente de revisar")}</span>
      <a class="${pendiente && i.alerta ? "boton" : "boton-sec"}" href="#/anomalias?${n}">${pendiente ? "Revisar" : "Ver caso"}<span class="oculto-visual"> ${esc(i.operacion_id)}</span></a></div>
  </li>`;
}

async function detalleCaso(d, q) {
  const tipo = d.universo, id = q.get("caso");
  const n = new URLSearchParams(q); n.delete("caso"); n.delete("guardado");
  const volver = { href: `#/anomalias?${n}`, texto: "Volver a la cola" };
  let c;
  try { c = await api("GET", `/api/anomalias/caso?tipo=${encodeURIComponent(tipo)}&id=${encodeURIComponent(id)}`); }
  catch (e) { return `${encabezado({ titulo: `Operación ${id}`, volver })}${errorHtml(e, { reintentar: e.status !== 404 })}`; }
  const p = c.publicaciones[0], v = c.caso_vigente;
  const hist = c.eventos.map(e => `<li><strong>${esc(EVENTO[e.tipo] || e.tipo)}</strong> · ${esc(fechaHora(e.fecha))} · ${esc(e.actor)}${e.estado_nuevo ? ` · ${esc(ESTADO[e.estado_anterior] || e.estado_anterior || "—")} → ${esc(ESTADO[e.estado_nuevo] || e.estado_nuevo)}` : ""}
    ${e.version_examinada ? `<span class="muted"> · versión ${esc(e.version_examinada)}</span>` : ""}${e.motivo ? `<div>${esc(e.motivo)}</div>` : ""}${e.evidencia ? `<div class="muted">Evidencia: ${esc(e.evidencia)}</div>` : ""}</li>`).join("");
  const comparar = (titulo, obs, ref, fmt) => obs == null || ref == null ? `<h3>${titulo}</h3>${vacio("Información insuficiente para comparar.", "Faltan operaciones anteriores del mismo producto.")}` :
    `<h3>${titulo}</h3>${barras([{ etiqueta: "Esta operación", valor: obs, texto: fmt(obs) }, { etiqueta: "Referencia habitual", valor: ref, texto: fmt(ref) }], { etiquetaAria: `${titulo}: esta operación frente a la referencia, desde cero` })}`;
  const form = c.puede_revisar ? `<form id="f-rev" class="campos" novalidate><fieldset><legend>¿Qué encontraste?</legend>
      ${[["error_confirmado", "Error confirmado", "El dato está mal registrado. La corrección se hace cargando los datos de nuevo."], ["cambio_legitimo", "Cambio legítimo", "El valor es correcto: hubo una razón comercial."], ["informacion_insuficiente", "Información insuficiente", "No hay datos suficientes para decidir."]]
        .map(([k, t, a]) => `<label class="en-linea"><input type="radio" name="estado" value="${k}" required> <span><strong>${t}</strong><span class="ayuda" style="display:block">${a}</span></span></label>`).join("")}
      <span class="error-campo" id="err-estado"></span></fieldset>
      <label for="motivo-rev">Motivo <span class="ayuda">Obligatorio: qué revisaste y por qué decides esto.</span><textarea id="motivo-rev" name="motivo" required minlength="3" maxlength="400" aria-describedby="err-motivo"></textarea><span class="error-campo" id="err-motivo"></span></label>
      <label for="evidencia-rev">Evidencia (opcional) <span class="ayuda">Por ejemplo: número de factura o correo consultado.</span><input id="evidencia-rev" name="evidencia" maxlength="400"></label>
      <div class="fila"><button>Guardar la revisión</button></div></form>
      <p class="muted">La revisión no cambia importes ni la operación. Una corrección se hace cargando los datos de nuevo y queda enlazada a este caso.</p>`
    : '<p class="estado">Tu perfil puede consultar este caso, pero no registrar revisiones.</p>';
  return `${encabezado({ titulo: `Operación ${id}`, volver, estado: enPrueba(),
    descripcion: `${esc(UNIVERSO[tipo])} · ${esc(fechaLarga(p.fecha))} · ${tipo === "venta" ? `cliente ${esc(p.cliente_id)}` : `proveedor ${esc(p.proveedor_id)}`} · producto ${esc(p.producto_id)}`,
    contexto: [{ etiqueta: "Estado de revisión", valor: esc(v ? ESTADO[v.estado] : "Sin caso") }, ctxDatos(d.corte, "Publicación con datos hasta")] })}
  <div id="msg-an" role="status" tabindex="-1">${q.get("guardado") ? '<div class="estado ok"><strong>Revisión guardada.</strong> Aparece en «Qué ha pasado con este caso».</div>' : ""}</div>
  ${hallazgo({ que: p.estado_puntuacion === "puntuada" ? (() => { const m = principal(p); return `<strong>${m.que}: ${esc(desvioTexto(m.r).toLowerCase())}.</strong> ${m.obs} frente a ${m.ref} habitual.`; })() : esc((p.motivos || [])[0] || "Operación señalada para revisar."), porque: "Se aparta de lo habitual para este producto. Una señal no confirma un error ni un fraude: hace falta revisarla.", accion: c.puede_revisar ? '<button type="button" data-ir-a="f-rev-titulo">Registrar la revisión</button>' : "" })}
  <div class="grid2">
    <section class="panel"><h2>Esta operación frente a su referencia</h2>
      ${comparar(`Precio unitario (${esc(p.moneda)})`, p.valor_unitario, p.referencia_valor_unitario, x => valor(x, p.moneda))}
      ${comparar(`Cantidad (${esc(p.unidad || "unidades")})`, p.cantidad, p.referencia_cantidad, x => num(Math.round(x * 100) / 100))}
      <p class="muted">Cada medida tiene su propia escala. Referencia: ${plural(p.soporte, "operación anterior", "operaciones anteriores")} del mismo producto${p.antecedentes ? `, del ${esc(fechaLarga(p.antecedentes[0]))} al ${esc(fechaLarga(p.antecedentes[1]))}` : ""}.</p>
      ${(p.motivos || []).length > 1 ? `<h3>Todas las señales</h3><ul>${p.motivos.map(m => `<li>${esc(m)}</li>`).join("")}</ul>` : ""}
      <dl class="cifras"><div><dt>Importe en pesos</dt><dd>${p.importe_cop_oculto ? "Restringido a Finanzas" : p.estado_trm === "ausente" ? "Sin TRM: no convertible" : cop(p.importe_cop)}</dd></div>
        <div><dt>Precio por unidad</dt><dd>${esc(desvioTexto(p.razon_valor_unitario))}</dd></div><div><dt>Cantidad</dt><dd>${esc(desvioTexto(p.razon_cantidad))}</dd></div></dl></section>
    <section class="panel"><h2 id="f-rev-titulo" tabindex="-1">Registrar la revisión</h2>${form}</section>
  </div>
  <section class="panel"><h2>Qué ha pasado con este caso</h2>${hist ? `<ol class="historial">${hist}</ol>` : '<p class="muted">Sin movimientos: la operación todavía no tiene caso de revisión.</p>'}
    ${c.casos.length > 1 ? `<p class="muted">${num(c.casos.length)} versiones del caso por correcciones de datos; las decisiones anteriores se conservan.</p>` : ""}</section>
  <details class="panel"><summary>Ver puntuaciones publicadas y variables</summary>
    ${tablaHtml({ cabeceras: ["Fecha de los datos", "Versión", "Puntaje de rareza", "¿Para revisar?", "Estado"], numericas: new Set([2]), filas: c.publicaciones.map(x => [`${esc(fechaLarga(x.corte))}${x.publicacion_activa ? ' <span class="chip">vigente</span>' : ""}`, esc(x.version_modelo), x.puntaje == null ? "—" : num(Math.round(x.puntaje * 1000) / 1000), x.alerta ? "Sí" : "No", esc(x.estado_puntuacion)]) })}
    <p class="muted">El puntaje mide rareza dentro de su mes y su grupo; no es un porcentaje de error ni de fraude. Las puntuaciones publicadas no se modifican.</p>
    ${detalleTecnico(`<pre>${esc(JSON.stringify(p.variables, null, 2))}</pre><p class="muted">Variables en moneda de origen (desviaciones robustas en logaritmos). La TRM y el importe en pesos no entran al cálculo.</p>`, "Variables")}</details>`;
}

export async function vistaAnomalias() {
  const { q } = ruta();
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-an, #f-rev")) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${estadoHtml("", "Cargando las operaciones por revisar…")}`;
  const params = new URLSearchParams();
  for (const k of ["universo", "periodo", "producto", "moneda", "estado", "vista"]) if (q.get(k)) params.set(k, q.get(k));
  let d;
  try { d = await api("GET", `/api/anomalias?${params}`); }
  catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${errorHtml(e, { reintentar: e.status !== 403 })}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba() })}${vacio("No hay una publicación de operaciones por revisar.", esc(d.mensaje))}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  if (q.get("caso")) {
    const html = await detalleCaso(d, q);
    if (!vigente(turno)) return;
    $vista.innerHTML = html;
    enlazarRevision(d, q);
    return;
  }
  const u = d.universo, r = d.resumen;
  const dec = d.decision ? `${esc(DECISION[d.decision.decision] || d.decision.decision)}${motivoDecision(d.decision)}` : "Sin decisión registrada";
  $vista.innerHTML = `${encabezado({ titulo: TITULO, estado: enPrueba(),
    descripcion: "Ventas y compras cuyo precio o cantidad se aparta mucho de lo habitual para ese producto. Una persona decide si es un error o un cambio legítimo.",
    contexto: [ctxDatos(d.corte), { etiqueta: "Periodo", valor: `${esc(mesLargo(d.desde?.slice(0, 7)))} a ${esc(mesLargo(d.corte.slice(0, 7)))}` }] })}
  ${pestanas(Object.entries(UNIVERSO).map(([k, v]) => [k, v, `#/anomalias?universo=${k}`]), u, "Tipo de operación")}
  ${avisoPrueba("Una señal no confirma un error ni un fraude, y revisar un caso no cambia importes.")}
  ${r.cobertura_temporal === "no_declarada" ? `<p class="aviso-cifras" role="note">Cobertura incompleta: ${esc(r.nota_cobertura || "compras sin cobertura temporal declarada")}.</p>` : ""}
  ${hallazgo({
    que: `<strong>${plural(r.casos_pendientes, "caso está pendiente", "casos están pendientes")} de revisar</strong> en ${esc(UNIVERSO[u].toLowerCase())}.`,
    porque: `${plural(r.alertas, "operación quedó", "operaciones quedaron")} para revisar dentro de la capacidad del equipo (${num(r.capacidad_revision)}). Otras ${num(r.exceso_sobre_cupo)} se señalaron por reglas, fuera de esa capacidad.`,
    accion: d.items[0] ? `<a class="boton" href="#/anomalias?${new URLSearchParams({ universo: u, caso: d.items[0].operacion_id })}">Revisar el primer caso</a>` : "",
  })}
  ${(() => {
    const tot = r.casos_pendientes + r.casos_revisados, hecho = tot ? Math.round(r.casos_revisados / tot * 100) : 0;
    return `<section class="panel an-avance" aria-labelledby="t-avance"><div class="an-avance-cab"><h2 id="t-avance">Avance de la revisión</h2><p><strong>${num(r.casos_revisados)} de ${num(tot)}</strong> casos revisados</p></div>
      <div class="an-avance-barra" role="progressbar" aria-valuemin="0" aria-valuemax="${tot}" aria-valuenow="${r.casos_revisados}" aria-label="Casos revisados"><span style="width:${hecho}%"></span></div>
      <dl class="an-cifras"><div><dt>Pendientes</dt><dd>${num(r.casos_pendientes)}</dd></div>
        <div><dt>Prioritarias este periodo</dt><dd>${num(r.alertas)}</dd><dd class="muted">Las más raras, hasta la capacidad del equipo (${num(r.capacidad_revision)})</dd></div>
        <div><dt>Operaciones comparadas</dt><dd>${num(r.puntuadas)} de ${num(r.validas)}</dd><dd class="muted">${r.abstenciones ? `${plural(r.abstenciones, "sin historia suficiente para comparar", "sin historia suficiente para comparar")}` : "Todas tenían con qué compararse"}</dd></div></dl></section>`;
  })()}
  ${filtros(d, q)}
  <section class="panel"><h2>Cola para revisar <span class="muted an-cuantos">${plural(d.items.length, "operación", "operaciones")}</span></h2>
    <p class="muted">Primero las más raras de cada mes (prioridad 1). El medidor muestra cuánto se aparta la operación de lo habitual para ese producto.</p>
    ${d.items.length ? `<ol class="an-cola">${d.items.map(i => fila(i, q)).join("")}</ol>` : vacio("No hay operaciones con estos filtros.", "", `<a class="boton-sec" href="#/anomalias?universo=${esc(u)}">Quitar filtros</a>`)}
  </section>
  <details class="panel"><summary>Cómo se evaluó y qué queda sin evaluar</summary>
    <p><strong>Método publicado:</strong> ${esc(METODO[d.metodo] || d.metodo)}. Candidato de IA: ${esc(d.candidato === "isolation_forest" ? "Isolation Forest" : "en abstención")}. Decisión de la prueba: ${dec}. ${esc(d.politica_alertas?.convencion || "")}</p>
    <p class="muted">${esc(d.nota)} Versión ${esc(d.version)} · ${esc(d.emision?.tipo === "reconstruccion_historica" ? "reconstrucción histórica" : d.emision?.tipo || "")}.</p>
    <h3>Resultados de la revisión humana</h3>${metricas(d.metricas_revision)}
    <h3>Evaluación por mes</h3>
    ${tablaHtml({ cabeceras: ["Mes", "Válidas", "Evaluadas", "Sin historia", "Para revisar / capacidad", "Fuera de capacidad", "Cobertura temporal"], numericas: new Set([1, 2, 3, 4, 5]),
      filas: d.cobertura.map(c => [esc(mesLargo(c.periodo)), num(c.validas), num(c.puntuadas), num(c.abstenciones.historia_insuficiente), `${num(c.alertas)} / ${num(c.cupo)}`, num(c.exceso_sobre_cupo), c.cobertura_temporal === "declarada" ? "Declarada" : "No declarada"]) })}
    <p class="muted">Excluidas del universo: ${Object.entries(r.excluidas || {}).map(([k, v]) => `${num(v)} ${esc(k.replace(/_/g, " "))}`).join(", ") || "ninguna"}. Muestra de revisión: ${num(d.muestra.seleccionadas)} de ${num(d.muestra.objetivo)} previstas. ${esc(d.muestra.metodo || "")}</p>
    ${detalleTecnico(`<pre>${esc(JSON.stringify({ sombra: d.sombra_id, estado: d.estado_experimento, politica: d.politica_alertas, distribucion: d.resumen.distribucion_puntaje }, null, 2))}</pre>`, "Publicación (datos originales)")}</details>`;
  document.getElementById("f-an").addEventListener("submit", e => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(e.target)) if (v && !(k === "vista" && v === "cola")) p.set(k, v);
    ir(`#/anomalias?${p}`);
  });
}

function metricas(m) {
  const p = m.precision_alertas_revisadas, f = m.falsas_alertas_por_100_normales_revisadas;
  return `<p>${plural(m.revisadas, "operación revisada", "operaciones revisadas")}${Object.keys(m.por_estado).length ? ` (${Object.entries(m.por_estado).map(([k, v]) => `${num(v)} ${esc((ESTADO[k] || k).toLowerCase())}`).join(", ")})` : ""}.</p>
    <p>De las señaladas y revisadas, eran errores: ${p.valor == null ? "no estimable" : num(p.valor)} (${num(p.numerador)} de ${num(p.denominador)})${p.motivo ? ` <span class="muted">— ${esc(p.motivo)}</span>` : ""}.</p>
    <p>Señales en operaciones normales revisadas, por cada 100: ${f.por_100 == null ? "no estimable" : num(f.por_100)} (${num(f.numerador)} de ${num(f.denominador)})${f.motivo ? ` <span class="muted">— ${esc(f.motivo)}</span>` : ""}.</p>
    <p class="muted">${esc(m.nota)}</p>`;
}

function enlazarRevision(d, q) {
  const fr = document.getElementById("f-rev");
  if (!fr) return;
  fr.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(fr), motivo = document.getElementById("motivo-rev");
    let primero = null;
    document.getElementById("err-estado").textContent = fd.get("estado") ? "" : "Elige qué encontraste.";
    if (!fd.get("estado")) primero = fr.querySelector("input[name=estado]");
    const corto = (fd.get("motivo") || "").trim().length < 3;
    motivo.setAttribute("aria-invalid", String(corto)); document.getElementById("err-motivo").textContent = corto ? "Escribe el motivo (al menos 3 letras)." : "";
    if (corto && !primero) primero = motivo;
    if (primero) return primero.focus();
    const b = fr.querySelector("button"); b.disabled = true; b.textContent = "Guardando…";
    try {
      await api("POST", "/api/anomalias/revision", { tipo_operacion: d.universo, operacion_id: q.get("caso"), estado: fd.get("estado"), motivo: fd.get("motivo").trim(), evidencia: fd.get("evidencia") || null, __clave: fr.dataset.clave ||= clave() });
      const n = new URLSearchParams(q); n.set("guardado", "1"); ir(`#/anomalias?${n}`);
    } catch (err) { const m = document.getElementById("msg-an"); m.innerHTML = errorHtml(err); m.focus(); b.disabled = false; b.textContent = "Guardar la revisión"; }
  });
}
