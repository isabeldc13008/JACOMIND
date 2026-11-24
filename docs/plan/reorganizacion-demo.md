# JACOMIND · Reorganización de vistas para la demo

Fecha: 24 de noviembre de 2026. Audiencia: gerencia y equipos de trabajo.

**Requisito de audiencia actualizado:** diseñar para personas con muy poca experiencia digital, incluidos adultos mayores. Aplicar el [prompt de implementación accesible](prompt-implementacion-demo-accesible.md): lenguaje cotidiano, lectura principal de 18 px como referencia, controles amplios y detalle progresivo sin pérdida de información. Sus requisitos de accesibilidad y densidad prevalecen sobre las medidas más compactas de este plan.

**Propuesta:** presentar JACOMIND como una herramienta para entender el negocio, decidir a quién atender y ejecutar el siguiente paso. La navegación debe organizarse por trabajo —Clientes y ventas, Operaciones, Finanzas, Atención y Administración— con un Inicio adaptado al perfil. Los modelos aparecen dentro de esas decisiones; su evaluación técnica queda disponible en un centro de modelos y monitoreo.

Este documento es un plan de implementación. No modifica las pantallas ni declara que la aplicación ya esté lista para presentar. Actualiza el enfoque de [mejora-de-vistas.md](mejora-de-vistas.md), varias de cuyas propuestas ya están implementadas, e incorpora las vistas de los modelos actuales. Los ejemplos numéricos de aquel documento pertenecen a otra demostración y no deben copiarse al recorrido nuevo.

## 1. Revisión y diagnóstico

### Alcance y evidencia

- Se revisaron el enrutador, navegación, estilos y componentes compartidos, los 16 módulos de vistas y las capacidades definidas en `api/permisos.py`.
- Se inspeccionaron visualmente Entrada, Gerencia y Agenda; también se comprobaron en navegador el contenido y contexto de Próxima compra, Pronóstico de demanda y Operaciones atípicas. Las demás propuestas se apoyan en el código y sus contratos, no en una prueba visual completa de cada variante.
- La revisión adicional utilizó una copia de la base de demostración con datos completos en `salida/revision_ui_demo_2026_11_24/demo_completa.sqlite3`. No se publicaron cierres, enviaron respuestas, aprobaron recomendaciones ni cambiaron datos de negocio durante esta revisión.
- Quedan pendientes las pruebas de comprensión con personas de los perfiles objetivo, la revisión responsive completa y la validación visual del rediseño implementado.

### Hallazgos que determinan el plan

| Prioridad | Observación actual | Consecuencia para la demo | Decisión |
| --- | --- | --- | --- |
| P0 | Gerencia tiene 14 enlaces principales; conviven módulos operativos, modelos y administración. | El presentador debe explicar el menú antes de demostrar valor. | Agrupar por áreas y mostrar únicamente las autorizadas para cada rol. |
| P0 | En la copia revisada, la cabecera indica cierre del 30/09/2026, mientras Próxima compra y Demanda trabajan con publicaciones de octubre. | Una recomendación puede parecer calculada con el corte que ve el usuario arriba. | Mostrar contexto por panel y coherencia de fechas; no cambiar una etiqueta para aparentar sincronía. |
| P0 | Demanda ya dispone de histórico y horizontes de 1–3 meses, pero los muestra solo en una tabla. | Una capacidad valiosa resulta difícil de explicar a simple vista. | Gráfico principal de histórico y pronóstico, con tabla de respaldo e incertidumbre cuando exista. |
| P0 | La ficha reúne señales M1–M4 y varias tablas en secuencia; la agenda repite bastante texto por fila. | Cuesta identificar qué hacer con un cliente. | Ficha 360 con acción principal, evidencia y pestañas; lista comercial más breve. |
| P0 | Aparecen identificadores como `seg_1`, `ventas_cop:Total` y ejemplos `DEMO01` en un paquete con clientes `CLI...`. | Se percibe una herramienta técnica y se pueden abrir ejemplos inexistentes. | Etiquetas comprensibles, identificadores secundarios y ejemplos derivados del conjunto activo. |
| P1 | Hay buenas explicaciones y advertencias, pero algunos bloques experimentales y de método preceden al trabajo principal. | El usuario lee mucho antes de encontrar clientes o decisiones. | Mantener estado y límites críticos visibles; mover metodología a detalle progresivo. |
| P1 | Finanzas reúne resultado, proyección operativa, simulación TRM e informes en una página extensa. | Cambia la pregunta de negocio varias veces durante el desplazamiento. | Dividir en subpestañas con contexto compartido. |
| P1 | La presentación usa una jerarquía tipográfica pequeña y superficies similares; el tema depende del sistema. | En proyección pierde jerarquía y puede verse demasiado oscura. | Sistema visual más legible y tema explícito para la demo. |
| P1 | Modelos de IA y Monitoreo son destinos separados y no representan el mismo inventario. | Se duplica explicación y se confunde disponibilidad con calidad predictiva. | Unificar su acceso manteniendo las restricciones por modelo y perfil. |

**Conservar lo que ya funciona:** explicaciones en español, fuentes y cálculo desplegables, distinción entre datos sintéticos y reales, control por permisos, barras que filtran la agenda, historial mensual y acceso al detalle. La exportación filtrada de cartera ya está contemplada en el código actual; no debe tratarse como un defecto pendiente del plan anterior.

### Resultado de la comprobación estática

El analizador de diseño en modo estricto produjo 21 señales: 9 posibles botones sin acción detectable, 4 formularios sin contrato explícito de validación, 3 controles de texto sin regla compartida de tamaño y 5 decisiones sin documentar sobre controles nativos de selección/fecha. Resultado guardado en `salida/revision_ui_demo_2026_11_24/auditoria_ui.json`.

Es un diagnóstico heurístico: **no son 21 fallos funcionales confirmados**. Por ejemplo, los botones de valoración y sugerencias del asistente tienen manejadores en el código. Antes de corregir cada señal hay que comprobar su comportamiento y registrar la propiedad del componente. No eliminar controles funcionales ni desactivar validación del navegador sin implementar errores accesibles equivalentes.

## 2. Arquitectura de información

### Menú propuesto

| Área principal | Contenido | Pregunta de negocio |
| --- | --- | --- |
| Inicio | Resumen propio del rol; Gerencia abre la visión ejecutiva. | ¿Qué necesita mi atención? |
| Clientes y ventas | Cartera, Retención, Momento de contacto, Productos sugeridos, Seguimientos; ficha 360 como detalle. | ¿A quién atender, por qué y con qué propuesta? |
| Operaciones | Coberturas y renovaciones; Operaciones atípicas. | ¿Qué vence y qué operación necesita revisión? |
| Finanzas | Resultado, Pronóstico, Escenarios TRM, Informes. | ¿Qué ocurrió y cómo prepararnos? |
| Atención | Solicitudes, Beneficios, Base de conocimiento. | ¿Qué necesita el cliente y cómo responder con respaldo? |
| Administración | Datos y cierres, Modelos y monitoreo, Actividad, Configuración y respaldos. | ¿Con qué información y controles estamos trabajando? |

El asistente permanece accesible desde la cabecera y conserva su ruta completa. En una fase posterior podrá abrirse como panel contextual desde una cifra, un cliente o un caso. No debe ocupar el mismo nivel que todas las áreas de negocio.

**No todos los perfiles ven las seis áreas.** El menú se genera desde capacidades, no desde una lista fija ni desde nombres de rol escritos repetidamente en las vistas. Los permisos del servidor siguen siendo la autoridad.

| Perfil | Entrada y navegación útil | Restricciones que deben conservarse |
| --- | --- | --- |
| Gerencia | Inicio ejecutivo; vistas de consulta comerciales, operativas, financieras y de atención; monitoreo. | No adquiere gestión de tareas o revisión de anomalías por ver el resumen. |
| Ventas | Inicio comercial/Cartera; seguimiento; señales M1–M4; beneficios autorizados. | Sin exportar cartera cuando carezca de `cartera.exportar`; sin publicar beneficios ni ver finanzas por esta reorganización. |
| Operaciones | Inicio operativo; coberturas; anomalías; datos y cierres; demanda en unidades; informes y monitoreo autorizados. | Demanda en COP y otras cifras financieras únicamente con su capacidad específica. |
| Finanzas | Resultado; demanda; escenarios; informes; anomalías y monitoreo autorizados. | No obtiene acceso a fichas de cartera, gestión comercial o publicación de cierres. |
| Atención | Bandeja de solicitudes; catálogo de beneficios; conocimiento; asistente. | Respuesta pública solo mediante el flujo de revisión/aprobación existente. |
| Empresa | Portal propio: beneficios, solicitudes, asistente. | Solo su empresa; sin señales internas de riesgo, puntuaciones, cartera ni datos de otras empresas. |

### Rutas y compatibilidad

La primera entrega puede conservar todas las rutas existentes y cambiar la organización visual. No es necesario introducir un router o framework nuevo.

