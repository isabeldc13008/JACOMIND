# Guion de demostración · JACOMIND accesible (8 a 10 minutos)

Base de demostración: `salida/demo_accesible_2026_11_24/demo.sqlite3`. Es una copia de `salida/revision_ui_demo_2026_11_24/demo_completa.sqlite3` a la que se publicó, con el procedimiento existente, el cierre `salida/cierres/cierre-2026-10-31-a4a4de0b68d842de` (`python -m api --db … publicar …`).

**Resultado:** la cartera y las estimaciones en prueba usan la misma fecha, el 31 de octubre de 2026. Con esto se resuelve la diferencia septiembre/octubre de la revisión anterior sin cambiar ninguna etiqueta. Los cierres de agosto y septiembre siguen disponibles en «Mes de los datos».

## Antes de presentar

1. Restaurar la copia limpia (borra lo que se haya registrado en ensayos):
   `copy salida\demo_accesible_2026_11_24\demo_limpia.sqlite3 salida\demo_accesible_2026_11_24\demo.sqlite3` con el servidor detenido.
2. Iniciar: `python -m api --db salida/demo_accesible_2026_11_24/demo.sqlite3 servir --puerto 8000` y abrir `http://127.0.0.1:8000/app/`.
3. En «Letra y colores», elegir **Claro** y el tamaño que se lea bien en el proyector (Grande para salas medianas).
4. El asistente funciona en **modo básico** si no hay un modelo de lenguaje configurado. Hay que nombrarlo así y usar las preguntas de ejemplo.
5. Todos los datos son **de práctica**: decirlo al empezar. No presentar ninguna cifra como resultado de un cliente real ni como ahorro o ventas recuperadas.

## Recorrido

| Tiempo | Perfil y pantalla | Qué hacer | Qué decir | Qué debe verse |
| --- | --- | --- | --- | --- |
| 0:00–0:45 | Entrada → **Gerencia** | Elegir «Gabriela Gerencia» y pulsar «Entrar como Gerencia». | «Partimos de información concreta y sabemos hasta qué fecha llega.» | Cabecera «Datos hasta el 31 de octubre de 2026 · Datos de práctica». La franja: en octubre de 2026 se confirmaron ventas por **217,16 millones de COP**, 23,16 millones más que en septiembre (+11,9 %). |
| 0:45–2:00 | Resumen ejecutivo | Señalar la línea de 12 meses y «¿Dónde cambió el resultado?». Pulsar la barra **Servicios**. | «Localizamos dónde cambió: Servicios explica la mayor diferencia, +15,57 millones. Es una diferencia aritmética; la causa requiere más evidencia.» | Se abre Finanzas → Resultado con septiembre y octubre ya elegidos y la familia Servicios. |
| 2:00–3:30 | Volver al Inicio → «Ver clientes a revisar» → filtro **Revisar cobertura** → **CLI030** | Pulsar la barra «Revisar cobertura» y luego «Ver cliente» en CLI030. | «Del resumen pasamos a quién necesita atención y por qué.» | 64 clientes con cobertura por revisar, con el filtro visible. CLI030: la cobertura de Licencia de gestión documental vence el 18 de noviembre de 2026, a 18 días de la fecha de los datos. Pulsar «Volver a la cartera filtrada» conserva el filtro. |
| 3:30–5:00 | Ficha de CLI030 → pestaña «Estimaciones de los modelos»; después «Productos que podrías ofrecer» con CLI030 | Mostrar la cronología de la pestaña Resumen y luego las estimaciones. | «Las estimaciones ayudan a preparar la conversación, pero están en prueba y no actúan solas.» | Compra registrada el 24 de octubre (hecho); fin de cobertura el 18 de noviembre (contrato); ventana estimada del 3 al 19 de noviembre (del 10 % al 50 %, en prueba). 46,8 % de posibilidad estimada de compra en 30 días. Productos sugeridos con «Ya tiene / Se sugiere» y la compatibilidad por revisar. |
| 5:00–6:30 | Salir → **Ventas** («Víctor Ventas») → Seguimientos → abrir el primero | Elegir «Registrar un contacto». Pulsar «Guardar» sin escribir para mostrar la ayuda; luego escribir «Llamada; pide propuesta» y guardar. | «La decisión humana queda registrada y se puede seguir.» | Error junto al campo; luego «Contacto guardado. El seguimiento sigue abierto» y el evento en «Qué ha pasado». |
| 6:30–8:00 | Salir → **Finanzas** («Fernando Finanzas») → Pronóstico | Mostrar el gráfico y los tres meses estimados; abrir «Ver valores exactos». | «Vemos los próximos meses y también cuánto se equivocó la estimación en meses ya conocidos.» | Línea continua observada y discontinua estimada; rango solo para noviembre (empírico, sin garantía); error medio descrito como error, no como confianza; sello «En prueba». |
| 8:00–9:00 | **Modelos y monitoreo** (Gerencia o Finanzas) | Leer la tabla de capacidades. | «Conocemos los límites: qué está en uso, qué está en prueba y qué avisos hay.» | Compra a 30 días «En uso (modo demostración)»; el resto «En prueba» con validación inconclusa; los avisos activos del monitoreo, sin ningún «verde» por falta de datos. |
| Opcional | **Empresa A** → Nueva solicitud → **Atención** resuelve | Crear la solicitud; con Atención, clasificar, preparar el borrador, completar lo marcado y publicar (diálogo). Volver como Empresa A. | «La misma evidencia mejora la atención y solo publica lo revisado.» | Número de seguimiento tras crear; la publicación pide confirmación y nombra la empresa; la Empresa A ve la respuesta y la Empresa B no puede abrirla. |

## Casos de respaldo

- **Cliente sin estimación:** en la Cartera, «Mes de los datos» → 30 de septiembre de 2026. El modelo de compra no estaba disponible antes del 30 de octubre, así que se ve «Hay compras, pero falta la estimación».
- **Prevención frente a reactivación:** «Clientes que podrían dejar de comprar» separa 41 clientes con 30 a 89 días sin comprar de los 41 que ya llevan 90 días o más.
- **Operación por revisar:** VEN00668 (precio 1,11 veces la referencia; cantidad por debajo de la habitual). Decir que «una señal no confirma un error».
- **Accesibilidad:** cambiar a «Muy grande» y mostrar que la información sigue completa; en el teléfono, el botón «Menú».

## Qué no prometer

No presentar «más ventas», «menos fuga» ni «ahorro» como beneficios medidos. La efectividad comercial requiere un piloto con datos reales: adopción de sugerencias, tiempo de revisión, acciones completadas y resultados posteriores, con su población y su comparación.
