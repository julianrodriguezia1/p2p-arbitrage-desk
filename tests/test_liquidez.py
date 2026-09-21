"""Tests de la capa de liquidez: que el tablero no ofrezca un precio de un libro
que no mueve plata (el caso KuCoin que marcó el usuario el 2026-08-24)."""
import pytest

from core.arb_matrix import Venue, best_routes, build_venues
from core.p2p_depth import compute_depth_quote
from core.strategy import build_strategy, venue_liquido


class Ad:
    def __init__(self, price, available, min_amount=0.0, max_amount=1e12, orders=50):
        self.price = price
        self.available = available
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.orders = orders


# --- compute_depth_quote ahora reporta de qué libro salió el precio ---

def test_compute_depth_quote_informa_avisos_y_stock():
    buy = [Ad(1590, 500), Ad(1591, 800), Ad(1592, 400)]
    sell = [Ad(1585, 1000), Ad(1584, 2000)]
    q = compute_depth_quote(buy, sell, 1000)
    assert q["ask_avisos"] == 3
    assert q["ask_stock"] == pytest.approx(1700)
    assert q["bid_avisos"] == 2
    assert q["bid_stock"] == pytest.approx(3000)


def test_compute_depth_quote_dice_si_el_libro_alcanza_el_volumen():
    flaco = [Ad(1590, 100)]
    q = compute_depth_quote(flaco, flaco, 1000)
    assert q["ask_alcanza"] is False
    gordo = [Ad(1590, 5000)]
    assert compute_depth_quote(gordo, gordo, 1000)["ask_alcanza"] is True


def test_compute_depth_quote_cuenta_ordenes_necesarias():
    """Un precio repartido en muchos avisos son muchos chats: eso es fricción."""
    partido = [Ad(1590, 100) for _ in range(12)]
    q = compute_depth_quote(partido, partido, 1000)
    assert q["ask_ordenes"] == 10


def test_compute_depth_quote_sigue_dando_ask_y_bid_como_antes():
    q = compute_depth_quote([Ad(1590, 5000)], [Ad(1585, 5000)], 1000)
    assert q["ask"] == pytest.approx(1590)
    assert q["bid"] == pytest.approx(1585)


def test_compute_depth_quote_con_libro_vacio_no_inventa():
    q = compute_depth_quote([], [], 1000)
    assert q["ask"] is None and q["ask_avisos"] == 0
    assert q["ask_alcanza"] is False


# --- el criterio de "esto mueve plata de verdad" ---

def test_venue_liquido_exige_avisos_y_que_alcance():
    gordo = Venue("binancep2p", 1593, 1590, is_p2p=True,
                  ask_avisos=20, ask_stock=23143, ask_alcanza=True,
                  bid_avisos=20, bid_stock=82970, bid_alcanza=True)
    assert venue_liquido(gordo, "ask") is True
    assert venue_liquido(gordo, "bid") is True


def test_venue_liquido_rechaza_el_libro_flaco():
    """KuCoin real del 2026-08-24: 8 avisos y 7.724 USD del lado vendedor."""
    flaco = Venue("kucoinp2p", 1595.73, 1586.0, is_p2p=True,
                  ask_avisos=8, ask_stock=7724, ask_alcanza=True,
                  bid_avisos=18, bid_stock=311088, bid_alcanza=True)
    assert venue_liquido(flaco, "ask") is False
    assert venue_liquido(flaco, "bid") is True


def test_venue_liquido_rechaza_si_el_libro_no_llena_el_volumen():
    v = Venue("okexp2p", 1592, 1589, is_p2p=True,
              ask_avisos=20, ask_stock=200, ask_alcanza=False,
              bid_avisos=20, bid_stock=90000, bid_alcanza=True)
    assert venue_liquido(v, "ask") is False


def test_venue_liquido_deja_pasar_los_cex_que_no_tienen_libro():
    """Un CEX no publica orderbook: no se lo puede medir, no se lo castiga."""
    cex = Venue("satoshitango", 1645, 1600, is_p2p=False)
    assert venue_liquido(cex, "ask") is True


# --- best_routes con filtro ---

def test_best_routes_puede_excluir_puntas_no_liquidas():
    flaco = Venue("kucoinp2p", 1587.0, 1595.73, is_p2p=True,
                  ask_avisos=2, ask_stock=500, ask_alcanza=True,
                  bid_avisos=2, bid_stock=500, bid_alcanza=True)
    gordo = Venue("binancep2p", 1593.9, 1590.4, is_p2p=True,
                  ask_avisos=20, ask_stock=23143, ask_alcanza=True,
                  bid_avisos=20, bid_stock=82970, bid_alcanza=True)
    fees = {"kucoinp2p": 0.0, "binancep2p": 0.2}
    libre = best_routes([flaco, gordo], fee_pct=fees)
    filtrado = best_routes([flaco, gordo], fee_pct=fees, usable=venue_liquido)
    assert any(r.buy_venue == "kucoinp2p" or r.sell_venue == "kucoinp2p"
               for r in libre.values())
    assert all(r.buy_venue != "kucoinp2p" and r.sell_venue != "kucoinp2p"
               for r in filtrado.values())


def test_build_venues_transporta_la_liquidez_del_depth_quote():
    depth = {"kucoinp2p": {"ask": 1595.73, "bid": 1586.0, "ask_avisos": 8,
                           "ask_stock": 7724.0, "ask_alcanza": True,
                           "bid_avisos": 18, "bid_stock": 311088.0,
                           "bid_alcanza": True}}
    vs = build_venues(depth, {}, cex_venues=set(), blacklist=set(),
                      max_age_min=30, now=0)
    assert vs[0].ask_avisos == 8
    assert vs[0].ask_stock == pytest.approx(7724.0)


# --- la estrategia expone la jugada con volumen ---

def test_build_strategy_agrega_la_jugada_con_volumen():
    from core.arb_matrix import Route
    mejor = {"mm": Route("mm", "kucoinp2p", 1587.0, "publicando",
                         "kucoinp2p", 1595.73, "publicando", 0.55)}
    liquida = {"mm": Route("mm", "binancep2p", 1590.4, "publicando",
                           "binancep2p", 1593.9, "publicando", 0.22)}
    s = build_strategy(mejor, network_fee_pct=0.1, routes_liquidas=liquida)
    assert s.best.buy_venue == "kucoinp2p"
    assert s.con_volumen is not None
    assert s.con_volumen.buy_venue == "binancep2p"


def test_con_volumen_es_none_si_coincide_con_la_mejor():
    """Si la mejor ya es líquida no hay nada que agregar abajo."""
    from core.arb_matrix import Route
    r = {"mm": Route("mm", "binancep2p", 1590.4, "publicando",
                     "binancep2p", 1593.9, "publicando", 0.22)}
    s = build_strategy(r, network_fee_pct=0.1, routes_liquidas=dict(r))
    assert s.con_volumen is None


def test_build_strategy_sin_routes_liquidas_no_rompe():
    from core.arb_matrix import Route
    r = {"mm": Route("mm", "kucoinp2p", 1587.0, "publicando",
                     "kucoinp2p", 1595.73, "publicando", 0.55)}
    assert build_strategy(r, network_fee_pct=0.1).con_volumen is None