| Ruta actual | Destino conceptual | Tratamiento |
| --- | --- | --- |
| `#/inicio` | Acceso y origen | Conservar; no usarla como inicio ejecutivo autenticado. |
| `#/bienvenida` | Inicio de Operaciones | Conservar y simplificar. |
| `#/tableros/gerencia` | Inicio ejecutivo | Conservar. |
| `#/tableros/ventas`, `#/agenda` | Inicio comercial y Cartera | Unificar experiencia con pestañas Resumen/Cartera; conservar enlaces entrantes. |
| `#/clientes/:id` | Cliente 360 | Conservar contexto de retorno. |
| `#/tareas`, `#/tareas/:id` | Seguimientos y detalle | Conservar. |
| `#/prevencion` | Retención | Renombrar navegación, no contratos del modelo. |
| `#/proxima` | Momento de contacto | Renombrar navegación. |
| `#/venta-cruzada` | Productos sugeridos | Renombrar navegación. |
| `#/tableros/operaciones` | Coberturas y renovaciones | Conservar. |
| `#/anomalias` y parámetro `caso` | Operaciones atípicas y detalle | Conservar filtros y enlace directo al caso. |
| `#/finanzas` | Resultado, Escenarios e Informes | Añadir una sección en URL; respetar enlaces existentes. |
| `#/demanda` | Finanzas → Pronóstico | También accesible desde Operaciones para unidades; un mismo componente. |
| `#/pqrs`, `#/pqrs/:radicado` | Atención o Portal según capacidades | Conservar variantes y aislamiento. |
| `#/beneficios` | Catálogo interno o beneficios del portal | Conservar variantes. |
| `#/documentos` | Base de conocimiento | Conservar. |
| `#/asistente` | Asistente | Conservar y añadir contexto de forma explícita cuando se implemente. |
| `#/ia`, `#/monitoreo` | Modelos y monitoreo | Una entrada común; ambos enlaces siguen resolviendo a su contenido permitido. |
| `#/operacion?seccion=...` | Datos/cierres, Actividad o Configuración | Conservar `cargar`, `ejecutar`, `actividad`, `administrar`. |

Persistir en URL los filtros relevantes, orden, página, serie y selección. Al abrir una ficha o caso y volver, restaurar la selección y la posición. Cambiar filtros reinicia la página; cambiar perfil elimina contexto que ya no esté autorizado. Evitar dos elementos activos en el menú para una misma pantalla.

## 3. Dirección visual y patrones compartidos

**Dirección:** sala de decisiones comercial. Superficies claras, verde de marca, gráficos limpios y énfasis tipográfico en una conclusión por pantalla. El rasgo reconocible será una franja de **Hallazgo → Evidencia → Acción**, que enlaza cada explicación con el trabajo correspondiente.

| Elemento | Especificación de diseño |
| --- | --- |
| Estructura | Navegación lateral de unos 224–240 px en escritorio; cabecera con área, contexto de datos, asistente y sesión. Menú plegable en anchos menores. |
| Área de trabajo | Ancho flexible, máximo orientativo de 1440 px para analítica; lectura/formularios de 720–880 px. Evitar tablas excesivamente anchas y enormes márgenes en pantallas grandes. |
| Jerarquía | Título 28–32 px; cifra principal 32–40 px; subtítulos 22–24 px; cuerpo y controles de 18 px como referencia; información secundaria desde 16 px. Usar unidades relativas, números tabulares y unidades explícitas. |
| Tipografía | Mantener inicialmente Segoe UI/system-ui para no depender de una descarga. Diferenciar por escala, peso y espaciado, no por muchas fuentes. |
| Paleta | Preservar verde `#1f6e43`, fondos claros de la aplicación y azul para observaciones. Usar un color diferenciado y trazo discontinuo para estimaciones. Revisar contraste de las combinaciones finales. |
| Estados | Verde para resultado favorable/confirmado; ámbar para atención; rojo para bloqueo/error; gris para desconocido. Texto e icono acompañan siempre al color. |
| Componentes | Borde sutil, radios coherentes 8–12 px, separación de 8/16/24/32 px. Tres o cuatro indicadores útiles por cabecera, no una pared de tarjetas. |
| Tema | Selector Claro/Oscuro/Sistema, persistente. Preparar la demo en Claro y comprobar ambas variantes; no dejar el contraste de proyección al tema del equipo. |
| Movimiento | Transiciones breves solo para orientar, sin animaciones que retrasen cifras ni conteos que simulen procesamiento. Respetar movimiento reducido. |
| Tablas | Encabezado claro, cifras alineadas a la derecha, filas compactas, acción principal legible, paginación estable. Detalle secundario desplegable; no truncar la evidencia imprescindible. |
| Formularios | Etiqueta asociada, ayuda breve, error junto al campo, foco en el primer error y estado de envío. Fechas/selecciones nativas permitidas con decisión documentada y prueba de idioma. |

### Contexto de datos: una regla obligatoria

Cada bloque debe distinguir cuatro tiempos cuando apliquen: **fecha de los datos**, **publicación/versión**, **horizonte estimado** y **actualización del trabajo humano**. Un cierre histórico y una tarea actual pueden convivir, pero deben estar rotulados por separado.

Para el paquete revisado: «Cartera al 30 sep 2026» y «Estimación con datos al 31 oct 2026» son contextos distintos. Soluciones admisibles:

1. Preparar una publicación de demo coherente y validada para el mismo corte mediante los procesos existentes.
2. Si se muestran diferentes publicaciones, conservar sus fechas visibles y explicar que no son directamente comparables. Desactivar comparaciones que requieran equivalencia temporal.

No reemplazar fechas ni datos ausentes en el frontend para producir una historia más atractiva. La demostración de ocho clientes y el paquete completo deben tener nombres distintos y su propio recorrido.

### Contrato de cada gráfico

Todo gráfico tendrá una pregunta, población, periodo, unidad, fuente, alternativa en tabla y comportamiento al seleccionar. El título expresa lo que se observa; no atribuye causas sin evidencia.

- Barras parten de cero y mantienen unidad comparable. Participaciones incluyen denominador.
- Los datos faltantes crean huecos o un estado explícito; nunca se transforman en cero.
- Histórico y predicción se distinguen por etiqueta, trazo y color. Banda solo si el contrato entrega límites válidos y el nivel que representan.
- Variación porcentual = `(actual − anterior) / anterior × 100` únicamente con base válida y periodos comparables; con base cero mostrar diferencia absoluta y «sin base porcentual».
- Ventas acumuladas, ingresos del mes y valor potencial no se mezclan. No inventar ahorro, ventas recuperadas, margen ni ROI.
- Los puntajes de recomendación o rareza no se convierten en porcentajes de éxito o fraude.
- La suma de etiquetas que se solapan no se presenta como distribución. Usar acción principal cuando se necesiten grupos excluyentes.
- Selección mediante teclado y un enlace equivalente accesible; una gráfica que filtra debe mostrar el filtro aplicado y permitir quitarlo.

### Componentes a consolidar antes de las vistas

Crear o extender en `app/ui.js` un encabezado de página, contexto de datos, indicador, franja de hallazgo, estado vacío/error, filtros con selección visible, tabla de datos, evidencia desplegable, gráfico temporal y rango temporal por cliente. Mantener `app/nucleo.js` como punto de permisos/formato/contexto y `app/estilos.css` como fuente de tokens.

Para esta escala de datos, extender los SVG actuales es una opción razonable. Evaluar una librería solo si faltan interacciones difíciles de mantener; no migrar toda la aplicación para conseguir tres gráficos. Durante la implementación, documentar decisiones y contratos compartidos en `DESIGN.md` y `UX-CONTRACT.md`, evitando duplicar las reglas de negocio del servidor.

## 4. Plan por vista

Prioridades: **P0** = recorrido principal de la demo; **P1** = completar reorganización y recorridos secundarios; **P2** = evolución posterior. Cuando una pantalla tenga dos prioridades, la primera corresponde a su núcleo y la segunda a una ampliación explícita.

### V01 · Acceso y origen de datos — P0

**Objetivo:** entrar con el perfil correcto y saber qué conjunto se está mostrando.

**Distribución:** marca y frase «Decisiones comerciales con evidencia»; bloque principal de acceso al cierre publicado con identidad; nombre, periodo y condición sintética del conjunto; alternativas «Agenda local» y «Ejemplo básico de ocho clientes» en segundo nivel; ayuda técnica desplegada solo a petición.

**Cambios:** conservar los tres modos y capacidades actuales, reducir su competencia visual y distinguir el ejemplo reducido del paquete completo. No introducir contraseñas o autenticación distinta como parte de este rediseño. El selector de identidades ficticias debe identificarse como una función de demo.

**Datos y acciones:** estado disponible de API y sesión; CTA «Entrar a [área del perfil]». Si la identidad no existe en la base, explicar cómo preparar la demo al operador, sin simular una sesión exitosa. No necesita un gráfico.

**Aceptación:** cada identidad entra al área autorizada; no hay sugerencias de clientes ajenos al conjunto; servidor inaccesible, cierre ausente y ejemplo limitado tienen mensajes distintos. Fuente: `app/app.js`, `app/nucleo.js`.

