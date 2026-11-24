# M3 · Próxima compra (`proxima_compra`)

[Plan](plan/modelos/03-proxima-compra.md) · [Base común](plan/modelos/00-base-comun.md) · Protocolo `m3-protocolo-v1` ([configuración](../modelos/config/proxima_compra.json))

**Pregunta.** «Desde este cierre, ¿cuánto tiempo podría faltar hasta la próxima compra confirmada?»

No responde:

- si el cliente abandonará;
- cuándo vence una cobertura;
- la probabilidad de compra a 30 días;
- la duración media de un intervalo completo.

**Decisión (23-11-2026): inconcluso.**

- **Lo que sí funciona**: Cox L2 mejora con claridad la curva poblacional. El Brier integrado baja un 10,3 %, con un IC 95 % por cliente de [−0,034; −0,013].
- **Lo que no**: ninguna ventana p10–p90 es utilizable. El 90 % de probabilidad de compra no se alcanza en 60 días, porque cerca del 45 % de las fotografías no compra en ese plazo. Por eso la cobertura del 80 % no es estimable.
- **Referencia personal**: en el subconjunto común tiene un error mediano algo menor (15 frente a 16 días).
- **Uso actual**: el modelo queda en sombra y publica cuantiles parciales sin inventar fechas. No se promovió nada ni se activaron recordatorios.

## Código

| Pieza | Archivo |
|---|---|
| Seguimiento censurado, referencias, curvas, cuantiles, artefacto y C2 (biblioteca estándar) | `modelos/proxima_compra.py` |
| Preparar, Cox, rejilla, IBS-IPCW, selección, congelación, evaluación y decisión | `modelos/proxima_compra_experimento.py` |
| Protocolo | `modelos/config/proxima_compra.json` |
| Contrato C2 (`_reglas_proxima`) y lector de sombra con sello | `contratos/validar.py`, `contratos/publicacion.v1.schema.json` |
| API: consulta, ficha y recordatorios (bandera apagada) | `api/proxima.py`, `api/migraciones/0003_proxima.sql` |
| Vista | `app/vistas/proxima.js` (`#/proxima` y bloque «ventana estimada» en la ficha) |
| Pruebas | `tests/modelos/test_proxima_compra.py` (22 pruebas) |

Dependencias de supervivencia: `scikit-survival==0.26.0`, en el entorno analítico opcional (`requirements-modelos.txt`). Se instala fijando scikit-learn 1.7.1, numpy 1.26.4 y scipy 1.10.1 para no cambiar M1 ni M2.

El cierre, la API y la puntuación no la importan. Hay una prueba que lo comprueba en un subproceso que bloquea `sksurv`, `sklearn`, `numpy`, `scipy` y `pandas`.

## Datos y objetivo temporal

- **Fuente**: revisión 1 aceptada de A01 (`salida/a01`). Las huellas están en `datos.json`. Ventas declaradas hasta el 2026-10-31.
- **Fuentes no usadas**: base instalada, catálogo y compras a proveedores. Su disponibilidad histórica no está demostrada; el supuesto de M2.1 no la demuestra.
- **Unidad**: cliente × corte mensual C.
- **Elegibles**: clientes con alta anterior o igual a C y al menos una compra confirmada hasta C. Incluye recientes, habituales, ocasionales y fríos; no se copia la restricción 30–89 de M2.
- **Seguimiento**: `fin = min(C + 60, D)`, con D el `seguimiento_hasta` del bloque.
  - Si hay compra en (C, fin], es un evento y la duración son los días hasta la primera.
  - Si no, es una censura y la duración es fin − C.
  - Las filas con seguimiento de cero días se excluyen.
  - Las compras del mismo día cuentan como un día; una compra el día C pertenece al historial.

**Bloques y fronteras** (comprobadas por código en `verificar_fronteras`):

| Bloque | Cortes | Seguimiento hasta (D) | Primera predicción siguiente |
|---|---|---|---|
| Ajuste | mar 2025 – feb 2026 | 2026-04-29 | 2026-04-30 |
| Validación | 2026-04-30, 2026-05-31 | 2026-07-30 (selección) | 2026-07-31 |
| Comprobación | 2026-07-31, 2026-08-31 | 2026-10-30 | — (cobertura hasta 2026-10-31) |

**Conteos reales:**

