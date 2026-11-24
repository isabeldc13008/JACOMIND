// Componentes compartidos de lectura: encabezado con ubicación y fecha de los datos, franja «Qué pasa → Por qué importa →
// Qué puedes hacer», indicadores, estados, paginación, filtros activos, diálogo accesible y gráficos con tabla equivalente.
import { $vista, S, cop, esc, fechaHora, fechaLarga, mesCorto, mesLargo, millones, num } from "./nucleo.js";

// ---------------------------------------------------------------- encabezado de página
/**
 * Responde «¿Dónde estoy?» (ubicación y título), «¿De qué fecha son los datos?» (contexto) y «¿Cómo regreso?» (volver).
 * contexto: [{etiqueta, valor}] — fecha de los datos, publicación, horizonte, última actualización humana.
 */
export function encabezado({ titulo, descripcion = "", contexto = [], volver = null, estado = "", acciones = "" }) {
  const u = S.ubicacion;
  const migas = u ? `<nav class="migas" aria-label="Estás en"><ol><li>${esc(u.area)}</li>${u.item && u.item !== u.area ? `<li${titulo === u.item ? ' aria-current="page"' : ""}>${esc(u.item)}</li>` : ""}${u.item !== titulo && titulo ? `<li aria-current="page">${esc(titulo)}</li>` : ""}</ol></nav>` : "";
  const ctx = contexto.filter(c => c && c.valor);
  return `<header class="encabezado-pagina">
    ${volver ? `<a class="volver" href="${esc(volver.href)}"><span aria-hidden="true">←</span> ${esc(volver.texto)}</a>` : migas}
    <div class="titulo-fila"><h1>${esc(titulo)}${estado ? ` ${estado}` : ""}</h1>${acciones ? `<div class="acciones-titulo">${acciones}</div>` : ""}</div>
    ${descripcion ? `<p class="descripcion">${descripcion}</p>` : ""}
    ${ctx.length ? `<dl class="contexto-datos">${ctx.map(c => `<div><dt>${esc(c.etiqueta)}</dt><dd>${c.valor}</dd></div>`).join("")}</dl>` : ""}
  </header>`;
}
/** Fecha de los datos y origen sintético, en palabras. */
export const ctxDatos = (corte, etiqueta = "Datos hasta") => corte ? { etiqueta, valor: esc(fechaLarga(corte)) } : null;
// El origen sintético se anuncia una vez en la cabecera global («Datos de práctica») y en el pie; aquí solo se repite
// cuando la pantalla muestra un origen distinto del publicado (p. ej. un cierre anterior real).
export const ctxOrigen = (origen = S.estadoApi?.origen_activo) => origen && origen !== S.estadoApi?.origen_activo ? { etiqueta: "Origen", valor: origen === "sintetico" ? "Datos de práctica" : esc(origen) } : null;

/** Marca visible de estimación experimental. Nunca se oculta detrás de un desplegable. */
export const enPrueba = (texto = "En prueba") => `<span class="sello sello-prueba">${esc(texto)}</span>`;
export const avisoPrueba = (extra = "") => `<p class="aviso-prueba" role="note"><strong>En prueba.</strong> Esta sugerencia no ejecuta acciones automáticamente: ayuda a decidir, pero la decisión es de una persona. ${extra}</p>`;

// ---------------------------------------------------------------- lectura principal
/** Frase que contesta la pregunta principal de la pantalla, con su contexto (periodo, unidad, alcance). */
export function respuesta(frase, contexto = "") {
  return `<div class="respuesta"><p class="frase">${frase}</p>${contexto ? `<p class="contexto">${contexto}</p>` : ""}</div>`;
}

/** Franja distintiva «Qué está pasando → Por qué importa → Qué puedes hacer». */
export function hallazgo({ que, porque = "", accion = "" }) {
  return `<section class="hallazgo" aria-label="Resumen de la situación">
    <div><h2>Qué está pasando</h2><p>${que}</p></div>
    ${porque ? `<div><h2>Por qué importa</h2><p>${porque}</p></div>` : ""}
    ${accion ? `<div><h2>Qué puedes hacer</h2><div class="hallazgo-accion">${accion}</div></div>` : ""}
  </section>`;
}

