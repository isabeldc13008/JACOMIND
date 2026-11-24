# M1.1 · Línea experimental de compra a 30 días

Referencia vigente: [modelo de compra M1](modelo-compra.md) · Protocolo: [`modelos/config/compra_30d_m11.json`](../modelos/config/compra_30d_m11.json) (`m1.1-protocolo-v1`) · Código: [`modelos/compra_m11.py`](../modelos/compra_m11.py), [`modelos/boosting.py`](../modelos/boosting.py) · Señales comerciales: [inventario y contrato](plan/modelos/m1.1-senales-comerciales.md)

## Conclusión

**Ningún candidato M1.1 mejora las referencias.** Decisión pre‑declarada: **inconcluso** (no rechazado). Comparación en la población elegible, primeros diez por mes:

- **Seleccionado** (logística L2 con variables de ciclo, C = 0,1, sin calibrar): 16/30 compradores.
- **Recencia:** 17/30. Diferencia −3,3 puntos; IC 95 % por remuestreo de clientes de −20,0 a +16,7 puntos.
- **M1 v2 congelado:** 17/30.

El candidato no cumple la meta de +5 puntos ni la de log loss no peor que M1 v2. Sí cumple Brier no peor que la constante y no tiene meses con dos o más compradores perdidos.

`v1` sigue operativa y `v2` en sombra. Ningún candidato M1.1 se registra ni se promueve; quedan como resultados experimentales en `salida/experimentos/compra_30d_m11/ejecucion-001/`. Son datos sintéticos y un periodo (julio–septiembre de 2026) ya inspeccionado: los resultados son exploratorios y no demuestran mejora comercial.

## Protocolo (fijado antes de ajustar)

- **Objetivo, población y horizonte:** los mismos que M1 (recompra, compra confirmada en `(corte, corte + 30]`).
- **Variables:** versión `compra_30d-variables-v2`, que añade a v1 las nuevas; las definiciones v1 no cambian y los artefactos M1 se resuelven con ellas.
- **Desarrollo:** cortes 2025‑03‑31 a 2026‑06‑30. **Comprobación histórica:** julio–septiembre de 2026, reservada hasta congelar.
- **Validación temporal por origen creciente:**
  - 10 orígenes, del 2025‑09‑30 al 2026‑06‑30.
  - Cada origen `d` se predice con un modelo entrenado solo con cortes `t` tales que `t + 30 <= d`. Por ejemplo, el 31‑01‑2026 no entrena el origen del 28‑02.
  - Los clientes de un mismo corte van siempre juntos.
  - Las transformaciones (imputación y escalado) se reajustan dentro de cada partición.
- **Entrenamiento final:** los 16 cortes del desarrollo, cuyas etiquetas maduran a más tardar el 2026‑07‑30, antes del primer corte de comprobación.
- **Familias y rejilla fija:**
  - Logística L2 con C ∈ {0,1; 1; 10}.
  - Gradient boosting con profundidad 2, árboles ∈ {50, 150}, tasa 0,05 y hoja mínima ∈ {20, 60}, sin parada temprana ni partición aleatoria interna.
  - Ambas sobre tres combinaciones incrementales (base M1 + ciclo, base + cambio, base + ciclo + cambio): 21 configuraciones.
  - Además, un **control**: la especificación de M1 (4 variables, C = 10) reentrenada con este esquema, para separar el efecto de más datos del de las variables nuevas.
- **Selección:**
  - Población elegible y cupo K = 10.
  - Precisión media a 10 sobre los 10 orígenes, es decir, 100 plazas por especificación.
  - Desempates: AP, log loss, menos variables, logística antes que boosting y menor complejidad.
- **Calibración sigmoidal (Platt) sobre el puntaje bruto:**
  - Se aprende solo de predicciones fuera de muestra de la validación temporal.
  - Se evalúa en los seis últimos orígenes con calibradores entrenados en orígenes anteriores ya maduros.
  - Soporte mínimo: 300 filas, 50 positivos, 50 negativos y 4 cortes.
  - Se calibra solo si mejora el log loss de desarrollo.
  - Nunca se usa la comprobación histórica.
- **Umbral comercial:** 0,40 sin cambios. La política por cupo se informa aparte.
- **Metas** (las mismas de M1 más una de calidad probabilística):
  - +5 puntos de precisión a 10 frente a recencia en la población elegible.
  - Ningún mes con dos o más compradores perdidos.
  - Brier no peor que la constante.
  - Log loss no peor que M1 v2.
