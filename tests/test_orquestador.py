import asyncio
from unittest.mock import AsyncMock

import pytest

from bot import orquestador
from bot.captura import resolve_exchange
from bot.orquestador import cotizar_params, dispatch, help_text


def test_help_text_lista_lo_que_sabe_hacer():
    txt = help_text().lower()
    for kw in ("spread", "precio", "stock", "estrategia", "billeteras",
               "actualizar", "captura", "cotiz"):
        assert kw in txt


def test_dispatch_desconocido_devuelve_ayuda():
    assert dispatch("cualquier_cosa") == help_text()
    assert dispatch("ayuda") == help_text()


def test_dispatch_rutea_a_cada_funcion(monkeypatch):
    import config
    monkeypatch.setattr(config, "DASHBOARD_URL", "http://vps:8002", raising=False)
    llamadas = {}

    def fake(name):
        def _f(url):
            llamadas[name] = url
            return f"[{name}]"
        return _f

    monkeypatch.setattr(orquestador, "spread_text", fake("spread"))
    monkeypatch.setattr(orquestador, "stock_text", fake("stock"))
    monkeypatch.setattr(orquestador, "estrategia_text", fake("estrategia"))
    monkeypatch.setattr(orquestador, "billeteras_text", fake("billeteras"))

    # "precio" ya no está: pasó a contestar el ranking (ver el test de abajo).
    for action in ("spread", "stock", "estrategia", "billeteras"):
        assert dispatch(action) == f"[{action}]"
        assert llamadas[action] == "http://vps:8002"


def test_dispatch_actualizar_usa_el_bridge(monkeypatch):
    import config
    monkeypatch.setattr(config, "SYNC_BRIDGE_URL", "http://pc:8765/sync", raising=False)
    monkeypatch.setattr(config, "SYNC_BRIDGE_TOKEN", "TOK", raising=False)
    import bot.bridge_client as bc
    monkeypatch.setattr(bc, "actualizar_text", lambda url, tok: f"sync {url} {tok}")
    assert dispatch("actualizar") == "sync http://pc:8765/sync TOK"


# --- round-trip de captura: el usuario aclara el exchange por texto ---

def test_resolve_exchange_reconstruye_bybit_desde_ambiguo():
    raw = {"exchange": "Banco Galicia", "side": "compra", "cantidad_usdt": "150",
           "precio": "1556.50", "monto_ars": "233475", "comision": "0",
           "order_id": "X", "date": "2026-07-22", "bank": "MercadoPago"}
    mov, warnings, ambiguo = resolve_exchange(raw, "Bybit")
    assert ambiguo is False
    assert mov["exchange_coin"] == "Bybit / USDT"
    assert mov["usd_gross"] == "150"


def test_resolve_exchange_aplica_mana_lemon():
    # Venía como "?" (o Lemon Cash método de pago). El usuario aclara "Lemon"
    # y trae los campos de un intercambio real → se aplica el ÷0,99.
    raw = {"exchange": "Banco X", "side": "compra", "cambio_por": "95013.02",
           "cotizacion": "1471", "cantidad_usdt": "64.590770",
           "lemon_screen": "total", "order_id": "LM-7", "date": "2026-07-08",
           "bank": "Lemon"}
    mov, warnings, ambiguo = resolve_exchange(raw, "Lemon")
    assert ambiguo is False
    assert mov["exchange_coin"] == "Lemon / USDT"
    assert mov["total_ars"] == "95972.75"


def test_resolve_exchange_sigue_ambiguo_si_no_reconoce():
    raw = {"exchange": "?", "side": "compra", "cantidad_usdt": "100",
           "precio": "1500", "monto_ars": "150000", "comision": "0"}
    mov, warnings, ambiguo = resolve_exchange(raw, "Rappi")
    assert ambiguo is True


def test_help_text_menciona_las_capacidades_nuevas():
    txt = help_text().lower()
    for kw in ("cliente", "cotiz"):
        assert kw in txt


# --- cotizar_params ---

