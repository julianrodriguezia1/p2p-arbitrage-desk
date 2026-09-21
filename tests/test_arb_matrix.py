import importlib

import pytest

import config
from core.arb_matrix import (
    Venue, Route, best_routes, build_venues,
    _comprar_publicando, _comprar_tomando, _vender_publicando, _vender_tomando,
)


def test_config_has_arb_defaults():
    importlib.reload(config)
    # 2026-08-28: piso de 0,5% para todo aviso a Telegram.
    assert config.SPREAD_ALERT_MEDIA_PCT == 0.5
    assert config.SPREAD_ALERT_MM_PCT == 0.5
    assert config.SPREAD_ALERT_INSTANT_PCT == 0.5
    fees = config.FEE_PCT_BY_VENUE
    assert fees["binancep2p"] == 0.2
    assert fees["binance"] == 0.2
    assert fees["bybitp2p"] == 0.0
    assert fees["kucoinp2p"] == 0.0
    assert fees["okexp2p"] == 0.0
    assert fees["bitgetp2p"] == 0.0
    # venue no listado -> el lookup en arb_matrix usa .get(..., 0.0)
    assert "ripio" not in fees or fees["ripio"] == 0.0


# Sin fees para aislar la aritmética.
NO_FEES: dict[str, float] = {}


def test_instant_toma_ambas_puntas():
    # Comprar tomando (ask) en A, vender tomando (bid) en B.
    # A.ask=1000 -> B.bid=1010 => (1010-1000)/1000 = 1.0%
    vs = [
        Venue("A", ask=1000.0, bid=990.0, is_p2p=False),
        Venue("B", ask=1020.0, bid=1010.0, is_p2p=False),
    ]
    r = best_routes(vs, fee_pct=NO_FEES)["instant"]
    assert r.kind == "instant"
    assert r.buy_venue == "A" and r.buy_mode == "tomando" and r.buy_price == 1000.0
    assert r.sell_venue == "B" and r.sell_mode == "tomando" and r.sell_price == 1010.0
    assert abs(r.net_pct - 1.0) < 1e-9


def test_media_compra_tomando_vende_publicando():
    # Media espera variante 1: comprar tomando en A (ask=1000),
    # vender publicando en B (ask=1030, B es p2p) => 3.0%
    vs = [
        Venue("A", ask=1000.0, bid=980.0, is_p2p=False),
        Venue("Bp2p", ask=1030.0, bid=1005.0, is_p2p=True),
    ]
    r = best_routes(vs, fee_pct=NO_FEES)["media"]
    assert r.buy_mode == "tomando" and r.buy_price == 1000.0
    assert r.sell_mode == "publicando" and r.sell_venue == "Bp2p" and r.sell_price == 1030.0
    assert abs(r.net_pct - 3.0) < 1e-9


def test_media_variante_simetrica_compra_publicando():
    # Variante 2: comprar publicando en A (bid=1000, A p2p),
    # vender tomando en B (bid=1050) => 5.0%. Debe ganarle a la variante 1.
    # Ap2p.ask=1010 < B.ask=1060 garantiza que el par inverso (B->Ap2p publicando)
    # no supera: buy tomando B@1060 -> sell publicando Ap2p@1010 = negativo.
    vs = [
        Venue("Ap2p", ask=1010.0, bid=1000.0, is_p2p=True),
        Venue("B", ask=1060.0, bid=1050.0, is_p2p=False),
    ]
    r = best_routes(vs, fee_pct=NO_FEES)["media"]
    # V2 ganadora: comprar publicando Ap2p@1000 -> vender tomando B@1050 = 5.0%
    # V1 mejor: comprar tomando Ap2p@1010 -> sell publicando (B no es p2p: None) = inválida
    #           comprar tomando B@1060 -> sell publicando Ap2p@1010 = negativo = descartada
    assert r.buy_mode == "publicando" and r.buy_venue == "Ap2p" and r.buy_price == 1000.0
    assert r.sell_mode == "tomando" and r.sell_venue == "B" and r.sell_price == 1050.0
    assert abs(r.net_pct - 5.0) < 1e-9


