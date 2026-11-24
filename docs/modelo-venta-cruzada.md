# M4 · Venta cruzada (`venta_cruzada`)

[Plan](plan/modelos/04-venta-cruzada.md) · [Base común](plan/modelos/00-base-comun.md) · Protocolo `m4-protocolo-v1` ([configuración](../modelos/config/venta_cruzada.json)) · Compatibilidad [`compat-v1`](../modelos/config/compatibilidad_productos.json)

**Qué hace.** Propone hasta tres productos que el cliente aún no tiene, con evidencia y restricciones verificables, para que Ventas los revise. El objetivo aprendido es la compra confirmada del producto en (C, C+60].

Esa compra no es aceptación de una oferta, ni efecto de la recomendación, ni sensibilidad a descuentos, ni necesidad comercial confirmada.

**Decisión (23-11-2026): inconcluso.** El modelo acierta en el primer producto el 13,3 %, frente al 12,1 % de popularidad, sobre un universo fijo de 240 cliente-corte. La diferencia es de +1,25 puntos, con IC 95 % por cliente de [−0,4; +3,3]. No alcanza la meta de 5 puntos.

Por regla predeclarada **se conserva popularidad con los mismos filtros**, y eso es lo que se publica en sombra.

- **Integración técnica**: completa.
- **Revisión comercial**: pendiente; no hay revisiones humanas.
- **Promociones y tareas**: ninguna promoción; tareas desactivadas.

## Código

| Pieza | Archivo |
|---|---|
| Candidatos, etiqueta, estadísticas al corte, variables, referencias, artefacto, ranking, muestra y sombra (biblioteca estándar) | `modelos/venta_cruzada.py` |
| Control A07, preparar, ajustar, evaluar, remuestreo y decisión | `modelos/venta_cruzada_experimento.py` |
| Protocolo y reglas de compatibilidad | `modelos/config/venta_cruzada.json`, `modelos/config/compatibilidad_productos.json` |
| Contrato C2 (`recomendaciones_productos`, `cobertura_recomendaciones`, `validar_recomendaciones`) | `contratos/publicacion.v1.schema.json`, `contratos/validar.py` |
| API: importación verificada, consulta, decisiones, episodios, revisión y tareas (desactivadas) | `api/venta_cruzada.py`, `api/migraciones/0004_venta_cruzada.sql` |
| Vista `#/venta-cruzada` y bloque en la ficha | `app/vistas/venta_cruzada.js` |
| Pruebas (19) | `tests/modelos/test_venta_cruzada.py` |

## 1. Control A07 por familia (reproducido)

`python -m modelos.cli preparar-modelo --modelo venta_cruzada …` reproduce exactamente `calidad.venta_cruzada` del cierre: **11 aciertos de 69 en coocurrencia y en popularidad**.

| Parámetro | Valor |
|---|---|
| Corte | 2026-09-01 (cierre 2026-10-31 menos 60 días) |
| Horizonte | compras en (2026-09-01, 2026-10-31] |
| Familias | Continuidad, Servicios, Software y Soporte (4) |
| Recomendaciones | K = 1; coocurrencia con soporte mínimo 3 |
| Población | 120 clientes con historial; 51 ya tienen las 4 familias |
| Abstención | los 51 clientes sin familia que recomendar **salen del denominador**: 69 de 120 |

No es comparable con M4: tiene otra granularidad (familia frente a producto), otro universo y un denominador que excluye abstenciones.

## 2. Datos, candidatos y etiquetas

- **Datos**:
  - fuente: revisión 1 aceptada de A01 (`salida/a01`), con huellas en `datos.json`;
  - ventas declaradas hasta el 2026-10-31.
- **Fuentes**:
  - ventas: historial hasta C y etiqueta;
  - base instalada: exclusión por cobertura;
  - productos: lista y nombres;
  - TRM: importe;
  - compras a proveedores: no se usan.
