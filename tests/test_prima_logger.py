"""Tests del logger de prima: arma filas y las acumula sin perder datos."""
import csv
from datetime import datetime, timezone, timedelta

import pytest

from cli.prima_logger import (
    ART,
    CSV_HEADER,
    Muestra,
    append_row,
    prima_row,
)

AHORA = datetime(2026, 8, 23, 14, 30, 0, tzinfo=ART)


def _muestra(**kw):
    base = dict(asset="BTC", venue="binance", spot_usd=77000.0,
                ask_ars=123_750_000.0, bid_ars=121_800_000.0,
                usdt_ask=1587.9, usdt_bid=1585.0,
                n_ask=20, n_bid=20,
                depth_ask_usd=71_593.0, depth_bid_usd=657_809.0)
    base.update(kw)
    return Muestra(**base)


def test_prima_row_calcula_fx_y_prima():
    r = prima_row(_muestra(), AHORA)
    assert r["asset"] == "BTC"
    assert float(r["ask_fx"]) == pytest.approx(1607.14, abs=0.01)
    assert float(r["prima_ask_pct"]) == pytest.approx(1.21, abs=0.02)
    assert float(r["prima_bid_pct"]) == pytest.approx(-0.21, abs=0.02)
    assert float(r["ancho_pct"]) == pytest.approx(1.60, abs=0.02)


def test_prima_row_guarda_hora_y_dia_en_art():
    """El análisis es 'a qué hora se abre la prima': la hora tiene que ser ART."""
    r = prima_row(_muestra(), AHORA)
    assert r["hour"] == 14
    assert r["weekday"] == "Sun"
    assert r["timestamp_art"].startswith("2026-08-23T14:30:00")


def test_prima_row_guarda_profundidad_y_conteo_de_avisos():
    """Sin esto no se puede distinguir una prima real de un libro vacío."""
    r = prima_row(_muestra(n_ask=3, depth_ask_usd=1234.0), AHORA)
    assert int(r["n_ask"]) == 3
    assert float(r["depth_ask_usd"]) == pytest.approx(1234.0)


def test_prima_row_tolera_punta_faltante():
    r = prima_row(_muestra(ask_ars=None, n_ask=0, depth_ask_usd=0.0), AHORA)
    assert r["ask_fx"] == ""
    assert r["prima_ask_pct"] == ""
    assert r["ancho_pct"] == ""
    assert r["bid_fx"] != ""


def test_prima_row_del_usdt_no_tiene_prima_contra_si_mismo():
    r = prima_row(_muestra(asset="USDT", spot_usd=1.0,
                           ask_ars=1587.9, bid_ars=1585.0), AHORA)
    assert float(r["prima_ask_pct"]) == pytest.approx(0.0, abs=0.001)
    assert float(r["ancho_pct"]) == pytest.approx(0.183, abs=0.01)


def test_append_row_escribe_header_solo_una_vez(tmp_path):
    p = tmp_path / "sub" / "prima.csv"
    append_row(p, prima_row(_muestra(), AHORA))
    append_row(p, prima_row(_muestra(asset="ETH", spot_usd=3000.0,
                                     ask_ars=4_832_000.0, bid_ars=4_740_000.0), AHORA))
    rows = list(csv.DictReader(p.open(encoding="utf-8")))
    assert len(rows) == 2
    assert [r["asset"] for r in rows] == ["BTC", "ETH"]
    assert p.read_text(encoding="utf-8").count("timestamp_art") == 1


def test_append_row_respeta_el_header_declarado(tmp_path):
    p = tmp_path / "prima.csv"
    append_row(p, prima_row(_muestra(), AHORA))
    assert list(csv.reader(p.open(encoding="utf-8")))[0] == CSV_HEADER


def test_art_es_utc_menos_3():
    assert ART.utcoffset(None) == timedelta(hours=-3)


# ── Varios venues en la misma ronda ────────────────────────────────────────
# Sin esto sólo había histórico de Binance y no se podía contestar "a qué hora
# hay más libro en KuCoin", que es la punta con la que se combina Binance.

def test_main_recorre_todos_los_venues(monkeypatch, tmp_path):
    import cli.prima_logger as pl

    vistos = []
    monkeypatch.setattr(pl, "sample_once",
                        lambda path, *, venue, assets: vistos.append((venue, tuple(assets))) or 1)
    pl.main(["--once", "--csv", str(tmp_path / "x.csv"),
             "--venues", "binance", "kucoin", "--assets", "usdt"])
    assert vistos == [("binance", ("USDT",)), ("kucoin", ("USDT",))]


def test_main_sigue_aceptando_venue_en_singular(monkeypatch, tmp_path):
    """La unit de systemd vieja pasa --venue; no se puede romper en el deploy."""
    import cli.prima_logger as pl

    vistos = []
    monkeypatch.setattr(pl, "sample_once",
                        lambda path, *, venue, assets: vistos.append(venue) or 1)
    pl.main(["--once", "--csv", str(tmp_path / "x.csv"), "--venue", "bybit"])
    assert vistos == ["bybit"]


def test_un_venue_que_falla_no_corta_la_ronda(monkeypatch, tmp_path):
    """Si KuCoin no responde, Binance igual se tiene que loguear."""
    import cli.prima_logger as pl

    def fake(path, *, venue, assets):
        if venue == "kucoin":
            raise RuntimeError("451")
        return 3

    monkeypatch.setattr(pl, "sample_once", fake)
    assert pl.main(["--once", "--csv", str(tmp_path / "x.csv"),
                    "--venues", "kucoin", "binance"]) == 0