def test_mm_dos_puntas_incluye_intra_venue():
    # Market making intra-venue: comprar publicando (bid) y vender publicando (ask)
    # en el MISMO KuCoin. bid=1000, ask=1010 => 1.0%.
    vs = [Venue("kucoinp2p", ask=1010.0, bid=1000.0, is_p2p=True)]
    r = best_routes(vs, fee_pct=NO_FEES)["mm"]
    assert r.kind == "mm"
    assert r.buy_venue == "kucoinp2p" and r.buy_mode == "publicando"
    assert r.sell_venue == "kucoinp2p" and r.sell_mode == "publicando"
    assert abs(r.net_pct - 1.0) < 1e-9


def test_publicando_solo_para_p2p():
    # Dos CEX (no p2p): mm no tiene ruta (necesita publicar de los dos lados);
    # media tampoco puede publicar => solo instant existe.
    vs = [
        Venue("ripio", ask=1000.0, bid=995.0, is_p2p=False),
        Venue("belo", ask=1002.0, bid=1001.0, is_p2p=False),
    ]
    out = best_routes(vs, fee_pct=NO_FEES)
    assert "mm" not in out
    assert "media" not in out
    assert "instant" in out


def test_fees_binance_restan_y_penalizan_la_ruta():
    # Comprar en binancep2p (fee 0.20) vs bybitp2p (fee 0) hacia kucoinp2p.
    # Bruto igual, pero binance deja menos neto => la mejor 'media' NO usa binance.
    fees = {"binancep2p": 0.2, "bybitp2p": 0.0, "kucoinp2p": 0.0}
    vs = [
        Venue("binancep2p", ask=1000.0, bid=980.0, is_p2p=True),
        Venue("bybitp2p", ask=1000.0, bid=980.0, is_p2p=True),
        Venue("kucoinp2p", ask=1010.0, bid=1008.0, is_p2p=True),
    ]
    r = best_routes(vs, fee_pct=fees)["media"]
    # Con evaluación exhaustiva la mejor media es variante 2:
    #   comprar publicando bybitp2p@bid=980 -> vender tomando kucoinp2p@bid=1008
    #   bruto = (1008-980)/980*100 = 2.857...% - 0 fee bybit - 0 fee kucoin = 2.857...%
    # La misma ruta con binance sería 2.857...% - 0.2 = 2.657...% => bybit gana.
    assert r.buy_venue == "bybitp2p"
    expected_net = (1008.0 - 980.0) / 980.0 * 100  # ≈ 2.857142857...
    assert abs(r.net_pct - expected_net) < 1e-9


def test_venue_con_precio_faltante_se_ignora():
    vs = [
        Venue("A", ask=None, bid=None, is_p2p=False),
        Venue("B", ask=1000.0, bid=990.0, is_p2p=False),
        Venue("C", ask=1030.0, bid=1020.0, is_p2p=False),
    ]
    r = best_routes(vs, fee_pct=NO_FEES)["instant"]
    assert r.buy_venue == "B" and r.sell_venue == "C"


def test_media_dos_p2p_variante2_gana():
    # Dos P2P. Variante 2 (comprar publicando A@bid -> vender tomando B@bid) debe
    # ganarle a la variante 1 (comprar tomando A@ask -> vender publicando B@ask).
    vs = [
        Venue("Ap2p", ask=1005.0, bid=1000.0, is_p2p=True),
        Venue("Bp2p", ask=1006.0, bid=1080.0, is_p2p=True),
    ]
    r = best_routes(vs, fee_pct=NO_FEES)["media"]
    # V2: comprar publicando Ap2p@1000 -> vender tomando Bp2p@1080 = 8.0%
    # V1 mejor: comprar tomando Ap2p@1005 -> vender publicando Bp2p@1006 = 0.0995%
    assert r.buy_mode == "publicando" and r.buy_venue == "Ap2p" and r.buy_price == 1000.0
    assert r.sell_mode == "tomando" and r.sell_venue == "Bp2p" and r.sell_price == 1080.0
    assert abs(r.net_pct - 8.0) < 1e-9


from core.arb_matrix import P2P_DEPTH_VENUES, build_venues


def test_p2p_depth_venues_mapea_los_cinco():
    assert P2P_DEPTH_VENUES == {
        "binancep2p": "binance",
        "okexp2p": "okx",
        "bybitp2p": "bybit",
        "bitgetp2p": "bitget",
        "kucoinp2p": "kucoin",
    }


