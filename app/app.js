// JACOMIND · interfaz web sin dependencias.
// Orígenes de datos (selección explícita y siempre visible):
//   servidor → API con sesión (cierre publicado); salida → /salida/agenda.json; ejemplo → /app/fixtures/agenda.json
import { ACCIONES, motivos, ordenar, validarAgenda } from "./contrato.js";

const $vista = document.getElementById("vista");
const fmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const fmtCop = new Intl.NumberFormat("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cop = x => x == null ? "—" : `${fmtCop.format(x)} COP`;
const pct = p => p == null ? null : `${(p * 100).toFixed(1).replace(".", ",")} %`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const FUENTES = { servidor: "Servidor (cierre publicado)", salida: "Salida local /salida/agenda.json", ejemplo: "Ejemplo de práctica (ficticio)" };
const URL_FUENTE = { salida: "/salida/agenda.json", ejemplo: "/app/fixtures/agenda.json" };

const S = { fuente: null, usuario: null, apiDisponible: false, estadoApi: null, local: null, cierre: "activo", seq: 0 };
try { S.fuente = localStorage.getItem("jacomind.fuente"); } catch { /* sin almacenamiento */ }

// ---------------------------------------------------------------- utilidades
async function api(metodo, ruta, cuerpo) {
  const r = await fetch(ruta, {
    method: metodo, credentials: "same-origin",
    headers: { "X-Jacomind": "1", ...(cuerpo ? { "Content-Type": "application/json" } : {}), ...(cuerpo && cuerpo.__clave ? { "Idempotency-Key": cuerpo.__clave } : {}) },
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  const tipo = r.headers.get("content-type") || "";
  const datos = tipo.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw Object.assign(new Error(datos.mensaje || `Error ${r.status}`), { status: r.status, datos });
  return datos;
}
const puede = a => !!S.usuario && S.usuario.acciones.includes(a);
const enServidor = () => S.fuente === "servidor";
function ruta() {
  const [camino, qs] = (location.hash.slice(1) || "/agenda").split("?");
  return { partes: camino.split("/").filter(Boolean).map(decodeURIComponent), q: new URLSearchParams(qs || "") };
}
function ir(hash) { if (location.hash !== hash) location.hash = hash; else render(); }
function estadoHtml(tipo, texto) { return `<div class="estado ${tipo}" role="${tipo === "error" ? "alert" : "status"}">${esc(texto)}</div>`; }
function errorHtml(e) {
  const det = e.datos?.detalle?.errores ? `<ul>${e.datos.detalle.errores.slice(0, 8).map(x => `<li><code>${esc(x)}</code></li>`).join("")}</ul>` : "";
  return `<div class="estado error" role="alert">${esc(e.message)}${det}</div>`;
}
const nuevoTurno = () => ++S.seq;           // evita que una respuesta antigua reemplace una nueva
const vigente = t => t === S.seq;
const clave = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));

// ---------------------------------------------------------------- cabecera
function pintarCabecera() {
  const { partes } = ruta();
  const items = [];
  const add = (h, t) => items.push(`<a href="#/${h}" ${partes[0] === h.split("/")[0] ? 'aria-current="page"' : ""}>${t}</a>`);
  if (!enServidor()) add("agenda", "Agenda");
  else if (S.usuario) {
    if (puede("cartera.ver")) add("agenda", "Agenda");
    if (puede("tablero.ventas") || puede("tablero.operaciones") || puede("tablero.gerencia")) add("tableros", "Tableros");
    if (puede("tareas.ver")) add("tareas", "Seguimientos");
    if (puede("pqrs.ver_propias") || puede("pqrs.gestionar") || puede("pqrs.indicadores")) add("pqrs", "PQRS");
    if (puede("beneficios.portal") || puede("beneficios.ver_interno")) add("beneficios", "Beneficios");
    if (puede("agente.datos") || puede("agente.portal")) add("asistente", "Asistente");
    if (puede("finanzas.ver") || puede("informes.ver")) add("finanzas", "Finanzas");
    if (puede("documentos.gestionar")) add("documentos", "Documentos");
    if (puede("operacion.administrar")) add("operacion", "Operación");
  }
  add("inicio", "Origen y sesión");
  document.getElementById("menu").innerHTML = items.join("");
  let origen = S.fuente ? `Origen: <strong>${esc(FUENTES[S.fuente])}</strong>` : "Origen: <strong>sin seleccionar</strong>";
  if (!enServidor() && S.local?.datos) origen += ` · corte ${esc(S.local.datos.corte)} · ${esc(S.local.datos.origen)} · cargado ${esc(S.local.cargado)}`;
  if (enServidor() && S.estadoApi?.cierre_activo) origen += ` · cierre ${esc(S.cierre === "activo" ? S.estadoApi.cierre_activo : S.cierre)}`;
  document.getElementById("origen").innerHTML = origen;
  document.getElementById("sesion").innerHTML = S.usuario
    ? `<span class="muted">${esc(S.usuario.nombre)} · ${esc(S.usuario.roles.join(", "))}</span> <button class="sec" id="salir">Salir</button>` : "";
  document.getElementById("salir")?.addEventListener("click", async () => {
    await api("DELETE", "/api/sesion").catch(() => {}); S.usuario = null; ir("#/inicio");
  });
}

// ---------------------------------------------------------------- inicio: origen y sesión (B01/B02)
async function vistaInicio() {
  let ids = [];
  if (S.apiDisponible && S.estadoApi?.login_demo) ids = await api("GET", "/api/identidades").catch(() => []);
  $vista.innerHTML = `<h1>Origen de datos y sesión</h1>
  <div class="panel"><h2>1 · Elige el origen</h2>
    <p class="muted">El modo de práctica se selecciona explícitamente. El origen elegido queda visible en la cabecera.</p>
    <div class="fila">${Object.entries(FUENTES).map(([k, t]) =>
      `<label class="fila" style="display:flex"><input type="radio" name="fuente" value="${k}" ${S.fuente === k ? "checked" : ""} ${k === "servidor" && !S.apiDisponible ? "disabled" : ""}> ${esc(t)}</label>`).join("")}</div>
    ${S.apiDisponible ? "" : '<p class="muted">Servidor no detectado: sirviendo archivos estáticos. Arranca <code>python -m api servir</code> para el modo multiusuario.</p>'}
  </div>
  <div class="panel ${S.apiDisponible ? "" : "oculto"}"><h2>2 · Inicia sesión (identidades ficticias de demostración)</h2>
    ${S.usuario ? `<p>Sesión activa: <strong>${esc(S.usuario.nombre)}</strong>.</p>` : ""}
    <div class="fila"><select id="ident">${ids.map(i => `<option value="${esc(i.id)}">${esc(i.nombre)} — ${esc(i.rol)} (${esc(i.organizacion)})</option>`).join("")}</select>
    <button id="entrar" ${ids.length ? "" : "disabled"}>Entrar</button></div><div id="msg"></div>
  </div>`;
  $vista.querySelectorAll("input[name=fuente]").forEach(r => r.addEventListener("change", e => {
    S.fuente = e.target.value; S.local = null;
    try { localStorage.setItem("jacomind.fuente", S.fuente); } catch { }
    pintarCabecera();
    if (!enServidor()) ir("#/agenda");
  }));
  document.getElementById("entrar")?.addEventListener("click", async () => {
    try {
      const r = await api("POST", "/api/sesion", { identidad: document.getElementById("ident").value });
      S.usuario = r.usuario; S.fuente = "servidor";
      try { localStorage.setItem("jacomind.fuente", "servidor"); } catch { }
      ir(S.usuario.externo ? "#/beneficios" : puede("cartera.ver") ? "#/agenda" : puede("finanzas.ver") ? "#/finanzas" : "#/pqrs");
    } catch (e) { document.getElementById("msg").innerHTML = errorHtml(e); }
  });
}

// ---------------------------------------------------------------- agenda local (B01)
async function cargarLocal() {
  const url = URL_FUENTE[S.fuente];
  const [rEsq, rDat] = await Promise.all([fetch("/contratos/agenda.v1.schema.json", { cache: "no-store" }), fetch(url, { cache: "no-store" })]);
  if (!rDat.ok) {
    const ayuda = S.fuente === "salida"
      ? "No existe salida/agenda.json. Genérala con: python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json"
      : "No se encontró el archivo de ejemplo.";
    throw Object.assign(new Error(ayuda), { datos: {} });
  }
  if (!rEsq.ok) throw new Error("No se pudo leer el esquema /contratos/agenda.v1.schema.json (sirve la raíz del clon).");
  let datos;
  try { datos = await rDat.json(); } catch { throw new Error(`${url} no contiene JSON válido`); }
  const res = validarAgenda(datos, await rEsq.json());
  if (res.errores.length) {
    throw Object.assign(new Error(res.incompatible ? "Versión de agenda incompatible: se conserva la vista anterior." : "La agenda no cumple el contrato C1."),
      { datos: { detalle: { errores: res.errores } } });
  }
  S.local = { datos, url, cargado: new Date().toLocaleTimeString("es-CO") };
}

function filtrosDesdeQuery(q) {
  return { accion: q.get("accion") || "", segmento: q.get("segmento") || "", q: q.get("q") || "", frio: q.get("frio") || "", pagina: Number(q.get("pagina") || 1) };
}
function queryDeFiltros(f) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(f)) if (v && !(k === "pagina" && v === 1)) p.set(k, v);
  return p.toString();
}

