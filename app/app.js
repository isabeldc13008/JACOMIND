// JACOMIND · interfaz web sin dependencias.
// Orígenes de datos (selección explícita y siempre visible):
//   servidor → API con sesión (cierre publicado); salida → /salida/agenda.json; ejemplo → /app/fixtures/agenda.json
import {
  $vista, FUENTES, S, TAMANOS, TEMAS, alRenderizar, api, aplicarPreferencias, cambiarPreferencia, enServidor, errorHtml, esc,
  estadoHtml, fechaHora, fechaLarga, inicioDePerfil, ir, plural, preferencias, puede, ruta, tieneRol,
} from "./nucleo.js";
import { activoEn, areasPara, icono } from "./navegacion.js";
import { encabezado, vacio } from "./ui.js";
import { vistaAgenda, vistaFicha } from "./vistas/cartera.js";
import { vistaTableros } from "./vistas/tableros.js";
import { vistaTareas } from "./vistas/seguimientos.js";
import { vistaPqrs } from "./vistas/pqrs.js";
import { vistaBeneficios } from "./vistas/beneficios.js";
import { olvidarConversaciones, vistaAsistente } from "./vistas/asistente.js";
import { vistaFinanzas } from "./vistas/finanzas.js";
import { vistaDocumentos } from "./vistas/documentos.js";
import { vistaOperacion } from "./vistas/operacion.js";
import { vistaPrevencion } from "./vistas/prevencion.js";
import { vistaIA } from "./vistas/ia.js";
import { vistaProxima } from "./vistas/proxima.js";
import { vistaVentaCruzada } from "./vistas/venta_cruzada.js";
import { vistaDemanda } from "./vistas/demanda.js";
import { vistaAnomalias } from "./vistas/anomalias.js";
import { vistaMonitoreo } from "./vistas/monitoreo.js";
import { vistaGuia } from "./vistas/guia.js";
import { vistaAdmin } from "./vistas/admin.js";

const ROLES = { admin: "Administrador", operaciones: "Operaciones", ventas: "Ventas", finanzas: "Finanzas", atencion: "Atención", gerencia: "Gerencia", empresa: "Empresa" };
const menu = document.getElementById("menu"), botonMenu = document.getElementById("boton-menu");

