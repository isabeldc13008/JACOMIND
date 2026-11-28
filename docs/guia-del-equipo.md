# JACOMIND · Guía del equipo

Esta guía explica qué hace JACOMIND, cómo funciona por dentro, qué hace cada modelo de inteligencia artificial (IA) y cómo funciona el asistente.

**Está escrita para todo el equipo, no solo para quien programa.** La **Parte 1** usa lenguaje cotidiano y no requiere conocimientos técnicos. La **Parte 2** reúne el detalle técnico para quien mantiene el sistema. Si una palabra no es clara, búscala en el [glosario](#6-glosario-palabras-que-vas-a-encontrar).

> **Importante.** Todos los datos actuales son **de práctica** (sintéticos): no corresponden a clientes reales. Las cifras de esta guía describen cómo se comportan los modelos con esos datos; **no son resultados comerciales**. Para saber si ayudan a vender más hace falta una prueba piloto con datos reales de la empresa.

## Parte 1 · Para todo el equipo

## 1. Qué es JACOMIND, en pocas palabras

JACOMIND es una aplicación web que ayuda a cada área de la empresa a responder tres preguntas cada mes:

1. **¿Qué pasó?** Cuánto se vendió, qué cambió y dónde.
2. **¿A quién debemos atender?** Qué clientes necesitan una llamada, una renovación o una propuesta, y por qué.
3. **¿Qué hicimos?** Qué contacto se hizo, con qué resultado y quién lo hizo.

Además, las **empresas cliente** tienen un portal propio para ver sus beneficios y seguir sus solicitudes.

Tres ideas guían todo el diseño:

- **Una sola versión de los datos por mes.** Cada mes se publica el «cierre»: una foto oficial y verificada de la información. Todas las pantallas dicen hasta qué fecha llegan sus datos.
- **La IA sugiere; las personas deciden.** Los seis modelos están **en uso**: estiman, sugieren y alertan para que una persona decida. Ninguno actúa por sí solo.
- **Todo queda registrado.** Cada decisión guarda quién la tomó, cuándo y por qué.

**Ver la demo:** https://jacomind-demo.duckdns.org/app/ · Para presentarla a un cliente: [guion de demostración](demo-accesible.md).

## 2. Cómo funciona un mes

```pasos
Llegan los archivos | Ventas, compras, clientes, coberturas y tipo de cambio, en CSV o Excel.
Se revisa su calidad | Se apartan las filas con errores o duplicadas y se explica el motivo de cada una.
Se publica el cierre | Una foto oficial del mes. Si algo falla, la gente sigue viendo el cierre anterior.
Los modelos estiman | Calculan posibilidades, ventanas de tiempo, sugerencias y alertas para cada pantalla.
Las personas deciden | Ventas, Operaciones y Atención revisan, actúan y registran lo que hicieron.
```

Así, cuando alguien abre JACOMIND, todo lo que ve viene del mismo cierre. Las estimaciones de la IA siempre aparecen marcadas como tales.

## 3. Qué ve cada persona

Cada persona entra con su perfil y solo ve lo que le corresponde. Los permisos los controla el servidor, no solo la pantalla.

| Perfil | Al entrar ve… | Para qué le sirve |
| --- | --- | --- |
| **Gerencia** | El resumen ejecutivo | Entender las ventas del mes, dónde cambiaron y qué necesita atención. |
| **Ventas** | El resumen comercial | Saber a qué clientes llamar primero, por qué y con qué propuesta. |
| **Operaciones** | «¿Qué necesitas hacer?» | Atender coberturas que vencen, revisar operaciones raras y preparar el cierre. |
| **Finanzas** | El resultado del mes | Ver ventas y compras, el pronóstico, escenarios del dólar e informes. |
| **Atención** | Las solicitudes de clientes | Clasificar, preparar y publicar respuestas con base en las políticas. |
| **Empresa cliente** | Sus beneficios | Pedir un beneficio o seguir sus solicitudes. Nunca ve datos de otras empresas. |

Este es el reparto de la cartera al 31 de octubre de 2026 (120 clientes de práctica): lo primero que ve Ventas.

```barras
titulo: ¿Qué necesita cada cliente? (120 clientes, datos al 31 de octubre de 2026)
unidad: clientes
Revisar cobertura: 64
Revisar reactivación: 41
Seguimiento habitual: 12
Revisar oportunidad de recompra: 3
nota: Cada cliente aparece una sola vez, en su acción más urgente. Datos de práctica.
```

## 4. Los modelos de IA, explicados con sencillez

Un **modelo** es un cálculo que aprende de las compras pasadas para **estimar** algo que todavía no ha ocurrido. Una estimación no es un hecho: es una posibilidad, y puede equivocarse.

### Todos en uso

```tarjetas
En uso | Compra en 30 días (M1) | Ordena la cartera y activa la acción «Revisar oportunidad de recompra». En esta demo funciona con datos de práctica.
En uso | Los otros cinco modelos (M2 a M6) | Funcionan en sus pantallas: prevención, cuándo contactar, productos que ofrecer, pronóstico y operaciones por revisar. Sus resultados apoyan a una persona, que decide qué hacer.
```

**¿Qué significa «en uso»?** Que el modelo funciona y alimenta su pantalla. Cada uno se sigue comparando con una regla sencilla (por ejemplo, «llamar primero a quien lleva más días sin comprar») y el resultado de esa comparación se muestra en «Modelos y monitoreo». Las estimaciones pueden equivocarse: por eso la decisión final siempre es de una persona.

### Qué responde cada uno

```tarjetas
En uso | M1 · ¿Comprará pronto? | Estima la posibilidad de que un cliente compre en los próximos 30 días. Si supera el 40 %, se sugiere revisar una recompra. Pantalla: Cartera y ficha del cliente.
En uso | M2 · ¿Podría dejar de comprar? | Avisa qué clientes que todavía compran podrían llegar a 90 días sin comprar. Sirve para prevenir antes de perderlos. Pantalla: Clientes que podrían dejar de comprar.
En uso | M3 · ¿Cuándo conviene contactar? | Indica una ventana de fechas en la que es probable que el cliente vuelva a comprar. Es una estimación, no una fecha de contrato. Pantalla: Cuándo conviene contactar.
En uso | M4 · ¿Qué más podríamos ofrecer? | Propone hasta tres productos que el cliente aún no tiene, con el motivo. Aceptar una sugerencia no es una venta. Pantalla: Productos que podrías ofrecer.
En uso | M5 · ¿Cuánto venderemos? | Proyecta las ventas de los próximos 1 a 3 meses, con el margen de error de meses anteriores. Pantalla: Pronóstico.
En uso | M6 · ¿Hay algo raro? | Señala ventas o compras con precios o cantidades muy distintos a lo habitual. Una señal no es fraude ni un error confirmado: alguien debe revisarla. Pantalla: Operaciones por revisar.
```

### Qué tan bien funcionan hoy

Cada modelo se comparó con una regla sencilla, usando meses pasados de los datos de práctica. Estos gráficos muestran el resultado con honestidad: en varios casos la regla sencilla funcionó igual o mejor.

```barras
titulo: M1 · Compradores reales entre los 10 clientes que cada método pone primero (10 meses de prueba, 100 lugares)
unidad: de 100
Modelo en uso (M1.3): 60
Versión anterior del modelo: 56
Regla: más días sin comprar: 54
Otra variante probada: 51
nota: El modelo en uso queda primero, pero con una diferencia pequeña e inconclusa. Datos de práctica.
```

```barras
titulo: M2 · De cada 10 clientes señalados, cuántos sí llegaron a 90 días sin comprar (julio y agosto)
unidad: de 10
Regla: más días sin comprar: 8
Modelo M2: 6,5
Misma probabilidad para todos: 4,5
nota: En esta comparación con datos de práctica la regla sencilla acertó más; se sigue midiendo cada mes en «Modelos y monitoreo».
```

```barras
titulo: M4 · El primer producto sugerido fue comprado después (porcentaje de casos)
unidad: %
Modelo aprendido: 13,3
Productos más populares: 12,1
nota: La diferencia (1,2 puntos) no alcanza la meta de 5 puntos. Se publica la sugerencia por popularidad, filtrada por compatibilidad.
```

```barras
titulo: M5 · Resultado de 42 comparaciones (14 series × 3 horizontes)
unidad: comparaciones
Se mantuvo el método sencillo: 21
Sin conclusión clara: 14
El método nuevo fue peor: 6
El método nuevo fue mejor: 1
nota: Las ventas de práctica suben y bajan sin una tendencia clara; por eso el pronóstico sale casi plano.
```

```barras
titulo: M6 · Casos raros de prueba que la versión actual detecta (ventas)
unidad: %
Versión actual (M6.1): 86,4
Versión anterior (M6): 68,9
nota: Además, las señales en operaciones reales bajaron de 14 a 1, así que hay menos falsas alarmas. Datos de práctica.
```

## 5. El asistente

El asistente responde preguntas escritas en lenguaje normal, como «¿A quién debo llamar primero?» o «¿Qué cambió en las ventas de octubre?». Se abre con el botón **Asistente** en la parte superior de la pantalla.

```pasos
Haces una pregunta | En tus palabras, sobre clientes, ventas, políticas o los modelos.
Busca en los datos | Solo consulta lo que tu perfil puede ver.
Redacta la respuesta | Usa las cifras que encontró, sin inventar otras.
Muestra sus fuentes | Cada dato lleva un número que lleva a su origen para comprobarlo.
```

Debes saber cuatro cosas:

- **Tiene dos modos.** Con el modelo de lenguaje activo (Gemini) responde de forma conversacional. Si el servicio no responde o llega a su límite de uso, pasa a **modo básico**: respuestas más simples con reglas fijas. La pantalla siempre dice en qué modo está.
- **Avisa si duda de una cifra.** Si escribe un número que no aparece en los datos consultados, lo marca para que lo revises.
- **No actúa por ti.** No envía mensajes, no crea tareas y no cambia datos. Solo informa.
- **Respeta los permisos.** Una empresa cliente solo recibe información de su propia empresa.

### Textos redactados por IA en las pantallas

Además del asistente, la IA redacta textos de apoyo en dos lugares, donde más ayudan a quien va a hablar con un cliente:

```tarjetas
IA | Productos que podrías ofrecer | «Cómo plantear la conversación» y, en cada producto, por qué podría interesarle al cliente, en lenguaje comercial. Los datos originales siguen debajo, en «Datos que lo respaldan».
IA | Ficha del cliente | «Para preparar la conversación»: qué pasa con el cliente, qué atender primero y dos o tres preguntas para la llamada.
```

- **Se reconocen por el sello morado «Redactado por IA»**, con el nombre del modelo que los escribió.
- **Solo usan datos de esa pantalla.** Si un texto trae una cifra que no está en los datos, se descarta y se muestra el texto original.
- **Se redactan una vez y se guardan.** Si un texto aún no existe, la pantalla dice «Redactando con IA…» y lo muestra al terminar (hasta un par de minutos). Puedes seguir trabajando mientras tanto.
- **Son apoyo, no datos nuevos.** Revísalos antes de usarlos; no crean tareas ni envían nada.

## 6. Glosario: palabras que vas a encontrar

| Palabra | Qué significa |
| --- | --- |
| **Cierre** | La foto oficial de los datos de un mes. Todo lo que ves viene de un cierre. |
| **Fecha de los datos** | Hasta qué día llega la información. Aparece arriba en cada pantalla. |
| **Modelo de IA** | Un cálculo que aprende del pasado para estimar algo futuro. |
| **Estimación** | Lo que el modelo cree que puede pasar. No es un hecho. |
| **En uso** | El modelo funciona y alimenta su pantalla; una persona decide qué hacer con lo que estima. Los seis modelos están en uso. |
| **Regla sencilla o referencia** | La forma simple de decidir sin IA, contra la que se compara cada modelo. |
| **Pendiente de madurez** | Aún no pasó el tiempo para saber si el modelo acertó: lo estimado en octubre se comprueba con lo que pase en noviembre. |
| **Ventana estimada** | Un rango de fechas en el que es probable que algo ocurra. |
| **Cobertura** | Un servicio contratado con fecha de fin, que puede renovarse. |
| **Seguimiento** | Una tarea con un cliente: quién la atiende, qué se hizo y con qué resultado. |
| **PQRS** | Peticiones, quejas, reclamos y sugerencias de las empresas cliente. |
| **Datos de práctica** | Datos inventados para probar el sistema sin usar información real. |

## 7. Preguntas frecuentes

**¿La IA decide a quién llamar?** No. Ordena y sugiere; una persona decide y registra lo que hizo.

**¿Por qué una gráfica de pronóstico sale casi plana?** Porque las ventas de práctica suben y bajan sin una tendencia clara. Un buen pronóstico no inventa picos: muestra un nivel y cuánto se ha equivocado antes.

**¿Qué significa «Pendiente de madurez» en los modelos?** Que hay que esperar al mes siguiente para comparar lo estimado con lo que realmente pasó. No es un error.

**¿Por qué se usan datos de práctica?** Para probar todo el sistema sin exponer información real de clientes. Los resultados con datos reales pueden ser diferentes.

**¿Qué hago si veo algo raro o un número que no cuadra?** Abre «Ver cifras exactas y cómo se calcularon» en esa pantalla y avisa al equipo técnico con la fecha de los datos y la pantalla.

## Parte 2 · Detalle técnico

## 8. Arquitectura

```pasos
Archivos de la empresa | CSV o Excel de ventas, compras, clientes, productos, coberturas y TRM.
A01 · carga y calidad | pipeline/: filas aceptadas, duplicadas y aisladas, con su incidencia.
Cierre mensual (C2) | Agenda C1, historial, coberturas, series, oportunidades y M1. Se valida y se publica de forma atómica.
API y SQLite | api/: servidor con la biblioteca estándar; permisos en api/permisos.py.
Aplicación web | app/: HTML, CSS y JS sin frameworks; vistas por perfil.
```

| Pieza | Qué hace | Dónde |
| --- | --- | --- |
| A01 · carga y calidad | Lee CSV o Excel y separa filas aceptadas, duplicadas y aisladas, con el motivo de cada una. | `pipeline/`, vista *Datos y cierres* |
| Cierre mensual | Genera la publicación del mes, la valida contra el contrato C2 y la publica de forma atómica. Si falla, sigue vigente el cierre anterior. | `python -m api cierre`, `api/publicacion.py` |
| Contratos | C1 (agenda) y C2 (publicación) son esquemas JSON. Lo que no los cumple no se publica. | `contratos/` |
| API | Servidor HTTP con la biblioteca estándar de Python y SQLite. Los permisos se comprueban en el servidor. | `api/servidor.py`, `api/permisos.py` |
| Aplicación web | Accesible: letra de 18 px, controles de 48 px, ajustes de tamaño y tema. | `app/`, [DESIGN.md](../DESIGN.md), [UX-CONTRACT.md](../UX-CONTRACT.md) |
| Modelos | Entrenamiento y evaluación con protocolos fijados antes de ver resultados. La inferencia y la API funcionan **sin** scikit-learn ni statsmodels. | `modelos/`, [plan de modelos](plan/modelos/README.md) |
| Publicaciones de M2–M6 | Las salidas de M2–M6 se importan con `python -m api sombra <carpeta>` (el nombre del comando es histórico) y no cambian el cierre. | `api/prevencion.py`, `api/proxima.py`, `api/venta_cruzada.py`, `api/demanda.py`, `api/anomalias.py` |
| Monitoreo | Observaciones de salud, distribución, desempeño y revisión humana por modelo, con avisos persistentes. | `api/monitoreo*.py`, [monitoreo-modelos.md](monitoreo-modelos.md) |

## 9. Modelos: métodos, estado y documentación

| Modelo | Método publicado | Decisión de la evaluación | Ficha |
| --- | --- | --- | --- |
| M1 · `compra_30d` | `compra_30d-m13-P`: regresión logística, pesos por antigüedad (semivida de 180 días) y ajuste de nivel | Inconclusa; **en uso en modo demostración** | [modelo-compra.md](modelo-compra.md), [M1.3](modelo-compra-m13.md) |
| M2 · `inactividad_60d` | `m21-poisson-180`: ritmo de compra de los últimos 180 días | Inconclusa; la referencia es «mayor recencia» | [modelo-inactividad.md](modelo-inactividad.md) |
| M3 · `proxima_compra` | Cox con regularización L2; publica la ventana del 10 % al 50 % | Inconclusa; mejora a la curva poblacional (Brier integrado −10,3 %) | [modelo-proxima-compra.md](modelo-proxima-compra.md) |
| M4 · `venta_cruzada` | Popularidad filtrada por compatibilidad (`compat-v1`) | Inconclusa; se conservó la referencia | [modelo-venta-cruzada.md](modelo-venta-cruzada.md) |
| M5 · `demanda` | Referencias por serie (último mes, promedio de 3 meses) y candidatos SES/Holt amortiguado; total = suma de familias | 21 de 42 conservan la referencia | [modelo-demanda.md](modelo-demanda.md) |
| M6 · `anomalias` | M6.1: reglas de catálogo y contexto (mediana/MAD) con cupo de revisión | Se conservan las reglas; Isolation Forest no aportó valor demostrable | [modelo-anomalias.md](modelo-anomalias.md) |

**Estado:** los seis modelos están en uso en la aplicación. La columna «Decisión de la evaluación» resume cómo se compararon con su referencia en los datos de práctica. El registro técnico de versiones mantiene su propio protocolo (`python -m modelos.cli promover`). **Estados de monitoreo:** sin información, pendiente de madurez, no comparable, sin problemas detectados (nunca aparece por falta de datos), requiere revisión y publicación rechazada. Reconocer o resolver un aviso exige un motivo y nunca reentrena un modelo.

## 10. Asistente: detalle técnico

- **Orquestación:** grafo de LangGraph (`api/agente_chat.py`) con herramientas construidas según los permisos del usuario. El modo básico es un grafo de reglas (`api/agente.py`).
- **Proveedores** (`api/llm.py`): Gemini es el principal, con **dos claves** (`GEMINI_API_KEY` y `GEMINI_API_KEY2`); Anthropic es el respaldo final opcional. Las claves van en `/etc/jacomind/jacomind.env` o en `.env`, **nunca en el repositorio**. Si no hay cupo en ningún modelo, el asistente responde en modo básico con un aviso.
- **Salvaguardas:** se eliminan las citas a fuentes que no existen, se detectan las cifras sin respaldo, la memoria se guarda por conversación y está aislada entre usuarios y empresas, y las estimaciones de los modelos se presentan como apoyo a la decisión, no como hechos.

| Grupo | Herramientas | Quién |
| --- | --- | --- |
| Cartera | `resumen_cartera`, `buscar_clientes`, `ficha_cliente`, `oportunidades_prioritarias`, `seguimientos_pendientes`, `coberturas_por_vencer` | Perfiles con acceso a la cartera |
| Finanzas | `ventas_o_compras_por_mes`, `clientes_que_redujeron_compras`, `simular_tipo_de_cambio` | Finanzas y Gerencia |
| Modelos | `riesgo_inactividad`, `proxima_compra`, `venta_cruzada`, `pronostico_demanda` (en pesos solo para Finanzas y Gerencia), `operaciones_atipicas`, `monitoreo_de_modelos`, `resultados_de_modelos` | Los mismos permisos que la pantalla de cada modelo |
| Conocimiento | `buscar_politicas`, `buscar_en_documentacion`, `definicion_de_indicador` | Según el perfil |
| Portal | `mis_solicitudes`, `mis_beneficios`, `buscar_politicas` | Empresa: solo su empresa |

## 11. Orquestador de cuotas de Gemini

Las claves del plan gratuito de Gemini tienen tres límites por modelo: **solicitudes por minuto** (RPM), **tokens por minuto** (TPM) y **solicitudes por día** (RPD). El día se reinicia a medianoche de la hora del Pacífico. `api/cuota_llm.py` decide, en cada llamada, **qué clave y qué modelo** usar:

```pasos
Reserva | Antes de llamar comprueba los tres límites de esa clave y ese modelo, usando como máximo el 90 %.
Llama | Si cabe, llama a Google; si no, pasa al siguiente candidato sin gastar nada.
Anota | Guarda los tokens reales. El registro vive en var/llm_cuota.sqlite3 y sobrevive a reinicios.
Bloquea | Si Google responde 429 o el modelo está saturado, aparta esa combinación hasta el minuto o el día siguiente.
```

| Tarea | Orden de modelos (en cada uno, primero la clave menos usada hoy) | Por qué |
| --- | --- | --- |
| **Asistente** (`chat`) | Gemini 3.5 Flash Lite → 3.1 Flash Lite → Gemma 4 31B → Gemma 4 26B → 2.5 Flash Lite → 2.5 Flash → los mejores Flash, solo el 25 % de su cupo | Los Flash Lite dan 500 solicitudes al día por clave. Gemma da 14 400 al día, pero solo 16 000 tokens por minuto. |
| **Redacción** (`redaccion`) | Gemini 3.8 Flash → 3.6 Flash → 3 Flash → Flash Lite, hasta el 30 % de su cupo | Los mejores modelos solo dan 20 al día por clave, así que se usan en lotes de 5 clientes y el resultado se guarda. |

```barras
titulo: Solicitudes diarias disponibles con las dos claves (después del margen del 90 %)
unidad: al día
Flash Lite 3.5 y 3.1 (asistente): 1800
Gemma 4 31B y 26B (respaldo del asistente): 51840
Flash 3.8, 3.6 y 3 (redacción): 108
Flash 2.5 y 2.5 Lite (respaldo): 72
nota: Una pregunta al asistente usa de 1 a 4 solicitudes. Redactar los textos de todos los clientes de un cierre usa unas 50 solicitudes de los mejores modelos.
```

- **Consultar el uso:** `python -m api cuota-llm` o `GET /api/llm/cuota`, con permiso de Operaciones o de monitoreo. Nunca muestra las claves, solo una huella.
- **Textos de IA** (`api/narrativas.py`): se guardan en la tabla `narrativas` con una huella de los datos de entrada. El servidor los pre-redacta poco a poco al arrancar y luego cada hora, dentro del cupo (`JACOMIND_NARRATIVAS_AUTO=0` lo desactiva). También se pueden pre-redactar con `python -m api narrativas`.
- **Privacidad:** en el plan gratuito, Google puede usar lo que se le envía para mejorar sus productos. Sirve para la demo con datos de práctica; **con datos reales de clientes hay que usar un plan de pago** o desactivar la IA (`JACOMIND_LLM=0`).

## 12. Operación, despliegue y trabajo en local

| Tema | Resumen | Más |
| --- | --- | --- |
| Servidor | Amazon Lightsail (Ubuntu 24.04, 1 GB, Ohio), Caddy con HTTPS automático, servicio `jacomind` y datos en `/var/lib/jacomind` | [despliegue.md](despliegue.md) |
| CI | GitHub Actions corre las pruebas de aplicación, integración y modelos en cada push | `.github/workflows/ci.yml` |
| CD | Si el CI de `main` pasa, se despliega ese commit con respaldo previo y vuelta atrás automática si no arranca | `.github/workflows/despliegue.yml` |
| Datos de la demo | El despliegue actualiza el **código**. La base de la demo se sube aparte. | [demo-accesible.md](demo-accesible.md) |
| Respaldos | Copia diaria a las 03:30, guardada 30 días | [operacion.md](operacion.md) |

```
python -m api --db salida/demo_cliente_2026_11_25/demo.sqlite3 servir --puerto 8000   # abrir http://127.0.0.1:8000/app/
python -m unittest discover                                         # carril A (datos y modelos)
python -m unittest discover -s tests/app -t tests/app               # carril B (API y aplicación)
python -m unittest discover -s tests/integracion -t tests/integracion
```

## 13. Reglas del proyecto

- **Datos:** no se modifican los datos originales, las ejecuciones históricas ni las publicaciones congeladas para que pase una prueba.
- **Protocolos:** se fijan **antes** de ver los resultados y no se cambian después.
- **Promoción:** ningún modelo se promueve automáticamente.
- **Lo que no se inventa:** etiquetas, revisiones, resultados comerciales, ahorro, ventas recuperadas ni ROI.
- **Controles:** no se desactivan para que algo funcione. Si una publicación falla la integridad, se investiga.
- **Lo que no va al repositorio:** datos de clientes ni claves. El repositorio es **público**.
- **IA con datos reales:** no se usa el plan gratuito de Gemini con datos reales de clientes.

## 14. Mapa de documentos

| Necesito… | Documento |
| --- | --- |
| Presentar la demo | [demo-accesible.md](demo-accesible.md) |
| Entender las pantallas y el diseño | [DESIGN.md](../DESIGN.md), [UX-CONTRACT.md](../UX-CONTRACT.md), [matriz V01–V31](plan/matriz-v01-v31.md) |
| Detalle de un modelo | Fichas `modelo-*.md` y [plan de modelos](plan/modelos/README.md) |
| Monitoreo e integridad | [monitoreo-modelos.md](monitoreo-modelos.md) |
| Desplegar u operar | [despliegue.md](despliegue.md), [operacion.md](operacion.md) |
| Ficha 360 y reglas de la agenda | [ficha-360.md](ficha-360.md), [ficha-operaciones.md](ficha-operaciones.md) |
