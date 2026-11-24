# Planes de desarrollo y evaluación de modelos

Fecha de planificación: 23 de noviembre de 2026.

El objetivo es convertir el prototipo de JACOMIND en capacidades que ayuden a decidir a quién dar seguimiento, cuándo hacerlo, qué ofrecer y qué operaciones preparar o revisar. Este programa incluye la mejora del modelo de compra actual y cinco modelos adicionales. Cada entrega debe funcionar con los datos disponibles, compararse con una alternativa sencilla y conservar esa alternativa cuando el modelo no la supere.

M1 (compra a 30 días) quedó implementado el 23 de noviembre de 2026, con decisión «inconcluso» y el candidato en sombra (ver la [ficha](../../modelo-compra.md)). M2 (inactividad a 60 días) quedó implementado y evaluado el mismo día, con decisión «inconcluso»: mayor recencia sigue siendo mejor para el cupo (ver la [ficha](../../modelo-inactividad.md)). M2.1 (candidatos Poisson, supervivencia y logística reducida) mejoró a M2 (0,70 frente a 0,65; mejor Brier), pero también quedó «inconcluso» frente a mayor recencia (0,80). M3 (próxima compra) quedó implementado y evaluado: Cox reduce el Brier integrado un 10 % frente a Kaplan–Meier, pero no hay ventanas p10–p90 utilizables en 60 días; decisión «inconcluso», en sombra (ver la [ficha](../../modelo-proxima-compra.md)). M3.1 cambió la ventana a «inicio probable» (p10–p50) y añadió la probabilidad acumulada a 15/30/60 días: ventanas útiles para el 60 % de los casos y cobertura compatible con el 40 % nominal; sigue «inconcluso» por calibración y por la referencia personal. M3.2 probó un ajuste de nivel por corte: no mejoró en validación (la caída de compras llegó después de los meses maduros) y no se seleccionó; en la comprobación, solo como contexto, habría calibrado mejor a costa de ventanas más anchas. Queda para el piloto. M4 (venta cruzada) quedó implementado: reproduce el control 11/69 por familia y, por producto, el modelo acierta el primer producto el 13,3 % frente al 12,1 % de popularidad (IC incluye 0); decisión «inconcluso», se conserva popularidad filtrada en sombra y la revisión comercial está pendiente (ver la [ficha](../../modelo-venta-cruzada.md)). M4.1 (antigüedad y secuencias) tampoco mejora (11,7 %); el azar entre candidatos da 12,9–14,6 % y el techo por producto 16,25 %, así que en estos datos el valor está en restricciones y revisión comercial, no en el ranking. M5 (pronóstico de demanda) quedó implementado: reproduce A08 exactamente, concilia 88/88 meses-familia con A02 y decide por serie y horizonte (21 referencias conservadas, 14 inconclusos, 6 rechazados, 1 favorable exploratorio); 22 de 45 filas publicadas tienen banda empírica con cobertura comprobada (ver la [ficha](../../modelo-demanda.md)). M6 (operaciones atípicas) quedó implementado: 1.371 ventas confirmadas y 240 compras como universos separados, contexto por producto y moneda con historia estrictamente anterior al día, A02 reproducido (122 alertas) e Isolation Forest exportado a JSON con equivalencia exacta. En anomalías sembradas a igual cupo, el bosque detecta 81 % frente a 77 % de mediana/MAD en ventas (IC incluye 0) y 96 % frente a 89 % en compras (IC por encima de 0, pero 1 alerta en 67 controles negativos frente a 0). La regla predeclarada conserva la referencia en ambos universos; la cola queda en sombra con 0 revisiones humanas reales (ver la [ficha](../../modelo-anomalias.md)). M6.1 añadió la política de catálogo, la cantidad solo alta y el cupo como máximo con evidencia: en la comprobación (exploratoria, no independiente) las alertas sobre operaciones reales bajan de 14 a 1 en ventas y de 4 a 0 en compras, las alertas en normales construidas de 4,8 % a 1,4 % y de 23 % a 0 %, y la detección sembrada en ventas sube de 69 % a 86 % (compras 80 % en ambos). Isolation Forest no mejora a las reglas: se conservan. Amplían los [tickets de datos y modelos](../datos-y-modelos.md) y mantienen la aplicación actual de Python con biblioteca estándar, SQLite y publicaciones C1/C2. La arquitectura propuesta en documentos iniciales no implica una migración a FastAPI o PostgreSQL para ejecutar este programa.