async function vistaAgenda() {
  if (!S.fuente) return ir("#/inicio");
  if (enServidor() && !S.usuario) return ir("#/inicio");
  const { q } = ruta();
  const f = filtrosDesdeQuery(q);
  const turno = nuevoTurno();
  $vista.innerHTML = `<h1>Agenda de seguimiento</h1>${estadoHtml("", "Cargando agenda…")}`;
  let datos;
  try {
    if (enServidor()) {
      const p = new URLSearchParams({ ...f, tam: 25 });
      const [res, ag] = await Promise.all([api("GET", `/api/cierres/${S.cierre}/resumen`), api("GET", `/api/cierres/${S.cierre}/agenda?${p}`)]);
      datos = { resumen: res.resumen, frecuentes: res.frecuentes, por_accion: res.por_accion, modelo: res.modelo, items: ag.items, total: ag.total,
        paginas: ag.paginas, pagina: ag.pagina, segmentos: ag.segmentos_disponibles, ingreso_filtrado: ag.ingreso_cop_filtrado, corte: ag.corte, cierres: await api("GET", "/api/cierres") };
    } else {
      if (!S.local) await cargarLocal();
      const a = S.local.datos, umbral = a.modelo?.umbral ?? null;
      let items = ordenar(a.clientes).map(c => ({ ...c, motivos: motivos(c, umbral), sin_historial: c.ultima_compra === null }));
      if (f.accion) items = items.filter(c => c.accion === f.accion);
      if (f.segmento) items = items.filter(c => c.segmento === f.segmento);
      if (f.q) items = items.filter(c => c.cliente_id.toUpperCase().includes(f.q.toUpperCase()));
      if (f.frio) items = items.filter(c => c.frio);
      const tam = 25, paginas = Math.max(1, Math.ceil(items.length / tam));
      datos = { resumen: a.resumen, frecuentes: a.clientes.filter(c => c.frecuente).length,
        por_accion: ACCIONES.map(x => ({ accion: x, clientes: a.clientes.filter(c => c.accion === x).length })), modelo: a.modelo,
        items: items.slice((f.pagina - 1) * tam, f.pagina * tam), total: items.length, paginas, pagina: f.pagina,
        segmentos: [...new Set(a.clientes.map(c => c.segmento).filter(Boolean))], ingreso_filtrado: items.reduce((s, c) => s + c.ingreso_cop, 0), corte: a.corte };
    }
  } catch (e) {
    if (!vigente(turno)) return;
    $vista.innerHTML = `<h1>Agenda de seguimiento</h1>${errorHtml(e)}<p><a href="#/inicio">Cambiar origen</a></p>`;
    pintarCabecera(); return;
  }
  if (!vigente(turno)) return;
  pintarCabecera();
  const r = datos.resumen;
  const revisar = datos.por_accion.filter(x => x.accion !== "Seguimiento habitual").reduce((s, x) => s + x.clientes, 0);
  $vista.innerHTML = `<h1>Agenda de seguimiento · corte ${esc(datos.corte)}</h1>
  ${enServidor() && datos.cierres?.length > 1 ? `<label>Cierre <select id="cierre">${datos.cierres.map(c => `<option value="${esc(c.id)}" ${(S.cierre === c.id || (S.cierre === "activo" && c.activo)) ? "selected" : ""}>${esc(c.corte)} · r${c.revision}${c.activo ? " (activo)" : ""}</option>`).join("")}</select></label>` : ""}
  <div class="tarjetas" aria-label="Indicadores de toda la cartera">
    <div class="tarjeta"><div class="e">Clientes (toda la cartera)</div><div class="v">${fmt.format(r.clientes)}</div></div>
    <div class="tarjeta"><div class="e">Ventas confirmadas acumuladas</div><div class="v">${fmt.format(r.ventas_confirmadas)}</div></div>
    <div class="tarjeta"><div class="e">Ingreso confirmado acumulado</div><div class="v" style="font-size:18px">${cop(r.ingreso_cop)}</div></div>
    <div class="tarjeta"><div class="e">Clientes fríos</div><div class="v">${fmt.format(r.clientes_frios)}</div><div class="e">Frecuentes: ${fmt.format(datos.frecuentes)} (pueden solaparse)</div></div>
    <div class="tarjeta"><div class="e">Requieren revisión</div><div class="v">${fmt.format(revisar)}</div></div>
  </div>
  <form class="filtros" id="filtros">
    <label>Acción <select name="accion"><option value="">Todas</option>${ACCIONES.map(a => `<option ${f.accion === a ? "selected" : ""}>${esc(a)}</option>`).join("")}</select></label>
    <label>Segmento <select name="segmento"><option value="">Todos</option>${(datos.segmentos || []).map(s => `<option ${f.segmento === s ? "selected" : ""}>${esc(s)}</option>`).join("")}</select></label>
    <label>Buscar ID <input name="q" value="${esc(f.q)}" placeholder="CLI001" autocomplete="off"></label>
    <label class="fila" style="display:flex"><input type="checkbox" name="frio" value="1" ${f.frio ? "checked" : ""}> Solo fríos</label>
    <button>Aplicar</button>${enServidor() && puede("cartera.exportar") ? `<a class="chip" href="/api/cierres/${esc(S.cierre)}/agenda.csv">Exportar CSV</a>` : ""}
  </form>
  <p class="muted">${datos.total} cliente(s) con los filtros · ingreso del conjunto filtrado ${cop(datos.ingreso_filtrado)} · orden: acción, probabilidad descendente (sin estimación al final), ID.</p>
  ${datos.total === 0 ? estadoHtml("", "Sin coincidencias para estos filtros.") : `
  <div class="tabla"><table><thead><tr><th>Cliente</th><th>Acción sugerida</th><th>Motivos</th><th class="n">Prob. compra 30 d</th><th class="n">Días sin compra</th><th class="n">Ingreso</th></tr></thead><tbody>
  ${datos.items.map(c => `<tr class="fila-enlace"><td><a href="#/clientes/${encodeURIComponent(c.cliente_id)}?${queryDeFiltros(f)}">${esc(c.cliente_id)}</a>${c.segmento ? `<div class="muted">${esc(c.segmento)}</div>` : ""}</td>
    <td>${esc(c.accion)}</td><td>${c.motivos.map(m => `<span class="chip ${m === c.accion ? "fuerte" : ""}">${esc(m)}</span>`).join("")}${c.frecuente ? '<span class="chip">Frecuente</span>' : ""}</td>
    <td class="n">${c.sin_historial ? "Sin historial" : c.prob_compra_30d == null ? "Modelo no disponible" : pct(c.prob_compra_30d)}</td>
    <td class="n">${c.dias_sin_compra ?? "Sin historial"}</td><td class="n">${cop(c.ingreso_cop)}</td></tr>`).join("")}
  </tbody></table></div>
  <div class="fila" style="margin-top:8px">${datos.pagina > 1 ? `<a href="#/agenda?${queryDeFiltros({ ...f, pagina: datos.pagina - 1 })}">← Anterior</a>` : ""}
    <span class="muted">Página ${datos.pagina} de ${datos.paginas}</span>
    ${datos.pagina < datos.paginas ? `<a href="#/agenda?${queryDeFiltros({ ...f, pagina: datos.pagina + 1 })}">Siguiente →</a>` : ""}</div>`}
  <p class="muted">La probabilidad estima propensión de compra; una alerta no es una venta confirmada. ${datos.modelo ? `Modelo ${esc(datos.modelo.version || "")}, umbral ${esc(datos.modelo.umbral ?? "—")}.` : ""}</p>`;
  document.getElementById("filtros").addEventListener("submit", ev => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    ir(`#/agenda?${queryDeFiltros({ accion: fd.get("accion"), segmento: fd.get("segmento"), q: fd.get("q").trim(), frio: fd.get("frio") || "", pagina: 1 })}`);
  });
  document.getElementById("cierre")?.addEventListener("change", e => { S.cierre = e.target.value; render(); });
}

