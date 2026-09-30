"""Escritura de fichas en SQLite.

Se guarda una ficha por transacción y se reemplaza completa si ya existía
(borrado en cascada de sus filas hijas), de modo que reprocesar un informe es
idempotente.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from project_agent.config import DB_PATH, FICHAS_DIR
from project_agent.ficha import Ficha

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def save_ficha(conn: sqlite3.Connection, ficha: Ficha) -> None:
    code = ficha.codigo_proyecto
    with conn:
        conn.execute("DELETE FROM proyectos WHERE codigo_proyecto = ?", (code,))
        conn.execute(
            """
            INSERT INTO proyectos (
                codigo_proyecto, titulo, cliente, descripcion_cliente, sector, subsector, ubicacion,
                fecha_inicio, fecha_fin, duracion_semanas, fecha_aceptacion, estado, gerente_proyecto,
                equipo_consultor, tamano_equipo, contraparte_cliente, problema, resumen, alcance,
                objetivos_cumplidos, objetivos_totales, archivo_fuente
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code, ficha.titulo, ficha.cliente, ficha.descripcion_cliente, ficha.sector, ficha.subsector,
                ficha.ubicacion, _iso(ficha.fecha_inicio), _iso(ficha.fecha_fin), ficha.duracion_semanas,
                _iso(ficha.fecha_aceptacion), ficha.estado, ficha.gerente_proyecto, ficha.equipo_consultor,
                ficha.tamano_equipo, ficha.contraparte_cliente, ficha.problema, ficha.resumen, ficha.alcance,
                ficha.objetivos_cumplidos, ficha.objetivos_totales, ficha.archivo_fuente,
            ),
        )
        conn.executemany(
            "INSERT INTO objetivos VALUES (?, ?)", [(code, o) for o in ficha.objetivos]
        )
        conn.executemany(
            "INSERT INTO metodologias VALUES (?, ?)", [(code, m) for m in ficha.metodologias]
        )
        conn.executemany(
            "INSERT INTO iniciativas VALUES (?, ?)", [(code, i) for i in ficha.iniciativas]
        )
        conn.executemany(
            "INSERT INTO indicadores VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    code, i.nombre, i.unidad, i.linea_base, i.meta, i.resultado, i.variacion,
                    i.linea_base_valor, i.resultado_valor, i.estado_meta.value, i.notas,
                )
                for i in ficha.indicadores
            ],
        )
        conn.executemany(
            "INSERT INTO lecciones VALUES (?, ?, ?)", [(code, l.titulo, l.descripcion) for l in ficha.lecciones]
        )
        conn.executemany(
            "INSERT INTO recomendaciones VALUES (?, ?)", [(code, r) for r in ficha.recomendaciones]
        )
        conn.executemany(
            "INSERT INTO salvedades VALUES (?, ?, ?)", [(code, s.tipo, s.descripcion) for s in ficha.salvedades]
        )


def load_ficha_json(path: str | Path) -> Ficha:
    return Ficha.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_ficha_json(ficha: Ficha, directory: str | Path = FICHAS_DIR) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ficha.codigo_proyecto}.json"
    path.write_text(json.dumps(ficha.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def rebuild_db_from_json(fichas_dir: str | Path = FICHAS_DIR, db_path: str | Path = DB_PATH) -> int:
    """Reconstruye la base desde los JSON de fichas (fuente de verdad versionada en Git)."""
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    conn = connect(db_path)
    try:
        init_db(conn)
        fichas = [load_ficha_json(p) for p in sorted(Path(fichas_dir).glob("*.json"))]
        for ficha in fichas:
            save_ficha(conn, ficha)
        return len(fichas)
    finally:
        conn.close()