@pytest.mark.parametrize("crudo,esperado", [
    ("compra", "compra"), ("Compra", "compra"), ("venta", "venta"),
    ("VENTA", "venta"),
])
def test_cotizar_params_normaliza_el_lado(crudo, esperado):
    lado, _, _ = cotizar_params({"lado_cliente": crudo})
    assert lado == esperado


@pytest.mark.parametrize("crudo", [None, "", "cualquiera"])
def test_cotizar_params_lado_ilegible(crudo):
    lado, _, _ = cotizar_params({"lado_cliente": crudo})
    assert lado is None


@pytest.mark.parametrize("crudo,esperado", [
    (2, 2.0), ("2", 2.0), ("1,5", 1.5), ("2%", 2.0),
])
def test_cotizar_params_normaliza_el_margen(crudo, esperado):
    _, margen, _ = cotizar_params({"lado_cliente": "compra", "margen": crudo})
    assert margen == esperado


@pytest.mark.parametrize("crudo", [None, "", "ni idea", 0, -1])
def test_cotizar_params_margen_invalido_es_none(crudo):
    _, margen, _ = cotizar_params({"lado_cliente": "compra", "margen": crudo})
    assert margen is None


@pytest.mark.parametrize("crudo", ["10001578", 101, "500%"])
def test_cotizar_params_margen_absurdo_es_none(crudo):
    """Circuit breaker: un margen de cotización no pasa del 100%."""
    _, margen, _ = cotizar_params({"lado_cliente": "compra", "margen": crudo})
    assert margen is None


def test_cotizar_params_acepta_el_margen_del_techo():
    _, margen, _ = cotizar_params({"lado_cliente": "compra", "margen": 100})
    assert margen == 100.0


# --- on_text: ruteo real ---

class FakeMessage:
    def __init__(self, text):
        self.text = text
        self.reply_text = AsyncMock()
        self.reply_photo = AsyncMock()


class FakeContext:
    def __init__(self):
        self.user_data = {}


class FakeUpdate:
    def __init__(self, text):
        self.message = FakeMessage(text)


@pytest.fixture
def on_text_env(monkeypatch):
    """Autoriza el chat y deja fijar qué devuelve classify()."""
    import config
    monkeypatch.setattr(config, "VPS_API_URL", "http://vps:8002", raising=False)
    monkeypatch.setattr(config, "DASHBOARD_URL", "http://vps:8002", raising=False)
    monkeypatch.setattr(orquestador, "_authorized", lambda update: True)

    estado = {"clasificado": [], "ops": [], "placas": [], "cotizaciones": []}

    def _classify(text):
        estado["clasificado"].append(text)
        return estado["result"]

    async def _start_op(message, context, params):
        estado["ops"].append(params)

    def _placa(url, lado, margen, activo="USDT"):
        estado["placas"].append((lado, margen, activo))
        return None, "placa"

    monkeypatch.setattr(orquestador, "classify", _classify)
    monkeypatch.setattr(orquestador, "start_op", _start_op)
    def _texto(url, asset="USDT", size=None, margen=None):
        estado["cotizaciones"].append((asset, size, margen))
        return "cotización"

    monkeypatch.setattr("bot.commands.cotizacion_placa", _placa)
    monkeypatch.setattr("bot.commands.cotizacion_text", _texto)
    return estado


def test_pending_cotiza_no_se_traga_una_carga_de_op(on_text_env):
    """Con una cotización a medias, un mensaje de op se re-clasifica.

    El bug era que parse_amount le sacaba los no-dígitos y mandaba una placa
    con 10.001.578% de margen, perdiendo la venta en silencio."""
    on_text_env["result"] = {"action": "registrar_op_cliente",
                             "params": {"cliente": "Daniel", "monto": 1000}}
    update, ctx = FakeUpdate("le vendí 1000 a Daniel a 1578"), FakeContext()
    ctx.user_data["pending_cotiza"] = {"lado": "compra", "activo": "USDT"}

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["placas"] == []                 # ninguna placa absurda
    assert "pending_cotiza" not in ctx.user_data       # se descartó
    assert on_text_env["clasificado"] == ["le vendí 1000 a Daniel a 1578"]
    assert on_text_env["ops"] == [{"cliente": "Daniel", "monto": 1000}]
    update.message.reply_photo.assert_not_called()


