import threading

from companion.controller import SyncController


def test_run_stores_last_result():
    ctrl = SyncController(lambda: {"binance": {"nuevas": 1, "ya": 0, "errores": []}})
    out = ctrl.run()
    assert out["binance"]["nuevas"] == 1
    assert ctrl.last_result == out


def test_concurrent_run_returns_busy():
    started = threading.Event()
    release = threading.Event()

    def slow():
        started.set()
        release.wait(timeout=2)
        return {"ok": True}

    ctrl = SyncController(slow)
    t = threading.Thread(target=ctrl.run)
    t.start()
    started.wait(timeout=2)
    assert ctrl.run() == {"busy": True}  # el segundo no entra
    release.set()
    t.join(timeout=2)
