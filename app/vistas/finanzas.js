// Finanzas: ventas y compras a proveedores, simulación del tipo de cambio e informes mensuales (entradas 17 a 19).
import {
  $vista, S, api, conSigno, cop, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, mesLargo, millones, nuevoTurno, num, plural, puede, ruta, vigente,
} from "../nucleo.js";
import { activarTooltips, barras, detalleTecnico, fuenteCierre, graficoLinea, respuesta, verDatos } from "../ui.js";

const pesos = x => x == null ? "—" : `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(Math.round(x))} COP`;
const PREGUNTA = { ventas: "¿Cuánto vendimos?", compras: "¿Cuánto compramos a proveedores?" };
const VERBO = { ventas: ["vendimos", "se vendió"], compras: ["compramos a proveedores", "se compró"] };

export async function vistaFinanzas() {
  const { q } = ruta();
  const serie = q.get("serie") === "compras" ? "compras" : "ventas";
  const soloInformes = !puede("finanzas.ver");
  const turno = nuevoTurno();
  const [pan, informes, cierres] = await Promise.all([soloInformes ? null : api("GET", `/api/finanzas/${S.cierre}/panel?serie=${serie}`),
    puede("informes.ver") ? api("GET", "/api/informes") : [], puede("informes.ver") ? api("GET", "/api/cierres").catch(() => []) : []]).catch(e => [e]);
  if (!vigente(turno)) return;
  if (pan instanceof Error) { $vista.innerHTML = errorHtml(pan); return; }
  const titulo = soloInformes ? "Informes mensuales" : "Finanzas";
  $vista.innerHTML = `<h1>${titulo}</h1>${pan ? panelSerie(pan, serie, q) + simulador(pan, q) : ""}${puede("informes.ver") ? seccionInformes(informes, cierres, soloInformes) : ""}`;
  activarTooltips();
  enlazarSerie(serie, q);
  enlazarSimulador();
  enlazarInformes();
}

// ---------------------------------------------------------------- ventas y compras (entrada 17)
function ultimoPar(hist) {
  const completos = hist.filter(p => p.valor_cop != null && p.completo !== false);
  return completos.length >= 2 ? [completos.at(-2), completos.at(-1)] : completos.length ? [null, completos.at(-1)] : [null, null];
}

