"""Sincronización de informes nuevos al arrancar (el extractor se simula: no se llama a Gemini)."""

import shutil

import pytest

from project_agent.config import FICHAS_DIR, REPORTS_DIR
from project_agent.llm import LLMError
from project_agent.storage.query import run_readonly_query
from project_agent.storage.repository import load_ficha_json
from project_agent.sync import pending_reports, sync_reports

COOP = "Informe_Cierre_PC-2025-014_Cooperativa_Horizonte_Andino.pdf"
CLINIC = "Informe_Cierre_PC-2025-033_Clinica_Santa_Lucia.pdf"


@pytest.fixture
def workspace(tmp_path):
    """Carpeta con dos informes y solo la ficha del primero: el segundo es «nuevo»."""
    reports, fichas = tmp_path / "informes", tmp_path / "fichas"
    reports.mkdir()
    fichas.mkdir()
    for name in (COOP, CLINIC):
        shutil.copy(REPORTS_DIR / name, reports / name)
    shutil.copy(FICHAS_DIR / "PC-2025-014.json", fichas / "PC-2025-014.json")
    return reports, fichas, tmp_path / "fichas.db"


def _fake_extract(document):
    ficha = load_ficha_json(FICHAS_DIR / f"{document.project_code}.json")
    ficha.archivo_fuente = document.source_file
    return ficha


def _projects(db):
    return [row[0] for row in run_readonly_query("SELECT codigo_proyecto FROM proyectos ORDER BY 1", db).rows]


def test_detects_reports_without_ficha(workspace):
    reports, fichas, _ = workspace
    assert [p.name for p in pending_reports(reports, fichas)] == [CLINIC]


def test_new_report_gets_its_ficha_and_the_database_is_updated(workspace):
    reports, fichas, db = workspace
    messages = []
    processed = sync_reports(reports, fichas, db, extract=_fake_extract, out=messages.append)
    assert processed == [CLINIC]
    assert (fichas / "PC-2025-033.json").exists()
    assert _projects(db) == ["PC-2025-014", "PC-2025-033"]
    assert any("Informe nuevo detectado" in m for m in messages)


def test_nothing_new_means_no_extraction(workspace):
    reports, fichas, db = workspace
    sync_reports(reports, fichas, db, extract=_fake_extract, out=lambda m: None)

    def must_not_be_called(document):
        raise AssertionError("no debería llamarse al modelo si no hay informes nuevos")

    assert sync_reports(reports, fichas, db, extract=must_not_be_called, out=lambda m: None) == []


def test_extraction_failure_does_not_block_startup(workspace):
    reports, fichas, db = workspace

    def failing(document):
        raise LLMError("sin cuota", "cuota")

    messages = []
    assert sync_reports(reports, fichas, db, extract=failing, out=messages.append) == []
    assert _projects(db) == ["PC-2025-014"]  # la base se crea con las fichas que sí existen
    assert any("No se pudo generar la ficha" in m for m in messages)


def test_second_file_of_the_same_project_does_not_replace_the_ficha(workspace):
    reports, fichas, db = workspace
    shutil.copy(reports / COOP, reports / "Copia_del_informe_PC-2025-014.pdf")
    (reports / CLINIC).unlink()
    messages = []

    def must_not_be_called(document):
        raise AssertionError("un duplicado se detecta por su código, sin llamar al modelo")

    processed = sync_reports(reports, fichas, db, extract=must_not_be_called, out=messages.append)
    assert processed == []
    assert load_ficha_json(fichas / "PC-2025-014.json").archivo_fuente == COOP
    assert any("No se reemplaza" in m for m in messages)


def test_warns_about_fichas_whose_report_was_removed(workspace):
    reports, fichas, db = workspace
    (reports / COOP).unlink()
    messages = []
    sync_reports(reports, fichas, db, extract=_fake_extract, out=messages.append)
    assert any("ya no está en la carpeta" in m for m in messages)
