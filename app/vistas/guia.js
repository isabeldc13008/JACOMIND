// «Cómo funciona JACOMIND»: muestra docs/guia-del-equipo.md dentro de la aplicación (una sola fuente que mantener).
// Solo perfiles internos (capacidad guia.ver). Los enlaces a otros documentos abren el archivo en el repositorio.
import { $vista, api, errorHtml, esc, estadoHtml, nuevoTurno, vigente } from "../nucleo.js";
import { barras, encabezado } from "../ui.js";

const REPO = "https://github.com/isabeldc13008/JACOMIND/blob/main/";

/** Resuelve un enlace relativo de la guía (escrita en docs/) a su archivo en el repositorio. */
export function enlaceRepo(destino, base = "docs/") {
  if (/^(https?:|mailto:)/.test(destino)) return destino;
  const [ruta, ancla] = destino.split("#");
  const partes = (base + ruta).split("/");
  const limpio = [];
  for (const p of partes) { if (p === "..") limpio.pop(); else if (p && p !== ".") limpio.push(p); }
  return `${REPO}${limpio.join("/")}${ancla ? `#${ancla}` : ""}`;
}

const idDe = t => "g-" + t.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

function enLinea(t) {
  return esc(t)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, texto, url) => {
      if (url.startsWith("#")) return `<button type="button" class="enlace" data-ir-a="g-${esc(url.slice(1))}">${texto}</button>`;   // salto dentro de la guía
      const destino = enlaceRepo(url.replace(/&amp;/g, "&"));
      return `<a href="${esc(destino)}" target="_blank" rel="noopener">${texto}<span class="oculto-visual"> (se abre en una pestaña nueva)</span></a>`;
    });
}

const numero = t => Number(String(t).trim().replace(/\./g, "").replace(",", "."));

/** Bloques ilustrados de la guía. En GitHub se leen como texto; aquí se dibujan. */
function bloqueEspecial(tipo, lineas) {
  const filas = lineas.map(l => l.trim()).filter(Boolean);
  if (tipo === "pasos") {
    const pasos = filas.map(l => l.split("|").map(x => x.trim()));
    return `<ol class="guia-pasos">${pasos.map(([t, d], i) => `<li><span class="guia-paso-num" aria-hidden="true">${i + 1}</span><strong>${enLinea(t)}</strong>${d ? `<span>${enLinea(d)}</span>` : ""}</li>`).join("")}</ol>`;
  }
  if (tipo === "tarjetas") {
    return `<div class="guia-tarjetas">${filas.map(l => {
      const [estado, titulo, texto] = l.split("|").map(x => x.trim());
      const uso = /uso/i.test(estado), ia = /^IA$/i.test(estado);
      return `<article class="guia-tarjeta ${uso ? "uso" : ia ? "ia" : "prueba"}"><span class="sello ${uso ? "sello-ok" : ia ? "sello-ia" : "sello-prueba"}">${esc(estado)}</span><h4>${enLinea(titulo)}</h4><p>${enLinea(texto || "")}</p></article>`;
    }).join("")}</div>`;
  }
  if (tipo === "barras") {
    const meta = {}, items = [];
    for (const l of filas) {
      const m = l.match(/^(titulo|unidad|nota):\s*(.*)$/i);
      if (m) { meta[m[1].toLowerCase()] = m[2]; continue; }
      const k = l.lastIndexOf(":");
      if (k > 0) {
        const bruto = l.slice(k + 1).trim();
        items.push({ etiqueta: l.slice(0, k).trim(), valor: numero(bruto), texto: `${bruto}${meta.unidad === "%" ? " %" : meta.unidad ? ` ${meta.unidad}` : ""}` });
      }
    }
    return `<figure class="guia-grafico panel"><figcaption><strong>${enLinea(meta.titulo || "")}</strong></figcaption>
      ${barras(items, { etiquetaAria: meta.titulo || "Gráfico de barras" })}${meta.nota ? `<p class="muted">${enLinea(meta.nota)}</p>` : ""}</figure>`;
  }
  return null;
}

