"""Precio de publicación por tamaño de ticket, y contra qué se cierra.

Dos reglas de negocio, no una:

1. Cuando publico un aviso de 5.000 USDT de mínimo, mis rivales NO son los 40
   avisos del libro. Son sólo los que aceptan una orden de ese tamaño
   (min <= ticket <= max). Esa lista es más corta y peor posicionada, así que
   el precio que puedo poner es mejor.

2. El neto NO sale de publicar las dos puntas en el mismo venue: ese ciclo no
   se opera nunca (te quedás esperando dos avisos y pagás la comisión de
   publicar dos veces). Sale de publicar UNA pata y cerrar la otra TOMANDO el
   libro del venue que más convenga, aunque sea otro exchange.
"""
from dataclasses import dataclass

from core.ad_curve import Cierre, Nivel, nivel, curva


@dataclass(frozen=True)
class _Ad:
    price: float
    min_amount: float
    max_amount: float


# Libro chico y explícito. Precios en ARS por USDT, límites en ARS.
# Avisos donde YO COMPRO (side "BUY" del fetcher) = mis rivales al publicar VENTA.
BUY = [
    _Ad(1590.0, 10_000, 3_000_000),    # chico: no aguanta un ticket grande
    _Ad(1596.0, 10_000, 9_000_000),    # aguanta todo
    _Ad(1598.0, 5_000_000, 20_000_000),  # sólo tickets grandes
]
# Avisos donde YO VENDO (side "SELL") = mis rivales al publicar COMPRA.
SELL = [
    _Ad(1584.0, 10_000, 3_000_000),
    _Ad(1580.0, 10_000, 9_000_000),
    _Ad(1578.0, 5_000_000, 20_000_000),
]

BASE = dict(tick=1.0, maker_pct=0.0, floor=500.0, ceil=5000.0,
            venue="binancep2p", cierres=[], network_fee_pct=0.0)


# ---------------------------------------------------------------------------
# 1. A qué precio publico: quién me compite a ese tamaño
# ---------------------------------------------------------------------------

def test_rival_chico_no_compite_por_un_ticket_grande():
    """Un aviso con max 3.000.000 ARS no compite por una orden de 8.000.000."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=5000.0, precio_ref=1600.0, **BASE)
    assert n.rivales_venta == 2   # se cae el de max 3.000.000
    assert n.rivales_compra == 2


def test_rival_de_minimo_alto_no_compite_por_un_ticket_chico():
    """Un aviso con min 5.000.000 ARS no compite por una orden de 1.600.000."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    assert n.rivales_venta == 2   # se cae el de min 5.000.000
    assert n.rivales_compra == 2


def test_publico_venta_un_tick_abajo_del_rival_mas_barato():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    assert n.venta == 1589.0      # min(1590, 1596) - 1


def test_publico_compra_un_tick_arriba_del_rival_que_mas_paga():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    assert n.compra == 1585.0     # max(1584, 1580) + 1


def test_el_ticket_grande_deja_mejor_precio_de_las_dos_puntas():
    """El corazón del asunto: mismo libro, ticket más grande, mejor precio."""
    chico = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    grande = nivel(ads_buy=BUY, ads_sell=SELL, volume=5000.0, precio_ref=1600.0, **BASE)
    assert grande.venta > chico.venta      # vendo más caro
    assert grande.compra < chico.compra    # compro más barato


def test_sin_rivales_a_ese_tamano_no_hay_precio():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=50_000.0, precio_ref=1600.0, **BASE)
    assert n.rivales_venta == 0
    assert n.venta is None