## Planes por modelo

| Plan | Decisión que apoya | Punto de partida | Dependencia funcional |
|---|---|---|---|
| [M1 Compra a 30 días](01-compra-30-dias.md) | Priorizar clientes con probabilidad de recompra | Regresión logística reproducible, con ventaja comercial aún no demostrada | A01, A02 y A03 |
| [M2 Riesgo de inactividad](02-riesgo-inactividad.md) | Anticipar qué clientes activos pueden pasar a fríos | Regla de recencia en A06 | A01 y A03 |
| [M3 Próxima compra](03-proxima-compra.md) | Programar una ventana de seguimiento | Mediana y extremos de intervalos en A06 | A01 y A03 |
| [M4 Venta cruzada](04-venta-cruzada.md) | Elegir productos complementarios pertinentes | Coocurrencia que empata con popularidad en A07 | A01, A03 y catálogo disponible al corte |
| [M5 Pronóstico de demanda](05-pronostico-demanda.md) | Planificar ventas, adquisiciones y capacidad | Media móvil de A08 frente al último valor observado | A01 y A02 |
| [M6 Operaciones atípicas](06-operaciones-atipicas.md) | Concentrar la revisión de precios, cantidades y costos | Mediana y desviación absoluta mediana en A02 | A01 y A02 |

Todos usan la [base común de datos, evaluación e integración](00-base-comun.md). M2, M3, M4, M5 y M6 no necesitan que M1 obtenga una mejora para poder desarrollarse. La segmentación A05, el simulador TRM A09 y el clasificador PQRS A10 quedan fuera de estos seis planes.

## Evidencia de partida

El paquete sintético contiene 120 clientes, 10 productos de cuatro familias, 1.407 ventas —1.371 confirmadas—, 240 compras y 243 instalaciones. Cubre enero de 2025 a octubre de 2026. Hay 22 observaciones mensuales por serie completa, no miles de meses independientes. Los datos permiten verificar un prototipo; la evaluación comercial requiere un conjunto empresarial autorizado.

| Componente | Resultado de referencia | Implicación |
|---|---|---|
| Compra a 30 días | 360 observaciones de prueba; precisión 40,4 %, sensibilidad 90,9 % y F1 0,5594 | El umbral actual detecta muchos compradores y produce 177 falsos positivos |
| Orden comercial | Primeros diez por mes: modelo 13/30 aciertos; recencia 17/30 | Incluir la capacidad de seguimiento en la selección del método |
| Venta cruzada por familia | Coocurrencia y popularidad: 11/69 aciertos cada una | El nuevo ranking debe superar una referencia competitiva |
| Inactividad | Exploración: 1.444 observaciones elegibles y 278 eventos con la definición del plan | Recalcular conteos cuando se fijen reglas y particiones |
| Próxima compra | 1.251 intervalos entre días de compra | Los intervalos pertenecen a 120 clientes y están correlacionados |

La auditoría local del 22 de noviembre generó `salida/auditoria_modelos_2026_11_22/resultados.json`; esa carpeta no se versiona. Las referencias persistentes son el [modelo de compra](../../modelo-compra.md), la [ficha del pipeline](../../ficha-modelo.md), el código y los valores controlados del paquete. Los nuevos experimentos deben conservar sus propios resultados reproducibles.

## Orden de ejecución

1. Completar la base común: datos publicados, tiempo observable, particiones, artefactos y contratos.
2. Desarrollar M1 y M2 para comparar la agenda actual con recompra y prevención de inactividad. M5 puede avanzar en cuanto estén conciliadas las series.
3. Desarrollar M4 con las restricciones del catálogo y el registro de resultados comerciales.
4. Desarrollar M3, que exige tratar correctamente los periodos sin compra observada.
5. Completar M6 y su conjunto de anomalías revisadas. Puede adelantarse si Operaciones dispone de revisores.
6. Integrar únicamente los candidatos que pasen sus criterios técnicos. Ejecutar en modo sombra antes de cambiar prioridades o generar tareas.

En modo sombra se calculan resultados y se comparan con el proceso vigente, sin modificar las decisiones que reciben los usuarios.

