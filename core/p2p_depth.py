"""Precio P2P real por profundidad (VWAP del order book) + filtro de anzuelos."""
from __future__ import annotations

import statistics


def _lado_de(ads: list) -> str:
    """"BUY" (te venden) o "SELL" (te compran), por mayoría de los avisos."""
    lados = [getattr(a, "side", "") for a in ads]
    return "SELL" if lados.count("SELL") > lados.count("BUY") else "BUY"


def _weighted_median_price(ads: list, cuantil: float = 0.25) -> float:
    """El precio de referencia del libro: donde compite la gente.

    Se acumula stock DESDE LA PUNTA COMPETITIVA (el más barato si te venden, el
    más caro si te compran) hasta juntar `cuantil` del total, y se devuelve ese
    precio. No es el medio del libro: es la zona que se ejecuta.

    Antes se usaba la mediana ponderada por stock sobre todo el libro, y tenía el
    problema inverso al que vino a resolver. Caso real (KuCoin, 08/09/2026): dos
    avisos absurdos a 1.370 y 1.212 con 122.000 de stock contra ~50.000 de los
    precios reales ponían el centro en 1.370, y `filter_traps` descartaba los
    avisos BUENOS de 1.575 como si fueran el anzuelo — el motor informaba que te
    compraban a 1.406 cuando te compraban a 1.575. En un libro P2P el stock
    grande lejos de la punta no es señal de legitimidad: son avisos que acumulan
    stock justamente porque nadie se los toma.

    Anclar en la punta arregla ese caso sin romper el que la ponderación vino a
    cubrir (una cola de avisos chicos ya no corre el centro, porque la punta
    manda mientras tenga stock).
    """
    if not ads:
        return 0.0
    ordered = sorted(ads, key=lambda a: a.price,
                     reverse=(_lado_de(ads) == "SELL"))
    total = sum(a.available for a in ordered)
    if total <= 0:
        return statistics.median(a.price for a in ordered)
    objetivo, acc = total * cuantil, 0.0
    for a in ordered:
        acc += a.available
        if acc >= objetivo:
            return a.price
    return ordered[-1].price


def filter_traps(ads: list, max_dev_pct: float = 3.0) -> list:
    """Descarta anzuelos: avisos cuyo precio se aleja > max_dev_pct% del PRECIO
    DE REFERENCIA del libro — la zona competitiva, no el medio (ver
    `_weighted_median_price`). Con <=2 avisos no filtra (no hay con qué
    comparar). Si el filtro dejaría la lista vacía, devuelve los válidos sin
    filtrar."""
    valid = [a for a in ads if a.price > 0 and a.available > 0]
    valid = _sin_historial_fuera(valid)
    if len(valid) <= 2:
        return valid
    center = _weighted_median_price(valid)
    if center <= 0:
        return valid
    kept = [a for a in valid if abs(a.price - center) / center * 100 <= max_dev_pct]
    return kept or valid


def _sin_historial_fuera(ads: list) -> list:
    """Saca a las contrapartes que nunca cerraron una orden.

    El 22/08/2026 OKX ofrecía comprar USDT a 1.600 —0,9% arriba del mercado, con
    9.000 USDT y mínimo $1.600.000— de una cuenta con 0 órdenes y 0% de
    finalización. El desvío es demasiado chico para el filtro de anzuelos (1%
    contra un umbral de 3%), así que el tablero lo mostraba como la MEJOR opción
    para vender. Un precio mejor que el del mercado ofrecido por alguien sin un
    solo trade cerrado no es un precio, es una carnada.

    Sólo aplica a los avisos que traen el dato (los venues que no lo publican
    quedan como estaban) y nunca vacía el libro.
    """
    con_dato = [a for a in ads if getattr(a, "orders", None) is not None]
    if not con_dato:
        return ads
    kept = [a for a in ads if getattr(a, "orders", None) is None
            or a.orders > 0]
    return kept or ads


def _tomable(ad, remaining: float) -> float:
    """Cuánto se puede sacar REALMENTE de un aviso, en cripto.

    No alcanza con el stock: cada aviso publica un mínimo y un máximo POR ORDEN
    (en ARS). Encontrado el 22/08/2026 en el libro de Binance: el aviso más
    grande del tope tenía 1.990 USDT a buen precio pero un mínimo de $3.040.000
    — para una compra de $1.577.000 no existe. Contarlo como llenable es
    prometer un precio que no se puede ejecutar, el error que costó plata el
    21/08. Un límite en 0 (o ausente) significa "sin límite".
    """
    take = min(ad.available, remaining)
    maximo = getattr(ad, "max_amount", 0) or 0
    if maximo > 0:
        take = min(take, maximo / ad.price)
    minimo = getattr(ad, "min_amount", 0) or 0
    if minimo > 0 and take * ad.price < minimo:
        return 0.0          # no llegás al mínimo de ese aviso: no es tuyo
    return take


