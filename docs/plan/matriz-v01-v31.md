# Matriz de cobertura V01–V31 · reorganización accesible

Fecha: 24 de noviembre de 2026. Planes: [reorganizacion-demo.md](reorganizacion-demo.md) y [prompt-implementacion-demo-accesible.md](prompt-implementacion-demo-accesible.md). Sistema visual: [DESIGN.md](../../DESIGN.md). Comportamiento: [UX-CONTRACT.md](../../UX-CONTRACT.md).

**Leyenda.** *Implementada* = el código está en el repositorio. *Comprobada* = se verificó en el navegador con la base de demostración (`salida/demo_accesible_2026_11_24/demo.sqlite3`): medición automática de desbordes, texto menor de 16 px, controles bajos, `h1` único, campos sin etiqueta y errores, y capturas o recorridos donde se indica. **Ninguna vista se ha validado todavía con personas usuarias reales** (ver §4).

## 1. Matriz

Las anchuras comprobadas son: E = 1366 px · M = 390 px · R = 320 px con letra «Muy grande» · T = 1024 px con letra «Muy grande».

| Vista | Prio. | Estado | Cambios principales | Pruebas | Evidencia |
| --- | --- | --- | --- | --- | --- |
| V01 Acceso y origen | P0 | Implementada y comprobada (E) | Bienvenida con conjunto, fecha y origen; perfil de demostración identificado como tal; «Entrar como [perfil]»; agenda local y ejemplo de 8 clientes en segundo nivel; mensajes distintos para servidor ausente, sin cierre y sin identidades; aviso de sesión vencida o salida. | Recorrido en el navegador | Recorrido |
| V02 Resumen ejecutivo | P0 | Implementada y comprobada (E, M, R, T) | Franja Qué/Por qué/Qué hacer; 3 indicadores con base y población; línea de 12 meses con opción de ver todo; diferencias por familia ordenadas que abren Finanzas con los mismos meses; «Dónde actuar ahora» con un fallo independiente por foco; ingreso acumulado como dato secundario. | `test_app_graficos` (variación con base cero) y suite de tableros | `capturas/01_gerencia_1366.png` |
| V03 Resumen comercial y Cartera | P0 | Implementada y comprobada (E, M, R, T) | Pestañas Resumen/Cartera completa; barras excluyentes por acción que filtran; hasta 20 oportunidades rotuladas con su límite; búsqueda y filtros visibles, «Quitar filtros», «Mostrando X–Y de Z»; descarga con alcance explícito; segmentos legibles («Segmento 2»); 0 % frente a sin estimación frente a sin historial. | `test_app_vistas` (selección y CSV filtrado) | `capturas/06_cartera_movil_390.png` |
| V04 Cliente 360 | P0 | Implementada y comprobada (E, M, R) | Volver a la cartera filtrada; acción principal con motivo; última compra, cobertura relevante y seguimiento; pestañas Resumen / Compras y coberturas / Estimaciones de los modelos / Seguimiento; cronología con compra (hecho), fin de cobertura (contrato) y ventana estimada (en prueba) diferenciados; M1–M4 en bloques separados, cada uno con su fecha. | Recorrido | `capturas/02_ficha_estimaciones_1366.png` |
| V05 Seguimientos | P0 | Implementada y comprobada (E, M, T) | Filtros por responsable, estado y tipo en la URL; lista con motivo, estado, responsable y próxima revisión; barras por estado de la lista (no un embudo); resultados por tipo en el detalle; avisos recientes. | `test_app_consultas_tareas` | Recorrido |
| V06 Detalle de seguimiento | P0 | Implementada y comprobada (E) | Cinco acciones con su explicación; campos obligatorios con error junto al campo y foco; un solo envío; confirmación persistente; conflicto con las diferencias; resultado incierto; volver con filtros. | En el navegador: dos clics producen **un** evento; foco en el error; confirmación visible | `capturas/03_seguimiento_detalle_1366.png` |
| V07 Clientes que podrían dejar de comprar | P0 | Implementada y comprobada (E, M, T) | Prevenir frente a reactivar separados; grupos excluyentes de la publicación (sin calcular sobre el top-K); K explicado como capacidad de revisión; evaluación en «Cómo se obtuvo» sin afirmar «bien calibrado». | Suite de M2 sin cambios | Recorrido |
| V08 Cuándo conviene contactar | P0 | Implementada y comprobada (E, M) | Gráfico de rangos ordenado por inicio (15 primeros) con el eje limitado al horizonte; el nivel p10–p50 se explica («no es una banda del 80 %»); fin de cobertura como rombo o texto en el borde; lista completa con las mismas fechas; casos sin ventana en su propio bloque. | `test_app_graficos` (sin fin inventado) | Recorrido |
| V09 Productos que podrías ofrecer | P0 | Implementada y comprobada (E, M) | Lista de clientes a la izquierda y hasta 3 sugerencias con «Ya tiene / Se sugiere / Por qué»; el número indica orden, no probabilidad; compatibilidad visible; decisión con motivo obligatorio; evaluación de la muestra en su propia pestaña. | En el navegador: motivo obligatorio y decisión «Aplazada» persistida | Recorrido |
| V10 Coberturas y renovaciones | P0 | Implementada y comprobada (E, M, T) | Indicadores de vencidas y próximas, aclarando que se cuentan coberturas; barras por plazo que filtran; listas ordenadas; días contados desde la fecha de los datos y no desde hoy; seguimientos actuales en un bloque aparte. | `test_app_vistas` (intervalos) | Recorrido |
| V11 Operaciones por revisar | P1 | Implementada y comprobada (E, M, T) | Pestañas Ventas/Compras; aviso «no confirma un error ni un fraude»; indicadores de pendientes, capacidad y evaluadas; filtros activos; la descarga dice que no aplica los filtros; métricas y cobertura en «Cómo se evaluó». | Suite M6 sin cambios | Recorrido |
| V12 Detalle de operación | P1 | Implementada y comprobada (E) | Página propia con volver a la cola filtrada; comparación del precio y la cantidad con escalas separadas; «Información insuficiente» si falta referencia; tres decisiones explicadas; motivo obligatorio; historial; puntuaciones en el detalle. | En el navegador: validación y revisión persistida y visible | `capturas/04_caso_atipico_1366.png` |
| V13 Resultado del mes | P0 | Implementada y comprobada (E, M, R) | Pestañas de Finanzas; serie Ventas/Compras; indicadores; línea con la proyección operativa A08 rotulada aparte del M5; comparación por familia que filtra; mayores cambios en el detalle. | `test_app_agente_finanzas` | Recorrido |
| V14 Pronóstico de demanda | P0 | Implementada y comprobada (E, M, R) | Series con nombre comprensible; gráfico observado/estimado; rango solo donde existe, como barra por punto; huecos en los meses no observables; 3 indicadores mensuales; MAE descrito como «error medio», no como confianza; tabla de respaldo; Unidades frente a COP según el permiso. | `test_app_graficos` (banda parcial y nulos) | `capturas/05_pronostico_1366.png` |
| V15 Escenarios del dólar | P1 | Implementada y comprobada (E, M) | Qué cambia y qué queda fijo; mes y porcentaje validados; comparación base/escenario/diferencia; barras desde cero; fórmula; cambiar un dato invalida el resultado; «Volver a 0 %». | `test_app_vistas` (simulador) | Recorrido |
| V16 Informes mensuales | P1 | Implementada y comprobada (E) | Último informe del cierre y botón para abrirlo; generar solo con permiso y con confirmación; historial y huella en el detalle. | `test_app_vistas` (informe) | Recorrido |
| V17 Solicitudes (bandeja) | P1 | Implementada y comprobada (E, M, T) | Indicadores por clasificar, borradores y pendientes; colas 1 y 2; columna «Siguiente paso»; antigüedad sin colores de SLA; Gerencia solo ve indicadores. | `test_app_pqrs_atencion` | Recorrido |
| V18 Resolver solicitud | P1 | Implementada y comprobada (E) | Pasos Clasificar → Preparar → Revisar y publicar; columna de solicitud e historial; «puntaje del clasificador» en vez de «confianza»; publicar con diálogo que muestra el texto y la empresa; bloqueo si hay marcas de revisión. | En el navegador: clasificar → borrador → corregir marcas → publicar; la Empresa A lo ve y la Empresa B recibe 404 | Recorrido |
| V19 Portal: inicio y beneficios | P1 | Implementada y comprobada (E, M) | Saludo; accesos a Mis solicitudes, Nueva solicitud y Asistente; tarjetas con condición, vigencia y política; «Solicitar no lo aprueba automáticamente». | `test_app_beneficios_documentos` | Recorrido |
| V20 Mis solicitudes / nueva | P1 | Implementada y comprobada (E, M) | Lista en curso / respondidas; búsqueda con «Limpiar búsqueda»; formulario aparte con resumen de errores; referencia del beneficio; un solo envío; resultado incierto explicado. | En el navegador: dos clics crean **una** solicitud | Recorrido |
| V21 Detalle de solicitud propia | P1 | Implementada y comprobada (E, M) | Número de seguimiento destacado tras crear (recibe el foco); estado, respuesta, texto original y cronología pública; radicado ajeno → «No encontramos esa solicitud en tu empresa». | Recorrido y `test_app_pqrs_atencion` | Recorrido |
| V22 Catálogo de beneficios | P1 | Implementada y comprobada (E, M) | Búsqueda y filtro por estado; acciones por permiso con diálogo para publicar y retirar; nuevo borrador en su pestaña con vista previa de la audiencia; retención en otra pestaña. | `test_app_beneficios_documentos` | Recorrido |
| V23 Base de conocimiento | P1 | Implementada y comprobada (E, M) | Biblioteca con búsqueda y «Solo vigentes»; versiones; retirar con diálogo de consecuencias; importar y probar en pestañas propias. | `test_app_beneficios_documentos` | Recorrido |
| V24 Asistente | P0 (acceso); P2 (panel contextual) | P0 implementada y comprobada; **P2 no incluida** | Acceso en la cabecera; modo básico declarado con honestidad; preguntas de ejemplo con un cliente real del conjunto activo (no `DEMO01`); botones con texto («Me sirvió», «No es correcta», «Copiar respuesta»); la pregunta no respondida se conserva. | `test_app_agente_chat` | Recorrido |
| V25 Modelos y monitoreo | P1 | Implementada y comprobada (E, M, T) | Una entrada con dos pestañas según permiso; tabla de capacidades (qué responde, disponibilidad, fecha, validación, avisos, dónde verla); sin verde por omisión; evaluación por modelo en el detalle. | `test_app_graficos` (estados) | Recorrido |
| V26 Aviso de modelo | P1 | Implementada y comprobada (E, M) | Página de aviso con volver; regla y definición; historial; reconocer o resolver con motivo y explicación de que no reentrena. | `tests/modelos/test_monitoreo` | Recorrido |
| V27 Inicio de Operaciones | P1 | Implementada y comprobada (E, M) | Dos caminos: coberturas y preparación del cierre, contados por separado; pendientes reales; cada consulta falla por separado. | Recorrido | Recorrido |
| V28 Cargar y validar | P1 | Implementada y comprobada (E, M) | Pasos Elegir → Revisar calidad → Confirmar; validación del mes y del archivo; conteos que concilian; «Confirmar no es publicar». | `test_app_operacion` | Recorrido (sin cargar archivo nuevo) |
| V29 Ejecutar y publicar | P1 | Implementada y comprobada en pantalla (E) | Diálogo con lo que verán los usuarios; un solo envío; resultado incierto. **No se ejecutó un cierre** en la copia de la demo. | `test_app_operacion`, `test_app_publicacion_permisos` | Recorrido |
| V30 Actividad | P1 | Implementada y comprobada (E, M) | Filtros por tipo y resultado; primero lo que requiere atención; ficha técnica en el detalle. | Recorrido | Recorrido |
| V31 Configuración y respaldos | P1 | Implementada y comprobada en pantalla (E) | Efecto de cada función; estado confirmado y vuelta atrás si falla; copia de seguridad con su estado. **No se cambiaron funciones ni se crearon copias en la demo.** | `test_app_operacion` | Recorrido |

