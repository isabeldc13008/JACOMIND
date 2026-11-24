-- M3 · Próxima compra (experimental, en sombra) ---------------------------------------------------------------
-- Las publicaciones de sombra reutilizan sombra_publicaciones / sombra_predicciones (modelo_id = proxima_compra).
-- Episodio de recordatorio: identidad estable = cliente + último día de compra (no la versión del modelo ni el corte).
CREATE TABLE episodios_proxima (
  episodio_id TEXT PRIMARY KEY,                 -- proxima:<cliente_id>:<ultima_compra_ancla>
  cliente_id TEXT NOT NULL,
  ultima_compra_ancla TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('abierto', 'cerrado_compra')),
  tarea_id INTEGER REFERENCES tareas(id),
  tarea_compartida INTEGER NOT NULL DEFAULT 0,
  abierto_en_corte TEXT NOT NULL,
  sombra_apertura TEXT NOT NULL,
  version_modelo_apertura TEXT NOT NULL,
  ultima_evidencia_json TEXT NOT NULL,
  cerrado_en_corte TEXT,
  fecha_compra_cierre TEXT,
  creado_en TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_episodio_proxima_abierto ON episodios_proxima(cliente_id) WHERE estado = 'abierto';

-- Los recordatorios por ventana estimada quedan DESACTIVADOS por defecto.
INSERT OR IGNORE INTO banderas (nombre, activo, actualizado_en) VALUES ('proxima_recordatorios', 0, '2026-11-23T00:00:00+00:00');