### V02 · Inicio ejecutivo / Gerencia — P0

**Objetivo:** comprender el resultado y elegir una intervención en menos de un minuto.

**Distribución:** periodo y alcance arriba; frase ejecutiva; tres indicadores —ventas del último mes completo, variación respecto al anterior y clientes que requieren revisión—; gráfico de ventas mensuales ocupando dos tercios; variación por familia en el tercio restante; tres focos de atención con enlaces; detalle verificable al final. Cada indicador conserva su fecha y población.

**Gráficos:** línea de 12 meses, opción de ampliar histórico; barras divergentes por diferencia absoluta entre familias, ordenadas por impacto. Al seleccionar familia, abrir Finanzas con los mismos meses. Si la desagregación no concilia, mostrarlo y no explicar toda la variación con datos parciales.

**Cambios:** bajar el acumulado a indicador secundario, resolver nombres de segmentos y quitar explicaciones técnicas del primer bloque. Conservar fuentes y estado sintético visible.

**Datos:** tablero de Gerencia y panel financiero existentes; cualquier contador transversal nuevo requiere agregado autorizado, no sumar respuestas incompletas.

**Aceptación:** cifras concilian con Finanzas; el usuario identifica qué cambió y abre la evidencia en dos interacciones. Fuente: `app/vistas/tableros.js`.

### V03 · Inicio comercial y Cartera — P0

**Objetivo:** saber a quién revisar y abrir el siguiente cliente.

**Distribución:** pestañas Resumen/Cartera dentro de un mismo espacio. Resumen contiene volumen por acción principal y hasta 20 oportunidades, indicando ese límite. Cartera abre con filtros, total seleccionado y tabla; el resumen global permanece compacto y claramente separado de la selección.

**Gráficos:** barras por acción principal, excluyentes; clic filtra. Segmentos como vista secundaria, con nombre de negocio solo si existe un diccionario autorizado; de lo contrario «Segmento 1» más descripción disponible, sin inventar perfiles.

**Tabla:** Cliente, acción, motivo breve, última compra, estimación M1 cuando exista y acceso a ficha. Ingreso histórico puede ser columna opcional si está permitido; no convertirlo en oportunidad económica. Diferenciar 0 %, sin historial, estimación ausente y modelo desactivado.

**Acciones/datos:** APIs actuales de resumen, agenda y tablero de ventas; búsqueda, filtros, paginación y exportación autorizada con alcance explícito. Retirar la duplicación del menú Tableros/Agenda sin perder URLs.

**Aceptación:** barras y tabla concilian; volver desde ficha restaura filtros; no se muestran porcentajes o clientes ficticios de otro conjunto. Fuente: `cartera.js`, `tableros.js`.

### V04 · Cliente 360 — P0

**Objetivo:** explicar la acción recomendada con suficiente evidencia para decidir.

**Distribución:** identidad del cliente y retorno a la lista; franja de acción principal con motivo; última compra, historial resumido y cobertura relevante; pestañas Resumen, Compras y coberturas, Señales predictivas, Seguimientos. El panel de acción queda próximo a la evidencia, no debajo de todas las tablas.

**Gráficos:** cronología con compra observada, vencimiento contractual y ventana estimada como tipos visuales distintos. Serie de compras solo con detalle suficiente; indicar si se muestran las últimas 30 operaciones. M1–M4 tienen bloques separados y corte propio; no un promedio de sus puntuaciones.

**Acciones:** abrir seguimiento existente o el mecanismo de creación permitido; consultar producto sugerido y su evidencia. Si no existe un endpoint de creación desde la ficha, enlazar el flujo actual y programar esa integración aparte. Las sugerencias en sombra no crean tareas automáticamente.

**Datos:** ficha del cierre y paneles existentes de M2–M4. No inventar nombre comercial si solo hay identificador.

**Aceptación:** se distingue hecho, estimación y decisión humana; falta de un modelo no bloquea las compras ni la cobertura. Fuente: `app/vistas/cartera.js`.

### V05 · Seguimientos / Mi trabajo — P0

**Objetivo:** convertir prioridades en trabajo visible y trazable.

**Distribución:** Mis seguimientos/Todos según permiso; filtros por estado, tipo y responsable si está disponible; lista ordenada con prioridad y fecha pertinente; avisos recientes en panel secundario. «Hoy» y «Vencidos» solo si hay fecha límite contractual del seguimiento; no derivarlos de la ventana predictiva.

**Gráfico:** barras de cantidad por estado actual y tipo, con población del filtro. No usar un embudo de conversión: atendido o descartado no demuestra una venta ni una transición comercial completa.

**Tabla:** cliente, motivo, estado, responsable cuando exista, próxima fecha registrada y acción. Reducir repetición de evidencias largas, disponibles en el detalle.

**Acciones/datos:** `GET /api/tareas`, métricas y avisos actuales; gestión solo con `tareas.gestionar`. Si faltan asignación o vencimiento, ponerlos en una ampliación de contrato P1.

**Aceptación:** todo conteo abre la selección correspondiente; una mutación refleja el estado confirmado por el servidor, sin duplicar solicitudes. Fuente: `app/vistas/seguimientos.js`.

### V06 · Detalle de seguimiento — P0

**Objetivo:** realizar una acción y dejar claro su resultado.

**Distribución:** título con cliente y estado; origen de la tarea y evidencia; acción disponible; historial de eventos. Mostrar por separado información del cierre y última actualización de la tarea.

**Visualización:** línea de tiempo de eventos reales —creación, cambios y resolución— con actor y fecha cuando se disponga. No agregar porcentajes de avance a estados que no los definen.

**Cambios:** una acción primaria según estado; acciones alternativas discretas; motivo obligatorio donde el contrato lo exige; conservar texto del usuario ante error. Confirmación contextual con el resultado, no un mensaje genérico.

**Datos:** `GET /api/tareas/:id` y acciones actuales de la tarea. Respetar conflictos y volver a consultar si el estado ya cambió.

**Aceptación:** perfiles de consulta no ven controles de gestión; doble clic no duplica eventos; al regresar se conserva el filtro y la fila actualizada. Fuente: `app/vistas/seguimientos.js`.

### V07 · Retención / Prevención de inactividad — P0

**Objetivo:** priorizar revisión preventiva sin confundirla con reactivación.

**Distribución:** título comercial y estado experimental compacto; cartera elegible, seleccionados para revisar y cobertura del cálculo; lista priorizada como contenido principal; evaluación del modelo detrás de «Cómo se obtuvo».

**Gráficos:** barras de las cohortes excluyentes que entrega el servicio y distribución del riesgo en población elegible; los clientes ya inactivos se presentan aparte. Si la API no entrega la distribución completa, usar solo las cohortes existentes, sin calcularla sobre el top-K.

**Tabla:** cliente, motivo, estimación y horizonte, días sin compra al corte, enlace a ficha/seguimiento. Permitir ajustar K con explicación de capacidad de revisión, no de umbral de verdad.

**Datos:** `GET /api/prevencion?k=...`. Conservar población, exclusiones, fechas y condición de sombra. Evitar afirmar «bien calibrado» a partir de una sola métrica como Brier.

**Aceptación:** la persona distingue prevenir futura inactividad de recuperar a quien ya lleva 90 días sin comprar; ningún recordatorio se activa por un cambio visual. Fuente: `app/vistas/prevencion.js`.

### V08 · Momento de contacto / Próxima compra — P0

**Objetivo:** decidir cuándo revisar un contacto, entendiendo la incertidumbre.

**Distribución:** corte y horizonte; número con ventana utilizable; filtros; gráfico de rangos para los primeros 10–15 clientes y tabla completa debajo; casos sin ventana en bloque explícito.

**Gráfico:** fila por cliente y eje de fechas. Dibujar los cuantiles disponibles y su significado exacto: un intervalo p10–p50 no es una banda del 80 %. Marcar aparte vencimiento contractual; permitir ordenar por inicio estimado. Si un límite no se alcanza dentro del horizonte, indicarlo sin fabricar una fecha.

**Acciones:** abrir ficha y seguimiento existente. Planificar un recordatorio desde esta señal será una capacidad posterior si no hay integración autorizada; no habilitar automatismos.

**Datos:** `GET /api/proxima?dias=...`; conservar probabilidades por horizonte cuando se entreguen. Presentar el corte propio del modelo, no heredar silenciosamente el del cierre global.

**Aceptación:** se distingue compra probable de vencimiento; el usuario identifica amplitud y límites de una ventana; la tabla ofrece los mismos valores del gráfico. Fuente: `app/vistas/proxima.js`.

### V09 · Productos sugeridos / Venta cruzada — P0

**Objetivo:** preparar una propuesta comercial explicable.

**Distribución:** selección de cliente a la izquierda; hasta tres recomendaciones en el área principal; producto, razón, antecedentes y compatibilidad; decisión y motivo al pie de cada propuesta. La revisión de muestras se separa en una pestaña de evaluación para quienes tengan permiso.

