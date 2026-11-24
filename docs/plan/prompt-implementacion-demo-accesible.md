# Prompt de implementación · JACOMIND accesible y listo para demo

Este prompt complementa `docs/plan/reorganizacion-demo.md`. Incorpora el requisito del usuario de diseñar para personas con muy poca experiencia tecnológica, incluidos adultos mayores. Las reglas de lectura, controles y densidad de este prompt prevalecen sobre medidas más compactas del plan anterior.

---

Actúa como responsable de producto, diseñador UI/UX experto en accesibilidad y desarrollador senior de aplicaciones de negocio. Implementa la reorganización de JACOMIND en el proyecto actual.

Tu objetivo es entregar una aplicación profesional, estética y fácil de entender para gerencia y equipos de trabajo con muy poca experiencia digital, incluidos adultos mayores. Deben poder orientarse, comprender los datos y completar tareas con autonomía.

Trabaja en la aplicación real. Conserva sus reglas de negocio, datos, permisos, trazabilidad y capacidades. Completa los cambios y su verificación; no te detengas en un nuevo plan, una maqueta o un cambio superficial de colores.

## 1. Contexto y alcance

Lee primero:

- `docs/plan/reorganizacion-demo.md`, completo: contiene las 31 vistas V01–V31, sus prioridades, datos y criterios.
- `README.md`, instrucciones aplicables del repositorio y contratos relevantes.
- `app/app.js`, `app/nucleo.js`, `app/ui.js`, `app/estilos.css`, `app/index.html` y módulos de `app/vistas/`.
- `api/permisos.py` y los contratos/servicios que consumen las vistas modificadas.
- `DESIGN.md` y `UX-CONTRACT.md` si existen; utiliza las habilidades de diseño disponibles conforme a sus instrucciones.

Inspecciona el estado actual antes de modificar: pueden existir cambios posteriores al plan. Conserva el trabajo ajeno y las mejoras ya implementadas. No restaures archivos completos para simplificar la tarea.

Implementa las entregas P0 y P1 del plan por etapas verificables. Las ampliaciones explícitamente P2 quedan fuera, salvo que sean imprescindibles para que una función incluida opere correctamente. Priorizar P0 ordena el trabajo; no autoriza a omitir P1 silenciosamente.

Mantén el stack actual salvo necesidad demostrable. No migres de framework ni cambies modelos predictivos, entrenamiento, fórmulas o reglas comerciales por motivos visuales. Cambia backend únicamente cuando un contrato necesario lo justifique, con autorización equivalente y pruebas pertinentes.

No publiques ni despliegues fuera del entorno de trabajo como parte de este encargo.

## 2. Principio de experiencia

Cada pantalla debe contestar, en lenguaje cotidiano:

1. ¿Dónde estoy?
2. ¿Qué información estoy viendo y de qué fecha es?
3. ¿Qué significa para mi trabajo?
4. ¿Qué puedo hacer ahora?
5. ¿Dónde consulto el detalle o regreso?

Diseña para distintas capacidades y niveles de experiencia. No infantilices, no uses caricaturas ni crees un modo separado etiquetado para adultos mayores. La experiencia predeterminada debe ser cómoda y profesional para todos.

Reducir complejidad significa organizar y explicar. No significa borrar información, ocultar restricciones importantes, inventar certezas o eliminar capacidades existentes.

## 3. Conservar información sin saturar

Usa tres niveles de lectura:

- Nivel 1, siempre visible: conclusión, dato principal, fecha, unidad, estado relevante y siguiente acción.
- Nivel 2, claramente accesible: motivos, comparación, listado relacionado e historial.
- Nivel 3: cifras exactas, fuentes, cálculo, versión y evaluación técnica autorizadas.

Usa controles concretos: «Ver por qué aparece este cliente», «Ver compras», «Ver cifras exactas», «Cómo se calculó». Evita un «Ver más» genérico repetido por toda la aplicación.

No pongas en un tooltip la única explicación de una cifra. No ocultes detrás de un desplegable que los datos son de prueba, que una estimación no está disponible o que la acción publicará información.

