# Ficha de datos A01

## Propósito

La carga A01 recibe el paquete de datos de práctica o una carpeta equivalente y produce tablas normalizadas para A02. Los archivos empresariales deben permanecer fuera del repositorio.

## Ejecución

```powershell
uv run --python 3.12 python -m pipeline.cli `
  --datos C:\ruta\Green_Services_Recursos_de_Prueba `
  --salida C:\ruta\salida\a01
```

También acepta directamente la carpeta `01_Datos`.

Para una fuente con nombres, separador o formato distintos, `--config` acepta un JSON con entradas por tabla. `mapeo` usa la forma `nombre_canonico: nombre_de_fuente`:

```json
{
  "tablas": {
    "ventas": {
      "archivo": "ventas_alternas.csv",
      "delimitador": ";",
      "mapeo": {"venta_id": "id", "fecha": "f"}
    }
  }
}
```

## Tablas

Se cargan en este orden: `clientes`, `productos`, `proveedores`, `trm`, `instalaciones`, `ventas` y `compras`. Los identificadores son texto. Las fechas se convierten a ISO y los importes a `Decimal`; el CSV de incidencias opcional se procesa por separado y nunca se suma a `ventas.csv`.

## Salidas

- `lote_actual/` contiene las tablas aceptadas del intento no publicado.
- `publicado/` conserva la última publicación completamente válida; la promoción usa una carpeta temporal para no perderla ante un fallo.
- `inventario.json` contiene filas leídas, aceptadas, aisladas y duplicadas por tabla.
- `incidencias.jsonl` registra archivo, fila, campo, código, motivo y acción.
- `manifiesto.json` registra el estado del lote.

Estados: `publicable`, `reutilizado` para un reenvío idéntico, `pendiente_revision` cuando hay filas aisladas o duplicadas, y `fallido` cuando falta una tabla obligatoria o no puede leerse. Un lote pendiente o fallido no reemplaza `publicado/`. Cada publicación lleva `revision` y huellas SHA-256; los manifiestos anteriores se agregan a `historial_lotes.jsonl`.

## Códigos principales

`CAMPO_REQUERIDO`, `ERROR_NORMALIZACION`, `REFERENCIA_DESCONOCIDA`, `DUPLICADO_IDENTICO`, `DUPLICADO_CONFLICTIVO`, `MONEDA_NO_ADMITIDA`, `ESTADO_NO_ADMITIDO`, `ARCHIVO_FALTANTE` y `ERROR_LECTURA`.


## Generación del cierre para la aplicación (C1/C2)

```powershell
python -m pipeline.generar --datos ..\Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida\agenda.json
python -m contratos.validar --publicacion salida
```

`pipeline/generar.py` valida el lote (A01; se detiene si es `fallido` o `pendiente_revision`, salvo `--aceptar-parcial`) y lee solo la revisión aceptada. Calcula importes con redondeo por operación (A02), construye la ficha (A03) y puntúa compra a 30 días con la versión operativa registrada en `var/modelos` (o `--registro` / `JACOMIND_MODELOS`). No entrena; sin versión válida, o antes de su disponibilidad simulada (2026-10-30), deja la probabilidad nula con motivo en `predicciones_clientes`. Antes de calcular comprueba la cobertura temporal declarada del lote (`--observado-hasta`, manifiesto A01 o declaración registrada con huellas de origen idénticas): si no alcanza el corte o es desconocida, el cierre termina con error y no escribe tablas, de modo que se conserva la publicación activa; `--sin-cobertura-verificada` publica marcando la cobertura como no verificada y sin estimaciones del modelo. Con el paquete sintético (datos hasta el 2026-10-31) se puede cerrar octubre, pero no noviembre. La publicación se activa con un diario de recuperación: respaldo de la versión visible, huella SHA-256 por tabla en el manifiesto y sustitución del manifiesto al final. Si se interrumpe, el validador rechaza el directorio hasta que se ejecuta `--recuperar` o un nuevo cierre. `--config-a01` permite declarar la cobertura del lote. A01 crea una revisión nueva cuando cambia la declaración de cobertura aunque los CSV sean iguales. Antes del primer cierre se registra la referencia con `python -m modelos.cli preparar` e `inicializar-referencia` (ver [docs/modelo-compra.md](docs/modelo-compra.md)). Después segmenta (A05), genera oportunidades y venta cruzada con soporte (A07), publica series con pronóstico y error por horizonte (A08) y calcula escenarios de TRM de −8 %, 0 % y +8 % (A09). El manifiesto registra huellas de entrada, versiones y calidad.

Resultados del cierre de octubre (comprobación retrospectiva: el corte es anterior a la congelación real del 2026-11-23): 120 clientes, 1.371 ventas, 5.647.449.456,36 COP y 41 fríos. El umbral del modelo es 0,4. En la prueba (julio–septiembre), la regresión obtiene F1 0,5594 frente a 0,5368 de la regla de compra reciente. La venta cruzada por co-ocurrencia empata con la popularidad (11 de 69 aciertos), por lo que no aporta mejora demostrada.
