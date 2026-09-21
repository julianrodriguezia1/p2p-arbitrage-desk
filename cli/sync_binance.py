"""Trae órdenes P2P nuevas de Binance, confirma y las carga en la planilla."""
import argparse
from datetime import date, timedelta

from core.movements import Movement
from core.binance_p2p import BinanceP2PClient, order_to_movement
from core.sheet_writer import SheetWriter, open_spreadsheet, MonthTabNotFound, writer_from_config
from core.trades_db import TradesDB


def select_new_movements(movements: list[Movement], existing_ids: set[str]) -> list[Movement]:
    """Filtra los movimientos cuyo order_id ya está cargado (dedupe)."""
    return [m for m in movements if m.order_id not in existing_ids]


def filter_by_date(movements: list[Movement], target: date) -> list[Movement]:
    """Deja solo los movimientos cuya fecha coincide con `target`."""
    return [m for m in movements if m.date == target]


# Binance devuelve sólo los últimos 30 días si no se le pasa rango, así que
# todo lo que no se sincronizó a tiempo se cae de la ventana y queda invisible.
# Con `--desde` se rellena hacia atrás. Ver `core/binance_p2p.fetch_orders_range`.
VENTANA_DIAS = 30


def _desde_por_defecto(hoy: date) -> date:
    return hoy - timedelta(days=VENTANA_DIAS)


def _fetch_all(client: BinanceP2PClient, desde: date | None = None,
               hasta: date | None = None) -> list[Movement]:
    """Órdenes completadas de la ventana. Por defecto, los últimos 30 días."""
    hoy = date.today()
    desde = desde or _desde_por_defecto(hoy)
    hasta = hasta or hoy + timedelta(days=1)
    raw: list[dict] = []
    for trade_type in ("BUY", "SELL"):
        raw.extend(client.fetch_orders_range(trade_type, desde, hasta))
    completed = [o for o in raw if str(o.get("orderStatus", "")).upper() == "COMPLETED"]
    return [order_to_movement(o) for o in completed]


def _print_movement(m: Movement) -> None:
    print(f"  [{m.side.value}] {m.date:%d/%m/%y} #{m.order_id} | "
          f"{m.usd_net} {m.exchange_coin} @ {m.price} = {m.total_ars} ARS | {m.bank}")


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sincroniza órdenes P2P de Binance a la planilla.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Solo los movimientos de hoy.")
    g.add_argument("--date", metavar="YYYY-MM-DD", help="Solo los movimientos de esa fecha.")
    p.add_argument("--desde", metavar="YYYY-MM-DD",
                   help="Desde qué fecha pedirle a Binance (por defecto, 30 "
                        "días atrás). Sirve para rellenar huecos viejos.")
    return p.parse_args(argv)


def _target_date(args: argparse.Namespace) -> date | None:
    if args.today:
        return date.today()
    if args.date:
        return date.fromisoformat(args.date)
    return None


def main(argv=None) -> None:
    import config

    args = _parse_args(argv)
    target = _target_date(args)

    client = BinanceP2PClient(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    db = TradesDB(config.TRADES_DB_PATH)
    writer = writer_from_config(config)

    hoy = date.today()
    desde = date.fromisoformat(args.desde) if args.desde else _desde_por_defecto(hoy)
    if target is not None and target < desde:
        desde = target
    print(f"Pidiendo órdenes desde el {desde:%d/%m/%y} hasta hoy.")
    todas = _fetch_all(client, desde, hoy + timedelta(days=1))
    nuevos = select_new_movements(todas, db.all_order_ids())
    if target is not None:
        nuevos = filter_by_date(nuevos, target)
    if not nuevos:
        cuando = f" para {target:%d/%m/%y}" if target else ""
        print(f"No hay movimientos nuevos{cuando}.")
        return

    print(f"{len(nuevos)} movimiento(s) nuevo(s):")
    for m in nuevos:
        _print_movement(m)

    if input("¿Cargar a la planilla? [s/N] ").strip().lower() != "s":
        print("Cancelado, no se escribió nada.")
        return

    for m in nuevos:
        try:
            rng = writer.write_movement(m)
            db.insert(m)
            print(f"OK #{m.order_id} -> {m.month_tab()}!{rng}")
        except MonthTabNotFound as exc:
            print(f"SALTEADO #{m.order_id}: falta la pestaña '{exc}'. Creala y reintentá.")


if __name__ == "__main__":
    main()
