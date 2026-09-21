# tests/test_spread_alert_cli.py
from dataclasses import dataclass
from unittest.mock import patch

from cli.spread_alert import run_once
from core.spread_alert import load_state


def _fake_quote(exchange, ask, bid):
    from p2p_scanner import ExchangeQuote
    q = ExchangeQuote(exchange=exchange, ask_ads=[], bid_ads=[])
    q.best_ask = ask
    q.best_bid = bid
    return q


@dataclass
class _Route:
    buy_ex: str; buy_ask: float; sell_ex: str; sell_bid: float; gross_pct: float


def test_run_once_sends_alert_on_new_cross(tmp_path):
    sent = []

    def fake_scan(asset, fiat):
        # bybit barato (ask 1548) / binance caro (bid 1560) -> cross gordo
        return [_fake_quote("bybit", 1548.0, 1549.0),
                _fake_quote("binance", 1559.0, 1560.0)]

    def fake_send(msg, token, chat_id):
        sent.append(msg)

    state = tmp_path / "state.json"
    with patch("cli.spread_alert.config") as cfg:
        cfg.SPREAD_ALERT_MIN_PCT = 0.5
        cfg.SPREAD_ALERT_CEXP2P_PCT = 1.0
        cfg.SPREAD_ALERT_CROSS_PCT = 0.2
        cfg.SPREAD_ALERT_INTRA_PCT = 1.0
        cfg.SPREAD_ALERT_COSTO_PCT = 1.5
        cfg.SPREAD_ALERT_HYSTERESIS_PCT = 0.1
        cfg.SPREAD_ALERT_STATE_PATH = state
        cfg.TRADES_DB_PATH = tmp_path / "nope.db"   # DB vacía (SQLite la crea), all_movements() -> [], avg=None -> costo salteado
        cfg.TELEGRAM_BOT_TOKEN = "tok"
        cfg.TELEGRAM_CHAT_ID = "123"
        n = run_once(scan_fn=fake_scan, send_fn=fake_send, arb_fn=lambda v: [])

    assert n >= 1
    assert sent and "cross-exchange" in sent[0]
    # estado persistido -> segunda corrida NO re-avisa
    assert load_state(state)


def test_run_once_empty_scan_sends_nothing(tmp_path):
    sent = []
    with patch("cli.spread_alert.config") as cfg:
        cfg.SPREAD_ALERT_MIN_PCT = 0.5
        cfg.SPREAD_ALERT_CEXP2P_PCT = 1.0
        cfg.SPREAD_ALERT_CROSS_PCT = 0.2
        cfg.SPREAD_ALERT_INTRA_PCT = 1.0
        cfg.SPREAD_ALERT_COSTO_PCT = 1.5
        cfg.SPREAD_ALERT_HYSTERESIS_PCT = 0.1
        cfg.SPREAD_ALERT_STATE_PATH = tmp_path / "state.json"
        cfg.TRADES_DB_PATH = tmp_path / "nope.db"
        cfg.TELEGRAM_BOT_TOKEN = "tok"
        cfg.TELEGRAM_CHAT_ID = "123"
        n = run_once(scan_fn=lambda a, f: [], send_fn=lambda m, t, c: sent.append(m), arb_fn=lambda v: [])
    assert n == 0
    assert sent == []


def test_run_once_second_run_is_silent(tmp_path):
    sent = []

    def fake_scan(asset, fiat):
        return [_fake_quote("bybit", 1548.0, 1549.0),
                _fake_quote("binance", 1559.0, 1560.0)]

    with patch("cli.spread_alert.config") as cfg:
        cfg.SPREAD_ALERT_MIN_PCT = 0.5
        cfg.SPREAD_ALERT_CEXP2P_PCT = 1.0
        cfg.SPREAD_ALERT_CROSS_PCT = 0.2
        cfg.SPREAD_ALERT_INTRA_PCT = 1.0
        cfg.SPREAD_ALERT_COSTO_PCT = 1.5
        cfg.SPREAD_ALERT_HYSTERESIS_PCT = 0.1
        cfg.SPREAD_ALERT_STATE_PATH = tmp_path / "state.json"
        cfg.TRADES_DB_PATH = tmp_path / "nope.db"
        cfg.TELEGRAM_BOT_TOKEN = "tok"
        cfg.TELEGRAM_CHAT_ID = "123"
        send = lambda m, t, c: sent.append(m)
        first = run_once(scan_fn=fake_scan, send_fn=send, arb_fn=lambda v: [])
        second = run_once(scan_fn=fake_scan, send_fn=send, arb_fn=lambda v: [])

    assert first >= 1
    assert second == 0           # ya estaba activa -> silencio
    assert len(sent) == first


