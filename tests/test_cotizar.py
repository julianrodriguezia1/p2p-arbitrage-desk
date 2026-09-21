import pytest

from bot.cotizar import (build_board, build_cotizacion, equivalencia, make_placa,
                         normalize_asset, quote_price)

_SPREAD_BOARD = {
    "exchanges": [
        {"exchange": "binance", "ask": 1564.99, "bid": 1560.50},
        {"exchange": "bybit", "ask": 1561.99, "bid": 1560.49},
        {"exchange": "okx", "ask": 1565.45, "bid": 1561.50},
    ],
    "cheapest_buy": {"exchange": "bitsoalpha", "price": 1559.93, "type": "cex"},
    "dearest_sell": {"exchange": "satoshitango", "price": 1568.80, "type": "cex"},
}


def test_build_board_deriva_modos_de_ask_bid():
    b = build_board(_SPREAD_BOARD, top=4)   # top=4 para que bybit entre en ambos lados
    bybit_buy = next(o for o in b["buys"] if o["venue"] == "bybit")
    assert bybit_buy["mode"] == "p2p"
    assert bybit_buy["publicando"] == 1560.49 and bybit_buy["tomando"] == 1561.99
    assert bybit_buy["best"] == 1560.49              # comprar: publicando (bid) manda
    bybit_sell = next(o for o in b["sells"] if o["venue"] == "bybit")
    assert bybit_sell["publicando"] == 1561.99 and bybit_sell["tomando"] == 1560.49
    assert bybit_sell["best"] == 1561.99             # vender: publicando (ask) manda


def test_build_board_cex_es_directo_y_ordena():
    b = build_board(_SPREAD_BOARD)
    assert b["buys"][0]["venue"] == "bitsoalpha"     # 1559.93 el más barato
    assert b["buys"][0]["mode"] == "cex" and b["buys"][0]["price"] == 1559.93
    assert b["sells"][0]["venue"] == "satoshitango"  # 1568.80 el más caro
    assert b["best_buy"] == 1559.93 and b["best_sell"] == 1568.80
    assert b["diff_ars"] == pytest.approx(8.87)
    assert b["diff_pct"] == pytest.approx(8.87 / 1559.93 * 100)


def test_build_board_top_limita_a_tres():
    b = build_board(_SPREAD_BOARD, top=3)
    assert len(b["buys"]) == 3 and len(b["sells"]) == 3   # 3 p2p + 1 cex, top 3


def test_build_board_sin_exchanges_no_rompe():
    b = build_board({"cheapest_buy": {"exchange": "belo", "price": 1550.0}})
    assert b["buys"] and b["buys"][0]["venue"] == "belo"
    assert b["sells"] == [] and b["best_sell"] is None
    assert b["diff_ars"] is None


def test_build_board_vacio():
    b = build_board({})
    assert b["buys"] == [] and b["sells"] == []
    assert b["best_buy"] is None and b["diff_pct"] is None

_SPREAD = {
    "top_buys": [
        {"exchange": "bitsoalpha", "price": 1556.88},
        {"exchange": "fiwind", "price": 1557.50},
        {"exchange": "letsbit", "price": 1558.90},
    ],
    "top_sells": [
        {"exchange": "binance", "price": 1568.60},
        {"exchange": "satoshitango", "price": 1567.20},
        {"exchange": "belo", "price": 1566.00},
    ],
    "cheapest_buy": {"exchange": "bitsoalpha", "price": 1556.88, "type": "cex"},
    "dearest_sell": {"exchange": "binance", "price": 1568.60, "type": "cex"},
}


def test_quote_compra_suma_el_margen():
    assert quote_price("compra", 1556.88, 2.0) == pytest.approx(1556.88 * 1.02)


def test_quote_venta_resta_el_margen():
    assert quote_price("venta", 1568.60, 1.0) == pytest.approx(1568.60 * 0.99)


