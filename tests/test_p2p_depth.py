from dataclasses import dataclass
from core.p2p_depth import (filter_traps, depth_price, depth_fill,
                            compute_depth_quote)


@dataclass
class A:
    price: float
    available: float


def test_filter_traps_descarta_outlier_conserva_barato_con_poco_stock():
    ads = [A(1100, 26150), A(1546.88, 101.16), A(1548.70, 1043390)]
    kept = filter_traps(ads, max_dev_pct=3.0)
    precios = sorted(a.price for a in kept)
    assert 1100 not in precios            # anzuelo fuera
    assert 1546.88 in precios             # barato con poco stock se conserva
    assert 1548.70 in precios


def test_filter_traps_no_deja_vacio():
    # 2 avisos muy separados: el filtro no debe dejar la lista vacía.
    ads = [A(1100, 10), A(1547, 10)]
    assert len(filter_traps(ads)) == 2


def test_filter_traps_no_descarta_la_punta_buena_por_mediana_envenenada():
    # Libro tipo KuCoin: una cola de bids bajos hunde la mediana SIMPLE, pero la
    # liquidez real (y el mejor precio de venta) está arriba. La punta alta con
    # stock NO debe descartarse como anzuelo.
    ads = [
        A(1558.2, 16010), A(1554.0, 190307), A(1550.0, 5100), A(1549.0, 9556),
        A(1509.4, 18518), A(1502.0, 1000), A(1496.0, 150), A(1490.0, 120),
        A(1485.0, 100), A(1480.0, 90),
    ]
    kept = filter_traps(ads, max_dev_pct=3.0)
    precios = {round(a.price, 1) for a in kept}
    assert 1558.2 in precios and 1554.0 in precios   # la punta buena con liquidez se conserva
    # y el bid por profundidad para 1000 sale de la punta alta, no de la cola baja
    assert depth_price(kept, 1000, "SELL") >= 1553


def test_depth_price_buy_vwap_cruza_varias_ofertas():
    # Comprar 1000: 101.16 @ 1546.88 + 898.84 @ 1548.70
    ads = [A(1546.88, 101.16), A(1548.70, 1043390)]
    p = depth_price(ads, 1000, "BUY")
    esperado = (101.16 * 1546.88 + 898.84 * 1548.70) / 1000
    assert abs(p - esperado) < 1e-6


def test_depth_price_buy_entra_en_primera_oferta():
    ads = [A(1546.88, 500), A(1548.70, 1000)]
    assert depth_price(ads, 100, "BUY") == 1546.88


def test_depth_price_sell_toma_los_mas_altos():
    ads = [A(1544.25, 50), A(1542.50, 1000)]
    # Vender 100: 50 @ 1544.25 + 50 @ 1542.50
    p = depth_price(ads, 100, "SELL")
    assert abs(p - ((50 * 1544.25 + 50 * 1542.50) / 100)) < 1e-6


def test_depth_price_stock_insuficiente_promedia_lo_disponible():
    ads = [A(1546.88, 30)]
    assert depth_price(ads, 1000, "BUY") == 1546.88  # VWAP de los 30


def test_depth_price_sin_ads_es_none():
    assert depth_price([], 1000, "BUY") is None


def test_compute_depth_quote_ask_y_bid():
    buy = [A(1100, 1), A(1546.88, 101.16), A(1548.70, 1043390)]   # con anzuelo
    sell = [A(1544.25, 157266)]
    q = compute_depth_quote(buy, sell, 1000)
    assert abs(q["ask"] - (101.16 * 1546.88 + 898.84 * 1548.70) / 1000) < 1e-6
    assert q["bid"] == 1544.25


# ── Límites por orden: un aviso no se puede tomar por cualquier monto ──────
# Encontrado el 2026-08-22 mirando el libro real de Binance: el aviso más
# grande del tope (1.990 USDT a 1.587,00) tenía un MÍNIMO de $3.040.000. Para
# una compra de ~$1.577.000 ese aviso es intocable, pero el VWAP lo contaba
# como si se pudiera llenar. Es el mismo error que costó plata el 21/08:
# cotizar con un precio que no se puede ejecutar.

