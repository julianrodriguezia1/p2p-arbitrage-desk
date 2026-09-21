"""La operación de cliente en tandas: el ciclo que se hizo a mano el 2026-09-07.

Los números son los reales de esa operación (Daniel, 6.040.000 ARS → BTC).
"""
import pytest

from core.op_cliente import OpCliente, Tanda, PlanBtc


def op_daniel() -> OpCliente:
    """La operación real, con las dos compras de USDT ya hechas."""
    return OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                     compras=[Tanda(usdt=2700, price_ars=1578.70),
                              Tanda(usdt=1100, price_ars=1578.99)])


class TestPromedio:
    def test_suma_los_usdt_de_las_tandas(self):
        assert op_daniel().usdt_total() == 3800

    def test_suma_los_pesos_gastados(self):
        # 2700*1578.70 = 4.262.490 · 1100*1578.99 = 1.736.889
        assert op_daniel().ars_gastado() == pytest.approx(5_999_379, abs=1)

    def test_costo_promedio_divide_pesos_por_usdt(self):
        assert op_daniel().costo_promedio() == pytest.approx(1578.7839, abs=1e-3)

    def test_sin_compras_no_hay_promedio(self):
        vacia = OpCliente(cliente="X", ars_cliente=100_000, margen_pct=0.5)
        assert vacia.costo_promedio() is None


class TestCuantoFalta:
    def test_falta_lo_que_queda_del_presupuesto_al_precio_de_ahora(self):
        # presupuesto = 6.040.000 - 0,75% = 5.994.700; ya gastó 5.999.379
        # => se pasó, no falta nada
        assert op_daniel().falta_usdt(1580.0) == 0.0

    def test_con_una_sola_tanda_dice_cuanto_falta(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(usdt=2700, price_ars=1578.70)])
        # presupuesto 5.994.700 - 4.262.490 = 1.732.210 => /1580 = 1096,3 USDT
        assert op.falta_usdt(1580.0) == pytest.approx(1096.34, abs=0.01)

    def test_falta_ars_es_el_presupuesto_menos_lo_gastado(self):
        op = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=0.75,
                       compras=[Tanda(usdt=2700, price_ars=1578.70)])
        assert op.falta_ars() == pytest.approx(1_732_210, abs=1)


class TestPlanBtc:
    def test_reproduce_la_operacion_del_7_de_septiembre(self):
        # precio efectivo del spot = 3780,4669 USDT / 0,04789206 BTC recibidos
        plan = op_daniel().plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        assert plan.btc_al_cliente == pytest.approx(0.04808205, abs=1e-8)
        assert plan.precio_cantado == pytest.approx(125_618_000, rel=1e-4)
        assert plan.ganancia_ars == pytest.approx(45_300, abs=1)

    def test_el_cliente_recibe_el_bruto_menos_el_fee_de_red(self):
        plan = op_daniel().plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        assert plan.btc_bruto - plan.btc_al_cliente == pytest.approx(0.00002, abs=1e-9)

    def test_el_puente_bsc_se_descuenta_de_los_usdt(self):
        con = op_daniel().plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.20)
        sin = op_daniel().plan_btc(precio_efectivo_btc=78_937.1, fee_bridge_usdt=0.0)
        assert con.btc_al_cliente < sin.btc_al_cliente

    def test_margen_mas_alto_deja_menos_btc_al_cliente(self):
        base = op_daniel()
        caro = OpCliente(cliente="Daniel", ars_cliente=6_040_000, margen_pct=2.0,
                         compras=base.compras)
        assert caro.plan_btc(78_937.1).btc_al_cliente < base.plan_btc(78_937.1).btc_al_cliente

    def test_sin_compras_no_se_puede_planear(self):
        vacia = OpCliente(cliente="X", ars_cliente=100_000, margen_pct=0.5)
        with pytest.raises(ValueError):
            vacia.plan_btc(78_937.1)


class TestPrecioEfectivoDelSpot:
    def test_sale_de_los_usdt_gastados_sobre_el_btc_recibido(self):
        from core.op_cliente import precio_efectivo_spot
        # la orden real: 0,04794 BTC, comisión 0,00004794 BTC, 3780,46690200 USDT
        p = precio_efectivo_spot(usdt_gastados=3780.466902, btc_bruto=0.04794,
                                 comision_btc=0.00004794)
        assert p == pytest.approx(78_937.1, abs=1.0)


