"""Precio spot BTC/USDT: la pata global de la ruta ARS→USDT→BTC.

Por qué no se lee de Binance (2026-08-22): `api.binance.com` responde 451 desde
el VPS (bloqueo por geolocalización), igual que la API privada. OKX y Kraken sí
responden. Medido contra el precio real de Binance ese día: OKX se desvió 0,009%
y el cruce de CriptoYa (BTC/ARS ÷ USDT/ARS) 0,024% y encima con 0,29% de ancho
falso. Por eso la fuente es OKX, con Kraken de respaldo.
"""
from core import spot


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Session:
    """Devuelve una respuesta por host; lo que no esté mapeado, explota."""

    def __init__(self, **por_host):
        self._por_host = por_host
        self.pedidos: list[str] = []

    def get(self, url, **kw):
        self.pedidos.append(url)
        for host, resp in self._por_host.items():
            if host in url:
                if isinstance(resp, Exception):
                    raise resp
                return resp
        raise AssertionError(f"URL no esperada: {url}")


OKX_OK = _Resp({"code": "0", "data": [
    {"instId": "BTC-USDT", "askPx": "77088.5", "bidPx": "77088.4"}]})

KRAKEN_OK = _Resp({"error": [], "result": {
    "XBTUSDT": {"a": ["76950.80000", "1", "1.000"],
                "b": ["76950.70000", "1", "1.000"]}}})


def test_lee_el_par_de_okx():
    q = spot.spot_quote("BTC", session=_Session(okx=OKX_OK))
    assert q == {"ask": 77088.5, "bid": 77088.4, "fuente": "okx"}


def test_cae_a_kraken_si_okx_falla():
    """Un venue caído no puede dejar sin cotizar el BTC: hay respaldo."""
    s = _Session(okx=RuntimeError("503"), kraken=KRAKEN_OK)
    q = spot.spot_quote("BTC", session=s)
    assert q == {"ask": 76950.8, "bid": 76950.7, "fuente": "kraken"}


def test_devuelve_none_si_fallan_las_dos():
    """None y no una excepción: el motor tiene que poder seguir sin la ruta
    sintética en vez de tumbar la cotización entera."""
    s = _Session(okx=RuntimeError("503"), kraken=RuntimeError("503"))
    assert spot.spot_quote("BTC", session=s) is None


def test_descarta_precios_absurdos():
    """Un 0 o un negativo multiplicado por el precio del USDT da una cotización
    de cero pesos. Antes de propagarlo, se descarta la fuente."""
    s = _Session(okx=_Resp({"code": "0", "data": [{"askPx": "0", "bidPx": "0"}]}),
                 kraken=KRAKEN_OK)
    assert spot.spot_quote("BTC", session=s)["fuente"] == "kraken"


def test_activo_sin_par_conocido_no_pega_a_la_red():
    """USDT no tiene par contra sí mismo, y cualquier otro activo todavía no
    está mapeado: se contesta None sin gastar una request."""
    s = _Session()
    assert spot.spot_quote("USDT", session=s) is None
    assert s.pedidos == []
