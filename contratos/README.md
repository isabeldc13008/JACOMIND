# Contratos entre A (datos y modelos) y B (aplicación y operación)

B mantiene estos esquemas y muestras; ambos pueden leerlos. A valida su productor contra ellos y B valida su consumidor con las mismas muestras. Un cambio incompatible se prueba en una versión nueva (`version: 2`) antes de migrar el lector.

| Contrato | Archivo | Productor → consumidor | Comprobación |
|---|---|---|---|
| C1 · Agenda v1 | [`agenda.v1.schema.json`](agenda.v1.schema.json) | A → B | `python -m contratos.validar salida/agenda.json` |
| C2 · Publicación analítica v1 | [`publicacion.v1.schema.json`](publicacion.v1.schema.json) | A → B | `python -m contratos.validar --publicacion salida/cierres/<id>` |
| C3 · Trabajo operativo v1 | [`trabajo.v1.schema.json`](trabajo.v1.schema.json) | B → A | `GET /api/exportes/eventos`, `GET /api/exportes/pqrs` o `python -m api exportar-eventos` |
| C4 · Asistencia v1 | [`asistencia.v1.schema.json`](asistencia.v1.schema.json) | B ↔ A | clasificador de PQRS (abajo) y respuesta de herramientas |

El validador no tiene dependencias y no necesita la web. Códigos de salida: `0` válido, `1` inválido, `2` versión incompatible o archivo ausente. Con `--json` imprime el detalle.

## Acuerdos de C1 (agenda)

- Una fila por cliente dado de alta al corte; `cliente_id` único (texto, conserva ceros iniciales).
- Fechas ISO `AAAA-MM-DD`; conteos enteros (un booleano no cuenta como entero); COP numérico.
- **Nulos.** Cliente sin compras: `ultima_compra` y `dias_sin_compra` en `null`, `productos: []`, `frio: false`, `prob_compra_30d: null`. Sin modelo disponible: `prob_compra_30d: null`. `0.0` es una estimación real y se muestra como «0 %», distinta de «Sin historial».
- `accion` toma uno de cinco textos, en orden de precedencia: «Revisar reactivación», «Revisar cobertura», «Revisar oportunidad de recompra», «Revisar primera compra», «Seguimiento habitual».
- **Orden** (lo aplica B): acción → probabilidad descendente (nulos al final) → `cliente_id` ascendente. Las constantes están en [`agenda.py`](agenda.py).
- El `resumen` debe conciliar con las filas: clientes, fríos, ventas confirmadas y la suma de ingreso (tolerancia de 0,01 COP por fila).
- Campos opcionales nuevos (`modelo: {version, umbral}`, `segmento`, `motivos`, `generado_en`…) preservan la v1. Con `modelo.umbral`, B muestra el motivo de recompra para cualquier fila que lo alcance.

## Acuerdos de C2 (publicación)

A produce un directorio por ejecución con `manifiesto.json`, `agenda.json` (C1) y las tablas que tenga listas. Solo `agenda` es obligatoria. El manifiesto declara versión, identificador, corte, origen, huellas de entrada, versiones de reglas/modelos y, por tabla, `archivo`, `filas` y `sumas` opcionales. B rechaza el lote si un conteo, una suma o una clave no cuadra, y conserva el cierre anterior.

| Tabla | Clave | Uso en B |
|---|---|---|
| `historial_ventas` | `venta_id` | ficha, agente (productos, reducciones entre periodos) |
| `coberturas` | `instalacion_id` | ficha, tablero de Operaciones |
| `compras_proveedor` | `compra_id` | agente (proveedores), simulador de TRM |
| `series_mensuales` | `periodo, familia, serie, tipo` | panel financiero e informe (`valor_cop: null` = mes incompleto, distinto de 0) |
| `escenarios_trm` | `escenario_id, familia, proveedor_id` | simulador cuando no hay compras detalladas |
| `oportunidades` | `oportunidad_id` (+ `episodio_id` estable entre cierres) | agenda operativa de Ventas (una tarea por episodio) |
| `segmentos` | `cliente_id` | filtros y tableros |

