# Tareas de B | Aplicación, atención y operación

[Volver al plan integral y al orden de integración](../../PLAN_IMPLEMENTACION.md)

Cada ticket identifica el dato real que necesitará en integración y el sustituto que permite empezar ahora. Usar dos empresas ficticias, dos usuarios externos y usuarios internos de Ventas, Operaciones, Finanzas y Atención en las pruebas. El servidor determina qué registros y acciones corresponden a cada identidad.

### B01 · Definir contratos, preparar muestras y abrir la aplicación local

**Puede empezar con A01.** Entrega a A los esquemas versionados y una prueba de compatibilidad. La primera vista depende únicamente de C1.

1. Transcribir el contrato de la [agenda](../../PLAN_HACKATON.md) a un esquema comprobable. Versionar ejemplos de cierre válido, vacío, incompleto e incompatible. Incluir cliente frecuente y frío, cobertura próxima, cliente sin compras y probabilidad cero. Para C2–C4, añadir ejemplos mínimos al iniciar el primer ticket consumidor.
2. Implementar un lector de archivo local servido por HTTP. Validar esquema, tipos y claves antes de pintar la vista. Mostrar origen, fecha y estado de carga. El usuario selecciona explícitamente el modo de práctica. Entregar a A un comando de validación independiente de la pantalla.
3. Documentar el arranque desde un clon limpio y acordar claves, ordenación y tratamiento de nulos. Mantener los ejemplos en un directorio distinto de las salidas de ejecución.

**Probar.** Abrir el JSON válido, retirar el archivo, introducir una versión desconocida, repetir un ID y usar `null` y 0 para puntuación. Comprobar estados de carga, error y lista vacía. La selección de origen debe seguir visible.

**Evaluar y aceptar.** A puede validar su salida sin iniciar la web. B puede enseñar la agenda sin ejecutar el entrenamiento. Un cambio incompatible falla en la prueba de contrato antes de fusionar las ramas.

### B02 · Identidad, persistencia y publicación consistente

**Depende de B01.** Desarrollar con un cierre ficticio. Integrar el primer cierre de A cuando sus tablas estén disponibles.

1. Crear migraciones para organizaciones, identidades, pertenencias, permisos, lotes, cierres y vistas analíticas. Acordar con Green la matriz de acceso. Como punto de partida, Operaciones publica cierres, Ventas tramita oportunidades, Finanzas consulta exposición y Atención tramita PQRS. El usuario empresarial consulta únicamente sus beneficios y casos habilitados.
2. Integrar autenticación de sesión con el proveedor aprobado para el piloto. Resolver en el servidor rol y empresa en cada operación, incluidas búsquedas, exportaciones y lectura de documentos. La demo local usa identidades ficticias. Evitar publicar el JSON completo de cartera como archivo estático del portal.
3. Importar C2 a un área temporal, comprobar conteos y claves y activar el identificador del cierre en una transacción. Usar restricción única por revisión y controlar publicaciones concurrentes. Separar los datos operativos modificables de los cierres reproducibles. Registrar actor, acción, revisión y resultado.
4. Dar a Operaciones una pantalla de carga CSV/Excel para elegir periodo, tabla y hoja, previsualizar el mapeo y ejecutar A01. Mostrar filas aceptadas, duplicadas y aisladas antes de confirmar el cierre. Si el proceso falla, ofrecer el detalle por fila y permitir reintentar con el archivo corregido. La carga manual y la mensual programada deben usar la misma validación.

**Probar.** Dos publicaciones idénticas simultáneas producen una sola revisión activa. Una importación interrumpida conserva el cierre anterior. Probar sesión ausente, interna con permisos insuficientes y externa de otra empresa en lectura por ID, listado y exportación.

**Evaluar y aceptar.** Cada combinación rol/acción tiene resultado esperado en la matriz de pruebas. Cero registros ajenos en las consultas de las empresas de ensayo. Comparar métricas en base de datos con el manifiesto y comprobar el cambio atómico entre cierres desde dos sesiones.

