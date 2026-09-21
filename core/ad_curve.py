"""Qué aviso publico y contra qué lo cierro, por tamaño de ticket. Motor puro.

Dos cosas que dependen del tamaño y por eso viven acá:

1. **El precio de publicación.** Cada aviso del libro declara un mínimo y un
   máximo por orden, así que un rival sólo me compite si su rango contiene mi
   ticket. Al publicar 5.000 USDT se caen los avisos chicos y quedan pocos
   rivales, casi siempre peor posicionados: el precio que puedo poner mejora.

2. **Con qué cierro la otra pata.** Publicar las dos puntas en el mismo venue
   no es una jugada: quedás esperando dos avisos y pagás la comisión de
   publicar dos veces. Lo que se opera es publicar UNA pata y cerrar la otra
   TOMANDO el libro del venue que más convenga, aunque sea otro exchange. De
   ahí sale el neto: una sola comisión de publicar, más el fee de tomador de
   donde cerrás, más el fee de red si hay que mover la cripto.

Contra `core/arb_matrix`, que responde "qué jugada hago tomando el libro", acá
la pregunta es "qué número tipeo en el aviso, y dónde lo cierro".
"""
from dataclasses import dataclass
from decimal import Decimal

from core import pricing
from core.movements import Side


@dataclass(frozen=True)
class Cierre:
    """Un venue donde puedo cerrar la pata contraria TOMANDO su libro.

    `ask` es lo que me sale comprar ahí; `bid`, lo que me pagan por vender.
    Los dos ya vienen calculados por profundidad para el ticket en cuestión:
    este motor no mira orderbooks ajenos.
    """
    venue: str
    ask: float | None
    bid: float | None
    fee_tomando_pct: float = 0.0


@dataclass(frozen=True)
class Nivel:
    """La jugada que me conviene a un tamaño de ticket dado."""
    volume: float                  # tamaño del ticket, en cripto
    ticket_ars: float              # el mismo ticket valuado en ARS
    compra: float | None           # precio a publicar para COMPRAR
    venta: float | None            # precio a publicar para VENDER
    rivales_compra: int            # avisos que me compiten a ese tamaño
    rivales_venta: int
    lado: str | None               # "compra" | "venta": qué aviso publico
    precio: float | None           # el precio de esa pata
    cierre_venue: str | None       # dónde cierro tomando
    cierre_precio: float | None
    neto_pct: float | None         # neto de publicar + tomar + red
    ganancia_ars: float | None     # por el ticket entero, no por 1000


def rivales(ads, ticket_ars: float) -> list[float]:
    """Precios de los avisos que aceptan una orden de ese tamaño.

    Las dos puntas del rango importan: un aviso con máximo chico no puede
    atender mi ticket grande, y uno con mínimo alto no puede atender el chico.
    Un máximo en cero es "sin tope publicado", no un aviso vacío: varios
    fetchers dejan el campo en 0 cuando el exchange no lo devuelve.
    """
    out = []
    for a in ads:
        mx = float(a.max_amount)
        if float(a.min_amount) <= ticket_ars and (mx <= 0 or ticket_ars <= mx):
            out.append(float(a.price))
    return out


def _precio(precios: list[float], side: Side, tick: float,
            floor: float, ceil: float) -> float | None:
    """Un tick mejor que el mejor rival, descartando precios absurdos."""
    p = pricing.competitive_price(
        [Decimal(str(x)) for x in precios], side, Decimal(str(tick)))
    if p is None:
        return None
    p = pricing.apply_circuit_breaker(p, Decimal(str(floor)), Decimal(str(ceil)))
    return float(p) if p is not None else None


def _mejor_cierre(cierres, *, lado: str, publico: float | None, venue: str,
                  maker_pct: float, network_fee_pct: float):
    """El venue de cierre que deja el mejor neto para esa dirección.

    `lado` es lo que PUBLICO. Si publico venta, cierro comprando (uso el `ask`
    del otro y quiero el más barato); si publico compra, cierro vendiendo (uso
    el `bid` y quiero el más caro). El fee de red sólo se paga cuando hay que
    mover la cripto a otro exchange.
    """
    if publico is None or publico <= 0:
        return None
    mejor = None
    for c in cierres:
        precio = c.ask if lado == "venta" else c.bid
        if not precio or precio <= 0:
            continue
        bruto = ((publico - precio) / precio * 100 if lado == "venta"
                 else (precio - publico) / publico * 100)
        red = 0.0 if c.venue == venue else network_fee_pct
        neto = bruto - maker_pct - c.fee_tomando_pct - red
        if mejor is None or neto > mejor[0]:
            mejor = (neto, c.venue, precio)
    return mejor


