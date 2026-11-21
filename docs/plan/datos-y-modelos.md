# Tareas de A | Datos, aprendizaje automático y evaluación

[Volver al plan integral y al orden de integración](../../PLAN_IMPLEMENTACION.md)

Cada ticket se puede desarrollar con sus propias muestras. Las dependencias indicadas son las necesarias para **aceptarlo con datos integrados**. Mantener las transformaciones de entrenamiento e inferencia en el mismo código y guardar los resultados por cierre. En todas las comparaciones, indicar cuántos clientes o periodos sustentan la métrica.

### A01 · Importar, validar y actualizar datos mensualmente

**Entrada y salida.** Parte del diccionario y de los siete CSV principales. Entrega a A02 tablas normalizadas, inventario del lote y registro de filas aisladas. B01 puede avanzar con archivos equivalentes ficticios.

1. Definir adaptadores CSV y XLSX que reciban ruta, tipo de tabla, hoja si aplica y mapeo explícito de columnas. Preservar IDs como texto. Normalizar BOM, fechas ISO o fechas nativas de Excel y decimales según el formato declarado. Para otra fuente autorizada, implementar el mismo contrato y conservar el identificador original y la fecha de extracción.
2. Validar columnas, tipos, claves primarias, referencias, estados de venta, descuentos, cantidades, monedas y tasas. Cargar primero catálogos, después hechos. Registrar por incidencia archivo, fila, campo, motivo y acción. Separar errores que impiden publicar (p. ej., falta la tabla de ventas) de filas aislables. Un lote parcial requiere revisión visible antes de publicación.
3. Conservar la huella del archivo y la clave de negocio. Un reenvío idéntico reutiliza el lote. Una corrección con el mismo ID y distintos valores crea revisión trazable y recalcula los cierres afectados. Un fallo de lectura mantiene la última versión publicada.

**Probar.** Importar la misma venta desde CSV y XLSX y comparar sus campos. Repetir con una hoja equivocada, fecha ambigua, ID con ceros iniciales y referencia desconocida. Procesar aparte el CSV opcional con siete incidencias sembradas, incluido el ID duplicado. Verificar cada motivo contra `05_Validacion/Incidencias_esperadas.md`.

**Evaluar y aceptar.** Conciliar filas leídas con aceptadas, duplicadas idénticas y aisladas, contabilizando cada fila una vez aunque tenga varios motivos. Reimportar el lote y comprobar conteos e importes invariantes. Entregar comando de carga, esquema y registro de incidencias.

### A02 · Calcular ventas, compras, TRM y anomalías

**Depende de A01.** Entrega hechos monetarios y agregados por mes, familia, moneda y proveedor para la ficha, Gerencia y el informe.

1. Reutilizar la lógica de `ejemplo_operaciones.py`. Para ventas confirmadas calcular cantidad × precio × (1 − descuento/100). Para compras, cantidad × costo unitario. Conservar importe y moneda de origen, tasa utilizada e importe COP. Usar aritmética decimal y documentar en qué nivel se redondea. Validar el cierre contra el paquete con su misma política de redondeo.
2. Convertir USD con la tasa de su fecha. Aislar la operación si falta. Mantener ventas y compras en tablas de hechos independientes y agregar cada una antes de combinar por mes/familia. Separar conteo de operaciones, unidades e importe.
3. Identificar variaciones atípicas de precio o volumen dentro de la misma familia y moneda mediante mediana y desviación absoluta mediana de periodos anteriores. Para grupos pequeños o dispersión cero, aplicar un control determinista documentado o devolver «historia insuficiente». Conservar la operación y mostrar por qué merece revisión.

**Probar.** Verificar 180.000 COP para 2 unidades a 100.000 con 10 % de descuento y 1.200.000 COP para 3 unidades a USD 100 con tasa 4.000. Una anulada aporta cero. Dos compras y tres ventas del mismo producto conservan sus cinco operaciones originales. Inyectar un pico en volumen y probar también un aumento de gasto explicado únicamente por TRM.

