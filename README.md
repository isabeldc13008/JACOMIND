# JACOMIND

[Plan de la hackatón de Green Services para dos personas](PLAN_HACKATON.md)

[Plan de implementación del proyecto completo](PLAN_IMPLEMENTACION.md) · [Tareas de datos y modelos](docs/plan/datos-y-modelos.md) · [Tareas de aplicación y operación](docs/plan/aplicacion-y-operacion.md)

## Carga A01

La ingesta, normalización y validación de datos vive en `pipeline/`. Ejecuta la carga sobre el paquete sintético con:

```powershell
uv run --python 3.12 python -m pipeline.cli --datos C:\ruta\Green_Services_Recursos_de_Prueba --salida C:\ruta\salida\a01
```

El comando genera inventario, incidencias y tablas publicadas para el siguiente bloque A02. Los recursos de prueba y los datos empresariales permanecen fuera del repositorio.
