"""Plan de ejecución de una cotización a cliente: qué comprar y qué queda.

Motor puro, sin red. `core.cotizacion` resuelve los PRECIOS (con qué venue
conviene, precio ejecutable por profundidad, fee del spot); acá se traduce eso
a los pasos concretos: cuántos USDT comprar, cuánto entregar y cuánto queda de
ganancia.

La regla del proyecto sobre BTC vive acá adentro: **nunca se compra BTC por el
libro P2P**, siempre `ARS → USDT (P2P) → BTC (spot)`. Ver
`docs/investigacion-prima-btc-alts-ars.md`.
"""
from __future__ import annotations


def plan_para_cliente(
    *,
    ars: float,
    asset: str,
    margen_pct: float,
    costo_venue: float,
    usdt_price: float | None = None,
    spot_price: float | None = None,
    spot_fee_pct: float = 0.0,
    fee_red: float = 0.0,
) -> dict:
    """Traduce una cotización a los pasos de ejecución.

    `ars` es lo que manda el cliente; `costo_venue` es el precio ejecutable de
    reposición del activo (ARS por unidad, comisiones adentro) y es la base
    sobre la que se aplica `margen_pct`.

    Para BTC hacen falta además `usdt_price` (ARS por USDT en el P2P) y
    `spot_price` (unidades de USDT por BTC), porque la ruta pasa por USDT.

    `fee_red` es la comisión de red del retiro, en unidades del activo. **Lo
    absorbe el usuario pero va cobrado dentro del precio** (decisión del
    2026-09-03): se compra de más para cubrir el retiro, al cliente le llega
    EXACTO lo cotizado, y la ganancia que sale sigue siendo `margen_pct` ya neto
    del fee. Por eso el precio que se le canta es ARS ÷ lo que LE LLEGA. Nunca
    cotizar sobre el bruto: ese día se prometió 0,00508768 y llegaron 0,00507.
    """
    if ars <= 0:
        raise ValueError("El monto del cliente tiene que ser mayor a cero.")
    if costo_venue <= 0:
        raise ValueError("El costo de reposición tiene que ser mayor a cero.")

    pedido = (asset or "").strip().upper()
    # Precio de referencia sobre lo que SALE de la cuenta propia.
    precio_base = costo_venue * (1 + margen_pct / 100)
    entrega_bruta = ars / precio_base
    entrega = entrega_bruta - max(fee_red, 0.0)
    if entrega <= 0:
        raise ValueError("La comisión de red se come todo lo que hay que entregar.")

    if pedido == "USDT":
        usdt_a_comprar = None
        ars_a_gastar = entrega_bruta * costo_venue
    else:
        if not spot_price or not usdt_price:
            raise ValueError(
                f"Para cotizar {pedido} hace falta el precio del spot "
                f"{pedido}/USDT y el del USDT: la ruta es ARS→USDT→{pedido}.")
        # El fee del spot encarece los USDT que hay que poner para sacar la
        # cantidad de cripto que se le entrega al cliente.
        usdt_a_comprar = entrega_bruta * spot_price * (1 + spot_fee_pct / 100)
        ars_a_gastar = usdt_a_comprar * usdt_price

    ganancia_ars = ars - ars_a_gastar
    # Lo que el cliente paga por unidad RECIBIDA, en pesos y en USDT.
    precio_cliente = ars / entrega
    px_usdt = usdt_price if pedido != "USDT" else costo_venue
    usdt_equivalente = (ars / px_usdt) if px_usdt else None
    # "¿cuánto me salió en USD?" sólo tiene sentido si lo que recibe NO es USDT.
    precio_cliente_usdt = (usdt_equivalente / entrega
                           if usdt_equivalente and pedido != "USDT" else None)
    return {
        "asset": pedido,
        "ars_cliente": ars,
        "precio_base": precio_base,
        "precio_cliente": precio_cliente,
        "precio_cliente_usdt": precio_cliente_usdt,
        "usdt_equivalente": usdt_equivalente,
        "costo_venue": costo_venue,
        "entrega_bruta": entrega_bruta,
        "entrega": entrega,
        "fee_red": fee_red,
        "usdt_a_comprar": usdt_a_comprar,
        "usdt_price": usdt_price,
        "spot_price": spot_price,
        "ars_a_gastar": ars_a_gastar,
        "ganancia_ars": ganancia_ars,
        "ganancia_pct": (ganancia_ars / ars_a_gastar * 100) if ars_a_gastar else 0.0,
    }
