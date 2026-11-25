-- Textos redactados por IA (api/narrativas.py). Guardados por huella de los datos de entrada: si los datos no
-- cambian, no se vuelve a llamar al modelo. Son texto de apoyo: no cambian ningún dato ni crean tareas.
CREATE TABLE narrativas (
  huella TEXT PRIMARY KEY,            -- SHA-256 de versión + tipo + datos de entrada
  tipo TEXT NOT NULL,                 -- venta_cruzada | ficha
  sujeto TEXT NOT NULL,               -- cliente_id
  texto_json TEXT NOT NULL,
  modelo TEXT NOT NULL,
  version TEXT NOT NULL,
  creada_en TEXT NOT NULL
);
CREATE INDEX narrativas_tipo_sujeto ON narrativas (tipo, sujeto);
