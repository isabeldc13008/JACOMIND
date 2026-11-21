// Tableros por perfil: Ventas, Operaciones y Gerencia (entradas 4, 5 y 6 del plan).
import {
  $vista, S, api, conSigno, cop, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, incluye, mesLargo, millones,
  nuevoTurno, num, pct, plural, puede, relativoVencimiento, ruta, tieneRol, vigente,
} from "../nucleo.js";
import { activarTooltips, barras, fuenteCierre, graficoLinea, respuesta, verDatos } from "../ui.js";

const ESTADOS_TAREA = { abierta: "Abiertas, sin responsable", asignada: "Asignadas", pospuesta: "Pospuestas", atendida: "Atendidas", descartada: "Descartadas" };
const NOMBRES = { ventas: "Ventas", operaciones: "Operaciones", gerencia: "Gerencia" };

export async function vistaTableros(rolSel) {
  const roles = ["gerencia", "ventas", "operaciones"].filter(r => puede(`tablero.${r}`));
  const propio = roles.find(r => tieneRol(r)) || roles[0];
  const rol = roles.includes(rolSel) ? rolSel : propio;
  const { q } = ruta();
  const pestanas = roles.length > 1 ? `<nav class="pestanas" aria-label="Tableros">${roles.map(r => `<a href="#/tableros/${r}" ${r === rol ? 'aria-current="page"' : ""}>${NOMBRES[r]}</a>`).join("")}</nav>` : "";
  const turno = nuevoTurno();
  $vista.innerHTML = `<h1>Tablero de ${NOMBRES[rol]}</h1>${pestanas}${estadoHtml("", "Cargando…")}`;
  let t;
  try { t = await api("GET", `/api/cierres/${S.cierre}/tableros/${rol}`); } catch (e) { if (vigente(turno)) $vista.innerHTML = `<h1>Tablero de ${NOMBRES[rol]}</h1>${pestanas}${errorHtml(e)}`; return; }
  if (!vigente(turno)) return;
  const cuerpo = rol === "ventas" ? tableroVentas(t, q) : rol === "operaciones" ? tableroOperaciones(t, q) : tableroGerencia(t);
  $vista.innerHTML = `<h1>Tablero de ${NOMBRES[rol]}</h1>${pestanas}${cuerpo}`;
  activarTooltips();
}

