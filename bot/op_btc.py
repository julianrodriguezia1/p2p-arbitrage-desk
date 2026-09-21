"""`/op`: el ciclo completo de venderle BTC a un cliente, desde Telegram.

El cliente paga en tandas y por billeteras distintas; se compra USDT tanda por
tanda, el bot lleva el promedio real y al cerrar calcula el BTC exacto, el precio
a cantarle y carga las cuatro operaciones.

La cuenta vive en core/op_cliente (puro). Acá está la I/O: parseo de lo que
escribe el usuario, formato de los mensajes y armado de los movimientos.

Flujo:
    /op Daniel 6040000 0.75     → dónde comprar el USDT y cuánto poner
    /tanda 2700 1578.70          → registra cada compra, dice cuánto falta
    /spot 3780.466902 0.04794 0.00004794   → el plan final + botón para cargar
"""
from __future__ import annotations

from dataclasses import replace

import config
from bot.commands import _miles, _miles2
from core.op_cliente import (
    FEE_PUENTE_USDT, FEE_RED_USDT, FEE_RETIRO_BTC, OpCliente, PlanBtc, PlanUsdt,
    Tanda, precio_efectivo_spot,
)

ASSETS = ("BTC", "USDT")

NL = chr(10)


# --------------------------------------------------------------- parseo

def _num(raw: str) -> float:
    """'1.578,99' y '1578.99' son el mismo número. El punto de miles se va."""
    s = raw.strip().replace(" ", "")
    if "," in s:                      # coma decimal: los puntos son de miles
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:            # 6.040.000: todos los puntos son de miles
        s = s.replace(".", "")
    elif "." in s:
        entera, _, dec = s.partition(".")
        if len(dec) == 3 and len(entera) <= 3:   # 6.040 → miles, no decimales
            s = entera + dec
    return float(s)


def parse_op(text: str) -> OpCliente:
    """'Daniel 6040000 0.75' → la operación arrancada.

    El asset puede ir adelante o atrás ('USDT Daniel 500000', 'Daniel 500000
    usdt'). Sin asset es BTC, que es lo que más se opera.
    """
    partes = text.split()
    asset = "BTC"
    for p in list(partes):
        if p.upper() in ASSETS:
            asset = p.upper()
            partes.remove(p)
    if len(partes) < 2:
        raise ValueError("Falta el monto. Ej: /op Daniel 6040000 0.75")
    cliente = partes[0]
    ars = _num(partes[1])
    margen = _num(partes[2]) if len(partes) > 2 else config.COTIZA_MARGEN_PCT
    return OpCliente(cliente=cliente, ars_cliente=ars, margen_pct=margen,
                     asset=asset)


def fee_flat_de(venue: str) -> float:
    """El flat del tomador de ese venue, en USDT. Binance 0,07; el resto 0.

    Se cobra por ORDEN: cinco avisos son cinco flats. La API de Binance devuelve
    commission 0 igual, así que sale de config, no de la orden.
    """
    clave = venue.lower().replace(" ", "")
    if not clave.endswith("p2p"):
        clave += "p2p"
    return config.FEE_P2P_BY_MODE.get(clave, {}).get("taker_flat_quote", 0.0)


def parse_tanda(text: str, venue: str = "") -> Tanda:
    """'2700 1578.70' → la compra de USDT que acabás de hacer."""
    partes = text.split()
    if len(partes) < 2:
        raise ValueError("Necesito USDT y precio. Ej: /tanda 2700 1578.70")
    return Tanda(usdt=_num(partes[0]), price_ars=_num(partes[1]),
                 fee_usdt=fee_flat_de(venue) if venue else 0.0)


def parse_spot(text: str) -> tuple[float, float, float]:
    """'3780.466902 0.04794 0.00004794' → (USDT gastados, BTC, comisión en BTC)."""
    partes = text.split()
    if len(partes) < 2:
        raise ValueError("Necesito los USDT gastados y el BTC. "
                         "Ej: /spot 3780.466902 0.04794 0.00004794")
    com = _num(partes[2]) if len(partes) > 2 else 0.0
    return _num(partes[0]), _num(partes[1]), com


