# Guion de demostración y pruebas por rol

Datos ficticios. Todas las identidades, empresas y cifras de la demo son de práctica.

## Arranque desde un clon limpio

```bash
python --version                 # 3.10 o superior; no hace falta instalar nada
python -m api demo               # migra la base y carga la demo ficticia
python -m api servir --practica  # http://127.0.0.1:8000/app/
```

Sin servidor (solo lectura de archivos, modo B01): `python -m http.server 8000 --bind 127.0.0.1` desde la raíz del clon y abre `http://127.0.0.1:8000/app/`. Elige «Ejemplo de práctica» o «Salida local» de forma explícita.

## Recorrido de la hackatón (≈4 minutos)

1. **Operaciones** (`ops1`): abre la agenda del cierre 2026-10-31. Los indicadores de cabecera son de toda la cartera. Filtra «Revisar cobertura», abre `DEMO02` y explica: cobertura que vence en 20 días, compra reciente y probabilidad de compra 55 %. Vuelve: los filtros se conservan.
2. Muestra `DEMO01`: frecuente **y** frío, con dos motivos (reactivación y cobertura). Muestra `DEMO04`: «Sin historial», distinto de `DEMO05` con «0 %».
3. Busca `CLI999`: «Sin coincidencias»; la ficha directa responde «no encontrado, no se inventa historial».
4. **Ventas** (`ventas1`): Seguimientos con K = 3, abre la primera tarea, asígnala y registra el resultado.
5. **Gerencia** (`ger1`): tablero con ingreso confirmado acumulado y evolución mensual; genera el informe mensual dos veces (misma revisión).
6. **Finanzas** (`fin1`): simulador 2026-10, +8 % → diferencia de 96.000 COP sobre USD 300 a 4.000.
7. **Empresa A** (`cli_a`): beneficios vigentes, radica una PQRS. **Atención** (`aten1`): la clasifica, genera un borrador con fuentes vigentes, lo aprueba. El cliente ve la respuesta publicada.
8. Cierra mostrando cómo regenerar el siguiente cierre (`python -m api cierre --corte ... --datos ...`).

## Tareas observables por rol (B03, B11)

| Rol | Tarea | Resultado esperado | Registrar |
|---|---|---|---|
| Ventas | Explicar por qué `DEMO02` está antes que `DEMO06` | misma acción; probabilidad 55 % > 48 % | tiempo, dudas, si confundió alerta con venta |
| Operaciones | Identificar las coberturas próximas a vencer | `DEMO01` (45 d) y `DEMO02` (20 d); `DEMO06` vencida | tiempo, errores |
| Gerencia | Reconciliar el ingreso del tablero con el cierre | 51.150.000 COP en tablero, agenda e informe | discrepancias |
| Finanzas | Reconstruir la diferencia del escenario +8 % | 96.000 COP | correcciones necesarias |
| Atención | Resolver una PQRS con borrador asistido | respuesta con fuente vigente y aprobador registrado | ediciones al borrador |
| Empresa | Encontrar un beneficio y consultar su caso | solo beneficios y casos de su empresa | tiempo |

Repetir las tareas en las que alguien confundió una alerta con una venta confirmada.

## Pruebas de fallo para enseñar

- Publicar `contratos/ejemplos/agenda/incompatible.json` desde Operación: se rechaza y el cierre activo no cambia.
- Desactivar «Probabilidad de compra» en Operación: la agenda muestra «Modelo no disponible» y mantiene las reglas.
- Retirar `POL-BENEF` en Documentos y repetir la pregunta del portal: el asistente se abstiene y remite a Atención; el borrador pendiente pasa a revisión.
- Consultar como `cli_b` el radicado de `cli_a`: «No existe un caso con ese radicado para tu empresa».
