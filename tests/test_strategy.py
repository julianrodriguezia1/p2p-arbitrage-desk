import importlib
import config
from dataclasses import dataclass
from core.strategy import Play, OutsideNote, Strategy, build_strategy


def test_config_has_strategy_defaults():
    importlib.reload(config)
    assert config.STRATEGY_NETWORK_FEE_PCT == 0.1
    assert config.STRATEGY_OUTSIDE_MARGIN_PCT == 0.5


@dataclass(frozen=True)
class _Route:
    kind: str; buy_venue: str; buy_price: float; buy_mode: str
    sell_venue: str; sell_price: float; sell_mode: str; net_pct: float


def test_build_strategy_rankea_y_elige_headline():
    routes = {
        "instant": _Route("instant", "bybitp2p", 1560.0, "tomando", "okexp2p", 1564.0, "tomando", 0.25),
        "media": _Route("media", "bybitp2p", 1561.0, "tomando", "kucoinp2p", 1578.0, "publicando", 0.90),
        "mm": _Route("mm", "kucoinp2p", 1568.0, "publicando", "kucoinp2p", 1578.0, "publicando", 0.55),
    }
    s = build_strategy(routes, network_fee_pct=0.1)
    # media cross-venue: 0.90 - 0.1 = 0.80 ; instant cross: 0.25 - 0.1 = 0.15 ; mm intra: 0.55 (sin haircut)
    assert s.best.kind == "media"
    assert abs(s.best.net_pct - 0.80) < 1e-9
    assert [p.kind for p in s.alternatives] == ["mm", "instant"]  # 0.55, luego 0.15
    assert abs(s.alternatives[0].net_pct - 0.55) < 1e-9
    assert abs(s.alternatives[1].net_pct - 0.15) < 1e-9


def test_mm_intra_venue_no_sufre_haircut_de_red():
    routes = {"mm": _Route("mm", "kucoinp2p", 1000.0, "publicando", "kucoinp2p", 1010.0, "publicando", 1.0)}
    s = build_strategy(routes, network_fee_pct=0.1)
    assert s.best.buy_venue == s.best.sell_venue
    assert abs(s.best.net_pct - 1.0) < 1e-9  # sin descuento


def test_ars_per_1000_se_calcula_sobre_precio_de_compra():
    routes = {"media": _Route("media", "bybitp2p", 1561.0, "tomando", "kucoinp2p", 1578.0, "publicando", 0.90)}
    s = build_strategy(routes, network_fee_pct=0.1)
    # net final 0.80% -> 0.80/100 * 1000 * 1561 = 12488.0
    assert abs(s.best.ars_per_1000 - (0.80 / 100 * 1000 * 1561.0)) < 1e-6


def test_build_strategy_vacio_devuelve_best_none():
    s = build_strategy({}, network_fee_pct=0.1)
    assert s.best is None and s.alternatives == [] and s.outside_note is None


def test_build_strategy_todo_negativo_no_muestra_best():
    routes = {
        "media": _Route("media", "bybitp2p", 1561.0, "tomando", "kucoinp2p", 1560.0, "publicando", -0.05),
        "instant": _Route("instant", "bybitp2p", 1560.0, "tomando", "okexp2p", 1558.0, "tomando", -0.02),
    }
    s = build_strategy(routes, network_fee_pct=0.1)
    assert s.best is None
    assert s.alternatives == []


def test_build_strategy_top_positivo_con_alternativa_negativa_no_cambia():
    routes = {
        "media": _Route("media", "bybitp2p", 1561.0, "tomando", "kucoinp2p", 1578.0, "publicando", 0.90),
        "instant": _Route("instant", "bybitp2p", 1560.0, "tomando", "okexp2p", 1558.0, "tomando", -0.30),
    }
    s = build_strategy(routes, network_fee_pct=0.1)
    assert s.best is not None
    assert s.best.kind == "media"
    assert abs(s.best.net_pct - 0.80) < 1e-9
    assert [p.kind for p in s.alternatives] == ["instant"]
    assert s.alternatives[0].net_pct < 0


def test_build_strategy_pasa_el_outside_note():
    note = OutsideNote(venue="eldoradop2p", side="sell", price=1602.0)
    s = build_strategy({}, network_fee_pct=0.1, outside_note=note)
    assert s.outside_note is note


from core.strategy import find_outside_note

_BROAD = {"bybitp2p", "kucoinp2p", "eldoradop2p", "ripio", "dolarapp"}
_OPERABLE = {"bybitp2p", "kucoinp2p", "ripio"}
_REMESA = {"dolarapp"}


def test_outside_note_dispara_con_p2p_afuera_que_paga_mas():
    # eldoradop2p (p2p, afuera) publica a ask=1602; mejor operable vende a 1578 (kucoin ask).
    # 1602 / 1578 - 1 = 1.52% >= 0.5% -> dispara.
    payload = {
        "bybitp2p": {"ask": 1561.0, "bid": 1560.0, "time": 1000.0},
        "kucoinp2p": {"ask": 1578.0, "bid": 1576.0, "time": 1000.0},
        "eldoradop2p": {"ask": 1602.0, "bid": 1546.0, "time": 1000.0},
        "ripio": {"ask": 1590.0, "bid": 1560.0, "time": 1000.0},   # CEX -> vende a bid 1560
    }
    note = find_outside_note(payload, operable_venues=_OPERABLE, broad_whitelist=_BROAD,
                             remesa_venues=_REMESA, blacklist=set(),
                             margin_pct=0.5, max_age_min=30, now=1000.0)
    assert note is not None
    assert note.venue == "eldoradop2p" and note.side == "sell" and note.price == 1602.0


