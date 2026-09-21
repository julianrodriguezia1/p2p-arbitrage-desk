"""Bot de Telegram (VPS): allowlist + comandos de consulta + /actualizar."""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters,
)

from bot.bridge_client import actualizar_text, is_authorized
from bot.captura import on_callback as captura_on_callback, on_photo as captura_on_photo
from bot.cliente_ops import on_callback as cliente_on_callback
from bot.commands import (
    billeteras_text, binance_text, cotizacion_placa, cotizacion_text,
    estrategia_text, donde_text, spread_text, stock_text,
)
from bot.op_btc import (
    cmd_cerrar as op_cmd_cerrar, cmd_estado as op_cmd_estado, cmd_op,
    cmd_spot as op_cmd_spot,
    cmd_tanda as op_cmd_tanda, on_callback as op_on_callback,
)
from bot.orquestador import on_text as orquestador_on_text

COTIZA_ASSET, COTIZA_SIDE, COTIZA_MARGIN = range(3)


def _ok(update: Update) -> bool:
    import config
    allowed = config.TELEGRAM_CHAT_ID
    return bool(allowed) and is_authorized(update.effective_chat.id, int(allowed))


async def cmd_actualizar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text("⏳ Buscando órdenes nuevas…")
    texto = actualizar_text(config.SYNC_BRIDGE_URL, config.SYNC_BRIDGE_TOKEN)
    await update.message.reply_text(texto)


async def cmd_spread(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text(spread_text(config.DASHBOARD_URL))


async def cmd_precio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text(donde_text(config.DASHBOARD_URL))


async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text(stock_text(config.DASHBOARD_URL))


async def cmd_estrategia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text(estrategia_text(config.DASHBOARD_URL))


async def cmd_binance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """La mejor jugada que deja una orden en el P2P de Binance (Verificado)."""
    import config
    if not _ok(update):
        return
    await update.message.reply_text(binance_text(config.DASHBOARD_URL))


async def cmd_billeteras(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _ok(update):
        return
    await update.message.reply_text(billeteras_text(config.DASHBOARD_URL))


async def _cotizacion_directa(update: Update, asset: str) -> None:
    """Las dos puntas de una, sin conversación ni botones."""
    import config
    if not _ok(update):
        return
    await update.message.reply_text(cotizacion_text(config.DASHBOARD_URL, asset))


async def cmd_btc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cotizacion_directa(update, "BTC")


async def cmd_usdt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _cotizacion_directa(update, "USDT")


async def cmd_cotizar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _ok(update):
        return ConversationHandler.END
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("💵 USDT", callback_data="act_usdt"),
        InlineKeyboardButton("₿ BTC", callback_data="act_btc"),
    ]])
    import config
    await update.message.reply_text(f"{config.BRAND_NAME} — ¿qué cotizás?", reply_markup=kb)
    return COTIZA_ASSET


async def cotiza_asset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    activo = "BTC" if q.data == "act_btc" else "USDT"
    context.user_data["cotiza_asset"] = activo
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Me COMPRA", callback_data="compra"),
        InlineKeyboardButton("🔴 Me VENDE", callback_data="venta"),
    ]])
    await q.edit_message_text(f"{activo} — ¿qué quiere el cliente?", reply_markup=kb)
    return COTIZA_SIDE


async def cotiza_side(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.callback_query
    await q.answer()
    context.user_data["cotiza_side"] = q.data
    lado = "te COMPRA (vos le vendés)" if q.data == "compra" else "te VENDE (vos le comprás)"
    await q.edit_message_text(f"Cliente {lado}.\n¿Qué % de ganancia le ponés? (ej. 2)")
    return COTIZA_MARGIN


async def cotiza_margin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    import config
    txt = (update.message.text or "").strip().replace(",", ".").replace("%", "")
    try:
        margin = float(txt)
    except ValueError:
        await update.message.reply_text("Poné un número, ej. 2 o 1.5")
        return COTIZA_MARGIN
    side = context.user_data.get("cotiza_side", "compra")
    asset = context.user_data.get("cotiza_asset", "USDT")
    png, caption = cotizacion_placa(config.DASHBOARD_URL, side, margin, asset)
    if png is None:
        await update.message.reply_text(caption)
    else:
        await update.message.reply_photo(photo=png, caption=caption)
    return ConversationHandler.END


async def cotiza_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END


def main() -> None:
    import config
    app = Application.builder().token(config.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("actualizar", cmd_actualizar))
    app.add_handler(CommandHandler("spread", cmd_spread))
    app.add_handler(CommandHandler("precio", cmd_precio))
    app.add_handler(CommandHandler("stock", cmd_stock))
    app.add_handler(CommandHandler("estrategia", cmd_estrategia))
    app.add_handler(CommandHandler("hago", cmd_estrategia))
    app.add_handler(CommandHandler("oportunidad", cmd_estrategia))
    app.add_handler(CommandHandler("binance", cmd_binance))
    app.add_handler(CommandHandler("verificado", cmd_binance))
    app.add_handler(CommandHandler("billeteras", cmd_billeteras))
    app.add_handler(CommandHandler("btc", cmd_btc))
    app.add_handler(CommandHandler("usdt", cmd_usdt))
    # /op: el ciclo completo de venderle BTC a un cliente (ver bot/op_btc.py).
    app.add_handler(CommandHandler("op", cmd_op))
    app.add_handler(CommandHandler("tanda", op_cmd_tanda))
    app.add_handler(CommandHandler("estado", op_cmd_estado))
    app.add_handler(CommandHandler("spot", op_cmd_spot))
    app.add_handler(CommandHandler("cerrar", op_cmd_cerrar))
    app.add_handler(CallbackQueryHandler(op_on_callback, pattern="^op_(load|skip)$"))
    app.add_handler(MessageHandler(filters.PHOTO, captura_on_photo))
    app.add_handler(CallbackQueryHandler(captura_on_callback, pattern="^cap_(ok|no):"))
    app.add_handler(CallbackQueryHandler(cliente_on_callback, pattern="^cliop_"))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("cotizar", cmd_cotizar), CommandHandler("jr", cmd_cotizar)],
        states={
            COTIZA_ASSET: [CallbackQueryHandler(cotiza_asset, pattern="^act_(usdt|btc)$")],
            COTIZA_SIDE: [CallbackQueryHandler(cotiza_side, pattern="^(compra|venta)$")],
            COTIZA_MARGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, cotiza_margin)],
        },
        fallbacks=[CommandHandler("cancelar", cotiza_cancel)],
    ))
    # Texto libre → orquestador. Va DESPUÉS del ConversationHandler para que una
    # cotización en curso capture el margen; ~COMMAND deja pasar los /comandos.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, orquestador_on_text))
    app.run_polling()


if __name__ == "__main__":
    main()
