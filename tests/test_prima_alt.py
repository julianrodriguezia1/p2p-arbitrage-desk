"""Tests de core.prima_alt — la prima que paga en ARS lo que no es stablecoin."""
import pytest

from core.prima_alt import (
    JugadaPublicar,
    Prima,
    implied_fx,
    jugada_publicar,
    prima,
    rankear,
)


def test_implied_fx_traduce_precio_ars_a_pesos_por_dolar():
    # 123.750.000 ARS por 1 BTC con el BTC a 77.000 USD -> 1.607,14 ARS por dólar
    assert implied_fx(123_750_000, 77_000) == pytest.approx(1607.14, abs=0.01)


def test_implied_fx_del_usdt_es_el_precio_mismo():
    assert implied_fx(1587.9, 1.0) == pytest.approx(1587.9)


@pytest.mark.parametrize("px", [0, -1])
def test_implied_fx_rechaza_precio_usd_invalido(px):
    with pytest.raises(ValueError):
        implied_fx(123_750_000, px)


def test_prima_mide_cuanto_mas_caro_sale_el_activo_que_el_usdt():
    p = prima("BTC", "binance", ask_ars=123_750_000, bid_ars=121_800_000,
              usd_price=77_000, usdt_ask=1587.9, usdt_bid=1585.0)
    assert isinstance(p, Prima)
    assert p.ask_fx == pytest.approx(1607.14, abs=0.01)
    assert p.prima_ask_pct == pytest.approx(1.21, abs=0.02)   # +1,2% vs comprar USDT
    assert p.prima_bid_pct == pytest.approx(-0.21, abs=0.02)  # vender rinde casi igual
    assert p.ancho_pct == pytest.approx(1.60, abs=0.02)


def test_prima_tolera_libro_sin_una_punta():
    p = prima("BTC", "kucoin", ask_ars=None, bid_ars=116_871_942,
              usd_price=77_000, usdt_ask=1587.9, usdt_bid=1585.0)
    assert p.ask_fx is None
    assert p.prima_ask_pct is None
    assert p.ancho_pct is None
    assert p.bid_fx is not None


def test_jugada_publicar_descuenta_spot_y_maker():
    # Compro USDT a 1587,9 -> spot 0,1% -> publico BTC justo abajo del ask.
    j = jugada_publicar("BTC", "binance", ask_fx=1607.14, usdt_ask_fx=1587.9,
                        maker_pct=0.20, spot_fee_pct=0.1, undercut_pct=0.0)
    assert isinstance(j, JugadaPublicar)
    assert j.costo_fx == pytest.approx(1589.49, abs=0.01)
    assert j.bruto_pct == pytest.approx(1.11, abs=0.02)
    assert j.neto_pct == pytest.approx(0.91, abs=0.02)


def test_jugada_publicar_sin_maker_fee_rinde_mas():
    """Bybit/OKX/Bitget no cobran maker: la misma prima deja 0,20% más."""
    binance = jugada_publicar("BTC", "binance", ask_fx=1607.14, usdt_ask_fx=1587.9,
                              maker_pct=0.20, spot_fee_pct=0.1)
    bybit = jugada_publicar("BTC", "bybit", ask_fx=1607.14, usdt_ask_fx=1587.9,
                            maker_pct=0.0, spot_fee_pct=0.1)
    assert bybit.neto_pct - binance.neto_pct == pytest.approx(0.20, abs=0.01)


def test_jugada_publicar_undercut_baja_el_precio_de_venta():
    """Publicar 0,1% abajo del mejor ask para quedar primero cuesta 0,1%."""
    j = jugada_publicar("BTC", "binance", ask_fx=1607.14, usdt_ask_fx=1587.9,
                        maker_pct=0.20, spot_fee_pct=0.1, undercut_pct=0.1)
    assert j.vender_fx == pytest.approx(1605.53, abs=0.01)
    assert j.neto_pct == pytest.approx(0.81, abs=0.02)


def test_jugada_publicar_cobertura_compara_margen_contra_volatilidad():
    """El margen tiene que aguantar el movimiento del activo mientras dura la orden."""
    btc = jugada_publicar("BTC", "binance", ask_fx=1607.14, usdt_ask_fx=1587.9,
                          maker_pct=0.20, spot_fee_pct=0.1, vol_p90_pct=0.25)
    doge = jugada_publicar("DOGE", "binance", ask_fx=1618.1, usdt_ask_fx=1587.9,
                           maker_pct=0.20, spot_fee_pct=0.1, vol_p90_pct=1.09)
    assert btc.cobertura == pytest.approx(0.91 / 0.25, abs=0.05)
    # DOGE paga más prima pero cubre peor: ese es el punto del experimento.
    assert doge.bruto_pct > btc.bruto_pct
    assert doge.cobertura < btc.cobertura