// ---------------------------------------------------------------- ficha (B03)
async function vistaFicha(id, q) {
  const volver = `<a href="#/agenda?${q.toString()}">← Volver a la agenda</a>`;
  const turno = nuevoTurno();
  $vista.innerHTML = `${volver}${estadoHtml("", "Cargando ficha…")}`;
  let f;
  try {
    if (enServidor()) f = await api("GET", `/api/cierres/${S.cierre}/clientes/${encodeURIComponent(id)}`);
    else {
      if (!S.local) await cargarLocal();
      const c = S.local.datos.clientes.find(x => x.cliente_id === id);
      if (!c) throw Object.assign(new Error(`Cliente ${id} no encontrado en este corte; no se inventa historial.`), { status: 404 });
      f = { cierre: { corte: S.local.datos.corte }, cliente: { ...c, motivos: motivos(c, S.local.datos.modelo?.umbral ?? null), sin_historial: c.ultima_compra === null },
        productos: c.productos.map(p => ({ producto: p })), historial: [], coberturas: [], oportunidades: [] };
    }
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${volver}${errorHtml(e)}`; return; }
  if (!vigente(turno)) return;
  const c = f.cliente;
  $vista.innerHTML = `${volver}<h1>${esc(c.cliente_id)} <span class="muted">· corte ${esc(f.cierre.corte)}</span></h1>
  <div class="tarjetas">
    <div class="tarjeta"><div class="e">Acción sugerida</div><div class="v" style="font-size:17px">${esc(c.accion)}</div><div>${c.motivos.map(m => `<span class="chip">${esc(m)}</span>`).join("")}</div></div>
    <div class="tarjeta"><div class="e">Probabilidad de compra a 30 días (predicción)</div><div class="v">${c.sin_historial ? "Sin historial" : c.prob_compra_30d == null ? "—" : pct(c.prob_compra_30d)}</div><div class="e">${c.prob_compra_30d == null && !c.sin_historial ? "Modelo no disponible: se mantienen las reglas" : c.prob_compra_30d === 0 ? "0 % es una estimación, no ausencia de datos" : ""}</div></div>
    <div class="tarjeta"><div class="e">Última compra (histórico)</div><div class="v" style="font-size:17px">${c.ultima_compra ? esc(c.ultima_compra) : "Sin historial"}</div><div class="e">${c.dias_sin_compra != null ? `${c.dias_sin_compra} días sin compra` : ""}</div></div>
    <div class="tarjeta"><div class="e">Ventas confirmadas · ingreso</div><div class="v" style="font-size:17px">${c.ventas_confirmadas} · ${cop(c.ingreso_cop)}</div></div>
    <div class="tarjeta"><div class="e">Etiquetas</div><div>${c.frecuente ? '<span class="chip">Frecuente</span>' : ""}${c.frio ? '<span class="chip">Frío</span>' : ""}${!c.frecuente && !c.frio ? '<span class="muted">Ninguna</span>' : ""}</div><div class="e">Segmento: ${esc(f.segmento?.segmento || c.segmento || "—")}</div></div>
    <div class="tarjeta"><div class="e">Coberturas</div><div class="v" style="font-size:17px">${c.renovaciones_proximas} próximas · ${c.coberturas_vencidas} vencidas</div></div>
  </div>
  <div class="grid2">
   <div class="panel"><h2>Productos adquiridos</h2>${f.productos.length ? `<table><tr><th>Producto</th><th class="n">Op.</th><th class="n">Importe</th><th>Última</th></tr>${f.productos.map(p => `<tr><td>${esc(p.producto)}</td><td class="n">${p.operaciones ?? ""}</td><td class="n">${p.importe_cop != null ? cop(p.importe_cop) : ""}</td><td>${esc(p.ultima || "")}</td></tr>`).join("")}</table>` : '<p class="muted">Sin historial de compras.</p>'}</div>
   <div class="panel"><h2>Coberturas instaladas</h2>${f.coberturas.length ? `<table><tr><th>Instalación</th><th>Producto</th><th>Fin</th><th>Estado</th></tr>${f.coberturas.map(x => `<tr><td>${esc(x.instalacion_id)}</td><td>${esc(x.producto || x.producto_id)}</td><td>${esc(x.fecha_fin)}</td><td>${esc(x.estado)}${x.dias_para_fin != null ? ` (${x.dias_para_fin} d)` : ""}</td></tr>`).join("")}</table><p class="muted">Fecha contractual, no compra confirmada.</p>` : `<p class="muted">${enServidor() ? "Sin coberturas publicadas." : "Detalle no incluido en la agenda local."}</p>`}</div>
  </div>
  ${f.historial.length ? `<div class="panel"><h2>Historial de ventas (más recientes)</h2><div class="tabla"><table><tr><th>Fecha</th><th>Venta</th><th>Producto</th><th class="n">Cant.</th><th>Moneda</th><th class="n">COP</th></tr>${f.historial.slice(0, 20).map(v => `<tr><td>${esc(v.fecha)}</td><td>${esc(v.venta_id)}</td><td>${esc(v.producto || v.producto_id)}</td><td class="n">${v.cantidad}</td><td>${esc(v.moneda)}${v.tasa ? ` @ ${fmt.format(v.tasa)}` : ""}</td><td class="n">${cop(v.importe_cop)}</td></tr>`).join("")}</table></div></div>` : ""}
  ${f.tarea ? `<div class="panel"><h2>Seguimiento</h2><p>Tarea #${f.tarea.id} · ${esc(f.tarea.estado)}${f.tarea.responsable_id ? ` · responsable ${esc(f.tarea.responsable_id)}` : ""} · <a href="#/tareas/${f.tarea.id}">Abrir</a></p></div>` : ""}`;
  $vista.focus();
}

// ---------------------------------------------------------------- tableros (B03)
async function vistaTableros(rolSel) {
  const roles = ["ventas", "operaciones", "gerencia"].filter(r => puede(`tablero.${r}`));
  const rol = roles.includes(rolSel) ? rolSel : roles[0];
  const turno = nuevoTurno();
  $vista.innerHTML = `<h1>Tableros</h1><div class="fila">${roles.map(r => `<a class="chip ${r === rol ? "fuerte" : ""}" href="#/tableros/${r}">${r}</a>`).join("")}</div>${estadoHtml("", "Cargando…")}`;
  let t;
  try { t = await api("GET", `/api/cierres/${S.cierre}/tableros/${rol}`); } catch (e) { if (vigente(turno)) $vista.innerHTML += errorHtml(e); return; }
  if (!vigente(turno)) return;
  let cuerpo = "";
  if (rol === "ventas") {
    cuerpo = `<div class="grid2"><div class="panel"><h2>Clientes por segmento</h2><table>${t.segmentos.map(s => `<tr><td>${esc(s.segmento)}</td><td class="n">${s.clientes}</td></tr>`).join("")}</table>
      <p class="muted">Frecuentes ${t.etiquetas.frecuentes} · fríos ${t.etiquetas.frios}. ${esc(t.etiquetas.nota)}</p></div>
      <div class="panel"><h2>Oportunidades prioritarias</h2><table><tr><th>Cliente</th><th>Tipo</th><th>Motivos</th><th class="n">Prob.</th></tr>${t.oportunidades.map(o => `<tr><td><a href="#/clientes/${encodeURIComponent(o.cliente_id)}">${esc(o.cliente_id)}</a></td><td>${esc(o.tipo)}</td><td>${o.motivos.map(m => `<span class="chip">${esc(m)}</span>`).join("")}</td><td class="n">${pct(o.probabilidad) ?? "—"}</td></tr>`).join("") || '<tr><td colspan=4 class="muted">Sin oportunidades publicadas.</td></tr>'}</table></div></div>`;
  } else if (rol === "operaciones") {
    const filaCob = x => `<tr><td><a href="#/clientes/${encodeURIComponent(x.cliente_id)}">${esc(x.cliente_id)}</a></td><td>${esc(x.producto || x.producto_id)}</td><td>${esc(x.fecha_fin)}</td><td class="n">${x.dias_para_fin ?? ""}</td></tr>`;
    cuerpo = `<div class="tarjetas"><div class="tarjeta"><div class="e">Renovaciones próximas (≤45 d)</div><div class="v">${t.resumen_coberturas.renovaciones_proximas}</div></div>
      <div class="tarjeta"><div class="e">Coberturas vencidas</div><div class="v">${t.resumen_coberturas.coberturas_vencidas}</div></div>
      ${Object.entries(t.tareas_por_estado).map(([k, v]) => `<div class="tarjeta"><div class="e">Seguimientos ${esc(k)}</div><div class="v">${v}</div></div>`).join("")}</div>
      <div class="grid2"><div class="panel"><h2>Próximas a vencer</h2><table><tr><th>Cliente</th><th>Producto</th><th>Fin</th><th class="n">Días</th></tr>${t.coberturas_proximas.map(filaCob).join("") || '<tr><td colspan=4 class="muted">Ninguna.</td></tr>'}</table></div>
      <div class="panel"><h2>Vencidas</h2><table><tr><th>Cliente</th><th>Producto</th><th>Fin</th><th class="n">Días</th></tr>${t.coberturas_vencidas.map(filaCob).join("") || '<tr><td colspan=4 class="muted">Ninguna.</td></tr>'}</table></div></div><p class="muted">${esc(t.nota)}</p>`;
  } else {
    const i = t.indicadores;
    cuerpo = `<div class="tarjetas"><div class="tarjeta"><div class="e">Ingreso confirmado acumulado</div><div class="v" style="font-size:18px">${cop(i.ingreso_cop)}</div></div>
      <div class="tarjeta"><div class="e">Ventas confirmadas</div><div class="v">${fmt.format(i.ventas_confirmadas)}</div></div>
      <div class="tarjeta"><div class="e">Clientes</div><div class="v">${i.clientes}</div></div><div class="tarjeta"><div class="e">Fríos</div><div class="v">${i.clientes_frios}</div></div></div>
      <div class="grid2"><div class="panel grafico" style="position:relative"><h2>Ventas mensuales confirmadas (histórico, COP)</h2>${graficoLinea(t.evolucion.map(s => ({ periodo: s.periodo, valor: s.valor_cop })), [])}</div>
      <div class="panel"><h2>Clientes por segmento</h2><table><tr><th>Segmento</th><th class="n">Clientes</th><th class="n">Ingreso</th></tr>${t.segmentos.map(s => `<tr><td>${esc(s.segmento)}</td><td class="n">${s.clientes}</td><td class="n">${cop(s.ingreso_cop)}</td></tr>`).join("")}</table></div></div>`;
  }
  $vista.innerHTML = `<h1>Tablero de ${esc(rol)} · corte ${esc(t.cierre.corte)}</h1><div class="fila">${roles.map(r => `<a class="chip ${r === rol ? "fuerte" : ""}" href="#/tableros/${r}">${r}</a>`).join("")}</div>${cuerpo}`;
  activarTooltips();
}

// Gráfico de línea: una serie, histórico sólido y proyección punteada (misma serie, mismo color).
function graficoLinea(hist, proy) {
  const pts = [...hist.map(p => ({ ...p, tipo: "Histórico" })), ...proy.map(p => ({ ...p, tipo: "Proyección" }))];
  if (!pts.length) return '<p class="muted">Sin serie publicada.</p>';
  const W = 560, H = 220, m = { l: 64, r: 34, t: 12, b: 28 };
  const vals = pts.map(p => p.valor).filter(v => v != null);
  const max = Math.max(1, ...vals) * 1.1;
  const x = i => m.l + (pts.length === 1 ? 0 : i * (W - m.l - m.r) / (pts.length - 1));
  const y = v => H - m.b - v / max * (H - m.t - m.b);
  const seg = (desde, hasta) => {
    let d = "", abierto = false;
    for (let i = desde; i <= hasta; i++) {
      const v = pts[i].valor;
      if (v == null) { abierto = false; continue; }
      d += `${abierto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; abierto = true;
    }
    return d;
  };
  const nh = hist.length;
  const ticks = [0, .5, 1].map(f => max / 1.1 * f);
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Serie mensual en COP; tabla con los mismos valores debajo">
    ${ticks.map(t => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--rejilla)"/><text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--texto-2)">${fmt.format(Math.round(t / 1e6))} M</text>`).join("")}
    <path d="${seg(0, nh - 1)}" fill="none" stroke="var(--serie-1)" stroke-width="2"/>
    ${proy.length ? `<path d="${seg(Math.max(0, nh - 1), pts.length - 1)}" fill="none" stroke="var(--serie-1)" stroke-width="2" stroke-dasharray="5 4"/>` : ""}
    ${pts.map((p, i) => p.valor == null ? `<text x="${x(i) + 6}" y="${H - m.b - 16}" text-anchor="start" font-size="10" fill="var(--texto-3)">s/d</text>` :
      `<circle cx="${x(i)}" cy="${y(p.valor)}" r="4" fill="var(--serie-1)" stroke="var(--superficie)" stroke-width="2"/><circle class="hit" cx="${x(i)}" cy="${y(p.valor)}" r="12" fill="transparent" data-tip="${esc(`${p.periodo} · ${p.tipo}: ${cop(p.valor)}`)}"/>`).join("")}
    ${pts.map((p, i) => (i % Math.ceil(pts.length / 8) === 0 || i === pts.length - 1) ? `<text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="11" fill="var(--texto-2)">${esc(p.periodo)}</text>` : "").join("")}
  </svg><div class="tip oculto"></div>
  <details><summary class="muted">Ver tabla</summary><table><tr><th>Mes</th><th>Tipo</th><th class="n">COP</th></tr>${pts.map(p => `<tr><td>${esc(p.periodo)}</td><td>${p.tipo}</td><td class="n">${p.valor == null ? "Sin dato (mes incompleto)" : cop(p.valor)}</td></tr>`).join("")}</table></details>`;
}
function activarTooltips() {
  $vista.querySelectorAll(".grafico").forEach(g => {
    const tip = g.querySelector(".tip");
    g.querySelectorAll(".hit").forEach(h => {
      h.addEventListener("mouseenter", () => {
        const r = h.getBoundingClientRect(), b = g.getBoundingClientRect();
        tip.textContent = h.dataset.tip; tip.classList.remove("oculto");
        tip.style.left = `${Math.min(r.left - b.left, b.width - 180)}px`; tip.style.top = `${r.top - b.top - 34}px`;
      });
      h.addEventListener("mouseleave", () => tip.classList.add("oculto"));
    });
  });
}

// ---------------------------------------------------------------- seguimientos (B05)
async function vistaTareas(id) {
  if (id) return vistaTarea(Number(id));
  const { q } = ruta();
  const k = q.get("k") || "10", mias = q.get("mias") === "1";
  const turno = nuevoTurno();
  const [lista, avisos, met] = await Promise.all([api("GET", `/api/tareas?k=${encodeURIComponent(k)}${mias ? "&mias=1" : ""}`), api("GET", "/api/avisos"), api("GET", "/api/tareas/metricas")]).catch(e => [e]);
  if (!vigente(turno)) return;
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  $vista.innerHTML = `<h1>Seguimientos</h1>
  <form class="filtros" id="f"><label>Cupo de contactos (K) <input name="k" type="number" min="1" max="200" value="${esc(k)}"></label>
   <label class="fila" style="display:flex"><input type="checkbox" name="mias" value="1" ${mias ? "checked" : ""}> Solo asignadas a mí</label><button>Planificar</button></form>
  <div class="tabla"><table><tr><th>#</th><th>Cliente</th><th>Tipo</th><th>Motivos</th><th>Estado</th><th>Responsable</th><th>Revisar</th></tr>
  ${lista.map((t, i) => `<tr><td>${i + 1}</td><td><a href="#/clientes/${encodeURIComponent(t.cliente_id)}">${esc(t.cliente_id)}</a></td><td>${esc(t.tipo)}</td><td>${t.motivos.map(m => `<span class="chip">${esc(m)}</span>`).join("")}</td><td>${esc(t.estado)}</td><td>${esc(t.responsable_id || "—")}</td><td><a href="#/tareas/${t.id}">${esc(t.fecha_revision || "abrir")}</a></td></tr>`).join("") || '<tr><td colspan=7 class="muted">Sin tareas abiertas.</td></tr>'}
  </table></div>
  <div class="grid2"><div class="panel"><h2>Avisos</h2>${avisos.slice(0, 12).map(a => `<div class="muted">${esc(a.creado_en.slice(0, 16))} · ${esc(a.mensaje)}</div>`).join("") || '<p class="muted">Sin avisos.</p>'}</div>
  <div class="panel"><h2>Medición</h2><table><tr><th>Tipo</th><th class="n">Total</th><th class="n">Atendida</th><th class="n">Descarte</th></tr>${Object.entries(met.por_tipo).map(([t, v]) => `<tr><td>${esc(t)}</td><td class="n">${v.total}</td><td class="n">${pct(v.fraccion_atendida)}</td><td class="n">${pct(v.tasa_descarte)}</td></tr>`).join("")}</table>
  <p class="muted">Avisos duplicados: ${met.avisos_duplicados} · episodios con varias tareas: ${met.episodios_con_varias_tareas}. ${esc(met.nota)}</p></div></div>`;
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const fd = new FormData(e.target); ir(`#/tareas?k=${fd.get("k")}${fd.get("mias") ? "&mias=1" : ""}`); });
}
async function vistaTarea(id) {
  let t;
  try { t = await api("GET", `/api/tareas/${id}`); } catch (e) { $vista.innerHTML = errorHtml(e); return; }
  const editable = puede("tareas.gestionar") && !["atendida", "descartada"].includes(t.estado);
  $vista.innerHTML = `<a href="#/tareas">← Seguimientos</a><h1>Tarea #${t.id} · ${esc(t.cliente_id)}</h1>
  <p>${t.motivos.map(m => `<span class="chip">${esc(m)}</span>`).join("")} · estado <strong>${esc(t.estado)}</strong> · versión ${t.version}${t.responsable_id ? ` · responsable ${esc(t.responsable_id)}` : ""}</p>
  ${t.resultado ? `<p>Resultado: ${esc(t.resultado)} ${t.siguiente_paso ? `· Siguiente paso: ${esc(t.siguiente_paso)}` : ""}</p>` : ""}${t.motivo_descarte ? `<p>Descartada: ${esc(t.motivo_descarte)}</p>` : ""}
  <div id="msg"></div>
  ${editable ? `<div class="panel"><h2>Tramitar</h2><div class="fila">
    <button data-a="asignar">Asignarme</button>
    <label>Posponer hasta <input type="date" id="hasta"></label><button class="sec" data-a="posponer">Posponer</button>
    <button class="sec" data-a="contacto">Registrar contacto</button></div>
    <div class="fila" style="margin-top:8px"><label>Resultado <input id="resultado" placeholder="p. ej. agenda reunión"></label><label>Siguiente paso <input id="siguiente"></label>
    <label class="fila" style="display:flex"><input type="checkbox" id="atribuido"> Resultado atribuido al seguimiento</label><button data-a="atender">Marcar atendida</button></div>
    <div class="fila" style="margin-top:8px"><label>Motivo de descarte <input id="motivo"></label><button class="sec" data-a="descartar">Descartar</button></div>
    <p class="muted">La decisión humana se registra antes de cualquier contacto con la empresa.</p></div>` : ""}
  <div class="grid2"><div class="panel"><h2>Evidencia por cierre</h2>${t.historial_evidencia.map(e => `<div><strong>${esc(e.cierre_id)}</strong> ${e.motivos.map(m => `<span class="chip">${esc(m)}</span>`).join("")}<div class="muted"><code>${esc(JSON.stringify(e.evidencia))}</code> · modelo ${esc(e.version_modelo || "—")}</div></div>`).join("")}</div>
  <div class="panel"><h2>Eventos</h2>${t.eventos.map(e => `<div class="muted">${esc(e.fecha.slice(0, 16))} · ${esc(e.tipo)} · ${esc(e.actor)}${e.resultado ? ` · ${esc(e.resultado)}` : ""}</div>`).join("")}</div></div>`;
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    const a = b.dataset.a, cuerpo = { version: t.version, __clave: clave() };
    if (a === "posponer") cuerpo.hasta = document.getElementById("hasta").value;
    if (a === "descartar") cuerpo.motivo = document.getElementById("motivo").value;
    if (a === "atender") Object.assign(cuerpo, { resultado: document.getElementById("resultado").value, siguiente_paso: document.getElementById("siguiente").value, atribuido: document.getElementById("atribuido").checked });
    if (a === "contacto") cuerpo.siguiente_paso = document.getElementById("siguiente").value;
    try { await api("POST", `/api/tareas/${t.id}/${a}`, cuerpo); vistaTarea(t.id); }
    catch (e) { document.getElementById("msg").innerHTML = errorHtml(e); }
  }));
}