**Visualización:** tarjetas ordenadas por prioridad y comparación breve «Ya tiene / Se sugiere / Por qué». No añadir velocímetros ni «porcentaje de afinidad» a un puntaje no calibrado. Si se representa ranking, rotularlo como orden, no probabilidad.

**Acciones:** aceptar, aplazar o rechazar según el contrato existente. Una aceptación registra una decisión; no equivale a compra, cotización enviada ni mensaje al cliente. La compatibilidad pendiente debe poder bloquear una acción comercial si el flujo actual lo exige.

**Datos:** `/api/venta-cruzada`, decisiones y revisión existentes. Nombre del catálogo cuando esté disponible, identificador como respaldo.

**Aceptación:** cada propuesta muestra evidencia; estados de incompatibilidad y ausencia de candidatos tienen explicación útil; decisiones no se duplican y respetan capacidades. Fuente: `app/vistas/venta_cruzada.js`.

### V10 · Coberturas y renovaciones — P0

**Objetivo:** localizar los próximos vencimientos y las coberturas vencidas.

**Distribución:** fecha de referencia; indicadores de coberturas vencidas y próximas; bandas por plazo; lista ordenada por vencimiento; trabajo actual en un bloque distinto.

**Gráfico:** barras para vencidas y vencimientos a 0–15, 16–30 y 31–45 días, calculadas con la regla del cierre. El conteo es de coberturas, no de clientes; mostrar ambos solo cuando haya cálculo distinto y explícito. Seleccionar una barra abre su lista.

**Tabla:** cliente, producto, fecha contractual, días desde/hasta vencimiento al corte y enlace a ficha/seguimiento. No titular «vence hoy» usando la fecha del sistema cuando la pantalla está viendo un cierre histórico.

**Datos:** tablero de Operaciones y detalle disponible; si un agregado no ofrece listado, indicarlo hasta implementar consulta de detalle.

**Aceptación:** los intervalos no se solapan, la suma concilia y el orden pone primero la atención más próxima; tareas actuales no alteran métricas congeladas. Fuente: `app/vistas/tableros.js`.

### V11 · Operaciones atípicas / Cola — P1

**Objetivo:** revisar operaciones que se apartan de su referencia.

**Distribución:** universo ventas/compras y mes; estado experimental; pendientes y cobertura de puntuación; filtros; cola principal; estadísticas de evaluación en segundo nivel.

**Gráficos:** barras de casos por mes y estado, separadas de operaciones puntuadas. Solo usar agregados globales si la API los devuelve; no extrapolar una página de resultados. La prioridad se interpreta dentro de su universo/periodo, no como ranking absoluto comparable entre todas las monedas.

**Tabla:** operación, producto, señal principal, valor observado frente a referencia, soporte y revisión. Mantener accesibles operaciones sin historia suficiente, fuera del cupo y muestra de revisión.

**Acciones/datos:** abrir caso y exportar con alcance explícito; `GET /api/anomalias`. Ocultar importes cuando falte capacidad financiera. «Anomalía» nunca se convierte en «fraude» o «pérdida evitada».

**Aceptación:** usuario puede explicar por qué está la operación en la cola, con qué antecedentes y qué queda sin evaluar. Fuente: `app/vistas/anomalias.js`.

### V12 · Detalle de operación atípica — P1

**Objetivo:** resolver un caso con evidencia y trazabilidad.

**Distribución:** operación y estado; comparación observado/referencia; antecedentes comparables; formulario de revisión; historial. Abrir en detalle dedicado o panel amplio, sin obligar a recorrer nuevamente toda la cola.

**Gráfico:** puntos o barras comparativas por variable, con escalas independientes para precio y cantidad. Mostrar cantidad de antecedentes y referencia utilizada; no mezclar COP, USD y unidades en un solo eje. Si falta soporte, estado explícito de información insuficiente.

**Acciones:** registrar Error confirmado, Cambio legítimo o Información insuficiente con motivo, únicamente en perfiles autorizados. Corregir el registro sigue pasando por la carga de datos; revisar el caso no cambia el importe original.

**Datos:** `/api/anomalias/caso` y `/api/anomalias/revision`. No exigir cliente a una compra de proveedor si su contrato no lo incluye.

**Aceptación:** revisión persistida y visible al volver; la cola conserva filtros y posición; Gerencia consulta sin adquirir gestión. Fuente: `app/vistas/anomalias.js`.

### V13 · Finanzas / Resultado — P0

**Objetivo:** explicar la evolución de ventas y compras verificables.

**Distribución:** pestañas Resultado, Pronóstico, Escenarios TRM e Informes; selector de serie y periodo; tres indicadores; línea mensual principal; variación por familia; detalle transaccional o agregado de respaldo.

**Gráficos:** evolución mensual observada y barras de diferencias por familia. Mismo calendario y unidad que Gerencia. No superponer compras y ventas como «margen» si no existe el tratamiento contable que lo respalde.

**Cambios:** separar proyección operativa A08 del modelo M5 experimental. Si ambas permanecen, nombrar explícitamente su origen y estado; nunca escoger la cifra más atractiva para un mismo rótulo. Reducir párrafos repetidos y mover método a evidencia.

**Datos:** `/api/finanzas/:cierre/panel?serie=...`, cierre y permisos actuales. Una comparación a otro periodo debe conservar el mismo universo y reglas.

**Aceptación:** cada cifra concilia con el informe de la misma revisión; periodos incompletos no se comparan como meses completos. Fuente: `app/vistas/finanzas.js`.

### V14 · Pronóstico de demanda — P0

**Objetivo:** visualizar los próximos meses con límites suficientes para planificar.

**Distribución:** selector comprensible —Ventas totales, Ventas por familia o Unidades por producto—; origen del pronóstico; gráfico de histórico y horizontes; tres valores mensuales previstos; confianza/evidencia por horizonte; tabla de respaldo.

**Gráfico:** 12 meses observados en línea sólida; separación vertical en el último mes completo; tres puntos previstos con trazo discontinuo. Banda solo cuando existan límites válidos; un periodo incompleto/no observable queda diferenciado y no se rellena con cero. Se puede ampliar a todo el histórico disponible.

**Datos:** `GET /api/demanda?serie=...`; calendario, pronóstico, método, error histórico y muestra por serie/horizonte. Si los horizontes tienen métodos distintos, explicarlo en el detalle. No presentar MAE como porcentaje de confianza.

**Acciones:** cambiar serie, abrir datos y consultar explicación. Exportar o pasar a planificación de compras solo si se implementa su contrato; no convertir automáticamente pronóstico en orden.

**Aceptación:** todos los puntos concilian con la tabla; COP solo para perfiles autorizados; datos ausentes y pronóstico no disponible conservan la parte observada. Fuente: `app/vistas/demanda.js`.

### V15 · Escenarios TRM — P1

**Objetivo:** estimar el efecto de un tipo de cambio supuesto sobre compras registradas.

**Distribución:** explicación breve del supuesto; entrada de variación o valor permitidos por el servicio; resultado base, escenario y diferencia; gráfico comparativo; desglose y fórmula.

**Gráfico:** dos barras Base/Escenario en COP, con cantidades y precios en moneda de origen constantes. Solo añadir una curva de sensibilidad si el endpoint o cálculo autorizado permite múltiples escenarios consistentes. Mostrar alcance de compras en USD incluidas.

**Acciones/datos:** calcular/restablecer; `/api/finanzas/:cierre/simular`. Validaciones y límites del servidor prevalecen. La pantalla no pronostica la TRM ni asegura el coste futuro o el margen.

**Cambios:** sacar el simulador del desplazamiento largo de Resultado. Mostrar siempre qué supuesto cambió y qué datos quedaron fijos.

**Aceptación:** un escenario de variación cero coincide con la base; cambiar entradas invalida el resultado previo hasta recalcular; un fallo conserva el formulario. Fuente: `app/vistas/finanzas.js`.

### V16 · Informes ejecutivos — P1

**Objetivo:** llevar una versión consistente de los resultados a una reunión.

**Distribución:** último informe del cierre seleccionado, revisión y fecha; acción Abrir; generar nueva revisión únicamente para capacidades autorizadas; historial de versiones secundario.

**Contenido del informe:** resumen del periodo, evolución de ventas, familia que explica la mayor variación, focos operativos disponibles y notas de fuente. Proyecciones identificadas aparte con su propia publicación; si no corresponden al cierre, no incluirlas como parte del mismo resultado histórico.

**Visualización:** reutilizar los mismos gráficos/formatos de Gerencia y Finanzas con diseño imprimible, no una captura del menú. No añadir métricas inventadas de éxito comercial.

**Datos:** `GET /api/informes`, enlace por cierre/revisión y generación existente. La generación es una acción, no un efecto de entrar a la pestaña.

**Aceptación:** vista e informe concilian, URLs antiguas siguen abriendo y Finanzas no obtiene permiso de generar por acceder a la sección. Fuente: `app/vistas/finanzas.js` y generador actual de informes.

### V17 · Atención / Bandeja de solicitudes — P1

**Objetivo:** identificar solicitudes que necesitan clasificación, respuesta o revisión.

