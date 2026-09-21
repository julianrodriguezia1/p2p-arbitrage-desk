"""Logger de spread USDT/ARS: muestrea CriptoYa y registra a CSV.

Para responder "a qué hora conviene operar". NO opera ni publica nada, solo
lee precios públicos y guarda el mejor spread cross-exchange con timestamp.

Pensado para correr en la nube (GitHub Actions) con `--once` cada 15 min, o
local en loop con `--interval`. La hora se guarda en ART (UTC-3, Argentina no
usa horario de verano) para que el análisis por hora del día sea correcto.
"""
import csv
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from core.criptoya import Reference

# Argentina = UTC-3 fijo (sin DST desde 2009).
ART = timezone(timedelta(hours=-3), "ART")

CSV_HEADER = [
    "timestamp_art", "weekday", "hour",
    "best_ask", "ask_exchange", "best_bid", "bid_exchange",
    "spread_ars", "spread_pct",
]


def spread_row(ref: Reference, now: datetime) -> dict:
    """Arma una fila de log desde una Reference y un timestamp (en ART)."""
    spread_ars = ref.best_bid - ref.best_ask
    spread_pct = (spread_ars / ref.best_ask * 100) if ref.best_ask else Decimal(0)
    return {
        "timestamp_art": now.isoformat(timespec="seconds"),
        "weekday": now.strftime("%a"),
        "hour": now.hour,
        "best_ask": f"{ref.best_ask:.4f}",
        "ask_exchange": ref.best_ask_exchange,
        "best_bid": f"{ref.best_bid:.4f}",
        "bid_exchange": ref.best_bid_exchange,
        "spread_ars": f"{spread_ars:.4f}",
        "spread_pct": f"{spread_pct:.4f}",
    }


def append_row(path: Path, row: dict) -> None:
    """Agrega la fila al CSV; escribe el header solo si el archivo es nuevo."""
    path = Path(path)
    new = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADER)
        if new:
            w.writeheader()
        w.writerow(row)


def sample_once(path, *, fetch_ref, whitelist, volume,
                now_fn=lambda: datetime.now(ART)) -> dict | None:
    """Una muestra: fetch + append. Devuelve la fila, o None si CriptoYa falló."""
    ref = fetch_ref("USDT", "ARS", volume, whitelist=whitelist)
    if ref is None:
        return None
    row = spread_row(ref, now_fn())
    append_row(Path(path), row)
    return row


def main(argv=None) -> None:
    import argparse
    import config
    from core.criptoya import fetch_reference

    p = argparse.ArgumentParser(
        description="Logger de spread USDT/ARS (no opera, solo registra)."
    )
    p.add_argument("--out", default="data/spread_log_usdt_ars.csv",
                   help="ruta del CSV de salida")
    p.add_argument("--once", action="store_true",
                   help="una sola muestra y salir (modo cron/nube)")
    p.add_argument("--interval", type=float, default=15,
                   help="minutos entre muestras en modo loop (default 15)")
    args = p.parse_args(argv)

    def one():
        row = sample_once(
            args.out, fetch_ref=fetch_reference,
            whitelist=config.CRIPTOYA_WHITELIST, volume=config.CRIPTOYA_VOLUME,
        )
        ts = datetime.now(ART).strftime("%Y-%m-%d %H:%M")
        if row is None:
            print(f"{ts} ART — sin datos (CriptoYa no respondió)")
        else:
            print(f"{row['timestamp_art']}  spread {row['spread_pct']}%  "
                  f"compro {row['best_ask']} ({row['ask_exchange']}) / "
                  f"vendo {row['best_bid']} ({row['bid_exchange']})")
        return row

    if args.once:
        one()
        return

    print(f"Logger spread USDT/ARS -> {args.out} (cada {args.interval} min). "
          "Ctrl+C para cortar.")
    while True:
        one()
        time.sleep(args.interval * 60)


if __name__ == "__main__":
    main()
