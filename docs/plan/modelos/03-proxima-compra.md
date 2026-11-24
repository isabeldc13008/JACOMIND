# Plan del modelo de próxima compra

[Programa](README.md) · [Base común](00-base-comun.md)

## Objetivo y decisión

Estimar una ventana útil para el siguiente seguimiento comercial. En cada cierre se calcula el tiempo restante hasta la próxima compra confirmada de un cliente con historial. El producto debe diferenciar una fecha contractual de cobertura de una fecha estimada por comportamiento.

Responsable técnico: A. Integración: B. Usuario de evaluación: Ventas. Esfuerzo estimado: 6–9 jornadas persona. El modelo necesita más trabajo metodológico que una clasificación porque algunos clientes no vuelven a comprar durante la observación.

## Estado y enfoque

**Implementado el 23 de noviembre de 2026, con decisión «inconcluso».** Resultados, integración y piloto en la [ficha del modelo](../../modelo-proxima-compra.md).

[`pipeline/riesgo.py`](../../../pipeline/riesgo.py) calcula mediana, mínimo y máximo de intervalos. Esos extremos no son un intervalo de confianza. Hay 1.251 intervalos observados entre días de compra en el paquete, pertenecientes a 120 clientes; los periodos finales sin una nueva compra también aportan información y deben conservarse.

Usar un diseño de fotografías mensuales: el origen del tiempo es el corte C, no la última compra. Se predice el tiempo residual `proxima_compra - C`, incorporando recencia como variable. Así se evita sumar un intervalo histórico completo a un cliente que ya lleva parte de ese intervalo esperando.

## Dataset y censura

Una fila contiene cliente, corte, variables conocidas en C, duración observada y un indicador de compra observada. Sea D la fecha hasta la cual había información completa al ajustar o evaluar y H=60 días el horizonte inicial:

- `fin_seguimiento = min(C + H, D)`.
- Si existe compra posterior a C y hasta ese fin, duración = días hasta la primera compra e indicador = 1.
- Si no existe, duración = días hasta el fin e indicador = 0: observación censurada.
- Excluir filas con seguimiento de cero días; conservar las censuradas con seguimiento positivo.

En entrenamiento, D debe ser la fecha de disponibilidad del ajuste, no el final de todo el paquete. Una compra que se conocerá después no transforma retrospectivamente una fila censurada de ese ajuste en un evento conocido.

Elegibles: clientes con compras confirmadas previas. Para interpretar el modelo, separar comportamiento recurrente, ocasional y clientes fríos en el reporte. No inferir abandono definitivo a partir de la falta de una siguiente compra.

Variables iniciales: recencia, días distintos de compra a 90/180 días, frecuencia, mediana y dispersión de intervalos previos, importe reciente y composición recurrente/única. Limitar el número de variables y comprobar que todas se construyen antes del corte. Una sola compra permite usar referencia poblacional, con origen explícito; no permite una mediana personal.

## Referencias y candidato

1. Mediana personal de intervalos, cuando existen al menos dos intervalos positivos. El tiempo restante se obtiene restando recencia. Un resultado no positivo produce `estimacion_vencida`, sin desplazarlo arbitrariamente al futuro.
2. Curva de Kaplan–Meier de tiempos residuales del grupo de entrenamiento, con censura y un grupo global cuando los subgrupos tienen pocos eventos.
3. Candidato: Cox con regularización, ajustado sobre las fotografías y variables de origen. Probar pocas intensidades de penalización y revisar estabilidad de coeficientes y sensibilidad entre periodos.

La curva entrega la probabilidad de seguir sin compra y, cuando se alcanzan dentro del horizonte, cuantiles del tiempo restante. Mostrar p10, p50 y p90. Si p90 no se alcanza en 60 días, conservarlo nulo y señalar que el límite superior supera el horizonte estimable. No sustituirlo por el día 60 como si fuera un cuantil calculado. Si la mediana tampoco se alcanza, no publicar una fecha central inventada.

Las observaciones de un mismo cliente están relacionadas. No usar los errores estándar ordinarios de filas independientes como evidencia de estabilidad. Comparar mediante remuestreo por cliente y resultados por origen. La implementación puede limitarse a las curvas poblacionales si el modelo Cox no obtiene una mejora suficiente.

## Partición y evaluación

Protocolo inicial: fotografías de entrenamiento marzo de 2025–febrero de 2026, con seguimiento conocido hasta el 30 de abril y máximo 60 días por fila. Validar sobre orígenes 30 de abril y 31 de mayo con seguimiento hasta 60 días después. Elegir configuración cuando esas observaciones maduren, el 30 de julio. Comprobar sobre 31 de julio y 31 de agosto con seguimiento máximo hasta el 30 de octubre. No reentrenar con eventos de prueba.

Métrica principal: Brier integrado hasta 60 días, ajustado por censura, frente a Kaplan–Meier. Usar tiempos estrictamente dentro del soporte del seguimiento y donde la distribución de censura de entrenamiento permita ponderar. Si no existe soporte suficiente, reducir el horizonte declarado o dejar la métrica no disponible; no eliminar silenciosamente los casos difíciles.