def test_quote_side_invalido():
    with pytest.raises(ValueError):
        quote_price("otro", 1000, 1)


def test_build_cotizacion_compra_usa_top_buys_y_da_tres_opciones():
    c = build_cotizacion(_SPREAD, "compra", 2.0)
    assert c["base"] == 1556.88 and c["base_venue"] == "bitsoalpha"
    assert c["accion"] == "VENDO"
    assert c["quote"] == pytest.approx(1556.88 * 1.02)
    assert [o["exchange"] for o in c["options"]] == ["bitsoalpha", "fiwind", "letsbit"]


def test_build_cotizacion_venta_usa_top_sells():
    c = build_cotizacion(_SPREAD, "venta", 1.0)
    assert c["base"] == 1568.60 and c["base_venue"] == "binance"
    assert c["accion"] == "COMPRO"
    assert c["quote"] == pytest.approx(1568.60 * 0.99)
    assert len(c["options"]) == 3


def test_build_cotizacion_cae_al_single_si_no_hay_top():
    spread = {"cheapest_buy": {"exchange": "belo", "price": 1550.0}}
    c = build_cotizacion(spread, "compra", 2.0)
    assert c["base"] == 1550.0 and len(c["options"]) == 1


def test_build_cotizacion_sin_precio_falla():
    with pytest.raises(ValueError):
        build_cotizacion({"top_buys": []}, "compra", 2.0)


# CriptoYa caído: top_buys/sells y cheapest/dearest vacíos, pero exchanges (depth P2P) sí.
_SPREAD_SOLO_EXCHANGES = {
    "exchanges": [
        {"exchange": "bybit", "ask": 1574.97, "bid": 1570.90, "intra_pct": -0.26},
        {"exchange": "binance", "ask": 1575.70, "bid": 1572.50, "intra_pct": -0.20},
        {"exchange": "okx", "ask": 1573.99, "bid": 1570.17, "intra_pct": -0.24},
    ],
    "cheapest_buy": None, "dearest_sell": None,
    "top_buys": [], "top_sells": [],
}


def test_build_cotizacion_compra_cae_a_exchanges_si_criptoya_vacio():
    c = build_cotizacion(_SPREAD_SOLO_EXCHANGES, "compra", 0.5)
    assert c["base"] == 1573.99 and c["base_venue"] == "okx"   # ask más barato
    assert c["accion"] == "VENDO"
    assert c["quote"] == pytest.approx(1573.99 * 1.005)
    assert [o["exchange"] for o in c["options"]] == ["okx", "bybit", "binance"]


def test_build_cotizacion_venta_cae_a_exchanges_si_criptoya_vacio():
    c = build_cotizacion(_SPREAD_SOLO_EXCHANGES, "venta", 0.5)
    assert c["base"] == 1572.50 and c["base_venue"] == "binance"   # bid más caro
    assert c["accion"] == "COMPRO"
    assert c["quote"] == pytest.approx(1572.50 * 0.995)


