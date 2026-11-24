// V02 Inicio ejecutivo (Gerencia), V03 Resumen comercial (Ventas) y V10 Coberturas y renovaciones (Operaciones).
import {
  $vista, S, api, conSigno, cop, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, mesLargo, millones, nombreSegmento,
  nuevoTurno, num, pct, plural, puede, relativoVencimiento, ruta, tieneRol, vigente,
} from "../nucleo.js";
import {
  activarTooltips, barras, ctxDatos, ctxOrigen, encabezado, fuenteCierre, graficoLinea, hallazgo, indicadores, pestanas, tablaHtml, vacio, verDatos,
} from "../ui.js";

const ESTADOS_TAREA = { abierta: "Abiertas, sin responsable", asignada: "Asignadas", pospuesta: "Pospuestas", atendida: "Atendidas", descartada: "Descartadas" };
const TITULOS = { ventas: "Resumen comercial", operaciones: "Coberturas y renovaciones", gerencia: "Resumen ejecutivo" };
const DESCRIPCION = {
  gerencia: "Cómo fueron las ventas del último mes completo, dónde cambió el resultado y qué necesita atención.",
  ventas: "A quién conviene revisar primero y por qué. Desde aquí abres la cartera o la ficha de cada cliente.",
  operaciones: "Qué coberturas ya vencieron y cuáles vencen pronto, contadas desde la fecha de los datos.",
};

export async function vistaTableros(rolSel) {
  const roles = ["gerencia", "ventas", "operaciones"].filter(r => puede(`tablero.${r}`));
  const propio = roles.find(r => tieneRol(r)) || roles[0];
  const rol = roles.includes(rolSel) ? rolSel : propio;
  if (!rol) { $vista.innerHTML = `${encabezado({ titulo: "Resumen" })}${vacio("Tu perfil no tiene un tablero asignado.")}`; return; }
  const { q } = ruta();
  const turno = nuevoTurno();
  $vista.innerHTML = `${encabezado({ titulo: TITULOS[rol] })}${estadoHtml("", "Cargando el resumen…")}`;
  let t, extra = {};
  try {
    t = await api("GET", `/api/cierres/${S.cierre}/tableros/${rol}`);
    // Complementos que la pantalla puede mostrar sin ellos: cada uno falla por separado y lo dice.
    const pedir = (cond, r) => cond ? api("GET", r).catch(e => e) : Promise.resolve(null);
    const [resumen, ops, pqrs] = await Promise.all([
      pedir(rol !== "operaciones" && puede("cartera.ver"), `/api/cierres/${S.cierre}/resumen`),
      pedir(rol === "gerencia" && puede("tablero.operaciones"), `/api/cierres/${S.cierre}/tableros/operaciones`),
      pedir(rol === "gerencia" && puede("pqrs.indicadores"), "/api/pqrs-indicadores")]);
    extra = { resumen, ops, pqrs };
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULOS[rol] })}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  const cuerpo = rol === "ventas" ? tableroVentas(t, q, extra) : rol === "operaciones" ? tableroOperaciones(t, q) : tableroGerencia(t, q, extra);
  $vista.innerHTML = `${encabezado({ titulo: TITULOS[rol], descripcion: DESCRIPCION[rol], contexto: [ctxDatos(t.cierre.corte), ctxOrigen(t.cierre.origen || undefined)] })}${cuerpo}`;
  activarTooltips();
}

const fallo = (x, que) => x instanceof Error ? `<p class="muted">No se pudo cargar ${que}. <button type="button" class="enlace" data-reintentar>Volver a intentar</button></p>` : "";
const ok = x => x && !(x instanceof Error);
const revisar = r => (r.por_accion || []).filter(x => x.accion !== "Seguimiento habitual").reduce((s, x) => s + x.clientes, 0);

// ---------------------------------------------------------------- V02 · Gerencia
/** Variación porcentual solo con base positiva y periodos comparables; con base cero se dice «sin base porcentual». */
export function variacion(actual, anterior) {
  if (actual == null || anterior == null) return { diferencia: null, porcentaje: null };
  const d = actual - anterior;
  return { diferencia: d, porcentaje: anterior > 0 ? d / anterior * 100 : null };
}

