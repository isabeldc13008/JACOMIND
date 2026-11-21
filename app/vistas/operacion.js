// Operación del cierre: estado publicado, carga y validación, ejecución, actividad y administración (entrada 22).
import { $vista, S, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, num, plural, ruta } from "../nucleo.js";
import { barras, detalleTecnico } from "../ui.js";

const SECCIONES = [["cargar", "Cargar y validar"], ["ejecutar", "Ejecutar y publicar"], ["actividad", "Revisar actividad"], ["administrar", "Administrar y respaldar"]];
const TABLAS = { ventas: "Ventas", compras: "Compras a proveedores", clientes: "Clientes", productos: "Productos", base_instalada: "Coberturas instaladas", trm: "Tipo de cambio (TRM)", proveedores: "Proveedores" };
const NOMBRE_BANDERA = { modelo_compra: "Mostrar la estimación de compra a 30 días en agenda y fichas", asistente: "Ofrecer el asistente (equipo interno y portal de empresas)" };
const ESTADO_LOTE = { previsualizado: "Validado, pendiente de confirmar", confirmado: "Confirmado para el próximo cierre", rechazado: "Rechazado", fallido: "Falló" };
const ETAPAS = { generar: "Generar la publicación con los insumos", validar_y_publicar: "Validar el contrato y publicar" };
const CORRECCION = {
  "aislar fila": "Corrige el valor en el archivo y vuelve a cargarlo; mientras tanto la fila no se incorpora.",
  "descartar duplicado": "No hace falta corregir: la copia idéntica se descarta.",
  "corregir mapeo": "Asigna la columna correspondiente en el mapeo de columnas.",
  "rechazar lote": "Revisa que el archivo y la hoja contengan filas.",
};

let cargaEnCurso = null;
const columnasEsperadas = (op, tabla) => (op.tablas_carga?.[tabla] || []).length ? `Columnas que debe tener: ${op.tablas_carga[tabla].join(", ")}. Si se llaman distinto, podrás asignarlas después de validar.` : "";   // archivo y opciones de la última validación, para revalidar con otro mapeo u hoja

export async function vistaOperacion() {
  const sec = SECCIONES.some(([k]) => k === ruta().q.get("seccion")) ? ruta().q.get("seccion") : "cargar";
  const [op, lotes, cierres] = await Promise.all([api("GET", "/api/operacion"), api("GET", "/api/cargas"), api("GET", "/api/cierres")]).catch(e => [e]);
  if (op instanceof Error) { $vista.innerHTML = errorHtml(op); return; }
  const ultimaEjec = op.ejecuciones[0];
  const ultimaOk = op.ejecuciones.find(e => e.estado === "publicado");
  const pendientesConfirmar = lotes.filter(l => l.estado === "previsualizado" && !l.resumen?.bloqueante);
  const sinIncorporar = lotes.filter(l => l.estado === "confirmado" && (!ultimaOk || l.cargado_en > ultimaOk.inicio));
  const atencion = [
    ultimaEjec?.estado === "fallido" && `El último cierre (${esc(fechaHora(ultimaEjec.inicio))}) falló: ${esc(ultimaEjec.detalle?.error?.mensaje || "ver actividad").slice(0, 160)}. Los usuarios siguen viendo ${esc(op.cierre_activo || "el cierre anterior")}.`,
    pendientesConfirmar.length && `${plural(pendientesConfirmar.length, "lote validado espera", "lotes validados esperan")} confirmación.`,
    sinIncorporar.length && `${plural(sinIncorporar.length, "lote confirmado aún no se incorpora", "lotes confirmados aún no se incorporan")}: falta ejecutar el cierre mensual para que los usuarios lo vean.`,
    op.frescura_dias != null && op.frescura_dias > 45 && `Los datos publicados tienen ${op.frescura_dias} días: revisa si corresponde un cierre nuevo.`,
  ].filter(Boolean);
  $vista.innerHTML = `<h1>Operación del cierre</h1><div id="msg"></div>
  <div class="tres-preguntas">
    <section class="panel"><h2>Qué cierre está publicado</h2><p class="grande">${op.cierre_activo ? esc(op.cierre_activo) : "Ninguno"}</p><p class="muted">${op.publicado_en ? `Publicado ${esc(fechaHora(op.publicado_en))}` : "Aún no se ha publicado un cierre."}</p></section>
    <section class="panel"><h2>Hasta qué fecha llegan los datos</h2><p class="grande">${op.corte ? esc(fechaLarga(op.corte)) : "—"}</p><p class="muted">${op.frescura_dias != null ? `Han pasado ${plural(op.frescura_dias, "día", "días")} desde esa fecha.` : ""}</p></section>
    <section class="panel"><h2>Qué requiere atención</h2>${atencion.length ? `<ul>${atencion.map(a => `<li>${a}</li>`).join("")}</ul>` : '<p class="estado ok">Nada pendiente.</p>'}</section>
  </div>
  <nav class="pestanas" aria-label="Recorridos de operación">${SECCIONES.map(([k, t]) => `<a href="#/operacion?seccion=${k}" ${k === sec ? 'aria-current="page"' : ""}>${t}</a>`).join("")}</nav>
  ${sec === "cargar" ? seccionCargar(op) : sec === "ejecutar" ? seccionEjecutar(op, cierres) : sec === "actividad" ? seccionActividad(op, lotes) : seccionAdministrar(op)}`;
  enlazar(op);
}

