from decimal import Decimal

from core.capture_parser import _dec, _venue_key, build_movement, needs_exchange


def test_dec_normaliza_formatos():
    assert _dec("1556.50") == Decimal("1556.50")
    assert _dec("95.013,02") == Decimal("95013.02")   # formato AR
    assert _dec("233475") == Decimal("233475")
    assert _dec(150) == Decimal("150")
    assert _dec(None) is None
    assert _dec("") is None


def test_dec_saca_unidad_y_simbolo():
    # el modelo de visión suele devolver el número con la unidad tal como se ve
    assert _dec("95.013,02 ARS") == Decimal("95013.02")
    assert _dec("64,590770 USDT") == Decimal("64.590770")
    assert _dec("$1.234,56") == Decimal("1234.56")
    assert _dec("1556,50") == Decimal("1556.50")


def test_dec_ilegible_devuelve_none():
    # basura OCR → None (el llamador lo marca como warning, no rompe)
    assert _dec("chau") is None
    assert _dec("ARS") is None
    assert _dec("--") is None


def test_venue_key_detecta_exchange():
    assert _venue_key("Bybit") == "bybit"
    assert _venue_key("Lemon Cash") == "lemon"
    assert _venue_key("SaldoAr") == "saldoar"
    assert _venue_key("OKX") == "okx"
    assert _venue_key("Banco Galicia") == "otro"


def test_bybit_compra_sin_comision():
    raw = {
        "exchange": "Bybit", "side": "compra", "cantidad_usdt": "150",
        "precio": "1556.50", "monto_ars": "233475", "comision": "0",
        "order_id": "BYB-1", "date": "2026-07-08", "bank": "MercadoPago",
    }
    mov, warnings = build_movement(raw)
    assert mov["side"] == "COMPRA"
    assert mov["usd_gross"] == "150"
    assert mov["commission"] == "0"
    assert mov["usd_net"] == "150"
    assert mov["price"] == "1556.50"
    assert mov["total_ars"] == "233475"
    assert mov["exchange_coin"] == "Bybit / USDT"
    assert mov["bank"] == "MercadoPago"
    assert mov["order_id"] == "BYB-1"
    assert mov["date"] == "2026-07-08"
    assert warnings == []


def test_binance_comision_fija():
    raw = {
        "exchange": "Binance", "side": "venta", "cantidad_usdt": "100",
        "precio": "1560", "monto_ars": "156000", "comision": "0.14",
        "order_id": "BN-9", "date": "2026-07-08", "bank": "Uala",
    }
    mov, warnings = build_movement(raw)
    assert mov["side"] == "VENTA"
    assert mov["usd_gross"] == "100"
    assert mov["commission"] == "0.14"
    assert mov["usd_net"] == "99.86"          # gross - commission
    assert mov["exchange_coin"] == "Binance / USDT"


def test_saldoar_sin_mana():
    raw = {
        "exchange": "SaldoAr", "side": "compra", "cantidad_usdt": "200",
        "monto_ars": "312000", "order_id": "SA-3", "date": "2026-07-08",
        "bank": "Transferencia Pesos ARG",
    }
    mov, warnings = build_movement(raw)
    assert mov["usd_gross"] == "200"
    assert mov["usd_net"] == "200"
    assert mov["commission"] == "0"
    assert mov["total_ars"] == "312000"
    assert mov["exchange_coin"] == "SaldoAr / USDT"


def test_lemon_mana_div_099():
    # Caso confirmado: "Cambio por 95.013,02", cotiz 1.471.
    raw = {
        "exchange": "Lemon", "side": "compra", "cambio_por": "95013.02",
        "cotizacion": "1471", "cantidad_usdt": "64.590770",
        "lemon_screen": "total", "order_id": "LM-7", "date": "2026-07-08",
        "bank": "Lemon",
    }
    mov, warnings = build_movement(raw)
    assert mov["total_ars"] == "95972.75"
    assert mov["usd_gross"] == "65.243202"
    assert mov["commission"] == "0.652432"
    assert mov["usd_net"] == "64.590770"
    assert mov["price"] == "1471"
    assert mov["exchange_coin"] == "Lemon / USDT"
    assert warnings == []


