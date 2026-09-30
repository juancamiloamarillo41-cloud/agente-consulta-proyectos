"""Normalización de texto en español, compartida por la búsqueda y el SQL."""

from __future__ import annotations

import unicodedata


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: 'Línea' y 'linea' deben coincidir."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
