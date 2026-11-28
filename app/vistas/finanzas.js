// V13 Resultado del mes, V15 Escenarios del dólar (TRM) y V16 Informes mensuales: secciones de Finanzas con contexto común.
// El Pronóstico (M5) vive en #/demanda y comparte estas pestañas.
import {
  $vista, S, api, conSigno, cop, errorHtml, esc, estadoHtml, fechaHora, fechaLarga, ir, mesLargo, millones, nuevoTurno, num, plural, puede, ruta, vigente,
} from "../nucleo.js";
import {
  activarTooltips, barras, confirmar, ctxDatos, detalleTecnico, encabezado, fuenteCierre, graficoLinea, hallazgo, indicadores, pestanas, tablaHtml, vacio, verDatos,
} from "../ui.js";

const pesos = x => x == null ? "—" : `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(Math.round(x))} COP`;
const PREGUNTA = { ventas: "Ventas", compras: "Compras a proveedores" };
const VERBO = { ventas: "se vendieron", compras: "se compraron a proveedores" };
const SECCIONES = { resultado: "Resultado del mes", escenarios: "Escenarios del dólar", informes: "Informes mensuales" };

/** Pestañas compartidas por las secciones de Finanzas (y por el Pronóstico). Solo las autorizadas. */
export function pestanasFinanzas(activa) {
  const items = [];
  if (puede("finanzas.ver")) items.push(["resultado", "Resultado", "#/finanzas?seccion=resultado"]);
  if (puede("finanzas.ver") && (puede("demanda.ver_cop") || puede("demanda.ver_unidades"))) items.push(["pronostico", "Pronóstico", "#/demanda"]);
  if (puede("finanzas.ver")) items.push(["escenarios", "Escenarios del dólar", "#/finanzas?seccion=escenarios"]);
  if (puede("informes.ver")) items.push(["informes", "Informes", "#/finanzas?seccion=informes"]);
  return items.length > 1 ? pestanas(items, activa, "Secciones de Finanzas") : "";
}

export async function vistaFinanzas() {
  const { q } = ruta();
  const pedida = q.get("seccion");
  const seccion = !puede("finanzas.ver") ? "informes" : SECCIONES[pedida] ? pedida : q.get("periodo") || q.get("variacion") ? "escenarios" : "resultado";
  const serie = q.get("serie") === "compras" ? "compras" : "ventas";
  const turno = nuevoTurno();
  const titulo = SECCIONES[seccion];
  if (!$vista.querySelector(`[data-seccion="${seccion}"]`)) $vista.innerHTML = `${encabezado({ titulo })}${pestanasFinanzas(seccion)}${estadoHtml("", "Cargando…")}`;
  let pan = null, informes = [], cierres = [];
  try {
    [pan, informes, cierres] = await Promise.all([
      seccion !== "informes" ? api("GET", `/api/finanzas/${S.cierre}/panel?serie=${seccion === "escenarios" ? "compras" : serie}`) : null,
      seccion === "informes" ? api("GET", "/api/informes") : [],
      seccion === "informes" ? api("GET", "/api/cierres").catch(() => []) : []]);
  } catch (e) { if (vigente(turno)) $vista.innerHTML = `${encabezado({ titulo })}${pestanasFinanzas(seccion)}${errorHtml(e, { reintentar: true })}`; return; }
  if (!vigente(turno)) return;
  const corte = pan?.cierre?.corte || S.estadoApi?.corte_activo;
  const cuerpo = seccion === "resultado" ? panelSerie(pan, serie, q) : seccion === "escenarios" ? simulador(pan, q) : seccionInformes(informes, cierres);
  const descripcion = { resultado: "Cuánto se vendió y se compró cada mes, y qué familia explica los cambios. Son datos registrados, no estimaciones.",
    escenarios: "Qué pasaría con el costo de las compras en dólares de un mes si el dólar hubiera estado más alto o más bajo. No es una predicción del dólar.",
    informes: "Versión del cierre lista para llevar a una reunión: las mismas cifras y la misma revisión que ves en la aplicación." }[seccion];
  $vista.innerHTML = `<div data-seccion="${seccion}">${encabezado({ titulo, descripcion, contexto: [ctxDatos(corte), pan?.cierre?.id ? { etiqueta: "Cierre", valor: esc(pan.cierre.id) } : null] })}
    ${pestanasFinanzas(seccion)}${cuerpo}</div>`;
  activarTooltips();
  if (seccion === "resultado") enlazarSerie(serie, q);
  if (seccion === "escenarios") enlazarSimulador(q);
  if (seccion === "informes") enlazarInformes();
}

