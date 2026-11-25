# JACOMIND · Guía del equipo

Punto de entrada para quien llega al proyecto. Explica qué hace la aplicación, cómo fluyen los datos, qué hace cada modelo de IA y cómo funciona el asistente. El detalle técnico de cada pieza está en los documentos enlazados.

> **Estado al 25 de noviembre de 2026.** Todos los datos son **sintéticos** (paquete de prueba de Green Services). Ninguna métrica de esta guía es un resultado comercial real: la efectividad solo se puede medir con un piloto con datos de la empresa.

## 1. Qué es JACOMIND

Una aplicación web para que Gerencia, Ventas, Operaciones, Finanzas y Atención **entiendan qué pasó en el mes, decidan a quién atender y registren lo que hicieron**. Las empresas cliente tienen además un portal propio para ver sus beneficios y sus solicitudes.

Tiene tres ideas centrales:

1. **El cierre mensual es la fuente de verdad.** Cada mes se publica una versión sellada de los datos (el «cierre»). Todas las pantallas dicen hasta qué fecha llegan sus datos.
2. **La IA sugiere; las personas deciden.** Solo un modelo influye en el trabajo diario (M1). Los demás están **en prueba**: se muestran para revisión, pero no cambian nada por sí solos.
3. **Todo queda registrado.** Seguimientos, decisiones sobre sugerencias, revisiones de casos y respuestas a clientes guardan quién, cuándo y por qué.

**En línea (demo):** https://jacomind-demo.duckdns.org/app/ · Guion de demostración: [demo-accesible.md](demo-accesible.md)

## 2. Arquitectura en una página

```
 Archivos de la empresa            Carril A (pipeline/, modelos/)               Carril B (api/, app/)
 ventas, compras, clientes,  ──▶  A01 carga y calidad ─▶ cierre mensual  ──▶  Publicación sellada (C2) ──▶ Aplicación web
 coberturas, TRM, productos        reglas de agenda (C1)                       SQLite + API HTTP            por perfil
                                   modelo M1 (en uso)                                    ▲
                                   M2…M6 ─────────────▶ publicaciones «en prueba» ───────┘  (no cambian el cierre)
```

| Pieza | Qué hace | Dónde |
| --- | --- | --- |
| **A01 · carga y calidad** | Lee CSV o Excel y separa filas aceptadas, duplicadas y apartadas, con el motivo de cada una. | `pipeline/`, vista *Datos y cierres* |
| **Cierre mensual** | Genera la publicación del mes (agenda, historial, coberturas, series, oportunidades y predicciones de M1), la valida contra el contrato C2 y la publica de forma atómica. Si falla, sigue vigente el cierre anterior. | `python -m api cierre`, `api/publicacion.py` |
| **Contratos** | C1 (agenda) y C2 (publicación) son esquemas JSON. Lo que no los cumple no se publica. | `contratos/` |
| **API** | Servidor HTTP con la biblioteca estándar de Python y SQLite. Los permisos se comprueban en el servidor, no en la pantalla. | `api/servidor.py`, `api/permisos.py` |
| **Aplicación web** | HTML, CSS y JavaScript sin frameworks. Accesible: letra de 18 px, controles de 48 px, ajustes de tamaño y tema. | `app/`, [DESIGN.md](../DESIGN.md), [UX-CONTRACT.md](../UX-CONTRACT.md) |
| **Modelos** | Entrenamiento y evaluación con protocolos fijados antes de ver resultados. La inferencia y la API funcionan **sin** scikit-learn ni statsmodels. | `modelos/`, [plan/modelos](plan/modelos/README.md) |
| **Monitoreo** | Observaciones de salud, distribución, desempeño y revisión humana por modelo, con avisos persistentes. | `api/monitoreo*.py`, [monitoreo-modelos.md](monitoreo-modelos.md) |

### Perfiles y lo que ve cada uno

El menú se genera desde las capacidades de cada perfil (`app/navegacion.js` + `api/permisos.py`):

| Perfil | Inicio | Áreas principales |
| --- | --- | --- |
| Gerencia | Resumen ejecutivo | Todo lo de consulta; reconoce avisos de modelos |
| Ventas | Resumen comercial | Cartera, seguimientos, M1–M4, beneficios |
| Operaciones | «¿Qué necesitas hacer?» | Coberturas, operaciones por revisar, datos y cierres, configuración |
| Finanzas | Resultado del mes | Pronóstico, escenarios del dólar, informes, operaciones por revisar |
| Atención | Solicitudes | Bandeja, beneficios, base de conocimiento |
| Empresa (portal) | Beneficios | Solo su empresa: beneficios, mis solicitudes, asistente |