def nivel(*, ads_buy, ads_sell, volume: float, precio_ref: float, venue: str,
          cierres, tick: float, maker_pct: float, network_fee_pct: float,
          floor: float, ceil: float, puede_compra: bool = True,
          puede_venta: bool = True) -> Nivel:
    """Un tamaño de ticket en un venue.

    `ads_buy` son los avisos donde YO compraría (el "BUY" del fetcher): esos
    son mis rivales cuando publico una VENTA. `ads_sell`, al revés.

    `puede_compra` / `puede_venta` son las habilitaciones para CREAR el aviso.
    El precio de ese lado se sigue mostrando (sirve de referencia), pero la
    jugada no se elige por ahí: no es ejecutable.
    """
    ticket_ars = volume * precio_ref
    r_venta = rivales(ads_buy, ticket_ars)
    r_compra = rivales(ads_sell, ticket_ars)
    venta = _precio(r_venta, Side.VENTA, tick, floor, ceil)
    compra = _precio(r_compra, Side.COMPRA, tick, floor, ceil)

    opciones = []
    for lado, publico, habilitado in (("venta", venta, puede_venta),
                                      ("compra", compra, puede_compra)):
        if not habilitado:
            continue
        m = _mejor_cierre(cierres, lado=lado, publico=publico, venue=venue,
                          maker_pct=maker_pct, network_fee_pct=network_fee_pct)
        if m is not None:
            opciones.append((m[0], lado, publico, m[1], m[2]))

    lado = precio = cierre_venue = cierre_precio = neto = ganancia = None
    if opciones:
        neto, lado, precio, cierre_venue, cierre_precio = max(
            opciones, key=lambda o: o[0])
        # La base es la plata que pongo: comprar el ticket cuesta el precio de
        # cierre cuando publico venta, y el precio publicado cuando publico
        # compra. Sobre eso rinde el neto.
        base = cierre_precio if lado == "venta" else precio
        ganancia = volume * base * neto / 100

    return Nivel(volume=volume, ticket_ars=ticket_ars, compra=compra, venta=venta,
                 rivales_compra=len(r_compra), rivales_venta=len(r_venta),
                 lado=lado, precio=precio, cierre_venue=cierre_venue,
                 cierre_precio=cierre_precio, neto_pct=neto, ganancia_ars=ganancia)


def curva(*, libros: dict, volumes: list[float], precios_ref: dict[str, float],
          maker_pct: dict[str, float], cierres: dict[float, list[Cierre]],
          tick: float, network_fee_pct: float, floor: float, ceil: float,
          puede_compra: dict[str, bool] | None = None,
          puede_venta: dict[str, bool] | None = None) -> dict[str, list[Nivel]]:
    """{venue: [Nivel por cada tamaño]}. Un venue sin referencia se saltea.

    `cierres` viene por tamaño porque el precio ejecutable del venue donde
    cierro también depende del ticket: llenar 5.000 USDT come más avisos del
    libro que llenar 1.000.

    En `puede_compra` / `puede_venta`, ausente = habilitado: sólo se anota lo
    que el exchange todavía tiene bloqueado.
    """
    pub_c = puede_compra or {}
    pub_v = puede_venta or {}
    out: dict[str, list[Nivel]] = {}
    for venue, (ads_buy, ads_sell) in libros.items():
        ref = precios_ref.get(venue)
        if not ref or ref <= 0:
            continue
        out[venue] = [
            nivel(ads_buy=ads_buy, ads_sell=ads_sell, volume=v, precio_ref=ref,
                  venue=venue, cierres=cierres.get(v, []), tick=tick,
                  maker_pct=maker_pct.get(venue, 0.0),
                  network_fee_pct=network_fee_pct, floor=floor, ceil=ceil,
                  puede_compra=pub_c.get(venue, True),
                  puede_venta=pub_v.get(venue, True))
            for v in volumes
        ]
    return out
