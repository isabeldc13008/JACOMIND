# Plan del modelo de compra a 30 días

[Programa](README.md) · [Base común](00-base-comun.md)

## Objetivo y decisión

Mejorar la selección de clientes que Ventas puede atender en cada cierre. La pregunta es si un cliente con compras previas realizará al menos una compra confirmada en los siguientes 30 días. La salida ayuda a ordenar seguimientos; no estima el efecto de contactar al cliente ni el valor monetario de la venta.

Responsable técnico: A. Integración: B. Usuario de evaluación: Ventas. Esfuerzo estimado: 4–6 jornadas persona después de la base común.

## Estado y referencia

> **Estado al 23 de noviembre de 2026: implementado; decisión «inconcluso».** Resultados, comandos y limitaciones en la [ficha del modelo](../../modelo-compra.md). El código está en [`modelos/`](../../../modelos/) (`datos`, `variables`, `inferencia`, `metricas`, `registro`, `compra` y `cli`) y la configuración congelada en [`modelos/config/compra_30d.json`](../../../modelos/config/compra_30d.json). Las pruebas están en [`tests/modelos/test_compra_30d.py`](../../../tests/modelos/test_compra_30d.py) y [`tests/modelos/test_m1_correcciones.py`](../../../tests/modelos/test_m1_correcciones.py), esta última con la regresión de los siete hallazgos de la auditoría del 23 de noviembre. El operativo sigue siendo la referencia `A04-logistica-reglas-v1` (`v1`) y el candidato `compra_30d-m1-a-c10-b8799da6` (`v2`) queda en sombra. Congelación real: 2026-11-23. El corte de octubre es una comprobación retrospectiva y el primer corte prospectivo es el 2026-11-30, con horizonte hasta el 2026-12-30. El piloto está preparado, no ejecutado.

> **M1.3 (23-11-2026):** supervivencia de intervalos (S) y ponderación temporal con ajuste de nivel (P), evaluados en la validación temporal de desarrollo. S: 51/100 frente a 54/100 de recencia; P: log loss +0,0011 frente al control. Ambos **inconclusos**. En la comprobación exploratoria, P tiene la mejor calidad probabilística (Brier 0,2213) sin mejorar el orden. Ver la [ficha M1.3](../../modelo-compra-m13.md).

> **M1.2 (23-11-2026):** fusión de rangos recencia + modelo como orden del cupo, evaluada con la validación temporal de 10 orígenes como criterio principal: 52/100 frente a 54/100 de recencia (IC 95 % de −7 a +8 puntos); decisión **inconcluso**. Ver la [ficha M1.2](../../modelo-compra-m12.md).

> **M1.1 (23-11-2026):** se implementó y evaluó la línea experimental descrita en la [ficha M1.1](../../modelo-compra-m11.md), con protocolo `m1.1-protocolo-v1`. Incluye variables de ciclo y cambio de ritmo, logística frente a gradient boosting, calibración sigmoidal fuera de muestra y validación por origen creciente. Resultado: ningún candidato mejora las referencias (16/30 frente a 17/30 en la población elegible y 13/30 frente a 19/30 en la atendible); decisión **inconcluso**. Las variables de producto y vigencia del catálogo quedan excluidas porque su disponibilidad histórica no es demostrable, y las señales comerciales están pendientes de datos ([inventario](m1.1-senales-comerciales.md)). Las correcciones de la segunda auditoría (publicación del cierre, excepción de referencia, identidad de selección, cobertura reutilizada y evaluación rechazada) están en [`tests/modelos/test_m1_auditoria2.py`](../../../tests/modelos/test_m1_auditoria2.py).

Antes de esta entrega, [`pipeline/modelo_compra.py`](../../../pipeline/modelo_compra.py) construía fotografías, estandarizaba cuatro variables y ajustaba una regresión logística, y [`pipeline/generar.py`](../../../pipeline/generar.py) la reentrenaba en cada cierre sobre los CSV originales. Ahora la reproducción histórica se conserva como control explícito (`reproducir-referencia`, `inicializar-referencia`) y el cierre carga la versión operativa del registro sin entrenar.

En los 360 casos de prueba publicados: TP 120, TN 51, FP 177 y FN 12, con umbral 0,4. Precisión 40,4 %, sensibilidad 90,9 % y F1 0,5594. La regla de compra reciente obtiene precisión 52,1 % y F1 0,5368. En los diez primeros de cada mes, el modelo obtiene 5, 4 y 4 compras; el orden por recencia obtiene 5, 7 y 5. Los resultados son de la cartera sintética y ya se conocen.

## Dataset y etiqueta

Unidad de observación: cliente y cierre mensual. Incluir clientes dados de alta al corte y con al menos una compra confirmada previa. Reportar por separado la reproducción original, que incluye 177 fotografías sin compras en entrenamiento. La versión de recompra excluye esas fotografías y se vuelve a evaluar con esa población explícita.

