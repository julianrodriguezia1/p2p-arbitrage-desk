from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source
from core.trades_db import TradesDB


def make_movement(order_id="123"):
    return Movement(
        side=Side.COMPRA, date=date(2026, 6, 1), order_id=order_id,
        usd_gross=Decimal("16.92"), commission=Decimal("0.07"),
        usd_net=Decimal("16.85"), price=Decimal("1477"),
        total_ars=Decimal("25000"), exchange_coin="Binance / USDT",
        bank="Lemon Cash", source=Source.BINANCE_API,
    )


def test_insert_y_exists(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    assert db.exists("123") is False
    db.insert(make_movement("123"))
    assert db.exists("123") is True


def test_dedupe_no_duplica_y_preserva_decimal(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("123"))
    db.insert(make_movement("123"))  # mismo order_id: no rompe ni duplica
    assert db.all_order_ids() == {"123"}


def test_all_order_ids(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    db.insert(make_movement("b"))
    assert db.all_order_ids() == {"a", "b"}


def test_all_movements_devuelve_movimientos(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    db.insert(make_movement("b"))
    movs = db.all_movements()
    assert {m.order_id for m in movs} == {"a", "b"}
    # Reconstruye los tipos correctos
    m = next(m for m in movs if m.order_id == "a")
    assert m.side is Side.COMPRA
    assert m.usd_gross == Decimal("16.92")
    assert m.date == date(2026, 6, 1)
    assert m.source is Source.BINANCE_API


def test_delete_borra_y_devuelve_si_existia(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    assert db.delete("a") is True
    assert db.exists("a") is False
    assert db.delete("a") is False  # ya no estaba


def test_set_client_asigna_y_desasigna(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    assert db.set_client("a", 7) is True
    cur = db.conn.execute("SELECT client_id FROM movements WHERE order_id='a'")
    assert cur.fetchone()[0] == 7
    assert db.set_client("a", None) is True
    cur = db.conn.execute("SELECT client_id FROM movements WHERE order_id='a'")
    assert cur.fetchone()[0] is None
    assert db.set_client("noexiste", 7) is False


def test_dedupe_no_pisa_client_id(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    db.set_client("a", 5)
    db.insert(make_movement("a"))  # re-sync del mismo order_id
    cur = db.conn.execute("SELECT client_id FROM movements WHERE order_id='a'")
    assert cur.fetchone()[0] == 5  # la asignación sobrevive al dedupe


def test_client_ids_mapea_order_id_a_client(tmp_path):
    db = TradesDB(tmp_path / "t.db")
    db.insert(make_movement("a"))
    db.insert(make_movement("b"))
    db.set_client("a", 9)
    ids = db.client_ids()
    assert ids["a"] == 9
    assert ids["b"] is None