def test_run_once_alerta_cexp2p(tmp_path):
    sent = []

    def fake_scan(asset, fiat):
        # un solo exchange => sin cross/intra; la única alerta vendrá de cexp2p
        return [_fake_quote("binance", 1556.0, 1552.0)]

    def fake_route():
        return _Route("ripio", 1510.0, "okexp2p", 1535.0, 1.66)

    with patch("cli.spread_alert.config") as cfg:
        cfg.SPREAD_ALERT_MIN_PCT = 0.5
        cfg.SPREAD_ALERT_CROSS_PCT = 0.2
        cfg.SPREAD_ALERT_INTRA_PCT = 1.0
        cfg.SPREAD_ALERT_COSTO_PCT = 1.5
        cfg.SPREAD_ALERT_HYSTERESIS_PCT = 0.1
        cfg.SPREAD_ALERT_CEXP2P_PCT = 1.0
        cfg.SPREAD_ALERT_STATE_PATH = tmp_path / "state.json"
        cfg.TRADES_DB_PATH = tmp_path / "nope.db"
        cfg.TELEGRAM_BOT_TOKEN = "tok"
        cfg.TELEGRAM_CHAT_ID = "123"
        n = run_once(scan_fn=fake_scan, send_fn=lambda m, t, c: sent.append(m),
                     route_fn=fake_route, arb_fn=lambda v: [])

    assert n >= 1
    assert sent and "CEX→P2P" in sent[0]


def test_run_once_route_none_no_rompe(tmp_path):
    sent = []
    with patch("cli.spread_alert.config") as cfg:
        cfg.SPREAD_ALERT_MIN_PCT = 0.5
        cfg.SPREAD_ALERT_CROSS_PCT = 0.2
        cfg.SPREAD_ALERT_INTRA_PCT = 1.0
        cfg.SPREAD_ALERT_COSTO_PCT = 1.5
        cfg.SPREAD_ALERT_HYSTERESIS_PCT = 0.1
        cfg.SPREAD_ALERT_CEXP2P_PCT = 1.0
        cfg.SPREAD_ALERT_STATE_PATH = tmp_path / "state.json"
        cfg.TRADES_DB_PATH = tmp_path / "nope.db"
        cfg.TELEGRAM_BOT_TOKEN = "tok"
        cfg.TELEGRAM_CHAT_ID = "123"
        n = run_once(scan_fn=lambda a, f: [_fake_quote("binance", 1556.0, 1552.0)],
                     send_fn=lambda m, t, c: sent.append(m),
                     route_fn=lambda: None, arb_fn=lambda v: [])
    assert n == 0 and sent == []


def _arb_alert():
    from types import SimpleNamespace
    return SimpleNamespace(
        kind="media", route="media", pct=0.5, threshold=0.2,
        title="🟡 X",
        detail="Comprá tomando en bybitp2p @ 1.564 → vendé publicando en okexp2p @ 1.575 · +0,50% neto",
    )


def test_run_once_narra_cuando_esta_prendido(tmp_path, monkeypatch):
    import config
    import core.narrate as narr

    monkeypatch.setattr(config, "SPREAD_NARRATE", True)
    monkeypatch.setattr(config, "SPREAD_ALERT_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(narr, "ada_generate", lambda prompt: "CALL NARRADA")

    sent = {}

    def fake_send(text, token, chat):
        sent["text"] = text

    alert = _arb_alert()
    n = run_once(
        scan_fn=lambda a, f: [],
        send_fn=fake_send,
        arb_fn=lambda vol: [alert],
    )

    assert n == 1
    assert sent.get("text") == "CALL NARRADA"


def test_run_once_texto_numerico_cuando_esta_apagado(tmp_path, monkeypatch):
    import config
    from core.spread_alert import format_message

    monkeypatch.setattr(config, "SPREAD_NARRATE", False)
    monkeypatch.setattr(config, "SPREAD_ALERT_STATE_PATH", tmp_path / "state.json")

    sent = {}

    def fake_send(text, token, chat):
        sent["text"] = text

    alert = _arb_alert()
    n = run_once(
        scan_fn=lambda a, f: [],
        send_fn=fake_send,
        arb_fn=lambda vol: [alert],
    )

    assert n == 1
    assert sent.get("text") == format_message([alert])
