# A01 Importación y validación Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implementar una ingesta local reproducible para CSV/XLSX que normalice tablas, valide calidad y publique lotes trazables para A02.

**Architecture:** Separar lectura de formatos, esquemas, validación y gestión de lotes. El CLI coordina esas capas y escribe tablas normalizadas, inventario, incidencias y manifiesto; no calcula métricas de negocio de A02.

**Tech Stack:** Python 3.10+, biblioteca estándar (`csv`, `json`, `zipfile`, `xml.etree.ElementTree`, `hashlib`, `datetime`, `decimal`), `unittest` para pruebas sin dependencias.

**Spec:** `docs/superpowers/specs/2026-11-21-a01-importacion-validacion-design.md`

## Global Constraints

- Mantener Python 3.10+ y biblioteca estándar únicamente.
- Preservar IDs como texto, incluidos ceros iniciales.
- Normalizar CSV UTF-8/UTF-8 BOM y XLSX con fechas nativas o ISO.
- No modificar ni copiar los recursos sintéticos al repositorio.
- No publicar lotes con tablas obligatorias ausentes o fallos de lectura.
- Contabilizar cada fila una vez en aceptadas, duplicadas idénticas o aisladas.

## Review Focus

- CSV con BOM, separador declarado y encabezados inesperados: debe producir registros deterministas o una incidencia de encabezado.
- XLSX con hoja inexistente y fechas seriales: debe diferenciar error de hoja de una fecha válida.
- IDs con ceros iniciales y decimales: no deben convertirse a número binario ni perder precisión.
- Referencias desconocidas y claves duplicadas: deben aislarse con fila/campo/motivo/acción.
- Reenvío idéntico y corrección con la misma clave de negocio: deben reutilizar o versionar, nunca sobrescribir silenciosamente.

### Task 1: Contratos y lectores de entrada

**Files:**
- Create: `pipeline/__init__.py`
- Create: `pipeline/formatos.py`
- Create: `pipeline/esquemas.py`
- Test: `tests/datos/test_formatos.py`
- Test: `tests/datos/test_esquemas.py`

**Interfaces:**
- `pipeline.formatos.leer_csv(ruta: Path, encoding: str = "utf-8-sig", delimiter: str = ",") -> list[dict[str, str]]`
- `pipeline.formatos.leer_xlsx(ruta: Path, hoja: str | None = None) -> list[dict[str, str]]`
- `pipeline.formatos.leer_tabla(ruta: Path, tipo: str, hoja: str | None = None, delimiter: str = ",") -> list[dict[str, str]]`
- `pipeline.esquemas.TableSpec` describe nombre, columnas, tipos, clave y referencias.

- [ ] Escribir pruebas para CSV con BOM, preservación de `CLI001`, XLSX equivalente y hoja inexistente.
- [ ] Ejecutar `python -m unittest tests.datos.test_formatos tests.datos.test_esquemas -v` y observar fallo por módulos ausentes.
- [ ] Implementar lectores con biblioteca estándar y errores tipados de formato/hoja.
- [ ] Definir las siete tablas principales y sus columnas obligatorias a partir del diccionario de datos.
- [ ] Ejecutar las pruebas y verificar que pasen.
- [ ] Commit: `feat: add csv and xlsx table readers`

### Task 2: Normalización de celdas y validación de filas

**Files:**
- Create: `pipeline/normalizacion.py`
- Create: `pipeline/validacion.py`
- Test: `tests/datos/test_normalizacion.py`
- Test: `tests/datos/test_validacion.py`

**Interfaces:**
- `pipeline.normalizacion.normalizar_fila(row: Mapping[str, str], spec: TableSpec) -> dict[str, object]`
- `pipeline.validacion.validar_fila(row: Mapping[str, object], spec: TableSpec, catalogos: Mapping[str, set[str]]) -> list[Issue]`
- `pipeline.validacion.validar_tabla(rows: Iterable[Mapping[str, object]], spec: TableSpec, catalogos: Mapping[str, set[str]]) -> TableValidation`

