// JACOMIND · interfaz web sin dependencias.
// Orígenes de datos (selección explícita y siempre visible):
//   servidor → API con sesión (cierre publicado); salida → /salida/agenda.json; ejemplo → /app/fixtures/agenda.json
import { $vista, FUENTES, S, alRenderizar, api, enServidor, errorHtml, esc, fechaLarga, inicioDePerfil, ir, puede, ruta, tieneRol } from "./nucleo.js";
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

const ROLES = { operaciones: "Operaciones", ventas: "Ventas", finanzas: "Finanzas", atencion: "Atención", gerencia: "Gerencia", empresa: "Empresa" };

// ---------------------------------------------------------------- cabecera
function pintarCabecera() {
  const { partes } = ruta();
  const items = [];
  const add = (h, t) => items.push(`<a href="#/${h}" ${partes[0] === h.split("/")[0] ? 'aria-current="page"' : ""}>${t}</a>`);
  if (!enServidor()) { if (S.fuente) add("agenda", "Agenda"); }
  else if (S.usuario) {
    if (tieneRol("operaciones")) add("bienvenida", "Inicio");
    if (puede("tablero.ventas") || puede("tablero.operaciones") || puede("tablero.gerencia")) add("tableros", "Tableros");
    if (puede("cartera.ver")) add("agenda", "Agenda");
    if (puede("tareas.ver")) add("tareas", "Seguimientos");
    if (puede("prevencion.ver")) add("prevencion", "Prevención (IA)");
    if (puede("proxima.ver")) add("proxima", "Próxima compra (IA)");
    if (puede("venta_cruzada.ver")) add("venta-cruzada", "Venta cruzada (IA)");
    if (puede("demanda.ver_cop") || puede("demanda.ver_unidades")) add("demanda", "Pronóstico (IA)");
    if (puede("anomalias.ver")) add("anomalias", "Operaciones atípicas (IA)");
    if (puede("cartera.ver")) add("ia", "Modelos de IA");
    if (puede("pqrs.ver_propias") || puede("pqrs.gestionar") || puede("pqrs.indicadores")) add("pqrs", S.usuario.externo ? "Solicitudes" : "Solicitudes (PQRS)");
    if (puede("beneficios.portal") || puede("beneficios.ver_interno")) add("beneficios", "Beneficios");
    if (puede("agente.datos") || puede("agente.portal")) add("asistente", "Asistente");
    if (puede("finanzas.ver")) add("finanzas", "Finanzas");
    else if (puede("informes.ver")) add("finanzas", "Informes mensuales");
    if (puede("documentos.gestionar")) add("documentos", "Documentos");
    if (puede("operacion.administrar")) add("operacion", "Operación");
  }
  document.getElementById("menu").innerHTML = items.join("");
  document.querySelector(".marca").setAttribute("href", enServidor() && S.usuario ? inicioDePerfil() : S.fuente ? "#/agenda" : "#/inicio");
  let origen = "";
  if (!S.fuente) origen = "Elige cómo quieres trabajar";
  else if (enServidor()) {
    origen = `<strong>${esc(FUENTES.servidor.corto)}</strong>`;
    if (S.cierre !== "activo") origen += ` · ${esc(S.cierre)}`;
    else if (S.estadoApi?.corte_activo) origen += ` · datos hasta el ${esc(fechaLarga(S.estadoApi.corte_activo))}`;
    if (S.estadoApi?.origen_activo === "sintetico") origen += " · <strong>datos de práctica</strong>";
  } else {
    origen = `<strong>${esc(FUENTES[S.fuente].corto)}</strong>`;
    if (S.local?.datos) origen += ` · datos hasta el ${esc(fechaLarga(S.local.datos.corte))}`;
  }
  document.getElementById("origen").innerHTML = `${origen} · <a href="#/inicio">Cambiar</a>`;
  document.getElementById("sesion").innerHTML = S.usuario
    ? `<span class="muted">${esc(S.usuario.nombre)} · ${esc(S.usuario.roles.map(r => ROLES[r] || r).join(", "))}</span> <button class="sec" id="salir">Salir</button>` : "";
  document.getElementById("salir")?.addEventListener("click", async () => {
    await api("DELETE", "/api/sesion").catch(() => {});
    S.usuario = null; olvidarConversaciones(); ir("#/inicio");
  });
}