// ---------------------------------------------------------------- Ventas (entrada 4)
function tableroVentas(t, q) {
  const sel = q.get("segmento") || "";
  const s = t.segmentos.find(x => x.segmento === sel);
  const e = t.etiquetas;
  const filas = t.oportunidades.map(o => {
    const ev = o.evidencia || {};
    const hechos = [];
    if (ev.dias_sin_compra != null) hechos.push(`${ev.dias_sin_compra} días sin comprar`);
    if (ev.renovaciones_proximas) hechos.push(`${plural(ev.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en 45 días`);
    if (ev.coberturas_vencidas) hechos.push(`${plural(ev.coberturas_vencidas, "cobertura vencida", "coberturas vencidas")}`);
    if (ev.prob_compra_30d != null) hechos.push(`estimación ${pct(ev.prob_compra_30d)}`);
    return `<tr><td><a href="#/clientes/${encodeURIComponent(o.cliente_id)}">${esc(o.cliente_id)}</a></td><td>${esc(o.accion || o.tipo)}${o.motivos.length > 1 ? `<div class="muted">También: ${esc(o.motivos.filter(m => m !== o.accion).join(", "))}</div>` : ""}</td>
      <td>${esc(hechos.join(" · ") || "—")}</td><td>${o.fecha_sugerida ? esc(fechaLarga(o.fecha_sugerida)) : "Sin fecha sugerida"}</td></tr>`;
  }).join("");
  return `${respuesta(`<strong>${num(t.total_clientes)} clientes en ${num(t.segmentos.length)} segmentos.</strong> ${t.segmentos[0] ? `El más numeroso es «${esc(t.segmentos[0].segmento)}», con ${plural(t.segmentos[0].clientes, "cliente", "clientes")}.` : ""}`, esc(incluye(t.cierre.corte)))}
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>Clientes por segmento</h2>
      ${barras(t.segmentos.map(x => ({ etiqueta: x.segmento, valor: x.clientes, texto: plural(x.clientes, "cliente", "clientes"), href: `#/tableros/ventas${x.segmento === sel ? "" : `?segmento=${encodeURIComponent(x.segmento)}`}`, activo: x.segmento === sel })),
        { etiquetaAria: "Clientes por segmento; pulsa uno para ver su explicación" })}
      <p class="muted">Total: ${plural(t.total_clientes, "cliente", "clientes")}. Cada cliente pertenece a un segmento.</p>
      ${s ? `<div class="estado"><strong>${esc(s.segmento)}.</strong> ${esc(s.descripcion || "Sin descripción publicada.")} ${puede("cartera.ver") ? `<a href="#/agenda?segmento=${encodeURIComponent(s.segmento)}">Ver estos ${plural(s.clientes, "cliente", "clientes")} en la agenda</a>` : ""}</div>` : '<p class="muted">Pulsa un segmento para ver qué significa y abrir sus clientes.</p>'}
      ${verDatos({ tabla: { cabeceras: ["Segmento", "Clientes", "Descripción"], numericas: new Set([1]), filas: t.segmentos.map(x => [esc(x.segmento), num(x.clientes), esc(x.descripcion || "—")]) }, fuente: `Tabla «segmentos» del cierre ${esc(t.cierre.id)}`, actualizado: esc(incluye(t.cierre.corte)) })}
    </section>
    <section class="panel"><h2>Etiquetas que pueden coexistir</h2>
      <dl class="cifras"><div><dt>Frecuentes</dt><dd>${num(e.frecuentes)}</dd></div><div><dt>Con 90 días o más sin comprar</dt><dd>${num(e.frios)}</dd></div><div><dt>Ambas cosas a la vez</dt><dd>${num(e.ambas ?? 0)}</dd></div></dl>
      <p class="muted">Un cliente que compraba con frecuencia puede llevar 90 días o más sin comprar; por eso puede ser frecuente y necesitar reactivación. Los recuentos no se suman.</p></section>
  </div>
  <section class="panel"><h2>Hasta ${num(t.limite_oportunidades ?? 20)} oportunidades prioritarias</h2>
    <p class="muted">${t.total_oportunidades > t.oportunidades.length ? `Se muestran ${t.oportunidades.length} de ${t.total_oportunidades} oportunidades del cierre.` : `Se muestran las ${t.oportunidades.length} oportunidades del cierre.`} Orden: prioridad de la acción y estimación de compra.</p>
    <div class="tabla"><table><tr><th>Cliente</th><th>Acción</th><th>Motivo comprobable</th><th>Fecha sugerida</th></tr>${filas || '<tr><td colspan=4 class="muted">Sin oportunidades publicadas.</td></tr>'}</table></div></section>`;
}

// ---------------------------------------------------------------- Operaciones (entrada 5)
function tableroOperaciones(t, q) {
  const corte = t.cierre.corte;
  const sel = q.get("intervalo") || "";
  const intervalos = t.intervalos || [];
  const it = intervalos.find(x => x.clave === sel);
  const enIntervalo = x => !it || (it.desde == null ? x.estado === "vencida" : x.dias_para_fin >= it.desde && x.dias_para_fin <= it.hasta);
  const fila = x => `<tr><td><a href="#/clientes/${encodeURIComponent(x.cliente_id)}">${esc(x.cliente_id)}</a></td><td>${esc(x.producto || x.producto_id)}</td><td>${esc(fechaLarga(x.fecha_fin))}</td><td><strong>${esc(relativoVencimiento(x.dias_para_fin))}</strong></td></tr>`;
  const prox = t.coberturas_proximas.filter(enIntervalo), venc = t.coberturas_vencidas.filter(enIntervalo);
  const total = intervalos.reduce((s, x) => s + x.coberturas, 0);
  const primera = t.coberturas_proximas[0];
  const estados = Object.entries(t.tareas_por_estado || {});
  return `${respuesta(`<strong>${plural(t.coberturas_vencidas.length, "cobertura vencida", "coberturas vencidas")} y ${plural(t.coberturas_proximas.length, "cobertura vence", "coberturas vencen")} en los próximos 45 días.</strong>${primera ? ` La más próxima es la de ${esc(primera.cliente_id)}: ${esc(relativoVencimiento(primera.dias_para_fin))}.` : ""}`,
    `${esc(incluye(corte))} · los días se cuentan desde esa fecha · se cuentan coberturas, aunque un cliente tenga varias`)}
  ${!t.detalle_disponible ? estadoHtml("", `El cierre no publica el detalle de coberturas; solo hay totales por cliente (${num(t.resumen_coberturas.renovaciones_proximas)} próximas y ${num(t.resumen_coberturas.coberturas_vencidas)} vencidas). No se pueden listar ni agrupar por días.`) : `
  <div class="grid2 ancho-desigual">
    <section class="panel"><h2>Coberturas por días hasta su vencimiento</h2>
      ${barras(intervalos.map(x => ({ etiqueta: x.etiqueta, valor: x.coberturas, texto: plural(x.coberturas, "cobertura", "coberturas"), href: `#/tableros/operaciones${x.clave === sel ? "" : `?intervalo=${x.clave}`}`, activo: x.clave === sel })), { etiquetaAria: "Coberturas por intervalo de días; pulsa uno para listar esas coberturas" })}
      <p class="muted">Total en estos intervalos: ${plural(total, "cobertura", "coberturas")}. ${it ? `<a href="#/tableros/operaciones">Ver todas</a>` : "Pulsa una barra para abrir su listado."}</p>
      ${verDatos({ tabla: { cabeceras: ["Intervalo", "Coberturas"], numericas: new Set([1]), filas: intervalos.map(x => [esc(x.etiqueta), num(x.coberturas)]) }, fuente: `Tabla «coberturas» del cierre ${esc(t.cierre.id)} (instalaciones publicadas)`, actualizado: esc(incluye(corte)), regla: "Días hasta el fin de cobertura contados desde la fecha del cierre; «vencida» si la fecha de fin es anterior." })}
    </section>
    <section class="panel"><h2>Seguimientos · estado actual</h2>
      <p class="muted">A diferencia de las coberturas, este bloque refleja el estado de las tareas ahora (${esc(fechaHora(t.tareas_consultadas_en))}), no al cierre.</p>
      ${estados.length ? `<dl class="cifras">${estados.map(([k, v]) => `<div><dt>${esc(ESTADOS_TAREA[k] || k)}</dt><dd>${num(v)}</dd></div>`).join("")}</dl>` : '<p class="muted">No hay seguimientos registrados.</p>'}
      ${puede("tareas.ver") ? '<p><a href="#/tareas">Abrir seguimientos</a></p>' : ""}</section>
  </div>
  <div class="grid2">
    <section class="panel"><h2>Vencen pronto${it && it.desde != null ? ` · ${esc(it.etiqueta.toLowerCase())}` : ""}</h2><p class="muted">Ordenadas por fecha de vencimiento.</p>
      <div class="tabla"><table><tr><th>Cliente</th><th>Producto</th><th>Fin</th><th>Situación al cierre</th></tr>${prox.map(fila).join("") || '<tr><td colspan=4 class="muted">Ninguna en esta selección.</td></tr>'}</table></div></section>
    <section class="panel"><h2>Vencidas</h2><p class="muted">Ordenadas de la más antigua a la más reciente.</p>
      <div class="tabla"><table><tr><th>Cliente</th><th>Producto</th><th>Fin</th><th>Situación al cierre</th></tr>${venc.map(fila).join("") || '<tr><td colspan=4 class="muted">Ninguna en esta selección.</td></tr>'}</table></div></section>
  </div>`}
  <p class="muted">${esc(t.nota)}</p>`;
}

