"""Rutas y parámetros centrales del proyecto."""

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
REPORTS_DIR = DATA_DIR / "informes"
FICHAS_DIR = DATA_DIR / "fichas"
DB_PATH = DATA_DIR / "fichas.db"

SUPPORTED_EXTENSIONS = (".pdf", ".docx")

# Límite de filas que devuelve la herramienta SQL, para no saturar el contexto del modelo.
SQL_MAX_ROWS = 50
