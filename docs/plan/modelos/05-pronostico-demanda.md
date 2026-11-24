# Plan del modelo de pronóstico de demanda

[Programa](README.md) · [Base común](00-base-comun.md)

## Objetivo y decisión

Prever actividad comercial a uno, dos y tres meses para apoyar compras, presupuesto y preparación operativa. Publicar cada proyección con su unidad, horizonte, referencia y error histórico. La planificación de personal o inventario necesita además tiempos de servicio, existencias y plazos de entrega, que no están en el paquete actual.

Responsable técnico: A. Integración: B. Usuarios de evaluación: Operaciones y Finanzas. Esfuerzo estimado: 4–6 jornadas persona.

## Estado y alcance inicial

**Implementado el 23 de noviembre de 2026, en sombra.** Las referencias se conservan casi en todo; decisión por serie y horizonte. Resultados, integración y piloto en la [ficha del modelo](../../modelo-demanda.md).

[`pipeline/pronostico.py`](../../../pipeline/pronostico.py) ya implementa último valor, media móvil y evaluación por origen creciente. [`pipeline/generar.py`](../../../pipeline/generar.py) publica proyecciones COP y bandas de más/menos un MAE. Esas bandas describen el error medio; no son intervalos de confianza con una cobertura garantizada.

El paquete solo aporta 22 meses. El primer candidato es suavizamiento exponencial simple; comparar también Holt con tendencia amortiguada y sin estacionalidad anual. Los métodos de suavizamiento permiten ajustar nivel y tendencia para producir pronósticos. [Ejemplos oficiales de statsmodels](https://www.statsmodels.org/stable/examples/notebooks/generated/exponential_smoothing.html).

## Series y unidades

| Serie | Agregación | Uso y condición |
|---|---|---|
| Ingreso por ventas COP | Mes y familia; total como suma de familias | Presupuesto comercial, no margen contable |
| Unidades vendidas | Mes y producto | Demanda física/comercial del mismo producto |
| Compras a proveedores COP | Mes y familia, separadas de ventas | Referencia de desembolsos de adquisición, no demanda de clientes |
| Unidades por familia | Solo si los productos comparten una unidad de medida comparable | Requiere definición empresarial; no sumar servicios heterogéneos como capacidad de trabajo |

Empezar con ingresos por las cuatro familias. Añadir unidades por producto cuando existan suficientes meses completos y actividad. `cantidad` no contiene una unidad de medida documentada; no interpretar cinco servicios distintos como cinco horas equivalentes. Mantener esa limitación junto a cualquier suma de cantidades.

Construir calendario continuo desde el primer mes con cobertura fiable. Cero significa actividad observada igual a cero. Un mes incompleto es nulo con indicador de cobertura y no se imputa como cero. No incluir meses anteriores al alta o disponibilidad de un producto como ausencia de demanda conocida. Importes USD se convierten operación por operación a la TRM observada; las proyecciones COP reflejan también cambios históricos de moneda y precios, no solo volumen.

No proyectar TRM futura con este modelo. Los escenarios cambiarios de A09 siguen siendo cálculos separados. No emparejar compras y ventas para derivar costos de lo vendido o margen sin trazabilidad de inventario.

## Entrenamiento y referencias

Para cada serie comparar último mes y media móvil de tres meses con suavizamiento exponencial simple. Añadir Holt amortiguado solo si hay historia suficiente y mejora en validación. Fijar ese conjunto de alternativas antes de evaluar; evitar búsquedas grandes de órdenes o estacionalidades sobre 22 puntos.

Requisitos iniciales: al menos seis meses completos para referencias y doce para candidatos aprendidos. Si faltan, abstenerse del candidato y publicar la referencia disponible con su estado. Una serie toda cero puede producir referencia cero; una serie con huecos de ingestión no se trata como toda cero. Si hay demanda intermitente, evaluar la referencia y la cobertura antes de añadir otro algoritmo en un experimento posterior.

Elegir el método por serie y horizonte con errores anteriores a la prueba. Las comparaciones entre métodos usan los mismos orígenes, aunque una referencia pueda pronosticar antes. Volver a estimar parámetros con la historia disponible en cada origen de prueba es válido si el procedimiento de ajuste y la familia del modelo ya están fijados. No volver a seleccionar el método usando resultados futuros de esos orígenes.

## Evaluación por origen creciente

Desarrollo: enero de 2025–junio de 2026. Construir orígenes de desarrollo con al menos doce meses de historia para comparar candidatos y utilizar solo objetivos que terminen a más tardar el 30 de junio. El número de comparaciones será pequeño y debe publicarse; los errores adicionales de las referencias con seis meses sirven para diagnóstico, no para dar al candidato un universo distinto.

Comprobación histórica de objetivos julio–octubre de 2026:

| Horizonte | Orígenes con objetivo observable | Número máximo de errores por serie |
|---|---|---:|
| Un mes | Junio, julio, agosto y septiembre | 4 |
| Dos meses | Junio, julio y agosto | 3 |
| Tres meses | Junio y julio | 2 |

Cada origen usa únicamente meses completos hasta él. Un pronóstico a tres meses desde agosto necesita noviembre y queda pendiente con el paquete actual. Las proyecciones emitidas desde octubre son inferencia nueva; no tienen error observado todavía.

Métrica principal: MAE por serie y horizonte, en COP o unidades. Complementar con WAPE cuando la suma de valores observados sea positiva, sesgo y tabla predicho/observado. En unidades heterogéneas no sumar errores entre productos como si fueran intercambiables; presentar cada serie y comparar mejoras relativas. En COP se puede agregar el error con ponderación explícita.

El total publicado es la suma de proyecciones de las familias. Evaluar ese mismo total sumado frente al total real; un modelo total directo puede quedar como comparador, pero no sustituirlo silenciosamente. Las bandas se calculan a partir de errores de predicción fuera de ajuste y anteriores al origen, por horizonte. Con menos de doce errores comparables, dejar bandas nulas por historia insuficiente. El paquete probablemente no permita bandas para varios candidatos; no usar errores dentro del ajuste ni juntar horizontes para llenarlas. Una banda empírica se etiqueta con su método y cobertura comprobada, no como garantía.

## Tickets de implementación

| Ticket | Trabajo | Evidencia de cierre | Dependencia |
|---|---|---|---|
| M5-01 | Calendarizar y conciliar series, monedas y unidades | Sumatorias contra A02, ceros separados de meses incompletos | B0-01 |
| M5-02 | Implementar ajuste e inferencia de candidatos | Casos constante, tendencia y falta de historia | M5-01 |
| M5-03 | Evaluar por origen, serie y horizonte | Predicciones y errores con los límites temporales indicados | B0-03 y M5-02 |
| M5-04 | Seleccionar referencia/candidato y bandas | Decisión por serie, soporte y procedimiento congelado | M5-03 |
| M5-05 | Persistir y publicar tabla específica | Unidades, horizontes y claves validadas | B0-04, B0-05 y M5-04 |
| M5-06 | Integrar panel e informe, y seguimiento mensual | Histórico y futuro diferenciados; resultados pendientes de madurez | B0-07 y M5-05 |

Rutas propuestas: ampliar `pipeline/pronostico.py`, añadir `modelos/demanda.py`, ampliar `tests/modelos/test_modelos_restantes.py` o crear `test_demanda.py`, y adaptar `api/finanzas.py` y `app/vistas/tableros.js` al contrato acordado.

## Pruebas necesarias

- Serie constante mantiene nivel; una tendencia produce valores finitos y no negativos después de aplicar la política de salida.
- Si se recortan predicciones negativas a cero, evaluar exactamente ese resultado publicado y registrar el recorte.
- Mes observado sin actividad = cero; mes no recibido = nulo; el ajuste no confunde ambos.
- Añadir un pico posterior al origen no modifica la predicción ya emitida.
- Horizonte dos o tres se evalúa contra el mes correcto, no contra el siguiente mes inmediato.
- Suma de familias coincide con total publicado; el total histórico concilia con A02.
- WAPE queda no disponible cuando el denominador es cero.
- Series COP y unidades no colisionan en la clave ni comparten una banda con distinta unidad.
- Bandas ausentes no se pintan como ceros y no se inventan usando el MAE como confianza probabilística.

## Integración y salida

Publicar `pronosticos_demanda` con origen, `serie_id`, familia/producto cuando aplique, medida, unidad, horizonte, periodo objetivo, valor, método, estado, versión, MAE de evaluación, número de evaluaciones y banda opcional. Ejemplos de serie: `ventas_cop:Software` y `ventas_unidades:PRO01`.

Conservar `series_mensuales` para sus consumidores actuales. Los pronósticos COP pueden adaptarse a ese formato sin cambiar su significado; las unidades tienen identidad explícita en la nueva tabla. El panel muestra fecha de corte, método y error de la misma serie/horizonte. El informe no presenta una proyección como ingreso ya realizado. El cierre activo contiene la versión seleccionada de cada serie; las variantes candidatas permanecen en experimentos.

## Criterios de aceptación

- [ ] Calendario y totales conciliados; moneda, medida y mes completo explícitos.
- [ ] Meta inicial: reducción de al menos 10 % del MAE frente a la mejor referencia elegida en validación, para promover un candidato en una serie/horizonte.
- [ ] Sesgo absoluto normalizado no mayor al 15 % cuando el volumen observado sea positivo; revisar por separado series pequeñas o todas cero.
- [ ] Selección y parámetros reproducibles; publicar referencias donde ganen.
- [ ] Horizonte con menos de tres errores se marca como evidencia insuficiente para afirmar superioridad estable; puede mostrarse como experimental.
- [ ] No se publican bandas con soporte insuficiente ni sumas de unidades incompatibles.

Los porcentajes son metas iniciales. Con cuatro errores a un mes y dos a tres meses, el resultado histórico solo guía el piloto. Un candidato puede aceptarse para una familia y rechazarse para otra.

## Piloto y mantenimiento

En cada cierre guardar pronósticos antes de observar el mes objetivo. Incorporar el dato real cuando el periodo esté completo y calcular el error sin sobrescribir el pronóstico original. Medir tiempo de preparación y decisiones de adquisición apoyadas. Comparar faltantes, exceso o utilización de capacidad solo si se incorporan sus datos operativos; no inferir esas mejoras a partir de ventas pronosticadas.
