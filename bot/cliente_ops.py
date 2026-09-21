"""Ops de cliente por Telegram: texto libre → tarjeta ✅/❌ → carga al VPS.

La lógica de negocio vive en core/client_ops (puro). Acá está la I/O: los
llamados al VPS, el formato de los mensajes y los handlers."""
from __future__ import annotations

import json
import secrets
from datetime import date as _date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.commands import _miles, fetch_json
from cli.push_movement import (
    assign_client, create_client, get_client, list_clients, push,
)
from core.client_ops import (
    MISSING_QUESTIONS, apply_answer, build_client_movement, resolve_client,
)


def card_text(mov: dict, client_name: str, warnings: list[str]) -> str:
    """La tarjeta que se muestra antes de escribir nada."""
    if mov["side"] == "VENTA":
        lado, verbo = "🔴 VENTA", "Le vendiste a"
    else:
        lado, verbo = "🟢 COMPRA", "Le compraste a"
    lines = [
        "🧾 Entendí esto:",
        f"{lado}  ·  {verbo} {client_name}",
        f"Cantidad: {mov['usd_net']} USDT   Precio: {mov['price']}",
        f"Total: {mov['total_ars']} ARS",
        f"Método: {mov['bank']}   Fecha: {mov['date']}",
        f"ID: {mov['order_id']}",
    ]
    for w in warnings:
        lines.append(f"⚠️ {w}")
    lines.append("\n¿La cargo?")
    return "\n".join(lines)


def _detail(text: str) -> str:
    try:
        return json.loads(text).get("detail", text)
    except (ValueError, AttributeError):
        return text


def load_and_format(mov: dict, client_id: int, client_name: str, base_url: str,
                    *, session=None) -> str:
    """Carga la op en dos pasos y devuelve el texto para el usuario.

    Primero POST /api/movement (DB + planilla), después el linkeo al cliente.
    Si el linkeo falla la op igual quedó cargada — eso se dice, no se calla.
    Nunca lanza excepción."""
    try:
        status, text = push(mov, base_url, session=session)
    except Exception:
        return ("❌ No pude contactar el VPS — la operación NO quedó cargada. "
                "Probá de nuevo en un rato.")

    try:
        if status == 409:
            return f"⚠️ Esa op ya estaba cargada (#{mov['order_id']})."
        if status != 201:
            return f"❌ No se pudo cargar ({status}): {_detail(text)}"

        ok = f"✅ Cargada #{mov['order_id']} — {mov['usd_net']} USDT @ {mov['price']}"
        try:
            link_status, _ = assign_client(mov["order_id"], client_id, base_url,
                                           session=session)
        except Exception:
            link_status = 0
        if link_status != 200:
            return (f"{ok}.\n⚠️ Pero no pude linkearla a {client_name}. "
                    "Linkeala desde el dashboard.")
        return f"{ok} en {client_name}."
    except (KeyError, ValueError, TypeError) as e:
        return f"❌ Movimiento incompleto — falta un campo o tiene formato inválido. Probá de nuevo."


def market_price(side: str, base_url: str) -> float | None:
    """Precio de referencia del mercado para avisar si la op se fue de rango.

    VENTA usa la punta a la que se vende más caro; COMPRA, la más barata para
    comprar. Devuelve None si el dashboard no responde — es solo informativo."""
    clave = "dearest_sell" if side == "VENTA" else "cheapest_buy"
    try:
        data = fetch_json(base_url, "/api/spread/now")
        precio = (data.get(clave) or {}).get("price")
        return float(precio) if precio else None
    except Exception:
        return None


def prepare_op(params: dict, base_url: str, today=None) -> dict:
    """Todo lo previo a la tarjeta: resuelve el cliente, trae su historial y
    arma el movimiento. No escribe nada.

    Devuelve un dict con 'kind':
      card         → {'mov', 'client', 'text', 'warnings'}
      ask          → {'missing', 'params', 'client', 'text'}
      new_client   → {'name', 'params', 'text'}
      pick_client  → {'candidates', 'params', 'text'}
      error        → {'text'}
    """
    today = today or _date.today()
    nombre = params.get("cliente")
    if not str(nombre or "").strip():
        return {"kind": "error",
                "text": "¿A qué cliente? Decime el nombre y la cargo."}
    try:
        clientes = list_clients(base_url)
    except Exception:
        return {"kind": "error",
                "text": "❌ No pude leer los clientes del VPS. Probá de nuevo."}

    cliente, candidatos = resolve_client(nombre, clientes)
    if cliente is None and candidatos:
        opciones = ", ".join(c["name"] for c in candidatos)
        return {"kind": "pick_client", "candidates": candidatos, "params": params,
                "text": f"¿Cuál de todos? {opciones}"}
    if cliente is None:
        return {"kind": "new_client", "name": str(nombre).strip(), "params": params,
                "text": f"No tengo a {nombre} en el CRM. ¿Lo creo y sigo?"}

    return _op_para_cliente(params, cliente, base_url, today)


