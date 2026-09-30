import pytest

from project_agent.config import REPORTS_DIR
from project_agent.ingestion import load_reports, split_into_chunks
from project_agent.search import BM25Index


@pytest.fixture(scope="session")
def documents():
    return {doc.project_code: doc for doc in load_reports(REPORTS_DIR)}


@pytest.fixture(scope="session")
def chunks(documents):
    return [chunk for doc in documents.values() for chunk in split_into_chunks(doc)]


@pytest.fixture(scope="session")
def index(chunks):
    return BM25Index(chunks)