// ---------------------------------------------------------------- cabecera y navegación por áreas
function pintarCabecera() {
  const { partes, q } = ruta();
  const areas = enServidor() && S.usuario ? areasPara(S.usuario, puede) : [];
  const activo = activoEn(areas, partes, q);
  S.ubicacion = activo ? { area: activo.area.titulo, item: activo.item.titulo } : null;
  document.body.classList.toggle("sin-lateral", !areas.length);
  menu.innerHTML = areas.map(a => {
    const unica = a.items.length === 1 && (a.id === "inicio" || a.items[0].titulo === a.titulo);
    const enlace = i => `<li><a href="${esc(i.hash)}" ${activo?.item === i ? 'aria-current="page"' : ""}>${unica ? icono(a.icono) : ""}${esc(i.titulo)}</a></li>`;
    return unica ? `<div class="area area-unica"><ul>${a.items.map(enlace).join("")}</ul></div>`
      : `<div class="area"><h2 class="area-titulo">${icono(a.icono)}${esc(a.titulo)}</h2><ul>${a.items.map(enlace).join("")}</ul></div>`;
  }).join("");
  document.querySelector(".marca").setAttribute("href", enServidor() && S.usuario ? inicioDePerfil() : S.fuente ? "#/agenda" : "#/inicio");
  const asistente = document.getElementById("ir-asistente");
  asistente.classList.toggle("oculto", !(enServidor() && S.usuario && (puede("agente.datos") || puede("agente.portal"))));
  asistente.toggleAttribute("aria-current", partes[0] === "asistente");
  let origen = "";
  if (!S.fuente) origen = "Elige cómo quieres entrar";
  else if (enServidor()) {
    const corte = S.cierre === "activo" ? S.estadoApi?.corte_activo : null;
    origen = corte ? `<strong>Datos hasta el ${esc(fechaLarga(corte))}</strong>` : S.cierre !== "activo" ? `<strong>Viendo el cierre ${esc(S.cierre)}</strong>` : "<strong>Sin información publicada</strong>";
    if (S.estadoApi?.origen_activo === "sintetico") origen += ' <span class="sello sello-practica">Datos de práctica</span>';
  } else {
    origen = `<strong>${esc(FUENTES[S.fuente].corto)}</strong>`;
    if (S.local?.datos) origen += ` · datos hasta el ${esc(fechaLarga(S.local.datos.corte))}`;
  }
  document.getElementById("origen").innerHTML = `${origen}${!S.usuario ? ' · <a href="#/inicio">Cambiar forma de entrar</a>' : ""}`;
  document.getElementById("sesion").innerHTML = S.usuario
    ? `<span class="sesion-nombre"><strong>${esc(S.usuario.nombre.replace(/\s*\(fictici[oa]\)/, ""))}</strong>${esc(S.usuario.roles.map(r => ROLES[r] || r).join(", "))}${/ficticio|ficticia/.test(S.usuario.nombre) ? " · perfil de demostración" : ""}</span><button type="button" class="sec" id="salir">Salir</button>` : "";
  document.getElementById("salir")?.addEventListener("click", async () => {
    await api("DELETE", "/api/sesion").catch(() => {});
    S.usuario = null; olvidarConversaciones(); S.aviso = "Saliste de JACOMIND. Para volver, elige tu perfil."; ir("#/inicio");
  });
  botonMenu.classList.toggle("oculto", !areas.length);
}

function pintarPreferencias() {
  const p = preferencias();
  document.getElementById("panel-preferencias").innerHTML = `
    <fieldset><legend>Tamaño de la letra</legend>${Object.entries(TAMANOS).map(([k, t]) => `<label class="en-linea"><input type="radio" name="tamano" value="${k}" ${p.tamano === k ? "checked" : ""}> ${t}</label>`).join("")}</fieldset>
    <fieldset><legend>Colores</legend>${Object.entries(TEMAS).map(([k, t]) => `<label class="en-linea"><input type="radio" name="tema" value="${k}" ${p.tema === k ? "checked" : ""}> ${t}</label>`).join("")}</fieldset>
    <p class="muted">Se guarda en este equipo. También puedes usar el zoom del navegador (Ctrl y +).</p>
    <button type="button" class="sec" id="cerrar-preferencias">Listo</button>`;
}
document.getElementById("panel-preferencias").addEventListener("change", e => {
  if (e.target.name === "tamano" || e.target.name === "tema") cambiarPreferencia(e.target.name, e.target.value);
});
document.getElementById("panel-preferencias").addEventListener("click", e => {
  if (e.target.id === "cerrar-preferencias") { const d = document.getElementById("preferencias"); d.open = false; d.querySelector("summary").focus(); }
});
document.getElementById("preferencias").addEventListener("keydown", e => {
  if (e.key === "Escape") { const d = e.currentTarget; d.open = false; d.querySelector("summary").focus(); }
});
botonMenu.addEventListener("click", () => {
  const abierto = !menu.classList.contains("abierto");
  menu.classList.toggle("abierto", abierto); botonMenu.setAttribute("aria-expanded", String(abierto));
  if (abierto) menu.querySelector("a")?.focus();
});
// «Volver a intentar» de cualquier error: repite la pantalla actual sin perder la dirección.
// Los saltos dentro de la página no usan «#id» porque la dirección (#/...) es la ruta de la aplicación.
document.addEventListener("click", e => {
  if (e.target.closest("[data-reintentar]")) return render();
  const salto = e.target.closest("[data-ir-a]");
  if (salto) { const d = document.getElementById(salto.dataset.irA); if (d) { d.scrollIntoView({ block: "start" }); d.focus({ preventScroll: true }); } }
});
document.getElementById("saltar").addEventListener("click", e => { e.preventDefault(); $vista.focus(); $vista.scrollIntoView(); });

