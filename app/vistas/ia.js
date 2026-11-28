// V25 Modelos y monitoreo · resumen: qué estima cada modelo, su disponibilidad, fecha, estado de validación y avisos.
// Compone /api/ia (explicación y evaluación, cartera.ver) y /api/monitoreo (avisos, monitoreo.ver) sin ampliar permisos.
import { $vista, api, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, nuevoTurno, num, pct, puede, vigente } from "../nucleo.js";
import { encabezado, hallazgo, pestanas, tablaHtml, vacio } from "../ui.js";

const ENLACES = {
  compra_30d: () => puede("cartera.ver") && ["#/agenda", "Ver en la cartera"],
  inactividad_60d: () => puede("prevencion.ver") && ["#/prevencion", "Ver la lista de prevención"],
  proxima_compra: () => puede("proxima.ver") && ["#/proxima", "Ver cuándo contactar"],
  venta_cruzada: () => puede("venta_cruzada.ver") && ["#/venta-cruzada", "Ver productos sugeridos"],
  demanda: () => (puede("demanda.ver_cop") || puede("demanda.ver_unidades")) && ["#/demanda", "Ver el pronóstico"],
  anomalias: () => puede("anomalias.ver") && ["#/anomalias", "Ver operaciones por revisar"],
};
export const CAPACIDAD = {
  compra_30d: "¿Es probable que el cliente compre en los próximos 30 días?",
  inactividad_60d: "¿Podría el cliente llegar a 90 días sin comprar?",
  proxima_compra: "¿Cuándo es probable que vuelva a comprar?",
  venta_cruzada: "¿Qué producto que aún no tiene podría interesarle?",
  demanda: "¿Cuánto se venderá en los próximos meses?",
  anomalias: "¿Qué ventas o compras se apartan de lo habitual?",
};
const ORDEN = Object.keys(CAPACIDAD);
const TIPO = { ia: "Modelo", regla: "Regla", referencia: "Referencia" };
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
const periodo = cortes => {
  const ms = cortes.map(c => MESES[Number(c.slice(5, 7)) - 1]);
  return `${ms.length > 1 ? `${ms.slice(0, -1).join(", ")} y ${ms.at(-1)}` : ms[0]} de ${cortes.at(-1).slice(0, 4)}`;
};
const dec3 = x => x == null ? "—" : x.toFixed(3).replace(".", ",");
const SELLO = { sin_informacion: "sello-practica", pendiente_madurez: "sello-practica", no_comparable: "sello-prueba", sin_problemas: "sello-ok", requiere_revision: "sello-alerta", publicacion_rechazada: "sello-alerta" };

/** Disponibilidad en palabras a partir del estado publicado; nunca verde por ausencia de evaluación. */
export function disponibilidad(estado = "") {
  if (/operativo/.test(estado)) return /demostraci/.test(estado) ? "En uso (modo demostración)" : "En uso";
  if (/sombra|experimental/.test(estado)) return "En prueba";
  if (/desactiv/.test(estado)) return "Desactivado";
  return estado ? estado : "No publicado";
}
export function validacion(estado = "") {
  const m = estado.match(/decisi[oó]n ([a-záéíóú ]+?)(?:\s*·|$)/i);
  if (m) return `Validación ${m[1].trim() === "inconcluso" ? "inconclusa: no demuestra mejora sobre la regla" : m[1].trim()}`;
  if (/referencia conservada/.test(estado)) return "Se mantiene el método de referencia";
  if (/operativo/.test(estado)) return "Aprobado para uso en esta demostración";
  return "Sin evaluación publicada";
}

/** Pestañas del centro de modelos: solo las autorizadas (el monitoreo exige monitoreo.ver). */
export function pestanasModelos(activa) {
  const items = [];
  if (puede("cartera.ver")) items.push(["ia", "Qué estima cada modelo", "#/ia"]);
  if (puede("monitoreo.ver")) items.push(["monitoreo", "Avisos y seguimiento", "#/monitoreo"]);
  return items.length > 1 ? pestanas(items, activa, "Secciones de modelos") : "";
}