// ---------------------------------------------------------------- PQRS (B04/B10)
async function vistaPqrs(rad) {
  if (rad) return vistaPqrsDetalle(rad);
  const { q } = ruta();
  const externo = S.usuario.externo;
  const [lista, ind, bandeja] = await Promise.all([
    api("GET", `/api/pqrs?${new URLSearchParams({ estado: q.get("estado") || "", revision: q.get("revision") || "" })}`),
    puede("pqrs.indicadores") ? api("GET", "/api/pqrs-indicadores") : null,
    puede("pqrs.gestionar") ? api("GET", "/api/atencion/bandeja") : null]).catch(e => [e]);
  if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
  $vista.innerHTML = `<h1>${externo ? "Mis PQRS" : "Bandeja de PQRS"}</h1>
  ${puede("pqrs.crear") ? `<div class="panel"><h2>Radicar una PQRS</h2><form id="nueva"><label>Asunto <input name="asunto" required maxlength="200"></label>
    <label>Descripción <textarea name="descripcion" required maxlength="5000"></textarea></label><button>Radicar</button></form><div id="msg"></div></div>` : ""}
  ${ind ? `<div class="tarjetas">${Object.entries(ind.por_estado).map(([k, v]) => `<div class="tarjeta"><div class="e">${esc(k.replace("_", " "))}</div><div class="v">${v}</div></div>`).join("")}<div class="tarjeta"><div class="e">En revisión de clasificación</div><div class="v">${ind.en_revision}</div></div></div>
    <p class="muted">Mediana horas a primera gestión: ${esc(JSON.stringify(ind.horas_primera_gestion_mediana))} · a respuesta: ${esc(JSON.stringify(ind.horas_resolucion_mediana))} · abiertos: ${esc(JSON.stringify(ind.abiertos_por_categoria))}. ${esc(ind.nota)}</p>` : ""}
  ${bandeja ? `<div class="panel"><h2>Revisión pendiente</h2><p class="muted">Casos sin clasificación confiable: ${bandeja.casos_sin_clasificar.map(c => `<a href="#/pqrs/${esc(c.radicado)}">${esc(c.radicado)}</a>`).join(", ") || "ninguno"} · borradores por aprobar: ${bandeja.borradores.map(b => `<a href="#/pqrs/${esc(b.radicado)}">${esc(b.radicado)}</a> (${esc(b.estado)})`).join(", ") || "ninguno"}</p></div>` : ""}
  ${!externo ? `<div class="filtros"><a class="chip" href="#/pqrs">Todos</a>${["recibido", "en_gestion", "respondido", "cerrado"].map(e => `<a class="chip" href="#/pqrs?estado=${e}">${e.replace("_", " ")}</a>`).join("")}<a class="chip" href="#/pqrs?revision=1">Requieren revisión</a></div>` : ""}
  <div class="tabla"><table><tr><th>Radicado</th><th>Asunto</th><th>Estado</th>${externo ? "" : "<th>Categoría</th><th class='n'>Antigüedad</th><th>Responsable</th>"}<th>Creado</th></tr>
  ${lista.map(c => `<tr><td><a href="#/pqrs/${esc(c.radicado)}">${esc(c.radicado)}</a></td><td>${esc(c.asunto)}</td><td>${esc(c.estado.replace("_", " "))}</td>
    ${externo ? "" : `<td>${esc(c.categoria || "—")}${c.requiere_revision ? ' <span class="chip">revisar</span>' : ""}</td><td class="n">${c.antiguedad_dias} d${c.vencido ? " ⚠" : ""}</td><td>${esc(c.responsable_id || "—")}</td>`}<td>${esc(c.creado_en.slice(0, 10))}</td></tr>`).join("") || `<tr><td colspan=7 class="muted">Sin casos.</td></tr>`}
  </table></div>`;
  document.getElementById("nueva")?.addEventListener("submit", async e => {
    e.preventDefault();
    const btn = e.target.querySelector("button"); btn.disabled = true;
    const fd = new FormData(e.target);
    e.target.dataset.clave ||= clave();   // reintentos del mismo formulario → mismo radicado
    try {
      const r = await api("POST", "/api/pqrs", { asunto: fd.get("asunto"), descripcion: fd.get("descripcion"), __clave: e.target.dataset.clave });
      ir(`#/pqrs/${r.radicado}`);
    } catch (err) { document.getElementById("msg").innerHTML = errorHtml(err); btn.disabled = false; }
  });
}
async function vistaPqrsDetalle(rad) {
  let c;
  try { c = await api("GET", `/api/pqrs/${encodeURIComponent(rad)}`); } catch (e) { $vista.innerHTML = `<a href="#/pqrs">← PQRS</a>${errorHtml(e)}`; return; }
  if (S.usuario.externo) {
    $vista.innerHTML = `<a href="#/pqrs">← Mis PQRS</a><h1>${esc(c.radicado)}</h1><p><strong>${esc(c.asunto)}</strong> · estado ${esc(c.estado.replace("_", " "))}</p><div class="burbuja">${esc(c.descripcion)}</div>
    <h2>Respuesta</h2>${c.respuesta_publicada ? `<div class="burbuja yo">${esc(c.respuesta_publicada)}</div>` : '<p class="muted">Aún no hay una respuesta publicada.</p>'}
    <h2>Historial</h2>${c.historial.map(h => `<div class="muted">${esc(h.ts.slice(0, 16))} · ${esc(h.accion)} → ${esc(h.a_estado || "")}</div>`).join("")}`;
    return;
  }
  const sug = c.sugerencias.at(-1);
  $vista.innerHTML = `<a href="#/pqrs">← Bandeja</a><h1>${esc(c.radicado)} <span class="muted">· ${esc(c.organizacion)}</span></h1>
  <p><strong>${esc(c.asunto)}</strong> · estado <strong>${esc(c.estado)}</strong> · versión ${c.version} · responsable ${esc(c.responsable_id || "—")}</p>
  <div class="burbuja">${esc(c.descripcion)}</div><div id="msg"></div>
  <div class="grid2"><div class="panel"><h2>Clasificación</h2>
    <p>Sugerida: <strong>${esc(sug?.categoria || "—")}</strong> (${sug?.confianza != null ? pct(sug.confianza) : "—"}, ${esc(sug?.version || "")})${sug?.revisar ? ` · <span class="chip">revisión: ${esc(sug.motivo || "baja confianza")}</span>` : ""}<br>Revisada: <strong>${esc(c.categoria_revisada || "pendiente")}</strong></p>
    <div class="fila"><select id="cat">${["peticion", "queja", "reclamo", "sugerencia"].map(x => `<option ${x === (c.categoria_revisada || sug?.categoria) ? "selected" : ""}>${x}</option>`).join("")}</select>
    <button data-a="categorizar">Confirmar categoría</button><button class="sec" data-r="reclasificar">Reprocesar sugerencia</button></div></div>
   <div class="panel"><h2>Gestión</h2><div class="fila"><button data-a="asignar">Asignarme</button><button class="sec" data-a="cerrar">Cerrar</button>
    <label>Motivo de reapertura <input id="nota"></label><button class="sec" data-a="reabrir">Reabrir</button></div>
    <p class="muted">${c.respuesta_publicada ? `Respuesta publicada: ${esc(c.respuesta_publicada)}` : "Sin respuesta publicada."}</p></div></div>
  <div class="panel"><h2>Borradores asistidos</h2><button id="gen">Generar borrador con fuentes vigentes</button>
   ${c.borradores.map(b => `<div class="panel"><p>#${b.id} · <strong>${esc(b.estado)}</strong>${b.motivo_revision ? ` · ${esc(b.motivo_revision)}` : ""} · ${esc(b.version_generador)}${b.aprobado_por ? ` · aprobado por ${esc(b.aprobado_por)}` : ""}</p>
     <textarea data-b="${b.id}" ${["pendiente", "requiere_revision"].includes(b.estado) ? "" : "readonly"}>${esc(b.texto)}</textarea>
     <p class="muted">Fuentes: ${b.fuentes.map(f => `${esc(f.titulo)} v${f.version} (${esc(f.localizador)})`).join("; ") || "ninguna"}</p>
     ${["pendiente", "requiere_revision"].includes(b.estado) ? `<div class="fila"><button class="sec" data-ed="${b.id}">Guardar edición</button><button data-ap="${b.id}" data-rev="${b.estado === "requiere_revision" ? 1 : 0}">Aprobar y publicar al cliente</button></div>` : ""}</div>`).join("")}</div>
  <div class="panel"><h2>Bitácora</h2>${c.bitacora.map(h => `<div class="muted">${esc(h.ts.slice(0, 16))} · ${esc(h.actor)} · ${esc(h.accion)} ${esc(h.de_estado || "")} → ${esc(h.a_estado || "")} ${h.nota ? `· ${esc(h.nota)}` : ""}</div>`).join("")}</div>`;
  const msg = e => { document.getElementById("msg").innerHTML = errorHtml(e); };
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    const a = b.dataset.a, cuerpo = { version: c.version };
    if (a === "categorizar") cuerpo.categoria = document.getElementById("cat").value;
    if (a === "reabrir") cuerpo.nota = document.getElementById("nota").value;
    try { await api("POST", `/api/pqrs/${c.radicado}/${a}`, cuerpo); vistaPqrsDetalle(c.radicado); } catch (e) { msg(e); }
  }));
  $vista.querySelector("[data-r]").addEventListener("click", async () => { try { await api("POST", `/api/pqrs/${c.radicado}/reclasificar`, {}); vistaPqrsDetalle(c.radicado); } catch (e) { msg(e); } });
  document.getElementById("gen").addEventListener("click", async () => { try { await api("POST", `/api/pqrs/${c.radicado}/borradores`, {}); vistaPqrsDetalle(c.radicado); } catch (e) { msg(e); } });
  $vista.querySelectorAll("[data-ed]").forEach(b => b.addEventListener("click", async () => {
    try { await api("POST", `/api/borradores/${b.dataset.ed}/editar`, { texto: $vista.querySelector(`textarea[data-b="${b.dataset.ed}"]`).value }); vistaPqrsDetalle(c.radicado); } catch (e) { msg(e); }
  }));
  $vista.querySelectorAll("[data-ap]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true;
    try { await api("POST", `/api/borradores/${b.dataset.ap}/aprobar`, { confirmar_revision: b.dataset.rev === "1" }); vistaPqrsDetalle(c.radicado); } catch (e) { msg(e); b.disabled = false; }
  }));
}