def test_outside_note_no_dispara_si_no_supera_el_margen():
    payload = {
        "kucoinp2p": {"ask": 1600.0, "bid": 1576.0, "time": 1000.0},
        "eldoradop2p": {"ask": 1602.0, "bid": 1546.0, "time": 1000.0},  # solo +0.125% vs 1600
    }
    note = find_outside_note(payload, operable_venues={"kucoinp2p"}, broad_whitelist={"kucoinp2p", "eldoradop2p"},
                             remesa_venues=set(), blacklist=set(),
                             margin_pct=0.5, max_age_min=30, now=1000.0)
    assert note is None


def test_outside_note_cex_compara_por_neto_total():
    # satoshitango (CEX afuera): bid crudo 1600 superaría a kucoin (1578), pero su
    # totalBid neto es 1570 < 1578 -> no debe disparar. Se compara por lo que REALMENTE cobrás.
    payload = {
        "kucoinp2p": {"ask": 1578.0, "bid": 1576.0, "time": 1000.0},
        "satoshitango": {"ask": 1605.0, "bid": 1600.0, "totalBid": 1570.0, "time": 1000.0},
    }
    note = find_outside_note(payload, operable_venues={"kucoinp2p"},
                             broad_whitelist={"kucoinp2p", "satoshitango"},
                             remesa_venues=set(), blacklist=set(),
                             margin_pct=0.5, max_age_min=30, now=1000.0)
    assert note is None


def test_outside_note_ignora_remesa_blacklist_y_viejos():
    payload = {
        "kucoinp2p": {"ask": 1578.0, "bid": 1576.0, "time": 1000.0},
        "dolarapp": {"ask": 1700.0, "bid": 1690.0, "time": 1000.0},     # remesa -> ignorado
        "eldoradop2p": {"ask": 1650.0, "bid": 1546.0, "time": 0.0},     # viejo (>30min) -> ignorado
    }
    note = find_outside_note(payload, operable_venues={"kucoinp2p"},
                             broad_whitelist={"kucoinp2p", "dolarapp", "eldoradop2p"},
                             remesa_venues={"dolarapp"}, blacklist=set(),
                             margin_pct=0.5, max_age_min=30, now=2000.0)
    assert note is None


# --- La jugada que pasa por Binance (para sumar hacia el Verificado, 2026-08-28) ---

_SIN_BINANCE = {"instant": _Route("instant", "bybitp2p", 1500.0, "tomando",
                                  "okexp2p", 1515.0, "tomando", 1.0)}
_POR_BINANCE = {"instant": _Route("instant", "binancep2p", 1505.0, "tomando",
                                  "okexp2p", 1515.0, "tomando", 0.66)}


def test_build_strategy_expone_la_mejor_jugada_por_binance():
    s = build_strategy(_SIN_BINANCE, network_fee_pct=0.1,
                       routes_binance=_POR_BINANCE)
    assert s.best.buy_venue == "bybitp2p"
    assert s.binance is not None
    assert s.binance.buy_venue == "binancep2p"
    assert abs(s.binance.net_pct - 0.56) < 1e-9   # 0.66 - 0.1 de fee de red
    assert s.best_en_binance is False


def test_binance_es_none_cuando_la_mejor_ya_pasa_por_binance():
    """No repetir el bloque: se marca que la de arriba ya suma para el Verificado."""
    s = build_strategy(_POR_BINANCE, network_fee_pct=0.1,
                       routes_binance=dict(_POR_BINANCE))
    assert s.binance is None
    assert s.best_en_binance is True


def test_binance_no_se_muestra_si_la_jugada_da_negativa():
    """Decisión del usuario: si hacer volumen en Binance cuesta plata, no se ofrece."""
    perdedora = {"instant": _Route("instant", "binancep2p", 1505.0, "tomando",
                                   "okexp2p", 1500.0, "tomando", -0.33)}
    s = build_strategy(_SIN_BINANCE, network_fee_pct=0.1, routes_binance=perdedora)
    assert s.binance is None
    assert s.best_en_binance is False


def test_build_strategy_sin_routes_binance_no_rompe():
    s = build_strategy(_SIN_BINANCE, network_fee_pct=0.1)
    assert s.binance is None
    assert s.best_en_binance is False


# --- venues secundarios: casi no operan, nunca encabezan (pedido 2026-09-16) ---
_CON_KUCOIN = {
    "media": _Route("media", "bybitp2p", 1561.0, "tomando", "kucoinp2p", 1578.0, "publicando", 0.90),
    "mm": _Route("mm", "binancep2p", 1568.0, "publicando", "binancep2p", 1578.0, "publicando", 0.55),
    "instant": _Route("instant", "bybitp2p", 1560.0, "tomando", "okexp2p", 1564.0, "tomando", 0.25),
}


def test_venue_secundario_no_encabeza_pero_queda_como_alternativa():
    s = build_strategy(_CON_KUCOIN, network_fee_pct=0.1,
                       routes_liquidas=_CON_KUCOIN, routes_binance=_CON_KUCOIN,
                       secundarios=frozenset({"kucoinp2p"}))
    assert s.best.kind == "mm" and "kucoinp2p" not in (s.best.buy_venue, s.best.sell_venue)
    assert s.best.secundario is False
    assert [a.kind for a in s.alternatives] == ["media", "instant"]
    assert s.alternatives[0].secundario is True
    assert s.con_volumen is None            # la mejor con volumen ya es la mm
    assert s.best_en_binance is True


def test_sin_secundarios_el_comportamiento_no_cambia():
    s = build_strategy(_CON_KUCOIN, network_fee_pct=0.1)
    assert s.best.kind == "media"
    assert s.best.secundario is False
