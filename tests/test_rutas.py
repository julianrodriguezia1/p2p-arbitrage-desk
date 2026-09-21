"""Tests del buscador de rutas: encuentra ciclos ARS->...->ARS que dejen plata."""
import pytest

from core.rutas import Paso, buscar, neto_pct


def p(origen, destino, rate, *, fee=0.0, tipo="tomar", venue="binance",
      publica=False, red=False, avisos=None):
    return Paso(origen=origen, destino=destino, rate=rate, fee_pct=fee, tipo=tipo,
                venue=venue, publica=publica, red=red, avisos=avisos)


# --- la matemática del ciclo ---

def test_neto_pct_multiplica_las_tasas_y_resta_los_fees():
    # 1 ARS -> 1/1000 USDT -> *1010 ARS = 1,010 ARS, menos 0,1% de fee
    pasos = [p("ARS", "USDT@b", 1 / 1000), p("USDT@b", "ARS", 1010, fee=0.1)]
    assert neto_pct(pasos) == pytest.approx(0.899, abs=0.01)


def test_neto_pct_de_un_ciclo_alineado_da_negativo_por_los_fees():
    """Sin desalineación, un ciclo sólo pierde los fees. Es el umbral a vencer."""
    pasos = [p("ARS", "USDT@b", 1 / 1000, fee=0.1), p("USDT@b", "ARS", 1000, fee=0.1)]
    assert neto_pct(pasos) < 0


def test_neto_pct_de_ruta_vacia_es_cero():
    assert neto_pct([]) == 0.0


# --- la búsqueda de ciclos ---

def test_buscar_encuentra_el_ciclo_rentable():
    pasos = [p("ARS", "USDT@b", 1 / 1587.9), p("USDT@b", "ARS", 1600.0)]
    rutas = buscar(pasos, inicio="ARS", max_pasos=3)
    assert len(rutas) == 1
    assert rutas[0].neto_pct == pytest.approx(0.762, abs=0.01)
    assert [s.destino for s in rutas[0].pasos] == ["USDT@b", "ARS"]


def test_buscar_descarta_los_ciclos_que_pierden():
    pasos = [p("ARS", "USDT@b", 1 / 1600.0), p("USDT@b", "ARS", 1587.9)]
    assert buscar(pasos, inicio="ARS", max_pasos=3) == []


def test_buscar_arma_rutas_de_tres_patas():
    """ARS -> USDT -> BTC -> ARS: la ruta sintética, que una sola pata no ve."""
    pasos = [
        p("ARS", "USDT@b", 1 / 1587.9),
        p("USDT@b", "BTC@b", 1 / 77000, fee=0.1, tipo="spot"),
        # pesos por BTC = fx de venta (1,1% arriba del de compra) x precio en USD
        p("BTC@b", "ARS", 1587.9 * 1.011 * 77000, fee=0.2, tipo="publicar", publica=True),
    ]
    rutas = buscar(pasos, inicio="ARS", max_pasos=4)
    assert len(rutas) == 1
    r = rutas[0]
    assert [s.tipo for s in r.pasos] == ["tomar", "spot", "publicar"]
    assert r.neto_pct == pytest.approx(0.80, abs=0.05)


def test_buscar_ordena_de_mayor_a_menor_neto():
    pasos = [
        p("ARS", "USDT@b", 1 / 1587.9), p("USDT@b", "ARS", 1600.0),
        p("ARS", "USDT@k", 1 / 1587.9), p("USDT@k", "ARS", 1620.0, venue="kucoin"),
    ]
    rutas = buscar(pasos, inicio="ARS", max_pasos=3)
    assert len(rutas) == 2
    assert rutas[0].neto_pct > rutas[1].neto_pct


def test_buscar_respeta_el_maximo_de_pasos():
    pasos = [
        p("ARS", "USDT@b", 1 / 1587.9),
        p("USDT@b", "BTC@b", 1 / 77000, tipo="spot"),
        p("BTC@b", "ARS", 1587.9 * 1.05 * 77000),
    ]
    assert buscar(pasos, inicio="ARS", max_pasos=2) == []
    assert len(buscar(pasos, inicio="ARS", max_pasos=3)) == 1


def test_buscar_no_repite_nodos_para_no_ciclar_infinito():
    pasos = [
        p("ARS", "USDT@b", 1 / 1587.9),
        p("USDT@b", "USDT@k", 1.0, tipo="red", red=True),
        p("USDT@k", "USDT@b", 1.0, tipo="red", red=True),
        p("USDT@k", "ARS", 1620.0),
    ]
    rutas = buscar(pasos, inicio="ARS", max_pasos=6)
    for r in rutas:
        nodos = [s.destino for s in r.pasos[:-1]]
        assert len(nodos) == len(set(nodos))


# --- el perfil de riesgo de cada ruta ---

def test_ruta_cuenta_las_patas_que_dependen_de_que_te_tomen():
    pasos = [
        p("ARS", "BTC@b", 1 / 1580.0, tipo="publicar", publica=True),
        p("BTC@b", "ARS", 1610.0, tipo="publicar", publica=True),
    ]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert r.publica_n == 2      # doble maker: el doble de riesgo de no cerrar