- **Catálogo**: un producto está disponible si alguien lo compró hasta C. Es un proxy sintético: la primera venta observada no demuestra la fecha de lanzamiento. Una aparición futura nunca habilita un producto hacia atrás, y esto está probado.
- **Candidato** (se construye antes de mirar el futuro): un producto disponible que el cliente no compró hasta C (incluido el día C), sin cobertura vigente y sin incompatibilidad ni requisito incumplido.
  - **Cobertura vigente**: `fecha_inicio ≤ C ≤ fecha_fin`. Sigue la convención de vigencia del proyecto (`pipeline/ficha.py`: `fecha_fin ≥ corte`) y la convención sintética de que la instalación se conoce desde `fecha_inicio`. Excluye aunque no haya factura: 80 de 243 instalaciones no tienen venta del producto.
  - **Compatibilidad**: `compat-v1` no contiene reglas, porque el paquete no las trae. **Todas las propuestas quedan `pendiente_revision`**; desconocido nunca se convierte en compatible. El motor de reglas (incompatible, requiere, compatible confirmado) está probado con datos de prueba.
- **Etiqueta**:
  - 1 si hay compra del producto en (C, C+60];
  - 0 si no la hay y el horizonte está completo;
  - pendiente en otro caso.

  Comprar otro producto no cambia la etiqueta, y varias compras cuentan como un positivo.

**Conteos:**

| Bloque | Cortes | Cliente-corte (universo) | Clientes | Pares | Positivos | Cliente-corte sin candidatos | Exclusiones: ya comprado / cobertura vigente |
|---|---|---:|---:|---:|---:|---:|---|
| Ajuste | mar 2025 – feb 2026 | 965 | 120 | 5.859 | 739 | 0 | 3.160 / 631 |
| Validación | abr y may 2026 | 240 | 120 | 992 | 86 | 2 | 1.276 / 132 |
| Comprobación | jul y ago 2026 | 240 | 120 | 863 | 97 | 3 | 1.443 / 94 |

- **Fronteras** (comprobadas por código): el ajuste madura el 2026-04-29, antes del 04-30; la validación madura el 07-30, antes del 07-31; la comprobación madura el 10-30, dentro de la cobertura.
- **Septiembre** queda fuera: 09-30 + 60 = 11-29, después de la cobertura.
- **Marzo y junio** quedan como separación.

**Soporte en el ajuste**: todos los productos superan los 10 positivos, así que no hace falta el respaldo por popularidad. Pero los pares positivos no son eventos independientes:

| Producto | Positivos | Clientes | Compras únicas | Fotografías repetidas del mismo evento |
|---|---:|---:|---:|---:|
| PRO01 | 65 | 38 | 38 | 27 |
| PRO05 | 87 | 49 | 49 | 38 |
| PRO09 | 101 | 57 | 57 | 44 |
| PRO02, PRO06 y PRO08 (los de menos soporte) | 60–61 | 35–37 | 35–37 | 23–26 |

## 3. Variables, estadísticas y modelo

- **Estadísticas**: popularidad (clientes distintos con el producto) y coocurrencia, **acumuladas hasta cada corte**. Se recalculan en cada fotografía solo con operaciones hasta C, con la misma política para el modelo y las referencias. Los snapshots quedan congelados en `estadisticas_por_corte.json` y la evaluación verifica que coinciden.
- **Variables**:
  - del cliente: recencia, días de compra (totales, 90 y 180 días), importe COP en 90 días y número de productos;
  - del par: popularidad relativa, afinidad máxima y coocurrencia relativa;
  - identidad del producto: indicadora por producto. Un producto desconocido no tiene indicadora ni soporte y cae a popularidad.
  - La combinación ampliada añade `familia_comprada` (convención: familia del catálogo actual) y afinidad × recencia.
  - **No se usan**: `cliente_id`, información futura, precios de transacción ni coberturas futuras.
