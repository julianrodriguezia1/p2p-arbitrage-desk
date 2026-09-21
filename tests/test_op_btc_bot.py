"""El comando /op de Telegram: el ciclo BTC de punta a punta sin pensar."""
import pytest

from bot.op_btc import (
    fmt_arranque, fmt_plan, fmt_tanda, parse_op, parse_spot, parse_tanda,
)
from core.op_cliente import OpCliente, Tanda


class TestParseArranque:
    def test_lee_cliente_monto_y_margen(self):
        op = parse_op("Daniel 6040000 0.75")
        assert (op.cliente, op.ars_cliente, op.margen_pct) == ("Daniel", 6_040_000, 0.75)

    def test_acepta_los_puntos_de_miles(self):
        assert parse_op("Daniel 6.040.000 0,75").ars_cliente == 6_040_000

    def test_sin_margen_usa_el_del_config(self):
        import config
        assert parse_op("Daniel 6040000").margen_pct == config.COTIZA_MARGEN_PCT

    def test_sin_monto_no_se_puede(self):
        with pytest.raises(ValueError):
            parse_op("Daniel")


class TestParseTanda:
    def test_lee_usdt_y_precio(self):
        t = parse_tanda("2700 1578.70")
        assert (t.usdt, t.price_ars) == (2700, 1578.70)

    def test_acepta_coma_decimal_y_puntos(self):
        t = parse_tanda("1.100 1.578,99")
        assert (t.usdt, t.price_ars) == (1100, 1578.99)

    def test_falta_un_dato(self):
        with pytest.raises(ValueError):
            parse_tanda("2700")


class TestParseSpot:
    def test_lee_los_tres_numeros_de_la_orden(self):
        usdt, btc, com = parse_spot("3780.466902 0.04794 0.00004794")
        assert (usdt, btc, com) == (3780.466902, 0.04794, 0.00004794)

    def test_sin_comision_asume_cero(self):
        assert parse_spot("3780.46 0.04794")[2] == 0.0


class TestMensajes:
    def test_el_arranque_dice_cuanto_usdt_hay_que_comprar(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75)
        txt = fmt_arranque(op, venue="bybitp2p", precio=1580.0, publicando=False)
        assert "Daniel" in txt and "3.794" in txt and "bybit" in txt.lower()

    def test_la_tanda_dice_lo_que_falta(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(2700, 1578.70)])
        txt = fmt_tanda(op, precio_reposicion=1580.0)
        assert "1.096" in txt

    def test_cuando_esta_completa_lo_dice(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(2700, 1578.70), Tanda(1100, 1578.99)])
        txt = fmt_tanda(op, precio_reposicion=1580.0)
        assert "completa" in txt.lower()

    def test_el_plan_final_trae_el_btc_el_precio_y_la_ganancia(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(2700, 1578.70), Tanda(1100, 1578.99)])
        plan = op.plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        txt = fmt_plan(op, plan)
        assert "0,04808" in txt          # lo que le llega al cliente
        assert "125.6" in txt            # el precio cantado, en millones
        assert "45.300" in txt           # la ganancia


class TestMovimientosACargar:
    def test_arma_las_cuatro_ops_de_la_operacion(self):
        from bot.op_btc import build_movements
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(2700, 1578.70), Tanda(1100, 1578.99)])
        plan = op.plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        movs = build_movements(op, plan, fecha="2026-09-07",
                               spot=(3780.466902, 0.04794, 0.00004794),
                               venue="Bybit", bank="Lemon Cash")
        assert len(movs) == 4
        assert [m["side"] for m in movs] == ["COMPRA", "COMPRA", "COMPRA", "VENTA"]
        venta = movs[-1]
        assert venta["exchange_coin"] == "OTC / BTC"
        assert float(venta["total_ars"]) == 6_040_000
        spot = movs[2]
        assert spot["exchange_coin"] == "Binance spot / BTC"
        assert spot["order_id"] == "spot-btcusdt-20260907"

    def test_la_venta_lleva_el_fee_de_red_como_comision(self):
        from bot.op_btc import build_movements
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(3800, 1578.7839)])
        plan = op.plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        movs = build_movements(op, plan, fecha="2026-09-07",
                               spot=(3780.4, 0.04794, 0.00004794),
                               venue="Bybit", bank="Lemon")
        venta = movs[-1]
        assert float(venta["usd_gross"]) - float(venta["usd_net"]) == pytest.approx(0.00002)