def test_build_venues_marca_p2p_y_cex():
    depth = {"bybitp2p": {"ask": 1010.0, "bid": 1000.0}}
    payload = {"ripio": {"ask": 1005.0, "bid": 998.0, "time": 500.0}}
    vs = build_venues(depth, payload, cex_venues={"ripio"},
                      blacklist=set(), max_age_min=30, now=1000.0)
    by = {v.name: v for v in vs}
    assert by["bybitp2p"].is_p2p is True and by["bybitp2p"].ask == 1010.0
    assert by["ripio"].is_p2p is False and by["ripio"].bid == 998.0


def test_build_venues_descarta_cex_vieja_blacklist_y_cero():
    payload = {
        "ripio": {"ask": 1005.0, "bid": 998.0, "time": 0.0},        # vieja (>30 min)
        "weexp2p": {"ask": 1000.0, "bid": 999.0, "time": 2000.0},   # blacklist
        "belo": {"ask": 0.0, "bid": 0.0, "time": 2000.0},           # sin ofertas
        "buenbit": {"ask": 1003.0, "bid": 1001.0, "time": 2000.0},  # OK
    }
    vs = build_venues({}, payload, cex_venues={"ripio", "weexp2p", "belo", "buenbit"},
                      blacklist={"weexp2p"}, max_age_min=30, now=2000.0)
    names = {v.name for v in vs}
    assert names == {"buenbit"}


def test_build_venues_cex_usa_precio_neto_total():
    # SatoshiTango: bid crudo 1570 pero totalBid neto 1561.95 (comisión en ARS).
    # El Venue debe reflejar lo que REALMENTE cobrás/pagás, no el crudo.
    payload = {"satoshitango": {"ask": 1575.0, "totalAsk": 1583.0,
                                "bid": 1570.0, "totalBid": 1561.95, "time": 1000.0}}
    vs = build_venues({}, payload, cex_venues={"satoshitango"},
                      blacklist=set(), max_age_min=30, now=1000.0)
    by = {v.name: v for v in vs}
    assert by["satoshitango"].bid == 1561.95
    assert by["satoshitango"].ask == 1583.0


def test_build_venues_cex_cae_a_crudo_sin_total():
    # Si CriptoYa no manda totalAsk/totalBid, se usa el crudo (fallback).
    payload = {"buenbit": {"ask": 1003.0, "bid": 1001.0, "time": 1000.0}}
    vs = build_venues({}, payload, cex_venues={"buenbit"},
                      blacklist=set(), max_age_min=30, now=1000.0)
    by = {v.name: v for v in vs}
    assert by["buenbit"].ask == 1003.0 and by["buenbit"].bid == 1001.0


def test_build_venues_ignora_p2p_con_lado_faltante():
    depth = {"kucoinp2p": {"ask": None, "bid": 1000.0}}
    vs = build_venues(depth, {}, cex_venues=set(),
                      blacklist=set(), max_age_min=30, now=1000.0)
    # ask None -> el venue igual se crea con ask=None; best_routes lo tolera.
    assert len(vs) == 1 and vs[0].name == "kucoinp2p" and vs[0].ask is None


# --- filtro de rutas: "la mejor jugada que pase por Binance" (2026-08-28) ---

def _venues_binance_no_gana():
    """Escenario armado: la mejor global NO toca Binance.

    bybitp2p   ask 1500 / bid 1490
    okexp2p    ask 1520 / bid 1515
    binancep2p ask 1505 / bid 1500
    instant global: comprar bybit 1500 -> vender okex 1515 = +1.00%
    instant por Binance: comprar binance 1505 -> vender okex 1515 = +0.664%
    """
    return [
        Venue("bybitp2p", 1500.0, 1490.0, is_p2p=True),
        Venue("okexp2p", 1520.0, 1515.0, is_p2p=True),
        Venue("binancep2p", 1505.0, 1500.0, is_p2p=True),
    ]


def test_best_routes_sin_keep_elige_la_ruta_que_no_toca_binance():
    r = best_routes(_venues_binance_no_gana(), fee_pct={})["instant"]
    assert (r.buy_venue, r.sell_venue) == ("bybitp2p", "okexp2p")


