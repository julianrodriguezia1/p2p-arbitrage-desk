from datetime import datetime
from decimal import Decimal

from core.criptoya import Reference
from cli import spread_logger, spread_report


def _ref():
    return Reference(
        best_bid=Decimal("1510"), best_bid_exchange="binance",
        best_ask=Decimal("1490"), best_ask_exchange="weexp2p",
    )


def test_spread_row_calcula_spread_y_pct():
    now = datetime(2026, 6, 8, 14, 30, tzinfo=spread_logger.ART)
    row = spread_logger.spread_row(_ref(), now)
    assert row["best_ask"] == "1490.0000"
    assert row["ask_exchange"] == "weexp2p"
    assert row["best_bid"] == "1510.0000"
    assert row["spread_ars"] == "20.0000"
    # 20 / 1490 * 100 = 1.3423%
    assert row["spread_pct"].startswith("1.342")
    assert row["hour"] == 14
    assert row["weekday"] == "Mon"


def test_append_row_escribe_header_una_sola_vez(tmp_path):
    path = tmp_path / "sub" / "log.csv"
    now = datetime(2026, 6, 8, 14, 0, tzinfo=spread_logger.ART)
    spread_logger.append_row(path, spread_logger.spread_row(_ref(), now))
    spread_logger.append_row(path, spread_logger.spread_row(_ref(), now))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("timestamp_art,")  # header
    assert len(lines) == 3  # header + 2 filas


def test_sample_once_devuelve_none_si_no_hay_referencia(tmp_path):
    path = tmp_path / "log.csv"
    row = spread_logger.sample_once(
        path, fetch_ref=lambda *a, **k: None,
        whitelist={"x"}, volume=1000,
    )
    assert row is None
    assert not path.exists()  # no escribe nada si CriptoYa falló


def test_sample_once_escribe_cuando_hay_referencia(tmp_path):
    path = tmp_path / "log.csv"
    now = datetime(2026, 6, 8, 9, 0, tzinfo=spread_logger.ART)
    row = spread_logger.sample_once(
        path, fetch_ref=lambda *a, **k: _ref(),
        whitelist={"x"}, volume=1000, now_fn=lambda: now,
    )
    assert row is not None
    assert path.exists()
    assert "weexp2p" in path.read_text(encoding="utf-8")


# --- reporte ---

ROWS = [
    {"hour": "9", "weekday": "Mon", "spread_pct": "1.0"},
    {"hour": "9", "weekday": "Tue", "spread_pct": "3.0"},
    {"hour": "14", "weekday": "Mon", "spread_pct": "0.5"},
    {"hour": "bad", "weekday": "Mon", "spread_pct": "x"},  # se ignora
]


def test_group_by_hora_ignora_invalidas():
    g = spread_report.group_by(ROWS, "hour")
    assert g["9"] == [1.0, 3.0]
    assert g["14"] == [0.5]
    assert "bad" not in g  # spread_pct no numérico => fila descartada


def test_filter_outliers_descarta_fantasmas():
    rows = [
        {"spread_pct": "1.5"},    # ok
        {"spread_pct": "20.12"},  # fantasma (>5)
        {"spread_pct": "-8.0"},   # fuera de rango bajo
        {"spread_pct": "x"},      # inválido
        {"spread_pct": "2.0"},    # ok
    ]
    kept, dropped = spread_report.filter_outliers(rows, -5.0, 5.0)
    assert [r["spread_pct"] for r in kept] == ["1.5", "2.0"]
    assert dropped == 3


def test_summarize_calcula_stats():
    stats = spread_report.summarize(spread_report.group_by(ROWS, "hour"))
    assert stats["9"]["n"] == 2
    assert stats["9"]["mean"] == 2.0
    assert stats["9"]["median"] == 2.0
    assert stats["9"]["max"] == 3.0