`y = 1` cuando existe una compra confirmada en `(corte, corte + 30 días]`; `y = 0` solo si el horizonte completo está observado y no existe tal compra. Un futuro incompleto produce etiqueta pendiente, no cero. Clientes sin compras reciben `sin_historial` y la regla de primera compra.

| Grupo de variables | Construcción al corte | Control |
|---|---|---|
| Recencia y frecuencia | Recencia y conteos a 30, 90 y 180 días | Distinguir operaciones y días de compra |
| Valor | Importe COP a 90/180 días y ticket medio | Usar redondeo A02 y transformación logarítmica ajustada en entrenamiento |
| Cambio de actividad | Frecuencia últimos 30 días frente a los 30 anteriores | Con denominador cero, usar diferencia absoluta y un indicador |
| Recurrencia | Mediana y dispersión de intervalos entre días distintos | Historia escasa genera indicador, no un intervalo inventado |
| Productos | Participación por familia y compras de productos recurrentes | Catálogo conocido al corte; evitar ID de cliente como variable |
| Coberturas | Días a fin y coberturas próximas conocidas al corte | Incorporar solo si se puede reconstruir disponibilidad histórica |

Comenzar con recencia/frecuencia, luego añadir grupos de uno en uno. Limitar el primer candidato a unas 10–15 variables útiles para evitar complejidad innecesaria en 120 clientes. Ciudad, sector y canal quedan como análisis opcional, condicionado a soporte y disponibilidad, no como requisitos iniciales.

## Entrenamiento y selección

Comparar cuatro referencias: regresión actual congelada, regla `frecuencia_30d > 0`, ranking de menor recencia y tasa de compra del entrenamiento. Candidato principal: regresión logística L2 con transformaciones compartidas entre ajuste e inferencia. Ensayar una rejilla pequeña de regularización fijada antes de validar; por ejemplo `C` en 0,1, 1 y 10.

No equilibrar artificialmente las clases por defecto, porque interesa obtener probabilidades interpretables. Si se ensayan pesos, evaluar después la calibración. Un árbol de profundidad máxima tres puede ser un segundo experimento después de cerrar el primero, con nueva configuración y comparación explícita.

Usar la partición de 30 días de la base común. Seleccionar variables y regularización con validación. Si se calibra la probabilidad, generar predicciones temporales fuera de ajuste en bloques anteriores para entrenar el calibrador; no calibrar con predicciones sobre las mismas filas usadas para ajustar pesos. Mantener la probabilidad sin recalibrar cuando los datos no alcancen y reportar su sesgo. La prueba histórica no selecciona parámetros.

La métrica principal es precisión entre los primeros diez clientes de cada mes. Informar también K=20, sensibilidad a ese cupo, PR-AUC, F1 al umbral operativo, Brier, calibración y tamaños. Elegir el umbral únicamente en validación según cupo y costo acordados; no interpretar 0,4 como política empresarial. Mostrar resultados para toda la población elegible y para la lista realmente atendible tras aplicar prioridades de cobertura y deduplicación.

## Tickets de implementación

| Ticket | Trabajo | Evidencia para cerrarlo | Dependencia | Estado (2026-11-23) |
|---|---|---|---|---|
| M1-01 | Reproducir pesos, matriz y top diez de la versión actual | Informe con 360 casos y coincidencia de los controles | B0-01 | **Hecho.** `reproducir-referencia` coincide en todos los controles; artefacto `v1` con diferencia 0,0 frente a la fórmula original |
| M1-02 | Construir dataset de recompra y variables por grupos | Conteos de exclusión, fechas y prueba de invariancia ante futuro | B0-02 y M1-01 | **Hecho.** `modelos/variables.py`; conteos en `datos.json`; pruebas `FronterasTemporalesTests` |
| M1-03 | Ajustar candidatos y elegir política en validación | Configuración y comparación con las cuatro referencias | B0-03 y M1-02 | **Hecho.** Rejilla 3 × 3 en `seleccion.json`; elegido A, C = 10, umbral 0,40 |
| M1-04 | Evaluar calibración, ranking y errores comerciales | Tabla por mes y ejemplos de falsos positivos y omisiones | M1-03 | **Hecho.** `metricas_comprobacion_historica.json` y [ficha](../../modelo-compra.md) |
| M1-05 | Persistir y puntuar sin reentrenar | Recarga equivalente y fallo controlado de artefacto incompatible | B0-04 y M1-03 | **Hecho.** `ArtefactoTests` y `RegistroTests`; JSON frente a sklearn: 1,1 × 10⁻¹⁶ |
| M1-06 | Integrar versión activa en C1 y detalle C2 | Agenda y ficha concuerdan; corte anterior a disponibilidad se abstiene | B0-05 y M1-05 | **Hecho.** `predicciones_clientes` validada en C2; `IntegracionPaqueteTests` |
| M1-07 | Comparar en sombra y preparar piloto | Tiempo de preparación, cupo y resultados futuros pendientes o maduros | B0-07 y M1-06 | **Preparado.** Sombra `v2`, `comparar` sobre la cohorte original y `piloto_registro.csv`, que conserva el seguimiento humano entre actualizaciones; octubre queda como comprobación retrospectiva. Falta el piloto prospectivo desde el corte 2026-11-30 (madura el 2026-12-30), el tiempo de preparación de Ventas y los resultados maduros |