// ---------------------------------------------------------------- cargar y validar
function seccionCargar(op) {
  return `<section class="panel"><h2>Cargar y validar un archivo</h2>
  <p class="muted">Validar no cambia lo que ven los usuarios. Al confirmar, el lote queda guardado para el próximo cierre mensual.</p>
  <form id="carga"><div class="filtros"><label>Mes de los datos <input name="periodo" placeholder="2026-10" required pattern="\\d{4}-\\d{2}" value="${esc(cargaEnCurso?.periodo || "")}"></label>
    <label>Tipo de datos <select name="tabla">${Object.entries(TABLAS).map(([k, t]) => `<option value="${k}" ${cargaEnCurso?.tabla === k ? "selected" : ""}>${t}</option>`).join("")}</select></label>
    <label>Archivo CSV o Excel <input type="file" name="archivo" accept=".csv,.xlsx" ${cargaEnCurso ? "" : "required"}></label></div>
    ${cargaEnCurso ? `<p class="muted">Archivo actual: ${esc(cargaEnCurso.archivo.name)} (elige otro para reemplazarlo).</p>` : ""}
    <p class="muted" id="esperadas">${esc(columnasEsperadas(op, cargaEnCurso?.tabla || "ventas"))}</p>
    <button>Validar archivo</button></form><div id="prev"></div></section>`;
}

function resultadoCarga(r, op) {
  const suma = r.aceptadas + r.duplicadas + r.aisladas;
  const concilia = suma === r.leidas;
  const esperadas = r.columnas_esperadas || op.tablas_carga?.[cargaEnCurso.tabla] || [];
  const enc = r.encabezados || [];
  const mapeo = cargaEnCurso.mapeo || {};
  const inverso = Object.fromEntries(Object.entries(mapeo).map(([o, d]) => [d, o]));
  const faltan = r.incidencias.some(i => i.accion === "corregir mapeo");
  return `<h3>${r.bloqueante ? "El archivo no se puede usar todavía" : `Resultado de la validación${r.reutilizado ? " (mismo archivo ya validado)" : ""}`}</h3>
  ${concilia && r.leidas ? barras([{ etiqueta: "Aceptadas", valor: r.aceptadas, texto: plural(r.aceptadas, "fila", "filas") }, { etiqueta: "Duplicadas (se descartan)", valor: r.duplicadas, texto: plural(r.duplicadas, "fila", "filas") }, { etiqueta: "Aisladas (no se incorporan)", valor: r.aisladas, texto: plural(r.aisladas, "fila", "filas") }], { etiquetaAria: `Filas leídas: ${r.leidas}` })
    : `<p>Filas leídas ${num(r.leidas)} · aceptadas ${num(r.aceptadas)} · duplicadas ${num(r.duplicadas)} · aisladas ${num(r.aisladas)}${r.leidas && !concilia ? " (los conteos no concilian; revisa el detalle técnico)" : ""}</p>`}
  ${r.hojas?.length ? `<label>Hoja del libro <select id="hoja">${r.hojas.map(h => `<option ${h === cargaEnCurso.hoja ? "selected" : ""}>${esc(h)}</option>`).join("")}</select></label>` : ""}
  ${enc.length && esperadas.length ? `<details class="ver-datos" ${faltan ? "open" : ""}><summary>Columnas del archivo</summary>
    <p class="muted">Indica qué columna del archivo corresponde a cada dato esperado. Si los nombres coinciden, no hace falta cambiar nada.</p>
    <div class="mapeo">${esperadas.map(c => { const actual = inverso[c] || (enc.includes(c) ? c : ""); return `<label>${esc(c)} <select data-destino="${esc(c)}"><option value="">— sin asignar —</option>${enc.map(h => `<option ${h === actual ? "selected" : ""}>${esc(h)}</option>`).join("")}</select></label>`; }).join("")}</div></details>` : ""}
  ${(r.hojas?.length || (enc.length && esperadas.length)) ? '<button type="button" class="sec" id="revalidar">Validar de nuevo con esta hoja y estas columnas</button>' : ""}
  ${r.incidencias.length ? `<div class="tabla"><table><tr><th>Fila</th><th>Campo</th><th>Causa</th><th>Cómo corregirlo</th></tr>${r.incidencias.slice(0, 200).map(i => `<tr><td>${i.fila ?? "—"}</td><td>${esc(i.campo || "—")}</td><td>${esc(i.motivo)}</td><td>${esc(CORRECCION[i.accion] || i.accion)}</td></tr>`).join("")}</table></div>${r.incidencias.length > 200 ? `<p class="muted">Se muestran 200 de ${r.incidencias.length} incidencias.</p>` : ""}` : '<p class="estado ok">Sin incidencias.</p>'}
  ${r.bloqueante ? "<p>Corrige el archivo o el mapeo y vuelve a validarlo.</p>" : `<div class="fila"><button id="conf">Confirmar lote ${r.lote_id}</button><span class="muted">Guarda el lote para el próximo cierre. Los usuarios lo verán cuando ejecutes y publiques ese cierre.</span></div>`}
  ${detalleTecnico(`<p class="muted">${esc(r.validador || "")}${r.aviso_integracion ? ` · ${esc(r.aviso_integracion)}` : ""} · lote ${r.lote_id} · estado ${esc(r.estado)}</p>`)}`;
}

