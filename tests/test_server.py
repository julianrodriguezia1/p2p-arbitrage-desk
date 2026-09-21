from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from core.movements import Movement, Side, Source
from core.sheet_writer import MonthTabNotFound
from webapp.server import create_app


class FakeWriter:
    def __init__(self):
        self.written = []
        self.raise_month = False

    def write_movement(self, m):
        if self.raise_month:
            raise MonthTabNotFound(m.month_tab())
        self.written.append(m)
        return "A3"


@pytest.fixture
def ctx(tmp_path):
    from core.trades_db import TradesDB
    db = TradesDB(tmp_path / "t.db")
    writer = FakeWriter()
    parser = lambda image_bytes, mime: {"side": "COMPRA", "order_id": "p1"}
    app = create_app(db=db, writer=writer, parser=parser, html_path=None)
    return TestClient(app), db, writer


def _buy_payload(op_id="123"):
    return {"type": "buy", "date": "2026-06-01", "opId": op_id,
            "usdBruto": 100, "commPct": 0.16, "priceArs": 1477,
            "exchange": "Binance / USDT", "bank": "Lemon"}


def test_get_trades_vacio(ctx):
    client, _, _ = ctx
    r = client.get("/api/trades")
    assert r.status_code == 200
    assert r.json() == []


def _app_with_spread_csv(tmp_path, csv_text):
    from core.trades_db import TradesDB
    csv = tmp_path / "spread.csv"
    csv.write_text(csv_text, encoding="utf-8")
    app = create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                     parser=lambda b, m: {}, html_path=None,
                     spread_log_path=str(csv))
    return TestClient(app)


def test_spread_history_lee_csv_y_filtra_fantasma(tmp_path):
    csv_text = (
        "timestamp_art,weekday,hour,best_ask,ask_exchange,best_bid,bid_exchange,spread_ars,spread_pct\n"
        "2026-06-08T17:00:00-03:00,Mon,17,1490,weexp2p,1510,binance,20,1.34\n"
        "2026-06-09T06:00:00-03:00,Tue,6,1000,mexc,1200,mexcp2p,200,20.0\n"  # fantasma
    )
    r = _app_with_spread_csv(tmp_path, csv_text).get("/api/spread/history")
    assert r.status_code == 200
    d = r.json()
    assert d["samples"] == 1 and d["dropped"] == 1
    assert d["by_hour"][0]["hour"] == 17
    assert len(d["recent"]) == 2           # recent muestra crudo
    assert any(x["outlier"] for x in d["recent"])  # el 20% marcado como fantasma


def _ads_app(tmp_path, fetchers):
    from core.trades_db import TradesDB
    return TestClient(create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, p2p_fetchers=fetchers))


def test_p2p_cheapest_ordena_por_precio_y_serializa(tmp_path):
    from p2p_scanner import Ad

    def fake_fetch(asset, fiat, trade_type, rows=20):
        assert trade_type == "BUY"
        return [
            Ad("bybit", "BUY", 1515.0, 50000, 530000, 350, "GranVendedor",
               ["MercadoPago"], orders=2000, finish_rate=0.99),
            Ad("bybit", "BUY", 1511.8, 50000, 530000, 350, "ChicoGRX",
               ["Reba"], orders=46, finish_rate=0.979),
        ]

    r = _ads_app(tmp_path, {"bybit": fake_fetch}).get("/api/p2p/cheapest?exchange=bybit")
    assert r.status_code == 200
    body = r.json()
    assert body["exchange"] == "bybit"
    assert [a["price"] for a in body["ads"]] == [1511.8, 1515.0]   # ascendente
    assert body["ads"][0]["merchant"] == "ChicoGRX" and body["ads"][0]["orders"] == 46


def test_p2p_cheapest_side_sell_ordena_descendente(tmp_path):
    """side=SELL = 'donde lo pagan más caro': pide SELL al fetcher y ordena desc."""
    from p2p_scanner import Ad

    def fake_fetch(asset, fiat, trade_type, rows=20):
        assert trade_type == "SELL"
        return [
            Ad("bybit", "SELL", 1508.0, 50000, 530000, 350, "PagaPoco",
               ["MercadoPago"], orders=2000, finish_rate=0.99),
            Ad("bybit", "SELL", 1512.5, 50000, 530000, 350, "PagaMas",
               ["Reba"], orders=46, finish_rate=0.979),
        ]

    r = _ads_app(tmp_path, {"bybit": fake_fetch}).get(
        "/api/p2p/cheapest?exchange=bybit&side=SELL")
    assert r.status_code == 200
    body = r.json()
    assert body["side"] == "SELL"
    assert [a["price"] for a in body["ads"]] == [1512.5, 1508.0]   # descendente
    assert body["ads"][0]["merchant"] == "PagaMas"


def test_p2p_cheapest_side_invalido_da_422(tmp_path):
    r = _ads_app(tmp_path, {"bybit": lambda *a, **k: []}).get(
        "/api/p2p/cheapest?exchange=bybit&side=lateral")
    assert r.status_code == 422


def test_p2p_cheapest_exchange_no_soportado(tmp_path):
    r = _ads_app(tmp_path, {"binance": lambda *a, **k: []}).get("/api/p2p/cheapest?exchange=kraken")
    assert r.status_code == 404


def test_p2p_cheapest_error_de_red(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("403 IP bloqueada")
    r = _ads_app(tmp_path, {"okx": boom}).get("/api/p2p/cheapest?exchange=okx")
    assert r.status_code == 502


def test_spread_history_sin_archivo(tmp_path):
    from core.trades_db import TradesDB
    app = create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                     parser=lambda b, m: {}, html_path=None,
                     spread_log_path=str(tmp_path / "nope.csv"))
    r = TestClient(app).get("/api/spread/history")
    assert r.status_code == 200
    assert r.json()["samples"] == 0


def test_post_trade_guarda_en_db_y_sheet(ctx):
    client, db, writer = ctx
    r = client.post("/api/trades", json=_buy_payload("123"))
    assert r.status_code == 201
    assert r.json()["opId"] == "123"
    assert db.exists("123")
    assert len(writer.written) == 1


def test_get_trades_devuelve_lo_cargado(ctx):
    client, _, _ = ctx
    client.post("/api/trades", json=_buy_payload("123"))
    trades = client.get("/api/trades").json()
    assert len(trades) == 1
    assert trades[0]["type"] == "buy"
    assert trades[0]["usdBruto"] == 100.0


def test_post_trade_duplicado_da_409(ctx):
    client, _, _ = ctx
    client.post("/api/trades", json=_buy_payload("dup"))
    r = client.post("/api/trades", json=_buy_payload("dup"))
    assert r.status_code == 409


def test_post_trade_sin_pestania_da_422_y_no_guarda(ctx):
    client, db, writer = ctx
    writer.raise_month = True
    r = client.post("/api/trades", json=_buy_payload("nm"))
    assert r.status_code == 422
    assert not db.exists("nm")  # consistencia DB<->Sheet


def test_delete_trade(ctx):
    client, db, _ = ctx
    client.post("/api/trades", json=_buy_payload("del"))
    r = client.request("DELETE", "/api/trades/del")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert not db.exists("del")


def test_post_screenshot_devuelve_parsed_sin_guardar(ctx):
    client, db, _ = ctx
    r = client.post(
        "/api/screenshot",
        files={"file": ("cap.png", b"\x89PNG fake", "image/png")},
    )
    assert r.status_code == 200
    assert r.json()["parsed"]["order_id"] == "p1"
    assert db.all_order_ids() == set()  # no guardó nada


def test_post_trade_payload_invalido_da_422(ctx):
    client, db, _ = ctx
    # falta usdBruto/priceArs/date -> no debe explotar con 500
    r = client.post("/api/trades", json={"type": "buy", "opId": "x"})
    assert r.status_code == 422
    assert db.all_order_ids() == set()


# ── Task 2: GET /api/suggest ───────────────────────────────────────────────