@dataclass
class L:
    """Aviso con los límites por orden que Binance publica (en ARS)."""
    price: float
    available: float
    min_amount: float = 0.0
    max_amount: float = 0.0


def test_saltea_el_aviso_cuyo_minimo_no_llegas_a_cubrir():
    """El barato pide un mínimo más grande que toda la compra: no existe."""
    ads = [L(1586.0, 2000.0, min_amount=3_040_000.0, max_amount=3_152_000.0),
           L(1590.0, 2000.0, min_amount=10_000.0, max_amount=1_000_000.0)]
    assert depth_price(ads, 500.0, "BUY") == 1590.0


def test_respeta_el_maximo_por_orden_del_aviso():
    """El aviso tiene 2.000 USDT de stock pero no te deja comprar más de 100
    por orden: el resto se llena con el siguiente, más caro."""
    ads = [L(1000.0, 2000.0, max_amount=100_000.0),   # tope 100 USDT
           L(1100.0, 2000.0, max_amount=10_000_000.0)]
    # 100 a 1000 + 100 a 1100 = 210.000 / 200 = 1050
    assert depth_price(ads, 200.0, "BUY") == 1050.0


def test_sin_limites_declarados_se_comporta_como_antes():
    """Venues que no publican min/max no tienen que cambiar de precio."""
    ads = [L(1000.0, 100.0), L(1100.0, 100.0)]
    assert depth_price(ads, 200.0, "BUY") == 1050.0


def test_el_minimo_se_evalua_contra_lo_que_falta_no_contra_el_total():
    """Al final de la caminata queda poco por llenar: los avisos con mínimo alto
    dejan de servir aunque al principio sí servían."""
    ads = [L(1000.0, 50.0, max_amount=1_000_000.0),
           L(1100.0, 500.0, min_amount=200_000.0, max_amount=1_000_000.0)]
    # Faltan 10 USDT (11.000 ARS) y el segundo pide 200.000 de mínimo: no entra.
    assert depth_price(ads, 60.0, "BUY") == 1000.0


# ── Cuántas órdenes hace falta hacer ──────────────────────────────────────
# Un precio bueno repartido en 11 avisos no es el mismo negocio que el mismo
# precio en 1: son 11 chats, 11 transferencias y 11 esperas. El 22/08/2026 el
# usuario abandonó una compra en Binance por esto.

def test_depth_fill_cuenta_los_avisos_que_hay_que_tomar():
    ads = [L(1000.0, 50.0), L(1010.0, 50.0), L(1020.0, 50.0)]
    r = depth_fill(ads, 120.0, "BUY")
    assert r["ordenes"] == 3
    assert r["filled"] == 120.0


def test_depth_fill_no_cuenta_los_avisos_que_no_pudo_usar():
    """El que pide un mínimo inalcanzable no es una orden que vayas a hacer."""
    ads = [L(1000.0, 500.0, min_amount=9_000_000.0), L(1010.0, 500.0)]
    r = depth_fill(ads, 100.0, "BUY")
    assert r["ordenes"] == 1
    assert r["price"] == 1010.0


def test_depth_fill_avisa_cuando_el_libro_no_alcanza():
    ads = [L(1000.0, 10.0)]
    r = depth_fill(ads, 100.0, "BUY")
    assert r["filled"] == 10.0
    assert r["alcanza"] is False


def test_depth_price_sigue_dando_lo_mismo_que_depth_fill():
    """Una sola caminata del libro, dos vistas: no pueden discrepar."""
    ads = [L(1000.0, 50.0), L(1100.0, 50.0)]
    assert depth_price(ads, 100.0, "BUY") == depth_fill(ads, 100.0, "BUY")["price"]


