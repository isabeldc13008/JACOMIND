# Modelo de compra a 30 días (A04 / M1)

Plan: [M1 compra a 30 días](plan/modelos/01-compra-30-dias.md) · Base: [base común](plan/modelos/00-base-comun.md) · Código: [`modelos/`](../modelos/)

## Resumen

| | Versión | Estado en `var/modelos` | Uso |
|---|---|---|---|
| Referencia original A04 | `A04-logistica-reglas-v1` (registro `v1`) | **operativo** | Alimenta `agenda.prob_compra_30d` y `predicciones_clientes` |
| Candidato M1 | `compra_30d-m1-a-c10-b8799da6` (registro `v2`) | **sombra** | Solo se puntúa y compara; no cambia la agenda |
| Ranking por recencia | — | comparador | Referencia del piloto; no es una probabilidad y no rellena C1 |

Decisión de la comprobación histórica: **inconcluso**. El candidato iguala la precisión a 10 del ranking por recencia (17/30), supera a la regresión original (13/30) y mejora el Brier frente a la tasa constante. No alcanza la meta de +5 puntos sobre recencia y queda por debajo de ella a 20 y en average precision. Con datos sintéticos el estado máximo es sombra.

Líneas experimentales posteriores: [M1.3](modelo-compra-m13.md) (supervivencia de intervalos y ponderación temporal con ajuste de nivel; ambos inconclusos; el ajuste de nivel da la mejor probabilidad en julio–septiembre, de forma exploratoria), [M1.2](modelo-compra-m12.md) (orden del cupo por fusión recencia + modelo; inconcluso: 52/100 frente a 54/100 de recencia en la validación temporal) y [M1.1](modelo-compra-m11.md) (variables de ciclo, boosting y calibración sin fuga). **Ningún candidato M1.1 mejora las referencias** (16/30 frente a 17/30 de recencia y de M1 v2; decisión inconcluso); no se registra ni se promueve.

## Modo demostración: M1.3 «P» operativa como `v3` (23-11-2026)

Después de `v2`, y por decisión del responsable del proyecto, pasó a operativa la variante «P» de [M1.3](modelo-compra-m13.md). Es una regresión con ponderación temporal y ajuste de nivel al último corte maduro (2026-06-30).

- **Artefacto**: `salida/experimentos/compra_30d_m13/ejecucion-001/artefacto_P.json`, huella `b2814b98…`, con la congelación de M1.3 verificada antes de registrarlo.
- **Comando**: `promover-demo --version v3 --artefacto …`.
- **Comprobación histórica** (julio–septiembre, sintética y exploratoria):
  - 17 de 30 aciertos entre los 10 primeros, igual que `v2` y mayor recencia; `v1` acierta 13;
  - 32 entre los 20 primeros;
  - Brier 0,221, el mejor junto a «P solo nivel»;
  - probabilidad media del 34,9 % frente al 36,7 % observado. `v2` daba 46,8 %.
- **Agenda del 2026-10-31**: «Revisar oportunidad de recompra» baja a 3 clientes, con estimación media del 33,4 %. Con el mismo umbral de 0,40, `v2` marcaba 15 y `v1` 12. Reactivación y cobertura no cambian.
- **Volver atrás**: `revertir --estado operativo` pasa a `v2`; `revertir --estado operativo --a v1` vuelve a la referencia.

## Modo demostración: v2 operativa (23-11-2026), sustituida por `v3`

Por decisión del responsable del proyecto («esto es un proyecto demo»), `v2` pasó a operativa con datos sintéticos.

- **Por qué v2**: en la comprobación histórica acierta 17 de 30 entre los 10 primeros. `v1` acierta 13 de 30 y mayor recencia 17 de 30.
- **Regla del registro** (`modelos/registro.py`): sin el modo demostración se sigue exigiendo una evaluación con datos empresariales. El modo:
  - está apagado por defecto y se activa de forma explícita, con actor y motivo;
  - solo admite autorizaciones con `decision = demostracion` y `aprobado_por`;
  - deja el puntero marcado con `origen_datos = sintetico`.