// ---------------------------------------------------------------- beneficios (B06)
async function vistaBeneficios() {
  if (S.usuario.externo) {
    const lista = await api("GET", "/api/portal/beneficios").catch(e => e);
    if (lista instanceof Error) { $vista.innerHTML = errorHtml(lista); return; }
    $vista.innerHTML = `<h1>Beneficios y servicios disponibles</h1>
    ${lista.map(b => `<div class="panel"><h2>${esc(b.titulo)}</h2><p>${esc(b.descripcion)}</p>
      <p class="muted">${esc(b.empresa_emisora)} · fuente ${esc(b.fuente)} · vigente ${esc(b.vigencia_desde)} – ${esc(b.vigencia_hasta || "nuevo aviso")}</p>
      ${b.elegibilidad === "revision" ? '<p class="estado">Tu elegibilidad requiere revisión de Atención.</p>' : ""}
      <p>${esc(b.como_solicitar)} <a href="#/pqrs">Abrir una PQRS</a></p></div>`).join("") || estadoHtml("", "No hay beneficios vigentes para tu empresa.")}`;
    return;
  }
  const [cat, ret] = await Promise.all([api("GET", "/api/beneficios"), api("GET", "/api/beneficios-retencion")]).catch(e => [e]);
  if (cat instanceof Error) { $vista.innerHTML = errorHtml(cat); return; }
  $vista.innerHTML = `<h1>Catálogo de beneficios</h1><div id="msg"></div>
  <div class="tabla"><table><tr><th>ID</th><th>v</th><th>Título</th><th>Vigencia</th><th>Criterio</th><th>Estado</th><th></th></tr>
  ${cat.map(b => `<tr><td>${esc(b.id)}</td><td>${b.version}</td><td>${esc(b.titulo)}<div class="muted">${esc(b.politica || "")}</div></td><td>${esc(b.vigencia_desde)} – ${esc(b.vigencia_hasta || "…")}</td><td><code>${esc(JSON.stringify(b.criterio))}</code></td><td>${esc(b.estado)}</td>
   <td>${b.estado === "borrador" ? `<button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="enviar_revision">Enviar a revisión</button>` : ""}
   ${b.estado === "revision" && puede("beneficios.publicar") ? `<button data-b="${esc(b.id)}" data-v="${b.version}" data-a="publicar">Publicar</button><button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="devolver">Devolver</button>` : ""}
   ${b.estado === "publicado" && puede("beneficios.publicar") ? `<button class="sec" data-b="${esc(b.id)}" data-v="${b.version}" data-a="retirar">Retirar</button>` : ""}</td></tr>`).join("")}</table></div>
  ${puede("beneficios.editar") ? `<div class="panel"><h2>Nuevo borrador o nueva versión</h2><form id="nb" class="filtros">
    <label>ID <input name="id" required placeholder="BEN-..."></label><label>Título <input name="titulo" required></label><label>Descripción <input name="descripcion" required></label>
    <label>Fuente aprobada <input name="fuente" required></label><label>Desde <input type="date" name="vigencia_desde" required></label><label>Hasta <input type="date" name="vigencia_hasta"></label>
    <label>Criterio (JSON) <input name="criterio" value="{}"></label><label>Política <input name="politica"></label><button>Guardar borrador</button></form></div>` : ""}
  <div class="panel"><h2>Retención</h2><p class="muted">Elegibles para reactivación: ${ret.elegibles_reactivacion}. ${esc(ret.nota)}</p>${ret.por_beneficio.map(r => `<div>${esc(r.beneficio_id)}: ${r.seguimientos} seguimientos, ${r.atendidos} atendidos, ${r.recuperaciones} recuperaciones observadas</div>`).join("")}</div>`;
  const msg = e => { document.getElementById("msg").innerHTML = errorHtml(e); };
  $vista.querySelectorAll("button[data-a]").forEach(b => b.addEventListener("click", async () => {
    try { await api("POST", `/api/beneficios/${encodeURIComponent(b.dataset.b)}/${b.dataset.v}/${b.dataset.a}`, {}); vistaBeneficios(); } catch (e) { msg(e); }
  }));
  document.getElementById("nb")?.addEventListener("submit", async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    try { d.criterio = JSON.parse(d.criterio || "{}"); d.empresa_emisora = "Green Services (ficticio)"; if (!d.vigencia_hasta) delete d.vigencia_hasta; await api("POST", "/api/beneficios", d); vistaBeneficios(); }
    catch (err) { msg(err instanceof SyntaxError ? new Error("El criterio no es JSON válido") : err); }
  });
}