function panelSerie(pan, serie, q) {
  const fams = pan.familias.map(f => f.familia);
  const famSel = fams.includes(q.get("familia")) ? q.get("familia") : "Total";
  const g = pan.familias.find(f => f.familia === famSel);
  const pestanas = `<nav class="pestanas" aria-label="Serie">${["ventas", "compras"].map(s => `<a href="#/finanzas?serie=${s}" ${s === serie ? 'aria-current="page"' : ""}>${PREGUNTA[s]}</a>`).join("")}</nav>`;
  if (!pan.disponible || !g) return `${pestanas}${estadoHtml("", "Este cierre no publica la serie mensual; no hay datos observados ni proyección que mostrar.")}`;
  const [ant, ult] = ultimoPar(g.historico);
  const incompletos = g.historico.filter(p => p.valor_cop == null || p.completo === false).map(p => p.periodo);
  const etiquetaFam = famSel === "Total" ? "" : ` en la familia ${famSel}`;
  let frase;
  if (ult && ant) {
    const d = ult.valor_cop - ant.valor_cop;
    const porc = ant.valor_cop ? ` (${d < 0 ? "−" : "+"}${num(Math.abs(d / ant.valor_cop * 100))} %)` : "";
    frase = `<strong>En ${esc(mesLargo(ult.periodo))} ${VERBO[serie][0]} ${esc(millones(ult.valor_cop))}${esc(etiquetaFam)}.</strong> ${ult.valor_cop === 0 ? "Fue un mes sin operaciones registradas, no un dato ausente. " : ""}Frente a ${esc(mesLargo(ant.periodo))}, ${d === 0 ? "sin cambio" : `${esc(millones(Math.abs(d)))} ${d < 0 ? "menos" : "más"}${porc}`}.`;
  } else frase = ult ? `<strong>En ${esc(mesLargo(ult.periodo))} ${VERBO[serie][0]} ${esc(millones(ult.valor_cop))}${esc(etiquetaFam)}.</strong> No hay un mes anterior completo para comparar.` : "<strong>No hay meses completos publicados.</strong>";
  // Comparación por familia para el mismo par de meses (por defecto, el par del Total o el que llega desde Gerencia).
  const meses = [...new Set(pan.familias.flatMap(f => f.historico.map(p => p.periodo)))].sort();
  const parTotal = ultimoPar(pan.familias.find(f => f.familia === "Total")?.historico || []);
  const desde = meses.includes(q.get("desde")) ? q.get("desde") : parTotal[0]?.periodo;
  const hasta = meses.includes(q.get("hasta")) ? q.get("hasta") : parTotal[1]?.periodo;
  const valor = (f, m) => f.historico.find(p => p.periodo === m)?.valor_cop ?? null;
  const comp = pan.familias.filter(f => f.familia !== "Total").map(f => ({ familia: f.familia, a: valor(f, desde), b: valor(f, hasta) }))
    .map(x => ({ ...x, d: x.a == null || x.b == null ? null : x.b - x.a })).sort((x, y) => Math.abs(y.d ?? 0) - Math.abs(x.d ?? 0));
  const selMes = (n, v) => `<select name="${n}">${meses.map(m => `<option value="${m}" ${m === v ? "selected" : ""}>${esc(mesLargo(m))}</option>`).join("")}</select>`;
  const desc = (p, tipo) => p.valor_cop == null ? "Sin dato (mes incompleto)" : tipo === "Proyección" ? `${cop(p.valor_cop)} (proyección)` : p.valor_cop === 0 ? "0 COP (mes sin operaciones)" : cop(p.valor_cop);
  const mae = Object.entries(g.mae_por_horizonte || {}).map(([h, m]) => {
    const ing = g.mae_ingenuo_por_horizonte?.[h];
    return `<li>A ${plural(Number(h), "mes", "meses")} vista: ${m == null ? "sin evaluar (faltan meses para probarla)" : `se desvió en promedio ${esc(millones(m))} en meses ya conocidos`}${ing != null ? `; repetir el último mes observado se desvió ${esc(millones(ing))}` : ""}.</li>`;
  }).join("");
  return `${pestanas}
  ${respuesta(frase, `${esc(ult ? `Último mes completo: ${mesLargo(ult.periodo)}` : "")} · ${esc(`Datos hasta el ${fechaLarga(pan.cierre.corte)}`)} · pesos colombianos (COP)`)}
  ${incompletos.length ? estadoHtml("", `Mes incompleto sin dato: ${incompletos.map(mesLargo).join(", ")}. Es distinto de un mes con 0 COP.`) : ""}
  <div class="grid2">
    <section class="panel"><h2>${serie === "ventas" ? "Ventas confirmadas" : "Compras a proveedores"} por mes</h2>
      <form id="fam" class="fila"><label>Familia <select name="familia">${fams.map(f => `<option ${f === famSel ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label></form>
      ${graficoLinea(g.historico.map(s => ({ periodo: s.periodo, valor: s.valor_cop })), g.pronostico.map(s => ({ periodo: s.periodo, valor: s.valor_cop })),
        { marcas: [ant?.periodo, ult?.periodo].filter(Boolean), titulo: `${PREGUNTA[serie]} ${famSel}, por mes en COP` })}
      <p class="muted">Línea continua: observado. Punteada, a la derecha de «Pronóstico»: proyección, no ingreso confirmado. El total es el publicado en la serie; la vista no suma familias.</p>
      ${g.pronostico.length ? `<details class="ver-datos"><summary>Cómo se calcula la proyección</summary><p>Método: ${esc(g.metodo || "—")} (calculada ${esc(fechaHora(g.calculado_en))}). Error de la proyección en meses ya conocidos:</p><ul>${mae || "<li>Sin evaluar.</li>"}</ul></details>` : ""}
    </section>
    <section class="panel"><h2>Comparación por familia</h2>
      <form id="par" class="fila"><label>De ${selMes("desde", desde)}</label><label>a ${selMes("hasta", hasta)}</label><button class="sec">Comparar</button></form>
      ${desde && hasta ? `${barras(comp.filter(x => x.d != null).map(x => ({ etiqueta: x.familia, valor: x.d, texto: conSigno(x.d) })), { signo: true, etiquetaAria: `Diferencia por familia entre ${mesLargo(desde)} y ${mesLargo(hasta)}` })}
      <p class="muted">Diferencia de cada familia entre ${esc(mesLargo(desde))} y ${esc(mesLargo(hasta))}. Barras rayadas y con signo «−»: disminuciones.</p>
      ${verDatos({ titulo: "Ver la tabla de la comparación", tabla: { cabeceras: ["Familia", mesLargo(desde), mesLargo(hasta), "Diferencia"], numericas: new Set([1, 2, 3]), filas: comp.map(x => [esc(x.familia), x.a == null ? "Sin dato" : cop(x.a), x.b == null ? "Sin dato" : cop(x.b), x.d == null ? "—" : esc(conSigno(x.d))]) } })}` : '<p class="muted">Faltan meses para comparar.</p>'}
      <h3>Mayores cambios del histórico</h3><p class="muted">Cambios mensuales más grandes de cualquier familia; pueden ser meses distintos.</p>
      <div class="tabla"><table><tr><th>Familia</th><th>Mes</th><th class="n">Cambio frente al mes anterior</th></tr>${pan.mayores_cambios.map(c => `<tr><td>${esc(c.familia)}</td><td>${esc(mesLargo(c.periodo))}</td><td class="n">${esc(conSigno(c.cambio_cop))}${c.cambio_pct == null ? " (base 0)" : ` (${num(c.cambio_pct)} %)`}</td></tr>`).join("")}</table></div>
    </section>
  </div>
  ${verDatos({ tabla: { cabeceras: ["Mes", "Tipo", `${famSel} (COP)`], numericas: new Set([2]), filas: [...g.historico.map(p => [esc(mesLargo(p.periodo)), "Observado", desc(p, "Histórico")]), ...g.pronostico.map(p => [esc(mesLargo(p.periodo)), "Proyección", desc(p, "Proyección")])] },
    fuente: `${fuenteCierre(pan.cierre)} · tabla «series_mensuales»`, filtros: esc(`serie ${serie} · familia ${famSel}`), actualizado: esc(`Datos hasta el ${fechaLarga(pan.cierre.corte)}`), regla: esc(pan.agregacion) })}`;
}

function enlazarSerie(serie, q) {
  document.getElementById("fam")?.addEventListener("change", e => {
    const p = new URLSearchParams(q); p.set("serie", serie); p.set("familia", e.target.value); ir(`#/finanzas?${p}`);
  });
  document.getElementById("par")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target), p = new URLSearchParams(q);
    p.set("serie", serie); p.set("desde", fd.get("desde")); p.set("hasta", fd.get("hasta")); ir(`#/finanzas?${p}`);
  });
}