- **Al leer**: si el modo se apaga, la versión de demostración deja de servirse. Para apagarlo hay que revertir antes.
- **Agenda del 2026-10-31**: cambian 3 de 120 clientes, de «Seguimiento habitual» a «Revisar oportunidad de recompra». Reactivación y cobertura no cambian.
- **Limitación conocida**: v2 sobrestima en julio–septiembre (media 46,8 % frente a 36,7 % observado). Su umbral de 0,40 maximiza el F1, no un cupo.

```
python -m modelos.cli modo-demo --activar --actor "..." --motivo "..."
python -m modelos.cli promover-demo --version v2 --aprobado-por "..." --motivo "..."
# volver atrás:
python -m modelos.cli revertir --estado operativo --a v1
python -m modelos.cli modo-demo --apagar --actor "..." --motivo "..."
```

## Correcciones de la segunda auditoría (23-11-2026)

- **Publicación del cierre:** varios `os.replace` no forman una operación atómica. Ahora `_publicar_archivos` usa este procedimiento de recuperación verificable:
  1. Serializa todo en `.publicando-*`.
  2. Añade al manifiesto la huella SHA-256 de cada tabla.
  3. Copia la versión visible a `.respaldo-*`.
  4. Escribe el diario `.publicacion_en_curso.json`.
  5. Sustituye las tablas y, al final, el manifiesto.

  Ante un fallo restituye la versión anterior. Si el proceso muere, el diario permanece: el validador C2 rechaza el directorio y la siguiente ejecución (o `python -m pipeline.generar --recuperar --salida <dir>`) lo restituye. Además, el validador comprueba la huella de cada tabla.
- **Referencia histórica:** la excepción `referencia_vigente` solo se concede a la huella exacta de un artefacto del catálogo versionado `modelos/config/referencias_historicas.json` (hoy `A04-logistica-reglas-v1`, `b6c3d4a8…`). Se comprueba al promover, revertir y leer el registro; el texto de la decisión o el nombre de versión no bastan.
- **Identidad de selección del piloto:** `seleccion_id = corte|s-<huella>` combina corte, huellas de ambos artefactos, revisiones de datos de ambas puntuaciones, huella de la cohorte, cupo, política de selección y reconciliación. El lote de observación no forma parte de la identidad: incorporar resultados no exige una selección nueva, aunque el corte ya tenga otras. Los identificadores anteriores (`corte|versión|versión|kN`) se migran solo si todas sus filas coinciden con la selección recalculada (`seleccion_id_anterior` conserva el antiguo); si no, quedan como selección aparte.
- **Cobertura al reutilizar un lote:** A01 compara por separado la identidad del contenido (huellas de origen) y la declaración de cobertura. Con los mismos CSV y otra declaración crea una revisión nueva (`reutilizado`, `contenido_de_revision`, `cobertura_historial` con `primera_declaracion`, `declaracion_actualizada` o `declaracion_retirada`) y guarda la anterior en `historial_lotes.jsonl`. Una declaración incoherente con las transacciones (`COBERTURA_INCOHERENTE`) deja el lote como `fallido` y conserva la revisión válida. Retirar la declaración no conserva la fecha anterior.
- **Evaluación rechazada:** `evaluar` comprueba conflictos de métricas y decisión antes de escribir nada; un rechazo ya no reescribe `metricas_*.json` ni `predicciones.csv`.

## Qué pregunta responde

Probabilidad de que un cliente con compras previas registre al menos una venta confirmada en `(corte, corte + 30 días]`. Ayuda a ordenar seguimientos. No estima el efecto de contactar al cliente ni el valor de la venta. Las señales que acompañan cada estimación describen el historial observado y no son causas demostradas de compra.

## Datos y tiempo

