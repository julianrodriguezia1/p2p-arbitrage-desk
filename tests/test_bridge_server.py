# tests/test_bridge_server.py
from companion.bridge_server import handle_sync


def test_rejects_bad_token():
    status, body = handle_sync("nope", "secret", lambda: {"ok": True})
    assert status == 401
    assert "error" in body


def test_runs_with_good_token():
    status, body = handle_sync("secret", "secret", lambda: {"binance": {"nuevas": 2}})
    assert status == 200
    assert body["binance"]["nuevas"] == 2


def test_runner_exception_becomes_500():
    def boom():
        raise RuntimeError("explotó")
    status, body = handle_sync("secret", "secret", boom)
    assert status == 500
    assert "explotó" in body["error"]


def test_rejects_missing_token():
    # headers.get() returns None when the header is absent
    status, body = handle_sync(None, "secret", lambda: {"ok": True})
    assert status == 401
    assert "error" in body
