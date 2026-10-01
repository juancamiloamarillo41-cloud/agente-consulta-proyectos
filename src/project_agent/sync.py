"""Sincroniza la carpeta de informes con las fichas al arrancar el agente.

Así basta con copiar un informe nuevo en data/informes: la próxima vez que se abre el agente
(consola o web) se genera su ficha y se actualiza la base. Si no hay nada nuevo no se llama al
modelo. Si la extracción falla (sin cuota, sin conexión), el agente arranca igual con las fichas
que ya existen; el texto del informe nuevo sí queda disponible para la búsqueda.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from project_agent.config import DB_PATH, FICHAS_DIR, REPORTS_DIR, SUPPORTED_EXTENSIONS
from project_agent.extraction import extract_ficha, verify_ficha
from project_agent.ficha import Ficha
from project_agent.ingestion import Document, load_document
from project_agent.llm import LLMError
from project_agent.storage.repository import load_ficha_json, rebuild_db_from_json, save_ficha_json


def report_files(reports_dir: Path = REPORTS_DIR) -> list[Path]:
    return sorted(
        p for p in Path(reports_dir).iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("~$")
    )


def fichas_by_source(fichas_dir: Path = FICHAS_DIR) -> dict[str, Ficha]:
    """Fichas existentes indexadas por el archivo del que salieron (no por código de proyecto)."""
    fichas = {}
    for path in sorted(Path(fichas_dir).glob("*.json")):
        try:
            ficha = load_ficha_json(path)
        except ValueError:
            continue  # JSON dañado: se trata como si no existiera
        fichas[ficha.archivo_fuente] = ficha
    return fichas


def pending_reports(reports_dir: Path = REPORTS_DIR, fichas_dir: Path = FICHAS_DIR) -> list[Path]:
    """Informes de la carpeta que todavía no tienen ficha."""
    done = fichas_by_source(fichas_dir)
    return [path for path in report_files(reports_dir) if path.name not in done]


def _db_is_stale(fichas_dir: Path, db_path: Path) -> bool:
    if not db_path.exists():
        return True
    db_time = db_path.stat().st_mtime
    return any(p.stat().st_mtime > db_time for p in Path(fichas_dir).glob("*.json"))


def sync_reports(
    reports_dir: Path = REPORTS_DIR,
    fichas_dir: Path = FICHAS_DIR,
    db_path: Path = DB_PATH,
    extract: Callable[[Document], Ficha] = extract_ficha,
    out: Callable[[str], None] = print,
) -> list[str]:
    """Genera las fichas que falten y deja la base al día. Devuelve los archivos procesados."""
    existing = fichas_by_source(fichas_dir)
    codes_in_use = {ficha.codigo_proyecto: source for source, ficha in existing.items()}
    available = {path.name for path in report_files(reports_dir)}
    processed = []

    def duplicate_of(code: str | None, name: str) -> str | None:
        other = codes_in_use.get(code)
        return other if other and other != name else None

    for path in (p for p in report_files(reports_dir) if p.name not in existing):
        try:
            document = load_document(path)
        except Exception as exc:
            out(f"No se pudo leer {path.name}: {exc}")
            continue
        # Si el código del informe ya tiene ficha (otro archivo del mismo proyecto), se avisa sin
        # llamar al modelo: de lo contrario se gastaría una llamada en cada arranque.
        other = duplicate_of(document.project_code, path.name)
        if other:
            out(f"Aviso: {path.name} es del proyecto {document.project_code}, que ya tiene ficha (de {other}). No se reemplaza: quita uno de los dos archivos.")
            continue
        out(f"Informe nuevo detectado: {path.name}. Generando su ficha (puede tardar un minuto)...")
        try:
            ficha = extract(document)
        except (LLMError, ValueError) as exc:
            out(f"  No se pudo generar la ficha: {exc}")
            out("  El agente arranca sin ella; el texto del informe sí se puede buscar. Se reintentará al abrir de nuevo.")
            continue
        other = duplicate_of(ficha.codigo_proyecto, path.name)
        if other:
            # El código que devolvió el modelo ya está en uso: no se reemplaza en silencio la ficha existente.
            out(f"  Ya existe una ficha de {ficha.codigo_proyecto}, generada desde {other}. No se reemplaza: quita uno de los dos archivos.")
            continue
        save_ficha_json(ficha, fichas_dir)
        codes_in_use[ficha.codigo_proyecto] = path.name
        processed.append(path.name)
        out(f"  Ficha creada: {ficha.codigo_proyecto} · {ficha.cliente}")
        for issue in verify_ficha(ficha, document):
            out(f"  ADVERTENCIA: {issue}")

    for source in sorted(set(existing) - available):
        out(f"Aviso: hay una ficha de {source}, pero ese informe ya no está en la carpeta de informes.")

    if processed or _db_is_stale(fichas_dir, db_path):
        count = rebuild_db_from_json(fichas_dir, db_path)
        out(f"Base de fichas actualizada: {count} proyectos.")
    return processed


def sync_on_startup(out: Callable[[str], None] = print) -> None:
    """Sincroniza sin impedir nunca que el agente arranque."""
    try:
        sync_reports(out=out)
    except Exception as exc:  # carpeta inexistente, archivo ilegible, etc.
        out(f"Aviso: no se pudieron revisar los informes nuevos ({exc}).")
