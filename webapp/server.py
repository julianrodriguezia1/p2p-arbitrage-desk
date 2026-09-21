"""Servidor FastAPI local del dashboard P2P. Lee/escribe trades.db + planilla."""
import logging
from decimal import Decimal
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException, UploadFile, Header
from fastapi.responses import FileResponse, JSONResponse

logger = logging.getLogger(__name__)

_depth_cache: dict[tuple, tuple[float, dict]] = {}
_estrategia_cache: dict[tuple, tuple[float, dict]] = {}


def _fee_por_orden(venue: str, asset: str) -> float:
    """Flat de tomador por orden del venue (0,07 USDT en Binance), 0 si no tiene.
    Acepta clave de venue ("binancep2p") o de fetcher ("binance")."""
    import config
    from core import arb_matrix
    from core.fees import flat_por_orden
    return flat_por_orden(
        fees_by_venue=config.FEE_P2P_BY_MODE, venue=venue, asset=asset,
        flat_assets=config.TAKER_FLAT_ASSETS,
        alias={k: v for v, k in arb_matrix.P2P_DEPTH_VENUES.items()})

from core.movements import Source
from core.sheet_writer import MonthTabNotFound
from webapp.serialize import dashboard_to_movement, movement_to_dashboard
from webapp.clients_serialize import client_to_dashboard, dashboard_to_client, _INVERSE

ParserFn = Callable[[bytes, str], dict]


def _payload_to_snake(payload: dict) -> dict:
    """Mapea el payload camelCase del HTML a los campos snake_case editables."""
    return {_INVERSE[k]: v for k, v in payload.items() if k in _INVERSE}


def _build_default_suggester(db, config):
    """Construye el suggester real que usa compute_suggestion + suggestion_payload."""
    from p2p_scanner import fetch_binance, MIN_LIQUIDITY_ARS
    from core.criptoya import fetch_reference
    from cli.prepare_ad import (
        compute_suggestion, suggestion_payload, SIDE_MAP,
    )

    def suggester(*, side: str, asset: str, fiat: str,
                  ad_min, ad_max, methods, margin) -> dict:
        side_enum = SIDE_MAP[side]
        ad_min_d = Decimal(str(ad_min)) if ad_min is not None else config.DEFAULT_AD_MIN_ARS
        ad_max_d = Decimal(str(ad_max)) if ad_max is not None else config.DEFAULT_AD_MAX_ARS
        margin_d = Decimal(str(margin)) if margin is not None else config.MIN_MARGIN_PCT
        methods_list = (
            [m.strip() for m in methods.split(",") if m.strip()]
            if methods is not None
            else config.DEFAULT_METHODS
        )
        s = compute_suggestion(
            side_enum, asset, fiat,
            margin_pct=margin_d,
            movements=db.all_movements(),
            fetch_ads=fetch_binance,
            fetch_ref=fetch_reference,
            tick=config.TICK_ARS,
            floor=config.PRICE_FLOOR_ARS,
            ceil=config.PRICE_CEIL_ARS,
            min_liquidity=Decimal(str(MIN_LIQUIDITY_ARS)),
            whitelist=config.CRIPTOYA_WHITELIST,
            volume=config.CRIPTOYA_VOLUME,
        )
        return suggestion_payload(s, side_enum, asset, ad_min_d, ad_max_d, methods_list)

    return suggester


