"""Herramientas y bucle del agente, con el LLM simulado (sin llamadas a la API)."""

import pytest
from google.genai import types

from project_agent import agent as agent_module
from project_agent.agent import MAX_HISTORY_TURNS, Conversation, ProjectAgent
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


def test_sql_tool_warns_when_rows_are_not_tied_to_a_project(tools):
    unattributed = tools.run("consultar_fichas_sql", {"sql": "SELECT titulo, descripcion FROM lecciones"})
    attributed = tools.run("consultar_fichas_sql", {"sql": "SELECT codigo_proyecto, titulo FROM lecciones"})
    by_file = tools.run(
        "consultar_fichas_sql",
        {"sql": "SELECT p.archivo_fuente, l.titulo FROM lecciones l JOIN proyectos p USING (codigo_proyecto)"},
    )
    count = tools.run("consultar_fichas_sql", {"sql": "SELECT COUNT(*) FROM lecciones"})
    assert "codigo_proyecto" in unattributed.payload["advertencia"]
    assert "advertencia" not in attributed.payload
    assert "advertencia" not in by_file.payload
    assert COOP_FILE in by_file.sources
    assert "advertencia" not in count.payload


def test_single_project_filter_identifies_the_source(tools):
    output = tools.run(
        "consultar_fichas_sql", {"sql": "SELECT titulo, descripcion FROM lecciones WHERE codigo_proyecto = 'PC-2025-014'"}
    )
    assert output.sources == [COOP_FILE]
    assert "advertencia" not in output.payload


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


def test_agent_forces_final_answer_after_max_steps(tools, monkeypatch):
    def fake_generate(contents, config):
        tools_disabled = config.tool_config and config.tool_config.function_calling_config.mode == "NONE"
        if tools_disabled:
            return _model_turn(types.Part.from_text(text="Los informes no contienen ese dato."))
        return _model_turn(_call("buscar_en_informes", consulta="OEE"))

    monkeypatch.setattr(agent_module, "generate", fake_generate)
    answer = ProjectAgent(tools).ask("pregunta que no converge")
    assert len(answer.tool_calls) == agent_module.MAX_STEPS
    assert answer.usage.llm_calls == agent_module.MAX_STEPS + 1
    assert answer.text == "Los informes no contienen ese dato."


def test_system_prompt_lists_projects_with_their_caveats(tools):
    prompt = ProjectAgent(tools).config.system_instruction
    for code in ("PC-2025-014", "PC-2025-027", "PC-2025-033", "PC-2026-006"):
        assert code in prompt
    # Las salvedades clave quedan siempre a la vista del modelo.
    for caveat_type in ("[dato_no_oficial]", "[dato_no_validado]", "[resultado_no_atribuible]", "[documento_externo]"):
        assert caveat_type in prompt


# ------------------------------------------------------------------ memoria de conversación


def _text_of(content):
    return "".join(part.text or "" for part in content.parts)


def test_follow_up_questions_receive_previous_turns(tools, monkeypatch):
    seen = []

    def fake_generate(contents, config):
        seen.append(list(contents))
        return _model_turn(types.Part.from_text(text=f"respuesta {len(seen)}"))

    monkeypatch.setattr(agent_module, "generate", fake_generate)
    conversation = Conversation(ProjectAgent(tools))
    conversation.ask("¿Qué proyecto hicimos en retail?")
    conversation.ask("¿Y cuáles fueron sus lecciones?")

    first, second = seen
    assert len(first) == 1
    assert [c.role for c in second] == ["user", "model", "user"]
    assert _text_of(second[0]) == "¿Qué proyecto hicimos en retail?"
    assert _text_of(second[1]) == "respuesta 1"
    assert _text_of(second[2]) == "¿Y cuáles fueron sus lecciones?"


def test_history_is_limited_and_can_be_reset(tools, monkeypatch):
    seen = []

    def fake_generate(contents, config):
        seen.append(list(contents))
        return _model_turn(types.Part.from_text(text="ok"))

    monkeypatch.setattr(agent_module, "generate", fake_generate)
    conversation = Conversation(ProjectAgent(tools))
    for i in range(MAX_HISTORY_TURNS + 3):
        conversation.ask(f"pregunta {i}")
    # Solo viajan los últimos intercambios (pregunta + respuesta) más la pregunta actual.
    assert len(seen[-1]) == 2 * MAX_HISTORY_TURNS + 1

    conversation.reset()
    conversation.ask("pregunta nueva")
    assert len(seen[-1]) == 1
