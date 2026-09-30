"""Acceso al modelo de lenguaje (Google Gemini).

Todo el contacto con el proveedor pasa por este módulo, para que cambiar de
proveedor o de modelo no afecte al resto del código. Incluye:
- reintentos con espera exponencial ante errores transitorios (503 por demanda,
  429 por límite por minuto);
- una cadena de modelos de respaldo: si un modelo agotó su cuota diaria, reintentar
  no sirve y se pasa directamente al siguiente.
"""

from __future__ import annotations

import logging
import os
import time

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from project_agent.config import ROOT_DIR

# Se excluyen a propósito los modelos "lite": en la validación asignaron cifras a indicadores
# equivocados. Es preferible un error de cuota a una respuesta incorrecta.
# Cada modelo tiene su propia cuota diaria en la capa gratuita, así que la cadena también amplía la capacidad.
# gemini-2.5-flash no está: Google ya no lo ofrece a claves nuevas (responde 404).
DEFAULT_MODELS = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.8-flash", "gemini-3-flash-preview"]
RETRYABLE_STATUS = {429, 500, 503, 504}
MODEL_UNAVAILABLE_STATUS = 404  # el modelo no existe o no está habilitado para esta clave
MAX_ATTEMPTS_PER_MODEL = 2
REQUEST_TIMEOUT_MS = 90_000  # sin límite, una petición colgada bloquea al agente indefinidamente

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Fallo al consultar el modelo. `reason` permite mostrar un mensaje claro al usuario."""

    def __init__(self, message: str, reason: str = "otro"):
        super().__init__(message)
        self.reason = reason  # "cuota", "demanda", "configuracion" u "otro"


def _reason(error: Exception | None) -> str:
    if isinstance(error, httpx.TimeoutException):
        return "demanda"
    if isinstance(error, errors.APIError):
        if error.code == 429:
            return "cuota"
        if error.code in RETRYABLE_STATUS:
            return "demanda"
        if error.code == MODEL_UNAVAILABLE_STATUS:
            return "configuracion"
    return "otro"


_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        load_dotenv(ROOT_DIR / ".env")
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise LLMError("Falta GEMINI_API_KEY. Copia .env.example como .env y agrega tu clave.", "configuracion")
        _client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))
    return _client


def models_to_try() -> list[str]:
    """Modelos en orden de preferencia. GEMINI_MODELS permite cambiarlos sin tocar código."""
    load_dotenv(ROOT_DIR / ".env")
    configured = os.getenv("GEMINI_MODELS")
    return [m.strip() for m in configured.split(",") if m.strip()] if configured else DEFAULT_MODELS


def _daily_quota_exhausted(exc: errors.APIError) -> bool:
    return exc.code == 429 and "PerDay" in str(exc)


def generate(contents, config: types.GenerateContentConfig) -> types.GenerateContentResponse:
    """Llama al modelo con reintentos, recorriendo la cadena de respaldo si hace falta."""
    client = get_client()
    last_error: Exception | None = None
    for model in models_to_try():
        for attempt in range(MAX_ATTEMPTS_PER_MODEL):
            try:
                return client.models.generate_content(model=model, contents=contents, config=config)
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning("%s no respondió a tiempo (intento %d)", model, attempt + 1)
                continue
            except errors.APIError as exc:
                last_error = exc
                if exc.code == MODEL_UNAVAILABLE_STATUS:
                    logger.warning("%s no está disponible para esta clave; se usa el siguiente modelo", model)
                    break
                if exc.code not in RETRYABLE_STATUS:
                    raise LLMError(f"Error del proveedor ({model}): {exc}", _reason(exc)) from exc
                if _daily_quota_exhausted(exc):
                    logger.warning("%s agotó su cuota diaria; se usa el siguiente modelo", model)
                    break
                logger.warning("%s respondió %s (intento %d); se reintenta", model, exc.code, attempt + 1)
                time.sleep(min(5 * 2**attempt, 20))
    raise LLMError(f"Ningún modelo respondió tras varios intentos. Último error: {last_error}", _reason(last_error))