def _op_para_cliente(params: dict, cliente: dict, base_url: str, today) -> dict:
    """Con el cliente ya resuelto: trae su historial y arma el movimiento."""
    # El nombre canónico pisa lo que dijo el usuario ("Dani"): si después hay
    # round-trip, resolve_client vuelve a caer en este mismo cliente por match
    # exacto y no se repite la desambiguación.
    params = {**params, "cliente": cliente["name"]}
    try:
        movimientos = get_client(cliente["id"], base_url).get("movements") or []
    except Exception:
        return {"kind": "error",
                "text": f"❌ No pude leer el historial de {cliente['name']}."}

    lado = params.get("lado")
    side = "VENTA" if str(lado or "").startswith("vend") else "COMPRA"
    mov, missing, warnings = build_client_movement(
        params, cliente, movimientos, today, market_price=market_price(side, base_url))

    if missing is not None:
        return {"kind": "ask", "missing": missing, "params": params,
                "client": cliente, "text": MISSING_QUESTIONS[missing]}
    return {"kind": "card", "mov": mov, "client": cliente, "warnings": warnings,
            "text": card_text(mov, cliente["name"], warnings)}


def _card_kb(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Cargar", callback_data=f"cliop_ok:{token}"),
        InlineKeyboardButton("❌ Cancelar", callback_data=f"cliop_no:{token}"),
    ]])


def _new_client_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Crearlo", callback_data="cliop_new:si"),
        InlineKeyboardButton("❌ No", callback_data="cliop_no:x"),
    ]])


def _pick_kb(candidatos: list[dict]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(c["name"], callback_data=f"cliop_pick:{c['id']}")]
        for c in candidatos
    ])


# Los tres estados pendientes de una op de cliente. Nunca conviven: si arranca
# un flujo nuevo, los otros se caen — así un botón viejo no actúa sobre el
# flujo equivocado (ej. tocar "Crearlo" de Rodolfo y que cree a Daniela).
_PENDING_KEYS = ("pending_op", "pending_new_client", "pending_pick")


async def _responder(message, context, out: dict) -> None:
    """Manda al usuario lo que decidió prepare_op y guarda el estado que haga falta."""
    for clave in _PENDING_KEYS:
        context.user_data.pop(clave, None)
    if out["kind"] == "card":
        token = secrets.token_hex(3)
        context.user_data.setdefault("client_ops", {})[token] = {
            "mov": out["mov"], "client": out["client"],
        }
        await message.reply_text(out["text"], reply_markup=_card_kb(token))
        return
    if out["kind"] == "ask":
        context.user_data["pending_op"] = {"params": out["params"],
                                           "missing": out["missing"]}
        await message.reply_text(out["text"])
        return
    if out["kind"] == "new_client":
        context.user_data["pending_new_client"] = {"name": out["name"],
                                                   "params": out["params"]}
        await message.reply_text(out["text"], reply_markup=_new_client_kb())
        return
    if out["kind"] == "pick_client":
        context.user_data["pending_pick"] = {"params": out["params"]}
        await message.reply_text(out["text"], reply_markup=_pick_kb(out["candidates"]))
        return
    await message.reply_text(out["text"])


async def start_op(message, context: ContextTypes.DEFAULT_TYPE, params: dict) -> None:
    """Entrada desde el orquestador cuando la acción es registrar_op_cliente."""
    import config
    # Una carga por texto pisa cualquier captura a medias: no conviven.
    context.user_data.pop("pending_capture", None)
    await _responder(message, context, prepare_op(params, config.VPS_API_URL))


