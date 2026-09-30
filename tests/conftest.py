from pathlib import Path

import pytest

from project_agent.config import REPORTS_DIR
from project_agent.ingestion import load_reports, split_into_chunks
from project_agent.search import BM25Index
from project_agent.storage.repository import connect, init_db, load_ficha_json, save_ficha

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def documents():
    return {doc.project_code: doc for doc in load_reports(REPORTS_DIR)}


@pytest.fixture(scope="session")
def chunks(documents):
    return [chunk for doc in documents.values() for chunk in split_into_chunks(doc)]


@pytest.fixture(scope="session")
def index(chunks):
    return BM25Index(chunks)


@pytest.fixture
def golden_ficha():
    return load_ficha_json(FIXTURES / "ficha_PC-2025-014_golden.json")


@pytest.fixture
def db_path(tmp_path, golden_ficha):
    path = tmp_path / "fichas.db"
    conn = connect(path)
    init_db(conn)
    save_ficha(conn, golden_ficha)
    conn.close()
    return path
