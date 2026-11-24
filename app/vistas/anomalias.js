// Operaciones atípicas (M6): cola EXPERIMENTAL en sombra para revisión humana de ventas y compras. Muestra valor observado
// frente a referencia, motivos, soporte, método, cobertura, exceso sobre el cupo, historial y acciones de revisión.
// El puntaje es rareza: no es probabilidad de fraude ni porcentaje de error; la cola no modifica importes.
import { $vista, api, cop, errorHtml, esc, estadoHtml, fechaHora, ir, mesLargo, nuevoTurno, num, ruta, vigente } from "../nucleo.js";
import { detalleTecnico, respuesta } from "../ui.js";

const UNIVERSO = { venta: "Ventas confirmadas", compra: "Compras a proveedores" };
const ESTADO = { pendiente: "Pendiente", error_confirmado: "Error confirmado", cambio_legitimo: "Cambio legítimo",
  informacion_insuficiente: "Información insuficiente", sin_caso: "Sin caso" };
const DECISION = { favorable_demostracion_sombra: "Favorable para demostración en sombra", referencia_conservada: "Referencia conservada", inconcluso: "Inconcluso" };
const METODO = { isolation_forest: "Isolation Forest (IA)", mediana_mad: "Mediana/MAD contextual (referencia)" };
const EVENTO = { apertura: "Apertura", correccion_datos: "Corrección de datos", revision: "Revisión", evidencia_actualizada: "Nueva publicación" };
const valor = (x, moneda) => x == null ? "—" : moneda === "COP" ? cop(x) : `${num(Math.round(x * 100) / 100)} ${esc(moneda)}`;
const raz = x => x == null ? "" : ` <span class="muted">(×${num(Math.round(x * 100) / 100)})</span>`;
const titulo = `<h1>Operaciones atípicas <span class="chip">IA · experimental</span></h1>`;

const pp = x => `${x >= 0 ? "+" : "−"}${num(Math.round(Math.abs(x) * 1000) / 10)} pp`;
function motivoDecision(dc) {
  const c = dc.cumple || {}, v = dc.valores || {};
  if (!dc.valores) return dc.motivos?.length ? ` · ${esc(dc.motivos.join(" "))}` : "";
  const por = [];
  if (!c.supera_referencia_ic && v.diferencia != null) por.push(`la mejora de la IA en casos sembrados (${pp(v.diferencia)}, IC95 ${pp(v.ic95[0])} a ${pp(v.ic95[1])}) no es concluyente`);
  if (c.controles_negativos_no_peores === false) por.push(`la IA alertó en más controles negativos que la referencia (${num(Math.round(v.alertas_controles_candidato * 1000) / 10)} % frente a ${num(Math.round(v.alertas_controles_referencia * 1000) / 10)} %)`);
  if (c.meta_deteccion_candidato === false) por.push("la IA no alcanza la meta de detección del 80 %");
  if (c.trm_sin_cambio === false) por.push("un cambio solo de TRM alteró el puntaje");
  return por.length ? `, porque ${esc(por.join(" y "))}` : "";
}

function cabecera(d) {
  const u = d.universo, r = d.resumen;
  const pest = Object.entries(UNIVERSO).map(([k, v]) => `<a href="#/anomalias?universo=${k}"${k === u ? ' aria-current="page"' : ""}>${esc(v)}</a>`).join("");
  const dec = d.decision ? `${esc(DECISION[d.decision.decision] || d.decision.decision)}${motivoDecision(d.decision)}` : "Sin decisión registrada";
  return `${titulo}
  <nav class="pestanas" aria-label="Universo">${pest}</nav>
  ${respuesta(`<strong>${num(r.alertas)} alertas</strong> dentro de la capacidad de revisión (${num(r.capacidad_revision)}) y <strong>${num(r.exceso_sobre_cupo)}</strong> señaladas por reglas fuera del cupo, sobre ${num(r.validas)} ${u === "venta" ? "ventas" : "compras"} válidas (${esc(mesLargo(d.desde?.slice(0, 7)))} a ${esc(mesLargo(d.corte.slice(0, 7)))}).`,
    `Método publicado: ${esc(METODO[d.metodo] || d.metodo)} · candidato IA: ${esc(d.candidato === "isolation_forest" ? "Isolation Forest" : "en abstención")} · modelo ${esc(d.version)} · ${esc(d.emision?.tipo === "reconstruccion_historica" ? "reconstrucción histórica" : d.emision?.tipo || "")}.`)}
  <p class="muted">${esc(d.nota)}</p>
  <div class="aviso-cifras" role="status">Decisión experimental: ${dec}. Capacidad de demostración: ${esc(d.politica_alertas?.convencion || "")}</div>
  ${r.cobertura_temporal === "no_declarada" ? `<div class="aviso-cifras" role="status">Cobertura incompleta: ${esc(r.nota_cobertura || "compras sin cobertura temporal declarada")}</div>` : ""}
  <dl class="cifras">
    <div><dt>Puntuadas</dt><dd>${num(r.puntuadas)} de ${num(r.validas)}</dd></div>
    <div><dt>Sin historia suficiente</dt><dd>${num(r.abstenciones)}</dd></div>
    <div><dt>Excluidas del universo</dt><dd>${Object.entries(r.excluidas || {}).map(([k, v]) => `${num(v)} ${esc(k.replace(/_/g, " "))}`).join(", ") || "0"}</dd></div>
    <div><dt>Casos pendientes</dt><dd>${num(r.casos_pendientes)}</dd></div>
    <div><dt>Casos revisados</dt><dd>${num(r.casos_revisados)}</dd></div>
    <div><dt>Alertas por 100 válidas</dt><dd>${num(r.alertas_por_100_validas)}</dd></div>
  </dl>`;
}