async function validar(op) {
  const c = cargaEnCurso;
  const buf = new Uint8Array(await c.archivo.arrayBuffer());
  let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  const prev = document.getElementById("prev");
  prev.innerHTML = estadoHtml("", "Validando…");
  try {
    const r = await api("POST", "/api/cargas", { nombre: c.archivo.name, contenido_b64: btoa(bin), tabla: c.tabla, periodo: c.periodo, hoja: c.hoja || null, mapeo: c.mapeo && Object.keys(c.mapeo).length ? c.mapeo : null });
    prev.innerHTML = resultadoCarga(r, op);
    document.getElementById("revalidar")?.addEventListener("click", () => {
      const mapeo = {};
      prev.querySelectorAll("[data-destino]").forEach(s => { if (s.value && s.value !== s.dataset.destino) mapeo[s.value] = s.dataset.destino; });
      cargaEnCurso = { ...c, mapeo, hoja: document.getElementById("hoja")?.value || c.hoja };
      validar(op);
    });
    document.getElementById("conf")?.addEventListener("click", async () => {
      try {
        const k = await api("POST", `/api/cargas/${r.lote_id}/confirmar`, {});
        cargaEnCurso = null;
        prev.innerHTML = estadoHtml("ok", `Lote ${k.lote_id} confirmado y guardado en ${k.directorio_lote || "el directorio de lotes"}. Falta ejecutar el cierre mensual para que los usuarios lo vean.`)
          + '<p><a href="#/operacion?seccion=ejecutar">Ir a «Ejecutar y publicar»</a></p>';
      } catch (er) { prev.insertAdjacentHTML("afterbegin", errorHtml(er)); }
    });
  } catch (err) { prev.innerHTML = errorHtml(err); }
}

// ---------------------------------------------------------------- ejecutar y publicar
function etapasHtml(etapas) {
  return etapas?.length ? `<ol class="etapas">${etapas.map(s => `<li class="${s.estado === "ok" ? "ok" : "fallo"}"><strong>${esc(ETAPAS[s.etapa] || s.etapa)}</strong> · ${s.estado === "ok" ? "correcto" : "falló"} · ${num(s.segundos)} s${s.error ? `<div class="muted">${esc(String(s.error).slice(0, 300))}</div>` : ""}</li>`).join("")}</ol>` : "";
}

