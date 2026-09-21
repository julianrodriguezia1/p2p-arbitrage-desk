"""CLI de cotización a cliente: pide precios al VPS y arma los 3 renglones."""
import json

import pytest

from cli.cotizar_cliente import plan_desde_vps, render

_COT_BTC = {
    "asset": "BTC",
    "precio_venta_cliente": 129657456.69,
    "buys": [{"venue": "binancep2p", "price": 129012394.72, "mode": "vía USDT",
              "stock": 0.178, "via": {"usdt_price": 1581.76, "spot_price": 81480.9,
                                      "fuente": "okx"}}],
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, payload):
        self.calls = []
        self._payload = payload

    def get(self, url, params=None, timeout=None):
        self.calls.append(params)
        return _FakeResp(self._payload)


def test_pide_la_cotizacion_dos_veces_ajustando_el_tamano():
    """El precio ejecutable depende del volumen: la primera pasada es un sondeo
    y la segunda va con el tamaño real del pedido del cliente."""
    sess = _FakeSession(_COT_BTC)
    plan, _ = plan_desde_vps("http://vps", ars=660000, asset="BTC",
                             margen_pct=0.5, spot_fee_pct=0.1, session=sess)

    assert len(sess.calls) == 2
    assert sess.calls[0]["size"] == 0.001                    # sondeo
    assert sess.calls[1]["size"] == pytest.approx(0.00509034, abs=1e-8)
    assert sess.calls[1]["margen"] == 0.5
    assert plan["venue"] == "binancep2p"
    assert plan["usdt_a_comprar"] == pytest.approx(415.18, abs=0.01)
    assert plan["ganancia_ars"] == pytest.approx(3285, abs=2)


def test_render_btc_muestra_todo_el_circuito():
    """Los 4 datos que el usuario pidió el 03/09: a cuánto compra el USDT, a
    cuánto el BTC, qué cotización le canta (en pesos Y en USDT) y cuánto BTC
    le llega al cliente."""
    sess = _FakeSession(_COT_BTC)
    plan, _ = plan_desde_vps("http://vps", ars=660000, asset="BTC",
                             margen_pct=0.5, spot_fee_pct=0.1,
                             fee_red=0.00002, session=sess)
    texto = render(plan, "Daniel")

    assert "Daniel" in texto
    assert "1. Comprás 415,18 USDT en binancep2p a 1.581,76" in texto
    assert "2. Comprás BTC en spot a 81.480,9 USDT" in texto
    assert "le llegan 0,00507034 BTC exactos" in texto   # ya neto del fee
    assert "LE DECÍS:" in texto
    assert "ARS por BTC" in texto
    assert "USDT por BTC" in texto                     # el precio en dólares
    assert "Ganás 3.285 ARS (0,50%)" in texto
    assert "el fee de red ya está pagado" in texto


def test_render_avisa_el_fee_de_red_en_el_renglon_del_retiro():
    sess = _FakeSession(_COT_BTC)
    plan, _ = plan_desde_vps("http://vps", ars=660000, asset="BTC",
                             margen_pct=0.5, spot_fee_pct=0.1,
                             fee_red=0.00002, session=sess)
    texto = render(plan)
    assert "0,00002" in texto
    assert "0,00509034 BTC" in texto                   # lo que sale de la cuenta


def test_render_usdt_no_habla_de_spot():
    cot = {"asset": "USDT", "precio_venta_cliente": 1589.73,
           "buys": [{"venue": "bybitp2p", "price": 1581.82, "mode": "directo",
                     "stock": 5000.0, "via": None}]}
    sess = _FakeSession(cot)
    plan, _ = plan_desde_vps("http://vps", ars=660000, asset="USDT",
                             margen_pct=0.5, spot_fee_pct=0.1, session=sess)
    texto = render(plan)

    assert "spot" not in texto.lower()
    assert "Ganás" in texto
    assert plan["ganancia_pct"] == pytest.approx(0.5, abs=0.001)


def test_avisa_cuando_la_punta_no_tiene_stock():
    cot = json.loads(json.dumps(_COT_BTC))
    cot["buys"][0]["stock"] = 0.0001          # menos de lo que hace falta
    sess = _FakeSession(cot)
    plan, _ = plan_desde_vps("http://vps", ars=660000, asset="BTC",
                             margen_pct=0.5, spot_fee_pct=0.1, session=sess)
    assert "menos de lo que necesitás" in render(plan)


def test_sin_puntas_de_compra_no_inventa():
    cot = {"asset": "BTC", "precio_venta_cliente": 129657456.69, "buys": []}
    sess = _FakeSession(cot)
    with pytest.raises(SystemExit):
        plan_desde_vps("http://vps", ars=660000, asset="BTC",
                       margen_pct=0.5, spot_fee_pct=0.1, session=sess)
