# Plan del recomendador de venta cruzada

[Programa](README.md) · [Base común](00-base-comun.md)

## Objetivo y decisión

Proponer hasta tres productos complementarios por cliente, con evidencia y restricciones verificables. Ventas revisa la recomendación y decide si corresponde ofrecerla. El primer objetivo aprendido es compra de un producto elegible en 60 días, no respuesta causal a una oferta.

Responsable técnico: A. Integración: B. Usuario de evaluación: Ventas, con validación de compatibilidad por Operaciones. Esfuerzo estimado: 5–7 jornadas persona.

## Estado y diferencia del nuevo experimento

**Implementado el 23 de noviembre de 2026, con decisión «inconcluso»** (se conserva popularidad filtrada; revisión comercial pendiente). Resultados, integración y piloto en la [ficha del modelo](../../modelo-venta-cruzada.md).

[`pipeline/oportunidades.py`](../../../pipeline/oportunidades.py) recomienda familias por coocurrencia. En la comprobación al 1 de septiembre de 2026 obtuvo 11 aciertos entre 69 clientes, igual que popularidad. El nuevo experimento trabaja a nivel producto y cambia el conjunto de candidatos; por tanto, no compara directamente sus porcentajes con aquel 11/69.

Reproducir primero el control por familia. Para evaluar el nuevo ranking, reconstruir tanto popularidad como coocurrencia a nivel producto, con los mismos candidatos, cortes, horizontes y número de recomendaciones.

## Dataset y candidatos elegibles

Unidad de aprendizaje: cliente, producto y corte. Incluir clientes con historial y productos disponibles en ese momento. Construir la lista de productos candidatos antes de consultar las compras futuras.

Reglas iniciales de venta cruzada:

- Excluir productos ya adquiridos por el cliente hasta el corte. La recompra y renovación se atienden en sus recorridos propios.
- Excluir productos con cobertura vigente, aunque no aparezca su factura en ventas; la base instalada es una fuente independiente.
- Excluir incompatibilidades o requisitos incumplidos mediante una tabla de reglas versionada. La ausencia de reglas se marca como compatibilidad por revisar, no como compatibilidad confirmada.
- Si no se conoce la vigencia histórica del catálogo, usar en el ensayo sintético la primera aparición observada hasta el corte como proxy de disponibilidad y registrar la limitación. Para el piloto, solicitar versiones del catálogo con fechas.
- Mantener los clientes sin candidatos en el informe de cobertura; no inventar una recomendación para llenar tres posiciones.

Etiqueta por candidato: compra confirmada de ese producto en `(corte,corte+60]`. Una compra de otro producto no cambia su etiqueta. Cero significa ausencia de compra durante un horizonte completo, no rechazo expreso a una oferta. Usar todos los negativos elegibles al inicio; el catálogo de diez productos no exige muestreo negativo.

## Variables y entrenamiento

Variables del cliente: recencia, frecuencia y valor reciente. Variables del candidato: familia, tipo recurrente/único, precio de lista conocido al corte y soporte histórico. Variables de relación: familias ya adquiridas, afinidad con el producto, productos complementarios y coincidencia con necesidades verificables de coberturas. No usar la siguiente familia o compra como variable.

Candidato inicial: una regresión logística regularizada compartida entre clientes y productos, con producto/familia codificados como categorías y unas pocas interacciones de negocio. No ajustar un modelo independiente por cliente ni representar el ID de cliente como variable. Encoders, escalas, popularidad y afinidades se aprenden solo con el bloque de ajuste y se conservan para inferencia. Si se habilita actualizar una estadística al corte, aplicarlo como política temporal explícita a todos los métodos y probar que solo usa pasado.

Exigir inicialmente al menos diez positivos de entrenamiento por producto para mostrar una probabilidad propia. Productos con menos soporte pueden usar popularidad identificada como referencia o quedar sin recomendación. Publicar la cobertura que se pierde por este criterio. Un modelo sin suficientes clases o candidatos no se ajusta.

Fijar una rejilla pequeña de regularización. Elegir configuración en validación; calibrar solo con predicciones temporales fuera de ajuste cuando el soporte lo permita. Si se usa un puntaje no calibrado, publicarlo como `puntaje`, con `probabilidad = null`.

## Evaluación temporal y comercial

Usar la partición de 60 días de la base común, sin repartir al azar pares de un mismo cliente y corte. La prueba histórica inicial usa julio y agosto. Ninguna regla de filtro se decide a partir de si el producto fue comprado después.

Métrica principal: HitRate@1, proporción de clientes con una compra del primer producto recomendado en el horizonte. Secundarias: HitRate@3, Precision@3 con denominador de productos realmente sugeridos, NDCG@3, cobertura de clientes, cobertura de catálogo y tasas de exclusión. Comparar sobre un universo elegible fijo y también sobre los clientes con recomendación común entre métodos, para no aparentar mejora dejando fuera los casos difíciles.

