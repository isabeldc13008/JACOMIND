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

/** Los mensajes «En prueba» se retiraron de la interfaz; se conservan las funciones para no tocar cada vista. */
export const enPrueba = () => "";
export const avisoPrueba = () => "";

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
 * Línea de tiempo de ventanas (próxima compra), pensada para leerse sin conocimientos técnicos:
 * cada fila es un cliente; la barra es el periodo en que probablemente vuelva a comprar, más intensa donde la compra
 * es más probable, con un punto en la fecha más probable. El rombo es el fin de cobertura (fecha de contrato, aparte).
 * No inventa límites: si falta el final, la barra se desvanece y lo dice con texto.
 * filas: [{etiqueta, desde, hasta, probable, recencia, contractual}] con fechas AAAA-MM-DD; corte: fecha de los datos.
 */
export function graficoRangos(filas, { corte, titulo, nivel = "", horizonteDias = 60 }) {
  if (!filas.length) return "";
  const dia = f => Date.parse(`${f}T00:00:00Z`) / 86400000;
  const MES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const MES_L = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  const partes = f => f.split("-").map(Number);
  const corto = f => { const [aa, mm, dd] = partes(f); return `${dd} ${MES[mm - 1]}${String(aa) !== String(corte).slice(0, 4) ? ` ${aa}` : ""}`; };
  const largo = f => { const [, mm, dd] = partes(f); return `${dd} de ${MES_L[mm - 1]}`; };
  const rango = (a, b) => { const [, ma, da] = partes(a), [, mb] = partes(b); return ma === mb ? `${da}–${corto(b)}` : `${corto(a)} – ${corto(b)}`; };
  const enDias = n => n <= 0 ? "Ya empezó" : n === 1 ? "Empieza mañana" : `Empieza en ${n} días`;

  // Eje: de la fecha de los datos al horizonte del modelo; un fin de cobertura posterior se indica con texto en el borde.
  const min = dia(corte), max = Math.max(min + horizonteDias, ...filas.flatMap(f => [f.desde, f.hasta]).filter(Boolean).map(dia)) + 2;
  const W = 980, fh = 62, m = { l: 200, r: 120, t: 78, b: 14 };
  const H = m.t + filas.length * fh + m.b;
  const xd = d => m.l + (d - min) / Math.max(1, max - min) * (W - m.l - m.r);
  const x = f => xd(dia(f));
  const iso = d => new Date(d * 86400000).toISOString().slice(0, 10);

  // Semanas alternas sombreadas y una marca por semana desde la fecha de los datos.
  const semanas = [];
  for (let d = min, k = 0; d < max; d += 7, k++) semanas.push({ d, k });
  const fondoSemanas = semanas.filter(s => s.k % 2 === 1).map(s => `<rect x="${xd(s.d)}" y="${m.t - 8}" width="${xd(Math.min(s.d + 7, max)) - xd(s.d)}" height="${H - m.t - m.b + 8}" fill="var(--superficie-2)" opacity=".7"/>`).join("");
  const marcas = semanas.slice(1).map(s => `<line x1="${xd(s.d)}" x2="${xd(s.d)}" y1="${m.t - 8}" y2="${H - m.b}" stroke="var(--rejilla)"/>
    <text x="${xd(s.d)}" y="${m.t - 18}" text-anchor="middle" class="eje">${esc(corto(iso(s.d)))}</text>`).join("");
  const xc = x(corte);
  const marcaCorte = `<line x1="${xc}" x2="${xc}" y1="${m.t - 8}" y2="${H - m.b}" stroke="var(--texto-2)" stroke-width="2" stroke-dasharray="4 4"/><line x1="${xc}" x2="${xc}" y1="32" y2="${m.t - 8}" stroke="var(--texto)" stroke-width="2"/>
    <rect x="${xc - 64}" y="4" width="128" height="28" rx="14" fill="var(--texto)"/>
    <text x="${xc}" y="23" text-anchor="middle" class="eje-pildora">Datos al ${esc(corto(corte))}</text>`;

  const defs = [], cuerpo = [];
  filas.forEach((f, i) => {
    const y0 = m.t + i * fh, cy = y0 + fh / 2, alto = 20;
    const x1 = x(f.desde), x2 = f.hasta ? x(f.hasta) : W - m.r, ancho = Math.max(alto, x2 - x1);
    const xp = f.probable ? x(f.probable) : null;
    const pos = xp != null ? Math.min(1, Math.max(0, (xp - x1) / ancho)) : 0.5;
    const id = `vg-${i}-${String(f.etiqueta).replace(/[^\w-]/g, "")}`;
    // Intensidad: suave en los bordes, máxima en la fecha más probable; sin final, se desvanece hacia la derecha.
    defs.push(`<linearGradient id="${id}" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0" style="stop-color:var(--serie-est);stop-opacity:.2"/>
      <stop offset="${pos.toFixed(3)}" style="stop-color:var(--serie-est);stop-opacity:.75"/>
      <stop offset="1" style="stop-color:var(--serie-est);stop-opacity:${f.hasta ? ".2" : "0"}"/></linearGradient>`);
    const n = Math.round(dia(f.desde) - min);
    const tip = [`${f.etiqueta}: es probable que vuelva a comprar`,
      f.hasta ? ` entre el ${partes(f.desde)[1] === partes(f.hasta)[1] ? partes(f.desde)[2] : largo(f.desde)} y el ${largo(f.hasta)}` : ` a partir del ${largo(f.desde)} (sin fecha de fin dentro del horizonte)`,
      f.probable ? `; la fecha más probable es el ${largo(f.probable)}.` : ".",
      f.recencia != null ? ` Su última compra fue hace ${f.recencia} días.` : "",
      f.contractual ? ` Su cobertura termina el ${largo(f.contractual)} (fecha de contrato).` : ""].join("");
    const contractual = !f.contractual ? "" : dia(f.contractual) > max
      ? `<text x="${W - 8}" y="${cy + 26}" text-anchor="end" class="eje chico">fin de cobertura ${esc(corto(f.contractual))} →</text>`
      : `<rect x="${x(f.contractual) - 7}" y="${cy - 7}" width="14" height="14" transform="rotate(45 ${x(f.contractual)} ${cy})" fill="var(--superficie)" stroke="var(--texto)" stroke-width="2.5"/>`;
    const etiquetaFin = f.hasta ? `<text x="${x2 + 12}" y="${cy + 5}" class="eje valor">${esc(rango(f.desde, f.hasta))}</text>`
      : `<text x="${W - 8}" y="${cy + 5}" text-anchor="end" class="eje chico">sin fin en el horizonte →</text>`;
    cuerpo.push(`<g class="fila-rango">
      <rect class="fondo-fila" x="4" y="${y0 + 3}" width="${W - 8}" height="${fh - 6}" rx="10" fill="transparent"/>
      <text x="18" y="${cy - 3}" class="eje fuerte">${esc(f.etiqueta)}</text>
      <text x="18" y="${cy + 18}" class="eje chico${n <= 7 ? " pronto" : ""}">${esc(enDias(n))}</text>
      <rect x="${x1}" y="${cy - alto / 2}" width="${ancho}" height="${alto}" rx="${alto / 2}" fill="url(#${id})" stroke="var(--serie-est)" stroke-width="1.5" ${f.hasta ? "" : 'stroke-dasharray="6 4"'}/>
      ${xp != null ? `<circle cx="${xp}" cy="${cy}" r="8" fill="var(--serie-est)" stroke="var(--superficie)" stroke-width="2"/>` : ""}
      ${etiquetaFin}${contractual}
      <rect class="hit" tabindex="0" role="img" aria-label="${esc(tip)}" data-tip="${esc(tip)}" data-ancla="${((xp ?? x1) / W).toFixed(4)}" x="4" y="${y0 + 3}" width="${W - 8}" height="${fh - 6}" rx="10" fill="transparent"/>
    </g>`);
  });

  const svg = `<svg class="grafico-ventanas" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(titulo)}. La tabla de abajo tiene las mismas fechas.">
    <defs>${defs.join("")}</defs>${fondoSemanas}${marcas}${marcaCorte}${cuerpo.join("")}</svg>`;
  const hayProbable = filas.some(f => f.probable), hayContrato = filas.some(f => f.contractual);
  return `<figure class="grafico"><figcaption><strong>${esc(titulo)}</strong></figcaption>
    <ul class="leyenda"><li><span class="muestra ventana" aria-hidden="true"></span> Periodo en que probablemente vuelva a comprar</li>
      ${hayProbable ? '<li><span class="muestra punto" aria-hidden="true"></span> Fecha más probable</li>' : ""}
      <li><span class="muestra corte" aria-hidden="true"></span> Fecha de los datos</li>
      ${hayContrato ? '<li><span class="muestra rombo" aria-hidden="true"></span> Fin de cobertura (contrato, no estimado)</li>' : ""}</ul>
    <div class="grafico-lienzo" role="region" tabindex="0" aria-label="Gráfico de ventanas; se puede desplazar">${svg}<div class="tip oculto" role="status"></div></div>
    <p class="muted nota-grafico"><strong>Cómo leerlo:</strong> cuanto más intenso el color, más probable es la compra en esa fecha. Conviene contactar al cliente justo antes de que empiece su barra.${nivel ? ` La barra va ${esc(nivel)}.` : ""} Pasa el cursor o toca una fila para ver el detalle.</p></figure>`;
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
        // data-ancla: posición horizontal (0 a 1 del ancho del gráfico) donde conviene abrir el detalle.
        const svgR = h.ownerSVGElement?.getBoundingClientRect();
        const izq = h.dataset.ancla && svgR ? svgR.left - b.left + Number(h.dataset.ancla) * svgR.width - 40 : r.left - b.left - 60;
        tip.style.left = `${Math.max(0, Math.min(izq + lienzo.scrollLeft, lienzo.scrollWidth - 300))}px`; const arriba = r.top - b.top - tip.offsetHeight - 6;
        tip.style.top = `${h.dataset.ancla ? (arriba >= 0 ? arriba : r.bottom - b.top + 6) : Math.max(0, r.top - b.top - 70)}px`;
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
