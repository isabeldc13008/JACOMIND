# M2 · Riesgo de inactividad a 60 días (`inactividad_60d`)

[Plan](plan/modelos/02-riesgo-inactividad.md) · [Base común](plan/modelos/00-base-comun.md) · Protocolo: [`modelos/config/inactividad_60d.json`](../modelos/config/inactividad_60d.json) (`m2-protocolo-v1`, fijado el 2026-11-23 antes de entrenar)

**Qué estima:** la probabilidad de que un cliente hoy activo (menos de 90 días sin comprar) llegue a 90 días sin compra confirmada en algún momento de los próximos 60 días. Ayuda a Ventas a priorizar la prevención.

**Qué no es:**
- no es abandono definitivo;
- no es cancelación contractual;
- no es «1 − probabilidad de recompra».

**Estado:** implementado y evaluado el 2026-11-23. **Decisión: inconcluso.** El candidato no supera a «mayor recencia», que se mantiene como referencia del cupo. No hay ninguna versión registrada (ni operativa ni en sombra) y el registro de `compra_30d` no cambió.

## Código

| Pieza | Archivo | Dependencias |
|---|---|---|
| Población, etiqueta, fotografías, filas C2 y publicación en sombra | [`modelos/inactividad.py`](../modelos/inactividad.py) | biblioteca estándar |
| Variables `inactividad_60d-variables-v1` | [`modelos/variables.py`](../modelos/variables.py) (`variables_inactividad`) | biblioteca estándar |
| Preparar, entrenar, seleccionar, congelar y evaluar | [`modelos/inactividad_experimento.py`](../modelos/inactividad_experimento.py) | scikit-learn solo dentro de `ajustar` |
| Publicación consistente y recuperable de ejecuciones | [`modelos/ejecucion.py`](../modelos/ejecucion.py) | biblioteca estándar |
| Artefacto: especificación por modelo y rechazo de otro modelo, horizonte o esquema | [`modelos/inferencia.py`](../modelos/inferencia.py), [`modelos/registro.py`](../modelos/registro.py) | biblioteca estándar |
| Contrato C2 (`estructural`, reglas de inactividad, publicación en sombra) | [`contratos/validar.py`](../contratos/validar.py), [`publicacion.v1.schema.json`](../contratos/publicacion.v1.schema.json) | biblioteca estándar |
| Cierre: solo publica la versión **operativa** registrada | [`pipeline/generar.py`](../pipeline/generar.py) | biblioteca estándar |
| API: sombra, lista interna, episodios y bandera | [`api/prevencion.py`](../api/prevencion.py), [`api/migraciones/0002_prevencion.sql`](../api/migraciones/0002_prevencion.sql) | biblioteca estándar |
| Vista interna experimental y bloque en la ficha | [`app/vistas/prevencion.js`](../app/vistas/prevencion.js) | — |
| Pruebas | [`tests/modelos/test_inactividad.py`](../tests/modelos/test_inactividad.py) (28) | — |

## Datos, población y etiqueta

**Fuente de datos.** Se usa solo la revisión aceptada de A01 (`salida/a01/publicado`, revisión 1, estado `publicable`, huella de datos `6d338a2d42ea0363…`).

**Cobertura por fuente** (se registra en `datos.json`):

| Fuente | Cobertura | Uso |
|---|---|---|
| Ventas | Declarada hasta **2026-10-31**, por la declaración registrada del paquete con las siete huellas de origen idénticas. No se deduce de la última venta. | Variables y etiqueta |
| Clientes | Maestro sin fecha de corte | Elegibilidad por `fecha_alta` |
| TRM | Por fecha (2025-01-01 a 2026-10-31) | Importe con la tasa de la fecha de cada venta |

**Fuentes que no se usan:**
- base instalada y coberturas: su disponibilidad histórica no se puede reconstruir;
- atributos del catálogo: solo se conoce su estado actual;
- compras a proveedores;
- `incidencias.jsonl` de A01.

**Convención de disponibilidad:** fecha del evento (convención sintética documentada).

**Unidad de observación:** cliente × corte de fin de mes. La recencia es `C − L`, donde `L` es el último **día** de compra confirmada con fecha ≤ C. Así se clasifica cada fila:

| Población | Condición | Estado C2 | Probabilidad | Aprendizaje y ranking |
|---|---|---|---|---|
| Estructural | Recencia 0–29 | `estructural` | **0 exacto**, con motivo | No (sí cuenta en la cobertura) |
| Aprendible | Recencia 30–89 | `estimado` (o `modelo_no_disponible`) | Del modelo (o `null`) | Sí |
| Ya frío | Recencia ≥ 90 | `no_elegible`, motivo `ya_frio` | `null` | No (corresponde a reactivación) |
| Sin historial | Sin compras confirmadas | `sin_historial` | `null` | No |
| Alta posterior | Alta después del corte | `no_elegible` | `null` | No |

**Etiqueta** (`inactividad-60d-etiqueta-v1`). Se calcula sobre días de compra distintos, con el estado al final de cada día. El horizonte es `(C, E]`, con `E = C + 60`, y el cruce es `L + 90`.
1. Si el cruce cae fuera del horizonte, la etiqueta es 0.
2. Si hay una compra antes del cruce o el mismo día, `L` pasa a esa compra y se vuelve a calcular el cruce.
3. Si no la hay, la etiqueta es 1 y se guarda `fecha_cruce`. Una compra posterior al cruce no borra el evento.
4. Si la cobertura no llega a `E`, la etiqueta queda **pendiente**, también para cruces ya observados.

Ejemplo verificado en pruebas: `C = 2026-07-31`, `L = 2026-06-02`, cruce el 2026-08-31.
- Una compra el 30 o el 31 de agosto evita el cruce.
- Una compra el 1 de septiembre no lo evita: etiqueta 1 con fecha de cruce 2026-08-31.

**Comprobaciones por código** (`fotografias` se detiene si alguna falla):
- un cruce en el día 60 cuenta;
- en el día 61 no cuenta;
- ninguna fila estructural tiene evento.

### Conteos reales (recalculados)

| Bloque | Cortes | Fotografías | Aprendibles maduras | Clientes únicos aprendibles | Eventos | Sin evento | Clientes con evento | Estructurales | Ya fríos | Sin historial | Alta posterior | Pendientes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Ajuste | 2025-03 … 2026-02 (12) | 1.440 | 309 | 109 | 136 | 173 | 59 | 558 | 98 | 177 | 298 | 0 |
| Validación | 2026-04, 2026-05 | 240 | 107 | 86 | 60 | 47 | 47 | 102 | 31 | 0 | 0 | 0 |
| Comprobación histórica | 2026-07, 2026-08 | 240 | 69 | 58 | 35 | 34 | 26 | 93 | 78 | 0 | 0 | 0 |

Por mes, en la comprobación: julio tiene 39 aprendibles y 20 eventos; agosto tiene 30 aprendibles y 15 eventos.

Los 1.444 registros y 278 eventos de la exploración usaban otra población y otras particiones. No se forzaron.

## Variables (`inactividad_60d-variables-v1`)

Se calculan con ventas confirmadas de fecha ≤ corte, incluido ese día. Las frecuencias cuentan **días de compra distintos**.

| Variable | Fórmula y ventana | Ausencia | Transformación |
|---|---|---|---|
| `recencia_dias` | C − último día de compra | — | log1p |
| `dias_compra_30d`, `_90d`, `_180d` | Días con `0 ≤ C − día < k` | — | identidad |
| `dias_compra_distintos` | Días de compra hasta C | — | log1p |
| `cambio_dias_90d` | Días en [0, 90) − días en [90, 180) | — | identidad |
| `intervalo_mediano_dias` | Mediana de los intervalos entre días distintos | `null` si hay menos de 2 intervalos | log1p |
| `intervalo_dispersion_dias` | Desviación absoluta mediana de esos intervalos | `null` si hay menos de 2 intervalos | log1p |
| `ratio_recencia_ciclo` | recencia / intervalo mediano | `null` si hay menos de 2 intervalos | log1p |
| `historia_insuficiente` | 1 si hay menos de 2 intervalos | — | identidad |
| `importe_cop_90d` | Suma COP (A02, por operación) de las ventas con `C − fecha < 90` | `null` si falta la TRM de alguna venta de la ventana | log1p |

- **Imputación** por la mediana y **escalado** (media y desviación poblacional): se ajustan solo con el bloque de ajuste. Una prueba lo recalcula y compara.
- `dias_compra_30d` es siempre 0 en la población aprendible (recencia ≥ 30). Queda con desviación 1 y peso 0; no se retiró para no cambiar el protocolo después de ver los datos.