/** Hasta cuatro indicadores útiles: [{etiqueta, valor, detalle}]. El detalle dice periodo, población o base. */
export function indicadores(items) {
  return `<dl class="indicadores">${items.filter(Boolean).map(i => `<div class="indicador"><dt>${esc(i.etiqueta)}</dt><dd><span class="valor">${i.valor}</span>${i.detalle ? `<span class="detalle">${i.detalle}</span>` : ""}</dd></div>`).join("")}</dl>`;
}

/** Estado vacío: qué falta y qué hacer después. */
export function vacio(titulo, texto = "", accion = "") {
  return `<div class="vacio" role="status"><p><strong>${esc(titulo)}</strong></p>${texto ? `<p>${texto}</p>` : ""}${accion ? `<p>${accion}</p>` : ""}</div>`;
}

/** Pestañas de una misma pantalla, como enlaces (conservan Atrás/Adelante y acceso directo). */
export function pestanas(items, activo, etiqueta = "Secciones") {
  return `<nav class="pestanas" aria-label="${esc(etiqueta)}">${items.map(([k, t, h]) => `<a href="${esc(h)}" ${k === activo ? 'aria-current="page"' : ""}>${esc(t)}</a>`).join("")}</nav>`;
}

/** «Mostrando X–Y de Z» con anterior/siguiente escritos. */
export function paginacion({ pagina, tam, total, href }) {
  const paginas = Math.max(1, Math.ceil(total / tam));
  const desde = total ? (pagina - 1) * tam + 1 : 0, hasta = Math.min(total, pagina * tam);
  return `<nav class="paginacion" aria-label="Páginas"><p>Mostrando <strong>${num(desde)}–${num(hasta)}</strong> de <strong>${num(total)}</strong></p>
    <div class="fila">${pagina > 1 ? `<a class="boton-sec" href="${esc(href(pagina - 1))}"><span aria-hidden="true">←</span> Página anterior</a>` : ""}
    <span class="muted">Página ${num(pagina)} de ${num(paginas)}</span>
    ${pagina < paginas ? `<a class="boton-sec" href="${esc(href(pagina + 1))}">Página siguiente <span aria-hidden="true">→</span></a>` : ""}</div></nav>`;
}

/** Filtros aplicados con opción de quitar cada uno y todos. activos: [{texto, quitar}] */
export function filtrosActivos(activos, quitarTodos) {
  if (!activos.length) return '<p class="filtros-activos muted">Sin filtros: se muestra todo.</p>';
  return `<div class="filtros-activos" role="status"><span>Filtros aplicados:</span>${activos.map(a => `<a class="chip-filtro" href="${esc(a.quitar)}">${esc(a.texto)} <span aria-hidden="true">×</span><span class="oculto-visual"> (quitar este filtro)</span></a>`).join("")}
    <a class="boton-sec" href="${esc(quitarTodos)}">Quitar filtros</a></div>`;
}

// ---------------------------------------------------------------- diálogo accesible (sustituye a alert/confirm)
/** Confirmación con objeto, alcance y resultado esperado. Devuelve una promesa con true/false. */
export function confirmar({ titulo, mensaje, confirmar: si = "Confirmar", cancelar = "Cancelar" }) {
  return new Promise(resolve => {
    const previo = document.activeElement;
    const d = document.createElement("dialog");
    d.className = "dialogo";
    d.setAttribute("aria-labelledby", "dialogo-titulo");
    d.innerHTML = `<h2 id="dialogo-titulo">${esc(titulo)}</h2><div class="dialogo-cuerpo">${mensaje}</div>
      <div class="fila dialogo-acciones"><button type="button" data-si>${esc(si)}</button><button type="button" class="sec" data-no>${esc(cancelar)}</button></div>`;
    document.body.append(d);
    const cerrar = v => { d.close(); d.remove(); previo?.focus?.(); resolve(v); };
    d.querySelector("[data-si]").addEventListener("click", () => cerrar(true));
    d.querySelector("[data-no]").addEventListener("click", () => cerrar(false));
    d.addEventListener("cancel", e => { e.preventDefault(); cerrar(false); });
    d.showModal();
    d.querySelector("[data-no]").focus();
  });
}

