import pytest
from decimal import Decimal

from core import criptoya


@pytest.fixture(autouse=True)
def _clear_cache():
    criptoya._CACHE.clear()
    criptoya._ARB_CACHE.clear()
    criptoya._EXT_CACHE.clear()
    criptoya._PAYLOAD_CACHE.clear()

WL = {"lemoncash", "ripio", "buenbit"}

PAYLOAD = {
    "lemoncash": {"ask": 1500.0, "bid": 1490.0, "time": 1},
    "ripio":     {"ask": 1495.0, "bid": 1485.0, "time": 1},
    "buenbit":   {"ask": 1510.0, "bid": 1498.0, "time": 1},
    "dolarapp":  {"ask": 1400.0, "bid": 1399.0, "time": 1},  # fuera de whitelist
}


def test_best_reference_elige_mejor_bid_y_mejor_ask():
    ref = criptoya.best_reference(PAYLOAD, WL)
    assert ref.best_bid == Decimal("1498")        # max bid (buenbit)
    assert ref.best_bid_exchange == "buenbit"
    assert ref.best_ask == Decimal("1495")        # min ask (ripio)
    assert ref.best_ask_exchange == "ripio"


def test_best_reference_ignora_fuera_de_whitelist():
    # dolarapp tiene el ask más bajo pero NO está en whitelist => se ignora
    ref = criptoya.best_reference(PAYLOAD, WL)
    assert ref.best_ask_exchange != "dolarapp"


def test_best_reference_none_si_no_hay_whitelist():
    assert criptoya.best_reference({"dolarapp": {"ask": 1, "bid": 1}}, WL) is None


def test_best_reference_ignora_ask_o_bid_en_cero():
    # huobip2p sin ofertas (ask/bid 0) no debe ganar como "más barato".
    payload = {
        "lemoncash": {"ask": 1500.0, "bid": 1490.0},
        "huobip2p": {"ask": 0, "bid": 0},
    }
    ref = criptoya.best_reference(payload, {"lemoncash", "huobip2p"})
    assert ref.best_ask == Decimal("1500")
    assert ref.best_ask_exchange == "lemoncash"
    assert ref.best_bid_exchange == "lemoncash"


def test_best_reference_ignora_entradas_invalidas():
    payload = {
        "lemoncash": {"ask": "x", "bid": 1490.0},   # ask no numérico
        "ripio": {"bid": 1485.0},                    # falta ask
        "buenbit": {"ask": 1510.0, "bid": 1498.0},   # válido
    }
    ref = criptoya.best_reference(payload, WL)
    assert ref.best_ask_exchange == "buenbit"
    assert ref.best_bid_exchange == "buenbit"


def test_fetch_reference_parsea_y_cachea(monkeypatch):
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return PAYLOAD

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls["n"] += 1
            return FakeResp()

    clock = {"t": 1000.0}
    ref = criptoya.fetch_reference(
        "USDT", "ARS", 1000, whitelist=WL,
        session=FakeSession(), now=lambda: clock["t"], ttl=30.0,
    )
    assert ref.best_ask_exchange == "ripio"
    assert calls["n"] == 1
    # 2ª llamada dentro del TTL: NO vuelve a pegarle a la red
    criptoya.fetch_reference(
        "USDT", "ARS", 1000, whitelist=WL,
        session=FakeSession(), now=lambda: clock["t"] + 5, ttl=30.0,
    )
    assert calls["n"] == 1


def test_fetch_reference_refresca_tras_expirar_ttl():
    calls = {"n": 0}

    class FakeResp:
        def raise_for_status(self): pass
        def json(self): return PAYLOAD

    class FakeSession:
        def get(self, url, headers=None, timeout=None):
            calls["n"] += 1
            return FakeResp()

    sess = FakeSession()
    criptoya.fetch_reference("USDT", "ARS", 1000, whitelist=WL,
                             session=sess, now=lambda: 1000.0, ttl=30.0)
    # pasados 31s (> ttl) => vuelve a pegarle a la red
    criptoya.fetch_reference("USDT", "ARS", 1000, whitelist=WL,
                             session=sess, now=lambda: 1031.0, ttl=30.0)
    assert calls["n"] == 2