# --------------------------------------------------------------- mensajes

def _btc(n: float) -> str:
    return f"{n:.8f}".replace(".", ",")


def fmt_arranque(op: OpCliente, venue: str, precio: float,
                 publicando: bool) -> str:
    """Lo primero que ve: cuánto USDT comprar, dónde y a cuánto."""
    usdt = op.falta_usdt(precio)
    modo = "publicá compra" if publicando else "tomá"
    return NL.join([
        f"🧾 {op.asset} para {op.cliente} · {_miles(op.ars_cliente)} ARS "
        f"· margen {op.margen_pct}%",
        "",
        f"1️⃣ Comprá {_miles2(usdt)} USDT en {venue}: {modo} a {_miles2(precio)}",
        f"   ({_miles(op.falta_ars())} ARS)",
        "",
        "Cargá cada compra con  /tanda <usdt> <precio>",
    ])


def fmt_tanda(op: OpCliente, precio_reposicion: float) -> str:
    """Después de cada compra: qué llevás y qué falta."""
    falta = op.falta_usdt(precio_reposicion)
    lines = [
        f"✅ Van {_miles2(op.usdt_total())} USDT · promedio "
        f"{_miles2(op.costo_promedio())}",
        f"   Gastado {_miles(op.ars_gastado())} de {_miles(op.presupuesto_ars())} ARS",
    ]
    if falta < 1 and op.asset == "USDT":
        lines += [
            "",
            "🎯 Compra completa. Mandale los USDT y cerrá con  /cerrar",
        ]
    elif falta < 1:
        lines += [
            "",
            "🎯 Compra completa. Ahora:",
            f"   • Pasá los USDT a Binance por BSC (~{FEE_PUENTE_USDT} USD)",
            "   • Comprá el BTC ahí (nunca retirar desde Bybit: cobra 4x)",
            "   • Después: /spot <usdt gastados> <btc> <comisión btc>",
        ]
    else:
        lines += ["", f"⏳ Faltan {_miles2(falta)} USDT "
                      f"({_miles(op.falta_ars())} ARS)"]
    return NL.join(lines)


def fmt_plan(op: OpCliente, plan: PlanBtc) -> str:
    """El cierre: cuánto retirar, qué precio cantarle y cuánto ganaste."""
    return NL.join([
        f"🎯 {op.cliente} · {_miles(op.ars_cliente)} ARS",
        "",
        f"Retirá        {_btc(plan.btc_bruto)} BTC",
        f"Le llegan     {_btc(plan.btc_al_cliente)} BTC exactos",
        "",
        f"LE DECÍS: {_miles(plan.precio_cantado)} ARS por BTC",
        f"          {_miles2(plan.precio_cantado_usdt)} USDT por BTC",
        "",
        f"Ganás {_miles(plan.ganancia_ars)} ARS ({op.margen_pct}%) "
        f"· te sobran {_miles2(plan.ganancia_usdt)} USDT",
    ])


def fmt_plan_usdt(op: OpCliente, plan: PlanUsdt) -> str:
    """El cierre de una op en USDT: no hay spot ni BTC de por medio."""
    return NL.join([
        f"🎯 {op.cliente} · {_miles(op.ars_cliente)} ARS",
        "",
        f"Le mandás    {_miles2(plan.usdt_al_cliente)} USDT",
        "",
        f"LE DECÍS: {_miles2(plan.precio_cantado)} ARS por USDT",
        "",
        f"Ganás {_miles(plan.ganancia_ars)} ARS ({op.margen_pct}%) "
        f"· te sobran {_miles2(plan.ganancia_usdt)} USDT",
    ])


# --------------------------------------------------------------- carga