### B03 · Construir la ficha, la agenda de lectura y los tableros por rol

**Depende de B01.** Usar muestras de C1/C2. El piloto integrado requiere B02 y datos de A03. Las puntuaciones y segmentos se incorporan conforme estén disponibles.

1. Implementar consultas por cierre para resumen, búsqueda de clientes, detalle y agenda. Ordenar de forma estable por prioridad, probabilidad y cliente. Paginar después de ordenar y calcular totales con el mismo conjunto filtrado. Identificar cuando una tarjeta representa toda la cartera.
2. En Ventas, mostrar comprador, productos adquiridos, historial, RFM, segmento y motivo del seguimiento. En Operaciones, mostrar ventana estimada, coberturas y acción pendiente. En Gerencia, mostrar ingresos, compras, evolución y clientes por segmento. Los componentes financieros y de PQRS se conectan en B09 y B04. Distinguir gráfica histórica, predicción y simulación en etiquetas y unidades.
3. Implementar filtros por periodo, segmento y acción, búsqueda por ID y navegación lista → ficha → lista conservando filtros. Mostrar «Sin historial», «Modelo no disponible» y «Sin coincidencias» según el dato. Las etiquetas frecuente/frío se pueden superponer, por lo que sus recuentos pueden superar el número de clientes si se suman.

**Probar.** Filtrar una cartera con dos acciones iguales, navegar por teclado al detalle y regresar. Cambiar de mes durante una carga y comprobar que la respuesta anterior no reemplace la nueva. Comparar API, ficha y tablero para el mismo cliente y corte. Revisar etiquetas y unidades en pantalla pequeña.

**Evaluar y aceptar.** Un usuario de cada rol realiza una tarea observable: Ventas explica una prioridad, Operaciones identifica una cobertura y Gerencia reconcilia un indicador con el cierre. Registrar errores de interpretación, tiempo y cambios necesarios. Repetir las tareas en las que se confundió una alerta con una venta confirmada.

### B04 · Registrar, consultar y resolver PQRS

**Depende de B02 para el piloto.** El formulario, la máquina de estados y la bandeja pueden empezar con casos ficticios. Entrega C3 para A10.

1. Definir caso con radicado único, empresa, solicitante, fecha, descripción, categoría propuesta/revisada, responsable y estado. Implementar alta, listado filtrado, detalle y bitácora. Proponer el flujo recibido → en gestión → respondido → cerrado y acordar reapertura, plazos y estados definitivos con Atención.
2. El cliente crea y consulta sus casos según su permiso. Atención asigna, corrige categoría y registra respuesta. Guardar cada transición con fecha y actor y validar el estado previo. Soportar reintentos del formulario con clave de idempotencia y edición concurrente con versión del registro.
3. Agregar bandeja de pendientes, antigüedad por estado y conteos para Gerencia. Identificar vencimientos solo cuando exista un plazo aplicable aprobado. Preparar exportación anonimizada y autorizada de texto y etiquetas revisadas para A10.

**Probar.** Doble envío devuelve el mismo radicado. Dos operadores editan el mismo caso y el segundo ve el conflicto. Una transición inválida se rechaza. Cerrar y reabrir conserva el historial. Un usuario de la empresa B no puede consultar ni inferir el contenido de un caso de A.

**Evaluar y aceptar.** Desde el portal radicar un caso, localizarlo en la bandeja y consultar después la respuesta publicada. Conciliar pendientes con los estados registrados. Medir tiempo hasta primera gestión y resolución por categoría, indicando los casos que siguen abiertos.

### B05 · Convertir recomendaciones en agenda, alertas y resultados

**Depende de B02/B03.** Usar oportunidades ficticias de C2 mientras A04–A07 entregan puntuaciones, segmentos y motivos.

