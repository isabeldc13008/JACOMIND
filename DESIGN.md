# JACOMIND · Sistema visual

Registro de decisiones visuales vigentes. Corresponde a lo implementado en `app/estilos.css`, `app/ui.js`, `app/navegacion.js` e `app/index.html` (24-11-2026). El comportamiento está en [UX-CONTRACT.md](UX-CONTRACT.md).

## Dirección

**Sala de decisiones comercial**, para personas con poca experiencia digital, incluidos adultos mayores. Superficies claras, verde de marca, texto oscuro y una conclusión por pantalla. La calidad está en la alineación, el espacio, la jerarquía y la coherencia, no en adornos. Amplía la identidad anterior: conserva el verde `#1f6e43` y el azul de observaciones, sin reemplazarla.

El rasgo propio es la franja **«Qué está pasando → Por qué importa → Qué puedes hacer»** (`hallazgo()` en `app/ui.js`): una sola banda en tres columnas unidas por una flecha, que en móvil se apila. Abre cada pantalla de trabajo.

## Lectura

| Elemento | Valor | Notas |
| --- | --- | --- |
| Base | `html { font-size: 112.5% }` = 18 px con el ajuste habitual del navegador | Todo en `rem`: respeta el tamaño elegido en el navegador y el zoom. |
| Tamaño «Grande» / «Muy grande» | 125 % (20 px) / 140,625 % (22,5 px) | Preferencia persistente (`jacomind.tamano`). Cambia el tamaño, no la cantidad de información. |
| Texto principal, controles, tablas, etiquetas | 1 rem (18 px) | |
| Texto secundario (`--t-sec`) | 0,889 rem (16 px) | Mínimo para información visible. La auditoría automática no encontró texto menor de 16 px en las pantallas revisadas. |
| Título de página | 1,667 rem (30 px) | Uno por pantalla (`h1`). |
| Subtítulo | 1,278 rem (23 px) | |
| Cifra de indicador | 1,667 rem (30 px), peso 750, números tabulares | Se redujo de 34 px para que «217,16 millones de COP» no se parta en tres líneas. |
| Interlineado | 1,58 | Párrafos de hasta 72 caracteres. |
| Tipografía | Segoe UI / system-ui | Sin descargas externas para la demo. La jerarquía sale de la escala y el peso. Los datos usan números tabulares. |

## Color

Tokens en `:root` (claro, valor inicial) y `[data-theme="dark"]` (también según el sistema con «Según el equipo»).

| Uso | Claro | Contraste sobre blanco |
| --- | --- | --- |
| Texto principal `--texto` | `#15221b` | 16,4:1 |
| Texto secundario `--texto-2` | `#3b4a41` | 9,4:1 (8,5:1 sobre el fondo) |
| Texto terciario `--texto-3` | `#56645b` | 6,2:1 |
| Marca y enlaces `--acento` | `#1f6e43` | 6,2:1 (5,4:1 sobre `--acento-suave`) |
| Observado `--serie-obs` | `#1f5fae` | 6,4:1 · línea continua y círculos |
| Estimado `--serie-est` | `#a04d0a` | 5,9:1 · línea discontinua y rombos; fondo de rango `--estimado-suave` |
| Aviso (sello «En prueba») | `#7a4d00` sobre `#fdf1d6` | 6,5:1 |
| Error | `#b42318` sobre `#fdecea` | 5,8:1 · con icono «✕» y texto |
| Foco `--foco` | `#1b5fbf` | contorno de 3 px separado 3 px |

Tema oscuro: texto 15,1:1, secundario 10,8:1 y acento 9,1:1 sobre `#171e1a`. Valores calculados con la fórmula de luminancia de WCAG.

Los estados nunca dependen solo del color. Cada sello lleva texto («En prueba», «Vigente», «Requiere revisión»). Las barras negativas llevan un rayado y el signo «−» escrito. Lo observado y lo estimado se distinguen también por el trazo y la forma del marcador.

## Espacio, forma y profundidad