FAKE_SUGGEST_PAYLOAD = {
    "side": "VENTA", "asset": "USDT",
    "competitive": 1489.0, "margin": 1414.0, "final": 1489.0, "note": "",
    "reference": None, "margin_criptoya": None,
    "ad_min": 30000.0, "ad_max": 150000.0, "methods": ["LemonCash"],
    "ad_text": "=== Anuncio VENTA USDT ===",
}


@pytest.fixture
def ctx_suggest(tmp_path):
    from core.trades_db import TradesDB

    db = TradesDB(tmp_path / "t.db")
    writer = FakeWriter()
    parser = lambda image_bytes, mime: {"side": "COMPRA", "order_id": "p1"}

    def fake_suggester(*, side, asset, fiat, ad_min, ad_max, methods, margin):
        return FAKE_SUGGEST_PAYLOAD

    app = create_app(db=db, writer=writer, parser=parser, html_path=None,
                     suggester=fake_suggester)
    return TestClient(app)


def test_suggest_vender_devuelve_200_y_dict(ctx_suggest):
    client = ctx_suggest
    r = client.get("/api/suggest?side=vender")
    assert r.status_code == 200
    data = r.json()
    assert data["side"] == "VENTA"
    assert data["final"] == 1489.0


def test_suggest_side_invalido_da_422(ctx_suggest):
    client = ctx_suggest
    r = client.get("/api/suggest?side=invalido")
    assert r.status_code == 422


def test_cost_today_devuelve_promedio_y_breakeven(ctx):
    client, _, _ = ctx
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-10", "opId": "c1",
                "usdBruto": 100, "commPct": 0, "priceArs": 1400,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-10", "opId": "c2",
                "usdBruto": 100, "commPct": 0, "priceArs": 1500,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    r = client.get("/api/cost/today?day=2026-06-10")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 2
    assert d["avg_price"] == 1450.0
    assert d["breakeven"] == 1450.0
    assert d["units"] == 200.0


