from cli.sync_bybit import _fetch_all


class _FakeClient:
    def __init__(self, orders):
        self._orders = orders

    def fetch_all_orders(self):
        return self._orders


def _raw(oid, status):
    return {
        "id": oid, "side": 0, "tokenId": "USDT", "notifyTokenQuantity": "10",
        "fee": "0", "price": "1500", "amount": "15000", "currencyId": "ARS",
        "status": status, "createDate": 1781731080000, "paymentType": [],
    }


def test_fetch_all_solo_completadas_status_50():
    movs = _fetch_all(_FakeClient([_raw("a", 50), _raw("b", 40), _raw("c", 50)]))
    assert [m.order_id for m in movs] == ["a", "c"]


def test_fetch_all_mapea_a_movement():
    movs = _fetch_all(_FakeClient([_raw("x", 50)]))
    assert movs[0].exchange_coin == "Bybit / USDT"
    assert str(movs[0].usd_gross) == "10"