**Distribución:** colas por trabajo pendiente; indicadores breves; filtros; lista de casos; resumen de tiempos como bloque de supervisión. Separar la vista de indicadores de Gerencia de los controles de gestión de Atención.

**Gráficos:** barras por categoría y estado; tiempos medianos con periodo y población. Si no existe un plazo de servicio autorizado, no colorear casos como «SLA incumplido». La antigüedad sí puede mostrarse como duración observada.

**Tabla:** radicado, empresa autorizada, asunto, estado, categoría, última actualización y siguiente paso. Menos texto de políticas en la cola; evidencia completa en el caso.

**Datos:** `/api/pqrs`, `/api/pqrs-indicadores`, `/api/atencion/bandeja`. Una cuenta de casos debe aclarar si corresponde a filtro, cola o todo el periodo.

**Aceptación:** abrir caso y volver conserva selección; solo Atención ve gestión/exportación autorizada; no hay borradores presentados como respuestas publicadas. Fuente: `app/vistas/pqrs.js`.

### V18 · Atención / Resolver solicitud — P1

**Objetivo:** revisar y publicar una respuesta respaldada.

**Distribución:** cabecera con radicado y estado; columna de solicitud e historial; columna de clasificación, borrador y fuentes; pasos claros Clasificar → Preparar → Revisar y publicar. En pantallas estrechas, un flujo vertical conserva el borrador.

**Visualización:** cronología del caso y estado de cada paso; no necesita gráficos estadísticos. Las políticas citadas se abren junto a la respuesta para reducir saltos.

**Acciones:** confirmar/revisar clasificación, generar borrador, editar, previsualizar y aprobar siguiendo los endpoints actuales. El botón final dice qué se publicará y para quién. No fusionar generar con publicar.

**Estados:** fuente retirada o modificada, borrador que requiere revisión, conflicto, error de envío y sesión vencida. Preservar el trabajo permitido y evitar doble publicación.

**Aceptación:** la empresa solo ve la respuesta aprobada; fuentes y versión quedan identificadas; el flujo conserva todos los controles existentes. Fuente: `app/vistas/pqrs.js`.

### V19 · Portal / Inicio y beneficios — P1

**Objetivo:** que la empresa encuentre una ventaja disponible y sepa cómo solicitarla.

**Distribución:** saludo y empresa; beneficios vigentes con condiciones y vigencia; accesos a Mis solicitudes y Ayuda. Un resumen de solicitudes recientes es una ampliación opcional, no necesaria para presentar el catálogo.

**Visualización:** tarjetas de beneficios con etiqueta de categoría y acción; sin gráficas de riesgos ni métricas internas. Iconografía discreta por tipo; no bancos de imágenes decorativos que compitan con las condiciones.

**Datos:** `/api/portal/beneficios`; un resumen de casos usa únicamente la consulta ya restringida a la empresa. Las condiciones económicas se muestran textualmente según la política vigente, sin descuentos inventados.

**Acciones:** ver condiciones, consultar la sección citada, iniciar solicitud con referencia al beneficio. No asumir elegibilidad adicional ni aceptación automática.

**Aceptación:** Empresa A no obtiene contenido de B; beneficio vencido o retirado no parece disponible; falta de beneficios ofrece contacto/solicitud útil. Fuente: `app/vistas/beneficios.js`.

### V20 · Portal / Mis solicitudes y nueva solicitud — P1

**Objetivo:** consultar casos propios y crear uno sin fricción.

**Distribución:** listado con búsqueda, estado y fecha; acción «Nueva solicitud»; formulario separado y breve. Si viene desde un beneficio, mostrar la referencia y condiciones aplicables para evitar repetir información.

**Visualización:** estado como texto e indicador, no un gráfico de avance porcentual. La lista puede agruparse en abiertas/cerradas cuando esos estados estén definidos por el servicio.

**Formulario:** asunto, descripción y los campos ya admitidos; ayuda contextual; confirmación con radicado y enlace. No añadir adjuntos o canales inexistentes como si funcionaran.

**Datos:** `/api/pqrs` y creación actual, respetando su clave de idempotencia. Conservar texto ante fallo y distinguir «no se pudo confirmar» de «no se envió» cuando el resultado sea incierto.

**Aceptación:** doble clic no crea dos casos; búsqueda vacía explica cómo restablecer; el usuario ve claramente que la solicitud fue radicada. Fuente: `app/vistas/pqrs.js`.

### V21 · Portal / Detalle de solicitud — P1

**Objetivo:** entender estado y respuesta sin terminología interna.

**Distribución:** radicado y asunto; estado actual; solicitud original; respuesta publicada; cronología pública; acceso a beneficios o ayuda pertinente.

**Cambios:** destacar la respuesta más reciente y su fecha, conservando el historial público. Omitir propuestas de clasificación, borradores, puntajes y comentarios internos. No ofrecer responder o reabrir si el contrato no permite esas acciones.

**Visualización:** línea de tiempo con eventos autorizados, cada uno con texto. No mostrar una fecha estimada de solución sin compromiso de servicio definido.

**Datos:** consulta de caso actual bajo aislamiento de empresa. Un radicado inexistente o no autorizado debe dar una respuesta segura sin revelar datos de otra organización.

**Aceptación:** desde confirmación de nueva solicitud se llega a este detalle; se distingue recepción de resolución; ninguna respuesta no aprobada se filtra al portal. Fuente: `app/vistas/pqrs.js`.

### V22 · Catálogo interno de beneficios — P1

**Objetivo:** gestionar beneficios y sus versiones sin confundir edición con publicación.

**Distribución:** búsqueda y filtros por estado/vigencia; tabla o tarjetas compactas; detalle con condiciones, audiencia, fuente y versiones; formulario de borrador separado. Analítica de retención como pestaña secundaria.

**Visualización:** cronología de versiones. Solo mostrar gráficos de asignación/uso si los datos miden esos eventos; un catálogo publicado no demuestra uso, retención o ingresos.

**Acciones:** crear/editar con `beneficios.editar`; publicar con `beneficios.publicar`; consultar según capacidad. La vista previa del portal debe reflejar la versión concreta que se va a publicar.

**Datos:** `/api/beneficios` y `/api/beneficios-retencion`; fechas y restricciones existentes. No cambiar políticas comerciales como parte del diseño.

**Aceptación:** Ventas puede trabajar dentro de su permiso sin publicar; vencimiento y versión están claros; una actualización no elimina la trazabilidad de respuestas anteriores. Fuente: `app/vistas/beneficios.js`.

### V23 · Base de conocimiento / Documentos — P1

**Objetivo:** encontrar y mantener las políticas que respaldan respuestas.

**Distribución:** biblioteca de documentos por título, estado, vigencia y versión; detalle con contenido, fuentes y versiones; importación/actualización en su propio formulario; prueba de consultas como herramienta secundaria.

**Visualización:** historial de versiones; no hace falta una gráfica de documentos por categoría para completar la tarea. Priorizar búsqueda, estado y localización del fragmento citado.

**Acciones:** consultar para perfiles permitidos; importar y retirar solo con `documentos.gestionar`. Antes de retirar, mostrar la consecuencia real ya definida: respuestas/borradores que deban revisarse, sin inventar un conteo si no existe agregado.

**Datos:** `/api/documentos`, consulta y acciones actuales. Si se propone una lista de dependencias documentales, hace falta soporte de API y permisos; fase P2.

**Aceptación:** fuente retirada no aparece como vigente; citas abren el fragmento correcto; validación de formulario conserva texto y señala campos. Fuente: `app/vistas/documentos.js`.

### V24 · Asistente — P0 en acceso y ejemplos; P2 en panel contextual

**Objetivo:** explicar una cifra o un caso con referencias que el usuario pueda verificar.

**Distribución:** entrada accesible desde cabecera; página completa con preguntas iniciales adaptadas al perfil; conversación; fuentes junto a cada respuesta; información de modo básico/agente legible, sin detalles de proveedor como contenido principal.

**Cambios P0:** reemplazar sugerencias fijas como «¿Qué compró DEMO01?» por cliente existente o una pregunta sin identificador. Priorizar «¿Qué cambió?» y «¿A quién debo revisar?» sobre detalles del proyecto. Conservar advertencias sobre cifras no respaldadas.

**Ampliación P2:** «Explicar este dato» abre panel con entidad, corte, filtros y pregunta explícitos. Requiere contrato de contexto y la misma autorización en servidor; no enviar todo el contenido de la pantalla indiscriminadamente.

**Visualización:** respuestas breves y tablas/gráficos solo a partir de datos soportados; citas navegables. La conversación no sustituye la evidencia de la vista.

**Aceptación:** preguntas de ejemplo funcionan en el conjunto activo; modo básico se presenta honestamente; cita y retorno funcionan; error o latencia no bloquean la navegación. Fuente: `app/vistas/asistente.js`.

### V25 · Modelos y monitoreo / Resumen — P1

**Objetivo:** conocer disponibilidad, madurez y necesidad de revisión de las capacidades analíticas.

