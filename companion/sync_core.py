"""Núcleo del compañero de sync: fetch privado -> push al VPS (fuente única)."""
from typing import Callable

from core.movements import Movement

Fetcher = Callable[[], list[Movement]]
Pusher = Callable[..., tuple[int, str]]


def movement_to_payload(m: Movement) -> dict:
    """Serializa un Movement al formato que espera POST /api/movement."""
    return {
        "side": m.side.value,
        "date": m.date.isoformat(),
        "order_id": m.order_id,
        "usd_gross": str(m.usd_gross),
        "commission": str(m.commission),
        "usd_net": str(m.usd_net),
        "price": str(m.price),
        "total_ars": str(m.total_ars),
        "exchange_coin": m.exchange_coin,
        "bank": m.bank,
    }


def run_sync(fetchers: dict[str, Fetcher], push: Pusher, base_url: str) -> dict:
    """Por cada exchange: fetch -> push de cada movimiento. Cuenta 201/409/errores."""
    result: dict = {}
    for name, fetch in fetchers.items():
        nuevas = ya = 0
        errores: list[str] = []
        try:
            movimientos = fetch()
        except Exception as exc:  # fetch privado falló (red, 451, firma)
            result[name] = {"nuevas": 0, "ya": 0, "errores": [f"fetch: {exc}"]}
            continue
        for m in movimientos:
            status, text = push(movement_to_payload(m), base_url)
            if status == 201:
                nuevas += 1
            elif status == 409:
                ya += 1
            else:
                errores.append(f"#{m.order_id}: {status} {text}")
        result[name] = {"nuevas": nuevas, "ya": ya, "errores": errores}
    return result


def default_fetchers(config) -> dict[str, Fetcher]:
    """Construye los fetchers reales (clientes Binance/Bybit) sin invocarlos aún."""
    from core.binance_p2p import BinanceP2PClient
    from core.bybit_p2p import BybitP2PClient
    from cli.sync_binance import _fetch_all as binance_fetch
    from cli.sync_bybit import _fetch_all as bybit_fetch

    bclient = BinanceP2PClient(config.BINANCE_API_KEY, config.BINANCE_API_SECRET)
    yclient = BybitP2PClient(config.BYBIT_API_KEY, config.BYBIT_API_SECRET)
    return {
        "binance": lambda: binance_fetch(bclient),
        "bybit": lambda: bybit_fetch(yclient),
    }


def run_sync_default(config) -> dict:
    """Sync real: fetchers de config + push de push_movement + VPS_API_URL."""
    from cli.push_movement import push
    if not config.VPS_API_URL:
        raise RuntimeError("VPS_API_URL no configurada en .env")
    return run_sync(default_fetchers(config), push, config.VPS_API_URL)
