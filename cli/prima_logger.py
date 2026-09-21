"""Logger de la prima cripto/ARS: muestrea los libros P2P y registra a CSV.

Para responder lo que hoy NO sabemos (ver docs/investigacion-prima-btc-alts-ars.md):
¿el +1,2% que paga el BTC contra pesos es estable? ¿se abre de noche, los fines
de semana? ¿cuántos avisos lo sostienen en cada momento?

Registra las DOS puntas de cada activo, su fx implícito, la prima contra el USDT
del mismo momento, y —clave— cuántos avisos y cuánta profundidad hay detrás. Sin
eso no se puede distinguir una prima real de un libro vacío (el 9,8% de OKX).

NO opera ni publica nada: sólo lee precios públicos.

    python -m cli.prima_logger --once                    # una muestra
    python -m cli.prima_logger --interval 900            # loop cada 15 min
    python -m cli.prima_logger --interval 900 --assets BTC ETH
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.prima_alt import implied_fx
from core.p2p_depth import compute_depth_quote

# Argentina = UTC-3 fijo (sin DST desde 2009). Igual criterio que cli/spread_logger.
ART = timezone(timedelta(hours=-3), "ART")

DEFAULT_CSV = Path("data/prima_log.csv")
DEFAULT_ASSETS = ["BTC", "ETH", "USDT"]

CSV_HEADER = [
    "timestamp_art", "weekday", "hour", "asset", "venue",
    "spot_usd", "ask_ars", "bid_ars", "ask_fx", "bid_fx",
    "usdt_ask", "usdt_bid", "prima_ask_pct", "prima_bid_pct", "ancho_pct",
    "n_ask", "n_bid", "depth_ask_usd", "depth_bid_usd",
]


@dataclass(frozen=True)
class Muestra:
    """Una lectura cruda de un libro, antes de convertirla en fila."""
    asset: str
    venue: str
    spot_usd: float
    ask_ars: float | None
    bid_ars: float | None
    usdt_ask: float
    usdt_bid: float
    n_ask: int
    n_bid: int
    depth_ask_usd: float
    depth_bid_usd: float


#: Ticket de referencia del histórico: el precio que se guarda es el
#: ejecutable para este tamaño, para que la serie sea comparable en el tiempo.
DEPTH_TICKET_USD: float = 1000.0


def _num(x: float | None, d: int = 4) -> str:
    """Celda numérica; vacía si el dato no existe (no se inventa un 0)."""
    return "" if x is None else f"{x:.{d}f}"


def prima_row(m: Muestra, now: datetime) -> dict:
    """Arma la fila de CSV desde una lectura. `now` va en ART."""
    ask_fx = implied_fx(m.ask_ars, m.spot_usd) if m.ask_ars else None
    bid_fx = implied_fx(m.bid_ars, m.spot_usd) if m.bid_ars else None
    prima_ask = None if ask_fx is None else (ask_fx / m.usdt_ask - 1) * 100
    prima_bid = None if bid_fx is None else (bid_fx / m.usdt_bid - 1) * 100
    ancho = None if (ask_fx is None or bid_fx is None) else (ask_fx / bid_fx - 1) * 100
    return {
        "timestamp_art": now.isoformat(timespec="seconds"),
        "weekday": now.strftime("%a"),
        "hour": now.hour,
        "asset": m.asset,
        "venue": m.venue,
        "spot_usd": _num(m.spot_usd, 2),
        "ask_ars": _num(m.ask_ars, 2),
        "bid_ars": _num(m.bid_ars, 2),
        "ask_fx": _num(ask_fx),
        "bid_fx": _num(bid_fx),
        "usdt_ask": _num(m.usdt_ask),
        "usdt_bid": _num(m.usdt_bid),
        "prima_ask_pct": _num(prima_ask),
        "prima_bid_pct": _num(prima_bid),
        "ancho_pct": _num(ancho),
        "n_ask": m.n_ask,
        "n_bid": m.n_bid,
        "depth_ask_usd": _num(m.depth_ask_usd, 2),
        "depth_bid_usd": _num(m.depth_bid_usd, 2),
    }


def append_row(path, row: dict) -> None:
    """Agrega la fila al CSV; escribe el header sólo si el archivo es nuevo."""
    path = Path(path)
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new:
            w.writeheader()
        w.writerow(row)


# --- Lectura en vivo (se importa tarde para que los tests no toquen la red) ---

def leer_libro(venue: str, asset: str, spot_usd: float,
               usdt_ask: float, usdt_bid: float, rows: int = 20) -> Muestra | None:
    """Una lectura de las dos puntas de `asset` en `venue`."""
    from cli.prima_alt import FETCHERS
    fn = FETCHERS[venue]

    def lado(trade_type: str):
        try:
            return [a for a in fn(asset, "ARS", trade_type, rows=rows)
                    if a.price > 0 and a.orders > 0]
        except Exception:
            return []

    vende, compra = lado("BUY"), lado("SELL")
    if not vende and not compra:
        return None
    # Precio EJECUTABLE por profundidad, no la punta cruda. La punta miente: un
    # aviso trampa de Bybit a ~1.420 (mercado en 1.580) se coló en el 99,7% de
    # las filas desde el 31/08/2026 y daba anchos de -10,9%, arruinando toda
    # conclusión de horarios. Mismo motor que cli/rutas y el dashboard.
    q = compute_depth_quote(vende, compra, DEPTH_TICKET_USD)
    return Muestra(
        asset=asset, venue=venue, spot_usd=spot_usd,
        ask_ars=q["ask"],
        bid_ars=q["bid"],
        usdt_ask=usdt_ask, usdt_bid=usdt_bid,
        n_ask=len(vende), n_bid=len(compra),
        depth_ask_usd=sum(a.available for a in vende) * spot_usd,
        depth_bid_usd=sum(a.available for a in compra) * spot_usd,
    )


def sample_once(path, *, venue: str, assets: list[str],
                now_fn=lambda: datetime.now(ART)) -> int:
    """Una ronda: lee cada activo y escribe una fila por cada uno.

    El USDT del MISMO momento es la referencia de todas las primas de la ronda:
    tomarlo una sola vez evita comparar un BTC de ahora contra un USDT de antes.
    """
    from cli.prima_alt import spot_usd

    ref = leer_libro(venue, "USDT", 1.0, 1.0, 1.0)
    if ref is None or not ref.ask_ars or not ref.bid_ars:
        print("[prima_logger] sin libro de USDT — se saltea la ronda", flush=True)
        return 0
    u_ask, u_bid = ref.ask_ars, ref.bid_ars

    now = now_fn()
    escritas = 0
    for asset in assets:
        px = 1.0 if asset.upper() == "USDT" else spot_usd(asset)
        if px is None:
            print(f"[prima_logger] {asset}: sin precio spot — FALTA", flush=True)
            continue
        m = leer_libro(venue, asset, px, u_ask, u_bid)
        if m is None:
            continue
        append_row(path, prima_row(m, now))
        escritas += 1
    return escritas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    # --venues (plural) es lo que se usa; --venue queda por compatibilidad con
    # la unit de systemd vieja, que se sigue deployando hasta el próximo pull.
    ap.add_argument("--venues", nargs="+", default=None)
    ap.add_argument("--venue", default=None)
    ap.add_argument("--assets", nargs="+", default=DEFAULT_ASSETS)
    ap.add_argument("--once", action="store_true", help="una sola muestra y sale")
    ap.add_argument("--interval", type=int, default=900,
                    help="segundos entre muestras (default 900 = 15 min)")
    args = ap.parse_args(argv)

    assets = [a.upper() for a in args.assets]
    venues = args.venues or ([args.venue] if args.venue else ["binance"])

    def ronda() -> int:
        """Una vuelta por todos los venues. Un venue caído (451, timeout) no
        puede llevarse puestos a los demás: por eso el try es por venue."""
        total = 0
        for v in venues:
            try:
                total += sample_once(args.csv, venue=v, assets=assets)
            except Exception as e:
                print(f"[prima_logger] {v}: se saltea la ronda ({e})", flush=True)
        return total

    if args.once:
        print(f"[prima_logger] {ronda()} filas -> {args.csv}")
        return 0

    print(f"[prima_logger] loop cada {args.interval}s sobre {assets} en "
          f"{venues} -> {args.csv}. Ctrl-C para cortar.", flush=True)
    while True:
        try:
            n = ronda()
            print(f"[prima_logger] {datetime.now(ART):%Y-%m-%d %H:%M:%S} "
                  f"{n} filas", flush=True)
        except KeyboardInterrupt:
            print("[prima_logger] cortado")
            return 0
        except Exception as e:                      # una ronda que falla no mata el log
            print(f"[prima_logger] error en la ronda: {e}", flush=True)
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
