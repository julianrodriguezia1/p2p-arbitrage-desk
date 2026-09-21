"""Carga un movimiento individual (flujo screenshot) a la planilla, con confirmación."""
import argparse
import json
from datetime import date
from decimal import Decimal

from core.movements import Movement, Side, Source
from core.sheet_writer import SheetWriter, open_spreadsheet, MonthTabNotFound, writer_from_config
from core.trades_db import TradesDB


def movement_from_json(d: dict) -> Movement:
    """Construye un Movement desde un dict (flujo screenshot). source=SCREENSHOT."""
    gross = Decimal(str(d["usd_gross"]))
    commission = Decimal(str(d["commission"]))
    usd_net = Decimal(str(d["usd_net"])) if "usd_net" in d else gross - commission
    return Movement(
        side=Side(d["side"]),
        date=date.fromisoformat(d["date"]),
        order_id=str(d["order_id"]),
        usd_gross=gross,
        commission=commission,
        usd_net=usd_net,
        price=Decimal(str(d["price"])),
        total_ars=Decimal(str(d["total_ars"])),
        exchange_coin=d["exchange_coin"],
        bank=d["bank"],
        source=Source.SCREENSHOT,
    )


def main() -> None:
    import config

    parser = argparse.ArgumentParser(description="Cargar un movimiento P2P a la planilla.")
    parser.add_argument("--json", required=True, help="Movimiento en JSON.")
    parser.add_argument("--yes", action="store_true", help="Saltea la confirmación.")
    args = parser.parse_args()

    m = movement_from_json(json.loads(args.json))
    db = TradesDB(config.TRADES_DB_PATH)

    if db.exists(m.order_id):
        print(f"Ya cargado #{m.order_id}, no hago nada.")
        return

    print(f"[{m.side.value}] {m.date:%d/%m/%y} #{m.order_id} | "
          f"{m.usd_net} {m.exchange_coin} @ {m.price} = {m.total_ars} ARS | {m.bank}")

    if not args.yes and input("¿Cargar a la planilla? [s/N] ").strip().lower() != "s":
        print("Cancelado, no se escribió nada.")
        return

    writer = writer_from_config(config)
    try:
        rng = writer.write_movement(m)
        db.insert(m)
        print(f"OK #{m.order_id} -> {m.month_tab()}!{rng}")
    except MonthTabNotFound as exc:
        print(f"Falta la pestaña '{exc}'. Creala y reintentá.")


if __name__ == "__main__":
    main()
