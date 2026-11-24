# Integridad de ejecuciones M1.1–M1.3 y monitoreo de modelos M1–M6

[Base común](plan/modelos/00-base-comun.md) · [Programa de modelos](plan/modelos/README.md) · Evidencia local: `salida/verificacion_integridad_monitoreo_2026_11_24/` (no versionada)

Este documento separa cuatro cosas que no deben mezclarse:

| Dimensión | Qué cubre | Estado al 24-11-2026 |
|---|---|---|
| **Integridad técnica** | Que una ejecución, una evaluación o una publicación sean las que dicen ser y se puedan recuperar | Corregida y probada (sección A) |
| **Desempeño predictivo** | Lo que miden las evaluaciones y el monitoreo con resultados maduros | Sin cambios: la corrección no altera predicciones ni métricas |
| **Validación comercial** | Revisiones humanas, reglas reales y capacidad acordada | Pendiente de la empresa |
| **Autorización operativa** | Punteros del registro y aprobaciones | Sin cambios: ningún puntero se movió |

Corregir la infraestructura no convierte un candidato inconcluso en un modelo aprobado.

## A. Integridad y recuperación de M1.1, M1.2 y M1.3

### Problemas confirmados

Las pruebas de reproducción contra el código anterior fallaron por la causa esperada; la salida está en `pruebas_antes_de_corregir.txt`.

| Defecto | M1.1 | M1.2 | M1.3 |
|---|---|---|---|
| **A. Artefacto principal desvinculado** | **Sí.** `artefacto.json` no se comparaba con la huella congelada, y `artefacto_huella` estaba fuera del sello. Otro candidato válido, o un artefacto de otra ejecución, se evaluaba y quedaba registrado en la decisión, así que `promover` lo habría aceptado. | No (ya se verificaba) | No hay artefacto principal; cada candidato se verificaba |
| **B. Evidencia sin proteger** | `seleccion.json`, `predicciones_validacion_temporal.csv`, `cortes_entrenamiento_final` (define la referencia «constante», que entra en el criterio de Brier) y `fechas` | **`desarrollo.json`**: la diferencia y el IC deciden el resultado; alterarlo cambiaba la decisión. También `cortes_entrenamiento_final`. | **`desarrollo.json`** (decide S y P) y `cortes_entrenamiento_final` |
| **C. Recuperación incompleta** | Una interrupción después de las métricas hacía fallar el reintento con `FileNotFoundError` | Igual | Igual |

Además, la escritura no era atómica. Con métricas ausentes y la decisión ya escrita, el reintento reescribía la decisión con otra fecha; la prueba solo pasaba si caía en el mismo segundo.

### Cambio realizado

Hay un mecanismo único en `modelos/compra_m1_ejecucion.py`, que reutiliza `modelos/ejecucion.py` (`publicar_lote` y `verificar_lote`); no son tres implementaciones independientes.

- **Formato de congelación 3** (ejecuciones nuevas). El marcador `congelacion.json` sella:
  - modelo y variante;
  - protocolo (versión y huella);
  - huella y revisión de los datos;
  - artefactos (principal y por papel o candidato) y referencias;
  - cortes de entrenamiento final y bloques;
  - fechas de disponibilidad simulada;
  - equivalencia JSON ↔ scikit-learn;
  - SHA-256 del código que entrena y evalúa;
  - la huella SHA-256 de cada archivo obligatorio.
- **Archivos obligatorios por variante** (los que consume cada evaluador; no se añadió ningún archivo irrelevante):

| Variante | Archivos fijos | Además |
|---|---|---|
| M1.1 | `config.json`, `protocolo.json`, `datos.json`, `entorno.json`, `seleccion.json`, `artefacto.json`, `predicciones_validacion_temporal.csv` | `artefacto_<papel>_<calibrado\|sin_calibrar>.json`, `referencia_*.json` |
| M1.2 | `config.json`, `protocolo.json`, `datos.json`, `entorno.json`, `desarrollo.json`, `artefacto.json` | `referencia_*.json` |
| M1.3 | `config.json`, `protocolo.json`, `datos.json`, `entorno.json`, `desarrollo.json` | `artefacto_<candidato>.json`, `referencia_*.json` |

