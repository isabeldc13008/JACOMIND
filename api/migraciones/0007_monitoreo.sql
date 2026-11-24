-- Monitoreo común de modelos (M1–M6), contrato jacomind.monitoreo.v1 ----------------------------------------------------
-- Observaciones inmutables vinculadas a su origen (cierre, publicación en sombra, evaluación de resultados o revisión).
-- Una corrección (mismo origen, grupo, universo y periodo con contenido distinto) crea otra observación enlazada.
CREATE TABLE monitoreo_observaciones (
  id TEXT PRIMARY KEY,                          -- SHA-256 del contenido canónico
  clave_logica TEXT NOT NULL,                   -- modelo|variante|origen|grupo|universo|periodo
  modelo_id TEXT NOT NULL,
  variante TEXT,
  version_artefacto TEXT,
  origen_tipo TEXT NOT NULL CHECK (origen_tipo IN ('cierre', 'sombra', 'resultados', 'revision')),
  origen_id TEXT NOT NULL,
  corte TEXT NOT NULL,
  periodo TEXT,
  universo TEXT NOT NULL,
  grupo TEXT NOT NULL CHECK (grupo IN ('salud', 'distribucion', 'desempeno', 'revision')),
  madurez TEXT NOT NULL CHECK (madurez IN ('no_aplica', 'pendiente', 'parcial', 'madura')),
  clave_comparacion TEXT NOT NULL,
  restriccion TEXT,                             -- 'cop' (Finanzas y Gerencia) | 'unidades' | NULL
  vigente INTEGER NOT NULL DEFAULT 1,           -- 0 = publicación histórica importada sin activar: no es referencia de comparación
  anterior_id TEXT REFERENCES monitoreo_observaciones(id),
  reemplazada_por TEXT REFERENCES monitoreo_observaciones(id),
  datos_json TEXT NOT NULL,
  creada_en TEXT NOT NULL
);
CREATE INDEX ix_mon_obs_modelo ON monitoreo_observaciones(modelo_id, grupo, universo, corte);
CREATE INDEX ix_mon_obs_logica ON monitoreo_observaciones(clave_logica);

-- Los avisos de 0006 ganan regla, evidencia y estado; se conservan los existentes.
ALTER TABLE avisos_modelos ADD COLUMN regla_id TEXT;
ALTER TABLE avisos_modelos ADD COLUMN regla_version TEXT;
ALTER TABLE avisos_modelos ADD COLUMN observacion_id TEXT;
ALTER TABLE avisos_modelos ADD COLUMN universo TEXT;
ALTER TABLE avisos_modelos ADD COLUMN periodo TEXT;
ALTER TABLE avisos_modelos ADD COLUMN restriccion TEXT;
ALTER TABLE avisos_modelos ADD COLUMN estado TEXT NOT NULL DEFAULT 'activo';

-- Historial de estado: reconocer no es resolver; el aviso original no se modifica en su contenido.
CREATE TABLE avisos_eventos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clave_aviso TEXT NOT NULL REFERENCES avisos_modelos(clave),
  accion TEXT NOT NULL CHECK (accion IN ('creado', 'reconocido', 'resuelto')),
  actor TEXT NOT NULL,
  fecha TEXT NOT NULL,
  motivo TEXT
);
CREATE INDEX ix_avisos_eventos ON avisos_eventos(clave_aviso);
