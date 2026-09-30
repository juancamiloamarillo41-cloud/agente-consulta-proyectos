"""Agente de consulta: bucle de uso de herramientas con Gemini.

El bucle está escrito a mano (sin frameworks de agentes) porque es corto y así
cada paso es visible y defendible: el modelo pide herramientas, el código las
ejecuta, registra la traza y devuelve el resultado, hasta que el modelo responde
en texto. Si se alcanza el límite de pasos, se hace una última llamada con las
herramientas desactivadas para que responda con lo que ya obtuvo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from google.genai import types

from project_agent.llm import generate
from project_agent.storage.query import run_readonly_query
from project_agent.tools import ReportTools

MAX_STEPS = 6
FINAL_ANSWER_PROMPT = (
    "Se alcanzó el límite de consultas a herramientas. Responde ahora solo con la información ya "
    "obtenida, siguiendo las reglas. Si no encontraste el dato, di que los informes no lo contienen."
)

SYSTEM_PROMPT = """\
Eres el asistente de consulta de proyectos de Procesa Consultores. Respondes preguntas de consultores sobre los informes de cierre de proyectos anteriores.

Proyectos disponibles (código · cliente · sector · informe) y sus salvedades, que debes tener presentes al responder sobre cada proyecto:
{catalog}

Herramientas:
- consultar_fichas_sql: fichas estructuradas en SQLite. Úsala para listar, filtrar, contar o comparar (sector, gerente, fechas, metodologías, indicadores, cumplimiento de metas, lecciones, recomendaciones, salvedades).
- buscar_en_informes: texto original de los informes. Úsala para detalles, explicaciones, contexto y para verificar cifras.
Elige la herramienta según la pregunta; usa ambas cuando convenga (por ejemplo, SQL para ubicar proyectos y búsqueda para el detalle o para confirmar una cifra).

Reglas obligatorias:
1. Responde solo con información obtenida de las herramientas en esta conversación. Nunca uses conocimiento propio sobre los proyectos, los clientes ni el sector.
2. Cita la fuente de cada dato con el nombre del archivo del informe, por ejemplo: (Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf, 5. Resultados). Incluye la sección solo si viene en un resultado de buscar_en_informes (campo seccion); los datos de consultar_fichas_sql se citan solo con el archivo (campo fuentes). Nunca inventes nombres ni números de sección.
3. Si la información no está en los informes, dilo explícitamente ("Los informes no contienen información sobre ...") y no la supongas. Si solo tienes una parte, responde esa parte e indica qué falta. Antes de afirmar que un dato no está, haz una sola comprobación adicional con la otra herramienta o con otros términos (por ejemplo, la sección de Resultados o la tabla indicadores); si tampoco aparece, concluye que no está y no sigas buscando.
4. Al reportar resultados de un proyecto, ten en cuenta sus salvedades (están en el catálogo de arriba; no hace falta consultarlas de nuevo) y las notas de los indicadores: cifras preliminares frente a oficiales, alcance limitado (por ejemplo, una sola línea de producción), resultados no atribuibles al proyecto, datos no validados, pendientes y documentos externos no disponibles. Usa siempre la cifra oficial y menciona la salvedad relevante. Las salvedades no son una sección del informe: cítalas solo con el archivo.
5. No extrapoles ni generalices más allá de lo que dicen los informes. Si haces un cálculo simple (una suma, una diferencia), indícalo. No afirmes relaciones de causa y efecto que el informe no establezca. Al reportar alcances, exclusiones y salvedades, usa los mismos términos del informe, sin sinónimos. Nunca atribuyas un valor a un indicador o concepto cuyo nombre no venga en la misma fila o fragmento: si una consulta SQL no trae la columna que identifica cada valor (por ejemplo, indicadores.nombre), repítela incluyéndola.
6. Si una herramienta devuelve error, corrige la llamada y vuelve a intentarlo.
7. Responde en español, de forma breve y directa, en markdown simple y sin notación LaTeX (escribe ≤ o ≥, no $\\le$), y termina con una línea "Fuentes:" que liste solo los informes de los que tomaste datos (o "Fuentes: ninguna" si los informes no contienen la información).
"""


@dataclass
class ToolCallTrace:
    name: str
    args: dict[str, Any]
    summary: str
    seconds: float


@dataclass
class AgentAnswer:
    text: str
    tool_calls: list[ToolCallTrace] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)  # informes efectivamente recuperados por las herramientas
    usage: Usage = field(default_factory=lambda: Usage())


@dataclass
class Usage:
    """Consumo de la pregunta: base para estimar costos."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0  # incluye tokens de razonamiento, que se facturan como salida
    models: list[str] = field(default_factory=list)

    def add(self, response: types.GenerateContentResponse) -> None:
        self.llm_calls += 1
        meta = response.usage_metadata
        if meta:
            self.input_tokens += meta.prompt_token_count or 0
            self.output_tokens += (meta.candidates_token_count or 0) + (meta.thoughts_token_count or 0)
        if response.model_version and response.model_version not in self.models:
            self.models.append(response.model_version)


