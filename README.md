# JACOMIND

[Plan de la hackatón de Green Services para dos personas](PLAN_HACKATON.md)

[Plan de implementación del proyecto completo](PLAN_IMPLEMENTACION.md) · [Tareas de datos y modelos](docs/plan/datos-y-modelos.md) · [Tareas de aplicación y operación](docs/plan/aplicacion-y-operacion.md)

## Arranque rápido

Requiere Python 3.10 o superior. La aplicación y la API usan solo la biblioteca estándar.

```bash
python -m api demo               # crea var/jacomind.sqlite3 con datos ficticios de demostración
python -m api servir --practica  # abre http://127.0.0.1:8000/app/
```

En «Origen y sesión» elige el origen de datos (servidor, salida local o ejemplo de práctica) y una identidad ficticia: `ops1` (Operaciones), `ventas1`, `fin1`, `aten1`, `ger1`, `cli_a` (Empresa A) o `cli_b` (Empresa B). Guion completo: [docs/demo.md](docs/demo.md).

**Sin servidor (solo agenda).** Ejecuta `python -m http.server 8000 --bind 127.0.0.1` en la raíz y abre `/app/`. El lector valida `salida/agenda.json` (generada por A) o el ejemplo ficticio contra el contrato antes de pintar la vista.

**Con la agenda de A.**

```bash
python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json
python -m contratos.validar salida/agenda.json    # válido / inválido / incompatible (sin abrir la web)
python -m api publicar salida/agenda.json         # o un directorio C2 con manifiesto.json
```

## Asistente con modelo de lenguaje (opcional)

Las cifras siempre las calculan herramientas deterministas de solo lectura. El modelo solo redacta, y si añade cifras que no están en el resultado, se descarta su texto. El agente es un grafo **LangGraph** con los nodos interpretar → aclarar, denegar o ejecutar → redactar → registrar. La redacción usa **LangChain**: Gemini como proveedor principal y Anthropic de respaldo (`with_fallbacks`).

```bash
python -m pip install -r requirements-llm.txt
cp .env.example .env   # completa GEMINI_API_KEY y/o ANTHROPIC_API_KEY
```

Sin esas dependencias o claves, el asistente funciona igual con plantillas y ejecuta los mismos nodos en secuencia.

## Estructura del carril B

| Ruta | Contenido |
|---|---|
| `contratos/` | Esquemas C1–C4, validador sin dependencias, reglas de orden y muestras. Ver [contratos/README.md](contratos/README.md) |
| `api/` | Servidor HTTP y API, migraciones SQLite, identidad y permisos, publicación de cierres, consultas, tareas, PQRS, beneficios, documentos/RAG, agente, finanzas y operación |
| `app/` | Interfaz web (HTML/JS sin dependencias) y `fixtures/agenda.json` |
| `tests/app/`, `tests/integracion/` | Pruebas de unidad, de contrato, de la API, del servidor real y de fusión con A |
| `docs/demo.md`, `docs/operacion.md` | Guion por rol y procedimiento de cierre, respaldo y recuperación |

El carril A escribe en `pipeline/`, `modelos/`, `tests/datos/`, `tests/modelos/` y `docs/ficha-modelo.md`. Los puntos de enganche (generador, importador A01 y clasificador A10) están en [contratos/README.md](contratos/README.md#puntos-de-enganche-en-código-opcionales).

## Pruebas

```bash
python -m unittest discover -s tests/app -t tests/app
python -m unittest discover -s tests/integracion -t tests/integracion
```

## Convenciones

- Fechas ISO, importes en COP numéricos, IDs como texto.
- `null` significa «sin dato» y 0 es un valor medido: «Sin historial» y «Modelo no disponible» no equivalen a 0.
- Orden estable de la agenda: acción, probabilidad descendente (nulos al final) e ID.
- `contratos/ejemplos/` se versiona. `salida/` y `var/` no.
