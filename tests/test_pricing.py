import pytest
from datetime import date
from decimal import Decimal

from core.movements import Movement, Side, Source
from core import pricing


def _mv(side, usd_net, total_ars, coin="Binance / USDT", oid="x", day=date(2026, 6, 1), comm="0"):
    gross = Decimal(usd_net)
    commission = Decimal(comm)
    return Movement(
        side=side, date=day, order_id=oid,
        usd_gross=gross, commission=commission,
        usd_net=gross - commission, price=Decimal("0"),
        total_ars=Decimal(total_ars), exchange_coin=coin, bank="x",
        source=Source.BINANCE_API,
    )


def test_avg_cost_pondera_por_usd_net():
    # 100 USDT a 1000 ARS + 100 USDT a 1200 ARS => costo 1100 ARS/u
    movs = [
        _mv(Side.COMPRA, "100", "100000", oid="a"),
        _mv(Side.COMPRA, "100", "120000", oid="b"),
    ]
    assert pricing.avg_cost(movs, "USDT") == Decimal("1100")


def test_avg_cost_ignora_ventas():
    movs = [
        _mv(Side.COMPRA, "100", "100000", oid="a"),
        _mv(Side.VENTA, "100", "150000", oid="b"),
    ]
    assert pricing.avg_cost(movs, "USDT") == Decimal("1000")


def test_avg_cost_none_si_no_hay_compras():
    assert pricing.avg_cost([_mv(Side.VENTA, "1", "1")], "USDT") is None


def test_avg_cost_filtra_por_asset():
    movs = [
        _mv(Side.COMPRA, "100", "100000", coin="Binance / USDT", oid="a"),
        _mv(Side.COMPRA, "1", "60000000", coin="Binance / BTC", oid="b"),
    ]
    assert pricing.avg_cost(movs, "USDT") == Decimal("1000")


def test_cost_basis_resume_compras_con_promedio_ponderado():
    movs = [
        _mv(Side.COMPRA, "100", "100000", oid="a"),
        _mv(Side.COMPRA, "100", "120000", oid="b"),
    ]
    cb = pricing.cost_basis(movs, "USDT")
    assert cb.count == 2
    assert cb.units == Decimal("200")
    assert cb.total_ars == Decimal("220000")
    assert cb.avg_price == Decimal("1100")  # = break-even


def test_cost_basis_filtra_por_dia():
    movs = [
        _mv(Side.COMPRA, "100", "100000", oid="ayer", day=date(2026, 6, 9)),
        _mv(Side.COMPRA, "100", "150000", oid="hoy", day=date(2026, 6, 10)),
    ]
    cb = pricing.cost_basis(movs, "USDT", on=date(2026, 6, 10))
    assert cb.count == 1
    assert cb.avg_price == Decimal("1500")  # solo la compra de hoy


def test_cost_basis_none_si_no_hay_compras_ese_dia():
    movs = [_mv(Side.COMPRA, "100", "100000", day=date(2026, 6, 9))]
    assert pricing.cost_basis(movs, "USDT", on=date(2026, 6, 10)) is None


def test_cost_basis_ignora_ventas_y_filtra_asset():
    movs = [
        _mv(Side.COMPRA, "100", "100000", coin="Binance / USDT", oid="a"),
        _mv(Side.VENTA, "100", "150000", coin="Binance / USDT", oid="b"),
        _mv(Side.COMPRA, "1", "60000000", coin="Binance / BTC", oid="c"),
    ]
    cb = pricing.cost_basis(movs, "USDT")
    assert cb.count == 1 and cb.avg_price == Decimal("1000")


def test_day_position_stock_es_comprado_menos_vendido():
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="b"),
        _mv(Side.VENTA, "40", "60000", oid="s"),
    ]
    p = pricing.day_position(movs, "USDT")
    assert p.bought == Decimal("100")
    assert p.sold == Decimal("40")
    assert p.stock == Decimal("60")


def test_day_position_comision_baja_compra_y_sube_venta():
    # compra: entra gross-comm = 99; venta: sale gross+comm = 51; stock = 48
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="b", comm="1"),
        _mv(Side.VENTA, "50", "75000", oid="s", comm="1"),
    ]
    p = pricing.day_position(movs, "USDT")
    assert p.bought == Decimal("99")
    assert p.sold == Decimal("51")
    assert p.stock == Decimal("48")


def test_day_position_filtra_por_dia_y_asset():
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="ayer", day=date(2026, 6, 9)),
        _mv(Side.COMPRA, "30", "45000", oid="hoy", day=date(2026, 6, 10)),
        _mv(Side.COMPRA, "1", "60000000", coin="Binance / BTC", oid="btc", day=date(2026, 6, 10)),
    ]
    p = pricing.day_position(movs, "USDT", on=date(2026, 6, 10))
    assert p.bought == Decimal("30") and p.sold == Decimal("0") and p.stock == Decimal("30")


def test_competitive_price_vender_es_min_menos_tick():
    rivales = [Decimal("1490"), Decimal("1493"), Decimal("1500")]
    assert pricing.competitive_price(rivales, Side.VENTA, Decimal("1")) == Decimal("1489")


def test_competitive_price_comprar_es_max_mas_tick():
    rivales = [Decimal("1480"), Decimal("1485"), Decimal("1470")]
    assert pricing.competitive_price(rivales, Side.COMPRA, Decimal("1")) == Decimal("1486")


def test_competitive_price_none_sin_rivales():
    assert pricing.competitive_price([], Side.VENTA, Decimal("1")) is None


def test_margin_price_vender_suma_margen():
    assert pricing.margin_price(Decimal("1000"), Decimal("1"), Side.VENTA) == Decimal("1010.00")


