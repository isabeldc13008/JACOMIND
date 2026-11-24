# Base común para entrenar evaluar y publicar modelos

[Volver al programa](README.md)

Esta base evita que cada modelo resuelva de forma distinta la calidad del dato, el uso del futuro o la publicación. Es una entrega previa a la promoción de cualquier candidato, aunque la exploración de cada modelo puede comenzar con el paquete sintético.

## Datos y conocimiento disponible

Usar A01 para producir tablas normalizadas y aceptadas. El generador actual valida el lote y después vuelve a leer los archivos originales; cambiar ese recorrido para que el entrenamiento y el cierre consuman la misma revisión publicada. Un lote fallido o pendiente de revisión no sustituye por defecto el último válido. Una aceptación parcial explícita debe identificar filas excluidas y cobertura afectada.

Cada fotografía debe llevar `cliente_id` cuando corresponda, `corte`, revisión del lote, límite de cobertura completa de datos, versión de variables y fecha de disponibilidad. Una transacción con fecha anterior al corte pero recibida después no era conocida en ese momento. En datos reales se requiere historial de cargas o `disponible_desde`. En el paquete sintético solo se puede aplicar la convención de disponibilidad por fecha del evento y documentarla.

Reglas comunes:

- Ventas confirmadas hasta el corte, incluyendo ese día. Futuro objetivo desde el día siguiente.
- Cantidad, precio y moneda se conservan antes de convertir importes a COP con la tasa de su fecha.
- Compras y ventas permanecen como hechos distintos; se agregan antes de combinarlas.
- La última transacción no prueba por sí sola que un periodo esté completo. El manifiesto de ingestión debe declarar `datos_observados_hasta` por fuente.
- Coberturas iniciadas en el futuro, renovaciones registradas posteriormente y correcciones futuras no pueden entrar en las variables históricas.
- Si no puede reconstruirse la disponibilidad histórica de una cobertura o atributo, excluirlo del experimento principal y evaluar su incorporación prospectivamente.
- El CSV opcional con incidencias sirve para probar la ingesta, no para ampliar la muestra de entrenamiento.

## Particiones y madurez de etiquetas

En clasificación a H días, una fotografía solo tiene etiqueta si `corte + H <= datos_observados_hasta`. Además, toda etiqueta usada para ajustar parámetros debe estar disponible antes de la fecha de la predicción que se evalúa. Escalado, imputación, selección de variables, calibración y selección de modelos respetan ese mismo límite.

Protocolos históricos iniciales, sin reentrenar entre los bloques de validación y prueba:

| Objetivo | Cortes de ajuste | Cortes de validación | Cortes de comprobación histórica | Frontera que protege la prueba |
|---|---|---|---|---|
| Compra a 30 días | Marzo 2025–abril 2026 | Mayo y junio 2026 | Julio–septiembre 2026 | Etiqueta del 30 de junio madura el 30 de julio, antes del 31 de julio |
| Inactividad y recomendación a 60 días | Marzo 2025–febrero 2026 | Abril y mayo 2026 | Julio y agosto 2026 | Etiqueta del 31 de mayo madura el 30 de julio, antes del 31 de julio |

En el protocolo de 60 días se omiten marzo y junio como cortes entre bloques para evitar solapamientos que revelen futuro. La etiqueta de agosto madura el 30 de octubre. Septiembre necesita información hasta el 29 de noviembre y no puede evaluarse con el paquete actual. M3 usa el mismo calendario de orígenes con censura administrativa propia; M5 y M6 tienen protocolos específicos.

Estos datos ya fueron inspeccionados. Las comprobaciones históricas son evidencia exploratoria, aunque se mantengan particiones. Congelar configuración y métricas antes de recibir un periodo nuevo. El primer corte prospectivo debe ser posterior a la congelación y contar con la historia necesaria; su evaluación espera H días completos. Si se usa una nueva generación sintética independiente, solo valida generalización dentro de ese generador.

Para cada origen de una evaluación sucesiva, ajustar con etiquetas maduras en ese origen. No aplicar sin revisión una partición temporal de librería sobre filas: el orden debe ser por fecha y los clientes de un mismo corte permanecen juntos. Los registros repetidos de un cliente no son observaciones independientes. Estimar incertidumbre agrupando por cliente y mostrar resultados por mes; con dos o tres meses no afirmar estabilidad a largo plazo.