La relevancia offline es compra futura. La pertinencia comercial se valida en una muestra separada: Ventas marca pertinente, ya cubierto, incompatible, sin necesidad identificada o información insuficiente. Revisar inicialmente al menos 30 pares de cliente-producto, distribuidos entre familias y niveles de puntaje, o todos si hay menos. Los 30 son un tamaño de revisión del prototipo, no garantía de precisión estadística.

## Tickets de implementación

| Ticket | Trabajo | Evidencia de cierre | Dependencia |
|---|---|---|---|
| M4-01 | Reproducir coocurrencia/popularidad por familia | Control 11/69 y explicación de su universo | B0-01 |
| M4-02 | Catálogo temporal y filtro de candidatos | Exclusiones con motivo antes de etiquetar | B0-02 y M4-01 |
| M4-03 | Dataset de pares y referencias por producto | Conteos por clase/producto y muestras verificadas | M4-02 |
| M4-04 | Ajustar ranking y evaluar temporalmente | Comparación a igual candidatos, K y horizonte | B0-03 y M4-03 |
| M4-05 | Revisión comercial de propuestas | Registro por par con motivos y correcciones | M4-04 |
| M4-06 | Publicar recomendaciones y episodios | Contrato, reintentos, permisos y selección de versión | B0-04, B0-05 y M4-05 |
| M4-07 | Medir uso y resultado en piloto | Oferta, aceptación, compra y descarte diferenciados | B0-07 y M4-06 |

Rutas propuestas: ampliar `pipeline/oportunidades.py`, añadir `modelos/venta_cruzada.py`, `tests/modelos/test_venta_cruzada.py` y configuración versionada de compatibilidad. B adapta `api/tareas.py`, consultas y vista de seguimientos.

## Pruebas necesarias

- Un producto comprado después del corte puede ser etiqueta, pero no altera candidaturas ni afinidades previas.
- Una cobertura vigente excluye un producto aunque falte la venta asociada.
- Un producto incompatible no aparece aunque su puntaje sea el mayor.
- Producto o categoría nuevos usan el comportamiento de desconocido definido; no rompen el encoder.
- Cliente con todos los productos cubiertos obtiene lista vacía con motivo.
- Ranking estable con desempate por producto; no hay duplicados entre las tres sugerencias.
- Prueba y validación no modifican frecuencias de popularidad usadas para ajustar.
- Repetir un cierre o cambiar la versión del modelo no reabre una oportunidad descartada en el mismo episodio.
- La compra sugerida y la renovación de un producto ya adquirido permanecen diferenciadas.

## Integración y salida

En `recomendaciones_productos` publicar cliente, producto, posición, puntaje, probabilidad si está calibrada, horizonte 60, soporte, estado, versión y motivos con evidencia. Añadir estado de revisión de compatibilidad cuando aún no exista regla empresarial.

Las sugerencias operativas se traducen a `oportunidades` de tipo `venta_cruzada`, con `producto_id` explícito. El episodio identifica cliente, producto y ciclo comercial; sus decisiones sobreviven a nuevos cierres. Mantener los candidatos experimentales fuera de la cola activa. La interfaz muestra motivo, historial pertinente y opción de aceptar, posponer o descartar con razón.

## Criterios de aceptación

- [ ] Cero recomendaciones que incumplan las restricciones disponibles del catálogo o coberturas.
- [ ] Meta inicial: mejorar al menos cinco puntos porcentuales HitRate@1 frente a popularidad por producto, sobre el universo fijo.
- [ ] No reducir cobertura de clientes más de cinco puntos porcentuales sin una justificación comercial fijada antes de la comprobación.
- [ ] Publicar resultados por producto/familia con soporte y abstenerse de afirmar mejoras por grupos escasos.
- [ ] Meta inicial de revisión: al menos 80 % de propuestas pertinentes entre casos evaluables; información insuficiente se reporta aparte y no desaparece del denominador total de revisión.
- [ ] Tareas deduplicadas y motivos rastreables hasta registros del corte.

Si no supera popularidad, usar esa referencia con filtros de elegibilidad. La necesidad de revisar compatibilidad puede limitar una propuesta a modo sombra, aunque la predicción sea técnicamente correcta.

## Piloto y mantenimiento

Registrar exposición a la recomendación, oferta efectuada, aceptación comercial, compra confirmada y motivo de descarte. Una compra histórica sin oferta no permite aprender sensibilidad al contacto o al descuento. Revisar catálogo y compatibilidades en cada actualización y revalidar candidatos. El paquete tiene descuentos adicionales iguales a cero, por lo que este plan no incluye optimización de descuentos.