**Candidatos predeclarados:** regresión logística L2 con `lbfgs`, semilla 20261123 y C ∈ {0,1; 1; 10}, sobre dos combinaciones:
- básica: recencia y días de compra a 30, 90 y 180 días, y días distintos;
- ampliada: la básica más cambio, intervalos, relación con el ciclo, historia insuficiente e importe.

En total son 6 candidatos.
- **Árbol de profundidad 3:** no incluido, porque no se predeclaró.
- **No se añadieron:** boosting, supervivencia ni calibración.
- **Mínimo de clases:** si el ajuste o la validación carecen de alguna clase, no se entrena y se conserva la referencia. Probado con `entrenar` sin eventos.

**Selección en validación:** precisión media a 10, luego sensibilidad agregada a 10, luego Brier y luego simplicidad (menos variables y menor C). Los pesos se ajustan una vez con el bloque de ajuste y **no se reentrenan** antes de la comprobación.

## Protocolo temporal (comprobado por código)

| Bloque | Cortes | Última etiqueta madura | Primera inferencia del bloque siguiente |
|---|---|---|---|
| Ajuste | 2025-03-31 … 2026-02-28 | 2026-04-29 | 2026-04-30 (validación) |
| Validación | 2026-04-30, 2026-05-31 | 2026-07-30 | 2026-07-31 (comprobación) |
| Comprobación histórica | 2026-07-31, 2026-08-31 | 2026-10-30 ≤ cobertura 2026-10-31 | — |

- Marzo y junio de 2026 quedan fuera como separación.
- Septiembre de 2026 no se incluye, porque necesitaría datos hasta el 2026-11-29.
- `verificar_fronteras` rechaza un protocolo que solape bloques (prueba con validación desde marzo).

## Resultados

**Comprobación histórica EXPLORATORIA:** julio y agosto de 2026, datos ya inspeccionados. No es una validación prospectiva independiente.

### Validación (selección)

| Método | Precisión media a 10 | Aciertos a 10 | Sensibilidad agregada a 10 | Brier | AP conjunta |
|---|---:|---:|---:|---:|---:|
| ampliada C=0,1 (**elegido**) | 0,70 | 14/20 | 0,233 | 0,2509 | 0,688 |
| ampliada C=1 | 0,70 | 14/20 | 0,233 | 0,2565 | 0,698 |
| ampliada C=10 | 0,70 | 14/20 | 0,233 | 0,2584 | 0,700 |
| básica C=0,1 | 0,65 | 13/20 | 0,217 | 0,2521 | 0,664 |
| básica C=1 | 0,60 | 12/20 | 0,200 | 0,2584 | 0,649 |
| básica C=10 | 0,60 | 12/20 | 0,200 | 0,2611 | 0,647 |
| Mayor recencia | **0,75** | **15/20** | **0,250** | — | **0,702** |
| Constante (tasa de ajuste 0,440) | 0,65 | 13/20 | 0,217 | 0,2609 | 0,602 |

Ya en validación el mejor candidato quedaba 5 puntos por debajo de mayor recencia. La regla del protocolo era seleccionar y congelar sin cambiar el criterio, y así se hizo.

### Comprobación histórica (decisión)

Los mismos 69 clientes aprendibles por corte para todos los métodos.

| Método | Julio: aciertos a 10 / falsos + | Agosto: aciertos a 10 / falsos + | Precisión media a 10 | Sensibilidad agregada a 10 | Aciertos a 20 (sensibilidad) | AP media mensual / conjunta | Brier | Log loss |
|---|---|---|---:|---:|---|---|---:|---:|
| Candidato | 6 / 4 | 7 / 3 | 0,65 | 0,371 (13/35) | 25/40 (0,714) | 0,703 / 0,684 | 0,2351 | 0,660 |
| **Mayor recencia** | 7 / 3 | 9 / 1 | **0,80** | **0,457 (16/35)** | 24/40 (0,686) | **0,762 / 0,727** | — | — |
| Constante 0,440 | 5 / 5 | 4 / 6 | 0,45 | 0,257 (9/35) | 21/40 (0,600) | 0,550 / 0,529 | 0,2545 | 0,702 |

- **Media mensual frente a agregado.** La precisión media es la media de los meses. La sensibilidad agregada es la suma de aciertos entre la suma de eventos.
- **AP:** suma por escalones, no interpolada.

**Regla existente (`recencia + 60 ≥ 90`).** Es un booleano, no una probabilidad.

