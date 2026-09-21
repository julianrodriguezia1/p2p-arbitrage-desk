from pathlib import Path

import pytest

from core import captacion_chat as cap


def _write_docs(tmp_path: Path) -> Path:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "01-uno.md").write_text("UNO contenido", encoding="utf-8")
    (d / "02-dos.md").write_text("DOS contenido", encoding="utf-8")
    return d


def test_load_docs_concatena_en_orden(tmp_path):
    d = _write_docs(tmp_path)
    text = cap.load_docs(d)
    assert "UNO contenido" in text
    assert "DOS contenido" in text
    assert text.index("UNO") < text.index("DOS")
    assert "---" in text  # separador entre docs


def test_build_system_prompt_incluye_persona_docs_y_recordatorio():
    prompt = cap.build_system_prompt("PERSONA-XYZ", "DOCS-ABC")
    assert "PERSONA-XYZ" in prompt
    assert "DOCS-ABC" in prompt
    assert "no inventes" in prompt.lower()


def test_build_transcript_ordena_turnos():
    msgs = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "buenas"},
        {"role": "user", "content": "che"},
    ]
    t = cap.build_transcript(msgs)
    assert t.index("hola") < t.index("buenas") < t.index("che")
    assert "Usuario" in t and "Asistente" in t


def test_answer_arma_prompt_y_devuelve_texto(tmp_path):
    d = _write_docs(tmp_path)
    capturado = {}

    def fake_ask(system_prompt: str, transcript: str) -> str:
        capturado["system"] = system_prompt
        capturado["transcript"] = transcript
        return "respuesta de la IA"

    msgs = [{"role": "user", "content": "quiero captar clientes"}]
    out = cap.answer(msgs, docs_dir=d, ask=fake_ask)

    assert out == "respuesta de la IA"
    assert "UNO contenido" in capturado["system"]  # docs inyectados
    assert "quiero captar clientes" in capturado["transcript"]