/** Markdown de la guía → HTML seguro: títulos, párrafos, listas, tablas, citas, código y bloques ilustrados. */
export function guiaHtml(md) {
  const lineas = md.replace(/\r/g, "").split("\n");
  const html = [], indice = [];
  let i = 0, parrafo = [];
  const cerrar = () => { if (parrafo.length) { html.push(`<p>${enLinea(parrafo.join(" "))}</p>`); parrafo = []; } };
  while (i < lineas.length) {
    const l = lineas[i], t = l.trim();
    if (t.startsWith("```")) {
      cerrar(); const tipo = t.slice(3).trim(), bloque = []; i++;
      while (i < lineas.length && !lineas[i].trim().startsWith("```")) bloque.push(lineas[i++]);
      html.push(bloqueEspecial(tipo, bloque) ?? `<pre><code>${esc(bloque.join("\n"))}</code></pre>`); i++; continue;
    }
    let m;
    if ((m = t.match(/^(#{1,3})\s+(.*)$/))) {
      cerrar();
      const nivel = m[1].length, texto = m[2];
      if (nivel === 1) { i++; continue; }                       // el título va en el encabezado de la página
      const id = idDe(texto);
      if (nivel === 2 && /^Parte \d/.test(texto)) {                 // separador de las dos partes de la guía
        indice.push({ id, texto, parte: true });
        html.push(`<h2 id="${id}" tabindex="-1" class="guia-parte">${enLinea(texto)}</h2>`); i++; continue;
      }
      if (nivel === 2) indice.push({ id, texto });
      html.push(`<h${nivel} id="${id}" tabindex="-1">${enLinea(texto)}</h${nivel}>`); i++; continue;
    }
    if (/^\|.*\|$/.test(t)) {
      cerrar(); const filas = [];
      while (i < lineas.length && /^\|.*\|$/.test(lineas[i].trim())) filas.push(lineas[i++].trim());
      const celdas = f => f.replace(/^\||\|$/g, "").split("|").map(c => c.trim());
      const cuerpo = filas.filter(f => !/^\|?\s*:?-{3,}/.test(f));
      const cab = celdas(cuerpo[0]);
      html.push(`<div class="tabla" role="region" tabindex="0" aria-label="Tabla; se puede desplazar"><table><thead><tr>${cab.map(c => `<th scope="col">${enLinea(c)}</th>`).join("")}</tr></thead>
        <tbody>${cuerpo.slice(1).map(f => `<tr>${celdas(f).map(c => `<td>${enLinea(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (t.startsWith(">")) {
      cerrar(); const cita = [];
      while (i < lineas.length && lineas[i].trim().startsWith(">")) cita.push(lineas[i++].trim().replace(/^>\s?/, ""));
      html.push(`<div class="aviso-prueba" role="note">${guiaHtml(cita.join("\n")).html}</div>`); continue;
    }
    if ((m = t.match(/^(-|\d+\.)\s+(.*)$/))) {
      cerrar(); const ordenada = /\d/.test(m[1]), items = [];
      while (i < lineas.length) {
        const x = lineas[i].trim().match(/^(-|\d+\.)\s+(.*)$/);
        if (x) { items.push(x[2]); i++; }
        else if (lineas[i].startsWith("  ") && lineas[i].trim() && items.length) { items[items.length - 1] += ` ${lineas[i].trim()}`; i++; }
        else break;
      }
      html.push(`<${ordenada ? "ol" : "ul"}>${items.map(x => `<li>${enLinea(x)}</li>`).join("")}</${ordenada ? "ol" : "ul"}>`); continue;
    }
    if (!t) { cerrar(); i++; continue; }
    parrafo.push(t); i++;
  }
  cerrar();
  return { html: html.join("\n"), indice };
}

export async function vistaGuia() {
  const titulo = "Cómo funciona JACOMIND";
  const turno = nuevoTurno();
  $vista.innerHTML = `${encabezado({ titulo })}${estadoHtml("", "Cargando la guía…")}`;
  let d;
  try { d = await api("GET", "/api/guia"); } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo })}${errorHtml(e, { reintentar: e.status !== 403 && e.status !== 404 })}`; return; }
  if (!vigente(turno)) return;
  const { html, indice } = guiaHtml(d.markdown);
  $vista.innerHTML = `${encabezado({ titulo, descripcion: "Guía para el equipo: qué hace la aplicación, cómo fluyen los datos, qué hace cada modelo y cómo funciona el asistente.",
    contexto: [{ etiqueta: "Fuente", valor: `<a href="${esc(REPO + d.archivo)}" target="_blank" rel="noopener">${esc(d.archivo)}<span class="oculto-visual"> (se abre en una pestaña nueva)</span></a>` }] })}
  <div class="guia">
    <nav class="guia-indice panel" aria-label="Contenido de la guía"><h2>Contenido</h2>
      <ul>${indice.map(x => `<li class="${x.parte ? "guia-indice-parte" : ""}"><button type="button" class="enlace" data-ir-a="${x.id}">${esc(x.texto)}</button></li>`).join("")}</ul></nav>
    <article class="guia-texto">${html}</article>
  </div>`;
}