/**
 * Qué modelo usa cada capacidad y con qué datos, según las fichas técnicas de docs/ (método publicado hoy).
 * «probado» resume el candidato evaluado que no se publicó, para no presentarlo como el que está en uso.
 */
export const FICHAS = {
  compra_30d: {
    tipo: "Modelo de IA", metodo: "Regresión logística",
    como: "Aprende de las compras pasadas qué combinación de señales precede a una compra y da a cada cliente una probabilidad de comprar en 30 días. Da más peso a los meses recientes (semivida de 180 días) y ajusta el nivel a la tasa del último mes completo.",
    variables: ["Días desde la última compra", "Compras en los últimos 30 días", "Compras en los últimos 90 días", "Número total de compras de su historial"],
    noUsa: "No usa el identificador del cliente, la ciudad, el sector, el canal ni las coberturas.",
    tecnico: "compra_30d-m13-P · scikit-learn LogisticRegression (L2, C = 10) · umbral 40 %", ficha: "docs/modelo-compra.md",
  },
  inactividad_60d: {
    tipo: "Modelo estadístico", metodo: "Ritmo de compra (Poisson)",
    como: "Calcula cada cuánto compra el cliente en los últimos 180 días y, con ese ritmo, la probabilidad de que no compre en los días que le faltan para llegar a 90 sin comprar. A los clientes con poca historia los acerca al ritmo medio de la cartera.",
    variables: ["Días de compra en los últimos 180 días", "Días que lleva sin comprar (y cuántos le faltan para 90)", "Tiempo observado del cliente", "Ritmo medio de toda la cartera (para suavizar)"],
    probado: "También se probó una regresión logística con variables de ritmo de compra (frecuencias, intervalos entre compras, importe en 90 días); no superó a la regla de más días sin comprar.",
    tecnico: "m21-poisson-180 · p = e^(−λ·w), λ suavizado con m = 180 días", ficha: "docs/modelo-inactividad.md",
  },
  proxima_compra: {
    tipo: "Modelo de IA", metodo: "Modelo de supervivencia de Cox",
    como: "Estima, día a día, cómo crece la posibilidad de que el cliente vuelva a comprar y publica la ventana entre el 10 % y el 50 % de esa posibilidad. Si un cliente no tiene datos suficientes, usa la curva de toda la cartera.",
    variables: ["Días desde la última compra", "Días de compra en los últimos 90 y 180 días", "Días de compra totales", "Intervalo habitual entre compras (mediana)", "Qué tan irregulares son esos intervalos (dispersión)", "Si tiene poca historia", "Importe en pesos de los últimos 90 días"],
    tecnico: "Cox con regularización L2 (scikit-survival) · respaldo: Kaplan–Meier poblacional", ficha: "docs/modelo-proxima-compra.md",
  },
  venta_cruzada: {
    tipo: "Reglas de referencia", metodo: "Popularidad filtrada por compatibilidad",
    como: "Ordena los productos que el cliente todavía no tiene según cuántos clientes los compran, y descarta los que no son compatibles con lo que ya tiene. Muestra hasta tres.",
    variables: ["Productos que el cliente ya compró", "Popularidad de cada producto (clientes distintos que lo tienen)", "Reglas de compatibilidad del catálogo"],
    probado: "También se probó una regresión logística con datos del cliente (recencia, días de compra, importe en 90 días, número de productos) y del producto (popularidad, afinidad y coocurrencia); no superó a la popularidad, así que se conservó la referencia.",
    tecnico: "compat-v1 · candidato evaluado: regresión logística L2 (HitRate@1)", ficha: "docs/modelo-venta-cruzada.md",
  },
  demanda: {
    tipo: "Modelo estadístico", metodo: "Series de tiempo (suavizamiento exponencial)",
    como: "Para cada familia y producto elige el método que menos se equivocó en meses anteriores: repetir el último mes, el promedio de los últimos 3 meses, suavizamiento exponencial simple o Holt con tendencia amortiguada. El total es la suma de las familias.",
    variables: ["Ventas mensuales de cada familia (en pesos)", "Unidades mensuales de cada producto", "Al menos 12 meses de historia para los métodos de suavizamiento"],
    noUsa: "No usa clientes, precios futuros ni estacionalidad.",
    tecnico: "SES y Holt amortiguado frente a referencias; selección por menor MAE por serie y horizonte", ficha: "docs/modelo-demanda.md",
  },
  anomalias: {
    tipo: "Reglas estadísticas", metodo: "Comparación con lo habitual (mediana y MAD)",
    como: "Compara cada venta o compra con hasta 60 operaciones anteriores del mismo producto, moneda y unidad. Señala las que se apartan mucho y prioriza las más raras hasta la capacidad de revisión del equipo.",
    variables: ["Precio por unidad frente a su mediana habitual", "Cantidad frente a su mediana habitual", "Importe de la operación frente a su mediana habitual", "Número de operaciones anteriores (mínimo 5)"],
    noUsa: "No usa la TRM ni el importe en pesos, ni identificadores de cliente, proveedor o producto.",
    probado: "También se probó Isolation Forest (un bosque de 200 árboles de IA); no aportó valor demostrable frente a las reglas.",
    tecnico: "mediana_mad · señal si |z| ≥ 3,5, precio fuera de 0,67–1,5 veces o cantidad fuera de 0,2–3 veces", ficha: "docs/modelo-anomalias.md",
  },
};

