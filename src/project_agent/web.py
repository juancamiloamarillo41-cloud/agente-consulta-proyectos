"""Interfaz web sencilla: API REST (FastAPI) y una página HTML sin dependencias externas.

La web no agrega lógica: llama a `ProjectAgent.ask()` y muestra lo mismo que la consola
(respuesta, fuentes, herramientas usadas y consumo). Por seguridad escucha solo en
localhost, y el texto del modelo se escapa antes de convertir su markdown a HTML.

Uso:
    iniciar_web.bat                 # doble clic en Windows: arranca y abre el navegador
    agente-proyectos-web            # http://127.0.0.1:8000, abre el navegador
    agente-proyectos-web --sin-navegador
"""

from __future__ import annotations

import html
import re
import socket
import time
from pathlib import Path
from typing import Callable

import markdown
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from project_agent.agent import AgentAnswer, ProjectAgent
from project_agent.llm import LLMError
from project_agent.storage.query import run_readonly_query

STATIC_DIR = Path(__file__).with_name("static")
MAX_QUESTION_CHARS = 1000
FRIENDLY_ERRORS = {
    "cuota": "Se agotó la cuota diaria del modelo. Intenta más tarde o usa una clave con facturación activa.",
    "demanda": "El modelo está saturado en este momento. Intenta de nuevo en unos minutos.",
    "configuracion": "El modelo no está configurado correctamente (revisa GEMINI_API_KEY y GEMINI_MODELS).",
    "otro": "No se pudo consultar el modelo.",
}


# Una línea que no es de lista seguida de un elemento de lista ("Fuentes:\n- a.pdf").
_LIST_WITHOUT_BLANK_LINE = re.compile(r"^(?!\s*(?:[-*+]|\d+\.)\s)(\S.*)\n(?=\s*(?:[-*+]|\d+\.)\s)", re.MULTILINE)


class Question(BaseModel):
    pregunta: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)


def render_markdown(text: str) -> str:
    """Markdown a HTML sin permitir HTML crudo proveniente del modelo.

    El modelo suele escribir una lista justo debajo de un párrafo, sin línea en blanco; la
    librería markdown no la reconoce como lista en ese caso, así que se inserta la línea.
    """
    text = _LIST_WITHOUT_BLANK_LINE.sub(r"\1\n\n", text)
    return markdown.markdown(html.escape(text, quote=False), extensions=["extra", "sane_lists"])


def answer_to_json(answer: AgentAnswer, seconds: float) -> dict:
    return {
        "respuesta_html": render_markdown(answer.text),
        "respuesta_texto": answer.text,
        "herramientas": [
            {"nombre": c.name, "argumentos": c.args, "resumen": c.summary, "segundos": round(c.seconds, 3)}
            for c in answer.tool_calls
        ],
        "fuentes": answer.sources,
        "uso": {
            "llamadas": answer.usage.llm_calls,
            "tokens_entrada": answer.usage.input_tokens,
            "tokens_salida": answer.usage.output_tokens,
            "modelos": answer.usage.models,
        },
        "segundos": round(seconds, 1),
    }


def create_app(agent_factory: Callable[[], ProjectAgent] = ProjectAgent) -> FastAPI:
    """Crea la aplicación. El agente se construye una sola vez, en la primera petición que lo necesita."""
    app = FastAPI(title="Agente de consulta de proyectos", docs_url="/api/docs", redoc_url=None)
    state: dict[str, ProjectAgent] = {}

    def agent() -> ProjectAgent:
        if "agent" not in state:
            state["agent"] = agent_factory()
        return state["agent"]

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/proyectos")
    def projects() -> list[dict]:
        result = run_readonly_query(
            "SELECT codigo_proyecto, cliente, sector, archivo_fuente FROM proyectos ORDER BY codigo_proyecto",
            agent().tools.db_path,
        )
        return [dict(zip(result.columns, row)) for row in result.rows]

    @app.post("/api/preguntar")
    def ask(question: Question) -> dict:
        text = question.pregunta.strip()
        if not text:
            raise HTTPException(status_code=422, detail="La pregunta está vacía.")
        start = time.perf_counter()
        try:
            answer = agent().ask(text)
        except LLMError as exc:
            # Cuota agotada o modelo saturado: mensaje claro para el usuario y detalle técnico aparte.
            detail = {"mensaje": FRIENDLY_ERRORS.get(exc.reason, FRIENDLY_ERRORS["otro"]), "tecnico": str(exc)[:400]}
            raise HTTPException(status_code=503, detail=detail) from exc
        return answer_to_json(answer, time.perf_counter() - start)

    return app


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    import argparse
    import threading
    import webbrowser

    import uvicorn

    parser = argparse.ArgumentParser(description="Interfaz web del agente de consulta de proyectos.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador automáticamente.")
    args = parser.parse_args()
    url = f"http://127.0.0.1:{args.port}"

    if _port_in_use(args.port):
        # Lo normal es que la web ya esté abierta en otra ventana: basta con mostrarla.
        print(f"Ya hay un servidor en {url}; se abre en el navegador.")
        if not args.sin_navegador:
            webbrowser.open(url)
        return

    print(f"Interfaz web en {url} · cierra esta ventana o pulsa Ctrl+C para detenerla.")
    if not args.sin_navegador:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
