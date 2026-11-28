// Navegación por áreas de trabajo, generada desde las capacidades del perfil (no desde nombres de rol en cada vista).
// Módulo puro: no toca el DOM, para poder probarlo con Node. Los permisos del servidor siguen siendo la autoridad.

/** Inicio propio de cada perfil (V02, V03, V13, V17, V19, V27). */
export function inicioPara(usuario, puede) {
  if (!usuario) return "#/inicio";
  const rol = r => usuario.roles?.includes(r);
  if (usuario.externo) return "#/beneficios";
  if (rol("gerencia")) return "#/tableros/gerencia";
  if (rol("ventas")) return "#/tableros/ventas";
  if (rol("finanzas")) return "#/finanzas";
  if (rol("atencion")) return "#/pqrs";
  if (rol("operaciones")) return "#/bienvenida";
  if (rol("admin") || puede("usuarios.gestionar")) return "#/admin";
  return puede("cartera.ver") ? "#/agenda" : "#/inicio";
}

const ICONOS = {
  inicio: '<path d="M4 11.5 12 5l8 6.5"/><path d="M6.5 10v9h11v-9"/><path d="M10 19v-5h4v5"/>',
  clientes: '<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19c.6-3.2 2.8-5 5.5-5s4.9 1.8 5.5 5"/><circle cx="16.5" cy="9.5" r="2.3"/><path d="M15.5 14.2c2.4-.2 4.3 1.3 5 4.3"/>',
  operaciones: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 9.5h16M8.5 3v4M15.5 3v4M8 13.5h3M8 16.5h6"/>',
  finanzas: '<path d="M4 19h16"/><path d="M6.5 16v-4M11 16V8M15.5 16v-6M20 16V5"/>',
  atencion: '<path d="M5 6h14v9.5H10l-4 3.5v-3.5H5z"/><path d="M8.5 9.5h7M8.5 12.5h4.5"/>',
  administracion: '<circle cx="12" cy="12" r="3"/><path d="M12 3.5v2.3M12 18.2v2.3M3.5 12h2.3M18.2 12h2.3M6 6l1.6 1.6M16.4 16.4 18 18M6 18l1.6-1.6M16.4 7.6 18 6"/>',
  portal: '<path d="M4 9.5 12 5l8 4.5v9.5H4z"/><path d="M9.5 19v-5h5v5"/>',
  guia: '<path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H19v15H7.5A2.5 2.5 0 0 0 5 20.5z"/><path d="M5 20.5A2.5 2.5 0 0 1 7.5 18H19v3H7.5"/><path d="M9 7.5h6M9 10.5h4"/>',
  solicitudes: '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M8.5 8.5h7M8.5 12h7M8.5 15.5h4"/>',
};
export const icono = (nombre, clase = "icono") =>
  `<svg class="${clase}" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONOS[nombre] || ""}</svg>`;

/** Compara la ruta actual con un destino: mismo primer segmento y, si el destino fija parámetros, mismos valores. */
function coincide(destino, partes, q) {
  const [camino, qs] = destino.slice(2).split("?");
  const seg = camino.split("/").filter(Boolean);
  if (seg.some((s, i) => partes[i] !== s)) return false;
  const req = new URLSearchParams(qs || "");
  for (const [k, v] of req) if ((q.get(k) || "") !== v) return false;
  return true;
}

/**
 * Áreas visibles para el perfil: [{id, titulo, icono, items:[{hash, titulo, describe, rutas?}]}].
 * `rutas` agrupa destinos que pertenecen al mismo elemento (p. ej. la ficha dentro de Cartera).
 */
