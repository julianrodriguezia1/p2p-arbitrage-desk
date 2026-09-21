import hashlib
import hmac
from datetime import date
from decimal import Decimal

from core.movements import Side, Source
from core.bybit_p2p import sign_v5, order_to_movement

# createDate 1781731080000 = 2026-06-17 en hora Argentina (UTC-3)
ORDER = {
    "id": "2067320919276302336",
    "side": 0,
    "tokenId": "USDT",
    "notifyTokenQuantity": "333.3333",
    "fee": "0",
    "price": "1500.00",
    "amount": "500000.00",
    "currencyId": "ARS",
    "status": 50,
    "createDate": 1781731080000,
    "paymentType": [],
}


def test_sign_v5_es_hmac_sha256_hex():
    expected = hmac.new(b"SECRET", b"1700000000000KEY5000{\"page\":1,\"size\":30}",
                        hashlib.sha256).hexdigest()
    got = sign_v5("1700000000000", "KEY", "5000", '{"page":1,"size":30}', "SECRET")
    assert got == expected
    assert got == "5ecb378a7a3af4b7998c4e4da8f45145e78d50aed4eb02dc5969e4417c332cc5"
    assert len(got) == 64


def test_order_to_movement_mapea_compra():
    m = order_to_movement(ORDER)
    assert m.side == Side.COMPRA
    assert m.order_id == "2067320919276302336"
    assert m.usd_gross == Decimal("333.3333")
    assert m.commission == Decimal("0")
    assert m.usd_net == Decimal("333.3333")
    assert m.price == Decimal("1500.00")
    assert m.total_ars == Decimal("500000.00")
    assert m.exchange_coin == "Bybit / USDT"
    assert m.bank == ""
    assert m.source == Source.BYBIT_API
    assert m.date == date(2026, 6, 17)


def test_order_to_movement_side_1_es_venta():
    m = order_to_movement(dict(ORDER, side=1))
    assert m.side == Side.VENTA


def test_order_to_movement_paymentType_no_vacio():
    m = order_to_movement(dict(ORDER, paymentType=["Mercadopago"]))
    assert m.bank == "Mercadopago"


class _FakeResp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


class _FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def post(self, url, data=None, headers=None):
        self.calls.append((url, data, headers))
        return _FakeResp(self.pages.pop(0))


def test_signed_post_manda_headers_de_firma():
    sess = _FakeSession([{"result": {"count": 0, "items": []}}])
    from core.bybit_p2p import BybitP2PClient
    BybitP2PClient("KEY", "SECRET", session=sess).fetch_orders()
    _, data, headers = sess.calls[0]
    assert headers["X-BAPI-API-KEY"] == "KEY"
    assert len(headers["X-BAPI-SIGN"]) == 64
    assert headers["X-BAPI-TIMESTAMP"]
    assert headers["X-BAPI-RECV-WINDOW"] == "5000"


def test_fetch_all_orders_recorre_paginas():
    pages = [
        {"result": {"count": 3, "items": [{"id": "1"}, {"id": "2"}]}},
        {"result": {"count": 3, "items": [{"id": "3"}]}},
    ]
    from core.bybit_p2p import BybitP2PClient
    out = BybitP2PClient("KEY", "SECRET", session=_FakeSession(pages)).fetch_all_orders(size=2)
    assert [o["id"] for o in out] == ["1", "2", "3"]