1. Separar oportunidad calculada de tarea humana. Para cada episodio guardar responsable, fecha sugerida de revisión, todos los motivos, estado y resultado. Permitir asignar, posponer, descartar con motivo, marcar atendida y registrar el siguiente paso.
2. Generar avisos internos en cambios de prioridad y vencimientos. Usar una clave de deduplicación por episodio y tipo de aviso. Respetar el aplazamiento y el cierre manual al regenerar el mes. Si la evidencia cambia, conservar la anterior para explicar por qué apareció la tarea.
3. Publicar eventos C3 para medir exposición y atención. Diferenciar «compra posterior observada», «contacto registrado» y «resultado atribuido al seguimiento». Conservar la decisión humana antes de cualquier contacto empresarial.

**Probar.** Reprocesar un lote, recibir dos veces el mismo aviso, posponer hasta otro mes y cerrar una oportunidad desde dos sesiones. Una renovación y una señal de inactividad coexistentes conservan sus dos motivos. Si se retira la versión del modelo, se puede consultar la evidencia histórica.

**Evaluar y aceptar.** Un vendedor puede planificar su cupo de K contactos, explicar el primero y tramitar su resultado. Medir avisos duplicados, tareas abiertas por episodio, fracción atendida y tasa de descarte por tipo. A11 debe poder reconstruir el denominador desde los eventos.

### B06 · Portal de beneficios, fidelización y retención

**Depende de B02.** Usar catálogo ficticio hasta recibir beneficios, criterios y textos autorizados. Los datos de A05/A07 enriquecen la vista interna de retención.

1. Crear catálogo con ID, empresa emisora, título, descripción, fuente aprobada, vigencia, criterio de elegibilidad, versión y estado de publicación. Preparar vista interna para crear borrador, revisar, publicar y retirar. Registrar la política que justificó cada decisión de elegibilidad.
2. Implementar el portal empresarial de beneficios y servicios disponibles usando el ámbito de la sesión. Indicar cómo solicitar información o abrir una PQRS. Si la elegibilidad requiere un dato ausente, derivar a revisión. Mantener las puntuaciones internas de riesgo en la vista de Ventas.
3. En Ventas relacionar una iniciativa de fidelización con el segmento, motivo y resultado del seguimiento. Consultar desde el portal únicamente las condiciones aprobadas. El asistente de B10 reutilizará la misma consulta autorizada.

**Probar.** Beneficio futuro, vigente hoy, vencido, retirado, exclusivo de otra empresa y con criterio de elegibilidad incompleto. Acceder por enlace directo debe aplicar los mismos controles que la lista. Un cambio de elegibilidad se refleja tras publicar la revisión.

**Evaluar y aceptar.** Comparar el catálogo visible con una matriz manual empresa × beneficio × fecha. Atención valida el texto y los casos dudosos. Para retención medir elegibles, seguimientos realizados y recuperaciones observadas en la ventana definida con Ventas.

### B07 · Agente de consultas sobre datos e indicadores

**Depende de B02/B03.** Desarrollar primero las herramientas con respuestas deterministas. Conectar el componente de lenguaje en un entorno autorizado y registrar su versión.

1. Definir herramientas de solo lectura para historial de cliente, ventas por periodo, compras por proveedor, productos, oportunidades y explicación de indicadores. Cada entrada recibe parámetros tipados y límites de filas. Identidad y alcance proceden de la sesión.
2. Traducir la pregunta a intención y parámetros. Pedir aclaración cuando «compras» pueda referirse a ventas a clientes o adquisiciones a proveedores, o cuando falte periodo. El servicio calcula cifras y variaciones. Devolver evidencia con corte, unidad, filtros y referencia al detalle.
3. Generar la respuesta a partir del resultado estructurado. Ante cliente desconocido, periodo incompleto o proveedor de lenguaje caído, devolver estado explícito y permitir consulta mediante filtros. Registrar herramienta, latencia y corrección de la respuesta con contenido mínimo.

