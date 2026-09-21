"""Asistente de publicación: sugiere precio de anuncio P2P. NO publica nada."""
import sys
from dataclasses import dataclass, field
from decimal import Decimal

from core.movements import Side
from core import pricing
from core.criptoya import Reference

# Lado del anuncio (mi perspectiva) -> trade_type del fetcher para traer rivales.
# Publico para VENDER => mis rivales son los otros vendedores => fetch "BUY".
# Publico para COMPRAR => mis rivales son los otros compradores => fetch "SELL".
RIVAL_TRADE_TYPE = {Side.VENTA: "BUY", Side.COMPRA: "SELL"}
SIDE_MAP = {"vender": Side.VENTA, "comprar": Side.COMPRA}


@dataclass
class Suggestion:
    side: Side
    competitive: Decimal | None
    margin: Decimal | None
    final: Decimal | None
    note: str
    reference_bid: Decimal | None = None
    reference_ask: Decimal | None = None
    reference_bid_exchange: str = ""
    reference_ask_exchange: str = ""
    margin_criptoya: Decimal | None = None


def rival_prices(ads, min_liquidity: Decimal) -> list[Decimal]:
    """Precios de los anuncios rivales con liquidez >= min_liquidity (ARS)."""
    return [
        Decimal(str(a.price)) for a in ads
        if Decimal(str(a.max_amount)) >= min_liquidity
    ]


def suggest(rivals: list[Decimal], cost: Decimal | None, side: Side, *,
            tick: Decimal, margin_pct: Decimal,
            floor: Decimal, ceil: Decimal,
            reference: Reference | None = None) -> Suggestion:
    """Calcula precio competitivo, por margen y final, con avisos."""
    competitive = pricing.competitive_price(rivals, side, tick)
    had_rivals = bool(rivals)
    if competitive is not None:
        competitive = pricing.apply_circuit_breaker(competitive, floor, ceil)

    margin = None
    if side == Side.VENTA and cost is not None:
        margin = pricing.margin_price(cost, margin_pct, side)

    margin_criptoya = None
    note = ""

    if side == Side.VENTA:
        if margin is None:
            final = competitive
            note = "sin costo en trades.db: solo precio competitivo"
        elif competitive is None:
            final = margin
            note = ("sin rivales: publico al piso de margen" if not had_rivals
                    else "precio de mercado fuera de rango (circuit breaker): publico al piso")
        else:
            final = pricing.final_sell_price(competitive, margin)
            if final == margin and margin > competitive:
                note = "el mercado no da tu margen minimo: publico al piso"
        if reference is not None:
            margin_criptoya = pricing.margin_price(reference.best_bid, margin_pct, Side.VENTA)
    else:  # COMPRA
        if reference is not None:
            techo = pricing.margin_price(reference.best_ask, margin_pct, Side.COMPRA)
            margin_criptoya = techo
            candidates = [p for p in (competitive, techo) if p is not None]
            final = min(candidates) if candidates else None
            if final == techo and (competitive is None or techo < competitive):
                note = f"techo CriptoYa manda ({reference.best_ask_exchange})"
            else:
                note = f"dentro del techo CriptoYa ({reference.best_ask_exchange})"
        else:
            final = competitive
            note = "CriptoYa no disponible: solo precio competitivo"

    if final is None:
        note = "sin datos suficientes para sugerir un precio"

    s = Suggestion(side, competitive, margin, final, note)
    if reference is not None:
        s.reference_bid = reference.best_bid
        s.reference_ask = reference.best_ask
        s.reference_bid_exchange = reference.best_bid_exchange
        s.reference_ask_exchange = reference.best_ask_exchange
    s.margin_criptoya = margin_criptoya
    return s


def compute_suggestion(side: Side, asset: str, fiat: str, *, margin_pct: Decimal,
                       movements: list, fetch_ads, fetch_ref,
                       tick: Decimal, floor: Decimal, ceil: Decimal,
                       min_liquidity: Decimal, whitelist: set[str],
                       volume: float, cost_day=None) -> Suggestion:
    """Orquesta la sugerencia de precio: fetch ads + rivales + costo + referencia.

    El costo base del margen es el de las COMPRAS de hoy (así el piso protege el
    stock recién comprado y no te sugiere vender por debajo de lo que pagaste).
    Si hoy no compraste, cae al costo promedio histórico. `cost_day` permite fijar
    otro día (default = hoy).
    """
    from datetime import date as _date
    ads = fetch_ads(asset, fiat, RIVAL_TRADE_TYPE[side])
    rivals = rival_prices(ads, min_liquidity)
    today = cost_day or _date.today()
    cb_today = pricing.cost_basis(movements, asset, on=today)
    cost = cb_today.avg_price if cb_today is not None else pricing.avg_cost(movements, asset)
    try:
        reference = fetch_ref(asset, fiat, volume, whitelist=whitelist)
    except Exception:
        reference = None
    return suggest(rivals, cost, side, tick=tick, margin_pct=margin_pct,
                   floor=floor, ceil=ceil, reference=reference)