# ── Contraparte sin historial ─────────────────────────────────────────────
# Visto en vivo el 22/08/2026: OKX ofrecía comprar USDT a 1.600 (0,9% arriba
# del mercado) con 9.000 USDT de stock y mínimo $1.600.000 — de un usuario con
# 0 órdenes completadas y 0% de finalización, nick "zan***@outlook.com". El
# tablero lo mostraba como la mejor opción para vender. Un precio mejor que el
# del mercado ofrecido por alguien sin ningún trade cerrado no es un precio.

@dataclass
class R:
    price: float
    available: float
    min_amount: float = 0.0
    max_amount: float = 0.0
    orders: int = 500
    finish_rate: float = 0.99


def test_filter_traps_descarta_al_que_nunca_cerro_una_orden():
    ads = [R(1600.0, 9000.0, orders=0, finish_rate=0.0),
           R(1585.7, 8724.0), R(1585.6, 480.0)]
    precios = [a.price for a in filter_traps(ads)]
    assert 1600.0 not in precios
    assert 1585.7 in precios


def test_filter_traps_no_toca_los_avisos_sin_dato_de_reputacion():
    """Venues que no publican órdenes/finish (o fixtures viejos) no cambian."""
    ads = [A(1585.0, 100.0), A(1586.0, 100.0)]
    assert len(filter_traps(ads)) == 2


def test_filter_traps_no_deja_vacio_si_todos_son_nuevos():
    """Si el libro entero es de cuentas nuevas, mejor mostrarlo que no mostrar
    nada: el que decide es el usuario, con el dato a la vista."""
    ads = [R(1585.0, 100.0, orders=0), R(1586.0, 100.0, orders=0)]
    assert len(filter_traps(ads)) == 2


# --- fee fijo por orden: el llenado más barato NETO, no el de mejor precio ---
@dataclass
class L:
    price: float
    available: float
    min_amount: float = 0.0
    max_amount: float = 0.0


def _libro_vender():
    # 10 compradores chicos a buen precio (100 USDT c/u) y uno grande un poco
    # peor que llena los 1.000 solo. Pedido 2026-09-16: elegir el que rinde más
    # después del 0,07 por orden, y decir cuántas órdenes son.
    chicos = [L(1589.5 - i * 0.01, 100.0, max_amount=100.0 * 1600.0) for i in range(10)]
    grande = L(1588.9, 5000.0, min_amount=300_000.0)
    return chicos + [grande]


def test_sin_fee_por_orden_sigue_el_mejor_precio():
    r = depth_fill(_libro_vender(), 1000.0, "SELL")
    assert r["ordenes"] == 10 and r["alcanza"]
    assert r["price"] > 1589.4


def test_con_fee_por_orden_elige_el_llenado_que_rinde_mas_neto():
    # 10 órdenes: ~1589,455 − 10×0,07×1589/1000 ≈ 1588,34 neto por USDT.
    # 1 orden: 1588,90 − 0,07×1589/1000 ≈ 1588,79 neto. Gana la única.
    r = depth_fill(_libro_vender(), 1000.0, "SELL", fee_por_orden=0.07)
    assert r["ordenes"] == 1 and r["alcanza"]
    assert r["price"] == 1588.9


def test_con_fee_por_orden_comprando_tambien():
    chicos = [L(1592.0 + i * 0.01, 100.0, max_amount=100.0 * 1600.0) for i in range(10)]
    grande = L(1592.6, 5000.0)
    r = depth_fill(chicos + [grande], 1000.0, "BUY", fee_por_orden=0.07)
    assert r["ordenes"] == 1 and r["price"] == 1592.6


def test_con_fee_pero_libro_que_no_alcanza_devuelve_lo_que_hay():
    ads = [L(1589.0, 100.0), L(1588.0, 100.0)]
    r = depth_fill(ads, 1000.0, "SELL", fee_por_orden=0.07)
    assert r["alcanza"] is False and r["ordenes"] == 2


def test_compute_depth_quote_pasa_el_fee_por_orden():
    q = compute_depth_quote([], _libro_vender(), 1000.0, fee_por_orden=0.07)
    assert q["bid_ordenes"] == 1
    q0 = compute_depth_quote([], _libro_vender(), 1000.0)
    assert q0["bid_ordenes"] == 10
