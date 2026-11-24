# M5 · Pronóstico de demanda (`demanda`)

[Plan](plan/modelos/05-pronostico-demanda.md) · [Base común](plan/modelos/00-base-comun.md) · Protocolo `m5-protocolo-v1` ([configuración](../modelos/config/demanda.json))

**Qué hace.** Prevé la actividad comercial a 1, 2 y 3 meses calendario, con unidad, método y error histórico explícitos.

- **Alcance principal**: ingresos por ventas confirmadas en COP de las cuatro familias, y un total igual a la suma de familias.
- **Alcance adicional**: unidades vendidas por producto.

No es:
- margen;
- demanda de clientes (las compras a proveedores son desembolsos);
- horas equivalentes;
- una orden de compra o contratación;
- una predicción de TRM.

**Resultado (23-11-2026).** Las **referencias se conservan casi en todo**, y no hay un ganador global. De 42 decisiones (14 series × 3 horizontes):

| Decisión | Casos |
|---|---:|
| Referencia conservada | 21 |
| Inconcluso | 14 |
| Rechazado | 6 |
| Candidato con resultado exploratorio favorable | 1 (unidades de PRO10 a 2 meses) |

En las series COP ningún candidato mejora a las referencias con evidencia suficiente. Todo queda en sombra: las `series_mensuales` operativas (A08) no cambian y no se promovió nada.

## Código

| Pieza | Archivo |
|---|---|
| Calendario, conciliación, referencias A08, inferencia desde estados, artefacto de origen, sombra e incorporación de observaciones (biblioteca estándar) | `modelos/demanda.py` |
| Ajuste con statsmodels, reproducción de A08, desarrollo y selección, comprobación, total, bandas y ajuste para un origen nuevo | `modelos/demanda_experimento.py` |
| Protocolo | `modelos/config/demanda.json` |
| Contrato C2 (`pronosticos_demanda`, `calendario_demanda`, `validar_pronosticos`) | `contratos/` |
| API (`/api/demanda`), migración `0005` y vista `#/demanda` («Pronóstico (IA)») | `api/demanda.py`, `app/vistas/demanda.js` |
| Pruebas (14) | `tests/modelos/test_demanda.py` |

**statsmodels 0.15.0** se instaló en el entorno analítico opcional fijando numpy, scipy, scikit-learn y pandas, de modo que M1–M4 no cambian. El cierre, la API y la puntuación no lo cargan, y una prueba con importaciones bloqueadas lo verifica.

## 1. Calendarios, cobertura y conciliación

- **Fuente**: revisión 1 aceptada de A01, con huellas en `datos.json`.
- **Cobertura de ventas**:
  - **inicio declarado** el 2025-01-01, tomado del LEEME del paquete y de la declaración registrada («enero de 2025 a octubre de 2026»), **no deducido de la primera venta**;
  - fin el 2026-10-31, según la declaración del lote.
  - Resultado: **22 meses completos** (enero de 2025 a octubre de 2026).
- **Estados de un mes**:
  - **`completo`**: un mes sin operaciones vale 0; por ejemplo, Soporte de febrero a abril de 2025 y Continuidad en enero de 2025.
  - **`incompleto`**: el mes está cubierto solo en parte, o tiene alguna venta USD sin TRM de su fecha. Su valor es nulo y lleva motivo.
  - **`no_observable`**: meses anteriores a la disponibilidad del producto. Es un proxy por primera venta: PRO02 desde marzo de 2025, PRO05 y PRO07 desde marzo, entre otros.
  - **`sin_cobertura`**: compras a proveedores. **No tienen cobertura declarada propia**: no se usa la de ventas para certificarlas, y quedan en abstención.
- **Convenciones**:
  - las familias se toman del catálogo actual y se aplican a toda la historia, porque el paquete no tiene versiones del catálogo (convención sintética);
  - la unidad de las cantidades no está documentada, y no se suman cantidades de productos distintos.
- **Conciliación con A02** (`_summarize`, importe por operación redondeado a 2 decimales): **88 de 88 meses-familia coinciden**, con diferencia máxima de 0,00 COP y el mismo número de operaciones. Un error de conciliación impediría publicar la serie afectada.
- **Huecos**: solo se usan tramos completos y consecutivos que terminan en el origen. Los ceros nunca se imputan y los meses nulos no se comprimen.

## 2. Reproducción de A08

`control_a08.json` ejecuta la misma función del cierre (`pipeline.generar._series`). Coinciden **exactamente**, en las 4 familias y en el total:
- el histórico;
- la media móvil a 3 meses;
- el MAE de origen creciente: 16, 15 y 14 orígenes desde 6 meses.

