from bot.bridge_client import format_sync_result, actualizar_text, is_authorized


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
    def json(self):
        return self._payload


def test_is_authorized():
    assert is_authorized(123, 123)
    assert not is_authorized(999, 123)


def test_format_sync_result():
    txt = format_sync_result({
        "binance": {"nuevas": 2, "ya": 3, "errores": []},
        "bybit": {"nuevas": 0, "ya": 1, "errores": ["#x: 502 boom"]},
    })
    assert "Binance" in txt and "2" in txt
    assert "boom" in txt  # los errores se muestran


def test_actualizar_ok():
    def post(url, headers=None, timeout=None):
        return _Resp(200, {"binance": {"nuevas": 1, "ya": 0, "errores": []}})
    txt = actualizar_text("http://pc:8765/sync", "tok", post=post)
    assert "Binance" in txt and "1" in txt


def test_actualizar_pc_apagada():
    def post(url, headers=None, timeout=None):
        raise OSError("connection refused")
    txt = actualizar_text("http://pc:8765/sync", "tok", post=post)
    assert "prendi" in txt.lower() or "compu" in txt.lower()


def test_actualizar_error_status():
    def post(url, headers=None, timeout=None):
        return _Resp(500, {"error": "explotó"})
    txt = actualizar_text("http://pc:8765/sync", "tok", post=post)
    assert "500" in txt or "falló" in txt.lower()


def test_format_sync_result_busy():
    out = format_sync_result({"busy": True})
    assert "corriendo" in out.lower()


def test_actualizar_busy_does_not_crash():
    def post(url, headers=None, timeout=None):
        return _Resp(200, {"busy": True})
    txt = actualizar_text("http://pc:8765/sync", "tok", post=post)
    assert "corriendo" in txt.lower()
