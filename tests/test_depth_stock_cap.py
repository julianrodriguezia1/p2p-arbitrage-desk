"""Un aviso con stock gigante no puede definir solo el centro del libro.

Caso real, KuCoin 2026-09-08. El lado comprador tenía los precios de verdad
(1.575, 1.562) con ~50.000 de stock y dos avisos absurdos (1.370 y 1.212) con
122.000. La mediana ponderada por stock daba 1.370, así que `filter_traps`
descartaba los avisos BUENOS por "alejarse del centro" y el motor informaba que
en KuCoin te compraban a 1.406 cuando te compraban a 1.575.

El supuesto que falla: que mucho stock implica aviso legítimo. En un libro P2P
es al revés — esos avisos acumulan stock justamente porque nadie los toma.
"""
from core.p2p_depth import _weighted_median_price, compute_depth_quote, filter_traps
from p2p_scanner import Ad


def _ad(price, available, side="SELL", orders=500, minimo=15000):
    return Ad(exchange="kucoin", side=side, price=price, min_amount=minimo,
              max_amount=price * available, available=available,
              merchant="x", orders=orders, finish_rate=0.98)


#: El libro real de compradores de KuCoin del 2026-09-08.
KUCOIN_BID = [
    _ad(1575.00, 5000.0, minimo=150000), _ad(1575.00, 11000.0, minimo=150000),
    _ad(1572.10, 5000.0), _ad(1572.00, 7000.0), _ad(1571.60, 1359.6),
    _ad(1562.00, 20000.0, minimo=200000), _ad(1555.00, 5835.6),
    _ad(1496.00, 150.0), _ad(1496.00, 150.0), _ad(1406.47, 1000.0),
    _ad(1371.00, 200.0), _ad(1370.00, 70000.0), _ad(1212.00, 52188.0),
    _ad(1200.00, 1589.4),
]


class TestCentroDelLibro:
    def test_el_stock_gigante_de_un_aviso_absurdo_no_manda(self):
        centro = _weighted_median_price(KUCOIN_BID)
        assert centro > 1540, f"el centro se fue a la basura: {centro}"

    def test_los_avisos_buenos_sobreviven_al_filtro(self):
        precios = [a.price for a in filter_traps(KUCOIN_BID)]
        assert 1575.00 in precios, "descartó el mejor precio real"
        assert 1562.00 in precios

    def test_la_basura_se_va(self):
        precios = [a.price for a in filter_traps(KUCOIN_BID)]
        assert 1212.00 not in precios
        assert 1370.00 not in precios

    def test_el_precio_informado_es_el_real(self):
        q = compute_depth_quote([], KUCOIN_BID, 99)
        assert q["bid"] > 1550, f"informó {q['bid']}, el libro paga 1.575"


class TestNoRompeLoQueYaAndaba:
    def test_una_cola_de_avisos_chicos_sigue_sin_envenenar(self):
        """Lo que la mediana ponderada vino a arreglar tiene que seguir andando."""
        libro = [_ad(1580.0, 5000.0)] + [_ad(1400.0 + i, 5.0) for i in range(20)]
        assert _weighted_median_price(libro) > 1500

    def test_libro_sano_no_pierde_avisos(self):
        libro = [_ad(1580.0 - i, 1000.0) for i in range(5)]
        assert len(filter_traps(libro)) == 5

    def test_sin_stock_cae_a_la_mediana_simple(self):
        libro = [_ad(1580.0, 0.0), _ad(1570.0, 0.0), _ad(1560.0, 0.0)]
        assert _weighted_median_price(libro) == 1570.0