Antes de migrar cada vista, registra qué campos, acciones, estados y enlaces contiene. Después indica dónde quedó cada uno. Todo dato autorizado debe seguir accesible; cualquier eliminación requiere justificar redundancia real, no falta de espacio.

Las cifras pueden resumirse visualmente, pero el valor exacto, moneda y periodo deben estar disponibles mediante un control accesible, sin depender de hover. No cambiar precisión ni unidad en exportaciones o cálculos.

## 4. Lectura, controles y accesibilidad

Usa WCAG 2.2 AA como objetivo de accesibilidad y verifica los criterios aplicables. No declares conformidad completa únicamente porque pase una herramienta automática.

Estas son decisiones de producto para esta audiencia, adicionales al mínimo normativo:

- Texto principal y controles: equivalente inicial a 18 px con configuración habitual del navegador; usar unidades relativas.
- Etiquetas de campos, texto de tablas, instrucciones y errores: preferentemente 18 px.
- Texto secundario y etiquetas de gráficos: al menos equivalente a 16 px. La información indispensable no debe quedar como letra pequeña.
- Títulos: aproximadamente 28–32 px; subtítulos 22–24 px; indicadores 32–40 px cuando el espacio lo permita.
- Interlineado de lectura alrededor de 1,5–1,6; párrafos cortos y líneas de longitud cómoda.
- Botones, controles y zonas pulsables independientes: objetivo mínimo de 48 × 48 px CSS. En checkboxes/radios, ampliar la zona mediante su etiqueta sin deformar innecesariamente el indicador.
- Separación suficiente entre acciones para evitar pulsaciones accidentales; aproximadamente 8–12 px como punto de partida.
- Contraste del texto de al menos 4,5:1; procurar 7:1 para lectura principal cuando sea compatible con el diseño. Verificar contraste de controles y elementos gráficos esenciales según los criterios aplicables.
- Teclado completo, foco visible y sin quedar tapado, estructura semántica, etiquetas asociadas y nombres accesibles.
- Color acompañado de texto, forma o icono; estados distinguibles sin depender de rojo/verde.
- Acciones principales con palabras visibles: «Buscar clientes», «Guardar seguimiento», «Volver a la lista». Un icono solo no es suficiente para la navegación habitual.
- Sin doble clic, arrastrar, gestos ocultos o hover como requisito para completar una tarea.
- Tamaño de lectura Normal/Grande/Muy grande con preferencia persistente, sin interferir con el zoom y ajustes del navegador. No reducir la cantidad de información al aumentarlo.
- Sin carruseles automáticos, conteos animados, parpadeos ni actualizaciones que cambien la posición mientras se lee.

Los 18 px y 48 px son requisitos de diseño de este proyecto, no una afirmación de que WCAG AA exija esos tamaños exactos.

Comprueba ampliación al 200 % y reflujo equivalente a 320 px CSS —por ejemplo, 1280 px al 400 %— sin pérdida de contenido o acciones. Tablas que requieran dos dimensiones pueden desplazarse dentro de una región identificada; la página completa no debe obligar a desplazarse horizontalmente para leer textos y formularios.

## 5. Dirección estética profesional

Construye una identidad coherente con JACOMIND: verde de marca, superficies claras, texto oscuro, tipografía legible y gráficos sobrios. La calidad debe percibirse en alineación, espacio, jerarquía, claridad y consistencia.

- Tema claro como valor inicial para nuevas preferencias; conserva la elección existente y ofrece Claro/Oscuro/Sistema.
- Tipografía estable, legible y sin dependencia de descargas externas para la demo. Segoe UI/system-ui es válida si la jerarquía se trabaja bien.
- Sistema central de colores, tipografía, espaciado, bordes, foco y estados.
- Radios moderados, sombras discretas y divisiones claras; evitar paneles anidados innecesarios.
- Máximo orientativo de tres o cuatro indicadores en una cabecera. Cada uno debe responder una pregunta útil.
- Evitar gradientes intensos, transparencias que reduzcan contraste, gráficos 3D, fondos decorativos y una tarjeta para cada frase.
- No comprimir texto para que todo entre en una pantalla. Permitir desplazamiento vertical ordenado.
- Patrón distintivo común: «Qué está pasando → Por qué importa → Qué puedes hacer».