const SELLO_TIPO = t => /IA/.test(t) ? "sello-ia" : "sello-practica";

/** Bloque «Qué modelo usa y qué datos mira» de una capacidad. */
export function fichaModeloHtml(id, { titulo = true } = {}) {
  const f = FICHAS[id];
  if (!f) return "";
  return `${titulo ? `<h3>${esc(CAPACIDAD[id] || id)}</h3>` : ""}
    <p class="ia-metodo"><span class="sello ${SELLO_TIPO(f.tipo)}">${esc(f.tipo)}</span> <strong>${esc(f.metodo)}</strong></p>
    <p>${esc(f.como)}</p>
    <p class="etiqueta-datos">Variables que utiliza</p>
    <ul class="ia-variables">${f.variables.map(v => `<li>${esc(v)}</li>`).join("")}</ul>
    ${f.noUsa ? `<p class="muted">${esc(f.noUsa)}</p>` : ""}
    ${f.probado ? `<p class="muted">${esc(f.probado)}</p>` : ""}
    <p class="muted ia-tecnico">Nombre técnico: <code>${esc(f.tecnico)}</code> · Ficha: <a href="https://github.com/isabeldc13008/JACOMIND/blob/main/${esc(f.ficha)}" target="_blank" rel="noopener">${esc(f.ficha)}<span class="oculto-visual"> (se abre en una pestaña nueva)</span></a></p>`;
}

/** Tarjetas de todas las capacidades visibles. */
function fichasHtml(ids) {
  const visibles = ORDEN.filter(id => ids.has(id) && FICHAS[id]);
  if (!visibles.length) return "";
  return `<section class="panel" aria-labelledby="t-fichas"><h2 id="t-fichas">Qué modelo usa cada uno y qué datos mira</h2>
    <p class="muted">El método que está publicado hoy y las variables con las que calcula. «Modelo de IA» aprende de los datos; «modelo estadístico» y «reglas» siguen una fórmula fija.</p>
    <div class="ia-fichas">${visibles.map(id => `<article class="ia-ficha" id="ficha-${esc(id)}">${fichaModeloHtml(id)}</article>`).join("")}</div></section>`;
}

