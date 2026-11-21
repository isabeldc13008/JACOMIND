"""Genera la versión de formación del visor local de referencia (material complementario del plan de vistas).

El visor original pertenece al paquete de prueba y su integridad está fijada en MANIFIESTO_SHA256.txt, así que no
se modifica: este script lo lee, comprueba su huella, toma la misma fotografía de datos y escribe una copia que
muestra el recuento seleccionado y el detalle en palabras («última compra», «días sin comprar», «coberturas» y
«motivo de prioridad»), con el registro original desplegable para la persona técnica.

Uso: python docs/formacion/generar_visor.py [--paquete ../Green_Services_Recursos_de_Prueba] [--salida docs/formacion/visor-formacion.html]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RUTA_VISOR = "04_Codigo/Visor_local_de_referencia.html"


def leer_datos(paquete: Path) -> tuple[list[dict], str]:
    visor = paquete / RUTA_VISOR
    contenido = visor.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    manifiesto = (paquete / "MANIFIESTO_SHA256.txt").read_text(encoding="utf-8")
    esperada = next((l.split()[0] for l in manifiesto.splitlines() if l.strip().endswith(RUTA_VISOR)), None)
    if esperada != huella:
        raise SystemExit(f"La huella del visor no coincide con el manifiesto ({huella} ≠ {esperada}); no se genera la copia.")
    m = re.search(r"const data=(\[.*?\]);const money", contenido.decode("utf-8"), re.S)
    if not m:
        raise SystemExit("No se encontró la fotografía de datos en el visor original.")
    datos = json.loads(m.group(1))
    for d in datos:  # el original trae «frío» dañado (carácter de reemplazo + guion suave)
        d["prioridad_regla"] = d["prioridad_regla"].replace("�\xad", "í")
    return datos, huella


PLANTILLA = """<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Visor de formación · Green Services (datos de prueba)</title>
<style>
body{font:16px/1.5 system-ui,Arial,sans-serif;background:#f3f5fa;color:#152750;margin:0}main{max-width:1100px;margin:auto;padding:20px}
h1{font-size:26px;margin:0 0 4px}.aviso{border-left:6px solid #e0a100;background:#fff8e6;padding:12px 16px;border-radius:6px}
.filtros{display:flex;flex-wrap:wrap;gap:12px;align-items:end;margin:16px 0 8px}label{display:grid;gap:2px;font-size:14px;color:#3d4a6b}
input,select{padding:10px;font-size:16px;border:1px solid #c5cbe0;border-radius:6px}.cuenta{font-weight:700;margin:8px 0}
.tabla{overflow-x:auto;background:#fff;border-radius:8px}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:10px;border-bottom:1px solid #e3e6ef}
th{background:#152750;color:#fff;font-weight:600}td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
button{padding:8px 12px;background:#6654c0;color:#fff;border:0;border-radius:6px;cursor:pointer;font-size:15px}
#detalle{background:#fff;border-radius:8px;padding:16px;margin-top:16px}dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px 20px;margin:8px 0}
dt{font-size:13px;color:#56607a}dd{margin:0;font-weight:600}pre{white-space:pre-wrap;background:#f3f5fa;padding:10px;border-radius:6px;font-size:13px}
:focus-visible{outline:3px solid #2a78d6;outline-offset:2px}
@media (max-width:640px){table,tbody,tr,td{display:block;width:100%}thead{position:absolute;clip:rect(0 0 0 0);width:1px;height:1px;overflow:hidden}
tr{border-bottom:2px solid #e3e6ef;padding:8px}td{border:0;padding:3px 0;text-align:left!important}td[data-et]::before{content:attr(data-et);display:block;font-size:12px;color:#56607a}}
</style></head><body><main>
<h1>Visor de formación</h1><p>Green Services · EstudIA · versión para formación del visor local de referencia</p>
<p class="aviso" role="note"><strong>Fotografía precalculada con datos de prueba.</strong> Fecha fija del ejemplo: <strong>31 de octubre de 2026</strong>.
Las prioridades salen de reglas; no es una predicción ni contiene información real de la empresa. No se actualiza al modificar los CSV.</p>
<div class="filtros"><label>Buscar cliente <input id="q" placeholder="Ejemplo: CLI001" autocomplete="off"></label>
<label>Mostrar <select id="f"><option value="todos">Todos los clientes</option><option value="frio">Con 90 días o más sin comprar</option><option value="renovar">Con coberturas que vencen en 45 días</option></select></label></div>
<p class="cuenta" id="n" aria-live="polite"></p>
<div class="tabla"><table><thead><tr><th>Cliente</th><th>Motivo de prioridad</th><th class="n">Días sin comprar</th><th class="n">Ingreso acumulado</th><th><span style="position:absolute;clip:rect(0 0 0 0)">Detalle</span></th></tr></thead><tbody id="cuerpo"></tbody></table></div>
<section id="detalle" aria-live="polite"><h2>Detalle del cliente</h2><p>Pulsa «Ver detalle» en un cliente para explicar su prioridad.</p></section>
<p style="font-size:13px;color:#56607a">Generado a partir de 04_Codigo/Visor_local_de_referencia.html (SHA-256 __HUELLA__). Mismos __N__ registros que el original.</p>
</main>
<script>
const datos = __DATOS__;
const MESES = ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"];
const fecha = f => { if (!f) return "Sin compras registradas"; const [a, m, d] = f.split("-"); return `${Number(d)} de ${MESES[Number(m) - 1]} de ${a}`; };
const pesos = x => x >= 1e6 ? `${new Intl.NumberFormat("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(x / 1e6)} millones de COP` : `${new Intl.NumberFormat("es-CO", { maximumFractionDigits: 0 }).format(x)} COP`;
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
function porQue(x) {
  if (x.prioridad_regla.startsWith("Revisar cliente")) return `Han pasado ${x.dias_sin_compra} días desde su última compra (90 o más se considera pausa).`;
  if (x.prioridad_regla === "Revisar cobertura") return [x.renovaciones_proximas && `${plural(x.renovaciones_proximas, "cobertura vence", "coberturas vencen")} en los próximos 45 días`, x.coberturas_vencidas && `${plural(x.coberturas_vencidas, "cobertura vencida", "coberturas vencidas")}`].filter(Boolean).join(" y ") + " al 31 de octubre de 2026.";
  return x.sin_compras ? "Sin compras registradas." : "Sin alertas por regla.";
}
function texto(el, t) { el.textContent = t; return el; }
function detalle(x) {
  const s = document.getElementById("detalle"); s.replaceChildren();
  s.append(texto(document.createElement("h2"), `Detalle de ${x.cliente_id}`), texto(document.createElement("p"), `${x.prioridad_regla}. ${porQue(x)}`));
  const dl = document.createElement("dl");
  for (const [k, v] of [["Última compra", fecha(x.ultima_compra)], ["Días sin comprar al 31 de octubre de 2026", x.dias_sin_compra ?? "—"],
    ["Coberturas", `${x.renovaciones_proximas} vencen en 45 días · ${x.coberturas_vencidas} vencidas`], ["Motivo de prioridad", x.prioridad_regla],
    ["Ventas confirmadas", x.transacciones_confirmadas], ["Ingreso acumulado", pesos(x.ingreso_cop)],
    ["Etiquetas", [x.frecuente && "Frecuente", x.frio && "90 días o más sin comprar"].filter(Boolean).join(" · ") || "Ninguna"]]) {
    const div = document.createElement("div"); div.append(texto(document.createElement("dt"), k), texto(document.createElement("dd"), String(v))); dl.append(div);
  }
  const det = document.createElement("details"); det.append(texto(document.createElement("summary"), "Registro original (para la persona técnica)"), texto(document.createElement("pre"), JSON.stringify(x, null, 2)));
  s.append(dl, det); s.focus();
}
function mostrar() {
  const q = document.getElementById("q").value.toLowerCase(), f = document.getElementById("f").value;
  let a = datos.filter(x => x.cliente_id.toLowerCase().includes(q));
  if (f === "frio") a = a.filter(x => x.frio);
  if (f === "renovar") a = a.filter(x => x.renovaciones_proximas > 0);
  document.getElementById("n").textContent = `${a.length} de ${datos.length} clientes seleccionados`;
  const cuerpo = document.getElementById("cuerpo"); cuerpo.replaceChildren();
  for (const x of a) {
    const tr = document.createElement("tr");
    const celdas = [[x.cliente_id, null, ""], [x.prioridad_regla, "Motivo de prioridad", ""], [x.dias_sin_compra ?? "Sin compras", "Días sin comprar", "n"], [pesos(x.ingreso_cop), "Ingreso acumulado", "n"]];
    for (const [v, et, cl] of celdas) { const td = texto(document.createElement("td"), String(v)); if (et) td.dataset.et = et; if (cl) td.className = cl; tr.append(td); }
    const td = document.createElement("td"), b = texto(document.createElement("button"), "Ver detalle");
    b.setAttribute("aria-label", `Ver detalle de ${x.cliente_id}`); b.onclick = () => detalle(x); td.append(b); tr.append(td); cuerpo.append(tr);
  }
}
document.getElementById("detalle").tabIndex = -1;
document.getElementById("q").oninput = mostrar; document.getElementById("f").onchange = mostrar; mostrar();
</script></body></html>
"""


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--paquete", default=str(RAIZ.parent / "Green_Services_Recursos_de_Prueba"))
    p.add_argument("--salida", default=str(Path(__file__).with_name("visor-formacion.html")))
    a = p.parse_args()
    datos, huella = leer_datos(Path(a.paquete))
    html = (PLANTILLA.replace("__DATOS__", json.dumps(datos, ensure_ascii=False).replace("</", "<\\/"))
            .replace("__HUELLA__", huella[:16]).replace("__N__", str(len(datos))))
    Path(a.salida).write_text(html, encoding="utf-8")
    print(f"{a.salida}: {len(datos)} clientes (original {huella[:16]})")


if __name__ == "__main__":
    main()