| Mes | Activos maduros | Alertas | Eventos detectados | Falsas alarmas |
|---|---:|---:|---:|---:|
| Julio | 84 | 39 | 20/20 | 19 |
| Agosto | 78 | 30 | 15/15 | 15 |

- En total da 69 alertas, 35/35 eventos y 34 falsas alarmas (precisión 0,507).
- Sobre la población aprendible marca a todos, así que su sensibilidad es 1 y su precisión es la tasa de eventos.
- No ordena ni cabe en un cupo. Por eso el comparador del cupo es mayor recencia.

**Incertidumbre.** Bootstrap de 2.000 réplicas por cliente completo (58 clientes, con sus meses juntos):

| Diferencia | IC 95 % | Media |
|---|---|---:|
| Precisión media a 10, candidato − mayor recencia | [−0,25; +0,10] | −0,083 |
| Brier, candidato − constante | [−0,065; +0,028] | — |

**Probabilidades del candidato:**

| Medida | Valor |
|---|---|
| Media / tasa observada | 0,549 / 0,507 (sobrestima unos 4 puntos) |
| Distribución | mín. 0,156; p10 0,273; mediana 0,592; p90 0,759; máx. 0,872 |
| Por mes | julio: Brier 0,267, media 0,545, observada 0,513 · agosto: Brier 0,193, media 0,554, observada 0,500 |
| Calibración | 8 bandas con 2 a 18 casos, no monótona: 0,5–0,6 → 0,25 observada; 0,6–0,7 → 0,67 |

Con 69 casos la calibración por bandas solo es descriptiva.

**Cobertura** (2 cortes, 240 fotografías):

| Grupo | Fotografías |
|---|---:|
| Activos | 162 |
| Con estimación del modelo | 69 |
| Estructurales (0 exacto) | 93 |
| Ya fríos excluidos | 78 |
| Sin historial | 0 |
| Pendientes | 0 |
| Sin modelo | 0 |

### Decisión: **inconcluso**

Las reglas se fijaron en `m2-decision-v1` antes de evaluar.

| Meta | Resultado |
|---|---|
| Mínimos de evidencia (≥ 20 eventos, ≥ 5 por mes, 2 meses) | ✔ 35 eventos (20 y 15) |
| Mejora ≥ 5 puntos de precisión media a 10 frente a mayor recencia | ✘ −15 puntos |
| IC 95 % de la diferencia por encima de 0 | ✘ [−0,25; +0,10] |
| Sensibilidad agregada a 10 no menor | ✘ 0,371 frente a 0,457 |
| Brier no peor que la constante | ✔ 0,235 frente a 0,254 |

- **No es «rechazado»:** el IC de la diferencia principal incluye 0, y el de Brier frente a la constante también. No hay evidencia suficiente de deterioro.
- **Tampoco hay mejora:** mayor recencia queda por delante en validación y en comprobación.
- **Qué se conserva:** mayor recencia como orden del cupo y la regla como alerta.
- **Qué se descarta:** el candidato no habilita ni siquiera la sombra como sustituto. La puntuación en sombra queda solo para seguimiento.

## Integridad, reproducibilidad y recuperación

La auditoría anterior señaló tres problemas en M1.1–M1.3 (`compra_m11.py`, `compra_m12.py` y `compra_m13.py`) y **siguen presentes allí**:

- **A.** `artefacto.json` de M1.1 no se compara con el candidato congelado.
- **B.** `desarrollo.json` y `seleccion.json` no entran en el sello.
- **C.** Si un fallo ocurre entre métricas y decisión, el reintento no completa la decisión.

M2 no reutiliza esos evaluadores, así que no los modifiqué ni reescribí sus ejecuciones históricas. M2 los evita con [`modelos/ejecucion.py`](../modelos/ejecucion.py):

- `congelacion.json` es el último archivo que se escribe. Guarda el SHA-256 de cada archivo de evidencia y un sello sobre todo el marcador:
  - configuración y protocolo;
  - `datos.json` (identidad, cobertura por fuente, fronteras y conteos);
  - `seleccion.json`;
  - los 6 candidatos y `artefacto.json`;
  - `predicciones_validacion.csv` y `entorno.json`.

  Las fechas reales quedan aparte del sello, para que repetir otro día sea idempotente.
- **Verificación antes de cada evaluación**, también en los reintentos:
  - las huellas de toda la evidencia;
  - el protocolo;
  - artefacto principal = candidato elegido en `seleccion.json` = huella congelada.

  Un cambio se rechaza con el nombre del archivo y nunca se recalcula la huella. Probado alterando:
  - la selección;
  - las predicciones de validación;
  - `datos.json`;
  - la congelación;
  - el artefacto sustituido por otro candidato;
  - el artefacto resellado.