def test_pending_cotiza_con_margen_valido_manda_la_placa(on_text_env):
    on_text_env["result"] = {"action": "ayuda", "params": {}}
    update, ctx = FakeUpdate("2"), FakeContext()
    ctx.user_data["pending_cotiza"] = {"lado": "venta", "activo": "USDT"}

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["placas"] == [("venta", 2.0, "USDT")]
    assert on_text_env["clasificado"] == []            # no se re-clasificó
    assert "pending_cotiza" not in ctx.user_data


def test_on_text_rutea_una_op_de_cliente(on_text_env):
    on_text_env["result"] = {"action": "registrar_op_cliente",
                             "params": {"cliente": "Daniel"}}
    update, ctx = FakeUpdate("le vendí 1000 a Daniel a 1578"), FakeContext()
    asyncio.run(orquestador.on_text(update, ctx))
    assert on_text_env["ops"] == [{"cliente": "Daniel"}]


def test_on_text_ignora_al_no_autorizado(monkeypatch, on_text_env):
    monkeypatch.setattr(orquestador, "_authorized", lambda update: False)
    update, ctx = FakeUpdate("hola"), FakeContext()
    asyncio.run(orquestador.on_text(update, ctx))
    update.message.reply_text.assert_not_called()
    assert on_text_env["clasificado"] == []


# --- activo (USDT / BTC) en criollo ---

@pytest.mark.parametrize("crudo,esperado", [
    ("btc", "BTC"), ("BTC", "BTC"), ("bitcoin", "BTC"),
    (None, "USDT"), ("usdt", "USDT"), ("cualquiera", "USDT"),
])
def test_cotizar_params_normaliza_el_activo(crudo, esperado):
    *_, activo = cotizar_params({"lado_cliente": "compra", "activo": crudo})
    assert activo == esperado


def test_cotizar_flow_manda_la_placa_del_activo_pedido(on_text_env):
    on_text_env["result"] = {"action": "cotizar",
                             "params": {"lado_cliente": "compra", "margen": 3,
                                        "activo": "bitcoin"}}
    update, ctx = FakeUpdate("a cuánto le vendo bitcoin con 3 de ganancia"), FakeContext()

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["placas"] == [("compra", 3.0, "BTC")]


def test_cotizar_sin_margen_recuerda_el_activo(on_text_env):
    """El bug a evitar: preguntar el margen y volver cotizando USDT."""
    on_text_env["result"] = {"action": "cotizar",
                             "params": {"lado_cliente": "venta", "activo": "btc"}}
    update, ctx = FakeUpdate("a cuánto le compro btc"), FakeContext()

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["placas"] == []
    assert ctx.user_data["pending_cotiza"] == {"lado": "venta", "activo": "BTC"}


def test_pending_cotiza_con_activo_cotiza_ese_activo(on_text_env):
    on_text_env["result"] = {"action": "ayuda", "params": {}}
    update, ctx = FakeUpdate("2"), FakeContext()
    ctx.user_data["pending_cotiza"] = {"lado": "venta", "activo": "BTC"}

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["placas"] == [("venta", 2.0, "BTC")]
    assert "pending_cotiza" not in ctx.user_data


# --- cotizar sin preguntas: las dos puntas de una ---

def test_cotizar_sin_lado_responde_las_dos_puntas_sin_preguntar(on_text_env):
    """El pedido explícito del usuario: 'yo pongo cotizar BTC y que no me
    pregunte nada'. Antes preguntaba lado y margen."""
    on_text_env["result"] = {"action": "cotizar", "params": {"activo": "btc"}}
    update, ctx = FakeUpdate("cotizar BTC"), FakeContext()

    asyncio.run(orquestador.on_text(update, ctx))

    assert on_text_env["cotizaciones"] == [("BTC", None, None)]
    assert on_text_env["placas"] == []                  # no manda placa
    assert "pending_cotiza" not in ctx.user_data        # no queda esperando nada
    update.message.reply_text.assert_called_once()


