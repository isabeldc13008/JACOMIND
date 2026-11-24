# Plan del modelo de riesgo de inactividad

[Programa](README.md) · [Base común](00-base-comun.md)

## Objetivo y decisión

Identificar clientes que aún están activos pero alcanzarán 90 días sin compra durante los próximos 60 días. Ventas puede revisar esos clientes antes de que se conviertan en fríos. El objetivo mide una pausa comercial observable; no equivale a cancelación de contrato ni a abandono definitivo.

Responsable técnico: A. Integración: B. Usuario de evaluación: Ventas y Operaciones. Esfuerzo estimado: 4–6 jornadas persona.

## Estado y población

**Implementado el 23 de noviembre de 2026, con decisión «inconcluso».** Resultados, comandos, integración y piloto en la [ficha del modelo](../../modelo-inactividad.md).

[`pipeline/riesgo.py`](../../../pipeline/riesgo.py) devuelve actualmente una condición basada en recencia y horizonte. No contiene una probabilidad aprendida ni evalúa si una compra futura evitaría el cruce. La nueva versión conservará esa regla como referencia.

Unidad: cliente y cierre mensual. Elegibles: alta anterior o igual al corte, al menos una compra confirmada y recencia menor de 90 días. Clientes ya fríos reciben `no_elegible` con motivo `ya_frio`; clientes sin compras reciben `sin_historial`. Ninguno obtiene riesgo cero para representar su exclusión.

La exploración del paquete produjo 1.444 observaciones y 278 cruces con horizonte observable. Son conteos anteriores a la partición final, no tamaño del conjunto de prueba. Recalcularlos con la versión de etiqueta y registrar cuántos clientes únicos y eventos hay en cada bloque.

## Definición de la etiqueta

Convención inicial: una compra confirmada realizada el mismo día en que se cumplirían 90 días evita el cruce de ese día. Se usa el estado al finalizar el día. Ventas puede cambiar la convención antes de congelar el protocolo.

Para un corte C, última compra L y fin E=C+60:

1. Ordenar los días distintos de compras confirmadas en `(C,E]`.
2. Calcular el siguiente día de cruce como `L+90`.
3. Si ese día cae dentro del horizonte y es anterior a la próxima compra, etiquetar 1 y guardar la fecha del primer cruce.
4. Si la compra ocurre antes o el mismo día del cruce, actualizar L y continuar.
5. Si no se observa cruce y el horizonte está completo, etiquetar 0. Si falta futuro, dejar pendiente.

Una compra después de haberse cruzado el umbral no borra el evento: la pregunta es si llegó a estar frío dentro del horizonte. No convertir la etiqueta en «no compró en 60 días», porque son objetivos distintos.

Ejemplo de frontera: con C=31 de julio de 2026 y L=2 de junio, el cruce sería el 31 de agosto. Comprar el 30 o el 31 de agosto lo evita; comprar el 1 de septiembre no lo evita. Para recencia menor de 30 días al corte, no es posible llegar a 90 dentro de 60 días; aplicar riesgo estructural cero para este evento y conservar esos casos en la cobertura reportada. El aprendizaje se concentra en recencias de 30 a 89 días.

## Variables y modelos

Variables iniciales: recencia, frecuencia a 30/90/180 días, cambio de frecuencia, días distintos de compra, mediana y dispersión de intervalos, relación recencia/intervalo habitual y participación de familias recurrentes. Añadir importe a 90 días para describir actividad, sin confundir riesgo con valor del cliente.

No usar «frío futuro», siguiente compra ni ventas posteriores al corte. Las coberturas se añaden solo cuando se pueda reconstruir su disponibilidad. El valor comercial puede servir como desempate después del riesgo si Ventas fija esa política; no se incluye implícitamente como recompensa de entrenamiento.

Referencias: regla actual `recencia + 60 >= 90` y orden por mayor recencia. Candidato principal: regresión logística L2. Probar una rejilla pequeña fijada de regularización. Comparar opcionalmente un árbol de profundidad máxima tres cuando existan suficientes positivos en cada bloque. Si entrenamiento o validación contienen una sola clase en la población aprendible, no ajustar el candidato y publicar la referencia con el motivo.

## Evaluación temporal

Usar el protocolo de 60 días: ajuste marzo de 2025–febrero de 2026, validación abril/mayo y comprobación histórica julio/agosto. Congelar pesos, transformaciones y política después de validar. No añadir septiembre como prueba sin datos completos hasta el 29 de noviembre.

Métrica principal: precisión entre los diez clientes de mayor riesgo de cada corte. Secundarias: sensibilidad a ese cupo, PR-AUC, Brier, calibración y cobertura. Comparar con mayor recencia sobre exactamente los mismos clientes aprendibles, e informar también cobertura sobre todos los activos. Si un corte tiene menos de diez clientes, usar su tamaño real.