def test_cost_today_incluye_stock_de_hoy(ctx):
    client, _, _ = ctx
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-10", "opId": "b1",
                "usdBruto": 100, "commPct": 0, "priceArs": 1400,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    client.post("/api/trades", json={"type": "sell", "date": "2026-06-10", "opId": "s1",
                "usdBruto": 40, "commPct": 0, "priceArs": 1500,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    d = client.get("/api/cost/today?day=2026-06-10").json()
    assert d["units"] == 100.0   # comprado
    assert d["sold"] == 40.0     # vendido
    assert d["stock"] == 60.0    # neto del día


def test_cost_today_sin_compras_devuelve_count_cero(ctx):
    client, _, _ = ctx
    r = client.get("/api/cost/today?day=2026-06-10")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 0
    assert d["avg_price"] is None and d["breakeven"] is None


def test_cost_period_promedio_compra_y_venta(ctx):
    client, _, _ = ctx
    # 2026-06-24 es miércoles => semana lun 22 a dom 28.
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-23", "opId": "c1",
                "usdBruto": 100, "commPct": 0, "priceArs": 1400,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-24", "opId": "c2",
                "usdBruto": 100, "commPct": 0, "priceArs": 1500,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    client.post("/api/trades", json={"type": "sell", "date": "2026-06-24", "opId": "s1",
                "usdBruto": 50, "commPct": 0, "priceArs": 1520,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    d = client.get("/api/cost/period?period=semana&day=2026-06-24").json()
    assert d["start"] == "2026-06-22" and d["end"] == "2026-06-28"
    assert d["buy"]["count"] == 2 and d["buy"]["avg_price"] == 1450.0
    assert d["sell"]["count"] == 1 and d["sell"]["avg_price"] == 1520.0
    assert d["gap_ars"] == 70.0
    assert round(d["gap_pct"], 4) == round(70.0 / 1450.0 * 100, 4)


def test_cost_period_un_solo_lado_deja_gap_null(ctx):
    client, _, _ = ctx
    client.post("/api/trades", json={"type": "buy", "date": "2026-06-24", "opId": "c1",
                "usdBruto": 100, "commPct": 0, "priceArs": 1500,
                "exchange": "Binance / USDT", "bank": "Lemon"})
    d = client.get("/api/cost/period?period=hoy&day=2026-06-24").json()
    assert d["buy"]["avg_price"] == 1500.0
    assert d["sell"] is None
    assert d["gap_ars"] is None and d["gap_pct"] is None


def test_cost_period_invalido_da_422(ctx):
    client, _, _ = ctx
    assert client.get("/api/cost/period?period=trimestre").status_code == 422


def test_suggest_suggester_raising_da_502(tmp_path):
    from core.trades_db import TradesDB

    db = TradesDB(tmp_path / "t.db")
    writer = FakeWriter()
    parser = lambda image_bytes, mime: {}

    def failing_suggester(*, side, asset, fiat, ad_min, ad_max, methods, margin):
        raise RuntimeError("Binance caido")

    app = create_app(db=db, writer=writer, parser=parser, html_path=None,
                     suggester=failing_suggester)
    client = TestClient(app)
    r = client.get("/api/suggest?side=vender")
    assert r.status_code == 502


# ── Task 4: GET /api/dollar/ta ────────────────────────────────────────────


def _dollar_ta_app(tmp_path, fake):
    from core.trades_db import TradesDB
    return TestClient(create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, dollar_ta=fake))


def test_dollar_ta_endpoint_devuelve_payload(tmp_path):
    payload = {"verdict": "vender", "score": 42.0, "series": [1, 2, 3]}
    captured = {}

    def fake(window):
        captured["window"] = window
        return payload

    r = _dollar_ta_app(tmp_path, fake).get("/api/dollar/ta?window=90")
    assert r.status_code == 200
    assert r.json()["verdict"] == "vender"
    assert captured["window"] == 90


def test_dollar_ta_endpoint_error_es_502(tmp_path):
    def fake(window):
        raise RuntimeError("ArgentinaDatos caído")

    r = _dollar_ta_app(tmp_path, fake).get("/api/dollar/ta")
    assert r.status_code == 502


# ── Task 5: POST /api/sync/bybit ──────────────────────────────────────────


def _bybit_sync_app(tmp_path, fake):
    from core.trades_db import TradesDB
    return TestClient(create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, bybit_sync=fake))


def test_sync_bybit_endpoint_devuelve_resultado(tmp_path):
    fake = lambda: {"added": [], "skipped": [], "count": 0}
    r = _bybit_sync_app(tmp_path, fake).post("/api/sync/bybit")
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_sync_bybit_endpoint_error_es_502(tmp_path):
    def fake():
        raise RuntimeError("Bybit caído")
    r = _bybit_sync_app(tmp_path, fake).post("/api/sync/bybit")
    assert r.status_code == 502


# ── Task 1: POST /api/movement ────────────────────────────────────────────


def _mov_payload(order_id="lemon1"):
    # total_ars (300000) NO es bruto*precio (202.34*1482) -> caso maña Lemon
    return {"side": "COMPRA", "date": "2026-06-18", "order_id": order_id,
            "usd_gross": "202.34", "commission": "2.02", "usd_net": "200.32",
            "price": "1482", "total_ars": "300000",
            "exchange_coin": "Lemon / USDT", "bank": "Lemon"}


def test_post_movement_guarda_total_ars_explicito(ctx):
    client, db, _ = ctx
    r = client.post("/api/movement", json=_mov_payload())
    assert r.status_code == 201
    assert r.json()["totalArs"] == 300000.0   # respeta el total explícito, no bruto*precio
    assert db.exists("lemon1")


def test_post_movement_409_si_ya_existe(ctx):
    client, _, _ = ctx
    assert client.post("/api/movement", json=_mov_payload("dup")).status_code == 201
    assert client.post("/api/movement", json=_mov_payload("dup")).status_code == 409


def test_post_movement_422_si_falta_pestania(ctx):
    client, _, writer = ctx
    writer.raise_month = True
    assert client.post("/api/movement", json=_mov_payload("x")).status_code == 422


def _app_with_sync_jobs(token="testtoken"):
    from core.trades_db import TradesDB
    from webapp.sync_jobs import SyncJobs
    import tempfile
    db = TradesDB(tempfile.mktemp(suffix=".db"))
    jobs = SyncJobs()
    app = create_app(db=db, writer=FakeWriter(), parser=lambda b, m: {},
                     html_path=None, sync_jobs=jobs, sync_agent_token=token)
    return TestClient(app)


def test_sync_request_crea_job():
    client = _app_with_sync_jobs()
    r = client.post("/api/sync/request")
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    assert r.json()["job_id"]


def test_sync_poll_sin_token_da_401():
    client = _app_with_sync_jobs()
    r = client.get("/api/sync/poll")
    assert r.status_code == 401


def test_sync_poll_sin_job_devuelve_null():
    client = _app_with_sync_jobs()
    r = client.get("/api/sync/poll", headers={"X-Sync-Token": "testtoken"})
    assert r.status_code == 200
    assert r.json()["job_id"] is None


def test_sync_flujo_completo_request_poll_result_status():
    client = _app_with_sync_jobs()
    job_id = client.post("/api/sync/request").json()["job_id"]
    polled = client.get("/api/sync/poll", headers={"X-Sync-Token": "testtoken"}).json()
    assert polled["job_id"] == job_id
    r = client.post("/api/sync/result", headers={"X-Sync-Token": "testtoken"},
                    json={"job_id": job_id, "ok": True,
                          "result": {"binance": {"nuevas": 2, "ya": 5, "errores": []}}})
    assert r.status_code == 200
    assert r.json()["applied"] is True
    v = client.get("/api/sync/status", params={"job_id": job_id}).json()
    assert v["status"] == "done"
    assert v["result"]["binance"]["nuevas"] == 2


def test_sync_status_job_inexistente_da_404():
    client = _app_with_sync_jobs()
    r = client.get("/api/sync/status", params={"job_id": "noexiste"})
    assert r.status_code == 404


def test_sync_result_sin_token_da_401():
    client = _app_with_sync_jobs()
    r = client.post("/api/sync/result", json={"job_id": "x", "ok": True})
    assert r.status_code == 401


def _app_with_exe(exe_path):
    from core.trades_db import TradesDB
    import tempfile
    db = TradesDB(tempfile.mktemp(suffix=".db"))
    app = create_app(db=db, writer=FakeWriter(), parser=lambda b, m: {},
                     html_path=None, agente_exe_path=str(exe_path))
    return TestClient(app)


def test_descargar_agente_404_si_no_existe(tmp_path):
    client = _app_with_exe(tmp_path / "noexiste.exe")
    assert client.get("/api/agente/descargar").status_code == 404


def test_descargar_agente_sirve_el_exe(tmp_path):
    p = tmp_path / "agente-arbitrador.exe"
    p.write_bytes(b"FAKEEXE")
    client = _app_with_exe(p)
    r = client.get("/api/agente/descargar")
    assert r.status_code == 200
    assert r.content == b"FAKEEXE"


def _app_with_captacion(chat_fn):
    from core.trades_db import TradesDB
    import tempfile
    db = TradesDB(tempfile.mktemp(suffix=".db"))
    app = create_app(db=db, writer=FakeWriter(), parser=lambda b, m: {},
                     html_path=None, captacion_chat=chat_fn)
    return TestClient(app)


def test_captacion_chat_devuelve_reply():
    client = _app_with_captacion(lambda messages: "hola, soy ADA")
    r = client.post("/api/captacion/chat",
                    json={"messages": [{"role": "user", "content": "buenas"}]})
    assert r.status_code == 200
    assert r.json() == {"reply": "hola, soy ADA"}


def test_captacion_chat_body_invalido_422():
    client = _app_with_captacion(lambda messages: "x")
    r = client.post("/api/captacion/chat", json={"messages": []})
    assert r.status_code == 422
    r2 = client.post("/api/captacion/chat", json={
        "messages": [{"role": "assistant", "content": "hola"}]})
    assert r2.status_code == 422


def test_captacion_chat_error_motor_502():
    def boom(messages):
        raise RuntimeError("sin login")
    client = _app_with_captacion(boom)
    r = client.post("/api/captacion/chat",
                    json={"messages": [{"role": "user", "content": "hola"}]})
    assert r.status_code == 502


# ── Clientes (CRM) ─────────────────────────────────────────────────────────


@pytest.fixture
def cctx(tmp_path):
    from core.trades_db import TradesDB
    from core.clients_db import ClientsDB
    db = TradesDB(tmp_path / "t.db")
    clients = ClientsDB(db.conn)
    app = create_app(db=db, writer=FakeWriter(), parser=lambda b, m: {},
                     html_path=None, clients_db=clients)
    return TestClient(app), db, clients


def test_crud_clientes(cctx):
    client, _, _ = cctx
    r = client.post("/api/clients", json={"name": "Juan", "cbuCvu": "000",
                                          "status": "prospecto"})
    assert r.status_code == 201
    cid = r.json()["id"]
    assert r.json()["cbuCvu"] == "000"

    r = client.get("/api/clients")
    assert r.status_code == 200
    assert any(c["name"] == "Juan" and c["ops"] == 0 for c in r.json())

    r = client.put(f"/api/clients/{cid}", json={"status": "contactado"})
    assert r.status_code == 200 and r.json()["status"] == "contactado"

    r = client.post(f"/api/clients/{cid}/contacted")
    assert r.status_code == 200 and r.json()["lastContactedAt"]

    r = client.delete(f"/api/clients/{cid}")
    assert r.status_code == 200 and r.json()["deleted"] is True


def test_ficha_y_asignar_movimiento(cctx):
    client, db, _ = cctx
    r = client.post("/api/clients", json={"name": "Juan"})
    cid = r.json()["id"]
    # Cargar una op vía el endpoint existente
    client.post("/api/trades", json=_buy_payload("op-1"))

    r = client.put("/api/movements/op-1/client", json={"client_id": cid})
    assert r.status_code == 200 and r.json()["updated"] is True

    r = client.get(f"/api/clients/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert body["client"]["name"] == "Juan"
    assert [m["opId"] for m in body["movements"]] == ["op-1"]

    # Desasignar
    r = client.put("/api/movements/op-1/client", json={"client_id": None})
    assert r.status_code == 200
    assert client.get(f"/api/clients/{cid}").json()["movements"] == []


def test_cliente_inexistente_404(cctx):
    client, _, _ = cctx
    assert client.get("/api/clients/999").status_code == 404
    assert client.put("/api/clients/999", json={"name": "x"}).status_code == 404
    assert client.post("/api/clients/999/contacted").status_code == 404


def test_post_cliente_sin_name_422(cctx):
    client, _, _ = cctx
    assert client.post("/api/clients", json={"alias": "x"}).status_code == 422


def test_trades_expone_client_id(cctx):
    client, _, _ = cctx
    cid = client.post("/api/clients", json={"name": "Juan"}).json()["id"]
    client.post("/api/trades", json=_buy_payload("op-x"))
    client.put("/api/movements/op-x/client", json={"client_id": cid})
    trades = client.get("/api/trades").json()
    row = next(t for t in trades if t["opId"] == "op-x")
    assert row["clientId"] == cid


# ── Task 1 (bot): GET /api/spread/now ─────────────────────────────────────


def _spread_app(tmp_path, fake_spread_now):
    from webapp.server import create_app
    from core.trades_db import TradesDB
    return TestClient(create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, spread_now=fake_spread_now))


def test_spread_now_devuelve_payload(tmp_path):
    fake = lambda asset="USDT": {
        "asset": "USDT", "fiat": "ARS",
        "exchanges": [{"exchange": "binance", "ask": 1510.0, "bid": 1560.0, "intra_pct": 3.31}],
        "best_cross": {"buy_ex": "bybit", "buy": 1512.0, "sell_ex": "binance",
                       "sell": 1560.0, "net_pct": 0.2},
    }
    r = _spread_app(tmp_path, fake).get("/api/spread/now")
    assert r.status_code == 200
    body = r.json()
    assert body["exchanges"][0]["exchange"] == "binance"
    assert body["best_cross"]["buy_ex"] == "bybit"


def test_spread_now_error_es_502(tmp_path):
    def boom(asset="USDT"):
        raise RuntimeError("exchanges caídos")
    r = _spread_app(tmp_path, boom).get("/api/spread/now")
    assert r.status_code == 502


def test_build_spread_now_agrega_mas_barato_mas_caro(monkeypatch):
    """El builder enriquece con CriptoYa: más barato p/comprar + más caro p/vender."""
    import config
    from webapp import server
    from core.criptoya import MarketExtremes

    class Q:
        def __init__(self, ex, ask, bid):
            self.exchange, self.best_ask, self.best_bid = ex, ask, bid

    monkeypatch.setattr("p2p_scanner.scan", lambda a, f: [Q("binance", 1548.0, 1544.0)])
    monkeypatch.setattr("p2p_scanner.find_opportunities", lambda q, a: ([], []))
    # más barato = dolarapp (remesa), más caro = binancep2p (p2p)
    monkeypatch.setattr(
        "core.criptoya.fetch_market_extremes",
        lambda *a, **k: MarketExtremes("dolarapp", 1450.0, "binancep2p", 1560.0),
    )
    out = server._build_default_spread_now(config)()
    assert out["cheapest_buy"]["exchange"] == "dolarapp"
    assert out["cheapest_buy"]["type"] == "remesa"
    assert out["dearest_sell"]["exchange"] == "binancep2p"
    assert out["dearest_sell"]["type"] == "p2p"
    assert out["best_route"]["buy_ex"] == "dolarapp" and out["best_route"]["sell_ex"] == "binancep2p"
    assert round(out["best_route"]["gross_pct"], 2) == round((1560 - 1450) / 1450 * 100, 2)


def test_build_spread_now_sobrevive_criptoya_caido(monkeypatch):
    import config
    from webapp import server

    class Q:
        def __init__(self, ex, ask, bid):
            self.exchange, self.best_ask, self.best_bid = ex, ask, bid

    monkeypatch.setattr("p2p_scanner.scan", lambda a, f: [Q("binance", 1548.0, 1544.0)])
    monkeypatch.setattr("p2p_scanner.find_opportunities", lambda q, a: ([], []))
    monkeypatch.setattr("core.criptoya.fetch_market_extremes",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    out = server._build_default_spread_now(config)()
    assert out["cheapest_buy"] is None and out["dearest_sell"] is None
    assert out["best_route"] is None
    assert out["exchanges"][0]["exchange"] == "binance"   # lo de P2P sigue andando


def _depth_app(tmp_path, fetchers):
    from webapp import server
    from core.trades_db import TradesDB
    server._depth_cache.clear()
    return TestClient(server.create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, p2p_fetchers=fetchers))


class _Ad:
    def __init__(self, price, available):
        self.price, self.available = price, available


def test_depth_quote_calcula_vwap(tmp_path):
    def fake_bitget(asset, fiat, side, rows=20):
        if side == "BUY":
            return [_Ad(1546.88, 101.16), _Ad(1548.70, 1043390)]
        return [_Ad(1544.25, 157266)]
    r = _depth_app(tmp_path, {"bitget": fake_bitget}).get(
        "/api/p2p/depth_quote?exchange=bitget&volume=1000")
    assert r.status_code == 200
    body = r.json()
    assert abs(body["ask"] - (101.16 * 1546.88 + 898.84 * 1548.70) / 1000) < 1e-6
    assert body["bid"] == 1544.25


def test_depth_quote_exchange_desconocido_404(tmp_path):
    r = _depth_app(tmp_path, {"bitget": lambda *a, **k: []}).get(
        "/api/p2p/depth_quote?exchange=nope&volume=1000")
    assert r.status_code == 404


def test_depth_quote_degradado_si_falla_un_lado(tmp_path):
    def flaky(asset, fiat, side, rows=20):
        if side == "BUY":
            raise RuntimeError("bloqueo")
        return [_Ad(1544.25, 157266)]
    r = _depth_app(tmp_path, {"bitget": flaky}).get(
        "/api/p2p/depth_quote?exchange=bitget&volume=1000")
    assert r.status_code == 200
    body = r.json()
    assert body["ask"] is None and body["bid"] == 1544.25


def test_estrategia_arma_headline_y_alternativas(tmp_path, monkeypatch):
    import webapp.server as server
    import config
    # El fixture usa kucoin como venue de ejemplo; acá se prueba la mecánica,
    # no la regla de "venue secundario" (esa tiene su test en test_strategy).
    monkeypatch.setattr(config, "VENUES_SECUNDARIOS", frozenset())
    from p2p_scanner import Ad
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient

    server._estrategia_cache.clear()

    # precio por (exchange, side): bybit barato para comprar, kucoin caro para vender.
    prices = {
        ("bybit", "BUY"): 1561.0, ("bybit", "SELL"): 1560.0,
        ("kucoin", "BUY"): 1580.0, ("kucoin", "SELL"): 1578.0,
    }

    def make_fetcher(ex):
        def f(asset, fiat, side, rows=20):
            return [Ad(exchange=ex, side=side, price=prices[(ex, side)],
                       min_amount=0, max_amount=0, available=100000.0)]
        return f

    fetchers = {"bybit": make_fetcher("bybit"), "kucoin": make_fetcher("kucoin")}
    # sin CriptoYa: aísla la rama de profundidad y deja outside_note en None
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})

    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None, p2p_fetchers=fetchers)
    r = TestClient(app).get("/api/estrategia?volume=1000")
    assert r.status_code == 200
    data = r.json()
    assert data["best"] is not None
    assert data["best"]["sell_venue"] == "kucoinp2p"   # vende publicando caro en kucoin
    assert data["best"]["net_pct"] > 0
    assert isinstance(data["alternatives"], list)
    assert data["outside_note"] is None                # payload CriptoYa vacío


