"""Funciones puras de pricing para el asistente de publicación. Sin red."""
import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from core.movements import Movement, Side


@dataclass(frozen=True)
class CostBasis:
    """Resumen de costo de las COMPRAS de un asset (opcionalmente de un día)."""
    count: int          # cantidad de compras
    units: Decimal      # USDT neto comprado (con comisiones descontadas)
    total_ars: Decimal  # ARS realmente gastado
    avg_price: Decimal  # ARS por USDT neto = precio para salir even


def cost_basis(movements: list[Movement], asset: str, *,
               on: date | None = None) -> CostBasis | None:
    """Costo de las COMPRAS del asset. Si `on` se pasa, solo las de ese día.

    avg_price = total_ars / units (pondera por unidades recibidas) y es el
    precio mínimo para salir even al vender. None si no hay compras.
    """
    buys = [
        m for m in movements
        if m.side == Side.COMPRA and asset.upper() in m.exchange_coin.upper()
        and (on is None or m.date == on)
    ]
    total_units = sum((m.usd_net for m in buys), Decimal(0))
    if not total_units:
        return None
    total_ars = sum((m.total_ars for m in buys), Decimal(0))
    return CostBasis(len(buys), total_units, total_ars, total_ars / total_units)


@dataclass(frozen=True)
class DayPosition:
    """Flujo de inventario de un asset (opcionalmente de un día)."""
    bought: Decimal  # USDT que entró por compras (gross - comisión)
    sold: Decimal    # USDT que salió por ventas (gross + comisión)
    stock: Decimal   # bought - sold (neto del período)


def day_position(movements: list[Movement], asset: str, *,
                 on: date | None = None) -> DayPosition:
    """Stock neto del asset = comprado - vendido (mismo criterio que la dashboard).

    Compra suma las unidades que entran (gross - comisión); venta resta las que
    salen de la billetera (gross + comisión). Si `on` se pasa, solo ese día.
    """
    ms = [
        m for m in movements
        if asset.upper() in m.exchange_coin.upper()
        and (on is None or m.date == on)
    ]
    bought = sum((m.usd_gross - m.commission for m in ms if m.side == Side.COMPRA),
                 Decimal(0))
    sold = sum((m.usd_gross + m.commission for m in ms if m.side == Side.VENTA),
               Decimal(0))
    return DayPosition(bought, sold, bought - sold)


def avg_cost(movements: list[Movement], asset: str) -> Decimal | None:
    """Costo promedio ponderado (ARS por unidad) de las COMPRAS del asset.

    Pondera por usd_net (unidades realmente recibidas). None si no hay compras.
    """
    cb = cost_basis(movements, asset)
    return cb.avg_price if cb is not None else None


def period_bounds(kind: str, today: date) -> tuple[date, date]:
    """Rango de fechas inclusivo para un período. ValueError si kind es inválido.

    'hoy'    -> (today, today)
    'semana' -> lunes a domingo que contiene today (semana calendario ISO).
    'mes'    -> primer a último día del mes calendario de today.
    """
    if kind == "hoy":
        return today, today
    if kind == "semana":
        monday = today - timedelta(days=today.weekday())
        return monday, monday + timedelta(days=6)
    if kind == "mes":
        last = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=1), today.replace(day=last)
    raise ValueError(f"período inválido: {kind!r}")


@dataclass(frozen=True)
class PeriodAvg:
    """Precio promedio de un lado/asset en un rango de fechas (ARS por unidad bruta)."""
    side: Side
    count: int          # cantidad de operaciones
    units: Decimal      # USDT bruto operado
    total_ars: Decimal  # ARS total
    avg_price: Decimal  # total_ars / units = precio real por moneda


def period_average(movements: list[Movement], asset: str, side: Side, *,
                   start: date, end: date) -> PeriodAvg | None:
    """Precio promedio del lado/asset entre start y end (inclusivos).

    avg_price = total_ars / usd_gross (pondera por unidades BRUTAS, no netas):
    es el precio real por moneda en la orden y nunca supera el máximo individual.
    None si no hay operaciones de ese lado en el rango.
    """
    ops = [
        m for m in movements
        if m.side == side and asset.upper() in m.exchange_coin.upper()
        and start <= m.date <= end
    ]
    total_units = sum((m.usd_gross for m in ops), Decimal(0))
    if not total_units:
        return None
    total_ars = sum((m.total_ars for m in ops), Decimal(0))
    return PeriodAvg(side, len(ops), total_units, total_ars, total_ars / total_units)


def competitive_price(rival_prices: list[Decimal], side: Side,
                      tick: Decimal) -> Decimal | None:
    """Precio para superar a la competencia por 1 tick.

    VENDER: min(rivales) - tick (ser el más barato => vendés primero).
    COMPRAR: max(rivales) + tick (ser el que más paga).
    None si no hay rivales.
    """
    if not rival_prices:
        return None
    if side == Side.VENTA:
        return min(rival_prices) - tick
    return max(rival_prices) + tick


def margin_price(cost: Decimal, margin_pct: Decimal, side: Side) -> Decimal:
    """Precio por margen sobre el costo. VENDER suma, COMPRAR resta."""
    factor = margin_pct / Decimal(100)
    if side == Side.VENTA:
        return cost * (Decimal(1) + factor)
    return cost * (Decimal(1) - factor)


def apply_circuit_breaker(price: Decimal, floor: Decimal,
                          ceil: Decimal) -> Decimal | None:
    """None si price está fuera de [floor, ceil] (precio absurdo / dato roto).

    Raises ValueError si floor > ceil (misconfiguration).
    """
    if floor > ceil:
        raise ValueError("floor > ceil")
    return price if floor <= price <= ceil else None


def final_sell_price(competitive: Decimal, margin_floor: Decimal) -> Decimal:
    """Lado vender: competís salvo que cruces el piso de margen."""
    return max(competitive, margin_floor)