- **Revisión aceptada (A01):** entrenamiento, evaluación, puntuación y cierre leen `<a01>/publicado`, nunca los CSV originales. Un lote `fallido` no se usa. Un lote `pendiente_revision` solo se usa con `--aceptar-parcial`, que lee las filas aceptadas de `lote_actual/`, registra las exclusiones y no sustituye a `publicado/`. El CSV opcional con incidencias se valida aparte y nunca se suma a las ventas.
- **Cobertura declarada:** `datos_observados_hasta` se toma, por orden, del argumento `--observado-hasta`, del manifiesto A01 (`datos_observados_hasta.ventas`, declarable en la configuración de la carga) o de una declaración registrada en `modelos/config/coberturas_declaradas.json` que solo aplica si las siete huellas de origen del lote coinciden. En el paquete sintético es 2026-10-31 (`parametros_prueba.json`), con disponibilidad por fecha del evento. Un lote distinto sin declaración tiene cobertura desconocida y no se puntúa. La última venta no se usa como prueba de completitud; una venta posterior a la cobertura declarada rechaza el lote.
- **Fotografía:** una fila por cliente y corte de fin de mes, con `cliente_id`, `corte`, `revision_datos`, `huella_datos`, `version_variables` (`compra_30d-variables-v1`), `datos_observados_hasta`, `elegibilidad` (`elegible`, `sin_historial`, `alta_posterior`) y `estado_etiqueta` (`madura`, `pendiente`, `no_aplica`).
- **Etiqueta:** 1 si hay venta confirmada en `(corte, corte + 30]`; 0 si `corte + 30 <= datos_observados_hasta` y no la hubo; pendiente en otro caso.
- **Ventanas** (con `d = corte − fecha` en días): variables con `fecha <= corte`; ventana de k días `0 <= d < k`; los 30 días anteriores, `30 <= d < 60`. Dos ventas del mismo día cuentan como dos operaciones y un solo día de compra. Los intervalos se miden entre días distintos y exigen al menos tres; si no, quedan nulos con `historia_insuficiente = 1`. Los importes COP siguen la convención A02: importe por operación redondeado a dos decimales antes de sumar.

## Variables y combinaciones (fijadas antes de evaluar)

| Grupo | Variables | Transformación |
|---|---|---|
| A | `recencia_dias`, `frecuencia_30d`, `frecuencia_90d`, `historial_n` | log1p en recencia e historial |
| B | `frecuencia_180d`, `dias_compra_distintos`, `cambio_frecuencia_30d` (diferencia absoluta), `intervalo_mediano_dias`, `intervalo_dispersion_dias` (MAD), `historia_insuficiente` | log1p en días distintos e intervalos |
| C | `importe_cop_90d`, `ticket_medio_cop`, `participacion_recurrentes` | log1p en importes |

Combinaciones: A (4 variables), A+B (10) y A+B+C (13). La imputación por mediana y el escalado (media y desviación poblacional) se ajustan solo con las filas de ajuste. La misma función `aplicar_transformaciones` sirve en el ajuste y en la inferencia. Se excluyen del experimento principal el ID de cliente, ciudad, sector, canal y coberturas.

## Protocolo

| Bloque | Cortes | Población de recompra | Positivos |
|---|---|---:|---:|
| Ajuste | 2025-03-31 a 2026-04-30 (14) | 1.205 de 1.680 fotografías (excluye 298 con alta posterior y 177 sin historial) | 620 |
| Validación | 2026-05-31 y 2026-06-30 | 240 (120 clientes) | 99 |
| Comprobación histórica | 2026-07-31 a 2026-09-30 | 360 (120 clientes; 0 exclusiones; 0 pendientes) | 132 |

Fronteras verificadas en código: las etiquetas del ajuste maduran el 2026-05-30, antes de la primera inferencia de validación (2026-05-31). Las de validación maduran el 2026-07-30, antes de la primera inferencia de prueba (2026-07-31).

Rejilla: 3 combinaciones × C ∈ {0,1; 1; 10}, con `LogisticRegression` de scikit-learn (L2, lbfgs, `tol` 1e-10, sin pesos de clase, semilla 20261123). Selección en validación por precisión media a 10; los desempates, en orden, son AP media mensual, Brier, menos variables y menor C. El umbral maximiza el F1 de validación en la rejilla 0,05–0,95; en empate se toma el mayor. El candidato se congeló antes de leer julio–septiembre y no se reentrenó con validación.