- Espaciado: 0,5 / 1 / 1,5 / 2 / 3 rem (`--e1`…`--e5`).
- Radios: 10 px en controles y 14 px en paneles. Sombra discreta con desplazamiento (`--sombra`); sin sombra en el tema oscuro.
- Paneles sin anidar tarjetas dentro de tarjetas. A lo sumo cuatro indicadores por cabecera, cada uno con su periodo, base o población.
- Estructura: navegación lateral de 16,5 rem; contenido con un ancho máximo de 90 rem. En las páginas sin sesión, una sola columna de hasta 64 rem.

## Controles

- Altura mínima `--control` = 2,75 rem (49,5 px con la base de 18 px). La auditoría no encontró controles de menos de 44 px en ningún perfil ni ancho; la mayoría mide 49 px o más.
- Separación de 8 a 12 px entre acciones.
- Las acciones principales tienen texto visible («Buscar clientes», «Guardar el contacto», «Volver a la lista filtrada»). Los iconos acompañan, nunca sustituyen el texto. Los iconos son SVG propios de trazo uniforme (`navegacion.js`); no se usan emoji.
- Las casillas y botones de opción miden 1,35 rem. Su zona pulsable es toda la etiqueta (`label.en-linea`, ≥ 48 px).
- Controles nativos: `select`, `input type=date` y `input type=file` son nativos por decisión. Son accesibles con teclado y lector de pantalla y toman el idioma del navegador. Las fechas «AAAA-MM» se escriben con ayuda visible y validación propia.

## Gráficos (`app/ui.js`)

| Componente | Reglas implementadas |
| --- | --- |
| `graficoLinea` | Título que responde una pregunta, unidad, leyenda con texto, etiquetas del eje de 17 px dentro de un lienzo de al menos 40 rem. En pantallas estrechas el lienzo se desplaza dentro de su región, sin encoger las letras. Los nulos son huecos con el texto «sin dato», nunca cero. Las estimaciones tienen otro color, línea discontinua y rombos. El rango solo aparece en los puntos que traen límite inferior y superior, como barra vertical con su nivel en la leyenda. Separación vertical rotulada «← Observado / Estimado →». Siempre con «Ver valores exactos» (tabla con COP exactos). |
| `graficoRangos` | Una fila por cliente y un eje desde la fecha de los datos hasta el horizonte del modelo. La ventana es una barra; el fin de cobertura es un rombo (fecha de contrato). Un límite que no se alcanza se muestra como «sin fin en el horizonte →». Un vencimiento fuera del eje se indica con texto en el borde. La lista completa debajo tiene las mismas fechas. |
| `barras` | Base cero. Todas las filas comparten columnas (subgrid), así que las longitudes son comparables. El valor va escrito. Cuando la barra es un enlace, filtra y muestra el filtro aplicado. |

## Excepciones de la auditoría estática

`impeccable detect` (resultado en `salida/demo_accesible_2026_11_24/evidencia/auditoria_ui.json`) deja cinco señales. Se revisaron y se conservan porque son funcionales:

| Señal | Dónde | Por qué se conserva |
| --- | --- | --- |
| `side-tab` (borde izquierdo de 3 px) | `.cronologia`, `.actividad`, `.historial` | Es el eje de la línea de tiempo, no un acento decorativo de una tarjeta. |
| `border-accent-on-rounded` (borde inferior de 4 px) | Pestaña activa | Indica la pestaña seleccionada, junto con el peso del texto y `aria-current`. |
| `border-accent-on-rounded` (borde superior de 3 px) | `.muestra` de la leyenda | Reproduce el trazo de la serie en la leyenda. |
| `repeating-stripes-gradient` | Barras negativas | Distingue disminuciones sin depender del color. |
| `gpt-thin-border-wide-shadow` | Panel «Letra y colores», diálogo | Profundidad de elementos que flotan sobre la página; no se aplica a tarjetas. |

Se corrigieron dos señales: un contraste bajo al pasar el puntero (enlace «Saltar al contenido» y destino activo del menú) y una animación pulsante del asistente, que se cambió por un indicador de carga sin parpadeo.
