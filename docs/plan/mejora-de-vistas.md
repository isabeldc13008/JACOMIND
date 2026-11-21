# Plan de mejora de las vistas de JACOMIND

**Primera entrega recomendada.** Conectar el tablero de Gerencia, la agenda y la ficha de cliente. Una persona debe poder pasar de «¿qué cambió este mes?» a «¿qué cliente merece atención y por qué?». En ese recorrido ya existen las ventas mensuales, los motivos de prioridad, las fechas de cobertura y las tareas. La mejora inicial consiste en darles contexto y enlazarlas.

La revisión cubre la aplicación web y el informe mensual que se abre desde ella. Las 22 entradas de este plan distinguen pantallas, variantes por perfil y secciones con una decisión propia. Se revisaron el código, los datos publicados y la demo en el navegador con los perfiles de Gerencia, Finanzas, Ventas, Operaciones, Atención y Empresa. Las cifras de ejemplo corresponden al cierre **sintético del 31 de octubre de 2026**. Las pruebas de comprensión propuestas quedan pendientes de realizar con usuarios.

**Ir al área de interés** · [Entrada y cartera](#entrada-y-cartera) · [Tableros por perfil](#tableros-por-perfil) · [Trabajo comercial](#trabajo-comercial) · [Solicitudes y atención](#solicitudes-y-atención-al-cliente) · [Beneficios y asistente](#beneficios-y-asistente) · [Finanzas e informes](#finanzas-e-informes) · [Operación y documentos](#documentos-calidad-y-operación) · [Orden de entrega](#orden-de-entrega-y-validación)

## Cómo debería leerse una pantalla

| Al abrirla | Al explorarla | Al verificarla |
| --- | --- | --- |
| Una frase contesta la pregunta principal. Indica el periodo, la unidad y a quién corresponde el dato. | Una gráfica o lista muestra dónde se concentra el cambio. Desde ella se puede abrir la selección que lo explica. | «Ver datos y cálculo» abre la tabla exacta, la fuente, los filtros, la fecha de actualización y, cuando corresponda, la regla o versión del modelo. |

**Ejemplo para Gerencia con datos de la demo**

> **En octubre se confirmaron ventas por 4,56 millones de COP.** En septiembre fueron 21,02 millones. La disminución fue de 16,46 millones. El ingreso acumulado de la cartera hasta el 31 de octubre fue de 51,15 millones de COP.
>
> **Dónde mirar.** Las ventas de la familia Infraestructura disminuyeron 16,44 millones de COP en octubre. **Ver ventas por familia** abre la comparación de esos dos meses.

La primera frase da al directivo una respuesta que puede usar en una reunión. La segunda lleva al analista hasta una variación que puede comprobar. Para explicar la causa comercial de la caída haría falta evidencia adicional.

| Término actual | Texto que puede aparecer junto al dato |
| --- | --- |
| Corte | «Incluye información hasta el 31 de octubre». Para una tarea o un caso, mostrar aparte su última actualización. |
| Cliente frío | «Han pasado al menos 90 días desde su última compra al cierre». Una persona puede haber comprado con frecuencia antes de esa pausa. |
| Umbral del modelo | «Nivel de probabilidad a partir del cual se sugiere revisar una posible recompra». En el detalle de la demo, identificar el umbral del 40 % y la versión que lo aplicó. |
| Sin historial / modelo no disponible / 0 % | «Sin compras registradas», «Hay compras, pero falta la estimación» y «El modelo estimó 0 %», respectivamente. |

## Entrada y cartera

### 1. Origen de datos y sesión

**Hoy.** La primera decisión exige elegir entre «Servidor», una ruta de archivo y un ejemplo. El formulario de identidades sigue visible cuando hay servidor. Gerencia entra por la agenda y, al pulsar «Tableros», aterriza en Ventas.

**Cambio.** Ofrecer tres entradas llamadas «Trabajar con el cierre publicado», «Consultar una agenda local» y «Explorar una demostración». Indicar qué se puede hacer con cada una. Mostrar el selector de identidad ficticia donde corresponde y dejar rutas y comandos en la ayuda técnica. Proponer como entrada el tablero propio de Gerencia, la agenda para Ventas, Finanzas para ese equipo, la bandeja para Atención y los beneficios para Empresa. Operaciones debe poder elegir entre revisar vencimientos y preparar el cierre.

**Prueba.** Una persona que entra por primera vez identifica si trabaja con datos de práctica, llega a su tarea y encuentra el corte sin conocer el término «servidor».

### 2. Agenda de seguimiento

**Hoy.** Las tarjetas resumen toda la cartera. Una línea bajo los filtros contiene el total seleccionado. La acción suele repetirse como motivo y «Exportar CSV» descarga toda la cartera incluso con filtros activos.

**Cambio.** Encabezar la agenda con «6 de 8 clientes requieren revisión» en la demo. Añadir barras horizontales por **acción principal**, calculadas sobre toda la cartera. Pulsar «Revisar cobertura» filtra la lista y muestra «2 clientes seleccionados · 12,56 millones de COP de ingreso acumulado». Indicar junto a la exportación su alcance real. En la fila, explicar el hecho que justifica la acción y permitir abrir la ficha. Exponer el orden aplicado también cuando el modelo está desactivado.

**Prueba.** Los dos clientes son DEMO02 y DEMO06. La persona puede explicar por qué los ve, qué total cambia al filtrar y qué filas contendrá la descarga. El dato ausente, la falta de historial y la probabilidad estimada de 0 % tienen textos propios.

### 3. Ficha de cliente

**Hoy.** Seis tarjetas y varias tablas obligan a reconstruir una recomendación. El servicio entrega oportunidades y fecha sugerida que la ficha omite. La versión local puede tener un resumen de compras sin su detalle.

**Cambio.** Abrir con una recomendación explicada. La ficha de DEMO02 podría decir «Revisa la cobertura de respaldo. Al cierre del 31 de octubre faltaban 20 días para su vencimiento. La última compra fue el 10 de octubre». Debajo, mostrar el 55 % como estimación de compra a 30 días y enlazar el seguimiento existente. Una línea de tiempo distingue compra confirmada, vencimiento contractual y revisión sugerida. Las tablas conservan producto, importe, moneda y fuente. Indicar cuántas operaciones recientes se muestran y si el origen trae solo el resumen.

**Prueba.** Ventas puede señalar la compra que ocurrió y la fecha que todavía era futura al corte. En la agenda local queda claro qué detalle requiere el cierre completo.

## Tableros por perfil

### 4. Tablero de Ventas

**Hoy.** Una tabla enumera los segmentos y otra muestra oportunidades con códigos como `reactivacion`. La consulta presenta hasta 20 oportunidades y la pantalla omite ese límite.

**Cambio.** Ordenar barras por número de clientes en cada segmento, con el total visible y una explicación breve del segmento seleccionado. Enlazar con la agenda filtrada. Para oportunidades, mostrar acción, motivo comprobable y fecha sugerida. Identificar la lista como «Hasta 20 oportunidades prioritarias». Presentar «frecuente» y «con 90 días o más sin comprar» como etiquetas que pueden coexistir.

**Prueba.** Ventas entiende por qué DEMO01 puede ser frecuente y necesitar reactivación, y llega desde su segmento a la ficha.

### 5. Tablero de Operaciones

**Hoy.** Las tablas distinguen coberturas próximas y vencidas, pero en la demo la que vence en 45 días aparece antes de la que vence en 20. Las tarjetas de tareas muestran su estado actual junto a cifras del cierre.

**Cambio.** Ordenar las próximas por fecha y escribir «vence en 20 días» o «venció hace 60 días», siempre relativo al corte indicado. Usar una barra para las vencidas y tres para las que vencen en 0–15, 16–30 y 31–45 días. Contar **coberturas**, aunque un cliente tenga varias. Abrir el listado desde cada barra. En otro bloque, fechar los seguimientos como «estado actual».

**Prueba.** Operaciones encuentra primero a DEMO02 entre las próximas y reconoce la de DEMO06 como vencida. Puede conciliar los intervalos con las instalaciones publicadas. Si solo hay totales, ve la limitación de detalle.

### 6. Tablero de Gerencia

**Hoy.** Ya tiene una línea mensual y una tabla por segmento. El énfasis visual recae en el ingreso acumulado. El lector debe estimar la caída mirando el eje y buscar en otra pantalla qué familia cambió.

**Cambio.** Usar el ejemplo ejecutivo de apertura. Dar prioridad al último mes completo, la diferencia en COP y el mes de comparación. Conservar la línea y su tabla, rotular los dos puntos comparados y añadir barras de ingreso por segmento. Desde «Ver ventas por familia», pasar a Finanzas con el mismo corte y meses. Mostrar fecha y fuente para que Finanzas pueda verificar la cifra con sus permisos.

**Prueba.** En 30 segundos, como meta de diseño, Gerencia identifica el resultado mensual, el acumulado y una familia que explica aritméticamente la variación. Ante un mes incompleto, la pantalla identifica la falta de datos.

## Trabajo comercial

### 7. Seguimientos · lista y planificación

**Hoy.** «Cupo de contactos (K)» y «Planificar» limitan la lista. La sección «Medición» conserva cifras de todas las tareas aunque se active «Solo asignadas a mí». La fecha de revisión hace de enlace al detalle.

**Cambio.** Preguntar «¿Cuántos seguimientos quieres revisar?» y usar «Ver prioridades». Mostrar fecha, responsable, motivo y un enlace «Abrir tarea». Identificar el alcance de la medición del equipo. Usar barras por tipo para tareas atendidas y descartadas, acompañadas del total que sirve de denominador. Para mostrar el total pendiente de la selección además del cupo, ampliar la consulta con un conteo anterior al límite.

**Prueba.** Con cupo de tres, Ventas identifica tres tareas prioritarias y sabe si ya tienen responsable. Cambiar el cupo o filtrar por persona mantiene visible el alcance de los porcentajes.

### 8. Seguimientos · detalle de tarea

**Hoy.** «Asignarme», «Posponer», «Registrar contacto», «Marcar atendida» y «Descartar» compiten por atención. La evidencia del cierre se presenta como un objeto JSON.

**Cambio.** Encabezar con cliente, motivo, responsable y próxima revisión. Agrupar las acciones por intención y mostrar los campos de la elegida. En una cronología, distinguir la evidencia del cierre, el contacto registrado y el resultado que Ventas declara. Mantener la versión y los datos originales desplegables. Si otra persona actualiza la tarea, mostrar qué cambió antes de reintentar.

**Prueba.** Ventas registra una llamada y un siguiente paso sin dar por cerrada la tarea. Gerencia puede leer el resultado y la evidencia respetando su acceso de consulta.

## Solicitudes y atención al cliente

### 9. Empresa · mis solicitudes y radicación

**Hoy.** «Mis PQRS» abre con un formulario y una tabla de radicados. El nombre no explica que la lista corresponde a la empresa. La búsqueda por radicado o asunto ya está en el servicio.

**Cambio.** Titular «Solicitudes de mi empresa» y explicar una vez «Peticiones, quejas, reclamos y sugerencias (PQRS)». Ofrecer «Consultar una solicitud» y «Crear solicitud», con un ejemplo de asunto y una confirmación con el número de seguimiento. Una lista buscable responde mejor que una gráfica a «¿dónde está mi caso?».

**Prueba.** La persona encuentra su caso por asunto y reconoce el número que debe guardar al crear uno nuevo.

### 10. Empresa · detalle de solicitud

**Hoy.** El número de radicado encabeza la pantalla. La respuesta y el historial aparecen como texto corrido, con acciones internas del sistema expresadas como verbos y flechas.

**Cambio.** Dar prioridad al asunto, el estado en lenguaje cotidiano, la última actualización pública y la respuesta publicada. Para un caso recién radicado puede decir «Recibimos tu solicitud. Podrás consultar la respuesta aquí». Usar una cronología de los cambios públicos, incluyendo reaperturas cuando existan. Mostrar una fecha límite únicamente cuando haya un plazo aprobado y comunicable.

**Prueba.** La empresa entiende si ya recibió respuesta y dónde volver a consultarla. Solo ve el historial público de su organización.

### 11. Atención y Gerencia · bandeja e indicadores de PQRS

**Hoy.** Los tiempos y los casos abiertos por categoría aparecen como objetos JSON. Gerencia recibe enlaces a radicados cuyo detalle exige permisos de gestión o de consulta empresarial.

**Cambio.** Para Atención, empezar por «Requieren clasificación» y «Borradores por aprobar», con los casos correspondientes. Para Gerencia, abrir con pendientes y barras por categoría. Explicar «tiempo habitual hasta la primera atención» con la mediana en horas y presentar aparte el tiempo hasta la respuesta. Conservar en el detalle la definición de mediana. Recuperar el número de casos con tiempo medido por categoría para acompañar cada indicador. Aplicar los permisos existentes también a los enlaces.

**Prueba.** Atención identifica su siguiente caso. Gerencia puede decir qué categoría acumula más pendientes. Cuando todavía nadie ha respondido, la pantalla indica «Aún no hay respuestas para calcular el tiempo».

### 12. Atención · gestión de un caso

**Hoy.** La sugerencia, la categoría confirmada, el borrador y el texto publicado conviven con controles de cierre y reapertura. El formulario permite editar texto mientras el botón de aprobación opera sobre la versión guardada.

**Cambio.** Guiar al agente para revisar la categoría sugerida, preparar la respuesta y revisar lo que verá la empresa. Mostrar qué política sustenta cada afirmación y qué requiere revisión. Antes de publicar, comprobar que coincide el texto de la vista previa con la edición guardada. Ofrecer las acciones válidas para el estado actual y dejar la bitácora accesible.

**Prueba.** Atención corrige un borrador, revisa la versión final y comprueba que el texto publicado coincide con la vista previa. Una política retirada marca el borrador para revisión humana.

## Beneficios y asistente

### 13. Empresa · beneficios disponibles

**Hoy.** Cada tarjeta incluye vigencia, fuente e instrucciones, pero «Abrir una PQRS» lleva al formulario general y obliga a repetir el beneficio.

**Cambio.** Encabezar cada tarjeta con qué obtiene la empresa, hasta cuándo puede solicitarlo y qué condición debe cumplir. Diferenciar «Puedes solicitarlo» y «Atención debe revisar tu caso». Usar «Solicitar este beneficio» para abrir el formulario con el beneficio identificado, sujeto a confirmación por la persona. Incluir la política como fuente consultable según permisos.

**Prueba.** La empresa identifica el descuento de renovación de la demo, su vigencia y cómo pedirlo. El portal conserva el alcance de su organización.

### 14. Equipo interno · catálogo y retención

**Hoy.** Las condiciones de elegibilidad se leen y editan como JSON. Un beneficio puede figurar «publicado» antes del inicio de su vigencia. El contador titulado «Elegibles para reactivación» cuenta tareas de reactivación.

**Cambio.** Traducir condiciones a controles de empresa, segmento y datos requeridos. Mostrar una vista previa como «Aplica a empresas del segmento Recurrente en pausa». Indicar por separado estado editorial y fechas de disponibilidad. Nombrar el contador según su unidad y comparar por beneficio los seguimientos, los atendidos y las recuperaciones observadas. Antes de calcular tasas, acordar con Ventas la definición de recuperación y su ventana de observación.

**Prueba.** Atención entiende quién podría verlo antes de publicar. Gerencia diferencia tareas de empresas únicas y una recuperación observada de un efecto atribuible al beneficio.

### 15. Asistente · consultas del equipo interno

**Hoy.** Junto al texto se muestran herramienta, motor, versión y filtros técnicos. Los ejemplos dependen del perfil y del cierre, pero el historial de pantalla vive en memoria compartida durante la navegación por la aplicación.

**Cambio.** Presentar respuesta breve, periodo, alcance y «Ver los datos que sustentan esta respuesta». Para comparaciones con dos valores verificables, usar dos barras o una tabla pequeña. Para una definición, basta una frase. Reservar herramienta, versión y filtros originales para «Detalle técnico». Vincular historial y ejemplos a identidad, permisos y cierre. Ajustar las preguntas sugeridas a lo que cada perfil puede consultar.

**Prueba.** Un usuario puede reconstruir una cifra desde su fuente. Al cambiar de identidad, la conversación que aparece corresponde únicamente a la sesión actual.

### 16. Asistente · consultas de la empresa

**Hoy.** Las preguntas de ejemplo ya tratan casos y beneficios, pero el encabezado describe herramientas y modelos, y las respuestas usan el mismo formato técnico que las internas.

**Cambio.** Abrir con «Consulta tus beneficios o el estado de una solicitud». Para un caso, devolver asunto, estado público y enlace autorizado. Para un beneficio, resumir la condición y citar la política vigente. Si falta un radicado o una fuente válida, pedir el dato concreto u ofrecer el canal de Atención.

**Prueba.** Una persona obtiene el estado de su caso o entiende cuál es el dato que debe aportar. Puede consultar una política disponible para su empresa sin ver filtros técnicos ni referencias a otra organización.

## Finanzas e informes

### 17. Finanzas · ventas y compras a proveedores

**Hoy.** Ambas pestañas ya presentan historia y proyección. La leyenda mezcla método, error por horizonte y comparación con el método «ingenuo». El cuadro de mayores cambios reúne distintos meses y la gráfica solo dibuja el total.

**Cambio.** Titular cada pestaña con «¿Cuánto vendimos?» o «¿Cuánto compramos a proveedores?». Indicar último mes completo, importe y variación frente al anterior. Añadir selector de familia con las series ya publicadas y marcar el comienzo del pronóstico. Ofrecer una comparación por familia para **el mismo par de meses**, conservando aparte el listado de mayores cambios del histórico. En el detalle, traducir el error absoluto medio a «cuántos pesos se desvió en promedio» e identificar el horizonte evaluado.

**Prueba.** Finanzas distingue un mes incompleto, un mes con cero compras y un mes proyectado. Puede conciliar el valor mensual con su tabla y con el tablero. El total proviene de la serie publicada.

### 18. Finanzas · simulación del tipo de cambio

**Hoy.** «Simulador de TRM» exige conocer la sigla. Presenta base, escenario y diferencia, pero deja la interpretación al usuario. El servicio identifica compras sin tasa que la vista no explica.

**Cambio.** Preguntar «¿Cuánto cambiaría el costo de las compras en dólares si cambia el tipo de cambio?». Mostrar dos barras, costo base y simulado, con la diferencia escrita. Para octubre de la demo, el resultado sería «Si el dólar subiera 8 %, esas compras pasarían de 1.200.000 a 1.296.000 COP. Costarían 96.000 COP más». Debajo, ofrecer desglose por proveedor y familia, compras en pesos, supuestos y operaciones excluidas por falta de tasa. Distinguir escenario parcial, ausencia de compras y ausencia de exposición.

**Prueba.** Gerencia interpreta los 96.000 COP como un posible aumento del costo. Finanzas puede reconstruirlo con las operaciones incluidas. La simulación conserva el cierre publicado.

### 19. Archivo y generación de informes mensuales

**Hoy.** El enlace se llama «r1», junto a un identificador de cierre y una huella. Para Operaciones esta sección es todo lo que se ve bajo el título «Finanzas».

**Cambio.** Presentar «Abrir informe de octubre de 2026 · revisión 1», fecha, autor y estado. En el perfil que solo utiliza informes, nombrar la entrada «Informes mensuales». Explicar cuándo se reutilizó una revisión y dejar la huella de contenido en el detalle de verificación. Ofrecer generación solo a los perfiles habilitados.

**Prueba.** Finanzas encuentra la revisión disponible. Operaciones identifica el mes antes de generar y reconoce cuándo la aplicación reutiliza el mismo informe.

### 20. Informe mensual publicado

**Hoy.** El «Resumen ejecutivo» es una tabla de cifras. Más abajo se suceden tablas de cambios, segmentos, oportunidades y escenarios. La calidad del dato se imprime como información técnica. Las PQRS reflejan el momento de generación y las ventas corresponden al cierre.

**Cambio.** Abrir con lo que cambió, dónde se concentra la variación y qué merece revisión. Usar la comparación mensual y barras por acción principal. Etiquetar la fecha de referencia de cada bloque. Conservar tablas y metodología en un anexo imprimible de la misma revisión. Para incorporar una serie completa, guardarla junto con el contenido al generar el informe y preservar su reproducibilidad.

**Prueba.** La revisión de octubre reproduce los 51,15 millones de COP acumulados que muestra Gerencia. Al imprimirla, el lector conserva fecha, unidad, fuente y distinción entre hechos y escenarios.

## Documentos, calidad y operación

### 21. Documentos y políticas

**Hoy.** La tabla destaca ID, versión y «Frag.». En el formulario se elige empresa, pero no se ven los perfiles que recibirán acceso. «Retirar» tiene efecto sobre los borradores que citan la política.

**Cambio.** Encabezar con título, a quién aplica, vigencia y versión actual. Mostrar las versiones en una cronología por política. Antes de importar o retirar, indicar audiencia efectiva y consecuencia para el asistente y los borradores. Hacer visibles los perfiles autorizados en la previsualización. En «Probar consulta», mostrar respuesta, sección citada y enlace al fragmento autorizado. Dejar el recuento de fragmentos en el detalle.

**Prueba.** Atención identifica qué versión de la política de beneficios está vigente y qué audiencia podrá consultarla. Puede comprobar la sección de origen de una respuesta.

### 22. Operación del cierre

**Hoy.** Carga, ejecución, publicación, versiones, opciones de funcionamiento y respaldo compiten en una pantalla. «Frescura» significa días desde el corte. El mapeo de columnas requiere JSON y una carga confirmada todavía necesita incorporarse al proceso de cierre.

**Cambio.** Abrir con «Qué cierre está publicado», «Hasta qué fecha llegan los datos» y «Qué requiere atención». Organizar las herramientas según el trabajo que necesita hacer el equipo.

| Recorrido | Mejora y evidencia |
| --- | --- |
| Cargar y validar | Elegir archivo, hoja y columnas mediante controles. Mostrar una barra de filas aceptadas, duplicadas y aisladas cuando los conteos concilien. Junto a cada incidencia, explicar campo, causa y corrección. |
| Ejecutar y publicar | Distinguir confirmar un lote, ejecutar un cierre y publicar una salida preparada. Mostrar las etapas reales, su resultado, duración y último cierre válido si hay un fallo. |
| Revisar actividad | Ordenar lotes y ejecuciones por fecha. Mostrar primero el que requiere atención. La ficha técnica reúne rutas, versiones, intentos y errores originales. |
| Administrar y respaldar | Nombrar cada función por su efecto visible. Explicar qué cambia al desactivar la predicción. Dar al respaldo una confirmación con fecha y archivo. |

**Prueba.** Operaciones puede responder «¿qué datos ven los usuarios ahora?», localizar una fila que debe corregir y explicar qué paso falta para que el lote se vea publicado.

### Material complementario · visor local de referencia

El paquete de prueba también incluye un HTML independiente con una tabla filtrable y un detalle que muestra el registro como JSON. Si se utiliza en formación, mantener la advertencia de que es una fotografía precalculada, mostrar el recuento seleccionado y presentar el detalle como «última compra», «días sin comprar», «coberturas» y «motivo de prioridad». Dejar el registro original desplegable para la persona técnica. La prueba consiste en explicar la prioridad de un cliente usando los campos visibles y reconocer la fecha fija del ejemplo.

## Orden de entrega y validación

| Entrega propuesta | Responsable sugerido | Resultado para darla por terminada |
| --- | --- | --- |
| 1. Lectura del negocio | Producto, Gerencia y Ventas con el equipo de interfaz | Probar ingreso por rol, tablero de Gerencia, agenda y ficha con la demo. Conciliar mes, acumulado y selección. Aplicar desde esta entrega los permisos a enlaces y el aislamiento de conversaciones. |
| 2. Decisiones de ventas, cobertura y costos | Ventas, Operaciones y Finanzas con los equipos de datos e interfaz | Probar los otros dos tableros, lista y detalle de seguimiento, series financieras, simulador y ambas vistas de informes. Entregar cada gráfica con su tabla y origen. |
| 3. Servicio y publicación | Atención y Operaciones con los equipos de aplicación y datos | Completar solicitudes, beneficios, ambos asistentes, documentos y cierre. Validar por separado el recorrido de una empresa y el de los equipos internos. |

**Dependencias de datos.** Las barras por acción, los segmentos, los días hasta vencimiento, la comparación de meses y el escenario cambiario ya tienen datos de origen. Para tasas por cohorte, totales de listas limitadas, tendencias históricas de solicitudes o una tasa de recuperación comercial hacen falta conteos, series o definiciones adicionales. Publicar cada indicador cuando tenga periodo, población y fuente verificables. Una lista parcial de oportunidades o los últimos 20 movimientos de una ficha sirven para examinar casos individuales.

**Prueba con personas.** Usar el mismo cierre sintético antes y después del rediseño. Pedir a Gerencia que explique el cambio mensual, a Ventas que priorice y justifique un contacto, a Finanzas que reconstruya el escenario, a Operaciones que identifique un vencimiento y el cierre activo, a Atención que compruebe la fuente de un borrador y a una empresa que encuentre su beneficio y su radicado. Registrar tiempo, acierto, dudas y necesidad de ayuda. Como objetivo inicial, que al menos cuatro de cada cinco participantes de cada perfil completen su tarea sin ayuda cuando se alcance esa muestra. Ningún participante debería interpretar un pronóstico como ingreso confirmado.

**Lectura accesible.** Cada gráfica tendrá título en palabras del negocio, periodo, unidad, valores consultables con teclado o tacto y tabla equivalente. Usar escalas legibles también para cifras inferiores a un millón. Nombrar estados y distinguirlos con texto o trazo además del color. Comprobar en móvil que la conclusión y la acción principal siguen visibles, y que los importes exactos se pueden leer al ampliar.

**Referencias del proyecto.** [Vistas y navegación](../../app/app.js) · [Consultas de cartera y tableros](../../api/consultas.py) · [Finanzas e informe publicado](../../api/finanzas.py) · [Permisos por perfil](../../api/permisos.py) · [Guion de pruebas por rol](../demo.md) · [Datos del cierre de demostración](../../contratos/ejemplos/publicacion/demo-2026-10/).

## Estado de implementación

Implementado en la rama `feat/mejora-de-vistas` sobre el cierre sintético de octubre de 2026. La interfaz se dividió en `app/nucleo.js`, `app/ui.js` y `app/vistas/` (una vista por área). Los componentes comunes aplican las reglas de lectura: frase de respuesta con periodo y unidad, barras con valor escrito y «Ver datos y cálculo» con tabla, fuente, filtros y regla.

| Entradas | Pantallas | Cambios en la API (aditivos) |
| --- | --- | --- |
| 1 | Tres entradas de origen, identidad solo con el cierre publicado, ayuda técnica plegada, entrada por perfil y elección para Operaciones | — |
| 2–3 | Agenda con barras por acción, selección y exportación con su alcance; ficha con recomendación, estimación, oportunidades y línea de tiempo | CSV con los filtros de la vista; ficha con oportunidades, fecha sugerida, modelo y total de operaciones |
| 4–6 | Tableros de Ventas, Operaciones y Gerencia | Segmentos ordenados con descripción, límite de oportunidades, intervalos de cobertura, comparación mensual por familia y fuente |
| 7–8 | Seguimientos con cupo, alcance de la medición, acciones por intención, cronología y aviso de conflicto | Pendientes antes del cupo; datos de cada evento |
| 9–12 | Solicitudes de la empresa, detalle público, bandeja e indicadores, gestión guiada del caso | Historial público sin acciones internas, última actualización y casos medidos por mediana |
| 13–14 | Beneficios con condición y «Solicitar este beneficio»; catálogo con criterio por controles y vista previa | Condición en palabras, disponibilidad por fechas, tareas frente a clientes únicos |
| 15–16 | Asistentes con alcance, sustento y detalle técnico; conversación por identidad y cierre; enlaces según permisos | Estado del caso en lenguaje cotidiano en el portal |
| 17–20 | Finanzas por pregunta, familias y par de meses; simulador con frase, barras y exclusiones; informes por mes; informe que abre con lo que cambió | Comparación mensual, operaciones incluidas y en pesos, escenario parcial, informe con serie guardada y anexo |
| 21–22 | Documentos por política con audiencia y confirmación en página; operación con tres preguntas y cuatro recorridos | Encabezados del archivo, columnas esperadas y efecto de cada función |

**Verificación.** `tests/app/test_app_vistas.py` comprueba las cifras de este plan (4,56 y 21,02 millones; Infraestructura −16,44; DEMO02 y DEMO06 con 12,56 millones; 96.000 COP) y la sintaxis de los módulos. Se recorrieron en el navegador los perfiles de Gerencia, Ventas, Empresa, Atención y Operaciones y la demostración sin sesión.

**Móvil.** Se midieron 21 vistas de los seis perfiles en una ventana de 394 px: ninguna se desborda hacia los lados, y la frase principal y la acción quedan en la primera pantalla. La agenda pasa a tarjetas en pantallas estrechas.

**Accesibilidad automatizada.** En las vistas de los seis perfiles, con temas claro y oscuro, se revisó lo que expone el navegador a un lector de pantalla. Todos los controles tienen nombre accesible, cada gráfica tiene descripción y una tabla equivalente, y el texto cumple el contraste mínimo de WCAG AA (4,5:1; 3:1 en texto grande). La revisión encontró y corrigió el texto blanco sobre el verde claro de los botones en modo oscuro (2,2:1). No sustituye a la prueba con un lector real en un teléfono.

**Material complementario.** `docs/formacion/visor-formacion.html` es la versión de formación del visor local. La genera `python docs/formacion/generar_visor.py`, que comprueba la huella del original contra `MANIFIESTO_SHA256.txt` y no lo modifica. Muestra la advertencia de fotografía precalculada con su fecha fija, el recuento seleccionado y el detalle en palabras, con el registro original desplegable. También corrige el texto «frío» dañado en los datos del original.

**Prueba con personas.** El guion, las consignas por perfil con su respuesta correcta y la hoja de registro están en [prueba-con-personas.md](prueba-con-personas.md). Su ejecución requiere participantes reales y queda a cargo del equipo, al igual que la confirmación en teléfonos reales.
