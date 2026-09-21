"""Puntas del libro por venue, mejor cruce y vigilancia de los avisos propios.

Motor puro, sin red. Contesta tres cosas que el tablero necesita a la vez:

  1. ¿a qué precio se publica hoy en cada venue, de los dos lados?
  2. ¿cuál es el cruce que más deja, contando makers y fee de red?
  3. mi aviso publicado, ¿sigue siendo la punta o me pasaron?

La (3) sale de un problema real: el 2026-09-11 el usuario dejó una venta
publicada, el libro se corrió y siguió vendiendo al precio viejo.

Dos decisiones que el motor sostiene a propósito:

· **El fee de red se reparte en la TANDA, no en cada operación.** Es un flat
  en USDT por transferencia: se hacen 20 compras de 50 en KuCoin y se pasan
  los 1.000 de una sola vez. Cobrárselo a cada operación mata rutas que en
  realidad dan (corrección del usuario, 2026-09-12).

· **Un precio sin stock detrás no es un precio.** Tanto para la punta (un
  aviso de dos monedas no mueve el mercado) como para el cruce (en KuCoin se
  mueve poco: un precio divino sin contraparte no es una jugada).

Convención de `p2p_scanner.Ad.side`:
  "BUY"  = avisos de gente que te VENDE  → vos comprás (te_venden)
  "SELL" = avisos de gente que te COMPRA → vos vendés  (te_compran)

Y la de acá, que es la del que publica:
  `comprar_publicando` = dónde te ponés para COMPRAR = la mejor oferta de compra
  `vender_publicando`  = dónde te ponés para VENDER  = el aviso de venta más barato
"""
from __future__ import annotations

from dataclasses import dataclass

from core.p2p_depth import filter_traps

# Stock mínimo acumulado (USDT) para que un precio cuente como punta del libro.
# Un aviso solo con dos monedas es un anzuelo, no un precio: el 2026-09-10 uno a
# 1.580,56 arrastró el precio de venta publicado 5 ARS abajo del mercado.
PUNTA_STOCK_MIN_USDT = 100.0

LADOS = ("compra", "venta")

# El venue cuyas órdenes cuentan para el Comerciante Verificado.
BINANCE = "binancep2p"


@dataclass(frozen=True)
class Punta:
    venue: str
    comprar_publicando: float | None
    vender_publicando: float | None
    ancho_pct: float | None
    stock_compra: float   # USDT ofrecidos del lado donde vos vendés
    stock_venta: float    # USDT ofrecidos del lado donde vos comprás


@dataclass(frozen=True)
class Cruce:
    comprar_en: str
    vender_en: str
    comprar_a: float
    vender_a: float
    neto_ars_por_usdt: float
    neto_pct: float
    cross_venue: bool
    patas_binance: int = 0   # cuántas de las dos patas son órdenes del P2P de Binance


@dataclass(frozen=True)
class EstadoAviso:
    venue: str
    lado: str                      # "compra" | "venta"
    mi_precio: float
    punta: float | None
    estado: str                    # "punta" | "pasado" | "regalando" | "sin_dato"
    diferencia_ars: float | None   # cuánto te separa de la punta, en ARS por USDT
    sugerido: float | None         # a cuánto ponerte para volver a la punta


def punta_de_libro(ads: list, mas_caro: bool,
                   stock_min: float = PUNTA_STOCK_MIN_USDT) -> float | None:
    """Precio de punta con stock real detrás: recorre el libro desde el mejor
    precio y devuelve el primero donde el stock acumulado llega a `stock_min`."""
    limpios = [a for a in filter_traps(list(ads)) if a.price > 0]
    if not limpios:
        return None
    limpios.sort(key=lambda a: a.price, reverse=mas_caro)
    acum = 0.0
    for a in limpios:
        acum += float(a.available or 0)
        if acum >= stock_min:
            return float(a.price)
    return float(limpios[-1].price)


def _stock(ads: list) -> float:
    return sum(float(a.available or 0) for a in filter_traps(list(ads)))


def sin_mios(ads: list, excluir=()) -> list:
    """Saca del libro los avisos propios (por apodo, sin distinguir mayúsculas).

    Mi aviso publicado aparece en el libro público: si cuenta como punta, el
    vigilante se compara contra sí mismo y siempre dice "sos la punta" (bug
    visto el 2026-09-13 con MiApodoP2P primero en Binance y Bybit)."""
    nicks = {n.strip().lower() for n in excluir if n and n.strip()}
    if not nicks:
        return list(ads)
    return [a for a in ads if (getattr(a, "merchant", "") or "").strip().lower() not in nicks]


def precio_propio(ads: list, nicks=(), mas_caro: bool = False) -> float | None:
    """El precio de MI aviso, leído del libro por apodo. None si no aparece.

    El precio tipeado en el tablero no sirve: el 2026-09-13 decía 1.597 (el del
    rival, congelado al elegir el lado) y el aviso real estaba en 1.599, así que
    marcaba "sos la punta" estando pasado. Con varios avisos propios del mismo
    lado vale el mejor (el que más paga comprando, el más barato vendiendo)."""
    todos = [a for a in ads if a.price > 0]
    otros = {id(a) for a in sin_mios(todos, nicks)}
    mios = [a.price for a in todos if id(a) not in otros]
    if not mios:
        return None
    return float(max(mios) if mas_caro else min(mios))