// ---------------------------------------------------------------- V01 · acceso y origen de los datos
async function vistaInicio() {
  document.body.classList.add("pantalla-acceso");
  let ids = [];
  const elegido = S.fuente || (S.apiDisponible ? "servidor" : null);
  if (S.apiDisponible && S.estadoApi?.login_demo && elegido === "servidor" && !S.usuario) ids = await api("GET", "/api/identidades").catch(() => []);
  const aviso = S.aviso ? `<div class="acceso-aviso" role="status">${esc(S.aviso)}</div>` : "";
  S.aviso = null;
  const corte = S.estadoApi?.corte_activo;
  const metadatos = corte ? `<p class="acceso-meta"><span>Datos hasta el ${esc(fechaLarga(corte))}</span><span>${S.estadoApi.origen_activo === "sintetico" ? "Entorno de demostración" : "Green Services &amp; Solutions"}</span></p>` : `<p class="acceso-meta">Entorno listo para explorar</p>`;
  const opciones = ids.length ? ids.map(i => `<option value="${esc(i.id)}" data-rol="${esc(ROLES[i.rol] || i.rol)}">${esc(i.nombre)} · ${esc(ROLES[i.rol] || i.rol)}${i.organizacion && i.organizacion !== "GREEN" ? " (" + esc(i.organizacion) + ")" : ""}</option>`).join("") : `<option value="">No hay perfiles disponibles</option>`;
  const loginLocal = S.estadoApi?.login_local ? `<details class="acceso-local"><summary>Usar usuario y contraseña</summary><form id="f-login-local" class="acceso-local-form"><label>Usuario<input name="usuario" required autocomplete="username"></label><label>Contraseña<input name="password" type="password" required autocomplete="current-password"></label><button class="boton-sec">Iniciar sesión</button></form><div id="msg-local" aria-live="polite"></div></details>` : "";
  const perfil = S.estadoApi?.login_demo ? `<form id="f-entrar" class="acceso-form"><label for="ident">Perfil de acceso</label><div class="acceso-select"><select id="ident" ${ids.length ? "" : "disabled"}>${opciones}</select><svg class="icono" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="m6 9 6 6 6-6"/></svg></div><button id="entrar" class="acceso-submit" ${ids.length ? "" : "disabled"}>Ingresar a JACOMIND <span aria-hidden="true">→</span></button></form>` : loginLocal;
  const accesoContenido = S.usuario ? `<p>Ya entraste como <strong>${esc(S.usuario.nombre)}</strong>.</p><a class="acceso-submit acceso-submit-link" href="${esc(inicioDePerfil())}">Ir a mi inicio <span aria-hidden="true">→</span></a>` : perfil;
  $vista.innerHTML = `<div class="pantalla-acceso-grid">
    <section class="acceso-hero" aria-labelledby="acceso-hero-title">
      <div class="acceso-brand"><span class="acceso-brand-mark" aria-hidden="true">J</span><span>JACOMIND</span></div>
      <div class="acceso-hero-copy"><p class="acceso-eyebrow">INTELIGENCIA PARA DECIDIR</p><h1 id="acceso-hero-title">De los datos a la acción.</h1><p>Inteligencia comercial y operativa para decisiones que generan valor.</p></div>
      <svg class="acceso-chart" viewBox="0 0 600 250" role="img" aria-label="Visualización abstracta de tendencias y conexiones de datos"><defs><linearGradient id="linea-acceso" x1="0" x2="1"><stop stop-color="#C4B5FD" stop-opacity=".2"/><stop offset=".5" stop-color="#C4B5FD"/><stop offset="1" stop-color="#fff" stop-opacity=".65"/></linearGradient></defs><path class="chart-grid" d="M30 210H570M30 160H570M30 110H570M30 60H570"/><path class="chart-line chart-line-soft" d="M30 190C110 165 115 185 180 140S270 170 325 115s85-5 120-55 75 10 125-35"/><path class="chart-line" d="M30 205C90 205 118 170 170 178s70-70 120-48 80 35 118-4 70-8 90-47 40-22 72-48"/><g class="chart-nodes"><circle cx="170" cy="178" r="5"/><circle cx="290" cy="130" r="5"/><circle cx="408" cy="126" r="5"/><circle cx="498" cy="79" r="5"/></g></svg>
      <div class="acceso-ind"><span class="ind-orb" aria-hidden="true">i</span><div><p class="acceso-ind-label">IND · AGENTE DE IA</p><p>Inteligencia que anticipa oportunidades.</p></div><span class="ind-pulse" aria-hidden="true"></span></div>
    </section>
    <section class="acceso-panel" aria-labelledby="acceso-title"><div class="acceso-panel-top"><span class="acceso-demo"><span></span>Modo demostración</span><details class="preferencias acceso-preferencias" id="preferencias-acceso"><summary aria-label="Configurar accesibilidad"><svg class="icono" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 19 9 5l5 14M6 14h6M15 19l3-8 3 8M16 16.5h4"/></svg><span class="oculto-visual">Accesibilidad</span></summary><div class="panel-preferencias" id="panel-preferencias-acceso"></div></details></div><div class="acceso-form-wrap"><div class="acceso-heading"><p class="acceso-kicker">ESPACIO DE TRABAJO</p><h2 id="acceso-title">Bienvenido a JACOMIND</h2><p>Accede a tu espacio de trabajo.</p></div>${aviso}${accesoContenido}<div id="msg" aria-live="polite"></div>${loginLocal && S.estadoApi?.login_demo ? loginLocal : ""}<div class="acceso-alternativas"><p>Otras opciones de acceso</p><a href="#/agenda" class="acceso-link" data-fuente="salida"><span class="acceso-link-icon">↗</span>Consultar agenda guardada</a><a href="#/agenda" class="acceso-link" data-fuente="ejemplo"><span class="acceso-link-icon">✦</span>Explorar ejemplo de práctica</a></div>${metadatos}</div><p class="acceso-footer">Desarrollado para Green Services &amp; Solutions</p></section>
  </div>`;
  const panelAcceso = document.getElementById("panel-preferencias-acceso");
  if (panelAcceso) {
    panelAcceso.innerHTML = document.getElementById("panel-preferencias").innerHTML;
    panelAcceso.addEventListener("change", e => { if (e.target.name === "tamano" || e.target.name === "tema") cambiarPreferencia(e.target.name, e.target.value); });
    panelAcceso.addEventListener("click", e => { if (e.target.id === "cerrar-preferencias") { const d = document.getElementById("preferencias-acceso"); d.open = false; d.querySelector("summary").focus(); } });
  }
  document.getElementById("preferencias-acceso")?.addEventListener("keydown", e => { if (e.key === "Escape") { const d = e.currentTarget; d.open = false; d.querySelector("summary").focus(); } });
  $vista.querySelectorAll(".acceso-link").forEach(a => a.addEventListener("click", e => { e.preventDefault(); S.fuente = a.dataset.fuente; S.local = null; try { localStorage.setItem("jacomind.fuente", S.fuente); } catch { /* sin almacenamiento */ } ir("#/agenda"); }));
  document.getElementById("ident")?.addEventListener("change", () => { document.getElementById("entrar").innerHTML = `Ingresar a JACOMIND <span aria-hidden="true">→</span>`; });
  document.getElementById("f-login-local")?.addEventListener("submit", async e => {
    e.preventDefault(); const b = e.target.querySelector("button"), msg = document.getElementById("msg-local"); b.disabled = true; b.textContent = "Entrando…";
    try { const r = await api("POST", "/api/sesion", Object.fromEntries(new FormData(e.target))); S.usuario = r.usuario; S.fuente = "servidor"; localStorage.setItem("jacomind.fuente", "servidor"); ir(r.usuario.requiere_cambio_clave ? "#/cambiar-clave" : inicioDePerfil()); }
    catch (err) { msg.innerHTML = errorHtml(err); b.disabled = false; b.textContent = "Entrar"; }
  });
  document.getElementById("f-entrar")?.addEventListener("submit", async e => {
    e.preventDefault();
    const b = document.getElementById("entrar"); b.disabled = true; b.textContent = "Ingresando…";
    try {
      const r = await Promise.race([
        api("POST", "/api/sesion", { identidad: document.getElementById("ident").value }),
        new Promise((_, reject) => setTimeout(() => reject(new Error("La solicitud tardó demasiado. Verifica que el servidor esté disponible e inténtalo de nuevo.")), 12000)),
      ]);
      olvidarConversaciones();
      S.usuario = r.usuario; S.fuente = "servidor";
      try { localStorage.setItem("jacomind.fuente", "servidor"); } catch { /* sin almacenamiento */ }
      ir(inicioDePerfil());
    } catch (err) { document.getElementById("msg").innerHTML = errorHtml(err.message?.startsWith("La solicitud") ? { mensaje: err.message } : err); b.disabled = false; b.innerHTML = `Ingresar a JACOMIND <span aria-hidden="true">→</span>`; }
  });
}