def test_lemon_pata_no_carga():
    raw = {
        "exchange": "Lemon", "side": "compra", "cambio_por": "50000",
        "cotizacion": "1471", "lemon_screen": "pata", "order_id": "LM-8",
        "date": "2026-07-08", "bank": "Lemon",
    }
    mov, warnings = build_movement(raw)
    assert mov is None
    assert any("total" in w.lower() for w in warnings)


def test_lemon_cash_metodo_de_pago_no_se_confunde_con_exchange():
    # Op de Bybit pagada con "Lemon Cash": la visión metió "Lemon Cash" en
    # exchange, pero NO hay campos propios de Lemon (cambio_por/cotizacion/
    # lemon_screen) y SÍ los normales. Debe armar el movimiento igual (no
    # devolver None) y avisar que se verifique el exchange.
    raw = {
        "exchange": "Lemon Cash", "side": "compra", "cantidad_usdt": "99.8727",
        "precio": "1572", "monto_ars": "157000", "comision": "0",
        "order_id": "2080040913438056448", "date": "2026-07-22",
        "bank": "Lemon Cash",
    }
    mov, warnings = build_movement(raw)
    assert mov is not None
    assert mov["usd_gross"] == "99.8727"
    assert mov["total_ars"] == "157000"
    assert mov["price"] == "1572"
    assert mov["commission"] == "0"
    assert any("exchange" in w.lower() for w in warnings)


def test_lemon_real_sigue_andando_con_lemon_screen():
    # Un Lemon de verdad trae lemon_screen aunque falte cambio_por: no debe
    # caer al branch genérico (seguiría con la maña del ÷0,99).
    raw = {
        "exchange": "Lemon", "side": "compra", "cambio_por": "95013.02",
        "cotizacion": "1471", "cantidad_usdt": "64.590770",
        "lemon_screen": "total", "order_id": "LM-9", "date": "2026-07-08",
        "bank": "Lemon",
    }
    mov, warnings = build_movement(raw)
    assert mov["total_ars"] == "95972.75"      # maña Lemon aplicada
    assert mov["exchange_coin"] == "Lemon / USDT"
    assert warnings == []


def test_cross_check_agrega_warning():
    # gross*price = 233475 pero total dice 250000 → desvío ~7% > 1,5%.
    raw = {
        "exchange": "Bybit", "side": "compra", "cantidad_usdt": "150",
        "precio": "1556.50", "monto_ars": "250000", "comision": "0",
        "order_id": "BYB-2", "date": "2026-07-08", "bank": "MercadoPago",
    }
    mov, warnings = build_movement(raw)
    assert mov is not None
    assert any("no cierra" in w.lower() or "revisá" in w.lower() for w in warnings)


def test_needs_exchange_true_cuando_no_reconoce():
    raw = {"exchange": "Banco Galicia", "side": "compra", "cantidad_usdt": "100",
           "precio": "1500", "monto_ars": "150000"}
    mov, warnings = build_movement(raw)
    assert needs_exchange(raw, warnings) is True


def test_needs_exchange_true_cuando_lemon_es_metodo_de_pago():
    raw = {"exchange": "Lemon Cash", "side": "compra", "cantidad_usdt": "99.8727",
           "precio": "1572", "monto_ars": "157000", "comision": "0",
           "order_id": "X", "date": "2026-07-22", "bank": "Lemon Cash"}
    mov, warnings = build_movement(raw)
    assert mov is not None
    assert needs_exchange(raw, warnings) is True


def test_needs_exchange_false_para_exchanges_reconocidos():
    for ex in ("Bybit", "SaldoAr", "OKX", "Binance"):
        raw = {"exchange": ex, "side": "compra", "cantidad_usdt": "100",
               "precio": "1500", "monto_ars": "150000", "comision": "0",
               "order_id": "X", "date": "2026-07-22", "bank": "MP"}
        mov, warnings = build_movement(raw)
        assert needs_exchange(raw, warnings) is False


def test_needs_exchange_false_para_lemon_real():
    raw = {"exchange": "Lemon", "side": "compra", "cambio_por": "95013.02",
           "cotizacion": "1471", "cantidad_usdt": "64.590770",
           "lemon_screen": "total", "order_id": "LM-7", "date": "2026-07-08",
           "bank": "Lemon"}
    mov, warnings = build_movement(raw)
    assert needs_exchange(raw, warnings) is False