def test_best_routes_con_keep_solo_devuelve_rutas_que_pasan_por_binance():
    pasa_por_binance = lambda r: "binancep2p" in (r.buy_venue, r.sell_venue)
    routes = best_routes(_venues_binance_no_gana(), fee_pct={}, keep=pasa_por_binance)
    assert routes
    assert all(pasa_por_binance(r) for r in routes.values())
    r = routes["instant"]
    assert (r.buy_venue, r.sell_venue) == ("binancep2p", "okexp2p")
    assert r.net_pct == pytest.approx((1515 - 1505) / 1505 * 100)


def test_best_routes_con_keep_que_no_deja_pasar_nada_devuelve_vacio():
    assert best_routes(_venues_binance_no_gana(), fee_pct={},
                       keep=lambda r: False) == {}


# --- Publicar sólo donde está habilitado (2026-08-29) ---
# Bitget no me deja crear anuncios todavía. Una jugada que me pide publicar ahí
# no es una jugada: es un número que no puedo ejecutar.

def _venues_bitget():
    return [
        Venue("binancep2p", 1590.0, 1580.0, is_p2p=True),
        Venue("bitgetp2p", 1600.0, 1560.0, is_p2p=True),
    ]


def test_venue_sin_permiso_no_ofrece_publicar_venta():
    v = Venue("bitgetp2p", 1600.0, 1560.0, is_p2p=True, puede_publicar_venta=False)
    assert _vender_publicando(v) is None
    assert _vender_tomando(v) == 1560.0   # tomar sigue disponible


def test_venue_sin_permiso_no_ofrece_publicar_compra():
    v = Venue("bitgetp2p", 1600.0, 1560.0, is_p2p=True, puede_publicar_compra=False)
    assert _comprar_publicando(v) is None
    assert _comprar_tomando(v) == 1600.0


def test_build_venues_marca_donde_no_puedo_publicar():
    depth = {"binancep2p": {"ask": 1590.0, "bid": 1580.0},
             "bitgetp2p": {"ask": 1600.0, "bid": 1560.0}}
    vs = {v.name: v for v in build_venues(
        depth, {}, cex_venues=set(), blacklist=set(), max_age_min=10, now=0,
        puede_publicar_compra={"bitgetp2p": False},
        puede_publicar_venta={"bitgetp2p": False})}
    assert vs["bitgetp2p"].puede_publicar_compra is False
    assert vs["bitgetp2p"].puede_publicar_venta is False
    assert vs["binancep2p"].puede_publicar_venta is True  # ausente = habilitado


def test_ninguna_ruta_me_pide_publicar_donde_no_puedo():
    depth = {"binancep2p": {"ask": 1590.0, "bid": 1580.0},
             "bitgetp2p": {"ask": 1600.0, "bid": 1560.0}}
    vs = build_venues(depth, {}, cex_venues=set(), blacklist=set(),
                      max_age_min=10, now=0,
                      puede_publicar_compra={"bitgetp2p": False},
                      puede_publicar_venta={"bitgetp2p": False})
    for r in best_routes(vs, fee_pct={}).values():
        assert not (r.buy_venue == "bitgetp2p" and r.buy_mode == "publicando")
        assert not (r.sell_venue == "bitgetp2p" and r.sell_mode == "publicando")


# --- Lemon P2P: libro P2P sin orderbook público (2026-08-29) ---
# Lemon no expone el libro (ver docs/investigacion-lemon-api-p2p.md), así que el
# precio viene de CriptoYa. Pero SÍ se puede publicar ahí, y publicar cuesta 1%
# contra 1,5% de tomar. Con el flat de siempre la jugada de publicar nunca
# aparecería con su costo real.

_PAY_LEMON = {"lemoncashp2p": {"ask": 1604.0, "totalAsk": 1628.06,
                               "bid": 1596.68, "totalBid": 1572.73, "time": 0}}


def test_p2p_sin_profundidad_usa_el_precio_crudo_no_el_de_tomador():
    """El total* de CriptoYa ya trae clavado el fee de tomador (1,5%). Si la
    jugada es publicar, ese precio castiga de más."""
    v = {x.name: x for x in build_venues(
        {}, _PAY_LEMON, cex_venues={"lemoncashp2p"}, blacklist=set(),
        max_age_min=10, now=0, p2p_sin_profundidad={"lemoncashp2p"})}["lemoncashp2p"]
    assert v.is_p2p is True
    assert v.ask == 1604.0 and v.bid == 1596.68


