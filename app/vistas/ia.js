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
  if (/sombra|experimental/.test(estado)) return "En uso";   // los seis modelos están en uso
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
 * Modelo de IA de cada capacidad, según las fichas técnicas de docs/: qué algoritmo es, con qué aprende, qué variables
 * usa (con su significado) y qué entrega. «hoy» aclara cuando la pantalla usa además o en su lugar un cálculo sin IA.
 */
export const FICHAS = {
  compra_30d: {
    ia: true, modelo: "Regresión logística",
    queEs: "Un modelo de aprendizaje supervisado que aprende, a partir de miles de ejemplos del pasado, cuánto pesa cada señal del cliente en la posibilidad de que vuelva a comprar. Combina las señales en una suma ponderada y la convierte en una probabilidad entre 0 % y 100 %.",
    aprende: "Toma una «fotografía» de cada cliente al cierre de cada mes y la compara con lo que pasó después: si compró o no en los 30 días siguientes. Da más peso a los meses recientes (semivida de 180 días) y ajusta el nivel general a la tasa de compra del último mes completo, sin cambiar el orden entre clientes.",
    variables: [
      ["Días desde la última compra", "Cuánto hace que el cliente compró por última vez. Se usa en escala logarítmica: pasar de 5 a 10 días pesa más que pasar de 200 a 205."],
      ["Compras en los últimos 30 días", "Número de operaciones del último mes: indica si el cliente está activo ahora."],
      ["Compras en los últimos 90 días", "Número de operaciones del último trimestre: muestra su ritmo reciente."],
      ["Compras totales de su historial", "Cuántas operaciones lleva desde que es cliente, en escala logarítmica: separa a los clientes nuevos de los de siempre."],
    ],
    resultado: "La probabilidad de que el cliente compre en los próximos 30 días. Desde el 40 % la cartera sugiere «Revisar oportunidad de recompra».",
    noUsa: "No usa el identificador del cliente, la ciudad, el sector, el canal ni las coberturas.",
    tecnico: "compra_30d-m13-P · scikit-learn LogisticRegression (L2, C = 10) · variables escaladas con media y desviación del entrenamiento · umbral 40 %",
    ficha: "docs/modelo-compra.md",
  },
  inactividad_60d: {
    ia: true, modelo: "Regresión logística",
    queEs: "El mismo tipo de modelo de aprendizaje supervisado que M1, entrenado para otra pregunta: de los clientes que llevan entre 30 y 89 días sin comprar, cuáles llegarán a 90 días sin compra en los próximos 60.",
    aprende: "Con fotografías mensuales de clientes que estaban entre 30 y 89 días sin comprar, marcadas según si después llegaron o no a 90 días sin compra. Se probaron 6 configuraciones (dos grupos de variables × tres niveles de regularización) y se eligió la que mejor ordenaba a los 10 primeros.",
    variables: [
      ["Días desde la última compra", "Cuánto lleva sin comprar (escala logarítmica). Es la señal más fuerte."],
      ["Días con compra en 30, 90 y 180 días", "En cuántos días distintos compró en cada ventana: mide su actividad a corto y largo plazo."],
      ["Días de compra totales", "En cuántos días distintos ha comprado desde el inicio (escala logarítmica)."],
    ],
    probado: "También se entrenó una versión ampliada que suma el cambio de actividad, el intervalo habitual entre compras y su irregularidad, el retraso frente a su ciclo y el importe de 90 días; no mejoró a la versión básica.",
    resultado: "Una probabilidad de llegar a 90 días sin comprar en los próximos 60, y una lista ordenada de mayor a menor riesgo.",
    hoy: "La lista que ves hoy se ordena con un cálculo del ritmo de compra de los últimos 180 días (Poisson), que en la comparación con datos de práctica acertó igual o mejor que la regresión.",
    tecnico: "scikit-learn LogisticRegression (L2, lbfgs; mejor configuración: variables básicas, C = 0,1) · variables inactividad_60d-variables-v1 · selección por precisión media a 10",
    ficha: "docs/modelo-inactividad.md",
  },
  proxima_compra: {
    ia: true, modelo: "Modelo de supervivencia de Cox (con regularización)",
    queEs: "Un modelo de aprendizaje que no predice «sí o no», sino cuándo: estima, día a día, cómo crece la posibilidad de que el cliente vuelva a comprar. Es el tipo de modelo que se usa para estimar tiempos hasta un evento, y sabe aprovechar a los clientes que todavía no han vuelto a comprar (casos «censurados») sin descartarlos.",
    aprende: "De la historia de compras: para cada fotografía mensual mide cuántos días pasaron hasta la siguiente compra. Aprende cómo cada variable acelera o retrasa esa compra respecto de una curva base de toda la cartera. La regularización (α = 0,1) evita que se ajuste de más a pocos clientes.",
    variables: [
      ["Días desde la última compra", "Cuánto lleva sin comprar."],
      ["Días con compra en 90 y 180 días", "Su actividad reciente y de medio plazo: más actividad adelanta la próxima compra."],
      ["Días de compra totales", "Cuánta historia tiene."],
      ["Intervalo habitual entre compras", "Cada cuántos días suele comprar (mediana)."],
      ["Irregularidad de esos intervalos", "Cuánto varían: es la variable más estable del modelo; los clientes irregulares tienden a tardar más."],
      ["Historia insuficiente", "Si tiene muy pocas compras para medir intervalos."],
      ["Importe de los últimos 90 días", "Cuánto compró en pesos en el último trimestre."],
    ],
    resultado: "Una curva de probabilidad acumulada por cliente. De ella sale la ventana de contacto: desde la fecha en que la compra llega al 10 % de posibilidad hasta la fecha en que llega al 50 %.",
    hoy: "Si un cliente no tiene datos suficientes, se usa la curva de toda la cartera (Kaplan–Meier), igual para todos.",
    tecnico: "scikit-survival CoxPHSurvivalAnalysis (L2, α = 0,1, empates de Breslow) · variables proxima_compra-variables-v1 · mejora el Brier integrado un 10,3 % frente a la curva poblacional",
    ficha: "docs/modelo-proxima-compra.md",
  },
  venta_cruzada: {
    ia: true, modelo: "Regresión logística de ranking",
    queEs: "Un modelo de aprendizaje supervisado que puntúa cada par cliente–producto: cuanto más alto el puntaje, más encaja ese producto con ese cliente. Con los puntajes ordena los productos que el cliente todavía no tiene y propone los tres primeros.",
    aprende: "De los productos que los clientes compraron por primera vez después de cada cierre: aprende qué rasgos del cliente y del producto anticipan esa primera compra. Un solo modelo sirve para todos los productos, con una señal propia para cada uno.",
    variables: [
      ["Actividad del cliente", "Días desde su última compra, días con compra (totales, en 90 y en 180 días) e importe de los últimos 90 días."],
      ["Amplitud del cliente", "Cuántos productos distintos tiene ya."],
      ["Popularidad relativa del producto", "Qué tan comprado es el producto entre todos los clientes."],
      ["Afinidad máxima", "Qué tanto suelen comprar este producto los clientes que tienen alguno de los productos de este cliente."],
      ["Coocurrencia relativa", "Con qué frecuencia aparece el producto junto a los que ya tiene el cliente."],
      ["Identidad del producto", "Una señal por producto que recoge su atractivo propio."],
    ],
    resultado: "Un puntaje por producto (sin convertirlo en probabilidad) y el orden de las tres propuestas, siempre entre productos compatibles que el cliente aún no tiene.",
    noUsa: "No usa el identificador del cliente, información posterior al cierre, precios de las operaciones ni coberturas futuras.",
    hoy: "En la comprobación con datos de práctica el modelo acertó un poco más que la popularidad en la primera propuesta (13,3 % frente a 12,1 %), pero la diferencia no fue concluyente; por eso las propuestas que ves hoy se ordenan por popularidad filtrada por compatibilidad.",
    tecnico: "Regresión logística L2 compartida (variables básicas, C = 0,1) · métrica HitRate@1 · respaldo por popularidad para productos con menos de 10 compras",
    ficha: "docs/modelo-venta-cruzada.md",
  },
  demanda: {
    ia: false, modelo: "Series de tiempo (sin modelo de IA)",
    queEs: "El pronóstico no usa un modelo de IA: proyecta cada serie con métodos de series de tiempo (suavizamiento exponencial simple y Holt con tendencia amortiguada) o con referencias simples, y elige por serie el que menos se equivocó en meses anteriores.",
    variables: [["Historia mensual de cada serie", "Ventas en pesos por familia y unidades por producto; al menos 12 meses para los métodos de suavizamiento."]],
    resultado: "Las ventas esperadas de los próximos 1 a 3 meses, con el margen de error de meses anteriores.",
    tecnico: "SES y Holt amortiguado frente a referencias (último mes, media de 3 meses) · selección por menor MAE",
    ficha: "docs/modelo-demanda.md",
  },
  anomalias: {
    ia: true, modelo: "Isolation Forest (bosque de aislamiento)",
    queEs: "Un modelo de aprendizaje no supervisado para detectar rarezas: no necesita ejemplos marcados de errores. Construye 200 árboles que parten los datos al azar; las operaciones raras quedan aisladas en muy pocos cortes, y eso se convierte en un puntaje de rareza.",
    aprende: "De todas las ventas y compras válidas, un bosque para ventas y otro para compras. Cada operación se describe frente a su propio historial (mismo producto, moneda y unidad), así que el modelo aprende qué combinaciones de desvíos son poco habituales.",
    variables: [
      ["Desvío del precio por unidad", "Cuánto se aparta el precio de la mediana de las operaciones anteriores del mismo producto, en escala logarítmica y medido en desviaciones típicas robustas."],
      ["Desvío de la cantidad", "Lo mismo para la cantidad."],
      ["Desvío del importe", "Lo mismo para el importe total de la operación (en una de las dos configuraciones)."],
    ],
    resultado: "Un puntaje de rareza por operación. Las más raras de cada mes, hasta la capacidad de revisión del equipo, pasan a la cola «Operaciones por revisar».",
    noUsa: "No usa la TRM ni el importe en pesos (un cambio solo de tipo de cambio no altera el puntaje), ni identificadores de cliente, proveedor o producto.",
    hoy: "La cola que ves hoy prioriza con reglas sobre esos mismos desvíos (mediana y MAD), porque el bosque no mostró una ventaja clara en la evaluación.",
    tecnico: "scikit-learn IsolationForest (200 árboles, sin bootstrap, max_features = 1, submuestra 64 o 128) · puntaje = −score_samples",
    ficha: "docs/modelo-anomalias.md",
  },
};

