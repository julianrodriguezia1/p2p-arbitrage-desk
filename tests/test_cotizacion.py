"""Motor de cotización al cliente: precio EJECUTABLE, no el optimista.

El bug que originó este módulo (2026-08-21): el cotizador daba el precio de
PUBLICAR (que depende de que alguien te tome el aviso) y de la PUNTA del libro
(que puede ser un aviso de 0,012 BTC). El usuario cotizó con eso, no lo tomaron,
tuvo que comprar instantáneo más caro y perdió plata.
"""
import pytest

from core import cotizacion


class FakeAd:
    """Mismo pato que p2p_scanner.Ad para lo que usa el motor."""

    def __init__(self, price, available):
        self.price = price
        self.available = available


AHORA = 1_700_000_000.0
FEES = {
    "binancep2p": {"maker_pct": 0.20, "taker_pct": 0.0, "taker_flat_quote": 0.08},
    "okexp2p": {"maker_pct": 0.0, "taker_pct": 0.0, "taker_flat_quote": 0.0},
}
WL = {"binancep2p", "okexp2p", "fiwind", "bitsoalpha", "saldo"}


def _cy(**venues):
    """Payload estilo CriptoYa con time fresco."""
    return {n: {**v, "time": AHORA} for n, v in venues.items()}


def _build(criptoya=None, books=None, **kw):
    opts = dict(asset="BTC", size=0.01, margin_pct=0.5, whitelist=WL, fees=FEES,
                max_age_min=30, now=AHORA)
    opts.update(kw)
    return cotizacion.build(criptoya or {}, books or {}, **opts)


# ── CEX: precio neto y directo ────────────────────────────────────────────

def test_cex_usa_el_precio_neto_no_el_crudo():
    """totalAsk/totalBid ya traen la comisión. Usar ask/bid es cotizar de menos:
    Bitso figuraba a 121,4M y en realidad costaba 123,3M."""
    c = _build(_cy(fiwind={"ask": 121_400_000.0, "totalAsk": 123_300_000.0,
                           "bid": 121_000_000.0, "totalBid": 120_000_000.0}))
    assert c.buys[0].price == 123_300_000.0
    assert c.sells[0].price == 120_000_000.0
    assert c.buys[0].mode == "directo"


def test_cex_cae_al_crudo_si_no_viene_el_total():
    c = _build(_cy(fiwind={"ask": 123_000_000.0, "bid": 120_000_000.0}))
    assert c.buys[0].price == 123_000_000.0


def test_ignora_venues_fuera_de_whitelist():
    c = _build(_cy(dolarapp={"ask": 1.0, "totalAsk": 1.0,
                             "bid": 999.0, "totalBid": 999.0}))
    assert c.buys == [] and c.sells == []


def test_ignora_cotizaciones_rancias():
    viejo = {"fiwind": {"ask": 1.0, "totalAsk": 1.0, "bid": 1.0, "totalBid": 1.0,
                        "time": AHORA - 3600}}
    assert _build(viejo, max_age_min=30).buys == []


# ── P2P: profundidad real, no la punta del libro ──────────────────────────

def test_p2p_camina_el_libro_por_el_monto_pedido():
    """La punta tiene 0,002 BTC; para 0,01 BTC hay que caminar hasta el 3er
    aviso. El precio ejecutable es el VWAP, no los 122.000.000 de la punta."""
    books = {"okexp2p": {"BUY": [FakeAd(122_000_000.0, 0.002),
                                 FakeAd(123_000_000.0, 0.003),
                                 FakeAd(124_000_000.0, 0.05)]}}
    c = _build(books=books)
    esperado = (122_000_000 * 0.002 + 123_000_000 * 0.003
                + 124_000_000 * 0.005) / 0.01
    assert c.buys[0].price == pytest.approx(esperado)
    assert c.buys[0].price > 122_000_000.0        # nunca la punta sola
    assert c.buys[0].mode == "tomando"


def test_p2p_avisa_cuando_el_libro_no_alcanza():
    """Lo que le faltó saber: el libro entero tenía menos de lo que necesitaba."""
    books = {"okexp2p": {"BUY": [FakeAd(122_000_000.0, 0.003)]}}
    c = _build(books=books, size=0.01)
    assert c.buys[0].alcanza is False
    assert c.buys[0].stock == pytest.approx(0.003)


