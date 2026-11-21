// Validación del contrato C1 en el navegador (espejo de contratos/validar.py).
// Usa el mismo esquema versionado (/contratos/agenda.v1.schema.json) y las mismas
// comprobaciones semánticas antes de pintar la vista.
export const ACCIONES = ["Revisar reactivación", "Revisar cobertura", "Revisar oportunidad de recompra",
  "Revisar primera compra", "Seguimiento habitual"];
export const ORDEN = Object.fromEntries(ACCIONES.map((a, i) => [a, i + 1]));
const TIPOS = {
  object: v => v !== null && typeof v === "object" && !Array.isArray(v),
  array: Array.isArray, string: v => typeof v === "string", boolean: v => typeof v === "boolean",
  null: v => v === null, integer: v => Number.isInteger(v), number: v => typeof v === "number" && Number.isFinite(v),
};

function fechaValida(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + "T00:00:00Z");
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}

export function validarEsquema(v, e, ruta = "$") {
  const err = [];
  if ("const" in e && v !== e.const) return [`${ruta}: se esperaba ${JSON.stringify(e.const)} y llegó ${JSON.stringify(v)}`];
  if (e.enum && !e.enum.includes(v)) return [`${ruta}: valor ${JSON.stringify(v)} fuera de la lista permitida`];
  if (e.type) {
    const lista = Array.isArray(e.type) ? e.type : [e.type];
    if (!lista.some(t => TIPOS[t](v))) return [`${ruta}: tipo no admitido (esperado ${lista.join("/")})`];
  }
  if (v === null) return err;
  if (typeof v === "string") {
    if (v.length < (e.minLength || 0)) err.push(`${ruta}: texto vacío`);
    if (e.pattern && !new RegExp(e.pattern).test(v)) err.push(`${ruta}: no cumple el patrón`);
    if (e.format === "date" && !fechaValida(v)) err.push(`${ruta}: fecha inválida (${v})`);
  }
  if (typeof v === "number") {
    if ("minimum" in e && v < e.minimum) err.push(`${ruta}: ${v} < ${e.minimum}`);
    if ("maximum" in e && v > e.maximum) err.push(`${ruta}: ${v} > ${e.maximum}`);
  }
  if (TIPOS.object(v)) {
    for (const c of e.required || []) if (!(c in v)) err.push(`${ruta}: falta el campo obligatorio '${c}'`);
    for (const [c, sub] of Object.entries(v)) if (e.properties && e.properties[c]) err.push(...validarEsquema(sub, e.properties[c], `${ruta}.${c}`));
  }
  if (Array.isArray(v) && e.items) v.forEach((x, i) => err.push(...validarEsquema(x, e.items, `${ruta}[${i}]`)));
  return err;
}

export function validarAgenda(datos, esquema) {
  const r = { errores: [], advertencias: [], incompatible: false };
  if (!TIPOS.object(datos)) { r.errores.push("$: la agenda debe ser un objeto JSON"); return r; }
  if (datos.version !== 1) { r.incompatible = true; r.errores.push(`$.version: versión ${JSON.stringify(datos.version)} no soportada (soportada: 1)`); return r; }
  r.errores.push(...validarEsquema(datos, esquema));
  if (r.errores.length) return r;
  const vistos = new Set();
  datos.clientes.forEach((c, i) => {
    const ruta = `$.clientes[${i}]`;
    if (vistos.has(c.cliente_id)) r.errores.push(`${ruta}.cliente_id: ID repetido '${c.cliente_id}'`);
    vistos.add(c.cliente_id);
    if ((c.ultima_compra === null) !== (c.dias_sin_compra === null)) r.errores.push(`${ruta}: ultima_compra y dias_sin_compra deben ser ambos null o ambos informados`);
    if (c.ultima_compra === null && c.frio) r.errores.push(`${ruta}.frio: un cliente sin compras no puede estar frío`);
    if (c.ultima_compra === null && c.ventas_confirmadas !== 0) r.errores.push(`${ruta}: sin última compra pero con ventas`);
    if (c.ultima_compra !== null && c.ventas_confirmadas === 0) r.errores.push(`${ruta}: última compra con 0 ventas`);
  });
  const res = datos.resumen, cl = datos.clientes;
  if (res.clientes !== cl.length) r.errores.push(`$.resumen.clientes=${res.clientes} no coincide con ${cl.length} filas`);
  const frios = cl.filter(c => c.frio).length;
  if (res.clientes_frios !== frios) r.errores.push(`$.resumen.clientes_frios=${res.clientes_frios} no coincide con ${frios}`);
  const ventas = cl.reduce((s, c) => s + c.ventas_confirmadas, 0);
  if (res.ventas_confirmadas !== ventas) r.errores.push(`$.resumen.ventas_confirmadas no coincide con ${ventas}`);
  const ingreso = cl.reduce((s, c) => s + c.ingreso_cop, 0);
  if (Math.abs(res.ingreso_cop - ingreso) > 0.01 * (cl.length + 1)) r.errores.push(`$.resumen.ingreso_cop no coincide con la suma ${ingreso.toFixed(2)}`);
  return r;
}

export function motivos(c, umbral) {
  const m = [];
  if (c.frio) m.push("Revisar reactivación");
  if ((c.renovaciones_proximas || 0) > 0 || (c.coberturas_vencidas || 0) > 0) m.push("Revisar cobertura");
  const p = c.prob_compra_30d;
  if (p !== null && p !== undefined && ((umbral != null && p >= umbral) || (umbral == null && c.accion === "Revisar oportunidad de recompra"))) m.push("Revisar oportunidad de recompra");
  if (c.ultima_compra === null && (c.ventas_confirmadas || 0) === 0) m.push("Revisar primera compra");
  if (c.accion in ORDEN && !m.includes(c.accion) && c.accion !== "Seguimiento habitual") m.push(c.accion);
  m.sort((a, b) => (ORDEN[a] || 99) - (ORDEN[b] || 99));
  return m.length ? m : ["Seguimiento habitual"];
}

export function ordenar(clientes) {
  return [...clientes].sort((a, b) => {
    const d = (ORDEN[a.accion] || 99) - (ORDEN[b.accion] || 99);
    if (d) return d;
    const pa = a.prob_compra_30d, pb = b.prob_compra_30d;
    if ((pa == null) !== (pb == null)) return pa == null ? 1 : -1;
    if (pa != null && pb !== pa) return pb - pa;
    return a.cliente_id < b.cliente_id ? -1 : a.cliente_id > b.cliente_id ? 1 : 0;
  });
}