class TestRetiro:
    def test_binance_es_mas_barato_que_bybit_para_retirar_btc(self):
        from core.op_cliente import FEE_RETIRO_BTC
        assert FEE_RETIRO_BTC["binance"] < FEE_RETIRO_BTC["bybit"]


class TestAsset:
    def test_por_defecto_es_btc(self):
        assert OpCliente(cliente="X", ars_cliente=1, margen_pct=0.5).asset == "BTC"

    def test_plan_usdt_no_pasa_por_el_spot(self):
        op = OpCliente(cliente="Daniel", ars_cliente=500_000, margen_pct=0.5,
                       asset="USDT",
                       compras=[Tanda(usdt=315.0, price_ars=1580.0)])
        plan = op.plan_usdt(fee_red_usdt=1.0)
        # presupuesto 497.500 / 1580 = 314,873 USDT - 1 de red = 313,873
        assert plan.usdt_al_cliente == pytest.approx(313.873, abs=1e-3)
        assert plan.precio_cantado == pytest.approx(500_000 / plan.usdt_al_cliente, rel=1e-9)
        assert plan.ganancia_ars == pytest.approx(2500, abs=1)

    def test_el_fee_de_red_sale_de_los_usdt_del_cliente(self):
        op = OpCliente(cliente="G", ars_cliente=500_000, margen_pct=0.5,
                       asset="USDT", compras=[Tanda(315.0, 1580.0)])
        caro = op.plan_usdt(fee_red_usdt=5.0)
        barato = op.plan_usdt(fee_red_usdt=1.0)
        assert barato.usdt_al_cliente - caro.usdt_al_cliente == pytest.approx(4.0)

    def test_sin_compras_no_se_puede_planear_usdt(self):
        op = OpCliente(cliente="X", ars_cliente=100_000, margen_pct=0.5, asset="USDT")
        with pytest.raises(ValueError):
            op.plan_usdt()


class TestFeeFlatDeTomador:
    """Binance cobra ~0,07 USDT por CADA orden tomada, aunque su API diga 0."""

    def test_la_tanda_descuenta_el_flat(self):
        t = Tanda(usdt=1139.24, price_ars=1580.0, fee_usdt=0.07)
        assert t.usdt_neto == pytest.approx(1139.17)
        assert t.ars == pytest.approx(1139.24 * 1580.0)   # los pesos no cambian

    def test_sin_fee_el_neto_es_el_bruto(self):
        assert Tanda(usdt=100, price_ars=1580.0).usdt_neto == 100

    def test_el_total_suma_netos_no_brutos(self):
        op = OpCliente(cliente="G", ars_cliente=1_000_000, margen_pct=0.5,
                       compras=[Tanda(500, 1580.0, fee_usdt=0.07),
                                Tanda(500, 1580.0, fee_usdt=0.07)])
        assert op.usdt_total() == pytest.approx(999.86)

    def test_cinco_ordenes_cuestan_cinco_flats(self):
        """Partir una compra en cinco avisos cuesta cinco veces el flat."""
        una = OpCliente(cliente="G", ars_cliente=1_000_000, margen_pct=0.5,
                        compras=[Tanda(500, 1580.0, fee_usdt=0.07)])
        cinco = OpCliente(cliente="G", ars_cliente=1_000_000, margen_pct=0.5,
                          compras=[Tanda(100, 1580.0, fee_usdt=0.07) for _ in range(5)])
        assert una.usdt_total() - cinco.usdt_total() == pytest.approx(0.28)

    def test_el_promedio_sube_porque_el_flat_se_paga_igual(self):
        con = OpCliente(cliente="G", ars_cliente=1_000_000, margen_pct=0.5,
                        compras=[Tanda(1000, 1580.0, fee_usdt=0.07)])
        sin = OpCliente(cliente="G", ars_cliente=1_000_000, margen_pct=0.5,
                        compras=[Tanda(1000, 1580.0)])
        assert con.costo_promedio() > sin.costo_promedio()
