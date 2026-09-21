"""El matemático fanático: arma el grafo completo de lo que se puede hacer con
pesos y busca TODOS los ciclos que dejan plata.

No parte de ninguna jugada conocida. Baja los libros P2P de cada venue, los
precios de spot, y construye una arista por cada operación posible:

    tomar compra / tomar venta / publicar compra / publicar venta   (P2P)
    convertir contra USDT                                           (spot)
    mover cripto entre venues                                       (red)

Después busca todos los ciclos `ARS → … → ARS` de hasta N patas y los rankea por
neto, mostrando de qué depende cada uno: cuántas patas necesitan que **te tomen**
el aviso, cuántas transferencias hace, y cuál es el libro más flaco que pisa.

    python -m cli.rutas
    python -m cli.rutas --venues binance bybit okx --max-pasos 4
    python -m cli.rutas --ticket 3000 --solo-creibles

No opera ni publica nada: sólo lee y calcula.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

import config
from core.fees import red_pct
from core.p2p_depth import compute_depth_quote
import p2p_scanner as scanner
from cli.prima_alt import FEE_KEY, FETCHERS
from core.rutas import Paso, buscar, cuello_usd_h, ganancia_ars_h

DEFAULT_ASSETS = ["USDT", "BTC", "ETH"]
DEFAULT_VENUES = ["binance", "bybit", "okx"]

_SESSION = requests.Session()
_SESSION.headers.update(scanner.BROWSER_HEADERS)


def spot_puntas(asset: str) -> tuple[float, float] | None:
    """(ask, bid) del par ASSET/USDT en el spot. USDT contra sí mismo es 1."""
    if asset.upper() == "USDT":
        return (1.0, 1.0)
    try:
        r = _SESSION.get("https://www.okx.com/api/v5/market/ticker",
                         params={"instId": f"{asset.upper()}-USDT"}, timeout=12)
        d = r.json()["data"][0]
        return (float(d["askPx"]), float(d["bidPx"]))
    except (requests.RequestException, KeyError, IndexError, ValueError):
        return None


def libro(venue: str, asset: str, rows: int = 20, ticket_usd: float = 1000.0):
    """(ask, bid, n_ask, n_bid) del libro P2P en ARS, sin contrapartes fantasma.

    El precio es el EJECUTABLE POR PROFUNDIDAD para `ticket_usd`, el mismo que
    usa el dashboard, no la mejor punta absoluta. La punta sola miente: el
    2026-09-07 un aviso de Bybit a 1.422 con 3,2 USDT de stock (contra un
    mercado en 1.580) infló todas las rutas del ranking a +12,72%.
    """
    fn = FETCHERS[venue]

    def lado(tt):
        try:
            return [a for a in fn(asset, "ARS", tt, rows=rows)
                    if a.price > 0 and a.orders > 0]
        except Exception:
            return []

    vende, compra = lado("BUY"), lado("SELL")
    q = compute_depth_quote(vende, compra, ticket_usd)
    return q["ask"], q["bid"], len(vende), len(compra)


def fees_p2p(venue: str, asset: str, ticket_usd: float) -> tuple[float, float]:
    """(maker_pct, taker_pct) efectivos. El flat del tomador se pasa a % usando
    el ticket: 0,07 USDT sobre 1.000 es 0,007%, sobre 100 es 0,07%."""
    f = config.FEE_P2P_BY_MODE.get(FEE_KEY[venue], {})
    maker = f.get("maker_pct", 0.0)
    taker = f.get("taker_pct", 0.0)
    flat = f.get("taker_flat_quote", 0.0)
    if flat and asset.upper() in config.TAKER_FLAT_ASSETS and ticket_usd > 0:
        taker += flat / ticket_usd * 100
    return maker, taker


def armar_grafo(venues: list[str], assets: list[str], ticket_usd: float,
                *, con_red: bool) -> tuple[list[Paso], list[str]]:
    """Todas las aristas posibles. Devuelve (pasos, avisos_de_lo_que_falto)."""
    faltantes: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        spot = dict(zip(assets, ex.map(spot_puntas, assets)))

    pasos: list[Paso] = []
    nodos_cripto: dict[str, list[str]] = {}

    for venue in venues:
        for asset in assets:
            if spot.get(asset) is None:
                faltantes.append(f"{asset}: sin precio de spot")
                continue
            ask, bid, n_ask, n_bid = libro(venue, asset,
                                           ticket_usd=ticket_usd)
            nodo = f"{asset}@{venue}"
            maker, taker = fees_p2p(venue, asset, ticket_usd)
            if ask:
                # Comprar tomando: entrego ARS, recibo 1/ask del activo.
                pasos.append(Paso("ARS", nodo, 1 / ask, taker, "tomar", venue,
                                  avisos=n_ask, asset=asset, lado="ask",
                                  detalle=f"comprás a {ask:,.2f}"))
                # Publicar la venta: entrego el activo y cobro el precio del ask.
                pasos.append(Paso(nodo, "ARS", ask, maker, "publicar", venue,
                                  publica=True, avisos=n_ask, asset=asset,
                                  lado="ask",
                                  detalle=f"publicás venta a {ask:,.2f}"))
            if bid:
                # Vender tomando: entrego el activo, cobro el bid.
                pasos.append(Paso(nodo, "ARS", bid, taker, "tomar", venue,
                                  avisos=n_bid, asset=asset, lado="bid",
                                  detalle=f"vendés a {bid:,.2f}"))
                # Publicar la compra: entrego ARS al precio del bid (más barato).
                pasos.append(Paso("ARS", nodo, 1 / bid, maker, "publicar", venue,
                                  publica=True, avisos=n_bid, asset=asset,
                                  lado="bid",
                                  detalle=f"publicás compra a {bid:,.2f}"))
            if ask or bid:
                nodos_cripto.setdefault(asset, []).append(venue)

        # Spot dentro del venue, siempre contra USDT (es como se hace de verdad).
        if "USDT" not in assets:
            continue
        for asset in assets:
            if asset == "USDT" or spot.get(asset) is None:
                continue
            s_ask, s_bid = spot[asset]
            u, a = f"USDT@{venue}", f"{asset}@{venue}"
            pasos.append(Paso(u, a, 1 / s_ask, config.SPOT_FEE_PCT, "spot", venue,
                              detalle=f"spot: comprás {asset} a {s_ask:,.2f}"))
            pasos.append(Paso(a, u, s_bid, config.SPOT_FEE_PCT, "spot", venue,
                              detalle=f"spot: vendés {asset} a {s_bid:,.2f}"))

    if con_red:
        for asset, vs in nodos_cripto.items():
            for v1 in vs:
                for v2 in vs:
                    if v1 == v2:
                        continue
                    # El fee de red es un FLAT en USDT, no un %: su peso sale
                    # del ticket. Para USDT sale de la tabla medida; para el
                    # resto de los activos no hay dato y queda el % viejo.
                    fee = (red_pct(volume=ticket_usd) if asset == "USDT"
                           else config.STRATEGY_NETWORK_FEE_PCT)
                    pasos.append(Paso(f"{asset}@{v1}", f"{asset}@{v2}", 1.0,
                                      fee, "red", v2,
                                      red=True, detalle=f"mandás {asset} {v1}->{v2}"))
    return pasos, faltantes


def describir(r) -> str:
    return "  ->  ".join(f"[{s.tipo}] {s.detalle or s.destino}" for s in r.pasos)


def main(argv: list[str] | None = None) -> int:
    # La consola de Windows (cp1252) no sabe imprimir "→": sin esto --help revienta.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--venues", nargs="+", default=DEFAULT_VENUES, choices=list(FETCHERS))
    ap.add_argument("--assets", nargs="+", default=DEFAULT_ASSETS)
    ap.add_argument("--max-pasos", type=int, default=4)
    ap.add_argument("--ticket", type=float, default=1000.0,
                    help="tamaño de la operación en USD (define el peso del fee flat)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--solo-creibles", action="store_true",
                    help="esconde las rutas que pisan un libro sin competencia")
    ap.add_argument("--sin-red", action="store_true",
                    help="no considerar transferencias entre venues")
    ap.add_argument("--flujo", default=None,
                    help="JSON {\"BTC_ask\": usd_por_hora, ...} medido; con esto "
                         "rankea por PESOS POR HORA en vez de por %%")
    ap.add_argument("--fx", type=float, default=1590.0,
                    help="ARS por dólar para convertir la ganancia (default 1590)")
    args = ap.parse_args(argv)

    assets = [a.upper() for a in args.assets]
    print(f"armando el grafo: {args.venues} x {assets} (ticket {args.ticket:,.0f} USD)…")
    pasos, faltantes = armar_grafo(args.venues, assets, args.ticket,
                                   con_red=not args.sin_red)
    for f in faltantes:
        print(f"  FALTA {f}")
    nodos = {s.origen for s in pasos} | {s.destino for s in pasos}
    print(f"{len(nodos)} nodos, {len(pasos)} operaciones posibles\n")

    flujo = {}
    if args.flujo:
        with open(args.flujo, encoding="utf-8") as f:
            for k, v in json.load(f).items():
                asset, lado = k.rsplit("_", 1)
                flujo[(asset, lado)] = float(v)

    rutas = buscar(pasos, inicio="ARS", max_pasos=args.max_pasos,
                   solo_creibles=args.solo_creibles)
    if not rutas:
        print("ningún ciclo deja plata ahora mismo.")
        return 0

    def _libro(r):
        return ("?" if r.min_avisos is None
                else ("VACIO" if not r.creible else str(r.min_avisos)))

    if flujo:
        # Con flujo medido manda la plata por hora, no el porcentaje: un 2% sobre
        # un libro que mueve 0 USD/h rinde 0.
        con_plata = [(r, ganancia_ars_h(r, flujo, args.fx)) for r in rutas]
        medidas = sorted([(r, g) for r, g in con_plata if g is not None],
                         key=lambda t: t[1], reverse=True)
        sin_medir = sum(1 for _, g in con_plata if g is None)
        print(f"{len(rutas)} ciclos rentables ({sin_medir} con alguna pata sin "
              f"flujo medido, no rankeables). Top {args.top} por ARS/hora:\n")
        print(f"{'#':>3} {'ARS/hora':>10} {'NETO':>7} {'cuello USD/h':>13} "
              f"{'te tomen':>9} {'libro':>6}  ruta")
        for i, (r, g) in enumerate(medidas[:args.top], 1):
            print(f"{i:>3} {g:>10,.0f} {r.neto_pct:>6.2f}% "
                  f"{cuello_usd_h(r, flujo):>13,.0f} {r.publica_n:>9} "
                  f"{_libro(r):>6}  {' -> '.join(r.nodos)}")
        if medidas:
            rutas = [r for r, _ in medidas]
    else:
        print(f"{len(rutas)} ciclos rentables. Top {args.top}:\n")
        print(f"{'#':>3} {'NETO':>7} {'patas':>6} {'te tomen':>9} {'red':>4} "
              f"{'libro':>6}  ruta")
        for i, r in enumerate(rutas[:args.top], 1):
            print(f"{i:>3} {r.neto_pct:>6.2f}% {len(r.pasos):>6} {r.publica_n:>9} "
                  f"{r.red_n:>4} {_libro(r):>6}  {' -> '.join(r.nodos)}")

    print("\n--- las 3 mejores, en detalle ---")
    for i, r in enumerate(rutas[:3], 1):
        print(f"\n{i}) NETO {r.neto_pct:.2f}%  |  {r.publica_n} pata(s) dependen de "
              f"que te tomen  |  {r.red_n} transferencia(s)  |  "
              f"libro más flaco: {r.min_avisos if r.min_avisos is not None else '?'}")
        for s in r.pasos:
            print(f"     [{s.tipo:9}] {s.venue:8} {s.detalle}"
                  + (f"   (fee {s.fee_pct:.2f}%)" if s.fee_pct else ""))

    print("\nte tomen = patas donde publicás y dependés de que alguien acepte: "
          "el neto es real sólo si se cierran las DOS puntas.")
    print("libro = avisos vivos en la punta más flaca de la ruta; 'VACIO' es "
          "precio que nadie disputa, no oportunidad.")
    print("OJO: el maker de BTC/alts en Binance NO está publicado — se asume el "
          "0,20% del USDT (FALTA verificar en binance.com/en/fee/p2pFeeRate).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