async function vistaCambioClave() {
  $vista.innerHTML = `${encabezado({ titulo: "Cambia tu contraseña", descripcion: "La contraseña inicial es temporal y debes reemplazarla antes de continuar." })}<section class="panel"><form id="f-cambio-clave" class="campos"><label>Contraseña actual <input name="actual" type="password" required autocomplete="current-password"></label><label>Nueva contraseña <input name="nueva" type="password" minlength="8" required autocomplete="new-password"></label><button>Guardar contraseña</button></form><div id="msg-cambio" aria-live="polite"></div></section>`;
  document.getElementById("f-cambio-clave").addEventListener("submit", async e => {
    e.preventDefault(); const b = e.target.querySelector("button"), msg = document.getElementById("msg-cambio"); b.disabled = true;
    try { const r = await api("POST", "/api/sesion/cambiar-clave", Object.fromEntries(new FormData(e.target))); S.usuario = r.usuario; ir(inicioDePerfil()); }
    catch (err) { msg.innerHTML = errorHtml(err); b.disabled = false; }
  });
}

// ---------------------------------------------------------------- V27 · inicio de Operaciones
async function vistaBienvenida() {
  if (!tieneRol("operaciones")) return ir(inicioDePerfil());
  $vista.innerHTML = `${encabezado({ titulo: `Hola, ${S.usuario.nombre.split(" ")[0]}` })}${estadoHtml("", "Cargando lo pendiente…")}`;
  const [op, lotes, tab] = await Promise.all([
    puede("operacion.administrar") ? api("GET", "/api/operacion").catch(e => e) : null,
    puede("operacion.administrar") ? api("GET", "/api/cargas").catch(() => []) : [],
    puede("tablero.operaciones") ? api("GET", `/api/cierres/${S.cierre}/tableros/operaciones`).catch(e => e) : null]);
  const ok = x => x && !(x instanceof Error);
  const pendientes = [];
  if (ok(op)) {
    const ult = op.ejecuciones[0], ultOk = op.ejecuciones.find(e => e.estado === "publicado");
    if (ult?.estado === "fallido") pendientes.push(`El último cierre (${esc(fechaHora(ult.inicio))}) falló. Los usuarios siguen viendo el cierre anterior. <a href="#/operacion?seccion=actividad">Ver qué pasó</a>`);
    const porConfirmar = lotes.filter(l => l.estado === "previsualizado" && !l.resumen?.bloqueante).length;
    if (porConfirmar) pendientes.push(`${plural(porConfirmar, "archivo validado espera", "archivos validados esperan")} confirmación. <a href="#/operacion?seccion=cargar">Revisar archivos</a>`);
    const sinIncorporar = lotes.filter(l => l.estado === "confirmado" && (!ultOk || l.cargado_en > ultOk.inicio)).length;
    if (sinIncorporar) pendientes.push(`${plural(sinIncorporar, "archivo confirmado aún no se ve", "archivos confirmados aún no se ven")}: falta ejecutar el cierre del mes. <a href="#/operacion?seccion=ejecutar">Preparar el cierre</a>`);
  }
  const cob = ok(tab) ? `<p class="grande">${plural(tab.coberturas_vencidas.length, "cobertura vencida", "coberturas vencidas")} · ${plural(tab.coberturas_proximas.length, "vence", "vencen")} en 45 días</p><p class="muted">Se cuentan coberturas, no clientes. Datos hasta el ${esc(fechaLarga(tab.cierre.corte))}.</p>`
    : tab instanceof Error ? errorHtml(tab, { reintentar: true }) : "";
  const datos = ok(op) ? `<p class="grande">${op.corte ? `Datos hasta el ${esc(fechaLarga(op.corte))}` : "Sin cierre publicado"}</p><p class="muted">${op.cierre_activo ? `Los usuarios ven el cierre ${esc(op.cierre_activo)}${op.publicado_en ? `, publicado el ${esc(fechaHora(op.publicado_en))}` : ""}.` : ""}</p>`
    : op instanceof Error ? errorHtml(op, { reintentar: true }) : "";
  $vista.innerHTML = `${encabezado({ titulo: `Hola, ${S.usuario.nombre.split(" ")[0]}. ¿Qué necesitas hacer?`, descripcion: "Elige uno de los dos trabajos principales. Las coberturas y la preparación de datos se cuentan por separado." })}
  <div class="grid2">
    <section class="panel"><h2>Revisar coberturas</h2>${cob}<a class="boton" href="#/tableros/operaciones">Revisar coberturas y renovaciones</a></section>
    <section class="panel"><h2>Preparar el cierre del mes</h2>${datos}
      ${pendientes.length ? `<ul>${pendientes.map(p => `<li>${p}</li>`).join("")}</ul>` : ok(op) ? '<p class="estado ok">No hay archivos ni cierres pendientes.</p>' : ""}
      <a class="boton" href="#/operacion?seccion=cargar">Cargar y publicar datos</a></section>
  </div>
  <section class="panel"><h2>Otros accesos</h2><div class="fila">
    ${puede("anomalias.ver") ? '<a class="boton-sec" href="#/anomalias">Operaciones por revisar</a>' : ""}
    ${puede("informes.ver") ? '<a class="boton-sec" href="#/finanzas?seccion=informes">Informes mensuales</a>' : ""}
    ${puede("demanda.ver_unidades") ? '<a class="boton-sec" href="#/demanda">Pronóstico de demanda</a>' : ""}
    ${puede("monitoreo.ver") ? '<a class="boton-sec" href="#/ia">Modelos y monitoreo</a>' : ""}</div></section>`;
}

