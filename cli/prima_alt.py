"""Dónde está la prima: rankea qué activo conviene PUBLICAR contra pesos.

Mide, en vivo, cuánto más caro que el USDT se paga cada activo en los libros P2P
en ARS, y calcula el neto de la jugada "me fondeo en USDT, convierto en spot y
publico la venta". Descuenta el maker de cada venue y el fee de spot, y compara
el margen contra la volatilidad del activo durante una orden P2P.

    python -m cli.prima_alt                       # Binance, activos por defecto
    python -m cli.prima_alt --venues binance bybit okx
    python -m cli.prima_alt --assets BTC ETH --solo-creibles

No publica nada: es un tablero de lectura.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

import config
import p2p_scanner as scanner
from core.prima_alt import MIN_COMPETIDORES, jugada_publicar, prima, rankear

FETCHERS = {
    "binance": scanner.fetch_binance,
    "bybit": scanner.fetch_bybit,
    "okx": scanner.fetch_okx,
    "bitget": scanner.fetch_bitget,
    "kucoin": scanner.fetch_kucoin,
}
# Clave de fee en config para cada venue del scanner.
FEE_KEY = {"binance": "binancep2p", "bybit": "bybitp2p", "okx": "okexp2p",
           "bitget": "bitgetp2p", "kucoin": "kucoinp2p"}
DEFAULT_ASSETS = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE", "ADA"]
ORDEN_MIN = 20   # minutos que tarda una orden P2P; ventana de riesgo de precio

_SESSION = requests.Session()
_SESSION.headers.update(scanner.BROWSER_HEADERS)


def spot_usd(asset: str) -> float | None:
    """Precio del activo en USD (mid de OKX spot). USDT vale 1 por definición."""
    if asset.upper() in ("USDT", "USDC"):
        return 1.0
    try:
        r = _SESSION.get("https://www.okx.com/api/v5/market/ticker",
                         params={"instId": f"{asset.upper()}-USDT"}, timeout=12)
        d = r.json()["data"][0]
        return (float(d["askPx"]) + float(d["bidPx"])) / 2
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


def vol_p90(asset: str, minutos: int = ORDEN_MIN) -> float | None:
    """Percentil 90 del movimiento absoluto del activo en `minutos`, en %."""
    if asset.upper() in ("USDT", "USDC"):
        return 0.0
    try:
        r = _SESSION.get("https://www.okx.com/api/v5/market/candles",
                         params={"instId": f"{asset.upper()}-USDT",
                                 "bar": "1m", "limit": 300}, timeout=15)
        c = [float(x[4]) for x in reversed(r.json().get("data", []))]
    except (requests.RequestException, KeyError, ValueError):
        return None
    if len(c) < minutos + 30:
        return None
    mv = sorted(abs(c[i + minutos] / c[i] - 1) * 100 for i in range(len(c) - minutos))
    return mv[int(len(mv) * 0.90)]


def _mejor(ads, side: str) -> float | None:
    """Mejor punta real: descarta precio 0 y contrapartes sin historial."""
    vivos = [a for a in ads if a.price > 0 and a.orders > 0]
    if not vivos:
        return None
    return min(a.price for a in vivos) if side == "ask" else max(a.price for a in vivos)


def puntas(venue: str, asset: str, rows: int = 20):
    """(ask, bid, n_ask): las puntas en ARS y cuántos avisos vivos hay del lado
    que voy a disputar. n_ask es el que decide si la prima es creíble."""
    fn = FETCHERS[venue]
    try:
        vende = [a for a in fn(asset, "ARS", "BUY", rows=rows)
                 if a.price > 0 and a.orders > 0]
    except Exception:
        vende = []
    try:
        compra = fn(asset, "ARS", "SELL", rows=rows)
    except Exception:
        compra = []
    ask = min((a.price for a in vende), default=None)
    bid = _mejor(compra, "bid")
    return ask, bid, len(vende)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venues", nargs="+", default=["binance"], choices=list(FETCHERS))
    ap.add_argument("--assets", nargs="+", default=DEFAULT_ASSETS)
    ap.add_argument("--undercut", type=float, default=0.1,
                    help="%% por debajo del mejor ask para quedar primero (default 0,1)")
    ap.add_argument("--min-cobertura", type=float, default=None,
                    help="descarta jugadas cuyo neto no cubra N veces la volatilidad")
    ap.add_argument("--solo-creibles", action="store_true",
                    help="esconde las primas que se sostienen en un libro vacío")
    args = ap.parse_args(argv)

    assets = [a.upper() for a in args.assets]
    with ThreadPoolExecutor(max_workers=8) as ex:
        px = dict(zip(assets, ex.map(spot_usd, assets)))
        vol = dict(zip(assets, ex.map(vol_p90, assets)))

    jugadas, filas = [], []
    for venue in args.venues:
        u_ask, u_bid, _ = puntas(venue, "USDT")
        if not u_ask or not u_bid:
            print(f"[{venue}] sin libro de USDT — FALTA referencia, se saltea")
            continue
        maker = config.FEE_P2P_BY_MODE.get(FEE_KEY[venue], {}).get("maker_pct", 0.0)
        print(f"\n### {venue}  —  USDT/ARS: comprás a {u_ask:,.2f} / vendés a "
              f"{u_bid:,.2f}  |  maker {maker:.2f}%")
        for asset in assets:
            if px.get(asset) is None:
                print(f"  {asset}: sin precio spot — FALTA"); continue
            ask, bid, n_ask = puntas(venue, asset)
            p = prima(asset, venue, ask_ars=ask, bid_ars=bid, usd_price=px[asset],
                      usdt_ask=u_ask, usdt_bid=u_bid)
            filas.append(p)
            if p.ask_fx is None:
                continue
            jugadas.append(jugada_publicar(
                asset, venue, ask_fx=p.ask_fx, usdt_ask_fx=u_ask, maker_pct=maker,
                spot_fee_pct=config.SPOT_FEE_PCT, undercut_pct=args.undercut,
                vol_p90_pct=vol.get(asset), competidores=n_ask))

    def f(x, w=8, d=2, suf=""):
        return f"{'n/d':>{w}}" if x is None else f"{x:>{w},.{d}f}{suf}"

    print(f"\n{'activo':7}{'venue':9}{'ask fx':>10}{'prima':>8}{'bid fx':>10}"
          f"{'prima':>8}{'ancho':>8}")
    for p in filas:
        print(f"{p.asset:7}{p.venue:9}{f(p.ask_fx,10,1)}{f(p.prima_ask_pct)}"
              f"{f(p.bid_fx,10,1)}{f(p.prima_bid_pct)}{f(p.ancho_pct)}")

    top = rankear(jugadas, min_cobertura=args.min_cobertura,
                  solo_creibles=args.solo_creibles)
    print(f"\n=== JUGADAS: fondearse en USDT y PUBLICAR la venta "
          f"(undercut {args.undercut}%) ===")
    if not top:
        print("  ninguna deja plata ahora mismo.")
    print(f"{'activo':7}{'venue':9}{'costo fx':>10}{'vendo fx':>10}{'bruto':>8}"
          f"{'NETO':>8}{'vol20m':>9}{'cobert':>8}{'avisos':>7}  libro")
    for j in top:
        cob = "n/d" if j.cobertura is None else f"{j.cobertura:.1f}x"
        if j.creible is None:
            libro = "sin medir"
        elif j.creible:
            libro = "real"
        else:
            libro = "!! VACIO — prima de fantasía, nadie la disputa"
        print(f"{j.asset:7}{j.venue:9}{j.costo_fx:>10,.1f}{j.vender_fx:>10,.1f}"
              f"{j.bruto_pct:>7.2f}%{j.neto_pct:>7.2f}%{f(j.vol_p90_pct,8,2)}%"
              f"{cob:>8}{str(j.competidores):>7}  {libro}")
    print("\ncobertura = NETO / cuánto se mueve el activo en 20 min (p90). "
          "Abajo de ~2x el ruido se come el margen.")
    print(f"libro = avisos vivos en la punta a disputar; menos de "
          f"{MIN_COMPETIDORES} no sostiene su propia prima.")
    print("OJO: el maker de BTC/alts en Binance NO está publicado — se asume el "
          "0,20% del USDT (FALTA verificar logueado en binance.com/en/fee/p2pFeeRate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