def _project_catalog(tools: ReportTools) -> str:
    """Catálogo de proyectos con sus salvedades.

    Las salvedades van en el prompt porque son lo que más errores evita (cifras preliminares,
    alcance limitado...) y el modelo las consultaba en casi todas las preguntas: tenerlas siempre
    presentes ahorra una llamada por pregunta. Con muchos proyectos habría que volver a consultarlas.
    """
    projects = run_readonly_query(
        "SELECT codigo_proyecto, cliente, sector, archivo_fuente FROM proyectos ORDER BY codigo_proyecto",
        tools.db_path,
    )
    caveats = run_readonly_query(
        "SELECT codigo_proyecto, tipo, descripcion FROM salvedades ORDER BY codigo_proyecto, rowid", tools.db_path
    )
    lines = []
    for row in projects.rows:
        lines.append(" · ".join(str(value) for value in row))
        lines.extend(f"    - [{tipo}] {descripcion}" for code, tipo, descripcion in caveats.rows if code == row[0])
    return "\n".join(lines)


class ProjectAgent:
    def __init__(self, tools: ReportTools | None = None):
        self.tools = tools or ReportTools()
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT.format(catalog=_project_catalog(self.tools)),
            tools=[types.Tool(function_declarations=[types.FunctionDeclaration(**d) for d in self.tools.declarations()])],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def ask(self, question: str) -> AgentAnswer:
        contents: list[types.Content] = [types.Content(role="user", parts=[types.Part.from_text(text=question)])]
        answer = AgentAnswer(text="")

        for _ in range(MAX_STEPS):
            response = generate(contents, self.config)
            answer.usage.add(response)
            calls = response.function_calls or []
            if not calls:
                answer.text = (response.text or "").strip() or "No pude generar una respuesta."
                return answer

            # Se conserva el turno del modelo completo (incluye las firmas de razonamiento que exige Gemini).
            contents.append(response.candidates[0].content)
            response_parts = []
            for call in calls:
                args = dict(call.args or {})
                start = time.perf_counter()
                output = self.tools.run(call.name, args)
                answer.tool_calls.append(ToolCallTrace(call.name, args, output.summary, time.perf_counter() - start))
                answer.sources.extend(s for s in output.sources if s not in answer.sources)
                response_parts.append(types.Part.from_function_response(name=call.name, response=output.payload))
            contents.append(types.Content(role="user", parts=response_parts))

        # Límite alcanzado: se fuerza una respuesta en texto con lo ya recuperado, sin más herramientas.
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=FINAL_ANSWER_PROMPT)]))
        final_config = self.config.model_copy(
            update={"tool_config": types.ToolConfig(function_calling_config=types.FunctionCallingConfig(mode="NONE"))}
        )
        response = generate(contents, final_config)
        answer.usage.add(response)
        answer.text = (response.text or "").strip() or "No pude completar la respuesta dentro del límite de pasos."
        return answer
