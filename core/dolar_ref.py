"""Referencia del 'dólar cripto' que ven los clientes (el que muestran Dólar Hoy /
Ámbito). Fuente: dolarapi.com (compra/venta del USDT-ARS de mercado). Best-effort:
si no responde, devuelve None y el que llama omite la línea. `http_get` inyectable
para testear sin red, igual patrón que core/dollar_ta."""
from __future__ import annotations

DOLAR_CRIPTO_URL = "https://dolarapi.com/v1/dolares/cripto"


def parse_dolar_cripto(payload: dict) -> dict:
    """Normaliza el payload de dolarapi a {'compra': float, 'venta': float}."""
    return {"compra": float(payload["compra"]), "venta": float(payload["venta"])}


def fetch_dolar_cripto(http_get=None) -> dict | None:
    """Devuelve {'compra', 'venta'} del dólar cripto, o None si falla. `http_get`
    es un callable sin args que devuelve el payload (dict); default = dolarapi."""
    def _default():
        import json
        import urllib.request
        req = urllib.request.Request(
            DOLAR_CRIPTO_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; arbitrador/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.load(r)

    try:
        return parse_dolar_cripto((http_get or _default)())
    except Exception:
        return None
