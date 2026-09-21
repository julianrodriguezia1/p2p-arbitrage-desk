from datetime import date
from decimal import Decimal
from core.movements import Side, Source
from cli.add_movement import movement_from_json


def test_movement_from_json_completo():
    d = {
        "side": "VENTA", "date": "2026-06-01", "order_id": "777",
        "usd_gross": "100", "commission": "0.1", "usd_net": "99.9",
        "price": "1480", "total_ars": "148000",
        "exchange_coin": "OKX / USDT", "bank": "Galicia",
    }
    m = movement_from_json(d)
    assert m.side == Side.VENTA
    assert m.date == date(2026, 6, 1)
    assert m.usd_net == Decimal("99.9")
    assert m.exchange_coin == "OKX / USDT"
    assert m.source == Source.SCREENSHOT


def test_movement_from_json_calcula_usd_net_si_falta():
    d = {
        "side": "COMPRA", "date": "2026-06-01", "order_id": "888",
        "usd_gross": "16.92", "commission": "0.07",
        "price": "1477", "total_ars": "25000",
        "exchange_coin": "Bybit / USDT", "bank": "Belo",
    }
    assert movement_from_json(d).usd_net == Decimal("16.85")