// ---------------------------------------------------------------- simulación del tipo de cambio (entrada 18)
function simulador(pan, q) {
  const periodo = q.get("periodo") || pan.cierre.corte.slice(0, 7);
  return `<section class="panel" id="simulador"><h2>¿Cuánto cambiaría el costo de las compras en dólares si cambia el tipo de cambio?</h2>
  <p class="muted">Escenario hipotético: no modifica el cierre publicado. «Tipo de cambio» es la tasa de pesos por dólar de cada compra (TRM).</p>
  <form id="sim" class="filtros"><label>Mes de las compras <input name="periodo" value="${esc(periodo)}" pattern="\\d{4}-\\d{2}" placeholder="2026-10"></label>
    <input type="hidden" name="moneda" value="USD"><label>Si el dólar cambia (%) <input name="variacion" type="number" step="0.5" min="-50" max="50" value="${esc(q.get("variacion") || "8")}"></label><button>Simular</button></form>
  <div id="res" aria-live="polite"></div></section>`;
}

function resultadoSimulacion(r) {
  const mes = mesLargo(r.periodo);
  if (r.estado === "sin_datos") return estadoHtml("", `No hay compras publicadas en ${mes}: no hay nada que simular.`);
  if (r.estado === "sin_exposicion") return estadoHtml("", `En ${mes} hubo compras, pero ninguna en dólares: el tipo de cambio no afecta su costo.${r.componente_cop_sin_cambio ? ` Compras en pesos: ${pesos(r.componente_cop_sin_cambio)}.` : ""}`);
  if (r.estado === "sin_tasa") return estadoHtml("error", `Hay compras en dólares en ${mes}, pero ninguna tiene tasa registrada (${r.operaciones_sin_tasa.join(", ")}). No se puede simular.`);
  const v = r.variacion_pct, d = r.diferencia_cop;
  const verbo = v >= 0 ? "subiera" : "bajara";
  const frase = `<strong>Si el dólar ${verbo} ${num(Math.abs(v))} %, esas compras pasarían de ${pesos(r.base_cop)} a ${pesos(r.simulado_cop)}.</strong> ${d === 0 ? "Su costo no cambiaría." : `Costarían ${pesos(Math.abs(d))} ${d > 0 ? "más" : "menos"}.`}`;
  const parcial = r.estado === "parcial" ? estadoHtml("error", `Escenario parcial: ${plural(r.operaciones_sin_tasa.length, "compra en dólares quedó excluida", "compras en dólares quedaron excluidas")} por falta de tasa (${r.operaciones_sin_tasa.join(", ")}).`) : "";
  const incl = r.operaciones_incluidas || [];
  const pesosLista = r.compras_en_pesos || [];
  return `${respuesta(frase, `Compras en dólares de ${esc(mes)} · ${esc(r.indicador)}`)}${parcial}
    ${barras([{ etiqueta: "Costo con la tasa registrada", valor: r.base_cop, texto: pesos(r.base_cop) }, { etiqueta: `Costo si el dólar ${verbo} ${num(Math.abs(v))} %`, valor: r.simulado_cop, texto: pesos(r.simulado_cop) }], { etiquetaAria: "Costo base y simulado de las compras en dólares" })}
    <details class="ver-datos" open><summary>Desglose por proveedor y familia</summary>${r.detalle?.length ? `<div class="tabla"><table><tr><th>Proveedor</th><th>Familia</th><th class="n">Costo base</th><th class="n">Costo simulado</th><th class="n">Diferencia</th></tr>${r.detalle.map(x => `<tr><td>${esc(x.proveedor || x.proveedor_id || "—")}</td><td>${esc(x.familia || "—")}</td><td class="n">${pesos(x.costo_base_cop)}</td><td class="n">${pesos(x.costo_escenario_cop)}</td><td class="n">${pesos(x.diferencia_cop)}</td></tr>`).join("")}</table></div>` : '<p class="muted">Sin desglose.</p>'}</details>
    ${verDatos({ titulo: "Ver operaciones, supuestos y exclusiones", tabla: incl.length ? { cabeceras: ["Compra", "Fecha", "Proveedor", "Cantidad × costo unitario", "Tasa", "Costo base"], numericas: new Set([5]), filas: incl.map(o => [esc(o.compra_id), esc(fechaLarga(o.fecha)), esc(o.proveedor), esc(`${num(o.cantidad)} × ${num(o.costo_unitario)} ${o.moneda}`), num(o.tasa), pesos(o.costo_base_cop)]) } : null,
      fuente: esc(`Tabla «${r.fuente}» del cierre ${r.cierre}`), regla: esc(r.supuestos.join(". ")),
      extra: `${pesosLista.length ? `<p><strong>Compras en pesos (no cambian):</strong> ${esc(pesos(r.componente_cop_sin_cambio))} en ${plural(pesosLista.length, "operación", "operaciones")} (${pesosLista.map(x => esc(x.compra_id)).join(", ")}).</p>` : ""}
        ${r.operaciones_sin_tasa?.length ? `<p><strong>Excluidas por falta de tasa:</strong> ${esc(r.operaciones_sin_tasa.join(", "))}.</p>` : "<p>No hay operaciones excluidas.</p>"}` })}`;
}

