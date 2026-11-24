-- M6 · Operaciones atípicas (experimental, en sombra) ------------------------------------------------------------------
-- Las publicaciones reutilizan sombra_publicaciones (modelo_id = anomalias). Tres capas separadas:
--   1. resultado inmutable de puntuación (sombra_anomalias, sombra_cobertura_anomalias, sombra_muestras_revision);
--   2. caso operativo de revisión (casos_anomalia): identidad = tipo + ID + huella de los valores observados;
--   3. historial de eventos humanos y de sistema (eventos_anomalia), con clave de idempotencia.
CREATE TABLE sombra_anomalias (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('venta', 'compra')),
  operacion_id TEXT NOT NULL,
  periodo TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, tipo_operacion, operacion_id)
);
CREATE TABLE sombra_cobertura_anomalias (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  tipo_operacion TEXT NOT NULL,
  periodo TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, tipo_operacion, periodo)
);

-- Caso de revisión. Cambiar corte, puntaje o versión no crea otro ni reabre una decisión cerrada; una corrección de los
-- valores observados (otra huella) crea un caso nuevo enlazado al anterior, que conserva su decisión y su historial.
CREATE TABLE casos_anomalia (
  caso_id TEXT PRIMARY KEY,                     -- anomalias:<tipo>:<operacion_id>:<huella[:12]>
  tipo_operacion TEXT NOT NULL CHECK (tipo_operacion IN ('venta', 'compra')),
  operacion_id TEXT NOT NULL,
  huella_valores TEXT NOT NULL,
  revision_datos INTEGER,
  caso_anterior TEXT REFERENCES casos_anomalia(caso_id),
  reemplazado_por TEXT REFERENCES casos_anomalia(caso_id),
  cliente_id TEXT,                              -- nulo en compras
  proveedor_id TEXT,                            -- nulo en ventas
  estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'error_confirmado', 'cambio_legitimo', 'informacion_insuficiente')),
  origen TEXT NOT NULL,                         -- alerta | muestra_revision | alerta+muestra
  abierto_sombra TEXT NOT NULL,
  version_abierta TEXT NOT NULL,
  ultima_sombra TEXT NOT NULL,
  ultima_evidencia_json TEXT NOT NULL,
  creado_en TEXT NOT NULL,
  actualizado_en TEXT NOT NULL
);
CREATE UNIQUE INDEX ux_caso_anomalia ON casos_anomalia(tipo_operacion, operacion_id, huella_valores);
CREATE INDEX ix_caso_anomalia_op ON casos_anomalia(tipo_operacion, operacion_id);

CREATE TABLE eventos_anomalia (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  caso_id TEXT NOT NULL REFERENCES casos_anomalia(caso_id),
  tipo TEXT NOT NULL CHECK (tipo IN ('apertura', 'correccion_datos', 'revision', 'evidencia_actualizada')),
  estado_anterior TEXT,
  estado_nuevo TEXT,
  actor TEXT NOT NULL,
  fecha TEXT NOT NULL,
  motivo TEXT,
  evidencia TEXT,
  version_examinada TEXT,
  sombra_id TEXT,
  clave_idempotencia TEXT UNIQUE
);
CREATE INDEX ix_eventos_anomalia_caso ON eventos_anomalia(caso_id);

-- Avisos de monitoreo reutilizables por modelo (persistentes e idempotentes por clave).
CREATE TABLE avisos_modelos (
  clave TEXT PRIMARY KEY,
  modelo_id TEXT NOT NULL,
  sombra_id TEXT,
  tipo TEXT NOT NULL,
  severidad TEXT NOT NULL CHECK (severidad IN ('integridad', 'estadistico', 'informativo')),
  mensaje TEXT NOT NULL,
  datos_json TEXT,
  creado_en TEXT NOT NULL
);
