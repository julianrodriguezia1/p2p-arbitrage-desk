import p2p_scanner


# Payload fake adaptado al esquema REAL de la API KuCoin (confirmado probe 2026-07-02):
# - items a raiz del JSON (no bajo "data")
# - precio: "floatPrice" (no "price")
# - metodos: "payTypeNameEn" (no "payTypeName")
# - ordenes: "dealOrderNum" como STRING (no int)
# - finish_rate: "dealOrderRate" como string "99.52%" (no float 0-1)
_FAKE = {
    "success": True,
    "code": "200",
    "items": [
        {
            "floatPrice": "1570.5",
            "limitMinQuote": "10000",
            "limitMaxQuote": "500000",
            "currencyQuantity": "1234.5",
            "nickName": "trader1",
            "adPayTypes": [{"payTypeNameEn": "Mercado Pago"}],
            "dealOrderNum": "320",
            "dealOrderRate": "98.00%",
        },
        {
            "floatPrice": "1571.0",
            "limitMinQuote": "5000",
            "limitMaxQuote": "200000",
            "currencyQuantity": "88.0",
            "nickName": "trader2",
            "adPayTypes": [{"payTypeNameEn": "Uala"}],
            "dealOrderNum": "12",
            "dealOrderRate": "100.00%",
        },
    ],
}


def test_fetch_kucoin_parsea_avisos(monkeypatch):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return _FAKE

    def fake_get(url, **kw):
        assert "kucoin.com/_api/otc/ad/list" in url
        # comprar USDT -> side=SELL (el maker vende)
        assert kw["params"]["side"] == "SELL"
        assert kw["params"]["currency"] == "USDT"
        assert kw["params"]["legal"] == "ARS"
        return _Resp()

    monkeypatch.setattr(p2p_scanner.requests, "get", fake_get)
    ads = p2p_scanner.fetch_kucoin("USDT", "ARS", "BUY", rows=20)
    assert len(ads) == 2
    a = ads[0]
    assert a.exchange == "kucoin" and a.side == "BUY"
    assert a.price == 1570.5
    assert a.min_amount == 10000.0 and a.max_amount == 500000.0
    assert a.available == 1234.5
    assert a.merchant == "trader1"
    assert a.methods == ["Mercado Pago"]
    assert a.orders == 320
    assert abs(a.finish_rate - 0.98) < 1e-9


def test_fetch_kucoin_sell_side(monkeypatch):
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"success": True, "items": []}

    def fake_get(url, **kw):
        # vender USDT -> side=BUY (el maker compra)
        assert kw["params"]["side"] == "BUY"
        return _Resp()

    monkeypatch.setattr(p2p_scanner.requests, "get", fake_get)
    ads = p2p_scanner.fetch_kucoin("USDT", "ARS", "SELL", rows=20)
    assert ads == []


def test_fetch_kucoin_registrado_en_fetchers():
    assert p2p_scanner.FETCHERS["kucoin"] is p2p_scanner.fetch_kucoin