def build_movements(op: OpCliente, plan: PlanBtc, fecha: str,
                    spot: tuple[float, float, float],
                    venue: str, bank: str,
                    order_ids: list[str] | None = None) -> list[dict]:
    """Las cuatro ops de la operación, listas para `cli.push_movement`.

    Una por cada compra de USDT, la del spot y la venta al cliente.
    """
    usdt_gastados, btc_bruto, comision_btc = spot
    dia = fecha.replace("-", "")
    movs: list[dict] = []

    for i, t in enumerate(op.compras):
        oid = (order_ids[i] if order_ids and i < len(order_ids)
               else f"op-{op.cliente.lower()}-usdt-{dia}-{i + 1}")
        movs.append({
            "side": "COMPRA", "date": fecha, "order_id": oid,
            "usd_gross": f"{t.usdt}", "commission": "0", "usd_net": f"{t.usdt}",
            "price": f"{t.price_ars}", "total_ars": f"{t.ars:.0f}",
            "exchange_coin": f"{venue} / USDT", "bank": bank,
        })

    promedio = op.costo_promedio() or 0.0
    btc_neto = btc_bruto - comision_btc
    total_ars_spot = usdt_gastados * promedio
    movs.append({
        "side": "COMPRA", "date": fecha, "order_id": f"spot-btcusdt-{dia}",
        "usd_gross": f"{btc_bruto:.8f}", "commission": f"{comision_btc:.8f}",
        "usd_net": f"{btc_neto:.8f}",
        "price": f"{total_ars_spot / btc_neto:.2f}",
        "total_ars": f"{total_ars_spot:.0f}",
        "exchange_coin": "Binance spot / BTC",
        "bank": "USDT de stock propio (no movio ARS)",
    })

    fee_red = plan.btc_bruto - plan.btc_al_cliente
    movs.append({
        "side": "VENTA", "date": fecha,
        "order_id": f"man-{op.cliente.lower()}-btc-{dia}",
        "usd_gross": f"{plan.btc_bruto:.8f}", "commission": f"{fee_red:.8f}",
        "usd_net": f"{plan.btc_al_cliente:.8f}",
        "price": f"{plan.precio_cantado:.2f}",
        "total_ars": f"{op.ars_cliente:.0f}",
        "exchange_coin": "OTC / BTC", "bank": bank,
    })
    return movs


def build_movements_usdt(op: OpCliente, plan: PlanUsdt, fecha: str,
                         venue: str, bank: str,
                         order_ids: list[str] | None = None) -> list[dict]:
    """Las ops de una venta de USDT: una por tanda comprada más la venta."""
    dia = fecha.replace("-", "")
    movs: list[dict] = []
    for i, t in enumerate(op.compras):
        oid = (order_ids[i] if order_ids and i < len(order_ids)
               else f"op-{op.cliente.lower()}-usdt-{dia}-{i + 1}")
        movs.append({
            "side": "COMPRA", "date": fecha, "order_id": oid,
            "usd_gross": f"{t.usdt}", "commission": "0", "usd_net": f"{t.usdt}",
            "price": f"{t.price_ars}", "total_ars": f"{t.ars:.0f}",
            "exchange_coin": f"{venue} / USDT", "bank": bank,
        })
    movs.append({
        "side": "VENTA", "date": fecha,
        "order_id": f"man-{op.cliente.lower()}-usdt-{dia}",
        "usd_gross": f"{plan.usdt_al_cliente:.6f}", "commission": "0",
        "usd_net": f"{plan.usdt_al_cliente:.6f}",
        "price": f"{plan.precio_cantado:.2f}",
        "total_ars": f"{op.ars_cliente:.0f}",
        "exchange_coin": "OTC / USDT", "bank": bank,
    })
    return movs


# --------------------------------------------------------------- handlers

def _precio_compra(base_url: str, volumen: float) -> tuple[str, float, float]:
    """(venue, precio tomando, precio publicando) para comprar USDT ahora.

    Sale del motor del VPS, que ya descuenta comisiones por venue y por modo:
    por eso nunca propone publicar en Binance (el 0,20% de maker se come el spread).
    """
    from bot.commands import fetch_json
    data = fetch_json(base_url, "/api/estrategia", {"volume": max(volumen, 100)})
    jugadas = [data["best"], *data.get("alternatives", [])]
    tomando = next((j for j in jugadas if j["buy_mode"] == "tomando"), None)
    publicando = next((j for j in jugadas if j["buy_mode"] == "publicando"), None)
    ref = tomando or publicando or data["best"]
    return (ref["buy_venue"].replace("p2p", "").title(),
            (tomando or ref)["buy_price"],
            (publicando or ref)["buy_price"])


