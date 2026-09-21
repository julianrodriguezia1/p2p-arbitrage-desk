from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source
from cli.sync_binance import select_new_movements, filter_by_date


def mv(order_id, d=date(2026, 6, 1)):
    return Movement(
        side=Side.COMPRA, date=d, order_id=order_id,
        usd_gross=Decimal("1"), commission=Decimal("0"), usd_net=Decimal("1"),
        price=Decimal("1"), total_ars=Decimal("1"), exchange_coin="Binance / USDT",
        bank="x", source=Source.BINANCE_API,
    )


def test_select_new_movements_filtra_los_ya_cargados():
    movements = [mv("a"), mv("b"), mv("c")]
    nuevos = select_new_movements(movements, existing_ids={"b"})
    assert [m.order_id for m in nuevos] == ["a", "c"]


def test_select_new_movements_vacio_si_todos_existen():
    assert select_new_movements([mv("a")], existing_ids={"a"}) == []


def test_filter_by_date_deja_solo_la_fecha_pedida():
    movements = [
        mv("a", date(2026, 6, 3)),
        mv("b", date(2026, 6, 1)),
        mv("c", date(2026, 6, 3)),
    ]
    filtrados = filter_by_date(movements, date(2026, 6, 3))
    assert [m.order_id for m in filtrados] == ["a", "c"]


def test_filter_by_date_vacio_si_no_hay_de_esa_fecha():
    assert filter_by_date([mv("a", date(2026, 6, 1))], date(2026, 6, 3)) == []


class _FakeClient:
    """Registra con qué ventana se le pidió cada lado."""

    def __init__(self):
        self.pedidos = []

    def fetch_orders_range(self, trade_type, desde, hasta):
        self.pedidos.append((trade_type, desde, hasta))
        return [{
            "orderNumber": f"229000000000000000{len(self.pedidos)}",
            "tradeType": trade_type, "orderStatus": "COMPLETED",
            "asset": "USDT", "fiat": "ARS", "amount": "100",
            "totalPrice": "160000", "unitPrice": "1600",
            "commission": "0.2", "createTime": 1_780_000_000_000,
            "payMethodName": "Galicia",
        }]


def test_fetch_all_pide_por_rango_de_fechas_los_dos_lados():
    """Sin rango Binance devuelve sólo los últimos 30 días y lo viejo queda
    invisible para siempre (medido el 2026-08-30)."""
    from cli.sync_binance import _fetch_all

    cli = _FakeClient()
    movs = _fetch_all(cli, desde=date(2026, 5, 26), hasta=date(2026, 8, 30))

    assert [p[0] for p in cli.pedidos] == ["BUY", "SELL"]
    assert all(p[1] == date(2026, 5, 26) and p[2] == date(2026, 8, 30)
               for p in cli.pedidos)
    assert len(movs) == 2


def test_desde_por_defecto_cubre_la_ventana_de_30_dias():
    from cli.sync_binance import _desde_por_defecto

    assert _desde_por_defecto(date(2026, 8, 30)) == date(2026, 7, 31)


def test_parse_args_acepta_desde_para_rellenar_hacia_atras():
    from cli.sync_binance import _parse_args

    assert _parse_args(["--desde", "2026-05-26"]).desde == "2026-05-26"
