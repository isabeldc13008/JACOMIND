# JOCAMIND | Plan de implementación para dos personas

La ampliación del 23 de noviembre de 2026 está en los [seis planes detallados de modelos](docs/plan/modelos/README.md). Esos planes parten de la implementación actual con Python, SQLite y contratos C1/C2 y especifican la mejora del modelo de compra y cinco capacidades adicionales.

**Primera entrega:** Operaciones abre un cierre mensual, elige a quién dar seguimiento y puede explicar su decisión con hechos y una predicción evaluada. **Entrega completa:** Ventas gestiona oportunidades y retención, Gerencia evalúa tendencias y escenarios, y cada cliente empresarial autorizado puede consultar beneficios y sus propias PQRS. El mismo cierre alimenta la ficha, el tablero, el informe y el asistente.

La [especificación de la agenda](PLAN_HACKATON.md) detalla la primera integración. Este plan abarca el producto completo y avanza por criterios de aceptación. Las instrucciones de construcción, los casos de prueba y el criterio de aceptación de cada tarea están en los [once tickets de datos y modelos](docs/plan/datos-y-modelos.md) y los [once tickets de aplicación y operación](docs/plan/aplicacion-y-operacion.md). Son trabajos propuestos. En el clon hay documentación y, en la carpeta hermana, datos y código didáctico de referencia.

## 1. Decisiones de alcance

| Propuesta | Función que se construirá | Evidencia necesaria para entregarla |
|---|---|---|
| GreenOps | Carga CSV/Excel, conciliación de compras y ventas, calidad, ficha 360°, informe mensual y consultas en lenguaje natural. | Un mismo importe se reconstruye desde el registro fuente hasta la pantalla, el informe y la respuesta del asistente. |
| GreenPulse | Segmentos, recompra, riesgo de inactividad, próxima ventana de compra, renovaciones, venta cruzada y agenda explicable. | Comparación temporal contra reglas sencillas y registro de qué hizo Ventas con cada sugerencia. |
| GreenForecast | Tendencia y pronóstico de ventas y compras, cambios de volumen, escenarios de TRM y sensibilidad de costos. | Error fuera de muestra frente al último mes observado. Finanzas puede verificar el escenario con una operación en USD. |
| Plataforma JOCAMIND y Loyalty & Care | Vistas por rol, portal de beneficios, registro y seguimiento de PQRS, clasificación y respuesta asistida con documentación. | Pruebas con dos empresas aisladas, contenido vigente, revisión humana de borradores y trazabilidad del caso. |