// ---------------------------------------------------------------- V13 · resultado
function ultimoPar(hist) {
  const completos = hist.filter(p => p.valor_cop != null && p.completo !== false);
  return completos.length >= 2 ? [completos.at(-2), completos.at(-1)] : completos.length ? [null, completos.at(-1)] : [null, null];
}

function panelSerie(pan, serie, q) {
  const fams = pan.familias.map(f => f.familia);
  const famSel = fams.includes(q.get("familia")) ? q.get("familia") : "Total";
  const g = pan.familias.find(f => f.familia === famSel);
  const enlace = cambio => { const n = new URLSearchParams(q); n.set("seccion", "resultado"); for (const [a, b] of Object.entries(cambio)) b ? n.set(a, b) : n.delete(a); return `#/finanzas?${n}`; };
  const serieNav = pestanas(["ventas", "compras"].map(s => [s, PREGUNTA[s], enlace({ serie: s === "ventas" ? "" : s, familia: "" })]), serie, "Qué serie ver");
  if (!pan.disponible || !g) return `${serieNav}${vacio("Este cierre no publica la serie mensual.", "No hay datos observados ni proyección que mostrar.")}`;
  const [ant, ult] = ultimoPar(g.historico);
  const incompletos = g.historico.filter(p => p.valor_cop == null || p.completo === false).map(p => p.periodo);
  const etiquetaFam = famSel === "Total" ? "" : ` en la familia ${famSel}`;
  const d = ult && ant ? ult.valor_cop - ant.valor_cop : null;
  const porc = d != null && ant.valor_cop > 0 ? `${d < 0 ? "−" : "+"}${num(Math.round(Math.abs(d / ant.valor_cop * 1000)) / 10)} %` : d != null ? "sin base porcentual" : null;
  const que = ult ? `En <strong>${esc(mesLargo(ult.periodo))}</strong> ${VERBO[serie]} <strong>${esc(millones(ult.valor_cop))}</strong>${esc(etiquetaFam)}.${ult.valor_cop === 0 ? " Fue un mes sin operaciones registradas, no un dato ausente." : ""}` : "No hay meses completos publicados.";
  const porque = d != null ? `Frente a ${esc(mesLargo(ant.periodo))}, ${d === 0 ? "no cambió" : `fueron ${esc(millones(Math.abs(d)))} ${d < 0 ? "menos" : "más"} (${esc(porc)})`}.` : ult ? "No hay un mes anterior completo para comparar." : "";
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
    return `<li>A ${plural(Number(h), "mes", "meses")}: ${m == null ? "sin comprobar (faltan meses)" : `se desvió en promedio ${esc(millones(m))} en meses ya conocidos`}${ing != null ? `; repetir el último mes se desvió ${esc(millones(ing))}` : ""}.</li>`;
  }).join("");
  return `${serieNav}
  ${hallazgo({ que, porque: `${porque} ${famSel === "Total" && comp[0]?.d != null ? `La familia ${esc(comp[0].familia)} explica el cambio más grande (${esc(conSigno(comp[0].d))}).` : ""}`,
    accion: '<button type="button" class="sec" data-ir-a="comparacion-familias">Ver la comparación por familia</button>' })}
  ${indicadores([
    ult && { etiqueta: `${PREGUNTA[serie]} de ${mesLargo(ult.periodo)}`, valor: esc(millones(ult.valor_cop)), detalle: `último mes completo · ${esc(famSel === "Total" ? "todas las familias" : famSel)} · COP` },
    d != null && { etiqueta: "Cambio frente al mes anterior", valor: esc(conSigno(d)), detalle: `${esc(porc)} · base: ${esc(mesLargo(ant.periodo))}` },
  ])}
  ${incompletos.length ? `<p class="aviso-cifras" role="note">Mes incompleto sin dato: ${esc(incompletos.map(mesLargo).join(", "))}. Es distinto de un mes con 0 COP y no se compara.</p>` : ""}
  <div>
    <section class="panel"><h2>${esc(PREGUNTA[serie])} por mes</h2>
      <form id="fam" class="fila"><label>Familia <select name="familia">${fams.map(f => `<option ${f === famSel ? "selected" : ""}>${esc(f)}</option>`).join("")}</select></label></form>
      ${graficoLinea(g.historico.map(s => ({ periodo: s.periodo, valor: s.valor_cop })), g.pronostico.map(s => ({ periodo: s.periodo, valor: s.valor_cop })),
        { marcas: [ant?.periodo, ult?.periodo].filter(Boolean), titulo: `${PREGUNTA[serie]} · ${famSel === "Total" ? "todas las familias" : famSel}, por mes`, etiquetaEstimado: "Proyección operativa" })}
      <p class="muted">La proyección operativa del cierre (regla A08: ${esc(g.metodo || "—")}) no es ingreso confirmado. Es distinta del pronóstico de la pestaña «Pronóstico».</p>
      ${g.pronostico.length ? `<details class="ver-datos"><summary>Cómo se calcula la proyección operativa</summary><p>Regla ${esc(g.metodo || "—")}, calculada el ${esc(fechaHora(g.calculado_en))}. Error en meses ya conocidos:</p><ul>${mae || "<li>Sin comprobar.</li>"}</ul></details>` : ""}
    </section>
    <section class="panel" id="comparacion-familias" tabindex="-1"><h2>¿Qué familia cambió más?</h2>
      <form id="par" class="filtros"><label>Desde ${selMes("desde", desde)}</label><label>Hasta ${selMes("hasta", hasta)}</label><button class="sec">Comparar estos meses</button></form>
      ${desde && hasta ? `${barras(comp.filter(x => x.d != null).map(x => ({ etiqueta: x.familia, valor: x.d, texto: conSigno(x.d), href: enlace({ familia: x.familia }), activo: x.familia === famSel })), { signo: true, etiquetaAria: `Diferencia por familia entre ${mesLargo(desde)} y ${mesLargo(hasta)}; pulsa una para ver su serie` })}
      <p class="muted">Diferencia entre ${esc(mesLargo(desde))} y ${esc(mesLargo(hasta))}. Las barras rayadas con «−» son disminuciones. Pulsa una familia para ver su serie.</p>
      ${verDatos({ titulo: "Ver cifras exactas de la comparación", tabla: { cabeceras: ["Familia", mesLargo(desde), mesLargo(hasta), "Diferencia"], numericas: new Set([1, 2, 3]), filas: comp.map(x => [esc(x.familia), x.a == null ? "Sin dato" : cop(x.a), x.b == null ? "Sin dato" : cop(x.b), x.d == null ? "—" : esc(conSigno(x.d))]) } })}` : vacio("Faltan meses para comparar.")}
    </section>
  </div>
  <details class="panel"><summary>Ver los mayores cambios mensuales del histórico</summary>
    <p class="muted">Cambios más grandes de cualquier familia frente a su mes anterior; pueden ser meses distintos.</p>
    ${tablaHtml({ cabeceras: ["Familia", "Mes", "Cambio frente al mes anterior"], numericas: new Set([2]), filas: pan.mayores_cambios.map(c => [esc(c.familia), esc(mesLargo(c.periodo)), `${esc(conSigno(c.cambio_cop))}${c.cambio_pct == null ? " (sin base porcentual)" : ` (${num(c.cambio_pct)} %)`}`]) })}</details>
  ${verDatos({ tabla: { cabeceras: ["Mes", "Tipo", `${famSel} (COP)`], numericas: new Set([2]), filas: [...g.historico.map(p => [esc(mesLargo(p.periodo)), "Observado", desc(p, "Histórico")]), ...g.pronostico.map(p => [esc(mesLargo(p.periodo)), "Proyección operativa", desc(p, "Proyección")])] },
    fuente: `${fuenteCierre(pan.cierre)} · tabla «series_mensuales»`, filtros: esc(`serie ${serie} · familia ${famSel}`), actualizado: esc(`Datos hasta el ${fechaLarga(pan.cierre.corte)}`), regla: esc(pan.agregacion) })}`;
}