function tablaMetodos(m) {
  if (m.tabla) return tablaHtml({ cabeceras: m.tabla.columnas, numericas: new Set(m.tabla.columnas.map((_, i) => i).filter(i => i > 0)), filas: m.tabla.filas.map(f => f.map(v => esc(v))) });
  const mejorTop10 = Math.max(...m.filas.map(f => f.aciertos_top10 ?? -1));
  const briers = m.filas.map(f => f.brier).filter(b => b != null);
  const mejorBrier = briers.length ? Math.min(...briers) : null;
  const b = (cond, txt) => cond ? `<strong>${txt}</strong>` : txt;
  return tablaHtml({ cabeceras: ["Método", "Tipo", "Aciertos entre los 10 primeros", "Entre los 20 primeros", `Probabilidad media (real ${pct(m.tasa_observada)})`, "Error de Brier (menos es mejor)"], numericas: new Set([2, 3, 4, 5]),
    filas: m.filas.map(f => [`${f.actual ? "<strong>" : ""}${esc(f.metodo)}${f.actual ? '</strong> <span class="chip fuerte">en uso</span>' : ""}<span class="muted">${esc(f.descripcion)}</span>`, esc(TIPO[f.tipo] || f.tipo),
      f.aciertos_top10 == null ? "—" : b(f.aciertos_top10 === mejorTop10, `${num(f.aciertos_top10)} de ${num(f.de_top10)}`), f.aciertos_top20 == null ? "—" : num(f.aciertos_top20),
      f.probabilidad_media == null ? (f.tipo === "regla" ? "No da probabilidad" : "—") : esc(pct(f.probabilidad_media)), f.brier == null ? "—" : b(f.brier === mejorBrier, dec3(f.brier))]) });
}

function evaluacionHtml(m) {
  const enlace = ENLACES[m.modelo_id]?.();
  return `<details class="panel" id="modelo-${esc(m.modelo_id)}"><summary>${esc(m.titulo)}: cómo se usa y cómo se evaluó</summary>
    <p><strong>Pregunta que responde:</strong> ${esc(m.pregunta)}</p>
    <p><strong>Dónde se usa:</strong> ${esc(m.uso)} ${enlace ? `<a href="${enlace[0]}">${esc(enlace[1])}</a>` : ""}</p>
    <ul>${m.lectura.map(l => `<li>${esc(l)}</li>`).join("")}</ul>
    ${FICHAS[m.modelo_id] ? `<div class="ia-ficha en-detalle"><h3>Qué modelo usa y qué datos mira</h3>${fichaModeloHtml(m.modelo_id, { titulo: false })}</div>` : ""}
    <h3>Cómo se evaluó</h3>
    ${tablaMetodos(m)}
    <p class="muted">Medido en ${num(m.casos)} casos de ${esc(periodo(m.periodo))} (${num(m.eventos)} con el resultado buscado). Versión ${esc(m.version)}. Estado: ${esc(m.estado)}.</p></details>`;
}

/** Matriz de capacidades: une explicación (ia) y monitoreo (mon) por modelo, solo con lo que el perfil puede ver. */
export function matrizModelos(ia, mon) {
  const porId = new Map();
  for (const m of ia?.modelos || []) porId.set(m.modelo_id, { id: m.modelo_id, titulo: m.titulo, estado: m.estado });
  for (const m of mon?.modelos || []) porId.set(m.modelo_id, { ...(porId.get(m.modelo_id) || { id: m.modelo_id, titulo: m.nombre }), mon: m });
  const filas = [...porId.values()].sort((a, b) => ORDEN.indexOf(a.id) - ORDEN.indexOf(b.id));
  if (!filas.length) return vacio("No hay modelos visibles para tu perfil.");
  const conMon = !!mon;
  return tablaHtml({
    cabeceras: ["Qué responde", "Disponibilidad", "Fecha de los datos", "Validación", ...(conMon ? ["Seguimiento y avisos"] : []), "Dónde verlo"],
    filas: filas.map(f => {
      const enlace = ENLACES[f.id]?.();
      return [`<strong>${esc(CAPACIDAD[f.id] || f.titulo)}</strong><span class="muted">${esc(f.mon?.nombre || f.titulo)}</span>`,
        esc(f.estado ? disponibilidad(f.estado) : f.mon?.ultima_publicacion ? "Publicado" : "No publicado"),
        f.mon?.ultimo_corte ? esc(fechaLarga(f.mon.ultimo_corte)) : "—",
        esc(f.estado ? validacion(f.estado) : "Sin evaluación publicada"),
        ...(conMon ? [f.mon ? `<span class="sello ${SELLO[f.mon.estado] || "sello-practica"}">${esc(f.mon.estado_texto)}</span>${f.mon.avisos_activos.length ? `<span class="muted"><a href="#/monitoreo?modelo=${encodeURIComponent(f.id)}">${num(f.mon.avisos_activos.length)} ${f.mon.avisos_activos.length === 1 ? "aviso" : "avisos"}</a></span>` : '<span class="muted">Sin avisos activos</span>'}` : '<span class="muted">Sin acceso o sin observaciones</span>'] : []),
        enlace ? `<a href="${enlace[0]}">${esc(enlace[1])}</a>` : "—"];
    }),
  }, { leyenda: "Capacidades analíticas visibles para tu perfil. «En prueba» significa que ayuda a revisar, pero no actúa por sí sola." });
}