**Probar.** Preparar preguntas con respuestas calculadas previamente: «¿qué compró este cliente?», «¿a qué proveedores compramos en agosto?» y «¿qué clientes redujeron compras entre dos periodos comparables?». Añadir una pregunta ambigua, un periodo sin datos y una comparación con periodo base cero. Contrastar cifras, unidades, corte e IDs con la consulta directa.

**Evaluar y aceptar.** Reservar reformulaciones que no se usaron para ajustar el asistente. Medir selección correcta de herramienta, exactitud numérica, identificación de filtros y abstención en preguntas irresolubles. Una cifra de aceptación debe coincidir con el cálculo determinista al redondeo mostrado. Una respuesta que exceda permisos bloquea la habilitación del módulo para ese rol.

### B08 · Recuperación documental y respuestas con fuentes (RAG)

**Depende de B02 y el contrato de B07.** Empezar con un manual y dos versiones de una política ficticia. La aceptación empresarial requiere un corpus aprobado.

1. Inventariar documentos con propietario, permisos, empresa, versión, vigencia y estado. Extraer texto por sección o página, mantener esos localizadores y revisar que las tablas con condiciones se hayan interpretado correctamente. Importar, actualizar y retirar documentos con trazabilidad.
2. Indexar fragmentos con texto, localizador y metadatos. Empezar con búsqueda por palabras, comparar recuperación semántica o híbrida si mejora las consultas de prueba. Limitar la búsqueda a fuentes autorizadas y vigentes antes de entregar fragmentos al generador.
3. Responder citando documento, versión y página/sección. Ofrecer acceso autenticado a la evidencia. Si hay versiones contradictorias sin precedencia definida o información insuficiente, explicar la incertidumbre y remitir a Atención. Invalidar resultados almacenados al retirar una política o cambiar permisos.

**Probar.** Paráfrasis que exige recuperar la misma política, una pregunta fuera del corpus, dos políticas contradictorias, un documento vencido y uno de otra empresa. Retirar el único documento válido después de una consulta y repetirla. Verificar que el texto recuperado se trate como contenido de referencia.

**Evaluar y aceptar.** Atención prepara preguntas con fragmento esperado, respuesta permitida y casos de abstención. Medir recuperación del fragmento correcto en los primeros K, proporción de afirmaciones respaldadas y abstenciones correctas. Revisar manualmente citas que existen pero no sustentan la conclusión. Exigir fuente vigente y autorizada para cada condición empresarial publicada.

### B09 · Panel financiero e informe automático mensual

**Depende de B03.** Montar las vistas con meses y escenarios ficticios. Integrar ventas y compras de A02, pronósticos de A08 y escenarios de A09.

1. Visualizar histórico y proyección por mes/familia con unidades, horizonte, método, fecha de cálculo y error observado. Mostrar cambios de compras y tendencias de ventas. Identificar el nivel de agregación y diferenciar valores faltantes de meses con cero.
2. Crear un simulador con periodo, moneda de exposición y variación porcentual. Mostrar base, simulado, diferencia COP y supuestos de costos. Cuando falte trazabilidad de margen, identificar el indicador disponible como variación de costo. El escenario nunca sobrescribe el cierre.
3. Generar un informe mensual a partir del cierre publicado: resumen ejecutivo, variaciones, segmentos, oportunidades, exposición cambiaria, calidad y limitaciones del modelo. Usar una plantilla HTML imprimible con metadatos y totales calculados por el servicio. Conservar la revisión exacta del informe y limitar su acceso por rol.

**Probar.** Generar dos veces la misma revisión y comparar el contenido de negocio. Cambiar el corte y comprobar que cambian todos los apartados. Probar escenario 0 % y +8 %, periodo incompleto y fallo del pronóstico. Conciliar tarjetas, gráfica, informe y servicio para la misma selección.

**Evaluar y aceptar.** Finanzas puede reconstruir la diferencia de 96.000 COP del caso de A09 y localizar el mayor cambio mensual por familia. Operaciones compara tiempo y errores al preparar el mismo informe con el procedimiento habitual y con la aplicación. Registrar ambos tiempos y el número de correcciones necesarias.

