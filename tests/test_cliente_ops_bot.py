import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest

from bot import cliente_ops
from bot.cliente_ops import card_text, consultar_text, load_and_format, summary_text

MOV = {
    "side": "VENTA", "date": "2026-08-12", "order_id": "man-daniel-20260812",
    "usd_gross": "1000", "commission": "0", "usd_net": "1000",
    "price": "1578", "total_ars": "1578000.00",
    "exchange_coin": "OTC / USDT", "bank": "Uala",
}


class _Resp:
    def __init__(self, status, text=""):
        self.status_code = status
        self.text = text


class _Session:
    """Sesión falsa: devuelve lo que le digas para el POST y para el PUT."""

    def __init__(self, post=(201, ""), put=(200, ""), put_raises=False):
        self._post, self._put = post, put
        self._put_raises = put_raises
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json))
        return _Resp(*self._post)

    def put(self, url, json=None, timeout=None):
        self.calls.append(("PUT", url, json))
        if self._put_raises:
            raise ConnectionError("boom")
        return _Resp(*self._put)


def test_card_text_muestra_todo_lo_entendido():
    txt = card_text(MOV, "Daniel", [])
    assert "VENTA" in txt
    assert "Daniel" in txt
    assert "1000" in txt
    assert "1578" in txt
    assert "1578000.00" in txt
    assert "Uala" in txt
    assert "man-daniel-20260812" in txt
    assert "¿La cargo?" in txt


def test_card_text_de_una_compra_usa_el_verbo_correcto():
    txt = card_text({**MOV, "side": "COMPRA"}, "Pablo", [])
    assert "COMPRA" in txt
    assert "compraste" in txt.lower()


def test_card_text_marca_los_warnings():
    txt = card_text(MOV, "Daniel", ["mercado ahora ~1800"])
    assert "⚠️" in txt
    assert "1800" in txt


def test_carga_ok_hace_los_dos_llamados_en_orden():
    sess = _Session(post=(201, "{}"), put=(200, '{"updated":true}'))
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=sess)
    assert "✅" in msg
    assert "Daniel" in msg
    assert [c[0] for c in sess.calls] == ["POST", "PUT"]
    assert sess.calls[0][1] == "http://vps:8002/api/movement"
    assert sess.calls[0][2] == MOV
    assert sess.calls[1][1] == "http://vps:8002/api/movements/man-daniel-20260812/client"
    assert sess.calls[1][2] == {"client_id": 4}


def test_si_falla_el_linkeo_avisa_que_quedo_sin_dueno():
    sess = _Session(post=(201, "{}"), put=(500, "boom"))
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=sess)
    assert "✅" in msg              # la op SÍ quedó cargada
    assert "⚠️" in msg
    assert "no pude linkearla" in msg.lower()
    assert "dashboard" in msg.lower()


def test_si_el_linkeo_explota_tambien_avisa():
    sess = _Session(post=(201, "{}"), put_raises=True)
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=sess)
    assert "✅" in msg
    assert "no pude linkearla" in msg.lower()


def test_409_no_intenta_linkear():
    sess = _Session(post=(409, '{"detail":"Ya cargado"}'))
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=sess)
    assert "⚠️" in msg
    assert "ya estaba" in msg.lower()
    assert [c[0] for c in sess.calls] == ["POST"]


def test_422_muestra_el_detalle_del_vps():
    sess = _Session(post=(422, '{"detail":"Falta la pestaña \'Agosto\'"}'))
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=sess)
    assert "Agosto" in msg
    assert [c[0] for c in sess.calls] == ["POST"]


class _SessionCaida:
    def post(self, url, json=None, timeout=None):
        raise ConnectionError("boom")


def test_sin_red_deja_claro_que_no_se_cargo():
    msg = load_and_format(MOV, 4, "Daniel", "http://vps:8002", session=_SessionCaida())
    assert "❌" in msg
    assert "NO quedó cargada" in msg


def test_mov_sin_order_id_no_lanza_excepcion():
    """Si falta order_id, devuelve error sin explotar."""
    mov_incompleto = {**MOV}
    del mov_incompleto["order_id"]
    sess = _Session(post=(201, "{}"))
    msg = load_and_format(mov_incompleto, 4, "Daniel", "http://vps:8002", session=sess)
    assert isinstance(msg, str)
    assert "❌" in msg
    assert "incompleto" in msg.lower()


