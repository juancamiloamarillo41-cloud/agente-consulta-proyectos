"""Estructuras intermedias comunes a todos los formatos de informe.

PDF y Word se convierten a una misma lista de bloques, de modo que el resto del
sistema (secciones, búsqueda, extracción de fichas) no depende del formato.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal["heading", "text", "table"]


@dataclass
class Block:
    kind: BlockKind
    text: str
    page: int | None = None  # Word no tiene paginación fija: None
    level: int = 1  # solo para encabezados: 1 = sección, 2 = subsección


@dataclass
class Document:
    source_file: str  # nombre del archivo, usado como cita
    project_code: str | None
    title: str
    client: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Texto completo en formato markdown ligero (tablas como tablas markdown)."""
        parts = []
        for block in self.blocks:
            parts.append(f"## {block.text}" if block.kind == "heading" else block.text)
        return "\n\n".join(parts)


@dataclass
class Chunk:
    """Fragmento citable de un informe: una sección (o subsección) completa."""

    chunk_id: str
    project_code: str | None
    client: str
    source_file: str
    section: str
    pages: tuple[int, ...]
    text: str

    @property
    def citation(self) -> str:
        pages = ""
        if self.pages:
            pages = f", pág. {self.pages[0]}" if len(self.pages) == 1 else f", págs. {self.pages[0]}-{self.pages[-1]}"
        return f"{self.source_file} — {self.section}{pages}"
