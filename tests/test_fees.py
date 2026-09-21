"""Fee por modo, a un tamaño de ticket dado.

Existe porque publicar y tomar no cuestan lo mismo, y porque el fee de tomador
de Binance es un FLAT de 0,07 USDT por orden, no un %: pesa 0,007% en un ticket
de 1.000 y 0,07% en uno de 100. Una constante no puede representarlo.
"""
import pytest

from core.fees import por_modo

TABLA = {
    "binancep2p": {"maker_pct": 0.20, "taker_pct": 0.0, "taker_flat_quote": 0.07},
    "okexp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
    "lemoncashp2p": {"maker_pct": 1.0, "taker_pct": 1.5, "taker_flat_quote": 0.0},
}
BASE = dict(fees_by_venue=TABLA, asset="USDT", flat_assets=("USDT",))


def test_publicar_es_el_maker_tal_cual():
    f = por_modo(volume=1000.0, **BASE)
    assert f["binancep2p"]["publicando"] == 0.20
    assert f["lemoncashp2p"]["publicando"] == 1.0


def test_el_flat_del_tomador_se_diluye_en_el_ticket_grande():
    assert por_modo(volume=1000.0, **BASE)["binancep2p"]["tomando"] == pytest.approx(0.007)
    assert por_modo(volume=100.0, **BASE)["binancep2p"]["tomando"] == pytest.approx(0.07)


def test_el_venue_con_fee_porcentual_no_depende_del_ticket():
    for v in (100.0, 5000.0):
        assert por_modo(volume=v, **BASE)["lemoncashp2p"]["tomando"] == 1.5


def test_el_flat_solo_aplica_a_los_activos_donde_esta_anunciado():
    """Para BTC no hay comunicado público del flat: no se inventa uno."""
    f = por_modo(fees_by_venue=TABLA, volume=0.01, asset="BTC", flat_assets=("USDT",))
    assert f["binancep2p"]["tomando"] == 0.0
    assert f["binancep2p"]["publicando"] == 0.20


def test_volumen_cero_no_explota():
    f = por_modo(volume=0.0, **BASE)
    assert f["binancep2p"]["tomando"] == 0.0


def test_zero_fee_queda_en_cero_de_los_dos_lados():
    f = por_modo(volume=1000.0, **BASE)
    assert f["okexp2p"] == {"publicando": 0.0, "tomando": 0.0, "tomando_por_orden": 0.0}


def test_expone_el_flat_por_orden_para_cobrarlo_por_cada_aviso_tomado():
    """Si llenar el ticket lleva 2 avisos, son 2 órdenes y 2 veces el 0,07."""
    out = por_modo(volume=1000.0, **BASE)
    assert out["binancep2p"]["tomando_por_orden"] == pytest.approx(0.007)
    assert out["okexp2p"]["tomando_por_orden"] == 0.0
    assert out["lemoncashp2p"]["tomando_por_orden"] == 0.0


def test_flat_por_orden_por_venue_y_por_alias_de_fetcher():
    from core.fees import flat_por_orden
    base = dict(fees_by_venue=TABLA, asset="USDT", flat_assets=("USDT",))
    assert flat_por_orden(venue="binancep2p", **base) == 0.07
    assert flat_por_orden(venue="okexp2p", **base) == 0.0
    assert flat_por_orden(venue="binance", alias={"binance": "binancep2p"}, **base) == 0.07
    assert flat_por_orden(venue="binancep2p", fees_by_venue=TABLA, asset="BTC", flat_assets=("USDT",)) == 0.0
