import pytest

from project_agent.config import REPORTS_DIR
from project_agent.ingestion import load_reports, split_into_chunks


@pytest.fixture(scope="session")
def documents():
    return {doc.project_code: doc for doc in load_reports(REPORTS_DIR)}


@pytest.fixture(scope="session")
def chunks(documents):
    return [chunk for doc in documents.values() for chunk in split_into_chunks(doc)]
