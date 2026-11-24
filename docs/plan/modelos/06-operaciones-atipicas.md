# Plan del modelo de detección de operaciones atípicas

[Programa](README.md) · [Base común](00-base-comun.md)

**Implementado el 23 de noviembre de 2026, en sombra.** Se conserva la referencia mediana/MAD en ventas y compras; la cola de revisión funciona con 0 revisiones reales. Resultados, integración y piloto en la [ficha del modelo](../../modelo-anomalias.md).

## Objetivo y decisión

Crear una cola de revisión de ventas y compras con precios, cantidades o costos inusuales. La alerta identifica qué cambió respecto de operaciones comparables y permite a Operaciones confirmar, descartar o corregir. Una puntuación alta no equivale a fraude ni autoriza eliminar la operación.

Responsable técnico: A. Integración: B. Usuarios de evaluación: Operaciones y Finanzas. Esfuerzo estimado: 4–6 jornadas persona.

## Estado y separación de controles

[`pipeline/operaciones.py`](../../../pipeline/operaciones.py) ya usa mediana y desviación absoluta mediana para detectar variaciones. Mantener ese control como referencia interpretable. El modelo candidato es Isolation Forest, un detector no supervisado de observaciones atípicas. Su puntuación expresa rareza respecto al ajuste, no una probabilidad de error. [Documentación oficial](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).

Separar errores de esquema y anomalías comerciales. Una fecha inválida, una referencia inexistente o un duplicado pertenecen a A01 y no deben entrar al modelo. El CSV opcional con incidencias valida esa barrera; no constituye un conjunto etiquetado de fraude o anomalías comerciales.

## Dataset y variables

Unidad: operación válida, con clave compuesta por tipo de operación e ID. Trabajar con ventas confirmadas y compras como universos separados. Nunca mezclar sus precios y costos como si midieran el mismo concepto.

| Señal | Construcción | Control |
|---|---|---|
| Cantidad | Cantidad y logaritmo; desviación respecto de historia comparable | Comparar dentro del mismo producto y unidad |
| Precio o costo unitario | Valor en moneda de origen y relación con mediana histórica | Moneda, producto y tipo de operación explícitos |
| Importe | Cantidad por precio/costo, moneda de origen e importe COP separados | Un aumento por cantidad tiene motivo distinto del aumento de precio |
| Cambio cambiario | TRM observada y variación del componente COP | La rareza comercial en USD no debe cambiar solo por convertir a COP |
| Contexto histórico | Número de comparables y dispersión | Indicar cuándo el grupo tiene poco soporte |

Calcular las referencias de cada operación con datos anteriores a su fecha. Si varias operaciones comparten día y no existe hora fiable, ninguna se usa como pasado de otra ese mismo día. Con menos de cinco operaciones comparables previas, usar un grupo compatible documentado o `historia_insuficiente`. No mezclar productos con unidades distintas para fabricar soporte.

Entrenar inicialmente dos detectores, uno para ventas y otro para compras, sobre variables normalizadas respecto a su contexto comparable. No entrenar decenas de modelos por producto/proveedor con solo 240 compras. Exigir inicialmente al menos 50 filas utilizables por detector; si un universo no llega, conservar el control estadístico. No incluir identificadores arbitrarios de cliente/proveedor como magnitudes numéricas.

Los descuentos adicionales son todos cero en este paquete. La variable puede mantenerse como control, pero no se puede demostrar aprendizaje de descuentos inusuales hasta contar con variación o casos de prueba explícitos.

## Entrenamiento y umbral

Referencias: control de mediana/desviación absoluta y reglas concretas de razón de precio o cantidad. Candidato: Isolation Forest con semilla fija y una configuración pequeña de partida, por ejemplo 200 árboles y submuestra limitada por el tamaño real. Seleccionar en validación como máximo unas pocas configuraciones previamente registradas.

Usar la puntuación continua para ordenar. Fijar el umbral con el conjunto de validación revisado y con la capacidad de revisión; no tratar el parámetro de contaminación como una proporción real conocida de errores. Si no hay etiquetas revisadas, solo se puede establecer un cupo de alertas y evaluar casos sembrados, dejando la precisión comercial como pendiente.

Una transformación, regla o límite ajustado al ver las anomalías de prueba es una nueva versión que necesita otra comprobación. Conservar operaciones atípicas plausibles en el histórico y documentar cualquier exclusión del entrenamiento, evitando limpiarlo hasta que el modelo parezca perfecto.

## Evaluación temporal y casos controlados

Partición inicial: entrenamiento enero–diciembre de 2025; validación enero–junio de 2026; comprobación histórica julio–octubre de 2026. Dentro de cada bloque, las variables conservan orden temporal y soporte previo. No usar operaciones del bloque final para definir normalizadores o umbrales.

Crear copias de evaluación con perturbaciones comerciales válidas: precio unitario multiplicado, cantidad extrema, costo de proveedor alterado y combinación moderada de ambas variables. Mantener claves nuevas y trazabilidad a la operación base. Separar operaciones base y familias de perturbación entre validación y prueba para que variantes casi idénticas no aparezcan en ambos bloques.

