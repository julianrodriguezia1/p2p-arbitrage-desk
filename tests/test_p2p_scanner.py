import json
import p2p_scanner
from p2p_scanner import fetch_bitget, FETCHERS


class _Resp:
    def __init__(self, payload): self._p = payload
    def raise_for_status(self): pass
    def json(self): return self._p


def _bitget_payload(side):
    # side=1 -> avisos donde el maker VENDE (comprás); side=2 -> vendés.
    if side == 1:
        ads = [
            {"price": 1100, "amount": 26150, "minAmount": 22000, "maxAmount": 22000,
             "nickName": "Trampa", "turnoverNum": 1, "turnoverRate": 0.5, "paymethodInfo": []},
            {"price": 1546.88, "amount": 101.16, "minAmount": 7000, "maxAmount": 70574.9,
             "nickName": "MerchantUno", "turnoverNum": 582, "turnoverRate": 0.99,
             "paymethodInfo": [{"paymethodName": "Uala"}, {"paymethodName": "Naranja X"}]},
        ]
    else:
        ads = [
            {"price": 1544.25, "amount": 157266.63, "minAmount": 500000, "maxAmount": 700000,
             "nickName": "MerchantDos", "turnoverNum": 100, "turnoverRate": 0.98, "paymethodInfo": []},
        ]
    return {"code": "00000", "data": {"dataList": ads}}


def test_fetch_bitget_buy_y_sell(monkeypatch):
    captured = {}
    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["side"] = json["side"]
        return _Resp(_bitget_payload(json["side"]))
    monkeypatch.setattr(p2p_scanner.requests, "post", fake_post)

    buy = fetch_bitget("USDT", "ARS", "BUY", rows=10)
    assert captured["url"].endswith("/p2p/pub/adv/queryAdvList")
    assert captured["side"] == 1
    assert buy[0].exchange == "bitget" and buy[0].side == "BUY"
    # parsea precio/stock/min/max/merchant/órdenes/finish_rate/métodos
    greg = buy[1]
    assert greg.price == 1546.88 and greg.available == 101.16
    assert greg.min_amount == 7000 and greg.max_amount == 70574.9
    assert greg.merchant == "MerchantUno" and greg.orders == 582
    assert abs(greg.finish_rate - 0.99) < 1e-9
    assert "Uala" in greg.methods and "Naranja X" in greg.methods

    sell = fetch_bitget("USDT", "ARS", "SELL", rows=10)
    assert captured["side"] == 2
    assert sell[0].side == "SELL" and sell[0].price == 1544.25


def test_bitget_registrado_en_fetchers():
    assert FETCHERS.get("bitget") is fetch_bitget
