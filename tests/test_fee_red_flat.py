"""El fee de red es un monto fijo, no un porcentaje.

Leído de la API de Binance el 2026-09-08 (/sapi/v1/capital/config/getall):
BSC 0,01 · MATIC 0,07 · ARBITRUM 0,1 · ETH 0,3 · TRX 1,5 USDT. Modelarlo como
0,1% castiga las rutas cross-venue hasta 100 veces de más en tickets grandes.
"""
import pytest

import config
from core.fees import red_pct


class TestRedPct:
    def test_el_flat_pesa_mas_en_tickets_chicos(self):
        assert red_pct(volume=99) > red_pct(volume=1000)

    def test_bsc_sobre_mil_dolares_es_casi_cero(self):
        # 0,01 USDT sobre 1.000 = 0,001%
        assert red_pct(volume=1000) == pytest.approx(0.001, abs=1e-6)

    def test_bsc_sobre_noventa_y_nueve(self):
        assert red_pct(volume=99) == pytest.approx(0.0101, abs=1e-4)

    def test_se_puede_pedir_otra_red(self):
        # TRC20 cuesta 150 veces más que BSC
        assert red_pct(volume=1000, red="TRX") == pytest.approx(0.15, abs=1e-6)

    def test_una_red_desconocida_no_rompe_y_avisa_caro(self):
        """Sin dato no se inventa uno barato: se cobra la red más cara conocida."""
        caro = max(config.FEE_RED_USDT_FLAT.values())
        assert red_pct(volume=1000, red="LOQUESEA") == pytest.approx(
            caro / 1000 * 100, abs=1e-6)

    def test_volumen_cero_no_divide_por_cero(self):
        assert red_pct(volume=0) == 0.0


class TestConfig:
    def test_estan_las_redes_medidas(self):
        for red in ("BSC", "TRX", "ETH"):
            assert red in config.FEE_RED_USDT_FLAT

    def test_bsc_es_la_mas_barata(self):
        assert config.FEE_RED_USDT_FLAT["BSC"] == min(
            config.FEE_RED_USDT_FLAT.values())
