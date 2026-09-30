"""Normalización de tablas a markdown.

Las tablas son donde viven los indicadores (línea base, meta, resultado), así que
conservar la relación fila-columna es crítico para no atribuir un valor a otro
indicador. Los documentos convertidos desde Word generan columnas "fantasma" por
celdas combinadas; aquí se colapsan a las columnas lógicas de la cabecera.
"""

from __future__ import annotations

import re


def _clean(cell: str | None) -> str:
    return re.sub(r"\s+", " ", cell or "").strip()


def _collapse_phantom_columns(rows: list[list[str]]) -> list[list[str]]:
    """Reduce las columnas a las que tienen etiqueta en la cabecera.

    Cada columna física se asigna a la etiqueta de cabecera más cercana (en caso de
    empate, la de la derecha, porque las celdas combinadas empiezan a la izquierda
    de su etiqueta). En cada grupo se toma el primer valor no vacío.
    """
    header = rows[0]
    labels = [i for i, cell in enumerate(header) if cell]
    if not labels or len(labels) == len(header):
        return rows

    groups: dict[int, list[int]] = {label: [] for label in labels}
    for col in range(len(header)):
        nearest = min(labels, key=lambda label: (abs(label - col), -label))
        groups[nearest].append(col)

    collapsed = []
    for row in rows:
        new_row = []
        for label in labels:
            values = [row[c] for c in groups[label] if c < len(row) and row[c]]
            new_row.append(values[0] if values else "")
        collapsed.append(new_row)
    return collapsed


def _merge_vertical_spans(rows: list[list[str]]) -> list[list[str]]:
    """Une a la fila anterior las filas de continuación de una celda combinada vertical.

    Una fila es de continuación si repite la primera celda de la anterior o si la
    tiene vacía (el texto de la celda combinada solo aparece en la primera fila).
    """
    merged: list[list[str]] = []
    for row in rows:
        is_continuation = not row[0] or (merged and row[0] == merged[-1][0])
        if len(merged) > 1 and is_continuation:
            previous = merged[-1]
            for i, value in enumerate(row[1:], start=1):
                if value and value != previous[i]:
                    previous[i] = f"{previous[i]} {value}".strip()
        else:
            merged.append(row)
    return merged


def clean_rows(raw_rows: list[list[str | None]]) -> list[list[str]]:
    """Limpia celdas, elimina filas vacías y colapsa celdas combinadas."""
    rows = [[_clean(cell) for cell in row] for row in raw_rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return []
    rows = _collapse_phantom_columns(rows)
    rows = [row for row in rows if any(row)]
    return _merge_vertical_spans(rows)


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]

    def fmt(row: list[str]) -> str:
        return "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"

    lines = [fmt(rows[0]), "|" + "---|" * width]
    lines.extend(fmt(row) for row in rows[1:])
    return "\n".join(lines)
