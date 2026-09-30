"""Ejecución de SQL de solo lectura sobre la base de fichas.

El SQL lo escribe el modelo, así que se trata como entrada no confiable. Hay tres
barreras independientes:
1. Validación sintáctica: una sola sentencia que empiece por SELECT o WITH.
2. Conexión abierta en modo de solo lectura (`mode=ro`).
3. Un autorizador de SQLite que solo permite operaciones de lectura.
Además se limita el número de filas devueltas para no saturar el contexto.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from project_agent.config import DB_PATH, SQL_MAX_ROWS

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


def _open_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise SqlQueryError(f"No existe la base de fichas en {db_path}. Ejecuta primero la extracción.")
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
    conn.set_authorizer(_authorizer)
    return conn


def _project_sources(conn: sqlite3.Connection, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    conn.set_authorizer(None)
    placeholders = ",".join("?" * len(codes))
    rows = conn.execute(
        f"SELECT codigo_proyecto, archivo_fuente FROM proyectos WHERE codigo_proyecto IN ({placeholders})",
        sorted(codes),
    ).fetchall()
    return dict(rows)


def run_readonly_query(sql: str, db_path: str | Path = DB_PATH, max_rows: int = SQL_MAX_ROWS) -> QueryResult:
    statement = validate_sql(sql)
    conn = _open_readonly(Path(db_path))
    try:
        try:
            cursor = conn.execute(statement)
        except sqlite3.DatabaseError as exc:
            raise SqlQueryError(f"Error de SQL: {exc}") from exc
        columns = [d[0] for d in cursor.description or []]
        rows = cursor.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        rows = rows[:max_rows]

        # Para poder citar: si el resultado trae códigos de proyecto, se añade su informe fuente.
        codes = set()
        if "codigo_proyecto" in columns:
            idx = columns.index("codigo_proyecto")
            codes = {row[idx] for row in rows if row[idx]}
        return QueryResult(columns, rows, truncated, _project_sources(conn, codes))
    finally:
        conn.close()


def describe_schema(db_path: str | Path = DB_PATH) -> str:
    """Esquema de la base en texto (CREATE TABLE) para incluirlo en la descripción de la herramienta."""
    conn = _open_readonly(Path(db_path))
    try:
        conn.set_authorizer(None)
        rows = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' ORDER BY rowid").fetchall()
        return "\n\n".join(r[0] for r in rows)
    finally:
        conn.close()
