"""Ops de cliente en criollo: texto libre → movimiento OTC. Puro, sin red.

Este módulo NO importa requests ni telegram: se testea entero sin mocks de HTTP.
Toda la I/O vive en bot/cliente_ops.py y cli/push_movement.py."""
from __future__ import annotations

import re
import unicodedata
from datetime import date as _date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from core.capture_parser import parse_number


def normalize(s: str | None) -> str:
    """Minúsculas, sin acentos, espacios colapsados. Para comparar nombres."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return " ".join(s.lower().split())


def _searchable(c: dict) -> list[str]:
    """Nombre y alias del cliente, normalizados (descarta los vacíos)."""
    return [n for n in (normalize(c.get("name")), normalize(c.get("alias"))) if n]


def resolve_client(name: str | None, clients: list[dict]) -> tuple[dict | None, list[dict]]:
    """Busca el cliente por nombre o alias, en tres pasadas: exacto → prefijo →
    substring. La primera pasada que da resultados manda.

    Devuelve (cliente, []) si hay uno solo, (None, candidatos) si hay varios y
    (None, []) si no hay ninguno."""
    n = normalize(name)
    if not n:
        return None, []
    pasadas = (
        lambda a, b: a == b,
        lambda a, b: b.startswith(a),
        lambda a, b: a in b,
    )
    for coincide in pasadas:
        hits = [c for c in clients if any(coincide(n, x) for x in _searchable(c))]
        if len(hits) == 1:
            return hits[0], []
        if len(hits) > 1:
            return None, hits
    return None, []


_ARS_Q = Decimal("0.01")        # 2 decimales para ARS
_USDT_Q = Decimal("0.000001")   # 6 decimales para USDT

PRICE_MIN = Decimal("100")      # circuit breaker: abajo de esto es dedo gordo
PRICE_MAX = Decimal("10000")
MAX_DAYS_BACK = 60              # una op más vieja que esto se repregunta
MARKET_TOL = Decimal("0.05")    # 5% de diferencia con el mercado → aviso

# "vendi" es desde la perspectiva del usuario: él le vendió USDT al cliente.
_SIDES = {"vendi": "VENTA", "venta": "VENTA",
          "compre": "COMPRA", "compra": "COMPRA"}

MISSING_QUESTIONS = {
    "lado": "¿Se la vendiste o se la compraste?",
    "monto": "¿Cuántos USDT?",
    "precio": "¿A qué precio?",
    "fecha": "¿Qué día fue? (hoy, ayer, o 2026-08-10)?",
    "banco": "¿Por dónde te pagó? (ej. Uala, Mercado Pago)?",
}

# '1.578.000' → solo separador de miles. En una captura no aparece (siempre
# vienen con decimales) pero escrito a mano es lo más común.
_SOLO_MILES = re.compile(r"^-?\d{1,3}(\.\d{3})+$")


def parse_amount(value) -> Decimal | None:
    """Número en criollo → Decimal, o None si es ilegible."""
    if isinstance(value, str):
        limpio = re.sub(r"[^0-9.,-]", "", value)
        if _SOLO_MILES.match(limpio):
            return Decimal(limpio.replace(".", ""))
    return parse_number(value)


def _slug(name: str) -> str:
    """'Martín Pérez' → 'danielperez' (para el order_id)."""
    return re.sub(r"[^a-z0-9]", "", normalize(name))


def _next_order_id(slug: str, day: _date, existing: set[str]) -> str:
    """man-daniel-20260812, y -2/-3/... si ya hay ops de ese cliente ese día."""
    base = f"man-{slug}-{day:%Y%m%d}"
    if base not in existing:
        return base
    n = 2
    while f"{base}-{n}" in existing:
        n += 1
    return f"{base}-{n}"


def _parse_day(value, today: _date) -> _date | None:
    """ISO o vacío (= hoy). None si es ilegible, futura o de hace mucho."""
    if value in (None, ""):
        return today
    try:
        day = _date.fromisoformat(str(value).strip())
    except ValueError:
        return None
    if day > today or (today - day).days > MAX_DAYS_BACK:
        return None
    return day


def _default_bank(movements: list[dict]) -> str:
    """El método de pago de la última op del cliente ('' si no tiene ops)."""
    if not movements:
        return ""
    last = max(movements, key=lambda m: str(m.get("date") or ""))
    return str(last.get("bank") or "")


def build_client_movement(
    params: dict,
    client: dict,
    client_movements: list[dict],
    today: _date,
    market_price=None,
) -> tuple[dict | None, str | None, list[str]]:
    """Arma el JSON de /api/movement para una op con un cliente.

    Devuelve (movimiento, campo_faltante, warnings). Cuando falta un dato,
    movimiento es None y campo_faltante dice cuál preguntar — de a uno por vez,
    en el orden lado → monto → precio → fecha → banco."""
    side = _SIDES.get(normalize(params.get("lado")))
    if side is None:
        return None, "lado", []

    monto = parse_amount(params.get("monto"))
    if monto is None or monto <= 0:
        return None, "monto", []

    price = parse_amount(params.get("precio"))
    if price is None or not (PRICE_MIN <= price <= PRICE_MAX):
        return None, "precio", []

    day = _parse_day(params.get("fecha"), today)
    if day is None:
        return None, "fecha", []

    bank = str(params.get("banco") or "").strip() or _default_bank(client_movements)
    if not bank:
        return None, "banco", []

    # Un número suelto son USDT; solo cuenta como ARS si el mensaje lo dijo.
    if normalize(params.get("unidad")) == "ars":
        total = monto
        usd = (monto / price).quantize(_USDT_Q, ROUND_HALF_UP)
    else:
        usd = monto
        total = (monto * price).quantize(_ARS_Q, ROUND_HALF_UP)

    warnings: list[str] = []
    market = parse_amount(market_price)
    if market and market > 0 and abs(price - market) / market > MARKET_TOL:
        warnings.append(f"mercado ahora ~{market}")

    existing = {str(m.get("opId") or m.get("id") or "") for m in client_movements}
    movement = {
        "side": side,
        "date": day.isoformat(),
        "order_id": _next_order_id(_slug(client.get("name", "")), day, existing),
        "usd_gross": str(usd),
        "commission": "0",
        "usd_net": str(usd),
        "price": str(price),
        "total_ars": str(total),
        "exchange_coin": "OTC / USDT",
        "bank": bank,
    }
    return movement, None, warnings


# Un banco es un nombre corto ("Uala", "Mercado Pago"), no una frase. El tope
# es lo que evita que "che mejor decime el spread" quede cargado como método
# de pago cuando el usuario cambió de tema en vez de contestar.
_BANK_MAX_CHARS = 25
_BANK_MAX_WORDS = 3

_PESOS_HINTS = ("peso", "ars", "palo", "luca")


def apply_answer(params: dict, missing: str, text: str, today: _date) -> dict | None:
    """Mete la respuesta del usuario en el slot que faltaba.

    Devuelve los params actualizados, o None si el texto no sirve como
    respuesta — ahí el bot descarta la carga a medias y clasifica el mensaje
    de cero, así nunca queda trabado en una conversación."""
    t = (text or "").strip()
    nuevo = dict(params)

    if missing in ("monto", "precio"):
        valor = parse_amount(t)
        if valor is None or valor <= 0:
            return None
        nuevo[missing] = str(valor)
        if missing == "monto":
            n = normalize(t)
            nuevo["unidad"] = "ars" if any(h in n for h in _PESOS_HINTS) else "usdt"
        return nuevo

    if missing == "lado":
        n = normalize(t)
        if "ven" in n:
            nuevo["lado"] = "vendi"
        elif "compr" in n:
            nuevo["lado"] = "compre"
        else:
            return None
        return nuevo

    if missing == "fecha":
        n = normalize(t)
        if n == "hoy":
            nuevo["fecha"] = today.isoformat()
        elif n == "ayer":
            nuevo["fecha"] = (today - timedelta(days=1)).isoformat()
        else:
            try:
                nuevo["fecha"] = _date.fromisoformat(t).isoformat()
            except ValueError:
                return None
        return nuevo

    if missing == "banco":
        if not t or len(t) > _BANK_MAX_CHARS or len(t.split()) > _BANK_MAX_WORDS:
            return None
        nuevo["banco"] = t
        return nuevo

    return None
