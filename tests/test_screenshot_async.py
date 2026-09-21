"""Leer una captura tiene que funcionar también desde dentro del bot.

El 2026-09-08 el usuario mandó una captura de KuCoin por Telegram y el bot la
perdió: los modelos gratuitos no pudieron leerla, cayó al fallback de Claude y
ese hacía `asyncio.run()` adentro del event loop del bot →
"asyncio.run() cannot be called from a running event loop". La imagen no quedaba
en ningún lado, así que hubo que pedírsela de nuevo.
"""
import asyncio

import pytest

from core.screenshot_parser import _run_sync


async def _dame(v):
    await asyncio.sleep(0)
    return v


class TestRunSync:
    def test_sin_loop_corriendo_devuelve_el_resultado(self):
        assert _run_sync(lambda: _dame(42)) == 42

    def test_dentro_de_un_loop_no_explota(self):
        """El caso del bot: ya hay un event loop andando."""
        async def desde_el_bot():
            return _run_sync(lambda: _dame("ok"))
        assert asyncio.run(desde_el_bot()) == "ok"

    def test_propaga_el_error_de_la_corutina(self):
        async def rompe():
            raise ValueError("boom")
        with pytest.raises(ValueError, match="boom"):
            _run_sync(rompe)

    def test_propaga_el_error_tambien_desde_un_loop(self):
        async def rompe():
            raise ValueError("boom")

        async def desde_el_bot():
            return _run_sync(rompe)
        with pytest.raises(ValueError, match="boom"):
            asyncio.run(desde_el_bot())