- **Semilla:** 20261123. Entorno en `entorno.json`.

## Variables

| Grupo | Variables | Hipótesis | Mínimo de historia | Estado |
|---|---|---|---|---|
| Base M1 | `recencia_dias`, `frecuencia_30d`, `frecuencia_90d`, `historial_n` | Actividad reciente | 1 compra | En todas las combinaciones |
| Ciclo individual | `ratio_recencia_ciclo` (recencia ÷ intervalo mediano), `desfase_ciclo_dias` (recencia − intervalo; asinh), `cv_intervalos` (MAD ÷ mediana), `ciclo_insuficiente` | Un cliente regular compra cuando se cumple su ciclo | 3 días de compra distintos | Implementadas y evaluadas |
| Cambio de comportamiento | `ritmo_90_vs_previo` = log((f90+1)/(f90‑180+1)), `cambio_intervalo_rel` = log((último+1)/(mediana previa+1)), `operaciones_por_dia`, `cambio_insuficiente` | Aceleración o freno del ritmo; sin divisiones inestables (suavizado +1) | 4 días distintos para el cambio de intervalo | Implementadas y evaluadas |
| Producto y vigencia | `dias_desde_recurrente`, `margen_vigencia_dias`, `sin_recurrente`, `ciclo_x_recurrente` | Cercanía al fin de vigencia de lo comprado | 1 compra recurrente | **Implementadas, excluidas**: dependen de tipo y vigencia del catálogo, cuya disponibilidad histórica no puede demostrarse (`productos.csv` no tiene fechas) |
| Coberturas de `base_instalada` | — | — | — | **Descartadas**: tabla de estado actual; `fecha_fin` puede incluir renovaciones registradas después del corte |
| Señales comerciales (cotizaciones, oportunidades, solicitudes) | — | — | — | **Pendientes de datos**: no existen fuentes con historia ([inventario](plan/modelos/m1.1-senales-comerciales.md)) |

Por debajo del mínimo, la variable queda nula y se imputa con la mediana de entrenamiento; su indicador vale 1. No se inventan ciclos. Dos ventas del mismo día cuentan como dos operaciones y un día de compra. No se usa el ID de cliente ni se entrenan modelos por segmentos.

## Validación temporal (desarrollo, 10 orígenes)

| Especificación | Precisión media a 10 | AP media | Log loss | Brier |
|---|---:|---:|---:|---:|
| **logística · base + ciclo · C = 0,1 (seleccionada)** | **0,580** (58/100) | 0,547 | 0,6924 | 0,2495 |
| logística · base + ciclo · C = 1 | 0,570 | 0,545 | 0,6941 | 0,2502 |
| control M1 reentrenado | 0,560 | 0,552 | 0,6940 | 0,2503 |
| logística · base + ciclo + cambio · C = 0,1 | 0,550 | 0,543 | 0,6944 | 0,2503 |
| **boosting · base + ciclo · 50 árboles · hoja 20 (mejor de su familia)** | 0,540 | 0,537 | 0,6940 | 0,2503 |
| logística · base + cambio (mejor C) | 0,500 | 0,533 | 0,6954 | 0,2509 |
| boosting · otras 11 configuraciones | 0,39–0,53 | 0,51–0,53 | 0,697–0,714 | 0,252–0,260 |

Las diferencias en desarrollo son de pocas plazas de 100 y las observaciones son 120 clientes repetidos, no miles de clientes independientes. El grupo de cambio no aporta, y el boosting con más árboles empeora la probabilidad (sobreajuste).

## Calibración (con y sin)

| Modelo | Desarrollo: log loss sin → con | Brier sin → con | Prob. media sin → con (observada 0,470) | ¿Calibrar? | Comprobación: Brier sin / con | Log loss sin / con |
|---|---|---|---|---|---|---|
| Seleccionado (logística, ciclo) | 0,6935 → 0,6935 | 0,2501 → 0,2502 | 0,503 → 0,519 | No (no mejora) | **0,2346** / 0,2376 | **0,6620** / 0,6683 |
| Boosting (mejor) | 0,6978 → 0,6982 | 0,2521 → 0,2525 | 0,510 → 0,520 | No | **0,2334** / 0,2348 | **0,6590** / 0,6621 |
| Control M1 reentrenado | 0,6947 → 0,6947 (−0,00002) | 0,2507 → 0,2508 | 0,511 → 0,523 | Sí, por regla estricta, con mejora despreciable | **0,2244** / 0,2323 | **0,6408** / 0,6575 |