def test_p2p_alcanza_cuando_hay_stock_de_sobra():
    books = {"okexp2p": {"BUY": [FakeAd(122_000_000.0, 5.0)]}}
    c = _build(books=books, size=0.01)
    assert c.buys[0].alcanza is True and c.buys[0].stock == pytest.approx(5.0)


def test_p2p_libro_vacio_no_aporta_opcion():
    assert _build(books={"okexp2p": {"BUY": [], "SELL": []}}).buys == []


# ── comisiones por modo ───────────────────────────────────────────────────

def test_tomar_no_paga_el_fee_de_publicar():
    """El bug de config: a quien TOMA se le cobraba el 0,20% de maker. Tomar en
    Binance P2P cuesta un flat de centavos, no un porcentaje."""
    books = {"binancep2p": {"BUY": [FakeAd(100_000_000.0, 5.0)]}}
    c = _build(books=books, asset="BTC")
    assert c.buys[0].price == pytest.approx(100_000_000.0)   # sin 0,20%


def test_el_flat_de_tomador_solo_aplica_a_usdt():
    """Verificado en los comunicados de Binance: el flat está anunciado para
    pares USDT. En BTC no hay comunicado, así que no se cobra de prepo."""
    books = {"binancep2p": {"BUY": [FakeAd(1000.0, 5000.0)]}}
    c = _build(books=books, asset="USDT", size=1000.0)
    # 0,08 USDT sobre 1000 USDT = 0,008% encarece la compra
    assert c.buys[0].price == pytest.approx(1000.0 * (1 + 0.08 / 1000 / 100 * 100))

    c_btc = _build(books={"binancep2p": {"BUY": [FakeAd(1000.0, 5000.0)]}},
                   asset="BTC", size=1000.0)
    assert c_btc.buys[0].price == pytest.approx(1000.0)


def test_publicar_paga_el_fee_de_maker():
    # Libro normal: se compra tomando a 123M (lado BUY) y se vende tomando a
    # 122M (lado SELL). Publicar para comprar te pone en los 122M, 0,8% mejor.
    books = {"binancep2p": {"BUY": [FakeAd(123_000_000.0, 5.0)],
                            "SELL": [FakeAd(122_000_000.0, 5.0)]}}
    c = _build(books=books)
    assert c.mejor_publicando_compra.price == pytest.approx(122_000_000.0 * 1.002)
    assert c.mejor_publicando_compra.mode == "publicando"


# ── ranking y precio al cliente ───────────────────────────────────────────

_MERCADO = _cy(
    saldo={"ask": 122_900_000.0, "totalAsk": 122_948_635.0,
           "bid": 118_000_000.0, "totalBid": 118_000_000.0},
    fiwind={"ask": 123_100_000.0, "totalAsk": 123_132_589.0,
            "bid": 122_203_286.0, "totalBid": 122_203_286.0},
    bitsoalpha={"ask": 123_200_000.0, "totalAsk": 123_272_994.0,
                "bid": 121_000_000.0, "totalBid": 121_000_000.0},
)


def test_rankea_compras_de_mas_barata_a_mas_cara():
    c = _build(_MERCADO)
    assert [l.venue for l in c.buys] == ["saldo", "fiwind", "bitsoalpha"]


def test_rankea_ventas_de_mas_cara_a_mas_barata():
    c = _build(_MERCADO)
    assert [l.venue for l in c.sells] == ["fiwind", "bitsoalpha", "saldo"]


def test_top_limita_la_cantidad():
    assert len(_build(_MERCADO, top=2).buys) == 2


def test_precio_al_cliente_suma_y_resta_el_margen():
    c = _build(_MERCADO, margin_pct=0.5)
    assert c.precio_venta_cliente == pytest.approx(122_948_635.0 * 1.005)
    assert c.precio_compra_cliente == pytest.approx(122_203_286.0 * 0.995)


# ── el veredicto que le habría evitado la pérdida ─────────────────────────

