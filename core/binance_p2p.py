"""Cliente read-only del historial P2P (C2C) de Binance y mapeo a Movement."""
import hashlib
import hmac
import time
from datetime import date, datetime, time as _time, timedelta
from decimal import Decimal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import requests

from .movements import Movement, Side, Source

BASE_URL = "https://api.binance.com"
PATH = "/sapi/v1/c2c/orderMatch/listUserOrderHistory"
TIME_PATH = "/api/v3/time"
AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Sin `startTimestamp`/`endTimestamp` Binance devuelve SOLO los últimos 30 días,
# por más que se le pidan 50 filas (medido el 2026-08-30: sin rango daba 11
# compras desde el 02/08 y 0 ventas; con rango apareció julio entero). Y no
# acepta ventanas más largas que eso, así que hay que partirlas.
MAX_VENTANA_DIAS = 25
ROWS_POR_PAGINA = 50


def _ms(d: date) -> int:
    """Fecha a epoch en ms, a medianoche hora Argentina."""
    return int(datetime.combine(d, _time.min, tzinfo=AR_TZ).timestamp() * 1000)


def sign(query: str, secret: str) -> str:
    """Firma HMAC-SHA256 (hex) del query string."""
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def _effective_commission(raw: dict) -> Decimal:
    """Comision real: Binance la pone en `commission` o, si es 0, en `takerCommission`."""
    comm = Decimal(str(raw.get("commission") or 0))
    taker = Decimal(str(raw.get("takerCommission") or 0))
    return comm if comm > 0 else taker


def order_to_movement(raw: dict) -> Movement:
    """Mapea una orden cruda del endpoint C2C a un Movement."""
    side = Side.COMPRA if raw["tradeType"].upper() == "BUY" else Side.VENTA
    gross = Decimal(str(raw["amount"]))
    commission = _effective_commission(raw)
    when = datetime.fromtimestamp(int(raw["createTime"]) / 1000, tz=AR_TZ).date()
    return Movement(
        side=side,
        date=when,
        order_id=str(raw["orderNumber"]),
        usd_gross=gross,
        commission=commission,
        usd_net=gross - commission,
        price=Decimal(str(raw["unitPrice"])),
        total_ars=Decimal(str(raw["totalPrice"])),
        exchange_coin=f"Binance / {raw['asset']}",
        bank=raw.get("payMethodName") or "",
        source=Source.BINANCE_API,
    )


class BinanceP2PClient:
    def __init__(self, api_key: str, api_secret: str, session=None,
                 base_url: str = BASE_URL, recv_window: int = 5000):
        self._key = api_key
        self._secret = api_secret
        self._session = session or requests.Session()
        self._base = base_url
        self._recv_window = recv_window
        self._time_offset_ms: int | None = None

    def _timestamp(self) -> int:
        """Timestamp en ms ajustado al server time de Binance.

        El reloj local suele estar adelantado y Binance solo tolera +1000ms
        (error -1021), así que sincronizamos el offset una vez y lo cacheamos.
        """
        if self._time_offset_ms is None:
            local_before = int(time.time() * 1000)
            resp = self._session.get(f"{self._base}{TIME_PATH}")
            resp.raise_for_status()
            server = resp.json().get("serverTime")
            self._time_offset_ms = int(server) - local_before if server else 0
        return int(time.time() * 1000) + self._time_offset_ms

    def _signed_get(self, path: str, params: dict) -> dict:
        params = dict(params)
        params["recvWindow"] = self._recv_window
        params["timestamp"] = self._timestamp()
        query = urlencode(params)
        signature = sign(query, self._secret)
        url = f"{self._base}{path}?{query}&signature={signature}"
        resp = self._session.get(url, headers={"X-MBX-APIKEY": self._key})
        resp.raise_for_status()
        return resp.json()

    def fetch_orders(self, trade_type: str, rows: int = ROWS_POR_PAGINA,
                     page: int = 1, start: date | None = None,
                     end: date | None = None) -> list[dict]:
        """Lista cruda de órdenes (campo `data`) para BUY o SELL.

        `start`/`end` acotan la ventana. Sin ellos Binance devuelve sólo los
        últimos 30 días.
        """
        params = {"tradeType": trade_type, "rows": rows, "page": page}
        if start is not None and end is not None:
            params["startTimestamp"] = _ms(start)
            params["endTimestamp"] = _ms(end)
        return self._signed_get(PATH, params).get("data", [])

    def fetch_orders_range(self, trade_type: str, desde: date,
                           hasta: date) -> list[dict]:
        """Todas las órdenes entre `desde` y `hasta`, partiendo la ventana y
        paginando. Deduplica por `orderNumber`."""
        vistas: dict[str, dict] = {}
        inicio = desde
        while inicio < hasta:
            fin = min(inicio + timedelta(days=MAX_VENTANA_DIAS), hasta)
            page = 1
            while True:
                data = self.fetch_orders(trade_type, page=page,
                                         start=inicio, end=fin)
                for o in data:
                    vistas[str(o.get("orderNumber"))] = o
                if len(data) < ROWS_POR_PAGINA:
                    break
                page += 1
            inicio = fin
        return list(vistas.values())
