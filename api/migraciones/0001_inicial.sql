-- JACOMIND · esquema inicial (SQLite; SQL portable a PostgreSQL salvo AUTOINCREMENT).
-- Separación: tablas an_* = cierres reproducibles (se reemplazan por cierre);
-- el resto = datos operativos modificables que sobreviven a una regeneración.

CREATE TABLE organizaciones (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  tipo TEXT NOT NULL CHECK (tipo IN ('interna', 'empresa')),
  cliente_id TEXT,                     -- vínculo con la cartera para empresas externas
  segmento TEXT
);

CREATE TABLE identidades (
  id TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  organizacion_id TEXT NOT NULL REFERENCES organizaciones(id),
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE pertenencias (
  identidad_id TEXT NOT NULL REFERENCES identidades(id),
  organizacion_id TEXT NOT NULL REFERENCES organizaciones(id),
  rol TEXT NOT NULL,
  PRIMARY KEY (identidad_id, organizacion_id, rol)
);

CREATE TABLE permisos (
  rol TEXT NOT NULL,
  accion TEXT NOT NULL,
  PRIMARY KEY (rol, accion)
);

CREATE TABLE sesiones (
  token TEXT PRIMARY KEY,
  identidad_id TEXT NOT NULL REFERENCES identidades(id),
  creada_en TEXT NOT NULL,
  expira_en TEXT NOT NULL
);

CREATE TABLE auditoria (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT,
  accion TEXT NOT NULL,
  recurso TEXT,
  revision TEXT,
  resultado TEXT NOT NULL,
  detalle TEXT
);

-- Lotes y cierres ---------------------------------------------------------
CREATE TABLE lotes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  huella TEXT NOT NULL UNIQUE,
  origen TEXT,
  tabla TEXT,
  periodo TEXT,
  cargado_por TEXT,
  cargado_en TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('previsualizado', 'confirmado', 'rechazado', 'fallido')),
  resumen_json TEXT
);

CREATE TABLE cierres (
  id TEXT PRIMARY KEY,
  corte TEXT NOT NULL,
  revision INTEGER NOT NULL,
  huella TEXT NOT NULL UNIQUE,         -- dos publicaciones idénticas => una sola revisión
  version_contrato INTEGER NOT NULL,
  origen TEXT,
  manifiesto_json TEXT NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('publicado', 'reemplazado')),
  publicado_por TEXT,
  publicado_en TEXT NOT NULL,
  UNIQUE (corte, revision)
);

CREATE TABLE cierre_activo (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  cierre_id TEXT NOT NULL REFERENCES cierres(id),
  activado_en TEXT NOT NULL
);

CREATE TABLE stg_filas (               -- área temporal de importación
  token TEXT NOT NULL,
  tabla TEXT NOT NULL,
  clave TEXT NOT NULL,
  cliente_id TEXT,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (token, tabla, clave)
);

CREATE TABLE an_agenda (
  cierre_id TEXT NOT NULL REFERENCES cierres(id),
  cliente_id TEXT NOT NULL,
  accion TEXT NOT NULL,
  orden_accion INTEGER NOT NULL,
  prob REAL,
  frio INTEGER NOT NULL,
  frecuente INTEGER NOT NULL,
  ingreso_cop REAL NOT NULL,
  segmento TEXT,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (cierre_id, cliente_id)
);

CREATE TABLE an_filas (
  cierre_id TEXT NOT NULL REFERENCES cierres(id),
  tabla TEXT NOT NULL,
  clave TEXT NOT NULL,
  cliente_id TEXT,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (cierre_id, tabla, clave)
);
CREATE INDEX an_filas_cliente ON an_filas (cierre_id, tabla, cliente_id);

-- PQRS --------------------------------------------------------------------
CREATE TABLE pqrs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  radicado TEXT NOT NULL UNIQUE,
  organizacion_id TEXT NOT NULL REFERENCES organizaciones(id),
  solicitante_id TEXT NOT NULL REFERENCES identidades(id),
  clave_idempotencia TEXT,
  creado_en TEXT NOT NULL,
  asunto TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  categoria_propuesta TEXT,
  categoria_revisada TEXT,
  fecha_revision TEXT,
  responsable_id TEXT REFERENCES identidades(id),
  estado TEXT NOT NULL CHECK (estado IN ('recibido', 'en_gestion', 'respondido', 'cerrado')),
  requiere_revision INTEGER NOT NULL DEFAULT 0,
  plazo_dias INTEGER,
  respuesta_publicada TEXT,
  respuesta_aprobada_por TEXT,
  primera_gestion_en TEXT,
  respondido_en TEXT,
  cerrado_en TEXT,
  uso_autorizado INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (organizacion_id, solicitante_id, clave_idempotencia)
);

CREATE TABLE pqrs_bitacora (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pqrs_id INTEGER NOT NULL REFERENCES pqrs(id),
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  accion TEXT NOT NULL,
  de_estado TEXT,
  a_estado TEXT,
  nota TEXT,
  interna INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE pqrs_sugerencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pqrs_id INTEGER NOT NULL REFERENCES pqrs(id),
  categoria TEXT,
  responsable TEXT,
  confianza REAL,
  version TEXT,
  revisar INTEGER NOT NULL,
  motivo TEXT,
  creado_en TEXT NOT NULL
);

CREATE TABLE pqrs_borradores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  pqrs_id INTEGER NOT NULL REFERENCES pqrs(id),
  texto TEXT NOT NULL,
  fuentes_json TEXT NOT NULL,
  version_generador TEXT NOT NULL,
  version_caso INTEGER NOT NULL,
  estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'requiere_revision', 'aprobado', 'descartado')),
  motivo_revision TEXT,
  creado_por TEXT NOT NULL,
  creado_en TEXT NOT NULL,
  aprobado_por TEXT,
  aprobado_en TEXT
);