function filtros(d) {
  const f = d.filtros, o = d.opciones;
  const sel = (n, etiqueta, ops, actual, txt = x => x) => `<label>${etiqueta} <select name="${n}"><option value="">Todos</option>${ops.map(x => `<option value="${esc(x)}"${x === actual ? " selected" : ""}>${esc(txt(x))}</option>`).join("")}</select></label>`;
  return `<form class="filtros" id="f-an"><input type="hidden" name="universo" value="${esc(d.universo)}">
    ${sel("periodo", "Periodo", o.periodos, f.periodo, mesLargo)}${sel("producto", "Producto", o.productos, f.producto)}${sel("moneda", "Moneda", o.monedas, f.moneda)}
    ${sel("estado", "Estado", Object.keys(ESTADO), f.estado, x => ESTADO[x])}
    <label>Vista <select name="vista">${[["cola", "Cola priorizada"], ["todas", "Todas las operaciones"], ["sin_historia", "Sin historia suficiente"]].map(([k, v]) => `<option value="${k}"${k === f.vista ? " selected" : ""}>${v}</option>`).join("")}</select></label>
    <button>Filtrar</button>${d.puede_exportar ? ` <a href="/api/anomalias/exportar.csv?universo=${esc(d.universo)}" download>Exportar CSV</a>` : ""}</form>`;
}

function fila(i) {
  const tipo = i.estado_puntuacion !== "puntuada" ? '<span class="chip">Sin historia suficiente</span>'
    : i.alerta ? `<span class="chip fuerte">Alerta · prioridad ${num(i.prioridad)} de cupo ${num(i.cupo_periodo)}</span>`
      : i.fuera_de_cupo ? '<span class="chip fuerte">Fuera de cupo (pendiente)</span>' : `<span class="chip">Prioridad ${num(i.prioridad)}</span>`;
  const contraparte = i.tipo_operacion === "venta" ? `Cliente ${esc(i.cliente_id)}` : `Proveedor ${esc(i.proveedor_id)}`;
  return `<tr><td><a href="#/anomalias?universo=${esc(i.tipo_operacion)}&caso=${encodeURIComponent(i.operacion_id)}">${esc(i.operacion_id)}</a><div class="muted">${esc(i.fecha)} · ${contraparte}</div></td>
    <td>${esc(i.producto_id)}<div class="muted">${esc(i.moneda)} · ${esc(i.unidad)}</div></td>
    <td class="n">${valor(i.valor_unitario, i.moneda)}<div class="muted">ref. ${valor(i.referencia_valor_unitario, i.moneda)}${raz(i.razon_valor_unitario)}</div></td>
    <td class="n">${num(i.cantidad)}<div class="muted">ref. ${num(i.referencia_cantidad == null ? null : Math.round(i.referencia_cantidad * 100) / 100)}${raz(i.razon_cantidad)}</div></td>
    <td>${tipo}<div class="muted">${i.puntaje == null ? "sin puntaje" : `puntaje ${num(Math.round(i.puntaje * 1000) / 1000)} · ${esc(METODO[i.metodo] || i.metodo)}`}</div></td>
    <td>${(i.motivos || []).map(m => `<div>${esc(m)}</div>`).join("")}<div class="muted">Soporte: ${num(i.soporte)} antecedentes${i.muestra ? ` · muestra de revisión (${esc(i.muestra.estrato.replace("_", " "))})` : ""}</div></td>
    <td><span class="chip${i.estado_revision === "pendiente" ? " fuerte" : ""}">${esc(ESTADO[i.estado_revision] || i.estado_revision)}</span></td></tr>`;
}

