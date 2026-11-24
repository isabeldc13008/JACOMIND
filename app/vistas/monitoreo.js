// V26 Modelos y monitoreo · avisos y seguimiento (M1–M6): estado de cada modelo, avisos persistentes y su detalle.
// Solo lee lo persistido; nunca muestra «sin problemas» sin observaciones suficientes. Reconocer no resuelve ni reentrena.
import { $vista, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, nuevoTurno, num, pct, puede, ruta, vigente } from "../nucleo.js";
import { detalleTecnico, encabezado, filtrosActivos, hallazgo, tablaHtml, vacio } from "../ui.js";
import { CAPACIDAD, matrizModelos, pestanasModelos } from "./ia.js";

const GRUPO = { salud: "Salud de datos y publicación", distribucion: "Distribución de resultados", desempeno: "Desempeño con resultados observados", revision: "Revisión humana" };
const MADUREZ = { no_aplica: "No aplica", pendiente: "Aún sin resultados para comparar", parcial: "Resultados parciales", madura: "Resultados completos" };
const SEVERIDAD = { integridad: "Integridad de datos", estadistico: "Cambio estadístico", informativo: "Informativo" };
const TIPO = { publicacion_rechazada: "Publicación rechazada", caida_cobertura: "Caída de cobertura", sin_registros: "Periodo sin registros",
  cambio_tasa_alertas: "Cambio en la cantidad de señales", cambio_politica: "Cambio de política o versión", deterioro_frente_referencia: "Empeora frente a la referencia" };
const ESTADO_AVISO = { activo: "Activo", reconocido: "Reconocido (en revisión)", resuelto: "Resuelto" };
const SELLO = { sin_informacion: "sello-practica", pendiente_madurez: "sello-practica", no_comparable: "sello-prueba", sin_problemas: "sello-ok", requiere_revision: "sello-alerta", publicacion_rechazada: "sello-alerta" };
const TITULO = "Modelos y monitoreo";

function valor(m) {
  if (!m) return "—";
  if (m.valor == null) return `<span class="muted">no estimable${m.motivo ? `: ${esc(m.motivo)}` : ""}</span>`;
  const v = Math.abs(m.valor) <= 1 && m.unidad == null && m.denominador != null ? pct(m.valor) : num(Math.round(m.valor * 10000) / 10000);
  const soporte = m.denominador != null ? ` <span class="muted">(${num(m.numerador)} de ${num(m.denominador)})</span>` : m.soporte != null ? ` <span class="muted">(${num(m.soporte)} casos)</span>` : "";
  const ref = m.referencia ? `<span class="muted">referencia ${esc(m.referencia.id || "")}: ${m.referencia.valor == null ? "no estimable" : num(Math.round(m.referencia.valor * 10000) / 10000)}</span>` : "";
  return `${esc(v)}${m.unidad && m.unidad !== "probabilidad" ? ` <span class="muted">${esc(m.unidad)}</span>` : ""}${soporte}${ref}`;
}

function tablaObs(obs, titulo) {
  if (!obs.length) return `<p class="muted">${esc(titulo)}: sin observaciones.</p>`;
  return `<h3>${esc(titulo)}</h3>${tablaHtml({ cabeceras: ["Fecha de los datos", "Grupo", "Resultados", "Medidas", "Conteos"],
    filas: obs.map(o => [`${esc(fechaLarga(o.corte))}${o.vigente ? "" : ' <span class="chip">histórica, no vigente</span>'}${o.anterior_id ? ' <span class="chip">corrige otra</span>' : ""}`,
      esc(o.universo), `${esc(MADUREZ[o.madurez] || o.madurez)}${(o.datos.motivos || []).length ? `<span class="muted">${esc(o.datos.motivos.join(" · "))}</span>` : ""}`,
      Object.entries(o.datos.metricas).map(([k, m]) => `<div><strong>${esc(k.replace(/_/g, " "))}</strong>: ${valor(m)}</div>`).join("") || '<span class="muted">Sin medidas todavía</span>',
      `<span class="muted">${esc(Object.entries(o.datos.conteos).filter(([, v]) => typeof v !== "object").map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", "))}</span>`]) })}`;
}