Contar y mostrar los eventos que la regla consideraba evitables, los detectados y las falsas alarmas. Los porcentajes sin suficientes eventos se marcan como descriptivos. Estimar incertidumbre por cliente y no tratar las fotografías mensuales como clientes independientes.

## Tickets de implementación

| Ticket | Trabajo | Evidencia de cierre | Dependencia |
|---|---|---|---|
| M2-01 | Implementar elegibilidad y reconstrucción del primer cruce | Casos antes, durante y después del umbral con fechas esperadas | B0-02 |
| M2-02 | Construir variables y separar riesgo estructural de aprendido | Conteos por población y revisión de un cliente completo | M2-01 |
| M2-03 | Entrenar y comparar referencias | Métricas por corte, clases y configuración congelada | B0-03 y M2-02 |
| M2-04 | Persistir y explicar puntuaciones | Artefacto recargable y motivos con datos del corte | B0-04 y M2-03 |
| M2-05 | Publicar C2 y vista interna de prevención | Riesgo separado de compra, clientes fríos excluidos y permisos | B0-05 y M2-04 |
| M2-06 | Registrar episodios de prevención y evaluación | Repetir un cierre no duplica tareas ni borra resultados | B0-07 y M2-05 |

Rutas propuestas: ampliar `pipeline/riesgo.py`, añadir `modelos/inactividad.py` y `tests/modelos/test_inactividad.py`; ampliar `api/consultas.py`, `api/tareas.py` y la ficha interna al integrar.

## Pruebas necesarias

- Recencias 29, 30, 89 y 90 días: riesgo estructural, frontera aprendible y exclusión correctos.
- Compra antes del cruce, exactamente el mismo día y al día siguiente según la convención descrita.
- Cruce al día 60 incluido y al día 61 excluido.
- Compra posterior al cruce conserva etiqueta positiva.
- Horizonte incompleto mantiene etiqueta pendiente aunque todavía no haya compras.
- Cliente sin historial y cliente ya frío no reciben probabilidad cero por ausencia de elegibilidad.
- Probabilidad dentro de [0,1], nulos con motivo y clasificación de riesgo diferenciada de recompra.
- Una compra que cierre el episodio permite crear otro episodio únicamente cuando vuelva a cumplir la política; el cambio de modelo no crea otro por sí solo.

## Integración y salida

En `predicciones_clientes` publicar `modelo_id = inactividad_60d`, `probabilidad`, `horizonte_dias = 60`, `umbral_frio_dias = 90`, `estado`, recencia y motivos. Conservar `prob_compra_30d` sin cambios.

Durante el piloto en sombra, la ficha interna muestra el resultado sin cambiar la precedencia C1. Una lista interna de prevención puede usar el ranking y crear tareas de `comprobacion`, con evidencia que identifique el motivo de prevención, tras activar esa política. Evitar duplicar una tarea de cobertura existente: mantener ambos motivos en el mismo seguimiento cuando corresponda. No mostrar este riesgo en el portal externo.

## Criterios de aceptación

- [x] Las etiquetas cumplen todos los casos de cruce y madurez.
- [ ] Meta inicial: mejorar al menos cinco puntos porcentuales la precisión media a diez respecto de mayor recencia, a igual población. **No cumplida:** −15 puntos (0,65 frente a 0,80), con IC 95 % [−0,25; +0,10].
- [ ] La sensibilidad al mismo cupo no disminuye en el conjunto evaluado; publicar los resultados por mes. **No cumplida:** 0,371 frente a 0,457; resultados por mes publicados.
- [x] Brier no peor que la tasa de entrenamiento de la población aprendible, con diagnóstico de calibración (0,235 frente a 0,254; el IC incluye 0).
- [x] Se informa la proporción de activos cubiertos, estructurales, excluidos y sin modelo.
- [x] La lista y las tareas conservan permisos, episodios y resultados humanos (tareas automáticas desactivadas por defecto).

Si no se alcanza la mejora o hay muy pocos eventos, mantener la regla o declarar el experimento inconcluso. Pasar los controles sintéticos habilita el piloto, no prueba retención real.

## Piloto y mantenimiento

Registrar revisión, contacto, causa comercial identificada, compra posterior y primer cruce de 90 días. Medir alertas pertinentes, tiempo de gestión y eventos a 60 días. Los clientes ya fríos se evalúan en reactivación, fuera de este objetivo. Revisar cambios de la política de inactividad y de periodicidad de productos antes de reutilizar etiquetas históricas. Un cambio de 90 a otro umbral requiere una etiqueta y versión nuevas.
