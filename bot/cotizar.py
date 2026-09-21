"""Cotizador para clientes. Dado el lado del cliente y el margen del
usuario, calcula el precio a cotizarle y arma una placa PNG con la marca.

Lógica (el usuario es el cambista, el cliente es la contraparte):
- side "compra" = el CLIENTE me COMPRA USDT. Yo consigo barato (cheapest_buy) y le
  vendo con margen arriba → precio = base * (1 + margin%). (JR VENDE.)
- side "venta" = el CLIENTE me VENDE USDT. Yo lo revendo caro (dearest_sell) y le
  pago con margen abajo → precio = base * (1 - margin%). (JR COMPRA.)
Ver memoria project_otc_pago_terceros / project_estrategias_spread."""
from __future__ import annotations

import io


def quote_price(side: str, base_price: float, margin_pct: float) -> float:
    """Precio a cotizarle al cliente. 'compra' suma el margen (le vendo más caro),
    'venta' lo resta (le compro más barato)."""
    if base_price <= 0:
        raise ValueError("base_price debe ser > 0")
    if side == "compra":
        return base_price * (1 + margin_pct / 100)
    if side == "venta":
        return base_price * (1 - margin_pct / 100)
    raise ValueError(f"side inválido: {side!r} (usar 'compra' o 'venta')")


def build_cotizacion(spread: dict, side: str, margin_pct: float,
                     asset: str = "USDT") -> dict:
    """Elige la base del payload de /api/spread/now según el lado del cliente y
    calcula el precio, con hasta 3 opciones de respaldo. 'compra' usa top_buys
    (dónde consigo más barato); 'venta' usa top_sells (dónde revendo más caro).
    Cae al único cheapest_buy/dearest_sell si no vienen los top_*."""
    if side == "compra":
        opts = list(spread.get("top_buys") or [])
        single = spread.get("cheapest_buy")
        accion = "VENDO"   # JR le vende USDT al cliente
    elif side == "venta":
        opts = list(spread.get("top_sells") or [])
        single = spread.get("dearest_sell")
        accion = "COMPRO"  # JR le compra USDT al cliente
    else:
        raise ValueError(f"side inválido: {side!r}")
    opts = [o for o in opts if float(o.get("price") or 0) > 0]
    if not opts and single and float(single.get("price") or 0) > 0:
        opts = [single]
    if not opts:
        opts = _opts_from_exchanges(spread, side)
    if not opts:
        raise ValueError("sin precio de referencia disponible")
    base = float(opts[0]["price"])
    return {
        "side": side,
        "asset": normalize_asset(asset),
        "accion": accion,
        "base": base,
        "base_venue": opts[0].get("exchange", "?"),
        "margin_pct": margin_pct,
        "quote": quote_price(side, base, margin_pct),
        "options": opts[:3],
    }


def _opts_from_exchanges(spread: dict, side: str) -> list[dict]:
    """Respaldo cuando CriptoYa no trae nada (top_*/cheapest_*/dearest_* vacíos):
    deriva las opciones de `exchanges` (profundidad P2P). Misma semántica que
    CriptoYa: 'compra' usa el ask más barato (comprar), 'venta' el bid más caro
    (vender). Devuelve [{exchange, price}] ordenado del mejor al peor."""
    cand: list[dict] = []
    for e in spread.get("exchanges") or []:
        name = e.get("exchange")
        price = e.get("ask") if side == "compra" else e.get("bid")
        if name and price and float(price) > 0:
            cand.append({"exchange": name, "price": float(price)})
    cand.sort(key=lambda o: o["price"], reverse=(side == "venta"))
    return cand


# Ancho máximo creíble entre el ask y el bid del MISMO venue. Más que esto no
# es un mercado, es un libro sin contraparte: OKX en BTC/ARS llegó a 15% (medido
# 2026-08-21) y el tablero lo leía como una oportunidad del 15%. Mismo criterio
# (y mismo número) que el max_dev_pct de core.p2p_depth.filter_traps.
WIDE_BOOK_PCT = 3.0


def _libro_ancho(ask: float, bid: float) -> bool:
    return bid > 0 and (ask - bid) / bid * 100 > WIDE_BOOK_PCT