function enlazarSimulador() {
  document.getElementById("sim")?.addEventListener("submit", async e => {
    e.preventDefault();
    const p = new URLSearchParams(new FormData(e.target));
    try { document.getElementById("res").innerHTML = resultadoSimulacion(await api("GET", `/api/finanzas/${S.cierre}/simular?${p}`)); }
    catch (err) { document.getElementById("res").innerHTML = errorHtml(err); }
  });
}

// ---------------------------------------------------------------- informes mensuales (entrada 19)
function seccionInformes(informes, cierres, soloInformes) {
  const activo = cierres.find(c => S.cierre === "activo" ? c.activo : c.id === S.cierre);
  const mesActivo = activo ? mesLargo(activo.corte) : "del cierre vigente";
  const filas = informes.map(i => `<tr><td><a href="/api/informes/${esc(i.cierre_id)}/${i.revision}" target="_blank" rel="noopener">Abrir informe de ${esc(i.corte ? mesLargo(i.corte) : i.cierre_id)} · revisión ${i.revision}</a></td>
    <td>${esc(fechaHora(i.generado_en))}</td><td>${esc(i.autor || i.generado_por)}</td><td>${i.estado === "disponible" ? "Disponible" : esc(i.estado || "—")}</td></tr>`).join("");
  return `<section class="panel"><h2>${soloInformes ? "Informes publicados" : "Informes mensuales"}</h2>
    ${soloInformes ? respuesta(informes.length ? `<strong>Último informe: ${esc(informes[0].corte ? mesLargo(informes[0].corte) : informes[0].cierre_id)}, revisión ${informes[0].revision}.</strong>` : "<strong>Todavía no hay informes generados.</strong>", "Cada informe reproduce el cierre de su mes.") : ""}
    ${puede("informes.generar") ? `<div class="fila"><button id="gen">Generar informe de ${esc(mesActivo)}</button><span class="muted">Si el contenido no cambió desde la última revisión, la aplicación reutiliza esa revisión en lugar de crear otra.</span></div><div id="msg"></div>` : ""}
    <div class="tabla"><table><tr><th>Informe</th><th>Generado</th><th>Autor</th><th>Estado</th></tr>${filas || '<tr><td colspan=4 class="muted">Sin informes.</td></tr>'}</table></div>
    ${informes.length ? detalleTecnico(`<table><tr><th>Cierre</th><th>Revisión</th><th>Huella del contenido</th></tr>${informes.map(i => `<tr><td>${esc(i.cierre_id)}</td><td>${i.revision}</td><td><code>${esc(i.huella_contenido)}</code></td></tr>`).join("")}</table>`, "Verificación (huella del contenido)") : ""}</section>`;
}

function enlazarInformes() {
  document.getElementById("gen")?.addEventListener("click", async e => {
    e.target.disabled = true;
    try {
      const r = await api("POST", "/api/informes", { cierre: S.cierre });
      await vistaFinanzas();
      document.getElementById("msg").innerHTML = estadoHtml("ok", r.reutilizado ? `El contenido es idéntico al de la revisión ${r.revision}: se reutiliza esa revisión y no se creó otra.` : `Informe generado: revisión ${r.revision}.`);
    } catch (err) { document.getElementById("msg").innerHTML = errorHtml(err); e.target.disabled = false; }
  });
}