| Validación (2 meses) | Precisión media a 10 | AP media | Brier |
|---|---:|---:|---:|
| **A, C = 10 (elegido)** | 0,55 (11/20) | 0,5114 | 0,2415 |
| A, C = 0,1 / 1 | 0,55 | 0,5113 | 0,2418 / 0,2416 |
| A+B, C = 10 / 1 / 0,1 | 0,50 / 0,50 / 0,45 | ≈0,507 | ≈0,238 |
| A+B+C, C = 1 / 10 / 0,1 | 0,45 / 0,45 / 0,40 | ≈0,509 | ≈0,237 |
| Regresión original congelada | 0,50 | 0,4944 | 0,2399 |

Artefacto elegido: variables A con log1p en recencia e historial; intercepto 0,0588; pesos −0,0965 (recencia), 0,0455 (f30), 0,1056 (f90) y −0,0764 (historial); umbral 0,40. La inferencia desde JSON difiere de scikit-learn en 1,1 × 10⁻¹⁶ (tolerancia declarada: 10⁻⁹).

## Referencia original reproducida

Se ejecutó `pipeline/modelo_compra.py` sin cambios sobre la revisión aceptada. Todos los controles coinciden: 1.382 / 240 / 360 fotografías; umbral 0,4; TP 120, TN 51, FP 177, FN 12; precisión 0,4040, sensibilidad 0,9091, F1 0,5594. Primeros diez por mes: probabilidad 5, 4 y 4; recencia 5, 7 y 5. La regla `frecuencia_30d > 0` obtiene precisión 0,5214 y F1 0,5368. El artefacto JSON `v1` reproduce la fórmula original con diferencia 0,0 en todas las fotografías con historial. La agenda y todas las tablas de octubre son idénticas a las generadas antes del cambio.

## Comprobación histórica (exploratoria, julio–septiembre de 2026)

Mismas 360 fotografías para todos los métodos. Orden: puntaje descendente y desempate por `cliente_id`. Denominador `min(K, n)`. AP: suma por escalones sin interpolar sobre ese orden. Brier: media de `(p − y)²`.

| Método | Aciertos top 10 (jul/ago/sep) | Precisión media a 10 | Top 20 | Precisión a 20 | Sensib. a 10 / 20 | AP media mensual | Brier |
|---|---|---:|---|---:|---|---:|---:|
| **Candidato M1** | 5 / 7 / 5 = 17 | **0,567** | 10 / 11 / 9 = 30 | 0,500 | 0,129 / 0,228 | 0,521 | **0,2306** |
| Ranking por recencia | 5 / 7 / 5 = 17 | 0,567 | 13 / 11 / 10 = 34 | 0,567 | 0,129 / 0,258 | 0,541 | — |
| Regla compra 30 días | 7 / 6 / 3 = 16 | 0,533 | 12 / 11 / 6 = 29 | 0,483 | 0,119 / 0,216 | 0,523 | — |
| Original congelado | 5 / 4 / 4 = 13 | 0,433 | 13 / 8 / 9 = 30 | 0,500 | 0,099 / 0,228 | 0,475 | 0,2316 |
| Tasa constante (0,5145) | 5 / 5 / 4 = 14 | 0,467 | 9 / 6 / 10 = 25 | 0,417 | 0,106 / 0,194 | 0,409 | 0,2541 |

Positivos/negativos por mes: 47/73, 47/73 y 38/82 (120 clientes únicos cada mes). La tasa constante y la regla ordenan sus empates por ID; su orden a 10 no tiene contenido predictivo.

Matriz al umbral elegido en validación (0,40): TP 130, TN 36, FP 192, FN 2. Precisión 0,4037, sensibilidad 0,9848, F1 0,5727, con 322 de 360 seleccionados. Para comparar, el original a 0,4 obtiene F1 0,5594 y la regla 0,5368. La política de F1 máximo seleccionó casi a todos tanto en validación (237 de 240) como en prueba, así que no sirve como cupo comercial. Cambiarla exige una versión nueva del protocolo y otra comprobación.

