from decimal import Decimal

from core.movements import Side
from core.criptoya import Reference
from cli import prepare_ad


class FakeAd:
    def __init__(self, price, max_amount):
        self.price = price
        self.max_amount = max_amount


def test_rival_prices_filtra_por_liquidez():
    ads = [FakeAd(1490, 200000), FakeAd(1485, 50000), FakeAd(1500, 300000)]
    precios = prepare_ad.rival_prices(ads, Decimal("100000"))
    assert precios == [Decimal("1490"), Decimal("1500")]


def test_suggest_vender_competitivo_supera_piso():
    # rivales venden a 1490/1493; costo 1400 => piso 1414 (margen 1%)
    s = prepare_ad.suggest(
        [Decimal("1490"), Decimal("1493")], Decimal("1400"), Side.VENTA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"),
    )
    assert s.competitive == Decimal("1489")
    assert s.margin == Decimal("1414.00")
    assert s.final == Decimal("1489")


def test_suggest_vender_usa_piso_si_mercado_no_da_margen():
    # rivales a 1410/1412 => competitivo 1409 < piso 1414 => final = piso
    s = prepare_ad.suggest(
        [Decimal("1410"), Decimal("1412")], Decimal("1400"), Side.VENTA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"),
    )
    assert s.final == Decimal("1414.00")
    assert "margen" in s.note.lower()


def test_suggest_vender_circuit_breaker_distingue_de_sin_rivales():
    # rival a 9000 (fuera de [500,5000]) => competitive circuit-broken, pero HAY rival
    s = prepare_ad.suggest(
        [Decimal("9000")], Decimal("1400"), Side.VENTA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"),
    )
    assert s.competitive is None
    assert s.final == Decimal("1414.00")
    assert "circuit breaker" in s.note.lower()


def test_suggest_comprar_solo_competitivo():
    s = prepare_ad.suggest(
        [Decimal("1480"), Decimal("1485")], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"),
    )
    assert s.competitive == Decimal("1486")
    assert s.margin is None
    assert s.final == Decimal("1486")
    assert "no disponible" in s.note.lower()


def test_suggest_sin_rivales_vender_publica_al_piso():
    s = prepare_ad.suggest(
        [], Decimal("1400"), Side.VENTA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"),
    )
    assert s.competitive is None
    assert s.final == Decimal("1414.00")


def test_format_report_incluye_precios_y_bloque_de_anuncio():
    s = prepare_ad.Suggestion(
        side=Side.VENTA, competitive=Decimal("1489"),
        margin=Decimal("1414.00"), final=Decimal("1489"), note="",
    )
    out = prepare_ad.format_report(
        s, asset="USDT", ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash", "MercadoPago"],
    )
    assert "1489" in out          # precio final
    assert "1414" in out          # precio por margen
    assert "30000" in out and "150000" in out
    assert "LemonCash" in out
    assert "VENTA" in out.upper()


def test_format_report_redondea_a_dos_decimales():
    s = prepare_ad.Suggestion(
        side=Side.VENTA, competitive=Decimal("1489"),
        margin=Decimal("1414.567"), final=Decimal("1489"), note="",
    )
    out = prepare_ad.format_report(
        s, asset="USDT", ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash"],
    )
    assert "1414.57" in out
    assert "1414.567" not in out


# ── Task 4: suggest con reference ──────────────────────────────────────────


def _ref(bid="1498", ask="1495"):
    return Reference(Decimal(bid), "buenbit", Decimal(ask), "ripio")


def test_suggest_comprar_con_reference_aplica_techo():
    # competitive = max(rivals)+tick = 1486; techo = 1495*(1-1%) = 1480.05
    # final = min(1486, 1480.05) = 1480.05
    s = prepare_ad.suggest(
        [Decimal("1480"), Decimal("1485")], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=_ref(),
    )
    assert s.competitive == Decimal("1486")
    assert s.margin_criptoya == Decimal("1480.05")
    assert s.final == Decimal("1480.05")
    assert "criptoya" in s.note.lower()


def test_suggest_comprar_sin_reference_es_fase1():
    s = prepare_ad.suggest(
        [Decimal("1480"), Decimal("1485")], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=None,
    )
    assert s.final == Decimal("1486")
    assert "no disponible" in s.note.lower()