function enlazarSerie(serie, q) {
  const base = () => { const p = new URLSearchParams(q); p.set("seccion", "resultado"); if (serie === "compras") p.set("serie", serie); return p; };
  document.getElementById("fam")?.addEventListener("change", e => { const p = base(); p.set("familia", e.target.value); ir(`#/finanzas?${p}`); });
  document.getElementById("par")?.addEventListener("submit", e => {
    e.preventDefault();
    const fd = new FormData(e.target), p = base();
    p.set("desde", fd.get("desde")); p.set("hasta", fd.get("hasta")); ir(`#/finanzas?${p}`);
  });
}

// ---------------------------------------------------------------- V15 · escenarios del dólar
function simulador(pan, q) {
  const periodo = q.get("periodo") || pan.cierre.corte.slice(0, 7);
  const meses = [...new Set((pan.familias || []).flatMap(f => f.historico.map(p => p.periodo)))].sort().reverse();
  return `<div class="grid2">
  <section class="panel"><h2>Qué supuesto cambias</h2>
    <p>Eliges un mes y un cambio del dólar (TRM: pesos por dólar). La aplicación recalcula el costo en pesos de las compras de ese mes hechas en dólares.</p>
    <p><strong>Lo que no cambia:</strong> las cantidades, los precios en dólares y las compras hechas en pesos. El cierre publicado tampoco cambia.</p>
    <form id="sim" class="campos" novalidate>
      <label for="periodo-sim">Mes de las compras <select id="periodo-sim" name="periodo">${(meses.length ? meses : [periodo]).map(m => `<option value="${esc(m)}" ${m === periodo ? "selected" : ""}>${esc(mesLargo(m))}</option>`).join("")}</select></label>
      <input type="hidden" name="moneda" value="USD">
      <label for="variacion-sim">Si el dólar cambia (en %) <span class="ayuda">Por ejemplo 8 si sube 8 %, o −5 si baja 5 %. Entre −50 y 50.</span>
        <input id="variacion-sim" name="variacion" type="number" step="0.5" min="-50" max="50" inputmode="decimal" value="${esc(q.get("variacion") || "8")}" aria-describedby="err-var"><span class="error-campo" id="err-var" aria-live="polite"></span></label>
      <div class="fila"><button>Calcular el escenario</button><button type="button" class="sec" id="restablecer">Volver a 0 %</button></div></form>
  </section>
  <section class="panel" aria-live="polite"><h2>Resultado</h2><div id="res">${vacio("Aún no has calculado un escenario.", "Elige el mes y el cambio, y pulsa «Calcular el escenario».")}</div></section></div>`;
}

