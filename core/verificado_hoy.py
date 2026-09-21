"""Tarjeta "Hoy" del Verificado: la vuelta que conviene AHORA con un ticket dado.

Motor puro, sin red. Recibe los avisos de Binance ya bajados y los movimientos de
trades.db; devuelve el mejor aviso de cada lado que ACEPTE el ticket (mínimo,
máximo y stock por orden), cuánto cuesta la vuelta tomando las dos puntas y
publicándolas, y el conteo de ops de hoy contra el ritmo que pide la meta.

Convención de `p2p_scanner.Ad.side`: "BUY" = avisos de gente que te VENDE (vos
comprás); "SELL" = avisos de gente que te COMPRA (vos vendés).

Cuentas (todo en ARS, por vuelta = 1 compra + 1 venta del mismo ticket):
- tomar:    usdt × (te_compran − te_venden) − 2 × flat × fx
            (el libro suele estar en contra: lo que se paga es el ancho más dos flats)
- publicar: usdt × (te_venden − te_compran) − 2 × maker% × ticket
            (te ponés al precio del mejor de cada lado, cobrás el ancho, pagás dos makers;
             depende de que te tomen LAS DOS puntas)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from core.merchant import _es_binance
from core.p2p_depth import _tomable, filter_traps
from core.puntas import PUNTA_STOCK_MIN_USDT, punta_de_libro

if TYPE_CHECKING:
    from core.movements import Movement


@dataclass(frozen=True)
class Aviso:
    price: float
    min_ars: float
    max_ars: float
    stock_usdt: float
    merchant: str


@dataclass(frozen=True)
class PlanVuelta:
    ticket_ars: float
    ticket_usdt: float
    comprar_a: Aviso | None      # el mejor que te VENDE y acepta el ticket
    vender_a: Aviso | None       # el mejor que te COMPRA y acepta el ticket
    ancho_pct: float | None      # (te_venden − te_compran) / fx × 100
    neto_tomar_ars: float | None
    neto_publicar_ars: float | None
    modo: str | None             # "tomar" | "publicar" | None si falta un lado
    ops_hoy: int
    ops_30d: int
    ops_meta_dia: float
    punta_te_venden: float | None = None   # el más barato del libro, acepte o no el ticket
    punta_te_compran: float | None = None  # el que más paga del libro, acepte o no el ticket


def _acepta(ad, ticket_ars: float) -> bool:
    """El aviso acepta una orden de exactamente `ticket_ars`."""
    if ad.price <= 0:
        return False
    usdt = ticket_ars / ad.price
    return _tomable(ad, usdt) >= usdt * 0.999


def _aviso(ad) -> Aviso:
    return Aviso(price=float(ad.price), min_ars=float(ad.min_amount or 0),
                 max_ars=float(ad.max_amount or 0), stock_usdt=float(ad.available),
                 merchant=getattr(ad, "merchant", "") or "")


def _mejor(ads: list, ticket_ars: float, mas_caro: bool) -> Aviso | None:
    validos = [a for a in filter_traps(list(ads)) if _acepta(a, ticket_ars)]
    if not validos:
        return None
    return _aviso(max(validos, key=lambda a: a.price) if mas_caro
                  else min(validos, key=lambda a: a.price))


# El criterio de punta (stock real detrás del precio) vive en core/puntas.py,
# que es el que usa el tablero. Acá se reusa para no tener dos definiciones.
_punta = punta_de_libro


def plan_vuelta(te_venden: list, te_compran: list, ticket_ars: float, fx: float,
                maker_pct: float, taker_flat: float, movimientos: list,
                hoy: date, ops_meta: int = 400, ventana_dias: int = 30) -> PlanVuelta:
    ticket_usdt = ticket_ars / fx if fx > 0 else 0.0
    comprar_a = _mejor(te_venden, ticket_ars, mas_caro=False)
    vender_a = _mejor(te_compran, ticket_ars, mas_caro=True)
    punta_v = _punta(te_venden, mas_caro=False)
    punta_c = _punta(te_compran, mas_caro=True)

    ancho = tomar = publicar = None
    modo = None
    if comprar_a is not None and vender_a is not None and fx > 0:
        ancho = (comprar_a.price - vender_a.price) / fx * 100.0
        tomar = ticket_usdt * (vender_a.price - comprar_a.price) - 2 * taker_flat * fx
        publicar = (ticket_usdt * (comprar_a.price - vender_a.price)
                    - 2 * (maker_pct / 100.0) * ticket_ars)
        modo = "publicar" if publicar > tomar else "tomar"

    binance = [m for m in movimientos if _es_binance(m)]
    desde = hoy - timedelta(days=ventana_dias)
    ops_hoy = sum(1 for m in binance if m.date == hoy)
    ops_30d = sum(1 for m in binance if desde < m.date <= hoy)

    return PlanVuelta(
        ticket_ars=ticket_ars, ticket_usdt=ticket_usdt,
        comprar_a=comprar_a, vender_a=vender_a, ancho_pct=ancho,
        neto_tomar_ars=tomar, neto_publicar_ars=publicar, modo=modo,
        ops_hoy=ops_hoy, ops_30d=ops_30d,
        ops_meta_dia=ops_meta / ventana_dias if ventana_dias > 0 else float(ops_meta),
        punta_te_venden=punta_v, punta_te_compran=punta_c,
    )
