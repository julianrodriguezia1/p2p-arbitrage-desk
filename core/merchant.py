"""Progreso hacia el Comerciante Verificado de Binance P2P (puro, sin red).

Requisitos aportados por el usuario el 2026-08-28 (Argentina) y ratificados
por él el 2026-08-30 como dato bueno: se toman como válidos, no se re-discuten.
De los ocho, acá viven sólo los tres que se pueden medir con `trades.db`:

    · 400 operaciones en los últimos 30 días
    · 0,5 BTC de volumen en los últimos 30 días  ← el que más pesa
    · 1 BTC de volumen histórico

Los otros cinco (antigüedad de cuenta, 98% de finalización, KYC avanzado,
depósito de garantía y tiempo de liberación) el usuario ya los tiene y no se
muestran.

Dos honestidades que el motor mantiene a propósito:
  · el volumen histórico es un **piso**: mide desde la primera operación cargada
    en trades.db, no desde que existe la cuenta de Binance;
  · sin precio de BTC no se estima nada: el requisito queda en FALTA.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.movements import Movement

# Prefijo de `exchange_coin` de las órdenes que cuentan. Cubre "Binance / USDT"
# y "Binance / USDC": las dos son órdenes del P2P de Binance.
BINANCE_PREFIJO = "binance"

# Un número de orden P2P de Binance es un entero de 20 dígitos. Las filas
# cargadas por captura que NO son órdenes del libro —compras de spot
# (`spot-2026...`), ops de cliente (`cliente-carlos-...`, `LUCAS-...`) o ids
# cortos de otra billetera— quedan afuera: Binance no las cuenta para el
# Verificado. Medido el 2026-08-30: eran 21 filas y 8.857 USD de más.
_ORDEN_P2P = re.compile(r"^\d{17,}$")


@dataclass(frozen=True)
class Requisito:
    clave: str            # "ops_30d" | "vol_30d_btc" | "vol_hist_btc"
    etiqueta: str
    valor: float | None   # None = no se pudo medir (FALTA), nunca un estimado
    meta: float
    unidad: str           # "operaciones" | "BTC"
    cumple: bool
    pct: float | None     # avance 0..100 (tope 100); None si no es medible
    nota: str


@dataclass(frozen=True)
class Progreso:
    requisitos: list       # list[Requisito]
    desde: "date | None"   # primera operación de Binance en trades.db
    ventana_dias: int
    btc_usd: float | None


def _es_binance(m: "Movement") -> bool:
    return (m.exchange_coin.strip().lower().startswith(BINANCE_PREFIJO)
            and bool(_ORDEN_P2P.match(str(m.order_id).strip())))


def _es_btc(m: "Movement") -> bool:
    return m.exchange_coin.strip().lower().endswith("btc")


def _usd(m: "Movement", btc_usd: float) -> float:
    """USD de la orden. Las filas de BTC guardan BTC en `usd_gross`, no USD."""
    bruto = float(m.usd_gross)
    return bruto * btc_usd if _es_btc(m) else bruto


def _pct(valor: float, meta: float) -> float:
    if meta <= 0:
        return 100.0
    return min(100.0, valor / meta * 100.0)


def _medido(clave: str, etiqueta: str, valor: float, meta: float,
            unidad: str, nota: str = "") -> Requisito:
    return Requisito(clave=clave, etiqueta=etiqueta, valor=valor, meta=meta,
                     unidad=unidad, cumple=valor >= meta, pct=_pct(valor, meta),
                     nota=nota)


def _falta(clave: str, etiqueta: str, meta: float, unidad: str,
           nota: str) -> Requisito:
    return Requisito(clave=clave, etiqueta=etiqueta, valor=None, meta=meta,
                     unidad=unidad, cumple=False, pct=None, nota=nota)


def progreso(
    movements: list,
    *,
    hoy: date,
    btc_usd: float | None,
    ops_meta: int = 400,
    vol_30d_meta: float = 0.5,
    vol_hist_meta: float = 1.0,
    ventana_dias: int = 30,
) -> Progreso:
    """Los 3 requisitos medibles, con su avance. `movements` es trades.db entero."""
    binance = [m for m in movements if _es_binance(m)]
    corte = hoy - timedelta(days=ventana_dias)
    ventana = [m for m in binance if corte <= m.date <= hoy]

    desde = min((m.date for m in binance), default=None)
    tiene_precio = btc_usd is not None and btc_usd > 0
    precio = float(btc_usd) if tiene_precio else 0.0
    usd_30d = sum(_usd(m, precio) for m in ventana)
    usd_hist = sum(_usd(m, precio) for m in binance)

    nota_hist = "Piso: mide lo cargado en trades.db"
    if desde is not None:
        nota_hist += f" desde el {desde.strftime('%d/%m/%Y')}"
    nota_hist += ". Tu histórico real en Binance puede ser mayor."

    reqs = [_medido("ops_30d", f"Operaciones en {ventana_dias} días",
                    float(len(ventana)), float(ops_meta), "operaciones",
                    "Cuenta sólo lo sincronizado: si operaste y no corriste el "
                    "sync, acá figura de menos.")]

    if not tiene_precio:
        sin_precio = "FALTA: sin precio de BTC no se calcula el volumen."
        reqs.append(_falta("vol_30d_btc", f"Volumen en {ventana_dias} días",
                           vol_30d_meta, "BTC", sin_precio))
        reqs.append(_falta("vol_hist_btc", "Volumen histórico",
                           vol_hist_meta, "BTC", f"{sin_precio} {nota_hist}"))
    else:
        reqs.append(_medido("vol_30d_btc", f"Volumen en {ventana_dias} días",
                            usd_30d / btc_usd, vol_30d_meta, "BTC",
                            f"USD {usd_30d:,.0f} al precio de BTC de ahora."))
        reqs.append(_medido("vol_hist_btc", "Volumen histórico",
                            usd_hist / btc_usd, vol_hist_meta, "BTC",
                            f"USD {usd_hist:,.0f}. {nota_hist}"))

    return Progreso(requisitos=reqs, desde=desde, ventana_dias=ventana_dias,
                    btc_usd=btc_usd)
