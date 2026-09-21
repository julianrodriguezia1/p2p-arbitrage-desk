"""Referencia de mercado local desde CriptoYa. Solo lectura pública."""
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import requests

BASE_URL = "https://criptoya.com/api"


@dataclass
class Reference:
    best_bid: Decimal
    best_bid_exchange: str
    best_ask: Decimal
    best_ask_exchange: str


@dataclass
class ArbRoute:
    buy_ex: str
    buy_ask: float
    sell_ex: str
    sell_bid: float
    gross_pct: float


@dataclass
class MarketExtremes:
    """Dónde comprar más barato (ask mínimo) y vender más caro (bid máximo).

    A diferencia de ArbRoute, NO excluye que ambas puntas sean el mismo venue
    (acá solo informamos extremos del mercado, no exigimos una ruta cruzada).
    """
    buy_ex: str
    buy_ask: float
    sell_ex: str
    sell_bid: float

    @property
    def spread_pct(self) -> float:
        return (self.sell_bid - self.buy_ask) / self.buy_ask * 100


_CACHE: dict[tuple, tuple[float, Reference | None]] = {}


def best_reference(payload: dict, whitelist: set[str]) -> "Reference | None":
    """Mejor bid (max) y mejor ask (min) entre exchanges de la whitelist.

    payload: dict CriptoYa {exchange: {"ask":.., "bid":.., ...}}.
    whitelist: claves (lowercase) de exchanges aprobados.
    None si ningún exchange whitelist aporta datos válidos.
    """
    bids: list[tuple[Decimal, str]] = []
    asks: list[tuple[Decimal, str]] = []
    for name, info in payload.items():
        if name.lower() not in whitelist:
            continue
        try:
            bid = Decimal(str(info["bid"]))
            ask = Decimal(str(info["ask"]))
        except (KeyError, TypeError, InvalidOperation):
            continue
        # Exchanges sin ofertas devuelven 0: ignorarlos para no falsear el mejor
        # bid/ask (un ask=0 se tomaría como "el más barato" y rompe el spread).
        if bid <= 0 or ask <= 0:
            continue
        bids.append((bid, name))
        asks.append((ask, name))
    if not bids or not asks:
        return None
    best_bid, bb = max(bids, key=lambda x: x[0])
    best_ask, ba = min(asks, key=lambda x: x[0])
    return Reference(best_bid, bb, best_ask, ba)


def arbitrage_route(payload: dict, whitelist: set[str], *,
                    max_age_min: int, now: float) -> "ArbRoute | None":
    """Mejor ruta CEX->P2P: comprar al ask mínimo, vender al bid máximo.

    Solo considera exchanges de `whitelist` con bid/ask>0 y cotización fresca
    (`now - time <= max_age_min*60`). None si no queda venue válido o si el
    mejor ask y el mejor bid son del mismo exchange.
    """
    max_age = max_age_min * 60
    asks: list[tuple[float, str]] = []
    bids: list[tuple[float, str]] = []
    for name, info in payload.items():
        if name.lower() not in whitelist:
            continue
        try:
            ask = float(info["ask"])
            bid = float(info["bid"])
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ask <= 0 or bid <= 0:
            continue
        if now - t > max_age:
            continue
        asks.append((ask, name))
        bids.append((bid, name))
    if not asks or not bids:
        return None
    buy_ask, buy_ex = min(asks)
    sell_bid, sell_ex = max(bids)
    if buy_ex == sell_ex:
        return None
    gross_pct = (sell_bid - buy_ask) / buy_ask * 100
    return ArbRoute(buy_ex, buy_ask, sell_ex, sell_bid, gross_pct)


def market_extremes(payload: dict, whitelist: set[str], *,
                    max_age_min: int, now: float) -> "MarketExtremes | None":
    """Ask mínimo (comprar más barato) y bid máximo (vender más caro).

    Solo considera exchanges de `whitelist` con bid/ask>0 y cotización fresca
    (`now - time <= max_age_min*60`), para no tomar precios fantasma de monedas
    delisteadas. None si no queda ningún venue válido.
    """
    max_age = max_age_min * 60
    asks: list[tuple[float, str]] = []
    bids: list[tuple[float, str]] = []
    for name, info in payload.items():
        if name.lower() not in whitelist:
            continue
        try:
            ask = float(info["ask"])
            bid = float(info["bid"])
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ask <= 0 or bid <= 0:
            continue
        if now - t > max_age:
            continue
        asks.append((ask, name))
        bids.append((bid, name))
    if not asks or not bids:
        return None
    buy_ask, buy_ex = min(asks)
    sell_bid, sell_ex = max(bids)
    return MarketExtremes(buy_ex, buy_ask, sell_ex, sell_bid)