**Distribución:** matriz de capacidades autorizadas: Compra, Inactividad, Próxima compra, Venta cruzada, Demanda y Operaciones atípicas; columnas Disponibilidad, Corte, Estado de validación y Avisos; detalle seleccionable.

**Cambios:** una entrada sustituye la competencia entre Modelos de IA y Monitoreo. Mantener explicación comercial de cada modelo y acceso al recorrido de negocio. Diferenciar modelo no publicado, desactivado, experimental, inconcluso, sin evaluación y con aviso.

**Gráficos:** cobertura de datos y estado de avisos; métricas predictivas solo en el detalle del modelo adecuado. No promediar AUC, MAE, precisión o rareza para producir una «salud IA 95 %».

**Datos:** `/api/ia` y `/api/monitoreo`. Es necesario unificar metadatos sin ampliar los permisos; para Ventas se mantiene la explicación autorizada de modelos comerciales sin exponer monitoreo restringido.

**Aceptación:** la matriz refleja el inventario real autorizado y sus estados; datos sintéticos no aparecen como validación empresarial; ausencia de evaluación no es verde. Fuentes: `ia.js`, `monitoreo.js`, `api/permisos.py`.

### V26 · Modelo / Evaluación y aviso — P1

**Objetivo:** entender una limitación o aviso y registrar su revisión cuando proceda.

**Distribución:** propósito y publicación; pestañas Datos, Evaluación, Distribución y Avisos; línea temporal de publicaciones; detalle de aviso con evidencia, alcance y acciones disponibles.

**Gráficos:** comparación con referencia dentro de la misma métrica, población y horizonte; distribución o evolución solo con datos del contrato. Mostrar tamaño de muestra, intervalo si existe y exclusiones. No comparar porcentajes de distintos objetivos como si midieran lo mismo.

**Acciones:** abrir evidencia y recorrido afectado; reconocer o revisar aviso solo con capacidad autorizada y motivo. Reconocer no borra el problema ni reentrena el modelo.

**Datos:** consultas de monitoreo y detalle de aviso actuales; evaluar cada familia de métricas con su propio componente. Versiones M1.1–M1.3 pueden estar en detalle, sin multiplicar el menú de negocio.

**Aceptación:** un aviso reconocido conserva historia; ninguna métrica sin población o periodo se muestra como mejora concluyente; el rol no accede a detalles restringidos. Fuente: `app/vistas/monitoreo.js`.

### V27 · Inicio de Operaciones — P1

**Objetivo:** elegir entre actuar sobre coberturas y preparar información nueva.

**Distribución:** dos caminos claros: «Revisar coberturas» y «Preparar cierre»; contexto del cierre publicado; pendientes reales de carga/publicación; accesos secundarios a informes y monitoreo.

**Cambios:** evitar que la bienvenida repita todos los módulos. La señal principal conduce a un trabajo específico: lote pendiente de confirmar, cierre fallido o coberturas próximas, según disponibilidad y permiso.

**Visualización:** estado de datos/publicación y un resumen compacto de coberturas. No mezclar una carga pendiente con una renovación pendiente en un contador único.

**Datos:** información existente de operación y tablero; si agregarlos causa cargas pesadas, devolver un resumen pequeño desde API en P1.

**Aceptación:** cada aviso abre su sección; fallo de una consulta no oculta el camino alternativo; siempre se identifica qué versión ven los usuarios. Fuentes: `app/app.js`, `app/vistas/operacion.js`.

### V28 · Datos y cierres / Cargar y validar — P1

**Objetivo:** entender qué información entrará al siguiente cierre.

**Distribución:** pasos Cargar → Revisar calidad → Confirmar lote; campos de periodo, tipo y archivo; previsualización; mapeo cuando haga falta; incidencias con corrección concreta; resumen antes de confirmar.

**Gráfico:** barra apilada de filas aceptadas, duplicadas y aisladas con total leído. Conciliación explícita; una discrepancia bloquea una lectura tranquilizadora. El gráfico acompaña la tabla de errores, no la reemplaza.

**Acciones:** validar, corregir mapeo/revalidar y confirmar según contratos actuales. Confirmar lote no se presenta como publicar el cierre. Mantener la ruta avanzada a hoja y columnas cuando sea necesaria.

**Datos:** `/api/cargas` y confirmación; configuración de tablas desde `/api/operacion`.

**Aceptación:** archivos fallidos preservan opciones, confirmación repetida respeta idempotencia y el usuario puede decir qué filas se excluyeron y qué ven todavía los demás. Fuente: `app/vistas/operacion.js`.

### V29 · Datos y cierres / Ejecutar y publicar — P1

**Objetivo:** publicar una versión verificable sin confundir etapas.

**Distribución:** cierre actual a la izquierda; preparación de nuevo cierre con corte e insumos; estado de ejecución; resultado publicado con revisión y fecha. La publicación de una salida existente permanece como opción avanzada distinta.

**Visualización:** etapas reales del proceso con estado, inicio/fin y errores. No dibujar porcentaje de progreso si el servicio solo conoce etapas. Diferenciar en curso, fallido, publicado y resultado incierto.

**Acciones:** ejecutar/publicar con los contratos actuales; no alterar si el backend realiza ambas etapas de forma conjunta. Explicar antes de la acción qué datos quedarán visibles y que un fallo conserva el cierre anterior cuando así lo garantice el servicio.

**Datos:** `/api/cierres`, ejecución, publicación y `/api/estado` existentes.

**Aceptación:** no hay doble ejecución por clic repetido; el éxito incluye identificación del cierre realmente publicado; no se muestra un resultado viejo como si fuera nuevo. Fuente: `app/vistas/operacion.js`.

### V30 · Actividad y trazabilidad — P1

**Objetivo:** reconstruir cargas, ejecuciones y cambios de manera comprensible.

**Distribución:** filtros por tipo, periodo y resultado; lista cronológica; detalle de un evento y enlace a lote/cierre cuando exista. Diferenciar bitácora de datos y seguimiento comercial.

**Visualización:** línea de tiempo; barras de éxito/fallo únicamente si la API entrega población completa y periodo. No es prioritario añadir gráficos a una bitácora de pocos eventos.

**Datos:** actividad ya disponible en la sección operativa. El permiso `auditoria` no implica automáticamente acceso a todo `/api/operacion`: si Gerencia requiere una vista independiente, implementar un contrato de lectura que devuelva solo los eventos autorizados.

**Acciones:** abrir evidencia y, si existe capacidad, descargarla. No añadir botones para borrar historial.

**Aceptación:** se identifica actor, momento y resultado cuando estén disponibles; datos ausentes no se rellenan; los enlaces a revisiones históricas se mantienen. Fuente: `app/vistas/operacion.js`, `api/permisos.py`.

### V31 · Configuración y respaldos — P1

**Objetivo:** administrar capacidades y respaldos con consecuencias claras.

**Distribución:** configuración por dominio, estado actual y explicación; sección separada de respaldos; resultado de cada acción. Mantener esta vista fuera del recorrido comercial normal.

**Cambios:** los interruptores existentes deben explicar el efecto exacto —por ejemplo, mostrar la estimación de compra— sin prometer que habilitan todos los modelos. Separar acciones de guardar/cambiar de crear respaldo, con estados propios.

**Visualización:** listado de estado y última operación conocida; no requiere gráfico. Si el backend no ofrece historial de respaldos, mostrar únicamente el resultado que sí entrega.

**Datos:** acciones actuales de banderas y respaldo. No exponer secretos, añadir permisos ni cambiar retención de datos como consecuencia del rediseño.

**Aceptación:** fallo al cambiar una bandera restablece el estado confirmado; solo perfiles autorizados ejecutan; un respaldo se declara creado únicamente con respuesta exitosa. Fuente: `app/vistas/operacion.js`.

## 5. Esquemas de distribución

Son wireframes de jerarquía; no representan una implementación ni cifras reales. En escritorio, la navegación lateral permanece fuera de estos bloques.

### Inicio ejecutivo

```text
Inicio ejecutivo                 [Periodo] [Contexto] [Asistente]
Una frase explica el resultado del mes y su comparación

[Ventas del mes]        [Variación mensual]       [Clientes a revisar]
 periodo + unidad        base de comparación        población + corte

┌──────────────────────────────────┬─────────────────────────────┐
│ Evolución mensual                │ ¿Dónde cambió el resultado? │
│ Línea observada                  │ Diferencia por familia      │
│ Periodo seleccionable            │ Barras + enlace a Finanzas  │
└──────────────────────────────────┴─────────────────────────────┘

Dónde actuar ahora
Hallazgo                    Evidencia                  Acción
Coberturas próximas         cantidad + periodo         Ver coberturas
Clientes para revisar       razón + fecha              Abrir cartera
Casos pendientes            alcance autorizado         Ver solicitudes

[Ver datos, filtros y cálculo]
```

### Cliente 360