async def on_pending_op(message, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Respuesta al round-trip. True si la consumió; False si el texto no servía
    (y ahí ya descartó el pendiente, para que el mensaje se clasifique de cero)."""
    import config
    pend = context.user_data.get("pending_op")
    if not pend:
        return False
    params = apply_answer(pend["params"], pend["missing"], text, _date.today())
    if params is None:
        context.user_data.pop("pending_op", None)
        pregunta = MISSING_QUESTIONS.get(pend["missing"], "ese dato")
        await message.reply_text(
            f"Dejé esa carga a medias (no entendí {pregunta.lower().strip('¿?')}).")
        return False
    await _responder(message, context, prepare_op(params, config.VPS_API_URL))
    return True


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    import config
    q = update.callback_query
    await q.answer()
    accion, _, arg = q.data.partition(":")

    if accion == "cliop_no":
        context.user_data.pop("pending_new_client", None)
        context.user_data.pop("pending_pick", None)
        context.user_data.get("client_ops", {}).pop(arg, None)
        await q.edit_message_text("Cancelada.")
        return

    if accion == "cliop_new":
        pend = context.user_data.pop("pending_new_client", None)
        if pend is None:
            await q.edit_message_text("Eso ya no está disponible, repetime el mensaje.")
            return
        try:
            cliente = create_client(pend["name"], config.VPS_API_URL)
        except Exception:
            await q.edit_message_text(f"❌ No pude crear a {pend['name']} en el CRM.")
            return
        await q.edit_message_text(f"👤 Creé a {cliente['name']}.")
        out = _op_para_cliente(pend["params"], cliente, config.VPS_API_URL, _date.today())
        await _responder(q.message, context, out)
        return

    if accion == "cliop_pick":
        pend = context.user_data.pop("pending_pick", None)
        if pend is None:
            await q.edit_message_text("Eso ya no está disponible, repetime el mensaje.")
            return
        await q.edit_message_text("Dale.")
        try:
            cliente = get_client(int(arg), config.VPS_API_URL)["client"]
        except Exception:
            await q.message.reply_text("❌ No pude leer ese cliente del VPS.")
            return
        out = _op_para_cliente(pend["params"], cliente, config.VPS_API_URL, _date.today())
        await _responder(q.message, context, out)
        return

    # cliop_ok: la única rama que escribe.
    guardado = context.user_data.get("client_ops", {}).pop(arg, None)
    if guardado is None:
        await q.edit_message_text("Esa op ya no está disponible, repetime el mensaje.")
        return
    await q.edit_message_text("⏳ Cargando…")
    cliente = guardado["client"]
    msg = load_and_format(guardado["mov"], cliente["id"], cliente["name"],
                          config.VPS_API_URL)
    await q.edit_message_text(msg)


def summary_text(client_name: str, movements: list[dict], today,
                 periodo: str | None = None) -> str:
    """Resumen de lo operado con un cliente. Puro: recibe las ops ya traídas."""
    movs = sorted(movements, key=lambda m: str(m.get("date") or ""))
    if periodo == "mes":
        prefijo = f"{today:%Y-%m}"
        movs = [m for m in movs if str(m.get("date") or "").startswith(prefijo)]
        titulo = f"👤 {client_name} — {prefijo}"
        vacio = "Sin operaciones este mes."
    else:
        titulo = f"👤 {client_name}"
        vacio = "Sin operaciones cargadas."
    if not movs:
        return f"{titulo}\n{vacio}"

    def _suma(ops, clave):
        return sum(float(m.get(clave) or 0) for m in ops)

    ventas = [m for m in movs if m.get("type") == "sell"]
    compras = [m for m in movs if m.get("type") == "buy"]
    lines = [titulo,
             f"{len(movs)} op(s) · {_miles(_suma(movs, 'totalArs'))} ARS"]
    if ventas:
        lines.append(f"🔴 Le vendiste {_miles(_suma(ventas, 'usdNeto'))} USDT")
    if compras:
        lines.append(f"🟢 Le compraste {_miles(_suma(compras, 'usdNeto'))} USDT")
    ultima = movs[-1]
    verbo = "vendiste" if ultima.get("type") == "sell" else "compraste"
    lines.append(f"Última: {ultima.get('date')} · le {verbo} "
                 f"{_miles(float(ultima.get('usdNeto') or 0))} @ "
                 f"{_miles(float(ultima.get('priceArs') or 0))}")
    return "\n".join(lines)


def consultar_text(params: dict, base_url: str, today=None) -> str:
    """Resuelve el cliente del mensaje y devuelve su resumen. Solo lectura."""
    today = today or _date.today()
    nombre = params.get("cliente")
    if not str(nombre or "").strip():
        return "¿De qué cliente? Decime el nombre."
    try:
        clientes = list_clients(base_url)
    except Exception:
        return "❌ No pude leer los clientes del VPS. Probá de nuevo."

    cliente, candidatos = resolve_client(nombre, clientes)
    if cliente is None and candidatos:
        return "¿Cuál de todos? " + ", ".join(c["name"] for c in candidatos)
    if cliente is None:
        return f"No tengo a {nombre} en el CRM."
    try:
        movimientos = get_client(cliente["id"], base_url).get("movements") or []
    except Exception:
        return f"❌ No pude leer el historial de {cliente['name']}."
    return summary_text(cliente["name"], movimientos, today,
                        periodo=params.get("periodo"))