def rank_extremes(payload: dict, whitelist: set[str], *, max_age_min: int,
                  now: float, top: int = 3) -> dict:
    """Top-N venues para comprar (más barato) y para vender (más caro), frescos y
    de la whitelist. Usa el precio NETO de CriptoYa (totalAsk/totalBid, ya con
    comisiones y costo de cash-out), cayendo a ask/bid crudo si no viene el total.
    Así el precio a cotizarle al cliente es lo que realmente pagás/cobrás.
    Devuelve {"buys": [{"exchange","price"}...], "sells": [{"exchange","price"}...]}."""
    max_age = max_age_min * 60
    asks: list[tuple[float, str]] = []
    bids: list[tuple[float, str]] = []
    for name, info in payload.items():
        if name.lower() not in whitelist:
            continue
        try:
            ask = float(info.get("totalAsk") or info["ask"])
            bid = float(info.get("totalBid") or info["bid"])
            t = float(info["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if ask <= 0 or bid <= 0 or now - t > max_age:
            continue
        asks.append((ask, name))
        bids.append((bid, name))
    buys = [{"exchange": n, "price": p} for p, n in sorted(asks)[:top]]
    sells = [{"exchange": n, "price": p} for p, n in sorted(bids, reverse=True)[:top]]
    return {"buys": buys, "sells": sells}


def fetch_reference(asset: str, fiat: str, volume: float, *,
                    whitelist: set[str], session=None,
                    now=None, ttl: float = 30.0) -> "Reference | None":
    """GET {BASE_URL}/{asset}/{fiat}/{volume}; cachea `ttl` seg por clave.

    Devuelve None si CriptoYa falla o no hay datos whitelist (el CLI sigue).
    """
    now_fn = now or time.time
    key = (asset.upper(), fiat.upper(), volume)
    t = now_fn()
    cached = _CACHE.get(key)
    if cached is not None and t - cached[0] < ttl:
        return cached[1]

    sess = session or requests.Session()
    url = f"{BASE_URL}/{asset}/{fiat}/{volume}"
    try:
        resp = sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        ref = best_reference(resp.json(), whitelist)
    except Exception:
        ref = None
    _CACHE[key] = (t, ref)
    return ref


_ARB_CACHE: dict[tuple, tuple[float, "ArbRoute | None"]] = {}


def fetch_arbitrage_route(asset: str, fiat: str, volume: float, *,
                          whitelist: set[str], max_age_min: int,
                          session=None, now=None,
                          ttl: float = 30.0) -> "ArbRoute | None":
    """GET {BASE_URL}/{asset}/{fiat}/{volume} y devuelve la mejor ruta CEX->P2P.

    Cachea `ttl` seg por clave. None si CriptoYa falla o no hay ruta válida.
    """
    now_fn = now or time.time
    key = (asset.upper(), fiat.upper(), volume)
    t = now_fn()
    cached = _ARB_CACHE.get(key)
    if cached is not None and t - cached[0] < ttl:
        return cached[1]

    sess = session or requests.Session()
    url = f"{BASE_URL}/{asset}/{fiat}/{volume}"
    try:
        resp = sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        route = arbitrage_route(resp.json(), whitelist,
                                max_age_min=max_age_min, now=t)
    except Exception:
        route = None
    _ARB_CACHE[key] = (t, route)
    return route


_EXT_CACHE: dict[tuple, tuple[float, "MarketExtremes | None"]] = {}


def fetch_market_extremes(asset: str, fiat: str, volume: float, *,
                          whitelist: set[str], max_age_min: int,
                          session=None, now=None,
                          ttl: float = 30.0) -> "MarketExtremes | None":
    """GET {BASE_URL}/{asset}/{fiat}/{volume} y devuelve dónde comprar más barato
    y vender más caro (ask mínimo / bid máximo, frescos).

    Cachea `ttl` seg por clave. None si CriptoYa falla o no hay venue válido.
    """
    now_fn = now or time.time
    key = (asset.upper(), fiat.upper(), volume)
    t = now_fn()
    cached = _EXT_CACHE.get(key)
    if cached is not None and t - cached[0] < ttl:
        return cached[1]

    sess = session or requests.Session()
    url = f"{BASE_URL}/{asset}/{fiat}/{volume}"
    try:
        resp = sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        ext = market_extremes(resp.json(), whitelist,
                              max_age_min=max_age_min, now=t)
    except Exception:
        ext = None
    _EXT_CACHE[key] = (t, ext)
    return ext


_PAYLOAD_CACHE: dict[tuple, tuple[float, dict]] = {}


def fetch_payload(asset: str, fiat: str, volume: float, *,
                  session=None, now=None, ttl: float = 30.0) -> dict:
    """GET {BASE_URL}/{asset}/{fiat}/{volume} y devuelve el dict crudo de CriptoYa.

    Cachea `ttl` seg por clave. Devuelve {} si CriptoYa falla (el CLI sigue).
    """
    now_fn = now or time.time
    key = (asset.upper(), fiat.upper(), volume)
    t = now_fn()
    cached = _PAYLOAD_CACHE.get(key)
    if cached is not None and t - cached[0] < ttl:
        return cached[1]

    sess = session or requests.Session()
    url = f"{BASE_URL}/{asset}/{fiat}/{volume}"
    try:
        resp = sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            data = {}
    except Exception:
        data = {}
    _PAYLOAD_CACHE[key] = (t, data)
    return data