- **Modelo**: regresión logística L2 compartida, C ∈ {0,1; 1; 10}, semilla 20261123. Imputación y escalado ajustados solo con el ajuste. Se publica el puntaje (logit sin calibrar) con `probabilidad = null`.
- **Respaldo por popularidad**: los productos con menos de 10 positivos se ordenarían después de los puntuados (orden lexicográfico, sin mezclar escalas). Aquí no hizo falta.
- **Validación** (HitRate@1 sobre el universo):

  | Candidato o referencia | HitRate@1 |
  |---|---:|
  | Básica (los tres C) | 0,079 |
  | Ampliada | 0,075 |
  | Popularidad | 0,071 |
  | Coocurrencia | 0,083 |

  Se elige **básica con C = 0,1**. El artefacto recargado reproduce scikit-learn hasta 9×10⁻¹⁶.

## 4. Comprobación histórica (julio y agosto; exploratoria)

Universo fijo de 240 cliente-corte: clientes con historial y horizonte observado. Las abstenciones cuentan como fallo. Los tres métodos usan los mismos candidatos, el mismo K y el mismo horizonte.

| | Modelo | Popularidad | Coocurrencia |
|---|---:|---:|---:|
| **HitRate@1 (universo de 240)** | **0,133** (32) | 0,121 (29) | 0,125 (30) |
| HitRate@1 con candidatos (237) = recomendación común (237) | 0,135 | 0,122 | 0,127 |
| HitRate@3 (universo) | 0,275 | 0,275 | 0,275 |
| Precision@3 (639 productos sugeridos) | 0,117 | 0,119 | 0,117 |
| NDCG@3 (78 cliente-corte con algún candidato comprado) | 0,631 | 0,622 | 0,616 |
| Cobertura de clientes / catálogo | 98,75 % / 100 % | 98,75 % / 100 % | 98,75 % / 100 % |
| Violaciones de restricciones | 0 | 0 | 0 |

- **Por corte** (aciertos en primera posición): julio 18 / 17 / 16 y agosto 14 / 12 / 14.
- **Número de sugerencias**: 0 para 3 cliente-corte (sin candidatos), 1 para 15, 2 para 42 y 3 para 180.
- **Remuestreo de clientes completos** (2.000 réplicas):
  - frente a popularidad: +0,0125, IC [−0,004; +0,033];
  - frente a coocurrencia: IC [−0,038; +0,054];
  - la diferencia de cobertura es 0.
- **Por producto**: el modelo pone PRO09 (Revisión de continuidad) en primer lugar en 85 de 237 casos y acierta 14. Es básicamente un orden por producto más popular entre recién llegados. El resto de productos tiene menos de 30 apariciones en primera posición: no se afirman mejoras por producto.

**Decisión: inconcluso.**

| Meta | Resultado |
|---|---|
| Mínimos de evidencia | Sí |
| +5 puntos de HitRate@1 frente a popularidad | No (+1,25) |
| IC 95 % por encima de 0 | No |
| Cobertura sin bajar más de 5 puntos | Sí |
| Cero violaciones | Sí |

No es «rechazado»: el IC incluye 0 y no hay violaciones. **Sistema conservado: popularidad filtrada.**

## 5. Sombra, contrato e interfaz

- **Publicación** (`salida/sombra/venta_cruzada/2026-10-31`, sello `4dd18f36…`):
  - versión `venta_cruzada-popularidad-filtrada-compat-v1`, con el candidato congelado como referencia;
  - **292 recomendaciones**: 117 clientes con propuestas y 3 sin candidatos;
  - los 3 sin candidatos (CLI035, CLI045 y CLI112) aparecen en el informe de cobertura con su motivo, sin filas ficticias;
  - incluye `muestra_revision.json`.