### B10 · Atención asistida, enrutamiento y borradores de PQRS

**Depende de B04/B06/B07/B08.** Usar clasificador simulado bajo C4 mientras A10 prepara y evalúa el modelo.

1. Incorporar al alta una sugerencia de categoría y responsable. Si la clasificación llega tarde o tiene baja confianza, mantener el caso visible en la bandeja de revisión. Persistir por separado sugerencia, decisión humana y versión. Reprocesar un caso conserva las correcciones del operador.
2. En el contexto autenticado, enrutar preguntas sobre estado a la herramienta de PQRS, beneficios al catálogo y políticas al recuperador documental. Para responder una PQRS, combinar solo hechos del caso y disposiciones vigentes. Crear un borrador editable con sus fuentes y versión.
3. Mostrar al responsable la descripción original, clasificación, borrador y citas. Exigir acción explícita de aprobación para publicar al cliente y guardar quién aprobó. Si cambia el caso o se retira la política antes de publicar, marcar el borrador para revisión. Exponer al cliente la respuesta aprobada y su estado.

**Probar.** Baja confianza lleva a revisión, corrección humana prevalece, un borrador pendiente permanece interno y una doble aprobación genera una sola publicación. Consultar un caso de otra empresa o pedir beneficios fuera de vigencia debe respetar los mismos permisos y criterios que las pantallas del portal.

**Evaluar y aceptar.** Atención revisa una muestra reservada por categoría y califica fidelidad al caso, respaldo de cada condición, utilidad y necesidad de edición. Medir tasa de correcciones, borradores aceptados y tiempo de resolución frente al proceso manual. Si falta evidencia para una condición, el borrador debe solicitar revisión.

### B11 · Automatizar pruebas, operar el cierre y preparar el piloto

**Depende de los módulos que se publicarán.** Comenzar las pruebas de contrato desde B01 y ampliar la suite en cada integración. Este ticket reúne las comprobaciones finales y el procedimiento de recuperación.

1. En cada cambio ejecutar pruebas unitarias, contratos productor/consumidor e integración de base con migraciones. Para cada entrega ejecutar flujos de navegador con dos empresas y los roles internos. Separar datos sintéticos reproducibles de pruebas con información empresarial autorizada.
2. Preparar entorno de ensayo y entorno de piloto. Configurar secretos fuera del repo, retención y acceso a registros según lo acordado con Green. Programar el cierre mensual con ID de ejecución, reintentos seguros y publicación después de validar. Registrar duración por etapa, frescura, filas rechazadas, modelos usados y última publicación válida.
3. Ensayar copia de respaldo y restauración en un entorno aislado. Versionar esquema, cierre, aplicación, documentos y modelos para recuperar una combinación compatible. Acordar con Operaciones cuánto dato puede recuperar y en cuánto tiempo. Probar desactivación independiente del asistente o de una versión del modelo, manteniendo las tareas y PQRS existentes.
4. Ejecutar el piloto con usuarios designados y un guion por rol. Registrar errores funcionales, latencia observada de las consultas habituales y comprensión de las recomendaciones. Corregir y repetir el mismo recorrido. Capacitar a la persona que ejecutará el siguiente cierre y dejarle el procedimiento.

**Probar.** Simular carga interrumpida, reejecución, indisponibilidad del modelo, documento retirado, caducidad de sesión y restauración de un respaldo conocido. Verificar que las acciones confirmadas antes del respaldo reaparecen y documentar el tratamiento de los eventos posteriores según el punto de recuperación acordado.

**Evaluar y aceptar.** En un entorno limpio, otra persona publica un cierre, revisa una oportunidad, reproduce el informe, resuelve una PQRS y restaura el servicio siguiendo el procedimiento. Entregar versión probada, resultados por rol, incidentes abiertos, tiempos de recuperación medidos y decisión de Green sobre cada módulo listo para el piloto.