export async function vistaIA() {
  const turno = nuevoTurno();
  const titulo = "Modelos y monitoreo";
  $vista.innerHTML = `${encabezado({ titulo })}${pestanasModelos("ia")}${estadoHtml("", "Cargando los modelos…")}`;
  const [d, mon] = await Promise.all([api("GET", "/api/ia").catch(e => e), puede("monitoreo.ver") ? api("GET", "/api/monitoreo").catch(e => e) : null]);
  if (!vigente(turno)) return;
  if (d instanceof Error) { $vista.innerHTML = `${encabezado({ titulo })}${pestanasModelos("ia")}${errorHtml(d, { reintentar: true })}`; return; }
  const monOk = mon && !(mon instanceof Error) ? mon : null;
  const conAviso = monOk ? monOk.modelos.filter(m => m.avisos_activos.length).length : 0;
  // Capacidades que el perfil puede ver: las publicadas, las monitoreadas y las que tienen pantalla autorizada.
  const idsVisibles = new Set([...(d.modelos || []).map(m => m.modelo_id), ...(monOk?.modelos || []).map(m => m.modelo_id), ...ORDEN.filter(id => ENLACES[id]?.())]);
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Qué estima cada modelo, si está en uso o en prueba, con qué datos y si tiene avisos. Las métricas técnicas están en el detalle de cada uno.",
    contexto: [d.generado_en ? { etiqueta: "Evaluación generada", valor: esc(fechaHora(d.generado_en)) } : null, { etiqueta: "Origen de la evaluación", valor: d.origen_datos === "sintetico" ? "datos de práctica" : esc(d.origen_datos || "—") }] })}
  ${pestanasModelos("ia")}
  ${d.estado !== "ok" ? vacio("Aún no se ha generado el resumen de los modelos.", `${esc(d.mensaje || "")} Se genera con <code>${esc(d.comando || "")}</code>.`) + fichasHtml(idsVisibles) : `
  ${hallazgo({
    que: `<strong>${num(d.modelos.length + (monOk && !d.modelos.some(m => m.modelo_id === "demanda") && monOk.modelos.some(m => m.modelo_id === "demanda") ? 1 : 0))} capacidades analíticas</strong> visibles para tu perfil: ${(() => { const uso = d.modelos.filter(m => disponibilidad(m.estado).startsWith("En uso")); return uso.length ? `${num(uso.length)} en uso (${esc(uso.map(m => m.titulo).join(", "))}) y el resto en prueba` : "todas en prueba"; })()}.`,
    porque: esc(d.advertencia),
    accion: monOk ? `<a class="boton-sec" href="#/monitoreo">${conAviso ? `Ver avisos (${num(conAviso)} ${conAviso === 1 ? "modelo" : "modelos"} con avisos)` : "Ver el seguimiento"}</a>` : "",
  })}
  ${mon instanceof Error ? `<p class="muted">No se pudo cargar el monitoreo. <button type="button" class="enlace" data-reintentar>Volver a intentar</button></p>` : ""}
  <section class="panel"><h2>Capacidades y su estado</h2>${matrizModelos(d, monOk)}</section>
  ${fichasHtml(idsVisibles)}
  <h2>Detalle de cada modelo</h2>
  ${d.modelos.map(evaluacionHtml).join("")}`}`;
}
