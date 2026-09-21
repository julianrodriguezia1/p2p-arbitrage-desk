"""Lógica de los comandos del bot: fetch al dashboard + formato (testeable)."""
from __future__ import annotations

import requests


def fetch_json(base_url: str, path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{base_url}{path}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


NL = chr(10)   # separador de líneas de los mensajes de Telegram


def _pct2(n: float | None) -> str:
    """Porcentaje con 2 decimales. El de 1 decimal redondea 0,09% a 0,1% y en
    una cotización esa diferencia es justo la que decide ganar o perder."""
    return f"{n:+.2f}%".replace(".", ",") if n is not None else "—"


def _miles(n: float | None) -> str:
    return f"{n:,.0f}".replace(",", ".") if n is not None else "—"


def _miles2(n: float | None) -> str:
    """Con centavos. El precio del USDT los necesita: entre 1.586,80 y 1.587,00
    hay $190 en una op de un millón y medio."""
    if n is None:
        return "—"
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(n: float | None) -> str:
    return f"{n:+.1f}%".replace(".", ",") if n is not None else "—"


_VENUE_LABEL = {
    "binance": "Binance", "binancep2p": "Binance P2P", "okexp2p": "OKX", "okx": "OKX",
    "bybit": "Bybit", "bybitp2p": "Bybit", "bitgetp2p": "Bitget",
    "kucoinp2p": "KuCoin", "eldoradop2p": "El Dorado",
    "saldo": "SaldoAr", "lemoncash": "Lemon", "lemoncashp2p": "Lemon P2P",
    "belo": "Belo", "ripio": "Ripio", "ripioexchange": "Ripio",
    "buenbit": "Buenbit", "satoshitango": "SatoshiTango", "letsbit": "Let'sBit",
    "cryptomktpro": "CryptoMKT", "cryptomkt": "CryptoMKT", "fiwind": "Fiwind",
    "cocoscrypto": "Cocos Crypto", "tiendacrypto": "TiendaCrypto",
    "pluscrypto": "PlusCrypto", "bitsoalpha": "Bitso", "decrypto": "Decrypto",
    "huobip2p": "Huobi", "bingxp2p": "BingX", "coinexp2p": "CoinEx",
}


def _label(venue: str) -> str:
    return _VENUE_LABEL.get(venue, venue)


_KIND_TAG = {
    "media": "⏳ esperás de un lado",
    "mm": "🟠 market-making (2 puntas)",
    "instant": "⚡ instantáneo",
}


def format_spread(data: dict) -> str:
    exchanges = data.get("exchanges") or []
    if not exchanges:
        return "No pude leer el spread ahora, probá de nuevo."
    lines = ["📊 Spread USDT/ARS (ahora)"]
    for e in exchanges:
        lines.append(
            f"{e['exchange']:<8} compra {_miles(e['ask'])}   "
            f"venta {_miles(e['bid'])}   intra {_pct(e['intra_pct'])}"
        )
    cb = data.get("cheapest_buy")
    if cb:
        lines.append(
            f"🟢 Más barato (comprar): {cb['exchange']} {_miles(cb['price'])}"
            f"  · {cb.get('type', '')}".rstrip()
        )
    ds = data.get("dearest_sell")
    if ds:
        lines.append(
            f"🔴 Más caro (vender): {ds['exchange']} {_miles(ds['price'])}"
            f"  · {ds.get('type', '')}".rstrip()
        )
    br = data.get("best_route")
    if br:
        lines.append(f"🚀 Spread: {_pct(br['gross_pct'])}")
    return "\n".join(lines)


def spread_text(base_url: str) -> str:
    try:
        return format_spread(fetch_json(base_url, "/api/spread/now"))
    except Exception:
        return "No pude leer el spread ahora, probá de nuevo."



def format_stock(position: dict, cost: dict) -> str:
    lines = [f"💰 Stock USDT: {_miles(position.get('stock'))}  (histórico: comprado − vendido)"]
    if cost.get("count"):
        lines.append(f"📥 Compras hoy: {_miles(cost.get('units'))} USDT @ prom {_miles(cost.get('avg_price'))}")
        be = cost.get("breakeven")
        if be is not None:
            lines.append(f"   Break-even al vender: {_miles(be)}")
    else:
        lines.append("📥 Sin compras hoy.")
    return "\n".join(lines)


def stock_text(base_url: str) -> str:
    try:
        pos = fetch_json(base_url, "/api/position")
        cost = fetch_json(base_url, "/api/cost/today")
        return format_stock(pos, cost)
    except Exception:
        return "No pude leer tu stock ahora, probá de nuevo."


def _play_line(p: dict) -> str:
    return (
        f"Comprá {p['buy_mode']} en {_label(p['buy_venue'])} @ {_miles(p['buy_price'])} → "
        f"vendé {p['sell_mode']} en {_label(p['sell_venue'])} @ {_miles(p['sell_price'])}"
    )


def format_estrategia(data: dict) -> str:
    best = data.get("best")
    if not best:
        return "🤔 Sin jugada con ganancia ahora. Probá de nuevo en un rato."
    lines = [
        f"🚀 MEJOR AHORA — {_pct(best['net_pct'])} neto (~${_miles(best['ars_per_1000'])} / 1000 USDT)",
        _play_line(best),
        f"{_KIND_TAG.get(best['kind'], '')} · neto de fees + red",
    ]
    cv = data.get("con_volumen")
    if cv:
        lines.append(f"📦 Con volumen real: {_play_line(cv)} ({_pct(cv['net_pct'])})")
    alts = data.get("alternatives") or []
    if alts:
        lines.append("")
        lines.append("Alternativas:")
        for a in alts:
            lines.append(f"{_KIND_TAG.get(a['kind'], a['kind'])}: {_label(a['buy_venue'])}→"
                         f"{_label(a['sell_venue'])} {_pct(a['net_pct'])}")
    note = data.get("outside_note")
    if note:
        lines.append("")
        lines.append(f"⚠️ Ojo: {_label(note['venue'])} paga {_miles(note['price'])} "
                     f"(fuera de tu whitelist, verificá liquidez)")
    return "\n".join(lines)


def estrategia_text(base_url: str) -> str:
    try:
        return format_estrategia(fetch_json(base_url, "/api/estrategia"))
    except Exception:
        return "No pude calcular la estrategia ahora, probá de nuevo."


# ── La jugada por Binance ─────────────────────────────────────────────────
# Aparte de la mejor jugada a secas: sólo las órdenes que quedan en el P2P de
# Binance cuentan para el Comerciante Verificado, así que a veces conviene la
# segunda mejor con tal de que la orden sume.

_BINANCE_P2P = "binancep2p"


def _patas_binance(p: dict) -> int:
    return [p.get("buy_venue"), p.get("sell_venue")].count(_BINANCE_P2P)


def _valor_meta(r: dict) -> str:
    """El avance de un requisito. Sin dato va FALTA, nunca un estimado."""
    valor, meta = r.get("valor"), r.get("meta")
    if valor is None:
        return f"{r.get('etiqueta', '')} FALTA"
    es_btc = str(r.get("unidad", "")).upper() == "BTC"
    fmt = (lambda n: f"{n:.3f}".replace(".", ",")) if es_btc else _miles
    unidad = " BTC" if es_btc else ""
    return f"{r.get('etiqueta', '')} {fmt(valor)}/{fmt(meta)}{unidad}"


def format_merchant(data: dict | None) -> str | None:
    reqs = (data or {}).get("requisitos") or []
    return "🎯 Verificado: " + " · ".join(_valor_meta(r) for r in reqs) if reqs else None


def format_binance(estrategia: dict, merchant: dict | None) -> str:
    ya = bool(estrategia.get("best_en_binance")) and estrategia.get("best")
    p = estrategia.get("best") if ya else estrategia.get("binance")
    if not p:
        return ("🅱️ Sin jugada por Binance ahora: ninguna que gane deja una orden "
                "en su P2P. Probá de nuevo en un rato.")
    cabeza = ("🅱️ La mejor jugada de ahora YA pasa por Binance"
              if ya else "🅱️ Mejor jugada POR BINANCE (no es la mejor a secas)")
    patas = _patas_binance(p)
    ordenes = f"{patas} orden" + ("es" if patas != 1 else "")
    lines = [
        f"{cabeza} — {_pct(p['net_pct'])} neto (~${_miles(p['ars_per_1000'])} / 1000 USDT)",
        _play_line(p),
        f"{_KIND_TAG.get(p['kind'], '')} · suma {ordenes} para el Verificado".lstrip(" ·"),
    ]
    avance = format_merchant(merchant)
    if avance:
        lines.append(avance)
    return NL.join(lines)


def binance_text(base_url: str) -> str:
    try:
        est = fetch_json(base_url, "/api/estrategia")
    except Exception:
        return "No pude calcular la jugada por Binance ahora, probá de nuevo."
    try:
        merch = fetch_json(base_url, "/api/merchant")
    except Exception:
        merch = None      # el avance del Verificado es un extra, no bloquea
    return format_binance(est, merch)


def format_billeteras(data: dict) -> str:
    month = data.get("month", "")
    wallets = data.get("wallets", {})
    lines = [f"📊 Billeteras — {month}"]

    def heat(w: dict) -> float:
        return w.get("pct_in") or 0.0

    for name, w in sorted(wallets.items(), key=lambda kv: (-heat(kv[1]), kv[0])):
        entra, tin, pin, rin = w["entra"], w["tope_in"], w["pct_in"], w["restante_in"]
        if tin:
            emoji = "🟢" if pin < 70 else ("🟡" if pin < 90 else "🔴")
            lines.append(f"{emoji} {name}  entra {_miles(entra)}/{_miles(tin)} "
                         f"({_pct(pin)}) · quedan {_miles(rin)}")
        else:
            lines.append(f"⚪ {name}  entra {_miles(entra)} (sin tope)")

    sin_mapear = data.get("sin_mapear", [])
    if sin_mapear:
        lines.append("⚠️ sin mapear: " + ", ".join(sin_mapear))
    return "\n".join(lines)


def billeteras_text(base_url: str) -> str:
    try:
        return format_billeteras(fetch_json(base_url, "/api/wallets"))
    except Exception:
        return "No pude traer las billeteras ahora, probá de nuevo."


def cotizacion_placa(base_url: str, side: str, margin_pct: float,
                     asset: str = "USDT"):
    """Cotiza al cliente según su lado + margen y devuelve
    (png_bytes, caption). (None, mensaje) si falla. side = 'compra' (el cliente me
    compra) | 'venta' (el cliente me vende). asset = 'USDT' | 'BTC'."""
    from bot.cotizar import (build_cotizacion, build_board, equivalencia,
                             make_placa, normalize_asset)
    asset = normalize_asset(asset)
    try:
        spread = fetch_json(base_url, "/api/spread/now", {"asset": asset})
        cot = build_cotizacion(spread, side, margin_pct, asset)
    except Exception:
        return None, "No pude leer los precios ahora, probá de nuevo."
    verbo = "Le vendés" if cot["accion"] == "VENDO" else "Le comprás"
    lines = [f"{verbo} {asset} a {_miles(cot['quote'])}  (margen {_pct(margin_pct)})"]
    eq = equivalencia(cot)
    if eq:
        lines.append(f"🔎 {eq}")
    # El dólar cripto es el precio del USDT: al lado de un precio de BTC no
    # informa nada y se lee como si fuera la referencia de la cotización.
    ref = _dolar_cripto() if asset == "USDT" else None
    if ref:
        lines.append(f"📊 Dólar cripto hoy: compra {_miles(ref['compra'])} "
                     f"· venta {_miles(ref['venta'])}")
    try:
        lines += _board_lines(build_board(spread))
    except Exception:
        pass
    return make_placa(cot), "\n".join(lines)


# ── Cotización al cliente con precio EJECUTABLE (bot: "cotizar BTC") ──────
# Responde las dos puntas de una, sin preguntar nada. El precio base es el que
# se ejecuta YA; publicar se muestra aparte porque depende de que te llenen.

def _monto(n: float, asset: str) -> str:
    """El monto cotizado, con los decimales que el activo necesita."""
    txt = f"{n:,.8f}".rstrip("0").rstrip(".") if asset == "BTC" else f"{n:,.0f}"
    return txt.replace(",", "X").replace(".", ",").replace("X", ".") + f" {asset}"


def _pasos_via(leg: dict, size: float, side: str) -> str:
    """Los dos pasos de la ruta sintética, con los números que hay que tipear.

    Sin esto la ruta es un precio que el usuario no sabe ejecutar: no sabe
    cuántos USDT comprar ni a qué precio convertir. La fuente del spot se dice
    porque NO es Binance (451 desde el VPS) y si no, no cierra contra su
    pantalla."""
    via = leg.get("via")
    if not via:
        return ""
    usdt = size * via["spot_price"]
    fuente = via["fuente"]
    if side == "BUY":
        # Comprar: primero los pesos se hacen USDT, después el USDT se hace BTC.
        return (f"{NL}   → comprás {_miles(usdt)} USDT @ "
                f"{_miles2(via['usdt_price'])} y convertís @ "
                f"{_miles(via['spot_price'])} ({fuente})")
    # Vender es al revés: primero el BTC se hace USDT, después el USDT se hace
    # pesos. Al revés le estaría diciendo que venda USDT que todavía no tiene.
    return (f"{NL}   → convertís a {_miles(usdt)} USDT @ "
            f"{_miles(via['spot_price'])} ({fuente}) y los vendés @ "
            f"{_miles2(via['usdt_price'])}")


def _leg_line(i: int, leg: dict, size: float, side: str = "BUY") -> str:
    modo = {"directo": "directo", "tomando": "instantáneo",
            "publicando": "publicando"}.get(leg["mode"], leg["mode"])
    linea = f"{i}. {_label(leg['venue']):<14}{_miles(leg['price']):>14}  {modo}"
    stock = leg.get("stock")
    if stock is not None:
        hay = f"{stock:.4f}".rstrip("0").rstrip(".").replace(".", ",")
        linea += f"  · hay {hay}"
        if not leg.get("alcanza", True):
            linea += f"  ⚠️ NO ALCANZA para {_monto(size, leg.get('asset', ''))}".rstrip()
    return linea + _pasos_via(leg, size, side)


def cotizacion_text(base_url: str, asset: str = "USDT",
                    size: float | None = None, margen: float | None = None) -> str:
    """Cotización de las dos puntas para mandar por Telegram. Nunca pregunta:
    con lo que sabe arma la respuesta completa o dice por qué no puede."""
    params: dict = {"asset": asset}
    if size is not None:
        params["size"] = size
    if margen is not None:
        params["margen"] = margen
    try:
        d = fetch_json(base_url, "/api/cotizacion", params)
    except Exception:
        return "No pude leer los precios ahora, probá de nuevo."

    a, sz = d.get("asset", asset), d.get("size") or 0
    if not d.get("buys") and not d.get("sells"):
        return (f"Sin precio de referencia para {a} ahora mismo "
                f"(ningún exchange de tu lista está cotizando). Probá de nuevo.")

    out = [f"{'₿' if a == 'BTC' else '💵'} {a} — para {_monto(sz, a)} "
           f"· margen {_pct(d.get('margin_pct'))} · precios netos", ""]

    if d.get("buys"):
        out.append("🟢 COMPRÁS más barato")
        out += [_leg_line(i, l, sz, "BUY") for i, l in enumerate(d["buys"], 1)]
        if d.get("precio_venta_cliente"):
            out.append(f"➡️ Le VENDÉS a {_miles(d['precio_venta_cliente'])}")
        out.append("")

    if d.get("sells"):
        out.append("🔴 VENDÉS más caro")
        out += [_leg_line(i, l, sz, "SELL") for i, l in enumerate(d["sells"], 1)]
        if d.get("precio_compra_cliente"):
            out.append(f"➡️ Le COMPRÁS a {_miles(d['precio_compra_cliente'])}")
        out.append("")

    if d.get("vuelta_pct") is not None:
        out.append(f"Costo de darte vuelta: {_pct2(d['vuelta_pct'])}")
        if d.get("cubre"):
            out.append(f"✅ El margen {_pct(d.get('margin_pct'))} cubre.")
        else:
            falta = d.get("faltante_pct")
            # faltante_pct ya viene positivo = lo que se pierde. Sin signo, que
            # un "+" delante de una pérdida se lee al revés.
            perdes = f" perdés {falta:.2f}%".replace(".", ",") if falta else ""
            out.append(f"⚠️ NO CUBRE:{perdes} — subí el margen antes de cotizar.")

    pub = d.get("publicando_compra")
    if pub:
        hay = f"{pub['stock']:.4f}".rstrip("0").rstrip(".").replace(".", ",")
        out += ["", f"💡 Si publicás en {_label(pub['venue'])} comprás a "
                    f"{_miles(pub['price'])}, pero dependés de que te tomen el "
                    f"aviso (del otro lado hay {hay})."]
    out += ["", "ℹ️ P2P = profundidad real del libro · CEX = cotización del "
                "exchange, sin libro visible. El precio se mueve: revalidá si "
                "pasaron unos minutos."]
    return NL.join(out).rstrip()


def _dolar_cripto():
    """Referencia del dólar cripto (dolarapi) o None. Función aparte para poder
    mockearla en tests y para que un fallo no rompa la placa."""
    from core.dolar_ref import fetch_dolar_cripto
    return fetch_dolar_cripto()


def _board_line(i: int, o: dict) -> str:
    """Una opción del tablero: CEX = precio directo; P2P = publicando · tomando."""
    label = _label(o["venue"])
    if o.get("mode") == "cex":
        return f"{i}. {label} {_miles(o['price'])} directo"
    aviso = " ⚠️ libro ancho" if o.get("ancho") else ""
    return (f"{i}. {label} {_miles(o['publicando'])} public. "
            f"· {_miles(o['tomando'])} tom.{aviso}")


def _board_lines(board: dict) -> list[str]:
    """Tablero de referencia (solo para el usuario): dónde comprás barato y
    dónde vendés caro, con modo, más la diferencia."""
    out: list[str] = []
    if board.get("buys"):
        out += ["", "🟢 COMPRÁS (barato)"]
        out += [_board_line(i, o) for i, o in enumerate(board["buys"], 1)]
    if board.get("sells"):
        out += ["", "🔴 VENDÉS (caro)"]
        out += [_board_line(i, o) for i, o in enumerate(board["sells"], 1)]
    if board.get("diff_ars") is not None:
        out += ["", f"💰 Dif: {_miles(board['best_buy'])} → "
                    f"{_miles(board['best_sell'])} = {_pct(board['diff_pct'])}"]
    return out


# ── "dónde compro más barato" / "dónde vendo más caro" ────────────────────
# Ranking entre venues con las DOS modalidades y las comisiones ya adentro de
# cada número: 0,07 USDT fijo tomando en Binance, 0,20% sólo si publicás ahí,
# cero en el resto. El usuario no tiene que hacer ninguna cuenta.

def _donde_linea(i: int, leg: dict) -> str:
    linea = f"{i}. {_label(leg['venue']):<14}{_miles2(leg['price']):>11}"
    if leg["mode"] == "directo":
        return linea + "   directo"
    if leg["mode"] == "publicando":
        return linea      # publicás UN aviso: contar órdenes acá sería ruido
    n = leg.get("ordenes") or 1
    # El plural lleva tilde y el singular no: "1 orden" / "7 órdenes".
    return linea + f"   {n} " + ("órdenes" if n != 1 else "orden")


def _donde_bloque(titulo: str, legs: list) -> list:
    if not legs:
        return []
    return [titulo] + [_donde_linea(i, l) for i, l in enumerate(legs, 1)] + [""]


def _ahorro_publicando(tomando: list, publicando: list, side: str) -> str | None:
    """Cuánto mejora publicar contra lo mejor que podés ejecutar YA. Es la
    cuenta que el usuario pidió que el bot hiciera solo: en los venues sin
    comisión publicar casi siempre gana, en Binance el 0,20% de maker se come
    la ventaja."""
    if not tomando or not publicando:
        return None
    base, mejor = tomando[0], publicando[0]
    pct = ((base["price"] - mejor["price"]) / base["price"] * 100 if side == "BUY"
           else (mejor["price"] - base["price"]) / base["price"] * 100)
    if pct <= 0:
        return None
    return (f"💡 Publicando en {_label(mejor['venue'])} mejorás {_pct2(pct)} "
            f"contra lo mejor de tomar, pero dependés de que te llenen.")


def _donde_punta(d: dict, side: str, asset: str, size: float) -> list:
    comprar = side == "BUY"
    tomando = d.get("buys" if comprar else "sells") or []
    publicando = d.get("publicando_buys" if comprar else "publicando_sells") or []
    cabeza = ("🟢 COMPRAR" if comprar else "🔴 VENDER")
    out = [f"{cabeza} — {_miles(size)} {asset}", ""]
    out += _donde_bloque("⚡ YA (tomando)", tomando)
    out += _donde_bloque("⏳ PUBLICANDO (esperás que te tomen)", publicando)
    aviso = _ahorro_publicando(tomando, publicando, side)
    if aviso:
        out += [aviso, ""]
    return out


def donde_text(base_url: str, lado: str = "ambos", monto: float | None = None,
               asset: str = "USDT", top: int = 5) -> str:
    """Ranking de dónde comprar más barato / vender más caro, con comisiones
    adentro. `lado` = 'compro' | 'vendo' | 'ambos'."""
    params: dict = {"asset": asset, "top": top, "margen": 0}
    if monto is not None:
        params["size"] = monto
    try:
        d = fetch_json(base_url, "/api/cotizacion", params)
    except Exception:
        return "No pude leer los precios ahora, probá de nuevo."

    a, sz = d.get("asset", asset), d.get("size") or 0
    sides = {"compro": ["BUY"], "vendo": ["SELL"]}.get(lado, ["BUY", "SELL"])
    out: list[str] = []
    for s in sides:
        out += _donde_punta(d, s, a, sz)
    if not [l for l in out if l.startswith(("1.", "2."))]:
        return f"No tengo precios de {a} ahora mismo. Probá de nuevo."
    out.append("ℹ️ Precios netos: tomando en Binance paga 0,07 USDT fijo, "
               "publicar ahí 0,20%; el resto no cobra. El precio cambia con el "
               "monto — pedime otro si vas a operar más grande.")
    return NL.join(out).rstrip()