def test_precio_absurdo_se_descarta():
    """Circuit breaker: un libro roto no puede sugerir publicar a 90.000."""
    roto = [_Ad(90_000.0, 10_000, 9_000_000)]
    n = nivel(ads_buy=roto, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    assert n.venta is None


def test_maximo_en_cero_es_sin_tope():
    """Varios fetchers dejan max_amount=0 cuando el exchange no publica tope.
    Tomarlo literal borraría el aviso del libro."""
    sin_tope = [_Ad(1592.0, 10_000, 0)]
    n = nivel(ads_buy=sin_tope, ads_sell=SELL, volume=5000.0, precio_ref=1600.0, **BASE)
    assert n.rivales_venta == 1
    assert n.venta == 1591.0


# ---------------------------------------------------------------------------
# 2. Contra qué cierro: publico UNA pata y tomo el libro del mejor venue
# ---------------------------------------------------------------------------

# Cerrar comprando en okx sale 1.586 y cerrar vendiendo ahí paga 1.586: contra
# este libro conviene publicar VENTA (1.589) y comprar tomando.
CIERRES = [
    Cierre(venue="okexp2p", ask=1586.0, bid=1586.0, fee_tomando_pct=0.0),
    Cierre(venue="bybitp2p", ask=1590.0, bid=1584.0, fee_tomando_pct=0.0),
]
CROSS = {**BASE, "cierres": CIERRES}


def test_el_neto_sale_de_publicar_una_pata_y_cerrar_tomando():
    """Publico venta a 1.589 y compro tomando a 1.586, no el ciclo entero."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **CROSS)
    assert n.lado == "venta"
    assert n.precio == 1589.0
    assert n.cierre_venue == "okexp2p"
    assert n.cierre_precio == 1586.0
    assert round(n.neto_pct, 4) == round((1589.0 - 1586.0) / 1586.0 * 100, 4)


def test_elige_el_venue_de_cierre_mas_barato_para_comprar():
    """bybit vende a 1.590 y okx a 1.586: cierro donde me sale menos."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **CROSS)
    assert n.cierre_venue == "okexp2p"


def test_gana_la_direccion_que_mas_rinde():
    """Si cerrar vendiendo paga mucho, la jugada pasa a ser publicar COMPRA."""
    caros = [Cierre(venue="okexp2p", ask=1620.0, bid=1620.0, fee_tomando_pct=0.0)]
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
              **{**CROSS, "cierres": caros})
    assert n.lado == "compra"
    assert n.precio == 1585.0
    assert round(n.neto_pct, 4) == round((1620.0 - 1585.0) / 1585.0 * 100, 4)


def test_la_comision_de_publicar_se_cobra_una_sola_vez():
    """Lo que motivó el cambio: 0,20% de Binance, no 0,40%."""
    sin = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **CROSS)
    con = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
                **{**CROSS, "maker_pct": 0.2})
    assert round(sin.neto_pct - con.neto_pct, 6) == 0.2


def test_el_fee_de_tomador_del_venue_de_cierre_se_descuenta():
    caro = [Cierre(venue="okexp2p", ask=1586.0, bid=1586.0, fee_tomando_pct=0.15)]
    sin = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **CROSS)
    con = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
                **{**CROSS, "cierres": caro})
    assert round(sin.neto_pct - con.neto_pct, 6) == 0.15


def test_cerrar_en_otro_exchange_paga_el_fee_de_red():
    """Mover el USDT cuesta; cerrar en el mismo venue no."""
    propio = [Cierre(venue="binancep2p", ask=1586.0, bid=1586.0, fee_tomando_pct=0.0)]
    ajeno = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
                  **{**CROSS, "network_fee_pct": 0.1})
    mismo = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
                  **{**CROSS, "cierres": propio, "network_fee_pct": 0.1})
    assert round(mismo.neto_pct - ajeno.neto_pct, 6) == 0.1


def test_ganancia_es_por_el_ticket_entero():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=3000.0, precio_ref=1600.0, **CROSS)
    assert round(n.ganancia_ars - 3000.0 * n.cierre_precio * n.neto_pct / 100, 6) == 0


def test_sin_venue_donde_cerrar_no_hay_jugada():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0, **BASE)
    assert n.neto_pct is None and n.ganancia_ars is None and n.lado is None
    assert n.venta == 1589.0          # el precio de publicación sigue estando