def test_cotizar_a_secas_es_usdt(on_text_env):
    on_text_env["result"] = {"action": "cotizar", "params": {}}
    asyncio.run(orquestador.on_text(FakeUpdate("cotizar"), FakeContext()))
    assert on_text_env["cotizaciones"] == [("USDT", None, None)]


def test_cotizar_toma_el_monto_y_el_margen_si_los_decis(on_text_env):
    on_text_env["result"] = {"action": "cotizar",
                             "params": {"activo": "btc", "monto": "0.05",
                                        "margen": "2"}}
    asyncio.run(orquestador.on_text(FakeUpdate("cotizar 0.05 btc al 2"), FakeContext()))
    assert on_text_env["cotizaciones"] == [("BTC", 0.05, 2.0)]


def test_cotizar_con_lado_explicito_sigue_mandando_la_placa(on_text_env):
    """No se pierde lo que ya funcionaba: si dice el lado, va la placa."""
    on_text_env["result"] = {"action": "cotizar",
                             "params": {"lado_cliente": "compra", "margen": 3,
                                        "activo": "btc"}}
    asyncio.run(orquestador.on_text(FakeUpdate("a cuánto le vendo btc al 3"),
                                    FakeContext()))
    assert on_text_env["placas"] == [("compra", 3.0, "BTC")]
    assert on_text_env["cotizaciones"] == []


# ── Fallo de infraestructura: no mostrar el menú de ayuda ──────────────────

def test_dispatch_fallo_de_infra_no_muestra_el_menu():
    """Si NVIDIA no contestó, el bot no entendió NADA — ni siquiera llegó a
    intentarlo. Mostrar el menú de comandos ahí es lo que hace creer que no
    entiende lenguaje natural y empuja a usar las barras."""
    from bot.orquestador import dispatch, help_text

    out = dispatch("ayuda", error="infra")
    assert out != help_text()
    assert "de nuevo" in out.lower() or "repetí" in out.lower()


def test_dispatch_ayuda_genuina_sigue_mostrando_el_menu():
    """El modelo contestó y no era ninguna acción conocida: ahí sí va el menú."""
    from bot.orquestador import dispatch, help_text

    assert dispatch("ayuda") == help_text()
    assert dispatch("ayuda", error=None) == help_text()


def test_dispatch_donde_y_precio_dan_el_mismo_ranking(monkeypatch):
    """'precio' pasaba a contestar sólo a qué publicar en Binance. Ahora las dos
    dan el ranking entre venues con las dos modalidades."""
    import bot.orquestador as o

    monkeypatch.setattr("bot.commands.donde_text",
                        lambda base, **kw: f"[donde {kw.get('lado')}]")
    assert o.dispatch("donde") == "[donde ambos]"
    assert o.dispatch("precio") == "[donde ambos]"


def test_dispatch_donde_pasa_el_lado_y_el_monto(monkeypatch):
    import bot.orquestador as o

    visto = {}

    def fake(base, **kw):
        visto.update(kw)
        return "ok"
    monkeypatch.setattr("bot.commands.donde_text", fake)
    o.dispatch("donde", params={"lado": "compro", "monto": 500, "activo": "btc"})
    assert visto["lado"] == "compro"
    assert visto["monto"] == 500
    assert visto["asset"] == "BTC"


# ── "binance" a secas: la jugada que suma para el Verificado ───────────────

def test_dispatch_binance_pide_la_jugada_por_binance(monkeypatch):
    import config
    monkeypatch.setattr(config, "DASHBOARD_URL", "http://vps:8002", raising=False)
    monkeypatch.setattr(orquestador, "binance_text", lambda url: f"[binance {url}]")
    assert dispatch("binance") == "[binance http://vps:8002]"


def test_help_text_nombra_las_palabras_sueltas():
    """El menú tiene que enseñar que se escriben sin barra."""
    txt = help_text().lower()
    assert "oportunidad" in txt and "binance" in txt