## Responsables y esfuerzo estimado

Se mantienen los roles del proyecto: A prepara datos, entrena y evalúa; B mantiene contratos, publicación, API, interfaz y eventos. Ventas revisa pertinencia comercial, Operaciones verifica calidad y Finanzas define unidades y uso de las proyecciones. Los roles no asignan una persona concreta ni crean agentes de trabajo.

| Entrega | Jornadas persona combinadas de A y B | Resultado |
|---|---:|---|
| Base común | 5–8 | Flujo reproducible de experimentos y publicación |
| M1 Compra | 4–6 | Comparación del ranking y artefacto congelado |
| M2 Inactividad | 4–6 | Riesgo entre clientes activos y alertas deduplicadas |
| M3 Próxima compra | 6–9 | Ventanas con censura y cobertura verificadas |
| M4 Venta cruzada | 5–7 | Ranking filtrado por elegibilidad de producto |
| M5 Demanda | 4–6 | Proyecciones con errores por horizonte y unidad |
| M6 Anomalías | 4–6 | Cola de revisión con carga controlada |
| Total | 32–48 | Seis capacidades evaluadas e integradas según resultados |

Son estimaciones iniciales para reutilizar el proyecto actual, incluyendo pruebas e integración descritas. No incluyen espera de datos, correcciones extensas en fuentes empresariales, despliegue de infraestructura ni el tiempo necesario para observar resultados del piloto. Dos personas a tiempo completo no eliminan las dependencias ni la espera de etiquetas de 30 o 60 días.

## Hitos de entrega

| Hito | Evidencia requerida | Resultado si no se cumple |
|---|---|---|
| Datos utilizables | Conteos conciliados, claves válidas, fechas de disponibilidad y cobertura temporal | Corregir o abstenerse en el grupo afectado |
| Modelo reproducible | Mismos datos, configuración y versión producen puntuaciones equivalentes | Resolver diferencias antes de integrar |
| Comparación favorable | Mejora sobre la referencia en la métrica principal y controles del plan | Conservar la referencia; registrar el experimento |
| Integración correcta | Contrato válido, permisos, ausencia de tareas duplicadas y lectura sin dependencias de entrenamiento | Mantener resultado solo en experimentación |
| Piloto útil | Datos nuevos, tiempo de trabajo medido y resultados de seguimiento con denominadores | Continuar en sombra o ajustar el proceso |

Los umbrales numéricos de cada plan son metas iniciales de ingeniería, no resultados obtenidos ni políticas aprobadas por Green. Deben fijarse en la configuración antes de evaluar candidatos. La mejora en datos sintéticos habilita una prueba del flujo, no una afirmación de aumento de ventas.

## Primera tanda de trabajo

- [x] B0-01 a B0-03: construir el dataset temporal y congelar el protocolo. Hecho para 30 días (M1) y para 60 días (M2, [`inactividad_60d.json`](../../../modelos/config/inactividad_60d.json)); M4 reutilizará el calendario de 60 días.
- [x] B0-04 y B0-05: guardar artefactos y preparar contratos con ejemplos mínimos. Hecho para `compra_30d` y `predicciones_clientes`, y para las tablas de M4 (`recomendaciones_productos`, `cobertura_recomendaciones`), M5 (`pronosticos_demanda`, `calendario_demanda`) y M6 (`anomalias_operaciones`, `cobertura_anomalias`).
- [x] M1-01: reproducir la referencia y verificar etiquetas (controles idénticos; ver la [ficha](../../modelo-compra.md)).
- [x] M2-01: reproducir la referencia de inactividad y verificar etiquetas (casos de frontera en `tests/modelos/test_inactividad.py`; ver la [ficha](../../modelo-inactividad.md)).
- [x] M5-01: conciliar calendarios, monedas y unidades (88/88 meses-familia con A02; ver la [ficha](../../modelo-demanda.md)).
- [x] M6-01 a M6-06: errores A01 separados, variables contextuales, casos sembrados, selección en validación, comprobación y cola persistida (ver la [ficha](../../modelo-anomalias.md)). M6-07 (carga y utilidad del piloto) espera revisiones reales.
- [ ] Registrar el estado de cada ticket con enlace al cambio, evidencia y decisión; las casillas se marcan cuando exista esa evidencia.