async def cmd_op(update, context) -> None:
    """/op Daniel 6040000 0.75 — arranca una operación de cliente."""
    import config
    args = " ".join(context.args) if context.args else ""
    try:
        op = parse_op(args)
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    try:
        venue, tomando, publicando = _precio_compra(
            config.VPS_API_URL, op.presupuesto_ars() / 1600)
    except Exception:
        await update.message.reply_text(
            "❌ No pude leer los precios del VPS. Probá de nuevo en un rato.")
        return
    context.user_data["op"] = op
    context.user_data["op_venue"] = venue
    txt = fmt_arranque(op, venue, tomando, publicando=False)
    if publicando < tomando:
        ahorro = (tomando - publicando) * op.falta_usdt(tomando)
        txt += (f"{NL}{NL}💡 Publicando a {_miles2(publicando)} ahorrás "
                f"{_miles(ahorro)} ARS, pero esperás.")
    await update.message.reply_text(txt)


async def cmd_tanda(update, context) -> None:
    """/tanda 2700 1578.70 — suma una compra de USDT a la operación en curso."""
    import config
    op: OpCliente | None = context.user_data.get("op")
    if op is None:
        await update.message.reply_text("No hay operación abierta. Arrancá con /op")
        return
    try:
        tanda = parse_tanda(" ".join(context.args) if context.args else "",
                            venue=context.user_data.get("op_venue", ""))
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    op.compras.append(tanda)
    try:
        _, tomando, _ = _precio_compra(config.VPS_API_URL,
                                       max(op.falta_usdt(1600), 100))
    except Exception:
        tomando = tanda.price_ars
    await update.message.reply_text(fmt_tanda(op, tomando))


async def cmd_estado(update, context) -> None:
    """/estado — dónde está parada la operación."""
    import config
    op: OpCliente | None = context.user_data.get("op")
    if op is None:
        await update.message.reply_text("No hay operación abierta. Arrancá con /op")
        return
    try:
        _, tomando, _ = _precio_compra(config.VPS_API_URL, max(op.falta_usdt(1600), 100))
    except Exception:
        tomando = op.costo_promedio() or 1600.0
    await update.message.reply_text(fmt_tanda(op, tomando))


async def cmd_spot(update, context) -> None:
    """/spot 3780.466902 0.04794 0.00004794 — cierra: da el BTC y el precio."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    op: OpCliente | None = context.user_data.get("op")
    if op is None:
        await update.message.reply_text("No hay operación abierta. Arrancá con /op")
        return
    if op.asset != "BTC":
        await update.message.reply_text(
            "Esta operación es en USDT: no hay spot. Cerrala con /cerrar")
        return
    if not op.compras:
        await update.message.reply_text("Todavía no cargaste ninguna compra (/tanda).")
        return
    try:
        usdt_gastados, btc_bruto, comision = parse_spot(
            " ".join(context.args) if context.args else "")
    except ValueError as exc:
        await update.message.reply_text(f"❌ {exc}")
        return
    precio_ef = precio_efectivo_spot(usdt_gastados, btc_bruto, comision)
    plan = op.plan_btc(precio_ef)
    context.user_data["op_plan"] = plan
    context.user_data["op_spot"] = (usdt_gastados, btc_bruto, comision)
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Cargar las 4 ops", callback_data="op_load"),
        InlineKeyboardButton("❌ No", callback_data="op_skip"),
    ]])
    await update.message.reply_text(fmt_plan(op, plan), reply_markup=kb)


async def cmd_cerrar(update, context) -> None:
    """/cerrar — cierra una operación en USDT (las de BTC van por /spot)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    op: OpCliente | None = context.user_data.get("op")
    if op is None:
        await update.message.reply_text("No hay operación abierta. Arrancá con /op")
        return
    if op.asset == "BTC":
        await update.message.reply_text(
            "Esta operación es en BTC: cerrala con /spot <usdt> <btc> <comisión>")
        return
    if not op.compras:
        await update.message.reply_text("Todavía no cargaste ninguna compra (/tanda).")
        return
    fee = _num(context.args[0]) if context.args else FEE_RED_USDT
    plan = op.plan_usdt(fee_red_usdt=fee)
    context.user_data["op_plan"] = plan
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Cargar las ops", callback_data="op_load"),
        InlineKeyboardButton("❌ No", callback_data="op_skip"),
    ]])
    await update.message.reply_text(fmt_plan_usdt(op, plan), reply_markup=kb)