- **Contrato C2**:
  - **clave**: cliente y producto, con un máximo de tres productos únicos por cliente;
  - **ranking**: posiciones 1..n coherentes con el puntaje y el desempate por `producto_id`; `popularidad_sin_soporte` siempre detrás;
  - **restricciones**: ningún producto excluido;
  - **valores**: puntaje finito y probabilidad nula o en [0, 1];
  - **concordancia** con el manifiesto: corte, versión, reglas y catálogo;
  - **cobertura**: cada cliente sin recomendaciones tiene motivo, y los conteos coinciden.
  - Las seis publicaciones en sombra existentes siguen siendo válidas.
- **API** (`/api/venta-cruzada`):
  - **Lectura** (`venta_cruzada.ver`: operaciones, ventas y gerencia): consulta, filtro por compatibilidad y ficha.
  - **Decisiones** (`venta_cruzada.decidir`, solo Ventas): aceptar, aplazar, descartar o marcar en revisión, siempre con motivo.
  - **Revisión comercial** (`venta_cruzada.revisar`): registro de la revisión de cada par de la muestra.
  - **Importación** (`operacion.administrar`): carga de la publicación en sombra.
  - **Portal externo**: no recibe nada.
  - **Importación fuera de orden**: un corte anterior no desplaza al activo.
- **Episodios**:
  - la identidad es `venta_cruzada:<cliente>:<producto>:<ciclo>`; un nuevo corte, puntaje, posición o versión no crea otro episodio;
  - un episodio descartado no se reabre (409);
  - una compra posterior lo cierra («compra posterior observada») sin tocar resultado, responsable ni decisiones;
  - con la bandera `venta_cruzada_tareas` apagada (por defecto) no se crea nada. Con la bandera activa, solo las propuestas **aceptadas por Ventas** generan un seguimiento o añaden su motivo a uno abierto, sin duplicados.
- **Vista y ficha**: producto, posición, origen, evidencia, compatibilidad («por revisar»), corte, estado experimental y acciones con motivo.
  - No se muestran porcentajes de modelo, porque solo hay puntaje. La evidencia sí cita proporciones observadas, como «71 % de quienes compraron…».
  - Venta cruzada queda separada de la recompra y la renovación (agenda C1).

**Comprobación en el navegador** (base temporal, identidad ficticia de Ventas):
- **Estados revisados**: sin publicación (vacío), con datos (292 propuestas, todas por revisar), ficha sin candidatos (CLI035), decisión guardada («Aceptada» con motivo) y error (mensaje visible tras una propuesta inexistente).
- **Teclado**: el foco sigue un orden lógico (filtro, botón, cliente, acción, motivo) y tiene un contorno visible de 2,7 px.
- **Anchura reducida**: no se pudo renderizar. La ventana del navegador está maximizada y no se deja redimensionar, y `frame-ancestors 'none'` bloquea el iframe, lo cual es correcto. Se verificó que las vistas usan `.tabla` (desplazamiento horizontal), `.filtros` (pasa a varias líneas) y las reglas de pantallas de 640 px o menos.

## 6. Revisión comercial

- **Muestra**: 30 pares de la sombra, con semilla 20261123 y reparto circular entre estratos de familia (convención) × tercil de puntaje. Universo: 292 recomendaciones.
- **Estado real**: 0 de 30 revisados y 30 pendientes. Pertinencia: no estimable.
- **Meta**: al menos 80 % entre casos evaluables. La información insuficiente se informa aparte y los pendientes siguen en el denominador.
- Los datos de prueba solo prueban el flujo; no acreditan pertinencia comercial.

| Dimensión | Estado |
|---|---|
| Integración técnica | Completa y probada |
| Evidencia predictiva | Inconclusa: popularidad conservada |
| Revisión comercial | Pendiente |
| Condiciones para un piloto | Revisión ≥ 80 % pertinente, reglas empresariales de compatibilidad, catálogo con fechas de vigencia, registro de exposición, oferta, aceptación, compra y descarte |

## 7. Comandos (2026-11-23)