Añadir controles negativos: incremento COP explicado solo por TRM, producto genuinamente más costoso, compra de volumen alto habitual y cambio de mezcla entre familias. Mantener precio y cantidad de origen al modificar únicamente la TRM. El detector comercial no debe señalar sobreprecio en ese control; una alerta cambiaria separada puede explicarlo si existe esa política.

Revisar una muestra de operaciones originales con Operaciones antes de llamarlas normales. El objetivo inicial es al menos 50 revisiones entre ventas y compras, con desacuerdos resueltos y motivo documentado. Aumentar la muestra cuando sea necesario para estimar precisión; ese mínimo permite una demostración del flujo, no asegura representatividad.

Métricas: detección por tipo/intensidad de anomalía sembrada, falsas alertas entre normales revisadas, precisión de las primeras N alertas revisadas y alertas por 100 operaciones válidas. Comparar candidato y referencia a igual cupo, por tipo de operación. Informar por separado casos sembrados, revisados e indeterminados.

## Tickets de implementación

| Ticket | Trabajo | Evidencia de cierre | Dependencia |
|---|---|---|---|
| M6-01 | Separar errores A01 y datos válidos para rareza | Incidencias inválidas aisladas antes de puntuar | B0-01 |
| M6-02 | Construir variables contextuales por fecha | Historia previa, moneda, unidad y soporte verificables | B0-02 y M6-01 |
| M6-03 | Crear casos sembrados y revisión de originales | Registro de origen, perturbación, bloque y etiqueta revisada | M6-02 |
| M6-04 | Ajustar detector y elegir umbral/cupo | Comparación contra mediana y reglas en validación | B0-03 y M6-03 |
| M6-05 | Comprobar detección y falsas alertas | Informe por tipo de operación y escenario | M6-04 |
| M6-06 | Persistir y publicar cola de revisión | Puntajes, motivos, permisos y resultados humanos persistentes | B0-04, B0-05 y M6-05 |
| M6-07 | Medir carga y utilidad del piloto | Tiempo por revisión y errores/cambios confirmados | B0-07 y M6-06 |

Rutas propuestas: `modelos/anomalias.py`, ampliación de `pipeline/operaciones.py`, `tests/modelos/test_anomalias.py`, tabla C2 y consultas de Operaciones. Reutilizar el patrón de eventos de `api/tareas.py` para revisiones, sin forzar una anomalía de proveedor a tener un cliente.

## Pruebas necesarias

- Precio multiplicado y cantidad multiplicada se detectan con motivos distintos cuando el modelo los considere atípicos.
- Un cambio solo de TRM no modifica las variables de precio/cantidad en moneda de origen ni genera motivo falso de sobreprecio.
- Dos productos con precios base diferentes se comparan en su contexto, no por magnitud COP global.
- Grupo sin historia o con dispersión cero conserva una regla explícita o abstención.
- Agregar operaciones futuras no cambia referencias ni puntuaciones pasadas del artefacto evaluado.
- Una anomalía sembrada de prueba no participa en ajuste ni selección de umbral.
- Dos operaciones de distinto tipo con el mismo ID no colisionan.
- Repetir la publicación no duplica alertas; una corrección crea una revisión con vínculo a la anterior y conserva el historial.
- El puntaje jamás se presenta como «probabilidad de fraude» o «porcentaje de error».

## Integración y salida

En `anomalias_operaciones` publicar tipo, ID de operación, fecha, producto, proveedor o cliente cuando aplique, puntaje, estado, versión, variables atípicas, valor observado, referencia y soporte. La dirección del puntaje se normaliza y documenta para que un valor mayor siempre signifique más prioridad de revisión en la aplicación.

La cola permite marcar error confirmado, cambio legítimo, información insuficiente y pendiente. Una corrección se realiza en el flujo de datos con trazabilidad; el modelo no sobrescribe importes. La cola queda restringida a los perfiles internos correspondientes y sus resultados no alteran automáticamente segmentación, beneficios ni crédito del cliente.

## Criterios de aceptación

- [ ] Los errores de ingesta no llegan al detector y las monedas permanecen separadas correctamente.
- [ ] Meta inicial: detectar al menos 80 % de las anomalías comerciales sembradas relevantes, reportando también las omisiones por tipo.
- [ ] Meta inicial: no más de cinco falsas alertas por 100 operaciones revisadas como normales; con menos casos, mostrar el conteo y la incertidumbre sin afirmar ese límite con certeza.
- [ ] Superar la referencia en detección a igual cupo, o reducir el tiempo de revisión sin empeorar detección medida.
- [ ] Acordar cupo mensual y mostrar alertas pendientes; no descartar silenciosamente el exceso para mejorar la tasa reportada.
- [ ] Puntajes y motivos trazables, sin modificación automática de datos y con resultados humanos conservados.

Si solo se cumplen las metas sobre casos sembrados, aceptar la demostración técnica y mantener el detector en sombra hasta reunir revisiones de operaciones reales. Cuando el control estadístico funcione mejor, conservarlo como método operativo.

## Piloto y mantenimiento

Medir operaciones revisadas, tiempo por caso, errores confirmados y cambios legítimos encontrados. Cuantificar importes corregidos únicamente cuando exista una corrección contable documentada. Revisar la tasa de alertas por tipo, producto y moneda y los cambios de proveedores o lista de precios. Si una nueva política comercial cambia la distribución, comprobarla antes de interpretar el cambio como degradación del modelo.
