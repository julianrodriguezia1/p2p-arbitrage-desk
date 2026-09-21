"""Oneshot: escanea spreads y avisa a Telegram lo nuevo (edge-triggered).

Uso: python -m cli.spread_alert --once
Pensado para correr cada 15 min vía systemd timer en el VPS.
"""
from __future__ import annotations

import argparse
from typing import Callable

import config
from core import pricing
from core.spread_alert import (
    diff_state, evaluate, format_message, load_state, save_state,
)
from core.trades_db import TradesDB
from p2p_scanner import find_opportunities, scan, send_telegram, FETCHERS
from core.p2p_depth import compute_depth_quote
from core import arb_matrix
from core.spread_alert import arb_candidates

ASSET = "USDT"
FIAT = "ARS"


def _piso(umbral: float) -> float:
    """Ningun umbral avisa por debajo de config.SPREAD_ALERT_MIN_PCT.

    Los umbrales por regla viven en el .env del VPS; uno viejo mas bajo seguiria
    mandando avisos que el usuario no quiere ver. El piso se aplica aca, en el
    unico lugar donde se leen todos.
    """
    return max(umbral, config.SPREAD_ALERT_MIN_PCT)


def _arb_thresholds() -> dict[str, float]:
    """Umbrales de las 3 jugadas de arbitraje, ya pisados."""
    return {
        "media": _piso(config.SPREAD_ALERT_MEDIA_PCT),
        "mm": _piso(config.SPREAD_ALERT_MM_PCT),
        "instant": _piso(config.SPREAD_ALERT_INSTANT_PCT),
    }


def _cost_inputs() -> tuple[float, float | None]:
    """(stock, avg_cost) de USDT desde trades.db; (0.0, None) si falla."""
    try:
        movs = TradesDB(config.TRADES_DB_PATH).all_movements()
        stock = float(pricing.day_position(movs, ASSET).stock)
        avg = pricing.avg_cost(movs, ASSET)
        return stock, (float(avg) if avg is not None else None)
    except Exception as e:  # DB ausente/corrupta: seguimos sin la regla de costo
        print(f"  [!] trades.db no disponible ({type(e).__name__}); salteo regla costo")
        return 0.0, None


def _cexp2p_route():
    """Mejor ruta CEX->P2P de CriptoYa; None si falla (la regla se saltea)."""
    try:
        from core.criptoya import fetch_arbitrage_route
        return fetch_arbitrage_route(
            ASSET, FIAT, config.CRIPTOYA_VOLUME,
            whitelist=config.CRIPTOYA_ARBITRAGE_WHITELIST,
            max_age_min=config.MAX_QUOTE_AGE_MIN,
        )
    except Exception as e:
        print(f"  [!] CriptoYa no disponible ({type(e).__name__}); salteo regla cexp2p")
        return None


def _depth_quotes(volume: float) -> dict[str, dict]:
    """{venue_name: {"ask","bid"}} por profundidad (VWAP) para los 5 P2P.

    Un venue que falle (bloqueo de IP, timeout) se saltea; el resto sigue.
    """
    out: dict[str, dict] = {}
    for venue_name, fetch_key in arb_matrix.P2P_DEPTH_VENUES.items():
        fetcher = FETCHERS.get(fetch_key)
        if fetcher is None:
            continue
        try:
            buy = fetcher(ASSET, FIAT, "BUY", rows=20)
        except Exception:
            buy = []
        try:
            sell = fetcher(ASSET, FIAT, "SELL", rows=20)
        except Exception:
            sell = []
        from core.fees import flat_por_orden
        q = compute_depth_quote(buy, sell, volume, fee_por_orden=flat_por_orden(
            fees_by_venue=config.FEE_P2P_BY_MODE, venue=venue_name, asset=ASSET,
            flat_assets=config.TAKER_FLAT_ASSETS))
        if q["ask"] or q["bid"]:
            out[venue_name] = q
    return out