def build_board(spread: dict, top: int = 3) -> dict:
    """Tablero de referencia (solo para el usuario): dónde comprás más barato y
    dónde vendés más caro, con modo por venue. Usa `exchanges` (P2P con ask/bid →
    tomando y publicando) y los CEX `cheapest_buy`/`dearest_sell` (precio único →
    directo). Convención de arb_matrix: comprar tomando=ask, publicando=bid;
    vender tomando=bid, publicando=ask.

    Devuelve {"buys": [...], "sells": [...], "best_buy", "best_sell",
    "diff_ars", "diff_pct"} — buys ordenadas asc por precio (más barato primero),
    sells desc (más caro primero), top N cada una. buys/sells vacías si no hay dato."""
    buys: dict[str, dict] = {}   # dedupe por venue, P2P pisa CEX (más informativo)
    sells: dict[str, dict] = {}

    for e in spread.get("exchanges") or []:
        name = e.get("exchange")
        ask, bid = e.get("ask"), e.get("bid")
        if not name or not ask or not bid or ask <= 0 or bid <= 0:
            continue
        ancho = _libro_ancho(float(ask), float(bid))
        buys[name] = {"venue": name, "mode": "p2p", "ancho": ancho,
                      "tomando": float(ask), "publicando": float(bid),
                      "best": float(bid)}          # comprar: publicando (bid) es lo mejor
        sells[name] = {"venue": name, "mode": "p2p", "ancho": ancho,
                       "tomando": float(bid), "publicando": float(ask),
                       "best": float(ask)}         # vender: publicando (ask) es lo mejor

    cb = spread.get("cheapest_buy")
    if cb and float(cb.get("price") or 0) > 0 and cb.get("exchange") not in buys:
        buys[cb["exchange"]] = {"venue": cb["exchange"], "mode": "cex", "ancho": False,
                                "price": float(cb["price"]), "best": float(cb["price"])}
    ds = spread.get("dearest_sell")
    if ds and float(ds.get("price") or 0) > 0 and ds.get("exchange") not in sells:
        sells[ds["exchange"]] = {"venue": ds["exchange"], "mode": "cex", "ancho": False,
                                 "price": float(ds["price"]), "best": float(ds["price"])}

    buy_ord = sorted(buys.values(), key=lambda o: o["best"])
    sell_ord = sorted(sells.values(), key=lambda o: o["best"], reverse=True)
    buy_list, sell_list = buy_ord[:top], sell_ord[:top]

    # Los de libro ancho se muestran (son un dato) pero no entran en la
    # diferencia: si entraran, el tablero anunciaría un spread que no existe.
    firmes_buy = [o for o in buy_ord if not o["ancho"]]
    firmes_sell = [o for o in sell_ord if not o["ancho"]]
    best_buy = firmes_buy[0]["best"] if firmes_buy else None
    best_sell = firmes_sell[0]["best"] if firmes_sell else None
    diff_ars = diff_pct = None
    if best_buy and best_sell:
        diff_ars = best_sell - best_buy
        diff_pct = diff_ars / best_buy * 100

    return {"buys": buy_list, "sells": sell_list,
            "best_buy": best_buy, "best_sell": best_sell,
            "diff_ars": diff_ars, "diff_pct": diff_pct}


# Ticket chico de referencia por activo: 1 BTC son decenas de millones de ARS,
# así que el cliente no dimensiona el precio sin una unidad más chica. USDT no
# está acá porque su precio ya es por unidad operable.
ASSET_TICKET: dict[str, float] = {"BTC": 0.01}


def normalize_asset(raw) -> str:
    """'btc' / 'Bitcoin' → 'BTC'. Cualquier otra cosa (o nada) → 'USDT', que es
    lo que se cotiza el 99% de las veces: ante la duda, el default de siempre."""
    return "BTC" if str(raw or "").strip().lower() in ("btc", "bitcoin") else "USDT"


def equivalencia(cot: dict) -> str | None:
    """Cuánto sale un ticket chico al precio cotizado, para activos caros.
    None si el activo no tiene ticket (USDT ya se cotiza por unidad)."""
    ticket = ASSET_TICKET.get(cot["asset"])
    if not ticket:
        return None
    a, q = cot["asset"], cot["quote"]
    return f"{f'{ticket:g}'.replace('.', ',')} {a} = ${_miles0(q * ticket)}"


def _miles0(n: float) -> str:
    """Sin centavos: a decenas de millones de pesos los centavos son ruido."""
    return f"{n:,.0f}".replace(",", ".")


def _miles(n: float) -> str:
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _font(size: int):
    from PIL import ImageFont
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_placa(cot: dict) -> bytes:
    """Placa PNG chica y prolija con la marca (config.BRAND_NAME) y el precio cotizado."""
    from PIL import Image, ImageDraw

    W, H = 620, 340
    bg, accent, white, grey = (14, 17, 22), (51, 200, 130), (240, 244, 248), (150, 160, 170)
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, W, 6], fill=accent)                 # barra superior
    import config
    d.text((32, 34), config.BRAND_NAME.upper(), font=_font(40), fill=accent)
    accion, asset = cot["accion"], cot["asset"]             # VENDO / COMPRO
    d.text((32, 92), f"{accion} {asset}", font=_font(26), fill=white)

    # BTC va sin centavos: con ellos el número no entra a 72px de ancho de placa.
    precio = _miles0(cot["quote"]) if asset in ASSET_TICKET else _miles(cot["quote"])
    d.text((32, 168), "$", font=_font(46), fill=grey)
    d.text((78, 158), precio, font=_font(72), fill=white)
    d.text((32, 254), f"Precio por 1 {asset} · pago en pesos", font=_font(20), fill=grey)
    eq = equivalencia(cot)
    if eq:
        d.text((32, 288), eq, font=_font(18), fill=grey)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