| Bloque | Filas | Clientes | Eventos | Censuras | Excluidas (alta posterior / sin historial / seguimiento 0) | Referencia personal (disponible / vencida / insuficiente) |
|---|---:|---:|---:|---:|---|---|
| Ajuste | 965 | 120 | 737 | 228 | 298 / 177 / 0 | 342 / 301 / 322 |
| Validación | 240 | 120 | 146 | 94 | 0 / 0 / 0 | 108 / 120 / 12 |
| Comprobación | 240 | 120 | 131 | 109 (45 %) | 0 / 0 / 0 | 92 / 143 / 5 |

- **Comprobación por corte**: 67 eventos el 2026-07-31 y 64 el 2026-08-31.
- **Grupos en la comprobación**: 92 recientes, 68 habituales, 2 ocasionales y 78 fríos.

## Variables, referencias y candidato

- **Variables** (`proxima_compra-variables-v1`, calculadas con información hasta C):
  - recencia;
  - días distintos de compra en 90 y en 180 días;
  - días de compra totales;
  - mediana y dispersión de los intervalos;
  - indicador de historia insuficiente;
  - importe COP en 90 días.

  La imputación y el escalado se ajustan solo con el bloque de ajuste.
- **Referencia personal**:
  - mediana de al menos 2 intervalos positivos menos la recencia; por ejemplo, intervalos [20, 30, 40] con recencia 10 dan 20 días;
  - un resultado de 0 o menos es «vencida» y se publica tal cual, sin desplazarlo;
  - con menos de 2 intervalos es «insuficiente».
- **Kaplan–Meier global**: de los tiempos residuales del ajuste, con censura. Es la referencia principal y no usa subgrupos. No reutiliza las curvas de intervalos completos de M1.3 ni M2.1.
- **Cox L2** (`CoxPHSurvivalAnalysis`, empates de Breslow):
  - **Penalización verificada en el código de scikit-survival 0.26**: pérdida media + Σα·w²/(2n), es decir, α·‖w‖²/2 sobre la log-verosimilitud parcial total. Con unas 1.000 filas, α < 1 es casi nula, así que la rejilla predeclarada es α ∈ {0,1; 1; 10; 100}.
  - **Selección**: menor Brier integrado en validación, y solo si mejora a Kaplan–Meier. En empate gana Kaplan–Meier y, entre Cox, el α mayor.

## Curvas, cuantiles y estados

- **Curva**: S(t) en días enteros de 0 a T, con T = 60 (soporte del ajuste). Se verifica que S(0) = 1, que es no creciente y que está en [0, 1]. Fuera del soporte vale `None`.
- **Cuantil q**: el primer t con 1 − S(t) ≥ q; si no se alcanza, es nulo.
- **Estados**:
  - `estimado`: tiene p10, p50 y p90;
  - `estimacion_parcial`: falta algún cuantil (los nulos van siempre a la derecha);
  - `sin_historial`, `no_elegible`, `modelo_no_disponible` y `sin_soporte`.
- **Origen**: `modelo_cox` o `poblacional_km`.
- **Ventana utilizable**: p10 y p90 existen y p90 − p10 ≤ 30.

## Resultados

**Validación** (rejilla de los días 1 a 59):

| Método | Brier integrado | Error mediano de p50 (eventos con referencia personal) |
|---|---:|---:|
| Kaplan–Meier | 0,2254 | 18,0 días (personal 16,5) |
| **Cox α = 0,1 (elegido)** | **0,2195** | 16,0 (personal 16,5) |
| Cox α = 1 | 0,2195 | 16,0 |
| Cox α = 10 | 0,2198 | 16,0 |
| Cox α = 100 | 0,2214 | 16,5 |

- Todas las variantes convergen sin avisos.
- El artefacto recargado coincide con scikit-survival con un error máximo de 2,2×10⁻¹⁶ (en la curva y en el predictor, 440 filas × 60 tiempos).

**Estabilidad de los coeficientes** (α = 0,1; 100 remuestreos de clientes). El valor entre paréntesis es la proporción de remuestreos con el mismo signo:

| Variable | Coeficiente | Mismo signo |
|---|---:|---:|
| Dispersión de intervalos | −0,112 | 0,98 |
| Recencia | −0,037 | 0,72 |
| Días de compra en 90 d | +0,046 | 0,74 |
| Días de compra en 180 d | +0,092 | 0,72 |
| Días de compra totales | −0,061 | 0,64 |
| Intervalo mediano | +0,014 | 0,61 |
| Historia insuficiente | −0,008 | 0,59 |
| Importe COP en 90 d | +0,034 | 0,60 |

Solo la dispersión de intervalos es estable; el resto de coeficientes son pequeños y de signo inestable.

**Comprobación histórica** (julio y agosto; exploratoria; 240 fotografías, todas incluidas, también las censuradas):

| | Cox (elegido) | Kaplan–Meier |
|---|---:|---:|
| Brier integrado (días 1–59) | **0,2042** | 0,2276 |
| Concordancia IPCW (τ = 59) | 0,631 | 0,500 |
| Con p10 / p50 / p90 | 100 % / 100 % / **0 %** | 100 % / 100 % / 0 % |
| Ventanas utilizables | **0 de 240** | 0 de 240 |
| Error mediano de p50 (131 compradores) | 17 días | 15 días |
| Subconjunto común con referencia personal (64) | 16 días (personal 15) | 15 (personal 15) |

- **Diferencia de Brier** (remuestreo de 1.000 réplicas por cliente): −0,0235, con IC 95 % [−0,034; −0,013]. Reducción relativa: 10,3 %.
- **Por corte** (Cox frente a Kaplan–Meier): 0,202 / 0,224 el 31 de julio y 0,206 / 0,232 el 31 de agosto.
- **Por grupo**:

  | Grupo | Cox | Kaplan–Meier | Lectura |
  |---|---:|---:|---|
  | Fríos | 0,182 | 0,252 | la mayor ganancia |
  | Habituales | 0,217 | 0,226 | mejora |
  | Recientes | 0,213 | 0,209 | algo peor |
  | Ocasionales | — | — | solo 2 casos |

- **Referencia personal**: su concordancia es 0,355 en sus 235 casos con referencia, frente a 0,636 de Cox en ese mismo subconjunto. La referencia «vencida» (143 casos) ordena al revés: quien ya superó su intervalo habitual suele tardar más, no menos.
- **Contraste con scikit-survival**: mi Brier integrado coincide con `integrated_brier_score` hasta 5,6×10⁻¹⁷. La distribución de censura se estima con el ajuste, con la convención `reverse=True` de scikit-survival.

## Decisión: **inconcluso**

| Meta (predeclarada) | Resultado |
|---|---|
| Mínimos de evidencia (≥ 150 filas, ≥ 50 eventos, ≥ 20 por corte, ≥ 30 puntos) | Sí: 240 filas, 131 eventos, 67 y 64 por corte, 59 puntos |
| Reducción de Brier ≥ 5 % frente a Kaplan–Meier | **Sí: 10,3 %** |
| IC 95 % de la diferencia de Brier por debajo de 0 | **Sí: [−0,034; −0,013]** |
| Error mediano no peor que la referencia personal (subconjunto común ≥ 20) | No: 16 frente a 15 días (64 casos) |
| Ventanas utilizables en al menos el 50 % de elegibles | No: 0 % (p90 nunca dentro de 60 días) |
| Cobertura del 80 % compatible | No estimable: 0 ventanas determinadas |

No es «rechazado»: el Brier mejora con claridad y no hay evidencia de deterioro.

**Uso recomendado**: mostrar la curva (p10 y p50 con su fecha) como estimación experimental y no crear recordatorios. No hay ventana utilizable, así que no se generan fechas exactas.

## Ejemplos (sombra del 2026-10-31, `salida/sombra/proxima_compra/2026-10-31`)

| Caso | Cliente | Publicación |
|---|---|---|
| Parcial con referencia personal disponible | CLI002 (recencia 9) | p10 día 5 (05-11), p50 día 26 (26-11), p90 nulo; referencia personal 8 días; `ventana_utilizable = false` |
| Parcial con referencia vencida | CLI001 (recencia 212, frío) | p10 día 8, p50 día 50, p90 nulo; referencia personal −191 («vencida»), sin desplazar |
| Ventana completa | — | Ningún cliente real en este corte. El caso está cubierto con datos de prueba (DEMO05: días 2–20) |
| Sin estimación | — | No hay clientes sin compras en este corte. El estado `sin_historial` (fechas nulas y sin referencia) está cubierto en las pruebas |