def test_avisa_cuando_el_margen_no_cubre_el_costo_de_darse_vuelta():
    """Comprar a 122.948.635 y vender a 122.203.286 cuesta 0,61%. Con 0,5% de
    margen se pierde: eso es exactamente lo que pasó el 2026-08-21."""
    c = _build(_MERCADO, margin_pct=0.5)
    assert c.vuelta_pct == pytest.approx(
        (122_203_286.0 - 122_948_635.0) / 122_948_635.0 * 100)
    assert c.cubre is False
    assert c.faltante_pct == pytest.approx(-c.vuelta_pct - 0.5)


def test_cubre_cuando_el_margen_supera_el_costo():
    c = _build(_MERCADO, margin_pct=2.0)
    assert c.cubre is True and c.faltante_pct is None


def test_margen_justo_en_el_limite_cubre():
    c = _build(_MERCADO, margin_pct=0.61)
    assert c.cubre is True


def test_sin_mercado_no_inventa_precio():
    c = _build({})
    assert c.buys == [] and c.sells == []
    assert c.precio_venta_cliente is None and c.precio_compra_cliente is None
    assert c.cubre is False and c.vuelta_pct is None


# ── endpoint /api/cotizacion ──────────────────────────────────────────────

def _app(tmp_path, fake_cotizacion):
    from fastapi.testclient import TestClient
    from webapp.server import create_app
    from core.trades_db import TradesDB
    from tests.test_server import FakeWriter
    return TestClient(create_app(
        db=TradesDB(tmp_path / "t.db"), writer=FakeWriter(),
        parser=lambda b, m: {}, html_path=None, cotizacion=fake_cotizacion))


def test_endpoint_pasa_activo_monto_y_margen(tmp_path):
    visto = {}

    def fake(asset, size, margin_pct, top=3):
        visto.update(asset=asset, size=size, margin_pct=margin_pct)
        return {"asset": asset}

    r = _app(tmp_path, fake).get("/api/cotizacion",
                                 params={"asset": "btc", "size": 0.05, "margen": 2})
    assert r.status_code == 200
    assert visto == {"asset": "BTC", "size": 0.05, "margin_pct": 2.0}


def test_endpoint_usa_los_defaults_de_config(tmp_path):
    """Sin monto ni margen: 0,01 para BTC (config) y el margen por defecto."""
    import config
    visto = {}

    def fake(asset, size, margin_pct, top=3):
        visto.update(asset=asset, size=size, margin_pct=margin_pct)
        return {}

    _app(tmp_path, fake).get("/api/cotizacion", params={"asset": "BTC"})
    assert visto["size"] == config.CRIPTOYA_VOLUME_BY_ASSET["BTC"]
    assert visto["margin_pct"] == config.COTIZA_MARGEN_PCT


def test_endpoint_activo_desconocido_es_400(tmp_path):
    llamadas = []
    r = _app(tmp_path, lambda **k: llamadas.append(k)).get(
        "/api/cotizacion", params={"asset": "ETH"})
    assert r.status_code == 400 and llamadas == []


def test_endpoint_monto_invalido_es_400(tmp_path):
    llamadas = []
    r = _app(tmp_path, lambda **k: llamadas.append(k)).get(
        "/api/cotizacion", params={"asset": "BTC", "size": 0})
    assert r.status_code == 400 and llamadas == []


def test_endpoint_falla_con_502(tmp_path):
    def boom(asset, size, margin_pct):
        raise RuntimeError("criptoya caído")
    assert _app(tmp_path, boom).get("/api/cotizacion").status_code == 502


# ── el mensaje que llega a Telegram ───────────────────────────────────────

_PAYLOAD = {
    "asset": "BTC", "size": 0.01, "margin_pct": 0.5,
    "buys": [
        {"venue": "saldo", "price": 122_948_635.0, "mode": "directo",
         "stock": None, "alcanza": True},
        {"venue": "binancep2p", "price": 123_132_589.0, "mode": "tomando",
         "stock": 0.003, "alcanza": False},
        {"venue": "bitsoalpha", "price": 123_272_994.0, "mode": "directo",
         "stock": None, "alcanza": True},
    ],
    "sells": [
        {"venue": "binancep2p", "price": 122_224_705.0, "mode": "tomando",
         "stock": 10.56, "alcanza": True},
        {"venue": "fiwind", "price": 122_203_286.0, "mode": "directo",
         "stock": None, "alcanza": True},
    ],
    "precio_venta_cliente": 123_563_378.0,
    "precio_compra_cliente": 121_613_581.0,
    "vuelta_pct": -0.59, "cubre": False, "faltante_pct": 0.09,
    "publicando_compra": {"venue": "binancep2p", "price": 122_244_000.0,
                          "mode": "publicando", "stock": 0.74, "alcanza": True},
    "publicando_venta": None,
}