def test_el_lado_que_no_puedo_publicar_no_se_elige():
    """Bitget no me deja crear el aviso: ese precio es referencia, no jugada."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
              **{**CROSS, "puede_venta": False})
    assert n.venta == 1589.0          # el precio se sigue mostrando
    assert n.lado == "compra"         # pero la jugada sale del otro lado


def test_sin_ningun_lado_habilitado_no_hay_jugada():
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=1000.0, precio_ref=1600.0,
              **{**CROSS, "puede_venta": False, "puede_compra": False})
    assert n.lado is None and n.neto_pct is None


def test_curva_respeta_las_habilitaciones_por_venue():
    out = curva(
        libros={"binancep2p": (BUY, SELL), "bitgetp2p": (BUY, SELL)},
        volumes=[1000.0],
        precios_ref={"binancep2p": 1600.0, "bitgetp2p": 1600.0},
        maker_pct={}, cierres={1000.0: CIERRES},
        tick=1.0, floor=500.0, ceil=5000.0, network_fee_pct=0.0,
        puede_compra={"bitgetp2p": False}, puede_venta={"bitgetp2p": False},
    )
    assert out["binancep2p"][0].lado == "venta"
    assert out["bitgetp2p"][0].lado is None


def test_sin_precio_para_publicar_no_hay_jugada():
    """A 50.000 USDT no hay rival: no hay aviso que publicar de ningún lado."""
    n = nivel(ads_buy=BUY, ads_sell=SELL, volume=50_000.0, precio_ref=1600.0, **CROSS)
    assert n.lado is None and n.neto_pct is None


# ---------------------------------------------------------------------------
# 3. La curva: un nivel por venue y por tamaño
# ---------------------------------------------------------------------------

def test_curva_arma_un_nivel_por_venue_y_por_tamano():
    out = curva(
        libros={"binancep2p": (BUY, SELL), "bybitp2p": (BUY, SELL)},
        volumes=[1000.0, 5000.0],
        precios_ref={"binancep2p": 1600.0, "bybitp2p": 1600.0},
        maker_pct={"binancep2p": 0.2},
        cierres={1000.0: CIERRES, 5000.0: CIERRES},
        tick=1.0, floor=500.0, ceil=5000.0, network_fee_pct=0.0,
    )
    assert sorted(out) == ["binancep2p", "bybitp2p"]
    assert [n.volume for n in out["binancep2p"]] == [1000.0, 5000.0]
    assert isinstance(out["binancep2p"][0], Nivel)
    # bybit publica gratis: mismo libro, mejor neto que binance
    assert out["bybitp2p"][0].neto_pct > out["binancep2p"][0].neto_pct


def test_curva_le_pasa_a_cada_venue_su_propio_nombre():
    """Sin eso, el fee de red no sabría si el cierre es en casa o afuera."""
    propio = [Cierre(venue="binancep2p", ask=1586.0, bid=1586.0, fee_tomando_pct=0.0)]
    out = curva(
        libros={"binancep2p": (BUY, SELL), "bybitp2p": (BUY, SELL)},
        volumes=[1000.0],
        precios_ref={"binancep2p": 1600.0, "bybitp2p": 1600.0},
        maker_pct={}, cierres={1000.0: propio},
        tick=1.0, floor=500.0, ceil=5000.0, network_fee_pct=0.1,
    )
    # binance cierra en su propia casa (no paga red); bybit tiene que mandarlo
    assert round(out["binancep2p"][0].neto_pct - out["bybitp2p"][0].neto_pct, 6) == 0.1


def test_curva_saltea_el_venue_sin_precio_de_referencia():
    out = curva(
        libros={"binancep2p": (BUY, SELL), "roto": (BUY, SELL)},
        volumes=[1000.0], precios_ref={"binancep2p": 1600.0},
        maker_pct={}, cierres={1000.0: CIERRES},
        tick=1.0, floor=500.0, ceil=5000.0, network_fee_pct=0.0,
    )
    assert list(out) == ["binancep2p"]
