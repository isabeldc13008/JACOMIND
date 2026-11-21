// Componentes de lectura: respuesta principal, barras, «Ver datos y cálculo» y gráfica de línea accesible.
import { $vista, cop, esc, fechaHora, mesCorto, mesLargo, millones } from "./nucleo.js";

/** Frase que contesta la pregunta principal de la pantalla, con su contexto (periodo, unidad, alcance). */
export function respuesta(frase, contexto = "") {
  return `<div class="respuesta"><p class="frase">${frase}</p>${contexto ? `<p class="contexto">${contexto}</p>` : ""}</div>`;
}

/**
 * Barras horizontales: etiqueta, longitud proporcional y valor escrito (no depende del color).
 * items: [{etiqueta, valor, texto, href?, activo?, nota?}]. Con `signo`, los negativos usan otro trazo y el signo escrito.
 */
export function barras(items, { titulo = "", etiquetaAria = "", signo = false, vacio = "Sin datos para graficar." } = {}) {
  if (!items.length) return `<p class="muted">${esc(vacio)}</p>`;
  const max = Math.max(1e-9, ...items.map(i => Math.abs(i.valor || 0)));
  const fila = i => {
    const ancho = (Math.abs(i.valor || 0) / max * 100).toFixed(1);
    const neg = signo && i.valor < 0;
    const cuerpo = `<span class="b-et">${esc(i.etiqueta)}${i.nota ? `<span class="b-nota">${esc(i.nota)}</span>` : ""}</span>
      <span class="b-pista" aria-hidden="true"><span class="b-relleno ${neg ? "neg" : ""}" style="width:${ancho}%"></span></span>
      <span class="b-val">${esc(i.texto ?? String(i.valor))}</span>`;
    return i.href
      ? `<li><a class="b-fila ${i.activo ? "activo" : ""}" href="${esc(i.href)}" ${i.activo ? 'aria-current="true"' : ""}>${cuerpo}</a></li>`
      : `<li><div class="b-fila ${i.activo ? "activo" : ""}">${cuerpo}</div></li>`;
  };
  return `${titulo ? `<h3>${esc(titulo)}</h3>` : ""}<ul class="barras" aria-label="${esc(etiquetaAria || titulo)}">${items.map(fila).join("")}</ul>`;
}

/**
 * «Ver datos y cálculo»: tabla exacta, fuente, filtros, fecha de actualización y regla o versión.
 * tabla: {cabeceras: [...], filas: [[...]], numericas: Set(índices)}
 */
