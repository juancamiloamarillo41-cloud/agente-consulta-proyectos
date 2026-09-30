"""Ejecución de SQL de solo lectura sobre la base de fichas.

El SQL lo escribe el modelo, así que se trata como entrada no confiable. Hay tres
barreras independientes:
1. Validación sintáctica: una sola sentencia que empiece por SELECT o WITH.
2. Conexión abierta en modo de solo lectura (`mode=ro`).
3. Un autorizador de SQLite que solo permite operaciones de lectura.
Además se limita el número de filas devueltas para no saturar el contexto.

`LIKE` se redefine para ignorar mayúsculas y tildes: el modelo escribe "Martin" o
"credito" sin tilde con frecuencia y el LIKE nativo de SQLite no los encontraría.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from project_agent.config import DB_PATH, SQL_MAX_ROWS
from project_agent.text import normalize

_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    getattr(sqlite3, "SQLITE_RECURSIVE", 33),
}


class SqlQueryError(ValueError):
    """Error de validación o ejecución; el mensaje se devuelve al modelo para que corrija la consulta."""


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool
    sources: dict[str, str] = field(default_factory=dict)  # codigo_proyecto -> archivo_fuente


def _authorizer(action, *_):
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def validate_sql(sql: str) -> str:
    statement = sql.strip().rstrip(";").strip()
    if not statement:
        raise SqlQueryError("La consulta está vacía.")
    if ";" in statement:
        raise SqlQueryError("Solo se permite una sentencia SQL por consulta.")
    if not re.match(r"^(select|with)\b", statement, re.IGNORECASE):
        raise SqlQueryError("Solo se permiten consultas de lectura (SELECT o WITH ... SELECT).")
    return statement


@lru_cache(maxsize=256)
def _like_regex(pattern: str, escape: str | None) -> re.Pattern:
    parts, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if escape and ch == escape and i + 1 < len(pattern):
            parts.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        parts.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
        i += 1
    return re.compile("".join(parts), re.DOTALL)


def _like(pattern, value, escape=None):
    """Implementación de LIKE insensible a mayúsculas y tildes (SQLite llama like(patrón, valor))."""
    if pattern is None or value is None:
        return None
    return _like_regex(normalize(str(pattern)), escape).fullmatch(normalize(str(value))) is not None


def _open_readonly(db_path: Path, restricted: bool = True) -> sqlite3.Connection:
    """Abre la base en solo lectura.

    `restricted` agrega el autorizador y se usa para el SQL del modelo. Las consultas internas
    (fuentes, esquema) usan una conexión propia sin autorizador, en lugar de quitárselo a la del
    modelo: así esa conexión nunca baja la guardia (y `set_authorizer(None)` no existe en Python 3.10).
    """
    if not db_path.exists():
        raise SqlQueryError(f"No existe la base de fichas en {db_path}. Ejecuta primero la extracción.")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.create_function("like", 2, _like, deterministic=True)
    conn.create_function("like", 3, _like, deterministic=True)
    if restricted:
        conn.set_authorizer(_authorizer)
    return conn


def _project_sources(db_path: Path, codes: set[str], files: set[str]) -> dict[str, str]:
    """Mapea codigo_proyecto -> archivo_fuente para los proyectos presentes en el resultado."""
    if not codes and not files:
        return {}
    code_marks = ",".join("?" * len(codes)) or "NULL"
    file_marks = ",".join("?" * len(files)) or "NULL"
    conn = _open_readonly(db_path, restricted=False)
    try:
        rows = conn.execute(
            "SELECT codigo_proyecto, archivo_fuente FROM proyectos "
            f"WHERE codigo_proyecto IN ({code_marks}) OR archivo_fuente IN ({file_marks})",
            [*sorted(codes), *sorted(files)],
        ).fetchall()
    finally:
        conn.close()
    return dict(rows)


def run_readonly_query(sql: str, db_path: str | Path = DB_PATH, max_rows: int = SQL_MAX_ROWS) -> QueryResult:
    statement = validate_sql(sql)
    db_path = Path(db_path)
    conn = _open_readonly(db_path)
    try:
        try:
            cursor = conn.execute(statement)
        except sqlite3.DatabaseError as exc:
            raise SqlQueryError(f"Error de SQL: {exc}") from exc
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        # Para poder citar: si el resultado identifica proyectos (por código o por archivo), se añade su informe.
        def values(column: str) -> set[str]:
            if column not in columns:
                return set()
            idx = columns.index(column)
            return {row[idx] for row in rows if row[idx]}

        sources = _project_sources(db_path, values("codigo_proyecto"), values("archivo_fuente"))
        return QueryResult(columns, rows, truncated, sources)
    finally:
        conn.close()


def describe_schema(db_path: str | Path = DB_PATH) -> str:
    """Esquema de la base en texto (CREATE TABLE) para incluirlo en la descripción de la herramienta."""
    conn = _open_readonly(Path(db_path), restricted=False)
    try:
        rows = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' ORDER BY rowid").fetchall()
        return "\n\n".join(r[0] for r in rows)
    finally:
        conn.close()