**Evaluar y aceptar.** Octubre debe conciliar con 1.371 ventas confirmadas y 5.647.449.456,36 COP acumulados al corte. Para anomalías usar casos sembrados y una muestra revisada de operaciones normales. Reportar detecciones, omisiones y alertas por cada 100 operaciones. Acordar con Operaciones el volumen revisable antes de activar alertas.

### A03 · Construir ficha 360°, recurrencia y coberturas

**Depende de A02.** Entrega una fila por cliente y cierre para C1 y el detalle comercial para C2.

1. Incluir clientes con alta anterior o igual al corte. Agregar ventas por cliente y producto, con fechas, cantidades y COP. Calcular recencia en días, frecuencia de operaciones, valor monetario, intervalos entre días distintos de compra y primera/última compra. Preservar clientes sin ventas con totales cero y fechas ausentes.
2. Calcular etiquetas independientes con parámetros versionados. En la referencia, «frecuente» desde ocho operaciones y «frío» desde 90 días sin comprar. «Nuevo» usará antigüedad desde el alta con una ventana acordada con Ventas. Distinguir siempre alta reciente de ausencia de compras.
3. Incorporar instalaciones iniciadas al corte. Clasificar por fecha fin en vigente, próxima (entre 0 y 45 días inclusive) o vencida. Una instalación próxima puede seguir vigente. Conservar ID y producto para revisar renovaciones ya registradas. Incorporar histórico y coberturas a la ficha sin multiplicar importes.

**Probar.** Casos con 7/8 ventas, 89/90 días, fin ayer/hoy/en 45/en 46 días, alta futura, dos ventas el mismo día y un cliente frecuente que también está frío. Agregar dos coberturas al mismo cliente mantiene su ingreso. Agregar una compra a proveedor nunca aumenta la frecuencia del cliente.

**Evaluar y aceptar.** Con el paquete original obtener 120 IDs únicos y 41 fríos en octubre. Conciliar una ficha con las ventas y otra con las instalaciones originales. En la prueba de cliente sin historial, distinguir `null` de cero. Pasar C1 antes de integrar B03.

### A04 · Entrenar y puntuar compra a 30 días

**Depende de A02 y A03.** Entrega probabilidad, versión, umbral y ficha del modelo. La puntuación de octubre es una nueva inferencia.

1. Reproducir `04_Codigo/modelo_compra.py`. Crear fotografías mensuales por cliente elegible. Usar solo ventas confirmadas conocidas al cierre para recencia, frecuencias a 30/90 días y total histórico. Etiquetar 1 si hay compra en los 30 días siguientes. Excluir del aprendizaje cortes sin horizonte observable.
2. Ajustar escalado y regresión logística con cortes de marzo de 2025 a abril de 2026. Elegir el umbral en mayo–junio de 2026. Evaluar en julio–septiembre y comparar con «compró en los últimos 30 días». Congelar transformaciones, pesos y umbral. Si se experimenta después de conocer esta prueba publicada, usar un periodo nuevo para confirmar cualquier mejora.
3. En inferencia aplicar la transformación guardada a la misma fecha de cierre que la ficha. Con historial insuficiente o modelo no disponible en esa fecha usar probabilidad nula y motivo documentado. Informar por separado resultados de todos los elegibles de la referencia y del subconjunto con compra previa que verá una estimación de recompra.

**Probar.** Una venta al cierre entra como variable. Una venta al día siguiente puede cambiar la etiqueta y deja intactas las variables. Una venta al día 31 queda fuera de la etiqueta. Verificar que el normalizador solo usa entrenamiento y que las etiquetas de un bloque maduran antes de la primera inferencia del siguiente.

**Evaluar y aceptar.** Reproducir las 360 observaciones históricas y la matriz TP/TN/FP/FN de 120/51/177/12 frente a 73/161/67/59 para la regla. El modelo recupera más compras y también asigna más seguimientos improductivos. Reportar precisión, sensibilidad, F1, calibración por bandas y precisión entre los primeros K de **cada mes**. Como control adicional, al ordenar el CSV de referencia por probabilidad descendente e ID ascendente, hay 5, 4 y 4 compradores entre los primeros 10 en julio, agosto y septiembre. Este control mide propensión de compra, no efecto causal del contacto. Elegir el método operativo según el costo y la capacidad de Ventas.

