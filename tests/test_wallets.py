from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source
from core import wallets as wl


def _mov(bank, side=Side.VENTA, total="1000", d=date(2026, 7, 1), oid="x"):
    return Movement(side=side, date=d, order_id=oid,
                    usd_gross=Decimal("1"), commission=Decimal("0"),
                    usd_net=Decimal("1"), price=Decimal("1000"),
                    total_ars=Decimal(total), exchange_coin="X / USDT", bank=bank,
                    source=Source.SCREENSHOT)


ALIAS_GROUPS = {
    "MercadoPago": ["MercadoPagoNew", "Mercadopago", "Mercado Pago"],
    "Sin clasificar": ["", "Binance Spot"],
}

LIMITS = {"MercadoPago": {"in": 2_000_000, "out": None}}


def test_norm_collapses_case_and_spaces():
    assert wl._norm("  Mercado  Pago ") == "mercado pago"
    assert wl._norm(None) == ""


def test_build_alias_lookup_maps_normalized_raw_to_canonical():
    lookup = wl.build_alias_lookup(ALIAS_GROUPS)
    assert lookup["mercadopagonew"] == "MercadoPago"
    assert lookup["mercado pago"] == "MercadoPago"
    assert lookup[""] == "Sin clasificar"


def test_canonical_for_maps_known_and_flags_unknown():
    lookup = wl.build_alias_lookup(ALIAS_GROUPS)
    assert wl.canonical_for("MercadoPagoNew", lookup) == ("MercadoPago", True)
    assert wl.canonical_for("", lookup) == ("Sin clasificar", True)
    assert wl.canonical_for("BilleteraNueva", lookup) == ("Sin clasificar", False)


def test_available_months_sorted_desc():
    movs = [_mov("x", d=date(2026, 5, 3)), _mov("x", d=date(2026, 7, 9)),
            _mov("x", d=date(2026, 7, 20))]
    assert wl.available_months(movs) == ["2026-07", "2026-05"]


def test_flows_group_alias_and_split_entra_sale():
    movs = [
        _mov("MercadoPagoNew", Side.VENTA, "1200000"),
        _mov("Mercadopago", Side.VENTA, "40000"),
        _mov("Mercado Pago", Side.COMPRA, "300000"),
    ]
    r = wl.monthly_wallet_flows(movs, "2026-07", ALIAS_GROUPS, LIMITS)
    mp = r["MercadoPago"]
    assert mp["entra"] == 1_240_000
    assert mp["sale"] == 300_000
    assert mp["n_entra"] == 2 and mp["n_sale"] == 1


def test_flows_tope_pct_and_restante():
    movs = [_mov("MercadoPagoNew", Side.VENTA, "1240000")]
    r = wl.monthly_wallet_flows(movs, "2026-07", ALIAS_GROUPS, LIMITS)
    mp = r["MercadoPago"]
    assert mp["tope_in"] == 2_000_000
    assert mp["pct_in"] == 62.0
    assert mp["restante_in"] == 760_000
    assert mp["pct_out"] is None and mp["restante_out"] is None  # tope_out None


def test_flows_unmapped_goes_to_bucket_and_is_listed():
    movs = [_mov("BilleteraNueva", Side.VENTA, "235650")]
    r = wl.monthly_wallet_flows(movs, "2026-07", ALIAS_GROUPS, LIMITS)
    assert r["Sin clasificar"]["entra"] == 235650
    assert r["_sin_mapear"] == ["BilleteraNueva"]


def test_flows_empty_bank_is_mapped_not_flagged():
    movs = [_mov("", Side.VENTA, "100")]
    r = wl.monthly_wallet_flows(movs, "2026-07", ALIAS_GROUPS, LIMITS)
    assert r["Sin clasificar"]["entra"] == 100
    assert r["_sin_mapear"] == []


def test_flows_filters_by_month():
    movs = [_mov("MercadoPagoNew", Side.VENTA, "999", d=date(2026, 5, 1))]
    r = wl.monthly_wallet_flows(movs, "2026-07", ALIAS_GROUPS, LIMITS)
    assert "MercadoPago" not in r
    assert r["_sin_mapear"] == []


def test_config_wallets_maps_messy_real_labels():
    import config_wallets as cw
    lookup = wl.build_alias_lookup(cw.WALLET_ALIASES)
    # variantes reales presentes en trades.db
    for raw, expected in [
        ("MercadoPagoNew", "MercadoPago"),
        ("Mercadopago", "MercadoPago"),
        ("Mercado Pago", "MercadoPago"),
        ("LemonCash", "Lemon Cash"),
        ("Lemon", "Lemon Cash"),
        ("UalaNew", "Ualá"),
        ("UalaNewest", "Ualá"),
        ("BankArgentina", "Banco"),
        ("", "Sin clasificar"),
        ("Binance Spot", "Sin clasificar"),
    ]:
        assert wl.canonical_for(raw, lookup) == (expected, True)


def test_config_limits_start_empty():
    import config_wallets as cw
    for name, lim in cw.WALLET_LIMITS.items():
        assert lim == {"in": None, "out": None}, name
