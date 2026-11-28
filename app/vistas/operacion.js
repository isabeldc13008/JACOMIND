// V28 Cargar y validar, V29 Ejecutar y publicar, V30 Actividad y V31 Configuración y respaldos.
// Confirmar un lote no es publicar: los usuarios solo ven los datos nuevos cuando se ejecuta y publica el cierre.
import { $vista, S, api, clave, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, num, plural, ruta } from "../nucleo.js";
import { barras, confirmar, detalleTecnico, encabezado, filtrosActivos, pestanas, tablaHtml, vacio } from "../ui.js";

const TITULOS = { cargar: "Datos y cierres", ejecutar: "Datos y cierres", actividad: "Actividad", administrar: "Configuración y respaldos" };
const TABLAS = { ventas: "Ventas", compras: "Compras a proveedores", clientes: "Clientes", productos: "Productos", base_instalada: "Coberturas instaladas", trm: "Tipo de cambio (TRM)", proveedores: "Proveedores" };
const NOMBRE_BANDERA = { modelo_compra: "Mostrar la posibilidad estimada de compra a 30 días en la cartera y las fichas", asistente: "Ofrecer el asistente (equipo interno y portal de empresas)" };
const ESTADO_LOTE = { previsualizado: "Validado, falta confirmar", confirmado: "Confirmado para el próximo cierre", rechazado: "Rechazado", fallido: "Falló" };
const ETAPAS = { generar: "Preparar la publicación con los archivos", validar_y_publicar: "Comprobar y publicar" };
const CORRECCION = {
  "aislar fila": "Corrige el valor en el archivo y vuelve a cargarlo; mientras tanto la fila no se incorpora.",
  "descartar duplicado": "No hace falta corregir: la copia idéntica se descarta.",
  "corregir mapeo": "Indica qué columna del archivo corresponde a ese dato (más abajo).",
  "rechazar lote": "Revisa que el archivo y la hoja tengan filas.",
};

let cargaEnCurso = null;   // archivo y opciones de la última validación, para revalidar con otro mapeo u hoja
const columnasEsperadas = (op, tabla) => (op.tablas_carga?.[tabla] || []).length ? `Columnas que debe tener: ${op.tablas_carga[tabla].join(", ")}. Si se llaman distinto, podrás indicarlo después de validar.` : "";