-- Agenda operativa (B05) --------------------------------------------------
CREATE TABLE tareas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  episodio_id TEXT NOT NULL UNIQUE,    -- una tarea por episodio
  oportunidad_id TEXT NOT NULL,
  cliente_id TEXT NOT NULL,
  tipo TEXT NOT NULL,
  motivos_json TEXT NOT NULL,
  evidencia_json TEXT NOT NULL,
  prioridad INTEGER NOT NULL,
  probabilidad REAL,
  responsable_id TEXT REFERENCES identidades(id),
  fecha_revision TEXT,
  estado TEXT NOT NULL CHECK (estado IN ('abierta', 'asignada', 'pospuesta', 'descartada', 'atendida')),
  pospuesta_hasta TEXT,
  motivo_descarte TEXT,
  resultado TEXT,
  siguiente_paso TEXT,
  beneficio_id TEXT,
  cierre_origen TEXT NOT NULL,
  cierre_ultimo TEXT NOT NULL,
  creada_en TEXT NOT NULL,
  actualizada_en TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE tarea_evidencias (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tarea_id INTEGER NOT NULL REFERENCES tareas(id),
  cierre_id TEXT NOT NULL,
  motivos_json TEXT NOT NULL,
  evidencia_json TEXT NOT NULL,
  version_modelo TEXT,
  ts TEXT NOT NULL,
  UNIQUE (tarea_id, cierre_id)
);

CREATE TABLE avisos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clave_dedup TEXT NOT NULL UNIQUE,    -- episodio + tipo de aviso (+ valor)
  tarea_id INTEGER REFERENCES tareas(id),
  tipo TEXT NOT NULL,
  mensaje TEXT NOT NULL,
  destinatario TEXT,
  creado_en TEXT NOT NULL,
  leido INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE eventos (
  evento_id TEXT PRIMARY KEY,
  clave_idempotencia TEXT UNIQUE,
  tipo TEXT NOT NULL,
  oportunidad_id TEXT,
  episodio_id TEXT,
  cliente_id TEXT,
  cierre_id TEXT,
  fecha TEXT NOT NULL,
  actor TEXT NOT NULL,
  estado TEXT,
  resultado TEXT,
  datos_json TEXT
);

-- Beneficios (B06) --------------------------------------------------------
CREATE TABLE beneficios (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  empresa_emisora TEXT NOT NULL,
  titulo TEXT NOT NULL,
  descripcion TEXT NOT NULL,
  fuente TEXT NOT NULL,
  vigencia_desde TEXT NOT NULL,
  vigencia_hasta TEXT,
  criterio_json TEXT NOT NULL,
  politica TEXT,
  como_solicitar TEXT,
  estado TEXT NOT NULL CHECK (estado IN ('borrador', 'revision', 'publicado', 'retirado')),
  actualizado_por TEXT,
  actualizado_en TEXT NOT NULL,
  PRIMARY KEY (id, version)
);

-- Documentos y RAG (B08) --------------------------------------------------
CREATE TABLE documentos (
  id TEXT NOT NULL,
  version INTEGER NOT NULL,
  titulo TEXT NOT NULL,
  tema TEXT,
  propietario TEXT NOT NULL,
  organizacion_id TEXT,                -- NULL = aplica a todas las empresas
  roles_json TEXT NOT NULL,            -- roles que pueden recuperarlo
  vigencia_desde TEXT NOT NULL,
  vigencia_hasta TEXT,
  precedencia INTEGER NOT NULL DEFAULT 0,
  estado TEXT NOT NULL CHECK (estado IN ('vigente', 'reemplazado', 'retirado')),
  huella TEXT NOT NULL,
  importado_por TEXT,
  importado_en TEXT NOT NULL,
  PRIMARY KEY (id, version)
);

CREATE TABLE fragmentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  documento_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  localizador TEXT NOT NULL,
  texto TEXT NOT NULL,
  FOREIGN KEY (documento_id, version) REFERENCES documentos(id, version)
);

CREATE TABLE consultas_cache (
  clave TEXT PRIMARY KEY,
  respuesta_json TEXT NOT NULL,
  creado_en TEXT NOT NULL
);

CREATE TABLE asistente_registro (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  herramienta TEXT,
  intencion TEXT,
  parametros_json TEXT,
  estado TEXT NOT NULL,
  latencia_ms INTEGER NOT NULL,
  version_componente TEXT,
  correcta INTEGER
);

-- Informes, ejecuciones y operación (B09/B11) ----------------------------
CREATE TABLE informes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cierre_id TEXT NOT NULL REFERENCES cierres(id),
  revision INTEGER NOT NULL,
  huella_contenido TEXT NOT NULL,
  html TEXT NOT NULL,
  generado_por TEXT,
  generado_en TEXT NOT NULL,
  UNIQUE (cierre_id, revision),
  UNIQUE (cierre_id, huella_contenido)
);

CREATE TABLE ejecuciones (
  id TEXT PRIMARY KEY,
  tipo TEXT NOT NULL,
  corte TEXT,
  inicio TEXT NOT NULL,
  fin TEXT,
  estado TEXT NOT NULL,
  intentos INTEGER NOT NULL DEFAULT 0,
  etapas_json TEXT,
  detalle_json TEXT
);

CREATE TABLE banderas (
  nombre TEXT PRIMARY KEY,
  activo INTEGER NOT NULL,
  actualizado_en TEXT NOT NULL
);