## 2. Antes y después: dónde quedó cada información

Ninguna vista perdió campos, acciones ni enlaces autorizados. Lo técnico pasó al nivel 3 («Ver cifras exactas…», «Cómo se obtuvo», «Detalle técnico»).

| Vista | Antes | Después |
| --- | --- | --- |
| Menú | 14 enlaces planos en la barra («Prevención (IA)», «Modelos de IA», «Monitoreo (IA)», «Tableros», «Agenda»…). | Seis áreas laterales según permiso. «Tableros» se repartió así: Gerencia → Inicio (y Finanzas para su perfil), Ventas → Resumen comercial, Operaciones → Coberturas. «Agenda» pasó a ser «Cartera de clientes». «Modelos de IA» y «Monitoreo» quedaron en una sola entrada. Finanzas conserva el Resumen ejecutivo (lo detectó `test_app_navegacion`). |
| Gerencia | Frase, gráfico con «Ver diferencia por familia» desplegable, ingreso por segmento, tabla. | Lo mismo, más los indicadores y los focos. Diferencia por familia visible como barras con enlace; tabla exacta en «Ver cifras exactas por familia»; ingreso por segmento al final; misma fuente y regla en «Ver cifras exactas…». |
| Cartera | Filtros, barras, «Toda la cartera», tabla de 7 columnas, paginación, CSV y selector de cierre. | Todo conservado. «Por qué» se unió a «Acción» («Qué hacer y por qué»); el selector de cierre se llama «Mes de los datos»; la paginación muestra «Mostrando X–Y de Z»; hay fichas de filtros activos. |
| Ficha | 8 bloques seguidos. | Cabecera, franja e indicadores, y luego pestañas: Resumen (cronología y cifras), Compras y coberturas (productos, coberturas, últimas **30** operaciones; antes 20), Estimaciones (M1 con señales, M2, M3, M4) y Seguimiento (tarea y oportunidades). El registro original sigue en «Detalle técnico». |
| Seguimiento | Formulario de K y «Solo míos», tabla, medición, avisos. Detalle con intenciones y cronología. | Se añaden filtros de estado y tipo; la medición del equipo queda en «Ver cómo terminaron, por tipo». Campos y eventos iguales; versión, episodio y evidencia en el detalle técnico. |
| M2, M3, M4, M5, M6 | Bloques de método y JSON al inicio; tablas. | Las mismas tablas y notas. Método y publicación en «Cómo se obtuvo» o «Cómo se evaluó»; el JSON original en el detalle técnico. Gráfico nuevo en M3 y M5. |
| Finanzas | Una página: resultado, simulador e informes. | Tres secciones con URL propia y pestaña Pronóstico. El simulador y los informes conservan todos sus campos, desgloses y huellas. |
| PQRS, beneficios y documentos | Botones y formularios en línea; retirar con confirmación en línea. | Mismas acciones; las de consecuencias relevantes usan un diálogo accesible. Los formularios de creación están en pestañas propias. |
| Operación | Tres preguntas, pestañas y cuatro secciones. | «Qué requiere atención» en Datos y cierres; Actividad y Configuración como destinos propios del menú; se conservan todas las acciones y fichas técnicas. |