Mantén o crea `DESIGN.md` y `UX-CONTRACT.md` para registrar decisiones duraderas, reutilización de componentes y comportamiento. Las especificaciones deben corresponder a los estilos y controles realmente implementados.

## 6. Lenguaje de la aplicación

Escribe en español claro, respetuoso y concreto. Usa frases cortas, una idea por párrafo y verbos que expliquen la acción. Mantén los mismos términos en menú, título, botón y confirmación.

Adapta términos sin cambiar su significado:

| Término técnico | Presentación comprensible |
| --- | --- |
| Corte | «Datos hasta el 31 de octubre de 2026». |
| Probabilidad de compra | «Posibilidad estimada de compra en los próximos 30 días». |
| Cliente frío | «Lleva 90 días o más sin comprar», con fecha de referencia. |
| Próxima compra | «Cuándo conviene contactar», aclarando que la ventana es estimada. |
| Venta cruzada | «Productos que podrías ofrecer». |
| Anomalías | «Operaciones por revisar», aclarando que una señal no confirma un error. |
| En sombra | «En prueba. Esta sugerencia no ejecuta acciones automáticamente», cuando ese comportamiento sea cierto. |
| Null o N/A | Explicación precisa: «Faltan datos», «Sin compras registradas» o «Estimación no disponible». |
| MAE, AUC, modelo M3.1 | Explicación útil primero; nombre exacto y valor en el detalle autorizado. |

No llamar «seguridad» o «confianza» a un porcentaje que mide otra cosa. No sustituir «inconcluso» por «confiable» para mejorar la presentación.

Formatos:

- Español de Colombia para cifras y moneda; indicar COP o USD sin ambigüedad.
- Fechas legibles: «31 de octubre de 2026». En ejes compactos puede usarse abreviación clara con alternativa completa.
- Instantes según la zona de negocio configurada; las fechas de calendario no deben desplazarse por conversión UTC.
- Evitar abreviaciones como «193.9M» o «5.4B». Usar «193,99 millones de COP» con valor exacto accesible.
- Identificadores internos como información secundaria; no inventar nombres de clientes, segmentos o productos.

Mensajes:

- Vacío: explica qué falta y el siguiente paso posible.
- Sin resultados: muestra filtros activos y «Quitar filtros».
- Error: explica qué no se pudo hacer y cómo reintentar; conserva lo escrito.
- Éxito: confirma qué se guardó y permite verlo. La confirmación importante permanece en la pantalla; no existe solo en un aviso que desaparece.
- Estado incierto: no afirmar que una acción falló o tuvo éxito sin confirmación del servidor.

## 7. Navegación y orientación

Implementa las seis áreas del plan: Inicio, Clientes y ventas, Operaciones, Finanzas, Atención y Administración. Cada perfil ve solo sus áreas y acciones autorizadas. Las etiquetas de subpáginas deben expresar tareas comprensibles.

- Navegación estable con texto e iconos complementarios; máximo dos niveles visibles habituales.
- Un único destino activo, título claro, ubicación y regreso a la lista donde proceda.
- Inicio propio de Gerencia, Ventas, Operaciones, Finanzas, Atención y Empresa.
- Portal externo separado de la complejidad interna.
- En móvil: botón visible «Menú»; no depender únicamente del icono de tres líneas.
- Asistente accesible desde cabecera y ruta propia. No obligar a conversar para usar funciones existentes.
- Conservar URLs anteriores, acceso directo y navegación Atrás/Adelante.
- Persistir filtros confirmados, orden, página, serie y selección apropiados; restaurarlos al volver del detalle.
- Mostrar «Mostrando X–Y de Z» y filtros activos con opción clara de quitarlos.

No repetir la misma función con nombres distintos ni crear menús por cada versión de modelo.

## 8. Implementación de las 31 vistas

Sigue la especificación V01–V31 del plan. Aplica las reglas de este prompt a cada una y mantén una matriz de avance por vista.

