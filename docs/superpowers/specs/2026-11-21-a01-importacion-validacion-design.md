# A01: Importación, validación y actualización mensual

## Intención

Construir la primera pieza reutilizable de datos y modelos: un cargador local que lea los siete CSV principales y archivos XLSX equivalentes, preserve los identificadores como texto, normalice fechas y decimales, valide el lote y produzca tablas normalizadas, inventario e incidencias trazables. El resultado alimentará A02 sin ocultar filas defectuosas ni publicar lotes parciales silenciosamente.

## Objetivos

- Leer CSV UTF-8/UTF-8 con BOM y XLSX sin dependencias externas.
- Recibir ruta, tipo de tabla, hoja opcional y mapeo explícito de columnas.
- Preservar IDs, ceros iniciales, fechas ISO/Excel y decimales según el contrato.
- Validar columnas, tipos, claves primarias, referencias, estados, descuentos, cantidades, monedas y tasas.
- Clasificar cada fila como aceptada, duplicada idéntica o aislada, registrando archivo, fila, campo, motivo y acción.
- Generar huella del archivo y clave de negocio para reutilizar reenvíos idénticos y versionar correcciones.
- Mantener la última publicación válida cuando falle la lectura o el lote no sea publicable.

## No objetivos de A01

- Calcular importes, agregados o anomalías de A02.
- Entrenar modelos o producir la agenda comercial.
- Persistir en una base de datos o enviar datos a internet.
- Resolver reglas comerciales que el plan deja para Operaciones, Ventas o Finanzas.

## Restricciones

- Python 3.10+ y biblioteca estándar únicamente.
- Los recursos sintéticos permanecen fuera del repositorio.
- La salida debe ser reproducible y conservar la procedencia del lote.
- El contrato debe poder ser consumido por B01 y A02 sin depender del formato físico de entrada.

## Enfoques considerados

1. **Biblioteca estándar, recomendado.** `csv` para CSV y `zipfile`/`xml.etree.ElementTree` para XLSX. Tiene más código de adaptación, pero mantiene la demo portable y coincide con el ejemplo entregado.
2. **pandas/openpyxl.** Reduce código de manipulación tabular, pero añade instalación, versiones y riesgo de divergencia entre entornos.
3. **Base de datos desde A01.** Facilita consultas futuras, pero mezcla ingestión con persistencia y hace más difícil verificar el contrato mínimo.

Se elige el primer enfoque porque el objetivo inmediato es un contrato determinista y ejecutable en el entorno de práctica.

## Diseño propuesto

- `pipeline/formatos.py`: lectura CSV/XLSX y normalización de encabezados/celdas.
- `pipeline/esquemas.py`: contratos de tablas, tipos, claves y referencias.
- `pipeline/validacion.py`: validación por fila/lote, clasificación de incidencias y resultado publicable.
- `pipeline/lotes.py`: huellas, claves de negocio, inventario y estado de publicación.
- `pipeline/cli.py`: comando reproducible para cargar una carpeta y emitir salida local.
- `tests/datos/`: pruebas unitarias y de aceptación sobre fixtures pequeños y el paquete sintético.
- `docs/ficha-modelo.md`: contrato de datos, política de errores y ejemplos de ejecución.

La salida de un lote incluirá tablas normalizadas en CSV, `inventario.json`, `incidencias.jsonl` y un manifiesto de publicación. Las filas aislables no entrarán en las tablas publicadas; una ausencia de tabla obligatoria o un fallo de lectura hará que el lote quede pendiente y conservará la última publicación.

## Criterio de aceptación

La misma venta importada desde CSV y XLSX produce el mismo registro normalizado; se conservan IDs con ceros iniciales; una hoja equivocada, fecha ambigua, referencia desconocida y duplicado producen incidencias con ubicación y acción; el reenvío idéntico reutiliza el lote; una corrección con la misma clave de negocio crea revisión trazable; y las pruebas reproducen los conteos de control del paquete sin modificarlo.