function resultadoSimulacion(r) {
  const mes = mesLargo(r.periodo);
  if (r.estado === "sin_datos") return vacio(`No hay compras publicadas en ${mes}.`, "No hay nada que recalcular. Elige otro mes.");
  if (r.estado === "sin_exposicion") return vacio(`En ${mes} no hubo compras en dólares.`, `El tipo de cambio no afecta su costo.${r.componente_cop_sin_cambio ? ` Compras en pesos: ${pesos(r.componente_cop_sin_cambio)}.` : ""}`);
  if (r.estado === "sin_tasa") return `<div class="estado error" role="alert"><p><strong>No se puede calcular.</strong> Hay compras en dólares en ${esc(mes)}, pero ninguna tiene tasa registrada (${esc(r.operaciones_sin_tasa.join(", "))}).</p></div>`;
  const v = r.variacion_pct, d = r.diferencia_cop;
  const verbo = v >= 0 ? "subiera" : "bajara";
  const parcial = r.estado === "parcial" ? `<p class="aviso-cifras" role="note">Escenario parcial: ${plural(r.operaciones_sin_tasa.length, "compra en dólares quedó excluida", "compras en dólares quedaron excluidas")} por falta de tasa (${esc(r.operaciones_sin_tasa.join(", "))}).</p>` : "";
  const incl = r.operaciones_incluidas || [];
  const pesosLista = r.compras_en_pesos || [];
  return `<p class="frase"><strong>Si el dólar ${verbo} ${num(Math.abs(v))} %, las compras en dólares de ${esc(mes)} costarían ${pesos(r.simulado_cop)}</strong> en lugar de ${pesos(r.base_cop)}. ${d === 0 ? "Su costo no cambiaría." : `Es decir, ${pesos(Math.abs(d))} ${d > 0 ? "más" : "menos"}.`}</p>${parcial}
    <dl class="comparacion"><div><dt>Costo con la tasa registrada</dt><dd>${pesos(r.base_cop)}</dd></div><div><dt>Costo en el escenario</dt><dd>${pesos(r.simulado_cop)}</dd></div><div><dt>Diferencia</dt><dd>${d === 0 ? "0 COP" : `${d > 0 ? "+" : "−"}${pesos(Math.abs(d))}`}</dd></div></dl>
    ${barras([{ etiqueta: "Con la tasa registrada", valor: r.base_cop, texto: pesos(r.base_cop) }, { etiqueta: `Si el dólar ${verbo} ${num(Math.abs(v))} %`, valor: r.simulado_cop, texto: pesos(r.simulado_cop) }], { etiquetaAria: "Costo base y del escenario, en pesos, desde cero" })}
    <p class="muted">${plural(incl.length, "compra en dólares incluida", "compras en dólares incluidas")}. ${esc(r.indicador)}. No es un pronóstico del dólar ni asegura el costo o el margen futuro.</p>
    <details class="ver-datos"><summary>Ver desglose por proveedor y familia</summary>${r.detalle?.length ? tablaHtml({ cabeceras: ["Proveedor", "Familia", "Costo base", "Costo en el escenario", "Diferencia"], numericas: new Set([2, 3, 4]), filas: r.detalle.map(x => [esc(x.proveedor || x.proveedor_id || "—"), esc(x.familia || "—"), pesos(x.costo_base_cop), pesos(x.costo_escenario_cop), pesos(x.diferencia_cop)]) }) : '<p class="muted">Sin desglose.</p>'}</details>
    ${verDatos({ titulo: "Ver compras, fórmula y exclusiones", tabla: incl.length ? { cabeceras: ["Compra", "Fecha", "Proveedor", "Cantidad × costo unitario", "Tasa", "Costo base"], numericas: new Set([5]), filas: incl.map(o => [esc(o.compra_id), esc(fechaLarga(o.fecha)), esc(o.proveedor), esc(`${num(o.cantidad)} × ${num(o.costo_unitario)} ${o.moneda}`), num(o.tasa), pesos(o.costo_base_cop)]) } : null,
      fuente: esc(`Tabla «${r.fuente}» del cierre ${r.cierre}`), regla: `Costo del escenario = cantidad × costo unitario en dólares × tasa registrada × (1 + cambio ÷ 100). ${esc(r.supuestos.join(". "))}`,
      extra: `${pesosLista.length ? `<p><strong>Compras en pesos (no cambian):</strong> ${esc(pesos(r.componente_cop_sin_cambio))} en ${plural(pesosLista.length, "compra", "compras")} (${pesosLista.map(x => esc(x.compra_id)).join(", ")}).</p>` : ""}
        ${r.operaciones_sin_tasa?.length ? `<p><strong>Excluidas por falta de tasa:</strong> ${esc(r.operaciones_sin_tasa.join(", "))}.</p>` : "<p>No hay compras excluidas.</p>"}` })}`;
}