Los tipos exactos están en `tablas_conocidas` del esquema. Muestra completa: [`ejemplos/publicacion/demo-2026-10/`](ejemplos/publicacion/demo-2026-10/). Si A solo entrega `agenda.json`, B lo envuelve en un manifiesto mínimo y lo publica igual.

## Puntos de enganche en código (opcionales)

B los busca por nombre y, si no existen o no cumplen el contrato, sigue funcionando con su sustituto. Las rutas se pueden cambiar por variable de entorno.

| Pieza de A | Ruta por defecto | Firma esperada |
|---|---|---|
| Generador del cierre | `python -m pipeline.generar --datos D --corte AAAA-MM-DD --salida salida/.../agenda.json` | escribe C1 (y opcionalmente `manifiesto.json` y tablas C2 en el mismo directorio); código ≠ 0 si falla. **Mientras A no lo publique**, B usa `api/integracion_a.py` (`python -m api generar-desde-a`), que construye C1/C2 con las funciones reales de `pipeline/`: `cargar_lote` (A01), `calcular_cierre` (A02), `construir_ficha` (A03), `entrenar_y_evaluar_desde_paquete` y `construir_fotografias` (A04), `segmentar_clientes` (A05), `pronosticar_media_movil` (A08) y `simular_exposicion` (A09) |
| Importador A01 | `JACOMIND_IMPORTADOR=pipeline.importar:importar_archivo` | `importar_archivo(ruta, tabla, hoja=None, mapeo=None) -> {"leidas", "aceptadas", "duplicadas", "aisladas", "bloqueante", "incidencias": [{"fila", "campo", "motivo", "accion"}]}` |
| Clasificador A10 | `JACOMIND_CLASIFICADOR=modelos.clasificador_pqrs:clasificar,pipeline.pqrs:clasificar_pqrs` (se usa el primero que exista) | `clasificar(texto) -> {"categoria": peticion\|queja\|reclamo\|sugerencia, "confianza": 0–1, "version", "revisar": bool, "motivo"?, "responsable"?}` |

## Muestras

`ejemplos/` es distinto de `salida/` (las salidas de ejecución no se versionan). Regenerar: `python -m contratos.ejemplos.generar_ejemplos`.

| Muestra | Resultado esperado |
|---|---|
| `agenda/valido.json` | válida: frecuente y frío, cobertura próxima y vencida, sin compras (`null`), probabilidad 0 y nula |
| `agenda/vacio.json` | válida, lista vacía |
| `agenda/incompleto.json` | inválida: falta `accion` |
| `agenda/incompatible.json` | incompatible: `version: 2` |
| `agenda/id_repetido.json` | inválida: ID repetido |
| `agenda/tipo_invalido.json` | inválida: probabilidad como texto |
| `trabajo/eventos.json`, `asistencia/clasificacion.json` | ejemplos mínimos de C3 y C4 |

## Estado de la integración con la rama de A (`codex/datos-modelos-completos`)

Fusionada en `integracion/a-b`. Solo hubo conflictos en `README.md` y `.gitignore`, que se resolvieron uniendo ambos lados. Con el paquete de datos, el cierre de octubre generado con las funciones de A concilia exactamente: 120 clientes, 1.371 ventas confirmadas, 5.647.449.456,36 COP, 41 fríos y umbral del modelo 0,4.

Pendiente para A:

- Sus pruebas `tests/datos/test_ficha.py`, `test_operaciones.py`, `test_aceptacion_a01.py` y `tests/modelos/test_modelo_compra.py` usan una ruta fija a su equipo (`C:\Users\idelg\...`). En otro equipo fallan aunque el código sea correcto; con la ruta local pasan las 36. Se sugiere leer la ruta de `JACOMIND_DATOS` o buscar la carpeta hermana `../Green_Services_Recursos_de_Prueba`.
- `pipeline.pqrs.clasificar_pqrs` devuelve `categoria: "revision_manual"` sin el campo `revisar`. B lo normaliza a C4 (`categoria: null`, `revisar: true`).
- Venta cruzada (A07) todavía no se publica: genera una sugerencia por cada familia no comprada, sin soporte mínimo evaluado.
- El pronóstico (A08) se publica sin error histórico (`mae: null`) y la vista lo indica.