def puntas_de(libros: dict[str, dict[str, list]],
              stock_min: float = PUNTA_STOCK_MIN_USDT,
              excluir=()) -> list[Punta]:
    """Una `Punta` por venue. `libros` = {venue: {"te_venden": [...], "te_compran": [...]}}.
    `excluir` = apodos propios: la punta es la de la competencia."""
    out: list[Punta] = []
    for venue, libro in libros.items():
        te_venden = sin_mios(libro.get("te_venden") or [], excluir)
        te_compran = sin_mios(libro.get("te_compran") or [], excluir)
        vender = punta_de_libro(te_venden, mas_caro=False, stock_min=stock_min)
        comprar = punta_de_libro(te_compran, mas_caro=True, stock_min=stock_min)
        ancho = None
        if vender is not None and comprar is not None and vender > 0:
            ancho = (vender - comprar) / vender * 100.0
        out.append(Punta(venue=venue, comprar_publicando=comprar,
                         vender_publicando=vender, ancho_pct=ancho,
                         stock_compra=_stock(te_compran),
                         stock_venta=_stock(te_venden)))
    return out


def mejor_cruce(puntas: list[Punta], *, maker_pct: dict[str, float],
                fee_red_usdt: dict[str, float], tanda_usdt: float,
                stock_min_usdt: float = 0.0) -> Cruce | None:
    """El cruce que más deja por USDT, neto de makers y del fee de red.

    `tanda_usdt` es el tamaño de la transferencia entre venues, no el de la
    operación: el flat de red se divide por ahí. Dentro del mismo venue no se
    mueve nada, así que no paga red.
    """
    candidatos = [c for c in _cruces(puntas, maker_pct, fee_red_usdt,
                                     tanda_usdt, stock_min_usdt)]
    if not candidatos:
        return None
    return max(candidatos, key=lambda c: c.neto_ars_por_usdt)


def ranking_cruces(puntas: list[Punta], *, maker_pct: dict[str, float],
                   fee_red_usdt: dict[str, float], tanda_usdt: float,
                   stock_min_usdt: float = 0.0,
                   priorizar: str | None = None) -> list[Cruce]:
    """Todos los cruces posibles, del que más deja al que menos.

    Con `priorizar` (normalmente "binancep2p"), los que tocan ese venue van
    primero aunque dejen menos: mientras se persigue el Comerciante Verificado,
    una ruta que no pasa por Binance no suma ninguna operación, así que el mejor
    porcentaje del tablero no es la mejor jugada. Los otros no se esconden:
    quedan abajo, para verlos.
    """
    cs = list(_cruces(puntas, maker_pct, fee_red_usdt, tanda_usdt, stock_min_usdt))
    if priorizar:
        return sorted(cs, key=lambda c: (_toca(c, priorizar), c.neto_ars_por_usdt),
                      reverse=True)
    return sorted(cs, key=lambda c: c.neto_ars_por_usdt, reverse=True)


def _toca(c: Cruce, venue: str) -> bool:
    return venue in (c.comprar_en, c.vender_en)


def _cruces(puntas, maker_pct, fee_red_usdt, tanda_usdt, stock_min_usdt):
    compras = [p for p in puntas if p.comprar_publicando
               and p.stock_compra >= stock_min_usdt]
    ventas = [p for p in puntas if p.vender_publicando
              and p.stock_venta >= stock_min_usdt]
    for pc in compras:
        for pv in ventas:
            compro_a = float(pc.comprar_publicando)
            vendo_a = float(pv.vender_publicando)
            cross = pc.venue != pv.venue
            neto = vendo_a - compro_a
            neto -= maker_pct.get(pc.venue, 0.0) / 100.0 * compro_a
            neto -= maker_pct.get(pv.venue, 0.0) / 100.0 * vendo_a
            if cross and tanda_usdt > 0:
                flat = fee_red_usdt.get(pc.venue, max(fee_red_usdt.values(), default=0.0))
                neto -= flat * vendo_a / tanda_usdt
            yield Cruce(comprar_en=pc.venue, vender_en=pv.venue,
                        comprar_a=compro_a, vender_a=vendo_a,
                        neto_ars_por_usdt=neto,
                        neto_pct=neto / compro_a * 100.0 if compro_a else 0.0,
                        cross_venue=cross,
                        patas_binance=(pc.venue == BINANCE) + (pv.venue == BINANCE))


def estado_aviso(*, mi_precio: float, lado: str, punta: float | None,
                 venue: str = "", tolerancia: float = 0.0) -> EstadoAviso:
    """Mi aviso publicado contra la punta del libro de ahora.

    Avisa en los DOS sentidos, que es lo que importa:

    · **pasado** — te ganaron la posición: alguien vende más barato que vos, o
      paga más que vos. Te dejaron de ver.
    · **regalando** — el libro se corrió a tu favor y vos seguís en el precio
      viejo: vendiendo más barato de lo que hace falta, o pagando de más. Es el
      caso que costó plata el 2026-09-12 (publicó vender a 1.594, el libro se fue
      a 1.596) y el que el tablero se callaba, porque técnicamente seguía siendo
      la punta.

    `tolerancia` en ARS: por debajo de esa diferencia no se avisa nada, para que
    no suene por un centavo cada 30 segundos.
    """
    if lado not in LADOS:
        raise ValueError(f"lado inválido: {lado!r}; esperaba {LADOS}")
    if not mi_precio or mi_precio <= 0 or punta is None:
        return EstadoAviso(venue=venue, lado=lado, mi_precio=mi_precio, punta=punta,
                           estado="sin_dato", diferencia_ars=None, sugerido=None)
    dif = abs(mi_precio - punta)
    if dif <= tolerancia:
        return EstadoAviso(venue=venue, lado=lado, mi_precio=mi_precio, punta=punta,
                           estado="punta", diferencia_ars=0.0, sugerido=None)
    pasado = punta < mi_precio if lado == "venta" else punta > mi_precio
    return EstadoAviso(venue=venue, lado=lado, mi_precio=mi_precio, punta=punta,
                       estado="pasado" if pasado else "regalando",
                       diferencia_ars=dif, sugerido=punta)