function seccionEjecutar(op, cierres) {
  return `<div class="grid3">
  <section class="panel"><h2>1 · Confirmar un lote</h2><p>Se hace en «Cargar y validar», archivo por archivo. Confirmar guarda los datos para el próximo cierre, pero no cambia lo que ven los usuarios.</p><a href="#/operacion?seccion=cargar">Ir a cargar y validar</a></section>
  <section class="panel"><h2>2 · Ejecutar el cierre mensual</h2><p>Genera la publicación con los insumos hasta la fecha indicada, la valida y, si todo es correcto, la publica. Si falla, los usuarios siguen viendo el último cierre válido.</p>
    <form id="eje" class="filtros"><label>Datos hasta <input type="date" name="corte" value="${esc(op.corte || "2026-10-31")}"></label><label>Carpeta de insumos <input name="datos" value="../Green_Services_Recursos_de_Prueba"></label><button>Ejecutar cierre mensual</button></form><div id="res-eje"></div></section>
  <section class="panel"><h2>3 · Publicar una salida preparada</h2><p>Publica una carpeta que ya contiene una publicación generada (por ejemplo, la demostración). No vuelve a calcular nada; solo la valida y la publica.</p>
    <form id="pub" class="fila"><label style="flex:1">Carpeta <input name="ruta" value="contratos/ejemplos/publicacion/demo-2026-10"></label><button class="sec">Publicar esta salida</button></form></section></div>
  <section class="panel"><h2>Cierres disponibles</h2><div class="tabla"><table><tr><th>Cierre</th><th>Datos hasta</th><th>Estado</th><th>Publicado por</th></tr>${cierres.map(c => `<tr><td>${esc(c.id)}${c.activo ? ' <span class="chip fuerte">lo ven los usuarios</span>' : ""}</td><td>${esc(fechaLarga(c.corte))}</td><td>${esc(c.estado)}</td><td>${esc(c.publicado_por || "—")}</td></tr>`).join("") || '<tr><td colspan=4 class="muted">Sin cierres.</td></tr>'}</table></div></section>`;
}

// ---------------------------------------------------------------- actividad
function seccionActividad(op, lotes) {
  const actividad = [
    ...op.ejecuciones.map(e => ({ fecha: e.inicio, atencion: e.estado === "fallido", html: `<strong>Cierre ${esc(e.corte ? `hasta el ${fechaLarga(e.corte)}` : "")}</strong> · ${e.estado === "publicado" ? "publicado" : e.estado === "fallido" ? "falló" : esc(e.estado)} · ${plural(e.intentos, "intento", "intentos")}${etapasHtml(e.etapas)}
      ${detalleTecnico(`<p class="muted">Ejecución ${esc(e.id)} · inicio ${esc(e.inicio)} · fin ${esc(e.fin || "—")} · salida <code>${esc(e.detalle?.salida || "—")}</code></p>${e.detalle?.error ? `<pre>${esc(JSON.stringify(e.detalle.error, null, 2))}</pre>` : ""}`, "Ficha técnica")}` })),
    ...lotes.map(l => ({ fecha: l.cargado_en, atencion: l.estado === "previsualizado" || l.resumen?.bloqueante, html: `<strong>${esc(TABLAS[l.tabla] || l.tabla)} · ${esc(l.periodo || "sin mes")}</strong> · ${esc(ESTADO_LOTE[l.estado] || l.estado)}${l.resumen?.bloqueante ? " · bloqueado por errores" : ""} · aceptadas ${num(l.resumen?.aceptadas)}, duplicadas ${num(l.resumen?.duplicadas)}, aisladas ${num(l.resumen?.aisladas)}
      ${detalleTecnico(`<p class="muted">Lote ${l.id} · archivo ${esc(l.origen)} · cargado por ${esc(l.cargado_por || "—")} · ruta <code>${esc(l.resumen?.archivo || "—")}</code>${l.resumen?.mapeo ? ` · mapeo <code>${esc(JSON.stringify(l.resumen.mapeo))}</code>` : ""}</p>`, "Ficha técnica")}` })),
  ].sort((a, b) => (b.atencion - a.atencion) || b.fecha.localeCompare(a.fecha));
  return `<section class="panel"><h2>Actividad reciente</h2><p class="muted">Primero lo que requiere atención; después, de lo más reciente a lo más antiguo.</p>
    ${actividad.length ? `<ul class="actividad">${actividad.map(a => `<li class="${a.atencion ? "requiere" : ""}"><div class="crono-fecha">${esc(fechaHora(a.fecha))}</div><div>${a.atencion ? '<span class="chip">Requiere atención</span> ' : ""}${a.html}</div></li>`).join("")}</ul>` : '<p class="muted">Sin actividad.</p>'}</section>`;
}