function tableroGerencia(t, q, { resumen, ops, pqrs }) {
  const i = t.indicadores, c = t.comparacion, corte = t.cierre.corte;
  const comparable = c && c.estado === "ok";
  const v = comparable ? variacion(c.valor, c.valor_anterior) : null;
  const fams = comparable ? c.familias.filter(f => f.familia !== "Total" && f.diferencia != null).sort((a, b) => Math.abs(b.diferencia) - Math.abs(a.diferencia)) : [];
  const top = fams[0];
  const verFinanzas = (fam = "") => puede("finanzas.ver") && comparable ? `#/finanzas?seccion=resultado&serie=ventas&desde=${encodeURIComponent(c.mes_anterior)}&hasta=${encodeURIComponent(c.mes)}${fam ? `&familia=${encodeURIComponent(fam)}` : ""}` : null;
  const porc = v?.porcentaje == null ? "sin base porcentual" : `${v.porcentaje < 0 ? "−" : "+"}${num(Math.round(Math.abs(v.porcentaje) * 10) / 10)} %`;
  const que = comparable
    ? `En <strong>${esc(mesLargo(c.mes))}</strong> se confirmaron ventas por <strong>${esc(millones(c.valor))}</strong>: ${v.diferencia === 0 ? "igual que" : `${esc(millones(Math.abs(v.diferencia)))} ${v.diferencia < 0 ? "menos" : "más"} que`} en ${esc(mesLargo(c.mes_anterior))} (${esc(porc)}).`
    : "Todavía no hay dos meses completos para comparar. Se muestra el histórico disponible.";
  const porque = top ? `La familia <strong>${esc(top.familia)}</strong> explica el cambio más grande: ${esc(conSigno(top.diferencia))}. Es una diferencia aritmética entre meses; la causa comercial requiere más evidencia.` : "";
  const clientesRevisar = ok(resumen) ? revisar(resumen) : null;
  const accion = [verFinanzas() && `<a class="boton" href="${esc(verFinanzas(top?.familia))}">Ver ventas por familia</a>`,
    puede("cartera.ver") && '<a class="boton-sec" href="#/agenda">Ver clientes a revisar</a>'].filter(Boolean).join("");
  const historicoCompleto = q.get("historico") === "todo";
  const serie = t.evolucion.map(s => ({ periodo: s.periodo, valor: s.valor_cop }));
  const visibles = historicoCompleto ? serie : serie.slice(-12);
  const incompletos = c?.meses_incompletos?.length ? `<p class="aviso-cifras" role="note">Mes incompleto, no se compara: ${esc(c.meses_incompletos.map(mesLargo).join(", "))}.</p>` : "";
  // Focos: cada uno con su evidencia y su propio enlace; un fallo no oculta los demás.
  const focos = [];
  if (ok(ops)) focos.push(`<tr><th scope="row">Coberturas por vencer</th><td>${plural(ops.coberturas_proximas.length, "cobertura vence", "coberturas vencen")} en 45 días y ${plural(ops.coberturas_vencidas.length, "ya venció", "ya vencieron")} (se cuentan coberturas, no clientes)</td><td><a href="#/tableros/operaciones">Ver coberturas</a></td></tr>`);
  if (clientesRevisar != null) focos.push(`<tr><th scope="row">Clientes para revisar</th><td>${plural(clientesRevisar, "cliente necesita", "clientes necesitan")} una acción distinta del seguimiento habitual, de ${num(resumen.resumen.clientes)}</td><td><a href="#/agenda">Abrir la cartera</a></td></tr>`);
  if (ok(pqrs)) focos.push(`<tr><th scope="row">Solicitudes pendientes</th><td>${plural(pqrs.pendientes ?? 0, "solicitud está", "solicitudes están")} recibidas o en gestión (estado actual, no del cierre)</td><td><a href="#/pqrs">Ver solicitudes</a></td></tr>`);
  return `${hallazgo({ que, porque, accion })}
  ${incompletos}
  ${indicadores([
    comparable && { etiqueta: "Ventas del último mes completo", valor: esc(millones(c.valor)), detalle: `${esc(mesLargo(c.mes))} · ventas confirmadas en COP` },
    comparable && { etiqueta: "Cambio frente al mes anterior", valor: esc(conSigno(v.diferencia)), detalle: `${esc(porc)} · base: ${esc(mesLargo(c.mes_anterior))}, ${esc(millones(c.valor_anterior))}` },
    clientesRevisar != null && { etiqueta: "Clientes que requieren revisión", valor: num(clientesRevisar), detalle: `de ${plural(resumen.resumen.clientes, "cliente", "clientes")} · datos hasta el ${esc(fechaLarga(corte))}` },
  ])}
  ${fallo(resumen, "el conteo de clientes")}
  <div>
    <section class="panel"><h2>¿Cómo evolucionaron las ventas?</h2>
      ${graficoLinea(visibles, [], { marcas: comparable ? [c.mes_anterior, c.mes] : [], titulo: `Ventas confirmadas por mes${historicoCompleto ? " (todo el histórico)" : " (últimos 12 meses)"}` })}
      <p class="muted">${comparable ? `Puntos destacados: ${esc(mesLargo(c.mes_anterior))} y ${esc(mesLargo(c.mes))}, los meses comparados. ` : ""}${serie.length > 12 ? `<a href="#/tableros/gerencia${historicoCompleto ? "" : "?historico=todo"}">${historicoCompleto ? "Ver solo los últimos 12 meses" : `Ver todo el histórico (${serie.length} meses)`}</a>` : ""}</p>
    </section>
    <section class="panel"><h2>¿Dónde cambió el resultado?</h2>
      ${comparable ? `<p class="muted">Diferencia de cada familia entre ${esc(mesLargo(c.mes_anterior))} y ${esc(mesLargo(c.mes))}, ordenada por tamaño. Las barras rayadas son disminuciones.</p>
      ${barras(fams.map(f => ({ etiqueta: f.familia, valor: f.diferencia, texto: conSigno(f.diferencia), href: verFinanzas(f.familia) })), { signo: true, etiquetaAria: "Diferencia por familia; cada barra abre Finanzas con esos dos meses" })}
      ${verDatos({ titulo: "Ver cifras exactas por familia", tabla: { cabeceras: ["Familia", mesLargo(c.mes_anterior), mesLargo(c.mes), "Diferencia"], numericas: new Set([1, 2, 3]), filas: fams.map(f => [esc(f.familia), cop(f.valor_anterior), cop(f.valor), esc(conSigno(f.diferencia))]) }, regla: "Las diferencias por familia suman la diferencia del total publicado." })}`
        : vacio("No hay dos meses completos para comparar por familia.")}
    </section>
  </div>
  <section class="panel"><h2>Dónde actuar ahora</h2>
    ${focos.length ? `<div class="tabla"><table><thead><tr><th scope="col">Hallazgo</th><th scope="col">Evidencia</th><th scope="col">Acción</th></tr></thead><tbody>${focos.join("")}</tbody></table></div>` : vacio("No hay focos disponibles para tu perfil.")}
    ${fallo(ops, "las coberturas")}${fallo(pqrs, "las solicitudes")}
  </section>
  <section class="panel"><h2>Ingreso acumulado por segmento de clientes</h2>
    <p class="muted">Ingreso confirmado de toda la historia hasta el ${esc(fechaLarga(corte))}: ${esc(millones(i.ingreso_cop))} de ${plural(i.clientes, "cliente", "clientes")}; ${num(i.clientes_frios)} llevan 90 días o más sin comprar. No es el ingreso de un mes.</p>
    ${barras(t.segmentos.map(s => ({ etiqueta: nombreSegmento(s.segmento), valor: s.ingreso_cop, texto: millones(s.ingreso_cop), nota: plural(s.clientes, "cliente", "clientes") })), { etiquetaAria: "Ingreso acumulado por segmento" })}
  </section>
  ${verDatos({ tabla: { cabeceras: ["Mes", "Ventas confirmadas (COP)"], numericas: new Set([1]), filas: t.evolucion.map(s => [esc(mesLargo(s.periodo)), s.valor_cop == null ? "Sin dato (mes incompleto)" : cop(s.valor_cop)]) },
    fuente: `${fuenteCierre(t.fuente)} · tablas ${esc((t.fuente?.tablas || []).join(" y "))}`, actualizado: esc(`Datos hasta el ${fechaLarga(corte)}`),
    regla: `Último mes completo frente al anterior: variación = (actual − anterior) ÷ anterior × 100, solo con base mayor que cero. Ingreso acumulado: ${esc(cop(i.ingreso_cop))}, ${num(i.ventas_confirmadas)} ventas confirmadas. Las cifras coinciden con Finanzas e Informes de este mismo cierre.` })}`;
}