- **Publicación de la evaluación:** métricas, predicciones y decisión se escriben de forma atómica y el marcador `evaluacion.json` va al final.
  - Si la evaluación se interrumpe después de las métricas, el reintento la completa sin borrar nada.
  - Repetirla es idempotente.
  - Un resultado distinto no sobrescribe al existente.
- **Datos o configuración distintos** exigen otra carpeta de ejecución.
- **Decisión.** `decision.json` identifica:
  - la huella y versión del artefacto evaluado;
  - el candidato;
  - el sello de congelación y la huella del protocolo.

  Las métricas y la puntuación usan ese mismo artefacto.
- **Reproducibilidad:** `ejecucion-002`, entrenada en otra carpeta, tiene el mismo sello (`93db3f18…`), los mismos archivos y la misma evaluación. Repetir la evaluación de `ejecucion-001` devuelve el mismo sello.
- **Equivalencia:** la probabilidad de sklearn y la del artefacto recargado desde JSON difieren como máximo 2,2 × 10⁻¹⁶. La tolerancia es 10⁻⁹.

## Integración

### C2 (`predicciones_clientes`, clave `cliente_id + modelo_id`)

- **Filas de inactividad.** Llevan:
  - `modelo_id = inactividad_60d` y `version_modelo`;
  - `corte` y `datos_hasta`;
  - `probabilidad`;
  - `horizonte_dias = 60` y `umbral_frio_dias = 90`;
  - `estado`, `recencia_dias`, `poblacion`, `posicion` y `motivos`.
- **Validador.** Comprueba:
  - tipos y rangos;
  - claves únicas;
  - `estructural` solo con recencia 0–29 y probabilidad 0 exacta;
  - `estimado` y `modelo_no_disponible` solo con recencia 30–89;
  - ya fríos como `no_elegible`;
  - `sin_historial` sin recencia.
- **Coexistencia con compra.** `compra_30d` y su coherencia con `agenda.prob_compra_30d` no cambian. Las dos filas de un mismo cliente conviven, y las consultas de compra filtran por `modelo_id`.
- **Cierre operativo** (`pipeline/generar.py`). Publica filas `inactividad_60d` **solo** si el registro tiene una versión **operativa** autorizada de ese modelo. Hoy no hay ninguna, así que el cierre no cambia y lo indica en `calidad.modelo_inactividad`.
- **Publicación en sombra.** Las variantes experimentales se publican aparte, como `publicacion_sombra` con `operativa: false`: `modelos.cli puntuar --modelo inactividad_60d`. Se validan con el mismo contrato.

### API y vista (solo internas)

- **Permisos.** `prevencion.ver` tiene los mismos roles que la cartera (Operaciones, Ventas y Gerencia). El rol empresa recibe 403 y el portal no expone el riesgo.
- **Importar la sombra:** `POST /api/prevencion/sombra` (Operación). Una publicación idéntica se importa una sola vez y una alterada se rechaza.
- **Lista experimental:** `GET /api/prevencion`. Muestra:
  - el estado del experimento y su decisión;
  - la posición por riesgo y por mayor recencia;
  - la acción C1 sin cambios;
  - la cobertura por población.
- **Ficha.** `GET …/clientes/{id}` añade `inactividad_sombra`, marcado como experimental. La acción, los motivos y la estimación de compra no cambian.
- **Vista.** `#/prevencion`, «Prevención (experimental)», más un bloque en la ficha.

### Episodios de prevención (`episodios_prevencion`)

- **Identidad:** `prevencion:<cliente>:<último día de compra>`. No depende de la versión del modelo: un cierre con otra versión y el mismo ancla no crea otro episodio.
- **Bandera `prevencion_tareas`:** desactivada por defecto. Sin ella, `POST /api/prevencion/sincronizar` solo devuelve los propuestos y no escribe.
- **Política:** los 10 primeros de la población aprendible estimada.
  - Si el cliente ya tiene un seguimiento abierto, se añade el motivo «Prevenir inactividad (experimento en sombra)» a ese seguimiento.
  - Si no, se crea una tarea `comprobacion` con prioridad posterior a las acciones C1.
