# Agente de consulta de proyectos — Procesa Consultores

[![Tests](https://github.com/juancamiloamarillo41-cloud/agente-consulta-proyectos/actions/workflows/tests.yml/badge.svg)](https://github.com/juancamiloamarillo41-cloud/agente-consulta-proyectos/actions/workflows/tests.yml)

Agente en Python que responde en lenguaje natural preguntas de consultores sobre los
informes de cierre de proyectos anteriores. Cada respuesta cita el informe del que
proviene, muestra qué herramientas se usaron para llegar a ella y, si algo no está en
los informes, lo dice en lugar de inventarlo.

```text
> ¿Cuál es el OEE de toda la planta de Plásticos del Pacífico?

El alcance del proyecto PC-2025-027 se limitó exclusivamente a la Línea 1 de inyección,
por lo que no se cuenta con una cifra de OEE que represente a la planta en su conjunto.
El OEE de la Línea 1 fue del 71% (línea base 58%). [...] Según los registros del cliente,
el OEE de la Línea 2 se mantuvo alrededor del 63%, pero Procesa Consultores no validó
dicha cifra ni su metodología de cálculo.

Fuentes: Informe_Cierre_PC-2025-027_Plasticos_del_Pacifico.pdf (1. Resumen ejecutivo, 4. Alcance)

── Trazabilidad ─────────────────────────────
  1. consultar_fichas_sql: SELECT * FROM indicadores WHERE codigo_proyecto = 'PC-2025-027' AND nombre LIKE '%OEE%'
     → 1 filas [0.00s]
  2. buscar_en_informes: {"consulta": "OEE planta total alcance", "codigo_proyecto": "PC-2025-027"}
     → 4 fragmentos (PC-2025-027 4. Alcance; PC-2025-027 1. Resumen ejecutivo; ...)
  Informes recuperados por las herramientas:
   - Informe_Cierre_PC-2025-027_Plasticos_del_Pacifico.pdf
```

---

## Cumplimiento del enunciado

| Requisito | Dónde se cumple |
|---|---|
| 1. Extracción de fichas con respuestas estructuradas del modelo; campos justificados | [`extraction.py`](src/project_agent/extraction.py) envía a Gemini el JSON Schema de [`ficha.py`](src/project_agent/ficha.py) como salida estructurada; la justificación de los campos está en la [sección 4](#4-diseño-de-la-ficha) |
| 2. Fichas en una base relacional | SQLite con 8 tablas ([`schema.sql`](src/project_agent/storage/schema.sql)); `data/fichas.db` se reconstruye desde los JSON |
| 3. Dos herramientas (texto y SQL); el agente decide cuál usar | [`tools.py`](src/project_agent/tools.py): `buscar_en_informes` (BM25) y `consultar_fichas_sql` (solo lectura); el modelo elige en [`agent.py`](src/project_agent/agent.py). En [VALIDACION.md](docs/VALIDACION.md) hay respuestas que usan una, la otra o ambas |
| 4. Cada respuesta indica su informe; si algo no está, lo dice | Reglas del prompt en `agent.py` y campo `fuentes` en los resultados de las herramientas. Casos verificados: preguntas 3, 4 y 6 de [VALIDACION.md](docs/VALIDACION.md) |
| 5. Trazabilidad de las herramientas usadas | Bloque «Trazabilidad» en la consola ([`cli.py`](src/project_agent/cli.py)) y en la web: herramienta, argumentos exactos (SQL o búsqueda) y resultado |
| 6. Interfaz por consola | `agente-proyectos` o doble clic en `iniciar_agente.bat` ([sección 1](#1-instalación-y-ejecución)); admite preguntas de seguimiento |
| Explicar la librería o framework usado | [Sección 3](#3-decisiones-técnicas): SDK oficial de Gemini, sin framework de agentes, y por qué |
| Entregable 1: repositorio con historial y código organizado | Commits por fase en este repositorio; tests automáticos en GitHub Actions; [tabla de módulos](#2-arquitectura) |
| Entregable 2: README con instalación, arquitectura y decisiones, supuestos, limitaciones y costo para 50 consultores | Secciones [1](#1-instalación-y-ejecución), [2](#2-arquitectura), [3](#3-decisiones-técnicas), [6](#6-supuestos), [7](#7-limitaciones-conocidas) y [8](#8-estimación-de-costo-50-consultores) |
| Entregable 3: fichas de los cuatro proyectos | [`data/fichas/`](data/fichas/) (JSON) |
| Entregable 4: video | Correo |
| No incluir claves de API | `.env` está en `.gitignore`; solo se versiona [`.env.example`](.env.example) |
| Opcional: interfaz web | [`web.py`](src/project_agent/web.py) y [`iniciar_web.bat`](iniciar_web.bat) |

---

## 1. Instalación y ejecución

Requisitos: Python 3.10 o superior y una clave de Google Gemini
([Google AI Studio](https://aistudio.google.com/apikey)).

```bash
git clone https://github.com/juancamiloamarillo41-cloud/agente-consulta-proyectos.git
cd agente-consulta-proyectos
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
pip install -e .                  # instala el paquete (src/project_agent) en modo editable
copy .env.example .env            # Linux/macOS: cp .env.example .env  (en Windows es opcional: ver abajo)
# editar .env y escribir la clave en GEMINI_API_KEY
python -c "from project_agent.storage.repository import rebuild_db_from_json; rebuild_db_from_json()"
```

El último comando crea `data/fichas.db` a partir de las fichas JSON versionadas (no consume API).

**La clave de Gemini, en Windows, sin editar archivos:** al abrir `iniciar_agente.bat` o
`iniciar_web.bat` por primera vez, si no hay `.env`, la ventana pide la clave (no se muestra al
pegarla), comprueba con Google que sea válida (sin gastar cuota de preguntas) y crea `.env`.
Lo mismo se puede hacer desde la terminal con `python -m project_agent.setup_env`. La clave se
consigue gratis en [Google AI Studio](https://aistudio.google.com/apikey).

**Dos formas de usarlo:**

- **Con doble clic (Windows):** `iniciar_agente.bat` e `iniciar_web.bat` no necesitan activar el
  entorno ni escribir comandos; usan directamente el Python de `.venv`.
- **Desde la terminal:** los comandos de la tabla (`agente-proyectos`, `python -m pytest`...) sí
  requieren activar el entorno en cada terminal nueva (`.venv\Scripts\activate`; en PowerShell
  también `.\.venv\Scripts\Activate.ps1`). Si no, Windows responde que `agente-proyectos` no se
  reconoce como comando. La alternativa es llamarlos con su ruta, por ejemplo
  `.venv\Scripts\agente-proyectos.exe`.

| Acción | Comando |
|---|---|
| Consola del agente, en Windows | **Doble clic en `iniciar_agente.bat`**: abre una ventana lista para preguntar, sin activar el entorno |
| Consola interactiva del agente | `agente-proyectos` (o `python -m project_agent`); `nueva` reinicia la conversación y `salir` termina |
| Una sola pregunta | `agente-proyectos "¿Qué hicimos en el sector salud?"` |
| Interfaz web (opcional), en Windows | **Doble clic en `iniciar_web.bat`**: arranca el servidor y abre el navegador; al cerrar la ventana se detiene |
| Interfaz web (opcional), desde la terminal | `agente-proyectos-web` (abre el navegador; `--sin-navegador` para no abrirlo) |
| Generar fichas de informes nuevos y reconstruir la base | `python -m project_agent.extraction` |
| Regenerar todas las fichas (llama al LLM) | `python -m project_agent.extraction --force` |
| Ejecutar los tests (sin LLM) | `python -m pytest` |
| Set de preguntas de validación | `python scripts/run_validation.py` |

Las fichas ya generadas están versionadas en [`data/fichas/`](data/fichas/).

Para agregar un informe nuevo: copiarlo (PDF o Word) en `data/informes/` y ejecutar
`python -m project_agent.extraction`. Solo se procesan los informes que aún no tienen ficha.

## 2. Arquitectura

```text
data/informes/*.pdf|*.docx
        │
        ▼
 ingestion/   PDF (PyMuPDF) y Word (python-docx) → bloques: encabezado / texto / tabla
        │     → fragmentos por sección, con cita (archivo, sección, páginas)
        ├─────────────► search.py (BM25) ───────────────► herramienta buscar_en_informes
        ▼
 extraction.py  LLM con salida estructurada (esquema = ficha.py)
        │       → verificación de cifras contra el informe → data/fichas/*.json
        ▼
 storage/     SQLite (schema.sql) ───────────────────────► herramienta consultar_fichas_sql
        ▼                                                     (solo lectura)
 agent.py     bucle de uso de herramientas con Gemini + reglas anti-alucinación + traza
        ▼
 cli.py       consola: respuesta, fuentes, herramientas usadas y consumo de tokens
 web.py       interfaz web (opcional): API FastAPI + página HTML con lo mismo que la consola
```

| Módulo | Responsabilidad |
|---|---|
| [`ingestion/loaders.py`](src/project_agent/ingestion/loaders.py) | Lee PDF y Word a una representación común; detecta encabezados por tipografía, descarta pies de página, convierte tablas a markdown |
| [`ingestion/tables.py`](src/project_agent/ingestion/tables.py) | Limpia tablas, incluidas las celdas combinadas de documentos exportados desde Word |
| [`ingestion/sections.py`](src/project_agent/ingestion/sections.py) | Divide cada informe en fragmentos citables por sección |
| [`search.py`](src/project_agent/search.py) | Índice BM25 con normalización para español (tildes, plurales, palabras vacías) |
| [`ficha.py`](src/project_agent/ficha.py) | Modelo Pydantic de la ficha: esquema del LLM, validación y estructura de la base |
| [`extraction.py`](src/project_agent/extraction.py) | Genera las fichas con el LLM y verifica sus cifras contra el informe |
| [`storage/`](src/project_agent/storage/) | Esquema SQLite, escritura idempotente y consulta SQL de solo lectura |
| [`tools.py`](src/project_agent/tools.py) | Las dos herramientas del agente: declaración, ejecución y resumen para la traza |
| [`agent.py`](src/project_agent/agent.py) | Bucle de uso de herramientas, prompt de sistema, traza y consumo |
| [`llm.py`](src/project_agent/llm.py) | Único punto de contacto con el proveedor: reintentos y cadena de modelos de respaldo |
| [`cli.py`](src/project_agent/cli.py) | Interfaz de consola |
| [`web.py`](src/project_agent/web.py) y [`static/index.html`](src/project_agent/static/index.html) | Interfaz web opcional: API REST y página sin dependencias externas |

## 3. Decisiones técnicas

**Sin framework de agentes.** El bucle del agente ocupa unas 40 líneas en
[`agent.py`](src/project_agent/agent.py): el modelo pide una herramienta, el código la
ejecuta, registra la traza y devuelve el resultado, hasta que el modelo responde en texto.
Hay un máximo de 6 pasos; si se alcanza, una última llamada con las herramientas
desactivadas obliga al modelo a responder con lo que ya obtuvo. LangChain o LlamaIndex agregarían dependencias y capas de abstracción sin
aportar nada que este caso necesite, y harían más difícil explicar qué ocurre en cada paso.
Se usa directamente el SDK oficial `google-genai`.

**Proveedor: Google Gemini.** Tiene capa gratuita y soporta salida estructurada con JSON
Schema y llamadas a funciones. Las llamadas a la API (cliente, reintentos, cadena de
modelos) están en [`llm.py`](src/project_agent/llm.py); `agent.py` y `extraction.py` usan
además los tipos de mensajes del SDK de Gemini. Cambiar de proveedor implica adaptar esos
tres módulos: la lectura de informes, la búsqueda, la base, las herramientas y los tests no
cambian. Hay una cadena de modelos Flash
(`gemini-3.5-flash` → `3.6` → `3.7` → `3.8` → `3-flash-preview`, configurable con la variable
`GEMINI_MODELS`): ante errores transitorios (503 por demanda) se reintenta con espera
exponencial y, si un modelo agotó su cuota diaria o no está disponible para la clave (404),
se pasa al siguiente. `gemini-2.5-flash` salió de la cadena porque Google ya no lo ofrece a
claves nuevas. Los modelos
"lite" se excluyeron a propósito: en la validación asignaron cifras a indicadores
equivocados, y es preferible un error de cuota a una respuesta incorrecta.

**Lectura de documentos con estructura, no texto plano.** Los indicadores viven en tablas;
si la tabla se aplana, "18% | ≤ 10% | 11%" pierde a qué columna pertenece cada valor. Por
eso las tablas se convierten a markdown conservando filas y columnas, y los encabezados se
detectan por tamaño y negrita de la fuente, no por numeración. El informe de la Clínica es
un PDF exportado desde Word, con celdas combinadas que generan columnas fantasma; se
colapsan a las columnas lógicas de la cabecera. Se soporta `.docx` además de PDF, porque el
enunciado anuncia un informe en Word.

**Fragmentos por sección.** Se corta por sección (1. Resumen, 5. Resultados…) y no cada N
palabras. La sección es la unidad natural de cita y mantiene junto el contexto que
condiciona los datos: la advertencia "todos los resultados corresponden a la Línea 1" o la
nota "el 24% es el dato oficial" quedan en el mismo fragmento que su tabla.

**Búsqueda BM25 en lugar de embeddings.** El corpus es pequeño (37 fragmentos), las preguntas
usan el vocabulario de los informes (OEE, SMED, quiebre de stock) y BM25 no necesita otro
servicio ni costo por consulta. Es determinista y explicable. El agente compensa la falta de
sinónimos reformulando la búsqueda. Con cientos de informes convendría una búsqueda híbrida
(BM25 + embeddings).

**Dos fuentes complementarias.** La base de fichas responde bien a preguntas de listar,
filtrar, contar y comparar ("¿qué proyectos no cumplieron metas?"); el texto responde a
preguntas de detalle y contexto ("¿cómo se redujeron las microparadas?"). El agente decide
cuál usar, o ambas, según la pregunta; la descripción de cada herramienta indica para qué
sirve y la de SQL incluye el esquema completo.

**Las fichas JSON son la fuente de verdad; SQLite se reconstruye.** Los JSON se versionan en
Git (son entregable y son legibles en una revisión). La base se regenera desde ellos sin
llamar al LLM.

**SQL generado por el modelo tratado como entrada no confiable.** Tres barreras
independientes: validación de una sola sentencia `SELECT`/`WITH`, conexión SQLite en modo
solo lectura (`mode=ro`) y un autorizador que solo permite operaciones de lectura. Además se
limita a 50 filas. Si la consulta falla, el error vuelve al modelo para que la corrija.
`LIKE` se redefine para ignorar mayúsculas y tildes, porque el modelo escribe "Martin" o
"credito" con frecuencia.

**Memoria de conversación acotada.** El agente admite preguntas de seguimiento («¿y cuáles
fueron sus lecciones?»). Solo recuerda las preguntas y respuestas finales de los últimos 6
intercambios, no los resultados de las herramientas, para que el costo por pregunta no crezca
sin límite; y el prompt le pide usar esa memoria solo para entender a qué se refiere el
usuario, volviendo a consultar las herramientas para los datos. En la consola la memoria dura
la sesión (`nueva` la reinicia); en la web la guarda el navegador y la envía en cada pregunta,
así que el servidor no guarda estado y varios usuarios no se mezclan.

**Interfaz web con FastAPI y una página propia, no Streamlit.** Es opcional: la consola
cumple el requisito. Se eligió FastAPI porque se puede probar con tests automáticos sin
llamar a la API (con un agente simulado) y deja una API REST reutilizable
(`POST /api/preguntar`, documentada en `/api/docs`). La página es un solo archivo HTML sin
librerías externas. La web no agrega lógica: llama al mismo `ProjectAgent.ask()` y muestra
la respuesta, las fuentes, la trazabilidad paso a paso y el consumo. Escucha solo en
`127.0.0.1`, y el texto del modelo se escapa antes de convertir su markdown a HTML, para que
no pueda inyectar código en la página. Si se agota la cuota o el modelo está saturado,
muestra un mensaje claro en lugar de fallar.

**Medidas contra respuestas inventadas.**
1. Prompt de sistema con reglas explícitas: responder solo con resultados de herramientas,
   citar el archivo, decir cuándo algo no está, usar la cifra oficial y mencionar salvedades.
2. Campo `salvedades` en la ficha, que registra lo que evita malinterpretar datos: cifras
   preliminares, alcance limitado, resultados no atribuibles, datos no validados, pendientes
   y documentos externos no incluidos.
3. Verificación determinista de la extracción: cada cifra de los indicadores debe existir en
   el informe. Detectó, por ejemplo, variaciones que el modelo había calculado por su cuenta.
4. Advertencias de la herramienta SQL: si una consulta a `indicadores` no trae la columna
   `nombre`, o las filas no traen `codigo_proyecto`, la herramienta pide al modelo que no
   atribuya esos valores y repita la consulta. Surgió de un error real de la validación:
   sin el nombre, el modelo etiquetó "OEE 95%" a la Calidad.
5. Las citas de sección solo se permiten cuando vienen de la búsqueda en texto, para que el
   modelo no invente números de sección.
6. Las fuentes que muestra la traza las calcula el código a partir de los resultados de las
   herramientas, no el modelo.

## 4. Diseño de la ficha

Cada grupo de campos responde a un tipo de pregunta que haría un consultor:

| Grupo | Campos | Preguntas que habilita |
|---|---|---|
| Identificación | código, título, cliente, descripción del cliente, sector, subsector, ubicación | ¿Qué hicimos en salud? ¿Con qué clientes de retail trabajamos? |
| Ejecución | fechas de inicio, fin y aceptación, duración, estado, gerente, equipo, contraparte | ¿Qué proyectos gerenció X? ¿Cuál fue el más largo? ¿Cuáles cerraron con pendientes? |
| Contenido | problema, resumen, objetivos, alcance, metodologías, iniciativas | ¿Dónde usamos SMED? ¿Cómo abordamos un problema de tiempos de espera? |
| Resultados | indicadores (línea base, meta, resultado, variación, valores numéricos, estado de meta, notas), objetivos cumplidos/totales | ¿Qué resultados obtuvimos? ¿Qué proyectos no cumplieron metas? |
| Aprendizajes | lecciones, recomendaciones | ¿Qué lecciones debo tener en cuenta? |
| Salvedades | tipo y descripción | Evita dar por buenas cifras preliminares, no validadas o fuera de alcance |
| Trazabilidad | archivo fuente | Permite citar cada fila que devuelve SQL |

Decisiones de detalle:
- Los valores de los indicadores se guardan **como texto, tal como en el informe** ("≤ 6",
  "0 de 3", "39,5 min"), para no perder matices, y además como número cuando es posible
  (`linea_base_valor`, `resultado_valor`) para poder comparar u ordenar.
- `estado_meta` usa cuatro valores (`cumplida`, `parcialmente_cumplida`, `no_cumplida`,
  `sin_meta`) porque los informes usan los cuatro casos.
- Las listas (indicadores, lecciones, metodologías…) van en tablas hijas para poder filtrarlas
  y agregarlas con SQL.

Las cuatro fichas generadas están en [`data/fichas/`](data/fichas/).

## 5. Validación

- **Tests automáticos** (`python -m pytest`, 100 tests, sin consumir API; se ejecutan en
  GitHub Actions en Linux y Windows con cada push): lectura de PDF y
  Word, limpieza de tablas, secciones, búsqueda, base de datos, barreras del SQL, bucle del
  agente con el modelo simulado, memoria de conversación, cadena de modelos de respaldo,
  interfaz web y **fidelidad de las fichas generadas** (cada cifra existe en
  su informe; la ficha de la Cooperativa coincide con una ficha escrita a mano; las trampas
  conocidas quedan registradas como salvedades).
- **Preguntas de validación**: [`docs/VALIDACION.md`](docs/VALIDACION.md) recoge 14 preguntas
  de consultor —incluidas 6 preguntas trampa— con la respuesta esperada, redactada a partir de
  los informes, y la respuesta real del agente. La primera ronda destapó errores reales (por
  ejemplo, cifras atribuidas al indicador equivocado); cada uno se diagnosticó con la traza y se
  corrigió. Tras las rondas 2 y 3, las 14 preguntas tienen una respuesta correcta, incluidas las
  6 trampas.

## 6. Supuestos

- Los informes son la única fuente de verdad. El agente no usa conocimiento general sobre los
  clientes ni los sectores, aunque podría completar la respuesta.
- Cuando un informe distingue una cifra preliminar de una oficial, vale la oficial.
- Un objetivo "parcialmente cumplido" no cuenta como cumplido.
- El enunciado indica que el informe de la Clínica llega en Word; en el material recibido es
  un PDF exportado desde Word. Se soportan ambos formatos.
- Los informes siguen la estructura general observada (portada con datos, secciones
  numeradas, tablas de indicadores), aunque no idéntica. El código de proyecto sigue el
  patrón `PC-AAAA-NNN`.
- Los usuarios son consultores internos que preguntan en español, por consola.

## 7. Limitaciones conocidas

- **Cuota gratuita de Gemini**: unas 20 peticiones diarias por modelo, y cada pregunta usa
  entre 2 y 4. La cadena de cinco modelos alarga el margen (unas 30 preguntas al día), pero
  un uso real requiere la capa de pago. Al cambiar de modelo a mitad de una pregunta la
  respuesta sigue siendo válida, aunque su estilo puede variar.
- **Privacidad**: en la capa gratuita, Google puede usar los datos enviados para mejorar sus
  productos. Con informes reales de clientes debe usarse la capa de pago (o Vertex AI), que
  no los usa para entrenamiento.
- **Variabilidad del modelo**: la misma pregunta puede recibir respuestas con distinto nivel
  de detalle; por ejemplo, no siempre menciona la cifra preliminar descartada, aunque sí usa
  la oficial.
- **Búsqueda léxica**: sinónimos que no aparecen en los informes pueden no encontrarse en la
  primera búsqueda; el agente reformula, pero no está garantizado.
- **PDF escaneados**: no se hace OCR; un informe escaneado sin capa de texto no se puede leer.
- **Heurísticas de estructura**: la detección de encabezados y tablas funciona con estos
  informes; formatos muy distintos (varias columnas, tablas sin bordes) pueden requerir
  ajustes.
- **SQL**: se rechaza cualquier consulta que contenga `;`, aunque esté dentro de un texto.
- **Memoria de conversación limitada**: recuerda los últimos 6 intercambios (preguntas y
  respuestas, no los resultados de las herramientas). En la web se pierde al recargar la
  página.
- **Extracción no determinista**: regenerar una ficha puede producir redacciones distintas;
  la verificación de cifras y los tests de fidelidad acotan ese riesgo.

## 8. Estimación de costo (50 consultores)

**Consumo medido.** Cada respuesta del agente registra sus llamadas y tokens (se ven en la
traza). En las rondas 2 y 3 de validación (16 respuestas con modelos Flash) una pregunta
consumió en promedio **unos 14.000 tokens de entrada y 1.400 de salida** (incluidos los de
razonamiento), con entre 2 y 7 llamadas; las preguntas simples rondan los 4.000-6.000 tokens
y las comparativas llegan a 33.000. La entrada pesa más porque en cada paso se reenvían el
prompt de sistema, el esquema de la base y los fragmentos recuperados. Tras la ronda 3 las
salvedades se incluyeron en el prompt para ahorrar la llamada que el modelo hacía en casi
cada pregunta, así que el consumo real debería quedar algo por debajo.

**Supuestos del escenario.** 50 consultores × 10 preguntas al día × 22 días hábiles =
**11.000 preguntas al mes**, con 14.000 tokens de entrada y 1.400 de salida por pregunta
(el promedio medido, sin descontar la optimización).

| Modelo (capa de pago, precios de ai.google.dev al 30-09-2026) | Entrada / salida por 1M tokens | Costo por pregunta | **Costo mensual** |
|---|---|---|---|
| gemini-3.5-flash (modelo principal) | USD 1,50 / 9,00 | USD 0,034 | **≈ USD 370** |
| gemini-3.6/3.7/3.8-flash (precio promocional hasta el 31-12-2026) | USD 0,75 / 3,75 | USD 0,016 | ≈ USD 173 |
| gemini-3.6/3.7/3.8-flash (precio desde 2027) | USD 1,50 / 7,50 | USD 0,032 | ≈ USD 347 |
| gemini-2.5-flash (solo cuentas que aún lo tienen habilitado) | USD 0,30 / 2,50 | USD 0,008 | ≈ USD 85 |

## 9. Estructura del repositorio

```text
├── .github/workflows/       tests automáticos en GitHub Actions
├── data/
│   ├── informes/            informes de cierre (entrada)
│   └── fichas/              fichas generadas (JSON, entregable)
├── docs/
│   ├── PLAN.md              plan de trabajo y trampas detectadas en los informes
│   ├── VALIDACION.md        preguntas de validación y resultados
│   └── validacion/          preguntas (JSON) y transcripciones del agente
├── iniciar_agente.bat       lanzador de la consola del agente con doble clic (Windows)
├── iniciar_web.bat          lanzador de la interfaz web con doble clic (Windows)
├── scripts/run_validation.py
├── src/project_agent/       código (ver tabla de módulos); static/ tiene la página web
└── tests/                   tests automáticos y ficha golden escrita a mano
```