def _sell_payload_bank(op_id, bank, total, d="2026-07-01"):
    # OJO: /api/movement usa cli.add_movement.movement_from_json (formato
    # snake_case), NO webapp.serialize.dashboard_to_movement (ese es el de
    # POST /api/trades, formato camelCase usdBruto/priceArs/totalArs). El
    # payload de /api/movement respeta total_ars TAL CUAL viene, sin
    # recalcular bruto*precio (ver test_post_movement_guarda_total_ars_explicito),
    # así que acá alcanza con pasarlo explícito.
    return {"side": "VENTA", "date": d, "order_id": op_id,
            "usd_gross": "100", "commission": "0", "usd_net": "100",
            "price": "1500", "total_ars": str(total),
            "exchange_coin": "KuCoin / USDT", "bank": bank}


def test_api_wallets_groups_and_defaults_to_latest_month(ctx):
    client, db, writer = ctx
    client.post("/api/movement", json=_sell_payload_bank("w1", "MercadoPagoNew", 1_200_000))
    client.post("/api/movement", json=_sell_payload_bank("w2", "Mercadopago", 40_000))
    r = client.get("/api/wallets")
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "2026-07"
    assert "2026-07" in body["months"]
    assert body["wallets"]["MercadoPago"]["entra"] == 1_240_000


def test_api_wallets_reports_unmapped(ctx):
    client, db, writer = ctx
    client.post("/api/movement", json=_sell_payload_bank("w3", "BilleteraNueva", 5_000))
    r = client.get("/api/wallets?month=2026-07")
    assert r.json()["sin_mapear"] == ["BilleteraNueva"]


def test_spread_now_acepta_el_activo(tmp_path):
    pedidos = []

    def fake(asset="USDT"):
        pedidos.append(asset)
        return {"asset": asset, "fiat": "ARS", "exchanges": []}

    r = _spread_app(tmp_path, fake).get("/api/spread/now", params={"asset": "btc"})
    assert r.status_code == 200
    assert pedidos == ["BTC"]                 # normaliza a mayúsculas
    assert r.json()["asset"] == "BTC"