def _texto(payload, monkeypatch):
    import bot.commands as c
    monkeypatch.setattr(c, "fetch_json", lambda base, path, params=None: payload)
    return c.cotizacion_text("http://x", asset="BTC")


def test_texto_muestra_las_dos_puntas_con_top3(monkeypatch):
    t = _texto(_PAYLOAD, monkeypatch)
    assert "COMPRÁS" in t and "VENDÉS" in t
    assert "SaldoAr" in t and "Binance P2P" in t and "Bitso" in t
    assert "123.563.378" in t and "121.613.581" in t


def test_texto_avisa_fuerte_cuando_el_margen_no_cubre(monkeypatch):
    """Es el aviso que le habría evitado la pérdida: tiene que ser imposible
    de pasar por alto."""
    t = _texto(_PAYLOAD, monkeypatch)
    assert "NO CUBRE" in t and "0,09" in t


def test_texto_confirma_cuando_el_margen_cubre(monkeypatch):
    t = _texto({**_PAYLOAD, "cubre": True, "faltante_pct": None,
                "vuelta_pct": -0.2, "margin_pct": 2.0}, monkeypatch)
    assert "NO CUBRE" not in t


def test_texto_marca_el_venue_sin_stock_suficiente(monkeypatch):
    """Binance P2P entra 2do para comprar pero solo tiene 0,003 de los 0,01."""
    t = _texto(_PAYLOAD, monkeypatch)
    assert "no alcanza" in t.lower()


def test_texto_dice_el_monto_cotizado(monkeypatch):
    """Un precio sin el monto al que corresponde es la mitad del dato."""
    assert "0,01 BTC" in _texto(_PAYLOAD, monkeypatch)


def test_texto_muestra_la_alternativa_de_publicar(monkeypatch):
    t = _texto(_PAYLOAD, monkeypatch)
    assert "publicá" in t.lower() or "publicando" in t.lower()


def test_texto_sin_mercado_no_inventa(monkeypatch):
    vacio = {**_PAYLOAD, "buys": [], "sells": [], "precio_venta_cliente": None,
             "precio_compra_cliente": None, "vuelta_pct": None, "cubre": False,
             "faltante_pct": None, "publicando_compra": None,
             "publicando_venta": None}
    t = _texto(vacio, monkeypatch)
    assert "no pude" in t.lower() or "sin precio" in t.lower()


def test_texto_si_falla_la_red_no_rompe(monkeypatch):
    import bot.commands as c

    def boom(base, path, params=None):
        raise RuntimeError("sin red")

    monkeypatch.setattr(c, "fetch_json", boom)
    assert "probá de nuevo" in c.cotizacion_text("http://x", asset="BTC")


# ── publicar solo se sugiere si el libro está vivo ─────────────────────────

def test_no_sugiere_publicar_en_un_libro_muerto():
    """KuCoin en BTC tenía 2 avisos y publicar daba 4% abajo del mercado. Un
    precio así no es una oportunidad: es un libro donde nadie te va a tomar."""
    mercado = _cy(fiwind={"ask": 122_000_000.0, "totalAsk": 122_000_000.0,
                          "bid": 121_000_000.0, "totalBid": 121_000_000.0})
    books = {"okexp2p": {"SELL": [FakeAd(117_000_000.0, 5.0)]}}   # 4% abajo
    c = _build(mercado, books)
    assert c.mejor_publicando_compra is None


def test_sugiere_publicar_cuando_la_mejora_es_creible():
    mercado = _cy(fiwind={"ask": 122_000_000.0, "totalAsk": 122_000_000.0,
                          "bid": 121_000_000.0, "totalBid": 121_000_000.0})
    books = {"okexp2p": {"SELL": [FakeAd(121_500_000.0, 5.0)]}}   # 0,4% abajo
    c = _build(mercado, books)
    assert c.mejor_publicando_compra is not None
    assert c.mejor_publicando_compra.price == pytest.approx(121_500_000.0)