def test_fetch_reference_none_si_la_red_falla():
    class BoomSession:
        def get(self, *a, **k): raise RuntimeError("boom")

    ref = criptoya.fetch_reference(
        "USDT", "ARS", 1000, whitelist=WL,
        session=BoomSession(), now=lambda: 2000.0,
    )
    assert ref is None


def test_arbitrage_whitelist_excluye_remesa_e_incluye_borderline():
    import importlib, config
    importlib.reload(config)
    wl = config.CRIPTOYA_ARBITRAGE_WHITELIST
    # remesa y P2P globales NUNCA
    # (KuCoin salió de acá: aprobado como venue pleno 2026-07-01 por decisión
    #  del usuario — zero-fee, order book real, retiro a ARS vía P2P)
    for banned in ("dolarapp", "takenos", "airtm", "astropay", "wallbit",
                   "p2pme", "grabrfi", "peanut", "vibrant", "vitawallet",
                   "mexc", "mexcp2p", "huobip2p", "weexp2p",
                   "eldoradop2p"):
        assert banned not in wl, f"{banned} no puede estar en la whitelist de arbitraje"
    # reales sí, incluidos los borderline confirmados (Bitget, SaldoAr, KuCoin)
    for ok in ("binance", "binancep2p", "okexp2p", "bybit", "bitgetp2p",
               "saldo", "lemoncash", "ripio", "fiwind", "decrypto", "bitsoalpha",
               "kucoinp2p"):
        assert ok in wl, f"{ok} debería estar en la whitelist de arbitraje"
    assert config.MAX_QUOTE_AGE_MIN == 30
    assert config.SPREAD_ALERT_CEXP2P_PCT == 1.0


# --- Tests para arbitrage_route ---
from core.criptoya import arbitrage_route, ArbRoute

NOW = 1_000_000.0  # referencia de "ahora" para los tests
FRESH = NOW - 60   # 1 min de antigüedad
STALE = NOW - 3600 # 60 min de antigüedad


def test_arbitrage_route_elige_ask_min_y_bid_max():
    payload = {
        "ripio":    {"ask": 1510.0, "bid": 1500.0, "time": FRESH},
        "okexp2p":  {"ask": 1520.0, "bid": 1535.0, "time": FRESH},
        "binance":  {"ask": 1515.0, "bid": 1525.0, "time": FRESH},
    }
    wl = {"ripio", "okexp2p", "binance"}
    r = arbitrage_route(payload, wl, max_age_min=30, now=NOW)
    assert isinstance(r, ArbRoute)
    assert r.buy_ex == "ripio" and r.buy_ask == 1510.0
    assert r.sell_ex == "okexp2p" and r.sell_bid == 1535.0
    assert abs(r.gross_pct - (1535.0 - 1510.0) / 1510.0 * 100) < 1e-9


def test_arbitrage_route_ignora_fuera_de_whitelist():
    # dolarapp tiene el bid más alto pero NO está en la whitelist -> no se elige
    payload = {
        "ripio":    {"ask": 1510.0, "bid": 1500.0, "time": FRESH},
        "okexp2p":  {"ask": 1520.0, "bid": 1530.0, "time": FRESH},
        "dolarapp": {"ask": 1400.0, "bid": 1700.0, "time": FRESH},
    }
    wl = {"ripio", "okexp2p"}
    r = arbitrage_route(payload, wl, max_age_min=30, now=NOW)
    assert r.sell_ex == "okexp2p" and r.sell_bid == 1530.0
    assert r.buy_ex == "ripio"


def test_arbitrage_route_descarta_rancios():
    # binance tiene un bid enorme pero rancio -> NO genera spread falso
    payload = {
        "ripio":   {"ask": 1510.0, "bid": 1500.0, "time": FRESH},
        "okexp2p": {"ask": 1520.0, "bid": 1525.0, "time": FRESH},
        "binance": {"ask": 1515.0, "bid": 9999.0, "time": STALE},
    }
    wl = {"ripio", "okexp2p", "binance"}
    r = arbitrage_route(payload, wl, max_age_min=30, now=NOW)
    assert r.sell_bid == 1525.0  # ignoró el 9999 rancio


