import core.screenshot_parser as sp


def test_extract_fields_json_limpio():
    raw = '{"side":"COMPRA","date":"2026-06-01","order_id":"123",' \
          '"usd_gross":"100","commission":"0.16","price":"1477",' \
          '"total_ars":"147700","exchange_coin":"Binance / USDT","bank":"Lemon"}'
    d = sp._extract_fields(raw)
    assert d["side"] == "COMPRA"
    assert d["order_id"] == "123"
    assert d["usd_gross"] == "100"


def test_extract_fields_json_en_markdown():
    raw = "Acá tenés los datos:\n```json\n{\"side\":\"VENTA\",\"date\":\"2026-06-02\"}\n```\nListo."
    d = sp._extract_fields(raw)
    assert d["side"] == "VENTA"
    assert d["date"] == "2026-06-02"


def test_extract_fields_sin_json_lanza():
    import pytest
    with pytest.raises(ValueError):
        sp._extract_fields("No pude leer la imagen.")


def test_parse_screenshot_usa_ask_claude(monkeypatch, tmp_path):
    captured = {}

    def fake_ask(prompt, image_path):
        captured["prompt"] = prompt
        captured["image_path"] = image_path
        return '{"side":"COMPRA","order_id":"999"}'

    monkeypatch.setattr(sp, "_ask_claude", fake_ask)
    d = sp.parse_screenshot(b"\x89PNG fake bytes", "image/png")
    assert d["order_id"] == "999"
    # Le pasó un archivo .png existente al momento de llamar
    assert captured["image_path"].endswith(".png")


def test_parse_screenshot_archivo_temporal_legible_durante_la_llamada(monkeypatch):
    import os
    seen = {}

    def fake_ask(prompt, image_path):
        seen["exists"] = os.path.exists(image_path)
        with open(image_path, "rb") as fh:
            seen["content"] = fh.read()
        seen["path"] = image_path
        return '{"order_id":"1"}'

    monkeypatch.setattr(sp, "_ask_claude", fake_ask)
    sp.parse_screenshot(b"PNGDATA", "image/png")
    assert seen["exists"] is True
    assert seen["content"] == b"PNGDATA"
    # el temporal se borra al terminar (bloque finally)
    assert not os.path.exists(seen["path"])


def test_extract_fields_ignora_segundo_objeto_json():
    raw = 'Intento 1: {"side":"COMPRA"} -- mejor: {"side":"VENTA"}'
    # Decodifica el PRIMER objeto y no rompe por el texto/objeto posterior
    assert sp._extract_fields(raw) == {"side": "COMPRA"}
