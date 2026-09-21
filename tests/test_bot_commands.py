from unittest.mock import patch

from bot.bridge_client import is_authorized
from bot.commands import format_spread, spread_text, format_stock, stock_text
from bot.commands import format_estrategia
from bot.commands import format_billeteras


def test_is_authorized_gate():
    assert is_authorized(426311895, 426311895) is True
    assert is_authorized(999, 426311895) is False


def test_format_spread_incluye_exchanges():
    data = {
        "asset": "USDT", "fiat": "ARS",
        "exchanges": [
            {"exchange": "binance", "ask": 1510.0, "bid": 1560.0, "intra_pct": 3.31},
            {"exchange": "okx", "ask": 1515.0, "bid": None, "intra_pct": None},
        ],
    }
    msg = format_spread(data)
    assert "binance" in msg and "1.510" in msg and "1.560" in msg
    assert "+3,3%" in msg                      # intra formateado
    assert "okx" in msg and "—" in msg          # bid faltante -> guion


def test_format_spread_mas_barato_mas_caro_y_spread():
    data = {
        "asset": "USDT", "fiat": "ARS",
        "exchanges": [{"exchange": "binance", "ask": 1548.0, "bid": 1544.0, "intra_pct": -0.2}],
        "cheapest_buy": {"exchange": "dolarapp", "price": 1482.0, "type": "remesa"},
        "dearest_sell": {"exchange": "binancep2p", "price": 1560.0, "type": "p2p"},
        "best_route": {"buy_ex": "dolarapp", "buy": 1482.0, "sell_ex": "binancep2p",
                       "sell": 1560.0, "gross_pct": 5.26},
    }
    msg = format_spread(data)
    assert "Más barato" in msg and "dolarapp" in msg and "1.482" in msg and "remesa" in msg
    assert "Más caro" in msg and "binancep2p" in msg and "1.560" in msg and "p2p" in msg
    assert "Spread" in msg and "+5,3%" in msg


def test_format_spread_sin_datos():
    data = {"asset": "USDT", "fiat": "ARS", "exchanges": [], "best_cross": None}
    assert "No pude leer el spread" in format_spread(data)


def test_spread_text_ok():
    fake = {"asset": "USDT", "fiat": "ARS",
            "exchanges": [{"exchange": "binance", "ask": 1510.0, "bid": 1560.0, "intra_pct": 3.31}],
            "best_cross": None}
    with patch("bot.commands.fetch_json", return_value=fake):
        msg = spread_text("http://x")
    assert "binance" in msg


def test_spread_text_error_amigable():
    with patch("bot.commands.fetch_json", side_effect=RuntimeError("down")):
        msg = spread_text("http://x")
    assert "No pude leer el spread ahora" in msg





def test_format_stock_con_compras_hoy():
    pos = {"asset": "USDT", "stock": 1832.0}
    cost = {"count": 6, "units": 2645.0, "avg_price": 1550.0, "breakeven": 1551.0}
    msg = format_stock(pos, cost)
    assert "1.832" in msg
    assert "2.645" in msg and "1.550" in msg
    assert "1.551" in msg


def test_format_stock_sin_compras_hoy():
    pos = {"asset": "USDT", "stock": 1832.0}
    cost = {"count": 0, "units": 0.0, "avg_price": None, "breakeven": None}
    msg = format_stock(pos, cost)
    assert "1.832" in msg
    assert "sin compras hoy" in msg.lower()


def test_stock_text_ok():
    def fake(base, path, params=None):
        if path == "/api/position":
            return {"asset": "USDT", "stock": 100.0}
        return {"count": 0, "units": 0.0, "avg_price": None, "breakeven": None}
    with patch("bot.commands.fetch_json", new=fake):
        msg = stock_text("http://x")
    assert "100" in msg


def test_stock_text_error_amigable():
    with patch("bot.commands.fetch_json", side_effect=RuntimeError("down")):
        assert "No pude leer tu stock" in stock_text("http://x")


