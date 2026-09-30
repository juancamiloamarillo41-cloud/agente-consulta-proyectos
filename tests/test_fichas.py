"""Valida las fichas generadas por el LLM (entregable versionado en data/fichas).

No llama al modelo: verifica que lo que quedó guardado sea fiel a los informes.
"""

import pytest

from project_agent.config import FICHAS_DIR
from project_agent.extraction import verify_ficha
from project_agent.storage.repository import load_ficha_json

CODES = ["PC-2025-014", "PC-2025-027", "PC-2025-033", "PC-2026-006"]


@pytest.fixture(scope="module")
def fichas():
    return {code: load_ficha_json(FICHAS_DIR / f"{code}.json") for code in CODES}


def _indicator(ficha, fragment):
    return next(i for i in ficha.indicadores if fragment.lower() in i.nombre.lower())


@pytest.mark.parametrize("code", CODES)
def test_every_indicator_figure_exists_in_its_report(fichas, documents, code):
    assert verify_ficha(fichas[code], documents[code]) == []


@pytest.mark.parametrize("code", CODES)
def test_source_file_is_recorded(fichas, documents, code):
    assert fichas[code].archivo_fuente == documents[code].source_file


def test_matches_hand_written_golden(fichas, golden_ficha):
    generated = fichas["PC-2025-014"]
    key = lambda i: (i.linea_base, i.meta, i.resultado, i.estado_meta)
    assert sorted(map(key, generated.indicadores)) == sorted(map(key, golden_ficha.indicadores))
    assert (generated.objetivos_cumplidos, generated.objetivos_totales) == (4, 5)
    assert generated.gerente_proyecto == golden_ficha.gerente_proyecto
    assert (generated.fecha_inicio, generated.fecha_fin) == (golden_ficha.fecha_inicio, golden_ficha.fecha_fin)
    assert len(generated.lecciones) == len(golden_ficha.lecciones)
    assert "resultado_no_atribuible" in {s.tipo for s in generated.salvedades}


def test_clinic_uses_official_waiting_time_and_flags_preliminary(fichas):
    clinic = fichas["PC-2025-033"]
    assert _indicator(clinic, "espera").variacion == "-24%"
    assert "30%" not in clinic.resumen
    assert "dato_no_oficial" in {s.tipo for s in clinic.salvedades}


def test_plastics_flags_line_2_as_unvalidated(fichas):
    plastics = fichas["PC-2025-027"]
    assert _indicator(plastics, "OEE").resultado == "71%"
    assert "dato_no_validado" in {s.tipo for s in plastics.salvedades}


def test_canasta_pending_items_and_external_document(fichas):
    canasta = fichas["PC-2026-006"]
    assert canasta.estado == "Cerrado con pendientes"
    # 2 cumplidos, 1 parcial y 1 no cumplido: el parcial no cuenta como cumplido.
    assert (canasta.objetivos_cumplidos, canasta.objetivos_totales) == (2, 4)
    assert _indicator(canasta, "integración").estado_meta == "no_cumplida"
    assert _indicator(canasta, "días de inventario").estado_meta == "parcialmente_cumplida"
    assert {"pendiente", "documento_externo"} <= {s.tipo for s in canasta.salvedades}