import base64
import json

from core.capture_parser import extract_fields, extract_fields_nvidia


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, content):
        self.calls = []
        self._content = content

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResp({"choices": [{"message": {"content": self._content}}]})


def test_extract_fields_arma_request_y_parsea(monkeypatch):
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "KEY123", raising=False)
    monkeypatch.setattr(config, "NVIDIA_BASE_URL", "https://nv/v1", raising=False)
    monkeypatch.setattr(config, "NVIDIA_VISION_MODEL", "vision-x", raising=False)

    content = '```json\n{"exchange":"Bybit","side":"compra","cantidad_usdt":"150"}\n```'
    sess = _FakeSession(content)
    out = extract_fields_nvidia(b"\x89PNGdata", session=sess)

    assert out["exchange"] == "Bybit"
    assert out["cantidad_usdt"] == "150"
    call = sess.calls[0]
    assert call["url"] == "https://nv/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer KEY123"
    assert call["json"]["model"] == "vision-x"
    # la imagen viaja como data URL base64 dentro del contenido del mensaje
    parts = call["json"]["messages"][0]["content"]
    img = next(p for p in parts if p["type"] == "image_url")
    assert base64.b64encode(b"\x89PNGdata").decode() in img["image_url"]["url"]


def test_extract_fields_json_plano(monkeypatch):
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    sess = _FakeSession('{"exchange":"Lemon","lemon_screen":"total"}')
    out = extract_fields_nvidia(b"x", session=sess)
    assert out["exchange"] == "Lemon"
    assert out["lemon_screen"] == "total"


def test_kucoin_es_venue_conocido():
    """KuCoin está en la whitelist del proyecto: la captura no debe quedar
    ambigua ni cuando el usuario aclara el exchange por texto."""
    assert _venue_key("KuCoin") == "kucoin"
    assert _venue_key("kucoin") == "kucoin"
    raw = {"exchange": "KuCoin", "side": "compra", "cantidad_usdt": "499",
           "precio": "1.591,1", "monto_ars": "793.958,9", "comision": "0",
           "order_id": "6a96e5e14a65dc0001429636", "date": "2026-09-01"}
    assert needs_exchange(raw, []) is False
    mov, warnings = build_movement(raw)
    assert mov["exchange_coin"] == "KuCoin / USDT"
    assert mov["usd_gross"] == "499" and mov["usd_net"] == "499"
    assert mov["total_ars"] == "793958.9"
    assert warnings == []


def test_prompt_prohibe_inventar_el_exchange():
    """La captura de KuCoin no dice su marca en ninguna parte: si el modelo no
    ve el nombre tiene que devolver null y que el bot pregunte, nunca adivinar
    (medido 2026-09-03: los modelos chicos contestaban 'Bybit' o 'Lemon')."""
    from core.capture_parser import _PROMPT
    assert "NO adivines" in _PROMPT
    assert "null" in _PROMPT


def test_exchange_null_pide_aclaracion():
    raw = {"exchange": None, "side": "compra", "cantidad_usdt": "499",
           "precio": "1591.1", "monto_ars": "793958.9"}
    mov, warnings = build_movement(raw)
    assert needs_exchange(raw, warnings) is True


def test_lectura_del_modelo_gratis_se_usa_si_las_cuentas_cierran():
    """El lector gratis va primero para no gastar suscripción de Claude."""
    sess = _FakeSession(json.dumps({
        "exchange": "KuCoin", "side": "compra", "cantidad_usdt": "499",
        "precio": "1591.1", "monto_ars": "793958.9", "comision": "0",
        "order_id": "6a96e5e14a65dc0001429636", "date": "2026-09-01"}))
    llamo_claude = []

    def claude(prompt, path):
        llamo_claude.append(1)
        return "{}"

    out = extract_fields(b"img", session=sess, ask_claude=claude)

    assert out["exchange"] == "KuCoin"
    assert len(sess.calls) == 1
    assert llamo_claude == []          # no se gastó Claude


