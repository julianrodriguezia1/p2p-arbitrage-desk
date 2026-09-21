import asyncio

import pytest

from telegram.ext import Application, CallbackQueryHandler, MessageHandler
from telegram.ext import filters as tg_filters

from bot import telegram_bot


def _build_app(monkeypatch):
    import config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "123:ABC", raising=False)
    captured = {}

    class _FakeApp:
        def __init__(self):
            self.handlers = []

        def add_handler(self, h):
            self.handlers.append(h)

        def run_polling(self):
            captured["app"] = self

    class _FakeBuilder:
        def token(self, _):
            return self

        def build(self):
            return _FakeApp()

    monkeypatch.setattr(Application, "builder", staticmethod(lambda: _FakeBuilder()))
    telegram_bot.main()
    return captured["app"]


def test_registra_handler_de_foto(monkeypatch):
    app = _build_app(monkeypatch)
    photo_handlers = [h for h in app.handlers
                      if isinstance(h, MessageHandler) and h.filters == tg_filters.PHOTO]
    assert len(photo_handlers) == 1


def test_registra_callback_de_captura(monkeypatch):
    app = _build_app(monkeypatch)
    cap_cb = [h for h in app.handlers
              if isinstance(h, CallbackQueryHandler)
              and getattr(h, "pattern", None) is not None
              and h.pattern.pattern == "^cap_(ok|no):"]
    assert len(cap_cb) == 1


def test_registra_handler_de_texto_libre(monkeypatch):
    from bot.orquestador import on_text
    app = _build_app(monkeypatch)
    text_handlers = [h for h in app.handlers
                     if isinstance(h, MessageHandler) and h.callback is on_text]
    assert len(text_handlers) == 1


def test_texto_libre_va_despues_del_cotizar(monkeypatch):
    # el ConversationHandler de /cotizar debe registrarse ANTES del handler de
    # texto, así una cotización en curso captura el margen.
    from telegram.ext import ConversationHandler
    from bot.orquestador import on_text
    app = _build_app(monkeypatch)
    idx_conv = next(i for i, h in enumerate(app.handlers)
                    if isinstance(h, ConversationHandler))
    idx_text = next(i for i, h in enumerate(app.handlers)
                    if isinstance(h, MessageHandler) and h.callback is on_text)
    assert idx_conv < idx_text


# ── /cotizar: primero el activo, después el lado, después el margen ────────

def test_cotizar_registra_el_estado_de_activo(monkeypatch):
    from telegram.ext import ConversationHandler
    app = _build_app(monkeypatch)
    conv = next(h for h in app.handlers if isinstance(h, ConversationHandler))
    estados = conv.states[telegram_bot.COTIZA_ASSET]
    assert any(h.pattern.pattern == "^act_(usdt|btc)$" for h in estados)


class _FakeMessage:
    def __init__(self, text=""):
        self.text = text
        self.replies = []
        self.photos = []

    async def reply_text(self, text, **kw):
        self.replies.append((text, kw))

    async def reply_photo(self, photo, caption=None, **kw):
        self.photos.append((photo, caption))


class _FakeQuery:
    def __init__(self, data):
        self.data = data
        self.edits = []

    async def answer(self):
        pass

    async def edit_message_text(self, text, **kw):
        self.edits.append(text)


class _FakeUpdate:
    def __init__(self, text=None, callback=None):
        self.message = _FakeMessage(text) if text is not None else None
        self.callback_query = _FakeQuery(callback) if callback else None
        self.effective_chat = type("C", (), {"id": 1})()


class _FakeCtx:
    def __init__(self):
        self.user_data = {}


@pytest.fixture
def cotiza_env(monkeypatch):
    import config
    monkeypatch.setattr(config, "DASHBOARD_URL", "http://vps:8002", raising=False)
    monkeypatch.setattr(telegram_bot, "_ok", lambda u: True)
    llamadas = []

    def _placa(url, lado, margen, activo="USDT"):
        llamadas.append((lado, margen, activo))
        return None, "placa"

    monkeypatch.setattr(telegram_bot, "cotizacion_placa", _placa)
    return llamadas


def test_cotizar_arranca_preguntando_el_activo(cotiza_env):
    update, ctx = _FakeUpdate(text="/cotizar"), _FakeCtx()
    estado = asyncio.run(telegram_bot.cmd_cotizar(update, ctx))
    assert estado == telegram_bot.COTIZA_ASSET
    botones = [b.callback_data
               for fila in update.message.replies[0][1]["reply_markup"].inline_keyboard
               for b in fila]
    assert botones == ["act_usdt", "act_btc"]


def test_cotizar_btc_llega_hasta_la_placa(cotiza_env):
    ctx = _FakeCtx()
    up_asset = _FakeUpdate(callback="act_btc")
    assert asyncio.run(telegram_bot.cotiza_asset(up_asset, ctx)) == telegram_bot.COTIZA_SIDE
    assert "BTC" in up_asset.callback_query.edits[0]

    up_side = _FakeUpdate(callback="compra")
    assert asyncio.run(telegram_bot.cotiza_side(up_side, ctx)) == telegram_bot.COTIZA_MARGIN

    up_margen = _FakeUpdate(text="3")
    asyncio.run(telegram_bot.cotiza_margin(up_margen, ctx))
    assert cotiza_env == [("compra", 3.0, "BTC")]


def test_cotizar_sin_elegir_activo_cotiza_usdt(cotiza_env):
    """Si el estado se pierde, el default de siempre; nunca un activo al azar."""
    ctx = _FakeCtx()
    ctx.user_data["cotiza_side"] = "venta"
    asyncio.run(telegram_bot.cotiza_margin(_FakeUpdate(text="2"), ctx))
    assert cotiza_env == [("venta", 2.0, "USDT")]


def test_registra_el_comando_de_cotizacion_directa(monkeypatch):
    """/btc y /usdt: la misma respuesta de las dos puntas, sin conversación."""
    from telegram.ext import CommandHandler
    app = _build_app(monkeypatch)
    nombres = {n for h in app.handlers if isinstance(h, CommandHandler)
               for n in h.commands}
    assert {"btc", "usdt"} <= nombres


def test_comando_btc_pide_la_cotizacion_de_btc(monkeypatch, cotiza_env):
    llamadas = []
    monkeypatch.setattr(telegram_bot, "cotizacion_text",
                        lambda url, asset="USDT", size=None, margen=None:
                        llamadas.append(asset) or "ok")
    update, ctx = _FakeUpdate(text="/btc"), _FakeCtx()
    asyncio.run(telegram_bot.cmd_btc(update, ctx))
    assert llamadas == ["BTC"]
    assert update.message.replies[0][0] == "ok"
