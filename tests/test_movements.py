from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source


def make_movement(**over):
    base = dict(
        side=Side.COMPRA, date=date(2026, 6, 1), order_id="123",
        usd_gross=Decimal("16.92"), commission=Decimal("0.07"),
        usd_net=Decimal("16.85"), price=Decimal("1477"),
        total_ars=Decimal("25000"), exchange_coin="Binance / USDT",
        bank="Lemon Cash", source=Source.BINANCE_API,
    )
    base.update(over)
    return Movement(**base)


def test_month_tab_devuelve_nombre_de_mes_en_espanol():
    assert make_movement(date=date(2026, 6, 1)).month_tab() == "Junio"
    assert make_movement(date=date(2026, 1, 15)).month_tab() == "Enero"
    assert make_movement(date=date(2026, 12, 31)).month_tab() == "Diciembre"


def test_side_y_source_son_enums_string():
    m = make_movement()
    assert m.side.value == "COMPRA"
    assert m.source.value == "binance_api"