## Métricas y decisión

Cada experimento registra población elegible, exclusiones, número de clientes únicos, eventos, referencias, métrica principal, métricas secundarias, denominadores y decisión. En rankings fijar desempate por ID y K antes de evaluar. Si hay menos de K elegibles, usar `min(K, n)` y publicar ese denominador.

La ausencia de evidencia suficiente produce `inconcluso`, no una mejora. Los límites comerciales aún por fijar usan valores iniciales indicados en cada plan. Cualquier cambio de objetivo, umbral o selección tras mirar la prueba crea una nueva versión de protocolo y necesita otra comprobación independiente.

Distinguir tres resultados: integración correcta, mejora predictiva y utilidad comercial. Un comprador posterior a un contacto no demuestra que el contacto causó la compra. Para medir incremento, el piloto puede asignar por cliente seguimiento habitual o asistido con autorización empresarial, manteniendo asignación estable y un cálculo previo del tamaño necesario. Si la muestra no permite estimarlo, reportar solo métricas descriptivas y tiempo de trabajo.

## Arquitectura y artefactos

Crear un paquete de experimentación `modelos/` y una dependencia opcional `requirements-modelos.txt`, con versiones compatibles verificadas al implementar. Separar scikit-learn, statsmodels y el módulo de supervivencia del entorno que sirve la API. Entrenar y puntuar en un proceso de análisis por lotes; la aplicación consume JSON validado y conserva su ejecución básica sin esas dependencias.

Separar las operaciones propuestas `entrenar`, `evaluar`, `puntuar` y `promover`. El cierre usa una versión seleccionada explícitamente y no llama al entrenamiento. Desde el 23 de noviembre de 2026 existen para los seis modelos: `compra_30d` (M1), `inactividad_60d` (M2), `proxima_compra` (M3), `venta_cruzada` (M4), `demanda` (M5) y `anomalias` (M6), con `--modelo` en `entrenar` y `puntuar`. `evaluar` detecta el modelo por la configuración de la ejecución. M2 a M6 se publican en sombra; `anomalias` no admite promoción ni modo demostración.

Interfaz de línea de comandos a implementar en `modelos/cli.py`, ejecutada desde la raíz del proyecto:

```text
python -m modelos.cli entrenar --modelo compra_30d --datos salida/a01/publicado --config modelos/config/compra_30d.json --salida salida/experimentos/compra_30d/ejecucion-001
python -m modelos.cli evaluar --ejecucion salida/experimentos/compra_30d/ejecucion-001 --bloque comprobacion_historica
python -m modelos.cli puntuar --artefacto var/modelos/compra_30d/v2 --datos salida/a01/publicado --corte 2026-10-31 --salida salida/puntuaciones/2026-10-31
python -m modelos.cli promover --ejecucion salida/experimentos/compra_30d/ejecucion-001 --registro var/modelos --version v2
```

Para `compra_30d` estos comandos funcionan; la CLI añade `preparar`, `reproducir-referencia`, `inicializar-referencia`, `comparar`, `revertir` y `estado` (ver la [ficha del modelo de compra](../../modelo-compra.md)). Los demás modelos usan la misma CLI con `--modelo`; M4–M6 añaden `preparar-modelo` y M5 `ajustar-origen` e `incorporar-observaciones`. Ver cada ficha. `entrenar` consume tablas aceptadas y conserva una referencia inmutable a sus datos. `evaluar` usa el bloque declarado sin reajustar parámetros. `puntuar` no necesita etiquetas futuras. `promover` exige una decisión registrada que permita el estado solicitado: un candidato aceptado solo para sombra no puede convertirse en versión operativa. Los IDs de los seis modelos son `compra_30d`, `inactividad_60d`, `proxima_compra`, `venta_cruzada`, `demanda` y `anomalias`.

Por ejecución guardar bajo `salida/experimentos/<modelo>/<ejecucion>/`:

