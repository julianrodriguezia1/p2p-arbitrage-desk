from companion.tray import _format_balloon


def test_busy():
    assert "corriendo" in _format_balloon({"busy": True}).lower()


def test_error_surfaces_message():
    out = _format_balloon({"error": {"nuevas": 0, "ya": 0, "errores": ["boom 451"]}})
    assert "boom 451" in out


def test_normal_lists_exchanges():
    out = _format_balloon({"binance": {"nuevas": 2, "ya": 1, "errores": []}})
    assert "binance" in out and "2" in out
