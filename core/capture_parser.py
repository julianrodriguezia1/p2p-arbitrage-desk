"""Captura P2P → movimiento. El modelo LEE (extract_fields, Task 2); Python
CALCULA (build_movement, acá)."""
from __future__ import annotations

import base64
import json
import logging
import re
import tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import requests

_log = logging.getLogger(__name__)

# Tolerancia del chequeo cruzado gross*price vs total_ars. 1,5% para no saltar
# por la comisión de Lemon (que mete ~1% de diferencia legítima).
_CROSS_CHECK_TOL = Decimal("0.015")

_USDT_Q = Decimal("0.000001")   # 6 decimales para montos USDT
_ARS_Q = Decimal("0.01")        # 2 decimales para ARS

_DISPLAY = {
    "lemon": "Lemon", "saldoar": "SaldoAr", "bybit": "Bybit",
    "binance": "Binance", "okx": "OKX", "bitget": "Bitget",
    "kucoin": "KuCoin",
}


def _dec(value) -> Decimal | None:
    """Normaliza un número crudo del modelo a Decimal. Acepta int/float y strings
    tal como los ve el modelo: formato argentino ('95.013,02'), punto decimal
    ('1556.50') y con unidad/símbolo ('95.013,02 ARS', '$1.234,56', '64,590770 USDT').
    Devuelve None ante None, vacío o algo ilegible (→ el llamador lo marca como
    warning en vez de romper)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    # Dejar solo dígitos, separadores y signo (saca 'ARS'/'USDT'/'$'/espacios/texto).
    s = re.sub(r"[^0-9.,-]", "", str(value))
    if not any(ch.isdigit() for ch in s):
        return None
    if "," in s and "." in s:          # AR: '95.013,02' -> '95013.02'
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # '1556,50' -> '1556.50'
        s = s.replace(",", ".")
    elif s.count(".") > 1:             # '1.234.567': todos son de miles
        s = s.replace(".", "")
    elif "." in s:
        # Un solo punto y ninguna coma: ambiguo. Con EXACTAMENTE tres dígitos
        # detrás es el punto de miles argentino ('350.000' son trescientos
        # cincuenta mil), salvo que la parte entera sea 0 — ahí es un monto de
        # BTC ('0.048'). El 08/09/2026 leer '350.000' como 350 rechazó tres
        # veces una captura de KuCoin que estaba perfecta.
        entera, _, dec = s.partition(".")
        if len(dec) == 3 and entera.lstrip("-") not in ("", "0"):
            s = entera + dec
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


# Alias público: el mismo parser de números en formato argentino lo usa
# core/client_ops para leer los montos que el usuario escribe a mano.
parse_number = _dec


def _venue_key(exchange: str | None) -> str:
    e = (exchange or "").lower().replace(" ", "")
    if "lemon" in e:
        return "lemon"
    if "saldo" in e:
        return "saldoar"
    if "bybit" in e:
        return "bybit"
    if "binance" in e:
        return "binance"
    if "okx" in e or "okex" in e:
        return "okx"
    if "bitget" in e:
        return "bitget"
    if "kucoin" in e or "kucon" in e:
        return "kucoin"
    return "otro"


def _side(raw_side: str | None) -> str:
    s = (raw_side or "").lower()
    if s.startswith("vent") or "sell" in s or "vend" in s:
        return "VENTA"
    return "COMPRA"


def _str(d: Decimal | None) -> str:
    # str() directo: preserva la escala del Decimal (trailing zeros de una resta,
    # p. ej. 64.590770). No usar normalize() (la comería → 64.59077).
    return "" if d is None else str(d)


def needs_exchange(raw: dict, warnings: list[str]) -> bool:
    """True cuando el exchange quedó ambiguo y hay que preguntárselo al usuario:
    o no se reconoció (``_venue_key`` == 'otro'), o saltó el aviso de "verificá
    el exchange" (el caso 'Lemon' que en realidad era el método de pago)."""
    if _venue_key(raw.get("exchange")) == "otro":
        return True
    return any("exchange" in w.lower() and "verific" in w.lower() for w in warnings)


