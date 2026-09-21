"""Operación de cliente en tandas: ARS del cliente → USDT (P2P) → BTC (spot) → retiro.

Motor puro, sin red. Reproduce el ciclo que se hizo a mano el 2026-09-07
(Daniel, 6.040.000 ARS): el cliente paga de a pedazos, se compra USDT tanda por
tanda, se lleva el promedio real de costo y recién al final se calcula cuánto BTC
le corresponde y a qué precio se le canta.

Reglas que ya están adentro (no rehacerlas afuera):
- El BTC nunca se compra por P2P: siempre ARS → USDT → BTC spot.
- El fee de retiro sale del BTC: se compra de más para que al cliente le llegue
  EXACTO lo cotizado.
- La base del margen es el costo promedio REAL de las compras, no el precio de
  reposición del momento en que se cotizó.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import config

#: Fee de retiro de BTC por exchange, en BTC.
#: Binance: config.BTC_NETWORK_FEE (medido). Bybit: captura del usuario 2026-09-07.
#: Bybit cobra 4x — por eso el BTC se compra y se retira SIEMPRE desde Binance.
FEE_RETIRO_BTC: dict[str, float] = {
    "binance": config.BTC_NETWORK_FEE,
    "bybit": 0.000083,
}

#: Fee de red al mandarle USDT a un cliente, en USDT. TRC20 ronda 1 USDT;
#: por BSC es menos, pero el cliente elige la red que sabe usar.
FEE_RED_USDT: float = 1.0

#: Costo de mover USDT entre exchanges por red BSC/BNB, en USDT.
#: Dato del usuario (2026-09-07): ~0,20 USD, muy por debajo del 0,1% que asume
#: STRATEGY_NETWORK_FEE_PCT para el motor de rutas.
FEE_PUENTE_USDT: float = 0.20


@dataclass(frozen=True)
class Tanda:
    """Una compra de USDT: lo que entró, a qué precio y qué se llevó el venue.

    `fee_usdt` es el flat del tomador, que se cobra por ORDEN: partir una compra
    en cinco avisos de Binance cuesta cinco veces 0,07. La API de Binance
    devuelve `commission: 0` igual, así que este número no sale de ahí sino de
    `config.FEE_P2P_BY_MODE`.
    """

    usdt: float
    price_ars: float
    fee_usdt: float = 0.0

    @property
    def usdt_neto(self) -> float:
        """Los USDT que quedan en la cuenta después del flat."""
        return self.usdt - self.fee_usdt

    @property
    def ars(self) -> float:
        """Los pesos que salieron: el flat se cobra en USDT, no cambia el débito."""
        return self.usdt * self.price_ars


@dataclass(frozen=True)
class PlanBtc:
    """Lo que hay que hacer al cerrar: cuánto BTC sale, cuánto llega, qué se cobra."""

    usdt_para_btc: float
    btc_bruto: float
    btc_al_cliente: float
    precio_cantado: float
    precio_cantado_usdt: float
    ganancia_ars: float
    ganancia_usdt: float


@dataclass(frozen=True)
class PlanUsdt:
    """El cierre cuando el cliente compra USDT: no hay spot ni BTC de por medio."""

    usdt_al_cliente: float
    precio_cantado: float
    ganancia_ars: float
    ganancia_usdt: float


@dataclass
class OpCliente:
    """Una operación de venta de cripto a un cliente que paga en pesos."""

    cliente: str
    ars_cliente: float
    margen_pct: float
    compras: list[Tanda] = field(default_factory=list)
    asset: str = "BTC"

    # --- lo comprado hasta ahora ---

    def usdt_total(self) -> float:
        """Netos de comisión: es lo que hay de verdad en la cuenta."""
        return sum(t.usdt_neto for t in self.compras)

    def ars_gastado(self) -> float:
        return sum(t.ars for t in self.compras)

    def costo_promedio(self) -> float | None:
        """ARS por USDT, promedio ponderado real. None si todavía no compró nada."""
        usdt = self.usdt_total()
        return self.ars_gastado() / usdt if usdt else None

    # --- cuánto falta ---

    def margen_ars(self) -> float:
        return self.ars_cliente * self.margen_pct / 100

    def presupuesto_ars(self) -> float:
        """Los pesos del cliente que se pueden gastar en USDT (el resto es ganancia)."""
        return self.ars_cliente - self.margen_ars()

    def falta_ars(self) -> float:
        return max(0.0, self.presupuesto_ars() - self.ars_gastado())

    def falta_usdt(self, precio_reposicion: float) -> float:
        """Cuántos USDT faltan comprar, al precio ejecutable de ahora."""
        return self.falta_ars() / precio_reposicion

    # --- el cierre ---

    def plan_usdt(self, fee_red_usdt: float = FEE_RED_USDT) -> PlanUsdt:
        """Cuánto USDT le llega al cliente y a qué precio se le canta.

        Sin spot ni BTC: se compra USDT y se le manda. El fee de red sale de los
        USDT del cliente, igual que el de BTC.
        """
        promedio = self.costo_promedio()
        if promedio is None:
            raise ValueError("no hay compras cargadas: falta el costo promedio")
        usdt_al_cliente = self.presupuesto_ars() / promedio - fee_red_usdt
        return PlanUsdt(
            usdt_al_cliente=usdt_al_cliente,
            precio_cantado=self.ars_cliente / usdt_al_cliente,
            ganancia_ars=self.margen_ars(),
            ganancia_usdt=self.usdt_total() - usdt_al_cliente - fee_red_usdt,
        )

    def plan_btc(self, precio_efectivo_btc: float,
                 fee_bridge_usdt: float = FEE_PUENTE_USDT,
                 fee_retiro_btc: float | None = None) -> PlanBtc:
        """Cuánto BTC comprar, cuánto le llega al cliente y a qué precio se le canta.

        `precio_efectivo_btc` es USDT por BTC CON el fee del spot adentro
        (ver `precio_efectivo_spot`). El fee de retiro se suma a la compra para
        que al cliente le llegue exacto lo cotizado.
        """
        promedio = self.costo_promedio()
        if promedio is None:
            raise ValueError("no hay compras cargadas: falta el costo promedio")
        if fee_retiro_btc is None:
            fee_retiro_btc = FEE_RETIRO_BTC["binance"]

        usdt_para_btc = self.presupuesto_ars() / promedio - fee_bridge_usdt
        btc_bruto = usdt_para_btc / precio_efectivo_btc
        btc_al_cliente = btc_bruto - fee_retiro_btc

        precio_cantado = self.ars_cliente / btc_al_cliente
        precio_cantado_usdt = (self.ars_cliente / promedio) / btc_al_cliente

        ganancia_usdt = self.usdt_total() - fee_bridge_usdt - usdt_para_btc
        return PlanBtc(
            usdt_para_btc=usdt_para_btc,
            btc_bruto=btc_bruto,
            btc_al_cliente=btc_al_cliente,
            precio_cantado=precio_cantado,
            precio_cantado_usdt=precio_cantado_usdt,
            ganancia_ars=self.margen_ars(),
            ganancia_usdt=ganancia_usdt,
        )


def precio_efectivo_spot(usdt_gastados: float, btc_bruto: float,
                         comision_btc: float) -> float:
    """USDT por BTC con la comisión del spot adentro (la comisión se cobra EN BTC)."""
    return usdt_gastados / (btc_bruto - comision_btc)
