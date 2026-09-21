"""Buscador de rutas: todos los ciclos ARS → … → ARS que dejan plata.

Matemática pura, sin red. La idea es no casarse con ninguna jugada conocida sino
armar el **grafo completo** de lo que se puede hacer —tomar, publicar, convertir
en spot, transferir entre venues— y dejar que la búsqueda encuentre los ciclos
rentables, incluidos los que a nadie se le ocurrieron.

Modelo:

- Los **pesos son un solo nodo** (`ARS`). Es plata en el banco: se mueve entre
  venues gratis y al instante. Por eso una ruta puede comprar en un venue y
  vender en otro **sin pagar fee de red**, siempre que ya tengas saldo de los dos
  lados (el "pre-fondear" de [[project_merchant_verificado]]).
- La **cripto es un nodo por venue** (`USDT@binance`, `BTC@bybit`): moverla entre
  venues cuesta fee de red y tiempo, y eso es una arista aparte.

Cada arista lleva una tasa (cuántas unidades del destino te dan por una del
origen) y su comisión. La ganancia del ciclo es el producto de las tasas netas:

    neto = Π (rate_i · (1 − fee_i)) − 1

El umbral a vencer nunca es 0: es la suma de todos los fees del ciclo.

Las rutas no se rankean sólo por el número. Cada una carga su perfil de riesgo:
cuántas patas dependen de que **te tomen** el aviso (`publica_n`), cuántas
**transferencias de red** necesita (`red_n`), y cuál es el **libro más flaco** que
pisa (`min_avisos`). Una ruta vale lo que su pata más débil: ver
[[reference_btc_ars_p2p_iliquido]].
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Avisos vivos mínimos para creerle a una punta. Mismo criterio que
# core.prima_alt.MIN_COMPETIDORES: con menos que esto el precio no es de mercado,
# es lo que nadie disputó.
MIN_AVISOS = 5


@dataclass(frozen=True)
class Paso:
    """Una operación: te lleva de un nodo a otro a una tasa, pagando un fee."""
    origen: str
    destino: str
    rate: float          # unidades de destino por unidad de origen, antes del fee
    fee_pct: float = 0.0
    tipo: str = "tomar"  # "tomar" | "publicar" | "spot" | "red"
    venue: str = ""
    publica: bool = False   # depende de que alguien te tome el aviso
    red: bool = False       # mueve cripto entre venues (tiempo + fee)
    avisos: int | None = None   # profundidad del libro detrás de esta punta
    asset: str = ""      # activo que se mueve en esta pata
    lado: str = ""       # "ask" | "bid": qué punta del libro consume
    detalle: str = ""

    @property
    def rate_neta(self) -> float:
        return self.rate * (1 - self.fee_pct / 100)


@dataclass(frozen=True)
class Ruta:
    """Un ciclo cerrado que arranca y termina en el mismo nodo."""
    pasos: list[Paso] = field(default_factory=list)
    neto_pct: float = 0.0
    publica_n: int = 0
    red_n: int = 0
    min_avisos: int | None = None
    creible: bool | None = None

    @property
    def nodos(self) -> list[str]:
        return ([self.pasos[0].origen] + [s.destino for s in self.pasos]
                if self.pasos else [])


def neto_pct(pasos: list[Paso]) -> float:
    """Ganancia del ciclo en %, ya neta de todas las comisiones."""
    if not pasos:
        return 0.0
    prod = 1.0
    for s in pasos:
        prod *= s.rate_neta
    return (prod - 1) * 100


def _armar_ruta(pasos: list[Paso]) -> Ruta:
    conteos = [s.avisos for s in pasos if s.avisos is not None]
    min_avisos = min(conteos) if conteos else None
    return Ruta(
        pasos=list(pasos),
        neto_pct=neto_pct(pasos),
        publica_n=sum(1 for s in pasos if s.publica),
        red_n=sum(1 for s in pasos if s.red),
        min_avisos=min_avisos,
        creible=None if min_avisos is None else min_avisos >= MIN_AVISOS,
    )


def cuello_usd_h(ruta: Ruta, flujo: dict[tuple[str, str], float]) -> float | None:
    """USD por hora que realmente pasan por la pata publicada más flaca.

    Es el número que convierte un porcentaje en plata. Publicar depende de que
    alguien te tome: si por esa punta del libro no pasa nadie, el neto por vuelta
    da igual porque no hay vueltas. Las patas que sólo TOMÁS no limitan el ritmo
    (no esperás a nadie), así que no entran.

    Devuelve None si alguna pata publicada no tiene flujo medido: no se inventa.
    """
    caudales = []
    for s in ruta.pasos:
        if not s.publica:
            continue
        v = flujo.get((s.asset, s.lado))
        if v is None:
            return None
        caudales.append(v)
    return min(caudales) if caudales else None


def ganancia_ars_h(ruta: Ruta, flujo: dict[tuple[str, str], float],
                   fx_ars_usd: float) -> float | None:
    """Pesos por hora que deja la ruta, limitada por su cuello de botella."""
    cuello = cuello_usd_h(ruta, flujo)
    if cuello is None:
        return None
    return cuello * ruta.neto_pct / 100 * fx_ars_usd


def buscar(pasos: list[Paso], *, inicio: str = "ARS", max_pasos: int = 4,
           solo_creibles: bool = False,
           min_neto_pct: float = 0.0) -> list[Ruta]:
    """Todos los ciclos que arrancan y vuelven a `inicio` dejando ganancia.

    No repite nodos intermedios (si no, `A→B→A→B…` no termina nunca). Devuelve
    ordenado de mayor a menor neto. Con `solo_creibles`, descarta las rutas que
    pisan un libro sin competencia — lo NO medido no se filtra: se desconoce, no
    se inventa.
    """
    salidas: dict[str, list[Paso]] = {}
    for s in pasos:
        salidas.setdefault(s.origen, []).append(s)

    rutas: list[Ruta] = []

    def caminar(nodo: str, camino: list[Paso], visitados: set[str]) -> None:
        if len(camino) >= max_pasos:
            return
        for s in salidas.get(nodo, []):
            if s.destino == inicio:
                if camino:                       # un ciclo necesita al menos 2 patas
                    r = _armar_ruta(camino + [s])
                    if r.neto_pct > min_neto_pct:
                        rutas.append(r)
                continue
            if s.destino in visitados:
                continue
            caminar(s.destino, camino + [s], visitados | {s.destino})

    caminar(inicio, [], {inicio})
    if solo_creibles:
        rutas = [r for r in rutas if r.creible is not False]
    return sorted(rutas, key=lambda r: r.neto_pct, reverse=True)
