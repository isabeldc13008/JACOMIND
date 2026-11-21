# Procedimiento de operación del cierre (B11)

Para la persona que ejecutará el siguiente cierre. Todos los comandos se lanzan desde la raíz del clon.

## Entornos y secretos

| Entorno | Base | Identidades | Cómo arrancar |
|---|---|---|---|
| Demo local | `var/jacomind.sqlite3` | ficticias (`python -m api demo`) | `python -m api servir --practica` |
| Ensayo | `JACOMIND_DB=var/ensayo.sqlite3` | ficticias + datos sintéticos | `python -m api servir` |
| Piloto | ruta acordada con Green | proveedor aprobado vía proxy (`JACOMIND_PROXY_AUTH=1`, `--sin-login-demo`) | `python -m api servir --sin-login-demo` |

Los secretos van en `.env` (no se versiona; plantilla en `.env.example`). La retención y el acceso a registros (`auditoria`, `asistente_registro`) se acuerdan con Green. Los datos empresariales nunca se copian al repositorio.

## Cierre mensual

```bash
python -m api cierre --corte 2026-11-30 --datos ../Green_Services_Recursos_de_Prueba
# o, si A ya generó el directorio de publicación:
python -m api cierre --corte 2026-11-30 --desde salida/cierres/<id>
```

1. **Generar.** Ejecuta `python -m pipeline.generar` de A con un ID de ejecución propio. Reintenta hasta `--reintentos` veces ante fallos transitorios.
2. **Validar y publicar.** Comprueba C1/C2, conteos, claves y sumas, y activa el cierre en una transacción. Publicar es idempotente: si los insumos no cambian, no se crea otra revisión. Un contrato inválido no se reintenta.
3. **Regenerar la agenda humana.** Las tareas existentes conservan responsable, aplazamientos y cierres manuales; la evidencia anterior queda guardada.

Si algo falla, la aplicación sigue mostrando el **último cierre válido**. En «Operación» se ven la duración por etapa, los intentos, la frescura (días desde el corte), las filas aisladas en cargas y las versiones de reglas y modelos.

Programación: el mismo comando en el programador del sistema (cron o Programador de tareas de Windows), una vez al mes, después de recibir los insumos. La carga manual desde «Operación → Cargar CSV/Excel» usa la misma validación que la programada.

## Carga manual de archivos

1. Elige periodo, tabla y, en Excel, la hoja. Si las columnas tienen otros nombres, indica el mapeo (`{"Fecha venta": "fecha"}`).
2. Previsualiza: filas leídas = aceptadas + duplicadas idénticas + aisladas (cada fila cuenta una vez aunque tenga varios motivos).
3. Si el lote es bloqueante (faltan columnas, sin filas válidas), corrige el archivo y vuelve a cargarlo. Un reenvío idéntico reutiliza el lote.
4. Confirma: el archivo queda en `var/lotes/<periodo>/` para el cierre.

## Respaldo y restauración

```bash
python -m api respaldo                                   # var/respaldos/jacomind-<fecha>.sqlite3 + manifiesto .json
python -m api restaurar var/respaldos/<archivo>.sqlite3 --destino var/ensayo-restaurado.sqlite3
JACOMIND_DB=var/ensayo-restaurado.sqlite3 python -m api servir --puerto 8001   # verificar en aislado
```

El manifiesto registra versión de la aplicación, del esquema, cierre activo, documentos vigentes, conteos y huella. La restauración verifica la huella y la integridad y compara los conteos. **Punto de recuperación:** las acciones confirmadas antes del respaldo reaparecen; las posteriores (tareas, PQRS, eventos) se pierden y se deben volver a registrar a partir de la auditoría o del sistema de origen. Frecuencia y tiempo de recuperación se acuerdan con Operaciones; registrar el tiempo medido en cada ensayo (`segundos` en la salida de `restaurar`).

## Desactivación independiente

En «Operación → Banderas»:

- **Asistente:** el asistente responde «desactivado»; agenda, fichas, tareas y PQRS siguen operando.
- **Probabilidad de compra:** oculta la probabilidad («Modelo no disponible») y ordena solo por reglas. Las tareas y la evidencia histórica se conservan.

Para retirar una versión de modelo, A publica un cierre sin ella (o con la anterior). La evidencia de cada tarea guarda la versión con la que se generó.

## Pruebas

```bash
python -m unittest discover -s tests/app -t tests/app                 # unidad, contratos y API
python -m unittest discover -s tests/integracion -t tests/integracion # servidor real y fusión con A
python -m contratos.validar salida/agenda.json                        # contrato del productor
```

`tests/integracion/test_int_pipeline_a.py` se activa solo cuando existen `pipeline/` y la carpeta hermana de datos: regenera octubre dos veces, valida C1, comprueba 120 clientes, 1.371 ventas, 41 fríos y el ingreso de referencia, publica y concilia la ficha de la API con la fila de A.

## Simulacros antes del piloto

| Simulacro | Cómo | Resultado esperado |
|---|---|---|
| Carga interrumpida | `publicacion.FALLO_SIMULADO = "mover"` (prueba automatizada) | se conserva el cierre anterior, sin filas temporales |
| Reejecución | repetir `python -m api cierre` con los mismos insumos | «ya_publicado», sin nueva revisión |
| Modelo no disponible | bandera «Probabilidad de compra» desactivada | agenda por reglas |
| Documento retirado | Documentos → Retirar | abstención del asistente, borradores a revisión |
| Sesión caducada | esperar `JACOMIND_SESION_MIN` | 401 y vuelta al inicio de sesión |
| Restauración | `respaldo` → acción posterior → `restaurar` | la acción previa aparece, la posterior no |