- **Repetir** no duplica tareas, evidencias ni eventos.
- **Cierre por compra.** Una compra nueva cierra el episodio (`cerrado_compra`, con un evento de observación, no de atribución). Llegar a frío lo cierra como `cerrado_frio`.
- **Otro episodio** exige volver a cumplir la política con un ancla nueva.
- **Datos humanos:** estado, responsable, contacto, siguiente paso y resultado no se modifican nunca.

## Comandos ejecutados (2026-11-23)

```powershell
python -m modelos.cli entrenar --modelo inactividad_60d --datos salida/a01 --salida salida/experimentos/inactividad_60d/ejecucion-001
python -m modelos.cli entrenar --modelo inactividad_60d --datos salida/a01 --salida salida/experimentos/inactividad_60d/ejecucion-002   # reproducibilidad
python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d/ejecucion-001
python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d/ejecucion-001   # repetición idempotente
python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d/ejecucion-002
python -m modelos.cli puntuar --modelo inactividad_60d --ejecucion salida/experimentos/inactividad_60d/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/inactividad_60d/2026-10-31
```

- **Preparación:** `salida/a01` ya existía (`python -m modelos.cli preparar --datos Green_Services_Recursos_de_Prueba --salida salida/a01`). No se regeneró.
- **Demostración aislada** (base SQLite temporal, cierre real de 2026-10-31, registro en solo lectura): guardada en `salida/demostraciones/inactividad_60d_prevencion.json`.
  - Con la bandera desactivada no se escribió nada y se propusieron 10 clientes.
  - Activada, los 10 ya tenían un seguimiento de cobertura abierto: se añadió el motivo (10 compartidos, 0 tareas nuevas).
  - Repetir no cambió nada.
- **Puntuación en sombra del 2026-10-31:** 41 estimados, 38 estructurales y 41 ya fríos.

## Piloto prospectivo

La congelación real fue el **2026-11-23** (`congelacion.json`, campo `volatiles.fechas_piloto`).

| Paso | Fecha o condición |
|---|---|
| Primer corte posterior a la congelación | **2026-11-30** |
| Cobertura necesaria para puntuarlo | Ventas completas hasta 2026-11-30, declaradas en el manifiesto A01 o con `--observado-hasta` |
| Evaluación | Solo con los 60 días completos: cobertura hasta **2027-01-29** |
| Cortes siguientes | Cada fin de mes; cada uno se evalúa 60 días después |

**Qué medir:**
- alertas pertinentes (eventos dentro de las 10 primeras) y falsas alarmas;
- sensibilidad al cupo frente a mayor recencia sobre los mismos clientes;
- Brier frente a la tasa de ajuste;
- cobertura y estados;
- **tiempo de gestión** por seguimiento;
- contacto, causa comercial identificada, compra posterior y primer cruce de 90 días.

**Tres resultados distintos:**
- **Integración correcta:** contrato, permisos, episodios y ausencia de duplicados. Está demostrada.
- **Calidad predictiva:** **no** está demostrada; hoy la recencia es mejor.
- **Utilidad comercial:** requiere el piloto. Una compra posterior a un contacto no demuestra que el seguimiento evitó la inactividad. Para medir el efecto haría falta una asignación estable por cliente, autorizada por la empresa.

## Limitaciones y qué permitiría continuar

- **Datos.** 120 clientes sintéticos, dos meses de comprobación y clientes repetidos (58 únicos). Los intervalos son amplios.
- **Variables.** Solo describen el ritmo de compra, y la recencia ya contiene casi toda esa señal.
- **Evidencia nueva que permitiría seguir:**
  - datos empresariales con más clientes y meses;
  - señales comerciales con disponibilidad histórica: contactos, cotizaciones, renovaciones e incidencias de servicio;
  - coberturas con fecha de registro;
  - un piloto prospectivo con tiempos de gestión.

  Cualquier variante nueva necesita otra `version_protocolo` y otra ejecución.
- **Sin promoción.** No se promovió ni registró nada:
  - `var/modelos/compra_30d` conserva `v1` operativa y `v2` en sombra;
  - no existe `var/modelos/inactividad_60d`;
  - no se modificaron registros humanos.

## M2.1 · Candidatos estructurales (protocolo `m21-protocolo-v1`)

**Implementado y evaluado el 23 de noviembre de 2026, con decisión «inconcluso».** Mayor recencia sigue siendo el mejor criterio para el cupo de 10.

### Por qué y qué cambia