async def on_callback(update, context) -> None:
    """Carga las cuatro operaciones y las linkea al cliente."""
    from datetime import date as _date

    import config
    from cli.push_movement import assign_client, create_client, list_clients, push

    q = update.callback_query
    await q.answer()
    if q.data == "op_skip":
        await q.edit_message_text("Listo, no cargué nada.")
        return

    op: OpCliente | None = context.user_data.get("op")
    plan = context.user_data.get("op_plan")
    spot = context.user_data.get("op_spot")
    if not (op and plan) or (op.asset == "BTC" and not spot):
        await q.edit_message_text("Se me perdió la operación. Rehacela con /op")
        return

    base = config.VPS_API_URL
    venue = context.user_data.get("op_venue", "Bybit")
    hoy = _date.today().isoformat()
    if op.asset == "BTC":
        movs = build_movements(op, plan, hoy, spot, venue=venue,
                               bank="varias billeteras")
    else:
        movs = build_movements_usdt(op, plan, hoy, venue=venue,
                                    bank="varias billeteras")

    ok, fallaron = 0, []
    for mov in movs:
        try:
            status, _ = push(mov, base)
            if status in (200, 201):
                ok += 1
            elif status == 409:
                ok += 1          # ya estaba cargada, no es un error
            else:
                fallaron.append(mov["order_id"])
        except Exception:
            fallaron.append(mov["order_id"])

    linea_cliente = ""
    try:
        clientes = list_clients(base)
        match = next((c for c in clientes
                      if c["name"].lower() == op.cliente.lower()), None)
        if match is None:
            match = create_client(op.cliente, base)
        assign_client(movs[-1]["order_id"], int(match["id"]), base)
        linea_cliente = f"{NL}Asignada a {op.cliente}."
    except Exception:
        linea_cliente = (f"{NL}⚠️ Las ops quedaron cargadas pero NO pude "
                         f"asignarlas a {op.cliente}: hacelo desde el panel.")

    # El precio se repite acá a propósito: es el mensaje que queda en el chat
    # para mandarle al cliente, después de que la tarjeta del plan se reemplaza.
    resumen = [f"📌 {op.cliente} · {_miles(op.ars_cliente)} ARS"]
    if op.asset == "BTC":
        resumen += [
            f"   {_btc(plan.btc_al_cliente)} BTC",
            f"   {_miles(plan.precio_cantado)} ARS por BTC",
            f"   {_miles2(plan.precio_cantado_usdt)} USDT por BTC",
        ]
    else:
        resumen += [
            f"   {_miles2(plan.usdt_al_cliente)} USDT",
            f"   {_miles2(plan.precio_cantado)} ARS por USDT",
        ]
    resumen.append(f"   Ganaste {_miles(plan.ganancia_ars)} ARS ({op.margen_pct}%)")
    texto = NL.join([f"✅ Cargué {ok} de {len(movs)} ops.{linea_cliente}", "", *resumen])
    if fallaron:
        texto += f"{NL}❌ Fallaron: {', '.join(fallaron)}"
    context.user_data.pop("op", None)
    context.user_data.pop("op_plan", None)
    context.user_data.pop("op_spot", None)
    await q.edit_message_text(texto)
