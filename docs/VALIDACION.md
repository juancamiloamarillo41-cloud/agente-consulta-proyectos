# Validación del agente frente a los informes

Se armó un set de 14 preguntas como las que haría un consultor
([`validacion/preguntas.json`](validacion/preguntas.json)). Para cada una se redactó a
mano la **respuesta esperada**, leyendo los informes. Incluye preguntas trampa diseñadas
a partir de las ambigüedades que tienen los propios informes:

| Tipo | Preguntas |
|---|---|
| Cifra preliminar frente a oficial (Clínica: 30% vs 24%) | 1 |
| Alcance limitado y dato no validado (Plásticos: solo Línea 1; Línea 2 no validada) | 2 |
| Documento externo no disponible (La Canasta: Informe de Diagnóstico) | 3 |
| Tema fuera de los informes (minería) y dato inexistente (presupuesto) | 4, 6 |
| Resultado no atribuible al proyecto (Cooperativa: +9% de colocación) | 5 |
| Consultas estructuradas: filtro, comparación, agregación, indicador | 7, 8, 9, 14 |
| Detalle de ejecución en el texto | 10, 11 |
| Síntesis entre proyectos y caso de uso para un proyecto nuevo | 12, 13 |

`python scripts/run_validation.py` ejecuta las preguntas y guarda cada respuesta con su
traza en [`validacion/transcripciones/`](validacion/transcripciones/). La comparación con
la respuesta esperada se hizo leyendo cada transcripción.

## Ronda 1: problemas encontrados y correcciones

La primera ronda se ejecutó con la cuota de `gemini-3.5-flash` ya agotada, así que la
mayoría de las respuestas las dio `gemini-3.1-flash-lite`. Las preguntas trampa (1 a 6)
se respondieron bien: el agente usó el 24% oficial, aclaró que no hay OEE de planta, que el
análisis por local está en un documento no disponible, que no hay proyectos de minería ni
datos de presupuesto, y que el +9% no es atribuible al proyecto. Aparecieron cuatro
problemas, cada uno con su corrección:

| # | Problema observado | Causa (vista en la traza) | Corrección |
|---|---|---|---|
| 11 | **Cifras atribuidas a indicadores equivocados**: dijo "OEE 95%" (95% es la Calidad; el OEE es 71%) e inventó nombres de indicadores | La consulta SQL trajo los valores de `resultado` sin la columna `nombre`, y el modelo rellenó las etiquetas | Regla explícita en el prompt; la herramienta SQL advierte cuando una consulta a `indicadores` no trae `nombre`; se sacaron los modelos "lite" de la cadena |
| 8 | Afirmó que el informe de la Cooperativa **"no detalla qué objetivo no se cumplió"** (sí lo detalla: abandono 11% frente a ≤ 10%) | Consultó solo la tabla `proyectos` y la búsqueda en texto no trajo la sección de Resultados | La descripción de la herramienta SQL orienta a la tabla `indicadores` para metas; regla de comprobar con la otra herramienta antes de afirmar que algo no está |
| 7 y 10 | Consultas vacías por tildes (`LIKE '%Martin Aguirre%'`, `'%Plasticos del Pacifico%'`); el agente se recuperó con llamadas extra | `LIKE` de SQLite distingue tildes | `LIKE` redefinido para ignorar mayúsculas y tildes |
| 12 | Atribuyó cada lección a su proyecto correctamente, pero deduciéndolo del texto: la consulta no traía `codigo_proyecto` | Falta la columna que identifica el proyecto | La herramienta SQL advierte cuando las filas no indican su proyecto |

Además, la ronda dejó ver que una petición a la API podía quedar colgada indefinidamente:
se agregó un tiempo límite de 90 s por petición.

## Ronda 2: resultados con las correcciones

Transcripciones en [`validacion/transcripciones/`](validacion/transcripciones/): allí queda la
última ejecución de cada pregunta (las de la ronda 1 están en
[`ronda1/`](validacion/transcripciones/ronda1/)). Esta ronda se ejecutó con modelos Flash
completos (3.6, 3.7, 3.8 y 3-preview), hasta agotar la cuota gratuita del día; las preguntas
marcadas "ronda 3" se ejecutaron después, con una clave nueva.