Calibración del candidato (banda: n, media estimada → tasa observada): 0,3–0,4: 38, 0,393 → 0,053; 0,4–0,5: 215, 0,446 → 0,358; 0,5–0,6: 102, 0,535 → 0,480; 0,6–0,7: 5, 0,624 → 0,800. Sobrestima: la probabilidad media es 0,468 y la tasa observada 0,367, porque la tasa de compra del ajuste (0,515) es mayor que la de julio–septiembre. No se recalibró: no hay bloques temporales fuera de ajuste suficientes para entrenar un calibrador sin reutilizar validación.

Incertidumbre (bootstrap de 1.000 remuestreos de clientes completos): AP candidato − recencia = −0,011 [−0,047; 0,024]; Brier candidato − constante = −0,023 [−0,032; −0,015].

Agenda operativa frente a ranking puro: si se restringe a los clientes que la agenda no asigna antes a reactivación o cobertura (26, 23 y 20 por mes; 69 fotografías), los diez primeros contienen candidato 7/3/6, recencia 8/5/6, regla 7/5/6 y original 7/3/5 compradores. Mejorar el ranking no cambia por sí solo la agenda, porque C1 aplica primero reactivación y cobertura.

Errores comerciales: en los tres meses, los falsos positivos del top 10 (5, 3 y 5) son clientes que compraron hace 0–18 días, con 2–7 operaciones en 90 días, y no recompran dentro del horizonte. Las primeras omisiones aparecen en las posiciones 11–28, con probabilidades entre 0,52 y 0,56, muy cercanas a la del décimo. El modelo separa poco a los clientes activos entre sí. El detalle por mes está en `errores_comerciales` de `metricas_comprobacion_historica.json`.

### Metas y decisión

| Meta (fijada en la configuración) | Resultado |
|---|---|
| +5 puntos de precisión media a 10 frente a recencia | No: +0,0 puntos |
| Ningún mes con 2 o más compradores perdidos frente a recencia | Sí: 0, 0 y 0 |
| Brier no peor que la tasa constante del ajuste | Sí: 0,2306 frente a 0,2541 |
| Calibración y tamaños visibles | Publicados arriba y en `metricas_*.json` |

**Inconcluso** (no rechazado: no queda 5 puntos o más por debajo de recencia y su Brier es mejor). Política recomendada:

- Mantener `v1` como operativo y el orden contractual de C1.
- Llevar el candidato `v2` solo en sombra.
- Usar el ranking por recencia como comparador del piloto a igual cupo.

Estos resultados son exploratorios: el periodo ya se había inspeccionado. Una validación independiente requiere cortes posteriores a la congelación real (2026-11-23): el primero es el 2026-11-30, que madura el 2026-12-30. La re‑evaluación con protocolo congelado (`ejecucion-002`) confirma el mismo dictamen.

## Fechas: congelación, disponibilidad, corte y maduración

| Concepto | Fecha | Significado |
|---|---|---|
| Congelación real del candidato | 2026-11-23 | `congelado_en` de `ejecucion-001` (y de `ejecucion-002`, que lo re‑congela con el formato nuevo) |
| Disponibilidad simulada | 2026-10-30 | `disponible_desde` del artefacto: último día en que maduró la comprobación histórica. Sirve para simular qué se habría conocido; no es una fecha real de uso |
| Cobertura del lote sintético | 2026-10-31 | Datos completos hasta esa fecha (declaración registrada del paquete) |
| Corte 2026-10-31 | **comprobación retrospectiva** | Anterior a la congelación real: no es evidencia prospectiva. Su horizonte terminaría el 2026-11-30 y el paquete no tiene esos datos |
| Primer corte prospectivo | **2026-11-30** | Primer fin de mes posterior a la congelación real; su horizonte termina el **2026-12-30** |