def test_ruta_cuenta_las_transferencias_de_red():
    pasos = [
        p("ARS", "USDT@b", 1 / 1587.9),
        p("USDT@b", "USDT@k", 1.0, fee=0.1, tipo="red", red=True),
        p("USDT@k", "ARS", 1620.0, venue="kucoin"),
    ]
    r = buscar(pasos, inicio="ARS", max_pasos=4)[0]
    assert r.red_n == 1


def test_ruta_reporta_el_libro_mas_flaco_que_usa():
    """Una ruta vale lo que su pata menos líquida."""
    pasos = [p("ARS", "USDT@b", 1 / 1587.9, avisos=20),
             p("USDT@b", "ARS", 1620.0, avisos=2)]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert r.min_avisos == 2
    assert r.creible is False


def test_ruta_creible_cuando_todas_las_patas_tienen_libro():
    pasos = [p("ARS", "USDT@b", 1 / 1587.9, avisos=20),
             p("USDT@b", "ARS", 1600.0, avisos=15)]
    assert buscar(pasos, inicio="ARS", max_pasos=3)[0].creible is True


def test_ruta_sin_conteo_de_avisos_no_afirma_credibilidad():
    pasos = [p("ARS", "USDT@b", 1 / 1587.9), p("USDT@b", "ARS", 1600.0)]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert r.min_avisos is None
    assert r.creible is None


def test_buscar_puede_filtrar_las_rutas_de_libro_fantasma():
    real = [p("ARS", "USDT@b", 1 / 1587.9, avisos=20), p("USDT@b", "ARS", 1600.0, avisos=15)]
    humo = [p("ARS", "BTC@o", 1 / 1590.0, avisos=20, venue="okx"),
            p("BTC@o", "ARS", 1746.0, avisos=3, venue="okx")]
    rutas = buscar(real + humo, inicio="ARS", max_pasos=3, solo_creibles=True)
    assert [r.pasos[0].destino for r in rutas] == ["USDT@b"]


# --- Lo que decide de verdad: cuánto flujo pasa por la pata que publicás ---
# Un 1,97% por vuelta sobre un libro que mueve 0 USD/hora rinde 0.

from core.rutas import cuello_usd_h, ganancia_ars_h


def pp(origen, destino, rate, *, asset, lado, publica=True, fee=0.2):
    return Paso(origen=origen, destino=destino, rate=rate, fee_pct=fee,
                tipo="publicar" if publica else "tomar", venue="binance",
                publica=publica, asset=asset, lado=lado)


FLUJO = {("BTC", "ask"): 235.0, ("BTC", "bid"): 1455.0,
         ("ETH", "ask"): 0.0, ("ETH", "bid"): 0.0,
         ("USDT", "ask"): 14690.0}


def test_cuello_usd_h_es_la_pata_publicada_mas_flaca():
    pasos = [pp("ARS", "BTC@b", 1 / 1580, asset="BTC", lado="bid"),
             pp("BTC@b", "ARS", 1610, asset="BTC", lado="ask")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert cuello_usd_h(r, FLUJO) == pytest.approx(235.0)   # el ask manda


def test_cuello_usd_h_detecta_el_mercado_muerto():
    pasos = [pp("ARS", "ETH@b", 1 / 3846752, asset="ETH", lado="bid"),
             pp("ETH@b", "ARS", 3938189, asset="ETH", lado="ask")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert r.neto_pct > 1.9                    # el % es lindo...
    assert cuello_usd_h(r, FLUJO) == 0.0       # ...y no pasa nadie


def test_cuello_usd_h_es_none_si_no_se_midio_esa_pata():
    pasos = [pp("ARS", "XRP@b", 1 / 1580, asset="XRP", lado="bid"),
             pp("XRP@b", "ARS", 1620, asset="XRP", lado="ask")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert cuello_usd_h(r, FLUJO) is None


def test_cuello_usd_h_ignora_las_patas_que_solo_tomas():
    """Tomar no espera a nadie: no limita el ritmo."""
    pasos = [pp("ARS", "USDT@b", 1 / 1587.9, asset="USDT", lado="ask",
                publica=False, fee=0.0),
             pp("USDT@b", "ARS", 1610, asset="USDT", lado="bid")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    # sólo la segunda pata publica, y de USDT bid no hay dato -> None
    assert cuello_usd_h(r, FLUJO) is None


def test_ganancia_ars_h_multiplica_neto_por_flujo_y_fx():
    pasos = [pp("ARS", "BTC@b", 1 / 1580, asset="BTC", lado="bid"),
             pp("BTC@b", "ARS", 1610, asset="BTC", lado="ask")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    # 235 USD/h de cuello x 1,50% neto x 1590 ARS/USD
    esperado = 235.0 * r.neto_pct / 100 * 1590
    assert ganancia_ars_h(r, FLUJO, 1590) == pytest.approx(esperado, rel=0.001)


def test_ganancia_ars_h_es_none_sin_flujo_medido():
    pasos = [pp("ARS", "XRP@b", 1 / 1580, asset="XRP", lado="bid"),
             pp("XRP@b", "ARS", 1620, asset="XRP", lado="ask")]
    r = buscar(pasos, inicio="ARS", max_pasos=3)[0]
    assert ganancia_ars_h(r, FLUJO, 1590) is None