function metricas(m) {
  const p = m.precision_alertas_revisadas, f = m.falsas_alertas_por_100_normales_revisadas;
  return `<section class="panel"><h2>Resultados de revisión humana</h2>
    <p>${num(m.revisadas)} operaciones revisadas (${Object.entries(m.por_estado).map(([k, v]) => `${num(v)} ${esc(ESTADO[k].toLowerCase())}`).join(", ")}).</p>
    <p>Precisión entre alertas revisadas: ${p.valor == null ? "no estimable" : num(p.valor)} (${num(p.numerador)} / ${num(p.denominador)})${p.motivo ? ` <span class="muted">— ${esc(p.motivo)}</span>` : ""}</p>
    <p>Falsas alertas por 100 normales revisadas: ${f.por_100 == null ? "no estimable" : num(f.por_100)} (${num(f.numerador)} / ${num(f.denominador)})${f.motivo ? ` <span class="muted">— ${esc(f.motivo)}</span>` : ""}</p>
    <p class="muted">${esc(m.nota)}</p></section>`;
}

async function detalleCaso(tipo, id, d) {
  let c;
  try { c = await api("GET", `/api/anomalias/caso?tipo=${encodeURIComponent(tipo)}&id=${encodeURIComponent(id)}`); }
  catch (e) { return `<section class="panel" id="caso">${errorHtml(e)}</section>`; }
  const p = c.publicaciones[0], v = c.caso_vigente;
  const hist = c.eventos.map(e => `<li><strong>${esc(EVENTO[e.tipo] || e.tipo)}</strong> · ${esc(fechaHora(e.fecha))} · ${esc(e.actor)}${e.estado_nuevo ? ` · ${esc(ESTADO[e.estado_anterior] || e.estado_anterior || "—")} → ${esc(ESTADO[e.estado_nuevo] || e.estado_nuevo)}` : ""}
    ${e.version_examinada ? `<span class="muted"> · versión ${esc(e.version_examinada)}</span>` : ""}${e.motivo ? `<div>${esc(e.motivo)}</div>` : ""}${e.evidencia ? `<div class="muted">Evidencia: ${esc(e.evidencia)}</div>` : ""}</li>`).join("");
  const pubs = c.publicaciones.map(x => `<tr><td>${esc(x.corte)}${x.publicacion_activa ? ' <span class="chip">activa</span>' : ""}</td><td>${esc(x.version_modelo)}</td><td class="n">${x.puntaje == null ? "—" : num(Math.round(x.puntaje * 1000) / 1000)}</td><td>${x.alerta ? "Sí" : "No"}</td><td>${esc(x.estado_puntuacion)}</td></tr>`).join("");
  const form = c.puede_revisar ? `<form id="f-rev" class="filtros"><label>Decisión <select name="estado" required>
      <option value="error_confirmado">Error confirmado</option><option value="cambio_legitimo">Cambio legítimo</option><option value="informacion_insuficiente">Información insuficiente</option></select></label>
      <label>Motivo <input name="motivo" required minlength="3" maxlength="400"></label><label>Evidencia <input name="evidencia" maxlength="400"></label><button>Registrar revisión</button></form>
      <p class="muted">La revisión no cambia importes ni la operación: una corrección contable se hace en el flujo de datos (nueva carga A01) y crea una revisión nueva enlazada.</p>`
    : '<p class="muted">Tu perfil puede consultar, pero no registrar revisiones.</p>';
  return `<section class="panel" id="caso"><h2>${esc(UNIVERSO[tipo])} · ${esc(id)}</h2><div id="msg-an" role="status"></div>
    <dl class="cifras"><div><dt>Fecha</dt><dd>${esc(p.fecha)}</dd></div><div><dt>Producto</dt><dd>${esc(p.producto_id)}</dd></div>
      <div><dt>${tipo === "venta" ? "Cliente" : "Proveedor"}</dt><dd>${esc(tipo === "venta" ? p.cliente_id : p.proveedor_id)}</dd></div>
      <div><dt>Valor unitario</dt><dd>${valor(p.valor_unitario, p.moneda)}</dd></div><div><dt>Referencia</dt><dd>${valor(p.referencia_valor_unitario, p.moneda)}</dd></div>
      <div><dt>Cantidad / referencia</dt><dd>${num(p.cantidad)} / ${num(p.referencia_cantidad == null ? null : Math.round(p.referencia_cantidad * 100) / 100)}</dd></div>
      <div><dt>Importe COP</dt><dd>${p.importe_cop_oculto ? '<span class="muted">restringido a Finanzas</span>' : p.estado_trm === "ausente" ? "TRM ausente: no convertible" : cop(p.importe_cop)}</dd></div>
      <div><dt>Antecedentes</dt><dd>${num(p.soporte)}${p.antecedentes ? ` (${esc(p.antecedentes[0])} a ${esc(p.antecedentes[1])})` : ""}</dd></div>
      <div><dt>Estado de revisión</dt><dd>${esc(v ? ESTADO[v.estado] : "Sin caso")}</dd></div></dl>
    ${(p.motivos || []).map(m => `<p>${esc(m)}</p>`).join("")}
    ${form}
    <h3>Historial</h3>${hist ? `<ol class="historial">${hist}</ol>` : '<p class="muted">Sin eventos: la operación no tiene caso de revisión.</p>'}
    ${c.casos.length > 1 ? `<p class="muted">${num(c.casos.length)} revisiones del caso por correcciones de datos; las decisiones anteriores se conservan.</p>` : ""}
    <h3>Puntuaciones publicadas (inmutables)</h3><div class="tabla"><table><tr><th>Corte</th><th>Versión</th><th class="n">Puntaje</th><th>Alerta</th><th>Estado</th></tr>${pubs}</table></div>
    ${detalleTecnico(`<pre>${esc(JSON.stringify(p.variables, null, 2))}</pre><p class="muted">Variables contextuales en moneda de origen (desviaciones robustas en logaritmos). La TRM y el importe COP no entran al detector.</p>`, "Variables")}
  </section>`;
}