Puntuar un corte exige datos completos hasta el corte; evaluarlo exige datos completos hasta el final de su horizonte (corte + 30 días). Si se congela un modelo o protocolo nuevo, las fechas prospectivas se calculan desde esa nueva congelación (`congelacion.json → fechas`).

## Artefactos, registro e integración

- Ejecuciones: `salida/experimentos/compra_30d/ejecucion-001/` (original, formato de congelación 1) y `ejecucion-002/` (misma configuración y datos, formato 2: huella de protocolo, referencia, datos y sello). Ambas producen el mismo artefacto (`ddd52bc0…`, registrado como `v2`), las mismas métricas y el dictamen **inconcluso**. Cada una contiene `config.json`, `datos.json`, `referencia.json`, `referencia_artefacto.json`, `artefacto.json`, `seleccion.json`, `congelacion.json`, `entorno.json`, `metricas_comprobacion_historica.json`, `predicciones_validacion.csv`, `predicciones.csv` y `decision.json`.
- Protocolo congelado (formato 2): `congelacion.json` guarda la huella canónica de la configuración completa (objetivo, horizonte, bloques, población, variables y sus transformaciones, rejillas, política de umbral, métricas, referencias, metas y regla de decisión, más las versiones de código de variables, etiqueta, métricas y decisión), la huella del artefacto, de la referencia y de la revisión de datos, y un sello que las vincula. `evaluar` lo verifica antes de medir: cualquier cambio semántico (no de formato JSON) se rechaza y exige una `version_protocolo` y una ejecución nuevas; una decisión ya emitida no se sobrescribe; la validación no emite decisiones. `ejecucion-001` es heredada (sin huella): se puede leer y su artefacto se puede usar, pero no emite decisiones nuevas; `verificar-protocolo` compara su configuración con la vigente como **verificación posterior** (coincide; no prueba qué estaba congelado antes de evaluar).
- Artefacto: JSON numérico `jacomind.regresion_logistica.v1` con variables ordenadas, transformaciones, intercepto, pesos, umbral y política, fechas, huella SHA-256 y versión de variables. La carga rechaza formato o versión incompatibles, dimensiones distintas, valores no finitos, desviaciones no positivas y alteraciones de la huella.
- Registro: `var/modelos/compra_30d/` con versiones inmutables (`v1/`, `v2/`: artefacto, decisión inicial y origen) y `registro.json` (punteros `operativo`/`sombra`, historial y `autorizaciones`). Las autorizaciones son eventos: la decisión inicial más cada aprobación posterior (huella exacta, estado máximo, actor, fecha y procedencia), sin borrar ninguna; rige la última de esa huella. `sombra` requiere estado máximo sombra u operativo; `operativo` requiere estado máximo operativo, datos no sintéticos y `aprobado_por` (salvo la referencia heredada `v1`). Repetir una promoción no cambia nada; `revertir` deshace la última promoción hacia la versión anterior distinta y autorizada; `revertir --a` exige autorización vigente. Todo se valida antes de escribir y `registro.json` se reescribe de forma atómica. Un registro anterior sin `autorizaciones` se lee igual (no hay migración).
- Cobertura temporal (política única en `modelos/datos.py` para `puntuar`, `comparar` y el cierre): `--observado-hasta` explícito, o `datos_observados_hasta.ventas` del manifiesto A01, o una declaración registrada en `modelos/config/coberturas_declaradas.json` cuyas siete huellas de origen coincidan con el lote (hoy solo el paquete sintético). Un lote distinto sin declaración tiene cobertura **desconocida**: no hereda la fecha sintética ni se deduce de la última venta.
- Cierre (`pipeline/generar.py`): no entrena. Antes de calcular nada comprueba que la cobertura alcanza el corte; si no la alcanza, o es desconocida, termina con código 1 y un mensaje con la causa y la solución, sin escribir tablas (la publicación activa de B se conserva). El modo explícito `--sin-cobertura-verificada` publica con `cobertura.estado = no_verificada` y el modelo se abstiene. Carga la versión operativa (`--registro`, `JACOMIND_MODELOS` o `var/modelos`), escribe `agenda.prob_compra_30d`, `agenda.modelo {version, umbral}`, `predicciones_clientes` y `manifiesto.cobertura` (corte, `datos_observados_hasta`, fuente, estado). Las tablas se escriben en un área temporal y el manifiesto se mueve el último.
- Dependencias: `requirements-modelos.txt` (scikit-learn 1.7, numpy, scipy) solo para `entrenar` y `evaluar`. Puntuar, comparar, generar, la API y la aplicación usan la biblioteca estándar; una prueba lo verifica bloqueando esas importaciones.