def test_mov_sin_usd_net_no_lanza_excepcion():
    """Si falta usd_net, devuelve error sin explotar."""
    mov_incompleto = {**MOV}
    del mov_incompleto["usd_net"]
    sess = _Session(post=(201, "{}"))
    msg = load_and_format(mov_incompleto, 4, "Daniel", "http://vps:8002", session=sess)
    assert isinstance(msg, str)
    assert "❌" in msg
    assert "incompleto" in msg.lower()


# --- prepare_op / market_price ---

HOY = date(2026, 8, 12)
CLIENTES = [{"id": 4, "name": "Daniel", "alias": ""},
            {"id": 9, "name": "Daniela", "alias": ""}]
DETALLE_DANIEL = {
    "client": {"id": 4, "name": "Daniel"},
    "movements": [{"opId": "man-daniel-20260810", "date": "2026-08-10",
                   "bank": "Uala", "type": "sell", "usdNeto": 1000.0,
                   "priceArs": 1583.0, "totalArs": 1583000.0}],
}
PARAMS = {"cliente": "Daniel", "lado": "vendi", "monto": 1000,
          "unidad": "usdt", "precio": 1578}


@pytest.fixture
def vps(monkeypatch):
    """Parchea los cuatro llamados al VPS y registra lo que se creó."""
    creados = []
    monkeypatch.setattr(cliente_ops, "list_clients", lambda url: CLIENTES)
    monkeypatch.setattr(cliente_ops, "get_client", lambda cid, url: DETALLE_DANIEL)
    monkeypatch.setattr(cliente_ops, "market_price", lambda side, url: None)

    def _create(name, url):
        creados.append(name)
        return {"id": 99, "name": name}

    monkeypatch.setattr(cliente_ops, "create_client", _create)
    return creados


def test_prepare_op_devuelve_la_tarjeta(vps):
    out = cliente_ops.prepare_op(PARAMS, "http://vps:8002", today=HOY)
    assert out["kind"] == "card"
    assert out["client"]["id"] == 4
    assert out["mov"]["order_id"] == "man-daniel-20260812"
    assert out["mov"]["bank"] == "Uala"
    assert "¿La cargo?" in out["text"]


def test_prepare_op_pide_lo_que_falta(vps):
    out = cliente_ops.prepare_op({**PARAMS, "precio": None}, "http://vps:8002", today=HOY)
    assert out["kind"] == "ask"
    assert out["missing"] == "precio"
    assert "precio" in out["text"].lower()
    assert out["params"]["cliente"] == "Daniel"


def test_prepare_op_ofrece_crear_al_cliente_desconocido(vps):
    out = cliente_ops.prepare_op({**PARAMS, "cliente": "Rodolfo"},
                                 "http://vps:8002", today=HOY)
    assert out["kind"] == "new_client"
    assert out["name"] == "Rodolfo"
    assert "Rodolfo" in out["text"]


def test_prepare_op_pide_elegir_si_hay_varios(vps):
    out = cliente_ops.prepare_op({**PARAMS, "cliente": "Dani"},
                                 "http://vps:8002", today=HOY)
    assert out["kind"] == "pick_client"
    assert {c["id"] for c in out["candidates"]} == {4, 9}


def test_prepare_op_sin_nombre_de_cliente_es_error(vps):
    out = cliente_ops.prepare_op({**PARAMS, "cliente": None},
                                 "http://vps:8002", today=HOY)
    assert out["kind"] == "error"


def test_prepare_op_con_el_vps_caido_es_error(monkeypatch):
    def _boom(url):
        raise ConnectionError("boom")

    monkeypatch.setattr(cliente_ops, "list_clients", _boom)
    out = cliente_ops.prepare_op(PARAMS, "http://vps:8002", today=HOY)
    assert out["kind"] == "error"
    assert "VPS" in out["text"]


def test_prepare_op_pega_el_aviso_de_mercado(monkeypatch, vps):
    monkeypatch.setattr(cliente_ops, "market_price", lambda side, url: 1800.0)
    out = cliente_ops.prepare_op(PARAMS, "http://vps:8002", today=HOY)
    assert out["kind"] == "card"
    assert "mercado" in out["text"]


def test_market_price_elige_la_punta_segun_el_lado(monkeypatch):
    payload = {"cheapest_buy": {"price": 1520.0}, "dearest_sell": {"price": 1583.0}}
    monkeypatch.setattr(cliente_ops, "fetch_json", lambda url, path: payload)
    assert cliente_ops.market_price("VENTA", "http://vps:8002") == 1583.0
    assert cliente_ops.market_price("COMPRA", "http://vps:8002") == 1520.0