// ---------------------------------------------------------------- enrutado
async function render() {
  document.body.classList.remove("pantalla-acceso");
  pintarCabecera();
  menu.classList.remove("abierto"); botonMenu.setAttribute("aria-expanded", "false");
  const { partes } = ruta();
  const [v, a] = partes;
  try {
    if (v === "cambiar-clave") return await vistaCambioClave();
    if (v === "inicio" || !S.fuente) return await vistaInicio();
    if (!enServidor() && v !== "agenda" && v !== "clientes") return ir("#/agenda");
    if (enServidor() && !S.usuario) return await vistaInicio();
    if (S.usuario?.requiere_cambio_clave) return ir("#/cambiar-clave");
    const sinPermiso = () => { S.aviso = null; ir(inicioDePerfil()); };
    switch (v) {
      case "bienvenida": return await vistaBienvenida();
      case "admin": return puede("usuarios.gestionar") ? await vistaAdmin() : sinPermiso();
      case "clientes": return await vistaFicha(a, ruta().q);
      case "tableros": return await vistaTableros(a);
      case "tareas": return await vistaTareas(a);
      case "pqrs": return await vistaPqrs(a);
      case "beneficios": return await vistaBeneficios();
      case "asistente": return await vistaAsistente();
      case "finanzas": return puede("finanzas.ver") || puede("informes.ver") ? await vistaFinanzas() : sinPermiso();
      case "documentos": return await vistaDocumentos();
      case "operacion": return await vistaOperacion();
      case "monitoreo": return puede("monitoreo.ver") ? await vistaMonitoreo() : sinPermiso();
      case "guia": return puede("guia.ver") ? await vistaGuia() : sinPermiso();
      case "anomalias": return puede("anomalias.ver") ? await vistaAnomalias() : sinPermiso();
      case "demanda": return puede("demanda.ver_cop") || puede("demanda.ver_unidades") ? await vistaDemanda() : sinPermiso();
      case "venta-cruzada": return puede("venta_cruzada.ver") ? await vistaVentaCruzada() : sinPermiso();
      case "proxima": return puede("proxima.ver") ? await vistaProxima() : sinPermiso();
      case "ia": return puede("cartera.ver") ? await vistaIA() : puede("monitoreo.ver") ? ir("#/monitoreo") : sinPermiso();
      case "prevencion": return puede("prevencion.ver") ? await vistaPrevencion() : sinPermiso();
      case "agenda": return puede("cartera.ver") || !enServidor() ? await vistaAgenda() : sinPermiso();
      default: return ir(enServidor() ? inicioDePerfil() : "#/agenda");
    }
  } catch (e) {
    if (e.status === 401) {
      S.usuario = null; olvidarConversaciones();
      S.aviso = "Tu sesión terminó. Vuelve a entrar con tu perfil; la pantalla que estabas viendo se abrirá de nuevo desde el menú.";
      return ir("#/inicio");
    }
    $vista.innerHTML = `${encabezado({ titulo: S.ubicacion?.item || "No se pudo abrir la pantalla" })}${errorHtml(e, { reintentar: true })}`;
  } finally {
    pintarCabecera();
  }
}
alRenderizar(render);

