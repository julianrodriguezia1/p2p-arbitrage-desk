"""Matemática pura de las 3 jugadas de arbitraje cross-venue (sin red).

Nomenclatura interna (NUNCA en UI/avisos):
  ask = precio de venta del venue  -> comprás TOMANDO   / vendés PUBLICANDO
  bid = precio de compra del venue -> vendés TOMANDO    / comprás PUBLICANDO
Publicar solo tiene sentido en venues P2P (order book real).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Venue:
    name: str            # clave estilo CriptoYa, ej "bybitp2p", "ripio"
    ask: float | None    # comprar tomando / vender publicando
    bid: float | None    # vender tomando / comprar publicando
    is_p2p: bool
    # Liquidez detrás de cada punta. None = no medible (los CEX no publican
    # orderbook); 0 avisos = medido y vacío. La distinción importa: lo no medido
    # no se castiga, lo medido y flaco sí.
    ask_avisos: int | None = None
    ask_stock: float | None = None
    ask_alcanza: bool | None = None
    bid_avisos: int | None = None
    bid_stock: float | None = None
    bid_alcanza: bool | None = None
    # Cuántos avisos hay que tomar para llenar el ticket por esa punta. El flat
    # de tomador (0,07 USDT en Binance) se paga por orden, así que 2 avisos = 2
    # fees. None = no medible; se cobra como una sola orden.
    ask_ordenes: int | None = None
    bid_ordenes: int | None = None
    # Si el exchange todavía no me deja CREAR anuncios, las jugadas de publicar
    # ahí no son jugadas: son números que no puedo ejecutar. Tomar avisos ajenos
    # no tiene requisitos, así que se restringe sólo el lado de publicar.
    puede_publicar_compra: bool = True
    puede_publicar_venta: bool = True


@dataclass(frozen=True)
class Route:
    kind: str            # "media" | "mm" | "instant"
    buy_venue: str
    buy_price: float
    buy_mode: str        # "tomando" | "publicando"
    sell_venue: str
    sell_price: float
    sell_mode: str       # "tomando" | "publicando"
    net_pct: float


def _comprar_tomando(v: Venue) -> float | None:
    return v.ask if v.ask and v.ask > 0 else None


def _comprar_publicando(v: Venue) -> float | None:
    if not v.is_p2p or not v.puede_publicar_compra:
        return None
    return v.bid if v.bid and v.bid > 0 else None


def _vender_tomando(v: Venue) -> float | None:
    return v.bid if v.bid and v.bid > 0 else None


def _vender_publicando(v: Venue) -> float | None:
    if not v.is_p2p or not v.puede_publicar_venta:
        return None
    return v.ask if v.ask and v.ask > 0 else None


def fee_pata(venue: str, mode: str, fee_pct: dict[str, float],
         fee_by_mode: dict[str, dict[str, float]] | None,
         ordenes: int | None = 1) -> float:
    """Fee de una pata. La tabla por modo pisa al flat, si el venue está en ella.

    Existe porque en algunos venues publicar y tomar no cuestan lo mismo y la
    diferencia decide la jugada: en Lemon publicar es 1% y tomar 1,5%. Sólo se
    consulta para los venues cargados en la tabla; el resto sigue con el flat.

    `ordenes` es cuántos avisos hay que tomar para llenar el ticket: el flat de
    tomador se paga por orden, así que cada aviso extra suma otro
    `tomando_por_orden` (lo trae `core.fees.por_modo`). Publicando no aplica.
    """
    if fee_by_mode:
        por_modo = fee_by_mode.get(venue)
        if por_modo is not None and mode in por_modo:
            fee = por_modo[mode]
            if mode == "tomando" and ordenes and ordenes > 1:
                fee += por_modo.get("tomando_por_orden", 0.0) * (ordenes - 1)
            return fee
    return fee_pct.get(venue, 0.0)


def _net(buy_price: float, buy_venue: str, buy_mode: str,
         sell_price: float, sell_venue: str, sell_mode: str,
         fee_pct: dict[str, float],
         fee_by_mode: dict[str, dict[str, float]] | None = None,
         buy_ordenes: int | None = 1, sell_ordenes: int | None = 1) -> float:
    gross = (sell_price - buy_price) / buy_price * 100
    return (gross
            - fee_pata(buy_venue, buy_mode, fee_pct, fee_by_mode, buy_ordenes)
            - fee_pata(sell_venue, sell_mode, fee_pct, fee_by_mode, sell_ordenes))


def best_routes(venues: list[Venue], *, fee_pct: dict[str, float],
                usable=None, keep=None,
                fee_by_mode: dict[str, dict[str, float]] | None = None
                ) -> dict[str, Route]:
    """Mejor ruta (máx neto) de cada jugada. Kinds sin ruta válida se omiten.

    - instant: comprar tomando(A) -> vender tomando(B).
    - media:   comprar tomando(A) -> vender publicando(B)  (B p2p), y su simétrica
               comprar publicando(A) (A p2p) -> vender tomando(B).
    - mm:      comprar publicando(A) (A p2p) -> vender publicando(B) (B p2p),
               INCLUYE A==B (market making intra-venue).

    `usable(venue, lado)` es un filtro opcional para descartar puntas que no
    sirven aunque el precio sea lindo (ej. un libro sin volumen). Se llama con
    lado "ask" o "bid" según qué punta usaría la jugada.

    `fee_by_mode` es {venue: {"publicando": %, "tomando": %}} y pisa a `fee_pct`
    para los venues que estén cargados ahí. El resto sigue con el flat.

    `keep(route)` es un filtro opcional sobre la ruta ya armada, para exigirle
    algo que no se puede pedir punta por punta: por ejemplo que alguna de las
    dos patas caiga en Binance P2P (sumar órdenes para el Comerciante
    Verificado). Un kind sin ninguna ruta que pase el filtro se omite.
    """
    best: dict[str, Route] = {}

    def ok(v: Venue, lado: str) -> bool:
        return usable is None or usable(v, lado)

    def consider(kind: str, a: Venue, buy_mode: str, buy_price: float | None,
                 b: Venue, sell_mode: str, sell_price: float | None) -> None:
        if buy_price is None or sell_price is None:
            return
        # Comprar tomando toma el ask de A; vender tomando, el bid de B.
        net = _net(buy_price, a.name, buy_mode, sell_price, b.name, sell_mode,
                   fee_pct, fee_by_mode,
                   buy_ordenes=a.ask_ordenes if buy_mode == "tomando" else 1,
                   sell_ordenes=b.bid_ordenes if sell_mode == "tomando" else 1)
        cur = best.get(kind)
        if cur is not None and net <= cur.net_pct:
            return
        route = Route(kind, a.name, buy_price, buy_mode,
                      b.name, sell_price, sell_mode, net)
        if keep is not None and not keep(route):
            return
        best[kind] = route

    for a in venues:
        # Comprar usa el ask del venue A (tomando) o su bid (publicando).
        compra_tom = _comprar_tomando(a) if ok(a, "ask") else None
        compra_pub = _comprar_publicando(a) if ok(a, "bid") else None
        for b in venues:
            venta_tom = _vender_tomando(b) if ok(b, "bid") else None
            venta_pub = _vender_publicando(b) if ok(b, "ask") else None
            # instant: ambas puntas se toman.
            consider("instant", a, "tomando", compra_tom, b, "tomando", venta_tom)
            # media espera, variante 1: comprar tomando -> vender publicando.
            consider("media", a, "tomando", compra_tom, b, "publicando", venta_pub)
            # media espera, variante 2 (simétrica): comprar publicando -> vender tomando.
            consider("media", a, "publicando", compra_pub, b, "tomando", venta_tom)
            # market making: publicar de los dos lados (incluye a==b).
            consider("mm", a, "publicando", compra_pub, b, "publicando", venta_pub)

    return best


# venue_name (estilo CriptoYa) -> clave del fetcher en p2p_scanner.FETCHERS
P2P_DEPTH_VENUES: dict[str, str] = {
    "binancep2p": "binance",
    "okexp2p": "okx",
    "bybitp2p": "bybit",
    "bitgetp2p": "bitget",
    "kucoinp2p": "kucoin",
}


def build_venues(depth_quotes: dict[str, dict], payload: dict, *,
                 cex_venues: set[str], blacklist: set[str],
                 max_age_min: int, now: float,
                 puede_publicar_compra: dict[str, bool] | None = None,
                 puede_publicar_venta: dict[str, bool] | None = None,
                 p2p_sin_profundidad: set[str] | None = None) -> list[Venue]:
    """Arma la lista de Venue. P2P desde profundidad (VWAP), CEX desde CriptoYa.

    - P2P: un Venue por clave de `depth_quotes` con is_p2p=True (ask/bid tal cual;
      None se conserva, best_routes lo tolera). `puede_publicar_*` apaga el lado
      de publicar donde el exchange todavía no me habilita crear anuncios.
    - `p2p_sin_profundidad`: venues que SON libros P2P (se puede publicar) pero no
      exponen el orderbook, así que el precio viene de CriptoYa. Se los marca
      is_p2p=True con el ask/bid CRUDO, no el total*: el total* ya trae clavado
      el fee de tomador y castigaría de más una jugada de publicar. La liquidez
      queda en None = no medible, nunca fingida.
    - CEX: un Venue por clave de `cex_venues` presente en `payload`, is_p2p=False,
      usando el precio NETO de CriptoYa (totalAsk/totalBid, ya con comisiones y
      cash-out), con fallback a ask/bid crudo; descartando blacklist, precio<=0 y
      cotizaciones más viejas que max_age_min.
    """
    out: list[Venue] = []
    pub_c = puede_publicar_compra or {}
    pub_v = puede_publicar_venta or {}
    sin_prof = p2p_sin_profundidad or set()

    for name, q in depth_quotes.items():
        out.append(Venue(
            name, q.get("ask"), q.get("bid"), is_p2p=True,
            ask_avisos=q.get("ask_avisos"), ask_stock=q.get("ask_stock"),
            ask_alcanza=q.get("ask_alcanza"),
            bid_avisos=q.get("bid_avisos"), bid_stock=q.get("bid_stock"),
            bid_alcanza=q.get("bid_alcanza"),
            ask_ordenes=q.get("ask_ordenes"), bid_ordenes=q.get("bid_ordenes"),
            # ausente = habilitado: sólo se anota lo que está bloqueado
            puede_publicar_compra=pub_c.get(name, True),
            puede_publicar_venta=pub_v.get(name, True),
        ))

    max_age = max_age_min * 60
    for name in cex_venues:
        if name in blacklist:
            continue
        info = payload.get(name)
        if not info:
            continue
        es_p2p = name in sin_prof
        try:
            if es_p2p:
                ask = float(info["ask"])
                bid = float(info["bid"])
            else:
                ask = float(info.get("totalAsk") or info["ask"])
                bid = float(info.get("totalBid") or info["bid"])
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ask <= 0 or bid <= 0:
            continue
        if now - t > max_age:
            continue
        out.append(Venue(name, ask, bid, is_p2p=es_p2p,
                         puede_publicar_compra=pub_c.get(name, True),
                         puede_publicar_venta=pub_v.get(name, True)))

    return out
