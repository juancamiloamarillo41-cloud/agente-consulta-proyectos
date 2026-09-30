"""Pasa el set de preguntas de validación por el agente y guarda las transcripciones.

Cada pregunta trae la respuesta esperada, redactada a mano a partir de los
informes. La comparación es manual (ver docs/VALIDACION.md): el script solo
ejecuta y deja registro de respuesta, traza y consumo de tokens.

Uso:
    python scripts/run_validation.py            # todas
    python scripts/run_validation.py 3 7        # solo las preguntas 3 y 7
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from project_agent.agent import ProjectAgent  # noqa: E402
from project_agent.cli import render  # noqa: E402
from project_agent.llm import LLMError  # noqa: E402

QUESTIONS_PATH = ROOT / "docs" / "validacion" / "preguntas.json"
OUTPUT_DIR = ROOT / "docs" / "validacion" / "transcripciones"
PAUSE_SECONDS = 20  # la capa gratuita limita las peticiones por minuto


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    selected = {int(a) for a in argv}
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    agent = ProjectAgent()

    for item in questions:
        if selected and item["id"] not in selected:
            continue
        print(f"[{item['id']}] {item['pregunta']}", flush=True)
        try:
            answer = agent.ask(item["pregunta"])
        except LLMError as exc:
            print(f"   ERROR: {exc}", flush=True)
            continue
        transcript = (
            f"# Pregunta {item['id']}: {item['pregunta']}\n\n"
            f"**Respuesta esperada (según los informes):** {item['esperado']}\n\n"
            f"## Respuesta del agente\n\n```text\n{render(answer)}\n```\n"
        )
        (OUTPUT_DIR / f"{item['id']:02d}.md").write_text(transcript, encoding="utf-8")
        print(f"   ok · {answer.usage.llm_calls} llamadas · {answer.usage.input_tokens}+{answer.usage.output_tokens} tokens", flush=True)
        time.sleep(PAUSE_SECONDS)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