def _build_default_binance_sync(db, writer, config):
    """Construye el sync real de Binance: trae órdenes nuevas, escribe planilla + DB."""
    from core.binance_p2p import BinanceP2PClient
    from cli.sync_binance import _fetch_all, select_new_movements

    def sync() -> dict:
        client = BinanceP2PClient(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
        nuevos = select_new_movements(_fetch_all(client), db.all_order_ids())
        added, skipped = [], []
        for m in nuevos:
            try:
                writer.write_movement(m)
                db.insert(m)
                added.append(movement_to_dashboard(m))
            except MonthTabNotFound as exc:
                # Falta la pestaña del mes: no se escribe ni se inserta, se reporta.
                skipped.append({"order_id": m.order_id, "missing_tab": str(exc)})
        return {"added": added, "skipped": skipped, "count": len(added)}

    return sync


def _build_default_bybit_sync(db, writer, config):
    """Sync real de Bybit: trae órdenes P2P nuevas, escribe planilla + DB."""
    from core.bybit_p2p import BybitP2PClient
    from cli.sync_bybit import _fetch_all, select_new_movements

    def sync() -> dict:
        client = BybitP2PClient(config.BYBIT_API_KEY, config.BYBIT_API_SECRET)
        nuevos = select_new_movements(_fetch_all(client), db.all_order_ids())
        added, skipped = [], []
        for m in nuevos:
            try:
                writer.write_movement(m)
                db.insert(m)
                added.append(movement_to_dashboard(m))
            except MonthTabNotFound as exc:
                skipped.append({"order_id": m.order_id, "missing_tab": str(exc)})
        return {"added": added, "skipped": skipped, "count": len(added)}

    return sync


def _build_default_dollar_ta(config):
    """Construye el analizador real del USDT/ARS.

    Fuente primaria: velas DIARIAS de Binance (precio del mercado donde se opera;
    la última vela es la de hoy en vivo, así que no hace falta pegar otro punto).
    Respaldo: ArgentinaDatos (dólar cripto) + precio de hoy de CriptoYa, por si
    Binance no responde o no devuelve suficiente historial para la MA larga.
    """
    import requests
    from core.criptoya import fetch_reference
    from core import dollar_ta as dta

    ARGDATOS_URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/cripto"
    BINANCE_KLINES_URL = (
        "https://api.binance.com/api/v3/klines?symbol=USDTARS&interval=1d&limit=1000"
    )

    def _binance_series():
        """Serie diaria desde Binance, o None si falla o no alcanza para la MA larga."""
        try:
            resp = requests.get(BINANCE_KLINES_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            serie = dta.parse_binance_klines(resp.json())
        except Exception:
            logger.exception("Binance klines no disponible, uso respaldo ArgentinaDatos")
            return None
        if len(serie) < config.DOLLAR_TA_MA_LONG:
            return None
        return serie

    def _argdatos_series():
        """Respaldo: ArgentinaDatos + punto de hoy de CriptoYa."""
        def http_get():
            resp = requests.get(ARGDATOS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            resp.raise_for_status()
            return resp.json()

        ref = fetch_reference("USDT", "ARS", config.CRIPTOYA_VOLUME,
                              whitelist=config.CRIPTOYA_WHITELIST)
        today_price = (ref.best_bid + ref.best_ask) / 2 if ref is not None else None
        return dta.fetch_history(http_get, today_price=today_price)

    def run(window: int) -> dict:
        serie = _binance_series() or _argdatos_series()
        return dta.analyze(
            serie,
            ma_short=config.DOLLAR_TA_MA_SHORT,
            ma_long=config.DOLLAR_TA_MA_LONG,
            rsi_period=config.DOLLAR_TA_RSI_PERIOD,
            dev_threshold=config.DOLLAR_TA_DEV_THRESHOLD,
            rsi_low=config.DOLLAR_TA_RSI_LOW,
            rsi_high=config.DOLLAR_TA_RSI_HIGH,
            window=window,
        )

    return run


def _build_default_cotizacion(config, p2p_fetchers):
    """Cotización al cliente con precio EJECUTABLE: junta el payload de CriptoYa
    (CEX, ya neto) con los libros P2P reales (para caminar la profundidad) y se
    lo pasa al motor puro de core.cotizacion."""
    import time as _t

    from core import cotizacion as motor
    from core import spot
    from core.criptoya import fetch_payload

    # Claves de CriptoYa por exchange, para que el motor y el fee model hablen
    # el mismo idioma que el resto del sistema.
    P2P_KEY = {"binance": "binancep2p", "okx": "okexp2p", "bybit": "bybitp2p",
               "bitget": "bitgetp2p", "kucoin": "kucoinp2p"}

    def _libros(asset: str) -> dict:
        books: dict[str, dict] = {}
        for ex, key in P2P_KEY.items():
            fetcher = p2p_fetchers.get(ex)
            if fetcher is None:
                continue
            libro = {}
            for side in ("BUY", "SELL"):
                try:
                    libro[side] = fetcher(asset, "ARS", side, rows=20)
                except Exception:
                    # Un venue caído no puede tumbar la cotización entera.
                    logger.warning("Libro P2P de %s/%s no disponible", ex, side)
                    libro[side] = []
            if libro["BUY"] or libro["SELL"]:
                books[key] = libro
        return books

    def _motor(asset: str, size: float, margin_pct: float, **extra):
        try:
            payload = fetch_payload(asset, "ARS", size)
        except Exception:
            logger.exception("Falló CriptoYa en la cotización")
            payload = {}
        return motor.build(
            payload, _libros(asset), asset=asset, size=size,
            margin_pct=margin_pct,
            whitelist={v.lower() for v in config.CRIPTOYA_ARBITRAGE_WHITELIST},
            fees=config.FEE_P2P_BY_MODE, max_age_min=config.MAX_QUOTE_AGE_MIN,
            now=_t.time(), flat_assets=config.TAKER_FLAT_ASSETS, **extra)

    def cotizar(asset: str, size: float, margin_pct: float,
                top: int = 3) -> dict:
        """Para un activo que no es USDT suma la ruta sintética ARS→USDT→activo,
        que en BTC sale más barata que cruzar el par contra pesos (ver
        core.spot). Si no hay spot, la cotización sigue igual que antes."""
        spot_q = usdt_cot = None
        if asset.upper() != "USDT":
            spot_q = spot.spot_quote(asset)
            if spot_q:
                # El libro de USDT hay que caminarlo por el monto EQUIVALENTE:
                # 0,0122 BTC no son 0,0122 USDT sino ~945.
                usdt_cot = _motor("USDT", size * spot_q["ask"], margin_pct,
                                  top=top)

        cot = _motor(asset, size, margin_pct, spot=spot_q, usdt=usdt_cot,
                     spot_fee_pct=config.SPOT_FEE_PCT, top=top)
        return _cotizacion_payload(cot)

    return cotizar


def _leg_payload(leg) -> dict | None:
    if leg is None:
        return None
    return {"venue": leg.venue, "price": leg.price, "mode": leg.mode,
            "stock": leg.stock, "alcanza": leg.alcanza,
            "via": getattr(leg, "via", None),
            "ordenes": getattr(leg, "ordenes", 1)}


def _cotizacion_payload(cot) -> dict:
    return {
        "asset": cot.asset, "size": cot.size, "margin_pct": cot.margin_pct,
        "buys": [_leg_payload(l) for l in cot.buys],
        "sells": [_leg_payload(l) for l in cot.sells],
        "precio_venta_cliente": cot.precio_venta_cliente,
        "precio_compra_cliente": cot.precio_compra_cliente,
        "vuelta_pct": cot.vuelta_pct, "cubre": cot.cubre,
        "faltante_pct": cot.faltante_pct,
        "publicando_compra": _leg_payload(cot.mejor_publicando_compra),
        "publicando_venta": _leg_payload(cot.mejor_publicando_venta),
        "publicando_buys": [_leg_payload(l) for l in cot.publicando_buys],
        "publicando_sells": [_leg_payload(l) for l in cot.publicando_sells],
    }


def _build_default_spread_now(config):
    """Resumen de spread USDT/ARS ahora: best ask/bid por exchange + mejor cross."""
    from p2p_scanner import scan, find_opportunities

    def spread_now(asset: str = "USDT", fiat: str = "ARS") -> dict:
        quotes = scan(asset, fiat)
        _intra, cross = find_opportunities(quotes, asset)
        exchanges = []
        for q in quotes:
            intra_pct = None
            if q.best_ask and q.best_bid:
                intra_pct = round((q.best_bid - q.best_ask) / q.best_ask * 100, 2)
            exchanges.append({
                "exchange": q.exchange,
                "ask": q.best_ask, "bid": q.best_bid, "intra_pct": intra_pct,
            })
        best_cross = None
        if cross:
            b_ex, b_ask, s_ex, s_bid, _net, pct = cross[0]
            best_cross = {"buy_ex": b_ex, "buy": b_ask, "sell_ex": s_ex,
                          "sell": s_bid, "net_pct": round(pct, 2)}
        vol = _criptoya_volume(config, asset)
        cheapest_buy, dearest_sell, best_route = _criptoya_overview(config, asset, fiat, vol)
        top_buys, top_sells = _criptoya_ranked(config, asset, fiat, vol)
        return {"asset": asset, "fiat": fiat,
                "exchanges": exchanges, "best_cross": best_cross,
                "cheapest_buy": cheapest_buy, "dearest_sell": dearest_sell,
                "best_route": best_route,
                "top_buys": top_buys, "top_sells": top_sells}

    return spread_now


def _venue_type(config, name: str) -> str:
    """Etiqueta informativa del venue: remesa / p2p / cex (solo a título de dato)."""
    n = name.lower()
    if n in config.REMESA_VENUES:
        return "remesa"
    if n.endswith("p2p"):
        return "p2p"
    return "cex"


def _criptoya_volume(config, asset: str) -> float:
    """Volumen de referencia para CriptoYa. Por activo, porque el default está
    calibrado en USDT (ver config.CRIPTOYA_VOLUME_BY_ASSET)."""
    return config.CRIPTOYA_VOLUME_BY_ASSET.get(asset, config.CRIPTOYA_VOLUME)


def _criptoya_overview(config, asset: str, fiat: str, volume: float | None = None):
    """Enriquece el spread con CriptoYa: dónde comprar más barato y vender más caro.

    Mira TODOS los exchanges que cotizan ARS (whitelist amplia), filtrando
    cotizaciones rancias. Devuelve (cheapest_buy, dearest_sell, best_route):
    - cheapest_buy: ask mínimo del momento (+ tipo de venue, solo informativo).
    - dearest_sell: bid máximo del momento (+ tipo de venue).
    - best_route: comprar al más barato → vender al más caro, con el % de spread.
    Todos None si CriptoYa falla; el resto del spread sigue andando.
    """
    try:
        from core.criptoya import fetch_market_extremes
        ext = fetch_market_extremes(
            asset, fiat, config.CRIPTOYA_VOLUME if volume is None else volume,
            whitelist=config.CRIPTOYA_WHITELIST,
            max_age_min=config.MAX_QUOTE_AGE_MIN)
    except Exception:
        logger.exception("Falló el overview de CriptoYa")
        ext = None
    if ext is None:
        return None, None, None
    cheapest_buy = {"exchange": ext.buy_ex, "price": ext.buy_ask,
                    "type": _venue_type(config, ext.buy_ex)}
    dearest_sell = {"exchange": ext.sell_ex, "price": ext.sell_bid,
                    "type": _venue_type(config, ext.sell_ex)}
    best_route = {"buy_ex": ext.buy_ex, "buy": ext.buy_ask,
                  "sell_ex": ext.sell_ex, "sell": ext.sell_bid,
                  "gross_pct": round(ext.spread_pct, 2)}
    return cheapest_buy, dearest_sell, best_route


def _criptoya_ranked(config, asset: str, fiat: str, volume: float | None = None):
    """Top-3 venues OPERABLES (whitelist de arbitraje, sin remesa) para comprar
    más barato y para vender más caro. Devuelve (top_buys, top_sells) — listas de
    {exchange, price}. ([], []) si CriptoYa falla. Sirve de opciones de respaldo."""
    import time as _t

    try:
        from core.criptoya import fetch_payload, rank_extremes
        payload = fetch_payload(
            asset, fiat, config.CRIPTOYA_VOLUME if volume is None else volume)
        ranked = rank_extremes(
            payload, {v.lower() for v in config.CRIPTOYA_ARBITRAGE_WHITELIST},
            max_age_min=config.MAX_QUOTE_AGE_MIN, now=_t.time(), top=3)
    except Exception:
        logger.exception("Falló el ranking de CriptoYa")
        return [], []
    return ranked["buys"], ranked["sells"]


def _build_default_captacion_chat(config):
    """Chat de la IA de Captación: usa core.captacion_chat.answer con login Max."""
    from core import captacion_chat

    def chat(messages: list[dict]) -> str:
        return captacion_chat.answer(messages, docs_dir=config.CAPTACION_DOCS_DIR)

    return chat


def _evaluar_mis(mis: str, puntas: list, key_map: dict, tol: float = 0.0,
                 mios: Optional[dict] = None) -> list:
    """Parsea "venue:lado:precio,..." y dice si cada aviso propio sigue siendo la
    punta. Una entrada rota se ignora en silencio: es texto del navegador, no
    puede tirar abajo el tablero.

    Con `mios` ({venue: {"compra": precio|None, "venta": ...}}, leído del libro
    por apodo) el precio tipeado no manda: se mide el aviso real. Si el aviso no
    aparece en el libro el estado es "fuera" (pausado o tan lejos de la punta que
    no entra en las primeras filas): nunca "sos la punta" por un precio viejo."""
    from dataclasses import asdict

    from core.puntas import estado_aviso

    por_venue = {p["venue"]: p for p in puntas}
    out = []
    for item in (mis or "").split(","):
        partes = item.strip().split(":")
        if len(partes) != 3:
            continue
        venue_raw, lado, precio_raw = (x.strip().lower() for x in partes)
        venue = key_map.get(venue_raw, venue_raw)
        try:
            precio = float(precio_raw)
        except ValueError:
            continue
        p = por_venue.get(venue)
        if p is None or lado not in ("compra", "venta"):
            continue
        punta = p["comprar_publicando"] if lado == "compra" else p["vender_publicando"]
        if mios is not None:
            real = (mios.get(venue) or {}).get(lado)
            if real is None:
                out.append({"venue": venue, "lado": lado, "mi_precio": None, "punta": punta,
                            "estado": "fuera", "diferencia_ars": None, "sugerido": punta})
                continue
            precio = real
        out.append(asdict(estado_aviso(mi_precio=precio, lado=lado, punta=punta,
                                       venue=venue, tolerancia=tol)))
    return out


def create_app(db=None, writer=None, parser: Optional[ParserFn] = None,
               html_path: Optional[str] = "dashboard.html",
               suggester=None, binance_sync=None,
               spread_log_path: Optional[str] = None,
               p2p_fetchers=None, dollar_ta=None, spread_now=None, bybit_sync=None,
               sync_jobs=None, sync_agent_token=None,
               agente_exe_path=None, captacion_chat=None,
               clients_db=None, cotizacion=None, btc_spot=None) -> FastAPI:
    if db is None or writer is None or parser is None:
        import config
        from core.trades_db import TradesDB
        from core.sheet_writer import writer_from_config
        from core.screenshot_parser import parse_screenshot
        db = db or TradesDB(config.TRADES_DB_PATH)
        # La planilla de Google es opcional: sin credenciales, sólo SQLite.
        writer = writer or writer_from_config(config)
        parser = parser or parse_screenshot

    if spread_log_path is None:
        import config
        spread_log_path = str(config.SPREAD_LOG_PATH)

    if p2p_fetchers is None:
        from p2p_scanner import FETCHERS
        p2p_fetchers = FETCHERS

    if btc_spot is None:
        # Precio BTC/USDT para pasar el volumen de Binance a BTC, que es la
        # unidad en la que Binance pide los requisitos del Verificado.
        from core.spot import spot_quote
        btc_spot = lambda: spot_quote("BTC")

    if suggester is None:
        import config
        suggester = _build_default_suggester(db, config)

    if binance_sync is None:
        import config
        binance_sync = _build_default_binance_sync(db, writer, config)

    if bybit_sync is None:
        import config
        bybit_sync = _build_default_bybit_sync(db, writer, config)

    if dollar_ta is None:
        import config
        dollar_ta = _build_default_dollar_ta(config)

    if spread_now is None:
        import config
        spread_now = _build_default_spread_now(config)

    if cotizacion is None:
        import config
        cotizacion = _build_default_cotizacion(config, p2p_fetchers)

    if sync_jobs is None:
        from webapp.sync_jobs import SyncJobs
        sync_jobs = SyncJobs()

    if sync_agent_token is None:
        import config
        sync_agent_token = config.SYNC_AGENT_TOKEN

    if agente_exe_path is None:
        import config
        agente_exe_path = str(config.AGENTE_EXE_PATH)

    if captacion_chat is None:
        import config
        captacion_chat = _build_default_captacion_chat(config)

    if clients_db is None:
        from core.clients_db import ClientsDB
        clients_db = ClientsDB(db.conn)

    app = FastAPI(title="P2P Desk")

    @app.get("/")
    def index():
        if not html_path:
            return JSONResponse({"ok": True})
        return FileResponse(html_path)

    @app.get("/api/trades")
    def get_trades():
        ids = db.client_ids()
        out = []
        for m in db.all_movements():
            d = movement_to_dashboard(m)
            d["clientId"] = ids.get(m.order_id)
            out.append(d)
        return out

    @app.post("/api/trades", status_code=201)
    def post_trade(payload: dict):
        src = Source(payload.get("source") or Source.SCREENSHOT.value)
        try:
            m = dashboard_to_movement(payload, source=src)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise HTTPException(422, f"Datos de la operación inválidos: {exc}")
        if db.exists(m.order_id):
            raise HTTPException(409, f"Ya cargado #{m.order_id}")
        try:
            writer.write_movement(m)
        except MonthTabNotFound as exc:
            raise HTTPException(422, f"Falta la pestaña '{exc}' en la planilla. Creala y reintentá.")
        db.insert(m)
        return movement_to_dashboard(m)

    @app.post("/api/movement", status_code=201)
    def post_movement(payload: dict):
        """Carga un movimiento EXPLÍCITO (formato cli/add_movement) en DB + planilla.

        A diferencia de /api/trades (que deriva total_ars=bruto*precio), acá el
        total_ars viene dado, así respeta la maña de Lemon. Dedup por order_id.
        """
        from cli.add_movement import movement_from_json
        try:
            m = movement_from_json(payload)
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise HTTPException(422, f"Datos del movimiento inválidos: {exc}")
        if db.exists(m.order_id):
            raise HTTPException(409, f"Ya cargado #{m.order_id}")
        try:
            writer.write_movement(m)
        except MonthTabNotFound as exc:
            raise HTTPException(422, f"Falta la pestaña '{exc}' en la planilla. Creala y reintentá.")
        db.insert(m)
        return movement_to_dashboard(m)

    @app.delete("/api/trades/{order_id}")
    def delete_trade(order_id: str):
        return {"deleted": db.delete(order_id)}

    @app.get("/api/clients")
    def list_clients():
        return clients_db.list_with_summary()

    @app.post("/api/clients", status_code=201)
    def create_client(payload: dict):
        try:
            c = dashboard_to_client(payload)
        except (KeyError, ValueError, TypeError) as exc:
            raise HTTPException(422, f"Datos del cliente inválidos: {exc}")
        cid = clients_db.create(c)
        return client_to_dashboard(clients_db.get(cid))

    @app.get("/api/clients/{client_id}")
    def get_client(client_id: int):
        c = clients_db.get(client_id)
        if c is None:
            raise HTTPException(404, "No existe ese cliente.")
        movs = clients_db.movements_for(client_id)
        return {
            "client": client_to_dashboard(c),
            "movements": [movement_to_dashboard(m) for m in movs],
        }

    @app.put("/api/clients/{client_id}")
    def update_client(client_id: int, payload: dict):
        if clients_db.get(client_id) is None:
            raise HTTPException(404, "No existe ese cliente.")
        clients_db.update(client_id, _payload_to_snake(payload))
        return client_to_dashboard(clients_db.get(client_id))

    @app.delete("/api/clients/{client_id}")
    def delete_client(client_id: int):
        return {"deleted": clients_db.delete(client_id)}

    @app.post("/api/clients/{client_id}/contacted")
    def contact_client(client_id: int):
        if clients_db.get(client_id) is None:
            raise HTTPException(404, "No existe ese cliente.")
        clients_db.mark_contacted(client_id)
        return client_to_dashboard(clients_db.get(client_id))

    @app.put("/api/movements/{order_id}/client")
    def assign_movement_client(order_id: str, payload: dict):
        cid = payload.get("client_id")
        if cid is not None and clients_db.get(cid) is None:
            raise HTTPException(404, "No existe ese cliente.")
        return {"updated": db.set_client(order_id, cid)}

    @app.post("/api/screenshot")
    async def screenshot(file: UploadFile):
        data = await file.read()
        try:
            parsed = parser(data, file.content_type or "image/png")
        except Exception as exc:  # parseo/visión falló
            logger.exception("Falló el parseo de la captura")
            raise HTTPException(422, f"No pude leer la captura: {exc}")
        return {"parsed": parsed}

    @app.post("/api/sync/binance")
    def sync_binance_endpoint():
        """Trae las órdenes P2P nuevas de Binance y las carga en planilla + DB."""
        try:
            return binance_sync()
        except Exception as exc:
            logger.exception("Falló el sync de Binance")
            raise HTTPException(502, f"No pude sincronizar con Binance: {exc}")

    @app.post("/api/sync/bybit")
    def sync_bybit_endpoint():
        """Trae las órdenes P2P nuevas de Bybit y las carga en planilla + DB."""
        try:
            return bybit_sync()
        except Exception as exc:
            logger.exception("Falló el sync de Bybit")
            raise HTTPException(502, f"No pude sincronizar con Bybit: {exc}")

    @app.get("/api/cost/today")
    def cost_today(asset: str = "USDT", day: str | None = None):
        """Costo promedio de las COMPRAS de hoy (con comisiones) + precio break-even.

        `day` opcional (YYYY-MM-DD) para consultar otro día; default = hoy.
        avg_price = total_ars / usd_net = precio mínimo para salir even al vender.
        """
        from datetime import date as _date
        from core import pricing
        try:
            target = _date.fromisoformat(day) if day else _date.today()
        except ValueError:
            raise HTTPException(422, "day debe ser una fecha YYYY-MM-DD")
        movs = db.all_movements()
        cb = pricing.cost_basis(movs, asset, on=target)
        pos = pricing.day_position(movs, asset, on=target)
        return {
            "asset": asset, "day": target.isoformat(),
            "count": cb.count if cb is not None else 0,
            "units": float(pos.bought),
            "total_ars": float(cb.total_ars) if cb is not None else 0.0,
            "avg_price": float(cb.avg_price) if cb is not None else None,
            "breakeven": float(cb.avg_price) if cb is not None else None,
            "sold": float(pos.sold),
            "stock": float(pos.stock),
        }

    @app.get("/api/cost/period")
    def cost_period(asset: str = "USDT", period: str = "hoy", day: str | None = None):
        """Precio promedio de compra y de venta del asset en un período.

        period: hoy | semana (lun-dom) | mes (calendario). `day` opcional
        (YYYY-MM-DD) fija la fecha de referencia; default = hoy.
        avg_price = total_ars / usd_gross (precio real por moneda, no break-even).
        """
        from datetime import date as _date
        from core import pricing
        from core.movements import Side
        try:
            ref = _date.fromisoformat(day) if day else _date.today()
        except ValueError:
            raise HTTPException(422, "day debe ser una fecha YYYY-MM-DD")
        try:
            start, end = pricing.period_bounds(period, ref)
        except ValueError:
            raise HTTPException(422, "period debe ser 'hoy', 'semana' o 'mes'")
        movs = db.all_movements()

        def leg(side):
            pa = pricing.period_average(movs, asset, side, start=start, end=end)
            if pa is None:
                return None
            return {"count": pa.count, "units": float(pa.units),
                    "total_ars": float(pa.total_ars), "avg_price": float(pa.avg_price)}

        buy, sell = leg(Side.COMPRA), leg(Side.VENTA)
        gap_ars = gap_pct = None
        if buy is not None and sell is not None:
            gap_ars = sell["avg_price"] - buy["avg_price"]
            gap_pct = gap_ars / buy["avg_price"] * 100 if buy["avg_price"] else None
        return {
            "asset": asset, "period": period,
            "start": start.isoformat(), "end": end.isoformat(),
            "buy": buy, "sell": sell, "gap_ars": gap_ars, "gap_pct": gap_pct,
        }

    @app.get("/api/position")
    def position(asset: str = "USDT"):
        """Posición TOTAL del asset en la DB: todo lo comprado - todo lo vendido.

        stock > 0 = USDT a favor (te queda para vender); < 0 = en contra.
        Solo es exacto si todos los movimientos históricos están cargados.
        """
        from core import pricing
        pos = pricing.day_position(db.all_movements(), asset)  # on=None => histórico
        return {
            "asset": asset,
            "bought": float(pos.bought),
            "sold": float(pos.sold),
            "stock": float(pos.stock),
        }

    @app.get("/api/wallets")
    def get_wallets(month: str | None = None):
        """Control mensual de flujo de ARS por billetera/vía de pago."""
        from core import wallets as wl
        import config_wallets
        movs = db.all_movements()
        months = wl.available_months(movs)
        if not month:
            month = months[0] if months else ""
        flows = wl.monthly_wallet_flows(
            movs, month, config_wallets.WALLET_ALIASES, config_wallets.WALLET_LIMITS)
        sin_mapear = flows.pop("_sin_mapear", [])
        return {"month": month, "months": months,
                "wallets": flows, "sin_mapear": sin_mapear}

    @app.get("/api/suggest")
    def suggest_price(side: str, asset: str = "USDT", fiat: str = "ARS",
                      min: float | None = None, max: float | None = None,
                      methods: str | None = None, margin: float | None = None):
        if side not in ("vender", "comprar"):
            raise HTTPException(422, "side debe ser 'vender' o 'comprar'")
        try:
            return suggester(side=side, asset=asset, fiat=fiat, ad_min=min,
                             ad_max=max, methods=methods, margin=margin)
        except Exception as exc:
            raise HTTPException(502, f"No pude calcular la sugerencia: {exc}")

    @app.get("/api/spread/history")
    def spread_history(max_spread: float = 5.0):
        """Resumen del historial de spread USDT/ARS (lee el CSV del logger)."""
        from cli.spread_report import load_rows, history_payload
        try:
            rows = load_rows(spread_log_path)
        except FileNotFoundError:
            rows = []
        return history_payload(rows, max_pct=max_spread, min_pct=-max_spread)

    @app.get("/api/p2p/cheapest")
    def p2p_cheapest(exchange: str = "binance", asset: str = "USDT",
                     fiat: str = "ARS", rows: int = 20, side: str = "BUY"):
        """Avisos reales de un exchange P2P (todos los makers, sin filtro de reputación).

        exchange: binance | okx | bybit.
        side: "BUY"  -> anuncios donde el maker VENDE (vos COMPRÁS); ordenados de
                        más barato a más caro (el mejor para comprar es el primero).
              "SELL" -> anuncios donde el maker COMPRA (vos VENDÉS, "donde lo pagan
                        más caro"); ordenados de más caro a más barato.
        A diferencia de CriptoYa, acá no se filtra por reputación: lista todo,
        incluidos makers con pocas órdenes, mostrando su rep para que decidas.
        """
        side = side.upper()
        if side not in ("BUY", "SELL"):
            raise HTTPException(422, "side debe ser 'BUY' o 'SELL'")
        fetcher = p2p_fetchers.get(exchange)
        if fetcher is None:
            raise HTTPException(404, f"Exchange '{exchange}' no soportado. Usá: {', '.join(p2p_fetchers)}")
        try:
            ads = fetcher(asset, fiat, side, rows=rows)
        except Exception as exc:
            raise HTTPException(502, f"No pude leer {exchange} P2P: {exc}")
        # BUY: el mejor es el más barato (asc). SELL: el mejor es el más caro (desc).
        ads = sorted(ads, key=lambda a: a.price, reverse=(side == "SELL"))
        return {
            "exchange": exchange, "asset": asset, "fiat": fiat, "side": side,
            "ads": [{
                "price": a.price, "merchant": a.merchant,
                "orders": a.orders, "finish_rate": a.finish_rate,
                "available": a.available, "min": a.min_amount, "max": a.max_amount,
                "methods": a.methods,
            } for a in ads],
        }

    @app.get("/api/p2p/depth_quote")
    def depth_quote(exchange: str = "bitget", asset: str = "USDT",
                    fiat: str = "ARS", volume: float = 1000.0):
        """Precio P2P real por profundidad (VWAP del order book) para `volume`.
        ask/bid en null si ese lado falla (degradado elegante)."""
        import time
        from core.p2p_depth import compute_depth_quote
        fetcher = p2p_fetchers.get(exchange)
        if fetcher is None:
            raise HTTPException(404, f"Exchange '{exchange}' no soportado. Usá: {', '.join(p2p_fetchers)}")
        key = (exchange, asset, fiat, volume)
        nowt = time.time()
        cached = _depth_cache.get(key)
        if cached is not None and nowt - cached[0] < 30:
            return cached[1]
        try:
            buy = fetcher(asset, fiat, "BUY", rows=20)
        except Exception:
            buy = []
        try:
            sell = fetcher(asset, fiat, "SELL", rows=20)
        except Exception:
            sell = []
        q = compute_depth_quote(buy, sell, volume,
                                fee_por_orden=_fee_por_orden(exchange, asset))
        out = {"exchange": exchange, "asset": asset, "fiat": fiat,
               "volume": volume, "ask": q["ask"], "bid": q["bid"]}
        _depth_cache[key] = (nowt, out)
        return out

    def _libros_p2p(asset: str, fiat: str) -> dict[str, tuple[list, list]]:
        """{venue: (ads_BUY, ads_SELL)} crudos, una sola bajada de red.

        Separado del calculo del VWAP porque la curva de tamanos necesita el
        MISMO libro evaluado a varios montos: bajarlo una vez por tamano seria
        cuatro escaneos de todos los venues y cuatro fotos distintas del mercado.
        """
        from core import arb_matrix
        libros: dict[str, tuple[list, list]] = {}
        for venue_name, fetch_key in arb_matrix.P2P_DEPTH_VENUES.items():
            fetcher = p2p_fetchers.get(fetch_key)
            if fetcher is None:
                continue
            try:
                buy = fetcher(asset, fiat, "BUY", rows=20)
            except Exception:
                buy = []
            try:
                sell = fetcher(asset, fiat, "SELL", rows=20)
            except Exception:
                sell = []
            libros[venue_name] = (buy, sell)
        return libros

    def _estrategia_de(libros, payload, volume: float, nowt: float,
                       asset: str = "USDT") -> dict:
        """Arma la respuesta de estrategia para UN tamano, sin tocar la red."""
        from dataclasses import asdict
        from core.p2p_depth import compute_depth_quote
        from core import arb_matrix
        from core.fees import por_modo
        from core.strategy import (
            build_strategy, find_outside_note, patas_binance, ruta_por_binance,
            venue_liquido,
        )

        depth: dict[str, dict] = {}
        for venue_name, (buy, sell) in libros.items():
            # El flat de tomador va por orden: el motor elige el llenado que
            # rinde más neto (no el de mejor precio bruto) y cuenta las órdenes.
            q = compute_depth_quote(buy, sell, volume,
                                    fee_por_orden=_fee_por_orden(venue_name, asset))
            if q["ask"] or q["bid"]:
                depth[venue_name] = q

        cex_venues = set(config.CRIPTOYA_ARBITRAGE_WHITELIST) - set(arb_matrix.P2P_DEPTH_VENUES)
        venues = arb_matrix.build_venues(
            depth, payload, cex_venues=cex_venues,
            blacklist=config.CRIPTOYA_BLACKLIST,
            max_age_min=config.MAX_QUOTE_AGE_MIN, now=nowt,
            puede_publicar_compra=config.P2P_PUEDE_PUBLICAR_COMPRA,
            puede_publicar_venta=config.P2P_PUEDE_PUBLICAR_VENTA,
            p2p_sin_profundidad=config.P2P_SIN_PROFUNDIDAD,
        )
        # El fee de tomador de Binance es un flat de 0,07 USDT: su peso en % sale
        # del tamano del ticket, asi que la tabla se arma por volumen.
        fee_modo = por_modo(fees_by_venue=config.FEE_P2P_BY_MODE, volume=volume,
                            asset=asset, flat_assets=config.TAKER_FLAT_ASSETS)
        routes = arb_matrix.best_routes(venues, fee_pct=config.FEE_PCT_BY_VENUE,
                                        fee_by_mode=fee_modo)
        # Misma busqueda, pero solo sobre puntas que mueven volumen. De aca sale
        # la jugada de abajo del panel: la mejor EJECUTABLE EN TAMANO.
        routes_liq = arb_matrix.best_routes(
            venues, fee_pct=config.FEE_PCT_BY_VENUE, usable=venue_liquido,
            fee_by_mode=fee_modo)
        # Y otra vez exigiendo que alguna pata caiga en el P2P de Binance: son
        # las unicas ordenes que suman para el Comerciante Verificado.
        routes_bin = arb_matrix.best_routes(
            venues, fee_pct=config.FEE_PCT_BY_VENUE, usable=venue_liquido,
            keep=ruta_por_binance, fee_by_mode=fee_modo)

        note = find_outside_note(
            payload,
            operable_venues={v.lower() for v in config.CRIPTOYA_ARBITRAGE_WHITELIST},
            broad_whitelist={v.lower() for v in config.CRIPTOYA_WHITELIST},
            remesa_venues={v.lower() for v in config.REMESA_VENUES},
            blacklist={v.lower() for v in config.CRIPTOYA_BLACKLIST},
            margin_pct=config.STRATEGY_OUTSIDE_MARGIN_PCT,
            max_age_min=config.MAX_QUOTE_AGE_MIN, now=nowt,
        )

        strat = build_strategy(routes, network_fee_pct=config.STRATEGY_NETWORK_FEE_PCT,
                               outside_note=note, routes_liquidas=routes_liq,
                               routes_binance=routes_bin,
                               secundarios=frozenset(config.VENUES_SECUNDARIOS))
        return {
            "asof": nowt,
            "volume": volume,
            "best": asdict(strat.best) if strat.best else None,
            "alternatives": [asdict(p) for p in strat.alternatives],
            "outside_note": asdict(strat.outside_note) if strat.outside_note else None,
            "con_volumen": asdict(strat.con_volumen) if strat.con_volumen else None,
            "binance": (
                {**asdict(strat.binance), "patas_binance": patas_binance(strat.binance)}
                if strat.binance else None
            ),
            "best_en_binance": strat.best_en_binance,
            # Venues cuyo precio sale de CriptoYa sin orderbook: la jugada existe
            # pero nadie garantiza que atras haya stock. El panel lo marca.
            "sin_profundidad": sorted(config.P2P_SIN_PROFUNDIDAD),
            "liquidez": {
                name: {k: q.get(k) for k in
                       ("ask_avisos", "ask_stock", "ask_alcanza", "ask_ordenes",
                        "bid_avisos", "bid_stock", "bid_alcanza", "bid_ordenes")}
                for name, q in depth.items()
            },
        }

    @app.get("/api/estrategia/curva")
    def estrategia_curva(sizes: str = "1000,3000,3500,5000",
                         asset: str = "USDT", fiat: str = "ARS"):
        """La misma jugada evaluada a varios tamanos de ticket.

        Existe porque el precio P2P escala con el monto: cada aviso publica un
        minimo y un maximo por orden, asi que un ticket grande abre avisos que
        con uno chico son intocables (y suelen tener mejor precio). Los libros
        se bajan UNA vez y se recalculan encima, para que los tamanos se comparen
        contra la misma foto del mercado.
        """
        import time as _t
        from core.criptoya import fetch_payload

        vols = _sizes(sizes)
        nowt = _t.time()
        libros = _libros_p2p(asset, fiat)
        try:
            payload = fetch_payload(asset, fiat, max(vols))
        except Exception:
            payload = {}
        return {"asof": nowt,
                "curva": [_estrategia_de(libros, payload, v, nowt, asset) for v in vols]}

    def _sizes(raw: str) -> list[float]:
        try:
            vols = [float(x) for x in raw.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(422, "sizes tiene que ser una lista de numeros separados por coma")
        if not vols or any(v <= 0 for v in vols):
            raise HTTPException(422, "los tamanos tienen que ser numeros mayores a cero")
        if len(vols) > 8:
            raise HTTPException(422, "hasta 8 tamanos por consulta")
        return vols

    @app.get("/api/anuncio/curva")
    def anuncio_curva(sizes: str = "1000,3000,5000", asset: str = "USDT",
                      fiat: str = "ARS",
                      venues: str = "binancep2p,okexp2p,bybitp2p"):
        """Que aviso PUBLICO y donde lo cierro, segun el tamano del ticket.

        Distinto de /api/estrategia/curva, que responde que jugada hago tomando
        las dos patas. Aca una pata es un aviso mio: gano por un tick al mejor
        rival que atienda una orden de ese tamano (los rivales chicos no
        compiten por un ticket grande, asi que el precio mejora), y la otra pata
        se cierra TOMANDO el libro del venue que mas convenga.

        El neto NO es el ciclo de publicar las dos puntas en el mismo venue: esa
        jugada no se opera. Es una sola comision de publicar, mas el fee de
        tomador de donde cierro, mas el de red si hay que mover la cripto.
        """
        import time as _t
        from dataclasses import asdict
        from core import ad_curve, arb_matrix
        from core.criptoya import fetch_payload
        from core.fees import por_modo
        from core.p2p_depth import compute_depth_quote
        from core.strategy import venue_liquido

        vols = _sizes(sizes)
        pedidos = [v.strip() for v in venues.split(",") if v.strip()]
        todos = _libros_p2p(asset, fiat)
        libros = {k: v for k, v in todos.items() if k in pedidos}

        # Referencia para valuar el ticket en ARS: el medio entre las dos mejores
        # puntas del libro. Alcanza para decidir que avisos entran en el filtro.
        precios_ref: dict[str, float] = {}
        for venue, (buy, sell) in libros.items():
            pb = [float(a.price) for a in buy if a.price]
            ps = [float(a.price) for a in sell if a.price]
            if pb and ps:
                precios_ref[venue] = (min(pb) + max(ps)) / 2
            elif pb or ps:
                precios_ref[venue] = (min(pb) if pb else max(ps))

        # Donde puedo cerrar la otra pata, por tamano: el precio ejecutable
        # cambia con el ticket, asi que se calcula una vez por cada uno. Solo
        # entran las puntas que mueven volumen: cerrar es TOMAR, y tomar contra
        # un libro vacio no es una jugada, es un numero.
        nowt = _t.time()
        cex_venues = set(config.CRIPTOYA_ARBITRAGE_WHITELIST) - set(arb_matrix.P2P_DEPTH_VENUES)
        cierres: dict[float, list] = {}
        for vol in vols:
            depth = {}
            for name, (buy, sell) in todos.items():
                q = compute_depth_quote(buy, sell, vol,
                                        fee_por_orden=_fee_por_orden(name, asset))
                if q["ask"] or q["bid"]:
                    depth[name] = q
            try:
                payload = fetch_payload(asset, fiat, vol)
            except Exception:
                payload = {}
            fee_modo = por_modo(fees_by_venue=config.FEE_P2P_BY_MODE, volume=vol,
                                asset=asset, flat_assets=config.TAKER_FLAT_ASSETS)
            opciones = []
            for v in arb_matrix.build_venues(
                    depth, payload, cex_venues=cex_venues,
                    blacklist=config.CRIPTOYA_BLACKLIST,
                    max_age_min=config.MAX_QUOTE_AGE_MIN, now=nowt,
                    p2p_sin_profundidad=config.P2P_SIN_PROFUNDIDAD):
                opciones.append(ad_curve.Cierre(
                    venue=v.name,
                    ask=v.ask if venue_liquido(v, "ask") else None,
                    bid=v.bid if venue_liquido(v, "bid") else None,
                    fee_tomando_pct=arb_matrix.fee_pata(
                        v.name, "tomando", config.FEE_PCT_BY_VENUE, fee_modo),
                ))
            cierres[vol] = opciones

        maker = {v: f.get("maker_pct", 0.0)
                 for v, f in config.FEE_P2P_BY_MODE.items()}
        out = ad_curve.curva(
            libros=libros, volumes=vols, precios_ref=precios_ref, maker_pct=maker,
            cierres=cierres, network_fee_pct=float(config.STRATEGY_NETWORK_FEE_PCT),
            tick=float(config.TICK_ARS), floor=float(config.PRICE_FLOOR_ARS),
            ceil=float(config.PRICE_CEIL_ARS),
            puede_compra=config.P2P_PUEDE_PUBLICAR_COMPRA,
            puede_venta=config.P2P_PUEDE_PUBLICAR_VENTA,
        )
        return {
            "asof": _t.time(), "asset": asset, "fiat": fiat, "sizes": vols,
            "venues": {v: [asdict(n) for n in niveles] for v, niveles in out.items()},
            # Ausente = habilitado. Lo unico que se anota es lo bloqueado.
            "habilitado_compra": {
                v: bool(config.P2P_PUEDE_PUBLICAR_COMPRA.get(v, True)) for v in out
            },
            "habilitado_venta": {
                v: bool(config.P2P_PUEDE_PUBLICAR_VENTA.get(v, True)) for v in out
            },
        }

    @app.get("/api/estrategia")
    def estrategia(asset: str = "USDT", fiat: str = "ARS", volume: float = 1000.0):
        """Mejor jugada de spread ahora (LA mejor + la de Binance + 2 alternativas)."""
        import time as _t
        from core.criptoya import fetch_payload

        key = (asset, fiat, volume)
        nowt = _t.time()
        cached = _estrategia_cache.get(key)
        if cached is not None and nowt - cached[0] < 30:
            return cached[1]

        libros = _libros_p2p(asset, fiat)
        try:
            payload = fetch_payload(asset, fiat, volume)
        except Exception:
            payload = {}
        out = _estrategia_de(libros, payload, volume, nowt, asset)
        _estrategia_cache[key] = (nowt, out)
        return out

    @app.get("/api/merchant")
    def merchant():
        """Progreso hacia el Comerciante Verificado de Binance P2P.

        Sólo los 3 requisitos que se pueden medir con trades.db. Si el precio de
        BTC no responde, los dos de volumen vuelven en FALTA: no se estiman.
        """
        import time as _t
        from dataclasses import asdict
        from datetime import date as _date
        from core.merchant import progreso

        try:
            q = btc_spot()
            btc_usd = (float(q["ask"]) + float(q["bid"])) / 2 if q else None
        except Exception:
            btc_usd = None

        p = progreso(
            db.all_movements(),
            hoy=_date.today(),
            btc_usd=btc_usd,
            ops_meta=config.MERCHANT_OPS_30D,
            vol_30d_meta=config.MERCHANT_VOL_30D_BTC,
            vol_hist_meta=config.MERCHANT_VOL_HIST_BTC,
            ventana_dias=config.MERCHANT_VENTANA_DIAS,
        )
        return {
            "asof": _t.time(),
            "btc_usd": p.btc_usd,
            "desde": p.desde.isoformat() if p.desde else None,
            "ventana_dias": p.ventana_dias,
            "requisitos": [asdict(r) for r in p.requisitos],
        }

    _vhoy_cache: dict = {}

    @app.get("/api/verificado/hoy")
    def verificado_hoy(ticket: float = 160000.0, fresh: int = 0):
        """La vuelta que conviene AHORA en Binance con un ticket dado (tarjeta "Hoy").

        Libro de Binance en vivo + ops de hoy de trades.db. Si Binance no responde
        los dos lados vuelven en null: no se estima. Cache 30 s por ticket.
        """
        import time as _t
        from dataclasses import asdict
        from datetime import date as _date
        from core.verificado_hoy import plan_vuelta

        key = round(float(ticket))
        nowt = _t.time()
        cached = _vhoy_cache.get(key)
        if not fresh and cached is not None and nowt - cached[0] < 30:
            return cached[1]

        fetcher = p2p_fetchers.get("binance")
        if fetcher is None:
            raise HTTPException(404, "No hay fetcher de Binance P2P")
        try:
            te_venden = fetcher("USDT", "ARS", "BUY", rows=20)
            te_compran = fetcher("USDT", "ARS", "SELL", rows=20)
        except Exception as exc:
            raise HTTPException(502, f"No pude leer Binance P2P: {exc}")
        # Mis avisos no son ni la punta ni algo que pueda tomar.
        from core.puntas import sin_mios
        te_venden = sin_mios(te_venden, config.MIS_NICKS_P2P)
        te_compran = sin_mios(te_compran, config.MIS_NICKS_P2P)
        precios = [a.price for a in te_venden + te_compran if a.price > 0]
        if not precios:
            raise HTTPException(502, "Binance P2P devolvió el libro vacío")
        fx = sorted(precios)[len(precios) // 2]
        fees = config.FEE_P2P_BY_MODE.get("binancep2p", {})

        p = plan_vuelta(
            te_venden, te_compran, ticket_ars=float(ticket), fx=fx,
            maker_pct=float(fees.get("maker_pct", 0.0)),
            taker_flat=float(fees.get("taker_flat_quote", 0.0)),
            movimientos=db.all_movements(), hoy=_date.today(),
            ops_meta=config.MERCHANT_OPS_30D, ventana_dias=config.MERCHANT_VENTANA_DIAS,
        )
        out = asdict(p)
        out.update({"asof": nowt, "fx": fx,
                    "maker_pct": fees.get("maker_pct"), "taker_flat": fees.get("taker_flat_quote"),
                    "avisos_te_venden": len(te_venden), "avisos_te_compran": len(te_compran)})
        _vhoy_cache[key] = (nowt, out)
        return out

    _puntas_cache: dict = {}

    @app.get("/api/puntas")
    def puntas(venues: str = "binance,kucoin,bybit", tanda: float = 1000.0,
               stock_min: float = 100.0, mis: str = "", tol: float = 1.0,
               priorizar: str = "binancep2p", fresh: int = 0):
        """A qué precio se PUBLICA hoy en cada venue, de los dos lados, y cuál es
        el cruce que más deja neto de comisiones y fee de red.

        `tanda` es el tamaño de la transferencia entre venues (el flat de red se
        reparte ahí, no en cada operación). Un venue que no responde sale con los
        dos lados en null: no se estima. Cache 30 s.

        `priorizar` pone adelante los cruces que tocan ese venue aunque dejen
        menos: mientras se persigue el Verificado, una ruta que no pasa por
        Binance no suma ninguna operación. El mejor de los que NO lo tocan sale
        aparte en `fuera_objetivo`, para no esconderlo.

        `mis` son los avisos propios publicados, para saber si todavía son la
        punta: "venue:lado:precio" separados por coma, ej.
        "binance:venta:1594,kucoin:compra:1584.15". No se cachea con el resto
        porque el precio propio cambia sin que cambie el libro. `tol` es cuánto
        se puede mover el libro (en ARS) antes de avisar.
        """
        import time as _t
        from dataclasses import asdict

        from core.puntas import puntas_de, ranking_cruces

        P2P_KEY = {"binance": "binancep2p", "okx": "okexp2p", "bybit": "bybitp2p",
                   "bitget": "bitgetp2p", "kucoin": "kucoinp2p"}
        pedidos = [v.strip().lower() for v in venues.split(",") if v.strip()]
        key = (tuple(pedidos), round(float(tanda)), round(float(stock_min)),
               priorizar or "")
        nowt = _t.time()
        cached = _puntas_cache.get(key)
        if not fresh and cached is not None and nowt - cached[0] < 30:
            out = dict(cached[1])
            out["avisos"] = _evaluar_mis(mis, out["puntas"], P2P_KEY, float(tol),
                                         out["mios"] if config.MIS_NICKS_P2P else None)
            return out

        libros: dict[str, dict] = {}
        caidos: list[str] = []
        for ex in pedidos:
            fetcher = p2p_fetchers.get(ex)
            venue = P2P_KEY.get(ex, ex)
            if fetcher is None:
                caidos.append(venue)
                continue
            try:
                libros[venue] = {"te_venden": fetcher("USDT", "ARS", "BUY", rows=20),
                                 "te_compran": fetcher("USDT", "ARS", "SELL", rows=20)}
            except Exception:
                caidos.append(venue)
        if not libros:
            raise HTTPException(502, "Ningún libro P2P respondió")

        ps = puntas_de(libros, stock_min=float(stock_min), excluir=config.MIS_NICKS_P2P)
        from core.puntas import precio_propio
        mios = {v: {"compra": precio_propio(l["te_compran"], config.MIS_NICKS_P2P, mas_caro=True),
                    "venta": precio_propio(l["te_venden"], config.MIS_NICKS_P2P, mas_caro=False)}
                for v, l in libros.items()}
        maker = {v: f.get("maker_pct", 0.0) for v, f in config.FEE_P2P_BY_MODE.items()}
        cruces = ranking_cruces(ps, maker_pct=maker,
                                fee_red_usdt=config.FEE_RED_RETIRO_USDT,
                                tanda_usdt=float(tanda),
                                stock_min_usdt=float(stock_min),
                                priorizar=priorizar or None)
        # El mejor de los que no tocan el venue priorizado, y sólo si deja más
        # que el que sí lo toca: si no, no hay nada que contar.
        fuera = None
        if priorizar and cruces:
            sin = [c for c in cruces if priorizar not in (c.comprar_en, c.vender_en)]
            if sin and sin[0].neto_ars_por_usdt > cruces[0].neto_ars_por_usdt:
                fuera = asdict(sin[0])
        out = {"asof": nowt, "tanda_usdt": float(tanda), "stock_min": float(stock_min),
               "puntas": [asdict(x) for x in ps],
               "cruces": [asdict(c) for c in cruces[:5]],
               "fuera_objetivo": fuera, "priorizar": priorizar,
               "caidos": caidos, "mios": mios}
        _puntas_cache[key] = (nowt, out)
        out = dict(out)
        out["avisos"] = _evaluar_mis(mis, out["puntas"], P2P_KEY, float(tol),
                                     mios if config.MIS_NICKS_P2P else None)
        return out

    @app.get("/api/dollar/ta")
    def dollar_ta_endpoint(window: int = 200):
        """Análisis técnico del USDT/ARS (MA50/200, RSI) + veredicto estoquear/vender."""
        try:
            return dollar_ta(window)
        except Exception as exc:
            logger.exception("Falló el análisis técnico del dólar")
            raise HTTPException(502, f"No pude calcular el análisis técnico: {exc}")

    @app.get("/api/spread/now")
    def spread_now_endpoint(asset: str = "USDT"):
        """Foto del spread {asset}/ARS ahora: best ask/bid por exchange + mejor
        cross. asset = USDT (default) | BTC."""
        pedido = (asset or "").strip().upper()
        if pedido not in config.SPREAD_ASSETS:
            # Caer a USDT sería contestar el precio de otra cosa sin avisar.
            raise HTTPException(
                400, f"No sé leer el spread de {asset!r}. "
                     f"Activos: {', '.join(config.SPREAD_ASSETS)}.")
        try:
            return spread_now(pedido)
        except Exception as exc:
            logger.exception("Falló el resumen de spread")
            raise HTTPException(502, f"No pude leer el spread: {exc}")

    @app.get("/api/cotizacion")
    def cotizacion_endpoint(asset: str = "USDT", size: float | None = None,
                            margen: float | None = None, top: int = 3):
        """Cotización al cliente de las DOS puntas, con precio ejecutable.
        asset = USDT | BTC; size = monto en cripto; margen = % sobre la base."""
        pedido = (asset or "").strip().upper()
        if pedido not in config.SPREAD_ASSETS:
            raise HTTPException(
                400, f"No sé cotizar {asset!r}. "
                     f"Activos: {', '.join(config.SPREAD_ASSETS)}.")
        monto = (config.CRIPTOYA_VOLUME_BY_ASSET.get(pedido, config.CRIPTOYA_VOLUME)
                 if size is None else float(size))
        if monto <= 0:
            raise HTTPException(400, "El monto tiene que ser mayor a cero.")
        pct = config.COTIZA_MARGEN_PCT if margen is None else float(margen)
        try:
            return cotizacion(asset=pedido, size=monto, margin_pct=pct,
                              top=max(1, min(int(top), 10)))
        except Exception as exc:
            logger.exception("Falló la cotización")
            raise HTTPException(502, f"No pude cotizar: {exc}")

    @app.post("/api/sync/request")
    def sync_request():
        """El dashboard pide un sync. Encola (o reusa) un job y devuelve su id."""
        job = sync_jobs.request()
        return {"job_id": job.job_id, "status": job.status}

    @app.get("/api/sync/status")
    def sync_status(job_id: str):
        """El dashboard consulta el estado del job (con timeouts derivados)."""
        v = sync_jobs.view(job_id)
        if v is None:
            raise HTTPException(404, "No existe ese job de sync.")
        return v

    @app.get("/api/sync/poll")
    def sync_poll(x_sync_token: str = Header(None)):
        """El agente de la PC pregunta si hay un job. Lo reclama si lo hay."""
        if not sync_agent_token or x_sync_token != sync_agent_token:
            raise HTTPException(401, "Token de agente inválido.")
        job = sync_jobs.claim()
        return {"job_id": job.job_id if job else None}

    @app.post("/api/sync/result")
    def sync_result(payload: dict, x_sync_token: str = Header(None)):
        """El agente reporta el resultado del sync."""
        if not sync_agent_token or x_sync_token != sync_agent_token:
            raise HTTPException(401, "Token de agente inválido.")
        applied = sync_jobs.finish(
            payload.get("job_id", ""), bool(payload.get("ok")),
            result=payload.get("result"), error=payload.get("error"),
        )
        return {"applied": applied}

    @app.get("/api/agente/descargar")
    def descargar_agente():
        """Sirve el instalador .exe del agente para bajarlo desde el dashboard."""
        from pathlib import Path as _P
        if not _P(agente_exe_path).is_file():
            raise HTTPException(404, "El instalador todavía no fue publicado.")
        return FileResponse(agente_exe_path, filename="agente-arbitrador.exe",
                            media_type="application/octet-stream")

    @app.post("/api/captacion/chat")
    def captacion_chat_endpoint(payload: dict):
        """Chat con la IA de Captación de Clientes de ADA. Body: {messages:[...]}."""
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(422, "Mandá 'messages' como lista no vacía.")
        if messages[-1].get("role") != "user":
            raise HTTPException(422, "El último mensaje tiene que ser del usuario.")
        try:
            reply = captacion_chat(messages)
        except Exception as exc:
            logger.exception("Falló el chat de captación")
            raise HTTPException(502, f"No pude responder ahora, reintentá: {exc}")
        return {"reply": reply}

    return app
