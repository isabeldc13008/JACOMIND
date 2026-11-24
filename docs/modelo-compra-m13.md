# M1.3 · Tiempo hasta la próxima compra (S) y ponderación temporal con ajuste de nivel (P)

Protocolo: [`modelos/config/compra_30d_m13.json`](../modelos/config/compra_30d_m13.json) (`m1.3-protocolo-v1`, guardado antes de calcular resultados) · Código: [`modelos/compra_m13.py`](../modelos/compra_m13.py), [`modelos/supervivencia.py`](../modelos/supervivencia.py) · Ejecución: `salida/experimentos/compra_30d_m13/ejecucion-001/`

## Candidatos (sin búsqueda de hiperparámetros)

- **S · supervivencia de intervalos.** Probabilidad de que el intervalo abierto (recencia `r`) termine en los próximos 30 días: `p = 1 − S(r+30)/S(r)`.
  - `S` mezcla los intervalos completos del cliente con la curva de Kaplan–Meier de toda la cartera, con contracción `k = 5`. Los intervalos abiertos entran como censurados.
  - Más allá del último tiempo observado se usa una cola exponencial.
  - No usa etiquetas: en cada origen solo ventas con fecha ≤ origen.
  - Artefacto `jacomind.supervivencia.v1` (curva congelada en JSON) con variables `compra_30d-intervalos-v1`.
- **P · ponderación temporal + ajuste de nivel.** Especificación M1 (4 variables, C = 10):
  - pesos por corte con semivida de 180 días;
  - desplazamiento del intercepto para alinear el nivel con la tasa del último corte maduro, guardado como `calibracion {a: 1, b}`, que conserva el orden.
  - Se informa además la descomposición (solo pesos, solo nivel) y el control (M1 reentrenado sin cambios).

**Criterio principal:** la validación temporal de desarrollo (10 orígenes, 100 plazas):
- **S** busca mejorar el ranking frente a recencia;
- **P** busca mejorar la probabilidad (log loss) frente al control.

## Resultado: ambos inconclusos

**Desarrollo (criterio principal):**

| Método | Top 10 | Top 20 | AP | Log loss | Brier | Prob. media (observada 0,490) |
|---|---:|---:|---:|---:|---:|---:|
| S | 51/100 | 105/200 | 0,528 | 0,747 | 0,268 | 0,530 |
| P | 60/100 | 108/200 | 0,547 | 0,6951 | 0,2508 | 0,502 |
| P solo pesos | 60/100 | 108/200 | 0,547 | 0,6941 | 0,2504 | 0,513 |
| P solo nivel | 56/100 | 110/200 | 0,552 | 0,6948 | 0,2506 | 0,501 |
| Control (M1 reentrenado) | 56/100 | 110/200 | 0,552 | 0,6940 | 0,2503 | 0,511 |
| Recencia | 54/100 | 108/200 | 0,546 | — | — | — |

- **S:** −3 puntos frente a recencia (IC 95 % por cliente de −17 a +10). Sin mejora y con la peor probabilidad. En la comprobación pierde 4 compradores en agosto. Decisión: **inconcluso**; no llega al margen de rechazo predeclarado de −5 puntos.
- **P:** log loss +0,0011 frente al control (IC 95 % de −0,005 a +0,008) y Brier ligeramente peor. Decisión: **inconcluso**.
- **Señal no predeclarada:** la ponderación temporal subió el top 10 de desarrollo de 56 a 60 de 100. No era el objetivo de P y el IC no se calculó para esa métrica, así que se registra como **hipótesis** para un protocolo futuro, no como resultado.

**Comprobación exploratoria (julio–septiembre; ya inspeccionada):**

| Método | Elegible top 10 | Top 20 | Atendible top 10 | Brier | Log loss | Prob. media (observada 0,367) |
|---|---|---:|---|---:|---:|---:|
| S | 4/3/4 = 11 | 21 | 6/6/5 = 17 | 0,2676 | 0,7718 | 0,481 |
| P | 5/7/5 = 17 | 32 | 7/3/5 = 15 | 0,2213 | 0,6328 | 0,349 |
| P solo nivel | 4/7/5 = 16 | 29 | 7/3/6 = 16 | **0,2204** | **0,6309** | 0,350 |
| Control | 4/7/5 = 16 | 29 | 7/3/6 = 16 | 0,2244 | 0,6408 | 0,437 |
| M1 v2 congelado | 5/7/5 = 17 | 30 | 7/3/6 = 16 | 0,2306 | 0,6540 | 0,468 |
| Recencia | 5/7/5 = 17 | **34** | **8/5/6 = 19** | — | — | — |

**Lectura:**

- **El tiempo hasta la próxima compra no funciona en esta cartera.** Los intervalos de cada cliente son poco regulares, así que la curva individual no ordena mejor que la recencia y sus probabilidades son las peores.
- **El ajuste de nivel acierta la tasa cuando esta cambia.** En julio–septiembre la compra bajó a 36,7 % y P estimó 34,9 %, frente a 43,7 % del control y 46,8 % de M1 v2, con el mejor Brier y log loss de todos los métodos. En desarrollo, donde la tasa era estable, no ayudó. Es coherente con su hipótesis, pero la regla de decisión era el desarrollo y la comprobación ya estaba inspeccionada, así que no cuenta como demostración.
- **Recencia sigue siendo la mejor para elegir a quién llamar** (34/60 a 20 y 19/30 en la población atendible).

## Qué queda para la prueba prospectiva

- **Fechas:** congelación real el 2026‑11‑23; primer corte prospectivo el **2026‑11‑30**, que madura el **2026‑12‑30**. Los artefactos `artefacto_S.json` y `artefacto_P.json` pueden puntuarse en sombra con `modelos.cli puntuar --artefacto …` cuando exista un lote con cobertura declarada hasta el 30‑11.
- **P:** es el candidato con más sentido para mejorar la calidad de `prob_compra_30d` (no el orden). Para usarlo prospectivamente hay que reaplicar el ajuste de nivel con el último corte maduro antes de cada cierre. Eso es una operación de recalibración fuera del cierre y requiere su propia versión del protocolo; aquí no se ha hecho.
- **Ponderación temporal para ordenar:** la señal (60 frente a 56 de 100 en desarrollo) solo puede confirmarse con un protocolo nuevo, que la predeclare como objetivo de ranking, y con cortes posteriores a su congelación.
- **Promoción:** nada se registra ni se promueve. `v1` sigue operativa y `v2` en sombra.

```powershell
python -m modelos.cli m13-entrenar --datos salida/a01 --config modelos/config/compra_30d_m13.json --salida salida/experimentos/compra_30d_m13/ejecucion-002
python -m modelos.cli m13-evaluar --ejecucion salida/experimentos/compra_30d_m13/ejecucion-002
```

## Integridad y recuperación (24-11-2026)

La ejecución histórica de esta variante es de **formato 2**: sigue legible con verificación parcial declarada (lo que su sello no protege, p. ej. la evidencia de desarrollo, figura en `verificacion.no_verificable`), pero no puede volver a evaluarse ni promoverse con `promover`. Las ejecuciones nuevas usan el **formato 3** (congelación y evaluación selladas, archivos obligatorios, coherencia candidato–artefacto–decisión y recuperación de interrupciones). La reproducción en carpeta nueva dio artefactos, métricas y decisión **idénticos**: la corrección no cambia el resultado predictivo ni la decisión. Detalle: [monitoreo e integridad](monitoreo-modelos.md#a-integridad-y-recuperación-de-m11-m12-y-m13).