export function areasPara(usuario, puede) {
  if (!usuario) return [];
  const inicio = inicioPara(usuario, puede);
  if (usuario.externo) {
    return [
      { id: "portal", titulo: "Inicio y beneficios", icono: "portal", items: [{ hash: "#/beneficios", titulo: "Beneficios de tu empresa", describe: "Ventajas vigentes y cómo pedirlas" }] },
      { id: "solicitudes", titulo: "Mis solicitudes", icono: "solicitudes", items: [{ hash: "#/pqrs", titulo: "Mis solicitudes", describe: "Consultar o crear una solicitud" }] },
    ].filter(a => a.id !== "solicitudes" || puede("pqrs.ver_propias"));
  }
  const demanda = puede("demanda.ver_cop") || puede("demanda.ver_unidades");
  const areas = [
    { id: "inicio", titulo: "Inicio", icono: "inicio", items: [{ hash: inicio, titulo: "Inicio", describe: "Lo que necesita tu atención" }] },
    { id: "clientes", titulo: "Clientes y ventas", icono: "clientes", items: [
      puede("tablero.ventas") && { hash: "#/tableros/ventas", titulo: "Resumen comercial", describe: "A quién revisar primero" },
      puede("cartera.ver") && { hash: "#/agenda", titulo: "Cartera de clientes", describe: "Buscar y abrir clientes", rutas: ["#/clientes"] },
      puede("tareas.ver") && { hash: "#/tareas", titulo: "Seguimientos", describe: "Trabajo registrado con cada cliente" },
      puede("prevencion.ver") && { hash: "#/prevencion", titulo: "Clientes que podrían dejar de comprar", describe: "Revisión preventiva" },
      puede("proxima.ver") && { hash: "#/proxima", titulo: "Cuándo conviene contactar", describe: "Ventanas estimadas" },
      puede("venta_cruzada.ver") && { hash: "#/venta-cruzada", titulo: "Productos que podrías ofrecer", describe: "Sugerencias para revisar" },
    ] },
    { id: "operaciones", titulo: "Operaciones", icono: "operaciones", items: [
      puede("tablero.operaciones") && { hash: "#/tableros/operaciones", titulo: "Coberturas y renovaciones", describe: "Qué vence y qué ya venció" },
      puede("anomalias.ver") && { hash: "#/anomalias", titulo: "Operaciones por revisar", describe: "Precios o cantidades fuera de lo habitual" },
      demanda && !puede("finanzas.ver") && { hash: "#/demanda", titulo: "Pronóstico de demanda", describe: "Próximos meses en unidades" },
    ] },
    { id: "finanzas", titulo: "Finanzas", icono: "finanzas", items: [
      puede("tablero.gerencia") && { hash: "#/tableros/gerencia", titulo: "Resumen ejecutivo", describe: "Ventas del mes y dónde cambiaron" },
      puede("finanzas.ver") && { hash: "#/finanzas?seccion=resultado", titulo: "Resultado del mes", describe: "Ventas y compras por mes", rutas: ["#/finanzas"] },
      demanda && puede("finanzas.ver") && { hash: "#/demanda", titulo: "Pronóstico", describe: "Próximos meses" },
      puede("finanzas.ver") && { hash: "#/finanzas?seccion=escenarios", titulo: "Escenarios del dólar", describe: "Qué pasa si cambia la TRM" },
      puede("informes.ver") && { hash: "#/finanzas?seccion=informes", titulo: "Informes mensuales", describe: "Versión para reuniones", rutas: puede("finanzas.ver") ? [] : ["#/finanzas"] },
    ] },
    { id: "atencion", titulo: "Atención", icono: "atencion", items: [
      (puede("pqrs.gestionar") || puede("pqrs.indicadores")) && { hash: "#/pqrs", titulo: puede("pqrs.gestionar") ? "Solicitudes de clientes" : "Indicadores de solicitudes", describe: "Peticiones, quejas y reclamos" },
      puede("beneficios.ver_interno") && { hash: "#/beneficios", titulo: "Catálogo de beneficios", describe: "Condiciones y publicación" },
      puede("documentos.gestionar") && { hash: "#/documentos", titulo: "Base de conocimiento", describe: "Políticas que respaldan respuestas" },
    ] },
    { id: "administracion", titulo: "Administración", icono: "administracion", items: [
      puede("usuarios.gestionar") && { hash: "#/admin", titulo: "Usuarios", describe: "Crear y administrar cuentas" },
      puede("operacion.administrar") && { hash: "#/operacion?seccion=cargar", titulo: "Datos y cierres", describe: "Cargar archivos y publicar el mes", rutas: ["#/operacion?seccion=ejecutar", "#/operacion"] },
      (puede("cartera.ver") || puede("monitoreo.ver")) && { hash: puede("cartera.ver") ? "#/ia" : "#/monitoreo", titulo: "Modelos y monitoreo", describe: "Qué estima cada modelo y sus avisos", rutas: ["#/ia", "#/monitoreo"] },
      puede("operacion.administrar") && { hash: "#/operacion?seccion=actividad", titulo: "Actividad", describe: "Cargas, cierres y errores" },
      puede("operacion.administrar") && { hash: "#/operacion?seccion=administrar", titulo: "Configuración y respaldos", describe: "Funciones activas y copias" },
    ] },
    // Ayuda al final del menú: la guía del equipo no compite con las áreas de trabajo.
    { id: "guia", titulo: "Cómo funciona JACOMIND", icono: "guia", items: [puede("guia.ver") && { hash: "#/guia", titulo: "Cómo funciona JACOMIND", describe: "Guía del proyecto, los modelos y el asistente" }] },
  ];
  return areas
    .map(a => ({ ...a, items: a.items.filter(Boolean).filter(i => a.id === "inicio" || i.hash !== inicio) }))
    .filter(a => a.items.length);
}

/**
 * Elemento activo: el más específico que coincide con la ruta. Inicio solo queda activo si nada más coincide,
 * para que una pantalla nunca tenga dos destinos activos.
 */
export function activoEn(areas, partes, q) {
  let mejor = null;
  for (const a of areas) for (const i of a.items) {
    const destinos = [i.hash, ...(i.rutas || [])];
    destinos.forEach((d, n) => {
      if (!coincide(d, partes, q)) return;
      const peso = (a.id === "inicio" ? 0 : 1000) + d.length - n * 0.1;
      if (!mejor || peso > mejor.peso) mejor = { area: a, item: i, peso };
    });
  }
  return mejor ? { area: mejor.area, item: mejor.item } : null;
}
