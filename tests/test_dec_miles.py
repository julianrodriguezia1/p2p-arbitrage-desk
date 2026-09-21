"""'350.000' en una captura argentina son trescientos cincuenta mil.

El 2026-09-08 una captura de KuCoin se rechazó tres veces con "las cuentas no
cierran (222.003742x1576.55 vs 350.000)". Los modelos habían leído bien —
222,003742 x 1.576,55 = 350.000 exacto — pero `_dec("350.000")` devolvía 350,
porque sin coma el punto se tomaba como decimal.
"""
import pytest

from core.capture_parser import _dec


class TestPuntoDeMiles:
    def test_el_caso_que_rompio(self):
        assert _dec("350.000") == 350000

    def test_varios_puntos_son_todos_de_miles(self):
        assert _dec("1.234.567") == 1234567

    def test_un_precio_de_usdt_sin_coma(self):
        assert _dec("1.580") == 1580


class TestLoQueYaAndaba:
    @pytest.mark.parametrize("crudo,esperado", [
        ("95.013,02", 95013.02),       # formato argentino completo
        ("1556.50", 1556.50),          # punto decimal, 2 dígitos
        ("1556,50", 1556.50),          # coma decimal
        ("222.003742", 222.003742),    # cantidad con 6 decimales
        ("95.013,02 ARS", 95013.02),
        ("$1.234,56", 1234.56),
        ("64,590770 USDT", 64.590770),
        ("1578.44", 1578.44),
    ])
    def test_no_se_rompe(self, crudo, esperado):
        assert float(_dec(crudo)) == pytest.approx(float(esperado))

    @pytest.mark.parametrize("crudo,esperado", [
        ("0.048", 0.048),              # BTC: la parte entera en 0 es decimal
        ("0.001", 0.001),
        ("0.00002", 0.00002),
    ])
    def test_los_montos_de_btc_siguen_siendo_decimales(self, crudo, esperado):
        assert float(_dec(crudo)) == pytest.approx(esperado)

    def test_none_y_basura(self):
        assert _dec(None) is None
        assert _dec("no es un numero") is None

    def test_numeros_nativos(self):
        assert _dec(1580) == 1580
        assert float(_dec(1580.5)) == pytest.approx(1580.5)


class TestValidacionCruzada:
    def test_la_captura_de_kucoin_ahora_cierra(self):
        gross, price, total = _dec("222.003742"), _dec("1576.55"), _dec("350.000")
        assert abs(gross * price - total) / total < 0.015
