"""Configuración guiada de la clave (sin llamar a Google: la validación es simulada)."""

from project_agent.setup_env import current_key, ensure_env

EXAMPLE = "# Plantilla\n# Clave de Google AI Studio\nGEMINI_API_KEY=\n"


def _project(tmp_path, env=None):
    (tmp_path / ".env.example").write_text(EXAMPLE, encoding="utf-8")
    if env is not None:
        (tmp_path / ".env").write_text(env, encoding="utf-8")
    return tmp_path


def _run(root, answers, validity=True):
    answers, messages = iter(answers), []
    ok = ensure_env(root, ask=lambda prompt: next(answers), validate=lambda key: validity, out=messages.append)
    return ok, messages


def test_existing_key_is_left_untouched(tmp_path):
    root = _project(tmp_path, env="GEMINI_API_KEY=clave-existente\n")
    ok, messages = _run(root, [])
    assert ok and messages == []
    assert current_key(root / ".env") == "clave-existente"


def test_missing_env_is_created_from_the_template(tmp_path):
    root = _project(tmp_path)
    ok, messages = _run(root, ['  "AIzaNUEVA1234"  '])
    content = (root / ".env").read_text(encoding="utf-8")
    assert ok
    assert "GEMINI_API_KEY=AIzaNUEVA1234" in content
    assert "# Plantilla" in content  # conserva los comentarios de la plantilla
    assert any("…1234" in m for m in messages)  # solo muestra el final de la clave


def test_empty_key_in_existing_env_is_completed(tmp_path):
    root = _project(tmp_path, env="GEMINI_API_KEY=\nGEMINI_MODELS=gemini-3.6-flash\n")
    ok, _ = _run(root, ["clave-completa"])
    content = (root / ".env").read_text(encoding="utf-8")
    assert ok and "GEMINI_API_KEY=clave-completa" in content and "GEMINI_MODELS=gemini-3.6-flash" in content


def test_rejected_key_is_asked_again_and_gives_up_after_three_attempts(tmp_path):
    root = _project(tmp_path)
    ok, messages = _run(root, ["mala1", "mala2", "mala3"], validity=False)
    assert not ok
    assert not (root / ".env").exists()
    assert sum("rechazó" in m for m in messages) == 3


def test_empty_and_spaced_inputs_are_rejected_before_validating(tmp_path):
    root = _project(tmp_path)
    ok, messages = _run(root, ["", "con espacio", "buena"])
    assert ok and current_key(root / ".env") == "buena"
    assert any("ninguna clave" in m for m in messages) and any("espacios" in m for m in messages)


def test_key_is_saved_when_it_cannot_be_checked_offline(tmp_path):
    root = _project(tmp_path)
    ok, messages = _run(root, ["sin-conexion"], validity=None)
    assert ok and current_key(root / ".env") == "sin-conexion"
    assert any("No se pudo comprobar" in m for m in messages)
