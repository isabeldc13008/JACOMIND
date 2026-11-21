# JOCAMIND · Implementación de la agenda de operaciones

Este documento especifica la primera integración de la agenda. El [plan integral](PLAN_IMPLEMENTACION.md) describe las demás funcionalidades y sus pruebas.

**Decisión para la demo.** Al cierre de octubre, una persona de Operaciones abre la agenda, elige qué cliente revisar con Ventas y puede explicar la decisión con su historial, su cobertura y una estimación de compra a 30 días. Gerencia puede consultar el ingreso confirmado en COP y cuántos clientes requieren revisión. El entregable es una aplicación local que se puede regenerar para otro cierre mensual. [Ficha del reto de Green Services and Solutions SAS](https://estudia-seguimiento.vercel.app/hackaton/retos/2.pdf)

## Qué tomar de cada propuesta

| Propuesta | Qué resuelve en el reto | Decisión para dos personas |
|---|---|---|
| GreenOps AI | Reduce la conciliación manual entre plataformas y permite ver qué se vendió a cada cliente. | Incorporar carga CSV, validaciones, conversión a COP y ficha por cliente. La consulta conversacional y el informe narrativo pueden esperar. |
| GreenPulse AI | Convierte el historial en una decisión de seguimiento medible. El paquete permite entrenar y contrastar un modelo. | Elegirla como núcleo. Usar el horizonte de 30 días del paquete. Un cliente frío merece revisión, aunque su probabilidad de compra sea baja. El abandono definitivo requeriría una etiqueta que el paquete no aporta. |
| GreenForecast AI | Ayuda a Gerencia a explorar compras, ventas y exposición cambiaria. | Usar la TRM de prueba de cada fecha para convertir importes. Dejar el pronóstico por categoría y el simulador para una segunda entrega. Hay 22 meses de historia y las compras a proveedores carecen de trazabilidad hasta cada venta para estimar márgenes reales. |
| Plataforma JOCAMIND | Conecta la segmentación de Ventas, la agenda de Operaciones y los indicadores de Gerencia. | Construir las tres consultas sobre una misma agenda. Empezar con etiquetas explicables de frecuencia y recencia. Evaluar clustering después si produce grupos con acciones distintas. RAG, beneficios y PQRS dependen de documentos, políticas y casos autorizados que faltan en el paquete. |

**Datos de partida.** El paquete de práctica está junto al clon, en `../Green_Services_Recursos_de_Prueba/`. Cada integrante debe poder indicar esa ruta desde su equipo. Contiene 120 clientes, 1.407 ventas, 10 productos, 240 compras a proveedores, 243 instalaciones y 669 tasas sintéticas. La ficha prevé posibles insumos empresariales anonimizados y exige confidencialidad. Usar los datos sintéticos en la demo y mantener los empresariales fuera del repositorio. Quedan para Green la definición comercial de cliente frío, la periodicidad de renovación y el significado de «com».

## Acuerdo de trabajo

**A** se encarga de datos y ML. **B** se encarga de la aplicación y la demo. Son roles intercambiables antes de empezar. Para aprovechar los ejemplos locales, se propone Python 3.10+ con biblioteca estándar para A y HTML/JavaScript servido por HTTP local para B.

| Propiedad de escritura | Rama sugerida | Archivos que puede cambiar |
|---|---|---|
| A · Datos y modelo | `feat/datos-modelo` | `pipeline/`, `tests/datos/`, `docs/ficha-modelo.md`. Su proceso genera `salida/agenda.json` localmente. |
| B · Aplicación e integración | `feat/agenda-demo` | `app/` (incluido `app/fixtures/agenda.json`), `tests/app/`, `docs/demo.md`, `README.md` y `.gitignore`. B excluye `salida/` del control de versiones. |

Ambos parten del mismo commit en clones o directorios de trabajo separados. Este plan fija el contrato inicial. Si hace falta cambiar un campo, quien detecta el problema propone nombre, tipo y ejemplo. Ambos acuerdan el cambio antes de aplicarlo y cada persona modifica solo su lado. B integra los cambios de A primero y después su propia rama. Evitar que ambos regeneren o suban salidas al mismo directorio compartido.

### Contrato que permite empezar por separado

A publica un único JSON UTF-8 por cierre. B construye su vista con el siguiente ejemplo ficticio de **una fila** y el mismo lector que usará con el archivo generado. Desde la raíz del clon, `python -m http.server 8000 --bind 127.0.0.1` servirá tanto `/app/` como `/salida/agenda.json`. El modo de ejemplo debe seleccionarse explícitamente. Si la salida real falta, la pantalla indicará cómo generarla.

```json
{
  "version": 1,
  "corte": "2026-10-31",
  "origen": "sintetico",
  "resumen": {"clientes": 1, "ventas_confirmadas": 2, "ingreso_cop": 180000, "clientes_frios": 1},
  "clientes": [
    {
      "cliente_id": "DEMO01",
      "ultima_compra": "2026-08-02",
      "dias_sin_compra": 90,
      "ventas_confirmadas": 2,
      "ingreso_cop": 180000,
      "productos": ["Producto de ejemplo"],
      "frecuente": false,
      "frio": true,
      "renovaciones_proximas": 1,
      "coberturas_vencidas": 0,
      "prob_compra_30d": 0.42,
      "accion": "Revisar reactivación"
    }
  ]
}
```

Una fila por cliente dado de alta al corte. Fechas ISO, conteos enteros, COP numérico y probabilidad entre 0 y 1. Para clientes sin compras, usar fecha y días `null`, productos vacíos, `frio=false` y probabilidad `null` en la agenda. Mostrar «Sin historial». El modelo de referencia evalúa compra en toda la cohorte elegible, que puede incluir primeras compras. Usar «recompra» en la ficha solo si existe una compra previa.

A asigna una acción por cliente en este orden: **revisar reactivación** si está frío, **revisar cobertura** si tiene una renovación próxima o vencida, **revisar oportunidad de recompra** si la probabilidad alcanza el umbral de validación, **revisar primera compra** si carece de historial y **seguimiento habitual** en los demás casos. Emitir esos cinco textos con inicial mayúscula. B muestra todos los motivos aplicables aunque coincidan y ordena por ese orden de acción, luego por probabilidad descendente (nulos al final) e identificador ascendente. Así se puede explicar por qué una renovación merece atención incluso con una puntuación baja.

## Tablero para dos personas

Cada etapa termina al verificar sus criterios de aceptación. Las dependencias entre personas se concentran en el acuerdo inicial y la prueba de integración. En cada celda se indica qué entregar y cómo comprobarlo.

| Etapa | A · Datos y modelo | B · Aplicación y demo |
|---|---|---|
| Contrato | **A0.** Revisar con B el ejemplo JSON, las prioridades y el corte. Localizar `01_Datos/`, `04_Codigo/` y `05_Validacion/` en el paquete. Listo cuando A puede leer las cabeceras de ventas y clientes. | **B0.** Confirmar el contrato con A, crear su rama y el archivo de ejemplo. Añadir casos de cliente frío y frecuente a la vez, cliente con renovación y cliente sin historial. Listo cuando puede servir y abrir los ejemplos en el navegador. |
| Preparación | **A1 · Integrar** (tras A0). Adaptar `04_Codigo/ejemplo_operaciones.py` en `pipeline/`. Vincular cliente, producto y cobertura por ID. Acumular solo ventas confirmadas hasta el corte. Aplicar cantidad × precio × (1 − descuento/100) y convertir USD con la tasa de esa fecha. Para tasas ausentes, aislar la fila e informar el motivo. Comprobar los totales de referencia indicados abajo. | **B1 · Agenda** (tras B0). Leer el JSON, mostrar corte y origen, buscar por ID, filtrar por acción y abrir la ficha. Mostrar «Sin historial» y «Sin resultados» según corresponda. Listo cuando los tres ejemplos pueden localizarse y el orden es reproducible. |
| Desarrollo | **A2 · Aprendizaje** (tras A1). Reutilizar el entrenamiento de `04_Codigo/modelo_compra.py`. Construir una fila por cliente y fin de mes desde su alta. Variables hasta ese día: días desde la última compra, frecuencias a 30 y 90 días y total histórico. Etiqueta 1 si compra en los 30 días siguientes. Ejecutar el protocolo temporal de abajo y guardar la comparación en la ficha del modelo. | **B2 · Evidencia para decidir** (tras B1). En la ficha, mostrar productos adquiridos, última venta, COP, etiquetas, coberturas y probabilidad. En la cabecera, total de clientes, ventas confirmadas, ingreso y clientes fríos. Listo cuando B puede justificar cada acción con campos del ejemplo y distingue «0 %» de «Sin historial». |
| Intercambio | **A3 · Producir agenda** (tras A1 y A2). Implementar la entrada `python -m pipeline.generar --datos ../Green_Services_Recursos_de_Prueba --corte 2026-10-31 --salida salida/agenda.json`. Aplicar al cierre el mismo cálculo de variables, escalado y pesos. Incorporar las etiquetas y acciones. Entregar a B el comando y el primer JSON completo. | **B3 · Probar el lector** (tras B2). Cubrir versión desconocida, archivo ausente, búsqueda de `CLI999`, filtros vacíos y motivos superpuestos. Dejar lista la lectura de `/salida/agenda.json` y escribir los pasos de demo en el README. Estas pruebas usan el ejemplo aunque A siga entrenando. |
| Integración | **A4 · Verificación** (tras A3). Ejecutar los casos controlados, probar otro corte y repetir el mismo cierre. Comprobar que los IDs son únicos, las cifras se reproducen y las pruebas históricas usan solo información disponible en su fecha. Entregar ficha con métricas, errores y limitaciones. | **B4 · Integración** (requiere A3 y B3). Incorporar la rama de A en el clon de integración y regenerar desde el paquete. Abrir la agenda, contrastar una ficha contra su fila del JSON y los totales contra la referencia. Registrar discrepancias y asignar cada corrección al dueño del archivo. |
| Aceptación | **A5 · Explicar el modelo** (tras A4). Elegir un acierto y un falso positivo del periodo de prueba. Preparar una explicación de lo que gana y pierde el equipo frente a la regla de compra reciente. | **B5 · Ensayar la entrega** (tras B4). Integrar las correcciones y repetir el arranque siguiendo el README. Pedir a otra persona que encuentre un cliente para revisar y explique por qué. Registrar el resultado y ensayar el guion con A. |

## Cómo demostrar el aprendizaje

1. Entrenar la regresión logística con cortes de marzo de 2025 a abril de 2026. Calcular media y desviación solo con entrenamiento. Seleccionar el umbral por F1 en mayo–junio de 2026. Reservar julio–septiembre para una evaluación final. Verificar que la etiqueta del último corte de cada bloque ya se conoce antes de hacer la primera predicción del bloque siguiente.
2. Comparar con la regla «hubo compra confirmada en los últimos 30 días» sobre las mismas filas. Registrar precisión, sensibilidad, F1 y matriz de confusión. Como control de reproducción, el paquete reporta 360 observaciones de prueba, F1 de 0,5594 para la regresión y 0,5368 para la regla. La regresión recupera 120 de 132 compras y genera 177 falsos positivos. La regla recupera 73 y genera 67 falsos positivos. Si Ventas tiene pocas horas de contacto, ese costo cambia la decisión de uso.
3. Puntuar el 31 de octubre únicamente como inferencia. El último corte evaluable del paquete es el 30 de septiembre. La salida histórica `predicciones_prueba.csv` no contiene la agenda de octubre. Para otros cierres, usar un modelo y umbral disponibles en esa fecha o indicar que aún no hay modelo validado y dejar la probabilidad vacía. Los mismos clientes reaparecen por mes, por lo que esta evaluación mide seguimiento de cartera existente.

## Pruebas de aceptación y entrega al jurado

| Prueba | Resultado que se debe observar | Responsable |
|---|---|---|
| Importe y estado | 2 × 100.000 COP con 10 % de descuento da 180.000 COP. 3 × 100 USD a 4.000 da 1.200.000 COP. Una venta anulada aporta cero al ingreso y a la frecuencia. | A |
| Fronteras de negocio | Con los parámetros del paquete, 8 operaciones confirman la etiqueta frecuente, 90 días exactos sin comprar activan frío y un fin de cobertura a 45 días entra en próximas. Un cliente puede ser frecuente y frío. | A calcula, B comprueba la presentación. |
| Conciliación del cierre | A 31 de octubre de 2026, 120 clientes, 1.371 ventas confirmadas, 5.647.449.456,36 COP y 41 clientes fríos. El total se conserva al añadir coberturas. Si se analizan compras a proveedores, agregarlas por separado para evitar multiplicar ventas. | A verifica el archivo, B verifica la pantalla. |
| Ausencia de información | Buscar `CLI999` devuelve cero resultados. Un cliente existente sin compras sí tiene ficha. Si falta el modelo, la pantalla muestra «Estimación no disponible» y conserva las reglas de seguimiento. | B |
| Ausencia de información futura | Añadir una venta posterior a un corte de prueba conserva las variables de ese corte. Si cae en su ventana futura, solo puede cambiar la etiqueta. Ninguna etiqueta de octubre entra al entrenamiento o a las métricas. | A |
| Repetición mensual | Desde el README, generar dos veces el cierre de octubre con los mismos insumos produce la misma agenda. Cambiar a septiembre actualiza la fecha y los indicadores. El archivo opcional con incidencias se prueba por separado. | Ambos, en el clon de integración. |

**Demostración de aceptación.** B plantea la pregunta de Operaciones, abre el cierre y selecciona un cliente que requiera revisión. Muestra lo vendido, el motivo de prioridad y la acción sugerida. A explica qué aprendió el modelo, compara un error real del conjunto de prueba con la regla y distingue la estimación de la fecha contractual. B cierra mostrando cómo regenerar el siguiente informe. La acción final la decide una persona. Presenten las cifras como resultados sobre datos sintéticos. La reducción de tiempo y la recuperación de clientes quedan como indicadores para medir en un piloto autorizado.

**Referencias de trabajo en el paquete.** Las definiciones y supuestos editables están en `02_Documentacion/Diccionario_de_datos.md` y `02_Documentacion/parametros_prueba.json`. Los resultados que sirven de control están en `05_Validacion/Casos_controlados.json`, `Referencia_resumen_prueba.json` y `Referencia_metricas_modelo.json` dentro de esa misma carpeta. Para la presentación pueden adaptar `03_Plantillas/Ficha_modelo.md` y `03_Plantillas/Guion_demostracion.md`.