## Comandos (desde la raíz; verificados el 2026-11-23)

```powershell
pip install -r requirements-modelos.txt                       # solo para entrenar/evaluar
# 1. Lote normalizado (A01). Un lote real debe declarar su cobertura en la configuración de la carga:
#    {"datos_observados_hasta": {"ventas": "AAAA-MM-DD"}, "tablas": {...}}  → --config-a01 archivo.json
python -m modelos.cli preparar --datos Green_Services_Recursos_de_Prueba --salida salida/a01
# 2. Reproducir la referencia y registrarla como operativa (inicialización explícita)
python -m modelos.cli reproducir-referencia --datos salida/a01 --salida salida/experimentos/compra_30d/referencia
python -m modelos.cli inicializar-referencia --datos salida/a01 --registro var/modelos --version v1
# 3. Entrenar, seleccionar (ajuste + validación) y congelar en una carpeta NUEVA
python -m modelos.cli entrenar --modelo compra_30d --datos salida/a01 --config modelos/config/compra_30d.json --salida salida/experimentos/compra_30d/ejecucion-002
# 4. Evaluar sin reajustar (verifica antes la congelación)
python -m modelos.cli evaluar --ejecucion salida/experimentos/compra_30d/ejecucion-002 --bloque comprobacion_historica
python -m modelos.cli verificar-protocolo --ejecucion salida/experimentos/compra_30d/ejecucion-001 --salida salida/experimentos/compra_30d/verificacion-ejecucion-001.json
# 5. Registrar para sombra (operativo se rechaza con código 2)
python -m modelos.cli promover --ejecucion salida/experimentos/compra_30d/ejecucion-002 --registro var/modelos --version v2 --estado sombra
# 6. Puntuar un corte cubierto por los datos (octubre: comprobación retrospectiva)
python -m modelos.cli puntuar --registro var/modelos --estado operativo --datos salida/a01 --corte 2026-10-31 --salida salida/puntuaciones/2026-10-31/operativo
python -m modelos.cli puntuar --registro var/modelos --estado sombra --datos salida/a01 --corte 2026-10-31 --salida salida/puntuaciones/2026-10-31/sombra
# 7. Generar y validar la publicación C1/C2 (un corte posterior a la cobertura se rechaza)
python -m pipeline.generar --datos Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/cierres/2026-10-31 --registro var/modelos
python -m contratos.validar --publicacion salida/cierres/2026-10-31
# 8. Comparar operativo, sombra y recencia a igual cupo; crea o ACTUALIZA el registro del piloto
python -m modelos.cli comparar --operativo salida/puntuaciones/2026-10-31/operativo --sombra salida/puntuaciones/2026-10-31/sombra --datos salida/a01 --salida salida/puntuaciones/2026-10-31/comparacion
# 9. Recuperar la versión anterior de un puntero, registrar aprobaciones y consultar el registro
python -m modelos.cli revertir --registro var/modelos --estado sombra
python -m modelos.cli autorizar --registro var/modelos --version vN --decision aprobacion.json --actor <responsable> --procedencia "<acta o ticket>"
python -m modelos.cli estado --registro var/modelos
```

`--observado-hasta AAAA-MM-DD` está disponible en `puntuar`, `comparar` y `pipeline.generar` para declarar la cobertura de un lote concreto. `revertir --estado operativo` en el registro real responde que no hay versión anterior (código 2), porque `v1` es la primera; la reversión del operativo está cubierta por `RegistroTests` y `RegistroCorreccionesTests`.

### Piloto en el primer corte prospectivo (2026-11-30)