def test_spread_now_sin_activo_sigue_siendo_usdt(tmp_path):
    pedidos = []

    def fake(asset="USDT"):
        pedidos.append(asset)
        return {"asset": asset, "fiat": "ARS", "exchanges": []}

    assert _spread_app(tmp_path, fake).get("/api/spread/now").status_code == 200
    assert pedidos == ["USDT"]


def test_spread_now_activo_desconocido_es_400(tmp_path):
    """Devolver el spread de USDT cuando pidieron ETH sería dar un dato falso
    con cara de bueno: mejor fallar."""
    llamadas = []
    r = _spread_app(tmp_path, lambda asset="USDT": llamadas.append(asset)).get(
        "/api/spread/now", params={"asset": "ETH"})
    assert r.status_code == 400
    assert llamadas == []


def test_build_spread_now_usa_volumen_chico_para_btc(monkeypatch):
    """1000 BTC no es un ticket, es una barbaridad: para BTC se pide 0,01."""
    import config
    from webapp import server

    class Q:
        def __init__(self, ex, ask, bid):
            self.exchange, self.best_ask, self.best_bid = ex, ask, bid

    vistos = []
    monkeypatch.setattr("p2p_scanner.scan", lambda a, f: [Q("binance", 1.0, 1.0)])
    monkeypatch.setattr("p2p_scanner.find_opportunities", lambda q, a: ([], []))
    def _ext(asset, fiat, vol, **k):
        vistos.append(("ext", asset, vol))
        return None

    def _pay(asset, fiat, vol):
        vistos.append(("pay", asset, vol))
        return {}

    monkeypatch.setattr("core.criptoya.fetch_market_extremes", _ext)
    monkeypatch.setattr("core.criptoya.fetch_payload", _pay)

    server._build_default_spread_now(config)("BTC")
    assert ("ext", "BTC", 0.01) in vistos and ("pay", "BTC", 0.01) in vistos

    vistos.clear()
    server._build_default_spread_now(config)("USDT")
    assert ("ext", "USDT", config.CRIPTOYA_VOLUME) in vistos


# ── La ruta sintética tiene que llegar al bot ──────────────────────────────

def test_leg_payload_incluye_los_pasos_de_la_ruta():
    """Sin `via` el bot no puede explicar 'comprás USDT acá, convertís allá' y
    la ruta queda como un número mágico que nadie sabe ejecutar."""
    from core.cotizacion import Leg
    from webapp.server import _leg_payload

    leg = Leg("binancep2p", 122_300_000.0, "vía USDT", 0.06, True,
              via={"usdt_price": 1_586.8, "spot_price": 77_000.0, "fuente": "okx"})
    assert _leg_payload(leg)["via"] == {
        "usdt_price": 1_586.8, "spot_price": 77_000.0, "fuente": "okx"}


def test_leg_payload_de_ruta_directa_no_trae_pasos():
    from core.cotizacion import Leg
    from webapp.server import _leg_payload

    assert _leg_payload(Leg("fiwind", 1.0, "directo", None, True))["via"] is None


def test_payload_expone_las_patas_de_publicar_por_venue():
    """El bot arma el bloque '⏳ PUBLICANDO' con esto. Sin la lista sólo tendría
    el mejor global y no podría comparar venue por venue."""
    from core.cotizacion import Cotizacion, Leg
    from webapp.server import _cotizacion_payload

    cot = Cotizacion(
        asset="USDT", size=1000.0, margin_pct=0.5, buys=[], sells=[],
        precio_venta_cliente=None, precio_compra_cliente=None, vuelta_pct=None,
        cubre=True, faltante_pct=None,
        mejor_publicando_compra=None, mejor_publicando_venta=None,
        publicando_buys=[Leg("bybitp2p", 1585.0, "publicando", 900.0, True)],
        publicando_sells=[Leg("okexp2p", 1590.0, "publicando", 900.0, True)])
    d = _cotizacion_payload(cot)
    assert [l["venue"] for l in d["publicando_buys"]] == ["bybitp2p"]
    assert [l["venue"] for l in d["publicando_sells"]] == ["okexp2p"]


def test_leg_payload_lleva_la_cantidad_de_ordenes():
    from core.cotizacion import Leg
    from webapp.server import _leg_payload

    assert _leg_payload(Leg("binancep2p", 1588.0, "tomando", 900.0, True,
                            ordenes=7))["ordenes"] == 7


# --- La jugada que pasa por Binance y el progreso del Verificado (2026-08-28) ---

def test_estrategia_expone_la_jugada_que_pasa_por_binance(tmp_path, monkeypatch):
    """La mejor global es bybit→kucoin; la que suma para el Verificado tiene que
    aparecer aparte, con al menos una pata en Binance P2P."""
    import webapp.server as server
    import config
    # El fixture usa kucoin como venue de ejemplo; acá se prueba la mecánica,
    # no la regla de "venue secundario" (esa tiene su test en test_strategy).
    monkeypatch.setattr(config, "VENUES_SECUNDARIOS", frozenset())
    from p2p_scanner import Ad
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient

    server._estrategia_cache.clear()

    prices = {
        ("bybit", "BUY"): 1561.0, ("bybit", "SELL"): 1560.0,
        ("kucoin", "BUY"): 1580.0, ("kucoin", "SELL"): 1578.0,
        ("binance", "BUY"): 1572.0, ("binance", "SELL"): 1570.0,
    }

    # 12 avisos por punta: los libros tienen que pasar el filtro de liquidez,
    # porque la jugada por Binance se busca sólo entre puntas que mueven plata.
    def make_fetcher(ex):
        def f(asset, fiat, side, rows=20):
            return [Ad(exchange=ex, side=side, price=prices[(ex, side)],
                       min_amount=0, max_amount=0, available=5000.0)
                    for _ in range(12)]
        return f

    fetchers = {k: make_fetcher(k) for k in ("bybit", "kucoin", "binance")}
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})

    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None,
                            p2p_fetchers=fetchers)
    data = TestClient(app).get("/api/estrategia?volume=1000").json()

    assert "binancep2p" not in (data["best"]["buy_venue"], data["best"]["sell_venue"])
    assert data["best_en_binance"] is False
    b = data["binance"]
    assert b is not None
    assert "binancep2p" in (b["buy_venue"], b["sell_venue"])
    assert b["net_pct"] > 0


def _app_merchant(tmp_path, movs, btc_spot):
    import webapp.server as server
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient
    db = TradesDB(tmp_path / "t.db")
    for m in movs:
        db.insert(m)
    app = server.create_app(db=db, writer=FakeWriter(), parser=lambda b, m: {},
                            html_path=None, btc_spot=btc_spot)
    return TestClient(app)


def _mov_binance(fecha, usd, order_id, exchange="Binance / USDT"):
    # Un order_id corto no es una orden P2P y el motor no lo cuenta: los tests
    # que miden el progreso del Verificado necesitan números de orden reales
    # (20 dígitos). Ver `core/merchant.py`.
    if str(order_id).isascii() and not str(order_id).isdigit():
        order_id = str(22900000000000000000 + sum(ord(c) for c in str(order_id)))
    return Movement(
        side=Side.COMPRA, date=fecha, order_id=order_id,
        usd_gross=Decimal(usd), commission=Decimal("0"), usd_net=Decimal(usd),
        price=Decimal("1600"), total_ars=Decimal(usd) * Decimal("1600"),
        exchange_coin=exchange, bank="Galicia", source=Source.BINANCE_API,
    )


def test_api_merchant_devuelve_los_tres_requisitos_medibles(tmp_path):
    hoy = date.today()
    movs = [_mov_binance(hoy, "25000", "a"), _mov_binance(hoy, "25000", "b"),
            _mov_binance(hoy, "9999", "c", "Lemon / USDT")]
    client = _app_merchant(tmp_path, movs,
                           lambda: {"ask": 100_000.0, "bid": 100_000.0})
    r = client.get("/api/merchant")
    assert r.status_code == 200
    data = r.json()
    claves = [q["clave"] for q in data["requisitos"]]
    assert claves == ["ops_30d", "vol_30d_btc", "vol_hist_btc"]
    ops = data["requisitos"][0]
    assert ops["valor"] == 2 and ops["meta"] == 400      # la de Lemon no cuenta
    assert data["requisitos"][1]["valor"] == pytest.approx(0.5)
    assert data["btc_usd"] == pytest.approx(100_000.0)


