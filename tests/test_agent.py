import pytest

from companion import agent


def test_poll_once_devuelve_job_id():
    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"job_id": "abc123"}
    def fake_get(url, headers, timeout): return FakeResp()
    assert agent.poll_once("http://vps", "tok", get=fake_get) == "abc123"


def test_poll_once_sin_job_devuelve_none():
    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"job_id": None}
    assert agent.poll_once("http://vps", "tok", get=lambda *a, **k: FakeResp()) is None


def test_handle_job_ok_reporta_resultado():
    capturado = {}
    def fake_report(base_url, token, job_id, ok, result=None, error=None):
        capturado.update(job_id=job_id, ok=ok, result=result, error=error)
    agent.handle_job("j1", lambda: {"binance": {"nuevas": 1}},
                     "http://vps", "tok", report_fn=fake_report)
    assert capturado["ok"] is True
    assert capturado["result"] == {"binance": {"nuevas": 1}}


def test_handle_job_error_reporta_error():
    capturado = {}
    def fake_report(base_url, token, job_id, ok, result=None, error=None):
        capturado.update(ok=ok, error=error)
    def boom(): raise RuntimeError("sin keys")
    agent.handle_job("j1", boom, "http://vps", "tok", report_fn=fake_report)
    assert capturado["ok"] is False
    assert "sin keys" in capturado["error"]