## 3. Pruebas realizadas (resultados reales)

| Comprobación | Resultado |
| --- | --- |
| `python -m unittest discover -s tests/app -t tests/app` | **156 OK, 1 omitida** (LangGraph). Incluye 12 pruebas nuevas: `test_app_navegacion` (5) y `test_app_graficos` (7). |
| `python -m unittest discover -s tests/integracion -t tests/integracion` | **10 OK, 5 omitidas**: faltan el paquete de datos hermano y `salida/agenda.json` del carril A en este equipo; no depende de estos cambios. |
| Sintaxis de los módulos (`node --check`, prueba existente) | OK |
| Medición automática en el navegador (Chrome; base de demostración; ventana de prueba de 1366, 1024, 390 y 320 px; letra normal y «Muy grande») | Pasada final con todos los cambios: **77 de 77** combinaciones correctas (42 a 1366 px, 20 a 390 px, 11 a 320 px con «Muy grande» y 4 a 1024 px con «Muy grande»), con los perfiles Gerencia, Ventas, Finanzas, Operaciones, Atención y Empresa A. Criterios: sin desborde horizontal de página, sin texto menor de 16 px, sin controles de menos de 44 px, un `h1` por pantalla, todos los campos etiquetados, un solo destino activo y ningún error visible. |
| Teclado | En la cartera, los 53 elementos enfocables muestran contorno de foco; «Saltar al contenido» es visible al enfocarlo. Diálogo de retirar una política: foco inicial en «Cancelar»; con la tecla Escape real se cierra, el foco vuelve al botón y no se retira nada. |
| Recorridos con persistencia (en la copia de la demo) | Contacto en el seguimiento 142; decisión «Aplazar» sobre PRO02 para CLI030; revisión «Información insuficiente» de VEN00668; solicitud PQRS-20261124-00004 creada por la Empresa A, clasificada, preparada y publicada por Atención y visible para la Empresa A; la Empresa B recibe 404. |
| Tema oscuro | Revisado en Finanzas; contrastes calculados en DESIGN.md. |
| Auditoría estática `impeccable detect` | 7 señales → 2 corregidas y 5 justificadas (DESIGN.md). |

