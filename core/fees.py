"""Comisiones por modo (publicar vs tomar), a un tamaño de ticket dado.

Por qué no es una constante: el fee de tomador de Binance P2P es un **flat de
0,07 USDT por orden**, no un porcentaje. En un ticket de 1.000 USDT pesa 0,007%;
en uno de 100, 0,07%. Cobrarle a las dos puntas el mismo número plano (0,20%,
que es el de PUBLICAR) infla el costo de tomar unas 28 veces y esconde jugadas
que sí dan.

Motor puro, sin red: las tablas llegan por parámetro desde `config`.
"""


def por_modo(*, fees_by_venue: dict[str, dict[str, float]], volume: float,
             asset: str, flat_assets: tuple[str, ...]) -> dict[str, dict[str, float]]:
    """{venue: {"publicando": %, "tomando": %}} para ese ticket.

    `flat_assets` son los activos donde el flat de tomador está efectivamente
    anunciado. Para el resto no se inventa uno: se cobra sólo el `taker_pct`.
    """
    out: dict[str, dict[str, float]] = {}
    for venue, f in fees_by_venue.items():
        tomando = f.get("taker_pct", 0.0)
        flat = f.get("taker_flat_quote", 0.0)
        # El flat es POR ORDEN. "tomando" lo cobra una vez (un solo aviso llena
        # el ticket); "tomando_por_orden" es lo que suma cada aviso extra que
        # haga falta tomar para llenarlo (lo decide el motor de profundidad).
        por_orden = 0.0
        if flat and asset in flat_assets and volume > 0:
            por_orden = flat / volume * 100
            tomando += por_orden
        out[venue] = {"publicando": f.get("maker_pct", 0.0), "tomando": tomando,
                      "tomando_por_orden": por_orden}
    return out


def flat_por_orden(*, fees_by_venue: dict[str, dict[str, float]], venue: str,
                   asset: str, flat_assets: tuple[str, ...],
                   alias: dict[str, str] | None = None) -> float:
    """El flat de tomador POR ORDEN de un venue, en unidades del activo (0,07
    USDT en Binance). 0 si el venue no lo tiene o el activo no lo anuncia.
    `alias` traduce claves de fetcher ("binance") a claves de venue
    ("binancep2p") para los llamadores que trabajan con la otra."""
    if asset not in flat_assets:
        return 0.0
    key = venue if venue in fees_by_venue else (alias or {}).get(venue, venue)
    return float(fees_by_venue.get(key, {}).get("taker_flat_quote", 0.0) or 0.0)


def red_pct(*, volume: float, red: str | None = None) -> float:
    """El fee de red de USDT como % de `volume`.

    Es un flat en USDT, así que su peso depende del ticket: 0,01 sobre USD 1.000
    es 0,001%, sobre USD 99 es 0,0101%. Una red desconocida se cobra al precio de
    la más cara que conocemos — sin dato no se asume barato.
    """
    import config

    if volume <= 0:
        return 0.0
    tabla = config.FEE_RED_USDT_FLAT
    red = red or config.FEE_RED_USDT_DEFAULT
    flat = tabla.get(red, max(tabla.values()))
    return flat / volume * 100
