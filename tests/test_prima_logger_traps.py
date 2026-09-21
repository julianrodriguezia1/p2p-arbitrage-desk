"""El logger de prima tiene que guardar el precio ejecutable, no la punta cruda.

Medido el 2026-09-07: un aviso trampa de Bybit a ~1.420 ARS (con el mercado en
1.580) estaba en 677 de 679 filas del histórico — el 99,7% —, dando anchos de
-10,9%. Cualquier conclusión de horarios sacada de esa serie estaba mal.
"""
import cli.prima_logger as pl
from p2p_scanner import Ad


def _ad(side, price, available=1000.0, orders=50):
    return Ad(exchange="bybit", side=side, price=price, min_amount=1000,
              max_amount=price * available, available=available,
              merchant="x", orders=orders, finish_rate=0.99)


def _patch(monkeypatch, vende, compra):
    import cli.prima_alt as pa

    def fn(asset, fiat, tradetype, rows=20):
        return vende if tradetype == "BUY" else compra
    monkeypatch.setitem(pa.FETCHERS, "bybit", fn)


class TestMuestraSinTrampas:
    def test_el_anzuelo_no_entra_en_la_serie(self, monkeypatch):
        vende = [_ad("BUY", 1420.0, available=3.0)] + [
            _ad("BUY", 1580.0 + i) for i in range(10)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(10)]
        _patch(monkeypatch, vende, compra)
        m = pl.leer_libro("bybit", "USDT", 1.0, usdt_ask=1580.0, usdt_bid=1578.0)
        assert m.ask_ars > 1570, f"el anzuelo se guardó: {m.ask_ars}"

    def test_el_ancho_deja_de_ser_negativo(self, monkeypatch):
        vende = [_ad("BUY", 1420.0, available=3.0)] + [
            _ad("BUY", 1580.0 + i) for i in range(10)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(10)]
        _patch(monkeypatch, vende, compra)
        m = pl.leer_libro("bybit", "USDT", 1.0, usdt_ask=1580.0, usdt_bid=1578.0)
        assert m.ask_ars > m.bid_ars, "quien vende no puede pedir menos que quien compra"

    def test_un_libro_sano_se_guarda_igual(self, monkeypatch):
        vende = [_ad("BUY", 1580.0 + i) for i in range(10)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(10)]
        _patch(monkeypatch, vende, compra)
        m = pl.leer_libro("bybit", "USDT", 1.0, usdt_ask=1580.0, usdt_bid=1578.0)
        assert 1580 <= m.ask_ars <= 1590
        assert 1569 <= m.bid_ars <= 1578

    def test_sigue_guardando_avisos_y_profundidad(self, monkeypatch):
        vende = [_ad("BUY", 1580.0 + i) for i in range(6)]
        compra = [_ad("SELL", 1578.0 - i) for i in range(4)]
        _patch(monkeypatch, vende, compra)
        m = pl.leer_libro("bybit", "USDT", 1.0, usdt_ask=1580.0, usdt_bid=1578.0)
        assert (m.n_ask, m.n_bid) == (6, 4)
        assert m.depth_ask_usd == 6000.0

    def test_libro_vacio_sigue_devolviendo_none(self, monkeypatch):
        _patch(monkeypatch, [], [])
        assert pl.leer_libro("bybit", "USDT", 1.0, usdt_ask=1580.0, usdt_bid=1578.0) is None
