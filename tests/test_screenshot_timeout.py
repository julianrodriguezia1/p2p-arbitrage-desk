"""El fallback a Claude no puede colgar el bot para siempre.

El 2026-09-08 el bot contestó "🔍 Leyendo la captura…" y no volvió nunca: los
modelos gratuitos fallaron, cayó al fallback de Claude y ahí se quedó sin
límite de tiempo. Para el usuario es peor que un error: no sabe si esperar.
"""
import asyncio

import pytest

from core.screenshot_parser import _run_sync


class TestTimeout:
    def test_una_corutina_lenta_corta_y_avisa(self):
        async def se_cuelga():
            await asyncio.sleep(30)
            return "tarde"
        with pytest.raises(TimeoutError):
            _run_sync(se_cuelga, timeout=0.3)

    def test_dentro_de_un_loop_tambien_corta(self):
        async def se_cuelga():
            await asyncio.sleep(30)

        async def desde_el_bot():
            return _run_sync(se_cuelga, timeout=0.3)
        with pytest.raises(TimeoutError):
            asyncio.run(desde_el_bot())

    def test_lo_que_responde_a_tiempo_pasa(self):
        async def rapida():
            return "ok"
        assert _run_sync(rapida, timeout=5) == "ok"

    def test_sin_timeout_explicito_hay_uno_por_defecto(self):
        from core.screenshot_parser import CLAUDE_TIMEOUT_S
        assert 0 < CLAUDE_TIMEOUT_S <= 180


class TestNoBloqueaElBot:
    def test_la_lectura_corre_fuera_del_hilo_del_bot(self):
        """Leer una captura tarda hasta 90s: si corre en el event loop, el bot
        no atiende nada más mientras tanto."""
        import inspect

        from bot import captura
        src = inspect.getsource(captura.on_photo)
        assert "to_thread" in src, "extract_fields bloquea el loop del bot"
