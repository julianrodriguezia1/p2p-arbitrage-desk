"""Handler de capturas por Telegram: foto → visión → tarjeta → carga al VPS."""
from __future__ import annotations

import json
import logging
import asyncio
import secrets
from datetime import datetime
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.bridge_client import is_authorized
from cli.push_movement import push
from core.capture_parser import build_movement, extract_fields, needs_exchange

_log = logging.getLogger(__name__)

# Exchanges que el bot sabe reconstruir cuando el usuario los aclara por texto.
_KNOWN_VENUES = "Bybit, OKX, Binance, Bitget, KuCoin, Lemon, SaldoAr"


def _authorized(update: Update) -> bool:
    import config
    allowed = config.TELEGRAM_CHAT_ID
    return bool(allowed) and is_authorized(update.effective_chat.id, int(allowed))


def card_text(mov: dict, warnings: list[str]) -> str:
    lado = "🟢 COMPRA" if mov["side"] == "COMPRA" else "🔴 VENTA"
    lines = [
        "📸 Entendí esto:",
        f"{lado}  ·  {mov['exchange_coin']}",
        f"Cantidad: {mov['usd_net']} (bruto {mov['usd_gross']}, com {mov['commission']})",
        f"Precio: {mov['price']}   Total: {mov['total_ars']} ARS",
        f"Método: {mov['bank']}   ID: {mov['order_id']}   Fecha: {mov['date']}",
    ]
    for w in warnings:
        lines.append(f"⚠️ {w}")
    lines.append("\n¿La cargo?")
    return "\n".join(lines)


def push_and_format(mov: dict, base_url: str, *, session=None) -> str:
    try:
        status, text = push(mov, base_url, session=session)
    except Exception:
        return ("❌ No pude contactar el VPS — la operación NO quedó cargada. "
                 "Reenviá la captura (si ya estaba, te aviso).")
    if status == 201:
        return f"✅ Cargada #{mov['order_id']}."
    if status == 409:
        return f"⚠️ Esa orden ya estaba cargada (#{mov['order_id']})."
    try:
        detail = json.loads(text).get("detail", text)
    except (ValueError, AttributeError):
        detail = text
    return f"❌ No se pudo cargar ({status}): {detail}"


def _card_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Cargar", callback_data=f"cap_ok:{token}"),
        InlineKeyboardButton("❌ Cancelar", callback_data=f"cap_no:{token}"),
    ]])


def ask_exchange_text() -> str:
    return ("🤔 Leí la operación pero no sé de qué exchange es. "
            f"Decime cuál y la termino: {_KNOWN_VENUES}…")


def resolve_exchange(raw: dict, exchange_text: str) -> tuple[dict | None, list[str], bool]:
    """Pisa el exchange del raw con lo que aclaró el usuario y reconstruye el
    movimiento (recalcula todo: maña Lemon ÷0,99, SaldoAr, etc.).

    Devuelve (mov, warnings, ambiguo). ``ambiguo`` sigue True si aun con la
    aclaración no se reconoce el exchange."""
    raw = {**raw, "exchange": (exchange_text or "").strip()}
    mov, warnings = build_movement(raw)
    return mov, warnings, needs_exchange(raw, warnings)


async def send_card(message, context: ContextTypes.DEFAULT_TYPE, mov: dict,
                    warnings: list[str]) -> None:
    """Guarda el movimiento con un token y manda la tarjeta ✅/❌."""
    token = secrets.token_hex(3)                  # 6 hex, entra en callback_data
    context.user_data.setdefault("captures", {})[token] = mov
    await message.reply_text(card_text(mov, warnings), reply_markup=_card_kb(token))


#: Dónde caen las capturas que el lector no pudo interpretar, para reintentarlas.
CAPTURAS_FALLIDAS = Path("data/capturas-fallidas")

_EXT_POR_MIME = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def guardar_fallida(image_bytes: bytes, mime: str = "image/jpeg",
                    carpeta: Path | None = None) -> Path | None:
    """Deja en disco una captura que no se pudo leer, y devuelve dónde quedó.

    El 2026-09-08 una captura de KuCoin se procesó en memoria, el lector falló y
    la imagen se perdió: hubo que pedírsela de nuevo al usuario. Guardar es un
    extra, así que si falla no puede tumbar la respuesta: devuelve None.
    """
    carpeta = Path(carpeta) if carpeta is not None else CAPTURAS_FALLIDAS
    ext = _EXT_POR_MIME.get(mime, ".jpg")
    nombre = f"captura-{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}{ext}"
    destino = carpeta / nombre
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(image_bytes)
        return destino
    except OSError:
        _log.warning("No pude guardar la captura fallida en %s", destino,
                     exc_info=True)
        return None


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text("🔍 Leyendo la captura…")
    photo = update.message.photo[-1]              # la más grande
    tg_file = await photo.get_file()
    image_bytes = bytes(await tg_file.download_as_bytearray())
    try:
        # Leer puede tardar hasta CLAUDE_TIMEOUT_S. En el event loop del bot eso
        # congela todos los demás comandos, así que va a un hilo aparte.
        raw = await asyncio.to_thread(extract_fields, image_bytes)
        mov, warnings = build_movement(raw)
    except Exception:
        # Dejar el motivo en el journal: un lector de visión caído se ve igual
        # que una captura ilegible, y así no se descubre por semanas.
        _log.warning("Falló la lectura de la captura.", exc_info=True)
        guardada = guardar_fallida(image_bytes)
        extra = f" La guardé en {guardada.name}." if guardada else ""
        await update.message.reply_text(
            "No pude leer la captura, probá de nuevo o pasámela a mí "
            f"(Claude).{extra}")
        return
    if mov is None:
        msg = " ".join(warnings) or "No parece una captura de operación 🤔"
        await update.message.reply_text(f"⚠️ {msg}")
        return
    if needs_exchange(raw, warnings):
        # No muestro la tarjeta todavía: guardo el raw crudo y pregunto de qué
        # exchange es. La respuesta de texto entra por bot/orquestador.on_text.
        context.user_data["pending_capture"] = raw
        await update.message.reply_text(ask_exchange_text())
        return
    await send_card(update.message, context, mov, warnings)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    q = update.callback_query
    await q.answer()
    action, _, token = q.data.partition(":")
    store = context.user_data.get("captures", {})
    mov = store.pop(token, None)
    if mov is None:
        await q.edit_message_text("Esa captura ya no está disponible, reenviala.")
        return
    if action == "cap_no":
        await q.edit_message_text("Cancelada.")
        return
    await q.edit_message_text("⏳ Cargando…")
    msg = push_and_format(mov, config.VPS_API_URL)
    await q.edit_message_text(msg)