// ---------------------------------------------------------------- asistente (B07/B08/B10)
const historialChat = [];
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
let contextoEjemplos = null;

// Ejemplos construidos con el cierre activo (cliente real y meses del corte), no con datos fijos.
async function ejemplosAsistente() {
  if (S.usuario.externo) return ["¿Cuál es el estado de mi caso?", "¿Qué beneficios tengo disponibles?", "¿Cómo solicito un beneficio de renovación por fidelidad?"];
  if (!contextoEjemplos || contextoEjemplos.cierre !== S.cierre) {
    const ctx = { cierre: S.cierre, cliente: null, corte: null };
    try {
      if (puede("cartera.ver")) {
        const a = await api("GET", `/api/cierres/${S.cierre}/agenda?tam=1`);
        ctx.cliente = a.items[0]?.cliente_id || null; ctx.corte = a.corte;
      } else if (puede("finanzas.ver")) {
        ctx.corte = (await api("GET", `/api/cierres/${S.cierre}/resumen`)).cierre.corte;
      }
    } catch { /* sin cierre publicado: ejemplos genéricos */ }
    contextoEjemplos = ctx;
  }
  const { cliente, corte } = contextoEjemplos;
  const ej = [];
  if (cliente) ej.push(`¿Qué compró ${cliente}?`);
  if (corte) {
    const anio = Number(corte.slice(0, 4)), mes = Number(corte.slice(5, 7));
    const ant = mes === 1 ? [12, anio - 1] : [mes - 1, anio];
    const ant2 = ant[0] === 1 ? [12, ant[1] - 1] : [ant[0] - 1, ant[1]];
    ej.push(`¿A qué proveedores compramos en ${MESES[ant[0] - 1]} de ${ant[1]}?`,
      `¿Qué clientes redujeron compras entre ${MESES[ant2[0] - 1]} de ${ant2[1]} y ${MESES[ant[0] - 1]} de ${ant[1]}?`,
      `Ventas de ${MESES[mes - 1]} de ${anio}`);
  }
  ej.push("¿Qué significa frío?");
  return ej;
}

async function vistaAsistente() {
  const ejemplos = await ejemplosAsistente();
  $vista.innerHTML = `<h1>Asistente</h1><p class="muted">Las cifras las calcula el servicio con herramientas de solo lectura; el modelo de lenguaje solo redacta. Comprueba la evidencia.</p>
  <div id="chat">${historialChat.join("")}</div>
  <form id="f" class="fila"><input id="p" style="flex:1;min-width:220px" maxlength="1000" placeholder="Escribe tu pregunta" autocomplete="off"><button>Preguntar</button></form>
  <div class="fila" style="margin-top:8px">${ejemplos.map(e => `<button class="sec" type="button" data-e="${esc(e)}">${esc(e)}</button>`).join("")}</div>`;
  const enviar = async pregunta => {
    historialChat.push(`<div class="burbuja yo">${esc(pregunta)}</div>`);
    let html;
    try {
      const r = await api("POST", "/api/asistente", { pregunta, cierre: S.cierre });
      const ev = r.evidencia || {};
      const fuentes = (ev.fuentes || []).map(f => f.titulo ? `${esc(f.titulo)} v${f.version} (${esc(f.localizador)})`
        : f.beneficio_id ? `${esc(f.beneficio_id)} v${f.version} (${esc(f.fuente)})` : esc(JSON.stringify(f))).join("; ");
      html = `<div class="burbuja"><div>${esc(r.texto)}</div><div class="muted">estado ${esc(r.estado)} · herramienta ${esc(r.herramienta || "—")}${ev.corte ? ` · corte ${esc(ev.corte)}` : ""}${ev.unidad ? ` · ${esc(ev.unidad)}` : ""}${ev.filtros && Object.keys(ev.filtros).length ? ` · filtros ${esc(JSON.stringify(ev.filtros))}` : ""}${ev.detalle ? ` · <a href="${esc(ev.detalle)}">detalle</a>` : ""}${fuentes ? ` · fuentes: ${fuentes}` : ""} · ${esc(r.motor || "")} · ${esc(r.version || "")}</div></div>`;
    } catch (e) { html = errorHtml(e); }
    historialChat.push(html);
    if (location.hash.startsWith("#/asistente")) vistaAsistente();
  };
  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); const p = document.getElementById("p").value.trim(); if (p) enviar(p); });
  $vista.querySelectorAll("[data-e]").forEach(b => b.addEventListener("click", () => enviar(b.dataset.e)));
  document.getElementById("p").focus();
}

