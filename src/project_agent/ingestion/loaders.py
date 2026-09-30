"""Lectores de informes en PDF y Word hacia la representación común de bloques.

Decisiones:
- PDF con PyMuPDF: da posición, tamaño y negrita de cada línea (para detectar
  encabezados sin depender de la numeración) y detecta tablas.
- Word con python-docx: recorre el cuerpo en orden, respetando la posición de las
  tablas entre párrafos; encabezados por estilo o por formato.
- Los encabezados y pies de página se descartan: repiten texto en cada página y
  contaminan la búsqueda.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import docx
import pymupdf
from docx.table import Table
from docx.text.paragraph import Paragraph

from project_agent.config import REPORTS_DIR, SUPPORTED_EXTENSIONS
from project_agent.ingestion.models import Block, Document
from project_agent.ingestion.tables import clean_rows, rows_to_markdown

PROJECT_CODE_RE = re.compile(r"PC-\d{4}-\d{3}")
SUBSECTION_RE = re.compile(r"^\d+\.\d+")
NUMBERED_HEADING_RE = re.compile(r"^(\d+(\.\d+)*\.?|Anexo\s+\w+\.?)\s+\S")
BULLET_CHARS = ("•", "·", "-", "–", "▪", "◦")

# Franja inferior de la página (en puntos) donde está el pie de página.
FOOTER_MARGIN_PT = 50
BOLD_FLAG = 16


def _heading_level(text: str) -> int:
    return 2 if SUBSECTION_RE.match(text) else 1


# --------------------------------------------------------------------------- PDF


def _pdf_font_stats(pdf: pymupdf.Document) -> tuple[float, float]:
    """Devuelve (tamaño de cuerpo de texto, tamaño del título).

    El cuerpo es el tamaño con más caracteres; el título, el mayor de la página 1.
    """
    sizes: Counter[float] = Counter()
    for page in pdf:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                for span in line["spans"]:
                    sizes[round(span["size"], 1)] += len(span["text"].strip())
    body_size = sizes.most_common(1)[0][0]
    first_page_sizes = [
        span["size"]
        for block in pdf[0].get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    ]
    return body_size, max(first_page_sizes)


def _join_lines(lines: list[str]) -> list[str]:
    """Une líneas de un bloque en párrafos; cada viñeta inicia un párrafo nuevo."""
    paragraphs: list[str] = []
    for line in lines:
        if not paragraphs or line.startswith(BULLET_CHARS):
            paragraphs.append(line)
        elif paragraphs[-1].endswith("-") and not paragraphs[-1].endswith(" -"):
            paragraphs[-1] = paragraphs[-1][:-1] + line
        else:
            paragraphs[-1] += " " + line
    return paragraphs


def _load_pdf(path: Path) -> tuple[list[Block], str, str]:
    pdf = pymupdf.open(path)
    body_size, title_size = _pdf_font_stats(pdf)
    blocks: list[Block] = []
    title_lines: list[str] = []
    subtitle = ""

    for page_number, page in enumerate(pdf, start=1):
        tables = page.find_tables().tables
        table_rects = [pymupdf.Rect(t.bbox) for t in tables]
        positioned: list[tuple[float, Block]] = [
            (t.bbox[1], Block("table", rows_to_markdown(clean_rows(t.extract())), page_number))
            for t in tables
        ]

        for raw_block in page.get_text("dict")["blocks"]:
            text_lines: list[str] = []
            block_y = raw_block["bbox"][1]
            for line in raw_block.get("lines", []):
                rect = pymupdf.Rect(line["bbox"])
                text = "".join(span["text"] for span in line["spans"]).strip()
                if not text or rect.y0 > page.rect.height - FOOTER_MARGIN_PT:
                    continue
                center = pymupdf.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                if any(center in table_rect for table_rect in table_rects):
                    continue  # ya incluido como tabla markdown

                span = next(s for s in line["spans"] if s["text"].strip())
                size, bold = span["size"], bool(span["flags"] & BOLD_FLAG)
                if page_number == 1 and abs(size - title_size) < 0.5:
                    title_lines.append(text)
                elif page_number == 1 and title_lines and not subtitle and not bold and size > body_size * 1.05:
                    subtitle = text
                if bold and body_size * 1.05 < size < title_size - 0.5:
                    if text_lines:
                        positioned += [(block_y, Block("text", p, page_number)) for p in _join_lines(text_lines)]
                        text_lines = []
                    positioned.append((rect.y0, Block("heading", text, page_number, _heading_level(text))))
                    block_y = rect.y1
                else:
                    text_lines.append(text)
            if text_lines:
                positioned += [(block_y, Block("text", p, page_number)) for p in _join_lines(text_lines)]

        # Orden estable por posición vertical (las tablas se intercalan en su sitio).
        blocks.extend(block for _, block in sorted(positioned, key=lambda item: item[0]))

    return _merge_broken_paragraphs(blocks), " ".join(title_lines), subtitle


def _merge_broken_paragraphs(blocks: list[Block]) -> list[Block]:
    """Une párrafos que el PDF partió en varios bloques (típico de documentos exportados desde Word).

    Se une cuando el bloque anterior no termina en puntuación de cierre y el
    siguiente continúa en minúscula, en la misma página.
    """
    merged: list[Block] = []
    for block in blocks:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.kind == block.kind == "text"
            and previous.page == block.page
            and not previous.text.endswith((".", ":", ";", "?", "!"))
            and block.text[:1].islower()
        ):
            previous.text = f"{previous.text} {block.text}"
        else:
            merged.append(block)
    return merged


# -------------------------------------------------------------------------- Word


def _docx_table_rows(table: Table) -> list[list[str]]:
    rows = []
    for row in table.rows:
        cells, seen = [], set()
        for cell in row.cells:
            # python-docx repite el mismo objeto de celda en celdas combinadas horizontales.
            if id(cell._tc) in seen:
                continue
            seen.add(id(cell._tc))
            cells.append(cell.text)
        rows.append(cells)
    return rows


def _is_docx_heading(paragraph: Paragraph) -> tuple[bool, int]:
    style = (paragraph.style.name if paragraph.style is not None else "").lower()
    match = re.match(r"(heading|título|titulo)\s*(\d)", style)
    if match:
        return True, int(match.group(2))
    runs = [run for run in paragraph.runs if run.text.strip()]
    text = paragraph.text.strip()
    if runs and all(run.bold for run in runs) and NUMBERED_HEADING_RE.match(text) and len(text) < 120:
        return True, _heading_level(text)
    return False, 1


def _load_docx(path: Path) -> tuple[list[Block], str, str]:
    document = docx.Document(str(path))
    blocks: list[Block] = []
    title, subtitle = "", ""

    for element in document.element.body.iterchildren():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "tbl":
            markdown = rows_to_markdown(clean_rows(_docx_table_rows(Table(element, document))))
            if markdown:
                blocks.append(Block("table", markdown))
        elif tag == "p":
            paragraph = Paragraph(element, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name if paragraph.style is not None else "").lower()
            if style in ("title", "título", "titulo") and not title:
                title = text
            elif style in ("subtitle", "subtítulo", "subtitulo") and not subtitle:
                subtitle = text
            is_heading, level = _is_docx_heading(paragraph)
            blocks.append(Block("heading", text, level=level) if is_heading else Block("text", text))

    return blocks, title, subtitle


# ------------------------------------------------------------------------ Público


def load_document(path: str | Path) -> Document:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        blocks, title, subtitle = _load_pdf(path)
    elif suffix == ".docx":
        blocks, title, subtitle = _load_docx(path)
    else:
        raise ValueError(f"Formato no soportado: {path.name} (se aceptan {', '.join(SUPPORTED_EXTENSIONS)})")

    first_text = " ".join(b.text for b in blocks[:40])
    code_match = PROJECT_CODE_RE.search(path.name) or PROJECT_CODE_RE.search(first_text)
    return Document(
        source_file=path.name,
        project_code=code_match.group(0) if code_match else None,
        title=title,
        client=subtitle or path.stem,
        blocks=blocks,
    )


def load_reports(directory: str | Path = REPORTS_DIR) -> list[Document]:
    """Carga todos los informes soportados de una carpeta, ordenados por nombre."""
    directory = Path(directory)
    paths = sorted(p for p in directory.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("~$"))
    return [load_document(p) for p in paths]
