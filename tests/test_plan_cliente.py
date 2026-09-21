"""El plan de ejecución de una cotización a cliente: qué comprar y cuánto queda.

Motor puro: recibe los precios ya resueltos (los trae `core.cotizacion` con red)
y devuelve los pasos concretos. Números del caso real del 2026-09-03 (Daniel,
660.000 ARS a BTC).
"""
import pytest

from core.plan_cliente import plan_para_cliente


def test_btc_arma_la_ruta_via_usdt_y_deja_el_margen_pedido():
    plan = plan_para_cliente(
        ars=660000, asset="BTC", margen_pct=0.5,
        costo_venue=129012394.72, usdt_price=1581.76,
        spot_price=81480.9, spot_fee_pct=0.1,
    )
    # El cliente recibe lo que pagó al precio con margen.
    assert plan["precio_cliente"] == pytest.approx(129657456.69, abs=0.01)
    assert plan["entrega"] == pytest.approx(0.00509034, abs=1e-8)
    # Para conseguir ese BTC hay que comprar USDT y pasarlos por el spot.
    assert plan["usdt_a_comprar"] == pytest.approx(415.18, abs=0.01)
    assert plan["ars_a_gastar"] == pytest.approx(656715, abs=2)
    assert plan["ganancia_ars"] == pytest.approx(3285, abs=2)
    assert plan["ganancia_pct"] == pytest.approx(0.5, abs=0.001)


def test_usdt_es_directo_sin_pata_de_spot():
    plan = plan_para_cliente(ars=660000, asset="USDT", margen_pct=0.5,
                             costo_venue=1581.82)
    assert plan["usdt_a_comprar"] is None          # no hay conversión intermedia
    assert plan["entrega"] == pytest.approx(660000 / (1581.82 * 1.005), abs=1e-6)
    assert plan["ganancia_pct"] == pytest.approx(0.5, abs=0.001)


def test_el_margen_sale_siempre_sobre_el_costo_de_reposicion():
    """La base es lo que cuesta reponer hoy, no un costo viejo: con margen 1%
    la ganancia tiene que dar 1% sobre lo gastado."""
    plan = plan_para_cliente(ars=1_000_000, asset="USDT", margen_pct=1.0,
                             costo_venue=1600.0)
    assert plan["ganancia_pct"] == pytest.approx(1.0, abs=0.001)
    assert plan["ganancia_ars"] == pytest.approx(
        1_000_000 - plan["ars_a_gastar"], abs=0.01)


def test_margen_cero_no_gana_ni_pierde():
    plan = plan_para_cliente(ars=500_000, asset="USDT", margen_pct=0.0,
                             costo_venue=1590.0)
    assert plan["ganancia_ars"] == pytest.approx(0.0, abs=0.01)


def test_btc_sin_precio_de_spot_falla_fuerte():
    """Sin el spot no hay ruta sintética: mejor romper que inventar un precio."""
    with pytest.raises(ValueError, match="spot"):
        plan_para_cliente(ars=660000, asset="BTC", margen_pct=0.5,
                          costo_venue=129012394.72, usdt_price=1581.82)


def test_el_fee_del_spot_encarece_los_usdt_necesarios():
    base = dict(ars=660000, asset="BTC", margen_pct=0.5,
                costo_venue=129012394.72, usdt_price=1581.76, spot_price=81480.9)
    con_fee = plan_para_cliente(**base, spot_fee_pct=0.1)
    sin_fee = plan_para_cliente(**base, spot_fee_pct=0.0)
    assert con_fee["usdt_a_comprar"] > sin_fee["usdt_a_comprar"]


def test_monto_invalido():
    with pytest.raises(ValueError):
        plan_para_cliente(ars=0, asset="USDT", margen_pct=0.5, costo_venue=1590.0)


