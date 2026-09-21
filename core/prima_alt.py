"""La prima que paga en ARS todo lo que NO es stablecoin, y la jugada que la
cobra. Matemática pura, sin red.

Hallazgo que originó el módulo (medido 2026-08-22, Binance P2P ARS): el libro de
USDT tiene un ancho de 0,18% y el de BTC 1,60%. Esa diferencia NO es un arbitraje
que se tome cruzando las dos puntas —comprar BTC y venderlo al toque pierde
plata— sino una **prima de conveniencia**: el que quiere BTC contra pesos paga
~1,2% más que el que compra USDT, mientras que el que vende BTC cobra casi lo
mismo que vendiendo USDT.

La forma de cobrarla es ser el que PUBLICA la venta, fondeándose por el mercado
líquido:

    ARS --(tomo P2P, USDT)--> USDT --(spot 0,1%)--> ACTIVO --(publico)--> ARS

Nomenclatura, igual que core.arb_matrix: `ask` = punta a la que TE VENDEN (comprás
tomando / vendés publicando); `bid` = punta a la que TE COMPRAN.

Todo se expresa en **fx = ARS por dólar implícito**, que es lo que hace
comparables un BTC de 123 millones y un USDT de 1.588.
"""
from __future__ import annotations

from dataclasses import dataclass


# Avisos vivos mínimos para creerle el precio a una punta. Con menos que esto el
# libro no tiene quien lo dispute y la "prima" es sólo un precio de fantasía.
MIN_COMPETIDORES = 5


def implied_fx(price_ars: float, usd_price: float) -> float:
    """ARS por dólar implícito en un precio en pesos. `usd_price` es lo que vale
    una unidad del activo en USD (1.0 para las stablecoins)."""
    if usd_price <= 0:
        raise ValueError(f"usd_price debe ser > 0, vino {usd_price!r}")
    return price_ars / usd_price


def _fx_opt(price_ars: float | None, usd_price: float) -> float | None:
    return None if not price_ars or price_ars <= 0 else implied_fx(price_ars, usd_price)


@dataclass(frozen=True)
class Prima:
    """Cuánto más caro/barato sale un activo que el USDT, en el mismo venue."""
    asset: str
    venue: str
    ask_fx: float | None
    bid_fx: float | None
    prima_ask_pct: float | None   # >0 = comprarlo sale más caro que comprar USDT
    prima_bid_pct: float | None   # <0 = venderlo rinde menos que vender USDT
    ancho_pct: float | None       # ask vs bid del propio activo


def prima(asset: str, venue: str, *, ask_ars: float | None, bid_ars: float | None,
          usd_price: float, usdt_ask: float, usdt_bid: float) -> Prima:
    """Compara las dos puntas del activo contra las del USDT del mismo venue."""
    if usdt_ask <= 0 or usdt_bid <= 0:
        raise ValueError("las puntas del USDT tienen que ser > 0")
    ask_fx = _fx_opt(ask_ars, usd_price)
    bid_fx = _fx_opt(bid_ars, usd_price)
    return Prima(
        asset=asset, venue=venue, ask_fx=ask_fx, bid_fx=bid_fx,
        prima_ask_pct=None if ask_fx is None else (ask_fx / usdt_ask - 1) * 100,
        prima_bid_pct=None if bid_fx is None else (bid_fx / usdt_bid - 1) * 100,
        ancho_pct=None if (ask_fx is None or bid_fx is None)
                  else (ask_fx / bid_fx - 1) * 100,
    )


@dataclass(frozen=True)
class JugadaPublicar:
    """Fondearse en USDT y publicar la venta del activo, cobrando la prima."""
    asset: str
    venue: str
    costo_fx: float       # lo que me sale el dólar ya convertido al activo
    vender_fx: float      # el fx al que publico
    bruto_pct: float
    neto_pct: float       # descontado el maker del venue
    vol_p90_pct: float | None   # cuánto se mueve el activo mientras dura la orden
    cobertura: float | None     # neto / volatilidad; <1 = el ruido se come el margen
    competidores: int | None    # avisos vivos en la punta que voy a disputar
    creible: bool | None        # False = la prima es enorme porque no hay libro


def jugada_publicar(asset: str, venue: str, *, ask_fx: float, usdt_ask_fx: float,
                    maker_pct: float, spot_fee_pct: float,
                    undercut_pct: float = 0.0,
                    vol_p90_pct: float | None = None,
                    competidores: int | None = None) -> JugadaPublicar:
    """Margen de publicar la venta de `asset` fondeándose con USDT tomado.

    `undercut_pct` es cuánto me paro por debajo del mejor ask para quedar primero
    en el libro: sale de mi margen, así que se descuenta del precio de venta.

    `competidores` son los avisos vivos en esa punta. Un libro con menos de
    MIN_COMPETIDORES no sostiene su propia prima: el precio alto no es lo que
    alguien paga, es lo que nadie disputó. Ver memoria
    reference_btc_ars_p2p_iliquido — el 21/08 el 15% de ancho de OKX se leyó como
    jugada y costó plata.
    """
    if ask_fx <= 0 or usdt_ask_fx <= 0:
        raise ValueError("los fx tienen que ser > 0")
    costo_fx = usdt_ask_fx * (1 + spot_fee_pct / 100)
    vender_fx = ask_fx * (1 - undercut_pct / 100)
    bruto = (vender_fx / costo_fx - 1) * 100
    neto = bruto - maker_pct
    cobertura = None
    if vol_p90_pct and vol_p90_pct > 0:
        cobertura = neto / vol_p90_pct
    creible = None if competidores is None else competidores >= MIN_COMPETIDORES
    return JugadaPublicar(
        asset=asset, venue=venue, costo_fx=costo_fx, vender_fx=vender_fx,
        bruto_pct=bruto, neto_pct=neto,
        vol_p90_pct=vol_p90_pct, cobertura=cobertura,
        competidores=competidores, creible=creible,
    )


def rankear(jugadas: list[JugadaPublicar], *,
            min_cobertura: float | None = None,
            solo_creibles: bool = False) -> list[JugadaPublicar]:
    """Las que dejan plata, de mayor a menor neto.

    `min_cobertura` saca las que no aguantan el movimiento del activo durante la
    orden; `solo_creibles` saca las que sostienen su prima en un libro vacío. En
    los dos casos, lo NO medido no se filtra: se desconoce, no se inventa.
    """
    out = [j for j in jugadas if j.neto_pct > 0]
    if min_cobertura is not None:
        out = [j for j in out if j.cobertura is None or j.cobertura >= min_cobertura]
    if solo_creibles:
        out = [j for j in out if j.creible is not False]
    return sorted(out, key=lambda j: j.neto_pct, reverse=True)
