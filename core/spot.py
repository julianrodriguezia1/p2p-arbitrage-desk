"""Precio spot BTC/USDT — la pata global de la ruta ARS→USDT→BTC.

Por qué existe: comprar BTC contra pesos es cruzar un mercado que no tiene
contraparte (medido el 22/08/2026: 1,54% de ancho en Binance P2P, 8,19% en
Bybit, 14,49% en OKX). Encadenar USDT/ARS (0,22% de ancho) con BTC/USDT
(0,000013%) sale más barato aunque pague el fee de spot.

Por qué NO se lee de Binance: `api.binance.com` devuelve 451 desde el VPS por
geolocalización. OKX responde y se desvió 0,009% del precio real de Binance en
la medición del 22/08; Kraken queda de respaldo.
"""
from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 10

# Par por activo. Lo que no esté acá no tiene ruta sintética y se contesta None
# sin pegarle a la red.
OKX_INST: dict[str, str] = {"BTC": "BTC-USDT"}
KRAKEN_PAIR: dict[str, str] = {"BTC": "XBTUSDT"}

OKX_URL = "https://www.okx.com/api/v5/market/ticker"
KRAKEN_URL = "https://api.kraken.com/0/public/Ticker"


def _valido(ask: float, bid: float) -> bool:
    """Un cero o un negativo multiplicado por el precio del USDT da una
    cotización de cero pesos: mejor probar la otra fuente."""
    return ask > 0 and bid > 0


def _okx(asset: str, sess) -> dict | None:
    inst = OKX_INST[asset]
    resp = sess.get(OKX_URL, params={"instId": inst}, timeout=TIMEOUT)
    resp.raise_for_status()
    d = (resp.json().get("data") or [])[0]
    ask, bid = float(d["askPx"]), float(d["bidPx"])
    return {"ask": ask, "bid": bid, "fuente": "okx"} if _valido(ask, bid) else None


def _kraken(asset: str, sess) -> dict | None:
    par = KRAKEN_PAIR[asset]
    resp = sess.get(KRAKEN_URL, params={"pair": par}, timeout=TIMEOUT)
    resp.raise_for_status()
    result = resp.json()["result"]
    # Kraken a veces renombra la clave del par (XBTUSDT → XXBTZUSD y demás), así
    # que se toma el único resultado en vez de asumir el nombre.
    d = result[par] if par in result else next(iter(result.values()))
    ask, bid = float(d["a"][0]), float(d["b"][0])
    return {"ask": ask, "bid": bid, "fuente": "kraken"} if _valido(ask, bid) else None


def spot_quote(asset: str, *, session=None) -> dict | None:
    """{"ask", "bid", "fuente"} del par {asset}/USDT, o None si no hay precio.

    None en vez de excepción: sin spot la cotización sigue viva, solo pierde la
    ruta sintética. Tumbarla entera sería peor.
    """
    asset = (asset or "").strip().upper()
    if asset not in OKX_INST:
        return None
    sess = session or requests
    for fuente in (_okx, _kraken):
        try:
            q = fuente(asset, sess)
            if q:
                return q
        except Exception:
            logger.warning("Spot %s no disponible en %s", asset,
                           fuente.__name__.strip("_"))
    return None