def test_api_merchant_sin_precio_de_btc_marca_falta(tmp_path):
    client = _app_merchant(tmp_path, [_mov_binance(date.today(), "100", "a")],
                           lambda: None)
    data = client.get("/api/merchant").json()
    assert data["btc_usd"] is None
    vol = data["requisitos"][1]
    assert vol["valor"] is None and "FALTA" in vol["nota"]
    assert data["requisitos"][0]["valor"] == 1          # las ops sí se cuentan


def test_api_merchant_no_se_cae_si_el_precio_de_btc_explota(tmp_path):
    def revienta():
        raise RuntimeError("okx 451")
    client = _app_merchant(tmp_path, [_mov_binance(date.today(), "100", "a")],
                           revienta)
    data = client.get("/api/merchant").json()
    assert data["btc_usd"] is None
    assert data["requisitos"][0]["valor"] == 1


# --- Curva de tamaño: cuánto mejora el precio si operás más grande (2026-08-28) ---

def _fetchers_con_minimo_alto():
    """Libro donde el mejor precio sólo se abre si tu ticket es grande.

    Lado comprador (BUY): un aviso caro sin mínimo y uno barato con mínimo de
    $4.000.000. Con 1.000 USDT no llegás al mínimo y pagás el caro; con 3.000 sí
    llegás. Es exactamente lo que el usuario vio en el libro de Binance.
    """
    from p2p_scanner import Ad

    def f(asset, fiat, side, rows=20):
        if side == "BUY":
            return ([Ad(exchange="binance", side=side, price=1600.0, min_amount=0,
                        max_amount=0, available=100000.0)] * 6
                    + [Ad(exchange="binance", side=side, price=1590.0,
                          min_amount=4_000_000, max_amount=0, available=100000.0)] * 6)
        return [Ad(exchange="binance", side=side, price=1620.0, min_amount=0,
                   max_amount=0, available=100000.0)] * 12
    return {"binance": f}


def test_curva_devuelve_una_fila_por_tamano_pedido(tmp_path, monkeypatch):
    import webapp.server as server
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient

    server._estrategia_cache.clear()
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None,
                            p2p_fetchers=_fetchers_con_minimo_alto())
    data = TestClient(app).get("/api/estrategia/curva?sizes=1000,3000,3500,5000").json()
    assert [f["volume"] for f in data["curva"]] == [1000.0, 3000.0, 3500.0, 5000.0]


def test_curva_muestra_que_el_precio_mejora_con_el_ticket_grande(tmp_path, monkeypatch):
    import webapp.server as server
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient

    server._estrategia_cache.clear()
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None,
                            p2p_fetchers=_fetchers_con_minimo_alto())
    curva = TestClient(app).get("/api/estrategia/curva?sizes=1000,3000").json()["curva"]

    chico, grande = curva[0], curva[1]
    # con 1.000 el aviso barato no se puede tomar; con 3.000 sí
    assert chico["best"]["buy_price"] == pytest.approx(1600.0)
    assert grande["best"]["buy_price"] == pytest.approx(1590.0)
    assert grande["best"]["net_pct"] > chico["best"]["net_pct"]


def test_curva_rechaza_tamanos_invalidos(tmp_path, monkeypatch):
    import webapp.server as server
    from core.trades_db import TradesDB
    from fastapi.testclient import TestClient

    server._estrategia_cache.clear()
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None,
                            p2p_fetchers=_fetchers_con_minimo_alto())
    client = TestClient(app)
    assert client.get("/api/estrategia/curva?sizes=cero,-5").status_code == 422
    # y no se puede pedir una lista infinita de tamaños
    assert client.get("/api/estrategia/curva?sizes=" +
                      ",".join(str(i) for i in range(1, 20))).status_code == 422


# --- Precio de publicación por tamaño de ticket (2026-08-29) ---

def _fetchers_para_publicar():
    """Libro donde los rivales chicos desaparecen si el ticket es grande.

    BUY (mis rivales al publicar VENTA): uno barato que sólo atiende hasta
    3.000.000 ARS y uno caro sin tope. Con 1.000 USDT compito contra los dos y
    tengo que igualar al barato; con 5.000 el barato no me compite y publico
    más caro. SELL es el espejo.

    Los diez avisos de relleno están peor puestos que los dos que definen el
    precio, así que no lo mueven. Están para que el libro pase el filtro de
    liquidez: cerrar la otra pata es TOMAR, y contra un libro flaco no se toma.
    """
    from p2p_scanner import Ad

    def f(asset, fiat, side, rows=20):
        if side == "BUY":
            return [Ad(exchange="x", side=side, price=1590.0, min_amount=10_000,
                       max_amount=3_000_000, available=100000.0),
                    Ad(exchange="x", side=side, price=1596.0, min_amount=10_000,
                       max_amount=90_000_000, available=100000.0)] + [
                    Ad(exchange="x", side=side, price=1597.0, min_amount=10_000,
                       max_amount=3_000_000, available=100000.0)] * 10
        return [Ad(exchange="x", side=side, price=1584.0, min_amount=10_000,
                   max_amount=3_000_000, available=100000.0),
                Ad(exchange="x", side=side, price=1580.0, min_amount=10_000,
                   max_amount=90_000_000, available=100000.0)] + [
                Ad(exchange="x", side=side, price=1579.0, min_amount=10_000,
                   max_amount=3_000_000, available=100000.0)] * 10
    return {"binance": f, "okx": f, "bybit": f, "bitget": f}


def _app_publicar(tmp_path):
    import webapp.server as server
    from core.trades_db import TradesDB
    return server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                             parser=lambda b, m: {}, html_path=None,
                             p2p_fetchers=_fetchers_para_publicar())


def test_anuncio_curva_da_precio_de_los_tres_venues(tmp_path):
    data = TestClient(_app_publicar(tmp_path)).get(
        "/api/anuncio/curva?sizes=1000,5000").json()
    assert sorted(data["venues"]) == ["binancep2p", "bybitp2p", "okexp2p"]
    filas = data["venues"]["binancep2p"]
    assert [f["volume"] for f in filas] == [1000.0, 5000.0]


def test_anuncio_curva_mejora_las_dos_puntas_con_ticket_grande(tmp_path, monkeypatch):
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    filas = TestClient(_app_publicar(tmp_path)).get(
        "/api/anuncio/curva?sizes=1000,5000").json()["venues"]["binancep2p"]
    chico, grande = filas
    assert chico["venta"] == pytest.approx(1589.0)   # min(1590,1596,1597) - 1
    assert chico["compra"] == pytest.approx(1585.0)  # max(1584,1580,1579) + 1
    assert grande["venta"] == pytest.approx(1595.0)  # los de max 3M ya no compiten
    assert grande["compra"] == pytest.approx(1581.0)
    assert grande["rivales_venta"] == 1 and chico["rivales_venta"] == 12


def test_anuncio_curva_cierra_la_otra_pata_tomando_el_libro(tmp_path, monkeypatch):
    """El neto es de UNA pata publicada, no del ciclo de publicar las dos."""
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    fila = TestClient(_app_publicar(tmp_path)).get(
        "/api/anuncio/curva?sizes=1000").json()["venues"]["bybitp2p"][0]
    assert fila["lado"] in ("compra", "venta")
    assert fila["cierre_venue"] in ("binancep2p", "okexp2p", "bybitp2p")
    assert fila["cierre_precio"] is not None
    # publico venta a 1.589 y cierro comprando a 1.590, sin comisiones en bybit
    assert fila["lado"] == "venta"
    assert fila["neto_pct"] == pytest.approx((1589.0 - 1590.0) / 1590.0 * 100)