def build_movement(raw: dict) -> tuple[dict | None, list[str]]:
    """Aplica la regla del venue y arma el JSON de /api/movement.

    Devuelve (movement_dict, warnings). movement_dict is None cuando no se debe
    cargar (p. ej. una pata de Lemon: hay que mandar la pantalla total)."""
    warnings: list[str] = []
    key = _venue_key(raw.get("exchange"))
    side = _side(raw.get("side"))
    coin = (raw.get("coin") or "USDT").upper()
    display = _DISPLAY.get(key, str(raw.get("exchange") or "?").strip().title())

    # "Lemon Cash" es a la vez el exchange Lemon y un método de pago que aparece
    # en Bybit/OKX/etc. La señal REAL de una op de Lemon son sus campos propios;
    # si dice "lemon" pero no están (y sí los normales), es solo el método de
    # pago → tratar como P2P común y avisar para que se verifique el exchange.
    lemon_signals = (raw.get("cambio_por") or raw.get("cotizacion")
                     or raw.get("lemon_screen"))
    if key == "lemon" and not lemon_signals:
        key = "otro"
        display = str(raw.get("exchange") or "?").strip().title()
        warnings.append("'Lemon' parece el método de pago, no el exchange — "
                        "verificá el exchange antes de cargar.")

    if key == "lemon":
        if str(raw.get("lemon_screen") or "").lower() == "pata":
            warnings.append("Es una pata de Lemon, no el total. Mandá la pantalla "
                            "'Recibiste X USDT a cambio de Y ARS' (el total).")
            return None, warnings
        cambio = _dec(raw.get("cambio_por"))
        cotiz = _dec(raw.get("cotizacion"))
        if cambio is None or cotiz is None or cotiz == 0:
            warnings.append("No pude leer 'Cambio por' o la cotización de Lemon.")
            return None, warnings
        total = (cambio / Decimal("0.99")).quantize(_ARS_Q, ROUND_HALF_UP)
        gross = (total / cotiz).quantize(_USDT_Q, ROUND_HALF_UP)
        commission = (total * Decimal("0.01") / cotiz).quantize(_USDT_Q, ROUND_HALF_UP)
        net = gross - commission
        price = cotiz
    elif key == "saldoar":
        total = _dec(raw.get("monto_ars"))
        gross = _dec(raw.get("cantidad_usdt"))
        commission = Decimal("0")
        net = gross
        price = (total / gross) if (total and gross) else _dec(raw.get("precio"))
    else:
        gross = _dec(raw.get("cantidad_usdt"))
        commission = _dec(raw.get("comision")) or Decimal("0")
        net = (gross - commission) if gross is not None else None
        total = _dec(raw.get("monto_ars"))
        price = _dec(raw.get("precio"))

    for label, val in (("cantidad USDT", gross), ("total ARS", total), ("precio", price)):
        if val is None:
            warnings.append(f"No pude leer {label}.")
    if not raw.get("order_id"):
        warnings.append("No pude leer el ID de la orden (puede fallar al cargar).")
    if not raw.get("date"):
        warnings.append("No pude leer la fecha (puede fallar al cargar).")

    if gross is not None and price is not None and total not in (None, Decimal("0")):
        implied = gross * price
        if abs(implied - total) / total > _CROSS_CHECK_TOL:
            warnings.append(f"Las cuentas no cierran: {gross}×{price}={implied} "
                            f"vs total {total}. Revisá antes de cargar.")

    movement = {
        "side": side,
        "date": str(raw.get("date") or ""),
        "order_id": str(raw.get("order_id") or ""),
        "usd_gross": _str(gross),
        "commission": _str(commission),
        "usd_net": _str(net),
        "price": _str(price),
        "total_ars": _str(total),
        "exchange_coin": f"{display} / {coin}",
        "bank": str(raw.get("bank") or ""),
    }
    return movement, warnings


_PROMPT = (
    "Mirá esta captura de una operación P2P de cripto (USDT/ARS) y devolvé SOLO "
    "un objeto JSON, sin texto alrededor, con estas claves (usá null si no la "
    "podés leer, NO inventes):\n"
    "  exchange: la PLATAFORMA donde se hizo la operación P2P (Bybit, Binance, "
    "OKX, Bitget, KuCoin, Lemon, SaldoAr). Tiene que estar ESCRITO o con su logo "
    "VISIBLE en la captura: si no lo ves, devolvé null. NO adivines por el diseño "
    "de la pantalla ni por los métodos de pago. Pistas: 'Centro de Ayuda P2P' + 'bloqueados "
    "por Bybit' → Bybit; marca Bitget → Bitget. OJO: NO confundas con el método "
    "de pago. 'Lemon Cash', 'Mercadopago', 'Uala', 'Naranja X' son MÉTODOS DE "
    "PAGO → van en 'bank', NO en 'exchange'. Poné exchange=Lemon SOLO si la "
    "pantalla es un intercambio de Lemon ('Intercambio con Lemmy' / 'Cambio "
    "por X').\n"
    "  side: 'compra' si el usuario recibió USDT / pagó ARS, 'venta' si vendió USDT\n"
    "  cantidad_usdt: cantidad de USDT\n"
    "  precio: precio ARS por USDT\n"
    "  monto_ars: total en ARS de la operación\n"
    "  comision: comisión mostrada (0 si no hay)\n"
    "  cambio_por: SOLO Lemon — el ARS de 'Cambio por X'\n"
    "  cotizacion: SOLO Lemon — la cotización mostrada\n"
    "  lemon_screen: SOLO Lemon — 'total' si dice 'Recibiste X USDT a cambio de "
    "Y ARS', 'pata' si es un detalle de un Lemoner/CUIT individual\n"
    "  order_id: ID de la orden (string)\n"
    "  date: fecha en formato YYYY-MM-DD\n"
    "  bank: banco o método de pago\n"
    "IMPORTANTE con los números: devolvé cada monto como STRING, EXACTAMENTE como "
    "aparece en la captura, con los MISMOS puntos y comas (ej: '95.013,02', "
    "'1.471,00', '1556.50'). NO los reformatees, NO saques separadores de miles, "
    "NO cambies la coma por punto, NO hagas ninguna cuenta. Copiá el texto tal cual."
)