Un cliente con *r* días sin comprar pasa a frío si no compra en los próximos `w = 90 − r` días. M2 trataba la recencia como una variable más. M2.1 prueba cuatro familias predeclaradas que usan esa estructura. Todas se ajustan solo con el bloque de ajuste y se eligen en validación.

| Familia | Fórmula | Hiperparámetro |
|---|---|---|
| Poisson | `p = exp(−λ·w)`, con `λ = (días de compra en 180 d + m·λ0) / (exposición + m)` | m ∈ {30, 90, 180} días |
| Supervivencia | `p = S(90) / S(r)`: curva Kaplan–Meier de la cartera hasta 2026-02-28, contraída con los intervalos del propio cliente | k ∈ {1, 3, 10} |
| Logística reducida | ventana restante, días de compra en 180 d, compras esperadas en la ventana, relación recencia/ciclo, historia insuficiente | C ∈ {0,1; 1; 10} |
| Logística con instalaciones | la reducida, más instalaciones vigentes y si la renovación (45 días antes del fin) se abre antes del cruce | C ∈ {0,1; 1; 10} |

Detalles de cada familia:

- **Poisson y supervivencia**: puntúan solo con la biblioteca estándar.
  - Formatos nuevos: `jacomind.inactividad_poisson.v1` y `jacomind.inactividad_supervivencia.v1`, en `modelos/inactividad_m21.py`.
  - Solo admiten `inactividad_60d`, horizonte 60, umbral 90 y `umbral` nulo.
- **Logísticas**: usan el formato existente y las variables `inactividad_60d-variables-v2`.
- **Base instalada**: se usa bajo un **supuesto declarado y no verificable**: cada instalación, con su `fecha_fin`, se conoce desde su `fecha_inicio`.

Se conservan de M2:

- la etiqueta, las poblaciones, los bloques y las fronteras (comprobadas por código);
- las métricas, las metas y la regla de decisión;
- el publicador sellado e idempotente.

**Advertencia de método.** M2.1 se diseñó después de conocer los resultados de M2 en validación y comprobación. Por eso la comprobación de julio y agosto es **exploratoria y reutilizada**: no puede confirmar una mejora. Solo pueden hacerlo el piloto prospectivo o datos empresariales.

### Resultados

**Validación (abril y mayo; selección):**

| Candidato | Precisión media a 10 | Sensibilidad a 10 | Brier |
|---|---:|---:|---:|
| Poisson, m=180 (**elegido**) | 0,80 | 0,267 | 0,252 |
| Supervivencia, k=10 | 0,80 | 0,267 | 0,252 |
| Poisson, m=90 y m=30 | 0,80 | 0,267 | 0,255 y 0,259 |
| Mejor logística (reducida, C=0,1) | 0,75 | 0,250 | 0,251 |
| Mayor recencia | 0,75 | 0,250 | — |
| Constante | — | — | 0,261 |

- Poisson m=180 empata en precisión con supervivencia k=10.
- Gana por Brier (diferencia en la cuarta cifra decimal).

**Comprobación histórica (julio y agosto; 69 casos aprendibles, 35 eventos):**

| Método | Aciertos a 10 (jul / ago) | Precisión media a 10 | Sensibilidad a 10 | Aciertos a 20 | Brier |
|---|---|---:|---:|---:|---:|
| M2.1 (Poisson, m=180) | 6 / 8 | 0,70 | 0,400 | 25 | **0,226** |
| M2 congelado | 6 / 7 | 0,65 | 0,371 | 25 | 0,235 |
| **Mayor recencia** | 7 / 9 | **0,80** | **0,457** | 24 | — |
| Constante | 5 / 4 | 0,45 | 0,257 | — | 0,254 |

- **Incertidumbre** (remuestreo de clientes, 2.000 réplicas):
  - diferencia frente a mayor recencia: −0,10, con IC 95 % [−0,15; +0,05];
  - Brier del candidato menos el de la constante: IC [−0,070; +0,013].
- **Probabilidades**: media 0,500 frente a una tasa observada de 0,507. En cada mes la media también coincide (0,504/0,513 y 0,494/0,500). Con 69 casos, las bandas no son monótonas.
- **Contexto** (no cambia la selección): ningún candidato supera a mayor recencia en la comprobación.
  - El mejor es la logística reducida, con 0,75.
  - Supervivencia queda entre 0,60 y 0,65.

### Decisión: **inconcluso**

- **Se cumple**: los mínimos de evidencia y un Brier no peor que la constante.
- **No se cumple**:
  - la mejora de 5 puntos (sale −10);
  - que el IC excluya 0;
  - que la sensibilidad no baje (0,400 frente a 0,457).
