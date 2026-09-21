"""El buscador de rutas tiene que ver el mismo precio que el dashboard.

El 2026-09-07 un aviso trampa de Bybit (1.422 ARS con 3,2 USDT de stock, contra
un mercado en 1.580) infló TODAS las rutas del ranking a +12,72%: `libro()`
tomaba la mejor punta absoluta en vez del precio ejecutable por profundidad.
"""
from cli.rutas import libro
from p2p_scanner import Ad


def _ad(side, price, available=1000.0, orders=50):
    return Ad(exchange="bybit", side=side, price=price, min_amount=1000,
              max_amount=price * available, available=available,
              merchant="x", orders=orders, finish_rate=0.99)


def _fetcher(vende, compra):
    def fn(asset, fiat, tradetype, rows=20):
        return vende if tradetype == "BUY" else compra
    return fn


class TestLibroIgnoraTrampas:
    def test_un_aviso_muy_barato_y_chico_no_baja_el_precio(self, monkeypatch):
        """El aviso trampa a 1.422 no puede pisar un libro que está en 1.580."""
        import cli.rutas as r
        vende = [_ad("BUY", 1422.0, available=3.2)] + [
            _ad("BUY", 1580.0 + i) for i in range(10)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(10)]
        monkeypatch.setitem(r.FETCHERS, "bybit", _fetcher(vende, compra))
        ask, bid, n_ask, n_bid = libro("bybit", "USDT")
        assert ask > 1570, f"el aviso trampa se coló: ask={ask}"

    def test_un_libro_normal_da_la_zona_de_la_punta(self, monkeypatch):
        import cli.rutas as r
        vende = [_ad("BUY", 1580.0 + i) for i in range(10)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(10)]
        monkeypatch.setitem(r.FETCHERS, "bybit", _fetcher(vende, compra))
        ask, bid, _, _ = libro("bybit", "USDT")
        assert 1580 <= ask <= 1590
        assert 1569 <= bid <= 1578

    def test_sigue_contando_los_avisos_vivos(self, monkeypatch):
        import cli.rutas as r
        vende = [_ad("BUY", 1580.0 + i) for i in range(7)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(4)]
        monkeypatch.setitem(r.FETCHERS, "bybit", _fetcher(vende, compra))
        _, _, n_ask, n_bid = libro("bybit", "USDT")
        assert (n_ask, n_bid) == (7, 4)

    def test_libro_vacio_no_rompe(self, monkeypatch):
        import cli.rutas as r
        monkeypatch.setitem(r.FETCHERS, "bybit", _fetcher([], []))
        assert libro("bybit", "USDT") == (None, None, 0, 0)
