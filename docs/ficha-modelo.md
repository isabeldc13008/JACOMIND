# Ficha de datos A01

## Propósito

La carga A01 recibe el paquete de datos de práctica o una carpeta equivalente y produce tablas normalizadas para A02. Los archivos empresariales deben permanecer fuera del repositorio.

## Ejecución

```powershell
uv run --python 3.12 python -m pipeline.cli `
  --datos C:\ruta\Green_Services_Recursos_de_Prueba `
  --salida C:\ruta\salida\a01
```

También acepta directamente la carpeta `01_Datos`.

## Tablas

Se cargan en este orden: `clientes`, `productos`, `proveedores`, `trm`, `instalaciones`, `ventas` y `compras`. Los identificadores son texto. Las fechas se convierten a ISO y los importes a `Decimal`; el CSV de incidencias opcional se procesa por separado y nunca se suma a `ventas.csv`.

## Salidas

- `lote_actual/` contiene las tablas aceptadas del intento.
- `publicado/` conserva la última publicación completamente válida.
- `inventario.json` contiene filas leídas, aceptadas, aisladas y duplicadas por tabla.
- `incidencias.jsonl` registra archivo, fila, campo, código, motivo y acción.
- `manifiesto.json` registra el estado del lote.

Estados: `publicable`, `pendiente_revision` cuando hay filas aisladas o duplicadas, y `fallido` cuando falta una tabla obligatoria o no puede leerse. Un lote pendiente o fallido no reemplaza `publicado/`.

## Códigos principales

`CAMPO_REQUERIDO`, `ERROR_NORMALIZACION`, `REFERENCIA_DESCONOCIDA`, `DUPLICADO_IDENTICO`, `DUPLICADO_CONFLICTIVO`, `MONEDA_NO_ADMITIDA`, `ESTADO_NO_ADMITIDO`, `ARCHIVO_FALTANTE` y `ERROR_LECTURA`.