- **No es «rechazado»**: el IC de la diferencia incluye 0.

**Lectura.** M2.1 mejora a M2: más precisión (0,70 frente a 0,65) y la mejor calibración de todos. Aun así, en estos datos sintéticos la señal útil para el cupo de 10 parece estar casi entera en la recencia. Para ordenar llamadas se mantiene mayor recencia. La probabilidad de M2.1 sirve como estimación calibrada del riesgo en la ficha, en sombra.

### Comandos (2026-11-23)

```
python -m modelos.cli entrenar --modelo inactividad_60d --config modelos/config/inactividad_60d_m21.json --datos salida/a01 --salida salida/experimentos/inactividad_60d_m21/ejecucion-001
python -m modelos.cli entrenar --modelo inactividad_60d --config modelos/config/inactividad_60d_m21.json --datos salida/a01 --salida salida/experimentos/inactividad_60d_m21/ejecucion-002
python -m modelos.cli evaluar --ejecucion salida/experimentos/inactividad_60d_m21/ejecucion-001 --m2 salida/experimentos/inactividad_60d/ejecucion-001   (dos veces, y también sobre la 002)
python -m modelos.cli puntuar --modelo inactividad_60d --ejecucion salida/experimentos/inactividad_60d_m21/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/inactividad_60d_m21/2026-10-31
```

### Verificación

- **Reproducibilidad**:
  - las ejecuciones 001 y 002 tienen el mismo sello (`46f89ca4…`) y el mismo artefacto (`inactividad_60d-m21-poisson-180-27007e4d`);
  - repetir la evaluación es idempotente (sello `385b53f2…`).
- **Sombra 2026-10-31**: 41 estimados, 38 estructurales y 41 ya fríos (sello `6dd90486…`). Está en una carpeta propia; la sombra de M2 no cambia.
- **Pruebas**: `tests/modelos/test_m21.py`, con 12 pruebas. Cubren:
  - variables y frontera de renovación;
  - fórmulas, incluido que un intervalo de exactamente 90 días no es evento;
  - artefactos alterados o de otro modelo;
  - puntuación sin scikit-learn;
  - doce candidatos, artefacto principal ligado a la selección y reproducibilidad;
  - evidencia alterada, otra configuración en la misma carpeta y sombra válida según C2;
  - registro y ejecuciones de M2 intactos.
- **Suites**: A 200 aprobadas; B 139 aprobadas y 1 omitida; integración 10 aprobadas y 1 omitida (con `JACOMIND_DATOS` apuntando al paquete).
- **CLI** (código 2): artefacto de M2.1 usado como compra, configuración de M2 sobre una carpeta de M2.1 y corte sin cobertura.
- **Archivos protegidos**: los 149 tienen huellas idénticas antes y después (registro, ejecuciones M1, ejecuciones y sombra de M2, lote A01 y CSV originales).
- **Sin promoción**: no existe `var/modelos/inactividad_60d`.

### Vista con M2.1 y comparación (2026-11-23)

- `puntuar --con-resumen` añade a la sombra un resumen de la comprobación histórica ya publicada y verificada (`modelo.decision.resumen`). La sombra anterior no se sobrescribe: la nueva está en `salida/sombra/inactividad_60d_m21/2026-10-31-con-resumen/` (sello `3ff8666c…`).
- `python -m api sombra RUTA` importa una publicación en sombra en la base de la aplicación. Equivale a `POST /api/prevencion/sombra` y no cambia la agenda.
- La vista `#/prevencion` muestra el panel «¿Qué tan bien funciona?», con el modelo frente a mayor recencia:
  - aciertos en los 10 primeros por mes y de media;
  - aciertos en los 20 primeros;
  - calibración y Brier;
  - intervalo de confianza, presentado como orientativo porque los datos son sintéticos y el periodo ya estaba visto.
- Las señales de cada cliente incluyen la renovación de una instalación cuando se abre antes del cruce.
- Se comprobó en el navegador con una base temporal (`python -m api demo` seguido de `python -m api sombra`).

## Monitoreo (24-11-2026)

M2: estimados, estructurales y abstenciones por separado (un estado estructural no es un fallo); desempeño a 60 días con Brier y precisión al cupo frente a recencia. Ver [monitoreo de modelos](monitoreo-modelos.md#b-monitoreo-de-m1m6).