function avisoFila(a) {
  return [`<span class="sello ${a.severidad === "informativo" ? "sello-practica" : "sello-alerta"}">${esc(SEVERIDAD[a.severidad] || a.severidad)}</span>`,
    `<strong>${esc(TIPO[a.tipo] || a.tipo.replace(/_/g, " "))}</strong><span class="muted">${esc([a.universo, a.periodo].filter(Boolean).join(" · "))}</span>`, esc(a.mensaje),
    `${esc(ESTADO_AVISO[a.estado] || a.estado)}<span class="muted">desde el ${esc(fechaHora(a.creado_en))}</span>`, `<a class="boton-sec" href="#/monitoreo?aviso=${encodeURIComponent(a.clave)}">Ver aviso</a>`];
}

function modeloHtml(m) {
  return `<details class="panel" id="mon-${esc(m.modelo_id)}"><summary>${esc(m.nombre)} · <span class="sello ${SELLO[m.estado] || "sello-practica"}">${esc(m.estado_texto)}</span>${m.avisos_activos.length ? ` · ${num(m.avisos_activos.length)} ${m.avisos_activos.length === 1 ? "aviso" : "avisos"}` : ""}</summary>
    <p>${esc(CAPACIDAD[m.modelo_id] || "")}</p>
    <p class="muted">Última publicación: ${esc(m.ultima_publicacion || "—")} · datos hasta ${esc(m.ultimo_corte ? fechaLarga(m.ultimo_corte) : "—")} · ${num(m.observaciones)} observaciones (${num(m.historicas_no_vigentes)} históricas no vigentes, ${num(m.corregidas)} corregidas).</p>
    ${m.avisos_activos.length ? tablaHtml({ cabeceras: ["Tipo", "Aviso", "Qué significa", "Estado", ""], filas: m.avisos_activos.map(avisoFila) }) : '<p class="muted">Sin avisos activos.</p>'}
    ${tablaObs(m.salud, GRUPO.salud)}${tablaObs(m.distribucion, GRUPO.distribucion)}${tablaObs(m.desempeno, GRUPO.desempeno)}
    ${m.revision.length ? tablaObs(m.revision, GRUPO.revision) : ""}</details>`;
}

async function avisoHtml(claveAviso, puedeReconocer, q) {
  const n = new URLSearchParams(q); n.delete("aviso"); n.delete("guardado");
  const volver = { href: `#/monitoreo${n.toString() ? `?${n}` : ""}`, texto: "Volver a los avisos" };
  let d;
  try { d = await api("GET", `/api/monitoreo/aviso?clave=${encodeURIComponent(claveAviso)}`); }
  catch (e) { return `${encabezado({ titulo: "Aviso", volver })}${errorHtml(e, { reintentar: e.status !== 404 })}`; }
  const a = d.aviso;
  return `${encabezado({ titulo: `Aviso: ${TIPO[a.tipo] || a.tipo.replace(/_/g, " ")}`, volver,
    descripcion: `Modelo ${esc(a.modelo_id)}${a.universo ? ` · ${esc(a.universo)}` : ""}${a.periodo ? ` · ${esc(a.periodo)}` : ""}`,
    contexto: [{ etiqueta: "Estado", valor: esc(ESTADO_AVISO[a.estado] || a.estado) }, { etiqueta: "Tipo", valor: esc(SEVERIDAD[a.severidad] || a.severidad) }, { etiqueta: "Desde", valor: esc(fechaHora(a.creado_en)) }] })}
  <div id="msg-mon" role="status" tabindex="-1">${q.get("guardado") ? '<div class="estado ok"><strong>Cambio guardado.</strong> Aparece en el historial del aviso.</div>' : ""}</div>
  ${hallazgo({ que: esc(a.mensaje), porque: `Regla «${esc(a.regla_id || a.tipo)}» (${esc(a.regla_version || "")}): ${esc(d.regla.definicion || "—")}`, accion: "" })}
  <div class="grid2">
    <section class="panel"><h2>Historial del aviso</h2><ol class="historial">${d.historial.map(e => `<li><strong>${esc(e.accion)}</strong> · ${esc(fechaHora(e.fecha))} · ${esc(e.actor)}${e.motivo ? `<div>${esc(e.motivo)}</div>` : ""}</li>`).join("")}</ol>
      ${detalleTecnico(`<pre>${esc(JSON.stringify({ evidencia: a.datos, observacion: d.observacion && d.observacion.datos }, null, 2))}</pre>`, "Evidencia (datos originales)")}</section>
    <section class="panel"><h2>Registrar la revisión</h2>
      ${puedeReconocer && a.estado !== "resuelto" ? `<form id="f-aviso" class="campos" novalidate>
        <fieldset><legend>¿Qué quieres registrar?</legend>
          <label class="en-linea"><input type="radio" name="accion" value="reconocido" checked> <span><strong>Reconocer</strong><span class="ayuda" style="display:block">Lo estás revisando. El aviso sigue abierto.</span></span></label>
          <label class="en-linea"><input type="radio" name="accion" value="resuelto"> <span><strong>Resolver</strong><span class="ayuda" style="display:block">Ya se revisó y se explicó la causa.</span></span></label></fieldset>
        <label for="motivo-aviso">Motivo <span class="ayuda">Obligatorio. Qué revisaste.</span><textarea id="motivo-aviso" name="motivo" required minlength="3" maxlength="400" aria-describedby="err-motivo-aviso"></textarea><span class="error-campo" id="err-motivo-aviso"></span></label>
        <div class="fila"><button>Guardar</button></div></form>
        <p class="muted">Reconocer o resolver no borra el aviso ni su historia, y ninguna acción promueve, revierte ni reentrena un modelo.</p>`
        : a.estado === "resuelto" ? '<p class="estado">Este aviso ya está resuelto. Su historia se conserva.</p>' : '<p class="estado">Tu perfil puede consultar el aviso, pero no reconocerlo ni resolverlo.</p>'}</section>
  </div>`;
}

