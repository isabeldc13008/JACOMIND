# JACOMIND · Contrato de experiencia

Comportamiento que toda pantalla cumple. Lo implementan los componentes comunes de `app/ui.js`, `app/nucleo.js`, `app/navegacion.js` y `app/app.js`. Las decisiones visuales están en [DESIGN.md](DESIGN.md). Los permisos del servidor (`api/permisos.py`) son siempre la autoridad: ocultar un botón no sustituye la autorización.

## 1. Cinco preguntas por pantalla

| Pregunta | Cómo se responde | Componente |
| --- | --- | --- |
| ¿Dónde estoy? | Destino activo único en el menú lateral; ruta «Área › Página»; un `h1`. | `areasPara`, `activoEn`, `encabezado()` |
| ¿De qué fecha son los datos? | Cabecera global («Datos hasta el 31 de octubre de 2026» y «Datos de práctica») y contexto propio de la página: fecha de los datos, publicación, horizonte y última actualización humana, cada uno con su rótulo. | `encabezado({contexto})`, `ctxDatos()` |
| ¿Qué significa? | Franja «Qué está pasando → Por qué importa → Qué puedes hacer» en lenguaje cotidiano. | `hallazgo()` |
| ¿Qué puedo hacer ahora? | Acción principal con verbo visible. Las acciones que el perfil no puede hacer no se muestran y se explica por qué. | botones, `vacio()` |
| ¿Cómo consulto el detalle o regreso? | «Ver cifras exactas y cómo se calcularon», «Ver valores exactos», «Cómo se obtuvo», y en los detalles un enlace «Volver a …» que conserva los filtros. | `verDatos()`, `encabezado({volver})` |

## 2. Navegación

- Hay seis áreas: Inicio, Clientes y ventas, Operaciones, Finanzas, Atención y Administración. El menú se genera desde las capacidades de cada perfil, sin listas fijas por rol. El portal de empresas tiene su propio menú de dos entradas.
- Cada perfil tiene su inicio: Gerencia (Resumen ejecutivo), Ventas (Resumen comercial), Operaciones («¿Qué necesitas hacer?»), Finanzas (Resultado), Atención (Solicitudes) y Empresa (Beneficios).
- El Asistente está en la cabecera y en `#/asistente`; no ocupa un área del menú.
- Por debajo de 1024 px hay un botón «Menú» con texto, que abre la navegación como bloque.
- Todas las rutas anteriores siguen funcionando: `#/agenda`, `#/tableros/:rol`, `#/clientes/:id`, `#/tareas/:id`, `#/finanzas`, `#/ia`, `#/monitoreo`, `#/operacion?seccion=…`, etc. Las nuevas secciones van en la URL (`?seccion=`, `?pestana=`, `?caso=`, `?aviso=`, `?cliente=`), así que Atrás y Adelante restauran la pantalla.
- Los filtros, la página, la serie y la selección viven en la URL. Al volver de una ficha o un caso se recupera la lista filtrada. Cambiar un filtro reinicia la página.
- Al cambiar de pantalla (no al filtrar), el foco pasa al contenido y la página vuelve arriba. Al filtrar, el foco se queda donde estaba.
- Los saltos dentro de la página usan `data-ir-a` y no `#id`, porque la dirección `#/…` es la ruta de la aplicación.

## 3. Datos y verdad