- [ ] Escribir pruebas para fechas ISO, fecha ambigua, decimal, cantidad, moneda/estado inválidos, referencia desconocida y clave duplicada.
- [ ] Ejecutar las pruebas y comprobar que fallan por implementación ausente.
- [ ] Implementar conversiones deterministas con `Decimal`, fechas ISO y seriales de Excel.
- [ ] Implementar incidencias con archivo, fila, campo, código, motivo y acción; separar aislables de bloqueantes.
- [ ] Ejecutar las pruebas y verificar que pasen.
- [ ] Commit: `feat: validate normalized data rows`

### Task 3: Lotes, huellas e idempotencia

**Files:**
- Create: `pipeline/lotes.py`
- Test: `tests/datos/test_lotes.py`

**Interfaces:**
- `pipeline.lotes.calcular_sha256(path: Path) -> str`
- `pipeline.lotes.clave_negocio(row: Mapping[str, object], spec: TableSpec) -> str`
- `pipeline.lotes.registrar_lote(...) -> BatchRecord`
- `pipeline.lotes.clasificar_reenvio(previous: BatchRecord | None, current_hash: str, business_rows: ...) -> BatchDecision`

- [ ] Escribir pruebas para reenvío idéntico, corrección con misma clave y archivo cambiado.
- [ ] Ejecutar las pruebas y observar fallo esperado.
- [ ] Implementar manifiesto de lote, huella de archivo y revisión por clave de negocio.
- [ ] Verificar que el lote idéntico sea reutilizable y que la corrección sea trazable.
- [ ] Commit: `feat: track batch fingerprints and revisions`

### Task 4: Coordinador de carga y salidas A01

**Files:**
- Create: `pipeline/carga.py`
- Create: `pipeline/cli.py`
- Create: `docs/ficha-modelo.md`
- Test: `tests/datos/test_carga.py`
- Test: `tests/datos/test_aceptacion_a01.py`

**Interfaces:**
- `pipeline.carga.cargar_lote(datos: Path, salida: Path, configuracion: Path | None = None) -> LoadResult`
- CLI: `python -m pipeline.cli --datos PATH --salida PATH [--config PATH]`

- [ ] Escribir prueba de integración con el paquete sintético: lee las siete tablas, registra inventario y no mezcla las salidas con el repositorio.
- [ ] Escribir prueba de lote parcial/fallo de lectura que conserve una publicación previa.
- [ ] Ejecutar las pruebas y verificar fallo por coordinador ausente.
- [ ] Implementar orden de carga de catálogos antes de hechos, salida de CSV normalizado, `inventario.json`, `incidencias.jsonl` y manifiesto.
- [ ] Implementar estado `publicable`, `pendiente_revision` o `fallido` y conservación de última publicación válida.
- [ ] Documentar contrato, comando, códigos de incidencia y límites conocidos.
- [ ] Ejecutar todas las pruebas: `python -m unittest discover -s tests -v`.
- [ ] Commit: `feat: add reproducible A01 batch loader`

### Task 5: Verificación final y revisión

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-11-21-a01-importacion-validacion.md`

- [ ] Ejecutar la carga contra `C:\Users\idelg\OneDrive\Documents\ChatGPT\Green_Services_Recursos_de_Prueba` en una carpeta de salida temporal fuera del repositorio.
- [ ] Comparar conteos de inventario con 120 clientes, 1.407 ventas, 240 compras, 243 instalaciones y 669 tasas.
- [ ] Ejecutar el CSV opcional de incidencias y comparar motivos con `05_Validacion/Incidencias_esperadas.md`.
- [ ] Ejecutar la suite completa y registrar cualquier limitación de entorno, incluida ausencia de Python si persiste.
- [ ] Actualizar README con el comando de A01 y el contrato para A02.
- [ ] Solicitar revisión del cambio y dejar resumen de archivos, pruebas y siguiente paso A02.