### A05 · Segmentar clientes con clustering

**Depende de A03.** Entrega segmento por cliente, descripción del grupo, tamaño y versión. B03/B05 pueden usar segmentos ficticios hasta integrarlo.

1. Preparar recencia, frecuencia, importe, recurrencia y composición por familia en una ventana común. Separar clientes sin historial y registrar cobertura. Transformar importes sesgados, escalar las variables con el periodo de ajuste y evitar incluir el ID como señal.
2. Usar agrupación por RFM como referencia interpretable. Comparar K-means con varios números pequeños de grupos, semillas fijas y suficientes clientes por grupo. Describir centroides en unidades de negocio y ejemplos anonimizados. Mantener una correspondencia de segmentos entre versiones para que un cambio de ID interno no cambie la etiqueta comercial.
3. Ventas revisa los perfiles y asigna una acción a cada grupo. «Potencial» requiere una definición y evidencia acordadas. Si dos grupos conducen a la misma acción, probar una partición más simple.

**Probar.** Duplicar artificialmente la escala del importe y reaplicar el escalado. Reordenar filas y repetir con la misma semilla. Incluir un cliente aislado de valor extremo y otro sin ventas. Comparar las asignaciones admitiendo permutación de nombres de grupo.

**Evaluar y aceptar.** Registrar silueta, tamaño mínimo, estabilidad entre semillas y entre cierres sobre los clientes comunes (índice de Rand ajustado), junto con las acciones que Ventas distingue. Publicar la segmentación que tenga grupos utilizables y documentar las razones para conservar RFM si el clustering no añade valor.

### A06 · Estimar riesgo de inactividad y próxima ventana de compra

**Depende de A03.** Dos estimaciones con etiquetas distintas, cada una con población, horizonte y criterio de abstención.

1. **Riesgo.** Entre clientes activos con compras previas al corte, definir como ejemplo de entrenamiento «alcanzará 90 días sin comprar en los próximos 60 días». Reconstruir día a día el primer cruce antes de una nueva compra, acordar con Ventas el tratamiento del día de empate y exigir 60 días futuros observables. Comparar regresión con una regla basada en la recencia. Ocultar esta puntuación para quienes ya están fríos.
2. **Próxima compra.** Empezar con la mediana de intervalos del cliente o, si escasea el historial, de clientes comparables. Estimar una ventana usando cuantiles de intervalos y señalar el origen. Cuando haya suficiente historia, comparar un modelo de tiempo hasta evento que trate los casos aún sin compra como censurados. Separar fechas de cobertura de fechas estimadas.
3. Publicar motivos entendibles, tamaño del historial, ventana y fecha de cálculo. Si el intervalo ya venció, mostrar «revisar estimación vencida» o abstenerse. Registrar proporción de clientes con estimación utilizable.

**Probar.** Simular una compra antes del cruce de 90 días, otra después del cruce, un cliente ya frío y un corte reciente sin futuro observable. Para intervalos [20, 30, 40] días, comprobar la mediana de 30. Probar una sola compra, dos compras el mismo día y falta de siguiente evento.

**Evaluar y aceptar.** Para riesgo, comparar precisión/sensibilidad y aciertos en los K seguimientos disponibles contra recencia. Para próxima compra, comparar error absoluto mediano en días entre los eventos observados, cobertura de la ventana, anchura y proporción sin evento observado. Desglosar por producto recurrente y único. Si la ventana resulta demasiado amplia para organizar la agenda, mantener solo el recordatorio verificable.

### A07 · Recomendar renovaciones, reactivación y venta cruzada

**Depende de A03 y A04.** A05 y A06 enriquecen motivos cuando están disponibles. Entrega oportunidades con cliente, producto, tipo, evidencia, fecha y versión de la regla.