def test_arbitrage_route_descarta_no_positivos_y_sin_time():
    payload = {
        "ripio":   {"ask": 0.0, "bid": 1500.0, "time": FRESH},     # ask<=0
        "okexp2p": {"ask": 1520.0, "bid": 0.0, "time": FRESH},     # bid<=0
        "belo":    {"ask": 1505.0, "bid": 1499.0},                  # sin time
    }
    wl = {"ripio", "okexp2p", "belo"}
    assert arbitrage_route(payload, wl, max_age_min=30, now=NOW) is None


def test_arbitrage_route_none_si_mismo_exchange():
    payload = {"ripio": {"ask": 1510.0, "bid": 1600.0, "time": FRESH}}
    r = arbitrage_route(payload, {"ripio"}, max_age_min=30, now=NOW)
    assert r is None  # ask min y bid max del mismo venue -> no hay ruta


# --- Tests para market_extremes (más barato para comprar / más caro para vender) ---
from core.criptoya import market_extremes, MarketExtremes


def test_market_extremes_ask_min_y_bid_max():
    payload = {
        "ripio":    {"ask": 1510.0, "bid": 1500.0, "time": FRESH},
        "okexp2p":  {"ask": 1520.0, "bid": 1535.0, "time": FRESH},
        "dolarapp": {"ask": 1480.0, "bid": 1505.0, "time": FRESH},
    }
    wl = {"ripio", "okexp2p", "dolarapp"}
    m = market_extremes(payload, wl, max_age_min=30, now=NOW)
    assert isinstance(m, MarketExtremes)
    assert m.buy_ex == "dolarapp" and m.buy_ask == 1480.0   # más barato p/comprar
    assert m.sell_ex == "okexp2p" and m.sell_bid == 1535.0  # más caro p/vender
    assert abs(m.spread_pct - (1535.0 - 1480.0) / 1480.0 * 100) < 1e-9


def test_market_extremes_descarta_rancios():
    payload = {
        "ripio":   {"ask": 1510.0, "bid": 1500.0, "time": FRESH},
        "belo":    {"ask": 1.0, "bid": 9999.0, "time": STALE},   # fantasma rancio
    }
    m = market_extremes(payload, {"ripio", "belo"}, max_age_min=30, now=NOW)
    assert m.buy_ex == "ripio" and m.sell_ex == "ripio"   # ignoró el rancio


def test_market_extremes_mismo_exchange_ok():
    # A diferencia de arbitrage_route, acá NO descartamos el mismo venue.
    payload = {"ripio": {"ask": 1510.0, "bid": 1600.0, "time": FRESH}}
    m = market_extremes(payload, {"ripio"}, max_age_min=30, now=NOW)
    assert m is not None and m.buy_ex == "ripio" and m.sell_ex == "ripio"


def test_market_extremes_none_si_vacio():
    assert market_extremes({}, {"ripio"}, max_age_min=30, now=NOW) is None


# --- Tests para fetch_arbitrage_route ---
from core.criptoya import fetch_arbitrage_route


class _FakeResp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


class _FakeSession:
    def __init__(self, payload=None, boom=False):
        self._p, self._boom = payload, boom
    def get(self, url, headers=None, timeout=None):
        if self._boom:
            raise RuntimeError("CriptoYa caído")
        return _FakeResp(self._p)


def test_fetch_arbitrage_route_ok():
    payload = {
        "ripio":   {"ask": 1510.0, "bid": 1500.0, "time": 999_999.0},
        "okexp2p": {"ask": 1520.0, "bid": 1535.0, "time": 999_999.0},
    }
    sess = _FakeSession(payload)
    r = fetch_arbitrage_route("USDT", "ARS", 1000, whitelist={"ripio", "okexp2p"},
                              max_age_min=30, session=sess, now=lambda: 1_000_000.0)
    assert r is not None and r.buy_ex == "ripio" and r.sell_ex == "okexp2p"


def test_fetch_arbitrage_route_error_da_none():
    sess = _FakeSession(boom=True)
    r = fetch_arbitrage_route("USDT", "ARS", 1000, whitelist={"ripio"},
                              max_age_min=30, session=sess, now=lambda: 1_000_000.0)
    assert r is None


# --- Tests para fetch_market_extremes ---
from core.criptoya import fetch_market_extremes


