"""Cliente read-only del historial P2P de Bybit (v5) y mapeo a Movement."""
import hashlib
import hmac
import json
import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import requests

from .movements import Movement, Side, Source

BASE_URL = "https://api.bybit.com"
PATH = "/v5/p2p/order/simplifyList"
AR_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def sign_v5(timestamp: str, api_key: str, recv_window: str, body: str, secret: str) -> str:
    """Firma v5 de Bybit: HMAC-SHA256 hex de timestamp+api_key+recv_window+body."""
    pre = f"{timestamp}{api_key}{recv_window}{body}"
    return hmac.new(secret.encode(), pre.encode(), hashlib.sha256).hexdigest()


def _bank_from_payment(payment_type) -> str:
    """paymentType suele venir como lista (a veces vacía). Lo unimos a un string."""
    if isinstance(payment_type, list):
        return ", ".join(str(x) for x in payment_type)
    return str(payment_type) if payment_type else ""


def order_to_movement(raw: dict) -> Movement:
    """Mapea una orden P2P cruda de Bybit a un Movement."""
    side = Side.COMPRA if int(raw["side"]) == 0 else Side.VENTA
    gross = Decimal(str(raw["notifyTokenQuantity"]))
    commission = Decimal(str(raw["fee"]))
    when = datetime.fromtimestamp(int(raw["createDate"]) / 1000, tz=AR_TZ).date()
    return Movement(
        side=side,
        date=when,
        order_id=str(raw["id"]),
        usd_gross=gross,
        commission=commission,
        usd_net=gross - commission,
        price=Decimal(str(raw["price"])),
        total_ars=Decimal(str(raw["amount"])),
        exchange_coin=f"Bybit / {raw['tokenId']}",
        bank=_bank_from_payment(raw.get("paymentType")),
        source=Source.BYBIT_API,
    )


class BybitP2PClient:
    def __init__(self, api_key: str, api_secret: str, session=None,
                 base_url: str = BASE_URL, recv_window: int = 5000):
        self._key = api_key
        self._secret = api_secret
        self._session = session or requests.Session()
        self._base = base_url
        self._recv_window = recv_window

    def _signed_post(self, path: str, body_dict: dict) -> dict:
        body = json.dumps(body_dict, separators=(",", ":"))
        ts = str(int(time.time() * 1000))
        recv = str(self._recv_window)
        signature = sign_v5(ts, self._key, recv, body, self._secret)
        headers = {
            "X-BAPI-API-KEY": self._key,
            "X-BAPI-TIMESTAMP": ts,
            "X-BAPI-RECV-WINDOW": recv,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }
        resp = self._session.post(f"{self._base}{path}", data=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    def fetch_orders(self, page: int = 1, size: int = 30) -> list[dict]:
        body = self._signed_post(PATH, {"page": page, "size": size})
        return (body.get("result") or {}).get("items") or []

    def fetch_all_orders(self, size: int = 30) -> list[dict]:
        """Trae todas las órdenes recorriendo páginas hasta cubrir result.count."""
        out: list[dict] = []
        page = 1
        while True:
            body = self._signed_post(PATH, {"page": page, "size": size})
            res = body.get("result") or {}
            items = res.get("items") or []
            out.extend(items)
            count = int(res.get("count") or 0)
            if not items or len(out) >= count:
                break
            page += 1
        return out
