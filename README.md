# JACOMIND

[Plan de la hackatón de Green Services para dos personas](PLAN_HACKATON.md)

[Plan de implementación del proyecto completo](PLAN_IMPLEMENTACION.md) · [Tareas de datos y modelos](docs/plan/datos-y-modelos.md) · [Tareas de aplicación y operación](docs/plan/aplicacion-y-operacion.md)

[Plan de mejora de las vistas por perfil](docs/plan/mejora-de-vistas.md) · [Reorganización accesible para la demo](docs/plan/reorganizacion-demo.md) · [Matriz V01–V31](docs/plan/matriz-v01-v31.md) · [Sistema visual](DESIGN.md) · [Contrato de experiencia](UX-CONTRACT.md)

[Planes detallados del modelo de compra y cinco modelos adicionales](docs/plan/modelos/README.md)

## Arranque rápido

Requiere Python 3.10 o superior. La aplicación y la API usan solo la biblioteca estándar.

```bash
python -m api demo               # crea var/jacomind.sqlite3 con datos ficticios de demostración
python -m api servir --practica  # abre http://127.0.0.1:8000/app/
```

En «Origen y sesión» elige el origen de datos (servidor, salida local o ejemplo de práctica) y una identidad ficticia: `ops1` (Operaciones), `ventas1`, `fin1`, `aten1`, `ger1`, `cli_a` (Empresa A) o `cli_b` (Empresa B). Guion completo: [docs/demo.md](docs/demo.md). Demostración accesible de 8–10 minutos con la base `salida/demo_accesible_2026_11_24/demo.sqlite3`: [docs/demo-accesible.md](docs/demo-accesible.md).

**Sin servidor (solo agenda).** Ejecuta `python -m http.server 8000 --bind 127.0.0.1` en la raíz y abre `/app/`. El lector valida `salida/agenda.json` (generada por A) o el ejemplo ficticio contra el contrato antes de pintar la vista.

**Con la agenda de A.**

```bash
python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json
python -m contratos.validar salida/agenda.json    # válido / inválido / incompatible (sin abrir la web)
python -m api publicar salida/agenda.json         # o un directorio C2 con manifiesto.json
```

Cierre mensual completo (A01→A09 → C2 → validación → publicación):

```bash
python -m api cierre --corte 2026-10-31 --datos ../Green_Services_Recursos_de_Prueba
```

## Demostración de los modelos de IA

Con el paquete de práctica junto al clon (o con `JACOMIND_DATOS`) y los modelos ya entrenados y evaluados:

```
python -m modelos.cli resumen-ia                       # resultados de los modelos para la página «Modelos de IA»
python -m api demo --sin-cierre                        # base con identidades ficticias
python -m api cierre --corte 2026-10-31 --datos ../Green_Services_Recursos_de_Prueba   # agenda con el modelo de compra operativo (M1.3 «P»)
python -m api sombra salida/sombra/inactividad_60d_m21/2026-10-31-con-resumen          # lista de prevención (M2.1, experimental)
python -m api sombra salida/sombra/proxima_compra_m31/2026-10-31                       # ventana de próxima compra (M3.1, experimental)
python -m api sombra salida/sombra/venta_cruzada/2026-10-31                            # venta cruzada (M4: popularidad filtrada, experimental)
python -m api sombra salida/sombra/demanda/2026-10                                     # pronóstico de demanda a 1-3 meses (M5, experimental)
python -m api sombra salida/sombra/anomalias_m61/2026-10-31                            # cola de operaciones atípicas (M6.1, experimental)
python -m api monitoreo recalcular                                                     # monitoreo de M1–M6 de lo publicado
python -m api monitoreo resultados --datos salida/a01                                  # desempeño con resultados maduros (los de octubre aún no maduran)
python -m api servir
```

Con un perfil interno, la aplicación muestra:

- **Modelos de IA** (`#/ia`): qué estima cada modelo y cómo se compara con las reglas.
- **Prevención (IA)** (`#/prevencion`): la lista de riesgo de inactividad.
- **Próxima compra (IA)** (`#/proxima`): ventanas de inicio probable y probabilidad de compra a 15, 30 y 60 días.
- **Venta cruzada (IA)** (`#/venta-cruzada`): hasta tres productos complementarios por cliente, con evidencia, compatibilidad por revisar, decisiones de Ventas (aceptar, aplazar o descartar con motivo) y la muestra de revisión comercial.
- **Pronóstico (IA)** (`#/demanda`): proyección a 1, 2 y 3 meses por familia (COP, Finanzas y Gerencia) y por producto (unidades, también Operaciones), con su error histórico y bandas cuando hay soporte.
- **Operaciones atípicas (IA)** (`#/anomalias`): cola de revisión de ventas y compras con valor observado frente a referencia, motivos, soporte, cupo y exceso, historial y decisiones humanas (Operaciones y Finanzas; importe COP solo para Finanzas y Gerencia).
- **Monitoreo (IA)** (`#/monitoreo`): estado de cada modelo (sin información, pendiente de madurez, no comparable, sin problemas, requiere revisión, publicación rechazada), cobertura, madurez, métricas con soporte y avisos con evidencia e historial ([documentación](docs/monitoreo-modelos.md)).
- **Ficha del cliente**: todas las estimaciones juntas (compra a 30 días, riesgo de inactividad, ventana de próxima compra y venta cruzada).

