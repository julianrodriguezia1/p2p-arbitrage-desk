# tests/test_sync_core.py
import types
from datetime import date
from decimal import Decimal

import pytest

from core.movements import Movement, Side, Source
from companion.sync_core import default_fetchers, movement_to_payload, run_sync, run_sync_default


def _mov(order_id: str) -> Movement:
    return Movement(
        side=Side.COMPRA, date=date(2026, 6, 18), order_id=order_id,
        usd_gross=Decimal("207.823551"), commission=Decimal("2.078243"),
        usd_net=Decimal("205.745308"), price=Decimal("1491.65"),
        total_ars=Decimal("310000.00"), exchange_coin="Binance / USDT",
        bank="Mercadopago", source=Source.BINANCE_API,
    )


def test_payload_serializes_decimals_as_str():
    p = movement_to_payload(_mov("abc"))
    assert p == {
        "side": "COMPRA", "date": "2026-06-18", "order_id": "abc",
        "usd_gross": "207.823551", "commission": "2.078243",
        "usd_net": "205.745308", "price": "1491.65",
        "total_ars": "310000.00", "exchange_coin": "Binance / USDT",
        "bank": "Mercadopago",
    }


def test_run_sync_counts_new_existing_and_errors():
    movs = [_mov("a"), _mov("b"), _mov("c")]
    statuses = {"a": (201, "ok"), "b": (409, "Ya cargado"), "c": (502, "boom")}
    calls = []

    def fake_push(payload, base_url, session=None):
        calls.append((payload["order_id"], base_url))
        return statuses[payload["order_id"]]

    out = run_sync({"binance": lambda: movs}, fake_push, "http://vps")
    assert out["binance"]["nuevas"] == 1
    assert out["binance"]["ya"] == 1
    assert len(out["binance"]["errores"]) == 1
    assert "#c" in out["binance"]["errores"][0]
    assert calls[0] == ("a", "http://vps")


def test_run_sync_reports_fetch_failure_without_crashing():
    def boom():
        raise RuntimeError("451 geobloqueado")

    out = run_sync({"bybit": boom}, lambda *a, **k: (201, ""), "http://vps")
    assert out["bybit"]["nuevas"] == 0
    assert "451" in out["bybit"]["errores"][0]


def test_default_fetchers_keys_and_lazy():
    cfg = types.SimpleNamespace(
        BINANCE_API_KEY="k", BINANCE_API_SECRET="s",
        BYBIT_API_KEY="k", BYBIT_API_SECRET="s",
    )
    fetchers = default_fetchers(cfg)
    assert set(fetchers) == {"binance", "bybit"}
    assert callable(fetchers["binance"]) and callable(fetchers["bybit"])


def test_run_sync_default_raises_without_vps_url():
    cfg = types.SimpleNamespace(
        VPS_API_URL="",
        BINANCE_API_KEY="k", BINANCE_API_SECRET="s",
        BYBIT_API_KEY="k", BYBIT_API_SECRET="s",
    )
    with pytest.raises(RuntimeError):
        run_sync_default(cfg)


def test_run_sync_default_delegates_to_run_sync(monkeypatch):
    cfg = types.SimpleNamespace(
        VPS_API_URL="http://vps",
        BINANCE_API_KEY="k", BINANCE_API_SECRET="s",
        BYBIT_API_KEY="k", BYBIT_API_SECRET="s",
    )
    captured = {}

    def fake_default_fetchers(config):
        return {"binance": lambda: []}

    def fake_run_sync(fetchers, push, base_url):
        captured["base_url"] = base_url
        captured["fetchers"] = fetchers
        return {"ok": True}

    monkeypatch.setattr("companion.sync_core.default_fetchers", fake_default_fetchers)
    monkeypatch.setattr("companion.sync_core.run_sync", fake_run_sync)
    out = run_sync_default(cfg)
    assert out == {"ok": True}
    assert captured["base_url"] == "http://vps"