export async function vistaMonitoreo() {
  const { q } = ruta();
  const turno = nuevoTurno();
  if (!$vista.querySelector("#f-mon, #f-aviso")) $vista.innerHTML = `${encabezado({ titulo: TITULO })}${pestanasModelos("monitoreo")}${estadoHtml("", "Cargando el monitoreo…")}`;
  const params = new URLSearchParams();
  for (const k of ["modelo", "variante", "periodo", "estado", "severidad", "tipo"]) if (q.get(k)) params.set(k, q.get(k));
  let d;
  try { d = await api("GET", `/api/monitoreo?${params}`); }
  catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo: TITULO })}${pestanasModelos("monitoreo")}${errorHtml(e, { reintentar: e.status !== 403 })}`; return; }
  if (!vigente(turno)) return;
  if (q.get("aviso")) {
    const html = await avisoHtml(q.get("aviso"), d.puede_reconocer, q);
    if (!vigente(turno)) return;
    $vista.innerHTML = html;
    enlazarAviso(q);
    return;
  }
  const sel = (n, etiqueta, ops) => `<label>${etiqueta} <select name="${n}"><option value="">Todos</option>${ops.map(([k, v]) => `<option value="${esc(k)}"${q.get(n) === k ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>`;
  const enlace = cambio => { const n = new URLSearchParams(q); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/monitoreo${n.toString() ? `?${n}` : ""}`; };
  const activos = ["modelo", "estado", "severidad", "tipo", "periodo", "variante"].filter(k => q.get(k)).map(k => ({ texto: `${{ modelo: "Modelo", estado: "Estado", severidad: "Tipo de aviso", tipo: "Aviso", periodo: "Periodo", variante: "Versión" }[k]}: ${k === "estado" ? d.estados[q.get(k)] || q.get(k) : k === "severidad" ? SEVERIDAD[q.get(k)] || q.get(k) : q.get(k)}`, quitar: enlace({ [k]: "" }) }));
  const avisos = d.modelos.flatMap(m => m.avisos_activos.map(a => ({ ...a, modelo: m.nombre })));
  const csv = `/api/monitoreo/exportar.csv${q.get("modelo") ? `?modelo=${encodeURIComponent(q.get("modelo"))}` : ""}`;
  $vista.innerHTML = `${encabezado({ titulo: TITULO, descripcion: "Seguimiento de cada modelo: si su publicación está sana, si sus resultados cambian y si hay avisos que revisar.",
    contexto: [{ etiqueta: "Reglas", valor: `${esc(d.reglas.version)} (iniciales, no aprobadas por la empresa)` }] })}
  ${pestanasModelos("monitoreo")}
  ${hallazgo({
    que: avisos.length ? `<strong>${num(avisos.length)} ${avisos.length === 1 ? "aviso activo" : "avisos activos"}</strong> en ${num(new Set(avisos.map(a => a.modelo)).size)} de ${num(d.modelos.length)} modelos.` : `Sin avisos activos en los ${num(d.modelos.length)} modelos visibles.`,
    porque: `${esc(d.nota)} «Sin problemas detectados» exige resultados observados suficientes; si faltan, el estado es «Pendiente de madurez».`,
    accion: avisos[0] ? `<a class="boton" href="#/monitoreo?aviso=${encodeURIComponent(avisos[0].clave)}">Ver el primer aviso</a>` : "",
  })}
  <section class="panel"><h2>Estado de cada modelo</h2>${matrizModelos(null, d)}</section>
  <section class="panel"><h2>Avisos activos</h2>
    ${avisos.length ? tablaHtml({ cabeceras: ["Modelo", "Tipo", "Aviso", "Qué significa", "Estado", ""], filas: avisos.map(a => [esc(a.modelo), ...avisoFila(a)]) }) : vacio("No hay avisos activos con estos filtros.")}</section>
  <section class="panel"><h2>Filtrar</h2><form class="filtros" id="f-mon">${sel("modelo", "Modelo", d.modelos.map(m => [m.modelo_id, m.nombre]))}${sel("estado", "Estado", Object.entries(d.estados))}
      ${sel("severidad", "Tipo de aviso", Object.entries(SEVERIDAD))}<label>Periodo (AAAA-MM) <input name="periodo" value="${esc(q.get("periodo") || "")}" inputmode="numeric" pattern="\\d{4}-\\d{2}"></label>
      <label>Versión <input name="variante" value="${esc(q.get("variante") || "")}"></label><button>Aplicar filtros</button></form>
    ${filtrosActivos(activos, "#/monitoreo")}
    <p><a class="boton-sec" href="${esc(csv)}" download>Descargar observaciones (CSV)</a> <span class="muted">${q.get("modelo") ? "Solo el modelo filtrado." : "Todos los modelos visibles para tu perfil."}</span></p></section>
  <h2>Detalle por modelo</h2>
  ${d.modelos.length ? d.modelos.map(modeloHtml).join("") : vacio("No hay modelos con ese filtro.")}`;
  document.getElementById("f-mon").addEventListener("submit", e => {
    e.preventDefault();
    const p = new URLSearchParams();
    for (const [k, v] of new FormData(e.target)) if (v) p.set(k, v);
    ir(`#/monitoreo${p.toString() ? `?${p}` : ""}`);
  });
}

function enlazarAviso(q) {
  const fa = document.getElementById("f-aviso");
  if (!fa) return;
  fa.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(fa), m = document.getElementById("motivo-aviso");
    const corto = (fd.get("motivo") || "").trim().length < 3;
    m.setAttribute("aria-invalid", String(corto)); document.getElementById("err-motivo-aviso").textContent = corto ? "Escribe el motivo (al menos 3 letras)." : "";
    if (corto) return m.focus();
    const b = fa.querySelector("button"); b.disabled = true; b.textContent = "Guardando…";
    try {
      await api("POST", "/api/monitoreo/aviso", { clave: q.get("aviso"), accion: fd.get("accion"), motivo: fd.get("motivo").trim(), __clave: fa.dataset.clave ||= clave() });
      const n = new URLSearchParams(q); n.set("guardado", "1"); ir(`#/monitoreo?${n}`);
    } catch (err) { const msg = document.getElementById("msg-mon"); msg.innerHTML = errorHtml(err); msg.focus(); b.disabled = false; b.textContent = "Guardar"; }
  });
}