// ---------------------------------------------------------------- finanzas e informes (B09)
async function vistaFinanzas() {
  const { q } = ruta();
  const serie = q.get("serie") || "ventas";
  const turno = nuevoTurno();
  const [pan, informes] = await Promise.all([puede("finanzas.ver") ? api("GET", `/api/finanzas/${S.cierre}/panel?serie=${serie}`) : null,
    puede("informes.ver") ? api("GET", "/api/informes") : []]).catch(e => [e]);
  if (!vigente(turno)) return;
  if (pan instanceof Error) { $vista.innerHTML = errorHtml(pan); return; }
  const total = pan?.familias.find(f => f.familia === "Total");
  $vista.innerHTML = `<h1>Finanzas${pan ? ` · corte ${esc(pan.cierre.corte)}` : ""}</h1>
  ${pan ? `<div class="fila"><a class="chip ${serie === "ventas" ? "fuerte" : ""}" href="#/finanzas?serie=ventas">Ventas</a><a class="chip ${serie === "compras" ? "fuerte" : ""}" href="#/finanzas?serie=compras">Compras a proveedores</a></div>
  ${!pan.disponible ? estadoHtml("", "Pronóstico no disponible en este cierre: se muestran solo datos observados cuando existan.") : ""}
  <div class="grid2"><div class="panel grafico" style="position:relative"><h2>${serie === "ventas" ? "Ventas" : "Compras"} Total por mes (COP)</h2>
    ${total ? graficoLinea(total.historico.map(s => ({ periodo: s.periodo, valor: s.valor_cop })), total.pronostico.map(s => ({ periodo: s.periodo, valor: s.valor_cop }))) : '<p class="muted">Sin serie.</p>'}
    ${total?.pronostico.length ? `<p class="muted">Línea continua: histórico observado. Punteada: proyección (${esc(total.metodo)}, calculada ${esc(total.calculado_en)}). Error absoluto medio por horizonte: ${Object.entries(total.mae_por_horizonte).map(([h, m]) => `${h} m: ${m == null ? "sin evaluar" : cop(m)}${total.mae_ingenuo_por_horizonte?.[h] != null ? ` (ingenuo ${cop(total.mae_ingenuo_por_horizonte[h])})` : ""}`).map(esc).join(" · ")}. «s/d» = mes incompleto, distinto de cero.</p>` : ""}</div>
   <div class="panel"><h2>Mayores cambios mensuales por familia</h2><table><tr><th>Familia</th><th>Mes</th><th class="n">Cambio COP</th><th class="n">%</th></tr>${pan.mayores_cambios.map(c => `<tr><td>${esc(c.familia)}</td><td>${esc(c.periodo)}</td><td class="n">${cop(c.cambio_cop)}</td><td class="n">${c.cambio_pct == null ? "base 0" : fmt.format(c.cambio_pct)}</td></tr>`).join("")}</table><p class="muted">${esc(pan.agregacion)}</p></div></div>
  <div class="panel"><h2>Simulador de TRM (escenario, no modifica el cierre)</h2><form id="sim" class="filtros">
    <label>Periodo <input name="periodo" value="${esc(q.get("periodo") || pan.cierre.corte.slice(0, 7))}" pattern="\\d{4}-\\d{2}"></label>
    <label>Moneda <select name="moneda"><option>USD</option></select></label><label>Variación % <input name="variacion" type="number" step="0.5" value="${esc(q.get("variacion") || "8")}"></label><button>Simular</button></form><div id="res"></div></div>` : ""}
  ${puede("informes.ver") ? `<div class="panel"><h2>Informe mensual</h2>${puede("informes.generar") ? '<button id="gen">Generar informe del cierre</button>' : ""}<div id="msg"></div>
    <table><tr><th>Cierre</th><th>Revisión</th><th>Generado</th><th>Huella</th></tr>${informes.map(i => `<tr><td>${esc(i.cierre_id)}</td><td><a href="/api/informes/${esc(i.cierre_id)}/${i.revision}" target="_blank" rel="noopener">r${i.revision}</a></td><td>${esc(i.generado_en.slice(0, 16))} · ${esc(i.generado_por)}</td><td><code>${esc(i.huella_contenido.slice(0, 12))}</code></td></tr>`).join("")}</table></div>` : ""}`;
  activarTooltips();
  document.getElementById("sim")?.addEventListener("submit", async e => {
    e.preventDefault();
    const p = new URLSearchParams(new FormData(e.target));
    try {
      const r = await api("GET", `/api/finanzas/${S.cierre}/simular?${p}`);
      document.getElementById("res").innerHTML = r.estado !== "ok" ? estadoHtml("", r.mensaje || "Sin exposición en la moneda elegida para ese periodo.") :
        `<div class="tarjetas"><div class="tarjeta"><div class="e">Costo base (USD→COP)</div><div class="v" style="font-size:17px">${cop(r.base_cop)}</div></div>
         <div class="tarjeta"><div class="e">Costo simulado ${r.variacion_pct >= 0 ? "+" : ""}${r.variacion_pct} %</div><div class="v" style="font-size:17px">${cop(r.simulado_cop)}</div></div>
         <div class="tarjeta"><div class="e">Diferencia</div><div class="v" style="font-size:17px">${cop(r.diferencia_cop)}</div></div>
         ${r.componente_cop_sin_cambio != null ? `<div class="tarjeta"><div class="e">Componente COP (sin cambio)</div><div class="v" style="font-size:17px">${cop(r.componente_cop_sin_cambio)}</div></div>` : ""}</div>
         <table><tr><th>Familia</th><th>Proveedor</th><th class="n">Base</th><th class="n">Escenario</th><th class="n">Diferencia</th></tr>${r.detalle.map(d => `<tr><td>${esc(d.familia)}</td><td>${esc(d.proveedor_id)}</td><td class="n">${cop(d.costo_base_cop)}</td><td class="n">${cop(d.costo_escenario_cop)}</td><td class="n">${cop(d.diferencia_cop)}</td></tr>`).join("")}</table>
         <p class="muted">Indicador: ${esc(r.indicador)}. Supuestos: ${esc(r.supuestos.join("; "))}.</p>`;
    } catch (err) { document.getElementById("res").innerHTML = errorHtml(err); }
  });
  document.getElementById("gen")?.addEventListener("click", async () => {
    try { const r = await api("POST", "/api/informes", { cierre: S.cierre }); document.getElementById("msg").innerHTML = estadoHtml("ok", r.reutilizado ? `Contenido idéntico a la revisión r${r.revision}; no se creó otra.` : `Informe r${r.revision} generado.`); setTimeout(vistaFinanzas, 600); }
    catch (e) { document.getElementById("msg").innerHTML = errorHtml(e); }
  });
}

// ---------------------------------------------------------------- documentos (B08)
async function vistaDocumentos() {
  const inv = await api("GET", "/api/documentos").catch(e => e);
  if (inv instanceof Error) { $vista.innerHTML = errorHtml(inv); return; }
  $vista.innerHTML = `<h1>Documentos y políticas</h1><div id="msg"></div>
  <div class="tabla"><table><tr><th>ID</th><th>v</th><th>Título</th><th>Tema</th><th>Empresa</th><th>Roles</th><th>Vigencia</th><th>Estado</th><th class="n">Frag.</th><th></th></tr>
  ${inv.map(d => `<tr><td>${esc(d.id)}</td><td>${d.version}</td><td>${esc(d.titulo)}</td><td>${esc(d.tema || "")}</td><td>${esc(d.organizacion_id || "todas")}</td><td>${esc(d.roles.join(", "))}</td><td>${esc(d.vigencia_desde)} – ${esc(d.vigencia_hasta || "…")}</td><td>${esc(d.estado)}</td><td class="n">${d.fragmentos}</td><td>${d.estado === "vigente" ? `<button class="sec" data-r="${esc(d.id)}">Retirar</button>` : ""}</td></tr>`).join("")}</table></div>
  <div class="grid2"><div class="panel"><h2>Importar documento o nueva versión</h2><form id="imp">
    <div class="filtros"><label>ID <input name="id" required></label><label>Título <input name="titulo" required></label><label>Tema <input name="tema"></label>
    <label>Desde <input type="date" name="vigencia_desde" required></label><label>Hasta <input type="date" name="vigencia_hasta"></label><label>Empresa (vacío = todas) <input name="organizacion_id"></label></div>
    <label>Texto (Markdown con secciones «##» o páginas separadas por salto de página) <textarea name="texto" required></textarea></label><button>Importar</button></form></div>
   <div class="panel"><h2>Probar consulta documental</h2><form id="con" class="fila"><input name="p" style="flex:1" placeholder="¿Cuál es el descuento por renovación?"><button>Consultar</button></form><div id="resp"></div></div></div>`;
  const msg = e => { document.getElementById("msg").innerHTML = errorHtml(e); };
  $vista.querySelectorAll("[data-r]").forEach(b => b.addEventListener("click", async () => { try { await api("POST", `/api/documentos/${encodeURIComponent(b.dataset.r)}/retirar`, {}); vistaDocumentos(); } catch (e) { msg(e); } }));
  document.getElementById("imp").addEventListener("submit", async e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target)); const texto = d.texto; delete d.texto;
    for (const k of ["vigencia_hasta", "organizacion_id", "tema"]) if (!d[k]) delete d[k];
    d.propietario = S.usuario.id;
    try { await api("POST", "/api/documentos", { meta: d, texto }); vistaDocumentos(); } catch (err) { msg(err); }
  });
  document.getElementById("con").addEventListener("submit", async e => {
    e.preventDefault();
    try {
      const r = await api("POST", "/api/documentos/consultar", { pregunta: new FormData(e.target).get("p") });
      document.getElementById("resp").innerHTML = `<div class="burbuja">${esc(r.texto)}<div class="muted">${esc(r.estado)} · ${r.fuentes.map(f => `${esc(f.titulo)} v${f.version} (${esc(f.localizador)})`).join("; ")}</div></div>`;
    } catch (err) { msg(err); }
  });
}

