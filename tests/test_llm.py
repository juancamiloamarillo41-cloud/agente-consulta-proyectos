"""Cadena de modelos de respaldo del cliente LLM, con un cliente simulado."""

import pytest
from google.genai import errors, types

from project_agent import llm


class FakeModels:
    def __init__(self, behaviour):
        self.behaviour = behaviour  # modelo -> excepción a lanzar (o None para responder)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append(model)
        error = self.behaviour.get(model)
        if error:
            raise error
        return f"respuesta de {model}"


def _api_error(code, message="error"):
    return errors.APIError(code, {"error": {"code": code, "message": message}})


@pytest.fixture
def fake(monkeypatch):
    def install(behaviour, models):
        models_api = FakeModels(behaviour)
        monkeypatch.setattr(llm, "get_client", lambda: type("Client", (), {"models": models_api})())
        monkeypatch.setattr(llm, "models_to_try", lambda: models)
        monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)
        return models_api

    return install


def test_unavailable_model_is_skipped(fake):
    api = fake({"viejo": _api_error(404, "no longer available")}, ["viejo", "nuevo"])
    assert llm.generate("hola", types.GenerateContentConfig()) == "respuesta de nuevo"
    assert api.calls == ["viejo", "nuevo"]


def test_daily_quota_skips_to_next_model_without_retrying(fake):
    api = fake({"a": _api_error(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")}, ["a", "b"])
    assert llm.generate("hola", types.GenerateContentConfig()) == "respuesta de b"
    assert api.calls == ["a", "b"]


def test_overloaded_model_is_retried_then_skipped(fake):
    api = fake({"a": _api_error(503, "high demand")}, ["a", "b"])
    assert llm.generate("hola", types.GenerateContentConfig()) == "respuesta de b"
    assert api.calls == ["a"] * llm.MAX_ATTEMPTS_PER_MODEL + ["b"]


def test_all_models_exhausted_reports_quota_reason(fake):
    fake({m: _api_error(429, "PerDay") for m in ("a", "b")}, ["a", "b"])
    with pytest.raises(llm.LLMError) as info:
        llm.generate("hola", types.GenerateContentConfig())
    assert info.value.reason == "cuota"


def test_invalid_request_fails_fast(fake):
    api = fake({"a": _api_error(400, "bad request")}, ["a", "b"])
    with pytest.raises(llm.LLMError):
        llm.generate("hola", types.GenerateContentConfig())
    assert api.calls == ["a"]
