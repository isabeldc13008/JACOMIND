-- M4 · Venta cruzada (experimental, en sombra) ----------------------------------------------------------------------
-- Las publicaciones reutilizan sombra_publicaciones (modelo_id = venta_cruzada); sus filas van en tablas propias.
CREATE TABLE sombra_recomendaciones (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  cliente_id TEXT NOT NULL,
  producto_id TEXT NOT NULL,
  posicion INTEGER NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, cliente_id, producto_id)
);
CREATE TABLE sombra_cobertura_recomendaciones (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  cliente_id TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, cliente_id)
);
CREATE TABLE sombra_muestras_revision (
  sombra_id TEXT PRIMARY KEY REFERENCES sombra_publicaciones(id),
  datos_json TEXT NOT NULL
);

-- Episodio comercial: cliente + producto + ciclo persistido. Cambiar corte, puntaje, posición o versión no crea otro.
CREATE TABLE episodios_venta_cruzada (
  episodio_id TEXT PRIMARY KEY,                 -- venta_cruzada:<cliente>:<producto>:<ciclo>
  cliente_id TEXT NOT NULL,
  producto_id TEXT NOT NULL,
  ciclo INTEGER NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('en_revision', 'aceptada', 'aplazada', 'descartada', 'cerrada_compra')),
  motivo TEXT,
  actor TEXT,
  tarea_id INTEGER REFERENCES tareas(id),
  tarea_compartida INTEGER NOT NULL DEFAULT 0,
  abierto_en_corte TEXT NOT NULL,
  sombra_apertura TEXT NOT NULL,
  version_propuesta TEXT NOT NULL,
  ultima_evidencia_json TEXT NOT NULL,
  cerrado_en_corte TEXT,
  creado_en TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_episodio_vc_ciclo ON episodios_venta_cruzada(cliente_id, producto_id, ciclo);

-- Revisión comercial humana de pares cliente-producto (no se generan automáticamente).
CREATE TABLE revisiones_venta_cruzada (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sombra_id TEXT NOT NULL,
  cliente_id TEXT NOT NULL,
  producto_id TEXT NOT NULL,
  version_propuesta TEXT NOT NULL,
  estado_revision TEXT NOT NULL CHECK (estado_revision IN ('pertinente', 'ya_cubierto', 'incompatible', 'sin_necesidad', 'informacion_insuficiente')),
  revisor TEXT NOT NULL,
  fecha TEXT NOT NULL,
  motivo TEXT NOT NULL,
  evidencia TEXT
);

-- Las tareas de venta cruzada quedan DESACTIVADAS por defecto.
INSERT OR IGNORE INTO banderas (nombre, activo, actualizado_en) VALUES ('venta_cruzada_tareas', 0, '2026-11-23T00:00:00+00:00');
