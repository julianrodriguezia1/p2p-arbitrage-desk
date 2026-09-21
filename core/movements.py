"""Modelo común de un movimiento P2P."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

MONTHS_ES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


class Side(str, Enum):
    COMPRA = "COMPRA"
    VENTA = "VENTA"


class Source(str, Enum):
    BINANCE_API = "binance_api"
    SCREENSHOT = "screenshot"
    BYBIT_API = "bybit_api"


@dataclass(frozen=True)
class Movement:
    side: Side
    date: date
    order_id: str
    usd_gross: Decimal
    commission: Decimal
    usd_net: Decimal
    price: Decimal
    total_ars: Decimal
    exchange_coin: str
    bank: str
    source: Source

    def month_tab(self) -> str:
        """Nombre de la pestaña de la planilla según el mes de la fecha."""
        return MONTHS_ES[self.date.month - 1]