### Acceso, Gerencia y Clientes — V01–V04

- Entrada simple con perfil y conjunto de datos; distingue la demo completa del ejemplo de ocho clientes.
- Gerencia: conclusión mensual, tres indicadores útiles, evolución de ventas, variación por familia y acciones con evidencia.
- Cartera: resumen compacto, búsqueda y filtros claros, lista legible con cliente, motivo y «Ver cliente».
- Ficha 360: acción principal, explicación, compra/cobertura relevante y pestañas comprensibles. Evitar apilar todos los modelos antes del historial.

### Seguimientos y recomendaciones — V05–V09

- Lista de trabajo y detalle con estado, evidencia, acciones disponibles y cronología real.
- Prevención: separar riesgo futuro de clientes que ya llevan 90 días sin comprar.
- Próxima compra: ventanas temporales claras y límites disponibles; distinguirlas de vencimientos contractuales.
- Venta cruzada: producto, motivo, compatibilidad y decisión permitida. Aceptar una sugerencia no significa que hubo una venta ni un mensaje enviado.

### Operaciones y Finanzas — V10–V16

- Coberturas: orden temporal, plazos comprensibles y conteo de coberturas distinto del de clientes.
- Operaciones por revisar: cola legible y detalle comparando valor observado con referencia, sin sugerir fraude confirmado.
- Finanzas: Resultado, Pronóstico, Escenarios e Informes como secciones coherentes.
- Demanda: gráfico principal de observado y estimado, horizonte y tabla de respaldo.
- TRM: explicar qué supuesto cambia y qué permanece fijo; no presentarlo como predicción del dólar.
- Informes: misma cifra, periodo y revisión que la aplicación; salida limpia para imprimir.

### Atención y Portal — V17–V23

- Bandeja: distinguir pendientes de clasificación, respuesta y revisión.
- Resolución: pasos claros para preparar, revisar y publicar; no fusionar generar borrador con publicar.
- Portal: beneficios y solicitudes propias con lenguaje simple; datos internos y borradores permanecen restringidos.
- Formularios breves, ayudas visibles, conservación de texto, radicado después de crear y detalle accesible.
- Beneficios y conocimiento: condiciones, vigencia, versión y fuentes; edición y publicación siguen siendo acciones distintas.

### Asistente, confianza y administración — V24–V31

- Asistente: sugerencias válidas para el conjunto actual, respuesta con fuentes y modo básico/agente identificado correctamente. El panel contextual completo sigue siendo P2.
- Centro de modelos y monitoreo: explicación por capacidad, fecha, disponibilidad, validación y avisos; métricas avanzadas en detalle autorizado.
- Inicio de Operaciones: caminos claros hacia coberturas y preparación de datos.
- Carga: elegir archivo, revisar calidad y confirmar lote; confirmar no equivale a publicar.
- Publicación: contexto del cierre actual, etapas reales y resultado confirmado.
- Actividad y configuración: fuera del recorrido comercial habitual, con efectos y permisos explícitos.

## 9. Gráficos que ayuden a entender

Cada gráfico debe incluir: título que responda una pregunta, frase de interpretación, periodo, unidad, etiquetas legibles, fuente, tabla equivalente y acción cuando corresponda.

Implementa los gráficos del plan que los datos reales permitan: línea mensual, barras por acción principal, diferencias por familia, coberturas por plazo, cronología del cliente, rangos de próxima compra, observado/estimado de demanda y comparación de operación atípica.

- Etiquetas directas cuando sea posible; limitar series simultáneas y ofrecer selección para consultar las restantes.
- Diferenciar observaciones y estimaciones por texto y trazo, además del color.
- No convertir nulos en cero ni unir huecos como observaciones continuas.
- Dibujar intervalos solo cuando el contrato los entregue. p10–p50 no equivale a una banda del 80 %.
- No dibujar porcentajes de confianza a partir de MAE ni porcentajes de fraude a partir de rareza.
- No combinar unidades o monedas en un mismo eje sin transformación justificada y visible.
- Un gráfico de una página o top-K no representa todo el universo; mostrar su alcance.
- Barras con cero como base y porcentajes con denominador definido.
- Seleccionar un gráfico conserva contexto y aplica un filtro visible; la misma acción está disponible mediante controles accesibles.
- En pantallas estrechas, reorganizar o permitir consulta tabular; no reducir el SVG entero hasta volver ilegibles sus letras.

