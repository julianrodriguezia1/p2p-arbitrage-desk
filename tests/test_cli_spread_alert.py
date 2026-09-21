import core.criptoya
import config
import cli.spread_alert as cli


def test_run_once_incluye_candidatos_de_arbitraje(tmp_path, monkeypatch):
    from core.spread_alert import Opportunity

    monkeypatch.setattr(config, "SPREAD_ALERT_STATE_PATH", tmp_path / "state.json")

    # scan vacío: aislamos la rama de arbitraje.
    def fake_scan(asset, fiat):
        return []

    sent = {}
    def fake_send(msg, token, chat):
        sent["msg"] = msg

    def fake_arb(volume):
        return [Opportunity(
            kind="media", route="media", pct=0.55, threshold=0.2,
            title="🟡 Arbitraje media espera",
            detail="Comprá tomando en bybitp2p @ 1.562 → vendé publicando en kucoinp2p @ 1.570\nGanás +0.55% neto · ⏳ esperás de un lado",
        )]

    n = cli.run_once(scan_fn=fake_scan, send_fn=fake_send,
                     route_fn=lambda: None, arb_fn=fake_arb)
    assert n == 1
    assert "Arbitraje media espera" in sent["msg"]


def test_depth_quotes_arma_dict_por_venue(monkeypatch):
    from p2p_scanner import Ad

    def fake_fetcher(asset, fiat, side, rows=20):
        price = 1010.0 if side == "BUY" else 1000.0
        return [Ad(exchange="x", side=side, price=price, min_amount=0,
                   max_amount=0, available=5000.0)]

    # Solo bybit disponible; venues no presentes en FETCHERS se saltean.
    monkeypatch.setattr(cli, "FETCHERS", {"bybit": fake_fetcher})
    q = cli._depth_quotes(1000.0)
    assert q["bybitp2p"]["ask"] == 1010.0
    assert q["bybitp2p"]["bid"] == 1000.0


def test_arb_candidates_integracion_fee_alignment(monkeypatch):
    """Integración end-to-end: _arb_candidates con 2 boundaries de red mockeados.

    Precios fijos (todos los P2P globales, CriptoYa vacío):
      bybitp2p:   ask=1500.0  bid=1495.0  fee=0.0%
      binancep2p: ask=1500.0  bid=1495.0  fee=0.20%   <- mismo precio, más caro
      kucoinp2p:  ask=1520.0  bid=1518.0  fee=0.0%

    Aritmética (build_venues+best_routes, jugada 'media' gana en variante 2):
      Comprar publicando bybitp2p @ 1495 → vender tomando kucoinp2p @ 1518
      gross = (1518 - 1495) / 1495 * 100 = 23/1495 * 100
      fees  = FEE_PCT_BY_VENUE["bybitp2p"]=0.0  +  FEE_PCT_BY_VENUE["kucoinp2p"]=0.0
      net   = 23/1495 * 100  ≈ 1.5385% > umbral 0.2%  → Opportunity emitida

    Alineación de fees (el punto del test):
      Si hubiese ganado binancep2p publicando → kucoinp2p tomando:
        net = 23/1495*100 - 0.20 ≈ 1.3385%  (peor que 1.5385%)
      Por tanto el ganador DEBE ser bybitp2p (fee=0), NO binancep2p (fee=0.20).
      Si FEE_PCT_BY_VENUE["binancep2p"] dejase de aplicarse el test falla.
    """
    # Precios de referencia
    BYBIT_ASK = 1500.0
    BYBIT_BID = 1495.0
    KUCOIN_ASK = 1520.0
    KUCOIN_BID = 1518.0
    BINANCE_ASK = 1500.0
    BINANCE_BID = 1495.0

    fake_depth: dict[str, dict] = {
        "bybitp2p":   {"ask": BYBIT_ASK,  "bid": BYBIT_BID},
        "binancep2p": {"ask": BINANCE_ASK, "bid": BINANCE_BID},
        "kucoinp2p":  {"ask": KUCOIN_ASK, "bid": KUCOIN_BID},
    }

    # Boundary 1: sin red para _depth_quotes
    monkeypatch.setattr(cli, "_depth_quotes", lambda volume: fake_depth)

    # Boundary 2: sin red para CriptoYa (payload vacío → solo P2P)
    monkeypatch.setattr(core.criptoya, "fetch_payload", lambda asset, fiat, volume: {})

    candidates = cli._arb_candidates(1000.0)

    # Debe haber al menos una Opportunity de tipo "media"
    media = [c for c in candidates if c.kind == "media"]
    assert media, "No se emitió ninguna Opportunity de tipo 'media'"
    op = media[0]

    # Verificar valor neto exacto de la ruta ganadora:
    # bybitp2p publicando @ 1495 → kucoinp2p tomando @ 1518
    expected_net = (KUCOIN_BID - BYBIT_BID) / BYBIT_BID * 100  # = 23/1495*100
    assert abs(op.pct - expected_net) < 1e-9, (
        f"net esperado {expected_net:.10f}%, got {op.pct:.10f}%"
    )

    # Verificar venues y modos de la ruta ganadora (acceso al Route subyacente
    # no disponible en Opportunity; lo verificamos por el detail string que
    # format_message usa):
    assert "bybitp2p" in op.detail, f"buy_venue debe ser bybitp2p, got detail: {op.detail!r}"
    assert "kucoinp2p" in op.detail, f"sell_venue debe ser kucoinp2p, got detail: {op.detail!r}"

    # Alineación de fee: binancep2p NO debe ser el comprador ganador
    assert "binancep2p" not in op.detail or "bybitp2p" in op.detail, (
        "binancep2p apareció como comprador aunque su fee 0.20% lo hace peor que bybitp2p"
    )


