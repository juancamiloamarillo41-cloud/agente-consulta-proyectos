"""Herramientas del agente.

Cada herramienta tiene tres partes: la declaración que ve el modelo (nombre,
descripción y parámetros), la implementación en Python y un resumen corto para la
traza que se muestra al usuario. Los resultados incluyen siempre el archivo fuente,
para que el modelo pueda citarlo y el sistema pueda listar las fuentes consultadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from project_agent.config import DB_PATH, REPORTS_DIR
from project_agent.ingestion import load_reports, split_into_chunks
from project_agent.search import BM25Index
from project_agent.storage.query import SqlQueryError, describe_schema, run_readonly_query


@dataclass
class ToolOutput:
    payload: dict[str, Any]  # lo que recibe el modelo
    summary: str  # lo que ve el usuario en la traza
    sources: list[str] = field(default_factory=list)


class ReportTools:
    def __init__(self, reports_dir: Path = REPORTS_DIR, db_path: Path = DB_PATH):
        self.db_path = db_path
        chunks = [chunk for doc in load_reports(reports_dir) for chunk in split_into_chunks(doc)]
        self.index = BM25Index(chunks)
        self._handlers: dict[str, Callable[..., ToolOutput]] = {
            "buscar_en_informes": self.search_reports,
            "consultar_fichas_sql": self.query_fichas,
        }

    # ------------------------------------------------------------ declaraciones

    def declarations(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "buscar_en_informes",
                "description": (
                    "Búsqueda por palabras clave (BM25) en el texto completo de los informes de cierre. "
                    "Devuelve secciones completas (con sus tablas) y su cita: archivo, sección y páginas. "
                    "Úsala para detalles, explicaciones, contexto, notas y aclaraciones, cómo se hizo algo, "
                    "o para verificar una cifra en el texto original. La búsqueda es léxica: usa términos "
                    "que probablemente aparezcan en el informe y, si no encuentras nada, reformula con sinónimos."
                ),
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {
                        "consulta": {"type": "string", "description": "Palabras clave a buscar."},
                        "codigo_proyecto": {
                            "type": "string",
                            "description": "Opcional. Restringe la búsqueda a un proyecto (p. ej. PC-2025-014).",
                        },
                        "max_resultados": {"type": "integer", "description": "Entre 1 y 8. Por defecto 4."},
                    },
                    "required": ["consulta"],
                },
            },
            {
                "name": "consultar_fichas_sql",
                "description": (
                    "Ejecuta una consulta SQL de solo lectura (SQLite) sobre las fichas estructuradas de los "
                    "proyectos. Úsala para listar, filtrar, contar o comparar proyectos: por sector, cliente, "
                    "gerente, fechas, estado, metodologías, indicadores y cumplimiento de metas, lecciones, "
                    "recomendaciones y salvedades. Para textos usa LIKE con comodines (ignora mayúsculas y tildes, "
                    "p. ej. sector LIKE '%salud%'). Para resultados y cumplimiento de metas consulta la tabla "
                    "indicadores (linea_base, meta, resultado, estado_meta, notas): ahí está qué indicador se cumplió y cuál no. "
                    "Incluye codigo_proyecto en el SELECT para que el resultado traiga el informe fuente.\n\n"
                    f"Esquema:\n{describe_schema(self.db_path)}"
                ),
                "parameters_json_schema": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "Una única sentencia SELECT."}},
                    "required": ["sql"],
                },
            },
        ]

    # ------------------------------------------------------------ ejecución

    def run(self, name: str, args: dict[str, Any]) -> ToolOutput:
        handler = self._handlers.get(name)
        if handler is None:
            return ToolOutput({"error": f"Herramienta desconocida: {name}"}, f"herramienta desconocida '{name}'")
        try:
            return handler(**args)
        except TypeError as exc:
            return ToolOutput({"error": f"Parámetros inválidos: {exc}"}, "parámetros inválidos")

    def search_reports(self, consulta: str, codigo_proyecto: str | None = None, max_resultados: int = 4) -> ToolOutput:
        top_k = max(1, min(int(max_resultados), 8))
        results = self.index.search(consulta, top_k=top_k, project_code=codigo_proyecto or None)
        if not results:
            return ToolOutput(
                {"resultados": [], "mensaje": "No se encontraron fragmentos con esos términos."},
                "0 fragmentos",
            )
        payload = {
            "resultados": [
                {
                    "cita": r.chunk.citation,
                    "codigo_proyecto": r.chunk.project_code,
                    "archivo": r.chunk.source_file,
                    "seccion": r.chunk.section,
                    "texto": r.chunk.text,
                }
                for r in results
            ]
        }
        sections = "; ".join(f"{r.chunk.project_code} {r.chunk.section}" for r in results)
        sources = list(dict.fromkeys(r.chunk.source_file for r in results))
        return ToolOutput(payload, f"{len(results)} fragmentos ({sections})", sources)

    def query_fichas(self, sql: str) -> ToolOutput:
        try:
            result = run_readonly_query(sql, self.db_path)
        except SqlQueryError as exc:
            return ToolOutput({"error": str(exc)}, f"error: {exc}")
        payload = {
            "columnas": result.columns,
            "filas": [list(row) for row in result.rows],
            "truncado": result.truncated,
            "fuentes": result.sources,
        }
        if not result.rows:
            payload["mensaje"] = "La consulta no devolvió filas."
        elif "indicadores" in sql.lower() and "nombre" not in result.columns:
            # Sin el nombre, el modelo tiende a inventar a qué indicador corresponde cada valor.
            payload["advertencia"] = (
                "Las filas no incluyen el nombre del indicador. No atribuyas estos valores a ningún "
                "indicador: repite la consulta incluyendo la columna nombre."
            )
        summary = f"{len(result.rows)} filas" + (" (truncado)" if result.truncated else "")
        return ToolOutput(payload, summary, sorted(set(result.sources.values())))
