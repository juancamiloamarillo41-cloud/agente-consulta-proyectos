import pytest

from project_agent.search import normalize, tokenize


def test_normalization_ignores_accents_and_case():
    assert normalize("Línea de Producción") == "linea de produccion"


def test_tokenize_removes_stopwords_and_plurals():
    assert tokenize("Las lecciones de los proyectos") == ["leccion", "proyecto"]
    assert tokenize("quiebre de 4,8%") == ["quiebre", "4,8"]


@pytest.mark.parametrize(
    "query, expected_code, expected_section",
    [
        ("resultados de OEE en la planta", "PC-2025-027", "7. Resultados"),
        ("línea 2 fuera del alcance sopladoras", "PC-2025-027", "4. Alcance"),
        ("tiempo de espera de pacientes resultado oficial", "PC-2025-033", "6. Resultados"),
        ("integración de órdenes con proveedores ERP", "PC-2026-006", "6. Resultados"),
        ("abandono de solicitudes microcrédito rural", "PC-2025-014", None),
        ("informe de diagnóstico quiebres de stock", "PC-2026-006", "2. Contexto"),
    ],
)
def test_relevant_section_ranks_first(index, query, expected_code, expected_section):
    top = index.search(query, top_k=1)[0].chunk
    assert top.project_code == expected_code
    if expected_section:
        assert top.section == expected_section


def test_cross_project_query_returns_several_projects(index):
    codes = {r.chunk.project_code for r in index.search("resistencia al cambio mandos medios", top_k=3)}
    assert {"PC-2025-014", "PC-2025-027"} <= codes


def test_project_filter(index):
    results = index.search("lecciones aprendidas", top_k=10, project_code="PC-2025-033")
    assert results and all(r.chunk.project_code == "PC-2025-033" for r in results)


def test_no_results_for_unrelated_query(index):
    assert index.search("criptomonedas blockchain") == []
