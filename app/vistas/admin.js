import { $vista, api, esc, errorHtml } from "../nucleo.js";
import { encabezado } from "../ui.js";

export async function vistaAdmin() {
  let usuarios, roles, permisos;
  try {
    [usuarios, roles, permisos] = await Promise.all([api("GET", "/api/usuarios"), api("GET", "/api/roles"), api("GET", "/api/permisos")]);
  } catch (e) { $vista.innerHTML = `${encabezado({ titulo: "Administración" })}${errorHtml(e, { reintentar: true })}`; return; }
  const opcionesRol = roles.filter(r => r.activo).map(r => `<option value="${esc(r.id)}">${esc(r.nombre)}</option>`).join("");
  const fila = u => `<tr><td>${esc(u.usuario)}</td><td>${esc(u.nombre)}</td><td>${esc(u.rol || "—")}</td><td>${u.activo ? "Activo" : "Inactivo"}</td><td><button class="sec" data-usuario="${esc(u.id)}" data-activo="${u.activo ? "false" : "true"}">${u.activo ? "Desactivar" : "Activar"}</button></td></tr>`;
  const casillas = permisos.map(p => `<label class="en-linea"><input type="checkbox" name="permisos" value="${esc(p)}"> ${esc(p)}</label>`).join("");
  $vista.innerHTML = `${encabezado({ titulo: "Administración", descripcion: "Gestiona usuarios y crea roles con permisos existentes de JACOMIND." })}
    <div class="grid2"><section class="panel"><h2>Crear usuario</h2><form id="f-usuario" class="campos">
      <label>Usuario <input name="usuario" required autocomplete="off" pattern="[A-Za-z0-9_-]+"></label>
      <label>Nombre <input name="nombre" required></label>
      <label>Rol <select name="rol">${opcionesRol}</select></label>
      <label>Contraseña inicial <input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
      <button>Crear usuario</button></form><div id="res-usuario" aria-live="polite"></div></section>
    <section class="panel"><h2>Usuarios registrados</h2><div class="tabla"><table><thead><tr><th>Usuario</th><th>Nombre</th><th>Rol</th><th>Estado</th><th>Acción</th></tr></thead><tbody>${usuarios.map(fila).join("") || '<tr><td colspan="5">No hay usuarios locales.</td></tr>'}</tbody></table></div></section></div>
    <section class="panel"><h2>Crear rol</h2><form id="f-rol" class="campos"><label>Identificador <input name="id" required pattern="[A-Za-z0-9_-]+" placeholder="analista"></label><label>Nombre visible <input name="nombre" required></label><fieldset><legend>Permisos</legend><div class="opciones-origen">${casillas}</div></fieldset><button>Crear rol</button></form><div id="res-rol" aria-live="polite"></div></section>
    <section class="panel"><h2>Roles existentes</h2><div class="tabla"><table><thead><tr><th>Identificador</th><th>Nombre</th><th>Tipo</th><th>Estado</th><th>Permisos</th></tr></thead><tbody>${roles.map(r => `<tr><td>${esc(r.id)}</td><td>${esc(r.nombre)}</td><td>${r.sistema ? "Sistema" : "Personalizado"}</td><td>${r.activo ? "Activo" : "Inactivo"}</td><td>${esc((r.permisos || []).join(", ") || "Sin permisos")}</td></tr>`).join("")}</tbody></table></div></section>`;
  document.getElementById("f-usuario").addEventListener("submit", async e => {
    e.preventDefault(); const form = e.target, res = document.getElementById("res-usuario"), b = form.querySelector("button"); b.disabled = true;
    try { await api("POST", "/api/usuarios", Object.fromEntries(new FormData(form))); res.innerHTML = '<div class="estado ok" role="status">Usuario creado correctamente.</div>'; setTimeout(vistaAdmin, 0); }
    catch (err) { res.innerHTML = errorHtml(err); } finally { b.disabled = false; }
  });
  document.getElementById("f-rol").addEventListener("submit", async e => {
    e.preventDefault(); const form = e.target, res = document.getElementById("res-rol"), b = form.querySelector("button"); b.disabled = true;
    const datos = Object.fromEntries(new FormData(form)); datos.permisos = [...form.querySelectorAll("input[name=permisos]:checked")].map(x => x.value);
    try { await api("POST", "/api/roles", datos); res.innerHTML = '<div class="estado ok" role="status">Rol creado correctamente.</div>'; setTimeout(vistaAdmin, 0); }
    catch (err) { res.innerHTML = errorHtml(err); } finally { b.disabled = false; }
  });
  $vista.querySelectorAll("[data-usuario]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true; try { await api("PATCH", `/api/usuarios/${encodeURIComponent(b.dataset.usuario)}`, { activo: b.dataset.activo === "true" }); vistaAdmin(); }
    catch (err) { b.insertAdjacentHTML("afterend", errorHtml(err)); b.disabled = false; }
  }));
}
