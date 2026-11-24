-- M5 · Pronóstico de demanda (experimental, en sombra) --------------------------------------------------------------
-- Las publicaciones reutilizan sombra_publicaciones (modelo_id = demanda). Un pronóstico emitido es inmutable.
CREATE TABLE sombra_pronosticos (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  serie_id TEXT NOT NULL,
  horizonte_meses INTEGER NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, serie_id, horizonte_meses)
);
CREATE TABLE sombra_calendario_demanda (
  sombra_id TEXT NOT NULL REFERENCES sombra_publicaciones(id),
  serie_id TEXT NOT NULL,
  periodo TEXT NOT NULL,
  datos_json TEXT NOT NULL,
  PRIMARY KEY (sombra_id, serie_id, periodo)
);
