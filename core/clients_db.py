"""CRM de clientes: tabla clients en trades.db (comparte conexión con TradesDB)."""
import sqlite3
from collections import defaultdict
from dataclasses import asdict, dataclass, fields as _fields
from datetime import date as _date
from decimal import Decimal

from .movements import Movement, Side, Source

VALID_STATUSES = frozenset({"prospecto", "contactado", "activo", "inactivo"})
DEFAULT_STATUS = "prospecto"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS clients (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    alias             TEXT NOT NULL DEFAULT '',
    doc_number        TEXT NOT NULL DEFAULT '',
    contact           TEXT NOT NULL DEFAULT '',
    notes             TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL DEFAULT '',
    status            TEXT NOT NULL DEFAULT 'prospecto',
    last_contacted_at TEXT NOT NULL DEFAULT '',
    bank_holder       TEXT NOT NULL DEFAULT '',
    bank_name         TEXT NOT NULL DEFAULT '',
    cbu_cvu           TEXT NOT NULL DEFAULT '',
    bank_alias        TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Campos editables vía update() (no se tocan id/created_at desde afuera).
_EDITABLE = (
    "name", "alias", "doc_number", "contact", "notes", "source", "status",
    "last_contacted_at", "bank_holder", "bank_name", "cbu_cvu", "bank_alias",
)


@dataclass
class Client:
    id: int | None
    name: str
    alias: str = ""
    doc_number: str = ""
    contact: str = ""
    notes: str = ""
    source: str = ""
    status: str = DEFAULT_STATUS
    last_contacted_at: str = ""
    bank_holder: str = ""
    bank_name: str = ""
    cbu_cvu: str = ""
    bank_alias: str = ""
    created_at: str = ""
    updated_at: str = ""


def _row_to_client(row: sqlite3.Row) -> Client:
    return Client(**{f.name: row[f.name] for f in _fields(Client)})


class ClientsDB:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def create(self, c: Client) -> int:
        status = c.status if c.status in VALID_STATUSES else DEFAULT_STATUS
        cur = self._conn.execute(
            """INSERT INTO clients
               (name, alias, doc_number, contact, notes, source, status,
                last_contacted_at, bank_holder, bank_name, cbu_cvu, bank_alias)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c.name, c.alias, c.doc_number, c.contact, c.notes, c.source, status,
             c.last_contacted_at, c.bank_holder, c.bank_name, c.cbu_cvu, c.bank_alias),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get(self, client_id: int) -> Client | None:
        row = self._conn.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
        return _row_to_client(row) if row else None

    def update(self, client_id: int, fields: dict) -> bool:
        sets = {k: v for k, v in fields.items() if k in _EDITABLE}
        if "status" in sets and sets["status"] not in VALID_STATUSES:
            del sets["status"]
        if not sets:
            return self.get(client_id) is not None
        cols = ", ".join(f"{k} = ?" for k in sets)
        cur = self._conn.execute(
            f"UPDATE clients SET {cols}, updated_at = datetime('now') WHERE id = ?",
            (*sets.values(), client_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete(self, client_id: int) -> bool:
        # Las ops del cliente quedan sin dueño (client_id NULL), no se borran.
        self._conn.execute(
            "UPDATE movements SET client_id = NULL WHERE client_id = ?", (client_id,)
        )
        cur = self._conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def mark_contacted(self, client_id: int, on: _date | None = None) -> bool:
        day = (on or _date.today()).isoformat()
        return self.update(client_id, {"last_contacted_at": day})

    def movements_for(self, client_id: int) -> list[Movement]:
        rows = self._conn.execute(
            """SELECT order_id, side, date, usd_gross, commission, usd_net,
                      price, total_ars, exchange_coin, bank, source
               FROM movements WHERE client_id = ? ORDER BY date ASC""",
            (client_id,),
        ).fetchall()
        return [
            Movement(
                order_id=r["order_id"], side=Side(r["side"]),
                date=_date.fromisoformat(r["date"]),
                usd_gross=Decimal(r["usd_gross"]), commission=Decimal(r["commission"]),
                usd_net=Decimal(r["usd_net"]), price=Decimal(r["price"]),
                total_ars=Decimal(r["total_ars"]), exchange_coin=r["exchange_coin"],
                bank=r["bank"], source=Source(r["source"]),
            )
            for r in rows
        ]

    def list_with_summary(self, today: _date | None = None) -> list[dict]:
        today = today or _date.today()
        clients = [
            _row_to_client(r)
            for r in self._conn.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE")
        ]
        by_client: dict[int, list[tuple]] = defaultdict(list)
        for r in self._conn.execute(
            """SELECT client_id, date, side, usd_net, total_ars
               FROM movements WHERE client_id IS NOT NULL"""
        ):
            by_client[r["client_id"]].append(
                (r["date"], r["side"], r["usd_net"], r["total_ars"])
            )
        result: list[dict] = []
        for c in clients:
            ops = sorted(by_client.get(c.id, []), key=lambda t: t[0])
            total = sum((Decimal(t[3]) for t in ops), Decimal("0"))
            last = ops[-1] if ops else None
            row = asdict(c)
            row.update({
                "ops": len(ops),
                "total_ars": float(total),
                "last_date": last[0] if last else None,
                "last_side": last[1] if last else None,
                "last_usd": float(Decimal(last[2])) if last else None,
                "last_ars": float(Decimal(last[3])) if last else None,
                "days_since": (today - _date.fromisoformat(last[0])).days if last else None,
            })
            result.append(row)
        return result