- **Campos volátiles** (fuera del sello, documentados): fecha real de congelación, primer corte prospectivo y su maduración, y fecha real de la primera evaluación. No influyen en la selección, el artefacto, los periodos, la decisión ni la promoción; la prueba `test_c_otros_datos_y_marcador_de_congelacion_manipulado` lo comprueba.
- **Coherencia, además de huellas:**
  - el candidato seleccionado existe;
  - su huella coincide con `artefacto.json` y con el sello;
  - `seleccion.json` nombra el mismo candidato;
  - los artefactos son de `compra_30d` a 30 días;
  - `protocolo.json`, `config.json` y `datos.json` corresponden al protocolo y a los datos congelados;
  - la evaluación exige la misma huella de datos.
- **Evaluación.** Métricas y decisión se escriben de forma atómica y el marcador `evaluacion.json` se escribe al final. Liga el sello de la congelación, la huella de datos, el protocolo y los artefactos, y la decisión repite esos vínculos.
- **Reintento:**
  - conserva lo idéntico y completa lo que falta;
  - rechaza lo distinto;
  - conserva la primera fecha de evaluación;
  - no vuelve a seleccionar ni a entrenar.
- **Consumo:** `compra_m1_ejecucion.evaluacion_publicada` rechaza una evaluación incompleta o desvinculada. La usan:
  - `promover`: para M1.3 exige `--candidato`;
  - el resumen «Modelos de IA».

  Entrenar no requiere evaluación. Evaluar requiere una congelación válida. Promover exige además los criterios y autorizaciones existentes del registro, sin cambios.

Los hashes prueban integridad respecto del marcador. **No son una firma de autenticidad** frente a alguien que pueda reemplazar todos los archivos y el marcador.

### Política para ejecuciones antiguas (formato 2)

- No se resellan ni se modifican. Sus huellas antes y después están en `huellas_historicas.json`.
- Se verifica todo lo que su formato permite:
  - sello parcial y protocolo;
  - artefactos por papel y referencias;
  - en M1.1, además, que `artefacto.json` sea el candidato global sellado, lo que ya detecta la sustitución.
- Se declara lo que no puede verificarse (`verificacion.no_verificable`). En M1.2 y M1.3, por ejemplo, `desarrollo.json`, que decide la comparación.
- Siguen legibles (`leer_evaluacion`; el resumen «Modelos de IA» de M1.3 se lee así), pero **no se pueden volver a evaluar ni promover** con `promover`.
- La versión operativa vigente (M1.3 «P» en modo demostración) se registró con `promover-demo` y no depende de esa ejecución. No se tocó.
- Para una evaluación verificable se **reproduce en una ejecución nueva**, como se hizo en la carpeta de evidencia. Una reproducción histórica no es una prueba prospectiva.

### Evidencia

- Reproducción en carpeta nueva (`salida/verificacion_integridad_monitoreo_2026_11_24/m11|m12|m13/ejecucion`). Frente al código anterior y a las ejecuciones históricas, en las tres variantes (`comparacion_antes_despues.json`):
  - **los artefactos son idénticos;**
  - **las métricas son idénticas** (sin campos de fecha);
  - **el resultado de la decisión es idéntico.**

  Solo cambian los metadatos: se añaden `sello_congelacion`, `huella_datos` y `variante`, y sale `decidido_en`, que ahora es volátil en el marcador. **La corrección no cambió ninguna predicción.**
- Dos reproducciones del mismo protocolo solo difieren en `protocolo.json`, que lleva la fecha real en que se registró el protocolo antes de ajustar.
- Pruebas `tests/modelos/test_m1_integridad.py` (12):
  - artefacto sustituido por otro candidato o por uno de otra ejecución;
  - selección, evidencia de desarrollo o cortes alterados;
  - interrupción tras las métricas y tras la decisión;
  - reintento idéntico;
  - decisión sin métricas y marcador ausente;
  - archivo publicado alterado y resultado distinto sin marcador;
  - otros datos;
  - marcador manipulado, distinguiendo campo volátil de campo sellado;
  - formato antiguo;
  - promoción;
  - reproducción en carpeta nueva.

## B. Monitoreo de M1–M6

### Esquema (`jacomind.monitoreo.v1`, reglas `monitoreo-reglas-v1`)

Cada observación es inmutable y lleva:

- modelo, variante y versión del artefacto;
- origen: cierre, publicación en sombra, resultados o revisión, con su id y su sello;
- corte y periodo;
- universo;
- grupo;
- huella de datos;
- política y su versión;
- conteos y métricas `{valor, numerador, denominador, soporte, motivo, unidad, referencia}`;
- madurez (`no_aplica | pendiente | parcial | madura`);
- motivos;
- restricción de acceso (`cop | unidades`).