// ---------------------------------------------------------------- operación (B02.4/B11)
async function vistaOperacion() {
  const [op, lotes, cierres] = await Promise.all([api("GET", "/api/operacion"), api("GET", "/api/cargas"), api("GET", "/api/cierres")]).catch(e => [e]);
  if (op instanceof Error) { $vista.innerHTML = errorHtml(op); return; }
  $vista.innerHTML = `<h1>Operación del cierre</h1><div id="msg"></div>
  <div class="tarjetas"><div class="tarjeta"><div class="e">Cierre activo</div><div class="v" style="font-size:16px">${esc(op.cierre_activo || "ninguno")}</div><div class="e">publicado ${esc((op.publicado_en || "").slice(0, 16))}</div></div>
   <div class="tarjeta"><div class="e">Frescura</div><div class="v">${op.frescura_dias ?? "—"} d</div><div class="e">desde el corte</div></div>
   <div class="tarjeta"><div class="e">Filas aisladas en cargas</div><div class="v">${op.filas_aisladas_en_cargas}</div></div>
   <div class="tarjeta"><div class="e">Versión</div><div class="v" style="font-size:16px">app ${esc(op.version_app)}</div><div class="e">${esc(JSON.stringify(op.versiones || {}))}</div></div></div>
  <div class="grid2"><div class="panel"><h2>Cargar CSV / Excel</h2><form id="carga">
    <div class="filtros"><label>Periodo <input name="periodo" placeholder="2026-10" required pattern="\\d{4}-\\d{2}"></label>
    <label>Tabla <select name="tabla">${["ventas", "compras", "clientes", "productos", "base_instalada", "trm", "proveedores"].map(t => `<option>${t}</option>`).join("")}</select></label>
    <label>Hoja (Excel) <input name="hoja" placeholder="primera"></label></div>
    <label>Mapeo de columnas (JSON origen→destino, opcional) <input name="mapeo" placeholder='{"Fecha venta":"fecha"}'></label>
    <label>Archivo <input type="file" name="archivo" accept=".csv,.xlsx" required></label><button>Previsualizar</button></form><div id="prev"></div></div>
   <div class="panel"><h2>Publicar y ejecutar cierre</h2><form id="pub" class="fila"><input name="ruta" style="flex:1" value="contratos/ejemplos/publicacion/demo-2026-10"><button>Publicar directorio C2 / agenda</button></form>
    <form id="eje" class="filtros" style="margin-top:8px"><label>Corte <input name="corte" value="2026-10-31"></label><label>Insumos <input name="datos" value="../Green_Services_Recursos_de_Prueba"></label><button>Ejecutar cierre mensual</button></form>
    <h3>Cierres</h3>${cierres.map(c => `<div class="muted">${esc(c.id)} · ${esc(c.estado)}${c.activo ? " · activo" : ""} · ${esc(c.publicado_por || "")}</div>`).join("")}
    <h3>Ejecuciones</h3>${op.ejecuciones.map(e => `<div class="muted">${esc(e.id)} · <strong>${esc(e.estado)}</strong> · intentos ${e.intentos} · ${(e.etapas || []).map(s => `${esc(s.etapa)} ${s.segundos}s ${esc(s.estado)}`).join(", ")}${e.detalle?.error ? ` · ${esc(e.detalle.error.mensaje).slice(0, 160)}` : ""}</div>`).join("") || '<p class="muted">Sin ejecuciones.</p>'}</div></div>
  <div class="grid2"><div class="panel"><h2>Banderas (desactivación independiente)</h2>${Object.entries(op.banderas).map(([k, b]) => `<label class="fila" style="display:flex"><input type="checkbox" data-f="${esc(k)}" ${b.activo ? "checked" : ""}> ${esc(b.descripcion)}</label>`).join("")}
    <p class="muted">Desactivar el asistente o el modelo conserva tareas y PQRS.</p></div>
   <div class="panel"><h2>Respaldo</h2><button id="resp">Crear respaldo</button><div id="rresp"></div><p class="muted">Restaurar en entorno aislado: <code>python -m api restaurar RESPALDO --destino var/ensayo.sqlite3</code></p></div></div>
  <div class="panel"><h2>Lotes</h2>${lotes.map(l => `<div class="muted">#${l.id} · ${esc(l.origen)} · ${esc(l.tabla)} ${esc(l.periodo || "")} · ${esc(l.estado)} · aceptadas ${l.resumen.aceptadas} · duplicadas ${l.resumen.duplicadas} · aisladas ${l.resumen.aisladas}</div>`).join("") || '<p class="muted">Sin lotes.</p>'}</div>`;
  const msg = (e, ok) => { document.getElementById("msg").innerHTML = ok ? estadoHtml("ok", ok) : errorHtml(e); };
  document.getElementById("carga").addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(e.target), archivo = fd.get("archivo");
    const buf = new Uint8Array(await archivo.arrayBuffer());
    let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    let mapeo = null;
    try { mapeo = fd.get("mapeo") ? JSON.parse(fd.get("mapeo")) : null; } catch { return msg(new Error("El mapeo no es JSON válido")); }
    try {
      const r = await api("POST", "/api/cargas", { nombre: archivo.name, contenido_b64: btoa(bin), tabla: fd.get("tabla"), periodo: fd.get("periodo"), hoja: fd.get("hoja") || null, mapeo });
      document.getElementById("prev").innerHTML = `<div class="estado ${r.bloqueante ? "error" : "ok"}">Leídas ${r.leidas} · aceptadas ${r.aceptadas} · duplicadas ${r.duplicadas} · aisladas ${r.aisladas}${r.reutilizado ? " · lote reutilizado (reenvío idéntico)" : ""}${r.hojas?.length ? ` · hojas: ${esc(r.hojas.join(", "))}` : ""}</div>
      <p class="muted">${esc(r.validador || "")}${r.aviso_integracion ? ` · ${esc(r.aviso_integracion)}` : ""}</p>
      ${r.incidencias.length ? `<div class="tabla"><table><tr><th>Fila</th><th>Campo</th><th>Motivo</th><th>Acción</th></tr>${r.incidencias.slice(0, 200).map(i => `<tr><td>${i.fila ?? ""}</td><td>${esc(i.campo || "")}</td><td>${esc(i.motivo)}</td><td>${esc(i.accion)}</td></tr>`).join("")}</table></div>` : ""}
      ${r.bloqueante ? "<p>Corrige el archivo y vuelve a cargarlo.</p>" : `<button id="conf">Confirmar lote #${r.lote_id}</button>`}`;
      document.getElementById("conf")?.addEventListener("click", async () => { try { const c = await api("POST", `/api/cargas/${r.lote_id}/confirmar`, {}); msg(null, `Lote confirmado en ${c.directorio_lote}. ${c.siguiente_paso || ""}`); } catch (er) { msg(er); } });
    } catch (err) { document.getElementById("prev").innerHTML = errorHtml(err); }
  });
  document.getElementById("pub").addEventListener("submit", async e => {
    e.preventDefault();
    try { const r = await api("POST", "/api/cierres/publicar", { ruta: new FormData(e.target).get("ruta") }); S.estadoApi = await api("GET", "/api/estado"); msg(null, r.ya_publicado ? `Sin cambios: ya publicado como ${r.cierre_id}.` : `Publicado ${r.cierre_id}.`); setTimeout(vistaOperacion, 800); }
    catch (err) { msg(err); }
  });
  document.getElementById("eje").addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(e.target);
    msg(null, "Ejecutando cierre…");
    try { const r = await api("POST", "/api/cierres/ejecutar", { corte: fd.get("corte"), datos: fd.get("datos"), reintentos: 0 }); r.estado === "publicado" ? msg(null, `Cierre publicado (${r.resultado.cierre_id}).`) : msg(new Error(`Cierre ${r.estado}: ${r.error?.mensaje || ""}. Se conserva ${r.ultimo_cierre_valido || "el cierre anterior"}.`)); setTimeout(vistaOperacion, 1500); }
    catch (err) { msg(err); }
  });
  $vista.querySelectorAll("[data-f]").forEach(c => c.addEventListener("change", async () => { try { await api("POST", "/api/operacion/banderas", { nombre: c.dataset.f, activo: c.checked }); } catch (e) { msg(e); } }));
  document.getElementById("resp").addEventListener("click", async () => { try { const r = await api("POST", "/api/operacion/respaldo", {}); document.getElementById("rresp").innerHTML = estadoHtml("ok", `Respaldo ${r.archivo}`); } catch (e) { msg(e); } });
}

// ---------------------------------------------------------------- enrutado
async function render() {
  pintarCabecera();
  const { partes, q } = ruta();
  const [v, a] = partes;
  try {
    if (v === "inicio" || !S.fuente) return await vistaInicio();
    if (!enServidor() && v !== "agenda" && v !== "clientes") return ir("#/agenda");
    if (enServidor() && !S.usuario) return await vistaInicio();
    switch (v) {
      case "clientes": return await vistaFicha(a, q);
      case "tableros": return await vistaTableros(a);
      case "tareas": return await vistaTareas(a);
      case "pqrs": return await vistaPqrs(a);
      case "beneficios": return await vistaBeneficios();
      case "asistente": return vistaAsistente();
      case "finanzas": return await vistaFinanzas();
      case "documentos": return await vistaDocumentos();
      case "operacion": return await vistaOperacion();
      default: return await vistaAgenda();
    }
  } catch (e) {
    if (e.status === 401) { S.usuario = null; return ir("#/inicio"); }
    $vista.innerHTML = errorHtml(e);
  }
}

async function iniciar() {
  try {
    const r = await fetch("/api/estado", { cache: "no-store" });
    if (r.ok) { S.estadoApi = await r.json(); S.apiDisponible = true; }
  } catch { /* modo estático */ }
  if (S.apiDisponible) S.usuario = (await api("GET", "/api/sesion").catch(() => null))?.usuario || null;
  if (!S.apiDisponible && S.fuente === "servidor") S.fuente = null;
  window.addEventListener("hashchange", render);
  render();
}
iniciar();