**Defectos encontrados y corregidos durante la verificación:**

- El script en línea de preferencias estaba bloqueado por la política de seguridad.
- Textos ocultos para lectores de pantalla desbordaban las tablas.
- En el Resumen ejecutivo, el gráfico obligaba a desplazarse dentro de su columna.
- Etiquetas de valor superpuestas y la leyenda «Proyección operativa» cortada.
- El eje de la próxima compra quedaba estirado por vencimientos de 2027.
- Las barras de distintas filas no eran comparables entre sí.
- Una casilla quedaba separada de su texto en móvil.
- Las listas desplegables con opciones largas desbordaban en móvil.
- Identificadores `seg_2` a la vista.
- El título «otra persona cambió…» aparecía para cualquier 409.
- No se avisaba de las marcas «[REVISIÓN REQUERIDA]» antes de publicar.
- Finanzas perdía el acceso al Resumen ejecutivo.

**Límites de la verificación:**

- El navegador de este equipo tiene una ventana de 1024 px CSS (pantalla de alta densidad). Para medir otros anchos se cargó la aplicación en un marco del tamaño pedido, a través de un proxy local de pruebas que solo relaja `frame-ancestors`; el servidor y su política no se modificaron. Los anchos 1440 y 1024 sin «Muy grande» se cubren con las mismas reglas, pero no se capturaron.
- El zoom del 200 % se aproximó con «Muy grande» a 1024 y a 320 px: es equivalente en reflujo, pero no es el zoom del navegador.
- No se probó con un lector de pantalla real: solo se comprobaron la estructura (encabezados, regiones, etiquetas, `aria-current`, `role=status`) y el foco.
- No se declara la conformidad con WCAG 2.2 AA.

