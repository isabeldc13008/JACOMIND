-- M2 · Prevención de inactividad (experimental, en sombra) -----------------------------------------
-- Publicaciones de sombra: separadas de los cierres operativos (no alteran agenda C1 ni predicciones del cierre).
CREATE TABLE sombra_publicaciones (
  id TEXT PRIMARY KEY,                          -- <modelo_id>:<corte>:<sello[:12]>
  modelo_id TEXT NOT NULL,
  corte TEXT NOT NULL,
  version_modelo TEXT NOT NULL,
  artefacto_huella TEXT NOT NULL,
  sello TEXT NOT NULL UNIQUE,                   -- una publicación idéntica se importa una sola vez
  estado_experimento TEXT NOT NULL,
  manifiesto_json TEXT NOT NULL,
  importada_en TEXT NOT NULL,
  importada_por TEXT,
  activa INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX ux_sombra_activa ON sombra_publicaciones(modelo_id) WHERE activa = 1;

CREATE TABLE sombra_predicciones (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  cliente_id TEXT NOT NULL,
  modelo_id TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, cliente_id, modelo_id)
);

-- Episodio de prevención: identidad estable = cliente + último día de compra que lo originó (no la versión del modelo).
CREATE TABLE episodios_prevencion (
  episodio_id TEXT PRIMARY KEY,                 -- prevencion:<cliente_id>:<ultima_compra_ancla>
  cliente_id TEXT NOT NULL,
  ultima_compra_ancla TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('abierto', 'cerrado_compra', 'cerrado_frio')),
  tarea_id INTEGER REFERENCES tareas(id),
  tarea_compartida INTEGER NOT NULL DEFAULT 0,  -- 1 = se añadió el motivo a un seguimiento existente
  abierto_en_corte TEXT NOT NULL,
  sombra_apertura TEXT NOT NULL,
  version_modelo_apertura TEXT NOT NULL,
  ultima_evidencia_json TEXT NOT NULL,
  cerrado_en_corte TEXT,
  fecha_compra_cierre TEXT,
  creado_en TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_episodio_prevencion_abierto ON episodios_prevencion(cliente_id) WHERE estado = 'abierto';

-- La creación automática de tareas de prevención queda DESACTIVADA por defecto.
INSERT OR IGNORE INTO banderas (nombre, activo, actualizado_en) VALUES ('prevencion_tareas', 0, '2026-11-23T00:00:00+00:00');