```powershell
# a) Cuando exista el lote con datos completos hasta el 2026-11-30 (cobertura declarada):
python -m modelos.cli preparar --datos <lote_noviembre> --config-a01 <config_con_cobertura.json> --salida salida/a01-2026-11
python -m modelos.cli puntuar --registro var/modelos --estado operativo --datos salida/a01-2026-11 --corte 2026-11-30 --salida salida/puntuaciones/2026-11-30/operativo
python -m modelos.cli puntuar --registro var/modelos --estado sombra --datos salida/a01-2026-11 --corte 2026-11-30 --salida salida/puntuaciones/2026-11-30/sombra
python -m modelos.cli comparar --operativo salida/puntuaciones/2026-11-30/operativo --sombra salida/puntuaciones/2026-11-30/sombra --salida salida/puntuaciones/2026-11-30/comparacion
# b) Ventas completa contacto_realizado (si/no), fecha_contacto (AAAA-MM-DD), tiempo_minutos (entero) y resultado_contacto.
# c) Con un lote completo hasta el 2026-12-30 o después, se actualizan etiquetas sin perder lo anterior:
python -m modelos.cli comparar --operativo salida/puntuaciones/2026-11-30/operativo --sombra salida/puntuaciones/2026-11-30/sombra --datos salida/a01-2026-12 --salida salida/puntuaciones/2026-11-30/comparacion
```

## Sombra y piloto (preparado, no ejecutado)

- Octubre (corte 2026-10-31) es una **comprobación retrospectiva**: 120 clientes estimados por cada versión y 0 abstenciones; los diez primeros de operativo y sombra coinciden en 8 clientes y los de sombra y recencia en 5. Sus 120 etiquetas siguen **pendientes**: el lote solo cubre hasta el 2026-10-31 y el horizonte acaba el 2026-11-30.
- El primer corte prospectivo es el **2026-11-30** (horizonte hasta el **2026-12-30**). Aún no hay datos de ese corte: no hay puntuaciones prospectivas, contactos ni resultados.
- `comparar` evalúa la **cohorte puntuada originalmente** (las altas posteriores se ignoran y se cuentan), con etiquetas `madura`, `pendiente`, `datos_faltantes` o `no_aplica` por cliente; nunca convierte la falta de información en compra = 0, y publica denominadores (en lista, evaluados, excluidos) y motivos de pendientes. Exige el mismo corte, cohorte y revisión de datos en ambas puntuaciones (o `--reconciliar`, que usa la intersección y lo informa). El lote de observación puede ser posterior y tener otra huella.
- `piloto_registro.csv` separa columnas calculadas (selección, versiones, huellas, posiciones, cupos, etiqueta) de las humanas (`contacto_realizado`, `fecha_contacto`, `tiempo_minutos`, `resultado_contacto`). Cada ejecución lee y valida el archivo existente, conserva los campos humanos por (`corte`, `cliente_id`, `seleccion_id`), actualiza solo las etiquetas y sustituye el archivo de forma atómica. Claves repetidas, campos humanos inválidos o una selección recalculada distinta para la misma clave detienen la operación sin tocar el archivo. Una selección distinta del mismo corte exige `--nueva-seleccion` y se añade sin reasignar contactos; los seguimientos de clientes que salen de la población se conservan (`en_cohorte_actual = False`). El CSV anterior se migra al leerlo (se deriva `seleccion_id` y se completan las huellas).
- Compra observada, contacto y efecto causal son cosas distintas: un contacto nunca se convierte en etiqueta, y un comprador contactado no prueba que el contacto causó la compra.

## Limitaciones

- Cartera sintética de 120 clientes y comprobación ya inspeccionada: no evidencia rendimiento con clientes empresariales.
- Tres meses de comprobación con cortes del mismo cliente correlacionados: no demuestran estabilidad.
- Mide propensión, no el efecto causal del contacto. El umbral de F1 no es una política de Green.
- Coberturas, ciudad, sector y canal no forman parte del candidato; incorporarlos requiere reconstruir su disponibilidad histórica.
