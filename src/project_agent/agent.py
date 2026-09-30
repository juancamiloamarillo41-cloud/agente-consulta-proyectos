"""Agente de consulta: bucle de uso de herramientas con Gemini.

El bucle está escrito a mano (sin frameworks de agentes) porque es corto y así
cada paso es visible y defendible: el modelo pide herramientas, el código las
ejecuta, registra la traza y devuelve el resultado, hasta que el modelo responde
en texto o se alcanza el límite de pasos.
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

SYSTEM_PROMPT = """\
Eres el asistente de consulta de proyectos de Procesa Consultores. Respondes preguntas de consultores sobre los informes de cierre de proyectos anteriores.

Proyectos disponibles (código · cliente · sector · informe):
{catalog}

Herramientas:
- consultar_fichas_sql: fichas estructuradas en SQLite. Úsala para listar, filtrar, contar o comparar (sector, gerente, fechas, metodologías, indicadores, cumplimiento de metas, lecciones, recomendaciones, salvedades).
- buscar_en_informes: texto original de los informes. Úsala para detalles, explicaciones, contexto y para verificar cifras.
Elige la herramienta según la pregunta; usa ambas cuando convenga (por ejemplo, SQL para ubicar proyectos y búsqueda para el detalle o para confirmar una cifra).

Reglas obligatorias:
1. Responde solo con información obtenida de las herramientas en esta conversación. Nunca uses conocimiento propio sobre los proyectos, los clientes ni el sector.
2. Cita la fuente de cada dato con el nombre del archivo del informe (y la sección si la conoces), por ejemplo: (Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf, 5. Resultados).
3. Si la información no está en los informes, dilo explícitamente ("Los informes no contienen información sobre ...") y no la supongas. Si solo tienes una parte, responde esa parte e indica qué falta.
4. Antes de reportar resultados de un proyecto, revisa sus salvedades (tabla salvedades o notas del informe): cifras preliminares frente a oficiales, alcance limitado (por ejemplo, una sola línea de producción), resultados no atribuibles al proyecto, datos no validados, pendientes y documentos externos no disponibles. Usa siempre la cifra oficial y menciona la salvedad relevante.
5. No extrapoles ni generalices más allá de lo que dicen los informes. Si haces un cálculo simple (una suma, una diferencia), indícalo.
6. Si una herramienta devuelve error, corrige la llamada y vuelve a intentarlo.
7. Responde en español, de forma breve y directa, y termina con una línea "Fuentes:" que liste solo los informes de los que tomaste datos (o "Fuentes: ninguna" si los informes no contienen la información).
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


def _project_catalog(tools: ReportTools) -> str:
    result = run_readonly_query(
        "SELECT codigo_proyecto, cliente, sector, archivo_fuente FROM proyectos ORDER BY codigo_proyecto",
        tools.db_path,
    )
    return "\n".join(" · ".join(str(value) for value in row) for row in result.rows)


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

        answer.text = (
            "No pude completar la respuesta dentro del límite de pasos. "
            "Intenta reformular la pregunta de forma más específica."
        )
        return answer