export async function vistaOperacion() {
  const { q } = ruta();
  const sec = TITULOS[q.get("seccion")] ? q.get("seccion") : "cargar";
  const titulo = TITULOS[sec];
  if (!$vista.querySelector(`[data-op="${sec}"]`)) $vista.innerHTML = `${encabezado({ titulo })}${estadoHtml("", "Cargando…")}`;
  const [op, lotes, cierres] = await Promise.all([api("GET", "/api/operacion"), api("GET", "/api/cargas"), api("GET", "/api/cierres")]).catch(e => [e]);
  if (op instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(op, { reintentar: true })}`; return; }
  const ultimaEjec = op.ejecuciones[0];
  const ultimaOk = op.ejecuciones.find(e => e.estado === "publicado");
  const pendientesConfirmar = lotes.filter(l => l.estado === "previsualizado" && !l.resumen?.bloqueante);
  const sinIncorporar = lotes.filter(l => l.estado === "confirmado" && (!ultimaOk || l.cargado_en > ultimaOk.inicio));
  const atencion = [
    ultimaEjec?.estado === "fallido" && `El último cierre (${esc(fechaHora(ultimaEjec.inicio))}) falló: ${esc(ultimaEjec.detalle?.error?.mensaje || "ver actividad").slice(0, 160)}. Los usuarios siguen viendo ${esc(op.cierre_activo || "el cierre anterior")}.`,
    pendientesConfirmar.length && `${plural(pendientesConfirmar.length, "archivo validado espera", "archivos validados esperan")} confirmación.`,
    sinIncorporar.length && `${plural(sinIncorporar.length, "archivo confirmado aún no se ve", "archivos confirmados aún no se ven")}: falta ejecutar el cierre del mes.`,
    op.frescura_dias != null && op.frescura_dias > 45 && `Los datos publicados tienen ${op.frescura_dias} días: revisa si corresponde un cierre nuevo.`,
  ].filter(Boolean);
  const descripcion = { cargar: "Prepara la información del mes: carga los archivos, revisa su calidad y publica el cierre que verán los usuarios.", ejecutar: "Prepara la información del mes: carga los archivos, revisa su calidad y publica el cierre que verán los usuarios.",
    actividad: "Qué cargas y cierres se hicieron, quién los hizo y si fallaron. No incluye el trabajo comercial con clientes.", administrar: "Funciones que se pueden activar o desactivar y copias de seguridad de la base. Cada cambio queda registrado." }[sec];
  $vista.innerHTML = `<div data-op="${sec}">${encabezado({ titulo, descripcion, contexto: [{ etiqueta: "Los usuarios ven", valor: op.cierre_activo ? `el cierre ${esc(op.cierre_activo)}` : "ningún cierre" }, op.corte ? { etiqueta: "Datos hasta", valor: esc(fechaLarga(op.corte)) } : null, op.publicado_en ? { etiqueta: "Publicado", valor: esc(fechaHora(op.publicado_en)) } : null] })}
  <div id="msg" tabindex="-1"></div>
  ${["cargar", "ejecutar"].includes(sec) ? `<section class="panel"><h2>Qué requiere atención</h2>${atencion.length ? `<ul>${atencion.map(a => `<li>${a}</li>`).join("")}</ul>` : '<p class="estado ok">Nada pendiente.</p>'}</section>
  ${pestanas([["cargar", "1. Cargar y validar archivos", "#/operacion?seccion=cargar"], ["ejecutar", "2. Ejecutar y publicar el cierre", "#/operacion?seccion=ejecutar"]], sec, "Pasos de datos y cierres")}` : ""}
  ${sec === "cargar" ? seccionCargar(op) : sec === "ejecutar" ? seccionEjecutar(op, cierres) : sec === "actividad" ? seccionActividad(op, lotes, q) : seccionAdministrar(op)}</div>`;
  enlazar(op);
}

// ---------------------------------------------------------------- V28 · cargar y validar
/** Mes actual en formato AAAA-MM (tope del calendario: no se cargan meses futuros). */
const mesActual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

function seccionCargar(op) {
  return `<ol class="pasos" aria-label="Pasos de la carga"><li aria-current="step">Elegir el archivo</li><li>Revisar la calidad</li><li>Confirmar el lote</li></ol>
  <section class="panel"><h2>Elegir y validar un archivo</h2>
  <p>Validar no cambia lo que ven los usuarios. Al confirmar, el archivo queda guardado para el próximo cierre.</p>
  <form id="carga" class="campos" novalidate><div id="resumen-errores" tabindex="-1"></div>
    <div class="campos-par">
      <label for="periodo-carga"><span>Mes de los datos</span><span class="ayuda" id="ayuda-periodo">Elige el mes en el calendario.</span>
        <input id="periodo-carga" type="month" name="periodo" required pattern="\d{4}-\d{2}" placeholder="2026-10" max="${mesActual()}" value="${esc(cargaEnCurso?.periodo || "")}" aria-describedby="ayuda-periodo err-periodo"><span class="error-campo" id="err-periodo"></span></label>
      <label for="tabla-carga"><span>Qué datos contiene</span><span class="ayuda" id="ayuda-tabla">El tipo de información del archivo.</span>
        <select id="tabla-carga" name="tabla" aria-describedby="ayuda-tabla">${Object.entries(TABLAS).map(([k, t]) => `<option value="${k}" ${cargaEnCurso?.tabla === k ? "selected" : ""}>${t}</option>`).join("")}</select><span class="error-campo" aria-hidden="true"></span></label>
    </div>
    <label for="archivo-carga">Archivo CSV o Excel <input id="archivo-carga" type="file" name="archivo" accept=".csv,.xlsx" aria-describedby="err-archivo"><span class="error-campo" id="err-archivo"></span></label>
    ${cargaEnCurso ? `<p class="muted">Archivo actual: ${esc(cargaEnCurso.archivo.name)} (elige otro para reemplazarlo).</p>` : ""}
    <p class="muted" id="esperadas">${esc(columnasEsperadas(op, cargaEnCurso?.tabla || "ventas"))}</p>
    <div class="fila"><button>Validar el archivo</button></div></form><div id="prev" aria-live="polite"></div></section>`;
}

function resultadoCarga(r, op) {
  const suma = r.aceptadas + r.duplicadas + r.aisladas;
  const concilia = suma === r.leidas;
  const esperadas = r.columnas_esperadas || op.tablas_carga?.[cargaEnCurso.tabla] || [];
  const enc = r.encabezados || [];
  const mapeo = cargaEnCurso.mapeo || {};
  const inverso = Object.fromEntries(Object.entries(mapeo).map(([o, d]) => [d, o]));
  const faltan = r.incidencias.some(i => i.accion === "corregir mapeo");
  return `<ol class="pasos" aria-label="Pasos de la carga"><li class="hecho">Elegir el archivo</li><li ${r.bloqueante ? 'aria-current="step"' : 'class="hecho"'}>Revisar la calidad</li><li ${r.bloqueante ? "" : 'aria-current="step"'}>Confirmar el lote</li></ol>
  <h3>${r.bloqueante ? "El archivo no se puede usar todavía" : `Resultado de la validación${r.reutilizado ? " (este archivo ya se había validado)" : ""}`}</h3>
  <p><strong>${plural(r.leidas, "fila leída", "filas leídas")}:</strong> ${num(r.aceptadas)} aceptadas, ${num(r.duplicadas)} duplicadas (se descartan) y ${num(r.aisladas)} apartadas (no se incorporan).</p>
  ${concilia && r.leidas ? barras([{ etiqueta: "Aceptadas", valor: r.aceptadas, texto: plural(r.aceptadas, "fila", "filas") }, { etiqueta: "Duplicadas (se descartan)", valor: r.duplicadas, texto: plural(r.duplicadas, "fila", "filas") }, { etiqueta: "Apartadas (no se incorporan)", valor: r.aisladas, texto: plural(r.aisladas, "fila", "filas") }], { etiquetaAria: `Filas leídas: ${r.leidas}` })
    : r.leidas ? '<p class="estado error"><strong>Los conteos no cuadran</strong> con las filas leídas. Revisa el detalle técnico antes de confirmar.</p>' : ""}
  ${r.hojas?.length ? `<label>Hoja del libro <select id="hoja">${r.hojas.map(h => `<option ${h === cargaEnCurso.hoja ? "selected" : ""}>${esc(h)}</option>`).join("")}</select></label>` : ""}
  ${enc.length && esperadas.length ? `<details class="ver-datos" ${faltan ? "open" : ""}><summary>Indicar qué columna corresponde a cada dato</summary>
    <p class="muted">Si los nombres coinciden, no hace falta cambiar nada.</p>
    <div class="mapeo">${esperadas.map(c => { const actual = inverso[c] || (enc.includes(c) ? c : ""); return `<label>${esc(c)} <select data-destino="${esc(c)}"><option value="">Sin asignar</option>${enc.map(h => `<option ${h === actual ? "selected" : ""}>${esc(h)}</option>`).join("")}</select></label>`; }).join("")}</div></details>` : ""}
  ${(r.hojas?.length || (enc.length && esperadas.length)) ? '<p><button type="button" class="sec" id="revalidar">Validar de nuevo con esta hoja y estas columnas</button></p>' : ""}
  ${r.incidencias.length ? `<h3>Problemas encontrados (${num(r.incidencias.length)})</h3>${tablaHtml({ cabeceras: ["Fila", "Dato", "Qué pasa", "Cómo corregirlo"], filas: r.incidencias.slice(0, 200).map(i => [i.fila ?? "—", esc(i.campo || "—"), esc(i.motivo), esc(CORRECCION[i.accion] || i.accion)]) })}${r.incidencias.length > 200 ? `<p class="muted">Se muestran 200 de ${num(r.incidencias.length)} problemas.</p>` : ""}` : '<p class="estado ok"><strong>Sin problemas.</strong></p>'}
  ${r.bloqueante ? "<p><strong>Corrige el archivo o las columnas y vuelve a validarlo.</strong></p>" : `<div class="fila"><button id="conf">Confirmar el lote ${r.lote_id}</button></div><p class="muted">Confirmar guarda el archivo para el próximo cierre. Los usuarios lo verán solo cuando ejecutes y publiques ese cierre.</p>`}
  ${detalleTecnico(`<p class="muted">${esc(r.validador || "")}${r.aviso_integracion ? ` · ${esc(r.aviso_integracion)}` : ""} · lote ${r.lote_id} · estado ${esc(r.estado)}</p>`)}`;
}

async function validar(op) {
  const c = cargaEnCurso;
  const buf = new Uint8Array(await c.archivo.arrayBuffer());
  let bin = ""; for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  const prev = document.getElementById("prev");
  const btn = document.querySelector("#carga button"); if (btn) { btn.disabled = true; btn.textContent = "Validando…"; }
  prev.innerHTML = estadoHtml("", "Validando el archivo…");
  try {
    const r = await api("POST", "/api/cargas", { nombre: c.archivo.name, contenido_b64: btoa(bin), tabla: c.tabla, periodo: c.periodo, hoja: c.hoja || null, mapeo: c.mapeo && Object.keys(c.mapeo).length ? c.mapeo : null });
    prev.innerHTML = resultadoCarga(r, op);
    prev.querySelector("h3")?.setAttribute("tabindex", "-1"); prev.querySelector("h3")?.focus();
    document.getElementById("revalidar")?.addEventListener("click", () => {
      const mapeo = {};
      prev.querySelectorAll("[data-destino]").forEach(s => { if (s.value && s.value !== s.dataset.destino) mapeo[s.value] = s.dataset.destino; });
      cargaEnCurso = { ...c, mapeo, hoja: document.getElementById("hoja")?.value || c.hoja };
      validar(op);
    });
    document.getElementById("conf")?.addEventListener("click", async ev => {
      const b = ev.currentTarget; b.disabled = true; b.textContent = "Confirmando…";
      try {
        const k = await api("POST", `/api/cargas/${r.lote_id}/confirmar`, {});
        cargaEnCurso = null;
        prev.innerHTML = `<div class="estado ok" role="status" tabindex="-1" id="lote-ok"><p><strong>Lote ${esc(k.lote_id)} confirmado.</strong> Quedó guardado para el próximo cierre${k.directorio_lote ? ` (${esc(k.directorio_lote)})` : ""}.</p><p>Los usuarios todavía no lo ven: falta ejecutar y publicar el cierre del mes.</p></div>
          <a class="boton" href="#/operacion?seccion=ejecutar">Ir a «Ejecutar y publicar el cierre»</a>`;
        document.getElementById("lote-ok").focus();
      } catch (er) { prev.insertAdjacentHTML("afterbegin", errorHtml(er)); b.disabled = false; b.textContent = `Confirmar el lote ${r.lote_id}`; }
    });
  } catch (err) { prev.innerHTML = errorHtml(err); }
  finally { if (btn) { btn.disabled = false; btn.textContent = "Validar el archivo"; } }
}

// ---------------------------------------------------------------- V29 · ejecutar y publicar
function etapasHtml(etapas) {
  return etapas?.length ? `<ol class="etapas">${etapas.map(s => `<li class="${s.estado === "ok" ? "ok" : "fallo"}"><strong>${esc(ETAPAS[s.etapa] || s.etapa)}</strong> · ${s.estado === "ok" ? "correcto" : "falló"} · ${num(s.segundos)} s${s.error ? `<div class="muted">${esc(String(s.error).slice(0, 300))}</div>` : ""}</li>`).join("")}</ol>` : "";
}

function seccionEjecutar(op, cierres) {
  return `<div class="grid2">
  <section class="panel"><h2>Ejecutar el cierre del mes</h2>
    <p>Prepara la publicación con los archivos hasta la fecha indicada, la comprueba y, si todo está bien, la publica. <strong>Si falla, los usuarios siguen viendo el último cierre válido.</strong></p>
    <form id="eje" class="campos" novalidate><label for="corte-eje">Datos hasta <input id="corte-eje" type="date" name="corte" required value="${esc(op.corte || "")}"></label>
      <label for="datos-eje">Carpeta de archivos <span class="ayuda">Ruta en este equipo.</span><input id="datos-eje" name="datos" required value="../Green_Services_Recursos_de_Prueba"></label>
      <div class="fila"><button>Ejecutar y publicar el cierre</button></div></form><div id="res-eje" aria-live="polite"></div></section>
  <section class="panel"><h2>Publicar una salida ya preparada</h2>
    <p>Para una carpeta que ya contiene una publicación (por ejemplo, la demostración). No recalcula nada: la comprueba y la publica.</p>
    <form id="pub" class="campos" novalidate><label for="ruta-pub">Carpeta <input id="ruta-pub" name="ruta" required value="contratos/ejemplos/publicacion/demo-2026-10"></label><div class="fila"><button class="sec">Publicar esta salida</button></div></form>
    <div id="res-pub" aria-live="polite"></div></section></div>
  <section class="panel"><h2>Cierres disponibles</h2>${cierres.length ? tablaHtml({ cabeceras: ["Cierre", "Datos hasta", "Estado", "Publicado por"], filas: cierres.map(c => [`${esc(c.id)}${c.activo ? ' <span class="sello sello-ok">Lo ven los usuarios</span>' : ""}`, esc(fechaLarga(c.corte)), esc(c.estado), esc(c.publicado_por || "—")]) }) : vacio("Todavía no hay cierres.")}</section>`;
}

// ---------------------------------------------------------------- V30 · actividad
function seccionActividad(op, lotes, q) {
  const tipo = q.get("tipo") || "", resultado = q.get("resultado") || "";
  const todos = [
    ...op.ejecuciones.map(e => ({ tipo: "cierre", fecha: e.inicio, fallo: e.estado === "fallido", atencion: e.estado === "fallido", html: `<strong>Cierre ${esc(e.corte ? `con datos hasta el ${fechaLarga(e.corte)}` : "")}</strong> · ${e.estado === "publicado" ? "publicado" : e.estado === "fallido" ? "falló" : esc(e.estado)} · ${plural(e.intentos, "intento", "intentos")}${etapasHtml(e.etapas)}
      ${detalleTecnico(`<p class="muted">Ejecución ${esc(e.id)} · inicio ${esc(fechaHora(e.inicio))} · fin ${esc(e.fin ? fechaHora(e.fin) : "—")} · salida <code>${esc(e.detalle?.salida || "—")}</code></p>${e.detalle?.error ? `<pre>${esc(JSON.stringify(e.detalle.error, null, 2))}</pre>` : ""}`, "Ficha técnica")}` })),
    ...lotes.map(l => ({ tipo: "carga", fecha: l.cargado_en, fallo: l.estado === "fallido" || l.estado === "rechazado" || l.resumen?.bloqueante, atencion: l.estado === "previsualizado" || l.resumen?.bloqueante, html: `<strong>Carga de ${esc(TABLAS[l.tabla] || l.tabla)} · ${esc(l.periodo || "sin mes")}</strong> · ${esc(ESTADO_LOTE[l.estado] || l.estado)}${l.resumen?.bloqueante ? " · bloqueada por errores" : ""} · ${num(l.resumen?.aceptadas)} aceptadas, ${num(l.resumen?.duplicadas)} duplicadas, ${num(l.resumen?.aisladas)} apartadas · por ${esc(l.cargado_por || "—")}
      ${detalleTecnico(`<p class="muted">Lote ${l.id} · archivo ${esc(l.origen)} · ruta <code>${esc(l.resumen?.archivo || "—")}</code>${l.resumen?.mapeo ? ` · columnas <code>${esc(JSON.stringify(l.resumen.mapeo))}</code>` : ""}</p>`, "Ficha técnica")}` })),
  ];
  const act = todos.filter(a => (!tipo || a.tipo === tipo) && (!resultado || (resultado === "fallo" ? a.fallo : !a.fallo)))
    .sort((a, b) => (b.atencion - a.atencion) || b.fecha.localeCompare(a.fecha));
  const enlace = cambio => { const n = new URLSearchParams(q); n.set("seccion", "actividad"); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/operacion?${n}`; };
  return `<section class="panel"><h2>Filtrar</h2><form class="filtros" id="f-act"><label>Tipo <select name="tipo"><option value="">Todo</option><option value="cierre" ${tipo === "cierre" ? "selected" : ""}>Cierres</option><option value="carga" ${tipo === "carga" ? "selected" : ""}>Cargas de archivos</option></select></label>
    <label>Resultado <select name="resultado"><option value="">Todos</option><option value="fallo" ${resultado === "fallo" ? "selected" : ""}>Con fallo o bloqueo</option><option value="ok" ${resultado === "ok" ? "selected" : ""}>Sin fallo</option></select></label><button>Aplicar filtros</button></form>
    ${filtrosActivos([tipo && { texto: tipo === "cierre" ? "Solo cierres" : "Solo cargas", quitar: enlace({ tipo: "" }) }, resultado && { texto: resultado === "fallo" ? "Con fallo" : "Sin fallo", quitar: enlace({ resultado: "" }) }].filter(Boolean), "#/operacion?seccion=actividad")}</section>
  <section class="panel"><h2>Actividad (${num(act.length)} de ${num(todos.length)})</h2><p class="muted">Primero lo que requiere atención; después, de lo más reciente a lo más antiguo.</p>
    ${act.length ? `<ul class="actividad">${act.map(a => `<li class="${a.atencion ? "requiere" : ""}"><div class="crono-fecha">${esc(fechaHora(a.fecha))}</div><div>${a.atencion ? '<span class="sello sello-prueba">Requiere atención</span> ' : ""}${a.html}</div></li>`).join("")}</ul>` : vacio("Sin actividad con estos filtros.")}</section>`;
}

