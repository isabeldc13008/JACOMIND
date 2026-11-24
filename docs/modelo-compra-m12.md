# M1.2 · Orden del cupo por fusión de rangos (recencia + modelo)

Protocolo: [`modelos/config/compra_30d_m12.json`](../modelos/config/compra_30d_m12.json) (`m1.2-protocolo-v1`, guardado antes de calcular resultados) · Código: [`modelos/compra_m12.py`](../modelos/compra_m12.py), [`modelos/ranking.py`](../modelos/ranking.py) · Ejecución: `salida/experimentos/compra_30d_m12/ejecucion-001/`

## Qué se probó

Un único cambio frente a M1, sin parámetros que ajustar. Dentro de cada corte se ordena por la suma de dos posiciones:

- la posición por menor recencia;
- la posición por mayor probabilidad del modelo (especificación M1: 4 variables, C = 10, reentrenado sin fuga en cada origen).

Los empates se resuelven por la posición de recencia y después por `cliente_id`.

La fusión solo define el **orden del cupo del piloto**. `prob_compra_30d` sigue siendo la probabilidad del modelo y C1 conserva su orden contractual; una prueba lo verifica publicando un cierre con este artefacto en un registro aislado. Un ranking no se convierte en probabilidad.

El criterio principal es la **validación temporal de desarrollo** (10 orígenes del 2025‑09‑30 al 2026‑06‑30, 100 plazas a K = 10), más estable que los tres meses de julio–septiembre, que ya se habían inspeccionado.

## Resultado: inconcluso; la fusión no mejora

| Desarrollo (criterio principal) | Top 10 | Top 20 |
|---|---:|---:|
| Fusión | 52/100 | 107/200 |
| Recencia | 54/100 | 108/200 |
| Modelo solo (M1 reentrenado) | 56/100 | 110/200 |
| Regla compra 30 días | 54/100 | 107/200 |

- **Diferencia fusión − recencia:** −2 puntos. IC 95 % por remuestreo de clientes: de −7 a +8. No se cumple la meta (+5 con un IC que excluya 0) y tampoco se llega al margen de rechazo (−5).
- **Por origen** (fusión / recencia / modelo): 7/6/8, 4/4/6, 6/4/9, 6/9/4, 7/5/6, 6/6/5, 4/5/5, 2/3/2, 7/8/7, 3/4/4. Ningún método domina de forma estable.

| Comprobación exploratoria (jul/ago/sep) | Elegible top 10 | Elegible top 20 | Atendible top 10 |
|---|---|---:|---|
| Fusión | 5/7/4 = 16 | 33 | 8/5/7 = 20 |
| Recencia | 5/7/5 = 17 | 34 | 8/5/6 = 19 |
| Modelo solo | 4/7/5 = 16 | 29 | 7/3/6 = 16 |
| M1 v2 congelado | 5/7/5 = 17 | 30 | 7/3/6 = 16 |
| v1 congelada | 5/4/4 = 13 | 30 | 7/3/5 = 15 |

La ventaja de un comprador en la población atendible (20 frente a 19) no es la población que gobierna la decisión y está dentro del ruido. La probabilidad del modelo reentrenado tiene Brier 0,2244 y log loss 0,6408; media estimada 0,437 frente a 0,367 observada.

**Conclusión.** Con estos datos, ni M1, M1.1 ni M1.2 superan de forma demostrable a la recencia. Las diferencias entre métodos (±2 compradores de 100) están dentro de la variación por cliente. `v1` sigue operativa y `v2` en sombra; el artefacto M1.2 (`compra_30d-m12-fusion-00462749`) queda como experimental y no se registra.

## Prueba prospectiva preparada

- **Fechas:** congelación real el 2026‑11‑23; primer corte prospectivo el **2026‑11‑30**, que madura el **2026‑12‑30**.
- **Uso:** el artefacto puede puntuarse en sombra junto a la versión operativa en cuanto exista un lote con cobertura declarada hasta el 30‑11:

```powershell
python -m modelos.cli puntuar --artefacto salida/experimentos/compra_30d_m12/ejecucion-001/artefacto.json --datos salida/a01-2026-11 --corte 2026-11-30 --salida salida/puntuaciones/2026-11-30/m12
python -m modelos.cli puntuar --registro var/modelos --estado operativo --datos salida/a01-2026-11 --corte 2026-11-30 --salida salida/puntuaciones/2026-11-30/operativo
python -m modelos.cli comparar --operativo salida/puntuaciones/2026-11-30/operativo --sombra salida/puntuaciones/2026-11-30/m12 --salida salida/puntuaciones/2026-11-30/comparacion-m12
```

- **Hoy:** con el lote actual (datos hasta el 31‑10) estos comandos se rechazan por cobertura insuficiente.
- **Reproducir:**

```powershell
python -m modelos.cli m12-entrenar --datos salida/a01 --config modelos/config/compra_30d_m12.json --salida salida/experimentos/compra_30d_m12/ejecucion-002
python -m modelos.cli m12-evaluar --ejecucion salida/experimentos/compra_30d_m12/ejecucion-002
```

Lo que más podría cambiar el resultado no es otra reordenación de las mismas ventas, sino información nueva (cotizaciones, renovaciones gestionadas, solicitudes: ver el [contrato de señales](plan/modelos/m1.1-senales-comerciales.md)) y más meses o más clientes para que las diferencias sean medibles.