- **Conteo del corte**: 120 en `estimacion_parcial`, 0 ventanas utilizables.
- **Rango de p10**: días 3 a 9.
- **Rango de p50**: días 19 a 56.

## Integración

- **C2** (`modelo_id = proxima_compra`):
  - `probabilidad` es siempre null;
  - `_reglas_proxima` valida cuantiles dentro del soporte, fechas iguales a corte + días, orden, nulos a la derecha, `ventana_utilizable` y `ancho_ventana_dias` recalculados, origen y coherencia de la referencia personal;
  - los tres modelos coexisten por la clave `cliente_id, modelo_id`;
  - el cierre solo publica M3 con una versión operativa registrada, y hoy no existe.
- **Sombra**: se importa con `python -m api sombra salida/sombra/proxima_compra/2026-10-31` (o `POST /api/proxima/sombra`).
  - `GET /api/proxima?dias=N` lista solo ventanas utilizables, verificadas de nuevo en el servidor. La acción C1 y el próximo fin de cobertura (contractual) aparecen en columnas separadas.
  - La ficha añade el bloque «ventana estimada» con el corte, el origen y las limitaciones.
- **Permisos**: `proxima.ver` para operaciones, ventas y gerencia. El portal externo no lo recibe.
- **Recordatorios**: bandera `proxima_recordatorios` apagada por defecto. Cuando está activa:
  - solo actúan sobre ventanas utilizables;
  - el episodio es estable (`proxima:<cliente>:<última compra>`) y no se duplica;
  - una compra posterior lo cierra;
  - si ya hay un seguimiento abierto, se añade el motivo sin tocar sus resultados humanos.

## Correcciones compartidas con M2 (regresiones en `test_proxima_compra.py`)

- **Publicación antigua**: una sombra de un corte anterior se guarda sin desplazar a la activa (`importar_sombra` devuelve `activa: false`).
- **Episodios**: no se modifican con evidencia anterior a su apertura o a su última actualización (`_evidencia_anterior`).
- **Lector**: verifica el sello del manifiesto además de las huellas, y la coherencia de versión, decisión, artefacto y conteos con las filas.
- **Cupos**: se calculan sobre clientes únicos, ordenando por probabilidad validada; no se confía en `posicion`.
- **Average precision**: con empates, la de M1/M2 depende del desempate por `cliente_id`. Se añadió `average_precision_empates`, igual a la de scikit-learn, y una prueba con ambas. Los resultados publicados de M1/M2 no se recalculan; M3 no usa AP.
- **Publicaciones existentes**: las tres de M2 y M2.1 siguen siendo válidas con el lector más estricto.

## Reproducibilidad e integridad

```
python -m modelos.cli entrenar --modelo proxima_compra --datos salida/a01 --salida salida/experimentos/proxima_compra/ejecucion-001
python -m modelos.cli entrenar --modelo proxima_compra --datos salida/a01 --salida salida/experimentos/proxima_compra/ejecucion-002
python -m modelos.cli evaluar --ejecucion salida/experimentos/proxima_compra/ejecucion-001   (dos veces, y también sobre la 002)
python -m modelos.cli puntuar --modelo proxima_compra --ejecucion salida/experimentos/proxima_compra/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/proxima_compra/2026-10-31
```

- **Reproducibilidad**:
  - las ejecuciones 001 y 002 tienen el mismo sello (`91704815…`) y el mismo artefacto `proxima_compra-m3-cox-a0_1-830e173f`;
  - repetir la evaluación es idempotente (`360573d0…`) y la 002 da la misma decisión;
  - repetir la sombra no cambia nada (`b03afa65…`).
- **Rechazos de la CLI** (código 2): evidencia alterada, corte sin cobertura y artefacto de M3 usado como compra.
- **Recuperación**: tras una interrupción simulada, la evaluación se completa al reintentar sin borrar archivos.

## Piloto prospectivo (desde la congelación real del 2026-11-23)