export async function vistaAnomalias() {
  const { q } = ruta();
  const turno = nuevoTurno();
  $vista.innerHTML = estadoHtml("", "Cargando la cola de operaciones atípicas…");
  const params = new URLSearchParams();
  for (const k of ["universo", "periodo", "producto", "moneda", "estado", "vista"]) if (q.get(k)) params.set(k, q.get(k));
  let d;
  try { d = await api("GET", `/api/anomalias?${params}`); }
  catch (e) { if (vigente(turno)) $vista.innerHTML = `${titulo}${e.status === 403 ? estadoHtml("error", "Tu perfil no tiene acceso a la cola de operaciones atípicas.") : errorHtml(e)}`; return; }
  if (!vigente(turno)) return;
  if (d.estado === "sin_sombra") {
    $vista.innerHTML = `${titulo}${estadoHtml("", d.mensaje)}<p class="muted">${esc(d.nota)}</p>`;
    return;
  }
  const caso = q.get("caso") ? await detalleCaso(d.universo, q.get("caso"), d) : "";
  if (!vigente(turno)) return;
  const filas = d.items.map(fila).join("");
  $vista.innerHTML = `${cabecera(d)}${filtros(d)}${caso}
  <div class="tabla"><table><caption class="muted">Cola priorizada por mes (prioridad 1 = más rara). Se muestran las alertas, las señaladas fuera del cupo, la muestra de revisión y los casos abiertos.</caption>
    <tr><th>Operación</th><th>Producto</th><th class="n">Valor unitario</th><th class="n">Cantidad</th><th>Prioridad y método</th><th>Motivos y soporte</th><th>Revisión</th></tr>
    ${filas || '<tr><td colspan="7" class="muted">No hay operaciones con estos filtros.</td></tr>'}</table></div>
  ${metricas(d.metricas_revision)}
  <section class="panel"><h2>Cobertura por mes</h2><div class="tabla"><table><tr><th>Mes</th><th class="n">Válidas</th><th class="n">Puntuadas</th><th class="n">Sin historia</th><th class="n">Alertas / cupo</th><th class="n">Fuera de cupo</th><th>Cobertura temporal</th></tr>
    ${d.cobertura.map(c => `<tr><td>${esc(mesLargo(c.periodo))}</td><td class="n">${num(c.validas)}</td><td class="n">${num(c.puntuadas)}</td><td class="n">${num(c.abstenciones.historia_insuficiente)}</td><td class="n">${num(c.alertas)} / ${num(c.cupo)}</td><td class="n">${num(c.exceso_sobre_cupo)}</td><td>${c.cobertura_temporal === "declarada" ? "Declarada" : "No declarada"}</td></tr>`).join("")}</table></div>
    <p class="muted">Muestra de revisión: ${num(d.muestra.seleccionadas)} de ${num(d.muestra.objetivo)} previstas. ${esc(d.muestra.metodo || "")}</p></section>
  ${detalleTecnico(`<pre>${esc(JSON.stringify({ sombra: d.sombra_id, estado: d.estado_experimento, politica: d.politica_alertas, distribucion: d.resumen.distribucion_puntaje }, null, 2))}</pre>`, "Publicación")}`;
  document.getElementById("f-an").addEventListener("submit", e => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
    ir(`#/anomalias?${p}`);
  });
  const fr = document.getElementById("f-rev");
  if (fr) fr.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(fr);
    try {
      await api("POST", "/api/anomalias/revision", { tipo_operacion: d.universo, operacion_id: q.get("caso"), estado: fd.get("estado"), motivo: fd.get("motivo"), evidencia: fd.get("evidencia") || null });
      vistaAnomalias();
    } catch (err) { document.getElementById("msg-an").innerHTML = errorHtml(err); }
  });
}
