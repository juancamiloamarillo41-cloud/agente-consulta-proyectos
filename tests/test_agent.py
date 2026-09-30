"""Herramientas y bucle del agente, con el LLM simulado (sin llamadas a la API)."""

import pytest
from google.genai import types

from project_agent import agent as agent_module
from project_agent.agent import ProjectAgent
from project_agent.config import FICHAS_DIR, REPORTS_DIR
from project_agent.storage.repository import rebuild_db_from_json
from project_agent.tools import ReportTools

COOP_FILE = "Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf"


@pytest.fixture(scope="module")
def tools(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "fichas.db"
    rebuild_db_from_json(FICHAS_DIR, db)
    return ReportTools(REPORTS_DIR, db)


def _model_turn(*parts):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=list(parts)))])


def _call(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


# ------------------------------------------------------------------ herramientas


def test_search_tool_returns_citations(tools):
    output = tools.run("buscar_en_informes", {"consulta": "tasa de abandono", "codigo_proyecto": "PC-2025-014"})
    first = output.payload["resultados"][0]
    assert first["archivo"] == COOP_FILE and first["cita"].startswith(COOP_FILE)
    assert output.sources == [COOP_FILE]


def test_search_tool_reports_empty_results(tools):
    output = tools.run("buscar_en_informes", {"consulta": "criptomonedas"})
    assert output.payload["resultados"] == [] and output.summary == "0 fragmentos"


def test_sql_tool_adds_sources(tools):
    output = tools.run("consultar_fichas_sql", {"sql": "SELECT codigo_proyecto, cliente FROM proyectos WHERE sector LIKE '%financ%'"})
    assert output.payload["filas"][0][0] == "PC-2025-014"
    assert output.payload["fuentes"] == {"PC-2025-014": COOP_FILE}
    assert output.sources == [COOP_FILE]


def test_sql_tool_warns_when_indicator_values_come_without_names(tools):
    unnamed = tools.run("consultar_fichas_sql", {"sql": "SELECT codigo_proyecto, resultado FROM indicadores"})
    named = tools.run("consultar_fichas_sql", {"sql": "SELECT codigo_proyecto, nombre, resultado FROM indicadores"})
    assert "advertencia" in unnamed.payload
    assert "advertencia" not in named.payload


def test_sql_tool_returns_errors_to_the_model(tools):
    output = tools.run("consultar_fichas_sql", {"sql": "DELETE FROM proyectos"})
    assert "error" in output.payload


def test_unknown_tool_and_bad_arguments(tools):
    assert "error" in tools.run("borrar_todo", {}).payload
    assert "error" in tools.run("consultar_fichas_sql", {"consulta": "x"}).payload


def test_sql_declaration_includes_schema(tools):
    sql_tool = next(d for d in tools.declarations() if d["name"] == "consultar_fichas_sql")
    assert "CREATE TABLE salvedades" in sql_tool["description"]


# ------------------------------------------------------------------ bucle


def test_agent_executes_tools_and_records_trace(tools, monkeypatch):
    calls = []
    scripted = iter([
        _model_turn(_call("consultar_fichas_sql", sql="SELECT codigo_proyecto FROM proyectos WHERE sector LIKE '%financ%'")),
        _model_turn(types.Part.from_text(text="Respuesta final.\nFuentes: " + COOP_FILE)),
    ])

    def fake_generate(contents, config):
        calls.append(list(contents))
        return next(scripted)

    monkeypatch.setattr(agent_module, "generate", fake_generate)
    answer = ProjectAgent(tools).ask("¿Qué proyectos hicimos en servicios financieros?")

    assert answer.text.startswith("Respuesta final.")
    assert [c.name for c in answer.tool_calls] == ["consultar_fichas_sql"]
    assert answer.tool_calls[0].summary == "1 filas"
    assert answer.sources == [COOP_FILE]
    # En la segunda llamada el modelo recibe su propio turno y el resultado de la herramienta.
    second_call = calls[1]
    assert second_call[1].role == "model"
    assert second_call[2].parts[0].function_response.response["fuentes"] == {"PC-2025-014": COOP_FILE}


def test_agent_stops_after_max_steps(tools, monkeypatch):
    monkeypatch.setattr(
        agent_module, "generate", lambda contents, config: _model_turn(_call("buscar_en_informes", consulta="OEE"))
    )
    answer = ProjectAgent(tools).ask("pregunta que no converge")
    assert len(answer.tool_calls) == agent_module.MAX_STEPS
    assert "límite de pasos" in answer.text


def test_system_prompt_lists_projects(tools):
    prompt = ProjectAgent(tools).config.system_instruction
    for code in ("PC-2025-014", "PC-2025-027", "PC-2025-033", "PC-2026-006"):
        assert code in prompt