class TestResumenQueQueda:
    def test_el_mensaje_final_repite_el_precio_en_pesos_y_en_usdt(self):
        """Después de cargar, la tarjeta del plan se reemplaza: el precio que
        se le canta al cliente tiene que quedar igual en el chat."""
        import inspect

        from bot import op_btc
        src = inspect.getsource(op_btc.on_callback)
        assert "precio_cantado_usdt" in src and "precio_cantado" in src
        assert "ARS por BTC" in src and "USDT por BTC" in src


class TestAssetEnElComando:
    def test_lee_el_asset_adelante(self):
        op = parse_op("USDT Daniel 500000 0.5")
        assert (op.asset, op.cliente, op.ars_cliente) == ("USDT", "Daniel", 500_000)

    def test_lee_el_asset_atras(self):
        op = parse_op("Daniel 500000 0.5 usdt")
        assert (op.asset, op.cliente, op.margen_pct) == ("USDT", "Daniel", 0.5)

    def test_sin_asset_sigue_siendo_btc(self):
        assert parse_op("Daniel 6040000 0.75").asset == "BTC"

    def test_btc_explicito_tambien_anda(self):
        op = parse_op("BTC Daniel 6040000 0.75")
        assert (op.asset, op.cliente, op.margen_pct) == ("BTC", "Daniel", 0.75)

    def test_el_arranque_de_usdt_no_habla_de_spot(self):
        from core.op_cliente import OpCliente as OC
        op = OC(cliente="Daniel", ars_cliente=500_000, margen_pct=0.5, asset="USDT")
        txt = fmt_arranque(op, venue="bybitp2p", precio=1580.0, publicando=False)
        assert "spot" not in txt.lower()

    def test_cuando_es_usdt_la_tanda_manda_a_cerrar_no_a_spot(self):
        from core.op_cliente import OpCliente as OC
        op = OC(cliente="G", ars_cliente=500_000, margen_pct=0.5, asset="USDT",
                compras=[Tanda(315.0, 1580.0)])
        txt = fmt_tanda(op, precio_reposicion=1580.0)
        assert "/cerrar" in txt and "/spot" not in txt

    def test_el_plan_de_usdt_trae_el_precio_y_lo_que_le_llega(self):
        from bot.op_btc import fmt_plan_usdt
        from core.op_cliente import OpCliente as OC
        op = OC(cliente="Daniel", ars_cliente=500_000, margen_pct=0.5, asset="USDT",
                compras=[Tanda(315.0, 1580.0)])
        txt = fmt_plan_usdt(op, op.plan_usdt(fee_red_usdt=1.0))
        assert "313,87" in txt and "1.593" in txt        # USDT que llegan y precio

    def test_las_ops_de_usdt_son_una_por_tanda_mas_la_venta(self):
        from bot.op_btc import build_movements_usdt
        from core.op_cliente import OpCliente as OC
        op = OC(cliente="Daniel", ars_cliente=500_000, margen_pct=0.5, asset="USDT",
                compras=[Tanda(315.0, 1580.0)])
        movs = build_movements_usdt(op, op.plan_usdt(fee_red_usdt=1.0),
                                    fecha="2026-09-07", venue="Bybit", bank="Lemon")
        assert [m["side"] for m in movs] == ["COMPRA", "VENTA"]
        assert movs[-1]["exchange_coin"] == "OTC / USDT"


class TestFeeFlatEnElBot:
    def test_binance_cobra_flat_los_demas_no(self):
        from bot.op_btc import fee_flat_de
        assert fee_flat_de("binancep2p") > 0
        assert fee_flat_de("Binance") > 0
        assert fee_flat_de("bybitp2p") == 0.0
        assert fee_flat_de("kucoin") == 0.0

    def test_la_tanda_del_comando_lo_aplica_segun_el_venue(self):
        t = parse_tanda("1139.24 1580", venue="Binance")
        assert t.usdt_neto == pytest.approx(1139.17)
        t2 = parse_tanda("1139.24 1580", venue="Bybit")
        assert t2.usdt_neto == pytest.approx(1139.24)