def test_no_sugiere_publicar_si_no_hay_stock_para_el_monto():
    mercado = _cy(fiwind={"ask": 122_000_000.0, "totalAsk": 122_000_000.0,
                          "bid": 121_000_000.0, "totalBid": 121_000_000.0})
    books = {"okexp2p": {"SELL": [FakeAd(121_500_000.0, 0.001)]}}
    assert _build(mercado, books, size=0.01).mejor_publicando_compra is None


def test_no_sugiere_publicar_si_no_mejora_el_precio_ejecutable():
    """Publicar más caro que comprar al toque no tiene sentido."""
    mercado = _cy(fiwind={"ask": 121_000_000.0, "totalAsk": 121_000_000.0,
                          "bid": 120_000_000.0, "totalBid": 120_000_000.0})
    books = {"okexp2p": {"SELL": [FakeAd(121_500_000.0, 5.0)]}}
    assert _build(mercado, books).mejor_publicando_compra is None


def test_texto_aclara_de_donde_sale_cada_precio(monkeypatch):
    """En P2P se ve el libro real; en CEX es la cotización del exchange y no hay
    profundidad visible. Decirlo evita creer que 'directo' garantiza el monto."""
    t = _texto(_PAYLOAD, monkeypatch)
    assert "P2P" in t and "CEX" in t
    assert "se mueve" in t.lower() or "revalidá" in t.lower()


# ── Ruta sintética ARS→USDT→BTC ───────────────────────────────────────────
# Comprar BTC contra pesos es cruzar un mercado sin contraparte (22/08/2026:
# 1,54% de ancho en Binance P2P, 14,49% en OKX). Encadenar USDT/ARS con
# BTC/USDT sale más barato. El motor arma esa ruta como una pata más y la deja
# competir por precio: si la directa gana, gana la directa.

SPOT = {"ask": 77_000.0, "bid": 76_900.0, "fuente": "okx"}


def _usdt_cot(compra=1_580.0, venta=1_570.0, venue="binancep2p", stock=5_000.0):
    """Cotización de USDT ya resuelta, como la que le pasa el server."""
    return cotizacion.Cotizacion(
        asset="USDT", size=770.0, margin_pct=0.5,
        buys=[cotizacion.Leg(venue, compra, "tomando", stock, True)],
        sells=[cotizacion.Leg(venue, venta, "tomando", stock, True)],
        precio_venta_cliente=None, precio_compra_cliente=None,
        vuelta_pct=None, cubre=False, faltante_pct=None,
        mejor_publicando_compra=None, mejor_publicando_venta=None)


def test_arma_la_pata_sintetica_encadenando_usdt_y_spot():
    """precio = USDT/ARS × BTC/USDT × (1 + fee de spot)."""
    c = _build(spot=SPOT, usdt=_usdt_cot(compra=1_580.0), spot_fee_pct=0.1)
    via = [l for l in c.buys if l.mode == "vía USDT"]
    assert len(via) == 1
    assert via[0].price == pytest.approx(1_580.0 * 77_000.0 * 1.001)
    assert via[0].venue == "binancep2p"


def test_la_sintetica_gana_si_es_mas_barata_que_la_directa():
    """El caso que motivó todo: el BTC directo salía 1,38% más caro."""
    c = _build(_cy(fiwind={"ask": 130_000_000.0, "bid": 120_000_000.0}),
               spot=SPOT, usdt=_usdt_cot(compra=1_580.0), spot_fee_pct=0.1)
    assert c.buys[0].mode == "vía USDT"


def test_la_directa_gana_si_es_mas_barata():
    """No es una ruta privilegiada: compite por precio como cualquier otra."""
    c = _build(_cy(fiwind={"ask": 100_000_000.0, "bid": 90_000_000.0}),
               spot=SPOT, usdt=_usdt_cot(compra=1_580.0), spot_fee_pct=0.1)
    assert c.buys[0].mode == "directo"
    assert c.buys[0].venue == "fiwind"


def test_la_punta_de_venta_usa_el_bid_y_resta_el_fee():
    c = _build(spot=SPOT, usdt=_usdt_cot(venta=1_570.0), spot_fee_pct=0.1)
    via = [l for l in c.sells if l.mode == "vía USDT"]
    assert via[0].price == pytest.approx(1_570.0 * 76_900.0 * 0.999)