// ---------------------------------------------------------------- administrar y respaldar
function seccionAdministrar(op) {
  return `<div class="grid2"><section class="panel"><h2>Funciones de la aplicación</h2>
    ${Object.entries(op.banderas).map(([k, b]) => `<div class="bandera"><label class="en-linea"><input type="checkbox" data-f="${esc(k)}" ${b.activo ? "checked" : ""}> <strong>${esc(NOMBRE_BANDERA[k] || b.descripcion)}</strong></label><p class="muted">${esc(b.efecto || b.descripcion)}</p></div>`).join("")}</section>
   <section class="panel"><h2>Respaldo</h2><p>Copia completa de la base (cierres, tareas, solicitudes, documentos) con su manifiesto.</p><button id="resp">Crear respaldo ahora</button><div id="rresp"></div>
    ${detalleTecnico(`<p class="muted">Restaurar en un entorno aislado: <code>python -m api restaurar RESPALDO --destino var/ensayo.sqlite3</code></p>`, "Cómo restaurar")}</section></div>
  ${detalleTecnico(`<p class="muted">Aplicación ${esc(op.version_app)} · ${esc(Object.entries(op.versiones || {}).map(([k, v]) => `${k} ${v}`).join(" · "))}</p>`, "Versiones")}`;
}

// ---------------------------------------------------------------- eventos
function enlazar(op) {
  const msg = (e, ok) => { document.getElementById("msg").innerHTML = ok ? estadoHtml("ok", ok) : errorHtml(e); window.scrollTo(0, 0); };
  document.querySelector("#carga [name=tabla]")?.addEventListener("change", e => { document.getElementById("esperadas").textContent = columnasEsperadas(op, e.target.value); });
  document.getElementById("carga")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target), archivo = fd.get("archivo");
    const nuevo = archivo && archivo.size ? archivo : cargaEnCurso?.archivo;
    if (!nuevo) return msg(new Error("Elige un archivo CSV o Excel."));
    cargaEnCurso = { archivo: nuevo, tabla: fd.get("tabla"), periodo: fd.get("periodo"), hoja: nuevo === cargaEnCurso?.archivo ? cargaEnCurso.hoja : null, mapeo: nuevo === cargaEnCurso?.archivo ? cargaEnCurso.mapeo : null };
    validar(op);
  });
  document.getElementById("pub")?.addEventListener("submit", async e => {
    e.preventDefault();
    try { const r = await api("POST", "/api/cierres/publicar", { ruta: new FormData(e.target).get("ruta") }); S.estadoApi = await api("GET", "/api/estado"); await vistaOperacion(); msg(null, r.ya_publicado ? `Sin cambios: esa salida ya estaba publicada como ${r.cierre_id}.` : `Publicado ${r.cierre_id}. Es el cierre que ven ahora los usuarios.`); }
    catch (err) { msg(err); }
  });
  document.getElementById("eje")?.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(e.target), res = document.getElementById("res-eje");
    res.innerHTML = estadoHtml("", "Ejecutando el cierre… puede tardar varios minutos.");
    try {
      const r = await api("POST", "/api/cierres/ejecutar", { corte: fd.get("corte"), datos: fd.get("datos"), reintentos: 0 });
      S.estadoApi = await api("GET", "/api/estado").catch(() => S.estadoApi);
      res.innerHTML = (r.estado === "publicado" ? estadoHtml("ok", `Cierre publicado (${r.resultado.cierre_id}). Es el que ven ahora los usuarios.`)
        : estadoHtml("error", `El cierre falló: ${r.error?.mensaje || "error desconocido"}. Los usuarios siguen viendo ${r.ultimo_cierre_valido || "el cierre anterior"}.`)) + etapasHtml(r.etapas);
    } catch (err) { res.innerHTML = errorHtml(err); }
  });
  $vista.querySelectorAll("[data-f]").forEach(c => c.addEventListener("change", async () => {
    try { await api("POST", "/api/operacion/banderas", { nombre: c.dataset.f, activo: c.checked }); msg(null, `${NOMBRE_BANDERA[c.dataset.f] || c.dataset.f}: ${c.checked ? "activado" : "desactivado"}.`); } catch (e) { msg(e); c.checked = !c.checked; }
  }));
  document.getElementById("resp")?.addEventListener("click", async () => {
    try { const r = await api("POST", "/api/operacion/respaldo", {}); document.getElementById("rresp").innerHTML = estadoHtml("ok", `Respaldo creado el ${fechaHora(r.creado_en)} en ${r.archivo}.`); } catch (e) { msg(e); }
  });
}