## 3. Los modelos

### Cómo leer el estado de un modelo

| Estado | Qué significa | Qué hace en la aplicación |
| --- | --- | --- |
| **En uso** | Pasó su evaluación y una persona lo promovió (en la demo: «modo demostración», aprobado solo para datos sintéticos). | Viaja dentro del cierre y **cambia el trabajo**: ordena la cartera, activa acciones y crea seguimientos. |
| **En prueba** (o «en sombra») | Su evaluación fue inconclusa o se conservó el método de referencia. | **Solo se muestra**, con el sello «En prueba». No cambia la cartera, no crea seguimientos ni recordatorios y no envía nada. |

Pasar de prueba a uso **nunca es automático**. Hacen falta tres cosas: una decisión favorable del protocolo, datos reales y la aprobación de una persona (`python -m modelos.cli promover`).

### Resumen

| | Pregunta que responde | Método publicado | Estado | Pantalla |
| --- | --- | --- | --- | --- |
| **M1** | ¿Es probable que el cliente compre en 30 días? | `compra_30d-m13-P`: regresión logística con pesos por antigüedad y ajuste de nivel | **En uso** (modo demostración) | Cartera, ficha del cliente |
| **M2** | ¿Podría llegar a 90 días sin comprar en los próximos 60? | `m21-poisson-180`: ritmo de compra de los últimos 180 días | En prueba | Clientes que podrían dejar de comprar |
| **M3** | ¿Cuándo es probable que vuelva a comprar? | Cox con regularización L2 (supervivencia) | En prueba | Cuándo conviene contactar |
| **M4** | ¿Qué producto que aún no tiene podría interesarle? | Popularidad filtrada por compatibilidad (se conservó la referencia) | En prueba | Productos que podrías ofrecer |
| **M5** | ¿Cuánto se venderá en los próximos 1–3 meses? | Referencias por serie (último mes, promedio de 3 meses) y candidatos SES/Holt; el total es la suma de las familias | En prueba | Pronóstico |
| **M6** | ¿Qué venta o compra se aparta de lo habitual? | M6.1: reglas de catálogo y contexto (mediana/MAD) con un cupo de revisión | En prueba | Operaciones por revisar |

### M1 · Compra en 30 días

- **Qué estima:** la posibilidad de que un cliente con historial compre en los 30 días siguientes a la fecha de los datos.
- **Cómo se usa:** si supera el **40 %**, la acción del cliente pasa a «Revisar oportunidad de recompra». La estimación también ordena la cartera dentro de cada acción.
- **Cómo se calcula:** regresión logística con cuatro variables de recencia y frecuencia. Los cortes recientes pesan más (semivida de 180 días) y el intercepto se ajusta al nivel del último mes con resultado conocido, sin cambiar el orden.
- **Distinciones que muestra la pantalla:** «0 %» (el modelo estimó cero), «Hay compras, pero falta la estimación» (no hay modelo para esa fecha) y «Sin compras registradas».
- **Límites:** frente a la regla «más días sin comprar», los resultados fueron inconclusos con datos sintéticos. Está en uso solo para demostrar el flujo completo.
- **Más:** [modelo-compra.md](modelo-compra.md), [M1.3](modelo-compra-m13.md)

### M2 · Riesgo de inactividad a 60 días

- **Qué estima:** para clientes con 30 a 89 días sin comprar, la probabilidad de llegar a 90 días sin compra en los próximos 60. Sirve para **prevenir**, no para reactivar a quien ya se pausó.
- **Quién queda fuera:** los que ya llevan 90 días o más (reactivación, en la cartera) y los que llevan menos de 30 (riesgo cero por definición).
- **Resultado de la evaluación:** entre los 10 primeros, la regla «más días sin comprar» acierta algo más. La diferencia no es concluyente, así que la regla sigue siendo la referencia.
- **Más:** [modelo-inactividad.md](modelo-inactividad.md)

### M3 · Próxima compra

- **Qué estima:** una **ventana** de inicio probable de la próxima compra. En la demo va del 10 % al 50 % de posibilidad acumulada; **no es una banda del 80 %**.
- **Cómo se muestra:** como barras en el tiempo, con el fin de cobertura (fecha de contrato) marcado aparte. Si un límite no se alcanza en 60 días, no se inventa la fecha.
- **Resultado de la evaluación:** mejora con claridad a la curva de toda la población, pero ninguna ventana del 10 % al 90 % es utilizable en 60 días.
- **Más:** [modelo-proxima-compra.md](modelo-proxima-compra.md)

