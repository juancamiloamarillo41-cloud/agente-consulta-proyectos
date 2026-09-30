"""Interfaz de consola del agente.

Uso:
    python -m project_agent                      # modo interactivo, con memoria de la conversación
    python -m project_agent "¿Qué hicimos en salud?"   # una sola pregunta
"""

from __future__ import annotations

import argparse
import json
import sys

from project_agent.agent import AgentAnswer, Conversation, ProjectAgent
from project_agent.llm import LLMError

EXIT_WORDS = {"salir", "exit", "quit", "q"}
RESET_WORDS = {"nueva", "nuevo", "reiniciar"}


def _format_args(args: dict) -> str:
    if set(args) == {"sql"}:
        return " ".join(str(args["sql"]).split())
    return json.dumps(args, ensure_ascii=False)


def render(answer: AgentAnswer) -> str:
    lines = [answer.text, "", "── Trazabilidad ─────────────────────────────"]
    if not answer.tool_calls:
        lines.append("  (no se usaron herramientas)")
    for i, call in enumerate(answer.tool_calls, start=1):
        lines.append(f"  {i}. {call.name}: {_format_args(call.args)}")
        lines.append(f"     → {call.summary} [{call.seconds:.2f}s]")
    if answer.sources:
        lines.append("  Informes recuperados por las herramientas:")
        lines.extend(f"   - {source}" for source in answer.sources)
    usage = answer.usage
    lines.append(
        f"  Modelo: {', '.join(usage.models) or '-'} · {usage.llm_calls} llamadas · "
        f"{usage.input_tokens} tokens de entrada · {usage.output_tokens} de salida"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not sys.stdin.isatty() and hasattr(sys.stdin, "reconfigure"):
        # Entrada por tubería: en Windows llegaría con la página de códigos antigua y, desde
        # PowerShell, con una marca BOM al inicio. utf-8-sig lee UTF-8 y descarta esa marca.
        sys.stdin.reconfigure(encoding="utf-8-sig")
    parser = argparse.ArgumentParser(description="Consulta los informes de cierre de proyectos.")
    parser.add_argument("pregunta", nargs="*", help="Pregunta a responder (sin argumentos: modo interactivo).")
    args = parser.parse_args(argv)

    try:
        agent = ProjectAgent()
    except Exception as exc:  # base inexistente, clave faltante, etc.
        print(f"No se pudo iniciar el agente: {exc}", file=sys.stderr)
        return 1

    if args.pregunta:
        questions = [" ".join(args.pregunta)]
    else:
        print(
            "Agente de proyectos de Procesa Consultores. Escribe tu pregunta; puedes hacer preguntas de "
            "seguimiento.\n'nueva' empieza otra conversación · 'salir' para terminar."
        )
        questions = None
    conversation = Conversation(agent)

    while True:
        if questions is not None:
            if not questions:
                return 0
            question = questions.pop(0)
        else:
            try:
                # lstrip: algunas terminales anteponen una marca invisible (BOM) al texto recibido.
                question = input("\n> ").strip().lstrip("﻿​").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not question:
                continue
            if question.lower() in EXIT_WORDS:
                return 0
            if question.lower() in RESET_WORDS:
                conversation.reset()
                print("Nueva conversación.")
                continue
        try:
            print(render(conversation.ask(question)))
        except LLMError as exc:
            print(f"Error al consultar el modelo: {exc}", file=sys.stderr)
            if questions is not None:
                return 1
