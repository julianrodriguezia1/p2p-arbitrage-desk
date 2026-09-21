"""Lógica pura de alertas de spread (sin red)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.criptoya import ArbRoute
    from core.arb_matrix import Route


@dataclass(frozen=True)
class Opportunity:
    kind: str        # "cross" | "intra" | "costo"
    route: str       # clave de estado, ej "cross:bybit->binance"
    pct: float       # spread neto %
    threshold: float # umbral aplicado a esta ruta
    title: str       # encabezado del mensaje
    detail: str      # cuerpo del mensaje


def _fmt(n: float) -> str:
    return f"{n:,.1f}"


def evaluate(
    intra: list[tuple[str, float, float, float, float]],
    cross: list[tuple[str, float, str, float, float, float]],
    *,
    stock: float,
    avg_cost_ars: float | None,
    best_bid: float | None,
    cross_pct: float,
    intra_pct: float,
    costo_pct: float,
    hysteresis: float,
    cexp2p_route: "ArbRoute | None" = None,
    cexp2p_pct: float = 1.0,
) -> list[Opportunity]:
    """Candidatos cuyo pct >= umbral - histéresis (encendidos o en la banda)."""
    out: list[Opportunity] = []

    for buy_ex, buy_ask, sell_ex, sell_bid, net_ars, pct in cross:
        if pct >= cross_pct - hysteresis:
            out.append(Opportunity(
                kind="cross",
                route=f"cross:{buy_ex}->{sell_ex}",
                pct=pct,
                threshold=cross_pct,
                title="🟢 Spread cross-exchange",
                detail=(
                    f"Comprar en {buy_ex} @ {_fmt(buy_ask)}\n"
                    f"Vender en {sell_ex} @ {_fmt(sell_bid)}\n"
                    f"Ganancia neta: {pct:+.2f}% (~${net_ars:,.0f} / 1000 USDT)"
                ),
            ))

    for ex, ask, bid, _spread, pct in intra:
        if pct >= intra_pct - hysteresis:
            out.append(Opportunity(
                kind="intra",
                route=f"intra:{ex}",
                pct=pct,
                threshold=intra_pct,
                title="🔵 Spread intra-exchange",
                detail=(
                    f"Comprar y vender en {ex}\n"
                    f"Compra @ {_fmt(ask)} · Venta @ {_fmt(bid)}\n"
                    f"Spread: {pct:+.2f}%"
                ),
            ))

    if stock > 0 and avg_cost_ars is not None and best_bid is not None:
        pct = (best_bid - avg_cost_ars) / avg_cost_ars * 100
        if pct >= costo_pct - hysteresis:
            out.append(Opportunity(
                kind="costo",
                route="costo",
                pct=pct,
                threshold=costo_pct,
                title="💰 Buen precio de venta vs tu costo",
                detail=(
                    f"El mercado paga {_fmt(best_bid)}\n"
                    f"Tu costo promedio: {_fmt(avg_cost_ars)}\n"
                    f"Ganás {pct:+.2f}% si vendés ahora"
                ),
            ))

    if cexp2p_route is not None and cexp2p_route.gross_pct >= cexp2p_pct - hysteresis:
        out.append(Opportunity(
            kind="cexp2p",
            route="cexp2p",
            pct=cexp2p_route.gross_pct,
            threshold=cexp2p_pct,
            title="🌐 Spread CEX→P2P (CriptoYa)",
            detail=(
                f"Comprar en {cexp2p_route.buy_ex} @ {_fmt(cexp2p_route.buy_ask)} → "
                f"vender en {cexp2p_route.sell_ex} @ {_fmt(cexp2p_route.sell_bid)}\n"
                f"Bruto: {cexp2p_route.gross_pct:+.2f}% (antes de comisiones)"
            ),
        ))

    return out


def diff_state(
    candidates: list[Opportunity],
    prev_active: set[str],
    *,
    hysteresis: float,
) -> tuple[list[Opportunity], set[str]]:
    """Edge-triggered state machine con histeresis.

    Devuelve (nuevos_avisos, nuevo_set_activo).
    Una ruta avisa solo si pasa de inactiva a pct >= threshold.
    Sigue activa (sin avisar) mientras pct >= threshold - hysteresis.
    Se apaga si cae por debajo.
    """
    new_active: set[str] = set()
    alerts: list[Opportunity] = []

    for c in candidates:
        was_active = c.route in prev_active
        if c.pct >= c.threshold:
            # Pasa el umbral: activar y alertar si era nueva
            new_active.add(c.route)
            if not was_active:
                alerts.append(c)
        elif was_active and c.pct >= c.threshold - hysteresis:
            # En la banda de histeresis: sigue encendida, sin nuevo aviso
            new_active.add(c.route)
        # Si no, queda apagada (no se agrega a new_active)

    return alerts, new_active


def load_state(path: Path) -> set[str]:
    """Lee el JSON {"active": [...]} de persistencia de estado.

    Si falta el archivo o está corrupto, devuelve set() vacío.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return set(data.get("active", []))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()


def save_state(path: Path, active: set[str]) -> None:
    """Escribe el estado activo como {"active": sorted(active)} en JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"active": sorted(active)}), encoding="utf-8")


def format_message(alerts: list[Opportunity]) -> str:
    """Formatea alertas para Telegram: title + detail separadas por línea en blanco.

    Retorna "" si la lista está vacía.
    """
    if not alerts:
        return ""
    return "\n\n".join(f"{a.title}\n{a.detail}" for a in alerts)


_ARB_TITLE: dict[str, str] = {
    "media": "🟡 Arbitraje media espera",
    "mm": "🟠 Market making (dos puntas)",
    "instant": "⚡ Arbitraje instantáneo",
}
_ARB_ESPERA: dict[str, str] = {
    "media": "⏳ esperás de un lado",
    "mm": "⏳⏳ esperás de los dos lados",
    "instant": "⚡ al toque",
}


def _arb_detail(r: "Route") -> str:
    buy_verb = "Comprá tomando" if r.buy_mode == "tomando" else "Comprá publicando"
    sell_verb = "vendé tomando" if r.sell_mode == "tomando" else "vendé publicando"
    return (
        f"{buy_verb} en {r.buy_venue} @ {_fmt(r.buy_price)} → "
        f"{sell_verb} en {r.sell_venue} @ {_fmt(r.sell_price)}\n"
        f"Ganás {r.net_pct:+.2f}% neto · {_ARB_ESPERA[r.kind]}"
    )


def arb_candidates(
    routes: dict[str, "Route"],
    *,
    thresholds: dict[str, float],
    hysteresis: float,
) -> list[Opportunity]:
    """Convierte la mejor ruta de cada jugada en Opportunity (band-filtered).

    La clave de estado (`route`) es el `kind` (media/mm/instant): máx 3 estados
    edge-triggered, sin spam. Emite solo las que superan umbral - histéresis.
    """
    out: list[Opportunity] = []
    for kind, r in routes.items():
        thr = thresholds[kind]
        if r.net_pct >= thr - hysteresis:
            out.append(Opportunity(
                kind=kind,
                route=kind,
                pct=r.net_pct,
                threshold=thr,
                title=_ARB_TITLE[kind],
                detail=_arb_detail(r),
            ))
    return out