def test_market_price_devuelve_none_si_falla(monkeypatch):
    def _boom(url, path):
        raise ConnectionError("boom")

    monkeypatch.setattr(cliente_ops, "fetch_json", _boom)
    assert cliente_ops.market_price("VENTA", "http://vps:8002") is None


# --- summary_text / consultar_text ---

MOVS = [
    {"opId": "a", "date": "2026-07-28", "type": "sell", "usdNeto": 1000.0,
     "priceArs": 1606.0, "totalArs": 1606000.0, "bank": "Uala"},
    {"opId": "b", "date": "2026-08-05", "type": "sell", "usdNeto": 1000.0,
     "priceArs": 1578.0, "totalArs": 1578000.0, "bank": "Uala"},
    {"opId": "c", "date": "2026-08-10", "type": "buy", "usdNeto": 500.0,
     "priceArs": 1540.0, "totalArs": 770000.0, "bank": "Uala"},
]


def test_summary_muestra_totales_y_la_ultima():
    # Ojo: _miles() formatea a la argentina, así que 1540.0 sale "1.540".
    txt = summary_text("Daniel", MOVS, HOY)
    assert "Daniel" in txt
    assert "3 op" in txt
    assert "2026-08-10" in txt      # la última por fecha
    assert "1.540" in txt
    assert "compraste" in txt       # la última fue una compra


def test_summary_separa_ventas_de_compras():
    txt = summary_text("Daniel", MOVS, HOY)
    assert "Le vendiste 2.000 USDT" in txt
    assert "Le compraste 500 USDT" in txt


def test_summary_del_mes_filtra_lo_de_julio():
    txt = summary_text("Daniel", MOVS, HOY, periodo="mes")
    assert "2026-08" in txt
    assert "2 op" in txt


def test_summary_sin_ops_lo_dice():
    assert "Sin operaciones" in summary_text("Rodolfo", [], HOY)


def test_summary_del_mes_sin_ops_lo_dice():
    viejas = [{"opId": "a", "date": "2026-01-05", "type": "sell", "usdNeto": 1.0,
               "priceArs": 1.0, "totalArs": 1.0}]
    assert "Sin operaciones" in summary_text("Daniel", viejas, HOY, periodo="mes")


def test_consultar_text_resuelve_y_resume(vps):
    txt = consultar_text({"cliente": "Daniel"}, "http://vps:8002", today=HOY)
    assert "Daniel" in txt
    assert "1.583" in txt           # el precio de su única op en el fixture


def test_consultar_text_cliente_desconocido(vps):
    txt = consultar_text({"cliente": "Rodolfo"}, "http://vps:8002", today=HOY)
    assert "Rodolfo" in txt
    assert "no" in txt.lower()


def test_consultar_text_ambiguo_lista_candidatos(vps):
    txt = consultar_text({"cliente": "Dani"}, "http://vps:8002", today=HOY)
    assert "Daniel" in txt and "Daniela" in txt


def test_consultar_text_sin_nombre():
    assert "cliente" in consultar_text({}, "http://vps:8002", today=HOY).lower()


def test_consultar_text_con_el_vps_caido(monkeypatch):
    def _boom(url):
        raise ConnectionError("boom")

    monkeypatch.setattr(cliente_ops, "list_clients", _boom)
    assert "❌" in consultar_text({"cliente": "Daniel"}, "http://vps:8002", today=HOY)


# --- handlers async: start_op / on_pending_op / on_callback ---

DETALLE_DANIELA = {"client": {"id": 9, "name": "Daniela"}, "movements": []}


class FakeMessage:
    """Mensaje de Telegram mínimo: solo lo que tocan los handlers."""

    def __init__(self):
        self.reply_text = AsyncMock()

    @property
    def ultimo_texto(self) -> str:
        return self.reply_text.call_args[0][0]


class FakeContext:
    def __init__(self):
        self.user_data = {}


class FakeQuery:
    def __init__(self, data, message):
        self.data = data
        self.message = message
        self.answer = AsyncMock()
        self.edit_message_text = AsyncMock()


class FakeUpdate:
    def __init__(self, query):
        self.callback_query = query


