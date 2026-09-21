"""Tarjeta "Hoy" del Verificado: qué vuelta hacer ahora con un ticket dado.

Motor puro: recibe los avisos de Binance ya bajados y los movimientos, devuelve
el mejor aviso para vender y para comprar que ACEPTEN el ticket, cuánto cuesta la
vuelta tomando y publicando, y cuántas ops van hoy contra el ritmo necesario.
"""
from datetime import date
from decimal import Decimal

from core.movements import Movement, Side, Source
from core.verificado_hoy import plan_vuelta
from p2p_scanner import Ad


def _ad(side: str, price: float, mn: float, mx: float, avail: float = 5000.0,
        merchant: str = "x") -> Ad:
    return Ad(exchange="binance", side=side, price=price, min_amount=mn,
              max_amount=mx, available=avail, merchant=merchant)


def _mov(fecha: date, order_id: str = "22900000000000000001",
         exchange: str = "Binance / USDT") -> Movement:
    return Movement(side=Side.VENTA, date=fecha, order_id=order_id,
                    usd_gross=Decimal("100"), commission=Decimal("0.07"),
                    usd_net=Decimal("100"), price=Decimal("1586"),
                    total_ars=Decimal("158600"), exchange_coin=exchange,
                    bank="MP", source=Source.BINANCE_API)


# "BUY" = avisos de gente que te VENDE (vos comprás). "SELL" = te COMPRAN.
TE_VENDEN = [_ad("BUY", 1585.8, 100_000, 1_200_000),
             _ad("BUY", 1584.0, 500_000, 3_000_000),   # más barato pero no acepta 160k
             _ad("BUY", 1586.0, 10_000, 11_633, avail=7)]  # stock 7 USDT: no llena
TE_COMPRAN = [_ad("SELL", 1586.1, 150_000, 250_000),
              _ad("SELL", 1586.0, 7_840, 415_991),
              _ad("SELL", 1590.0, 400_000, 19_000_000)]  # mejor precio, mínimo alto


def test_elige_el_mejor_aviso_que_acepta_el_ticket():
    p = plan_vuelta(TE_VENDEN, TE_COMPRAN, ticket_ars=160_000, fx=1586.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=[], hoy=date(2026, 9, 10))
    assert p.comprar_a.price == 1585.8      # el de 1584 pide 500k; el de 1586 tiene 7 USDT
    assert p.vender_a.price == 1586.1       # el de 1590 pide 400k
    assert round(p.ticket_usdt, 2) == round(160_000 / 1586.0, 2)


def test_costo_tomar_es_dos_flats_menos_lo_que_da_el_libro():
    p = plan_vuelta(TE_VENDEN, TE_COMPRAN, ticket_ars=160_000, fx=1586.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=[], hoy=date(2026, 9, 10))
    usdt = 160_000 / 1586.0
    esperado = usdt * (1586.1 - 1585.8) - 2 * 0.07 * 1586.0
    assert abs(p.neto_tomar_ars - esperado) < 0.01
    # Publicar: cobrás el ancho (te ponés al precio del mejor de cada lado) y pagás 2 makers.
    esperado_pub = usdt * (1585.8 - 1586.1) - 2 * 0.002 * 160_000
    assert abs(p.neto_publicar_ars - esperado_pub) < 0.01
    assert p.modo == "tomar"                 # -194 le gana a -643


def test_con_libro_ancho_conviene_publicar():
    venden = [_ad("BUY", 1595.0, 10_000, 1_000_000)]
    compran = [_ad("SELL", 1585.0, 10_000, 1_000_000)]   # ancho 0,63% > 0,40%
    p = plan_vuelta(venden, compran, ticket_ars=160_000, fx=1590.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=[], hoy=date(2026, 9, 10))
    assert p.modo == "publicar"
    assert p.neto_publicar_ars > 0
    assert round(p.ancho_pct, 2) == round((1595.0 - 1585.0) / 1590.0 * 100, 2)


def test_sin_aviso_que_acepte_el_ticket_queda_none_sin_inventar():
    p = plan_vuelta([_ad("BUY", 1580.0, 900_000, 2_000_000)], TE_COMPRAN,
                    ticket_ars=160_000, fx=1586.0, maker_pct=0.20, taker_flat=0.07,
                    movimientos=[], hoy=date(2026, 9, 10))
    assert p.comprar_a is None
    assert p.neto_tomar_ars is None and p.neto_publicar_ars is None
    assert p.modo is None


def test_cuenta_las_ops_de_hoy_solo_binance_p2p():
    hoy = date(2026, 9, 10)
    movs = [_mov(hoy, "22900000000000000001"),
            _mov(hoy, "22900000000000000002"),
            _mov(hoy, "spot-btcusdt-20260910", "Binance spot / BTC"),  # no cuenta
            _mov(date(2026, 9, 9), "22900000000000000003")]            # ayer
    p = plan_vuelta(TE_VENDEN, TE_COMPRAN, ticket_ars=160_000, fx=1586.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=movs, hoy=hoy,
                    ops_meta=400, ventana_dias=30)
    assert p.ops_hoy == 2
    assert round(p.ops_meta_dia, 2) == 13.33
    assert p.ops_30d == 3


def test_punta_del_libro_sin_filtrar_por_ticket_para_poner_precio_al_anuncio():
    p = plan_vuelta(TE_VENDEN, TE_COMPRAN, ticket_ars=160_000, fx=1586.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=[], hoy=date(2026, 9, 10))
    # el más barato que vende es 1584 (no acepta 160k pero manda en el precio del libro)
    assert p.punta_te_venden == 1584.0
    # el que más paga es 1590 (mínimo alto, pero es la punta)
    assert p.punta_te_compran == 1590.0


def test_un_anzuelo_sin_stock_no_arrastra_la_punta():
    # Un aviso a 1580,56 con 5 USDT no es "el más barato que vende": es un anzuelo.
    venden = [_ad("BUY", 1580.56, 8_000, 50_000, avail=5)] + TE_VENDEN
    compran = TE_COMPRAN + [_ad("SELL", 1599.0, 7_840, 20_000, avail=3)]
    p = plan_vuelta(venden, compran, ticket_ars=160_000, fx=1586.0,
                    maker_pct=0.20, taker_flat=0.07, movimientos=[], hoy=date(2026, 9, 10))
    assert p.punta_te_venden == 1584.0
    assert p.punta_te_compran == 1590.0
