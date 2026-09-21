"""Log de movimientos en SQLite (registro AFIP) + dedupe por order_id."""
import sqlite3
from datetime import date as _date
from decimal import Decimal
from pathlib import Path

from .movements import Movement, Side, Source

_SCHEMA = """
CREATE TABLE IF NOT EXISTS movements (
    order_id      TEXT PRIMARY KEY,
    side          TEXT NOT NULL,
    date          TEXT NOT NULL,
    usd_gross     TEXT NOT NULL,
    commission    TEXT NOT NULL,
    usd_net       TEXT NOT NULL,
    price         TEXT NOT NULL,
    total_ars     TEXT NOT NULL,
    exchange_coin TEXT NOT NULL,
    bank          TEXT NOT NULL,
    source        TEXT NOT NULL,
    client_id     INTEGER,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


class TradesDB:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._migrate_client_id()
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        """Conexión compartida (la usa ClientsDB para cruzar clients × movements)."""
        return self._conn

    def _migrate_client_id(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(movements)")}
        if "client_id" not in cols:
            self._conn.execute("ALTER TABLE movements ADD COLUMN client_id INTEGER")

    def set_client(self, order_id: str, client_id: int | None) -> bool:
        cur = self._conn.execute(
            "UPDATE movements SET client_id = ? WHERE order_id = ?",
            (client_id, order_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def exists(self, order_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM movements WHERE order_id = ?", (order_id,)
        )
        return cur.fetchone() is not None

    def insert(self, m: Movement) -> None:
        self._conn.execute(
            """INSERT OR IGNORE INTO movements
               (order_id, side, date, usd_gross, commission, usd_net,
                price, total_ars, exchange_coin, bank, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                m.order_id, m.side.value, m.date.isoformat(),
                str(m.usd_gross), str(m.commission), str(m.usd_net),
                str(m.price), str(m.total_ars), m.exchange_coin,
                m.bank, m.source.value,
            ),
        )
        self._conn.commit()

    def all_order_ids(self) -> set[str]:
        cur = self._conn.execute("SELECT order_id FROM movements")
        return {row[0] for row in cur.fetchall()}

    def client_ids(self) -> dict[str, int | None]:
        """Mapa order_id -> client_id (None si la op no tiene cliente asignado)."""
        cur = self._conn.execute("SELECT order_id, client_id FROM movements")
        return {row[0]: row[1] for row in cur.fetchall()}

    def all_movements(self) -> list[Movement]:
        cur = self._conn.execute(
            """SELECT order_id, side, date, usd_gross, commission, usd_net,
                      price, total_ars, exchange_coin, bank, source
               FROM movements ORDER BY date DESC"""
        )
        return [
            Movement(
                order_id=r[0],
                side=Side(r[1]),
                date=_date.fromisoformat(r[2]),
                usd_gross=Decimal(r[3]),
                commission=Decimal(r[4]),
                usd_net=Decimal(r[5]),
                price=Decimal(r[6]),
                total_ars=Decimal(r[7]),
                exchange_coin=r[8],
                bank=r[9],
                source=Source(r[10]),
            )
            for r in cur.fetchall()
        ]

    def delete(self, order_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM movements WHERE order_id = ?", (order_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0