def test_suggest_vender_con_reference_es_informativo():
    # final igual que Fase 1 (piso de costo); margin_criptoya = 1498*(1+1%) = 1512.98
    s = prepare_ad.suggest(
        [Decimal("1490"), Decimal("1493")], Decimal("1400"), Side.VENTA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=_ref(),
    )
    assert s.final == Decimal("1489")            # idéntico a Fase 1
    assert s.margin_criptoya == Decimal("1512.98")
    assert s.reference_bid == Decimal("1498")


# ── Task 5: format_report muestra referencia CriptoYa ──────────────────────


def test_format_report_muestra_referencia_criptoya():
    s = prepare_ad.suggest(
        [Decimal("1480"), Decimal("1485")], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=_ref(),
    )
    out = prepare_ad.format_report(
        s, asset="USDT", ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash"],
    )
    assert "CriptoYa" in out
    assert "1495.00" in out          # best ask redondeado
    assert "ripio" in out
    assert "1480.05" in out          # margen vs CriptoYa (techo)


def test_suggest_comprar_con_reference_sin_rivales_usa_techo():
    # sin rivales => competitive None; con reference el techo gobierna
    s = prepare_ad.suggest(
        [], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=_ref(),
    )
    assert s.competitive is None
    assert s.final == Decimal("1480.05")          # techo = 1495*(1-1%)
    assert "criptoya" in s.note.lower()


def test_format_report_sin_referencia_dice_no_disponible():
    s = prepare_ad.suggest(
        [Decimal("1480")], Decimal("1400"), Side.COMPRA,
        tick=Decimal("1"), margin_pct=Decimal("1"),
        floor=Decimal("500"), ceil=Decimal("5000"), reference=None,
    )
    out = prepare_ad.format_report(
        s, asset="USDT", ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash"],
    )
    assert "CriptoYa" in out and "no disponible" in out.lower()


# ── Task 1: compute_suggestion + suggestion_payload ────────────────────────


class FakeAdWithLiquidity:
    def __init__(self, price, max_amount):
        self.price = price
        self.max_amount = max_amount


def _make_fetch_ads(ads):
    """Retorna un fetcher fake que ignora sus argumentos y devuelve `ads`."""
    def fetch(asset, fiat, trade_type):
        return ads
    return fetch


def _make_fetch_ref(reference):
    """Retorna un fetcher fake que devuelve `reference` (o tira si es Exception)."""
    if isinstance(reference, type) and issubclass(reference, Exception):
        exc_class = reference
        def fetch(asset, fiat, volume, *, whitelist):
            raise exc_class("fake error")
    elif isinstance(reference, Exception):
        exc = reference
        def fetch(asset, fiat, volume, *, whitelist):
            raise exc
    else:
        def fetch(asset, fiat, volume, *, whitelist):
            return reference
    return fetch


def test_compute_suggestion_devuelve_suggestion_esperada():
    """Con rivales conocidos + reference fake, compute_suggestion devuelve la Suggestion correcta."""
    from cli.prepare_ad import compute_suggestion, Side
    from core.criptoya import Reference

    ads = [FakeAdWithLiquidity(1490, 200000), FakeAdWithLiquidity(1493, 300000)]
    ref = Reference(Decimal("1498"), "buenbit", Decimal("1495"), "ripio")

    s = compute_suggestion(
        Side.VENTA, "USDT", "ARS",
        margin_pct=Decimal("1"),
        movements=[],
        fetch_ads=_make_fetch_ads(ads),
        fetch_ref=_make_fetch_ref(ref),
        tick=Decimal("1"),
        floor=Decimal("500"),
        ceil=Decimal("5000"),
        min_liquidity=Decimal("100000"),
        whitelist={"buenbit", "ripio"},
        volume=1000.0,
    )
    assert s.competitive == Decimal("1489")
    assert s.reference_bid == Decimal("1498")
    assert s.final == Decimal("1489")