// Al cambiar de pantalla (no al aplicar un filtro en la misma), el foco va al contenido y la página vuelve arriba,
// para que el lector de pantalla anuncie el nuevo título. Los filtros conservan el foco donde estaba.
let pantallaPrevia = location.hash.split("?")[0];
window.addEventListener("hashchange", () => {
  const actual = location.hash.split("?")[0];
  if (actual !== pantallaPrevia) { window.scrollTo(0, 0); setTimeout(() => $vista.focus({ preventScroll: true }), 0); }
  pantallaPrevia = actual;
});

async function iniciar() {
  aplicarPreferencias();
  pintarPreferencias();
  try {
    const r = await fetch("/api/estado", { cache: "no-store" });
    if (r.ok) { S.estadoApi = await r.json(); S.apiDisponible = true; }
  } catch { /* modo estático */ }
  if (S.apiDisponible) S.usuario = (await api("GET", "/api/sesion").catch(() => null))?.usuario || null;
  if (!S.apiDisponible && S.fuente === "servidor") S.fuente = null;
  if (S.apiDisponible && !S.fuente) S.fuente = "servidor";
  window.addEventListener("hashchange", render);
  if (!location.hash && enServidor() && S.usuario) location.hash = S.usuario.requiere_cambio_clave ? "#/cambiar-clave" : inicioDePerfil();
  else render();
}
iniciar();