| Archivo | Contenido |
|---|---|
| `config.json` | Objetivo, horizontes, cortes, variables, semilla, candidatos y metas fijadas |
| `datos.json` | Huellas, revisión, cobertura temporal, reglas de elegibilidad y conteos |
| `artefacto.json` y archivo del estimador si se necesita | Variables ordenadas, transformaciones, parámetros, formato y versión |
| `metricas.json` | Resultados por bloque, mes, segmento, referencia y tamaños |
| `predicciones.csv` | Claves, origen, predicción, etiqueta o censura, referencia y versión |
| `decision.json` | Aceptado, rechazado o inconcluso; motivos y versión sustituida |

Para regresiones simples preferir parámetros numéricos en JSON. Cuando se conserve un estimador serializado, cargar solo artefactos creados por el proceso controlado, comprobar huella y entorno compatible y no aceptar archivos de modelos desde cargas del usuario. Los formatos basados en pickle pueden ejecutar código al cargarse. [Persistencia de modelos de scikit-learn](https://scikit-learn.org/stable/model_persistence.html).

Registrar modelos promovidos en `var/modelos/<modelo>/<version>/`, fuera del repositorio. Conservar versión anterior, versión de código y dependencias. Un cambio de variable, transformación, catálogo o definición de etiqueta exige una versión nueva. La promoción del puntero activo es atómica y no modifica un artefacto publicado.

## Contratos e integración

Mantener el significado de C1: `prob_compra_30d` sigue siendo la probabilidad de compra, no un riesgo de inactividad ni un puntaje de anomalía. C1 conserva sus cinco acciones actuales. La incorporación de acciones o semánticas incompatibles requiere una versión nueva y migración coordinada.

Extensiones aditivas previstas en C2:

| Tabla propuesta | Clave dentro de un cierre | Modelos |
|---|---|---|
| `predicciones_clientes` | `cliente_id, modelo_id` | M1, M2 y M3 |
| `recomendaciones_productos` | `cliente_id, producto_id` | M4 |
| `pronosticos_demanda` | `origen, serie_id, horizonte` | M5 |
| `anomalias_operaciones` | `tipo_operacion, operacion_id` | M6 |

Cada fila incluye `version_modelo`, `estado`, `motivos`, corte/origen y unidades aplicables. `null` indica estimación no disponible, acompañado de una causa. Los estados previstos son `estimado`, `referencia`, `sin_historial`, `historia_insuficiente`, `estimacion_vencida`, `no_elegible` y `modelo_no_disponible`. Los errores de lote impiden publicar; no se convierten en predicciones vacías aparentemente válidas.

El validador actual admite tablas desconocidas, pero no garantiza sus claves ni sus tipos. Añadirlas a `tablas_conocidas`, extender la validación semántica y probar productor y consumidor antes de publicarlas. Una tabla adicional no se considera integrada solo porque el JSON se acepte. El proceso operativo publica únicamente la versión activa; las variantes candidatas permanecen en experimentos.

Ampliar consultas internas, herramientas del asistente y vistas ya existentes sin cambiar autenticación. Aplicar permisos de cartera, finanzas y operaciones; el portal de clientes no recibe puntuaciones internas de riesgo. El asistente cita los resultados persistidos, no calcula probabilidades nuevas. Las propuestas de interfaz se detallarán al implementar cada vista.

Para las tareas humanas, conservar decisiones anteriores y una identidad estable por episodio. Versionar el modelo no crea por sí solo una tarea nueva. Al sustituir un cierre se comprueba que no cambien los resultados registrados por los usuarios.

## Tickets comunes

| Ticket | Responsable | Trabajo y evidencia de cierre | Depende de |
|---|---|---|---|
| B0-01 | A | Consumir la revisión aceptada de A01; demostrar que duplicados aislados no llegan al modelo | Ninguno |
| B0-02 | A | Variables y etiquetas con disponibilidad temporal; casos de fecha límite, futuro y lote incompleto | B0-01 |
| B0-03 | A y usuario del módulo | Configurar particiones, referencias, K y métricas; guardar el protocolo antes del ajuste | B0-02 |
| B0-04 | A | Separar ajuste y puntuación; guardar y recargar artefactos con predicciones equivalentes | B0-03 |
| B0-05 | B | Definir tablas, claves, tipos, permisos y muestras C2; rechazar duplicados y tipos incorrectos | B0-02 |
| B0-06 | A y B | Generar y publicar con una versión activa; simular fallo y conservar último cierre válido | B0-04 y B0-05 |
| B0-07 | A y B | Métricas por cierre, resultados pendientes de madurez, alertas de cobertura y reversión | B0-06 |

Estado al 23 de noviembre de 2026, con el alcance mínimo que necesita M1 (horizonte de 30 días):

- **B0-01 a B0-06: hechos para `compra_30d`.** El código está en `modelos/datos.py`, `variables.py`, `inferencia.py`, `registro.py` y `compra.py`, más `pipeline/generar.py` y `contratos/validar.py`. La evidencia está en `tests/modelos/test_compra_30d.py` y en la ejecución documentada en la [ficha del modelo de compra](../../modelo-compra.md).
- **B0-07: parcial.** Hay resultados pendientes de madurez, comparación en sombra y reversión. Desde M6 existe un componente reutilizable de avisos persistentes e idempotentes (`api/monitoreo.py`, tabla `avisos_modelos`): integridad al rechazar una publicación, caída de cobertura y cambio de tasa de alertas, con umbrales configurados. Por ahora solo M6 lo usa; faltan las alertas por cierre de M1–M5.
- **Protocolo de 60 días: hecho para M2** (`modelos/config/inactividad_60d.json`), con fronteras comprobadas por código. Las ejecuciones nuevas usan `modelos/ejecucion.py`: evidencia sellada, artefacto principal ligado al candidato elegido y evaluación recuperable e idempotente.
- **Tablas C2 de M4–M6: hechas** (`recomendaciones_productos`, `cobertura_recomendaciones`, `pronosticos_demanda`, `calendario_demanda`, `anomalias_operaciones`, `cobertura_anomalias`), validadas en `contratos/validar.py`.
- **Pendiente:** corregir en los evaluadores M1.1–M1.3 los tres problemas de la auditoría. Siguen allí porque M2 no reutiliza esos evaluadores; ver la [ficha de M2](../../modelo-inactividad.md#integridad-reproducibilidad-y-recuperación).

Los tickets específicos de los modelos añaden sus pruebas estadísticas y de negocio. Las decisiones empresariales pendientes no bloquean la implementación con las convenciones sintéticas documentadas.

## Pruebas comunes y operación

Probar que agregar una venta posterior al origen deja intactas las variables anteriores; que una etiqueta no madura sigue pendiente; que un lote duplicado no duplica predicciones; que cargar y puntuar un artefacto no vuelve a entrenar; y que cambiar su esquema provoca un rechazo entendible. Comparar parámetros persistidos y puntuaciones con tolerancia numérica declarada.

En cada cierre guardar cobertura, estados nulos, distribución de variables y puntuaciones, versión activa y tiempos de ejecución. Calcular métricas solo cuando madure cada horizonte. Umbrales iniciales de investigación: caída de cobertura mayor a diez puntos porcentuales o deterioro relativo mayor a 20 % frente a la referencia en dos cortes maduros. Con muestras pequeñas, revisar conteos y errores antes de decidir. Un error de esquema o integridad impide publicar de inmediato.

La reversión selecciona el artefacto anterior o la referencia documentada y regenera en un cierre nuevo, manteniendo el historial. No se retrena automáticamente por una alerta. Para reentrenar, definir datos añadidos, nuevo protocolo y comparador.

## Criterio de entrega

Las casillas marcadas corresponden a `compra_30d`; los demás modelos deben aportar su propia evidencia.

- [x] Un comando de cada operación propuesta funciona en un entorno documentado y aislado (`entrenar` verificado también con `uv run --python 3.10 --with-requirements requirements-modelos.txt`).
- [x] Es posible reproducir un resultado desde datos, configuración y código versionados (misma huella del artefacto al repetir la ejecución; en otro entorno, pesos iguales dentro de 3 × 10⁻¹⁶).
- [x] Pasan las pruebas de frontera temporal, persistencia, contrato y permisos correspondientes.
- [x] API y aplicación arrancan sin las dependencias opcionales de entrenamiento (prueba con importaciones de sklearn/numpy/scipy bloqueadas).
- [x] Un candidato rechazado deja activa la referencia o versión previa (`promover` rechaza `rechazado`; operativo exige `estado_maximo = operativo`).
- [x] Los resultados de la comprobación histórica se distinguen de los del piloto prospectivo (`alcance` en `metricas_*.json` y `decision.json`; octubre queda pendiente).