## 10. Fechas, permisos y verdad de los datos

Resuelve explícitamente la diferencia observada entre cierre de septiembre y publicaciones predictivas de octubre. Verifica el estado actual: esas fechas son evidencia de la revisión anterior, no valores a fijar en código.

Cada panel debe distinguir, cuando corresponda: fecha de datos, publicación/versión, horizonte y última actualización humana.

Prepara datos coherentes para la demo mediante procedimientos existentes o muestra los cortes diferentes de forma clara. No cambies etiquetas para aparentar sincronización ni combines resultados incompatibles.

Preserva:

- Datos sintéticos identificados como datos de prueba.
- Separación entre cero, falta de historial, dato ausente, modelo desactivado y servicio fallido.
- Estados experimental, no disponible e inconcluso.
- Diferencia entre M1–M4 y entre A08 operativo y M5 experimental.
- Capacidad de consulta distinta de capacidad de gestionar, publicar, exportar o reconocer avisos.
- Aislamiento Empresa A/B y controles del servidor; esconder un botón no reemplaza autorización.
- Fuentes, valores exactos y reglas de cálculo.

No inventes ahorro, ventas recuperadas, margen, ROI ni efectividad empresarial. Una operación aceptada por un usuario no prueba un resultado comercial.

## 11. Formularios, carga y recuperación

- Etiquetas siempre visibles; placeholder solo como ejemplo.
- Validación comprensible junto al campo y resumen cuando haya varios errores; foco en el primer error al intentar guardar.
- Conservar datos después de error o recarga controlada; no guardar información sensible en almacenamiento persistente sin un diseño autorizado.
- Envío duplicado bloqueado y resultado confirmado por servidor.
- Acciones rutinarias reversibles sin diálogos innecesarios. Publicaciones y acciones de consecuencias relevantes muestran objeto, alcance y resultado esperado conforme al flujo existente.
- Protección frente a pérdida de cambios y conflictos de versión; no sobrescribir silenciosamente datos nuevos.
- «Buscar» y «Limpiar búsqueda» visibles; actualizaciones sin mover el foco ni sobrescribir resultados con respuestas antiguas.
- Estados diferenciados de carga inicial, actualización, vacío, error y sesión vencida.
- Si existen límites de sesión, comunicarlos y preservar trabajo de forma segura; no debilitar la política de autenticación para facilitar la demo.
- No usar `alert`, `confirm` o `prompt` nativos para flujos de producto; reutilizar diálogo accesible del proyecto o crearlo como componente común.

## 12. Forma de ejecutar el trabajo

1. Verifica rutas, datos y permisos; establece una copia de prueba y el inventario antes/después por vista.
2. Documenta el sistema visual y los patrones de navegación, texto, formularios y recuperación.
3. Implementa componentes compartidos y shell accesible sin romper los enlaces existentes.
4. Completa Gerencia → Cartera → Ficha → Seguimiento como primer recorrido integrado.
5. Implementa señales comerciales, pronóstico y los módulos financieros/operativos.
6. Completa Atención, Portal, beneficios, conocimiento, monitoreo y administración.
7. Verifica cada etapa en navegador, corrige problemas y continúa hasta completar P0/P1.
8. Actualiza documentación y prepara el recorrido de demo de 8–10 minutos.

Reutiliza `app/ui.js`, `app/nucleo.js` y los tokens compartidos. Si un patrón se repite, implementa una primitiva común. Evita soluciones independientes de botón, estado, fecha o tabla en cada pantalla.

Si una vista necesita datos nuevos, comprueba primero si la API ya los entrega. Si falta un contrato imprescindible, impleméntalo respetando permisos y semántica, con pruebas. Si depende de una regla comercial no definida, documenta esa limitación sin inventarla y continúa el resto del trabajo.

