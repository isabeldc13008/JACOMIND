CREATE TABLE usuarios_locales (
  identidad_id TEXT PRIMARY KEY REFERENCES identidades(id),
  usuario TEXT NOT NULL UNIQUE,
  password_salt TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  activo INTEGER NOT NULL DEFAULT 1,
  creado_en TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);

CREATE INDEX usuarios_locales_usuario_activo ON usuarios_locales(usuario, activo);