function enlazarSimulador(q) {
  const form = document.getElementById("sim"), res = document.getElementById("res"), varIn = document.getElementById("variacion-sim");
  let calculado = false;
  const calcular = async () => {
    const v = Number(varIn.value);
    if (varIn.value === "" || Number.isNaN(v) || v < -50 || v > 50) {
      varIn.setAttribute("aria-invalid", "true"); document.getElementById("err-var").textContent = "Escribe un número entre −50 y 50."; varIn.focus(); return;
    }
    varIn.setAttribute("aria-invalid", "false"); document.getElementById("err-var").textContent = "";
    const p = new URLSearchParams(new FormData(form));
    const btn = form.querySelector("button"); btn.disabled = true; btn.textContent = "Calculando…";
    res.innerHTML = estadoHtml("", "Calculando el escenario…");
    try { res.innerHTML = resultadoSimulacion(await api("GET", `/api/finanzas/${S.cierre}/simular?${p}`)); calculado = true; }
    catch (err) { res.innerHTML = errorHtml(err); }
    finally { btn.disabled = false; btn.textContent = "Calcular el escenario"; }
  };
  form.addEventListener("submit", e => { e.preventDefault(); calcular(); });
  // Cambiar un dato invalida el resultado anterior hasta volver a calcular.
  form.addEventListener("input", () => { if (calculado) { res.innerHTML = vacio("Cambiaste los datos del escenario.", "El resultado anterior ya no corresponde. Pulsa «Calcular el escenario»."); calculado = false; } });
  document.getElementById("restablecer").addEventListener("click", () => { varIn.value = "0"; form.dispatchEvent(new Event("input")); calcular(); });
  if (q.get("variacion")) calcular();
}