```
python -m modelos.cli preparar-modelo --modelo venta_cruzada --datos salida/a01 --salida salida/experimentos/venta_cruzada/preparacion
python -m modelos.cli entrenar --modelo venta_cruzada --datos salida/a01 --salida salida/experimentos/venta_cruzada/ejecucion-001   (y -002)
python -m modelos.cli evaluar --ejecucion salida/experimentos/venta_cruzada/ejecucion-001   (tres veces, y sobre la 002)
python -m modelos.cli puntuar --modelo venta_cruzada --ejecucion salida/experimentos/venta_cruzada/ejecucion-001 --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/venta_cruzada/2026-10-31
python -m api sombra salida/sombra/venta_cruzada/2026-10-31
```

- **Reproducibilidad**: las ejecuciones 001 y 002 tienen el mismo sello (`a18b197d…`), el mismo artefacto (`venta_cruzada-m4-basica-c0_1-7baee4c1`) y la misma decisión. La evaluación es idempotente (`b5405e8d…`) y repetir la sombra no cambia nada.
- **Integridad**: la evidencia alterada se rechaza, y también las reglas o las estadísticas distintas de las congeladas.
- **Recuperación**: tras una interrupción antes o después de las métricas y la decisión, el reintento completa sin borrar archivos.

## 8. Piloto prospectivo (desde la congelación real del 2026-11-23)

- **Primer corte**: 2026-11-30, con ventas completas hasta esa fecha.
- **Evaluable**: desde el 2027-01-29.
- **Qué registrar por propuesta**:
  - exposición (mostrada a Ventas);
  - oferta realizada;
  - aceptación del cliente;
  - compra confirmada;
  - descarte con motivo.
- **Sin atribución**: para medir efecto hace falta un diseño con grupo sin exposición; sin él, una compra no se atribuye al recomendador.
- **Antes del piloto**: catálogo con fechas, reglas de compatibilidad de la empresa y revisión comercial.

## Limitaciones

- Datos sintéticos (120 clientes y 10 productos) ya inspeccionados: la comprobación es exploratoria.
- La disponibilidad del catálogo y de las coberturas se basa en convenciones sintéticas declaradas.
- No hay reglas empresariales de compatibilidad.
- Con 10 productos y clientes que ya tienen 6 a 8 de ellos, quedan pocos candidatos y la diferencia entre métodos es pequeña.

## M4.1 · Antigüedad, secuencia reciente y referencias azar y techo (protocolo `m41-protocolo-v1`)

**Implementado y evaluado el 23 de noviembre de 2026, con decisión «inconcluso».** No mejora a M4, y en estos datos ningún método se separa del azar. La configuración está en [`modelos/config/venta_cruzada_m41.json`](../modelos/config/venta_cruzada_m41.json) y el código en `modelos/venta_cruzada_m41.py`.

### Qué se añadió

- **`antiguedad_dias`**: corte − alta. En el ajuste los clientes nuevos compran más: 16 % en sus primeros 90 días frente a 10 % entre los 6 y 12 meses.
- **`transicion_reciente`**: secuencia «compró q en los últimos 60 días → compra p». Se suaviza hacia la tasa base de p con un peso de 20 eventos.
  - Solo usa eventos maduros: t + 60 ≤ C.
  - Solo considera el catálogo conocido al corte.
  - Una prueba verifica que añadir compras o productos posteriores al corte no cambia las estadísticas. Se corrigió una fuga en la que el universo de productos de un cliente incluía compras futuras.
- **Referencias fijas en el informe**:
  - azar reproducible entre los mismos candidatos (semilla + cliente + corte);
  - **techo por producto**: un diagnóstico que ordena por la tasa real de compra de cada producto en el propio bloque, así que usa la respuesta. Nunca interviene en la selección.
  - El candidato congelado de M4 se mide como contexto.
- **Combinaciones**: «antiguedad» (la básica de M4 + antigüedad) y «completa» (+ secuencia), con C ∈ {0,1; 1; 10}.

### Resultados

