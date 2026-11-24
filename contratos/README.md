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
| `predicciones_clientes` | `cliente_id, modelo_id` | ficha, agenda y asistente (la misma fila persistida). Para `modelo_id = compra_30d`: `probabilidad` (0–1 o `null`), `estado` (`estimado`, `sin_historial`, `no_elegible`, `modelo_no_disponible`…), `horizonte_dias = 30`, `version_modelo`, `corte`, `datos_hasta` y `motivos` (señales observadas, no causas). Para `modelo_id = inactividad_60d` (M2), además: `horizonte_dias = 60`, `umbral_frio_dias = 90`, `recencia_dias`, `poblacion` y `posicion`; estado `estructural` con probabilidad 0 exacta para recencia 0–29 |

Los tipos exactos están en `tablas_conocidas` del esquema. Para `predicciones_clientes`, `contratos/validar.py` añade reglas semánticas y rechaza el lote si no se cumplen: probabilidad finita en [0, 1]; solo `estimado` lleva probabilidad; horizonte 30 para `compra_30d`; `corte` igual al del manifiesto y `datos_hasta` no posterior; al menos un motivo; cliente presente en la agenda; `probabilidad` igual a `agenda.prob_compra_30d`; y `version_modelo` igual a `agenda.modelo.version`. Así agenda, ficha y asistente no pueden divergir. Para `inactividad_60d` se rechaza:

- `estructural` fuera de la recencia 0–29 o con probabilidad distinta de 0;
- `estimado` o `modelo_no_disponible` fuera de la recencia 30–89;
- un cliente ya frío (recencia ≥ 90) que no sea `no_elegible`;
- `sin_historial` con recencia;
- `umbral_frio_dias` distinto de 90.

Las filas de los dos modelos coexisten por la clave `cliente_id, modelo_id`. El cierre solo publica `inactividad_60d` con una versión operativa registrada. Las variantes experimentales van en un directorio aparte `publicacion_sombra` (`operativa: false`, sin agenda), que se valida con `validar_publicacion_sombra` y `leer_publicacion_sombra`. El portal de clientes no recibe esta tabla ni la sombra.

Integridad de la publicación: el manifiesto declara `tablas[*].sha256`, una propiedad aditiva que el generador incluye desde el 23-11-2026. El validador rechaza una tabla cuyo contenido no coincide con su huella. También rechaza un directorio con `.publicacion_en_curso.json`, es decir, una publicación interrumpida: se restituye con `python -m pipeline.generar --recuperar --salida <dir>` o en la siguiente ejecución. Los manifiestos sin `sha256` siguen siendo válidos.

`manifiesto.cobertura` (aditivo) declara `corte`, `datos_observados_hasta`, `fuente` y `estado` (`verificada` o `no_verificada`). Es obligatorio si hay predicciones `estimado`. El validador rechaza estas contradicciones: estimaciones sin cobertura declarada; cobertura `verificada` con `datos_observados_hasta` anterior al corte; estimaciones con cobertura `no_verificada`; `cobertura.corte` distinto del corte del manifiesto; falta de `fuente`; y `datos_hasta` posterior a la cobertura. Las publicaciones anteriores sin predicciones siguen siendo válidas. Muestra completa: [`ejemplos/publicacion/demo-2026-10/`](ejemplos/publicacion/demo-2026-10/). Si A solo entrega `agenda.json`, B lo envuelve en un manifiesto mínimo y lo publica igual.

## Puntos de enganche en código (opcionales)

B los busca por nombre y, si no existen o no cumplen el contrato, sigue funcionando con su sustituto. Las rutas se pueden cambiar por variable de entorno.

| Pieza de A | Ruta por defecto | Firma esperada |
|---|---|---|
| Generador del cierre | `python -m pipeline.generar --datos D --corte AAAA-MM-DD --salida salida/.../agenda.json` | escribe C1, `manifiesto.json` y tablas C2 en el mismo directorio; código ≠ 0 si falla (se conserva el cierre anterior). Lee solo la revisión aceptada por A01 (un lote pendiente exige `--aceptar-parcial`) y **no entrena**: carga la versión operativa de `compra_30d` desde `--registro`, `JACOMIND_MODELOS` o `var/modelos` (ver la [ficha del modelo de compra](../docs/modelo-compra.md)). Sin versión válida publica `prob_compra_30d: null` y `predicciones_clientes.estado = modelo_no_disponible`. `api/integracion_a.py` (`python -m api generar-desde-a`) delega en este generador |
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

Fusionada en `integracion/a-b`. Solo hubo conflictos en `README.md` y `.gitignore`, resueltos uniendo ambos lados. Con el paquete de datos, `python -m pipeline.generar` concilia exactamente con la referencia: 120 clientes, 1.371 ventas confirmadas, 5.647.449.456,36 COP, 41 fríos y umbral del modelo 0,4.

Resuelto tras la fusión:

- `pipeline/generar.py` produce C2 con la agenda C1 encadenando A01–A09; el cierre programado de B lo invoca como subproceso.
- Las pruebas de A localizan el paquete con `pipeline/rutas.py` (`JACOMIND_DATOS` o carpeta hermana) en vez de una ruta fija.
- `pipeline.pqrs.clasificar` cumple C4: `categoria: null` y `revisar: true` cuando el caso va a revisión humana.
- Venta cruzada (A07) por co-ocurrencia con soporte mínimo 3 y solo transacciones hasta el corte. En la evaluación temporal (corte 2026-09-01, compras hasta 2026-10-31) **no supera** a la popularidad: 11 aciertos de 69 en ambos métodos. Se publica con prioridad baja y el resultado queda en `calidad.venta_cruzada`.
- Pronóstico (A08) con error por horizonte, evaluado con origen creciente, frente al último valor observado (`mae`, `mae_ingenuo`, `sesgo`, `n_evaluaciones` y bandas ±MAE).