Características de A08 que se conservan:
- **Media móvil recursiva**: el horizonte 2 promedia los dos últimos meses y el pronóstico del mes 1. Se reproduce así, sin sustituirla por una media constante.
- **Bandas operativas** (valor ± MAE): describen el error medio. **No son intervalos de predicción con cobertura probabilística.**
- **Inicio del calendario**: A08 empieza en el primer mes con operaciones; M5 usa el inicio declarado. En este paquete coinciden.

## 3. Métodos, ajuste y selección

- **Referencias**: último mes y media móvil de 3 meses (A08). Requieren al menos 6 meses.
- **Candidatos**: suavizamiento exponencial simple y Holt con tendencia aditiva amortiguada, sin estacionalidad. Requieren al menos 12 meses.
- **Ajuste**:
  - inicialización `estimated`, optimización L-BFGS-B con búsqueda inicial;
  - límites: α y β en [0, 1] y φ en [0,8; 0,98];
  - escala: la media absoluta de la historia del propio origen, persistida en el artefacto.
- **Si el ajuste falla**: si no converge o la historia es toda cero, se usa la **media móvil de 3 meses** de forma explícita (campo `sustitucion`).
- **Salida**: se publica el máximo entre 0 y el valor bruto; se conservan ambos y se evalúa el publicado. En esta ejecución no hubo sustituciones ni recortes.
- **Desarrollo** (orígenes con al menos 12 meses y objetivos hasta junio de 2026): las familias COP tienen **6, 5 y 4 comparaciones** por horizonte, y los productos con disponibilidad tardía menos (por ejemplo, PRO05 tiene 4, 3 y 2). Los 504 errores adicionales de las referencias con 6 meses quedan aparte, en `diagnostico_referencias.json`.
- **Selección**: por serie y horizonte, menor MAE de desarrollo. En empate se sigue el orden último, media móvil, SES, Holt. **Se congela antes de la comprobación.**
- **Comprobación**: se reestima el método ya elegido en cada origen y no se vuelve a seleccionar. Las referencias se reconstruyen en los mismos orígenes y objetivos.

| Horizonte | Orígenes | Objetivos |
|---|---|---|
| 1 mes | junio a septiembre de 2026 | julio a octubre |
| 2 meses | junio a agosto | agosto a octubre |
| 3 meses | junio y julio | septiembre y octubre |

## 4. Resultados de las familias COP (comprobación exploratoria; MAE en millones de COP)

| Serie | h | Elegido en desarrollo | MAE de desarrollo (elegido / mejor referencia) | Comprobación: n, MAE elegido / mejor referencia | WAPE | Sesgo normalizado | Decisión |
|---|---|---|---|---|---:|---:|---|
| Continuidad | 1 | último | 4,27 / 4,27 | 4: 3,88 / 3,88 | 0,21 | 0,05 | referencia conservada |
| Continuidad | 2 | último | 7,76 / 7,76 | 3: 4,52 / 4,52 | 0,23 | 0,02 | referencia conservada |
| Continuidad | 3 | SES | 8,05 / 8,07 | 2: 4,62 / 4,21 | 0,23 | 0,09 | inconcluso (2 errores) |
| Servicios | 1 | media móvil 3 | 85,87 | 4: 33,60 | 0,21 | 0,21 | referencia conservada |
| Servicios | 2 | media móvil 3 | 79,32 | 3: 40,66 | 0,26 | 0,26 | referencia conservada |
| Servicios | 3 | media móvil 3 | 73,28 | 2: 63,81 | 0,45 | 0,45 | referencia conservada |
| Software | 1 | media móvil 3 | 6,55 | 4: 12,75 | 0,37 | 0,16 | referencia conservada |
| Software | 2 | SES | 4,87 / 5,09 | 3: 12,41 / 13,61 (−9 %) | 0,35 | 0,16 | inconcluso |
| Software | 3 | SES | 5,55 / 6,11 | 2: 12,60 / 11,89 | 0,46 | 0,46 | inconcluso (2 errores) |
| Soporte | 1 | último | 6,76 | 4: 3,44 | 0,25 | 0,02 | referencia conservada |
| Soporte | 2 | Holt amortiguado | 11,29 / 12,92 | 3: 5,91 / 2,35 | 0,42 | 0,42 | **rechazado** |
| Soporte | 3 | Holt amortiguado | 11,27 / 12,76 | 2: 8,34 / 1,62 | 0,55 | 0,55 | inconcluso (2 errores) |

**Total (suma de familias frente al total real)**, en millones de COP:

| Horizonte | n | MAE | WAPE | Sesgo normalizado | Comparador directo (solo contexto): media móvil / SES |
|---|---:|---:|---:|---:|---|
| 1 mes | 4 | 47,32 | 0,21 | 0,18 | 46,20 / 58,87 |
| 2 meses | 3 | 52,55 | 0,23 | 0,23 | 47,61 / 56,64 |
| 3 meses | 2 | 86,63 | 0,42 | 0,42 | 77,94 / 88,45 |

- El MAE del total se calcula con sus propias predicciones y observaciones agregadas, **no sumando los MAE de las familias**.
- **Unidades por producto**:
  - una decisión favorable exploratoria (PRO10 a 2 meses);
  - 6 «rechazado» (PRO01, PRO02 y PRO09 a 1 mes, PRO03 y PRO04 a 2 meses, además de Soporte COP a 2 meses);
  - el resto, referencias o inconclusos.
  - El detalle completo está en `salida/experimentos/demanda/ejecucion-001/metricas_comprobacion_historica.json` y `decision.json`.
- **Evidencia**: con 2 errores por serie y horizonte no se afirma superioridad; con 3 o 4 el resultado es exploratorio. Las familias y los horizontes están correlacionados y no se tratan como observaciones independientes.

## 5. Bandas: estado real

- **Regla**: cuantiles 10–90 de errores fuera de ajuste **del mismo método, serie y horizonte**, ya observados antes del origen. Se exigen al menos 12 errores y no se mezclan horizontes ni series.
- **Cobertura comprobada**: en cada origen anterior se construye la banda solo con los errores conocidos entonces y se mira si el valor observado cayó dentro.
- **Publicación del 2026-10**: **22 de 45 filas tienen banda**. Todas son de referencias, que acumulan 14 a 16 errores desde orígenes con 6 meses.
  - Coberturas comprobadas: por ejemplo, Servicios a 1 mes 4 de 4, Software a 1 mes 2 de 4, Continuidad a 1 mes 3 de 4 y el total a 1 mes 2 de 4.
  - Con tan pocos casos, la cobertura nominal del 80 % no está garantizada.
- **Sin banda**: los candidatos (8 o 9 errores) y el total a 2 y 3 meses. Quedan con `banda_motivo = historia_insuficiente` y el número de errores disponibles.
- **Total**: su banda sale de los errores del total sumado. Los límites de las familias nunca se suman.

## 6. Publicación, artefacto e incorporación de observaciones

- **Etapas separadas**:
  1. **Selección** (`entrenar`, congelada).
  2. **Reestimación** en el origen (`ajustar-origen --origen 2026-10`): escribe el artefacto JSON con estados finales (nivel, tendencia, φ, escala), parámetros, historia y su huella, selección, MAE, bandas y reglas de salida.
  3. **Emisión** (`puntuar`, sin ajustar nada). Rechaza un artefacto de otro origen o de otra evaluación.
  4. **Incorporación** del valor real (`incorporar-observaciones`): escribe `evaluaciones_<fecha>.json` en otra carpeta **sin modificar el pronóstico**. Con datos hasta octubre, las 45 filas quedan **pendientes**.
- **Equivalencia**: la inferencia desde el estado reproduce statsmodels en los tres horizontes con diferencia relativa 0 (tolerancia 1×10⁻⁸).
- **Sombra** (`salida/sombra/demanda/2026-10`, sello `bad376be…`): 45 filas, con origen 2026-10 y objetivos 2026-11, 2026-12 y 2027-01.
  - Total: 227,7 / 217,5 / 220,7 millones de COP.
  - Por familia, la suma se concilia a 0,01.
- **Contrato C2**, que valida:
  - clave por origen, serie y horizonte;
  - objetivo igual a origen + h meses calendario;
  - valores finitos y no negativos;
  - unidad coherente con la serie;
  - nulos con motivo;
  - bandas ordenadas con al menos 12 errores y método;
  - total igual a la suma de familias, o nulo si falta alguna;
  - concordancia con el manifiesto.
- **Importación**: una publicación de un origen anterior no desplaza a la activa.

## 7. Interfaz y permisos

- **Vista «Pronóstico (IA)»** (`#/demanda`). Distingue:
  - histórico observado;
  - mes incompleto o no observable, mostrado como «sin dato» con motivo y nunca como 0;
  - proyección y resultado pendiente;
  - referencia o candidato, con la decisión por horizonte;
  - error de la misma serie y horizonte, con su número de evaluaciones;
  - banda o «Banda no disponible: historia insuficiente (n errores; se exigen 12)».
- **Permisos**:
  - las series COP solo con `demanda.ver_cop` (Finanzas y Gerencia, como `finanzas.ver`);
  - las unidades también para Operaciones (`demanda.ver_unidades`);
  - Ventas, Atención y el portal reciben 403.