### M4 · Productos que podrías ofrecer

- **Qué hace:** propone hasta 3 productos que el cliente aún no tiene, con motivo y estado de compatibilidad. El número es un **orden**, no una probabilidad.
- **Resultado de la evaluación:** el modelo aprendido no superó por 5 puntos a la popularidad, así que se publica la popularidad filtrada. La compatibilidad queda «por revisar» porque la empresa aún no ha definido sus reglas.
- **Decisiones:** Ventas puede aceptar, aplazar o descartar con motivo. **Aceptar no es una venta ni envía una oferta.** Además hay una muestra para la evaluación comercial, que no tiene revisiones.
- **Más:** [modelo-venta-cruzada.md](modelo-venta-cruzada.md)

### M5 · Pronóstico de demanda

- **Qué estima:** ventas en pesos por familia y en total (suma de familias), y unidades por producto, a 1, 2 y 3 meses.
- **Cómo se muestra:** la línea continua es lo observado y la discontinua lo estimado. El rango solo aparece donde la publicación lo trae (empírico, sin garantía). El error medio en meses ya conocidos se presenta como error, **no como confianza**.
- **Por qué la línea sale casi plana:** las ventas sintéticas suben y bajan sin tendencia, y los métodos proyectan un nivel. De 42 decisiones (serie × horizonte), 21 conservaron la referencia y solo 1 fue favorable.
- **No confundir:** con la proyección operativa A08 de *Finanzas → Resultado*, que es una regla del cierre y no este modelo.
- **Más:** [modelo-demanda.md](modelo-demanda.md)

### M6 · Operaciones por revisar

- **Qué hace:** arma una cola de ventas y compras cuyo precio o cantidad se aparta de lo habitual para ese producto, con un cupo de revisión por mes.
- **Qué significa una señal:** **no es fraude ni un error confirmado.** Una persona decide si es un error, un cambio legítimo o si falta información. Revisar no cambia importes; una corrección se hace cargando los datos de nuevo.
- **M6.1 frente a M6:** la versión anterior usaba Isolation Forest, que no aportó valor demostrable. M6.1 usa reglas de catálogo y contexto y reduce las señales innecesarias.
- **Revisiones:** no hay ninguna revisión humana, así que la precisión no es estimable.
- **Más:** [modelo-anomalias.md](modelo-anomalias.md)

### Monitoreo de modelos

Cada publicación genera observaciones de cuatro tipos: salud de datos, distribución, desempeño frente a lo que realmente pasó y revisión humana.

**Estados que puede tener un modelo:**

| Estado | Cuándo aparece |
| --- | --- |
| Sin información | No hay observaciones. |
| **Pendiente de madurez** | Todavía no pasó el tiempo para saber si acertó. Es el estado actual de los seis: las estimaciones de octubre se comparan con noviembre. |
| No comparable | Cambió la versión o la política del modelo. |
| Sin problemas detectados | Hay resultados observados y no se activó ninguna regla. Nunca aparece por falta de datos. |
| Requiere revisión | Una regla detectó un cambio o un deterioro. |
| Publicación rechazada | Falló el control de integridad de una publicación. |

- **Reconocer o resolver un aviso** exige un motivo y queda en el historial. Nunca reentrena ni promueve un modelo.
- **Más:** [monitoreo-modelos.md](monitoreo-modelos.md)

## 4. El asistente

Disponible desde el botón «Asistente» de la cabecera. Responde preguntas sobre los datos, los clientes, las políticas y los modelos, y **cita de dónde sale cada dato**.

### Dos modos

| Modo | Cuándo | Cómo funciona |
| --- | --- | --- |
| **Asistente con IA** (agente) | Hay librerías de LangGraph y una clave de Gemini o Anthropic | Un modelo de lenguaje decide qué herramientas consultar. Responde con las cifras que devuelven y cita las fuentes. |
| **Modo básico** | Sin modelo de lenguaje, o si este falla o llega al límite de su cuota | Reglas fijas que reconocen intenciones (un cliente, un mes, una definición, un modelo) y responden con plantillas. La pantalla lo indica siempre. |

- **Proveedores:** Gemini es el principal (`gemini-3.5-flash-lite`, con `gemini-3.1-flash-lite` de respaldo) y Anthropic es opcional. Se configuran con variables en `/etc/jacomind/jacomind.env` (en el servidor) o en `.env` (en local). **Nunca en el repositorio.**
- **Si el proveedor no responde:** por ejemplo, ante un límite de peticiones por minuto, la respuesta sale en modo básico con un aviso, sin error para la persona.