- La fecha de los datos de cada estimación se muestra aparte. Si no coincide con la cartera, se avisa («Fechas distintas…») y no se compara.
- Las estimaciones llevan el sello visible **«En prueba»** y el aviso «Esta sugerencia no ejecuta acciones automáticamente». Nunca se ocultan en un desplegable.
- Se distinguen con texto: 0 %, «Sin compras registradas», «Hay compras, pero falta la estimación», «Estimación no disponible», «Sin dato (mes incompleto)» y «Tu perfil no tiene permiso».
- No se combinan M1 a M4 en una puntuación. M5 se presenta como estimación y no como ingreso. M6 se llama «Operaciones por revisar»: una señal no confirma un error ni un fraude.
- La variación porcentual es (actual − anterior) ÷ anterior × 100, solo con una base mayor que cero; si no, «sin base porcentual».
- Los identificadores técnicos pasan a segundo plano: «seg_2» se muestra como «Segmento 2» con su descripción publicada, y `ventas_cop:Total` como «Ventas totales (en pesos)». No se inventan nombres.
- Los importes se escriben como «217,16 millones de COP», con el valor exacto en la tabla, y nunca como «217M». Las fechas se escriben como «31 de octubre de 2026». Las horas se muestran en la zona de Colombia; las fechas de calendario no se convierten.

## 4. Formularios y acciones

| Regla | Implementación |
| --- | --- |
| Etiquetas siempre visibles, con ayuda debajo | `label` con `<span class="ayuda">`; el `placeholder` solo como ejemplo. |
| Error junto al campo y foco en el primero | `aria-invalid`, mensaje en `.error-campo`, resumen de errores en el portal, beneficios y documentos. |
| Se conserva lo escrito | Los errores no repintan el formulario. En el asistente, la pregunta no respondida vuelve al cuadro de texto. |
| Sin envíos duplicados | Botón deshabilitado con «Guardando…» y clave de idempotencia por formulario (`Idempotency-Key`), reutilizada al reintentar. Comprobado: dos clics crean un solo contacto y una sola solicitud. |
| Resultado incierto | Si se pierde la conexión: «No sabemos si … llegó; comprueba el estado actual». No se afirma éxito ni fallo sin respuesta del servidor. |
| Conflicto de versión | Se muestra qué cambió, no se sobrescribe y se ofrece «Ver la versión actual y decidir de nuevo». |
| Confirmación persistente | Las confirmaciones importantes quedan en la página (`#msg`), reciben el foco e indican dónde verificar el resultado. |
| Consecuencias relevantes | Un diálogo accesible propio (`confirmar()`, con `<dialog>`, foco inicial en «Cancelar» y Escape para cancelar) dice el objeto, el alcance y el resultado: publicar la respuesta a una empresa, publicar o retirar un beneficio, retirar una política, ejecutar o publicar un cierre, generar un informe. No se usan `alert`, `confirm` ni `prompt`. |
| Pasos separados | Preparar un borrador ≠ publicar. Confirmar un lote ≠ publicar el cierre. Aceptar una sugerencia ≠ vender. Reconocer un aviso ≠ resolverlo o reentrenar. |
| Precondiciones del servidor | El texto con marcas «[REVISIÓN REQUERIDA…]» desactiva «Publicar» y explica qué completar antes de enviar. |

## 5. Estados

| Estado | Presentación |
| --- | --- |
| Carga inicial | Indicador giratorio y texto «Cargando …». Al actualizar filtros no se borra la pantalla anterior. |
| Respuestas antiguas | Se descartan con `nuevoTurno()`/`vigente()`, para que una respuesta lenta no reemplace a otra más nueva. |
| Vacío | `vacio(título, qué falta, siguiente paso)`. |
| Sin resultados | Filtros aplicados como fichas con «×» y botón «Quitar filtros». |
| Error | Qué no se pudo hacer (permiso, no encontrado, conflicto, sin conexión) y botón «Volver a intentar». |
| Sesión vencida | Vuelve a la entrada con el aviso «Tu sesión terminó. Vuelve a entrar con tu perfil». |
| Sin permiso | Explicación del perfil («puede consultar, no modificar»); el servidor responde 403 de todos modos. |

## 6. Preferencias

«Letra y colores» en la cabecera ofrece el tamaño (Normal, Grande, Muy grande) y los colores (Claro, Oscuro, Según el equipo). Se guardan en este equipo y se aplican antes de pintar con `app/preferencias.js`, que va en un archivo aparte porque la política de seguridad del servidor bloquea los scripts en línea. No guardan datos sensibles y no interfieren con el zoom del navegador.