/** Bloque del modelo de IA de una capacidad. */
export function fichaModeloHtml(id, { titulo = true } = {}) {
  const f = FICHAS[id];
  if (!f) return "";
  return `${titulo ? `<h3>${esc(CAPACIDAD[id] || id)}</h3>` : ""}
    <p class="ia-metodo"><span class="sello ${f.ia ? "sello-ia" : "sello-practica"}">${f.ia ? "Modelo de IA" : "Sin IA"}</span> <strong>${esc(f.modelo)}</strong></p>
    <p>${esc(f.queEs)}</p>
    ${f.aprende ? `<p class="etiqueta-datos">Cómo aprende</p><p>${esc(f.aprende)}</p>` : ""}
    <p class="etiqueta-datos">Variables que usa</p>
    <dl class="ia-variables">${f.variables.map(([n, d]) => `<div><dt>${esc(n)}</dt><dd>${esc(d)}</dd></div>`).join("")}</dl>
    <p class="etiqueta-datos">Qué entrega</p><p>${esc(f.resultado)}</p>
    ${f.noUsa ? `<p class="muted">${esc(f.noUsa)}</p>` : ""}
    ${f.probado ? `<p class="muted">${esc(f.probado)}</p>` : ""}
    ${f.hoy ? `<p class="ia-hoy">${esc(f.hoy)}</p>` : ""}
    <details class="ia-tecnico"><summary>Detalle técnico</summary><p><code>${esc(f.tecnico)}</code></p>
      <p><a href="https://github.com/isabeldc13008/JACOMIND/blob/main/${esc(f.ficha)}" target="_blank" rel="noopener">Ficha completa: ${esc(f.ficha)}<span class="oculto-visual"> (se abre en una pestaña nueva)</span></a></p></details>`;
}

