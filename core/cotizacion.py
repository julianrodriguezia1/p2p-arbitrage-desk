"""Motor de cotización al cliente: qué precio le pasás, con el precio que podés
EJECUTAR ahora — no con el optimista.

Por qué existe (2026-08-21, después de perder plata en una op de BTC): el
cotizador anterior tomaba (a) el precio de PUBLICAR, que depende de que alguien
te tome el aviso, y (b) la PUNTA del libro, que puede ser un aviso de 0,012 BTC.
Se cotizó con eso, nadie tomó el aviso, hubo que comprar instantáneo más caro y
la operación cerró en pérdida.

Las tres reglas que salen de ahí:
1. La base de una cotización es el precio que se ejecuta YA (tomar en P2P,
   directo en CEX). Publicar se muestra aparte, como lo que es: una apuesta a que
   te llenen.
2. El precio se calcula caminando el libro por el MONTO pedido (VWAP), no con la
   punta. Y se dice cuánto stock hay.
3. Si el margen no cubre el costo de darse vuelta, se avisa. Un margen que no
   cubre no es una ganancia chica: es una pérdida.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.p2p_depth import depth_fill, filter_traps


@dataclass(frozen=True)
class Leg:
    """Una forma concreta de ejecutar una punta."""
    venue: str
    price: float           # ARS por unidad, YA neto de comisiones
    mode: str              # "directo" (CEX) | "tomando" | "publicando"
    stock: float | None    # cripto disponible en el libro (None en CEX)
    alcanza: bool          # el libro cubre el monto pedido
    via: dict | None = None  # pasos de la ruta sintética (None = ruta directa)
    ordenes: int = 1         # avisos distintos que hay que tomar para llenar


@dataclass(frozen=True)
class Cotizacion:
    asset: str
    size: float
    margin_pct: float
    buys: list                       # list[Leg], más barata primero
    sells: list                      # list[Leg], más cara primero
    precio_venta_cliente: float | None    # a este precio le VENDÉS
    precio_compra_cliente: float | None   # a este precio le COMPRÁS
    vuelta_pct: float | None         # costo de comprar y vender ya (negativo)
    cubre: bool                      # el margen alcanza para no perder
    faltante_pct: float | None       # cuánto falta si no cubre
    mejor_publicando_compra: "Leg | None"
    mejor_publicando_venta: "Leg | None"
    publicando_buys: list = field(default_factory=list)   # una por venue
    publicando_sells: list = field(default_factory=list)


def _fees(fees: dict, venue: str) -> dict:
    return fees.get(venue) or {"maker_pct": 0.0, "taker_pct": 0.0,
                               "taker_flat_quote": 0.0}


def _flat_pct(fees: dict, venue: str, asset: str, size: float,
              flat_assets: tuple[str, ...]) -> float:
    """El flat del tomador expresado como % del monto, para poder sumarlo al
    precio. Solo aplica a los activos donde está anunciado (ver config)."""
    if asset not in flat_assets or size <= 0:
        return 0.0
    return _fees(fees, venue)["taker_flat_quote"] / size * 100


def _cex_legs(criptoya: dict, whitelist: set[str], max_age_min: int,
              now: float) -> tuple[list, list]:
    """CEX: precio NETO de CriptoYa (totalAsk/totalBid, ya con comisión y costo
    de cash-out) y ejecución directa, sin esperar contraparte."""
    buys: list[Leg] = []
    sells: list[Leg] = []
    max_age = max_age_min * 60
    for name, info in criptoya.items():
        if name.lower() not in whitelist or name.lower().endswith("p2p"):
            continue
        try:
            ask = float(info.get("totalAsk") or info["ask"])
            bid = float(info.get("totalBid") or info["bid"])
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ask <= 0 or bid <= 0 or now - t > max_age:
            continue
        buys.append(Leg(name, ask, "directo", None, True))
        sells.append(Leg(name, bid, "directo", None, True))
    return buys, sells


def _vwap_leg(venue: str, ads: list, size: float, side: str, mode: str,
              fee_pct: float) -> "Leg | None":
    """Precio ejecutable caminando el libro por `size`, más el fee del modo.
    Comprar encarece (+fee), vender abarata (-fee)."""
    ads = [a for a in ads if a.price > 0 and a.available > 0]
    if not ads:
        return None
    fill = depth_fill(filter_traps(ads), size, side)
    if not fill or not fill["price"]:
        return None
    precio = fill["price"]
    stock = sum(a.available for a in ads)
    neto = precio * (1 + fee_pct / 100) if side == "BUY" else precio * (1 - fee_pct / 100)
    return Leg(venue, neto, mode, stock, stock >= size,
               ordenes=fill["ordenes"])


# Mejora máxima creíble de publicar contra el precio que se ejecuta ya. Más que
# esto no es una oportunidad, es un libro muerto: KuCoin en BTC daba 4% abajo del
# mercado con 2 avisos, y un aviso ahí no lo toma nadie. Sugerirlo es repetir el
# error que costó plata: mostrar un precio que no se puede realizar.
MEJORA_PUBLICANDO_MAX_PCT = 3.0

# Para fijar la punta contra la que publicás, un aviso tiene que aguantar al
# menos esta fracción de tu monto. Uno de 3 USDT contra una orden de 100 no es
# una referencia de precio, es ruido.
PUNTA_MIN_FRACCION = 0.10


def _mejor_publicando(venue: str, ads: list, side: str, maker_pct: float,
                      size: float) -> "Leg | None":
    """Publicar es ponerse del otro lado del libro: para COMPRAR publicando te
    cruzás con el mejor precio del lado SELL, y viceversa. Es la punta a secas
    (un aviso propio se llena de a poco), con el fee de maker."""
    ads = [a for a in ads if a.price > 0 and a.available > 0]
    if not ads:
        return None
    # La punta cruda la fija cualquier aviso minúsculo: OKX mostraba 1.600,00
    # como mejor precio de venta el 22/08/2026 con 3 USDT detrás. filter_traps
    # no lo agarra porque está a 1% de la mediana, muy por debajo de su umbral
    # de 3%. Publicar contra esa punta es prometer un precio que se llena con
    # el 3% de la orden y deja el resto colgado.
    ads = [a for a in filter_traps(ads)
           if a.available >= size * PUNTA_MIN_FRACCION]
    if not ads:
        return None
    stock = sum(a.available for a in ads)
    if stock < size:              # sin contraparte suficiente no hay qué publicar
        return None
    if side == "BUY":                       # comprar publicando
        precio = max(a.price for a in ads) * (1 + maker_pct / 100)
    else:                                   # vender publicando
        precio = min(a.price for a in ads) * (1 - maker_pct / 100)
    return Leg(venue, precio, "publicando", stock, True)


def _publicando_creible(leg: "Leg | None", base: float | None,
                        side: str) -> "Leg | None":
    """Descarta la sugerencia de publicar si no mejora el precio ejecutable, o
    si lo mejora tanto que delata un libro muerto."""
    if leg is None or not base:
        return None
    mejora = (base - leg.price) / base * 100 if side == "BUY" else (
        (leg.price - base) / base * 100)
    if mejora <= 0 or mejora > MEJORA_PUBLICANDO_MAX_PCT:
        return None
    return leg


# Venues que tienen P2P de USDT Y mercado spot propio. Comprar el USDT en uno
# y convertirlo en otro obliga a mover el USDT y pagar fee de red, que es
# justo lo que la ruta viene a ahorrar.
SPOT_VENUES: frozenset[str] = frozenset(
    {"binancep2p", "okexp2p", "bybitp2p", "bitgetp2p", "kucoinp2p"})


def _sintetica(leg: "Leg", spot: dict, side: str, fee_pct: float,
               size: float) -> "Leg | None":
    """Encadena una pata de USDT/ARS con el spot {asset}/USDT.

    Comprar paga el ask del spot y el fee encarece; vender cobra el bid y el fee
    abarata. El stock se pasa a unidades del activo caro: 5.000 USDT al lado de
    un monto en BTC se leería como 5.000 BTC.
    """
    if leg.venue not in SPOT_VENUES:
        return None
    px = spot["ask"] if side == "BUY" else spot["bid"]
    if px <= 0 or leg.price <= 0:
        return None
    precio = leg.price * px * (1 + fee_pct / 100 if side == "BUY"
                               else 1 - fee_pct / 100)
    stock = leg.stock / px if leg.stock is not None else None
    return Leg(leg.venue, precio, "vía USDT", stock,
               stock is None or stock >= size,
               via={"usdt_price": leg.price, "spot_price": px,
                    "fuente": spot.get("fuente", "?")})


def _sinteticas(spot: dict | None, usdt, fee_pct: float,
                size: float) -> tuple[list, list]:
    """Las dos puntas de la ruta ARS→USDT→{asset}. Vacías si falta el spot o la
    cotización de USDT: sin ellas la cotización sigue viva, solo sin la ruta."""
    if not spot or usdt is None:
        return [], []
    buys = [s for s in (_sintetica(l, spot, "BUY", fee_pct, size)
                        for l in usdt.buys) if s]
    sells = [s for s in (_sintetica(l, spot, "SELL", fee_pct, size)
                         for l in usdt.sells) if s]
    return buys, sells


def build(
    criptoya: dict,
    books: dict,
    *,
    asset: str,
    size: float,
    margin_pct: float,
    whitelist: set[str],
    fees: dict,
    max_age_min: int,
    now: float,
    top: int = 3,
    flat_assets: tuple[str, ...] = ("USDT",),
    spot: dict | None = None,
    usdt=None,
    spot_fee_pct: float = 0.0,
) -> Cotizacion:
    """Arma la cotización de las dos puntas.

    `criptoya` es el payload crudo de CriptoYa; `books` es
    {venue_p2p: {"BUY": [Ad], "SELL": [Ad]}} con los libros reales — "BUY" son
    los avisos contra los que VOS comprás, "SELL" contra los que vendés (misma
    convención que p2p_scanner.FETCHERS).
    """
    buys, sells = _cex_legs(criptoya, whitelist, max_age_min, now)
    pub_compra = pub_venta = None
    pub_buys: list[Leg] = []      # publicar, una pata por venue
    pub_sells: list[Leg] = []

    for venue, libro in (books or {}).items():
        if venue.lower() not in whitelist:
            continue
        f = _fees(fees, venue)
        taker = f["taker_pct"] + _flat_pct(fees, venue, asset, size, flat_assets)
        maker = f["maker_pct"]

        leg = _vwap_leg(venue, libro.get("BUY") or [], size, "BUY", "tomando", taker)
        if leg:
            buys.append(leg)
        leg = _vwap_leg(venue, libro.get("SELL") or [], size, "SELL", "tomando", taker)
        if leg:
            sells.append(leg)

        # Comprar publicando se cruza con el lado SELL del libro, y al revés.
        cand = _mejor_publicando(venue, libro.get("SELL") or [], "BUY", maker, size)
        if cand:
            pub_buys.append(cand)
            if pub_compra is None or cand.price < pub_compra.price:
                pub_compra = cand
        cand = _mejor_publicando(venue, libro.get("BUY") or [], "SELL", maker, size)
        if cand:
            pub_sells.append(cand)
            if pub_venta is None or cand.price > pub_venta.price:
                pub_venta = cand

    via_buys, via_sells = _sinteticas(spot, usdt, spot_fee_pct, size)
    buys += via_buys
    sells += via_sells

    buys.sort(key=lambda l: l.price)
    sells.sort(key=lambda l: l.price, reverse=True)
    buys, sells = buys[:top], sells[:top]

    base_compra = buys[0].price if buys else None
    base_venta = sells[0].price if sells else None
    pub_compra = _publicando_creible(pub_compra, base_compra, "BUY")
    pub_venta = _publicando_creible(pub_venta, base_venta, "SELL")
    # Publicar sólo se ofrece si mejora el precio que YA podés ejecutar en ese
    # mismo venue. Sin este filtro OKX aparecía con "publicá a 1.600" para
    # comprar mientras tomando ahí conseguías 1.588 (visto en vivo el 22/08).
    toma_por_venue = {l.venue: l.price for l in buys}
    pub_buys = [l for l in pub_buys
                if _publicando_creible(l, toma_por_venue.get(l.venue), "BUY")]
    toma_por_venue = {l.venue: l.price for l in sells}
    pub_sells = [l for l in pub_sells
                 if _publicando_creible(l, toma_por_venue.get(l.venue), "SELL")]
    pub_buys.sort(key=lambda l: l.price)
    pub_sells.sort(key=lambda l: l.price, reverse=True)
    venta_cliente = base_compra * (1 + margin_pct / 100) if base_compra else None
    compra_cliente = base_venta * (1 - margin_pct / 100) if base_venta else None

    vuelta, cubre, faltante = None, False, None
    if base_compra and base_venta:
        # Costo de darse vuelta: comprar ya y vender ya. Casi siempre negativo;
        # el margen tiene que ser mayor que ese costo para que la op deje algo.
        vuelta = (base_venta - base_compra) / base_compra * 100
        cubre = margin_pct >= -vuelta
        faltante = None if cubre else -vuelta - margin_pct

    return Cotizacion(
        asset=asset, size=size, margin_pct=margin_pct,
        buys=buys, sells=sells,
        precio_venta_cliente=venta_cliente, precio_compra_cliente=compra_cliente,
        vuelta_pct=vuelta, cubre=cubre, faltante_pct=faltante,
        mejor_publicando_compra=pub_compra, mejor_publicando_venta=pub_venta,
        publicando_buys=pub_buys[:top], publicando_sells=pub_sells[:top],
    )