### Herramientas según el perfil

El asistente solo puede usar las herramientas que corresponden a los permisos de la persona (`api/agente_chat.py`). Los permisos los comprueba el servidor.

| Grupo | Herramientas | Quién |
| --- | --- | --- |
| Cartera | `resumen_cartera`, `buscar_clientes`, `ficha_cliente`, `oportunidades_prioritarias`, `seguimientos_pendientes`, `coberturas_por_vencer` | Perfiles internos con acceso a la cartera |
| Finanzas | `ventas_o_compras_por_mes`, `clientes_que_redujeron_compras`, `simular_tipo_de_cambio` | Finanzas y Gerencia |
| Modelos | `riesgo_inactividad` (M2), `proxima_compra` (M3), `venta_cruzada` (M4), `pronostico_demanda` (M5, en pesos solo para Finanzas y Gerencia), `operaciones_atipicas` (M6), `monitoreo_de_modelos`, `resultados_de_modelos` | Los mismos permisos que la pantalla de cada modelo |
| Conocimiento | `buscar_politicas`, `buscar_en_documentacion`, `definicion_de_indicador` | Según el perfil |
| Portal | `mis_solicitudes`, `mis_beneficios`, `buscar_politicas` | Empresa: solo su empresa, nunca datos internos |

### Salvaguardas

- **Fuentes:** cada respuesta enumera las que usó. Las citas a fuentes que no existen se eliminan.
- **Cifras sin respaldo:** si el texto trae un número que no aparece en los datos consultados, se marca «revisa estas cifras».
- **Memoria:** se guarda por conversación y está aislada entre usuarios y empresas.
- **Estimaciones:** las de los modelos en prueba se presentan como experimentales, nunca como hechos.

## 5. Operación y despliegue

| Tema | Resumen | Más |
| --- | --- | --- |
| Servidor | Amazon Lightsail (Ubuntu 24.04, 1 GB, Ohio), Caddy con HTTPS automático, servicio systemd `jacomind` y datos en `/var/lib/jacomind` | [despliegue.md](despliegue.md) |
| CI | GitHub Actions corre las pruebas de aplicación, integración y modelos en cada push | `.github/workflows/ci.yml` |
| CD | Si el CI de `main` pasa, se despliega ese commit con respaldo previo y vuelta atrás automática si no arranca | `.github/workflows/despliegue.yml` |
| Datos de la demo | El despliegue solo actualiza el **código**. La base de la demo se sube aparte (`salida/demo_cliente_2026_11_25/demo.sqlite3`). | [demo-accesible.md](demo-accesible.md) |
| Respaldos | Copia diaria a las 03:30 en el servidor, guardada 30 días | [operacion.md](operacion.md) |

### Trabajar en local

```
python -m api --db salida/demo_cliente_2026_11_25/demo.sqlite3 servir --puerto 8000   # abrir http://127.0.0.1:8000/app/
python -m unittest discover                                         # carril A (datos y modelos)
python -m unittest discover -s tests/app -t tests/app               # carril B (API y aplicación)
python -m unittest discover -s tests/integracion -t tests/integracion
```

## 6. Reglas del proyecto

- **Datos:** no se modifican los datos originales, las ejecuciones históricas ni las publicaciones congeladas para que pase una prueba.
- **Protocolos:** se fijan **antes** de ver los resultados y no se cambian después.
- **Promoción:** ningún modelo se promueve automáticamente.
- **Lo que no se inventa:** etiquetas, revisiones, resultados comerciales, ahorro, ventas recuperadas ni ROI.
- **Controles:** no se desactivan para que algo funcione. Si una publicación falla la integridad, se investiga.
- **Lo que no va al repositorio:** datos de clientes ni claves. El repositorio es **público**.

## 7. Mapa de documentos

| Necesito… | Documento |
| --- | --- |
| Presentar la demo | [demo-accesible.md](demo-accesible.md) |
| Entender las pantallas y el diseño | [DESIGN.md](../DESIGN.md), [UX-CONTRACT.md](../UX-CONTRACT.md), [matriz V01–V31](plan/matriz-v01-v31.md) |
| Detalle de un modelo | Fichas `modelo-*.md` y [plan de modelos](plan/modelos/README.md) |
| Monitoreo e integridad | [monitoreo-modelos.md](monitoreo-modelos.md) |
| Desplegar u operar | [despliegue.md](despliegue.md), [operacion.md](operacion.md) |
| Ficha 360 y reglas de la agenda | [ficha-360.md](ficha-360.md), [ficha-operaciones.md](ficha-operaciones.md) |