```text
← Volver a la cartera filtrada                  Cliente + identificador
Acción principal · motivo verificable            [Abrir seguimiento]

[Última compra]          [Cobertura relevante]       [Estado de gestión]
     cierre                    cierre                    actual

[Resumen] [Compras y coberturas] [Señales predictivas] [Seguimientos]
┌──────────────────────────────────┬─────────────────────────────┐
│ Cronología                       │ Recomendación seleccionada  │
│ ● Compra observada               │ Qué sugiere y por qué       │
│ ◇ Vencimiento contractual        │ Fecha de los datos          │
│ ├──┤ Ventana estimada             │ Límites / evidencia         │
└──────────────────────────────────┴─────────────────────────────┘

Detalle del cliente / producto / operaciones según la pestaña
```

### Pronóstico

```text
Pronóstico de demanda              [Serie legible] [Ver datos]
Datos hasta ... · estimación experimental para ... · unidad ...

┌────────────────────────────────────────────────────────────────┐
│ Observado: línea sólida      │ Estimado: puntos y línea discontinua│
│                              │ Banda solo cuando esté disponible │
└────────────────────────────────────────────────────────────────┘
[Mes +1: estimación]       [Mes +2: estimación]       [Mes +3: estimación]

Qué permite decidir · qué limitación afecta esta serie
[Tabla completa] [Error histórico y muestra por horizonte]
```

En móvil: título/contexto, conclusión, acción, indicadores, gráfico, detalle. La navegación se pliega; listas de trabajo priorizan cliente/caso, motivo y acción. Las tablas numéricas pueden tener desplazamiento horizontal dentro de su región identificada, sin desplazar toda la página. No ocultar evidencia crítica detrás de hover.

## 6. Datos, contratos y trabajo de backend

### Lo que puede aprovecharse directamente

| Capacidad | Fuente actual | Trabajo de interfaz |
| --- | --- | --- |
| Resumen, agenda y ficha | `/api/cierres/:cierre/resumen`, `/agenda`, `/clientes/:id` | Nueva jerarquía, filtros persistentes y ficha por pestañas. |
| Tableros por perfil | `/api/cierres/:cierre/tableros/:rol` | Gráficos y enlaces con alcance/corte visibles. |
| Seguimiento | `/api/tareas`, métricas y detalle | Lista de trabajo, historial y controles por estado. |
| M2 | `/api/prevencion` | Prioridad comercial y evaluación progresiva. |
| M3 | `/api/proxima` | Rangos temporales usando los cuantiles disponibles. |
| M4 | `/api/venta-cruzada` | Selección de cliente y propuestas con razones. |
| M5 | `/api/demanda` | Histórico/estimación, bandas válidas y datos de evaluación. |
| M6 | `/api/anomalias` y detalle | Cola y comparación con referencia. |
| Finanzas | `/api/finanzas/:cierre/panel`, `/simular`, `/api/informes` | Subpestañas, comparación y salida imprimible coherente. |
| Atención y portal | PQRS, beneficios y documentos actuales | Separación de colas, edición, respuesta y consulta externa. |
| Estado de modelos | `/api/ia`, `/api/monitoreo` | Acceso unificado con contenido según permiso. |
| Datos y cierres | Operación, cargas, cierres y estado | Flujo por etapas y mensajes de resultado. |

La disponibilidad de un endpoint no prueba que todos sus agregados estén completos o paginados. Antes de construir cada gráfico, fijar una muestra de respuesta y verificar los campos, población, permisos y límites de consulta.

### Ampliaciones que requieren contrato explícito

| Necesidad propuesta | Dependencia | Solución inicial sin inventar datos |
| --- | --- | --- |
| Resumen ejecutivo transversal | Agregados autorizados de varias áreas con contexto temporal. | Usar los indicadores existentes y enlaces a vistas, sin nuevo «total global». |
| Nombres de segmentos/productos | Diccionario de etiquetas o catálogo disponible. | Etiqueta neutra «Segmento 1» o identificador acompañado de descripción existente. |
| Una fecha común de demo | Publicaciones de cierre y modelos coherentes y verificadas. | Mostrar fechas distintas y no combinar sus métricas. |
| Crear seguimiento desde una recomendación | Contrato de origen, idempotencia, permisos y vínculo. | Abrir ficha o seguimiento existente; no fabricar un botón funcional. |
| Asignación y vencimiento de tareas | Campos y reglas de gestión si no existen. | Mantener estado/tipo y datos realmente entregados. |
| Distribuciones completas de riesgo/casos | Agregados del universo filtrado, no solo top-K/página. | Mostrar conteos disponibles y listas; posponer gráfico. |
| Centro completo M1–M6 | Metadatos comunes autorizados de estado, corte, versión y validación. | Componer respuestas existentes sin revelar campos de otro permiso. |
| Asistente contextual | Contexto estructurado y validado en servidor. | Preguntas sugeridas de la página completa, ajustadas al conjunto. |
| Filtro de exportación de anomalías u otras tablas | Verificar alcance real de cada endpoint. | Rotular lo que descarga. La exportación de cartera ya tiene soporte de filtros. |
| Auditoría independiente para Gerencia | Lectura limitada a eventos autorizados. | Mantener el acceso actual sin abrir toda la administración. |

**Orden de dependencia:** contrato del contexto → componentes compartidos → gráfico o tabla → enlace de navegación → acción → prueba. No diseñar acciones que solo cambien un estado local sin persistencia.

## 7. Secuencia de implementación

Estimaciones orientativas para una persona familiarizada con el proyecto, incluyendo revisión visual y ajustes; no son un compromiso de calendario. Se refinan al comprobar respuestas reales y alcance de contratos. El camino completo puede requerir aproximadamente **12–18 jornadas**, y la primera demo centrada en el recorrido principal **5–7 jornadas** si no aparecen cambios mayores de backend.

| Paquete | Entrega concreta | Vistas | Dependencias | Esfuerzo orientativo |
| --- | --- | --- | --- | --- |
| A · Preparar una demo coherente | Identificar base, corte, publicaciones, identidades, ejemplos válidos y estado de cada modelo. Matriz de permisos y datos de referencia. | Todas | Ninguna; primera tarea. | 0,5–1 jornada |
| B · Navegación y sistema visual | Shell lateral, contexto, tipografía, tema, estados y componentes comunes. Compatibilidad de URLs. | Todas | A | 1–2 jornadas |
| C · Historia comercial | Inicio ejecutivo, Cartera, Cliente 360 y seguimiento list/detail conectados. | V02–V06 | A–B | 2–3 jornadas |
| D · Señales y pronóstico | Gráfico de M5; rangos M3; jerarquía M2; propuestas M4; títulos y contexto del asistente. | V07–V09, V14, V24 | A–B; C para enlaces | 2–3 jornadas |
| E · Finanzas y control operativo | Resultado, escenarios, informes, coberturas, anomalías y detalle. | V10–V16 | B–D | 1,5–2,5 jornadas |
| F · Servicio al cliente | Bandeja, resolver caso, portal, beneficios y conocimiento. | V17–V23 | B; permisos existentes | 2–3 jornadas |
| G · Confianza y administración | Modelos/monitoreo, avisos, datos/cierres, actividad y configuración. | V25–V31 | B; metadatos/permisos | 1,5–2 jornadas |
| H · Ensayo y correcciones | Recorrido por perfil, cifras, accesibilidad, responsive, errores y exportaciones. | Todas las modificadas | Paquetes que entren en la entrega | 1–1,5 jornadas |

Hay trabajo compartido entre paquetes; los extremos de cada rango no deben sumarse como una fecha cerrada. Los cambios de backend opcionales y la validación predictiva con datos empresariales reales quedan fuera de esta estimación.

### Alcance mínimo para presentar primero

1. Asegurar fechas, población y versiones; elegir ejemplos existentes y aptos para el recorrido.
2. Aplicar shell, nombres y componentes comunes sin reconstruir todas las pantallas.
3. Mejorar Gerencia, Cartera, Cliente 360 y Seguimientos.
4. Añadir el gráfico de M5 y un recorrido breve por M3/M4 usando el detalle actual cuando haga falta.
5. Ajustar acceso, sugerencias del asistente y mensajes de disponibilidad.
6. Ensayar en la resolución del equipo de presentación y preparar una copia reiniciable de la demo.

No es necesario completar un panel contextual del asistente, un calendario avanzado, kanban, nuevas métricas financieras ni reentrenar modelos para esta entrega. Su ausencia debe reflejarse en el alcance, no en botones simulados.

### Lista técnica por orden de trabajo

- Registrar decisiones visuales y comportamiento de componentes compartidos, incluidos controles nativos y validación.
- Refactorizar navegación en `app/app.js`; centralizar selección activa y capacidades en `app/nucleo.js`.
- Añadir tokens y layouts en `app/estilos.css`, manteniendo las vistas actuales funcionales durante la migración.
- Extender `app/ui.js` con encabezados, contexto, gráfico observado/estimado y rangos temporales accesibles.
- Migrar una pantalla de lista, una de detalle y una analítica; revisarlas antes de replicar el patrón.
- Introducir secciones en URL y restauración de filtros con compatibilidad de enlaces anteriores.
- Aplicar las vistas P0; después migrar los módulos P1 reutilizando los mismos componentes.
- Añadir adaptadores de presentación para etiquetas y metadatos; conservar los campos y reglas originales del servicio.
- Resolver señales estáticas confirmadas; documentar excepciones y falsos positivos con evidencia específica.
- Ejecutar las comprobaciones de la siguiente sección y guardar capturas de las vistas implementadas.

