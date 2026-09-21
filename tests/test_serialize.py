from datetime import date
from decimal import Decimal

from core.movements import Movement, Side, Source
from webapp.serialize import movement_to_dashboard, dashboard_to_movement


def make_movement(order_id="123"):
    return Movement(
        side=Side.COMPRA, date=date(2026, 6, 1), order_id=order_id,
        usd_gross=Decimal("100"), commission=Decimal("0.16"),
        usd_net=Decimal("99.84"), price=Decimal("1477"),
        total_ars=Decimal("147700"), exchange_coin="Binance / USDT",
        bank="Lemon Cash", source=Source.BINANCE_API,
    )


def test_movement_to_dashboard_mapea_campos():
    d = movement_to_dashboard(make_movement("abc"))
    assert d["id"] == "abc"
    assert d["opId"] == "abc"
    assert d["type"] == "buy"
    assert d["usdBruto"] == 100.0
    assert d["priceArs"] == 1477.0
    assert d["totalArs"] == 147700.0
    assert d["exchange"] == "Binance / USDT"
    assert d["bank"] == "Lemon Cash"
    assert d["source"] == "binance_api"
    # commPct = 0.16/100*100 = 0.16
    assert round(d["commPct"], 4) == 0.16
    assert round(d["usdNeto"], 2) == 99.84


def test_venta_mapea_a_sell():
    m = make_movement("v")
    m = Movement(**{**m.__dict__, "side": Side.VENTA})
    assert movement_to_dashboard(m)["type"] == "sell"


def test_dashboard_to_movement_calcula_derivados():
    d = {
        "type": "buy", "date": "2026-06-01", "opId": "xyz",
        "usdBruto": 100, "commPct": 0.16, "priceArs": 1477,
        "exchange": "Binance / USDT", "bank": "Lemon",
    }
    m = dashboard_to_movement(d, source=Source.SCREENSHOT)
    assert m.order_id == "xyz"
    assert m.side is Side.COMPRA
    assert m.commission == Decimal("100") * Decimal("0.16") / Decimal("100")
    assert m.usd_net == m.usd_gross - m.commission
    assert m.total_ars == Decimal("100") * Decimal("1477")
    assert m.source is Source.SCREENSHOT


def test_dashboard_to_movement_genera_order_id_si_falta():
    d = {"type": "sell", "date": "2026-06-01", "opId": "",
         "usdBruto": 10, "commPct": 0, "priceArs": 1000,
         "exchange": "weex", "bank": "MP"}
    m = dashboard_to_movement(d, source=Source.SCREENSHOT)
    assert m.order_id.startswith("man-")
    assert m.side is Side.VENTA


def test_roundtrip_preserva_valores():
    original = make_movement("rt")
    d = movement_to_dashboard(original)
    back = dashboard_to_movement(d, source=original.source)
    assert back.usd_gross == original.usd_gross
    assert back.total_ars == original.total_ars
    assert back.side == original.side