**Punto de partida verificado.** El juego sintético cubre 22 meses y 120 clientes. En octubre los 120 ya tienen compras confirmadas. Para probar el estado «sin historial» hay que construir un cliente de prueba o seleccionar un corte anterior apropiado. El paquete trae un visor precalculado y una regresión logística reproducible. Las probabilidades que vienen en el CSV corresponden a julio–septiembre. La agenda de octubre requiere inferencia nueva. [Ficha empresarial](https://estudia-seguimiento.vercel.app/hackaton/retos/2.pdf)

**Insumos que cambian el alcance del piloto.** Operaciones debe precisar el recurso «com», qué fuentes entregará y cómo registra rectificaciones. Ventas debe definir inactividad, capacidad semanal y productos compatibles. Finanzas debe definir exposición en USD, costos atribuibles y qué entiende por margen. Atención debe facilitar políticas de beneficios vigentes, reglas de enrutamiento y casos clasificados con permiso de uso. Mientras llegan, construir con ejemplos sintéticos rotulados. Se puede probar el flujo completo de PQRS y RAG con ellos, pero para medir calidad empresarial se necesitan casos y documentos aprobados. Si Green ofrece una plataforma de datos o un asistente existente, verificar sus interfaces antes de decidir la integración.

## 2. Arquitectura que permite trabajar por separado

1. **Demostración local.** A produce `salida/agenda.json` con el contrato v1 de la agenda. B lee ese archivo o una muestra de prueba explícita. Ambos pueden trabajar sin servidor de base de datos ni proveedor de IA.
2. **Piloto multiusuario.** Propuesta técnica: un servicio Python con FastAPI, una base PostgreSQL y una interfaz web que consume la API. Mantener los cálculos en un paquete Python independiente reutilizable por la carga, el entrenamiento y el cierre mensual. B conserva los componentes útiles de la demo y sustituye el lector JSON por un adaptador HTTP. El portal externo requiere autenticación y autorización en el servidor.
3. **Publicación del cierre.** A produce un directorio por ejecución con manifiesto, agenda y tablas analíticas. B implementa un importador que verifica versión, conteos y sumas, escribe en una transacción y marca el cierre como publicado. Todas las consultas toman el mismo identificador de cierre. Las acciones humanas, PQRS y auditoría tienen tablas propias para sobrevivir a una regeneración.
4. **Consultas y documentos.** El asistente usa operaciones tipadas de lectura para cifras y recuperación de fragmentos aprobados para políticas. Recibe del servidor la identidad y la empresa. Una respuesta puede combinar ambas fuentes, indicando fecha de corte, vigencia y procedencia. El producto funciona en modo consulta estructurada cuando el proveedor de generación está indisponible.

| Contrato | Productor → consumidor | Acuerdo mínimo y ejemplo de fallo que hay que probar |
|---|---|---|
| C1 · Agenda v1 | A → B | Respetar el JSON del [contrato de la agenda](PLAN_HACKATON.md). Una fila por cliente y corte, COP numérico, probabilidad nula cuando falte estimación. Una versión incompatible produce aviso y conserva el cierre anterior. |
| C2 · Publicación analítica | A → B | Manifiesto con versión, identificador, corte, origen, huellas de entrada, versión de reglas/modelo y conteos. Tablas con claves explícitas: cliente/corte, periodo/familia, escenario/moneda y oportunidad/cliente/producto. Duplicar una clave invalida el lote. Los campos nuevos opcionales preservan C1. |
| C3 · Trabajo operativo | B → A | Eventos con ID, oportunidad, cliente, fecha, actor, estado y resultado. PQRS añade empresa, categoría revisada y fecha de revisión. A recibe solo ejemplos anonimizados y autorizados para evaluar. Reintentar el mismo evento debe producir un único cambio. |
| C4 · Asistencia | B ↔ A | B define funciones de lectura con filtros permitidos, alcance de usuario, corte o documento/versión, evidencia y estado sin datos. A entrega el clasificador de PQRS con categoría, confianza, versión y opción de revisión. Probar un documento vencido y un texto de categoría incierta. |

**Propiedad de archivos.** A escribe en `pipeline/`, `modelos/`, `tests/datos/`, `tests/modelos/` y `docs/ficha-modelo.md`. B escribe en `app/`, `api/` (incluidas migraciones), `tests/app/`, `tests/integracion/`, `contratos/`, configuración compartida y README. Son rutas previstas para la implementación. B mantiene esquemas y muestras versionadas tras acordarlos con A. Ambos pueden leerlas. A valida su productor contra esos esquemas y B valida su consumidor con las mismas muestras. Un cambio incompatible se prueba en una versión nueva antes de migrar el lector.

**Un ejemplo de integración.** Para el mismo corte y cliente, la consulta de detalle, la agenda y la explicación del asistente deben devolver la misma recencia. B puede definir primero `GET /cierres/{cierre}/clientes/{id}` con ejemplos de cliente existente, ausente y sin historial. A implementa la transformación con esos casos. En integración, la prueba solicita la ficha a la API y la compara con la fila publicada por A. Aplicar este patrón también a pronósticos y escenarios. Para escrituras como `POST /pqrs`, el contrato incluye quién puede actuar, la clave de reintento y el resultado de repetir la solicitud.

## 3. Orden de ejecución y trabajo paralelo

**Paso 0, juntos.** Elegir A y B, identificar la carpeta de insumos en ambos equipos, fijar el corte de ensayo y guardar la versión inicial de C1. A anota las cifras de referencia. B prepara tres clientes ficticios y la forma de arrancar la vista. Acordar la capacidad de revisión para la demo (se proponen diez clientes por corte). En cada bloque, crear dos ramas cortas desde la misma base. Una persona revisa el cambio de la otra. Fusionar el productor y el consumidor cuando pase la prueba del contrato. Los cambios de estado del tablero se llevan en tickets individuales.

La tabla es una secuencia sugerida para **dos personas**. La columna final indica dónde se necesita el resultado del compañero. En cada bloque B puede desarrollar la interfaz o el flujo con muestras antes de integrar el resultado de A.

| Bloque | A · Datos y aprendizaje | B · Software y producto | Entrega conjunta |
|---|---|---|---|
| 1 | A01 · Importación y calidad | B01 · Contratos, muestras y visor local | Una carga limpia y una muestra inválida recorren sus lados del contrato. |
| 2 | A02 · Contabilidad operativa y anomalías | B02 · Identidad, base de datos y publicación | Primera publicación transaccional de un cierre de prueba. |
| 3 | A03 · Ficha, RFM y coberturas | B03 · Ficha, agenda y tableros por rol | Buscar un cliente y conciliar una cifra con la fuente. |
| 4 | A04 · Compra a 30 días | B04 · Registro y seguimiento de PQRS | Incorporar puntuaciones a B03. B04 avanza con empresas y casos ficticios. |
| 5 | A05 · Clustering de clientes | B05 · Gestión de agenda, alertas y resultados | Ventas filtra por segmento y registra una acción. |
| 6 | A06 · Inactividad y próxima compra | B06 · Beneficios y fidelización | Operaciones diferencia vencimiento, riesgo y ventana estimada. El portal muestra beneficios vigentes de prueba. |
| 7 | A07 · Renovación, reactivación y venta cruzada | B07 · Consultas en lenguaje natural | Buscar una oportunidad por cliente y obtener los mismos motivos en la ficha y en la consulta. |
| 8 | A08 · Pronóstico y cambios de volumen | B08 · Documentos y RAG | Revisar un pronóstico con sus errores y una respuesta documental con su cita. |
| 9 | A09 · Escenarios de TRM y costos | B09 · Panel financiero e informe mensual | Conciliar un escenario manual y generar dos veces el mismo informe. |
| 10 | A10 · Clasificación de PQRS | B10 · Atención asistida y borradores | Clasificar, remitir a revisión y responder desde el caso con fuentes vigentes. |
| 11 | A11 · Seguimiento de modelos y medición de impacto | B11 · Operación, recuperación y piloto | Ejecutar la prueba de extremo a extremo y revisar resultados con cada rol. |

**Ruta de entregas.** El primer hito permite verificar el flujo con datos sintéticos. Los once bloques cubren el producto completo. Pasen de un hito al siguiente cuando se cumpla su criterio de aceptación. La ruta crítica del producto local es ingesta → cierre conciliado → variables y modelo → agenda integrada. La del portal es identidad → casos y documentos aprobados → prueba de aislamiento → atención asistida.

**Cómo reordenar el trabajo si un insumo se retrasa.** Una vez aceptado A02, pronósticos (A08) y escenarios (A09) pueden adelantarse sin esperar a clustering ni al agente. Tras A03, segmentación (A05) e inactividad (A06) pueden construirse independientemente. En el otro carril, una vez disponible B02, casos (B04) y beneficios (B06) pueden avanzar sin puntuaciones del modelo. Si aún faltan políticas de Green, B puede completar el panel financiero (B09) con las tablas de A mientras los casos documentales permanecen en ensayo. La única espera necesaria para cada módulo es su integración y aceptación con los insumos indicados en su ticket.

## 4. Cómo aprobar una entrega

| Hito | Recorrido que debe ejecutar alguien distinto del autor | Evidencia que queda |
|---|---|---|
| Demo de la hackatón | Regenerar octubre, encontrar un cliente prioritario, explicar la acción y comparar regresión frente a compra reciente. | Comando reproducible, cifra conciliada, matriz de confusión, un falso positivo y una captura con datos de práctica. |
| Piloto comercial interno | Cargar el mismo lote dos veces, intentar publicar un lote defectuoso, consultar el último cierre válido, asignar una oportunidad y registrar su resultado. | Conteos y sumas idénticos tras el reintento, registro del rechazo y una sola acción persistida. |
| Piloto financiero | Reservar meses de prueba, contrastar las predicciones con sus valores observados y variar únicamente la tasa del escenario. | Errores por periodo y familia, supuestos explícitos, importes rastreables y ejemplo verificado por Finanzas. |
| Piloto de atención | Con dos usuarios de empresas distintas, publicar un beneficio, radicar una PQRS, clasificarla, aprobar una respuesta y consultar su estado. Retirar la política y volver a preguntar. | Historial de estados, autorización comprobada, respuesta con fuente vigente y abstención al faltar evidencia. |
| Entrega operable | Restaurar un cierre anterior en ensayo, reanudar la aplicación, reproducir el informe y confirmar que persisten los seguimientos y las PQRS. | Registro de restauración, tiempo medido y pruebas de lectura/escritura posteriores. |

**Criterio común de cierre de ticket.** El autor entrega código, una muestra mínima reproducible, el resultado esperado, el resultado observado y los límites conocidos. El compañero ejecuta el caso feliz y al menos el caso de fallo especificado. Para un modelo, registrar versión de datos, cortes, población, regla de comparación, métrica y decisión. Si el método aprendido pierde frente a la referencia, publicar la referencia identificada y documentar el experimento. Los umbrales de aceptación comercial se acuerdan con el usuario del módulo antes de evaluar el periodo final.

**Referencias locales.** Bajo `../Green_Services_Recursos_de_Prueba/`, consultar `02_Documentacion/Diccionario_de_datos.md` y `parametros_prueba.json` para campos y fronteras, `04_Codigo/` para los ejemplos reutilizables, `05_Validacion/` para valores esperados y `Salidas/predicciones_prueba.csv` para inspeccionar errores por cliente y mes. Conservar los recursos originales como referencia independiente.
