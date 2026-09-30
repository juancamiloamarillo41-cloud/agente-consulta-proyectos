"""División de un informe en fragmentos citables por sección.

Se corta por secciones de primer nivel (1. Resumen, 5. Resultados, ...) en lugar
de por número fijo de palabras: la sección es la unidad natural de cita y mantiene
junto el contexto que condiciona los datos (p. ej. "todos los resultados
corresponden a la Línea 1" queda en el mismo fragmento que la tabla). Solo si una
sección es muy larga se divide en sus subsecciones.
"""

from __future__ import annotations

from project_agent.ingestion.models import Block, Chunk, Document

FRONT_MATTER_SECTION = "Datos generales del proyecto"
MAX_SECTION_WORDS = 900


def _render(blocks: list[Block]) -> str:
    return "\n\n".join(f"### {b.text}" if b.kind == "heading" else b.text for b in blocks)


def _pages(blocks: list[Block]) -> tuple[int, ...]:
    return tuple(sorted({b.page for b in blocks if b.page is not None}))


def _split_long_section(title: str, blocks: list[Block]) -> list[tuple[str, list[Block]]]:
    """Divide una sección larga en subsecciones; la introducción queda como pieza propia."""
    pieces: list[tuple[str, list[Block]]] = [(title, [])]
    for block in blocks:
        if block.kind == "heading" and block.level >= 2:
            pieces.append((f"{title} › {block.text}", []))
        pieces[-1][1].append(block)
    return [(name, body) for name, body in pieces if body]


def split_into_chunks(document: Document) -> list[Chunk]:
    sections: list[tuple[str, list[Block]]] = [(FRONT_MATTER_SECTION, [])]
    for block in document.blocks:
        if block.kind == "heading" and block.level == 1:
            sections.append((block.text, []))
        else:
            sections[-1][1].append(block)

    chunks: list[Chunk] = []
    header = f"[{document.project_code or 'sin código'} · {document.client} · {document.source_file}]"
    for title, blocks in sections:
        if not blocks:
            continue
        words = sum(len(b.text.split()) for b in blocks)
        pieces = _split_long_section(title, blocks) if words > MAX_SECTION_WORDS else [(title, blocks)]
        for name, body in pieces:
            chunks.append(
                Chunk(
                    chunk_id=f"{document.project_code or document.source_file}#{len(chunks) + 1}",
                    project_code=document.project_code,
                    client=document.client,
                    source_file=document.source_file,
                    section=name,
                    pages=_pages(body),
                    text=f"{header}\n## {name}\n\n{_render(body)}",
                )
            )
    return chunks