- **Primer corte**: 2026-11-30. Requiere ventas completas hasta esa fecha.
- **Seguimiento completo**: desde el 2027-01-29, para evaluar los 60 días.
- **Qué medir**:
  - compras dentro de p10–p50;
  - Brier frente a Kaplan–Meier;
  - si con datos reales aparece alguna ventana utilizable.

  Si el p90 sigue sin alcanzarse en 60 días, conviene acordar con Ventas otra regla de ventana (por ejemplo p10–p50 o un horizonte mayor). Eso exige un protocolo nuevo.

## Limitaciones

- Datos sintéticos ya inspeccionados: la comprobación es exploratoria.
- Las fotografías mensuales de un cliente están correlacionadas; la incertidumbre se estima remuestreando clientes.
- El error entre compradores observados no describe a toda la cartera.
- Las censuras son administrativas; la falta de compra no se interpreta como abandono.

## M3.1 · Ventana de inicio probable y Cox estratificado (protocolo `m31-protocolo-v1`)

**Implementado y evaluado el 23 de noviembre de 2026, con decisión «inconcluso».** Cumple 5 de 7 metas y ahora sí entrega ventanas útiles. Queda en sombra. La configuración está en [`modelos/config/proxima_compra_m31.json`](../modelos/config/proxima_compra_m31.json).

### Por qué

En los datos de práctica, ni siquiera los mejores grupos bajan del 10 % sin compra a los 60 días (el entrenamiento da un 18–21 %). Por eso p90 nunca existe y la ventana p10–p90 no es alcanzable con ningún modelo. A 120 días sí se alcanza, pero la ventana iría del día 5 al 110.

Por decisión del responsable del proyecto, M3.1 cambia el producto:
- **Ventana de inicio probable p10–p50**, utilizable si mide 30 días o menos. Su cobertura nominal es del 40 %.
- **Probabilidad acumulada de compra a 15, 30 y 60 días** (`prob_acumulada` en C2).

Además, prueba a afinar Cox:
- curva base de Breslow por grupo (estratos), con coeficientes comunes;
- la variable `ratio_recencia_ciclo`.

scikit-survival no admite estratos, así que el ajuste es propio (`modelos/proxima_compra_m31.py`, L-BFGS con gradiente analítico) y usa la misma penalización. Con un solo estrato reproduce `CoxPHSurvivalAnalysis`: los coeficientes difieren en 4×10⁻⁸ y la curva base en 1×10⁻⁹.

Antes de entrenar se fijaron los candidatos: Kaplan–Meier, Cox (α ∈ {0,1; 1; 10; 100}) y Cox estratificado (mismos α). Los datos, bloques, fronteras, rejilla y referencias son los mismos que en M3.

### Resultados

**Validación:**
- **Brier integrado**: Kaplan–Meier 0,2254, Cox α=0,1 0,2195 y el mejor estratificado (α=10) 0,2202.
- **Selección**: **Cox α=0,1, el mismo modelo que en M3**. El estratificado no mejoró la curva; todas las variantes convergen.

La mejora de M3.1 viene del cambio de ventana y de la probabilidad acumulada, no de un modelo distinto.

**Comprobación** (julio y agosto; exploratoria y ya vista en M3; 240 fotografías):

| | M3.1 (Cox) | Kaplan–Meier | Referencia personal |
|---|---:|---:|---:|
| Brier integrado (días 1–59) | **0,204** | 0,228 | — |
| Ventanas de inicio probable utilizables (≤ 30 días) | **143 de 240 (60 %)**; M3 tenía 0 | 240 de 240 (igual para todos) | — |
| Compras dentro de p10–p50 (nominal 40 %) | **84 de 240 (35 %)**, IC 95 % [28,8 %; 41,3 %] | 66 de 240 (27,5 %) | — |
| Probabilidad a 15 / 30 / 60 días: estimada frente a real | 28,0 / 46,8 / 69,5 % frente a 27,1 / 39,2 / 54,6 % | 33,0 / 53,5 / 76,4 % frente a lo mismo | — |
| Error mediano de p50 en el subconjunto común (64) | 16 días | — | **15 días** |

- **Lectura**: el modelo adapta el ancho de la ventana a cada cliente. Da una ventana útil al 93 % de los recientes (86 de 92), al 69 % de los habituales (47 de 68) y al 10 % de los fríos (8 de 78). Su cobertura es compatible con el 40 % nominal; la de Kaplan–Meier se queda en 27,5 %.
- **Calibración**: sobrestima la compra a 30 y 60 días porque en julio–septiembre se compró menos que durante el entrenamiento, el mismo cambio de nivel que en M1. Kaplan–Meier sobrestima aún más.

