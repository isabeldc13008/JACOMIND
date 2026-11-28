CREATE TABLE roles (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL UNIQUE,
  sistema INTEGER NOT NULL DEFAULT 0,
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE roles_permisos (
  rol_id TEXT NOT NULL REFERENCES roles(id),
  accion TEXT NOT NULL,
  PRIMARY KEY (rol_id, accion)
);

ALTER TABLE usuarios_locales ADD COLUMN requiere_cambio_clave INTEGER NOT NULL DEFAULT 0;

CREATE INDEX roles_permisos_accion ON roles_permisos(accion);