@pytest.fixture
def vps_handlers(monkeypatch):
    """Como `vps` pero con detalle por id (Daniel tiene historial, Daniela no)."""
    import config
    monkeypatch.setattr(config, "VPS_API_URL", "http://vps:8002", raising=False)
    monkeypatch.setattr(cliente_ops, "list_clients", lambda url: CLIENTES)
    detalles = {4: DETALLE_DANIEL, 9: DETALLE_DANIELA}
    monkeypatch.setattr(cliente_ops, "get_client",
                        lambda cid, url: detalles[int(cid)])
    monkeypatch.setattr(cliente_ops, "market_price", lambda side, url: None)
    monkeypatch.setattr(cliente_ops, "create_client",
                        lambda name, url: {"id": 99, "name": name})


def test_round_trip_elegir_cliente_y_responder_el_dato_llega_a_la_tarjeta(vps_handlers):
    """'Dani' ambiguo → elijo Daniela → contesto el banco → tarjeta.

    El bug era que el pick se perdía y volvía a preguntar '¿Cuál de todos?'."""
    msg, ctx = FakeMessage(), FakeContext()

    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "cliente": "Dani"}))
    assert "¿Cuál de todos?" in msg.ultimo_texto
    assert "pending_pick" in ctx.user_data

    q = FakeQuery("cliop_pick:9", msg)
    asyncio.run(cliente_ops.on_callback(FakeUpdate(q), ctx))
    # Daniela no tiene historial → no hay banco por defecto, lo pregunta.
    assert ctx.user_data["pending_op"]["missing"] == "banco"
    # Y el cliente ya resuelto queda pegado a los params por su nombre canónico.
    assert ctx.user_data["pending_op"]["params"]["cliente"] == "Daniela"
    assert "pending_pick" not in ctx.user_data

    consumido = asyncio.run(cliente_ops.on_pending_op(msg, ctx, "Uala"))
    assert consumido is True
    texto = msg.ultimo_texto
    assert "¿La cargo?" in texto           # llegó a la tarjeta
    assert "Daniela" in texto
    assert "Uala" in texto
    assert "¿Cuál de todos?" not in texto  # NO volvió a desambiguar
    assert "pending_op" not in ctx.user_data


def test_on_pending_op_con_texto_que_no_sirve_descarta_la_carga(vps_handlers):
    msg, ctx = FakeMessage(), FakeContext()
    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "precio": None}))
    assert ctx.user_data["pending_op"]["missing"] == "precio"

    consumido = asyncio.run(cliente_ops.on_pending_op(msg, ctx, "che, el spread"))
    assert consumido is False
    assert "pending_op" not in ctx.user_data


def test_un_flujo_nuevo_limpia_el_pendiente_viejo(vps_handlers):
    """Un botón viejo no puede actuar sobre el flujo equivocado."""
    msg, ctx = FakeMessage(), FakeContext()

    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "cliente": "Rodolfo"}))
    assert ctx.user_data["pending_new_client"]["name"] == "Rodolfo"

    # Sin contestar, arranca otra op: la oferta de crear a Rodolfo se cae.
    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "precio": None}))
    assert "pending_new_client" not in ctx.user_data
    assert ctx.user_data["pending_op"]["missing"] == "precio"

    # Tocar el botón viejo "✅ Crearlo" ya no crea a nadie.
    q = FakeQuery("cliop_new:si", msg)
    asyncio.run(cliente_ops.on_callback(FakeUpdate(q), ctx))
    assert "ya no está disponible" in q.edit_message_text.call_args[0][0]


def test_pick_viejo_no_sobrevive_a_un_flujo_nuevo(vps_handlers):
    msg, ctx = FakeMessage(), FakeContext()
    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "cliente": "Dani"}))
    assert "pending_pick" in ctx.user_data

    asyncio.run(cliente_ops.start_op(msg, ctx, {**PARAMS, "cliente": "Rodolfo"}))
    assert "pending_pick" not in ctx.user_data
    assert "pending_new_client" in ctx.user_data


def test_on_callback_ok_carga_y_avisa(vps_handlers, monkeypatch):
    monkeypatch.setattr(cliente_ops, "load_and_format",
                        lambda mov, cid, name, url: f"✅ Cargada en {name}")
    msg, ctx = FakeMessage(), FakeContext()
    asyncio.run(cliente_ops.start_op(msg, ctx, PARAMS))
    token = next(iter(ctx.user_data["client_ops"]))

    q = FakeQuery(f"cliop_ok:{token}", msg)
    asyncio.run(cliente_ops.on_callback(FakeUpdate(q), ctx))
    assert q.edit_message_text.call_args[0][0] == "✅ Cargada en Daniel"
    assert token not in ctx.user_data["client_ops"]