def _arb_candidates(volume: float):
    """Candidatos de las 3 jugadas cross-venue. [] si no hay datos suficientes."""
    from core.criptoya import fetch_payload
    try:
        payload = fetch_payload(ASSET, FIAT, volume)
    except Exception as e:
        print(f"  [!] CriptoYa payload no disponible ({type(e).__name__})")
        payload = {}
    depth = _depth_quotes(volume)
    cex_venues = set(config.CRIPTOYA_ARBITRAGE_WHITELIST) - set(arb_matrix.P2P_DEPTH_VENUES)
    import time as _t
    venues = arb_matrix.build_venues(
        depth, payload,
        cex_venues=cex_venues,
        blacklist=config.CRIPTOYA_BLACKLIST,
        max_age_min=config.MAX_QUOTE_AGE_MIN,
        now=_t.time(),
        puede_publicar_compra=config.P2P_PUEDE_PUBLICAR_COMPRA,
        puede_publicar_venta=config.P2P_PUEDE_PUBLICAR_VENTA,
        p2p_sin_profundidad=config.P2P_SIN_PROFUNDIDAD,
    )
    if not venues:
        return []
    # El fee de tomador de Binance es un flat de 0,07 USDT: su peso en % depende
    # del tamano del ticket, asi que la tabla se arma por volumen.
    from core.fees import por_modo
    fee_modo = por_modo(fees_by_venue=config.FEE_P2P_BY_MODE, volume=volume,
                        asset=ASSET, flat_assets=config.TAKER_FLAT_ASSETS)
    routes = arb_matrix.best_routes(venues, fee_pct=config.FEE_PCT_BY_VENUE,
                                    fee_by_mode=fee_modo)
    return arb_candidates(
        routes,
        thresholds=_arb_thresholds(),
        hysteresis=config.SPREAD_ALERT_HYSTERESIS_PCT,
    )


def run_once(
    *,
    scan_fn: Callable[[str, str], list] | None = None,
    send_fn: Callable[[str, str, str], None] | None = None,
    route_fn: Callable[[], object] | None = None,
    arb_fn: Callable[[float], list] | None = None,
) -> int:
    """Una pasada. Devuelve cuántos avisos se mandaron."""
    scan_fn = scan_fn or scan
    send_fn = send_fn or send_telegram
    route_fn = route_fn or _cexp2p_route
    arb_fn = arb_fn or _arb_candidates

    quotes = scan_fn(ASSET, FIAT)
    hyst = config.SPREAD_ALERT_HYSTERESIS_PCT

    if quotes:
        intra, cross = find_opportunities(quotes, ASSET)
        best_bid = max((q.best_bid for q in quotes if q.best_bid), default=None)
        stock, avg = _cost_inputs()
        cexp2p_route = route_fn()
        candidates = evaluate(
            intra, cross,
            stock=stock, avg_cost_ars=avg, best_bid=best_bid,
            cross_pct=_piso(config.SPREAD_ALERT_CROSS_PCT),
            intra_pct=_piso(config.SPREAD_ALERT_INTRA_PCT),
            costo_pct=_piso(config.SPREAD_ALERT_COSTO_PCT),
            hysteresis=hyst,
            cexp2p_route=cexp2p_route,
            cexp2p_pct=_piso(config.SPREAD_ALERT_CEXP2P_PCT),
        )
    else:
        print("  Sin datos de exchanges P2P. Solo candidatos de arbitraje.")
        candidates = []

    candidates = candidates + arb_fn(config.CRIPTOYA_VOLUME)

    prev = load_state(config.SPREAD_ALERT_STATE_PATH)
    alerts, active = diff_state(candidates, prev, hysteresis=hyst)
    save_state(config.SPREAD_ALERT_STATE_PATH, active)

    if alerts:
        from core.narrate import narrate, default_generate
        send_fn(narrate(alerts, generate=default_generate()), config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID)
        print(f"  {len(alerts)} aviso(s) enviado(s).")
    else:
        print("  Sin oportunidades nuevas.")
    return len(alerts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Alertas de spread P2P a Telegram")
    ap.add_argument("--once", action="store_true", help="una pasada (default)")
    ap.parse_args()
    run_once()


if __name__ == "__main__":
    main()