// ---------------------------------------------------------------- Gerencia (entrada 6)
function tableroGerencia(t) {
  const i = t.indicadores, c = t.comparacion, corte = t.cierre.corte;
  let frase, donde = "", marcas = [];
  if (c && c.estado === "ok") {
    marcas = [c.mes_anterior, c.mes];
    const baja = c.diferencia < 0;
    frase = `<strong>En ${esc(mesLargo(c.mes))} se confirmaron ventas por ${esc(millones(c.valor))}.</strong> En ${esc(mesLargo(c.mes_anterior))} fueron ${esc(millones(c.valor_anterior, { unidad: false }))}. La ${baja ? "disminución" : "subida"} fue de ${esc(millones(Math.abs(c.diferencia), { unidad: false }))}. El ingreso acumulado de la cartera hasta el ${esc(fechaLarga(corte))} fue de ${esc(millones(i.ingreso_cop))}.`;
    const fams = c.familias.filter(f => f.familia !== "Total" && f.diferencia != null);
    const top = fams[0];
    const enlace = puede("finanzas.ver") ? ` <a href="#/finanzas?serie=ventas&desde=${esc(c.mes_anterior)}&hasta=${esc(c.mes)}">Ver ventas por familia</a> abre la comparación de esos dos meses.` : "";
    if (top) donde = `<p class="donde"><strong>Dónde mirar.</strong> Las ventas de la familia ${esc(top.familia)} ${top.diferencia < 0 ? "disminuyeron" : "aumentaron"} ${esc(millones(Math.abs(top.diferencia)))} en ${esc(mesLargo(c.mes))}.${enlace}</p>
      <p class="muted">La diferencia por familia explica aritméticamente la variación; la causa comercial requiere evidencia adicional.</p>`;
  } else {
    frase = `<strong>No hay dos meses completos para comparar.</strong> El ingreso acumulado de la cartera hasta el ${esc(fechaLarga(corte))} fue de ${esc(millones(i.ingreso_cop))}.`;
  }
  const incompletos = c?.meses_incompletos?.length ? estadoHtml("", `Faltan datos de ${c.meses_incompletos.map(mesLargo).join(", ")}: mes incompleto, no se compara.`) : "";
  const fams = (c?.familias || []).filter(f => f.familia !== "Total");
  return `${respuesta(frase, `${esc(incluye(corte))} · ventas confirmadas en pesos colombianos (COP) · toda la cartera`)}
  ${donde}${incompletos}
  <div class="grid2">
    <section class="panel"><h2>Ventas confirmadas por mes</h2>
      ${graficoLinea(t.evolucion.map(s => ({ periodo: s.periodo, valor: s.valor_cop })), [], { marcas, titulo: "Ventas confirmadas por mes, en COP (histórico)" })}
      ${c?.estado === "ok" ? `<p class="muted">Puntos rotulados: ${esc(mesLargo(c.mes_anterior))} y ${esc(mesLargo(c.mes))}, el par comparado.</p>` : ""}
      ${fams.length ? verDatos({ titulo: "Ver diferencia por familia", tabla: { cabeceras: ["Familia", mesLargo(c.mes_anterior), mesLargo(c.mes), "Diferencia"], numericas: new Set([1, 2, 3]), filas: fams.map(f => [esc(f.familia), cop(f.valor_anterior), cop(f.valor), esc(conSigno(f.diferencia))]) } }) : ""}
    </section>
    <section class="panel"><h2>Ingreso acumulado por segmento</h2>
      ${barras(t.segmentos.map(s => ({ etiqueta: s.segmento, valor: s.ingreso_cop, texto: millones(s.ingreso_cop), nota: plural(s.clientes, "cliente", "clientes") })), { etiquetaAria: "Ingreso acumulado por segmento" })}
      <p class="muted">Total: ${esc(millones(i.ingreso_cop))} de ${plural(i.clientes, "cliente", "clientes")}; ${num(i.clientes_frios)} con 90 días o más sin comprar.</p></section>
  </div>
  ${verDatos({ tabla: { cabeceras: ["Mes", "Ventas confirmadas (COP)"], numericas: new Set([1]), filas: t.evolucion.map(s => [esc(mesLargo(s.periodo)), s.valor_cop == null ? "Sin dato (mes incompleto)" : cop(s.valor_cop)]) },
    fuente: `${fuenteCierre(t.fuente)} · tablas ${esc((t.fuente?.tablas || []).join(" y "))}`, actualizado: esc(incluye(corte)),
    regla: `Último mes completo frente al anterior. Ingreso acumulado: ${esc(cop(i.ingreso_cop))}, ${num(i.ventas_confirmadas)} ventas confirmadas. Finanzas puede verificar la cifra con la serie publicada.` })}`;
}