// ---------------------------------------------------------------- entrada: origen y sesión (entrada 1)
async function vistaInicio() {
  let ids = [];
  const elegido = S.fuente;
  if (S.apiDisponible && S.estadoApi?.login_demo && elegido === "servidor" && !S.usuario) ids = await api("GET", "/api/identidades").catch(() => []);
  const tarjeta = (k) => {
    const f = FUENTES[k], deshabilitado = k === "servidor" && !S.apiDisponible;
    return `<label class="opcion-origen ${elegido === k ? "activa" : ""} ${deshabilitado ? "deshabilitada" : ""}">
      <input type="radio" name="fuente" value="${k}" ${elegido === k ? "checked" : ""} ${deshabilitado ? "disabled" : ""}>
      <strong>${esc(f.titulo)}</strong><span>${esc(f.explica)}</span>
      ${deshabilitado ? '<span class="muted">No disponible en este equipo: la ayuda técnica explica cómo activarlo.</span>' : ""}</label>`;
  };
  $vista.innerHTML = `<h1>¿Cómo quieres trabajar?</h1>
  <div class="opciones-origen" role="radiogroup" aria-label="Origen de los datos">${["servidor", "salida", "ejemplo"].map(tarjeta).join("")}</div>
  ${elegido === "servidor" && S.apiDisponible ? `<section class="panel"><h2>Inicia sesión</h2>
    ${S.usuario ? `<p>Ya entraste como <strong>${esc(S.usuario.nombre)}</strong>. <a href="${inicioDePerfil()}">Continuar</a></p>` : S.estadoApi?.login_demo ? `
    <p class="muted">Identidades ficticias de demostración: cada una entra con los permisos de su perfil.</p>
    <div class="fila"><label>Identidad <select id="ident">${ids.map(i => `<option value="${esc(i.id)}">${esc(i.nombre)} — ${esc(ROLES[i.rol] || i.rol)} (${esc(i.organizacion)})</option>`).join("")}</select></label>
    <button id="entrar" ${ids.length ? "" : "disabled"}>Entrar</button></div>` : '<p class="muted">El acceso se gestiona con el inicio de sesión de tu organización.</p>'}<div id="msg"></div></section>` : ""}
  ${elegido && elegido !== "servidor" ? `<p><a class="boton" href="#/agenda">Abrir la agenda</a></p>` : ""}
  <details class="tecnico"><summary>Ayuda técnica</summary>
    <ul><li><strong>Cierre publicado:</strong> arranca el servidor con <code>python -m api demo</code> y <code>python -m api servir --practica</code>.</li>
    <li><strong>Agenda local:</strong> se lee de <code>/salida/agenda.json</code>. Genérala con <code>python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json</code>.</li>
    <li><strong>Demostración:</strong> se lee de <code>/app/fixtures/agenda.json</code>.</li>
    ${S.apiDisponible ? "" : "<li>No se detectó el servidor: se están sirviendo archivos estáticos.</li>"}</ul></details>`;
  $vista.querySelectorAll("input[name=fuente]").forEach(r => r.addEventListener("change", e => {
    S.fuente = e.target.value; S.local = null;
    try { localStorage.setItem("jacomind.fuente", S.fuente); } catch { /* sin almacenamiento */ }
    if (enServidor() && S.usuario) return ir(inicioDePerfil());
    if (!enServidor()) return ir("#/agenda");
    pintarCabecera(); vistaInicio();
  }));
  document.getElementById("entrar")?.addEventListener("click", async () => {
    try {
      const r = await api("POST", "/api/sesion", { identidad: document.getElementById("ident").value });
      olvidarConversaciones();
      S.usuario = r.usuario; S.fuente = "servidor";
      try { localStorage.setItem("jacomind.fuente", "servidor"); } catch { /* sin almacenamiento */ }
      ir(inicioDePerfil());
    } catch (e) { document.getElementById("msg").innerHTML = errorHtml(e); }
  });
}