def test_sin_spot_no_hay_pata_sintetica():
    """OKX y Kraken caídos: la cotización sigue viva, solo sin la ruta."""
    c = _build(_cy(fiwind={"ask": 123_000_000.0, "bid": 120_000_000.0}),
               spot=None, usdt=_usdt_cot())
    assert all(l.mode != "vía USDT" for l in c.buys + c.sells)
    assert c.buys[0].venue == "fiwind"


def test_ignora_venues_sin_spot_propio():
    """Comprar el USDT en Fiwind y convertirlo en Binance obliga a mover el USDT
    y pagar fee de red — eso se come la ventaja. Solo venues con spot propio."""
    c = _build(spot=SPOT, usdt=_usdt_cot(venue="fiwind"), spot_fee_pct=0.1)
    assert all(l.mode != "vía USDT" for l in c.buys)


def test_el_stock_de_la_sintetica_va_en_btc():
    """La pata de USDT trae stock en USDT; mostrarlo así al lado de un monto en
    BTC diría que hay 5.000 BTC cuando hay 0,06."""
    c = _build(spot=SPOT, usdt=_usdt_cot(stock=5_000.0), spot_fee_pct=0.1)
    via = [l for l in c.buys if l.mode == "vía USDT"][0]
    assert via.stock == pytest.approx(5_000.0 / 77_000.0)


def test_guarda_los_pasos_para_poder_explicarlos():
    """El bot tiene que poder decir 'comprás X USDT acá y convertís allá'."""
    c = _build(spot=SPOT, usdt=_usdt_cot(compra=1_580.0), spot_fee_pct=0.1)
    via = [l for l in c.buys if l.mode == "vía USDT"][0]
    assert via.via == {"usdt_price": 1_580.0, "spot_price": 77_000.0,
                       "fuente": "okx"}


# ── El texto del bot tiene que explicar la ruta sintética ─────────────────

_PAYLOAD_VIA = {
    "asset": "BTC", "size": 0.0122, "margin_pct": 1.5,
    "buys": [
        {"venue": "binancep2p", "price": 122_302_623.0, "mode": "vía USDT",
         "stock": 0.065, "alcanza": True,
         "via": {"usdt_price": 1_586.80, "spot_price": 76_998.0, "fuente": "okx"}},
        {"venue": "fiwind", "price": 122_494_415.0, "mode": "directo",
         "stock": None, "alcanza": True, "via": None},
    ],
    "sells": [], "precio_venta_cliente": 124_137_162.0,
    "precio_compra_cliente": None, "vuelta_pct": None, "cubre": True,
    "faltante_pct": None, "publicando_compra": None, "publicando_venta": None,
}


def test_texto_explica_los_pasos_de_la_ruta_sintetica(monkeypatch):
    """Un precio que el usuario no sabe ejecutar no sirve: hay que decirle
    cuántos USDT comprar, dónde, y a qué precio convertir."""
    t = _texto(_PAYLOAD_VIA, monkeypatch)
    assert "1.586,8" in t          # el USDT que tiene que comprar
    assert "76.998" in t           # el spot al que convierte
    assert "939" in t or "940" in t  # los USDT del monto (0,0122 × 76.998)


def test_texto_dice_de_donde_sale_el_precio_del_spot(monkeypatch):
    """El spot no sale de Binance (451 desde el VPS). Si no se aclara, el
    usuario compara contra su pantalla de Binance y no entiende la diferencia."""
    assert "okx" in _texto(_PAYLOAD_VIA, monkeypatch).lower()


def test_texto_no_inventa_pasos_en_las_rutas_directas(monkeypatch):
    t = _texto(_PAYLOAD, monkeypatch)
    assert "vía USDT" not in t


def test_los_pasos_de_venta_van_en_el_orden_que_se_ejecutan():
    """Vender BTC es al revés que comprarlo: PRIMERO convertís el BTC a USDT en
    el spot y DESPUÉS vendés esos USDT por pesos. Decirlo al revés manda a
    vender USDT que todavía no tenés."""
    import bot.commands as c

    leg = {"venue": "bybitp2p", "price": 122_309_510.0, "mode": "vía USDT",
           "stock": 1.18, "alcanza": True,
           "via": {"usdt_price": 1_588.0, "spot_price": 77_098.0, "fuente": "okx"}}
    linea = c._leg_line(1, leg, 0.0122, "SELL")
    assert linea.index("77.098") < linea.index("1.588,00")
    assert "después de vender" not in linea


