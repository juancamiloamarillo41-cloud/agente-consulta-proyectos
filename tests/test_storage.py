import sqlite3

import pytest

from project_agent.storage.query import SqlQueryError, describe_schema, run_readonly_query
from project_agent.storage.repository import connect, rebuild_db_from_json, save_ficha, save_ficha_json


def test_saves_project_and_children(db_path):
    result = run_readonly_query(
        "SELECT codigo_proyecto, sector, gerente_proyecto, objetivos_cumplidos, objetivos_totales FROM proyectos",
        db_path,
    )
    assert result.rows == [("PC-2025-014", "Servicios financieros", "Ing. Daniela Cevallos", 4, 5)]

    counts = run_readonly_query(
        """
        SELECT (SELECT COUNT(*) FROM indicadores), (SELECT COUNT(*) FROM lecciones),
               (SELECT COUNT(*) FROM recomendaciones), (SELECT COUNT(*) FROM salvedades)
        """,
        db_path,
    )
    assert counts.rows == [(5, 3, 3, 2)]


def test_indicator_values_are_queryable(db_path):
    result = run_readonly_query(
        "SELECT codigo_proyecto, nombre, resultado FROM indicadores WHERE estado_meta = 'no_cumplida'", db_path
    )
    assert result.rows == [("PC-2025-014", "Tasa de abandono de solicitudes", "11%")]
    # Cada resultado con código de proyecto trae el informe fuente para poder citarlo.
    assert result.sources == {"PC-2025-014": "Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf"}


@pytest.mark.parametrize(
    "condition",
    ["cliente LIKE '%credito%'", "cliente LIKE '%CRÉDITO%'", "gerente_proyecto LIKE 'ing. daniela%'", "codigo_proyecto LIKE 'PC-2025-01_'"],
)
def test_like_ignores_case_and_accents(db_path, condition):
    assert run_readonly_query(f"SELECT codigo_proyecto FROM proyectos WHERE {condition}", db_path).rows == [("PC-2025-014",)]


def test_like_escape_clause(db_path):
    sql = "SELECT COUNT(*) FROM indicadores WHERE linea_base LIKE '34!%' ESCAPE '!'"
    assert run_readonly_query(sql, db_path).rows == [(1,)]


def test_resaving_a_ficha_is_idempotent(db_path, golden_ficha):
    conn = connect(db_path)
    save_ficha(conn, golden_ficha)
    conn.close()
    result = run_readonly_query("SELECT COUNT(*) FROM indicadores", db_path)
    assert result.rows == [(5,)]


def test_rebuild_from_json(tmp_path, golden_ficha):
    save_ficha_json(golden_ficha, tmp_path / "fichas")
    db = tmp_path / "rebuilt.db"
    assert rebuild_db_from_json(tmp_path / "fichas", db) == 1
    assert run_readonly_query("SELECT titulo FROM proyectos", db).rows[0][0].startswith("Optimización")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM proyectos",
        "DROP TABLE proyectos",
        "INSERT INTO lecciones VALUES ('X', 'a', 'b')",
        "SELECT 1; DROP TABLE proyectos",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'otra.db' AS otra",
        "",
    ],
)
def test_rejects_non_read_statements(db_path, sql):
    with pytest.raises(SqlQueryError):
        run_readonly_query(sql, db_path)


def test_write_inside_cte_is_blocked_by_readonly_connection(db_path):
    # Pasa la validación sintáctica (empieza por WITH) pero la conexión y el autorizador lo impiden.
    with pytest.raises(SqlQueryError):
        run_readonly_query("WITH x AS (SELECT 1) DELETE FROM proyectos", db_path)
    assert run_readonly_query("SELECT COUNT(*) FROM proyectos", db_path).rows == [(1,)]


def test_sql_errors_are_reported_for_the_model_to_fix(db_path):
    with pytest.raises(SqlQueryError, match="no such column"):
        run_readonly_query("SELECT columna_inexistente FROM proyectos", db_path)


def test_results_are_truncated(db_path):
    result = run_readonly_query("SELECT nombre FROM indicadores", db_path, max_rows=2)
    assert len(result.rows) == 2 and result.truncated


def test_missing_database_gives_clear_error(tmp_path):
    with pytest.raises(SqlQueryError, match="No existe la base"):
        run_readonly_query("SELECT 1", tmp_path / "no.db")


def test_schema_description_lists_tables(db_path):
    schema = describe_schema(db_path)
    for table in ("proyectos", "indicadores", "lecciones", "salvedades"):
        assert f"CREATE TABLE {table}" in schema


def test_invalid_estado_meta_is_rejected_by_db(db_path):
    conn = connect(db_path)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO indicadores (codigo_proyecto, nombre, estado_meta) VALUES ('PC-2025-014', 'x', 'quizas')")
    conn.close()