def test_lectura_dudosa_del_gratis_reintenta_con_claude():
    """Si cantidad × precio no da el total, el modelo leyó mal algún número:
    ahí sí vale gastar una lectura de Claude antes de mostrarle basura."""
    sess = _FakeSession(json.dumps({
        "exchange": "KuCoin", "side": "compra", "cantidad_usdt": "499",
        "precio": "1591.1", "monto_ars": "123456.0",     # no cierra
        "order_id": "abc", "date": "2026-09-01"}))

    def claude(prompt, path):
        return json.dumps({"exchange": "KuCoin", "side": "compra",
                           "cantidad_usdt": "499", "precio": "1591.1",
                           "monto_ars": "793958.9", "comision": "0",
                           "order_id": "6a96e5e14a65dc0001429636",
                           "date": "2026-09-01"})

    out = extract_fields(b"img", session=sess, ask_claude=claude)

    assert out["monto_ars"] == "793958.9"
    assert out["order_id"] == "6a96e5e14a65dc0001429636"


def test_lectura_incompleta_del_gratis_reintenta_con_claude():
    sess = _FakeSession(json.dumps({"exchange": "KuCoin", "side": "compra",
                                    "cantidad_usdt": None, "precio": None,
                                    "monto_ars": None}))

    def claude(prompt, path):
        return json.dumps({"exchange": "KuCoin", "side": "compra",
                           "cantidad_usdt": "499", "precio": "1591.1",
                           "monto_ars": "793958.9", "comision": "0",
                           "order_id": "x", "date": "2026-09-01"})

    out = extract_fields(b"img", session=sess, ask_claude=claude)
    assert out["cantidad_usdt"] == "499"


def test_si_el_gratis_muere_410_usa_claude(monkeypatch):
    """El caso real del 26/08: el modelo se retiró y la API devolvía 410."""
    import core.capture_parser as cp

    def nvidia_410(image_bytes, *, session=None):
        raise RuntimeError("410 Gone")

    monkeypatch.setattr(cp, "extract_fields_nvidia", nvidia_410)
    out = extract_fields(b"img", ask_claude=lambda p, path: '{"exchange":"KuCoin","cantidad_usdt":"499","precio":"1591.1","monto_ars":"793958.9","order_id":"x","date":"2026-09-01"}')
    assert out["exchange"] == "KuCoin"


def test_cadena_de_modelos_gratis_antes_de_pagar(monkeypatch):
    """Un 503 del primer modelo gratuito no tiene que costar una lectura de
    Claude: se prueba el segundo gratis y sólo después se paga.
    Medido 2026-09-03: nemotron-omni falló 2 de 6 corridas (503 y JSON roto),
    kimi-k3 pasó 6 de 6."""
    import config
    import core.capture_parser as cp

    monkeypatch.setattr(config, "NVIDIA_VISION_MODELS",
                        ["gratis-1", "gratis-2"], raising=False)
    intentos = []

    def nvidia(image_bytes, *, session=None, model=None):
        intentos.append(model)
        if model == "gratis-1":
            raise RuntimeError("HTTP 503")
        return {"exchange": "KuCoin", "side": "compra", "cantidad_usdt": "499",
                "precio": "1591.1", "monto_ars": "793958.9",
                "order_id": "x", "date": "2026-09-01"}

    monkeypatch.setattr(cp, "extract_fields_nvidia", nvidia)

    def claude_no(prompt, path):
        raise AssertionError("no se debería haber gastado Claude")

    out = extract_fields(b"img", ask_claude=claude_no)

    assert out["exchange"] == "KuCoin"
    assert intentos == ["gratis-1", "gratis-2"]


def test_si_todos_los_gratis_fallan_paga_claude(monkeypatch):
    import config
    import core.capture_parser as cp

    monkeypatch.setattr(config, "NVIDIA_VISION_MODELS",
                        ["gratis-1", "gratis-2"], raising=False)

    def nvidia(image_bytes, *, session=None, model=None):
        raise RuntimeError("410 Gone")

    monkeypatch.setattr(cp, "extract_fields_nvidia", nvidia)
    out = extract_fields(b"img", ask_claude=lambda p, path: '{"exchange":"KuCoin"}')
    assert out["exchange"] == "KuCoin"