No escondas fallos con datos simulados o controles decorativos. No reduzcas el alcance a la portada ni lo declares terminado por haber cambiado los estilos globales.

## 13. Verificación obligatoria

Ejecuta los comandos existentes aplicables y registra resultados reales. En este proyecto, el README documenta:

    python -m unittest discover -s tests/app -t tests/app
    python -m unittest discover -s tests/integracion -t tests/integracion

Ejecuta también las pruebas específicas de los contratos y transformaciones que modifiques; amplía a la suite de modelos si cambias código compartido que pueda afectarlos. No introduzcas pruebas que solo reproduzcan el HTML.

Verifica en navegador real:

- Todos los roles y variantes modificados; acceso directo, atrás/adelante y retorno desde detalles.
- Resoluciones 1366×768, 1440×900, ancho de 1024 px y móvil de 390 px.
- Texto ampliado, zoom 200 %, reflujo 320 px CSS y los temas admitidos.
- Teclado, foco, botones grandes, etiquetas, estructura semántica y una comprobación representativa con lector de pantalla si está disponible.
- Gráficos, cifras exactas, valores nulos, base cero, intervalos ausentes y fechas distintas.
- Carga lenta, error, vacío, filtros sin resultados, doble envío, conflicto y permisos insuficientes.
- Filtros y exportaciones con alcance real; portal sin datos de otra empresa.

Toma capturas de las vistas implementadas. Corrige texto pequeño, elementos recortados, áreas pulsables insuficientes, acciones ocultas, contraste bajo y desplazamiento horizontal global.

Ejecuta la auditoría estática de diseño disponible, guarda el resultado y revisa cada señal. No confundas una limitación del analizador con un botón roto; documenta falsos positivos con evidencia del código y comportamiento. Las comprobaciones automáticas no sustituyen las manuales.

Prepara cinco tareas de comprensión:

1. Encontrar las ventas de un mes y explicar si aumentaron o disminuyeron.
2. Encontrar un cliente que requiere revisión y explicar el motivo.
3. Distinguir una compra registrada, un vencimiento y una ventana estimada.
4. Registrar un seguimiento y comprobar que quedó guardado.
5. Crear o consultar una solicitud propia y reconocer su estado.

Pruébalas con personas representativas de baja experiencia digital, incluidos adultos mayores, cuando estén disponibles. No entrenes primero a los participantes en los botones que deben encontrar. Registra confusiones y corrige. Si no hay participantes, deja esa validación pendiente de forma explícita; no la sustituyas por una afirmación de usabilidad comprobada.

## 14. Entregables y criterio de finalización

Entrega:

1. Implementación funcional de las vistas P0/P1 y componentes compartidos.
2. `DESIGN.md` y `UX-CONTRACT.md` coherentes con el resultado.
3. Matriz V01–V31 con estado, cambios, pruebas y evidencia visual.
4. Mapeo antes/después de campos, acciones y rutas, demostrando conservación de información autorizada.
5. Resultados de pruebas y revisión de accesibilidad con límites explícitos.
6. Guion de demo, datos usados y casos de ejemplo realmente existentes.
7. Resumen de archivos cambiados y pendientes concretos, si los hubiera.

El trabajo está listo cuando una persona puede ubicarse, entender el periodo y el significado de los datos, consultar el detalle y completar una tarea autorizada sin depender de vocabulario técnico. La aplicación debe verse consistente y profesional, conservar la información y responder con claridad tanto cuando funciona como cuando falta algo.

Empieza inspeccionando el proyecto y continúa con la implementación. No solicites confirmación para decisiones rutinarias ya definidas por este prompt.

---

## Referencias para accesibilidad

Los tamaños reforzados de lectura y controles son decisiones del proyecto. Como referencia para los criterios aplicables y su verificación:

- [W3C: personas mayores y accesibilidad](https://www.w3.org/WAI/older-users/).
- [W3C: contraste mínimo](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
- [W3C: tamaño mínimo de objetivos de puntero](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html).
- [W3C: reflujo del contenido](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).