def suggestion_payload(s: Suggestion, side: Side, asset: str, ad_min: Decimal,
                       ad_max: Decimal, methods: list[str]) -> dict:
    """Serializa una Suggestion a dict con floats (para JSON)."""
    def f(x):
        return float(x) if x is not None else None
    ref = None
    if s.reference_bid is not None:
        ref = {"bid": f(s.reference_bid), "bid_exchange": s.reference_bid_exchange,
               "ask": f(s.reference_ask), "ask_exchange": s.reference_ask_exchange}
    return {
        "side": side.value, "asset": asset,
        "competitive": f(s.competitive), "margin": f(s.margin),
        "final": f(s.final), "note": s.note,
        "reference": ref, "margin_criptoya": f(s.margin_criptoya),
        "ad_min": float(ad_min), "ad_max": float(ad_max), "methods": methods,
        "ad_text": format_report(s, asset=asset, ad_min=ad_min, ad_max=ad_max, methods=methods),
    }


def format_report(s: Suggestion, *, asset: str, ad_min: Decimal,
                  ad_max: Decimal, methods: list[str]) -> str:
    comp = f"{s.competitive:.2f}" if s.competitive is not None else "—"
    marg = f"{s.margin:.2f}" if s.margin is not None else "N/A"
    final = f"{s.final:.2f}" if s.final is not None else "—"
    lines = [
        f"=== Anuncio {s.side.value} {asset} ===",
        f"Precio competitivo : {comp} ARS",
        f"Precio por margen  : {marg} ARS",
        f"-> PRECIO SUGERIDO : {final} ARS",
    ]
    if s.note:
        lines.append(f"   ({s.note})")
    if s.reference_bid is not None and s.reference_ask is not None:
        lines.append(
            f"Referencia CriptoYa: bid {s.reference_bid:.2f} ({s.reference_bid_exchange})"
            f" / ask {s.reference_ask:.2f} ({s.reference_ask_exchange})"
        )
    else:
        lines.append("Referencia CriptoYa: no disponible")
    mc = f"{s.margin_criptoya:.2f}" if s.margin_criptoya is not None else "N/A"
    lines.append(f"Margen vs CriptoYa : {mc} ARS")
    lines += [
        "",
        "--- Anuncio para copiar ---",
        f"{'Vendo' if s.side == Side.VENTA else 'Compro'} {asset} @ {final} ARS",
        f"Min {ad_min} / Max {ad_max} ARS",
        f"Metodos: {', '.join(methods)}",
        "Libero al confirmar acreditacion bancaria real.",
    ]
    return "\n".join(lines)


def main(argv=None) -> None:
    import argparse
    import config
    from p2p_scanner import fetch_binance, MIN_LIQUIDITY_ARS
    from core.trades_db import TradesDB
    from core.criptoya import fetch_reference

    p = argparse.ArgumentParser(description="Sugiere precio de anuncio P2P (no publica).")
    p.add_argument("--side", choices=list(SIDE_MAP), required=True)
    p.add_argument("--asset", default="USDT", choices=["USDT", "BTC"])
    p.add_argument("--fiat", default="ARS")
    p.add_argument("--min", dest="ad_min", type=Decimal, default=config.DEFAULT_AD_MIN_ARS)
    p.add_argument("--max", dest="ad_max", type=Decimal, default=config.DEFAULT_AD_MAX_ARS)
    p.add_argument("--methods", default=",".join(config.DEFAULT_METHODS))
    p.add_argument("--margin", type=Decimal, default=config.MIN_MARGIN_PCT)
    args = p.parse_args(argv)

    side = SIDE_MAP[args.side]
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]

    # Wrapper que preserva el sys.exit en caso de error de red de Binance.
    def fetch_ads_guarded(asset, fiat, trade_type):
        try:
            return fetch_binance(asset, fiat, trade_type)
        except Exception as e:
            sys.exit(
                f"Error al consultar Binance P2P: {e}\n"
                "(Si es 403, es bloqueo de IP: corré desde tu IP residencial.)"
            )

    s = compute_suggestion(
        side, args.asset, args.fiat,
        margin_pct=args.margin,
        movements=TradesDB(config.TRADES_DB_PATH).all_movements(),
        fetch_ads=fetch_ads_guarded,
        fetch_ref=fetch_reference,
        tick=config.TICK_ARS,
        floor=config.PRICE_FLOOR_ARS,
        ceil=config.PRICE_CEIL_ARS,
        min_liquidity=Decimal(str(MIN_LIQUIDITY_ARS)),
        whitelist=config.CRIPTOYA_WHITELIST,
        volume=config.CRIPTOYA_VOLUME,
    )
    print(format_report(s, asset=args.asset, ad_min=args.ad_min, ad_max=args.ad_max,
                        methods=methods))


if __name__ == "__main__":
    main()