def test_el_flat_de_tomador_de_binance_es_el_medido_en_la_cuenta():
    """0,07 USDT fijo, leído de dos órdenes propias del 22/08/2026 (273,53 y
    499,00 USDT, misma comisión). Antes decía 0,08, que salía de un rango
    anunciado (0,06-0,08) y no de un dato real. Sobre 500 USDT la diferencia es
    plata chica, pero el número que decide tomar-vs-publicar tiene que ser el
    medido. Ver memoria reference_fees_p2p_venues."""
    import config

    assert config.FEE_P2P_BY_MODE["binancep2p"]["taker_flat_quote"] == 0.07
    assert config.FEE_P2P_BY_MODE["binancep2p"]["maker_pct"] == 0.20


def test_los_venues_sin_comision_siguen_en_cero():
    """Verificado en 8 órdenes propias de Bybit (compras y ventas, comisión 0)."""
    import config

    for v in ("bybitp2p", "okexp2p", "kucoinp2p", "bitgetp2p"):
        f = config.FEE_P2P_BY_MODE[v]
        assert f["maker_pct"] == 0 and f["taker_pct"] == 0
        assert f["taker_flat_quote"] == 0


# ── Ranking "dónde compro/vendo": las dos modalidades, por venue ───────────

def test_la_pata_de_tomar_dice_cuantas_ordenes_son():
    """Un precio repartido en 11 avisos no es el mismo negocio que en 1."""
    libro = {"binancep2p": {"BUY": [FakeAd(1580, 40), FakeAd(1581, 40),
                                    FakeAd(1582, 40)], "SELL": []}}
    c = _build(books=libro, asset="USDT", size=100)
    assert c.buys[0].ordenes == 3


def test_hay_una_pata_de_publicar_por_cada_venue():
    """No alcanza con la mejor global: el usuario compara venue por venue."""
    libro = {"binancep2p": {"BUY": [FakeAd(1590, 500)], "SELL": [FakeAd(1580, 500)]},
             "okexp2p": {"BUY": [FakeAd(1591, 500)], "SELL": [FakeAd(1585, 500)]}}
    c = _build(books=libro, asset="USDT", size=100)
    venues = {l.venue for l in c.publicando_buys}
    assert venues == {"binancep2p", "okexp2p"}


def test_publicar_en_binance_paga_maker_y_en_los_otros_no():
    """El 0,20% es SOLO de Binance. En el resto publicar no cuesta nada, que es
    lo que hace que ahí publicar gane casi siempre."""
    libro = {"binancep2p": {"BUY": [FakeAd(1590, 500)], "SELL": [FakeAd(1580, 500)]},
             "okexp2p": {"BUY": [FakeAd(1590, 500)], "SELL": [FakeAd(1580, 500)]}}
    c = _build(books=libro, asset="USDT", size=100)
    por_venue = {l.venue: l.price for l in c.publicando_buys}
    assert por_venue["binancep2p"] == pytest.approx(1580 * 1.002)
    assert por_venue["okexp2p"] == pytest.approx(1580)


def test_publicar_no_usa_la_punta_envenenada():
    """OKX mostraba 1.600,00 como mejor punta de venta el 22/08: un anzuelo.
    Si se cuela, el bloque de publicar promete precios de fantasía."""
    libro = {"okexp2p": {"BUY": [FakeAd(1590, 500)],
                         "SELL": [FakeAd(1600, 3), FakeAd(1584, 900),
                                  FakeAd(1583, 900)]}}
    c = _build(books=libro, asset="USDT", size=100)
    assert c.publicando_buys[0].price == 1584


# ── "dónde compro más barato" / "dónde vendo más caro" ────────────────────

