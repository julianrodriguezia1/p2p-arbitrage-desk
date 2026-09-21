"""Capa de presentación de la estrategia de spread (pura, sin red). Rankea las
jugadas de core.arb_matrix, aplica el haircut de fee de red en cross-venue y
transporta el aviso 'afuera de whitelist'."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.arb_matrix import Route


@dataclass(frozen=True)
class Play:
    kind: str            # "media" | "mm" | "instant"
    buy_venue: str
    buy_price: float
    buy_mode: str        # "tomando" | "publicando"
    sell_venue: str
    sell_price: float
    sell_mode: str       # "tomando" | "publicando"
    net_pct: float       # neto de trading + fee de red (número final rankeable)
    ars_per_1000: float  # ganancia estimada en ARS por 1000 USDT
    # Toca un venue "secundario" (config.VENUES_SECUNDARIOS): libro que casi no
    # opera. Nunca encabeza; a lo sumo sale como alternativa marcada.
    secundario: bool = False


@dataclass(frozen=True)
class OutsideNote:
    venue: str           # clave del venue fuera de la whitelist, ej "eldoradop2p"
    side: str            # "sell" (paga más caro)
    price: float


@dataclass(frozen=True)
class Strategy:
    best: "Play | None"
    alternatives: list          # list[Play], hasta 2
    outside_note: "OutsideNote | None"
    # La mejor jugada entre las que SÍ mueven volumen. None si la mejor ya lo es
    # (no hay nada que aclarar) o si no se pudo medir la liquidez.
    con_volumen: "Play | None" = None
    # La mejor jugada con al menos una pata en Binance P2P: las órdenes que
    # cuentan para el Comerciante Verificado. None si la mejor ya pasa por
    # Binance (entonces best_en_binance queda True) o si no hay ninguna que gane.
    binance: "Play | None" = None
    best_en_binance: bool = False


# Piso para creerle a una punta P2P. Sale de medir el 2026-08-24: los libros
# sanos de USDT/ARS tenían 19-20 avisos y 23.000-32.000 USD de stock; KuCoin
# ofrecía el mejor precio del tablero con 8 avisos y 7.724 USD. Un precio que
# nadie disputa no es un precio de mercado.
LIQ_MIN_AVISOS = 10
LIQ_MIN_STOCK_USD = 10_000.0


def venue_liquido(v, lado: str) -> bool:
    """¿Esa punta del venue mueve plata de verdad?

    Los CEX no publican orderbook: no se los puede medir y **no se los castiga**
    (devuelve True). Para los P2P se exige que el libro llene el volumen pedido,
    tenga competencia y tenga stock.
    """
    avisos = getattr(v, f"{lado}_avisos", None)
    if avisos is None:                       # no medible (CEX): se deja pasar
        return True
    if getattr(v, f"{lado}_alcanza", None) is False:
        return False
    stock = getattr(v, f"{lado}_stock", None) or 0.0
    return avisos >= LIQ_MIN_AVISOS and stock >= LIQ_MIN_STOCK_USD


# Venue cuyas órdenes cuentan para el Comerciante Verificado de Binance P2P.
BINANCE_P2P = "binancep2p"


def ruta_por_binance(r: "Route") -> bool:
    """¿La jugada deja al menos una orden en el P2P de Binance?"""
    return BINANCE_P2P in (r.buy_venue, r.sell_venue)


def patas_binance(p: "Play") -> int:
    """Cuántas de las dos patas caen en Binance P2P (1 orden cada una)."""
    return [p.buy_venue, p.sell_venue].count(BINANCE_P2P)


def _play_from_route(r: "Route", *, network_fee_pct: float,
                     secundarios: frozenset[str] = frozenset()) -> Play:
    # Cross-venue paga fee de red (mover USDT); intra-venue (mm) no.
    net = r.net_pct if r.buy_venue == r.sell_venue else r.net_pct - network_fee_pct
    ars = net / 100 * 1000 * r.buy_price
    return Play(
        kind=r.kind,
        buy_venue=r.buy_venue, buy_price=r.buy_price, buy_mode=r.buy_mode,
        sell_venue=r.sell_venue, sell_price=r.sell_price, sell_mode=r.sell_mode,
        net_pct=net, ars_per_1000=ars,
        secundario=bool({r.buy_venue, r.sell_venue} & secundarios),
    )


def _mejor(routes: dict[str, "Route"], network_fee_pct: float,
           secundarios: frozenset[str] = frozenset()) -> list:
    plays = [_play_from_route(r, network_fee_pct=network_fee_pct,
                              secundarios=secundarios)
             for r in routes.values()]
    plays.sort(key=lambda p: p.net_pct, reverse=True)
    return plays


def _primera(plays: list) -> "Play | None":
    """La mejor jugada que gana y no pasa por un venue secundario."""
    for p in plays:
        if p.secundario:
            continue
        return p if p.net_pct > 0 else None
    return None


def _misma_jugada(a: "Play | None", b: "Play | None") -> bool:
    if a is None or b is None:
        return False
    return (a.buy_venue, a.buy_mode, a.sell_venue, a.sell_mode) ==            (b.buy_venue, b.buy_mode, b.sell_venue, b.sell_mode)


def build_strategy(
    routes: dict[str, "Route"],
    *,
    network_fee_pct: float,
    outside_note: "OutsideNote | None" = None,
    routes_liquidas: dict[str, "Route"] | None = None,
    routes_binance: dict[str, "Route"] | None = None,
    secundarios: frozenset[str] = frozenset(),
) -> Strategy:
    """Rankea las jugadas por neto final (con haircut de red aplicado) y devuelve
    la mejor + hasta 2 alternativas. `routes` es la salida de arb_matrix.best_routes.

    `routes_liquidas` es la misma búsqueda pero restringida a puntas con volumen.
    De ahí sale `con_volumen`: la mejor jugada *ejecutable en tamaño*, que se
    muestra abajo de la mejor cuando no son la misma. Sin eso el tablero ofrece
    el precio de un libro que no mueve plata.

    `secundarios` son venues que casi nunca operan (KuCoin, pedido 2026-09-16):
    ninguna tarjeta principal los usa; sólo aparecen entre las alternativas,
    marcados con `Play.secundario`.
    """
    plays = _mejor(routes, network_fee_pct, secundarios)
    best = _primera(plays)
    alternatives = [p for p in plays if p is not best][:2] if best is not None else []

    con_volumen = None
    if routes_liquidas:
        liq = _mejor(routes_liquidas, network_fee_pct, secundarios)
        cand = _primera(liq)
        if cand is not None and not _misma_jugada(cand, best):
            con_volumen = cand

    # La jugada para sumar en Binance. Si la mejor ya pasa por ahí no se repite:
    # se marca best_en_binance y el panel le pone el visto.
    binance = None
    best_en_binance = bool(best is not None and BINANCE_P2P in (best.buy_venue, best.sell_venue))
    if routes_binance and not best_en_binance:
        bin_plays = _mejor(routes_binance, network_fee_pct, secundarios)
        cand = _primera(bin_plays)
        if cand is not None and not _misma_jugada(cand, best):
            binance = cand

    return Strategy(best=best, alternatives=alternatives,
                    outside_note=outside_note, con_volumen=con_volumen,
                    binance=binance, best_en_binance=best_en_binance)


def _is_p2p(name: str) -> bool:
    return name.endswith("p2p")


def _sell_realize(name: str, info: dict) -> float | None:
    """Precio de venta que se realiza: P2P publicás arriba (ask); CEX vendés directo
    al bid NETO (totalBid, ya con comisiones), con fallback al bid crudo."""
    try:
        if _is_p2p(name):
            price = float(info["ask"])
        else:
            price = float(info.get("totalBid") or info["bid"])
    except (KeyError, TypeError, ValueError):
        return None
    return price if price > 0 else None


def find_outside_note(
    payload: dict,
    *,
    operable_venues: set[str],
    broad_whitelist: set[str],
    remesa_venues: set[str],
    blacklist: set[str],
    margin_pct: float,
    max_age_min: int,
    now: float,
) -> "OutsideNote | None":
    """Si un venue FUERA de operable_venues paga (vendiendo) más que el mejor operable
    por ≥ margin_pct, devuelve el aviso. Solo lado 'sell'. None si no aplica."""
    max_age = max_age_min * 60
    best_op: tuple[float, str] | None = None
    best_out: tuple[float, str] | None = None
    for name, info in payload.items():
        low = name.lower()
        if low not in broad_whitelist or low in remesa_venues or low in blacklist:
            continue
        try:
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - t > max_age:
            continue
        price = _sell_realize(low, info)
        if price is None:
            continue
        if low in operable_venues:
            if best_op is None or price > best_op[0]:
                best_op = (price, low)
        else:
            if best_out is None or price > best_out[0]:
                best_out = (price, low)
    if best_out is None or best_op is None:
        return None
    if best_out[0] >= best_op[0] * (1 + margin_pct / 100):
        return OutsideNote(venue=best_out[1], side="sell", price=best_out[0])
    return None