// ---------------------------------------------------------------- barras y verificación
/**
 * Barras horizontales desde cero: etiqueta, longitud proporcional y valor escrito (no depende del color).
 * items: [{etiqueta, valor, texto, href?, activo?, nota?}]. Con `signo`, los negativos usan otro trazo y el signo escrito.
 */
export function barras(items, { titulo = "", etiquetaAria = "", signo = false, vacio: textoVacio = "Sin datos para graficar." } = {}) {
  if (!items.length) return `<p class="muted">${esc(textoVacio)}</p>`;
  const max = Math.max(1e-9, ...items.map(i => Math.abs(i.valor || 0)));
  const fila = i => {
    const ancho = (Math.abs(i.valor || 0) / max * 100).toFixed(1);
    const neg = signo && i.valor < 0;
    const cuerpo = `<span class="b-et">${esc(i.etiqueta)}${i.nota ? `<span class="b-nota">${esc(i.nota)}</span>` : ""}</span>
      <span class="b-pista" aria-hidden="true"><span class="b-relleno ${neg ? "neg" : ""}" style="width:${ancho}%"></span></span>
      <span class="b-val">${esc(i.texto ?? String(i.valor))}</span>`;
    return i.href
      ? `<li><a class="b-fila ${i.activo ? "activo" : ""}" href="${esc(i.href)}" ${i.activo ? 'aria-current="true"' : ""}>${cuerpo}${i.activo ? '<span class="oculto-visual"> (filtro aplicado; pulsa para quitarlo)</span>' : ""}</a></li>`
      : `<li><div class="b-fila ${i.activo ? "activo" : ""}">${cuerpo}</div></li>`;
  };
  return `${titulo ? `<h3>${esc(titulo)}</h3>` : ""}<ul class="barras" aria-label="${esc(etiquetaAria || titulo)}">${items.map(fila).join("")}</ul>`;
}

/**
 * Nivel 3 de lectura: tabla exacta, fuente, filtros, fecha de actualización y regla o versión.
 * tabla: {cabeceras: [...], filas: [[...]], numericas: Set(índices)}
 */