Rutas entregadas: `pipeline/modelo_compra.py` se conserva sin cambios como ruta de reproducción de la referencia. La implementación nueva está en `modelos/` en lugar de ampliar `pipeline/modelo_compra.py`: así el entrenamiento opcional queda separado del pipeline que usa el cierre. Se añaden `modelos/cli.py`, `modelos/config/compra_30d.json`, `requirements-modelos.txt` y `tests/modelos/test_compra_30d.py`, y `tests/modelos/test_modelo_compra.py` se mantiene.

## Pruebas necesarias

- Compra al corte: entra en variables y no en etiqueta. Compra al día 30: entra en etiqueta. Al día 31: queda fuera.
- Un cliente de alta posterior o sin historial no obtiene puntuación de recompra.
- Mover una venta futura cambia la etiqueta cuando corresponde y deja intactas las variables.
- Dos ventas el mismo día cuentan como dos operaciones y un solo día para intervalos.
- La media y el escalado permanecen iguales al modificar exclusivamente validación/prueba.
- Empates de probabilidad se resuelven por ID; todas las pantallas usan ese mismo orden dentro de la acción.
- La inferencia de octubre funciona cargando el artefacto, aunque la rutina de entrenamiento se deshabilite en esa ejecución.
- Se preservan las prioridades vigentes de C1 y los resultados humanos de tareas anteriores.

## Integración y salida

Publicar la probabilidad en `agenda.prob_compra_30d`, la versión y el umbral en `agenda.modelo`. En `predicciones_clientes`, `modelo_id = compra_30d`, añadir estado, horizonte 30, fecha del cálculo y motivos basados en variables observadas. No presentar coeficientes como causas del comportamiento.

En ficha y agenda mostrar fecha de corte y una explicación breve de las señales. Ante artefacto ausente o incompatible, usar probabilidad nula y el recorrido por reglas. Conservar el modelo actual como referencia experimental incluso si el ranking por recencia resulta preferible para el piloto.

## Criterios de aceptación

- [x] Reproducción histórica exacta dentro de la tolerancia numérica declarada (controles idénticos; artefacto `v1` con diferencia 0,0; tolerancia 10⁻⁹).
- [x] Ninguna etiqueta inmadura ni dato futuro entra en el ajuste (fronteras verificadas en `verificar_fronteras` y prueba de invariancia al modificar solo el periodo de comprobación).
- [ ] Meta inicial: precisión media mensual a diez al menos cinco puntos porcentuales superior al ranking por recencia, en la misma población y cupo. **No cumplida:** 0,567 frente a 0,567 (+0,0).
- [x] Revisar todo mes donde el candidato pierda dos o más compradores en los diez primeros; no compensarlo solo con una media global favorable (ningún mes: 5/7/5 frente a 5/7/5).
- [x] Brier no peor que el de la tasa fija de entrenamiento y calibración por bandas publicada con sus tamaños (0,2306 frente a 0,2541; bandas en la ficha).
- [x] Artefacto versionado, C1/C2 válidos y API sin dependencias de entrenamiento.

Resultado: **inconcluso**. Se mantiene `v1` como operativo y el orden contractual de C1; el candidato queda en sombra y la recencia es el comparador del piloto.

Los cinco puntos son una meta propuesta, no una mejora lograda. Con tres cortes, una comparación favorable solo habilita la prueba prospectiva. Si el candidato no supera la referencia, publicar el método de referencia identificado y dejar documentados variables, errores y decisión.

## Piloto y mantenimiento

Preparación hecha:

- Puntuación en sombra del corte 2026-10-31, una comprobación retrospectiva anterior a la congelación real con 120 etiquetas pendientes, porque el lote acaba el 2026-10-31.
- `comparar` a igual cupo (K = 10) sobre la cohorte puntuada.
- `piloto_registro.csv`, que separa columnas calculadas y humanas y conserva contacto, fecha, minutos y resultado en cada actualización.

Ejecución pendiente, sin resultados atribuibles todavía:

- Requiere autorización de Ventas.
- Requiere un lote con cobertura declarada hasta el 2026-11-30 para puntuar el primer corte prospectivo y otro hasta el 2026-12-30 o después para evaluarlo.
- Ventas debe registrar los contactos.

Registrar clientes elegibles, prioridad asignada, contacto realizado, tiempo invertido y compra posterior, sin convertir un contacto en etiqueta de compra. Comparar a igual cupo. Evaluar cuando transcurran los 30 días completos. Medir precisión y calibración por cierre y por clientes con distinta antigüedad. Una nueva versión necesita datos nuevos o un cambio explícito de objetivo, y se compara con la versión activa antes de sustituirla.