def test_fetch_market_extremes_ok():
    payload = {
        "ripio":    {"ask": 1510.0, "bid": 1500.0, "time": 999_999.0},
        "dolarapp": {"ask": 1480.0, "bid": 1540.0, "time": 999_999.0},
    }
    sess = _FakeSession(payload)
    m = fetch_market_extremes("USDT", "ARS", 1000, whitelist={"ripio", "dolarapp"},
                              max_age_min=30, session=sess, now=lambda: 1_000_000.0)
    assert m is not None and m.buy_ex == "dolarapp" and m.sell_ex == "dolarapp"


def test_fetch_market_extremes_error_da_none():
    sess = _FakeSession(boom=True)
    m = fetch_market_extremes("USDT", "ARS", 1000, whitelist={"ripio"},
                              max_age_min=30, session=sess, now=lambda: 1_000_000.0)
    assert m is None


# --- Tests para fetch_payload (dict crudo) ---
from core.criptoya import fetch_payload


def test_fetch_payload_devuelve_dict_crudo_y_cachea():
    import core.criptoya as cy

    calls = {"n": 0}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"ripio": {"ask": 1005.0, "bid": 998.0, "time": 1.0}}

    class _Sess:
        def get(self, url, **kw):
            calls["n"] += 1
            return _Resp()

    cy._PAYLOAD_CACHE.clear()
    t = [1000.0]
    out = cy.fetch_payload("USDT", "ARS", 1000.0, session=_Sess(), now=lambda: t[0])
    assert out["ripio"]["ask"] == 1005.0
    # segunda llamada dentro del ttl: no vuelve a pegar
    cy.fetch_payload("USDT", "ARS", 1000.0, session=_Sess(), now=lambda: t[0])
    assert calls["n"] == 1


def test_fetch_payload_devuelve_vacio_si_falla():
    import core.criptoya as cy

    class _Sess:
        def get(self, url, **kw):
            raise RuntimeError("boom")

    cy._PAYLOAD_CACHE.clear()
    out = cy.fetch_payload("USDT", "ARS", 1000.0, session=_Sess(), now=lambda: 5000.0)
    assert out == {}


def test_rank_extremes_top3_operables_frescos():
    from core.criptoya import rank_extremes
    payload = {
        "bitsoalpha": {"ask": 1556.88, "bid": 1555.0, "time": 1000.0},
        "fiwind":     {"ask": 1557.50, "bid": 1556.0, "time": 1000.0},
        "letsbit":    {"ask": 1558.90, "bid": 1540.0, "time": 1000.0},
        "binance":    {"ask": 1561.00, "bid": 1568.60, "time": 1000.0},
        "dolarapp":   {"ask": 1500.00, "bid": 1600.0, "time": 1000.0},  # fuera de whitelist
        "viejo":      {"ask": 1000.00, "bid": 2000.0, "time": 0.0},     # rancio
    }
    wl = {"bitsoalpha", "fiwind", "letsbit", "binance"}
    r = rank_extremes(payload, wl, max_age_min=30, now=1000.0, top=3)
    assert [b["exchange"] for b in r["buys"]] == ["bitsoalpha", "fiwind", "letsbit"]
    assert r["sells"][0]["exchange"] == "binance"
    assert len(r["buys"]) == 3 and len(r["sells"]) == 3
    todos = r["buys"] + r["sells"]
    assert all(x["exchange"] not in ("dolarapp", "viejo") for x in todos)


def test_rank_extremes_usa_precio_neto_total():
    from core.criptoya import rank_extremes
    payload = {
        # bid crudo alto pero totalBid bajo (binance spot con cash-out)
        "binance": {"ask": 1560, "totalAsk": 1562, "bid": 1568, "totalBid": 1551, "time": 1000.0},
        "fiwind":  {"ask": 1559, "totalAsk": 1559, "bid": 1560, "totalBid": 1560, "time": 1000.0},
    }
    r = rank_extremes(payload, {"binance", "fiwind"}, max_age_min=30, now=1000.0, top=2)
    # por bid crudo binance ganaría (1568); por NETO gana fiwind (1560 > 1551)
    assert r["sells"][0]["exchange"] == "fiwind" and r["sells"][0]["price"] == 1560
    # compra: el más barato por neto es fiwind (totalAsk 1559 < 1562)
    assert r["buys"][0]["exchange"] == "fiwind"