def _extract_json_object(text: str) -> dict:
    """Extrae el primer objeto JSON del texto del modelo (ignora markdown/prosa)."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No se encontró JSON en la respuesta: {text!r}")
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    return obj


def _ask_claude_default(prompt: str, image_path: str) -> str:
    # import perezoso: el SDK sólo se necesita si de verdad se lee una captura.
    from core.screenshot_parser import _ask_claude
    return _ask_claude(prompt, image_path)


def motivo_dudoso(raw: dict) -> str | None:
    """Por qué NO confiar en esta lectura, o None si cierra.

    Los modelos de visión chicos y gratuitos leen bien casi siempre, pero
    cuando fallan lo hacen en silencio: cambian un dígito o se saltan un
    campo. Esto es el filtro que decide si vale gastar una lectura de Claude.
    """
    faltan = [k for k in ("cantidad_usdt", "precio", "monto_ars")
              if _dec(raw.get(k)) is None]
    # Lemon muestra "Cambio por" y cotización en vez de los campos normales.
    if faltan and (_dec(raw.get("cambio_por")) is None
                   or _dec(raw.get("cotizacion")) is None):
        return "no pudo leer " + ", ".join(faltan)
    if not raw.get("order_id"):
        return "sin ID de orden"
    if not raw.get("date"):
        return "sin fecha"
    gross, price = _dec(raw.get("cantidad_usdt")), _dec(raw.get("precio"))
    total = _dec(raw.get("monto_ars"))
    if gross and price and total:
        implied = gross * price
        if abs(implied - total) / total > _CROSS_CHECK_TOL:
            return f"las cuentas no cierran ({gross}x{price} vs {total})"
    return None


def _leer_con_claude(image_bytes: bytes, ask) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name
    try:
        return _extract_json_object(ask(_PROMPT, tmp_path))
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def extract_fields(image_bytes: bytes, *, session=None, ask_claude=None) -> dict:
    """Lee la captura y devuelve el dict crudo de campos.

    Primero el modelo de visión gratuito (NVIDIA): si la lectura cierra, se
    usa y no se gasta suscripción. Claude entra sólo cuando el gratis falla o
    devuelve algo que no cuadra — es el lector confiable, pero se paga.
    """
    import config

    for modelo in getattr(config, "NVIDIA_VISION_MODELS", None) or [None]:
        try:
            raw = extract_fields_nvidia(image_bytes, session=session, model=modelo)
        except Exception:
            _log.warning("El modelo gratuito %s falló al leer la captura.",
                         modelo, exc_info=True)
            continue
        motivo = motivo_dudoso(raw)
        if motivo is None:
            return raw
        _log.warning("Lectura dudosa de %s (%s): sigo probando.", modelo, motivo)
    _log.warning("Ningún modelo gratuito pudo leer la captura: uso Claude.")
    return _leer_con_claude(image_bytes, ask_claude or _ask_claude_default)


def extract_fields_nvidia(image_bytes: bytes, *, session=None, model=None) -> dict:
    """Lee la captura con un modelo de visión gratuito de NVIDIA."""
    import config

    sess = session or requests
    b64 = base64.b64encode(image_bytes).decode()
    body = {
        "model": model or config.NVIDIA_VISION_MODEL,
        "temperature": 0.0,
        # Tope de salida: acota el JSON y evita que un modelo de razonamiento
        # (p. ej. minimax) devuelva `choices` vacío al no cerrar la respuesta.
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": _PROMPT},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
    }
    url = config.NVIDIA_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {config.NVIDIA_API_KEY}"}
    resp = sess.post(url, headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    choices = resp.json().get("choices") or []
    if not choices:
        raise ValueError("La respuesta del modelo de visión vino sin choices.")
    content = choices[0]["message"]["content"]
    return _extract_json_object(content)