## 4. Validación pendiente con personas usuarias

No hubo participantes disponibles en esta sesión. **La facilidad de uso no está comprobada con usuarios.** Tareas preparadas para probar sin entrenamiento previo, con personas de poca experiencia digital, incluidos adultos mayores:

1. Encontrar las ventas de octubre de 2026 y decir si aumentaron o disminuyeron respecto a septiembre. Respuesta esperada: aumentaron en 23,16 millones de COP, un 11,9 %.
2. Encontrar un cliente que requiere revisión y explicar el motivo. Por ejemplo, CLI030: una cobertura vence el 18 de noviembre de 2026.
3. En la ficha de CLI030, distinguir la compra registrada (24 de octubre), el vencimiento de contrato (18 de noviembre) y la ventana estimada (del 3 al 19 de noviembre, en prueba).
4. Con el perfil de Ventas, registrar un contacto en un seguimiento y comprobar que quedó guardado.
5. Con el perfil de Empresa A, crear una solicitud y reconocer su estado y su número de seguimiento.

Registrar para cada tarea: si se completó sin ayuda, el tiempo, las dudas y las palabras que no se entendieron. Después, corregir y volver a probar.

## 5. Fuera de alcance (P2) y pendientes concretos

- Panel contextual del asistente («Explicar este dato»), calendario avanzado, kanban, métricas de ROI y automatización de contactos: P2, no implementados.
- Crear un seguimiento desde una recomendación: no existe ese contrato en la API. La ficha enlaza al seguimiento existente y explica que los crea el cierre.
- Asignación o fecha límite de los seguimientos, distribución completa del riesgo y nombres de producto en el pronóstico por unidades: requieren contrato o diccionario. Se muestran los identificadores.
- La descarga CSV de operaciones por revisar no aplica los filtros de pantalla (limitación de la API); la pantalla lo indica.