Una métrica desconocida es `null` con motivo, nunca cero. Las publicaciones antiguas sin bloque de monitoreo siguen siendo válidas; si no traen predicciones, el modelo muestra «sin información» y no se reconstruye nada.

| Grupo | Contenido | Interpretación |
|---|---|---|
| A. `salud` | Elegibles, puntuados, abstenciones, cobertura, excluidas | Datos y publicación |
| B. `distribucion` | Cuantiles de probabilidad o rareza, tasas de alerta, concentración | **Un cambio no demuestra deterioro predictivo** |
| C. `desempeno` | Métricas con resultados observados | Solo con madurez suficiente |
| D. `revision` | Resultados de revisión humana | Precisión comercial solo con revisiones |

Persistencia (migración `0007_monitoreo.sql`):

- `monitoreo_observaciones`: id = SHA-256 del contenido, más la clave lógica `modelo|variante|origen|grupo|universo|periodo`;
- `avisos_modelos`, ampliada con regla, versión, observación, universo, periodo, restricción y estado;
- `avisos_eventos`: historial.

Comportamiento:

- La misma observación no se duplica.
- Una corrección (mismo origen y clave lógica con contenido distinto) crea otra enlazada (`anterior_id` / `reemplazada_por`) y conserva ambas.
- Una publicación antigua importada sin activar queda con `vigente = 0`: no es referencia de comparación ni genera avisos.

### Métricas por modelo

| Modelo | Salud y distribución (al publicar o importar) | Desempeño (`python -m api monitoreo resultados`) |
|---|---|---|
| M1 `compra_30d` (cierres operativos) | Elegibles, estimados, abstenciones por estado, cobertura, cuantiles de probabilidad, tasa sobre el umbral | Madura si la cobertura declarada alcanza corte + 30. Brier, tasa observada y probabilidad media; precisión al cupo 10 frente a **mayor recencia** en el mismo universo y corte |
| M2 `inactividad_60d` | Elegibles, estimados, **estructurales** y fuera de población por separado; la cobertura cuenta estimados + estructurales, porque un estado estructural no es un fallo | A 60 días: Brier sobre estimados, precisión al cupo frente a recencia; estructurales contados aparte |
| M3 `proxima_compra` | Cobertura de probabilidades a 15, 30 y 60 días, ventanas utilizables y parciales o no estimables | **Un resultado por horizonte**, solo si ha madurado; los inmaduros quedan pendientes (censurados, nunca «no compró»). Cobertura de la ventana p10–p50 solo entre ventanas ya observables |
| M4 `venta_cruzada` | Elegibles, con candidatos y con recomendaciones; compatibilidad confirmada, pendiente o incompatible; soporte y concentración por producto. Revisión comercial: evaluables, pertinentes, descartadas e insuficientes | HitRate@1 y @3 a 60 días como **exposición y compra posterior, sin atribución causal** |
| M5 `demanda` | Por universo de unidad (`ventas_cop`, `ventas_cop_total`, `compras_cop`, `ventas_unidades:<producto>`): esperadas, estimadas, abstenciones por motivo y cobertura de bandas | Por universo: error firmado y absoluto, **MAE, WAPE y sesgo solo con meses completos**, cobertura empírica de bandas y MAE de la referencia A08 en los mismos orígenes y objetivos. COP y unidades nunca se mezclan; cada producto va en su unidad |
| M6 `anomalias` | Por universo venta o compra: válidas, puntuadas, excluidas, cobertura temporal; alertas por 100, cupo, exceso y cuantiles de rareza. Revisión: casos, pendientes, por estado, precisión entre alertas revisadas y falsas alertas por 100 normales | Solo por revisión humana; sin revisiones, nulo con motivo |

M6 conserva su comportamiento: las mismas claves y tipos de aviso, y la cola y las revisiones sin cambios. Ahora usa el motor común, que además marca como **no comparable** el paso de M6 a M6.1, porque cambió la política.

### Reglas, madurez y comparabilidad

Las reglas son **iniciales**, tomadas de la base común; no son políticas aprobadas. Están en `modelos/config/monitoreo.json`.