def test_el_precio_se_canta_sobre_lo_que_le_llega():
    """Medido el 03/09/2026 con Daniel: se retiraron 0,00509 BTC y al cliente
    le llegaron 0,00507. Cotizar sobre el bruto lo deja reclamando, así que el
    precio que se le dice es sobre lo que RECIBE."""
    plan = plan_para_cliente(
        ars=660000, asset="BTC", margen_pct=0.5,
        costo_venue=129012394.72, usdt_price=1581.76,
        spot_price=81480.9, spot_fee_pct=0.1, fee_red=0.00002,
    )
    assert plan["entrega_bruta"] == pytest.approx(0.00509034, abs=1e-8)
    assert plan["entrega"] == pytest.approx(plan["entrega_bruta"] - 0.00002, abs=1e-12)
    # El precio que se le canta es ARS ÷ lo que le llega, no ÷ lo que salió.
    assert plan["precio_cliente"] == pytest.approx(660000 / plan["entrega"], rel=1e-9)
    assert plan["precio_cliente"] > plan["precio_base"]
    # La ganancia no cambia: el fee está cobrado dentro del precio.
    assert plan["ganancia_pct"] == pytest.approx(0.5, abs=0.001)


def test_sin_fee_de_red_los_dos_precios_coinciden():
    plan = plan_para_cliente(ars=660000, asset="BTC", margen_pct=0.5,
                             costo_venue=129012394.72, usdt_price=1581.76,
                             spot_price=81480.9, spot_fee_pct=0.1)
    assert plan["entrega_bruta"] == pytest.approx(plan["entrega"], abs=1e-12)
    assert plan["precio_cliente"] == pytest.approx(plan["precio_base"], rel=1e-9)


def test_precio_al_cliente_tambien_en_usdt():
    """El cliente preguntó cuánto le salió el BTC en USDT (03/09/2026)."""
    plan = plan_para_cliente(
        ars=660000, asset="BTC", margen_pct=0.5,
        costo_venue=129012394.72, usdt_price=1581.76,
        spot_price=81480.9, spot_fee_pct=0.1, fee_red=0.00002,
    )
    esperado = (660000 / 1581.76) / plan["entrega"]
    assert plan["precio_cliente_usdt"] == pytest.approx(esperado, rel=1e-9)
    assert plan["usdt_equivalente"] == pytest.approx(660000 / 1581.76, rel=1e-9)


def test_usdt_no_tiene_fee_de_red_por_default():
    plan = plan_para_cliente(ars=660000, asset="USDT", margen_pct=0.5,
                             costo_venue=1581.82)
    assert plan["entrega_bruta"] == pytest.approx(plan["entrega"], abs=1e-12)
    # Cotizar USDT "en USD" no dice nada: el campo queda vacío.
    assert plan["precio_cliente_usdt"] is None


def test_el_fee_de_red_esta_cobrado_dentro_del_margen():
    """Decisión del usuario (03/09/2026): el fee de red lo absorbe él, pero va
    cobrado dentro del precio. O sea: el cliente recibe EXACTO lo cotizado y la
    ganancia sigue siendo el margen pedido, ya pagado el retiro."""
    fee = 0.00002
    plan = plan_para_cliente(
        ars=660000, asset="BTC", margen_pct=0.5,
        costo_venue=129012394.72, usdt_price=1581.76,
        spot_price=81480.9, spot_fee_pct=0.1, fee_red=fee,
    )
    # Compra de más para cubrir el retiro: paga el BTC del fee de su bolsillo.
    assert plan["entrega_bruta"] == pytest.approx(plan["entrega"] + fee, abs=1e-12)
    costo_del_fee = fee * plan["ars_a_gastar"] / plan["entrega_bruta"]
    assert costo_del_fee > 0

    # Y aun así la ganancia neta es el 0,5%: el fee está adentro del precio.
    assert plan["ganancia_pct"] == pytest.approx(0.5, abs=0.001)
    assert plan["ganancia_ars"] == pytest.approx(660000 - plan["ars_a_gastar"],
                                                 abs=0.01)
    # El precio que se le canta ya lo tiene contado.
    assert plan["precio_cliente"] * plan["entrega"] == pytest.approx(660000,
                                                                     rel=1e-9)
