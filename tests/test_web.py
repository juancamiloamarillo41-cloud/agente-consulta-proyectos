"""Interfaz web con el agente simulado (sin llamadas a la API)."""

import pytest
from fastapi.testclient import TestClient

from project_agent.agent import AgentAnswer, ToolCallTrace, Usage
from project_agent.config import FICHAS_DIR, REPORTS_DIR
from project_agent.llm import LLMError
from project_agent.storage.repository import rebuild_db_from_json
from project_agent.tools import ReportTools
from project_agent.web import create_app, render_markdown

COOP_FILE = "Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf"


class FakeAgent:
    def __init__(self, tools, answer=None, error=None):
        self.tools, self.answer, self.error = tools, answer, error
        self.questions = []

    def ask(self, question):
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture(scope="module")
def tools(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "fichas.db"
    rebuild_db_from_json(FICHAS_DIR, db)
    return ReportTools(REPORTS_DIR, db)


def _answer():
    return AgentAnswer(
        text="La productividad pasó de **85** a **124** (+46%).\n\nFuentes: " + COOP_FILE,
        tool_calls=[ToolCallTrace("consultar_fichas_sql", {"sql": "SELECT 1"}, "1 filas", 0.01)],
        sources=[COOP_FILE],
        usage=Usage(llm_calls=2, input_tokens=4000, output_tokens=500, models=["gemini-3.6-flash"]),
    )


def test_index_serves_the_page(tools):
    client = TestClient(create_app(lambda: FakeAgent(tools)))
    response = client.get("/")
    assert response.status_code == 200
    assert "Consulta de proyectos" in response.text


def test_projects_endpoint_lists_the_four_reports(tools):
    client = TestClient(create_app(lambda: FakeAgent(tools)))
    codes = [p["codigo_proyecto"] for p in client.get("/api/proyectos").json()]
    assert codes == ["PC-2025-014", "PC-2025-027", "PC-2025-033", "PC-2026-006"]


def test_ask_returns_answer_trace_sources_and_usage(tools):
    fake = FakeAgent(tools, answer=_answer())
    client = TestClient(create_app(lambda: fake))
    data = client.post("/api/preguntar", json={"pregunta": "  ¿Productividad?  "}).json()
    assert fake.questions == ["¿Productividad?"]
    assert "<strong>85</strong>" in data["respuesta_html"]
    assert data["fuentes"] == [COOP_FILE]
    assert data["herramientas"][0] == {"nombre": "consultar_fichas_sql", "argumentos": {"sql": "SELECT 1"}, "resumen": "1 filas", "segundos": 0.01}
    assert data["uso"]["llamadas"] == 2 and data["uso"]["modelos"] == ["gemini-3.6-flash"]


@pytest.mark.parametrize("payload", [{"pregunta": ""}, {"pregunta": "   "}, {"pregunta": "x" * 1001}, {}])
def test_invalid_questions_are_rejected(tools, payload):
    client = TestClient(create_app(lambda: FakeAgent(tools, answer=_answer())))
    assert client.post("/api/preguntar", json=payload).status_code == 422


def test_model_unavailable_returns_503_with_friendly_message(tools):
    fake = FakeAgent(tools, error=LLMError("429 RESOURCE_EXHAUSTED ...", "cuota"))
    client = TestClient(create_app(lambda: fake))
    response = client.post("/api/preguntar", json={"pregunta": "hola"})
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "cuota diaria" in detail["mensaje"]
    assert detail["tecnico"].startswith("429")


def test_agent_is_built_once(tools):
    built = []

    def factory():
        built.append(1)
        return FakeAgent(tools, answer=_answer())

    client = TestClient(create_app(factory))
    for _ in range(3):
        client.post("/api/preguntar", json={"pregunta": "hola"})
    assert len(built) == 1


def test_list_right_after_a_paragraph_is_rendered_as_list():
    rendered = render_markdown("Fuentes:\n- a.pdf\n- b.pdf")
    assert "<li>a.pdf</li>" in rendered and "<li>b.pdf</li>" in rendered
    nested = render_markdown("Resultado:\n1. uno\n2. dos")
    assert "<ol>" in nested


def test_model_html_is_escaped():
    rendered = render_markdown('Texto <script>alert("x")</script> y **negrita**')
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "<strong>negrita</strong>" in rendered
