from datetime import date

from core.trades_db import TradesDB
from core.clients_db import Client, ClientsDB, VALID_STATUSES


def make_db(tmp_path):
    trades = TradesDB(tmp_path / "t.db")
    return ClientsDB(trades.conn), trades


def test_create_y_get(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan", alias="juancho",
                           contact="+54911", cbu_cvu="000", status="prospecto"))
    c = db.get(cid)
    assert c is not None
    assert c.id == cid
    assert c.name == "Juan"
    assert c.alias == "juancho"
    assert c.cbu_cvu == "000"
    assert c.status == "prospecto"
    assert c.created_at  # timestamp seteado


def test_status_invalido_cae_a_default(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="X", status="cualquiera"))
    assert db.get(cid).status == "prospecto"
    assert "activo" in VALID_STATUSES


def test_update_parcial(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan"))
    assert db.update(cid, {"status": "contactado", "notes": "mueve 5k"}) is True
    c = db.get(cid)
    assert c.status == "contactado"
    assert c.notes == "mueve 5k"
    assert c.name == "Juan"  # no se tocó
    assert db.update(999, {"name": "z"}) is False


def test_update_ignora_status_invalido(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan", status="activo"))
    db.update(cid, {"status": "basura"})
    assert db.get(cid).status == "activo"  # se mantiene el válido previo


def test_delete(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan"))
    assert db.delete(cid) is True
    assert db.get(cid) is None
    assert db.delete(cid) is False


def test_delete_desasigna_movimientos(tmp_path):
    """Al borrar un cliente, sus ops quedan con client_id NULL (no huérfanas)."""
    from datetime import date
    from decimal import Decimal
    from core.movements import Movement, Side, Source
    db, trades = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan"))
    trades.insert(Movement(
        side=Side.VENTA, date=date(2026, 6, 1), order_id="o1",
        usd_gross=Decimal("100"), commission=Decimal("0"), usd_net=Decimal("100"),
        price=Decimal("1000"), total_ars=Decimal("100000"),
        exchange_coin="Binance / USDT", bank="Lemon", source=Source.BINANCE_API,
    ))
    trades.set_client("o1", cid)
    db.delete(cid)
    row = trades.conn.execute("SELECT client_id FROM movements WHERE order_id='o1'").fetchone()
    assert row[0] is None


def test_mark_contacted(tmp_path):
    db, _ = make_db(tmp_path)
    cid = db.create(Client(id=None, name="Juan"))
    assert db.mark_contacted(cid, on=date(2026, 6, 24)) is True
    assert db.get(cid).last_contacted_at == "2026-06-24"


from decimal import Decimal
from core.movements import Movement, Side, Source


def _mov(order_id, day, usd_gross, total_ars, side=Side.VENTA):
    return Movement(
        side=side, date=day, order_id=order_id,
        usd_gross=Decimal(usd_gross), commission=Decimal("0"),
        usd_net=Decimal(usd_gross), price=Decimal("1000"),
        total_ars=Decimal(total_ars), exchange_coin="Binance / USDT",
        bank="Lemon", source=Source.BINANCE_API,
    )


def test_list_with_summary(tmp_path):
    db, trades = make_db(tmp_path)
    juan = db.create(Client(id=None, name="Juan"))
    ana = db.create(Client(id=None, name="Ana"))
    trades.insert(_mov("o1", date(2026, 6, 1), "100", "100000"))
    trades.insert(_mov("o2", date(2026, 6, 10), "50", "55000"))
    trades.insert(_mov("o3", date(2026, 6, 5), "20", "21000"))
    trades.set_client("o1", juan)
    trades.set_client("o2", juan)
    trades.set_client("o3", ana)  # Ana 1 op; un movimiento sin cliente queda afuera
    trades.insert(_mov("o4", date(2026, 6, 20), "999", "999000"))  # sin cliente

    rows = {r["name"]: r for r in db.list_with_summary(today=date(2026, 6, 20))}
    j = rows["Juan"]
    assert j["ops"] == 2
    assert j["total_ars"] == 155000.0
    assert j["last_date"] == "2026-06-10"  # la más reciente de Juan
    assert j["last_usd"] == 50.0
    assert j["last_ars"] == 55000.0
    assert j["days_since"] == 10  # 2026-06-20 - 2026-06-10

    a = rows["Ana"]
    assert a["ops"] == 1
    assert a["total_ars"] == 21000.0
    assert a["days_since"] == 15


def test_summary_cliente_sin_ops(tmp_path):
    db, _ = make_db(tmp_path)
    db.create(Client(id=None, name="NuevoProspecto"))
    row = db.list_with_summary()[0]
    assert row["ops"] == 0
    assert row["total_ars"] == 0.0
    assert row["last_date"] is None
    assert row["days_since"] is None


def test_movements_for(tmp_path):
    db, trades = make_db(tmp_path)
    juan = db.create(Client(id=None, name="Juan"))
    trades.insert(_mov("o2", date(2026, 6, 10), "50", "55000"))
    trades.insert(_mov("o1", date(2026, 6, 1), "100", "100000"))
    trades.set_client("o1", juan)
    trades.set_client("o2", juan)
    ms = db.movements_for(juan)
    assert [m.order_id for m in ms] == ["o1", "o2"]  # orden por fecha asc
    assert isinstance(ms[0].total_ars, Decimal)