### Decisión: **inconcluso**

| Meta | Resultado |
|---|---|
| Mínimos de evidencia | Sí |
| Brier al menos 5 % mejor que Kaplan–Meier, con IC por debajo de 0 | **Sí**: 10,3 %, IC [−0,034; −0,013] |
| Ventanas utilizables en al menos el 50 % de elegibles | **Sí**: 59,6 % |
| Cobertura p10–p50 compatible con el 40 % | **Sí**: IC [0,29; 0,41] |
| Error no peor que la referencia personal | No: 16 frente a 15 días |
| Calibración acumulada con error ≤ 5 puntos | No: 14,9 puntos a 60 días |

- **No es «rechazado»**: no hay evidencia de deterioro.
- **Siguiente mejora con fundamento**: un ajuste de nivel al último corte maduro, como la variante «P» de M1.3. Exige un protocolo nuevo y confirmarlo en el piloto.

### Ejecución, sombra e integración

```
python -m modelos.cli entrenar --modelo proxima_compra --config modelos/config/proxima_compra_m31.json --datos salida/a01 --salida salida/experimentos/proxima_compra_m31/ejecucion-001   (y -002)
python -m modelos.cli evaluar --ejecucion salida/experimentos/proxima_compra_m31/ejecucion-001 --m3 salida/experimentos/proxima_compra/ejecucion-001   (dos veces, y sobre la 002)
python -m modelos.cli puntuar --modelo proxima_compra --ejecucion salida/experimentos/proxima_compra_m31/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/proxima_compra_m31/2026-10-31
python -m modelos.cli resumen-ia
```

- **Reproducibilidad**:
  - las ejecuciones 001 y 002 tienen el mismo sello (`5b28c964…`) y el mismo artefacto `proxima_compra-m31-cox-a0_1-58fdcb1b`;
  - repetir la evaluación es idempotente (`332c846d…`) y la 002 da la misma decisión;
  - la reevaluación de M3 sigue idéntica tras generalizar las métricas.
- **Sombra del 2026-10-31** (sello `d99258f6…`): 64 de 120 clientes tienen ventana de inicio probable utilizable, por grupo:
  - 32 de 38 recientes;
  - 31 de 41 habituales;
  - 1 de 41 fríos.

  Por ejemplo, CLI002 tiene inicio probable del 5 al 26 de noviembre y una probabilidad del 34 %, 56 % y 79 % a 15, 30 y 60 días. Las filas de M3 no cambian: los campos `ventana_tipo` y `prob_acumulada` solo aparecen con artefactos de M3.1.
- **Contrato**: `ventana_tipo` (`p10_p90` o `p10_p50`) define el ancho y si la ventana es utilizable. `prob_acumulada` debe tener valores en [0, 1], días dentro del soporte y ser no decreciente.
- **API y vista**:
  - la consulta y la ficha muestran «inicio probable (10 %–50 %)» y las probabilidades acumuladas;
  - la página «Modelos de IA» incluye este modelo con su propia tabla.
- **Pruebas**: `tests/modelos/test_proxima_compra_m31.py`, con 5 pruebas. Cubren la curva por grupo, un estrato sin soporte, el contrato, la compatibilidad con M3, el contraste con scikit-survival, la idempotencia y la sombra.

## M3.2 · Ajuste de nivel por corte (protocolo `m32-protocolo-v1`)

**Implementado y evaluado el 23 de noviembre de 2026, con decisión «inconcluso».** El ajuste de nivel no se seleccionó; el modelo publicado sigue siendo el de M3.1. La configuración está en [`modelos/config/proxima_compra_m32.json`](../modelos/config/proxima_compra_m32.json) y el código en `modelos/proxima_compra_m32.py`.

### Qué es

- **Coeficientes y forma de la curva**: los del ajuste, sin cambios.
- **Factor de nivel**: en cada corte C, el riesgo acumulado se multiplica por un factor.
- **Cálculo del factor** (`factor_nivel`): compras observadas ÷ Σ H0(Tᵢ)·exp(ηᵢ). Es la máxima verosimilitud con forma fija.
- **Cortes que usa**: los 3 últimos cortes C′ con C′ + 60 < C y seguimiento hasta C − 1. Por ejemplo, para el 31 de julio usa marzo, abril y mayo.
- **Sin fuga**: se comprueba por código y en las pruebas.
- **Publicación**: el factor se guarda en cada fila (`factor_nivel`) y en el manifiesto.