Los resultados vienen de datos sintéticos y son orientativos (ver `docs/modelo-compra.md`, `docs/modelo-inactividad.md`, `docs/modelo-proxima-compra.md`, `docs/modelo-venta-cruzada.md`, `docs/modelo-demanda.md` y `docs/modelo-anomalias.md`). El modelo de compra está operativo en **modo demostración**. Para volver a la versión original:

```
python -m modelos.cli revertir --estado operativo --a v1
```

## Despliegue

Un servidor Amazon Lightsail (Ubuntu 24.04, plan de 7 USD/mes) con Caddy para HTTPS, systemd, respaldo diario y cierre mensual programado. Se instala con un solo comando; ver [docs/despliegue.md](docs/despliegue.md). Lo que falta para la puesta en producción (primer despliegue, CI y CD) está en [PENDIENTES.md](PENDIENTES.md).

## Asistente con modelo de lenguaje (opcional)

El asistente es un chat con memoria que responde sobre el proyecto, analiza los datos del cierre y propone recomendaciones, citando cada dato. Está en `api/agente_chat.py` y es un agente **LangGraph** con el patrón estándar: nodo de modelo con `bind_tools`, `ToolNode`, `tools_condition` y memoria por conversación con `InMemorySaver`. El modelo usa **LangChain**: Gemini como proveedor principal y Anthropic de respaldo (`with_fallbacks`).

- **Herramientas de solo lectura y por perfil.** Cubren cartera, fichas, series de ventas y compras, coberturas, oportunidades, simulador, seguimientos, indicadores de solicitudes, políticas vigentes y la documentación del proyecto (`api/conocimiento.py`). Identidad, empresa y permisos salen de la sesión, y una herramienta no autorizada no se ofrece al modelo.
- **Citas verificables.** Cada herramienta numera sus fuentes y el modelo cita `[n]`. La respuesta incluye las fuentes, los pasos consultados y las cifras que no aparecen en los datos consultados, que se marcan para revisión.
- **Memoria aislada.** El hilo de conversación incluye usuario, empresa y cierre.

```bash
python -m pip install -r requirements-llm.txt
cp .env.example .env   # completa GEMINI_API_KEY y/o ANTHROPIC_API_KEY
```

Sin esas dependencias o claves, o si el modelo no responde, el asistente pasa a **modo básico**: el grafo de reglas de `api/agente.py` (interpretar → aclarar, denegar o ejecutar → redactar → registrar) con plantillas deterministas.

## Estructura del carril B

| Ruta | Contenido |
|---|---|
| `contratos/` | Esquemas C1–C4, validador sin dependencias, reglas de orden y muestras. Ver [contratos/README.md](contratos/README.md) |
| `api/` | Servidor HTTP y API, migraciones SQLite, identidad y permisos, publicación de cierres, consultas, tareas, PQRS, beneficios, documentos/RAG, agente, finanzas y operación |
| `app/` | Interfaz web (HTML/JS sin dependencias): `app.js` (entrada, cabecera y enrutado), `navegacion.js` (áreas del menú según capacidades), `nucleo.js` (sesión, API, preferencias de lectura y formatos), `ui.js` (encabezado, franja Qué/Por qué/Qué hacer, indicadores, estados, diálogo, gráficos con tabla), `preferencias.js`, `vistas/` (una por área) y `fixtures/agenda.json`. Decisiones en `DESIGN.md` y `UX-CONTRACT.md` |
| `tests/app/`, `tests/integracion/` | Pruebas de unidad, de contrato, de la API, del servidor real y de fusión con A |
| `docs/demo.md`, `docs/demo-accesible.md`, `docs/operacion.md` | Guiones de demostración y procedimiento de cierre, respaldo y recuperación |

El carril A escribe en `pipeline/`, `modelos/`, `tests/datos/`, `tests/modelos/` y `docs/ficha-modelo.md`. Los puntos de enganche (generador, importador A01 y clasificador A10) están en [contratos/README.md](contratos/README.md#puntos-de-enganche-en-código-opcionales).

## Pruebas

```bash
python -m unittest discover                                          # carril A (tests/datos, tests/modelos)
python -m unittest discover -s tests/app -t tests/app                # carril B
python -m unittest discover -s tests/integracion -t tests/integracion # servidor real y fusión A+B
```

## Convenciones

- Fechas ISO, importes en COP numéricos, IDs como texto.
- `null` significa «sin dato» y 0 es un valor medido: «Sin historial» y «Modelo no disponible» no equivalen a 0.
- Orden estable de la agenda: acción, probabilidad descendente (nulos al final) e ID.
- `contratos/ejemplos/` se versiona. `salida/` y `var/` no.

## Carga A01 (carril A)

La ingesta, normalización y validación de datos vive en `pipeline/`. Ejecuta la carga sobre el paquete sintético con:

```powershell
uv run --python 3.12 python -m pipeline.cli --datos C:\ruta\Green_Services_Recursos_de_Prueba --salida C:\ruta\salida\a01
```

El comando genera inventario, incidencias y tablas publicadas para el siguiente bloque A02. Los recursos de prueba y los datos empresariales permanecen fuera del repositorio.