def test_margin_price_comprar_resta_margen():
    assert pricing.margin_price(Decimal("1000"), Decimal("1"), Side.COMPRA) == Decimal("990.00")


def test_circuit_breaker_corta_fuera_de_rango():
    assert pricing.apply_circuit_breaker(Decimal("100"), Decimal("500"), Decimal("5000")) is None
    assert pricing.apply_circuit_breaker(Decimal("9000"), Decimal("500"), Decimal("5000")) is None


def test_circuit_breaker_deja_pasar_dentro_de_rango():
    assert pricing.apply_circuit_breaker(Decimal("1490"), Decimal("500"), Decimal("5000")) == Decimal("1490")


def test_final_sell_price_elige_competitivo_si_supera_el_piso():
    # competitivo 1489 está por encima del piso 1010 => publico competitivo
    assert pricing.final_sell_price(Decimal("1489"), Decimal("1010")) == Decimal("1489")


def test_final_sell_price_usa_el_piso_si_el_mercado_no_da_margen():
    # competitivo 1005 cruza el piso 1010 => publico al piso
    assert pricing.final_sell_price(Decimal("1005"), Decimal("1010")) == Decimal("1010")


def test_circuit_breaker_rechaza_bounds_invertidos():
    with pytest.raises(ValueError):
        pricing.apply_circuit_breaker(Decimal("1490"), Decimal("5000"), Decimal("500"))


# ===== period_bounds =====

def test_period_bounds_hoy_es_el_mismo_dia():
    assert pricing.period_bounds("hoy", date(2026, 6, 25)) == (date(2026, 6, 25), date(2026, 6, 25))


def test_period_bounds_semana_es_lunes_a_domingo():
    # 2026-06-25 es jueves => lunes 22, domingo 28
    assert pricing.period_bounds("semana", date(2026, 6, 25)) == (date(2026, 6, 22), date(2026, 6, 28))


def test_period_bounds_semana_desde_el_lunes():
    assert pricing.period_bounds("semana", date(2026, 6, 22)) == (date(2026, 6, 22), date(2026, 6, 28))


def test_period_bounds_semana_desde_el_domingo():
    assert pricing.period_bounds("semana", date(2026, 6, 28)) == (date(2026, 6, 22), date(2026, 6, 28))


def test_period_bounds_mes_es_calendario_completo():
    assert pricing.period_bounds("mes", date(2026, 6, 25)) == (date(2026, 6, 1), date(2026, 6, 30))


def test_period_bounds_mes_diciembre_cruza_fin_de_anio():
    assert pricing.period_bounds("mes", date(2026, 12, 10)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_period_bounds_kind_invalido():
    with pytest.raises(ValueError):
        pricing.period_bounds("trimestre", date(2026, 6, 25))


# ===== period_average =====

def test_period_average_usa_usd_bruto_no_neto():
    # gross 100, comm 1 (net 99), 150000 ARS => avg = 150000/100 = 1500 (bruto)
    movs = [_mv(Side.COMPRA, "100", "150000", comm="1", day=date(2026, 6, 25))]
    pa = pricing.period_average(movs, "USDT", Side.COMPRA,
                                start=date(2026, 6, 25), end=date(2026, 6, 25))
    assert pa.count == 1
    assert pa.units == Decimal("100")  # bruto, no 99
    assert pa.avg_price == Decimal("1500")


def test_period_average_pondera_por_bruto():
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="a", day=date(2026, 6, 23)),
        _mv(Side.COMPRA, "100", "152000", oid="b", day=date(2026, 6, 24)),
    ]
    pa = pricing.period_average(movs, "USDT", Side.COMPRA,
                                start=date(2026, 6, 22), end=date(2026, 6, 28))
    assert pa.units == Decimal("200")
    assert pa.avg_price == Decimal("1510")  # (150000+152000)/200


def test_period_average_venta_separada_de_compra():
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="c", day=date(2026, 6, 25)),
        _mv(Side.VENTA, "50", "76000", oid="v", day=date(2026, 6, 25)),
    ]
    buy = pricing.period_average(movs, "USDT", Side.COMPRA,
                                 start=date(2026, 6, 25), end=date(2026, 6, 25))
    sell = pricing.period_average(movs, "USDT", Side.VENTA,
                                  start=date(2026, 6, 25), end=date(2026, 6, 25))
    assert buy.avg_price == Decimal("1500")
    assert sell.avg_price == Decimal("1520")  # 76000/50


def test_period_average_filtra_por_rango():
    movs = [
        _mv(Side.COMPRA, "100", "150000", oid="dentro", day=date(2026, 6, 24)),
        _mv(Side.COMPRA, "100", "999000", oid="fuera", day=date(2026, 6, 29)),
    ]
    pa = pricing.period_average(movs, "USDT", Side.COMPRA,
                                start=date(2026, 6, 22), end=date(2026, 6, 28))
    assert pa.count == 1 and pa.avg_price == Decimal("1500")


def test_period_average_filtra_por_asset():
    movs = [
        _mv(Side.COMPRA, "100", "150000", coin="Binance / USDT", oid="u", day=date(2026, 6, 25)),
        _mv(Side.COMPRA, "1", "90000000", coin="Binance / BTC", oid="b", day=date(2026, 6, 25)),
    ]
    pa = pricing.period_average(movs, "USDT", Side.COMPRA,
                                start=date(2026, 6, 25), end=date(2026, 6, 25))
    assert pa.count == 1 and pa.avg_price == Decimal("1500")


def test_period_average_none_si_no_hay_ops():
    movs = [_mv(Side.COMPRA, "100", "150000", day=date(2026, 6, 25))]
    pa = pricing.period_average(movs, "USDT", Side.VENTA,
                                start=date(2026, 6, 25), end=date(2026, 6, 25))
    assert pa is None