/** Tarjetas de todas las capacidades visibles. */
function fichasHtml(ids) {
  const visibles = ORDEN.filter(id => ids.has(id) && FICHAS[id]);
  if (!visibles.length) return "";
  return `<section class="panel" aria-labelledby="t-fichas"><h2 id="t-fichas">Los modelos de IA y sus variables</h2>
    <p class="muted">Qué modelo de inteligencia artificial responde cada pregunta, cómo aprende, qué variables mira y qué entrega. Un modelo de IA aprende de las compras pasadas; sus resultados son estimaciones que apoyan la decisión de una persona.</p>
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
    ${FICHAS[m.modelo_id] ? `<div class="ia-ficha en-detalle"><h3>El modelo de IA y sus variables</h3>${fichaModeloHtml(m.modelo_id, { titulo: false })}</div>` : ""}
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
  }, { leyenda: "Capacidades analíticas visibles para tu perfil. Todas están en uso: sus resultados apoyan la decisión de una persona." });
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
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Qué estima cada modelo, con qué datos, cómo se evaluó y si tiene avisos. Las métricas técnicas están en el detalle de cada uno.",
    contexto: [d.generado_en ? { etiqueta: "Evaluación generada", valor: esc(fechaHora(d.generado_en)) } : null, { etiqueta: "Origen de la evaluación", valor: d.origen_datos === "sintetico" ? "datos de práctica" : esc(d.origen_datos || "—") }] })}
  ${pestanasModelos("ia")}
  ${d.estado !== "ok" ? vacio("Aún no se ha generado el resumen de los modelos.", `${esc(d.mensaje || "")} Se genera con <code>${esc(d.comando || "")}</code>.`) + fichasHtml(idsVisibles) : `
  ${hallazgo({
    que: `<strong>${num(d.modelos.length + (monOk && !d.modelos.some(m => m.modelo_id === "demanda") && monOk.modelos.some(m => m.modelo_id === "demanda") ? 1 : 0))} capacidades analíticas</strong> visibles para tu perfil: todas en uso.`,
    porque: esc(d.advertencia),
    accion: monOk ? `<a class="boton-sec" href="#/monitoreo">${conAviso ? `Ver avisos (${num(conAviso)} ${conAviso === 1 ? "modelo" : "modelos"} con avisos)` : "Ver el seguimiento"}</a>` : "",
  })}
  ${mon instanceof Error ? `<p class="muted">No se pudo cargar el monitoreo. <button type="button" class="enlace" data-reintentar>Volver a intentar</button></p>` : ""}
  <section class="panel"><h2>Capacidades y su estado</h2>${matrizModelos(d, monOk)}</section>
  ${fichasHtml(idsVisibles)}
  <h2>Detalle de cada modelo</h2>
  ${d.modelos.map(evaluacionHtml).join("")}`}`;
}