# --- Piso de 0,5%: nada por debajo llega a Telegram (pedido 2026-08-28) ---

def test_config_define_el_piso_y_sube_los_defaults():
    import importlib
    importlib.reload(config)
    assert config.SPREAD_ALERT_MIN_PCT == 0.5
    assert config.SPREAD_ALERT_CROSS_PCT == 0.5
    assert config.SPREAD_ALERT_MEDIA_PCT == 0.5
    assert config.SPREAD_ALERT_MM_PCT == 0.5
    assert config.SPREAD_ALERT_INSTANT_PCT == 0.5


def test_piso_levanta_un_umbral_viejo_y_respeta_uno_mas_alto(monkeypatch):
    """El .env del VPS puede tener 0,2% de antes: el piso lo levanta igual."""
    monkeypatch.setattr(config, "SPREAD_ALERT_MIN_PCT", 0.5)
    assert cli._piso(0.2) == 0.5
    assert cli._piso(1.5) == 1.5


def test_run_once_evalua_con_los_umbrales_pisados(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SPREAD_ALERT_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(config, "TRADES_DB_PATH", tmp_path / "trades.db")
    monkeypatch.setattr(config, "SPREAD_ALERT_MIN_PCT", 0.5)
    monkeypatch.setattr(config, "SPREAD_ALERT_CROSS_PCT", 0.2)
    monkeypatch.setattr(config, "SPREAD_ALERT_INTRA_PCT", 0.3)
    monkeypatch.setattr(config, "SPREAD_ALERT_CEXP2P_PCT", 0.1)
    monkeypatch.setattr(cli, "find_opportunities", lambda quotes, asset: ([], []))

    visto = {}
    def fake_evaluate(intra, cross, **kw):
        visto.update(kw)
        return []
    monkeypatch.setattr(cli, "evaluate", fake_evaluate)

    class _Q:
        best_bid = 1600.0
    cli.run_once(scan_fn=lambda a, f: [_Q()], send_fn=lambda *a: None,
                 route_fn=lambda: None, arb_fn=lambda v: [])

    assert visto["cross_pct"] == 0.5
    assert visto["intra_pct"] == 0.5
    assert visto["cexp2p_pct"] == 0.5


def test_umbrales_de_arbitraje_tambien_tienen_piso(monkeypatch):
    monkeypatch.setattr(config, "SPREAD_ALERT_MIN_PCT", 0.5)
    monkeypatch.setattr(config, "SPREAD_ALERT_MEDIA_PCT", 0.2)
    monkeypatch.setattr(config, "SPREAD_ALERT_MM_PCT", 0.2)
    monkeypatch.setattr(config, "SPREAD_ALERT_INSTANT_PCT", 0.9)
    assert cli._arb_thresholds() == {"media": 0.5, "mm": 0.5, "instant": 0.9}