- **Validación**: «antigüedad» 0,079 (los tres C) y «completa» 0,075. Se elige **antigüedad con C = 0,1**. Referencias: popularidad y azar 0,071, coocurrencia 0,083 y techo 0,133.
- **Comprobación** (julio y agosto; exploratoria y ya vista en M4; universo de 240 cliente-corte):

  | | M4 | M4.1 | Popularidad (publicada) | Coocurrencia | Azar | Techo* |
  |---|---:|---:|---:|---:|---:|---:|
  | HitRate@1 | 13,3 % | 11,7 % | 12,1 % | 12,5 % | **14,6 %** | 16,25 % |
  | HitRate@3 | 27,5 % | 26,7 % | 27,5 % | 27,5 % | 28,3 % | 30,8 % |
  | Precision@3 | 11,7 % | 11,4 % | 11,9 % | 11,7 % | 12,2 % | 13,5 % |
  | Cobertura de clientes | 98,75 % | 98,75 % | 98,75 % | 98,75 % | 98,75 % | 98,75 % |
  | Violaciones | 0 | 0 | 0 | 0 | 0 | 0 |

  \* El techo usa la respuesta del bloque.

- **IC 95 % de M4.1** (remuestreo por cliente): frente a popularidad, de −3,8 a +2,5 puntos; frente al azar, de −7,9 a +2,1.
- **Sensibilidad del azar a la semilla**: con otra semilla, en el diagnóstico previo, el azar dio 12,9 %. Esa variación de unos 2 puntos es del mismo tamaño que las diferencias entre métodos.

### Decisión e interpretación

**Inconcluso**: la mejora no llega a 5 puntos y el IC incluye 0. **Se mantiene popularidad filtrada** en la sombra publicada; la de M4 no cambia.

En los datos de práctica, la compra de un producto nuevo es casi aleatoria entre los candidatos:
- el azar, la popularidad y los modelos quedan dentro del mismo margen de ruido;
- incluso conociendo la tasa real de cada producto, solo se ganan unos 3 a 4 puntos.

Las mejoras con valor real no son predictivas:
- reglas de compatibilidad y complementariedad de la empresa;
- catálogo con fechas de vigencia;
- **la revisión comercial de la muestra de 30 pares**, que está pendiente. Sus valoraciones podrían usarse como un segundo objetivo de aprendizaje, más cercano a lo que Ventas necesita.

Con datos reales, conviene repetir M4 con las mismas referencias (azar y techo) desde el principio.

### Ejecución, reproducibilidad y pruebas

```
python -m modelos.cli entrenar --modelo venta_cruzada --config modelos/config/venta_cruzada_m41.json --datos salida/a01 --salida salida/experimentos/venta_cruzada_m41/ejecucion-001   (y -002)
python -m modelos.cli evaluar --ejecucion salida/experimentos/venta_cruzada_m41/ejecucion-001 --m4 salida/experimentos/venta_cruzada/ejecucion-001   (tres veces, y sobre la 002)
python -m modelos.cli resumen-ia
```

- **Reproducibilidad**: las ejecuciones 001 y 002 tienen el mismo sello (`4d946bc1…`) y la misma decisión; la evaluación es idempotente.
- **M4 intacto**: la reevaluación de M4 sigue idéntica y la sombra publicada no cambia.
- **Pruebas**: `tests/modelos/test_venta_cruzada_m41.py`, con 3 pruebas: secuencias sin fuga, suavizado y azar reproducible.
- **«Modelos de IA»**: la página incluye ahora venta cruzada, con M4, M4.1, popularidad, coocurrencia, azar y techo en la misma tabla.

## Monitoreo (24-11-2026)

M4: elegibles, con candidatos y con recomendaciones; compatibilidad; revisión comercial (grupo D) al registrar revisiones; HitRate a 60 días como exposición y compra posterior, sin atribución causal. Ver [monitoreo de modelos](monitoreo-modelos.md#b-monitoreo-de-m1m6).
