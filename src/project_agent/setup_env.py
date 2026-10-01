"""Configuración guiada de la clave de Gemini.

Los lanzadores (`iniciar_agente.bat`, `iniciar_web.bat`) ejecutan este módulo antes de
arrancar. Si no hay un `.env` con GEMINI_API_KEY, pide la clave en la ventana (visible, para
poder comprobar que se pegó completa), comprueba con Google que sea válida y crea el archivo a partir de `.env.example`.

Uso manual:
    python -m project_agent.setup_env
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable

from dotenv import dotenv_values

from project_agent.config import ROOT_DIR

KEY_NAME = "GEMINI_API_KEY"
MAX_ATTEMPTS = 3
API_KEY_URL = "https://aistudio.google.com/apikey"


def current_key(env_path: Path) -> str:
    if not env_path.exists():
        return ""
    return (dotenv_values(env_path).get(KEY_NAME) or "").strip()


def clean_key(raw: str) -> str:
    """Quita comillas y caracteres de control (p. ej. el ^V que deja Ctrl+V en algunas consolas)."""
    key = "".join(ch for ch in raw if ch.isprintable() or ch.isspace())
    return key.strip().strip('"').strip("'")


def validate_key(key: str) -> bool | None:
    """True si Google acepta la clave, False si la rechaza, None si no se pudo comprobar.

    Lista los modelos disponibles: no genera contenido, así que no consume la cuota de preguntas.
    """
    from google import genai
    from google.genai import errors

    try:
        # El cliente debe quedar en una variable: si es temporal, se cierra antes de enviar la consulta.
        client = genai.Client(api_key=key)
        next(iter(client.models.list()), None)
        return True
    except errors.ClientError as exc:
        if exc.code in (400, 401, 403):
            return False
        return None
    except Exception:  # sin conexión, proxy, etc.
        return None


def write_env(env_path: Path, example_path: Path, key: str) -> None:
    """Crea o completa `.env` con la clave, conservando el resto de la plantilla."""
    base = env_path if env_path.exists() else example_path
    lines = base.read_text(encoding="utf-8").splitlines() if base.exists() else []
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{KEY_NAME}="):
            lines[i] = f"{KEY_NAME}={key}"
            replaced = True
    if not replaced:
        lines.append(f"{KEY_NAME}={key}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_env(
    root: Path = ROOT_DIR,
    ask: Callable[[str], str] = input,
    validate: Callable[[str], bool | None] = validate_key,
    out: Callable[[str], None] = print,
) -> bool:
    """Garantiza que exista una clave en `.env`. Devuelve False si no se pudo configurar."""
    env_path, example_path = root / ".env", root / ".env.example"
    if current_key(env_path):
        return True

    out("No se encontró la clave de Gemini (archivo .env).")
    out(f"Consigue una gratis en {API_KEY_URL} y pégala aquí (clic derecho en la ventana).")
    for attempt in range(1, MAX_ATTEMPTS + 1):
        key = clean_key(ask("Clave de Gemini: "))
        if not key:
            out("No se recibió ninguna clave. Pégala con clic derecho y pulsa Enter.")
            continue
        if any(ch.isspace() for ch in key):
            out("La clave no puede tener espacios. Vuelve a pegarla.")
            continue
        valid = validate(key)
        if valid is False:
            out(
                f"Google rechazó esa clave de {len(key)} caracteres (intento {attempt} de {MAX_ATTEMPTS}). "
                "Revisa que esté completa."
            )
            continue
        write_env(env_path, example_path, key)
        suffix = f"…{key[-4:]}" if len(key) > 4 else ""
        if valid is None:
            out(f"No se pudo comprobar la clave (¿sin conexión?); se guardó igualmente {suffix}.")
        else:
            out(f"Clave válida {suffix}. Se guardó en .env; no tendrás que volver a escribirla.")
        return True

    out("No se configuró la clave. Puedes volver a intentarlo o editar .env a mano.")
    return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return 0 if ensure_env() else 1


if __name__ == "__main__":
    sys.exit(main())