def test_make_placa_devuelve_png():
    c = build_cotizacion(_SPREAD, "compra", 2.0)
    data = make_placa(c)
    assert isinstance(data, bytes) and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_cotizacion_placa_arma_png_con_quote_y_tablero(monkeypatch):
    import bot.commands as c
    spread = {**_SPREAD, **_SPREAD_BOARD}   # top_buys/sells para el quote + exchanges para el board
    monkeypatch.setattr(c, "fetch_json", lambda base, path, params=None: spread)
    monkeypatch.setattr(c, "_dolar_cripto", lambda: {"compra": 1557.69, "venta": 1565.46})
    png, caption = c.cotizacion_placa("http://x", "compra", 2.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    # quote al cliente = base compra 1556.88 * 1.02 = 1587.x
    assert "1.588" in caption
    # referencia dólar cripto para el usuario
    assert "Dólar cripto hoy" in caption and "1.558" in caption and "1.565" in caption
    # tablero para el usuario: los dos lados, modos y diferencia
    assert "COMPRÁS" in caption and "VENDÉS" in caption
    assert "public." in caption and "tom." in caption   # modo P2P de los exchanges
    assert "directo" in caption                          # CEX
    assert "Dif:" in caption


def test_cotizacion_placa_sin_dolar_ref_no_rompe(monkeypatch):
    import bot.commands as c
    monkeypatch.setattr(c, "fetch_json", lambda base, path, params=None: _SPREAD_BOARD)
    monkeypatch.setattr(c, "_dolar_cripto", lambda: None)   # dolarapi caído
    png, caption = c.cotizacion_placa("http://x", "compra", 2.0)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert "Dólar cripto" not in caption                    # se omite, sin romper


def test_cotizacion_placa_falla_devuelve_none(monkeypatch):
    import bot.commands as c
    def boom(base, path, params=None):
        raise RuntimeError("sin red")
    monkeypatch.setattr(c, "fetch_json", boom)
    png, caption = c.cotizacion_placa("http://x", "venta", 1.0)
    assert png is None and "probá de nuevo" in caption


# ── activo: USDT (default) y BTC ──────────────────────────────────────────

_SPREAD_BTC = {
    "asset": "BTC",
    "top_buys": [
        {"exchange": "binancep2p", "price": 122_800_000.0},
        {"exchange": "ripio", "price": 123_500_000.0},
    ],
    "top_sells": [
        {"exchange": "satoshitango", "price": 120_100_000.0},
        {"exchange": "buenbit", "price": 119_900_000.0},
    ],
}


@pytest.mark.parametrize("crudo", ["btc", "BTC", " btc ", "bitcoin", "Bitcoin"])
def test_normalize_asset_reconoce_btc(crudo):
    assert normalize_asset(crudo) == "BTC"


@pytest.mark.parametrize("crudo", [None, "", "usdt", "USDT", "cualquiera", 5])
def test_normalize_asset_cae_a_usdt(crudo):
    """Default seguro: si no se entiende, cotiza lo de siempre."""
    assert normalize_asset(crudo) == "USDT"


def test_build_cotizacion_lleva_el_activo():
    c = build_cotizacion(_SPREAD_BTC, "compra", 2.0, asset="BTC")
    assert c["asset"] == "BTC"
    assert c["base"] == 122_800_000.0 and c["base_venue"] == "binancep2p"
    assert c["quote"] == pytest.approx(122_800_000.0 * 1.02)


def test_build_cotizacion_sin_activo_es_usdt():
    assert build_cotizacion(_SPREAD, "compra", 2.0)["asset"] == "USDT"


def test_equivalencia_btc_muestra_solo_el_ticket_chico():
    """Sin repetir el precio de 1 BTC: ya es el número grande de la placa."""
    c = build_cotizacion(_SPREAD_BTC, "compra", 2.0, asset="BTC")  # 125.256.000
    assert equivalencia(c) == "0,01 BTC = $1.252.560"


def test_equivalencia_usdt_es_none():
    """El precio de USDT ya es por unidad: no hay nada que dimensionar."""
    assert equivalencia(build_cotizacion(_SPREAD, "compra", 2.0)) is None


def test_make_placa_btc_devuelve_png():
    c = build_cotizacion(_SPREAD_BTC, "venta", 1.0, asset="BTC")
    data = make_placa(c)
    assert isinstance(data, bytes) and data[:8] == b"\x89PNG\r\n\x1a\n"


def test_cotizacion_placa_btc_pide_el_activo_al_dashboard(monkeypatch):
    import bot.commands as c
    pedidos = []

    def _fetch(base, path, params=None):
        pedidos.append((path, params))
        return _SPREAD_BTC

    monkeypatch.setattr(c, "fetch_json", _fetch)
    png, caption = c.cotizacion_placa("http://x", "compra", 2.0, asset="BTC")
    assert pedidos == [("/api/spread/now", {"asset": "BTC"})]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert "BTC" in caption and "USDT" not in caption
    assert "0,01 BTC = $1.252.560" in caption     # la equivalencia del ticket chico


def test_cotizacion_placa_btc_no_muestra_dolar_cripto(monkeypatch):
    """El dólar cripto es el precio del USDT: al lado de un precio de BTC
    confunde en vez de ayudar."""
    import bot.commands as c
    monkeypatch.setattr(c, "fetch_json", lambda base, path, params=None: _SPREAD_BTC)
    monkeypatch.setattr(c, "_dolar_cripto", lambda: {"compra": 1557.69, "venta": 1565.46})
    _png, caption = c.cotizacion_placa("http://x", "compra", 2.0, asset="BTC")
    assert "Dólar cripto" not in caption


def test_cotizacion_placa_sin_activo_sigue_siendo_usdt(monkeypatch):
    import bot.commands as c
    pedidos = []

    def _fetch(base, path, params=None):
        pedidos.append(params)
        return _SPREAD

    monkeypatch.setattr(c, "fetch_json", _fetch)
    monkeypatch.setattr(c, "_dolar_cripto", lambda: None)
    _png, caption = c.cotizacion_placa("http://x", "compra", 2.0)
    assert pedidos == [{"asset": "USDT"}]
    assert "USDT" in caption and "BTC" not in caption


# ── libro ancho: un venue sin contraparte no es un precio de mercado ───────

# OKX en BTC/ARS medido el 2026-08-21: ask 135,5M contra bid 117,9M. No es una
# oportunidad del 15%, es que no hay con quién operar.
_SPREAD_LIBRO_ANCHO = {
    "exchanges": [
        {"exchange": "binance", "ask": 124_000_000.0, "bid": 121_000_000.0},
        {"exchange": "okx", "ask": 135_500_000.0, "bid": 117_900_000.0},
    ],
}


def test_build_board_marca_el_libro_ancho():
    b = build_board(_SPREAD_LIBRO_ANCHO)
    okx = next(o for o in b["buys"] if o["venue"] == "okx")
    binance = next(o for o in b["buys"] if o["venue"] == "binance")
    assert okx["ancho"] is True
    assert binance["ancho"] is False      # 2,5% de ancho: flaco pero real


def test_build_board_no_cuenta_el_libro_ancho_en_la_diferencia():
    """El bug a evitar: 'Dif +15%' que en realidad es OKX sin liquidez."""
    b = build_board(_SPREAD_LIBRO_ANCHO)
    assert b["best_buy"] == 121_000_000.0     # binance, no el bid de okx
    assert b["best_sell"] == 124_000_000.0    # binance, no el ask de okx
    assert b["diff_pct"] == pytest.approx(3_000_000 / 121_000_000 * 100)


def test_build_board_libros_normales_no_se_marcan():
    """USDT: los libros están en 0,2% de ancho, nada debe marcarse."""
    b = build_board(_SPREAD_BOARD, top=4)
    assert all(o["ancho"] is False for o in b["buys"] if o["mode"] == "p2p")
    assert b["best_buy"] == 1559.93 and b["best_sell"] == 1568.80


def test_build_board_todo_ancho_no_inventa_diferencia():
    b = build_board({"exchanges": [
        {"exchange": "okx", "ask": 135_500_000.0, "bid": 117_900_000.0}]})
    assert b["buys"][0]["ancho"] is True       # se sigue mostrando el dato
    assert b["best_buy"] is None and b["diff_pct"] is None


def test_board_line_avisa_del_libro_ancho():
    from bot.commands import _board_line
    linea = _board_line(1, {"venue": "okx", "mode": "p2p", "ancho": True,
                            "publicando": 117_900_000.0, "tomando": 135_500_000.0,
                            "best": 117_900_000.0})
    assert "libro ancho" in linea