def test_format_estrategia_headline_alternativas_y_aviso():
    data = {
        "asof": 1783100000.0, "volume": 1000.0,
        "best": {"kind": "media", "buy_venue": "bybitp2p", "buy_price": 1561.0, "buy_mode": "tomando",
                 "sell_venue": "kucoinp2p", "sell_price": 1578.0, "sell_mode": "publicando",
                 "net_pct": 0.8, "ars_per_1000": 12488.0},
        "alternatives": [
            {"kind": "mm", "buy_venue": "kucoinp2p", "buy_price": 1568.0, "buy_mode": "publicando",
             "sell_venue": "kucoinp2p", "sell_price": 1578.0, "sell_mode": "publicando",
             "net_pct": 0.55, "ars_per_1000": 8624.0},
            {"kind": "instant", "buy_venue": "bybitp2p", "buy_price": 1560.0, "buy_mode": "tomando",
             "sell_venue": "okexp2p", "sell_price": 1564.0, "sell_mode": "tomando",
             "net_pct": 0.15, "ars_per_1000": 2340.0},
        ],
        "outside_note": {"venue": "eldoradop2p", "side": "sell", "price": 1602.0},
    }
    txt = format_estrategia(data)
    assert "MEJOR AHORA" in txt
    assert "Bybit" in txt and "KuCoin" in txt          # labels legibles
    assert "publicando" in txt and "tomando" in txt
    assert "El Dorado" in txt
    assert "verificá liquidez" in txt.lower()
    assert "ask" not in txt.lower() and "bid" not in txt.lower()  # nomenclatura interna nunca


def test_format_estrategia_sin_jugada():
    data = {"asof": 1.0, "volume": 1000.0, "best": None, "alternatives": [], "outside_note": None}
    assert "Sin jugada" in format_estrategia(data)


def test_venue_label_cubre_todo_lo_emitible():
    import config
    import bot.commands as commands

    universo = set(config.CRIPTOYA_ARBITRAGE_WHITELIST) | {"huobip2p", "bingxp2p", "coinexp2p"}
    faltantes = universo - set(commands._VENUE_LABEL)
    assert not faltantes, f"venues sin label legible: {faltantes}"


def test_format_billeteras_tope_colors_and_restante():
    data = {"month": "2026-07", "sin_mapear": [], "wallets": {
        "MercadoPago": {"entra": 1240000, "sale": 0, "tope_in": 2000000,
                        "pct_in": 62.0, "restante_in": 760000,
                        "tope_out": None, "pct_out": None, "restante_out": None},
        "Lemon Cash": {"entra": 1700000, "sale": 0, "tope_in": 2000000,
                       "pct_in": 85.0, "restante_in": 300000,
                       "tope_out": None, "pct_out": None, "restante_out": None},
    }}
    out = format_billeteras(data)
    assert "Billeteras — 2026-07" in out
    assert "🟢 MercadoPago" in out       # 62% < 70
    assert "🟡 Lemon Cash" in out        # 85% en 70–90
    # más caliente arriba: Lemon (85) antes que MercadoPago (62)
    assert out.index("Lemon Cash") < out.index("MercadoPago")


def test_format_billeteras_sin_tope_and_unmapped():
    data = {"month": "2026-07", "sin_mapear": ["BilleteraNueva"], "wallets": {
        "Ualá": {"entra": 400000, "sale": 0, "tope_in": None, "pct_in": None,
                 "restante_in": None, "tope_out": None, "pct_out": None,
                 "restante_out": None},
    }}
    out = format_billeteras(data)
    assert "⚪ Ualá" in out and "sin tope" in out
    assert "sin mapear" in out and "BilleteraNueva" in out