- **Madurez.** Exige que la cobertura **declarada** de los datos alcance corte + horizonte; el paso del calendario no basta. En M5, el mes objetivo debe estar completo.
- **Comparables.** Dos observaciones lo son si coinciden la versión de reglas (que define las métricas), el modelo, el grupo y el universo, la política y su versión, y lo declarado en `comparacion` (horizonte, cupo, referencia y unidad).
  - La referencia es la observación vigente anterior de **otro** origen, con corte menor o igual: una publicación que sustituye a otra del mismo corte se compara con ella.
  - Si la clave cambió, se registra un aviso **informativo** `cambio_politica` y **no se compara**. Por eso no se declara deterioro por cambiar de cupo, filtro, catálogo o definición de etiqueta.
- **`caida_cobertura`:** 100 · (cobertura previa − actual) ≥ 10 pp. Cubre el paso de 100 % a 0 %.
- **`sin_registros`:** con 0 elegibles, la cobertura es nula con motivo (nunca 0 % ni 100 %) y se genera el aviso.
- **`cambio_tasa_alertas`:**
  - r = |a − b| / b ≥ 0,5 si b > 0, con ≥ 30 operaciones en ambos periodos;
  - si b = 0 y hay al menos 1 alerta: aviso «desde cero» (r no definido);
  - 0 → 0: sin cambio;
  - una tasa positiva que pasa a 0 da r = 1.
- **`deterioro_frente_referencia`:**
  - d = (x − r)/|r| si la dirección favorable es «menor» (Brier, log loss, MAE, WAPE);
  - d = (r − x)/|r| si es «mayor» (precisión al cupo, HitRate);
  - si r = 0: d = 0 cuando x = r y, en otro caso, no estimable (`referencia_cero`, sin aviso);
  - valores ausentes: d nulo con motivo;
  - hay aviso si d > 0,20 con soporte ≥ 30 **en dos cortes maduros consecutivos**: el actual y la observación madura comparable inmediatamente anterior. Un corte inmaduro intermedio impide la comparación.
- **`integridad`:** una publicación que no cumple sello, huellas o contrato se **rechaza, no se importa** y deja un aviso. Bloquea solo esa publicación.

Ningún aviso promueve, revierte ni reentrena modelos; la prueba comprueba que el monitoreo no importa ni llama al registro.

### Estado visible por modelo

| Estado | Cuándo |
|---|---|
| Sin información | Sin observaciones, o desempeño maduro sin nada estimable (p. ej. todo en abstención) |
| Pendiente de madurez | El desempeño de la **última** publicación aún no maduró |
| No comparable | La última publicación cambió de política o versión |
| Sin problemas detectados | Desempeño maduro y estimable de la última publicación, sin avisos activos. Nunca sin observaciones suficientes |
| Requiere revisión | Algún aviso estadístico activo o reconocido |
| Publicación rechazada | Algún aviso de integridad activo o reconocido |

Reconocer un aviso significa que alguien lo está revisando; **no lo resuelve**. Ambas acciones exigen permiso y motivo, quedan en el historial y conservan el aviso original.

### Integración

| Punto real | Qué observa |
|---|---|
| `api/publicacion.publicar`: cierres C1/C2 que usan M1, incluido `python -m api cierre` | Salud y distribución de M1. Un rechazo de contrato genera aviso de integridad |
| `importar_sombra` de M2/M3 (`api/prevencion.py`), M4, M5 y M6 | Salud, distribución y revisión. Un rechazo genera aviso de integridad |
| `venta_cruzada.registrar_revision` y `anomalias.revisar` | Revisión humana (grupo D) |
| `python -m api monitoreo resultados --datos <A01>` | Desempeño con resultados maduros. Idempotente |
| `python -m api monitoreo recalcular` | Salud, distribución y revisión de lo ya publicado. Idempotente |

La API **solo lee lo persistido**: no calcula métricas retrospectivas dentro de una consulta. Un fallo del cálculo de monitoreo se audita y no anula una publicación válida.

### API, interfaz y permisos

Rutas:

- `GET /api/monitoreo`, con filtros `modelo`, `variante`, `periodo`, `estado`, `severidad` y `tipo`;
- `GET /api/monitoreo/aviso?clave=`: evidencia, observación, regla e historial;
- `POST /api/monitoreo/aviso`: `{clave, accion: reconocido|resuelto, motivo}`;
- `GET /api/monitoreo/exportar.csv`.

La vista `#/monitoreo` (menú «Monitoreo (IA)») muestra los seis estados de forma distinguible, la última publicación, la cobertura y las abstenciones, la madurez, las métricas con su soporte y referencia, y los avisos con su evidencia e historial.

