"""Trae órdenes P2P nuevas de Bybit, confirma y las carga en la planilla."""
import argparse
from datetime import date

from core.movements import Movement
from core.bybit_p2p import BybitP2PClient, order_to_movement
from core.sheet_writer import SheetWriter, open_spreadsheet, MonthTabNotFound, writer_from_config
from core.trades_db import TradesDB
from cli.sync_binance import select_new_movements, filter_by_date

COMPLETED_STATUS = 50


def _fetch_all(client: BybitP2PClient) -> list[Movement]:
    raw = client.fetch_all_orders()
    completed = [o for o in raw if int(o.get("status", 0)) == COMPLETED_STATUS]
    return [order_to_movement(o) for o in completed]


def _print_movement(m: Movement) -> None:
    print(f"  [{m.side.value}] {m.date:%d/%m/%y} #{m.order_id} | "
          f"{m.usd_net} {m.exchange_coin} @ {m.price} = {m.total_ars} ARS | {m.bank}")


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sincroniza órdenes P2P de Bybit a la planilla.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--today", action="store_true", help="Solo los movimientos de hoy.")
    g.add_argument("--date", metavar="YYYY-MM-DD", help="Solo los movimientos de esa fecha.")
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

    client = BybitP2PClient(config.BYBIT_API_KEY, config.BYBIT_API_SECRET)
    db = TradesDB(config.TRADES_DB_PATH)
    writer = writer_from_config(config)

    nuevos = select_new_movements(_fetch_all(client), db.all_order_ids())
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