def test_format_billeteras_desempate_alfabetico_same_pct():
    """Cuando dos billeteras tienen igual pct_in (o ambas sin tope),
    deben ordenarse alfabéticamente por nombre (desempate estable)."""
    data = {"month": "2026-07", "sin_mapear": [], "wallets": {
        "Zulu": {"entra": 800000, "sale": 0, "tope_in": 1000000,
                 "pct_in": 80.0, "restante_in": 200000,
                 "tope_out": None, "pct_out": None, "restante_out": None},
        "Alpha": {"entra": 800000, "sale": 0, "tope_in": 1000000,
                  "pct_in": 80.0, "restante_in": 200000,
                  "tope_out": None, "pct_out": None, "restante_out": None},
        "Mike": {"entra": 800000, "sale": 0, "tope_in": 1000000,
                 "pct_in": 80.0, "restante_in": 200000,
                 "tope_out": None, "pct_out": None, "restante_out": None},
    }}
    out = format_billeteras(data)
    # A igual calor (80%), debe aparecer en orden alfabético: Alpha, Mike, Zulu
    alpha_idx = out.index("Alpha")
    mike_idx = out.index("Mike")
    zulu_idx = out.index("Zulu")
    assert alpha_idx < mike_idx < zulu_idx, \
        f"Desempate alfabético fallido: Alpha@{alpha_idx}, Mike@{mike_idx}, Zulu@{zulu_idx}"


# ── La jugada por Binance: la que suma para el Comerciante Verificado ──────

_BIN_BEST = {"kind": "media", "buy_venue": "bybitp2p", "buy_price": 1561.0,
             "buy_mode": "tomando", "sell_venue": "kucoinp2p", "sell_price": 1578.0,
             "sell_mode": "publicando", "net_pct": 0.8, "ars_per_1000": 12488.0}
_BIN_PLAY = {"kind": "media", "buy_venue": "binancep2p", "buy_price": 1564.0,
             "buy_mode": "tomando", "sell_venue": "okexp2p", "sell_price": 1577.0,
             "sell_mode": "publicando", "net_pct": 0.62, "ars_per_1000": 9700.0,
             "patas_binance": 1}
_MERCHANT = {"requisitos": [
    {"clave": "ops_30d", "etiqueta": "Órdenes 30d", "valor": 120, "meta": 400,
     "unidad": "operaciones", "cumple": False, "pct": 30.0, "nota": ""},
    {"clave": "vol_30d_btc", "etiqueta": "Volumen 30d", "valor": None, "meta": 0.5,
     "unidad": "BTC", "cumple": False, "pct": None, "nota": "sin precio de BTC"},
]}


def test_format_binance_muestra_la_jugada_y_cuantas_ordenes_suma():
    from bot.commands import format_binance
    txt = format_binance({"best": _BIN_BEST, "binance": _BIN_PLAY,
                          "best_en_binance": False}, _MERCHANT)
    assert "Binance" in txt and "OKX" in txt
    assert "+0,6" in txt                      # el neto, con coma decimal
    assert "1 orden" in txt                   # lo que suma para el Verificado
    assert "120" in txt and "400" in txt      # el avance del Verificado
    assert "FALTA" in txt                     # el volumen no se pudo medir
    assert "ask" not in txt.lower() and "bid" not in txt.lower()


def test_format_binance_cuando_la_mejor_ya_pasa_por_binance():
    from bot.commands import format_binance
    best = {**_BIN_BEST, "buy_venue": "binancep2p"}
    txt = format_binance({"best": best, "binance": None, "best_en_binance": True}, None)
    assert "Binance" in txt
    assert "+0,8" in txt


def test_format_binance_sin_jugada_lo_dice():
    from bot.commands import format_binance
    txt = format_binance({"best": _BIN_BEST, "binance": None,
                          "best_en_binance": False}, None)
    assert "binance" in txt.lower()
    assert "sin jugada" in txt.lower() or "ninguna" in txt.lower()


def test_binance_text_error_amigable():
    from bot.commands import binance_text
    with patch("bot.commands.fetch_json", side_effect=RuntimeError("down")):
        assert "no pude" in binance_text("http://x").lower()


def test_binance_text_anda_aunque_el_merchant_falle():
    """El progreso del Verificado es un extra: si no responde, la jugada igual
    se contesta."""
    from bot.commands import binance_text

    def fake(base, path, params=None):
        if "merchant" in path:
            raise RuntimeError("down")
        return {"best": _BIN_BEST, "binance": _BIN_PLAY, "best_en_binance": False}

    with patch("bot.commands.fetch_json", side_effect=fake):
        txt = binance_text("http://x")
    assert "OKX" in txt
