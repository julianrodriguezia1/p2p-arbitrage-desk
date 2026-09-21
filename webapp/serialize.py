"""Adaptador entre el Movement de la DB y la forma JSON que consume el HTML."""
import uuid
from datetime import date
from decimal import Decimal

from core.movements import Movement, Side, Source

_TYPE_TO_SIDE = {"buy": Side.COMPRA, "sell": Side.VENTA}
_SIDE_TO_TYPE = {Side.COMPRA: "buy", Side.VENTA: "sell"}


def movement_to_dashboard(m: Movement) -> dict:
    """Transforma un Movement de la DB al dict JSON que consume el HTML (tab de movimientos)."""
    gross = m.usd_gross
    comm_pct = float(m.commission / gross * 100) if gross else 0.0
    return {
        "id": m.order_id,
        "opId": m.order_id,
        "type": _SIDE_TO_TYPE[m.side],
        "date": m.date.isoformat(),
        "usdBruto": float(m.usd_gross),
        "commPct": comm_pct,
        "usdNeto": float(m.usd_gross - m.commission),
        "priceArs": float(m.price),
        "totalArs": float(m.total_ars),
        "exchange": m.exchange_coin,
        "bank": m.bank,
        "source": m.source.value,
        "createdAt": 0,  # Constante: el HTML solo lo usa como tiebreaker secundario de orden
    }


def dashboard_to_movement(d: dict, source: Source) -> Movement:
    """Transforma un dict JSON del HTML (captura/edición manual) a un Movement para persistir en la DB."""
    gross = Decimal(str(d["usdBruto"]))
    comm_pct = Decimal(str(d.get("commPct") or 0))
    commission = gross * comm_pct / Decimal("100")
    price = Decimal(str(d["priceArs"]))
    order_id = str(d.get("opId") or "").strip() or f"man-{uuid.uuid4().hex[:12]}"
    return Movement(
        side=_TYPE_TO_SIDE[d["type"]],
        date=date.fromisoformat(d["date"]),
        order_id=order_id,
        usd_gross=gross,
        commission=commission,
        usd_net=gross - commission,
        price=price,
        total_ars=gross * price,
        exchange_coin=d.get("exchange") or "",
        bank=d.get("bank") or "",
        source=source,
    )