1. Generar renovaciones desde las coberturas próximas y revisar si hay una cobertura posterior relacionada. Generar reactivaciones desde recencia y riesgo. Mantener aparte las oportunidades de clientes con alta propensión a comprar. Cuando falte trazabilidad para decidir si ya se renovó, generar tarea de comprobación.
2. Para venta cruzada, construir combinaciones de familias adquiridas por cliente usando solo transacciones previas al corte. Comparar con recomendar la familia popular. Excluir productos ya cubiertos o incompatibles, exigir soporte mínimo configurable y registrar soporte y justificación de cada sugerencia.
3. Definir con Operaciones la precedencia entre motivos, ordenar de forma estable y emitir un ID persistente por oportunidad/episodio. Abrir una sola tarea por episodio y conservar los demás motivos. El equipo comercial acepta, pospone o descarta en B05.

**Probar.** Una cobertura nueva sobre el mismo servicio suprime o envía a revisión la renovación anterior. Un cliente frío con renovación conserva ambos motivos. Una familia vista por primera vez después del corte nunca participa en el entrenamiento anterior. Una sugerencia incompatible debe quedar excluida aunque sea popular.

**Evaluar y aceptar.** Ventas revisa una muestra por tipo y marca pertinente, ya atendida o incorrecta. Para venta cruzada comparar aciertos en las primeras K sugerencias con las familias realmente compradas después, cobertura de catálogo y resultados frente a popularidad. Para renovación medir seguimientos válidos por cobertura próxima. En el piloto usar los resultados de B05 para medir atención y conversión.

### A08 · Detectar tendencias y pronosticar ventas y compras

**Depende de A02.** Entrega series y proyecciones por mes y familia, con unidad, horizonte y errores.

1. Construir calendario continuo y series separadas de ingresos por ventas en COP, compras a proveedores en COP y unidades. Distinguir mes completo con cero actividad de mes con ingestión incompleta. Calcular cambios absolutos y porcentuales respecto del mes anterior. Con denominador cero, mostrar solo el cambio absoluto.
2. Comparar el último mes observado y una media móvil con un modelo de suavizamiento exponencial sencillo. Usar ventanas de evaluación de origen creciente: entrenar hasta un mes, pronosticar el siguiente y desplazar el origen. Para proyecciones a dos o tres meses evaluar cada horizonte por separado. Ajustar alternativas con cortes anteriores y reservar los últimos meses para comprobación final.
3. Mostrar histórico, proyección y bandas empíricas solo cuando haya suficientes errores históricos. En familias con muchos ceros, mostrar cobertura y agregar a un nivel con señal suficiente. Con 22 meses disponibles, justificar cualquier estacionalidad anual con evidencia adicional.

**Probar.** Usar series constante, creciente, intermitente y con mes ausente. Inyectar un pico futuro y comprobar que el pronóstico de un origen anterior no cambia. Verificar sumas por familia y señalar explícitamente si el total publicado se obtiene sumando las proyecciones de las familias.

**Evaluar y aceptar.** Reportar MAE en COP o unidades, error ponderado absoluto cuando la suma observada sea positiva, sesgo y tabla predicho/observado por origen. Entregar una vista de los mayores cambios de volumen con sus familias. Publicar el método con error y sesgo aceptables frente al ingenuo, indicando dónde el histórico resulta insuficiente.

### A09 · Simular exposición cambiaria y efecto sobre costos

**Depende de A02.** Entrega a B09 un cálculo parametrizado con universo y moneda visibles.

1. Seleccionar compras en USD del periodo y dejar fijos cantidad y costo unitario en USD. Aplicar a la TRM de cada operación el cambio porcentual elegido. Mantener el componente COP. Calcular costo base, costo de escenario y diferencia por familia y proveedor.
2. Permitir escenarios de ejemplo −8 %, 0 % y +8 %. Registrar alcance, periodo, tasas y supuesto de precio de venta fijo. Para estimar margen se necesitan costos atribuibles, unidades vendidas vinculadas, política de inventario y definición de Finanzas. Mientras falten, publicar sensibilidad del costo de adquisición. Con esos insumos, comparar margen base y simulado sobre la misma cesta vendida.