// ---------------------------------------------------------------- V03 · Resumen comercial (Ventas)
function tableroVentas(t, q, { resumen }) {
  const sel = q.get("segmento") || "";
  const s = t.segmentos.find(x => x.segmento === sel);
  const e = t.etiquetas;
  const filas = t.oportunidades.map(o => {
    const ev = o.evidencia || {};
    const hechos = [];
    if (ev.dias_sin_compra != null) hechos.push(`${num(ev.dias_sin_compra)} días sin comprar`);
    if (ev.renovaciones_proximas) hechos.push(`${plural(ev.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en 45 días`);
    if (ev.coberturas_vencidas) hechos.push(plural(ev.coberturas_vencidas, "cobertura vencida", "coberturas vencidas"));
    if (ev.prob_compra_30d != null) hechos.push(`posibilidad estimada de compra ${pct(ev.prob_compra_30d)}`);
    return `<tr><td data-et="Cliente"><strong>${esc(o.cliente_id)}</strong></td><td data-et="Acción">${esc(o.accion || o.tipo)}${o.motivos.length > 1 ? `<span class="muted">También: ${esc(o.motivos.filter(m => m !== o.accion).join(", "))}</span>` : ""}</td>
      <td data-et="Motivo">${esc(hechos.join(" · ") || "—")}</td><td data-et="Revisar desde">${o.fecha_sugerida ? esc(fechaLarga(o.fecha_sugerida)) : "Sin fecha sugerida"}</td>
      <td>${puede("cartera.ver") ? `<a class="boton-sec" href="#/clientes/${encodeURIComponent(o.cliente_id)}">Ver cliente<span class="oculto-visual"> ${esc(o.cliente_id)}</span></a>` : ""}</td></tr>`;
  }).join("");
  const porAccion = ok(resumen) ? barras(resumen.por_accion.map(x => ({ etiqueta: x.accion, valor: x.clientes, texto: plural(x.clientes, "cliente", "clientes"), href: puede("cartera.ver") ? `#/agenda?accion=${encodeURIComponent(x.accion)}` : null })),
    { etiquetaAria: "Clientes por acción principal; cada barra abre la cartera filtrada" }) : fallo(resumen, "el conteo por acción");
  const n = ok(resumen) ? revisar(resumen) : null;
  return `${pestanas([["resumen", "Resumen", "#/tableros/ventas"], ...(puede("cartera.ver") ? [["cartera", "Cartera completa", "#/agenda"]] : [])], "resumen", "Vista comercial")}
  ${hallazgo({
    que: n != null ? `<strong>${plural(n, "cliente necesita", "clientes necesitan")} revisión</strong> de ${plural(t.total_clientes, "cliente", "clientes")}.` : `${plural(t.total_clientes, "cliente", "clientes")} en la cartera.`,
    porque: "Cada cliente aparece una sola vez, en su acción principal: cobertura por vencer, reactivación, recompra o primera compra.",
    accion: puede("cartera.ver") ? '<a class="boton" href="#/agenda">Abrir la cartera</a>' : "",
  })}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>Hasta ${num(t.limite_oportunidades ?? 20)} oportunidades prioritarias</h2>
      <p class="muted">${t.total_oportunidades > t.oportunidades.length ? `Se muestran ${num(t.oportunidades.length)} de ${num(t.total_oportunidades)} oportunidades del cierre (límite de esta lista).` : `Se muestran las ${num(t.oportunidades.length)} oportunidades del cierre.`} Orden: prioridad de la acción y posibilidad estimada de compra.</p>
      ${filas ? `<div class="tabla"><table class="apilable"><thead><tr><th scope="col">Cliente</th><th scope="col">Acción</th><th scope="col">Motivo comprobable</th><th scope="col">Revisar desde</th><th scope="col"><span class="oculto-visual">Abrir</span></th></tr></thead><tbody>${filas}</tbody></table></div>` : vacio("No hay oportunidades publicadas en este cierre.")}
    </section>
    <section class="panel"><h2>¿Qué acción necesita cada cliente?</h2>${porAccion}
      <p class="muted">Pulsa una barra para ver esos clientes en la cartera.</p></section>
  </div>
  <details class="panel"><summary>Ver clientes por segmento y etiquetas de frecuencia</summary>
    <div class="grid2">
      <div><h3>Clientes por segmento</h3>
        ${barras(t.segmentos.map(x => ({ etiqueta: nombreSegmento(x.segmento), nota: x.descripcion || "", valor: x.clientes, texto: plural(x.clientes, "cliente", "clientes"), href: `#/tableros/ventas${x.segmento === sel ? "" : `?segmento=${encodeURIComponent(x.segmento)}`}`, activo: x.segmento === sel })), { etiquetaAria: "Clientes por segmento; pulsa uno para ver su explicación" })}
        ${s ? `<div class="estado"><strong>${esc(nombreSegmento(s.segmento))}.</strong> ${esc(s.descripcion || "Sin descripción publicada.")} ${puede("cartera.ver") ? `<a href="#/agenda?segmento=${encodeURIComponent(s.segmento)}">Ver estos ${plural(s.clientes, "cliente", "clientes")} en la cartera</a>` : ""}</div>` : '<p class="muted">Pulsa un segmento para ver qué significa.</p>'}</div>
      <div><h3>Etiquetas que pueden coincidir</h3>
        <dl class="cifras"><div><dt>Compran con frecuencia</dt><dd>${num(e.frecuentes)}</dd></div><div><dt>Llevan 90 días o más sin comprar</dt><dd>${num(e.frios)}</dd></div><div><dt>Ambas cosas a la vez</dt><dd>${num(e.ambas ?? 0)}</dd></div></dl>
        <p class="muted">Un cliente que compraba con frecuencia puede llevar 90 días sin comprar. Por eso estos conteos no se suman.</p></div>
    </div>
    ${verDatos({ tabla: { cabeceras: ["Segmento", "Clientes", "Descripción"], numericas: new Set([1]), filas: t.segmentos.map(x => [`${esc(nombreSegmento(x.segmento))}<span class="muted">${esc(x.segmento)}</span>`, num(x.clientes), esc(x.descripcion || "—")]) }, fuente: `Tabla «segmentos» del cierre ${esc(t.cierre.id)}`, actualizado: esc(`Datos hasta el ${fechaLarga(t.cierre.corte)}`) })}
  </details>`;
}

// ---------------------------------------------------------------- V10 · Coberturas y renovaciones
function tableroOperaciones(t, q) {
  const corte = t.cierre.corte;
  const sel = q.get("intervalo") || "";
  const intervalos = t.intervalos || [];
  const it = intervalos.find(x => x.clave === sel);
  const enIntervalo = x => !it || (it.desde == null ? x.estado === "vencida" : x.dias_para_fin >= it.desde && x.dias_para_fin <= it.hasta);
  const fila = x => `<tr><td data-et="Cliente">${puede("cartera.ver") ? `<a href="#/clientes/${encodeURIComponent(x.cliente_id)}">${esc(x.cliente_id)}</a>` : esc(x.cliente_id)}</td><td data-et="Producto">${esc(x.producto || x.producto_id)}</td><td data-et="Fecha de fin (contrato)">${esc(fechaLarga(x.fecha_fin))}</td><td data-et="Situación a la fecha de los datos"><strong>${esc(relativoVencimiento(x.dias_para_fin).replace("del cierre", "de los datos"))}</strong></td></tr>`;
  const prox = t.coberturas_proximas.filter(enIntervalo), venc = t.coberturas_vencidas.filter(enIntervalo);
  const total = intervalos.reduce((s, x) => s + x.coberturas, 0);
  const primera = t.coberturas_proximas[0];
  const estados = Object.entries(t.tareas_por_estado || {});
  const tabla = (lista, vacioTxt) => lista.length ? `<div class="tabla"><table class="apilable"><thead><tr><th scope="col">Cliente</th><th scope="col">Producto</th><th scope="col">Fecha de fin (contrato)</th><th scope="col">Situación a la fecha de los datos</th></tr></thead><tbody>${lista.map(fila).join("")}</tbody></table></div>` : vacio(vacioTxt);
  if (!t.detalle_disponible) return vacio("Este cierre no publica el detalle de coberturas.", `Solo hay totales por cliente: ${num(t.resumen_coberturas.renovaciones_proximas)} próximas y ${num(t.resumen_coberturas.coberturas_vencidas)} vencidas. No se pueden listar ni agrupar por días.`);
  return `${hallazgo({
    que: `<strong>${plural(t.coberturas_vencidas.length, "cobertura ya venció", "coberturas ya vencieron")}</strong> y <strong>${plural(t.coberturas_proximas.length, "vence", "vencen")}</strong> en los próximos 45 días.`,
    porque: primera ? `La más próxima es la de ${esc(primera.cliente_id)}: ${esc(relativoVencimiento(primera.dias_para_fin).replace("del cierre", "de los datos"))}. Los días se cuentan desde el ${esc(fechaLarga(corte))}, no desde hoy.` : `Los días se cuentan desde el ${esc(fechaLarga(corte))}, no desde hoy.`,
    accion: '<button type="button" data-ir-a="lista-coberturas">Ver la lista ordenada</button>',
  })}
  ${indicadores([
    { etiqueta: "Coberturas vencidas", valor: num(t.coberturas_vencidas.length), detalle: `a la fecha de los datos (${esc(fechaLarga(corte))})` },
    { etiqueta: "Vencen en 45 días", valor: num(t.coberturas_proximas.length), detalle: "se cuentan coberturas: un cliente puede tener varias" },
  ])}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>¿Cuándo vencen?</h2>
      ${barras(intervalos.map(x => ({ etiqueta: x.etiqueta, valor: x.coberturas, texto: plural(x.coberturas, "cobertura", "coberturas"), href: `#/tableros/operaciones${x.clave === sel ? "" : `?intervalo=${x.clave}`}`, activo: x.clave === sel })), { etiquetaAria: "Coberturas por plazo; pulsa uno para listar solo esas" })}
      <p class="muted">Total en estos plazos: ${plural(total, "cobertura", "coberturas")}. ${it ? `Filtro aplicado: ${esc(it.etiqueta)}. <a href="#/tableros/operaciones">Quitar filtro</a>` : "Pulsa una barra para listar solo ese plazo."}</p>
      ${verDatos({ tabla: { cabeceras: ["Plazo", "Coberturas"], numericas: new Set([1]), filas: intervalos.map(x => [esc(x.etiqueta), num(x.coberturas)]) }, fuente: `Tabla «coberturas» del cierre ${esc(t.cierre.id)} (instalaciones publicadas)`, actualizado: esc(`Datos hasta el ${fechaLarga(corte)}`), regla: "Días hasta el fin de cobertura contados desde la fecha de los datos; «vencida» si la fecha de fin es anterior. Los plazos no se solapan." })}
    </section>
    <section class="panel"><h2>Seguimientos: estado actual</h2>
      <p class="muted">Este bloque muestra las tareas tal como están ahora (${esc(fechaHora(t.tareas_consultadas_en))}), no a la fecha de los datos. No cambia los conteos de coberturas.</p>
      ${estados.length ? `<dl class="cifras">${estados.map(([k, v]) => `<div><dt>${esc(ESTADOS_TAREA[k] || k)}</dt><dd>${num(v)}</dd></div>`).join("")}</dl>` : '<p class="muted">No hay seguimientos registrados.</p>'}
      ${puede("tareas.ver") ? '<a class="boton-sec" href="#/tareas">Abrir seguimientos</a>' : ""}</section>
  </div>
  <section class="panel" id="lista-coberturas" tabindex="-1"><h2>Vencen pronto${it && it.desde != null ? ` · ${esc(it.etiqueta.toLowerCase())}` : ""}</h2><p class="muted">Ordenadas por fecha de fin: primero la más próxima.</p>
    ${tabla(prox, "Ninguna cobertura vence en esta selección.")}</section>
  <section class="panel"><h2>Ya vencidas</h2><p class="muted">Ordenadas de la más antigua a la más reciente.</p>${tabla(venc, "No hay coberturas vencidas en esta selección.")}</section>
  <p class="muted">${esc(t.nota)}</p>`;
}

export const _prueba = { variacion, tablaHtml };
