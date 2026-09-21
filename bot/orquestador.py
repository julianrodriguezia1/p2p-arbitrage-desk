"""Orquestador de texto libre del bot de Telegram.

Un solo handler de texto (``~COMMAND``) que:
  1) si hay una captura esperando exchange, interpreta el texto como el exchange
     y termina de cargarla (round-trip);
  2) si no, clasifica la intención con NVIDIA y dispara la acción que ya existe
     en ``bot/commands.py``."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.bridge_client import is_authorized
from bot.captura import _KNOWN_VENUES, resolve_exchange, send_card
from bot.cliente_ops import consultar_text, on_pending_op, start_op
from bot.commands import (
    billeteras_text, binance_text, estrategia_text, spread_text, stock_text,
)
from core.orchestrator import classify


def _authorized(update: Update) -> bool:
    import config
    allowed = config.TELEGRAM_CHAT_ID
    return bool(allowed) and is_authorized(update.effective_chat.id, int(allowed))


def help_text() -> str:
    return (
        "Escribime en criollo y te entiendo 🙂 (sin barras, palabra suelta va):\n"
        "• «oportunidad» → la mejor jugada de spread ahora, comprando o vendiendo\n"
        "• «binance» → la mejor jugada que deje una orden en Binance P2P (Verificado)\n"
        "• el spread / la mejor jugada de arbitraje\n"
        "• a qué precio comprar y vender USDT\n"
        "• cuánto stock tenés y tu P&L\n"
        "• la estrategia (qué te conviene ahora)\n"
        "• cómo vienen las billeteras vs los topes\n"
        "• actualizar/sincronizar las órdenes nuevas\n"
        "• cargar una op de un cliente: \"le vendí 1000 a Daniel a 1578\"\n"
        "• contarte qué operaste con un cliente\n"
        "• cotizarle a un cliente con tu margen\n"
        "Y si me mandás una captura de una operación, la cargo."
    )


# Lo que se contesta cuando el router no pudo leer el mensaje (NVIDIA caído,
# rate limit, timeout). Distinto del menú de ayuda a propósito: el usuario tiene
# que saber que fue un problema nuestro y no que le entendimos mal.
SIN_ROUTER = ("Uf, se me colgó el traductor y no te pude leer. "
              "Mandámelo de nuevo, porfa.")


def dispatch(action: str, error: str | None = None,
             params: dict | None = None) -> str:
    """Ejecuta la acción elegida llamando a las funciones que ya existen y
    devuelve el texto a responder. Toda acción no mapeada cae en la ayuda.

    `error='infra'` significa que el router nunca llegó a clasificar: ahí no va
    el menú de ayuda, va el aviso de que hay que repetir el mensaje."""
    import config

    if error == "infra":
        return SIN_ROUTER

    from bot.bridge_client import actualizar_text

    if action == "spread":
        return spread_text(config.DASHBOARD_URL)
    if action in ("donde", "precio"):
        # "precio" contestaba sólo a qué publicar en Binance; eso quedó cubierto
        # por el bloque de publicando del ranking, que además compara venues.
        from bot.commands import donde_text
        from bot.cotizar import normalize_asset

        p = params or {}
        lado = str(p.get("lado") or "ambos").strip().lower()
        if lado not in ("compro", "vendo", "ambos"):
            lado = "ambos"
        try:
            monto = float(p["monto"]) if p.get("monto") is not None else None
        except (TypeError, ValueError):
            monto = None
        return donde_text(config.DASHBOARD_URL, lado=lado, monto=monto,
                          asset=normalize_asset(p.get("activo")))
    if action == "stock":
        return stock_text(config.DASHBOARD_URL)
    if action == "estrategia":
        return estrategia_text(config.DASHBOARD_URL)
    if action == "binance":
        return binance_text(config.DASHBOARD_URL)
    if action == "billeteras":
        return billeteras_text(config.DASHBOARD_URL)
    if action == "actualizar":
        return actualizar_text(config.SYNC_BRIDGE_URL, config.SYNC_BRIDGE_TOKEN)
    return help_text()


async def _handle_pending_capture(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                  raw: dict, text: str) -> None:
    mov, warnings, ambiguo = resolve_exchange(raw, text)
    if mov is None:
        # p. ej. una pata de Lemon: warnings explica qué mandar.
        msg = " ".join(warnings) or "No pude reconstruir la operación."
        await update.message.reply_text(f"⚠️ {msg}")
        return
    if ambiguo:
        context.user_data["pending_capture"] = raw   # sigue pendiente, reintenta
        await update.message.reply_text(
            f"No conozco ese exchange 🤔. Probá con uno de estos: {_KNOWN_VENUES}.")
        return
    await send_card(update.message, context, mov, warnings)


# Circuit breaker del margen, en el mismo espíritu que PRICE_MIN/PRICE_MAX de
# core.client_ops: un % de ganancia arriba de esto no es un margen, es un texto
# que se coló (ej. "le vendí 1000 a Daniel a 1578" → 10001578).
MARGEN_MAX = 100


def _monto_param(params: dict) -> float | None:
    """El monto a cotizar si lo dijo. None (= el default del server) si no se
    entiende: mejor cotizar el ticket de siempre que inventar un tamaño."""
    from core.client_ops import parse_amount

    monto = parse_amount(params.get("monto"))
    return float(monto) if monto is not None and monto > 0 else None


def cotizar_params(params: dict) -> tuple[str | None, float | None, str]:
    """Normaliza los datos de una cotización pedida en criollo.

    Devuelve (lado, margen, activo). lado es None si no se entendió de qué lado
    está el cliente; margen es None si no lo dijo, no es un número positivo o se
    pasa del techo razonable; activo siempre trae algo (USDT si no se entendió)."""
    from bot.cotizar import normalize_asset
    from core.client_ops import normalize, parse_amount

    n = normalize(params.get("lado_cliente"))
    lado = "compra" if n == "compra" else ("venta" if n == "venta" else None)
    margen_dec = parse_amount(params.get("margen"))
    valido = margen_dec is not None and 0 < margen_dec <= MARGEN_MAX
    margen = float(margen_dec) if valido else None
    return lado, margen, normalize_asset(params.get("activo"))


async def cotizar_flow(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       params: dict) -> None:
    """Manda la placa de cotización, o pregunta el margen si no lo dijo."""
    import config

    from bot.commands import cotizacion_placa

    from bot.commands import cotizacion_text

    lado, margen, activo = cotizar_params(params)
    if lado is None:
        # Sin lado no se pregunta: se contestan LAS DOS puntas de una. Pedido
        # explícito del usuario ("pongo cotizar BTC y que no me pregunte nada")
        # y además es lo útil: quiere ver dónde compra y dónde vende a la vez.
        await update.message.reply_text(
            cotizacion_text(config.DASHBOARD_URL, activo,
                            _monto_param(params), margen))
        return
    if margen is None:
        # Guarda lado Y activo: si solo guardara el lado, al responder el margen
        # volvería cotizando USDT aunque hubiera pedido BTC.
        context.user_data["pending_cotiza"] = {"lado": lado, "activo": activo}
        await update.message.reply_text(
            f"¿Qué % de ganancia le ponés al {activo}? (ej. 2)")
        return
    png, caption = cotizacion_placa(config.DASHBOARD_URL, lado, margen, activo)
    if png is None:
        await update.message.reply_text(caption)
    else:
        await update.message.reply_photo(photo=png, caption=caption)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    if not _authorized(update):
        return
    text = (update.message.text or "").strip()
    if not text:
        return

    raw = context.user_data.pop("pending_capture", None)
    if raw is not None:
        await _handle_pending_capture(update, context, raw, text)
        return

    # Cotización esperando el margen. Si el texto no sirve como margen se
    # descarta la cotización y el mensaje se clasifica de cero (mismo criterio
    # que pending_op): así el usuario nunca queda trabado ni se pierde una op.
    pendiente = context.user_data.pop("pending_cotiza", None)
    if pendiente is not None:
        cot = {"lado_cliente": pendiente["lado"], "margen": text,
               "activo": pendiente["activo"]}
        if cotizar_params(cot)[1] is not None:
            await cotizar_flow(update, context, cot)
            return

    # Una op esperando un dato tiene prioridad. Si el texto no servía, la
    # descarta y sigue de largo para clasificar este mensaje de cero.
    if context.user_data.get("pending_op"):
        if await on_pending_op(update.message, context, text):
            return

    result = classify(text)
    action, params = result["action"], result.get("params") or {}
    if action == "registrar_op_cliente":
        await start_op(update.message, context, params)
        return
    if action == "consultar_cliente":
        await update.message.reply_text(consultar_text(params, config.VPS_API_URL))
        return
    if action == "cotizar":
        await cotizar_flow(update, context, params)
        return
    await update.message.reply_text(
        dispatch(action, result.get("error"), params))
