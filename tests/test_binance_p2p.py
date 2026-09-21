import hashlib
import hmac
import time
from datetime import date
from decimal import Decimal
from core.movements import Side, Source
from core.binance_p2p import sign, order_to_movement

# createTime para 2026-06-01 ~15:34 hora Argentina (UTC-3) = 18:34 UTC
ORDER_BUY = {
    "orderNumber": "22894833143631372288",
    "tradeType": "BUY",
    "asset": "USDT",
    "fiat": "ARS",
    "amount": "16.92",
    "commission": "0.07",
    "unitPrice": "1477",
    "totalPrice": "25000",
    "payMethodName": "Lemon Cash",
    "orderStatus": "COMPLETED",
    "createTime": 1780338840000,
}


def test_sign_es_hmac_sha256_hex():
    expected = hmac.new(b"secret", b"a=1&b=2", hashlib.sha256).hexdigest()
    assert sign("a=1&b=2", "secret") == expected
    assert len(sign("a=1&b=2", "secret")) == 64


def test_order_to_movement_mapea_compra():
    m = order_to_movement(ORDER_BUY)
    assert m.side == Side.COMPRA
    assert m.order_id == "22894833143631372288"
    assert m.usd_gross == Decimal("16.92")
    assert m.commission == Decimal("0.07")
    assert m.usd_net == Decimal("16.85")
    assert m.price == Decimal("1477")
    assert m.total_ars == Decimal("25000")
    assert m.exchange_coin == "Binance / USDT"
    assert m.bank == "Lemon Cash"
    assert m.source == Source.BINANCE_API
    assert m.date == date(2026, 6, 1)


def test_order_to_movement_sell_es_venta():
    raw = dict(ORDER_BUY, tradeType="SELL")
    assert order_to_movement(raw).side == Side.VENTA


def test_order_to_movement_usa_taker_commission_si_commission_es_cero():
    # Binance a veces pone la comision en takerCommission y deja commission en 0.
    raw = dict(ORDER_BUY, commission="0", takerCommission="0.07")
    m = order_to_movement(raw)
    assert m.commission == Decimal("0.07")
    assert m.usd_net == Decimal("16.85")


def test_fetch_orders_firma_y_parsea_data():
    captured = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [ORDER_BUY], "success": True}

    class FakeSession:
        def get(self, url, headers=None):
            captured["url"] = url
            captured["headers"] = headers
            return FakeResp()

    from core.binance_p2p import BinanceP2PClient
    client = BinanceP2PClient("KEY", "SECRET", session=FakeSession())
    data = client.fetch_orders("BUY")

    assert data == [ORDER_BUY]
    assert "signature=" in captured["url"]
    assert "tradeType=BUY" in captured["url"]
    assert captured["headers"]["X-MBX-APIKEY"] == "KEY"


def test_timestamp_se_ajusta_al_server_time_de_binance():
    # El reloj local adelantado +5000ms debe corregirse con el server time.
    from core.binance_p2p import BinanceP2PClient, TIME_PATH

    class FakeResp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    class FakeSession:
        def __init__(self):
            self.calls = []

        def get(self, url, headers=None):
            self.calls.append(url)
            if TIME_PATH in url:
                # Server "atrasado" 5s respecto al reloj local.
                return FakeResp({"serverTime": int(time.time() * 1000) - 5000})
            return FakeResp({"data": [ORDER_BUY]})

    client = BinanceP2PClient("KEY", "SECRET", session=FakeSession())
    ts = client._timestamp()
    # Debe quedar ~5s por debajo del reloj local (tolerancia por latencia).
    assert -5200 < ts - int(time.time() * 1000) < -4800
    # El offset se cachea: una segunda llamada no vuelve a pegarle a /time.
    assert client._time_offset_ms is not None


def _fake_client(paginas):
    """Cliente con una sesión falsa que va devolviendo `paginas` en orden."""
    from core.binance_p2p import BinanceP2PClient

    urls = []

    class FakeResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return {"data": self._data, "success": True}

    class FakeSession:
        def get(self, url, headers=None):
            urls.append(url)
            if "/time" in url:
                return FakeResp(None) if False else _TimeResp()
            return FakeResp(paginas.pop(0) if paginas else [])

    class _TimeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"serverTime": 1_788_000_000_000}

    return BinanceP2PClient("KEY", "SECRET", session=FakeSession()), urls


def test_fetch_orders_acepta_rango_de_fechas():
    """Sin rango, Binance devuelve SOLO los últimos 30 días: por eso hay que
    poder pedirle una ventana explícita (medido el 2026-08-30)."""
    from datetime import date

    client, urls = _fake_client([[ORDER_BUY]])
    client.fetch_orders("BUY", start=date(2026, 6, 18), end=date(2026, 7, 13))

    url = [u for u in urls if "tradeType" in u][0]
    assert "startTimestamp=" in url and "endTimestamp=" in url


def test_fetch_orders_range_pagina_y_parte_la_ventana():
    """Binance no acepta ventanas de más de 30 días y pagina de a 50."""
    from datetime import date

    llena = [dict(ORDER_BUY, orderNumber=str(i)) for i in range(50)]
    resto = [dict(ORDER_BUY, orderNumber="500")]
    client, urls = _fake_client([llena, resto, [], []])
    data = client.fetch_orders_range("BUY", date(2026, 6, 1), date(2026, 8, 1))

    pedidos = [u for u in urls if "tradeType" in u]
    assert len(pedidos) > 2                      # partió la ventana y paginó
    assert all("startTimestamp=" in u for u in pedidos)
    assert len(data) == 51                       # juntó las dos páginas
    assert len({o["orderNumber"] for o in data}) == 51    # sin repetidos