def test_anuncio_curva_cobra_el_maker_de_binance_una_sola_vez(tmp_path, monkeypatch):
    """Lo que motivó el cambio: 0,20% por publicar, no 0,40% por el ciclo.

    Contra bybit, que publica y toma gratis, a binance le sobra el 0,20% de
    publicar más el flat de tomador de la pata de cierre (0,07 USDT sobre un
    ticket de 1.000 = 0,007%). Nada de eso se cobra dos veces.
    """
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    v = TestClient(_app_publicar(tmp_path)).get(
        "/api/anuncio/curva?sizes=1000").json()["venues"]
    assert v["bybitp2p"][0]["neto_pct"] - v["binancep2p"][0]["neto_pct"] \
        == pytest.approx(0.2 + 0.07 / 1000 * 100)


def test_anuncio_curva_marca_donde_no_puedo_publicar(tmp_path):
    """Bitget no me deja crear anuncios; en el resto publico las dos puntas.

    Confirmado por el usuario 2026-08-29. Ausente en el config = habilitado.
    """
    data = TestClient(_app_publicar(tmp_path)).get(
        "/api/anuncio/curva?sizes=1000"
        "&venues=binancep2p,okexp2p,bybitp2p,bitgetp2p").json()
    for lado in ("habilitado_compra", "habilitado_venta"):
        assert data[lado]["binancep2p"] is True
        assert data[lado]["okexp2p"] is True
        assert data[lado]["bybitp2p"] is True
        assert data[lado]["bitgetp2p"] is False


def test_anuncio_curva_rechaza_tamanos_invalidos(tmp_path):
    client = TestClient(_app_publicar(tmp_path))
    assert client.get("/api/anuncio/curva?sizes=cero").status_code == 422
    assert client.get("/api/anuncio/curva?sizes=-5").status_code == 422
    assert client.get("/api/anuncio/curva?sizes=" +
                      ",".join(str(i) for i in range(1, 20))).status_code == 422


# --- Lemon P2P: se puede publicar ahí, pero no hay orderbook (2026-08-29) ---

def _fetchers_binance_barato():
    """Binance con bid 1592,52: comprar publicando ahí es lo más barato."""
    from p2p_scanner import Ad

    def f(asset, fiat, side, rows=20):
        price = 1598.0 if side == "BUY" else 1592.52
        return [Ad(exchange="x", side=side, price=price, min_amount=10_000,
                   max_amount=9_000_000, available=100000.0)] * 8
    return {"binance": f}


_PAYLOAD_LEMON_ANCHO = {
    "lemoncashp2p": {"ask": 1620.0, "totalAsk": 1644.3,
                     "bid": 1596.68, "totalBid": 1572.73, "time": 0},
}


def _app_lemon(tmp_path, monkeypatch):
    import webapp.server as server
    from core.trades_db import TradesDB
    server._estrategia_cache.clear()
    monkeypatch.setattr("core.criptoya.fetch_payload",
                        lambda a, f, v, **k: _PAYLOAD_LEMON_ANCHO)
    monkeypatch.setattr("time.time", lambda: 0.0)
    return server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                             parser=lambda b, m: {}, html_path=None,
                             p2p_fetchers=_fetchers_binance_barato())


def test_lemon_aparece_como_jugada_de_publicar_cuando_el_gap_paga(tmp_path, monkeypatch):
    d = TestClient(_app_lemon(tmp_path, monkeypatch)).get("/api/estrategia?volume=1000").json()
    best = d["best"]
    assert best["sell_venue"] == "lemoncashp2p"
    assert best["sell_mode"] == "publicando"      # antes ni se evaluaba
    assert best["sell_price"] == pytest.approx(1620.0)   # crudo, no el 1644,3


def test_lemon_cobra_1_por_publicar_no_1_5_de_tomador(tmp_path, monkeypatch):
    d = TestClient(_app_lemon(tmp_path, monkeypatch)).get("/api/estrategia?volume=1000").json()
    bruto = (1620.0 - 1592.52) / 1592.52 * 100
    # 0,2% maker de Binance + 1% maker de Lemon + 0,1% de red (es cross-venue)
    assert d["best"]["net_pct"] == pytest.approx(bruto - 0.2 - 1.0 - 0.1)


def test_la_respuesta_avisa_que_lemon_no_tiene_profundidad(tmp_path, monkeypatch):
    d = TestClient(_app_lemon(tmp_path, monkeypatch)).get("/api/estrategia?volume=1000").json()
    assert "lemoncashp2p" in d["sin_profundidad"]
    assert "lemoncashp2p" not in d["liquidez"]   # no se inventa una medición


# --- Fee real por modo: Binance no cobra 0,20% al tomar (2026-08-29) ---

def _fetchers_instant():
    """Libro donde la única jugada es instantánea: tomar de los dos lados."""
    from p2p_scanner import Ad

    def bina(asset, fiat, side, rows=20):
        price = 1600.0 if side == "BUY" else 1590.0
        return [Ad(exchange="b", side=side, price=price, min_amount=10_000,
                   max_amount=9_000_000, available=100000.0)] * 8

    def okx(asset, fiat, side, rows=20):
        price = 1620.0 if side == "BUY" else 1610.0
        return [Ad(exchange="o", side=side, price=price, min_amount=10_000,
                   max_amount=9_000_000, available=100000.0)] * 8
    return {"binance": bina, "okx": okx}


def test_tomar_en_binance_cobra_el_flat_de_007_usdt_no_el_020_del_maker(tmp_path, monkeypatch):
    """Con un ticket de 1.000 USDT, 0,07 USDT son 0,007%, no 0,20%.

    Cobrarle 0,20% al que toma (que es el precio de PUBLICAR) infla el costo
    ~28 veces y esconde jugadas instantáneas que sí dan.
    """
    import webapp.server as server
    from core.trades_db import TradesDB
    server._estrategia_cache.clear()
    monkeypatch.setattr("core.criptoya.fetch_payload", lambda a, f, v, **k: {})
    app = server.create_app(db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
                            parser=lambda b, m: {}, html_path=None,
                            p2p_fetchers=_fetchers_instant())
    d = TestClient(app).get("/api/estrategia?volume=1000").json()
    inst = [p for p in [d["best"], d["con_volumen"]] + d["alternatives"]
            if p and p["kind"] == "instant"][0]
    # comprar tomando en binance 1600 -> vender tomando en okx 1610
    assert inst["buy_venue"] == "binancep2p" and inst["buy_mode"] == "tomando"
    bruto = (1610.0 - 1600.0) / 1600.0 * 100
    # binance tomando 0,007% (flat 0,07 / 1000) + okx cero + 0,1% de red cross
    assert inst["net_pct"] == pytest.approx(bruto - 0.007 - 0.1)


# --- /api/puntas: a qué precio se publica en cada venue y cuál es el mejor cruce ---

def _fetchers_puntas():
    """Binance y Bybit responden; KuCoin se cae. Precios del 2026-09-12."""
    from p2p_scanner import Ad

    def _ad(ex, side, price, avail=500.0):
        return Ad(exchange=ex, side=side, price=price, min_amount=1000.0,
                  max_amount=500000.0, available=avail, merchant="m",
                  orders=100, finish_rate=0.98)

    def binance(asset, fiat, side, rows=20):
        return ([_ad("binance", "BUY", 1594.0), _ad("binance", "BUY", 1595.0)]
                if side == "BUY" else
                [_ad("binance", "SELL", 1589.5), _ad("binance", "SELL", 1589.0)])

    def bybit(asset, fiat, side, rows=20):
        return ([_ad("bybit", "BUY", 1602.0)] if side == "BUY"
                else [_ad("bybit", "SELL", 1593.0)])

    def kucoin(asset, fiat, side, rows=20):
        raise RuntimeError("451")

    return {"binance": binance, "bybit": bybit, "kucoin": kucoin}


@pytest.fixture
def sin_apodos(monkeypatch):
    """Modo manual: sin apodos propios, vale el precio que manda el navegador."""
    import config
    monkeypatch.setattr(config, "MIS_NICKS_P2P", ())


