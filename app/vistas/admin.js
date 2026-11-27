import { $vista, api, esc, errorHtml } from "../nucleo.js";
import { encabezado } from "../ui.js";

const ROLES = { admin: "Administrador", operaciones: "Operaciones", ventas: "Ventas", finanzas: "Finanzas", atencion: "Atención", gerencia: "Gerencia", empresa: "Empresa" };

export async function vistaAdmin() {
  let usuarios;
  try { usuarios = await api("GET", "/api/usuarios"); }
  catch (e) { $vista.innerHTML = `${encabezado({ titulo: "Usuarios" })}${errorHtml(e, { reintentar: true })}`; return; }
  const fila = u => `<tr><td>${esc(u.usuario)}</td><td>${esc(u.nombre)}</td><td>${esc(ROLES[u.rol] || u.rol)}</td><td>${u.activo ? "Activo" : "Inactivo"}</td><td><button class="sec" data-usuario="${esc(u.id)}" data-activo="${u.activo ? "false" : "true"}">${u.activo ? "Desactivar" : "Activar"}</button></td></tr>`;
  $vista.innerHTML = `${encabezado({ titulo: "Administrar usuarios", descripcion: "Crea cuentas para los perfiles de JACOMIND y controla quién puede entrar." })}
    <div class="grid2"><section class="panel"><h2>Crear usuario</h2><form id="f-usuario" class="campos">
      <label>Usuario <input name="usuario" required autocomplete="off" pattern="[A-Za-z0-9_-]+"></label>
      <label>Nombre <input name="nombre" required></label>
      <label>Perfil <select name="rol">${Object.entries(ROLES).map(([v, n]) => `<option value="${v}" ${v === "operaciones" ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      <label>Contraseña <input name="password" type="password" minlength="8" required autocomplete="new-password"></label>
      <button>Crear usuario</button></form><div id="res-usuario" aria-live="polite"></div></section>
    <section class="panel"><h2>Usuarios registrados</h2><div class="tabla"><table><thead><tr><th>Usuario</th><th>Nombre</th><th>Perfil</th><th>Estado</th><th>Acción</th></tr></thead><tbody>${usuarios.map(fila).join("") || '<tr><td colspan="5">No hay usuarios locales.</td></tr>'}</tbody></table></div></section></div>`;
  document.getElementById("f-usuario").addEventListener("submit", async e => {
    e.preventDefault(); const fd = new FormData(e.target), res = document.getElementById("res-usuario"), b = e.target.querySelector("button");
    b.disabled = true;
    try { await api("POST", "/api/usuarios", Object.fromEntries(fd)); res.innerHTML = '<div class="estado ok" role="status">Usuario creado correctamente.</div>'; e.target.reset(); setTimeout(vistaAdmin, 0); }
    catch (err) { res.innerHTML = errorHtml(err); }
    finally { b.disabled = false; }
  });
  $vista.querySelectorAll("[data-usuario]").forEach(b => b.addEventListener("click", async () => {
    b.disabled = true;
    try { await api("PATCH", `/api/usuarios/${encodeURIComponent(b.dataset.usuario)}`, { activo: b.dataset.activo === "true" }); vistaAdmin(); }
    catch (err) { b.insertAdjacentHTML("afterend", errorHtml(err)); b.disabled = false; }
  }));
}