**Probar.** Con USD 300 a 4.000 y +8 %, el costo pasa de 1.200.000 a 1.296.000 COP y aumenta 96.000. Un componente COP se mantiene. Probar tasa faltante, escenario 0 %, moneda no cubierta y base sin exposición USD.

**Evaluar y aceptar.** Finanzas debe reproducir una familia a mano. Conciliar la suma de contribuciones con el cambio total y verificar que las simulaciones preservan las cifras históricas. La vista debe indicar qué costos entran en el cálculo y qué datos faltan para habilitar margen.

### A10 · Clasificar PQRS con revisión humana

**Depende del contrato C3 de B04.** A puede desarrollar con texto sintético rotulado. Aceptar un modelo para el piloto requiere casos autorizados y etiquetas revisadas.

1. Acordar con Atención ejemplos de petición, queja, reclamo y sugerencia, además de criterios de ambigüedad. Hacer que dos revisores etiqueten una muestra, resolver desacuerdos y versionar el conjunto. Retirar identificadores innecesarios antes del entrenamiento.
2. Comparar categoría mayoritaria y reglas de palabras con TF-IDF y regresión logística multiclase. Separar entrenamiento y prueba por caso/conversación y por fecha. Mantener duplicados o variantes del mismo caso en el mismo bloque. Ajustar en validación un umbral de confianza que derive textos dudosos a revisión manual.
3. Entregar a B10 etiqueta sugerida, versión, confianza y motivo para revisión. Guardar la etiqueta corregida por el agente como observación posterior. Medir cobertura automática y volumen que queda al equipo.

**Probar.** Caso vacío, texto con dos intenciones, vocabulario desconocido, caso duplicado, clase minoritaria y confianza baja. Una corrección humana persiste después de ejecutar nuevamente el clasificador.

**Evaluar y aceptar.** Reportar macro-F1, precisión/sensibilidad por categoría, matriz de confusión y tasa de revisión. Comparar con reglas sobre los mismos casos, revisar los errores que asignan un responsable equivocado y acordar tolerancia con Atención. Con muestras exclusivamente sintéticas, aceptar la integración y mantener la clasificación del piloto bajo revisión.

### A11 · Medir salud del modelo e impacto del seguimiento

**Depende de A04 y B05.** Extender los controles a cada modelo publicado. Entrega un reporte repetible por cierre y la decisión de conservar o sustituir la versión operativa.

1. Registrar versión de datos, variables, fecha máxima observada, cohorte objetivo, modelo y umbral. En cada cierre comparar cobertura, nulos, distribución de recencia y puntuaciones con las del ajuste. Una vez maduren las etiquetas, calcular rendimiento y calibración por mes y segmento.
2. Para el piloto acordar periodo, cupo de contactos, métrica principal y comparador. Registrar oportunidades asignadas, atendidas y motivos de descarte. Para estimar impacto incremental, asignar aleatoriamente clientes elegibles a seguimiento habitual o asistido si Green lo autoriza. Mantener la asignación por cliente. En una comparación observacional documentar sesgos.
3. Medir tiempo empleado en preparar el cierre, fracción de oportunidades atendidas, recuperación de fríos y compras dentro del horizonte. Definir denominadores de antemano. Ante degradación, probar el candidato en paralelo, comparar con la versión vigente y recuperar la anterior si es necesario.

**Probar.** Simular mes nuevo sin etiqueta madura, caída abrupta de cobertura y resultado tardío de un seguimiento. Un dato ausente debe producir «pendiente». Repetir el cálculo de cohortes conserva los denominadores.

**Evaluar y aceptar.** Entregar por modelo comparación con su referencia, tamaño muestral y decisión documentada. Para negocio, informar diferencia entre grupos con incertidumbre y tiempo observado. Separar una mejora en el modelo, una mejora del flujo de trabajo y una mejora comercial demostrada.