## 8. Criterios para considerar lista la demo

### Exactitud y confianza

- Todos los gráficos concilian con su tabla y con la respuesta correspondiente; periodo, población y unidad visibles.
- Datos de prueba identificados al entrar y durante el recorrido; ninguna cifra se promociona como resultado logrado por un cliente real.
- Estado experimental o inconcluso conservado junto a cada estimación pertinente.
- Diferenciación entre cero, dato ausente, sin historial, sin permisos y servicio no disponible.
- M1, M2, M3 y M4 no se combinan en una puntuación única; M5 no se confunde con ingreso realizado; M6 no se presenta como fraude confirmado.
- Misma definición y revisión para cifras repetidas entre Gerencia, Finanzas e informe; si difieren, una explicación explícita.

### Recorrido y funcionalidad

- Desde Inicio ejecutivo se llega a una selección, ficha y evidencia sin perder corte/filtros.
- Ventas completa una acción permitida y la ve persistida al regresar; Gerencia conserva lectura donde corresponde.
- Entrar directamente por una URL antigua funciona; Atrás/Adelante restauran un contexto válido.
- Los botones visibles realizan una acción real, abren un destino verificable o explican por qué están deshabilitados.
- Exportaciones nombran su alcance y respetan filtros cuando el contrato lo soporte.
- Casos en sombra no crean tareas, mensajes o movimientos comerciales automáticamente.
- Portal Empresa A/B conserva aislamiento; enlaces y consultas del asistente respetan las mismas capacidades.

### Diseño y accesibilidad

- Revisar las pantallas P0 a 1366×768 y 1440×900, más una pantalla ancha; probar 1024 px y 390 px para navegación, listas y formularios.
- Comprobar zoom al 200 %, teclado, foco visible y restauración de foco al cerrar paneles; acciones no ocultas bajo cabeceras o teclados.
- El primer bloque permite entender título, periodo, conclusión y siguiente acción sin recorrer una explicación técnica larga.
- Gráficos cuentan con tabla y selección equivalente por teclado; ninguna leyenda depende solo del color o hover.
- Formularios muestran errores asociados al campo, conservan valores y bloquean envío duplicado mientras se confirma.
- Carga, actualización, vacío, filtros sin resultados, error y sesión vencida tienen estados distintos y una salida útil.
- Revisar tema claro y oscuro con números, estados y series legibles; el tema de la demo queda fijado antes de presentar.

### Pruebas que aportan valor

| Prueba | Casos esenciales | Evidencia de aprobación |
| --- | --- | --- |
| Integración de contexto | Cambiar cierre/serie, abrir ficha, volver; dos publicaciones con fechas diferentes. | Ninguna fecha heredada errónea; selección restaurada. |
| Contrato de gráficos | Nulos, base cero, periodos incompletos, banda ausente, cuantiles parciales. | Tabla y gráfico concilian; no aparecen puntos o intervalos inventados. |
| Capacidades | Ventas, Gerencia, Finanzas, Operaciones, Atención, Empresa A/B. | Menú, acciones y respuestas del servidor coherentes; aislamiento preservado. |
| Trabajo persistente | Seguimiento, decisión comercial, revisión de anomalía y respuesta PQRS en copia de prueba. | Estado real después de recargar; doble envío y error no duplican eventos. |
| Enlaces y filtros | Acceso directo a rutas existentes y nuevas secciones; retroceso. | Sin callejones ni pérdida de selección. |
| Visual manual | Capturas de P0 y variantes representativas P1 en resoluciones objetivo. | Jerarquía y controles legibles, sin recortes ni desbordamiento global. |
| Comprensión | Una persona de gerencia y una operativa realizan tareas sin guía. | Identifican periodo, interpretación y siguiente paso; registrar errores de comprensión. |

No escribir pruebas que solo repliquen el HTML. Aprovechar la suite existente y añadir cobertura donde cambien navegación, transformaciones de datos, contexto o acciones. La comprobación estática complementa estas pruebas; no sustituye la inspección visual ni una prueba de permisos en servidor.

## 9. Guion comercial para audiencia mixta

Duración objetivo: 8–10 minutos. Mostrar la ruta principal con Gerencia y pasar a Ventas únicamente cuando se necesite registrar trabajo; no crear un perfil con privilegios ampliados para facilitar la presentación. El recorrido de Atención puede demostrarse aparte si hay tiempo.

| Tiempo | Pantalla y gesto | Mensaje de valor | Evidencia que debe verse |
| --- | --- | --- | --- |
| 0:00–0:45 | Acceso e Inicio ejecutivo | «Partimos de información concreta y sabemos hasta qué fecha llega». | Conjunto de práctica, periodo y tres cifras comprensibles. |
| 0:45–2:00 | Evolución y variación por familia | «Podemos localizar dónde cambió el resultado». | Comparación entre periodos, unidad y familia seleccionada. No atribuir causalidad no probada. |
| 2:00–3:30 | Cartera filtrada → Cliente 360 | «Pasamos del resumen a quién necesita atención y por qué». | Motivo verificable, compra, cobertura y contexto del cliente. |
| 3:30–5:00 | Momento de contacto / Productos sugeridos | «Las estimaciones ayudan a preparar la siguiente conversación». | Ventana con incertidumbre y propuesta con compatibilidad/evidencia; estado experimental. |
| 5:00–6:30 | Seguimiento con perfil Ventas | «La decisión humana queda registrada y puede seguirse». | Acción permitida, resultado confirmado e historial. Si se prefiere lectura, mostrar un caso ya preparado y rotulado. |
| 6:30–8:00 | Pronóstico de demanda | «Vemos los próximos meses y también qué tan limitada es la evidencia». | Histórico, estimación separada, horizonte y banda/error cuando existan. |
| 8:00–9:00 | Asistente o Modelos y monitoreo | «La explicación tiene fuente y conocemos los límites del sistema». | Cita verificable o estado de publicación/evaluación. |
| Opcional | Solicitud → respuesta revisada → Portal | «La misma evidencia mejora la atención al cliente». | Flujo humano de aprobación y visibilidad exclusiva de la empresa. |

### Preparación del presentador

- Usar una copia de demo controlada y con procedimiento de restauración conocido; no experimentar con la base de trabajo durante la reunión.
- Registrar conjunto activo, versión, corte del cierre y cortes de modelos. Para esta revisión se observaron 120 clientes en la copia completa; los demás conteos deben obtenerse del paquete final, no fijarse en el frontend.
- Elegir previamente un cliente con señal explicable, otro sin estimación y un seguimiento apto para mostrar. Tomarlos de las respuestas actuales; no fijar `DEMO01` por costumbre.
- Verificar cuenta y permisos de cada paso, tema, resolución, fuente de datos y tiempo de respuesta. El guion debe funcionar aunque no se active el proveedor de lenguaje.
- Si se dispone solo de modo básico del asistente, usar preguntas compatibles con ese modo y nombrarlo correctamente.
- Preparar capturas o un informe de respaldo con fecha y revisión identificadas. Si se usan, decir que son resultados guardados; no aparentar interacción en vivo.

### Qué prometer y qué medir después

Se puede demostrar priorización explicable, trazabilidad, conexión de vistas y acceso a proyecciones. La efectividad comercial requiere un piloto: adopción de sugerencias, tiempo de revisión, acciones completadas y resultados posteriores con definición de población y comparación. No presentar «más ventas», «menos fuga» o «ahorro» como beneficios ya medidos con este conjunto sintético.

Metas de diseño a validar, no resultados obtenidos: Gerencia entiende el cambio principal en unos 30 segundos; Ventas encuentra un cliente y su motivo sin ayuda; el equipo registra un seguimiento sin repetir datos; una persona distingue un dato observado de una estimación y encuentra la fuente.

## 10. Decisiones finales de alcance

**Agregar:** navegación por áreas, contexto por bloque, franja Hallazgo/Evidencia/Acción, ficha por pestañas, gráfico de demanda, rangos de próxima compra, centro común de modelos, estados y filtros consistentes.

**Reorganizar:** Tableros/Agenda en espacio comercial; Finanzas en cuatro secciones; Atención en cola y resolución; Operación en preparación de datos, publicación, actividad y configuración.

**Retirar de primer nivel:** enlaces repetidos de modelos, identificadores técnicos como títulos, explicaciones metodológicas extensas antes de la tarea y ejemplos que no pertenecen al conjunto activo. Conservar su detalle cuando sea útil para verificar.

**Posponer:** nuevo calendario avanzado, kanban, métricas de ROI, automatización de contactos, asistente contextual completo y migración de framework. No son necesarios para una primera demo convincente y verificable.

El criterio de cierre será un recorrido coherente que permita **entender → investigar → decidir → registrar → verificar**, con las cifras y permisos reales de la aplicación.