// ---------------------------------------------------------------- V31 · configuración y respaldos
function seccionAdministrar(op) {
  return `<div class="grid2"><section class="panel"><h2>Funciones de la aplicación</h2>
    <p class="muted">El cambio se aplica al marcar o desmarcar, y queda registrado. Si falla, la casilla vuelve a su estado anterior.</p>
    ${Object.entries(op.banderas).map(([k, b]) => `<div class="bandera"><label class="en-linea"><input type="checkbox" data-f="${esc(k)}" ${b.activo ? "checked" : ""}> <strong>${esc(NOMBRE_BANDERA[k] || b.descripcion)}</strong></label><p class="muted">Efecto: ${esc(b.efecto || b.descripcion)}</p><p class="muted" data-estado-f="${esc(k)}" aria-live="polite">Estado actual: ${b.activo ? "activada" : "desactivada"}.</p></div>`).join("")}</section>
   <section class="panel"><h2>Copia de seguridad</h2><p>Copia completa de la base (cierres, seguimientos, solicitudes, documentos) con su lista de contenido.</p><button id="resp">Crear una copia ahora</button><div id="rresp" aria-live="polite"></div>
    ${detalleTecnico(`<p class="muted">Restaurar en un entorno aislado: <code>python -m api restaurar RESPALDO --destino var/ensayo.sqlite3</code></p>`, "Cómo restaurar")}</section></div>
  ${detalleTecnico(`<p class="muted">Aplicación ${esc(op.version_app)} · ${esc(Object.entries(op.versiones || {}).map(([k, v]) => `${k} ${v}`).join(" · "))}</p>`, "Versiones")}`;
}