| # | Pregunta (resumida) | Resultado | Observaciones |
|---|---|---|---|
| 1 | Resultados de la Clínica y reducción de la espera | ✅ Correcta | 24% oficial (52 → 39,5 min) y explica que el 30% fue la medición preliminar; usa ambas herramientas |
| 2 | OEE de toda la planta de Plásticos | ✅ Correcta | No existe cifra de planta; Línea 1 de 58% a 71%; Línea 2 ≈ 63% según el cliente, no validado |
| 3 | Locales con peor precisión según el diagnóstico | ✅ Correcta | Remite al Informe de Diagnóstico no disponible; aporta el 78% global que sí está en el informe |
| 4 | Proyectos de minería | ✅ Correcta | "Los informes no contienen..." y "Fuentes: ninguna" |
| 5 | Aumento de colocación gracias al proyecto | ✅ Correcta | 9%, pero no atribuible al proyecto (campaña comercial paralela) |
| 6 | Presupuesto del proyecto de Plásticos | ✅ Correcta | No está en los informes. En la primera ejecución de esta ronda agotó el límite de pasos buscando; tras acotar la regla de verificación, respondió bien en 5 llamadas |
| 7 | Proyectos de Martín Aguirre | ✅ Correcta (ronda 3) | Plásticos (Manufactura) y Clínica (Salud), en una sola consulta: el `LIKE` sin tildes ya funciona |
| 8 | Proyectos que no cumplieron metas y por qué | ✅ Correcta (corregida desde la ronda 1) | Abandono 11% vs ≤ 10%; La Canasta: integración 0 de 3 (ERP y proveedor) y 31 días vs ≤ 30 (29 sin licores). Presenta la concentración del abandono en microcrédito rural como "razón", cuando el informe la plantea como foco a investigar. Citó una sección inexistente |
| 9 | Proyecto más largo | ✅ Correcta (ronda 3) | La Canasta, 25 semanas (2 de marzo al 21 de agosto de 2026) |
| 10 | Cómo se redujeron las microparadas | ✅ Correcta (ronda 3) | Tolvas con sensores de nivel, secuencia de secado de resina, registro en tablet con 24 causas y reunión diaria; 21 h/mes (17%) en la línea base; aclara que es solo la Línea 1 |
| 11 | Proyectos con SMED y su resultado | ✅ Correcta (corregida desde la ronda 1) | Cambio de formato 95 → 38 min; OEE 58% → 71%, cada cifra con su indicador. Citó secciones con número incorrecto |
| 12 | Lecciones que se repiten | ✅ Correcta | Mandos medios (Cooperativa y Plásticos), calidad de datos (los cuatro), participación de actores clave; atribución por `codigo_proyecto` |
| 13 | Recomendaciones para un proyecto de reposición | ✅ Correcta (ronda 3) | Datos maestros (15% de códigos, 3 semanas), dependencias de ERP y proveedores, administradores de tienda, conteos cíclicos, revisión trimestral; advierte del Informe de Diagnóstico no disponible |
| 14 | Productividad de analistas | ✅ Correcta (ronda 3) | De 85 a 124 solicitudes por analista al mes (+46%), meta ≥ 110 |

**Resumen:** con las rondas 2 y 3, **las 14 preguntas tienen una respuesta correcta**, incluidas
las 6 trampas y las 2 que fallaron en la ronda 1. Las preguntas 7, 9, 10, 13 y 14 se ejecutaron
en la ronda 3, al renovarse la cuota; la 8 y la 11 se repitieron para verificar las correcciones
de citas (ver ronda 3).

Correcciones hechas durante la ronda 2:
- **Límite de pasos (pregunta 6):** la regla de verificar antes de decir que algo no está se
  acotó a una sola comprobación adicional (verificado: la pregunta 6 volvió a ejecutarse y
  respondió bien). Además, si se alcanza el límite, el agente hace una última llamada con las
  herramientas desactivadas y responde con lo que ya obtuvo (cubierto por tests).
- **Secciones inventadas en las citas (preguntas 8 y 11):** el modelo añadía números de sección
  a datos que venían de SQL. Ahora solo cita la sección cuando proviene de la búsqueda en
  texto; los datos de SQL se citan con el archivo. Este cambio de prompt se hizo después de
  agotar la cuota y aún no se ha vuelto a ejecutar contra el modelo.

## Ronda 3: preguntas pendientes y un último ajuste

Se ejecutaron las preguntas pendientes (7, 9, 10, 13 y 14) y se repitieron la 8 y la 11 para
comprobar la regla de citas. Las cifras fueron correctas en todas, y el cierre forzado al llegar
al límite de pasos funcionó en vivo (preguntas 8 y 11). Aparecieron tres detalles, visibles en
[`ronda3_antes_de_ajustes/`](validacion/transcripciones/ronda3_antes_de_ajustes/):

| # | Problema observado | Corrección |
|---|---|---|
| 8 | Dijo que quedaron fuera los créditos "hipotecarios e **industriales**"; el informe dice "hipotecario y **corporativo**" (paráfrasis incorrecta de una salvedad). También presentó la concentración del abandono en microcrédito rural como la causa del incumplimiento | Reglas nuevas: usar los términos exactos del informe en alcances y salvedades, y no afirmar causas que el informe no establezca |
| 8, 11 | Citó "salvedades" como si fuera una sección del informe | Regla explícita: las salvedades se citan solo con el archivo |
| Casi todas | Una llamada extra en cada pregunta para leer la tabla `salvedades`; en la 14, una consulta repetida porque el aviso pedía `codigo_proyecto` aunque la fila ya traía `archivo_fuente` | Las salvedades de cada proyecto van en el prompt de sistema (~600 tokens), y `archivo_fuente` cuenta como identificador del proyecto |

Tras los ajustes se repitieron la 8 y la 14 ([transcripciones](validacion/transcripciones/)):

| # | Antes | Después |
|---|---|---|
| 8 | 7 llamadas, 31.900 tokens de entrada; "industriales"; cita "salvedades" | **5 llamadas**, 29.900 tokens; términos correctos; el 70% rural aparece como dato del informe, no como causa; citas limpias |
| 14 | 5 llamadas, 17.100 tokens de entrada; consulta repetida | **3 llamadas, 10.200 tokens**; misma respuesta correcta |

## Cómo repetir la validación

```bash
python scripts/run_validation.py          # las 14 preguntas
python scripts/run_validation.py 7 9 13   # solo algunas
```

Con la capa gratuita conviene ejecutar pocas preguntas por día o activar facturación.