def _libro_con_mio(propio_venta=None, propio_compra=None):
    from p2p_scanner import Ad

    def _ad(side, price, merchant):
        return Ad(exchange="binance", side=side, price=price, min_amount=1000.0,
                  max_amount=500000.0, available=500.0, merchant=merchant)

    def binance(asset, fiat, side, rows=20):
        if side == "BUY":
            return [_ad("BUY", 1597.0, "m")] + ([_ad("BUY", propio_venta, "MiApodoP2P")] if propio_venta else [])
        return [_ad("SELL", 1592.0, "m")] + ([_ad("SELL", propio_compra, "MiApodoP2P")] if propio_compra else [])
    return {"binance": binance}


def test_puntas_mide_el_precio_real_de_mi_aviso_no_el_tipeado(tmp_path, monkeypatch):
    """El casillero decía 1.597 (el del rival) y mi aviso estaba en 1.599: me pasaron."""
    import config
    monkeypatch.setattr(config, "MIS_NICKS_P2P", ("MiApodoP2P",))
    d = _ads_app(tmp_path, _libro_con_mio(propio_venta=1599.0)).get(
        "/api/puntas?venues=binance&tol=1&mis=binance:venta:1597").json()
    a = d["avisos"][0]
    assert a["mi_precio"] == 1599.0 and a["estado"] == "pasado"
    assert d["mios"]["binancep2p"] == {"compra": None, "venta": 1599.0}


def test_puntas_avisa_si_mi_aviso_no_aparece_en_el_libro(tmp_path, monkeypatch):
    """Bybit 13/09: el aviso de compra no estaba entre los 20 primeros y decía 'sos la punta'."""
    import config
    monkeypatch.setattr(config, "MIS_NICKS_P2P", ("MiApodoP2P",))
    d = _ads_app(tmp_path, _libro_con_mio()).get(
        "/api/puntas?venues=binance&tol=1&mis=binance:compra:1592").json()
    a = d["avisos"][0]
    assert a["estado"] == "fuera"
    assert a["sugerido"] == 1592.0


def test_puntas_no_cuenta_mis_propios_avisos(tmp_path, monkeypatch):
    """Mi aviso primero en el libro no puede ser la punta contra la que me mido."""
    from p2p_scanner import Ad
    import config
    monkeypatch.setattr(config, "MIS_NICKS_P2P", ("MiApodoP2P",))

    def _ad(side, price, merchant):
        return Ad(exchange="binance", side=side, price=price, min_amount=1000.0,
                  max_amount=500000.0, available=500.0, merchant=merchant)

    def binance(asset, fiat, side, rows=20):
        return ([_ad("BUY", 1599.0, "m")] if side == "BUY" else
                [_ad("SELL", 1594.05, "MiApodoP2P"), _ad("SELL", 1592.0, "m")])

    r = _ads_app(tmp_path, {"binance": binance}).get(
        "/api/puntas?venues=binance&tol=1&mis=binance:compra:1594.05")
    d = r.json()
    assert d["puntas"][0]["comprar_publicando"] == 1592.0
    assert d["avisos"][0]["estado"] == "regalando"


def test_puntas_da_los_dos_lados_de_cada_venue(tmp_path):
    r = _ads_app(tmp_path, _fetchers_puntas()).get("/api/puntas?venues=binance,bybit")
    assert r.status_code == 200
    d = {p["venue"]: p for p in r.json()["puntas"]}
    assert d["binancep2p"]["comprar_publicando"] == 1589.5
    assert d["binancep2p"]["vender_publicando"] == 1594.0
    assert d["bybitp2p"]["vender_publicando"] == 1602.0


def test_puntas_marca_el_venue_caido_y_no_lo_inventa(tmp_path):
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance,bybit,kucoin").json()
    assert "kucoinp2p" in d["caidos"]
    assert all(p["venue"] != "kucoinp2p" for p in d["puntas"])


def test_puntas_rankea_el_mejor_cruce_neto(tmp_path):
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance,bybit&tanda=1000").json()
    mejor = d["cruces"][0]
    assert (mejor["comprar_en"], mejor["vender_en"]) == ("binancep2p", "bybitp2p")
    assert mejor["neto_ars_por_usdt"] > 0


def test_puntas_sin_ningun_libro_no_devuelve_precios_de_mentira(tmp_path):
    r = _ads_app(tmp_path, {"kucoin": _fetchers_puntas()["kucoin"]}).get(
        "/api/puntas?venues=kucoin")
    assert r.status_code == 502


def test_puntas_dice_si_mi_aviso_publicado_sigue_siendo_la_punta(tmp_path, sin_apodos):
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance,bybit&mis=binance:venta:1596,bybit:compra:1593").json()
    por_venue = {a["venue"]: a for a in d["avisos"]}
    # publiqué vender a 1596 y la punta de Binance está en 1594: me pasaron
    assert por_venue["binancep2p"]["estado"] == "pasado"
    assert por_venue["binancep2p"]["sugerido"] == 1594.0
    assert por_venue["binancep2p"]["diferencia_ars"] == 2.0
    # comprando a 1593 en Bybit sigo arriba de todos
    assert por_venue["bybitp2p"]["estado"] == "punta"


def test_puntas_ignora_un_aviso_escrito_mal_sin_romperse(tmp_path, sin_apodos):
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance&mis=cualquiera,binance:venta:,binance:venta:1594").json()
    assert len(d["avisos"]) == 1 and d["avisos"][0]["estado"] == "punta"


def _fetchers_tres_venues():
    """Binance, Bybit y KuCoin con los precios del 2026-09-12: el cruce más
    ancho (KuCoin → Bybit) no toca Binance, así que no suma para el Verificado."""
    from p2p_scanner import Ad

    def _ad(ex, side, price):
        return Ad(exchange=ex, side=side, price=price, min_amount=1000.0,
                  max_amount=500000.0, available=500.0, merchant="m",
                  orders=100, finish_rate=0.98)

    def mk(ex, venden, compran):
        def f(asset, fiat, side, rows=20):
            return [_ad(ex, "BUY", venden)] if side == "BUY" else [_ad(ex, "SELL", compran)]
        return f

    return {"binance": mk("binance", 1594.0, 1589.5),
            "bybit": mk("bybit", 1600.0, 1593.55),
            "kucoin": mk("kucoin", 1599.0, 1585.15)}


def test_puntas_pone_primero_la_jugada_que_suma_para_el_verificado(tmp_path):
    d = _ads_app(tmp_path, _fetchers_tres_venues()).get("/api/puntas").json()
    assert d["cruces"][0]["patas_binance"] >= 1


def test_puntas_no_esconde_la_ruta_que_deja_mas_aunque_no_sume(tmp_path):
    d = _ads_app(tmp_path, _fetchers_tres_venues()).get("/api/puntas").json()
    fuera = d["fuera_objetivo"]
    assert fuera["patas_binance"] == 0
    assert fuera["neto_ars_por_usdt"] > d["cruces"][0]["neto_ars_por_usdt"]


def test_puntas_sin_priorizar_vuelve_al_ranking_por_plata(tmp_path):
    d = _ads_app(tmp_path, _fetchers_tres_venues()).get("/api/puntas?priorizar=").json()
    assert d["cruces"][0]["patas_binance"] == 0
    assert d["fuera_objetivo"] is None


def test_puntas_avisa_cuando_el_libro_se_movio_a_favor_y_quedaste_barato(tmp_path, sin_apodos):
    """Vendiendo a 1590 con la punta en 1594: seguís primero, pero regalás 4 ARS."""
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance&mis=binance:venta:1590").json()
    a = d["avisos"][0]
    assert a["estado"] == "regalando"
    assert a["sugerido"] == 1594.0


def test_puntas_no_molesta_por_una_diferencia_chica(tmp_path, sin_apodos):
    d = _ads_app(tmp_path, _fetchers_puntas()).get(
        "/api/puntas?venues=binance&mis=binance:venta:1593.5&tol=1").json()
    assert d["avisos"][0]["estado"] == "punta"
