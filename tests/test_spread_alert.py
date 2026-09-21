import importlib
from dataclasses import dataclass

import config
from core.spread_alert import Opportunity, evaluate, diff_state, load_state, save_state, format_message


@dataclass
class _Route:
    buy_ex: str; buy_ask: float; sell_ex: str; sell_bid: float; gross_pct: float


def test_config_has_alert_defaults():
    """Verify that config module has all spread_alert configuration attributes with correct defaults."""
    importlib.reload(config)
    # 2026-08-28: el usuario no quiere avisos por debajo de 0,5% de spread.
    assert config.SPREAD_ALERT_MIN_PCT == 0.5
    assert config.SPREAD_ALERT_CROSS_PCT == 0.5
    assert config.SPREAD_ALERT_INTRA_PCT == 1.0
    assert config.SPREAD_ALERT_COSTO_PCT == 1.5
    assert config.SPREAD_ALERT_HYSTERESIS_PCT == 0.1
    assert str(config.SPREAD_ALERT_STATE_PATH).endswith("spread_alert_state.json")


def test_cross_above_threshold_is_candidate():
    cross = [("bybit", 1548.0, "binance", 1554.5, 6500.0, 0.42)]
    opps = evaluate(
        intra=[], cross=cross,
        stock=0.0, avg_cost_ars=None, best_bid=1554.5,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    routes = {o.route for o in opps}
    assert "cross:bybit->binance" in routes
    o = next(o for o in opps if o.route == "cross:bybit->binance")
    assert o.kind == "cross"
    assert o.threshold == 0.2
    assert abs(o.pct - 0.42) < 1e-9
    assert "bybit" in o.detail and "binance" in o.detail


def test_cross_below_band_excluded():
    # pct 0.05 < threshold(0.2) - hysteresis(0.1) = 0.1 -> NO candidato
    cross = [("bybit", 1550.0, "binance", 1550.8, 800.0, 0.05)]
    opps = evaluate(
        intra=[], cross=cross,
        stock=0.0, avg_cost_ars=None, best_bid=1550.8,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert opps == []


def test_cross_in_hysteresis_band_is_candidate():
    # pct 0.15: por debajo de umbral 0.2 pero >= 0.2 - 0.1 = 0.1 -> candidato (en banda)
    cross = [("bybit", 1550.0, "binance", 1552.3, 2300.0, 0.15)]
    opps = evaluate(
        intra=[], cross=cross,
        stock=0.0, avg_cost_ars=None, best_bid=1552.3,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert {o.route for o in opps} == {"cross:bybit->binance"}


def test_intra_above_threshold_is_candidate():
    intra = [("binance", 1500.0, 1516.0, 16.0, 1.07)]
    opps = evaluate(
        intra=intra, cross=[],
        stock=0.0, avg_cost_ars=None, best_bid=1516.0,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert {o.route for o in opps} == {"intra:binance"}
    assert next(iter(opps)).kind == "intra"


def test_costo_fires_only_with_stock():
    # best_bid 1560 vs costo 1530 -> (1560-1530)/1530 = 1.96% >= 1.5
    sin_stock = evaluate(
        intra=[], cross=[],
        stock=0.0, avg_cost_ars=1530.0, best_bid=1560.0,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert sin_stock == []
    con_stock = evaluate(
        intra=[], cross=[],
        stock=120.0, avg_cost_ars=1530.0, best_bid=1560.0,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert {o.route for o in con_stock} == {"costo"}
    assert next(iter(con_stock)).kind == "costo"


def test_costo_does_not_fire_with_none_guards():
    # stock=120 but avg_cost_ars=None -> costo should NOT fire
    without_avg_cost = evaluate(
        intra=[], cross=[],
        stock=120.0, avg_cost_ars=None, best_bid=1560.0,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert without_avg_cost == []

    # stock=120 but best_bid=None -> costo should NOT fire
    without_best_bid = evaluate(
        intra=[], cross=[],
        stock=120.0, avg_cost_ars=1530.0, best_bid=None,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
    )
    assert without_best_bid == []


# === Tests for diff_state, load_state, save_state ===

def _opp(route, pct, threshold=0.2):
    return Opportunity(kind="cross", route=route, pct=pct,
                       threshold=threshold, title="t", detail="d")


def test_rising_edge_alerts():
    cands = [_opp("cross:a->b", 0.42)]
    alerts, active = diff_state(cands, prev_active=set(), hysteresis=0.1)
    assert [a.route for a in alerts] == ["cross:a->b"]
    assert active == {"cross:a->b"}


def test_already_active_is_silent():
    cands = [_opp("cross:a->b", 0.42)]
    alerts, active = diff_state(cands, prev_active={"cross:a->b"}, hysteresis=0.1)
    assert alerts == []
    assert active == {"cross:a->b"}


def test_stays_active_in_hysteresis_band_no_alert():
    # pct 0.15 < umbral 0.2 pero >= 0.2 - 0.1; estaba activa -> sigue activa, sin aviso
    cands = [_opp("cross:a->b", 0.15)]
    alerts, active = diff_state(cands, prev_active={"cross:a->b"}, hysteresis=0.1)
    assert alerts == []
    assert active == {"cross:a->b"}


def test_in_band_but_was_off_does_not_turn_on():
    # pct 0.15 en la banda, pero NO estaba activa -> no enciende (no llega al umbral)
    cands = [_opp("cross:a->b", 0.15)]
    alerts, active = diff_state(cands, prev_active=set(), hysteresis=0.1)
    assert alerts == []
    assert active == set()


def test_route_absent_turns_off():
    # estaba activa pero ya no es candidato (cayó por debajo de umbral-histéresis) -> off
    alerts, active = diff_state([], prev_active={"cross:a->b"}, hysteresis=0.1)
    assert alerts == []
    assert active == set()


def test_reignite_after_off_alerts_again():
    # apagada (set vacío) y vuelve a cruzar el umbral -> avisa de nuevo
    cands = [_opp("cross:a->b", 0.42)]
    alerts, active = diff_state(cands, prev_active=set(), hysteresis=0.1)
    assert [a.route for a in alerts] == ["cross:a->b"]


def test_state_roundtrip(tmp_path):
    p = tmp_path / "state.json"
    assert load_state(p) == set()          # falta -> vacío
    save_state(p, {"cross:a->b", "intra:binance"})
    assert load_state(p) == {"cross:a->b", "intra:binance"}


def test_corrupt_state_is_empty(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{ not json", encoding="utf-8")
    assert load_state(p) == set()


# === Tests for format_message ===

def test_format_empty_is_empty_string():
    assert format_message([]) == ""


def test_format_joins_title_and_detail():
    alerts = [
        Opportunity(kind="cross", route="cross:a->b", pct=0.42, threshold=0.2,
                    title="🟢 Spread cross-exchange",
                    detail="Comprar en a\nVender en b"),
        Opportunity(kind="intra", route="intra:binance", pct=1.2, threshold=1.0,
                    title="🔵 Spread intra-exchange",
                    detail="Comprar y vender en binance"),
    ]
    msg = format_message(alerts)
    assert "🟢 Spread cross-exchange" in msg
    assert "Comprar en a" in msg
    assert "🔵 Spread intra-exchange" in msg
    # las dos oportunidades separadas por línea en blanco
    assert "\n\n" in msg


# === Tests for cexp2p rule ===

def test_cexp2p_candidate_sobre_umbral():
    r = _Route("ripio", 1510.0, "okexp2p", 1535.0, 1.66)
    opps = evaluate(
        intra=[], cross=[],
        stock=0.0, avg_cost_ars=None, best_bid=None,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
        cexp2p_route=r, cexp2p_pct=1.0,
    )
    o = next(o for o in opps if o.route == "cexp2p")
    assert o.kind == "cexp2p"
    assert "ripio" in o.detail and "okexp2p" in o.detail
    assert "CEX→P2P" in o.title


def test_cexp2p_ausente_bajo_banda():
    r = _Route("ripio", 1510.0, "okexp2p", 1515.0, 0.33)  # < 1.0 - 0.1
    opps = evaluate(
        intra=[], cross=[],
        stock=0.0, avg_cost_ars=None, best_bid=None,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
        cexp2p_route=r, cexp2p_pct=1.0,
    )
    assert all(o.route != "cexp2p" for o in opps)


def test_cexp2p_none_no_rompe():
    opps = evaluate(
        intra=[], cross=[],
        stock=0.0, avg_cost_ars=None, best_bid=None,
        cross_pct=0.2, intra_pct=1.0, costo_pct=1.5, hysteresis=0.1,
        cexp2p_route=None, cexp2p_pct=1.0,
    )
    assert opps == []


# === Tests for arb_candidates ===

from core.arb_matrix import Route
from core.spread_alert import arb_candidates

_THR = {"media": 0.2, "mm": 0.2, "instant": 0.2}


def test_arb_candidates_sobre_umbral_emite_opportunity():
    routes = {
        "media": Route("media", "bybitp2p", 1562.0, "tomando",
                       "kucoinp2p", 1570.0, "publicando", 0.51),
    }
    opps = arb_candidates(routes, thresholds=_THR, hysteresis=0.1)
    assert len(opps) == 1
    o = opps[0]
    assert o.kind == "media" and o.route == "media" and o.threshold == 0.2
    assert abs(o.pct - 0.51) < 1e-9
    # criollo, sin "ask"/"bid":
    assert "Comprá tomando en bybitp2p" in o.detail
    assert "vendé publicando en kucoinp2p" in o.detail
    assert "ask" not in o.detail.lower() and "bid" not in o.detail.lower()
    assert "esperás de un lado" in o.detail


def test_arb_candidates_bajo_la_banda_se_excluye():
    # 0.05 < 0.2 - 0.1 = 0.1 -> no candidato
    routes = {"instant": Route("instant", "A", 1000.0, "tomando",
                               "B", 1000.5, "tomando", 0.05)}
    assert arb_candidates(routes, thresholds=_THR, hysteresis=0.1) == []


def test_arb_candidates_mm_intra_venue_texto_dos_puntas():
    routes = {"mm": Route("mm", "kucoinp2p", 1000.0, "publicando",
                          "kucoinp2p", 1010.0, "publicando", 1.0)}
    opps = arb_candidates(routes, thresholds=_THR, hysteresis=0.1)
    assert opps[0].kind == "mm"
    assert "esperás de los dos lados" in opps[0].detail