def test_jugada_publicar_sin_volatilidad_no_inventa_cobertura():
    j = jugada_publicar("BTC", "binance", ask_fx=1607.14, usdt_ask_fx=1587.9,
                        maker_pct=0.20, spot_fee_pct=0.1)
    assert j.cobertura is None


def test_rankear_ordena_por_neto_y_filtra_lo_que_no_cubre_riesgo():
    js = [
        jugada_publicar("BTC", "binance", ask_fx=1607.0, usdt_ask_fx=1587.9,
                        maker_pct=0.2, spot_fee_pct=0.1, vol_p90_pct=0.25),
        jugada_publicar("ADA", "binance", ask_fx=1614.7, usdt_ask_fx=1587.9,
                        maker_pct=0.2, spot_fee_pct=0.1, vol_p90_pct=1.25),
        jugada_publicar("ETH", "bybit", ask_fx=1613.9, usdt_ask_fx=1587.9,
                        maker_pct=0.0, spot_fee_pct=0.1, vol_p90_pct=0.46),
    ]
    top = rankear(js)
    assert [j.asset for j in top] == ["ETH", "ADA", "BTC"]      # por neto
    seguras = rankear(js, min_cobertura=2.0)
    assert [j.asset for j in seguras] == ["ETH", "BTC"]         # ADA no cubre


def test_rankear_descarta_jugadas_en_perdida():
    perdedora = jugada_publicar("USDC", "binance", ask_fx=1586.3, usdt_ask_fx=1587.9,
                                maker_pct=0.2, spot_fee_pct=0.1)
    assert perdedora.neto_pct < 0
    assert rankear([perdedora]) == []


# --- Guardia de liquidez: una prima enorme en un libro vacío NO es oportunidad ---
# Ver memoria reference_btc_ars_p2p_iliquido y feedback_precio_ejecutable: el 21/08
# el tablero leyó el 15% de ancho de OKX como una jugada y costó plata.

def test_jugada_sin_competencia_no_es_creible():
    """OKX BTC: ask a 1.748 fx (+10%) con 3 avisos y nadie del otro lado."""
    j = jugada_publicar("BTC", "okx", ask_fx=1748.1, usdt_ask_fx=1588.75,
                        maker_pct=0.0, spot_fee_pct=0.1, competidores=3)
    assert j.neto_pct > 9          # el número existe...
    assert j.creible is False      # ...pero no hay libro que lo sostenga


def test_jugada_con_libro_poblado_es_creible():
    j = jugada_publicar("BTC", "binance", ask_fx=1605.6, usdt_ask_fx=1587.85,
                        maker_pct=0.20, spot_fee_pct=0.1, competidores=18)
    assert j.creible is True


def test_creible_es_none_si_no_se_midio_la_competencia():
    j = jugada_publicar("BTC", "binance", ask_fx=1605.6, usdt_ask_fx=1587.85,
                        maker_pct=0.20, spot_fee_pct=0.1)
    assert j.creible is None


def test_rankear_puede_exigir_libro_creible():
    fantasma = jugada_publicar("BTC", "okx", ask_fx=1748.1, usdt_ask_fx=1588.75,
                               maker_pct=0.0, spot_fee_pct=0.1, competidores=3)
    real = jugada_publicar("BTC", "binance", ask_fx=1605.6, usdt_ask_fx=1587.85,
                           maker_pct=0.20, spot_fee_pct=0.1, competidores=18)
    # Sin filtro el fantasma encabeza por su 9,8% y es justo lo que NO queremos.
    assert rankear([real, fantasma])[0].venue == "okx"
    assert [j.venue for j in rankear([real, fantasma], solo_creibles=True)] == ["binance"]


def test_rankear_solo_creibles_no_descarta_lo_no_medido():
    """Sin dato de competencia no se filtra: se desconoce, no se inventa."""
    sin_dato = jugada_publicar("BTC", "binance", ask_fx=1605.6, usdt_ask_fx=1587.85,
                               maker_pct=0.20, spot_fee_pct=0.1)
    assert rankear([sin_dato], solo_creibles=True) == [sin_dato]