// ---------------------------------------------------------------- V16 · informes
function seccionInformes(informes, cierres) {
  const activo = cierres.find(c => S.cierre === "activo" ? c.activo : c.id === S.cierre);
  const mesActivo = activo ? mesLargo(activo.corte) : "del cierre vigente";
  const delActivo = activo ? informes.filter(i => i.cierre_id === activo.id) : [];
  const ultimo = delActivo[0] || informes[0];
  const abrir = i => `/api/informes/${esc(i.cierre_id)}/${i.revision}`;
  return `${hallazgo({
    que: ultimo ? `Último informe: <strong>${esc(ultimo.corte ? mesLargo(ultimo.corte) : ultimo.cierre_id)}</strong>, revisión ${num(ultimo.revision)}, generado el ${esc(fechaHora(ultimo.generado_en))}.` : "Todavía no hay informes generados.",
    porque: "Cada informe reproduce un cierre concreto. Sus cifras coinciden con Gerencia y Finanzas para ese mismo cierre y revisión.",
    accion: ultimo ? `<a class="boton" href="${abrir(ultimo)}" target="_blank" rel="noopener">Abrir el informe (pestaña nueva)</a>` : "",
  })}
  ${puede("informes.generar") ? `<section class="panel"><h2>Generar el informe de ${esc(mesActivo)}</h2>
    <p>Crea una revisión nueva solo si el contenido cambió desde la última. Si es idéntico, se reutiliza la revisión existente.</p>
    <div class="fila"><button id="gen">Generar el informe de ${esc(mesActivo)}</button></div><div id="msg" aria-live="polite"></div></section>` : '<p class="muted">Tu perfil puede abrir los informes, pero no generarlos.</p>'}
  <section class="panel"><h2>Historial de informes</h2>
    ${informes.length ? tablaHtml({ cabeceras: ["Informe", "Generado", "Autor", "Estado"], filas: informes.map(i => [`<a href="${abrir(i)}" target="_blank" rel="noopener">${esc(i.corte ? mesLargo(i.corte) : i.cierre_id)} · revisión ${num(i.revision)}<span class="oculto-visual"> (se abre en una pestaña nueva)</span></a>`,
      esc(fechaHora(i.generado_en)), esc(i.autor || i.generado_por), i.estado === "disponible" ? "Disponible" : esc(i.estado || "—")]) }) : vacio("Sin informes todavía.")}
    ${informes.length ? detalleTecnico(tablaHtml({ cabeceras: ["Cierre", "Revisión", "Huella del contenido"], filas: informes.map(i => [esc(i.cierre_id), num(i.revision), `<code>${esc(i.huella_contenido)}</code>`]) }), "Verificación (huella del contenido)") : ""}</section>`;
}

function enlazarInformes() {
  document.getElementById("gen")?.addEventListener("click", async e => {
    const b = e.currentTarget;
    const ok = await confirmar({ titulo: "¿Generar el informe?", mensaje: "<p>Se guardará una revisión con las cifras del cierre vigente. Si nada cambió desde la última revisión, se reutiliza esa y no se crea otra.</p><p>No cambia ningún dato.</p>", confirmar: "Generar el informe" });
    if (!ok) return;
    b.disabled = true; b.textContent = "Generando…";
    try {
      const r = await api("POST", "/api/informes", { cierre: S.cierre });
      await vistaFinanzas();
      document.getElementById("msg").innerHTML = `<div class="estado ok" role="status"><strong>${r.reutilizado ? `El contenido es idéntico al de la revisión ${num(r.revision)}: se reutiliza esa revisión.` : `Informe generado: revisión ${num(r.revision)}.`}</strong> <a href="/api/informes/${esc(r.cierre_id)}/${r.revision}" target="_blank" rel="noopener">Abrir el informe</a></div>`;
    } catch (err) { document.getElementById("msg").innerHTML = errorHtml(err); b.disabled = false; b.textContent = "Volver a intentar"; }
  });
}