// ---------------------------------------------------------------- eventos
function enlazar(op) {
  const msg = html => { const m = document.getElementById("msg"); m.innerHTML = html; m.focus(); };
  document.querySelector("#carga [name=tabla]")?.addEventListener("change", e => { document.getElementById("esperadas").textContent = columnasEsperadas(op, e.target.value); });
  document.getElementById("carga")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target), archivo = fd.get("archivo");
    const nuevo = archivo && archivo.size ? archivo : cargaEnCurso?.archivo;
    const per = document.getElementById("periodo-carga"), malPer = !/^\d{4}-\d{2}$/.test(fd.get("periodo") || "");
    per.setAttribute("aria-invalid", String(malPer)); document.getElementById("err-periodo").textContent = malPer ? "Elige el mes de los datos en el calendario." : "";
    document.getElementById("err-archivo").textContent = nuevo ? "" : "Elige un archivo CSV o Excel.";
    if (malPer) return per.focus();
    if (!nuevo) return document.getElementById("archivo-carga").focus();
    cargaEnCurso = { archivo: nuevo, tabla: fd.get("tabla"), periodo: fd.get("periodo"), hoja: nuevo === cargaEnCurso?.archivo ? cargaEnCurso.hoja : null, mapeo: nuevo === cargaEnCurso?.archivo ? cargaEnCurso.mapeo : null };
    validar(op);
  });
  document.getElementById("pub")?.addEventListener("submit", async e => {
    e.preventDefault();
    const ruta = new FormData(e.target).get("ruta").trim(), res = document.getElementById("res-pub");
    if (!ruta) return e.target.querySelector("input").focus();
    const ok = await confirmar({ titulo: "¿Publicar esta salida?", mensaje: `<p>Se comprobará la carpeta <code>${esc(ruta)}</code> y, si es válida, <strong>todos los usuarios pasarán a ver esa información</strong> en lugar de ${esc(op.cierre_activo || "la actual")}.</p><p>Si la comprobación falla, no cambia nada.</p>`, confirmar: "Publicar la salida" });
    if (!ok) return;
    const b = e.target.querySelector("button"); b.disabled = true; b.textContent = "Publicando…";
    res.innerHTML = estadoHtml("", "Comprobando y publicando…");
    try {
      const r = await api("POST", "/api/cierres/publicar", { ruta });
      S.estadoApi = await api("GET", "/api/estado").catch(() => S.estadoApi);
      res.innerHTML = `<div class="estado ok" role="status"><strong>${r.ya_publicado ? `Sin cambios: esa salida ya estaba publicada como ${esc(r.cierre_id)}.` : `Publicado el cierre ${esc(r.cierre_id)}. Es el que ven ahora los usuarios.`}</strong></div>`;
    } catch (err) { res.innerHTML = errorHtml(err); }
    finally { b.disabled = false; b.textContent = "Publicar esta salida"; }
  });
  document.getElementById("eje")?.addEventListener("submit", async e => {
    e.preventDefault();
    const fd = new FormData(e.target), res = document.getElementById("res-eje");
    if (!fd.get("corte")) return document.getElementById("corte-eje").focus();
    const ok = await confirmar({ titulo: "¿Ejecutar y publicar el cierre?", mensaje: `<p>Se prepararán los datos hasta el <strong>${esc(fechaLarga(fd.get("corte")))}</strong> con los archivos de <code>${esc(fd.get("datos"))}</code>.</p><p>Si todo es correcto, <strong>todos los usuarios verán el cierre nuevo</strong>. Si falla, siguen viendo ${esc(op.cierre_activo || "el anterior")}. Puede tardar varios minutos.</p>`, confirmar: "Ejecutar y publicar" });
    if (!ok) return;
    const b = e.target.querySelector("button"); b.disabled = true; b.textContent = "Ejecutando…";
    res.innerHTML = estadoHtml("", "Ejecutando el cierre… puede tardar varios minutos. No cierres esta ventana.");
    try {
      const r = await api("POST", "/api/cierres/ejecutar", { corte: fd.get("corte"), datos: fd.get("datos"), reintentos: 0, __clave: e.target.dataset.clave ||= clave() });
      S.estadoApi = await api("GET", "/api/estado").catch(() => S.estadoApi);
      res.innerHTML = (r.estado === "publicado" ? `<div class="estado ok" role="status"><strong>Cierre publicado: ${esc(r.resultado.cierre_id)}.</strong> Es el que ven ahora los usuarios.</div>`
        : `<div class="estado error" role="alert"><p><strong>El cierre falló:</strong> ${esc(r.error?.mensaje || "error desconocido")}.</p><p>Los usuarios siguen viendo ${esc(r.ultimo_cierre_valido || "el cierre anterior")}.</p></div>`) + etapasHtml(r.etapas);
      delete e.target.dataset.clave;
    } catch (err) {
      res.innerHTML = `${errorHtml(err)}${err.status === undefined ? '<p class="estado">No sabemos si el cierre terminó. Revisa «Actividad» antes de volver a ejecutarlo.</p>' : ""}`;
    } finally { b.disabled = false; b.textContent = "Ejecutar y publicar el cierre"; }
  });
  document.getElementById("f-act")?.addEventListener("submit", e => {
    e.preventDefault(); const fd = new FormData(e.target), n = new URLSearchParams({ seccion: "actividad" });
    for (const [k, v] of fd) if (v) n.set(k, v);
    ir(`#/operacion?${n}`);
  });
  $vista.querySelectorAll("[data-f]").forEach(c => c.addEventListener("change", async () => {
    const estado = $vista.querySelector(`[data-estado-f="${c.dataset.f}"]`);
    c.disabled = true; estado.textContent = "Guardando el cambio…";
    try {
      await api("POST", "/api/operacion/banderas", { nombre: c.dataset.f, activo: c.checked });
      estado.textContent = `Estado actual: ${c.checked ? "activada" : "desactivada"} (cambio guardado).`;
    } catch (e) { c.checked = !c.checked; estado.textContent = `No se pudo cambiar; sigue ${c.checked ? "activada" : "desactivada"}.`; msg(errorHtml(e)); }
    finally { c.disabled = false; c.focus(); }
  }));
  document.getElementById("resp")?.addEventListener("click", async ev => {
    const b = ev.currentTarget; b.disabled = true; b.textContent = "Creando la copia…";
    try { const r = await api("POST", "/api/operacion/respaldo", {}); document.getElementById("rresp").innerHTML = `<div class="estado ok" role="status"><strong>Copia creada</strong> el ${esc(fechaHora(r.creado_en))} en ${esc(r.archivo)}.</div>`; }
    catch (e) { document.getElementById("rresp").innerHTML = errorHtml(e); }
    finally { b.disabled = false; b.textContent = "Crear una copia ahora"; }
  });
}