Reportar además concordancia ajustada por censura, cobertura de estimaciones, proporción censurada, error absoluto mediano en días entre eventos observados y ancho de ventanas. Ese error entre eventos es una medida condicionada a observar compra y no describe a todos los clientes. Para la ventana p10–p90, publicar cobertura entre eventos con seguimiento completo y su denominador; cuando haya censura antes de sus límites, usar evaluación compatible con censura o declarar cobertura no estimable. [Evaluación de supervivencia](https://scikit-survival.readthedocs.io/en/stable/user_guide/evaluating-survival-models.html).

## Tickets de implementación

| Ticket | Trabajo | Evidencia de cierre | Dependencia |
|---|---|---|---|
| M3-01 | Construir fotografías y seguimiento censurado | Tabla de episodios con evento, duración y fecha disponible | B0-02 |
| M3-02 | Implementar referencias personal y poblacional | Ejemplos con historia suficiente, escasa y estimación vencida | M3-01 |
| M3-03 | Ajustar Cox y cuantiles dentro de soporte | Curvas válidas, penalización y límites documentados | B0-03 y M3-02 |
| M3-04 | Evaluar con censura y agrupación por cliente | Métricas, cobertura y errores por corte y tipo de producto | M3-03 |
| M3-05 | Persistir modelo y publicar ventana C2 | Misma predicción tras recarga; nulos fuera de soporte | B0-04, B0-05 y M3-04 |
| M3-06 | Integrar calendario y recordatorios en sombra | Fecha contractual y estimada distinguidas; tareas sin duplicados | B0-07 y M3-05 |

Rutas propuestas: `modelos/proxima_compra.py`, ampliación de `pipeline/riesgo.py`, `tests/modelos/test_proxima_compra.py` y lectura en la ficha interna y seguimientos. Las dependencias de supervivencia se ejecutan en el proceso analítico opcional.

## Pruebas necesarias

- Intervalos [20,30,40] producen mediana histórica 30; con recencia 10, referencia residual 20.
- Recencia mayor que la mediana produce estimación vencida, no una fecha futura automática.
- Compras el mismo día se consolidan para intervalos; la compra al corte no se considera el siguiente evento.
- Una última observación sin compra queda censurada y participa en el ajuste.
- Agregar una compra posterior al D de entrenamiento no cambia aquel dataset ni su artefacto.
- Las curvas empiezan en probabilidad de supervivencia 1, no aumentan con el tiempo y permanecen en [0,1].
- Cuantiles ordenados cuando existen; cuantiles no alcanzados quedan nulos con motivo.
- Casos sin eventos, con una sola compra o seguimiento insuficiente activan la referencia o abstención correspondiente.
- La ventana estimada nunca reemplaza ni altera el fin de una cobertura registrada.

## Integración y salida

En `predicciones_clientes`, `modelo_id = proxima_compra`, publicar `horizonte_dias`, `dias_p10`, `dias_p50`, `dias_p90`, fechas equivalentes cuando existan, `ventana_utilizable`, `origen_estimacion`, `estado` y motivos. Una ventana utilizable exige límites existentes y ancho compatible con el trabajo comercial.

La ficha muestra «ventana estimada» y la fecha de cálculo. Si el límite superior excede el horizonte, mostrar esa condición sin crear un recordatorio de día exacto. Los recordatorios se generan solo con una política activada y un episodio estable. Una compra posterior cierra el episodio; las tareas registradas siguen conservando sus resultados.

## Criterios de aceptación

- [ ] No se pierden observaciones censuradas ni se utilizan eventos desconocidos en el ajuste.
- [ ] Meta inicial: reducir al menos 5 % el Brier integrado frente a la curva poblacional en los orígenes evaluados, con soporte válido.
- [ ] El error mediano entre eventos no empeora frente a la referencia personal en el subconjunto común.
- [ ] Meta de utilidad: ventanas con ancho no mayor a 30 días para al menos 50 % de los elegibles; publicar tamaño y cobertura real, sin forzar cuantiles para cumplirla.
- [ ] La cobertura nominal de 80 % de p10–p90 se contrasta con incertidumbre y censura; con pocos casos, declarar el resultado inconcluso.
- [ ] Nulos, fechas vencidas y origen poblacional se muestran correctamente en aplicación y asistente.

Estas metas se fijan antes de validar y se pueden sustituir por el ancho de agenda acordado con Ventas. Si las ventanas son demasiado amplias, conservar la referencia explicable o la probabilidad por horizonte en modo sombra.

## Piloto y mantenimiento

Medir seguimientos realizados dentro de la ventana, tiempo de gestión, compras observadas y eventos fuera de la ventana. La precisión de la fecha se evalúa después de madurar el seguimiento. Revisar cambios en periodicidad de productos y distribución de censura. No eliminar clientes sin compra al evaluar una nueva versión: hacerlo favorecería artificialmente las estimaciones.
