#!/usr/bin/env python3
"""
========================================================================
 P2P SPREAD SCANNER  ·  USDT / BTC contra ARS
========================================================================
Escanea Binance P2P, OKX P2P y Bybit P2P buscando spreads de arbitraje.

- Lee SOLO datos públicos (no requiere login ni API key).
- Detecta spreads dentro del mismo exchange (bid vs ask) y cruzados
  entre exchanges (comprar en A, vender en B).
- Filtra por la whitelist de exchanges aprobados.
- Modo single (una pasada) o modo watch (loop con alertas por umbral).

USO:
    python p2p_scanner.py                 # una pasada, USDT
    python p2p_scanner.py --asset BTC     # una pasada, BTC
    python p2p_scanner.py --watch         # loop infinito cada 60s
    python p2p_scanner.py --watch --min-spread 1.5 --interval 30

REQUISITOS:
    pip install requests

NOTA: las APIs de los exchanges P2P bloquean IPs de datacenter/servidor.
Corré esto desde tu máquina (tu IP residencial) o desde WSL en tu PC.
Si te da 403, NO es un bug del script: es el exchange bloqueando.
========================================================================
"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

try:
    import requests
except ImportError:
    print("Falta requests. Instalá con:  pip install requests")
    sys.exit(1)


# ============================================================
#  CONFIG
# ============================================================

# Exchanges aprobados (whitelist). Solo estos entran en los cálculos.
# Las apps de FX/remesa (DolarApp, Takenos, etc.) NO van acá.
WHITELIST = {"binance", "okx", "bybit"}

# Fee de retiro de red por defecto (en unidades de la cripto) para TRC20.
NETWORK_FEE = {"USDT": 1.0, "BTC": 0.0000}  # BTC normalmente paga fee en sats; ajustá si operás BTC

# Monto de referencia para filtrar anuncios con liquidez real (en ARS).
# Anuncios cuyo máximo sea menor a esto se ignoran (evita micro-órdenes).
MIN_LIQUIDITY_ARS = 100_000

# Headers para parecer un navegador y reducir bloqueos.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}


# ============================================================
#  MODELO DE DATOS
# ============================================================

@dataclass
class Ad:
    """Un anuncio individual del orderbook P2P."""
    exchange: str
    side: str            # "BUY" = vos comprás USDT ; "SELL" = vos vendés USDT
    price: float         # precio en ARS por unidad de cripto
    min_amount: float    # mínimo en ARS
    max_amount: float    # máximo en ARS
    available: float     # stock disponible en cripto
    merchant: str = ""
    methods: List[str] = field(default_factory=list)
    orders: int = 0          # cantidad de órdenes del vendedor (reputación)
    finish_rate: float = 0.0 # % de finalización (0-1)


@dataclass
class ExchangeQuote:
    """Mejor compra y mejor venta de un exchange."""
    exchange: str
    best_ask: Optional[float] = None   # precio más bajo al que PODÉS COMPRAR
    best_bid: Optional[float] = None   # precio más alto al que PODÉS VENDER
    ask_ads: List[Ad] = field(default_factory=list)
    bid_ads: List[Ad] = field(default_factory=list)


# ============================================================
#  FETCHERS por exchange
# ============================================================

def fetch_binance(asset: str, fiat: str, trade_type: str, rows: int = 10) -> List[Ad]:
    """
    trade_type: "BUY"  -> anuncios donde el maker VENDE (vos comprás)
                "SELL" -> anuncios donde el maker COMPRA (vos vendés)
    """
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    # OJO: NO mandar "countries": ["AR"]. Ese filtro es por país de registro del
    # anunciante y esconde los avisos ARS más baratos (vendedores que operan en
    # pesos pero no figuran registrados en AR). El navegador logueado no lo aplica;
    # sin él, el libro coincide con lo que ve el usuario en binance.com.
    payload = {
        "page": 1, "rows": rows, "payTypes": [],
        "publisherType": None, "asset": asset, "fiat": fiat,
        "tradeType": trade_type,
    }
    r = requests.post(url, json=payload, headers=BROWSER_HEADERS, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    ads = []
    for item in data:
        adv = item.get("adv", {})
        advertiser = item.get("advertiser", {})
        try:
            ads.append(Ad(
                exchange="binance",
                side="BUY" if trade_type == "BUY" else "SELL",
                price=float(adv.get("price", 0)),
                min_amount=float(adv.get("minSingleTransAmount", 0) or 0),
                max_amount=float(adv.get("dynamicMaxSingleTransAmount",
                                          adv.get("maxSingleTransAmount", 0)) or 0),
                available=float(adv.get("surplusAmount", 0) or 0),
                merchant=advertiser.get("nickName", ""),
                methods=[m.get("tradeMethodName", m.get("identifier", ""))
                         for m in adv.get("tradeMethods", [])],
                orders=int(advertiser.get("monthOrderCount", 0) or 0),
                finish_rate=float(advertiser.get("monthFinishRate", 0) or 0),
            ))
        except (ValueError, TypeError):
            continue
    return ads


def fetch_okx(asset: str, fiat: str, trade_type: str, rows: int = 10) -> List[Ad]:
    """
    Para COMPRAR USDT tomás los anuncios de VENTA del maker (side=sell);
    para VENDER, los de compra (side=buy). OKX devuelve los datos en body[side].
    (Verificado contra okx.com: side=sell/body["sell"] == página "Comprar USDT".)
    """
    side = "sell" if trade_type == "BUY" else "buy"
    url = ("https://www.okx.com/v3/c2c/tradingOrders/books"
           f"?quoteCurrency={fiat}&baseCurrency={asset}&side={side}"
           "&paymentMethod=all&userType=all&showTrade=false"
           "&showFollow=false&showAlreadyTraded=false&isAbleFilter=false")
    headers = dict(BROWSER_HEADERS, **{"x-locale": "es_LA"})
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    body = r.json().get("data", {})
    items = body.get(side) or []
    ads = []
    for it in items[:rows]:
        try:
            ads.append(Ad(
                exchange="okx",
                side="BUY" if trade_type == "BUY" else "SELL",
                price=float(it.get("price", 0)),
                min_amount=float(it.get("quoteMinAmountPerOrder", 0) or 0),
                max_amount=float(it.get("quoteMaxAmountPerOrder", 0) or 0),
                available=float(it.get("availableAmount", 0) or 0),
                merchant=it.get("nickName", ""),
                # OKX devuelve paymentMethods como lista de strings (antes eran objetos).
                methods=[p if isinstance(p, str) else p.get("paymentMethod", "")
                         for p in (it.get("paymentMethods") or [])],
                orders=int(it.get("completedOrderQuantity", 0) or 0),
                finish_rate=float(it.get("completedRate", 0) or 0),  # OKX: 0-1
            ))
        except (ValueError, TypeError, AttributeError):
            continue
    return ads


def fetch_bybit(asset: str, fiat: str, trade_type: str, rows: int = 10) -> List[Ad]:
    """
    Bybit: para COMPRAR USDT tomás los anuncios de venta del maker (side=1);
    para VENDER, los de compra (side=0). (Verificado: side=1 = asks ~mercado+,
    side=0 = bids ~mercado-, así compra >= venta como corresponde.)
    """
    url = "https://api2.bybit.com/fiat/otc/item/online"
    side = "1" if trade_type == "BUY" else "0"
    payload = {
        "userId": "", "tokenId": asset, "currencyId": fiat,
        "payment": [], "side": side, "size": str(rows), "page": "1",
        "amount": "", "authMaker": False, "canTrade": False,
    }
    r = requests.post(url, json=payload, headers=BROWSER_HEADERS, timeout=15)
    r.raise_for_status()
    items = r.json().get("result", {}).get("items", [])
    ads = []
    for it in items[:rows]:
        try:
            ads.append(Ad(
                exchange="bybit",
                side="BUY" if trade_type == "BUY" else "SELL",
                price=float(it.get("price", 0)),
                min_amount=float(it.get("minAmount", 0) or 0),
                max_amount=float(it.get("maxAmount", 0) or 0),
                available=float(it.get("lastQuantity", 0) or 0),
                merchant=it.get("nickName", ""),
                methods=it.get("payments", []) if isinstance(it.get("payments"), list) else [],
                orders=int(it.get("recentOrderNum", 0) or 0),
                finish_rate=float(it.get("recentExecuteRate", 0) or 0) / 100,  # Bybit: 0-100
            ))
        except (ValueError, TypeError):
            continue
    return ads


def fetch_bitget(asset: str, fiat: str, trade_type: str, rows: int = 20) -> List[Ad]:
    """
    API P2P pública de Bitget. side=1 -> avisos donde el maker VENDE (vos COMPRÁS);
    side=2 -> el maker COMPRA (vos VENDÉS).
    """
    url = "https://www.bitget.com/v1/p2p/pub/adv/queryAdvList"
    side = 1 if trade_type == "BUY" else 2
    payload = {
        "side": side, "pageNo": 1, "pageSize": rows,
        "coinCode": asset, "fiatCode": fiat, "languageType": 0,
    }
    r = requests.post(url, json=payload, headers=BROWSER_HEADERS, timeout=15)
    r.raise_for_status()
    items = r.json().get("data", {}).get("dataList", [])
    ads = []
    for it in items[:rows]:
        try:
            ads.append(Ad(
                exchange="bitget",
                side="BUY" if trade_type == "BUY" else "SELL",
                price=float(it.get("price", 0) or 0),
                min_amount=float(it.get("minAmount", 0) or 0),
                max_amount=float(it.get("maxAmount", 0) or 0),
                available=float(it.get("amount", 0) or 0),
                merchant=it.get("nickName", ""),
                methods=[m.get("paymethodName", "") for m in (it.get("paymethodInfo") or [])],
                orders=int(it.get("turnoverNum", 0) or 0),
                finish_rate=float(it.get("turnoverRate", 0) or 0),  # Bitget: 0-1
            ))
        except (ValueError, TypeError):
            continue
    return ads


def fetch_kucoin(asset: str, fiat: str, trade_type: str, rows: int = 20) -> List[Ad]:
    """API web P2P pública de KuCoin. side=SELL -> el maker VENDE (vos COMPRÁS);
    side=BUY -> el maker COMPRA (vos VENDÉS).

    Esquema real confirmado con probe 2026-07-02:
    - items a raíz del JSON (NO bajo 'data')
    - precio en 'floatPrice' (no 'price')
    - métodos en 'payTypeNameEn' (no 'payTypeName')
    - dealOrderNum es STRING; dealOrderRate es string '99.52%'
    """
    url = "https://www.kucoin.com/_api/otc/ad/list"
    side = "SELL" if trade_type == "BUY" else "BUY"
    params = {
        "currency": asset, "side": side, "legal": fiat,
        "page": 1, "pageSize": rows, "status": "PUTUP", "lang": "es_ES",
    }
    r = requests.get(url, params=params, headers=BROWSER_HEADERS, timeout=15)
    r.raise_for_status()
    items = r.json().get("items", [])
    ads = []
    for it in items[:rows]:
        try:
            # dealOrderRate llega como "99.52%" -> convertir a float 0-1
            rate_str = str(it.get("dealOrderRate") or "0").replace("%", "").strip()
            finish_rate = float(rate_str) / 100 if rate_str else 0.0
            ads.append(Ad(
                exchange="kucoin",
                side="BUY" if trade_type == "BUY" else "SELL",
                price=float(it.get("floatPrice") or 0),
                min_amount=float(it.get("limitMinQuote") or 0),
                max_amount=float(it.get("limitMaxQuote") or 0),
                available=float(it.get("currencyQuantity") or 0),
                merchant=it.get("nickName", ""),
                methods=[m.get("payTypeNameEn", "") for m in (it.get("adPayTypes") or [])],
                orders=int(it.get("dealOrderNum") or 0),
                finish_rate=finish_rate,
            ))
        except (ValueError, TypeError, AttributeError):
            continue
    return ads


FETCHERS = {
    "binance": fetch_binance,
    "okx": fetch_okx,
    "bybit": fetch_bybit,
    "bitget": fetch_bitget,
    "kucoin": fetch_kucoin,
}


# ============================================================
#  LÓGICA DE SCANNING
# ============================================================

def get_quote(exchange: str, asset: str, fiat: str) -> Optional[ExchangeQuote]:
    """Trae los mejores precios de compra y venta de un exchange."""
    fetcher = FETCHERS[exchange]
    try:
        buy_ads = fetcher(asset, fiat, "BUY")    # vos comprás
        sell_ads = fetcher(asset, fiat, "SELL")  # vos vendés
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        print(f"  [!] {exchange}: HTTP {code} (probable bloqueo de IP). Saltando.")
        return None
    except Exception as e:
        print(f"  [!] {exchange}: error {type(e).__name__}: {e}. Saltando.")
        return None

    # Filtro de liquidez: descartamos anuncios chicos
    buy_ads = [a for a in buy_ads if a.max_amount >= MIN_LIQUIDITY_ARS]
    sell_ads = [a for a in sell_ads if a.max_amount >= MIN_LIQUIDITY_ARS]

    q = ExchangeQuote(exchange=exchange, ask_ads=buy_ads, bid_ads=sell_ads)
    if buy_ads:
        # mejor compra = precio más BAJO disponible
        q.best_ask = min(a.price for a in buy_ads)
    if sell_ads:
        # mejor venta = precio más ALTO disponible
        q.best_bid = max(a.price for a in sell_ads)
    return q


def scan(asset: str, fiat: str = "ARS") -> List[ExchangeQuote]:
    quotes = []
    for ex in WHITELIST:
        if ex not in FETCHERS:
            continue
        print(f"  → consultando {ex}...")
        q = get_quote(ex, asset, fiat)
        if q and (q.best_ask or q.best_bid):
            quotes.append(q)
    return quotes


def find_opportunities(quotes: List[ExchangeQuote], asset: str):
    """
    Devuelve dos listas:
      intra: spread dentro del mismo exchange (bid - ask)
      cross: comprar en A, transferir, vender en B
    """
    net_fee = NETWORK_FEE.get(asset, 0)

    intra = []
    for q in quotes:
        if q.best_ask and q.best_bid:
            spread = q.best_bid - q.best_ask
            pct = (spread / q.best_ask) * 100
            intra.append((q.exchange, q.best_ask, q.best_bid, spread, pct))
    intra.sort(key=lambda x: -x[4])

    cross = []
    for qb in quotes:                 # compro en qb
        for qs in quotes:             # vendo en qs
            if qb.exchange == qs.exchange:
                continue
            if not (qb.best_ask and qs.best_bid):
                continue
            # 1000 unidades de referencia, descontando fee de transferencia
            vol = 1000
            ars_in = vol * qb.best_ask
            ars_out = (vol - net_fee) * qs.best_bid
            net = ars_out - ars_in
            pct = (net / ars_in) * 100
            cross.append((qb.exchange, qb.best_ask, qs.exchange, qs.best_bid, net, pct))
    cross.sort(key=lambda x: -x[5])

    return intra, cross


# ============================================================
#  PRESENTACIÓN
# ============================================================

def fmt(n):
    return f"${n:,.2f}"


def print_report(quotes, intra, cross, asset, min_spread):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 70)
    print(f" REPORTE {asset}/ARS  ·  {ts}")
    print("=" * 70)

    if not quotes:
        print("\n Sin datos. Todos los exchanges fallaron (probable bloqueo de IP).")
        print(" Corré el script desde tu máquina/WSL, no desde un servidor.")
        return

    print("\n MEJORES PRECIOS POR EXCHANGE")
    print(f" {'Exchange':<12}{'Comprar (ask)':<18}{'Vender (bid)':<18}{'Spread int.'}")
    print(" " + "-" * 60)
    for q in quotes:
        ask = fmt(q.best_ask) if q.best_ask else "—"
        bid = fmt(q.best_bid) if q.best_bid else "—"
        sp = ""
        if q.best_ask and q.best_bid:
            sp = f"{((q.best_bid - q.best_ask)/q.best_ask)*100:+.3f}%"
        print(f" {q.exchange:<12}{ask:<18}{bid:<18}{sp}")

    print("\n CROSS-EXCHANGE (comprar en A → transferir → vender en B)")
    print(f" {'Comprar':<10}{'a':<14}{'Vender':<10}{'a':<14}{'Gan/1000':<14}{'%'}")
    print(" " + "-" * 64)
    any_good = False
    for b, ba, s, sb, net, pct in cross[:8]:
        flag = "  <<<" if pct >= min_spread else ""
        if pct >= min_spread:
            any_good = True
        print(f" {b:<10}{fmt(ba):<14}{s:<10}{fmt(sb):<14}{fmt(net):<14}{pct:+.3f}%{flag}")

    if not any_good:
        print(f"\n Ninguna oportunidad supera el umbral de {min_spread}%. Mercado eficiente.")
    return any_good


# ============================================================
#  ALERTA TELEGRAM (opcional, para el módulo de alertas)
# ============================================================

def send_telegram(msg: str, token: str = "", chat_id: str = ""):
    """Descomentá y configurá token/chat_id para recibir alertas al celu."""
    if not token or not chat_id:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
    except Exception as e:
        print(f"  [!] Telegram falló: {e}")


# ============================================================
#  MAIN
# ============================================================

def main():
    ap = argparse.ArgumentParser(description="Scanner de spreads P2P USDT/BTC ARS")
    ap.add_argument("--asset", default="USDT", choices=["USDT", "BTC"])
    ap.add_argument("--fiat", default="ARS")
    ap.add_argument("--watch", action="store_true", help="loop continuo")
    ap.add_argument("--interval", type=int, default=60, help="segundos entre pasadas")
    ap.add_argument("--min-spread", type=float, default=0.5,
                    help="umbral %% para marcar/alertar oportunidad")
    ap.add_argument("--tg-token", default="", help="token bot Telegram (opcional)")
    ap.add_argument("--tg-chat", default="", help="chat_id Telegram (opcional)")
    args = ap.parse_args()

    def one_pass():
        print(f"\n[{datetime.now():%H:%M:%S}] Escaneando {args.asset}/{args.fiat}...")
        quotes = scan(args.asset, args.fiat)
        intra, cross = find_opportunities(quotes, args.asset)
        good = print_report(quotes, intra, cross, args.asset, args.min_spread)
        if good and args.tg_token:
            best = cross[0]
            send_telegram(
                f"🟢 Spread {best[5]:+.2f}% — comprar {best[0]} vender {best[2]}",
                args.tg_token, args.tg_chat,
            )

    if args.watch:
        print(f"Modo watch: cada {args.interval}s. Ctrl+C para salir.")
        try:
            while True:
                one_pass()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nChau.")
    else:
        one_pass()


if __name__ == "__main__":
    main()