El soporte de calibración es de 1.146 filas, 562 positivos y 10 cortes. Se usó Platt sobre el puntaje bruto con a > 0, que conserva el orden: el top 10 es idéntico con y sin calibrar.

En la comprobación la calibración empeora la probabilidad. La tasa de compra de desarrollo (≈ 47 %) es mayor que la de julio–septiembre (36,7 %), y un calibrador aprendido en el pasado no corrige un cambio de nivel posterior. La probabilidad media del seleccionado baja de 46,8 % (M1 v2) a 43,6 %, lo que acerca la estimación a la frecuencia observada sin igualarla.

## Comprobación histórica (exploratoria, julio–septiembre de 2026)

Población: 360 fotografías de 120 clientes, con 132 compradores (47, 47 y 38 por mes). Población atendible tras las prioridades de C1: 69 fotografías (26, 23 y 20). Orden: puntaje descendente, desempate por `cliente_id`; denominador `min(K, n)`.

| Método | Elegible top 10 (jul/ago/sep) | Elegible top 20 | AP media | Atendible top 10 | Atendible top 20 | Brier | Log loss | Prob. media |
|---|---|---:|---:|---|---:|---:|---:|---:|
| **M1.1 seleccionado** (logística ciclo) | 5/6/5 = **16/30** | 28/60 | 0,444 | 6/3/4 = 13/30 | 31 | 0,2346 | 0,6620 | 0,436 |
| M1.1 mejor boosting | 6/6/3 = 15/30 | 28/60 | 0,472 | 5/5/4 = 14/30 | 34 | 0,2334 | 0,6590 | 0,426 |
| Control M1 reentrenado | 4/7/5 = 16/30 | 29/60 | 0,515 | 7/3/6 = 16/30 | 34 | **0,2244** | **0,6408** | 0,437 |
| M1 v2 congelado | 5/7/5 = **17/30** | 30/60 | 0,521 | 7/3/6 = 16/30 | 34 | 0,2306 | 0,6540 | 0,468 |
| v1 congelada | 5/4/4 = 13/30 | 30/60 | 0,475 | 7/3/5 = 15/30 | 32 | 0,2316 | 0,6557 | 0,450 |
| Recencia | 5/7/5 = **17/30** | **34/60** | **0,541** | 8/5/6 = **19/30** | 35 | — | — | — |
| Regla compra 30 días | 7/6/3 = 16/30 | 29/60 | 0,523 | 7/5/6 = 18/30 | 34 | — | — | — |
| Constante (tasa de entrenamiento 0,498) | 5/5/4 = 14/30 | 25/60 | 0,409 | 7/5/6 = 18/30 | 35 | 0,2494 | 0,6919 | 0,498 |

En la población atendible, el empate por ID de la constante coincide por azar con buenos resultados; no tiene contenido predictivo.

Lectura:

1. Las variables de ciclo mejoran ligeramente la selección en desarrollo, pero no se trasladan a la comprobación (16 frente a 17).
2. El boosting no supera a la logística.
3. El control (M1 con más datos) ofrece la mejor calidad probabilística, con un Brier 0,0062 menor que M1 v2, sin mejorar el ranking: más historia ayuda a la probabilidad, no al orden.
4. En la población atendible, recencia sigue siendo la mejor (19/30).

### Criterios de aceptación (seleccionado)

| Meta | Resultado | Estado |
|---|---|---|
| +5 puntos de precisión a 10 frente a recencia (elegible) | 0,533 frente a 0,567 (−3,3 puntos; IC bootstrap −20 a +17) | No cumple |
| Ningún mes con dos o más compradores perdidos frente a recencia | Pierde 1 en agosto | Cumple |
| Brier no peor que la constante | 0,2346 frente a 0,2494 | Cumple |
| Log loss no peor que M1 v2 | 0,6620 frente a 0,6540 | No cumple |
| Decisión | — | **Inconcluso** (no llega al margen de rechazo de −5 puntos) |

### Política por cupo (experimento separado; no cambia el umbral)

Con el umbral comercial de 0,40, el seleccionado marca como candidatos 90, 89 y 87 de 120 clientes por mes, con 40, 39 y 30 compradores entre ellos. Un cupo fijo de 10 por mes reduce la carga a 10 contactos, con 5, 6 y 5 compradores. Es una **reducción de carga**, no una mejora predictiva: la precisión del cupo (53 %) frente a la tasa base (37 %) refleja el ranking, que no supera a recencia.