def test_compute_suggestion_margen_usa_costo_de_hoy():
    """El margen se calcula sobre el costo de HOY, no el promedio histórico.

    Compra vieja barata (1400) + compra de hoy cara (1520). El piso por margen
    debe salir de 1520 (hoy), no del promedio. Mercado bajo => final = piso.
    """
    from datetime import date, timedelta
    from decimal import Decimal as D
    from cli.prepare_ad import compute_suggestion, Side
    from core.movements import Movement, Source

    hoy = date.today()
    ayer = hoy - timedelta(days=1)

    def mov(d, price, oid):
        return Movement(
            side=Side.COMPRA, date=d, order_id=oid,
            usd_gross=D("100"), commission=D("0"), usd_net=D("100"),
            price=D(str(price)), total_ars=D(str(price)) * D("100"),
            exchange_coin="binance / USDT", bank="x", source=Source.SCREENSHOT,
        )

    movs = [mov(ayer, 1400, "old"), mov(hoy, 1520, "new")]
    # rivales bajos => competitivo por debajo del piso => gana el piso (costo hoy)
    ads = [FakeAdWithLiquidity(1490, 200000)]

    s = compute_suggestion(
        Side.VENTA, "USDT", "ARS",
        margin_pct=Decimal("1"),
        movements=movs,
        fetch_ads=_make_fetch_ads(ads),
        fetch_ref=_make_fetch_ref(None),
        tick=Decimal("1"),
        floor=Decimal("500"),
        ceil=Decimal("5000"),
        min_liquidity=Decimal("100000"),
        whitelist=set(),
        volume=1000.0,
    )
    # piso = 1520 * 1,01 = 1535,20 (de HOY), no 1460*1,01 del promedio
    assert s.margin == Decimal("1535.20")


def test_compute_suggestion_fetch_ref_raising_da_reference_none():
    """Si fetch_ref tira excepcion, reference queda None y no rompe."""
    from cli.prepare_ad import compute_suggestion, Side

    ads = [FakeAdWithLiquidity(1490, 200000)]

    s = compute_suggestion(
        Side.VENTA, "USDT", "ARS",
        margin_pct=Decimal("1"),
        movements=[],
        fetch_ads=_make_fetch_ads(ads),
        fetch_ref=_make_fetch_ref(RuntimeError),
        tick=Decimal("1"),
        floor=Decimal("500"),
        ceil=Decimal("5000"),
        min_liquidity=Decimal("100000"),
        whitelist=set(),
        volume=1000.0,
    )
    assert s.reference_bid is None
    assert s.final is not None  # no explotó


def test_suggestion_payload_builds_dict_with_floats():
    """suggestion_payload arma el dict con floats y keys esperadas."""
    from cli.prepare_ad import compute_suggestion, suggestion_payload, Side

    ads = [FakeAdWithLiquidity(1490, 200000)]

    s = compute_suggestion(
        Side.VENTA, "USDT", "ARS",
        margin_pct=Decimal("1"),
        movements=[],
        fetch_ads=_make_fetch_ads(ads),
        fetch_ref=_make_fetch_ref(None),
        tick=Decimal("1"),
        floor=Decimal("500"),
        ceil=Decimal("5000"),
        min_liquidity=Decimal("100000"),
        whitelist=set(),
        volume=1000.0,
    )
    payload = suggestion_payload(
        s, Side.VENTA, "USDT",
        ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash", "MercadoPago"],
    )

    assert payload["side"] == "VENTA"
    assert payload["asset"] == "USDT"
    assert isinstance(payload["final"], float)
    assert payload["reference"] is None   # no habia reference
    assert payload["ad_min"] == 30000.0
    assert payload["ad_max"] == 150000.0
    assert payload["methods"] == ["LemonCash", "MercadoPago"]
    assert "ad_text" in payload


def test_suggestion_payload_reference_none_cuando_no_hay():
    """reference es None en el payload cuando no habia datos de CriptoYa."""
    from cli.prepare_ad import compute_suggestion, suggestion_payload, Side

    ads = [FakeAdWithLiquidity(1490, 200000)]

    s = compute_suggestion(
        Side.VENTA, "USDT", "ARS",
        margin_pct=Decimal("1"),
        movements=[],
        fetch_ads=_make_fetch_ads(ads),
        fetch_ref=_make_fetch_ref(ValueError),
        tick=Decimal("1"),
        floor=Decimal("500"),
        ceil=Decimal("5000"),
        min_liquidity=Decimal("100000"),
        whitelist=set(),
        volume=1000.0,
    )
    payload = suggestion_payload(
        s, Side.VENTA, "USDT",
        ad_min=Decimal("30000"), ad_max=Decimal("150000"),
        methods=["LemonCash"],
    )
    assert payload["reference"] is None
