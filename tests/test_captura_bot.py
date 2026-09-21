from bot.captura import card_text, push_and_format


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeSession:
    def __init__(self, status, text):
        self._status, self._text = status, text
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append((url, json))
        return _FakeResp(self._status, self._text)


MOV = {
    "side": "COMPRA", "date": "2026-07-08", "order_id": "BYB-1",
    "usd_gross": "150", "commission": "0", "usd_net": "150",
    "price": "1556.50", "total_ars": "233475", "exchange_coin": "Bybit / USDT",
    "bank": "MercadoPago",
}


def test_card_text_muestra_lo_entendido():
    txt = card_text(MOV, [])
    assert "COMPRA" in txt
    assert "Bybit / USDT" in txt
    assert "233475" in txt
    assert "1556.50" in txt
    assert "150" in txt


def test_card_text_marca_warnings():
    txt = card_text(MOV, ["Las cuentas no cierran: revisá."])
    assert "⚠️" in txt
    assert "no cierran" in txt


def test_push_and_format_201_cargada():
    sess = _FakeSession(201, '{"order_id":"BYB-1"}')
    msg = push_and_format(MOV, "http://vps:8002", session=sess)
    assert "✅" in msg
    assert sess.calls[0][0] == "http://vps:8002/api/movement"
    assert sess.calls[0][1] == MOV


def test_push_and_format_409_ya_estaba():
    sess = _FakeSession(409, '{"detail":"Ya cargado #BYB-1"}')
    msg = push_and_format(MOV, "http://vps:8002", session=sess)
    assert "⚠️" in msg
    assert "ya estaba" in msg.lower()


def test_push_and_format_422_muestra_detalle():
    sess = _FakeSession(422, '{"detail":"Falta la pestaña \'Julio\'"}')
    msg = push_and_format(MOV, "http://vps:8002", session=sess)
    assert "Julio" in msg


class _FakeSessionRaises:
    def post(self, url, json=None, timeout=None):
        raise ConnectionError("boom")


def test_push_and_format_network_error_no_queda_ambiguo():
    sess = _FakeSessionRaises()
    msg = push_and_format(MOV, "http://vps:8002", session=sess)
    assert "No pude contactar el VPS" in msg
    assert "NO quedó cargada" in msg


def test_on_photo_loguea_el_motivo_cuando_no_puede_leer(monkeypatch, caplog):
    """El fallo de lectura tiene que quedar en el journal. Sin esto, el modelo
    de visión de NVIDIA estuvo 8 días devolviendo 410 (retirado el 26/08/2026)
    y el bot sólo decía 'no pude leer', sin rastro en los logs."""
    import asyncio
    import logging

    import bot.captura as cap

    monkeypatch.setattr(cap, "_authorized", lambda update: True)

    def lector_roto(image_bytes):
        raise RuntimeError("410 Gone: el modelo ya no existe")

    monkeypatch.setattr(cap, "extract_fields", lector_roto)

    respuestas = []

    class _Foto:
        async def get_file(self):
            class _F:
                async def download_as_bytearray(self):
                    return bytearray(b"img")
            return _F()

    class _Msg:
        photo = [_Foto()]

        async def reply_text(self, text, **kw):
            respuestas.append(text)

    class _Update:
        message = _Msg()

    with caplog.at_level(logging.WARNING):
        asyncio.run(cap.on_photo(_Update(), object()))

    assert any("No pude leer" in r for r in respuestas)
    assert "410 Gone" in caplog.text