def _walk(ads: list, volume: float, side: str, chunk_min: float = 0.0) -> dict | None:
    """Una pasada por el libro en orden de precio. `chunk_min` saltea los avisos
    que aportan menos que eso (salvo que terminen de llenar el ticket)."""
    ordered = sorted(ads, key=lambda a: a.price, reverse=(side == "SELL"))
    remaining, cost, filled, ordenes = volume, 0.0, 0.0, 0
    for a in ordered:
        take = _tomable(a, remaining)
        if take <= 0:
            continue
        if chunk_min and take < min(chunk_min, remaining):
            continue
        cost += take * a.price
        filled += take
        remaining -= take
        ordenes += 1
        if remaining <= 0:
            break
    if filled <= 0:
        return None
    return {"price": cost / filled, "filled": filled, "ordenes": ordenes,
            "alcanza": remaining <= 0}


def precio_neto_por_orden(r: dict, side: str, fee_por_orden: float) -> float:
    """Precio efectivo por unidad con el flat por orden adentro, valuado al
    precio del llenado: comprar lo encarece, vender lo achica."""
    fee = r["ordenes"] * fee_por_orden * r["price"] / r["filled"]
    return r["price"] + fee if side == "BUY" else r["price"] - fee


# Tamaños mínimos de aviso a probar, como fracción del ticket. 1.0 = "una sola
# orden que lo llene entero"; 0 = el camino de siempre (mejor precio primero).
_CHUNKS = (0.1, 0.2, 0.34, 0.5, 1.0)


def depth_fill(ads: list, volume: float, side: str,
               fee_por_orden: float = 0.0) -> dict | None:
    """Camina el libro y cuenta todo lo que importa del llenado.

    Devuelve {"price", "filled", "ordenes", "alcanza"} o None si no hay avisos.
    `ordenes` es cuántos avisos distintos hay que tomar: un precio repartido en
    11 avisos son 11 chats y 11 transferencias, y eso decide tanto como el
    precio (el 22/08/2026 el usuario abandonó una compra en Binance por esto).

    `fee_por_orden` es el flat de tomador por orden, en unidades del activo
    (Binance: 0,07 USDT). Con eso el mejor precio ya no es el mejor llenado:
    10 avisos chicos a 1.589,46 rinden menos que uno grande a 1.588,90 después
    de pagar 10 fees. Se prueban llenados con avisos cada vez más grandes y se
    devuelve el que rinde más NETO del flat (pedido 2026-09-16). Si el libro no
    alcanza, se devuelve lo que hay, como siempre.
    """
    if not ads or volume <= 0:
        return None
    base = _walk(ads, volume, side)
    if not fee_por_orden or base is None or not base["alcanza"]:
        return base
    candidatos = [base]
    for frac in _CHUNKS:
        r = _walk(ads, volume, side, chunk_min=volume * frac)
        if r and r["alcanza"]:
            candidatos.append(r)
    mejor = max if side == "SELL" else min
    return mejor(candidatos, key=lambda r: precio_neto_por_orden(r, side, fee_por_orden))


def depth_price(ads: list, volume: float, side: str) -> float | None:
    """VWAP para llenar `volume`. BUY: de más barato a más caro; SELL: al revés.
    Si el stock no alcanza, promedia lo disponible. None si no hay avisos."""
    r = depth_fill(ads, volume, side)
    return r["price"] if r else None


def _lado(ads: list, volume: float, side: str, prefijo: str,
          fee_por_orden: float = 0.0) -> dict:
    """Precio y, además, de qué libro salió: sin eso no se distingue un precio
    bueno de uno que nadie puede ejecutar (el caso KuCoin del 2026-08-24)."""
    limpios = filter_traps(ads)
    r = depth_fill(limpios, volume, side, fee_por_orden=fee_por_orden)
    return {
        prefijo: r["price"] if r else None,
        f"{prefijo}_avisos": len(limpios),
        f"{prefijo}_stock": sum(a.available for a in limpios),
        f"{prefijo}_ordenes": r["ordenes"] if r else 0,
        f"{prefijo}_alcanza": bool(r and r["alcanza"]),
    }


def compute_depth_quote(buy_ads: list, sell_ads: list, volume: float,
                        fee_por_orden: float = 0.0) -> dict:
    """VWAP de las dos puntas para `volume`, filtrando anzuelos, más la liquidez
    que hay detrás de cada una (avisos, stock, órdenes a tomar, si alcanza).
    `fee_por_orden` (flat de tomador del venue) hace que se elija el llenado
    más barato neto, no el de mejor precio bruto; ver `depth_fill`."""
    return {**_lado(buy_ads, volume, "BUY", "ask", fee_por_orden),
            **_lado(sell_ads, volume, "SELL", "bid", fee_por_orden)}
