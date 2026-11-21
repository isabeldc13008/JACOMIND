# Prueba de comprensión con personas · mejora de vistas

Guion para ejecutar la **prueba con personas** del [plan de mejora de vistas](mejora-de-vistas.md#orden-de-entrega-y-validación). Usa el mismo cierre sintético antes y después del rediseño (demo del 31 de octubre de 2026). Antes del rediseño, usa la rama `main`; después, la rama `feat/mejora-de-vistas`. Registra cada sesión en [`registro-prueba-con-personas.csv`](registro-prueba-con-personas.csv).

## Preparación

1. `python -m api demo` sobre una base limpia y `python -m api servir --practica`.
2. Abre `http://127.0.0.1:8000/app/` y deja la pantalla de entrada. La persona elige el origen y su identidad sin ayuda.
3. En cada perfil, una sesión con escritorio y otra con teléfono. Para el teléfono, sirve la aplicación en la red local o usa el despliegue de prueba.
4. Lee la consigna tal como está escrita y no expliques la pantalla. Cronometra desde que termines de leer.

## Tareas por perfil

| Perfil (identidad) | Consigna | Respuesta correcta | Cuenta como ayuda |
| --- | --- | --- | --- |
| Gerencia (`ger1`) | «¿Cómo fueron las ventas del último mes frente al anterior y qué familia explica el cambio?» | Octubre 4,56 millones; septiembre 21,02 millones; −16,46 millones; Infraestructura −16,44 millones. El acumulado es 51,15 millones | Indicar dónde está «Ver ventas por familia» |
| Ventas (`ventas1`) | «Elige al cliente con el que hablarías primero por cobertura y justifica por qué.» | DEMO02: la cobertura de respaldo vence en 20 días al cierre y la estimación es del 55 %, mayor que el 48 % de DEMO06 | Señalar la barra «Revisar cobertura» |
| Ventas (`ventas1`) | «Registra una llamada con DEMO01 y su siguiente paso sin cerrar el seguimiento.» | Elegir «Registrar un contacto», completar nota y siguiente paso. La tarea sigue abierta | Explicar las opciones de «¿Qué quieres hacer?» |
| Finanzas (`fin1`) | «Si el dólar sube 8 %, ¿cuánto más costarían las compras en dólares de octubre? Demuéstralo.» | 96.000 COP más: 3 × 100 USD × 4.000 = 1.200.000 → 1.296.000 (compra CD03) | Abrir «Ver operaciones, supuestos y exclusiones» |
| Operaciones (`ops1`) | «¿Qué cobertura vence primero y qué cierre ven ahora los usuarios?» | DEMO02 (vence en 20 días); DEMO06 vencida. El cierre publicado es el 2026-10-31-r1, con datos hasta el 31 de octubre de 2026 | Indicar «Revisar vencimientos» |
| Atención (`aten1`) | «Prepara la respuesta al caso sobre el descuento por renovación y comprueba en qué política se apoya.» | Generar el borrador, abrir «Ver la sección citada» de POL-BENEF v2 y publicar después de guardar la edición | Explicar que la vista previa es la versión guardada |
| Empresa (`cli_a`) | «Encuentra el descuento por renovación, hasta cuándo puedes pedirlo y solicítalo. Después dime dónde volverás a consultar tu caso.» | Vigente hasta el 31 de diciembre de 2026; «Solicitar este beneficio»; guardar el número de seguimiento y volver a «Solicitudes de mi empresa» | Señalar «Solicitar este beneficio» |

**Pregunta de control para todos:** «Este 55 % (o esta proyección de noviembre), ¿es una venta?». La única respuesta correcta es **no**. Anota cualquier confusión entre pronóstico o alerta y venta confirmada.

## Registro y criterio

- Por tarea, anota: tiempo en segundos, acierto (sí, parcial o no), dudas en palabras de la persona, si necesitó ayuda y el dispositivo usado.
- **Objetivo inicial:** al menos 4 de cada 5 participantes de cada perfil completan su tarea sin ayuda. Evalúalo cuando cada perfil tenga al menos cinco participantes.
- **Meta de diseño en Gerencia:** responder la primera consigna en 30 segundos o menos.
- **Criterio de bloqueo:** ningún participante debe interpretar un pronóstico como ingreso confirmado. Si ocurre, repite la tarea después de corregir la pantalla.

## Revisión en teléfono

Con un ancho de 390 px, comprueba en cada perfil que la conclusión y la acción principal aparezcan sin desplazarse hacia los lados y que los importes exactos se lean al ampliar. En la implementación se midió con una ventana de 394 px: ninguna de las 21 vistas recorridas se desbordó, y la frase principal y la acción quedaron en la primera pantalla. Falta confirmarlo en dispositivos reales, con tacto y lector de pantalla.