Permisos, comprobados en el servidor:

- `monitoreo.ver`: Operaciones, Finanzas y Gerencia. Además, cada modelo exige **su propio** permiso de consulta (`cartera.ver`, `prevencion.ver`, `proxima.ver`, `venta_cruzada.ver`, `demanda.*` o `anomalias.ver`). Así, un panel global no abre acceso indirecto: Finanzas solo ve M5 y M6.
- Las series de M5 en COP solo se muestran con `demanda.ver_cop`, también en el detalle de avisos y en el CSV.
- `monitoreo.reconocer`: Operaciones y Gerencia.
- Ventas, Atención y el portal empresarial reciben 403.

### Procedimiento para investigar un aviso

1. Abre el aviso en `#/monitoreo` y revisa su evidencia: valores, soporte, regla, versión y observación de origen.
2. **Integridad:** compara el sello y las huellas de la publicación. Corrige en el flujo de datos o vuelve a puntuar en una carpeta nueva, reimporta y resuelve el aviso con su motivo.
3. **Caída de cobertura o periodo sin registros:** revisa la carga A01 (cobertura declarada, exclusiones) y la historia disponible antes de interpretar el modelo.
4. **Cambio de tasa de alertas o de distribución:** comprueba antes cambios de cupo, catálogo o política. No es deterioro sin revisiones comparables.
5. **Deterioro frente a la referencia:** confirma la madurez, el soporte y la comparabilidad de los dos cortes. Cualquier decisión (nueva versión, sombra, reversión) es humana y pasa por el registro con sus autorizaciones.
6. **Reconocer** mientras se investiga. **Resolver** solo cuando el problema esté corregido o explicado.

### Comandos reproducibles

```
python -m unittest tests.modelos.test_m1_integridad tests.modelos.test_monitoreo
python -m modelos.cli m11-entrenar --datos salida/a01 --salida <carpeta_nueva>/m11   # ídem m12, m13
python -m modelos.cli m11-evaluar --ejecucion <carpeta_nueva>/m11
python -m modelos.cli promover --ejecucion <ejecución_M1.3> --candidato P --version <v> --estado sombra   # solo con evaluación verificada (no se ejecutó)
python -m api monitoreo recalcular
python -m api monitoreo resultados --datos salida/a01
python -m api monitoreo estado
```

La evidencia completa, con base aislada, cierres de agosto y septiembre, sombras históricas, resultados maduros, el aviso de integridad generado con una copia alterada identificada como prueba y la vista en el navegador, está en `salida/verificacion_integridad_monitoreo_2026_11_24/LEEME.md`.

### Resultados observados en la evidencia

Base aislada; son reconstrucciones históricas, no resultados prospectivos.

- **M1:** los cierres de agosto y septiembre se abstuvieron con `modelo_no_disponible`, porque la versión operativa se habilitó después y no se usan datos futuros. Los resultados maduros no son estimables (soporte 0) y el estado es «sin información».
- **M2.1 (corte 31-08):**
  - Brier 0,245 sobre 30 estimados;
  - precisión al cupo 0,60, igual que mayor recencia.
- **M3.1 (corte 31-08):**
  - Brier 0,194, 0,223 y 0,259 a 15, 30 y 60 días;
  - cobertura de la ventana p10–p50 del 44,9 % (69 ventanas).
- **M4 (corte 31-08):** HitRate@1 10,2 % y @3 23,7 % sobre 118 clientes, como compra posterior y no atribución.
- **M5:** ningún mes objetivo está completo todavía, así que queda pendiente. No admite una reconstrucción anterior, porque la cobertura declarada no puede ser anterior a ventas ya presentes en el lote. Su cálculo maduro está probado con datos de prueba identificados.
- **M6:** «no comparable» frente a M6.1, por el cambio de política.

### Pendientes empresariales

Están separados y no se inventan:

- revisión comercial de M4;
- revisión humana de M6;
- reglas reales de compatibilidad;
- unidades y cobertura de compras;
- capacidad de revisión acordada;
- nuevos periodos para evaluación prospectiva;
- umbrales de monitoreo aprobados (los actuales son iniciales).

Los mecanismos para incorporar cada uno ya existen: revisiones en la aplicación, `compatibilidad_productos.json`, configuración de unidades y cobertura, cupos en los protocolos y `monitoreo resultados` con nuevos lotes A01.