_PAYLOAD_DONDE = {
    "asset": "USDT", "size": 1000.0, "margin_pct": 0.0,
    "buys": [
        {"venue": "binancep2p", "price": 1588.65, "mode": "tomando",
         "stock": 4000.0, "alcanza": True, "via": None, "ordenes": 7},
        {"venue": "okexp2p", "price": 1588.74, "mode": "tomando",
         "stock": 3000.0, "alcanza": True, "via": None, "ordenes": 3},
        {"venue": "fiwind", "price": 1589.40, "mode": "directo",
         "stock": None, "alcanza": True, "via": None, "ordenes": 1},
    ],
    "sells": [
        {"venue": "bybitp2p", "price": 1584.10, "mode": "tomando",
         "stock": 5000.0, "alcanza": True, "via": None, "ordenes": 2},
    ],
    "publicando_buys": [
        {"venue": "kucoinp2p", "price": 1581.12, "mode": "publicando",
         "stock": 2000.0, "alcanza": True, "via": None, "ordenes": 1},
        {"venue": "binancep2p", "price": 1586.30, "mode": "publicando",
         "stock": 4000.0, "alcanza": True, "via": None, "ordenes": 1},
    ],
    "publicando_sells": [
        {"venue": "kucoinp2p", "price": 1592.00, "mode": "publicando",
         "stock": 2000.0, "alcanza": True, "via": None, "ordenes": 1},
    ],
    "precio_venta_cliente": None, "precio_compra_cliente": None,
    "vuelta_pct": None, "cubre": True, "faltante_pct": None,
    "publicando_compra": None, "publicando_venta": None,
}


def _donde(payload, monkeypatch, **kw):
    import bot.commands as c
    monkeypatch.setattr(c, "fetch_json", lambda base, path, params=None: payload)
    return c.donde_text("http://x", **kw)


def test_donde_muestra_las_dos_modalidades(monkeypatch):
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="compro")
    assert "TOMANDO" in t.upper() and "PUBLICANDO" in t.upper()
    assert "Binance P2P" in t and "KuCoin" in t


def test_donde_dice_cuantas_ordenes_hay_que_hacer(monkeypatch):
    """Es el dato que hizo abandonar una compra en Binance el 22/08."""
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="compro")
    assert "7 órdenes" in t


def test_donde_no_dice_ordenes_en_los_cex(monkeypatch):
    """Un CEX no tiene avisos: '1 orden' ahí confunde."""
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="compro")
    linea = [l for l in t.split(chr(10)) if "Fiwind" in l][0]
    assert "orden" not in linea and "directo" in linea


def test_donde_calcula_cuanto_ahorras_publicando(monkeypatch):
    """(1588,65 − 1581,12) / 1588,65 = 0,47%."""
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="compro")
    assert "0,47%" in t


def test_donde_solo_la_punta_pedida(monkeypatch):
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="vendo")
    assert "VENDER" in t.upper()
    assert "Fiwind" not in t          # Fiwind sólo estaba en el bloque de compra


def test_donde_avisa_si_no_pudo_leer(monkeypatch):
    import bot.commands as c

    def boom(base, path, params=None):
        raise RuntimeError("timeout")
    monkeypatch.setattr(c, "fetch_json", boom)
    assert "de nuevo" in c.donde_text("http://x", lado="compro").lower()


def test_no_ofrece_publicar_donde_no_mejora_contra_tomar():
    """Visto en vivo el 22/08: OKX aparecía con 'publicar a 1.600' para COMPRAR
    cuando tomando ahí mismo conseguías 1.588. Publicar más caro que el precio
    que ya podés ejecutar no es una opción, es un error de lectura del libro."""
    libro = {"okexp2p": {"BUY": [FakeAd(1588, 5000)],      # tomando: 1588
                         "SELL": [FakeAd(1600, 5000)]}}    # publicando: 1600 ✗
    c = _build(books=libro, asset="USDT", size=1000)
    assert c.publicando_buys == []


def test_si_publicar_mejora_se_ofrece():
    libro = {"okexp2p": {"BUY": [FakeAd(1588, 5000)],
                         "SELL": [FakeAd(1584, 5000)]}}
    c = _build(books=libro, asset="USDT", size=1000)
    assert [l.venue for l in c.publicando_buys] == ["okexp2p"]


def test_el_bloque_de_publicar_no_habla_de_ordenes(monkeypatch):
    """Publicás UN aviso: contar órdenes ahí es ruido."""
    t = _donde(_PAYLOAD_DONDE, monkeypatch, lado="compro")
    bloque = t.split("PUBLICANDO")[1].split("💡")[0]
    assert "orden" not in bloque