// Operaciones elige entre revisar vencimientos y preparar el cierre.
function vistaBienvenida() {
  if (!tieneRol("operaciones")) return ir(inicioDePerfil());
  $vista.innerHTML = `<h1>Hola, ${esc(S.usuario.nombre.split(" ")[0])}. ¿Qué necesitas hacer?</h1>
  <div class="opciones-origen">
    <a class="opcion-origen" href="#/tableros/operaciones"><strong>Revisar vencimientos</strong><span>Coberturas vencidas y las que vencen en los próximos 45 días, con su cliente.</span></a>
    <a class="opcion-origen" href="#/operacion"><strong>Preparar el cierre</strong><span>Cargar y validar archivos, ejecutar y publicar el cierre mensual, revisar la actividad.</span></a>
    <a class="opcion-origen" href="#/finanzas"><strong>Informes mensuales</strong><span>Abrir o generar el informe del mes.</span></a>
    <a class="opcion-origen" href="#/ia"><strong>Resultados de la IA</strong><span>Qué estiman los modelos de compra e inactividad y cómo se comparan con las reglas.</span></a>
  </div>`;
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
      case "bienvenida": return vistaBienvenida();
      case "clientes": return await vistaFicha(a, q);
      case "tableros": return await vistaTableros(a);
      case "tareas": return await vistaTareas(a);
      case "pqrs": return await vistaPqrs(a);
      case "beneficios": return await vistaBeneficios();
      case "asistente": return await vistaAsistente();
      case "finanzas": return await vistaFinanzas();
      case "documentos": return await vistaDocumentos();
      case "operacion": return await vistaOperacion();
      case "anomalias": return puede("anomalias.ver") ? await vistaAnomalias() : ir(inicioDePerfil());
      case "demanda": return puede("demanda.ver_cop") || puede("demanda.ver_unidades") ? await vistaDemanda() : ir(inicioDePerfil());
      case "venta-cruzada": return puede("venta_cruzada.ver") ? await vistaVentaCruzada() : ir(inicioDePerfil());
      case "proxima": return puede("proxima.ver") ? await vistaProxima() : ir(inicioDePerfil());
      case "ia": return puede("cartera.ver") ? await vistaIA() : ir(inicioDePerfil());
      case "prevencion": return puede("prevencion.ver") ? await vistaPrevencion() : ir(inicioDePerfil());
      case "agenda": return puede("cartera.ver") || !enServidor() ? await vistaAgenda() : ir(inicioDePerfil());
      default: return ir(enServidor() ? inicioDePerfil() : "#/agenda");
    }
  } catch (e) {
    if (e.status === 401) { S.usuario = null; olvidarConversaciones(); return ir("#/inicio"); }
    $vista.innerHTML = errorHtml(e);
  }
}
alRenderizar(render);

async function iniciar() {
  try {
    const r = await fetch("/api/estado", { cache: "no-store" });
    if (r.ok) { S.estadoApi = await r.json(); S.apiDisponible = true; }
  } catch { /* modo estático */ }
  if (S.apiDisponible) S.usuario = (await api("GET", "/api/sesion").catch(() => null))?.usuario || null;
  if (!S.apiDisponible && S.fuente === "servidor") S.fuente = null;
  window.addEventListener("hashchange", render);
  if (!location.hash && enServidor() && S.usuario) location.hash = inicioDePerfil();
  else render();
}
iniciar();
