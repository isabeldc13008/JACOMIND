# M6 · Operaciones atípicas (`anomalias`)

[Plan](plan/modelos/06-operaciones-atipicas.md) · [Base común](plan/modelos/00-base-comun.md) · Protocolo [`modelos/config/anomalias.json`](../modelos/config/anomalias.json) (`m6-protocolo-v1`, fijado el 23-11-2026 antes de ajustar)

**Estado: experimental, en sombra. La publicación vigente es M6.1 ([sección 13](#13-m61-catálogo-dirección-y-cupo-con-evidencia)): reglas de catálogo y contexto con cupo máximo con evidencia, en ventas y en compras.** M6 se conserva como versión anterior. La cola de revisión funciona en la aplicación. Hay **0 revisiones humanas reales**, así que la precisión comercial no es estimable. Todos los resultados vienen de datos sintéticos ya inspeccionados, y la comprobación histórica es exploratoria.

Una puntuación de rareza **no es una probabilidad de fraude ni demuestra un error**. La cola no modifica importes, no anula operaciones y no afecta al cliente (segmentación, beneficios ni crédito). Una corrección contable sigue el flujo de datos: una nueva carga A01 crea una revisión enlazada del caso.

## 1. Datos y exclusiones

Fuente: la revisión aceptada por A01 (`salida/a01`, revisión 1, huella de datos registrada en `datos.json`). Las compras se leen de la **misma** revisión (`publicado/compras.csv`); nunca del CSV original.

| Concepto | Ventas | Compras |
|---|---|---|
| Filas aceptadas por A01 | 1.407 | 240 |
| Excluidas del universo | 36 `venta_anulada` | 0 (el esquema no tiene estado) |
| Operaciones válidas | **1.371** | **240** |
| Rango | 2025-01-06 a 2026-10-30 | 2025-01-02 a 2026-10-31 |
| Cobertura temporal | declarada hasta 2026-10-31 | **no declarada** |

Separación de responsabilidades (verificada en código y pruebas):

- Errores de esquema, referencias inválidas y duplicados: **A01**. El CSV opcional con incidencias (6 aisladas y 1 duplicada) no llega al modelo y **no** se usa como etiqueta de anomalía.
- Ventas anuladas: excluidas con motivo `venta_anulada`.
- Valores no finitos, cantidad o valor ≤ 0, o moneda no admitida: excluidos con motivo (`fuera_de_dominio`, `moneda_no_admitida`); nunca se convierten en anomalías. En el paquete no hay ninguno.
- Operaciones válidas pero inusuales: M6.
- Falta de historia: abstención explícita `historia_insuficiente`, **sin puntaje** (nunca un cero).

Identidad: `(tipo_operacion, operacion_id)`. Una venta y una compra con el mismo ID no colisionan (prueba `test_anuladas_dominio_y_colision_de_ids`).

**Compras sin cobertura declarada.** La cobertura de ventas no certifica compras. Se puntúan las compras observadas. Las tasas de compras son «por operaciones observadas» y no se presentan como tasas de periodos completos (`cobertura_temporal = no_declarada` en cada fila de cobertura y en la vista).

**Unidades.** El paquete no documenta la unidad de medida. La convención es que cada producto es su propia unidad (`unidad de catálogo de PROxx`) y nunca se comparan cantidades de productos distintos.

**Descuentos.** Todos valen 0 (sin variación útil). No se afirma que el modelo detecte descuentos anómalos.

## 2. Variables y temporalidad

Grupo comparable: (tipo de operación, producto, moneda de origen, unidad). Cada producto tiene una sola moneda en el paquete.

- **Historia estrictamente anterior.** No hay hora fiable, así que las operaciones del mismo día forman un bloque: ninguna usa a otra del mismo día como antecedente (`fecha < fecha de la operación`). El bloque se incorpora al historial después de puntuarlo. Se usan como máximo los 60 antecedentes más recientes.
- **Soporte mínimo:** 5 antecedentes. No hay respaldos documentados (`respaldos = {}`), así que con menos antecedentes la operación queda en `historia_insuficiente`. El mecanismo de respaldo existe, y solo se activa si la compatibilidad de producto, moneda y unidad está documentada (prueba `test_respaldo_solo_si_esta_documentado`).
- **Variables, en moneda de origen:**
  - `z_log_valor_unitario`, `z_log_cantidad` y `z_log_importe`, con z = (log x − mediana(log antecedentes)) / max(1,4826·MAD, 0,02), recortada a ±50;
  - como información: referencia = exp(mediana del log), razón = exp(log x − mediana), número de antecedentes y MAD.
- **Tratamiento numérico (probado):**
  - la mediana de logaritmos siempre es finita, porque los valores son > 0;
  - MAD = 0 (grupo constante) usa el piso de escala 0,02;
  - z nunca es infinito;
  - la razón nunca divide por cero.
- **TRM separada.** Se conservan la moneda y los valores de origen, y se publica el importe COP con la TRM de la fecha. El importe COP y la TRM **no** entran al detector. Un cambio exclusivo de TRM deja iguales las variables y el puntaje: 14 de 14 controles en ventas y 7 de 7 en compras tienen puntaje idéntico. Una TRM ausente queda como `estado_trm = ausente` con importe COP nulo, sin sustituirse por cero, y la operación se sigue puntuando.
- Excluidos del detector: identificadores de cliente, proveedor y producto, precios absolutos y descuento.

## 3. Referencias y candidato

| Método | Qué hace | Papel |
|---|---|---|
| **A02** (`pipeline/operaciones.detectar_anomalias`) | Mediana/MAD del **importe COP** por **familia y moneda**. Usa como historia las ventas anteriores en orden (periodo mensual, id), incluidas las del mismo mes y día. Sin compras. | Control de compatibilidad, reproducido exactamente: **122 alertas, idénticas** a `calcular_cierre`. Su comportamiento operativo no cambia. **No equivale** a una comparación por producto con historia estrictamente anterior. |
| **Referencia contextual `mediana_mad`** | Puntaje = max(\|z valor\|, \|z cantidad\|) sobre los mismos grupos e información temporal que el candidato. Reglas: \|z\| ≥ 3,5, razón de valor fuera de [0,67; 1,5] y razón de cantidad fuera de [0,2; 3]. | **Comparación principal a igual cupo.** Es el método publicado. |
| **Isolation Forest** (candidato) | Un bosque por universo: 200 árboles, semilla 20261123, sin bootstrap y `max_features = 1`. Cuatro configuraciones registradas: variables VC o VCI × submuestra 64 o 128, limitada al tamaño disponible. | Puntaje = rareza = −`score_samples` (mayor = más raro). `contamination` y `predict()` **no** deciden nada. |

Soporte de entrenamiento: 565 ventas y 89 compras utilizables, ambos ≥ 50. En compras, la submuestra de 128 queda limitada a 89.

## 4. Protocolo congelado

- Partición: entrenamiento enero–diciembre de 2025, validación enero–junio de 2026 y comprobación histórica julio–octubre de 2026.
- El bosque se ajusta solo con originales puntuables de 2025. No hay transformaciones aprendidas: las z dependen solo de antecedentes anteriores, con política fija.
- **Política de alertas: ranking con cupo** (no umbral; `umbral = null`). El cupo es el 5 % de las operaciones puntuadas del universo y mes (mínimo 1). Es una **convención de demostración, no una capacidad empresarial acordada**. Desempate estable: puntaje descendente, fecha y `operacion_id`. Con ~10 compras al mes, el mínimo de 1 eleva las alertas de compras a 10 por 100.
- **Selección (validación):** mayor detección a igual cupo. Desempates: combinación moderada, controles negativos y orden declarado. Se eligió `if_vc_128` en ambos universos:

| Validación (detección sembrada a igual cupo) | Referencia | if_vc_64 | **if_vc_128** | if_vci_64 | if_vci_128 |
|---|---|---|---|---|---|
| Ventas (de 200) | 62,5 % | 54,5 % | **77,0 %** | 45,5 % | 72,5 % |
| Compras (de 100) | 81,0 % | 87,0 % | **89,0 %** | 74,0 % | 88,0 % |

- La selección se congeló en `congelacion.json` (sello `d5d7899729f5…`, 24-11-2026 03:22 UTC) **antes** de construir la comprobación. No se reentrenó con el bloque final ni se cambió el protocolo después de verlo.
- **Regla de decisión `m6-decision-v1`** (predeclarada): el candidato es favorable solo si cumple todo esto:
  - detección ≥ 80 %;
  - diferencia frente a la referencia > 0, con el límite inferior del IC95 > 0 (bootstrap por operación base, 2.000 réplicas);
  - alertas en controles negativos ≤ las de la referencia;
  - TRM sin cambio de puntaje.

  Si no supera la referencia, se conserva la referencia; si ninguno alcanza la meta, el resultado es «inconcluso». El máximo posible con evidencia sintética es «favorable para demostración en sombra», sin promoción operativa. La CLI bloquea `modo-demo` y `promover-demo` para `anomalias`.

## 5. Escenarios de evaluación

Copias con ID nuevo (`SEM-…` y `CTL-…`). Cada una conserva su operación base, la transformación, la intensidad, la semilla, el bloque, la etiqueta sintética y el motivo. **Nunca** entran al historial, al entrenamiento ni a los grupos de otras operaciones (prueba `test_casos_sembrados_no_contaminan_historial_ni_bloques`). Para medir la detección se insertan de una en una en el conjunto de originales de su universo y mes; los empates con originales cuentan en contra.

- Bases: 40 ventas y 20 compras por bloque, sin reemplazo. Los bloques son disjuntos en el tiempo, así que ninguna base aparece en ambos.
- **Variantes reservadas.** Las intensidades de validación y comprobación son distintas:

| Tipo | Validación | Comprobación |
|---|---|---|
| precio, o costo, elevado | ×1,5 y ×2,0 | ×1,4 y ×2,5 |
| cantidad extrema | ×3 y ×5 | ×4 y ×6 |
| combinación moderada | ×1,25 y ×1,8 | ×1,3 y ×1,6 |

- **Controles negativos:**
  - cambio exclusivo de TRM (×1,3), solo en bases USD;
  - producto habitualmente más costoso, con sus valores de referencia;
  - volumen alto habitual (percentil 90);
  - cambio legítimo de mezcla de productos.

No se declaran normales las operaciones originales por falta de etiquetas.

## 6. Resultados por universo (comprobación histórica, exploratoria)

Anomalías sembradas detectadas a igual cupo (numerador / denominador):

| | Ventas · referencia | Ventas · Isolation Forest | Compras · referencia | Compras · Isolation Forest |
|---|---|---|---|---|
| **Total sembradas** | 154 / 200 (77,0 %) | 162 / 200 (81,0 %) | 89 / 100 (89,0 %) | 96 / 100 (96,0 %) |
| Precio o costo ×1,4 | 40 / 40 | 40 / 40 | 20 / 20 | 20 / 20 |
| Precio o costo ×2,5 | 40 / 40 | 40 / 40 | 20 / 20 | 20 / 20 |
| Cantidad ×4 | 12 / 40 | 19 / 40 | 12 / 20 | 17 / 20 |
| Cantidad ×6 | 22 / 40 | 23 / 40 | 17 / 20 | 19 / 20 |
| Combinación ×1,3 · ×1,6 | 40 / 40 | 40 / 40 | 20 / 20 | 20 / 20 |
| **Controles negativos con alerta** | 1 / 134 | 0 / 134 | 0 / 67 | 1 / 67 |
| TRM sin cambio de puntaje | 14 / 14 | 14 / 14 | 7 / 7 | 7 / 7 |
| Diferencia IA − referencia (IC95, por base) | — | +4,0 pp (−1,5 a +9,5) | — | +7,0 pp (+3,0 a +12,0) |
| **Decisión** | **referencia conservada** | | **referencia conservada** | |

Lectura:

- **Ventas.** La mejora del bosque (+4 pp) no es concluyente: el intervalo incluye 0. La única alerta de la referencia en controles negativos es un control de TRM con puntaje **idéntico** al de su base, que ya estaba dentro del cupo; la TRM no la causó.
- **Compras.** El bosque detecta más (+7 pp, con el IC por encima de 0), sobre todo cantidades extremas: 36 de 40 frente a 29 de 40. Pero alerta en 1 de 20 controles de volumen alto habitual, frente a 0 de la referencia. La regla predeclarada exige no empeorar los controles negativos, así que **se conserva la referencia**. Esto no se reinterpreta después de verlo.
- Las cantidades del paquete van de 1 a 8 de forma casi uniforme, así que multiplicar por 4 una cantidad baja sigue siendo «habitual». Las omisiones se concentran ahí, en ambos métodos.
- **Meta del 80 %:** el candidato la cumple en ambos universos sobre casos sembrados. La referencia la cumple en compras (89 %), pero no en ventas (77 %). La meta de ≤ 5 falsas alertas por 100 normales **revisadas** no es evaluable: hay 0 revisiones.
- **A02** (bandera sin cupo, solo ventas) marca 96 de 200 sembradas y 0 de 14 controles de TRM. No se compara a igual cupo.
- En los originales de la comprobación, ambos métodos usan el mismo cupo: 14 alertas en 255 ventas (5,49 por 100 válidas) y 4 en 40 compras (10 por 100 observadas). La cobertura de puntuación es del 100 %, con 0 abstenciones (todas las series tienen ≥ 5 antecedentes desde 2025).

Métricas no estimables, que se publican como nulas con su motivo:

- precisión entre las primeras N alertas revisadas;
- falsas alertas por 100 normales revisadas.

La prevalencia artificial de los casos sembrados no se usa para afirmar precisión comercial.

## 7. Artefactos, equivalencia e integridad

- `salida/experimentos/anomalias/preparacion/`: diagnóstico, exclusiones y control A02 (marcador `preparacion.json`).
- `salida/experimentos/anomalias/ejecucion-001/`:
  - `config.json`, `datos.json`, `preparacion.json` y `control_a02.json`;
  - `casos_validacion.json`, `validacion.json`, `equivalencia.json`, `seleccion.json` y `artefacto.json`;
  - marcador `congelacion.json`, con huellas de cada archivo, versiones (Python 3.11.3, scikit-learn 1.7.1, numpy 1.26.4), SHA-256 del código y fecha real de congelación fuera del sello;
  - `casos_comprobacion.json`, `comprobacion.json`, `detalle_casos.json` y `decision.json`, con el marcador `evaluacion.json` (sello `d3f93e8ed072…`).
- **Artefacto** `m6-5cb07a4d7d` (`jacomind.anomalias_iforest.v1`, huella `04a7accb20bc…`). Contiene:
  - variables y su orden;
  - árboles: variable, umbral, hijos y tamaño de nodo;
  - convenciones numéricas;
  - contexto y referencia;
  - política de cupo (`umbral = null`);
  - soporte, datos y versión.

  Se valida estructuralmente (hijos en rango, umbrales finitos y dimensiones) y con su huella. No se deserializa pickle ni joblib.
- **Equivalencia con scikit-learn 1.7.1.** Diferencia absoluta máxima de **0,0** en las 8 configuraciones, con el mismo ranking y las mismas alertas. Se probó con:
  - casos reales de entrenamiento y validación;
  - constantes y extremos (±50);
  - puntos **en y junto a los umbrales**: el umbral, sus vecinos float32 y ±1e-9.

  La inferencia JSON convierte la entrada a **float32**, como `tree.apply`. Suma por hoja la profundidad (raíz = 1) + c(n_hoja) − 1 en el orden de los árboles. La rareza es 2^(−suma / (n_árboles · c(max_muestras))). La tolerancia es 1e-12; si no se cumple, el entrenamiento se rechaza.
- **Publicación atómica** (`modelos/ejecucion.publicar_lote`):
  - una alteración de cualquier archivo, del artefacto o de la decisión invalida la ejecución;
  - un reintento idéntico es idempotente;
  - una interrupción se recupera sin sobrescribir evidencia distinta.

  Todo está probado en `test_evaluacion_interrupcion_idempotencia_alteraciones_y_puntuacion`.

## 8. Publicación en sombra y contrato C2

`salida/sombra/anomalias/2026-10-31/` (sello `a517bb2a6a52…`). Es una **reconstrucción histórica**: operaciones de julio a octubre de 2026, anteriores a la congelación. Una emisión prospectiva será la primera con operaciones posteriores al 23-11-2026. Contenido:

- `anomalias_operaciones.json`: 255 ventas y 40 compras. Cada fila lleva:
  - identidad, revisión de datos, fecha, producto, cliente o proveedor (las compras no llevan cliente), moneda y unidad;
  - valores observados y referencias contextuales, razones, variables, soporte y dispersión;
  - `puntaje` del método publicado, más `puntaje_referencia` y `puntaje_candidato` diferenciados;
  - `metodo`, `alerta`, `prioridad` y `cupo_periodo`, `senalada_por_reglas`, `motivos` y `variables_inusuales`;
  - `estado_puntuacion`, versión, corte, `tipo_emision` y `huella_valores`.
- `cobertura_anomalias.json`, por universo y mes: válidas, puntuadas, abstenciones, excluidas, alertas, cupo, señaladas por reglas, `exceso_sobre_cupo` y cobertura temporal. En esta publicación el exceso es 0 en los ocho meses: las 2 operaciones señaladas por las reglas quedaron dentro del cupo.
- `muestra_revision.json`: **50 operaciones** (30 ventas y 20 compras), con muestreo estratificado reproducible y probabilidad de inclusión registrada. Hay pocas alertas (14 ventas y 4 compras), así que el déficit de alertadas pasó al estrato no alertado del mismo universo: 1 en ventas y 6 en compras, registrado en `deficit_alertadas_reasignado`. Las alertadas quedan sobrerrepresentadas, por lo que la muestra **no** es representativa sin ponderar.
- Manifiesto: método publicado por universo y candidato, decisión con la huella del artefacto, huella de datos, coberturas por universo, `monitoreo` (válidas, puntuadas, abstenciones, cobertura, distribución del puntaje y alertas) y la duración de la puntuación fuera del sello.

El contrato (`contratos/validar.py: validar_anomalias`, tablas en `publicacion.v1.schema.json`) valida la coherencia, no solo los tipos:

- identidades únicas y números finitos;
- abstención con puntaje, prioridad, alerta y método nulos;
- prioridades consecutivas con desempate estable, y alerta ⇔ prioridad ≤ cupo;
- conteos reconciliados con la cobertura y `exceso_sobre_cupo`;
- versión, corte y método por universo;
- compras sin cliente, y TRM ausente sin importe COP;
- sello y huellas completos.

Las publicaciones anteriores (M1–M5) siguen validando igual.

## 9. API, permisos y revisión humana

Migración `api/migraciones/0006_anomalias.sql`, con tres capas:

- **Resultado inmutable:** `sombra_anomalias` y `sombra_cobertura_anomalias` (y la muestra en `sombra_muestras_revision`).
- **Caso de revisión:** `casos_anomalia`, con identidad tipo + ID + huella de los valores observados. Cambiar el corte, el puntaje o la versión **no** crea otro caso ni reabre una decisión cerrada. Una corrección de datos (otra huella) crea un caso nuevo con `caso_anterior` y marca el anterior `reemplazado_por`; el anterior conserva su decisión y su historial. Los casos de compras funcionan sin `cliente_id`.
- **Historial:** `eventos_anomalia` (apertura, revisión, corrección de datos y nueva publicación), con actor, fecha, motivo, evidencia, **versión examinada** y clave de idempotencia. Reimportar no duplica casos ni eventos.
- Importar una publicación de un corte anterior la guarda **sin desplazar** la activa y **sin abrir casos ni eventos**.

Rutas (`api/anomalias.py`), con permisos aplicados en el servidor:

| Ruta | Permiso | Uso |
|---|---|---|
| `GET /api/anomalias?universo=venta\|compra&periodo&producto&moneda&estado&vista=cola\|todas\|sin_historia` | `anomalias.ver` (Operaciones, Finanzas, Gerencia) | Cola priorizada, resumen, cobertura, métricas humanas y muestra |
| `GET /api/anomalias/caso?tipo&id` | `anomalias.ver` | Puntuaciones publicadas (inmutables), casos enlazados e historial |
| `POST /api/anomalias/revision` | `anomalias.revisar` (Operaciones, Finanzas) | `error_confirmado`, `cambio_legitimo` o `informacion_insuficiente`, con **motivo obligatorio** |
| `GET /api/anomalias/exportar.csv?universo` | `anomalias.exportar` | CSV de la cola |
| `GET /api/anomalias/monitoreo` | `anomalias.ver` | Publicaciones, casos por estado y avisos |
| `POST /api/anomalias/sombra` | `operacion.administrar` | Importar una publicación (rutas dentro de `salida/` o `var/`) |

- **Restricción financiera.** El importe en COP solo se entrega con `finanzas.ver` (Finanzas y Gerencia), también en el CSV. Operaciones ve precio o costo y cantidad en moneda de origen.
- Ventas, Atención y el portal empresarial reciben 403. El portal no expone puntajes ni operaciones.
- Gerencia consulta, pero no decide.
- Métricas humanas: precisión entre alertas revisadas y falsas alertas por 100 normales revisadas, con numerador y denominador. Si no son estimables son nulas con su motivo, y con soporte < 30 se marcan como descriptivas. Las operaciones sin revisar nunca cuentan como falsas alertas, e «información insuficiente» no cuenta como normal ni como error.

Vista `#/anomalias` (`app/vistas/anomalias.js`, menú «Operaciones atípicas (IA)»):

- pestañas de ventas y compras;
- filtros por periodo, producto, moneda, estado y vista;
- cola priorizada con valor observado frente a referencia y razón, motivos y soporte, método y versión;
- estado experimental y decisión;
- capacidad de revisión, alertas y exceso fuera del cupo (nunca oculto), casos pendientes y revisados;
- casos sin historia y aviso de cobertura incompleta en compras;
- cobertura por mes;
- detalle con historial, puntuaciones publicadas y formulario de revisión;
- estados sin publicación, vacío, carga, error y acceso denegado.

La página «Modelos de IA» resume la comparación.

## 10. Monitoreo

Por publicación, en `manifiesto.monitoreo`: válidas, puntuadas, abstenciones, cobertura, distribución del puntaje (p50, p90, p99 y máximo), alertas y alertas por 100. La aplicación añade los casos pendientes y revisados y los resultados humanos, y fuera del sello registra la duración de la puntuación.

Avisos persistentes e idempotentes (`api/monitoreo.py`, tabla `avisos_modelos`, reutilizable por otros modelos):

| Aviso | Severidad | Umbral (configurado en el protocolo) |
|---|---|---|
| `publicacion_rechazada` | integridad | Cualquier error de contrato, sello o huella: **la publicación no se importa** |
| `caida_cobertura` | estadístico | Caída ≥ 10 pp frente a la publicación activa anterior |
| `cambio_tasa_alertas` | estadístico | Cambio relativo ≥ 50 % con ≥ 30 operaciones en ambas |

Cada aviso explica la comparación y su soporte. Con política de cupo, la tasa de alertas depende del cupo y de la cobertura: un cambio de distribución **no** se declara deterioro predictivo, porque la precisión exige ≥ 30 revisiones comparables. Ningún aviso promociona ni revierte modelos.

## 11. Comandos reproducibles (ejecutados el 23/24-11-2026)

```
python -m modelos.cli preparar-modelo --modelo anomalias --datos salida/a01 --config modelos/config/anomalias.json --salida salida/experimentos/anomalias/preparacion
python -m modelos.cli entrenar --modelo anomalias --datos salida/a01 --config modelos/config/anomalias.json --salida salida/experimentos/anomalias/ejecucion-001
python -m modelos.cli evaluar --ejecucion salida/experimentos/anomalias/ejecucion-001 --datos salida/a01 --config modelos/config/anomalias.json
python -m modelos.cli estado --modelo anomalias --ejecucion salida/experimentos/anomalias/ejecucion-001
python -m modelos.cli puntuar --modelo anomalias --ejecucion salida/experimentos/anomalias/ejecucion-001 --datos salida/a01 --config modelos/config/anomalias.json --corte 2026-10-31 --salida salida/sombra/anomalias/2026-10-31
python -m api sombra salida/sombra/anomalias/2026-10-31
python -m modelos.cli resumen-ia
python -m unittest tests.modelos.test_anomalias
```

`entrenar` y `evaluar` necesitan `requirements-modelos.txt` (scikit-learn 1.7.1 ya instalado; no se actualizó ninguna dependencia). `puntuar`, la API y el cierre funcionan solo con la biblioteca estándar (prueba `test_puntuacion_api_y_cierre_sin_bibliotecas_analiticas`). `puntuar` no entrena ni selecciona. Repetir cualquier comando con los mismos datos y el mismo código no reescribe nada.

## 12. Limitaciones y condiciones del piloto

- **Solo hay evidencia sintética.** Los precios de venta del paquete tienen tres niveles (lista, −5 % y −10 %) y las cantidades van de 1 a 8 de forma casi uniforme. Por eso:
  - la referencia marca, por ejemplo, una venta a precio de lista tras una racha de ventas con descuento (VEN00668: ×1,11 con MAD pequeña);
  - las cantidades extremas moderadas se confunden con lo habitual.

  En datos reales, las distribuciones serán distintas.
- No hay operaciones anómalas reales etiquetadas. Los casos sembrados prueban el mecanismo, no la utilidad comercial.
- **El cupo del 5 % es una convención de demostración.** Falta acordar con Operaciones y Finanzas la capacidad mensual real.
- Compras sin cobertura temporal declarada: hace falta que la empresa la declare para hablar de tasas por periodo.
- Unidad de medida no documentada: la convención es por producto.
- Para el piloto hacen falta:
  1. revisores de Operaciones y Finanzas que revisen la muestra de 50 y las alertas mensuales, con desacuerdos resueltos;
  2. tiempo por revisión;
  3. errores confirmados con corrección contable documentada en el flujo de datos;
  4. ≥ 30 revisiones comparables antes de estimar precisión o falsas alertas.

  Solo entonces podría reconsiderarse el candidato, con un protocolo nuevo y una comprobación independiente.

## 13. M6.1: catálogo, dirección y cupo con evidencia

Protocolo [`modelos/config/anomalias_m61.json`](../modelos/config/anomalias_m61.json) (`m61-protocolo-v1`, fijado el 24-11-2026 antes de ajustar). Código: `modelos/anomalias_m61.py` (puntuación con biblioteca estándar) y `modelos/anomalias_m61_experimento.py`. Ejecución: `salida/experimentos/anomalias_m61/ejecucion-001` (artefacto `m61-769176920d`, congelación `67cba36ef5f9…`). Publicación: `salida/sombra/anomalias_m61/2026-10-31`, importada y activa.

**Por qué.** El diagnóstico de M6 mostró que la cola se llenaba de variación normal:

- 11 de 18 alertas eran cantidades **bajas** (vender 1 unidad es habitual);
- 5 eran ventas a **precio de lista** tras ventas con descuento (los tres niveles de precio son aleatorios);
- 2 no tenían ninguna variable inusual y solo llenaban el cupo;
- 26 de las 80 cantidades «extremas» sembradas en ventas quedaban dentro del rango normal (×4 de 1–2 unidades).

**Qué cambia:**

1. **Política de catálogo** (`productos.csv` de la misma revisión): precio de venta fuera de 90–100 % de la lista, costo fuera de 90–110 % del de referencia y venta por debajo del costo reciente de compra. Son convenciones de demostración, no políticas aprobadas.
2. **Dirección:** la cantidad solo cuenta por alta (`z_log_cantidad_alta`); precio y costo, en ambas direcciones.
3. **Cupo como máximo con evidencia** (`cupo_maximo_con_evidencia`): sin evidencia no hay alerta aunque quede cupo, y las operaciones con evidencia van primero. Una operación sin historia suficiente puede quedar señalada por el catálogo (visible, sin puntaje).
4. **Siembra corregida:** la cantidad extrema se fija por encima del **máximo histórico** del grupo. Se añaden precio bajo en ventas y dos controles: precio de lista tras descuentos y cantidad baja habitual.
5. **Regla `m61-decision-v1`:** los controles negativos se juzgan con **no inferioridad** (límite superior del IC95 de la diferencia ≤ 2 pp, por operación base).
6. **Candidato:** Isolation Forest con `[z valor, z cantidad alta]`. Su evidencia propia es una rareza ≥ al cuantil 99,5 % de la rareza de **entrenamiento**. Equivalencia JSON ↔ scikit-learn exacta.

**Resultados.** Comprobación julio–octubre 2026, **exploratoria y no independiente**: estos datos ya se usaron para diagnosticar M6. M6 se mide sobre los mismos casos solo como contexto.

| | Ventas M6 | Ventas M6.1 reglas | Ventas M6.1 IA | Compras M6 | Compras M6.1 reglas | Compras M6.1 IA |
|---|---|---|---|---|---|---|
| Sembradas detectadas | 193/280 (68,9 %) | **242/280 (86,4 %)** | 242/280 | 80/100 | **80/100** | 81/100 |
| Normales construidas con alerta | 10/208 (4,8 %) | **3/208 (1,4 %)** | 3/208 | 20/86 (23 %) | **0/86** | 0/86 |
| Alertas en operaciones reales | 14 de 255 | **1 de 255** | 1 | 4 de 40 | **0 de 40** | 0 |

- **Decisión:** se conserva la **referencia (reglas)** en ambos universos. La IA no mejora la detección con un IC95 por encima de 0: en ventas es idéntica, y en compras gana +1 caso (IC 0 a +3 pp).
- **Omisiones restantes.** La cantidad sembrada ×1,3 sobre el máximo histórico se detecta poco (2/40 en ventas y 0/20 en compras con las reglas): queda por debajo de la razón 3× y de z 3,5. Es una frontera explícita, no un fallo oculto.
- **Ruido restante.** 3 de 40 controles de «precio de lista tras descuentos» y la única alerta real (VEN00668, ×1,11) vienen de la regla de contexto: MAD pequeña con z ≥ 3,5. El catálogo ya dice que el precio de lista es válido. La siguiente mejora sería que el contexto de precio respete los niveles del catálogo; requiere un protocolo nuevo.
- **Monitoreo.** Al importar M6.1 se registraron los avisos `cambio_tasa_alertas` (14→1 y 4→0), con su explicación: el cambio es de política, no de deterioro.
- **Casos de M6.** Los casos abiertos por M6 siguen en la cola como pendientes: un cambio de versión nunca cierra decisiones automáticamente.

Comandos:

```
python -m modelos.cli preparar-modelo --modelo anomalias --datos salida/a01 --config modelos/config/anomalias_m61.json --salida salida/experimentos/anomalias_m61/preparacion
python -m modelos.cli entrenar --modelo anomalias --datos salida/a01 --config modelos/config/anomalias_m61.json --salida salida/experimentos/anomalias_m61/ejecucion-001
python -m modelos.cli evaluar --ejecucion salida/experimentos/anomalias_m61/ejecucion-001 --datos salida/a01 --m6 salida/experimentos/anomalias/ejecucion-001
python -m modelos.cli puntuar --modelo anomalias --ejecucion salida/experimentos/anomalias_m61/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/anomalias_m61/2026-10-31
python -m api sombra salida/sombra/anomalias_m61/2026-10-31
```