export function verDatos({ titulo = "Ver datos y cálculo", tabla = null, fuente = "", filtros = "", actualizado = "", regla = "", extra = "" } = {}) {
  const t = tabla && tabla.filas.length ? `<div class="tabla"><table><thead><tr>${tabla.cabeceras.map((c, i) => `<th class="${tabla.numericas?.has(i) ? "n" : ""}">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${tabla.filas.map(f => `<tr>${f.map((v, i) => `<td class="${tabla.numericas?.has(i) ? "n" : ""}">${v}</td>`).join("")}</tr>`).join("")}</tbody></table></div>` : "";
  const meta = [fuente && `<dt>Fuente</dt><dd>${fuente}</dd>`, filtros && `<dt>Filtros</dt><dd>${filtros}</dd>`,
    actualizado && `<dt>Actualización</dt><dd>${actualizado}</dd>`, regla && `<dt>Regla o versión</dt><dd>${regla}</dd>`].filter(Boolean).join("");
  return `<details class="ver-datos"><summary>${esc(titulo)}</summary>${t}${meta ? `<dl class="meta-datos">${meta}</dl>` : ""}${extra}</details>`;
}

/** Bloque de detalle técnico (versiones, rutas, datos originales) separado de la lectura principal. */
export function detalleTecnico(contenido, titulo = "Detalle técnico") {
  return `<details class="tecnico"><summary>${esc(titulo)}</summary>${contenido}</details>`;
}

export const fuenteCierre = c => c ? `Cierre ${esc(c.id || c.cierre_id || "")}${c.origen ? ` (${esc(c.origen)})` : ""}${c.publicado_en ? ` · publicado ${esc(fechaHora(c.publicado_en))}` : ""}` : "";

/**
 * Gráfica de línea de una serie mensual: histórico continuo y proyección punteada (misma serie).
 * opciones: {marcas: [periodos a rotular], titulo, unidad}. Los puntos son navegables con teclado.
 */
export function graficoLinea(hist, proy = [], { marcas = [], titulo = "Serie mensual", unidad = "COP" } = {}) {
  const pts = [...hist.map(p => ({ ...p, tipo: "Histórico" })), ...proy.map(p => ({ ...p, tipo: "Proyección" }))];
  if (!pts.length) return '<p class="muted">Sin serie publicada.</p>';
  const W = 560, H = 230, m = { l: 70, r: 30, t: 22, b: 30 };
  const vals = pts.map(p => p.valor).filter(v => v != null);
  const max = Math.max(1, ...vals) * 1.15;
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
  const ticks = [0, .5, 1].map(f => max / 1.15 * f);
  const etiquetaEje = t => millones(t, { unidad: false }).replace(" millones", " M");
  const describe = p => `${mesLargo(p.periodo)} · ${p.tipo}: ${p.valor == null ? "sin dato (mes incompleto)" : `${millones(p.valor)} (${cop(p.valor)})`}`;
  const inicioProy = proy.length ? x(nh - 0.5 < 0 ? 0 : nh - 0.5) : null;
  return `<figure class="grafico" style="position:relative"><figcaption class="oculto-visual">${esc(titulo)}. Unidad: ${esc(unidad)}. La tabla con los mismos valores está debajo.</figcaption>
  <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(titulo)}; tabla equivalente debajo">
    ${ticks.map(t => `<line x1="${m.l}" x2="${W - m.r}" y1="${y(t)}" y2="${y(t)}" stroke="var(--rejilla)"/><text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end" font-size="11" fill="var(--texto-2)">${esc(etiquetaEje(t))}</text>`).join("")}
    ${inicioProy != null ? `<line x1="${inicioProy}" x2="${inicioProy}" y1="${m.t - 8}" y2="${H - m.b}" stroke="var(--texto-3)" stroke-dasharray="2 3"/><text x="${inicioProy + 4}" y="${m.t - 10}" font-size="11" fill="var(--texto-2)">Pronóstico →</text>` : ""}
    <path d="${seg(0, nh - 1)}" fill="none" stroke="var(--serie-1)" stroke-width="2"/>
    ${proy.length ? `<path d="${seg(Math.max(0, nh - 1), pts.length - 1)}" fill="none" stroke="var(--serie-1)" stroke-width="2" stroke-dasharray="5 4"/>` : ""}
    ${pts.map((p, i) => p.valor == null ? `<text x="${x(i)}" y="${H - m.b - 6}" text-anchor="middle" font-size="10" fill="var(--texto-3)">s/d</text>` :
      `<circle cx="${x(i)}" cy="${y(p.valor)}" r="${marcas.includes(p.periodo) ? 5.5 : 4}" fill="${p.tipo === "Proyección" ? "var(--superficie)" : "var(--serie-1)"}" stroke="var(--serie-1)" stroke-width="2"/>
       ${marcas.includes(p.periodo) ? `<text x="${x(i)}" y="${y(p.valor) - 10}" text-anchor="${i === pts.length - 1 ? "end" : "middle"}" font-size="11" font-weight="600" fill="var(--texto)">${esc(millones(p.valor, { unidad: false }).replace(" millones", " M"))}</text>` : ""}
       <circle class="hit" tabindex="0" role="button" aria-label="${esc(describe(p))}" cx="${x(i)}" cy="${y(p.valor)}" r="12" fill="transparent" data-tip="${esc(describe(p))}"/>`).join("")}
    ${pts.map((p, i) => (i % Math.ceil(pts.length / 8) === 0 || i === pts.length - 1 || marcas.includes(p.periodo)) ? `<text x="${x(i)}" y="${H - 9}" text-anchor="middle" font-size="11" fill="var(--texto-2)" ${marcas.includes(p.periodo) ? 'font-weight="600"' : ""}>${esc(mesCorto(p.periodo))}</text>` : "").join("")}
  </svg><div class="tip oculto" role="status"></div>
  <details><summary class="muted">Ver tabla</summary><table><tr><th>Mes</th><th>Tipo</th><th class="n">COP</th></tr>${pts.map(p => `<tr><td>${esc(mesLargo(p.periodo))}</td><td>${p.tipo}</td><td class="n">${p.valor == null ? "Sin dato (mes incompleto)" : p.valor === 0 ? "0 COP (sin operaciones)" : cop(p.valor)}</td></tr>`).join("")}</table></details></figure>`;
}

/** Muestra el valor de un punto al pasar el ratón o al enfocarlo con teclado o tacto. */
export function activarTooltips() {
  $vista.querySelectorAll(".grafico").forEach(g => {
    const tip = g.querySelector(".tip");
    if (!tip) return;
    g.querySelectorAll(".hit").forEach(h => {
      const mostrar = () => {
        const r = h.getBoundingClientRect(), b = g.getBoundingClientRect();
        tip.textContent = h.dataset.tip; tip.classList.remove("oculto");
        tip.style.left = `${Math.max(0, Math.min(r.left - b.left - 40, b.width - 220))}px`; tip.style.top = `${Math.max(0, r.top - b.top - 40)}px`;
      };
      const ocultar = () => tip.classList.add("oculto");
      h.addEventListener("mouseenter", mostrar); h.addEventListener("focus", mostrar);
      h.addEventListener("mouseleave", ocultar); h.addEventListener("blur", ocultar);
    });
  });
}

/** Cronología: [{fecha, titulo, detalle, tipo}] ordenada por fecha; `futuro` marca lo posterior al cierre. */
export function cronologia(eventos, { corte = null, vacio = "Sin movimientos." } = {}) {
  if (!eventos.length) return `<p class="muted">${esc(vacio)}</p>`;
  let marcado = false;
  const items = [];
  for (const e of eventos) {
    if (corte && !marcado && e.fecha && e.fecha.slice(0, 10) > corte) {
      items.push(`<li class="crono-corte"><span>Cierre de los datos · ${esc(corte)}</span></li>`); marcado = true;
    }
    items.push(`<li class="crono-${esc(e.tipo || "evento")}"><div class="crono-fecha">${esc(e.etiquetaFecha || e.fecha || "")}</div>
      <div><strong>${esc(e.titulo)}</strong>${e.chip ? ` <span class="chip">${esc(e.chip)}</span>` : ""}${e.detalle ? `<div class="muted">${e.detalle}</div>` : ""}</div></li>`);
  }
  if (corte && !marcado) items.push(`<li class="crono-corte"><span>Cierre de los datos · ${esc(corte)}</span></li>`);
  return `<ol class="cronologia">${items.join("")}</ol>`;
}