## Artefactos, inferencia y reproducción

- Ejecución `salida/experimentos/compra_30d_m11/ejecucion-001/`:
  - Configuración y congelación: `config.json`, `protocolo.json` (huella guardada antes de ajustar), `congelacion.json` (huellas de protocolo, artefactos, referencias y datos, sello y fechas).
  - Selección: `seleccion.json` (21 configuraciones + control por origen, y la calibración).
  - Artefactos: `artefacto_{global,mejor_logistica,mejor_boosting,control}_{sin_calibrar,calibrado}.json` y `artefacto.json` (el seleccionado).
  - Referencias: `referencia_v1_congelada.json` y `referencia_m1_v2_congelado.json` (copias de solo lectura del registro).
  - Resultados: `metricas_comprobacion_historica.json`, `decision.json`, `predicciones_validacion_temporal.csv`.
  - Entorno: `entorno.json`, `datos.json`.
- Formatos:
  - `jacomind.regresion_logistica.v1`, con `calibracion` opcional.
  - `jacomind.gradient_boosting.v1`: JSON numérico, sin pickle. Se validan estructura y referencias de nodos (hacia delante, sin ciclos ni padres dobles), profundidad ≤ 6, ≤ 1000 árboles, índices de variables, valores finitos, `a > 0` de la calibración y huella.
  - La inferencia es de biblioteca estándar y compara en float32, como scikit-learn. La equivalencia con scikit-learn es ≤ 2,2 × 10⁻¹⁶ con y sin calibración (tolerancia 10⁻⁹).
- Compatibilidad: el cierre puntúa cualquier artefacto válido del registro con sus propias variables (`version_variables`). Una prueba publica un cierre con un boosting en un registro aislado, con scikit-learn y numpy bloqueados. Los artefactos M1 conservan sus huellas y la congelación de `ejecucion-002` sigue verificando.

```powershell
pip install -r requirements-modelos.txt
python -m modelos.cli m11-entrenar --datos salida/a01 --config modelos/config/compra_30d_m11.json --salida salida/experimentos/compra_30d_m11/ejecucion-002
python -m modelos.cli m11-evaluar --ejecucion salida/experimentos/compra_30d_m11/ejecucion-002
# Puntuar un artefacto experimental sin registrarlo (octubre: retrospectivo)
python -m modelos.cli puntuar --artefacto salida/experimentos/compra_30d_m11/ejecucion-001/artefacto.json --datos salida/a01 --corte 2026-10-31 --salida salida/puntuaciones/2026-10-31/m11
python -m modelos.cli comparar --operativo salida/puntuaciones/2026-10-31/operativo --sombra salida/puntuaciones/2026-10-31/m11 --datos salida/a01 --salida salida/puntuaciones/2026-10-31/comparacion-m11
```

## Condiciones para una prueba prospectiva

- Congelación real de M1.1: 2026‑11‑23. Primer corte prospectivo: 2026‑11‑30, que madura el 2026‑12‑30 (`congelacion.json → fechas`).
- Datos necesarios: un lote A01 con cobertura declarada hasta el 2026‑11‑30 para puntuar y otro hasta el 2026‑12‑30 o después para evaluar. Con tres cortes mensuales (36 plazas a K = 10), una diferencia de 1–2 compradores no es concluyente; hacen falta varios meses o una cartera mayor.
- Antes de reemplazar `v1` o `v2`: datos empresariales posteriores a la congelación, una evaluación con protocolo nuevo y una autorización con `aprobado_por`.
- Señales comerciales: integrarlas exige el contrato de datos `senales_comerciales` y una versión de variables nueva.

## Integridad y recuperación (24-11-2026)

La ejecución histórica de esta variante es de **formato 2**: sigue legible con verificación parcial declarada (lo que su sello no protege, p. ej. la evidencia de desarrollo, figura en `verificacion.no_verificable`), pero no puede volver a evaluarse ni promoverse con `promover`. Las ejecuciones nuevas usan el **formato 3** (congelación y evaluación selladas, archivos obligatorios, coherencia candidato–artefacto–decisión y recuperación de interrupciones). La reproducción en carpeta nueva dio artefactos, métricas y decisión **idénticos**: la corrección no cambia el resultado predictivo ni la decisión. Detalle: [monitoreo e integridad](monitoreo-modelos.md#a-integridad-y-recuperación-de-m11-m12-y-m13).