def test_sin_la_marca_lemon_sigue_entrando_como_cex_con_precio_total():
    v = {x.name: x for x in build_venues(
        {}, _PAY_LEMON, cex_venues={"lemoncashp2p"}, blacklist=set(),
        max_age_min=10, now=0)}["lemoncashp2p"]
    assert v.is_p2p is False
    assert v.ask == 1628.06


def test_p2p_sin_profundidad_no_finge_liquidez_medida():
    """No hay orderbook: la liquidez queda en None (no medible), nunca en 0."""
    v = {x.name: x for x in build_venues(
        {}, _PAY_LEMON, cex_venues={"lemoncashp2p"}, blacklist=set(),
        max_age_min=10, now=0, p2p_sin_profundidad={"lemoncashp2p"})}["lemoncashp2p"]
    assert v.ask_avisos is None and v.bid_avisos is None


def test_el_fee_por_modo_pisa_al_flat():
    """Publicar en Lemon cuesta 1%; tomar, 1,5%. El flat no sabe la diferencia."""
    vs = [Venue("binancep2p", 1593.0, 1592.52, is_p2p=True),
          Venue("lemoncashp2p", 1620.0, 1596.68, is_p2p=True)]
    fee_mode = {"lemoncashp2p": {"publicando": 1.0, "tomando": 1.5}}
    r = best_routes(vs, fee_pct={"binancep2p": 0.2, "lemoncashp2p": 1.5},
                    fee_by_mode=fee_mode)
    mm = r["mm"]   # las dos patas publicando
    assert mm.buy_venue == "binancep2p" and mm.sell_venue == "lemoncashp2p"
    bruto = (1620.0 - 1592.52) / 1592.52 * 100
    assert mm.net_pct == pytest.approx(bruto - 0.2 - 1.0)


def test_sin_tabla_por_modo_se_cobra_el_flat_de_siempre():
    vs = [Venue("binancep2p", 1593.0, 1592.52, is_p2p=True),
          Venue("lemoncashp2p", 1620.0, 1596.68, is_p2p=True)]
    r = best_routes(vs, fee_pct={"binancep2p": 0.2, "lemoncashp2p": 1.5})
    bruto = (1620.0 - 1592.52) / 1592.52 * 100
    assert r["mm"].net_pct == pytest.approx(bruto - 0.2 - 1.5)


def test_fee_pata_cobra_el_flat_una_vez_por_orden_tomada():
    from core.arb_matrix import fee_pata
    fm = {"binancep2p": {"publicando": 0.2, "tomando": 0.007, "tomando_por_orden": 0.007}}
    assert fee_pata("binancep2p", "tomando", {}, fm) == pytest.approx(0.007)
    assert fee_pata("binancep2p", "tomando", {}, fm, ordenes=3) == pytest.approx(0.021)
    # publicar no paga flat: las órdenes no cambian nada
    assert fee_pata("binancep2p", "publicando", {}, fm, ordenes=3) == pytest.approx(0.2)
    # tabla vieja sin el campo: se comporta como antes
    assert fee_pata("binancep2p", "tomando", {}, {"binancep2p": {"tomando": 0.007}}, ordenes=3) == pytest.approx(0.007)


def test_instant_paga_el_flat_por_cada_orden_que_llena_el_ticket():
    """Comprar 1.000 tomando lleva 2 avisos (2 órdenes), vender 1: 3 × 0,07."""
    vs = [Venue("binancep2p", 1592.0, 1593.0, is_p2p=True,
                ask_ordenes=2, bid_ordenes=1)]
    fm = {"binancep2p": {"publicando": 0.2, "tomando": 0.007, "tomando_por_orden": 0.007}}
    r = best_routes(vs, fee_pct={"binancep2p": 0.2}, fee_by_mode=fm)
    bruto = (1593.0 - 1592.0) / 1592.0 * 100
    assert r["instant"].net_pct == pytest.approx(bruto - 0.007 * 3)


def test_build_venues_carga_las_ordenes_por_punta():
    v = build_venues({"binancep2p": {"ask": 1592.0, "bid": 1593.0,
                                     "ask_ordenes": 2, "bid_ordenes": 1}},
                     {}, cex_venues=set(), blacklist=set(), max_age_min=10, now=0)[0]
    assert v.ask_ordenes == 2 and v.bid_ordenes == 1