Los candidatos son Kaplan–Meier, Cox sin nivel y Cox con nivel, cada uno con α ∈ {0,1; 1; 10; 100}. El resto es igual que en M3.1.

### Resultados

- **Validación**: Cox sin nivel 0,2195 y con nivel 0,2221. Se elige **Cox α=0,1 sin nivel**, el mismo que en M3.1.
  - Los factores fueron 1,066 (30 de abril) y 1,007 (31 de mayo): los meses maduros antes de abril aún tenían una tasa de compra alta.
  - La caída apareció después, y el nivel la detecta con unos dos meses de retraso.
- **Comprobación**: decisión idéntica a M3.1 (Brier 0,204, 143 ventanas utilizables, cobertura del 35 %). Calibración a 30 días: 46,8 % estimado frente a 39,2 % real.
- **Contexto**: medición de cada candidato congelado en la comprobación. **No cambia la selección**, porque ese bloque ya se había visto.

  | Candidato | Brier | Ventanas utilizables | Cobertura p10–p50 | Estimado / real a 15, 30 y 60 días |
  |---|---:|---:|---:|---|
  | Cox α=0,1 (elegido) | 0,2042 | 143 | 35 % | 28 / 27 · 47 / 39 · 70 / 55 % |
  | Cox α=0,1 con nivel (factores 0,76 y 0,70) | **0,2006** | 29 | 38 % | 21 / 27 · **37 / 39** · 58 / 55 % |
  | Kaplan–Meier | 0,2276 | 240 | 27,5 % | 33 / 27 · 54 / 39 · 76 / 55 % |

- **Lectura**: el nivel sí corrige la sobrestimación cuando la caída ya es visible en los meses maduros. El coste es que la ventana de inicio probable se ensancha y solo queda útil para 29 casos.
  - Hay que elegir entre una probabilidad bien calibrada y ventanas estrechas.
  - Con datos sintéticos y un cambio de nivel brusco, no hay evidencia para decidir. Lo correcto es medirlo en el piloto. Ambas variantes ya están congeladas en `salida/experimentos/proxima_compra_m32/ejecucion-001/candidatos/`.

### Reproducibilidad y pruebas

```
python -m modelos.cli entrenar --modelo proxima_compra --config modelos/config/proxima_compra_m32.json --datos salida/a01 --salida salida/experimentos/proxima_compra_m32/ejecucion-001   (y -002)
python -m modelos.cli evaluar --ejecucion salida/experimentos/proxima_compra_m32/ejecucion-001 --m31 salida/experimentos/proxima_compra_m31/ejecucion-001   (dos veces, y sobre la 002)
```

- **Reproducibilidad**: las ejecuciones 001 y 002 tienen el mismo sello (`68fc3bb1…`) y la misma decisión; repetir la evaluación es idempotente.
- **Sombra**: no publiqué una nueva, porque el artefacto elegido da las mismas predicciones que M3.1. La sombra activa sigue siendo `salida/sombra/proxima_compra_m31/2026-10-31`.
- **Pruebas**: `tests/modelos/test_proxima_compra_m32.py`, con 4 pruebas: cortes maduros, estimador sin fuga, artefacto que exige y aplica el factor, y contrato.
- **Sin cambios en M3 y M3.1**: sus filas y evaluaciones siguen idénticas.

### Piloto (desde el 2026-11-30)

- Puntuar en sombra **las dos variantes** congeladas: sin nivel (operativa en sombra) y con nivel (contexto).
- Desde el 2027-01-29, comparar calibración, cobertura y ventanas útiles con datos posteriores a la congelación.
- Solo entonces decidir, con un protocolo nuevo, si conviene el ajuste de nivel o una regla de ventana distinta.

## Monitoreo (24-11-2026)

M3: cobertura de probabilidades y ventanas; desempeño por horizonte (15, 30 y 60 días) solo cuando madura; los clientes censurados nunca cuentan como no compradores. Ver [monitoreo de modelos](monitoreo-modelos.md#b-monitoreo-de-m1m6).