export function verDatos({ titulo = "Ver cifras exactas y cómo se calcularon", tabla = null, fuente = "", filtros = "", actualizado = "", regla = "", extra = "", abierto = false } = {}) {
  const meta = [fuente && `<dt>Fuente</dt><dd>${fuente}</dd>`, filtros && `<dt>Filtros</dt><dd>${filtros}</dd>`,
    actualizado && `<dt>Fecha de los datos</dt><dd>${actualizado}</dd>`, regla && `<dt>Cómo se calcula</dt><dd>${regla}</dd>`].filter(Boolean).join("");
  return `<details class="ver-datos"${abierto ? " open" : ""}><summary>${esc(titulo)}</summary>${tabla ? tablaHtml(tabla) : ""}${meta ? `<dl class="meta-datos">${meta}</dl>` : ""}${extra}</details>`;
}
export function tablaHtml(tabla, { leyenda = "" } = {}) {
  if (!tabla || !tabla.filas.length) return "";
  return `<div class="tabla" role="region" tabindex="0" aria-label="${esc(leyenda || "Tabla de datos; se puede desplazar")}"><table>${leyenda ? `<caption>${esc(leyenda)}</caption>` : ""}<thead><tr>${tabla.cabeceras.map((c, i) => `<th scope="col" class="${tabla.numericas?.has(i) ? "n" : ""}">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${tabla.filas.map(f => `<tr>${f.map((v, i) => `<td class="${tabla.numericas?.has(i) ? "n" : ""}">${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/** Bloque de detalle técnico (versiones, rutas, datos originales) separado de la lectura principal. */
export function detalleTecnico(contenido, titulo = "Detalle técnico") {
  return `<details class="tecnico"><summary>${esc(titulo)}</summary>${contenido}</details>`;
}

export const fuenteCierre = c => c ? `Cierre ${esc(c.id || c.cierre_id || "")}${c.origen ? ` (${esc(c.origen === "sintetico" ? "datos de práctica" : c.origen)})` : ""}${c.publicado_en ? ` · publicado el ${esc(fechaHora(c.publicado_en))}` : ""}` : "";

// ---------------------------------------------------------------- gráfico temporal
/**
 * Línea mensual: observado con trazo continuo azul; estimado con trazo discontinuo de otro color y puntos huecos.
 * Los nulos son huecos (nunca cero). La banda solo se dibuja si cada punto estimado trae inferior y superior válidos.
 * opciones: {marcas, titulo, unidad, formato, etiquetaEstimado, banda}
 */
export function graficoLinea(hist, proy = [], { marcas = [], titulo = "Serie mensual", unidad = "COP", formato = null, etiquetaEstimado = "Estimado", nivelBanda = "" } = {}) {
  const fmt = formato || (v => millones(v));
  const exacto = formato ? formato : v => cop(v);
  const pts = [...hist.map(p => ({ ...p, tipo: "Observado" })), ...proy.map(p => ({ ...p, tipo: etiquetaEstimado }))];
  if (!pts.length) return '<p class="muted">No hay una serie publicada para graficar.</p>';
  const W = 720, H = 320, m = { l: 104, r: 40, t: 38, b: 50 };
  const vals = pts.flatMap(p => [p.valor, p.inferior, p.superior]).filter(v => v != null);
  const max = Math.max(1, ...vals) * 1.12;
  const x = i => m.l + (pts.length === 1 ? (W - m.l - m.r) / 2 : i * (W - m.l - m.r) / (pts.length - 1));
  const y = v => H - m.b - v / max * (H - m.t - m.b);
  const camino = (desde, hasta) => {
    let d = "", abierto = false;
    for (let i = desde; i <= hasta; i++) {
      const v = pts[i].valor;
      if (v == null) { abierto = false; continue; }
      d += `${abierto ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; abierto = true;
    }
    return d;
  };
  const nh = hist.length;
  const ticks = [0, .25, .5, .75, 1].map(f => max / 1.12 * f);
  const etiquetaEje = t => formato ? formato(t) : millones(t, { unidad: false }).replace(" millones", " mill.");
  const describe = p => `${mesLargo(p.periodo)} · ${p.tipo}: ${p.valor == null ? "sin dato (mes incompleto o no observable)" : `${fmt(p.valor)}${formato ? "" : ` (${cop(p.valor)})`}`}${p.inferior != null && p.superior != null ? ` · banda ${fmt(p.inferior)} a ${fmt(p.superior)}` : ""}`;
  // Banda: solo donde la publicación trae límite inferior y superior; se dibuja como rango vertical por punto, sin
  // inventar la forma entre puntos ni extenderla a horizontes que no la tienen.
  const conBanda = proy.some(p => p.inferior != null && p.superior != null);
  const banda = proy.map((p, k) => p.inferior == null || p.superior == null ? "" : (() => {
    const xi = x(nh + k);
    return `<rect x="${(xi - 9).toFixed(1)}" y="${y(p.superior).toFixed(1)}" width="18" height="${Math.max(2, y(p.inferior) - y(p.superior)).toFixed(1)}" rx="4" fill="var(--estimado-suave)" stroke="var(--serie-est)" stroke-width="1.5" stroke-dasharray="3 3"/>`;
  })()).join("");
  const sep = proy.length && nh ? x(nh - 1) + (x(nh) - x(nh - 1)) / 2 : null;
  const cadaEt = Math.max(1, Math.ceil(pts.length / 6));
  // Etiquetas de valor: en los puntos destacados y en los estimados. Si dos vecinas chocan, la menor va debajo del punto.
  const conEtiqueta = i => pts[i].valor != null && marcas.includes(pts[i].periodo);
  const paso = pts.length > 1 ? (W - m.l - m.r) / (pts.length - 1) : W;
  const abajo = i => [i - 1, i + 1].some(j => j >= 0 && j < pts.length && conEtiqueta(j) && paso < 110 && pts[j].valor > pts[i].valor);
  // Etiquetas del eje: se omite una si quedaría encima de la siguiente.
  const baseEje = i => i % cadaEt === 0 || i === pts.length - 1 || marcas.includes(pts[i].periodo);
  const enEje = i => baseEje(i) && !(i < pts.length - 1 && paso < 72 && baseEje(i + 1));
  const svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(titulo)}. Los valores exactos están en la tabla «Ver valores exactos».">
    ${ticks.map(t => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--rejilla)"/><text x="${m.l - 10}" y="${y(t) + 5}" text-anchor="end" class="eje">${esc(etiquetaEje(t))}</text>`).join("")}
    ${banda}
    ${sep != null ? `<line x1="${sep}" x2="${sep}" y1="${m.t - 6}" y2="${H - m.b}" stroke="var(--texto-3)" stroke-dasharray="3 4"/><text x="${W - 4}" y="${m.t - 12}" text-anchor="end" class="eje fuerte">${esc(etiquetaEstimado)} →</text><text x="${sep - 8}" y="${m.t - 12}" text-anchor="end" class="eje">← Observado</text>` : ""}
    <path d="${camino(0, nh - 1)}" fill="none" stroke="var(--serie-obs)" stroke-width="3"/>
    ${proy.length ? `<path d="${camino(Math.max(0, nh - 1), pts.length - 1)}" fill="none" stroke="var(--serie-est)" stroke-width="3" stroke-dasharray="8 6"/>` : ""}
    ${pts.map((p, i) => p.valor == null
      ? `<text x="${x(i)}" y="${H - m.b - 10}" text-anchor="middle" class="eje">sin dato</text>`
      : `${p.tipo === "Observado" ? `<circle cx="${x(i)}" cy="${y(p.valor)}" r="${marcas.includes(p.periodo) ? 7 : 5}" fill="var(--serie-obs)"/>`
        : `<rect x="${x(i) - 6}" y="${y(p.valor) - 6}" width="12" height="12" transform="rotate(45 ${x(i)} ${y(p.valor)})" fill="var(--superficie)" stroke="var(--serie-est)" stroke-width="3"/>`}
       ${conEtiqueta(i) ? `<text x="${x(i)}" y="${abajo(i) ? y(p.valor) + 30 : y(p.valor) - 14}" text-anchor="${i === pts.length - 1 ? "end" : i === 0 ? "start" : "middle"}" class="eje fuerte">${esc(etiquetaEje(p.valor))}</text>` : ""}
       <circle class="hit" tabindex="0" role="img" aria-label="${esc(describe(p))}" cx="${x(i)}" cy="${y(p.valor)}" r="14" fill="transparent" data-tip="${esc(describe(p))}"/>`).join("")}
    ${pts.map((p, i) => enEje(i) ? `<text x="${x(i)}" y="${H - 14}" text-anchor="middle" class="eje${marcas.includes(p.periodo) ? " fuerte" : ""}">${esc(mesCorto(p.periodo))}</text>` : "").join("")}
  </svg>`;
  const leyenda = `<ul class="leyenda"><li><span class="muestra obs" aria-hidden="true"></span> Observado (línea continua)</li>${proy.length ? `<li><span class="muestra est" aria-hidden="true"></span> ${esc(etiquetaEstimado)} (línea discontinua, rombos)</li>` : ""}${conBanda ? `<li><span class="muestra banda" aria-hidden="true"></span> Rango ${esc(nivelBanda || "publicado")}${proy.every(p => p.inferior != null) ? "" : "; solo en los meses que lo tienen"}</li>` : ""}</ul>`;
  const filas = pts.map(p => [esc(mesLargo(p.periodo)), esc(p.tipo), p.valor == null ? "Sin dato (no se rellena con cero)" : p.valor === 0 ? `${esc(exacto(0))} (sin operaciones)` : esc(exacto(p.valor)),
    p.inferior != null && p.superior != null ? `${esc(exacto(p.inferior))} a ${esc(exacto(p.superior))}` : p.tipo === "Observado" ? "—" : "Sin banda publicada"]);
  return `<figure class="grafico"><figcaption><strong>${esc(titulo)}</strong> <span class="muted">· unidad: ${esc(unidad)}</span></figcaption>
    ${leyenda}<div class="grafico-lienzo" role="region" tabindex="0" aria-label="Gráfico; en pantallas estrechas se puede desplazar">${svg}<div class="tip oculto" role="status"></div></div>
    <details class="ver-datos"><summary>Ver valores exactos</summary>${tablaHtml({ cabeceras: ["Mes", "Tipo", `Valor (${unidad})`, "Banda"], numericas: new Set([2]), filas })}</details></figure>`;
}

/**
 * Rangos de fechas por fila (próxima compra): barra desde el inicio hasta el fin de la ventana estimada y, aparte, un rombo
 * para el vencimiento contractual. No inventa límites: si falta el final, la barra termina en una flecha con texto.
 * filas: [{etiqueta, desde, hasta, hastaAbierto, contractual, nota}] con fechas AAAA-MM-DD; corte: fecha de los datos.
 */
export function graficoRangos(filas, { corte, titulo, nivel = "", horizonteDias = 60 }) {
  if (!filas.length) return "";
  const dia = f => Date.parse(`${f}T00:00:00Z`) / 86400000;
  // El eje cubre la fecha de los datos y el horizonte del modelo; un fin de cobertura posterior se indica con texto en el borde.
  const min = dia(corte), max = Math.max(min + horizonteDias, ...filas.flatMap(f => [f.desde, f.hasta]).filter(Boolean).map(dia)) + 2;
  const W = 720, fh = 44, m = { l: 110, r: 24, t: 44 };
  const H = m.t + filas.length * fh + 20;
  const x = f => m.l + (dia(f) - min) / Math.max(1, max - min) * (W - m.l - m.r);
  const marcasEje = [];
  for (let d = min; d <= max; d += Math.max(7, Math.round((max - min) / 5))) marcasEje.push(new Date(d * 86400000).toISOString().slice(0, 10));
  const corto = f => { const [aa, mm, dd] = f.split("-"); return `${Number(dd)} ${["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"][Number(mm) - 1]}${aa !== String(corte).slice(0, 4) ? ` ${aa}` : ""}`; };
  const svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(titulo)}. La tabla de abajo tiene las mismas fechas.">
    ${marcasEje.map(f => `<line x1="${x(f)}" x2="${x(f)}" y1="${m.t - 8}" y2="${H - 14}" stroke="var(--rejilla)"/><text x="${x(f)}" y="${m.t - 14}" text-anchor="middle" class="eje">${esc(corto(f))}</text>`).join("")}
    ${corte ? `<line x1="${x(corte)}" x2="${x(corte)}" y1="${m.t - 8}" y2="${H - 14}" stroke="var(--texto-3)" stroke-dasharray="3 4"/>` : ""}
    ${filas.map((f, i) => {
      const cy = m.t + i * fh + fh / 2;
      const x1 = x(f.desde), x2 = f.hasta ? x(f.hasta) : W - m.r;
      return `<text x="${m.l - 12}" y="${cy + 6}" text-anchor="end" class="eje fuerte">${esc(f.etiqueta)}</text>
        <rect x="${x1}" y="${cy - 9}" width="${Math.max(4, x2 - x1)}" height="18" rx="4" fill="var(--estimado-suave)" stroke="var(--serie-est)" stroke-width="2" ${f.hasta ? "" : 'stroke-dasharray="6 4"'}/>
        ${f.hasta ? "" : `<text x="${W - m.r - 4}" y="${cy + 5}" text-anchor="end" class="eje">sin fin en el horizonte →</text>`}
        ${!f.contractual ? "" : dia(f.contractual) > max ? `<text x="${W - m.r - 4}" y="${cy + 6}" text-anchor="end" class="eje">fin de cobertura ${esc(corto(f.contractual))} →</text>`
          : `<rect x="${x(f.contractual) - 7}" y="${cy - 7}" width="14" height="14" transform="rotate(45 ${x(f.contractual)} ${cy})" fill="var(--superficie)" stroke="var(--texto)" stroke-width="2.5"/>`}`;
    }).join("")}
  </svg>`;
  return `<figure class="grafico"><figcaption><strong>${esc(titulo)}</strong></figcaption>
    <ul class="leyenda"><li><span class="muestra rango" aria-hidden="true"></span> Ventana estimada${nivel ? ` (${esc(nivel)})` : ""}</li><li><span class="muestra rombo" aria-hidden="true"></span> Fin de cobertura (fecha de contrato, no estimada)</li><li><span class="muestra corte" aria-hidden="true"></span> Fecha de los datos</li></ul>
    <div class="grafico-lienzo" role="region" tabindex="0" aria-label="Gráfico de ventanas; se puede desplazar">${svg}</div></figure>`;
}

/** Muestra el valor de un punto al enfocarlo con teclado o tacto, o al pasar el ratón. La tabla tiene los mismos valores. */
export function activarTooltips() {
  $vista.querySelectorAll(".grafico").forEach(g => {
    const tip = g.querySelector(".tip"), lienzo = g.querySelector(".grafico-lienzo");
    if (!tip || !lienzo) return;
    g.querySelectorAll(".hit").forEach(h => {
      const mostrar = () => {
        const r = h.getBoundingClientRect(), b = lienzo.getBoundingClientRect();
        tip.textContent = h.dataset.tip; tip.classList.remove("oculto");
        tip.style.left = `${Math.max(0, Math.min(r.left - b.left + lienzo.scrollLeft - 60, lienzo.scrollWidth - 300))}px`; tip.style.top = `${Math.max(0, r.top - b.top - 70)}px`;
      };
      const ocultar = () => tip.classList.add("oculto");
      h.addEventListener("mouseenter", mostrar); h.addEventListener("focus", mostrar);
      h.addEventListener("mouseleave", ocultar); h.addEventListener("blur", ocultar);
    });
  });
}

/** Cronología: [{fecha, titulo, detalle, tipo, chip}] ordenada por fecha; marca la fecha de los datos. */
export function cronologia(eventos, { corte = null, vacio: textoVacio = "Sin movimientos." } = {}) {
  if (!eventos.length) return `<p class="muted">${esc(textoVacio)}</p>`;
  let marcado = false;
  const items = [];
  const marca = () => `<li class="crono-corte"><span>Fecha de los datos · ${esc(fechaLarga(corte))}. Lo que sigue era futuro en esa fecha.</span></li>`;
  for (const e of eventos) {
    if (corte && !marcado && e.fecha && e.fecha.slice(0, 10) > corte) { items.push(marca()); marcado = true; }
    items.push(`<li class="crono-${esc(e.tipo || "evento")}"><div class="crono-fecha">${esc(e.etiquetaFecha || e.fecha || "")}</div>
      <div><strong>${esc(e.titulo)}</strong>${e.chip ? ` <span class="chip">${esc(e.chip)}</span>` : ""}${e.detalle ? `<div class="muted">${e.detalle}</div>` : ""}</div></li>`);
  }
  if (corte && !marcado) items.push(marca());
  return `<ol class="cronologia">${items.join("")}</ol>`;
}
