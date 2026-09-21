from core.dolar_ref import parse_dolar_cripto, fetch_dolar_cripto

_PAYLOAD = {"moneda": "USD", "casa": "cripto", "nombre": "Cripto",
            "compra": 1557.69, "venta": 1565.46,
            "fechaActualizacion": "2026-07-13T20:55:00.000Z"}


def test_parse_dolar_cripto_normaliza():
    assert parse_dolar_cripto(_PAYLOAD) == {"compra": 1557.69, "venta": 1565.46}


def test_fetch_con_http_get_inyectado():
    got = fetch_dolar_cripto(http_get=lambda: _PAYLOAD)
    assert got == {"compra": 1557.69, "venta": 1565.46}


def test_fetch_devuelve_none_si_falla():
    def boom():
        raise RuntimeError("sin red")
    assert fetch_dolar_cripto(http_get=boom) is None


def test_fetch_devuelve_none_si_payload_incompleto():
    assert fetch_dolar_cripto(http_get=lambda: {"compra": 1557.69}) is None