- **Verificado en el navegador**:
  - con datos (total con y sin banda);
  - mes incompleto, sin historia y total incompleto (publicación de prueba claramente etiquetada);
  - error simulado de red;
  - teclado: el foco es visible y se puede elegir la serie y enviarla sin ratón.
- **Anchura reducida**: no se pudo renderizar en el navegador, porque la ventana está maximizada y `frame-ancestors 'none'` impide el iframe. La vista usa `.tabla` (desplazamiento horizontal) y `.filtros`.

## 8. Reproducibilidad y comandos (2026-11-23)

```
python -m modelos.cli preparar-modelo --modelo demanda --config modelos/config/demanda.json --datos salida/a01 --salida salida/experimentos/demanda/preparacion
python -m modelos.cli entrenar --modelo demanda --config modelos/config/demanda.json --datos salida/a01 --salida salida/experimentos/demanda/ejecucion-001   (y -002)
python -m modelos.cli evaluar --ejecucion salida/experimentos/demanda/ejecucion-001   (tres veces, y sobre la 002)
python -m modelos.cli ajustar-origen --config modelos/config/demanda.json --datos salida/a01 --ejecucion salida/experimentos/demanda/ejecucion-001 --origen 2026-10 --salida salida/experimentos/demanda/ejecucion-001/origenes/2026-10
python -m modelos.cli puntuar --modelo demanda --config modelos/config/demanda.json --ejecucion salida/experimentos/demanda/ejecucion-001 --artefacto salida/experimentos/demanda/ejecucion-001/origenes/2026-10/artefacto.json --datos salida/a01 --corte 2026-10-31 --salida salida/sombra/demanda/2026-10
python -m modelos.cli incorporar-observaciones --config modelos/config/demanda.json --datos salida/a01 --publicacion salida/sombra/demanda/2026-10 --salida salida/experimentos/demanda/evaluaciones_emision_2026-10
python -m api sombra salida/sombra/demanda/2026-10
```

- **Reproducibilidad**: las ejecuciones 001 y 002 tienen el mismo sello (`1c47bab9…`) y las mismas decisiones; la evaluación es idempotente y repetir la sombra no cambia nada.
- **Regeneración durante el desarrollo**: el artefacto de origen y la sombra se generaron una primera vez sin la cobertura comprobada de las bandas. Esas salidas, recién creadas y sin consumir, se borraron y se regeneraron con el código final. Las ejecuciones congeladas y evaluadas no se tocaron.
- **Pruebas**: 14. Cubren constante, tendencia y toda cero; mes cero frente a incompleto; hueco; disponibilidad; historia insuficiente; USD y conciliación; compras separadas; pico posterior; horizontes y cambio de año; orígenes idénticos; selección congelada; no convergencia; recorte; denominadores cero; total; bandas y errores futuros; equivalencia; evidencia alterada e interrupción; importación fuera de orden; observaciones que no sobrescriben; permisos; ausencia de dependencias.
- **Suites**: modelos 273 aprobadas; aplicación 139 aprobadas y 1 omitida; integración 10 aprobadas y 1 omitida.
- **Archivos protegidos**: los 442 de M1–M4 están intactos.

## 9. Limitaciones y fuentes pendientes

- Datos sintéticos de 22 meses ya inspeccionados: con 2 a 4 errores por serie y horizonte no hay evidencia estable.
- Las proyecciones COP mezclan volumen, precios y moneda.
- Familias y disponibilidad de productos con convenciones sintéticas.
- Unidades sin unidad de medida documentada.
- **Pendiente de la empresa**:
  - cobertura declarada de compras a proveedores;
  - catálogo con versiones de familia;
  - unidad de medida por producto;
  - para planificación: existencias, plazos de entrega y tiempos de servicio.

## Piloto prospectivo

- **Congelación real**: 2026-11-23.
- **Primer origen prospectivo**: 2026-11, cuando noviembre esté completo y declarado en la cobertura.
- **Cada mes**:
  1. `ajustar-origen` con el mes recién completado;
  2. `puntuar`, guardando el pronóstico antes de observar sus objetivos;
  3. cuando cada objetivo se complete, `incorporar-observaciones`, sin reescribir el pronóstico.
- **Registro**: se conservan la fecha de emisión y el corte de información, y las simulaciones históricas se mantienen separadas de los pronósticos prospectivos.
- **Bandas de candidatos**: se habilitan cuando acumulen 12 errores comparables.

## Monitoreo (24-11-2026)

M5: por universo de unidad (COP y cada producto en su unidad, nunca mezclados); MAE, WAPE, sesgo y cobertura de bandas solo con meses completos, frente a A08 en los mismos objetivos; las series en COP solo para Finanzas y Gerencia. Ver [monitoreo de modelos](monitoreo-modelos.md#b-monitoreo-de-m1m6).
