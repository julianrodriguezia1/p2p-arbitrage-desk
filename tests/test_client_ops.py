from datetime import date
from decimal import Decimal

import pytest

from core.client_ops import normalize, resolve_client

CLIENTES = [
    {"id": 3, "name": "Pablo", "alias": ""},
    {"id": 4, "name": "Daniel", "alias": ""},
    {"id": 7, "name": "Martín Pérez", "alias": "Tincho"},
    {"id": 9, "name": "Daniela", "alias": ""},
]


def test_normalize_saca_acentos_mayusculas_y_espacios():
    assert normalize("  Martín  PÉREZ ") == "martin perez"
    assert normalize(None) == ""


def test_resuelve_por_nombre_exacto():
    c, cand = resolve_client("Daniel", CLIENTES)
    assert c["id"] == 4
    assert cand == []


def test_resuelve_ignorando_acentos():
    c, _ = resolve_client("martin perez", CLIENTES)
    assert c["id"] == 7


def test_resuelve_por_alias():
    c, _ = resolve_client("Tincho", CLIENTES)
    assert c["id"] == 7


def test_el_exacto_le_gana_al_prefijo():
    # "daniel" es prefijo de "daniela", pero el match exacto manda.
    c, cand = resolve_client("daniel", CLIENTES)
    assert c["id"] == 4
    assert cand == []


def test_prefijo_ambiguo_devuelve_los_candidatos():
    c, cand = resolve_client("Dani", CLIENTES)
    assert c is None
    assert {x["id"] for x in cand} == {4, 9}


def test_resuelve_por_substring_cuando_es_unico():
    c, _ = resolve_client("perez", CLIENTES)
    assert c["id"] == 7


def test_cliente_inexistente():
    assert resolve_client("Rodolfo", CLIENTES) == (None, [])


def test_nombre_vacio_no_resuelve_nada():
    assert resolve_client("", CLIENTES) == (None, [])
    assert resolve_client(None, CLIENTES) == (None, [])


from core.client_ops import MISSING_QUESTIONS, build_client_movement, parse_amount

DANIEL = {"id": 4, "name": "Daniel", "alias": ""}
OPS = [
    {"opId": "man-daniel-20260805", "date": "2026-08-05", "bank": "Uala"},
    {"opId": "man-daniel-20260810", "date": "2026-08-10", "bank": "Uala"},
]
HOY = date(2026, 8, 12)
P = {"cliente": "Daniel", "lado": "vendi", "monto": 1000,
     "unidad": "usdt", "precio": 1578}


def test_parse_amount_entero_y_decimal():
    assert parse_amount(1578) == Decimal("1578")
    assert parse_amount("1578,50") == Decimal("1578.50")


def test_parse_amount_formato_argentino_completo():
    assert parse_amount("1.578.000,25") == Decimal("1578000.25")


def test_parse_amount_solo_separador_de_miles():
    # Caso que NO aparece en una captura pero sí cuando lo escribís a mano.
    assert parse_amount("1.578.000") == Decimal("1578000")
    assert parse_amount("$1.000") == Decimal("1000")


def test_parse_amount_ilegible_es_none():
    assert parse_amount("ni idea") is None
    assert parse_amount(None) is None


def test_arma_la_venta_con_la_convencion_otc():
    mov, missing, warns = build_client_movement(P, DANIEL, OPS, HOY)
    assert missing is None
    assert warns == []
    assert mov == {
        "side": "VENTA",
        "date": "2026-08-12",
        "order_id": "man-daniel-20260812",
        "usd_gross": "1000",
        "commission": "0",
        "usd_net": "1000",
        "price": "1578",
        "total_ars": "1578000.00",
        "exchange_coin": "OTC / USDT",
        "bank": "Uala",
    }


def test_le_compre_es_una_compra():
    mov, _, _ = build_client_movement({**P, "lado": "compre"}, DANIEL, OPS, HOY)
    assert mov["side"] == "COMPRA"


def test_banco_explicito_pisa_al_heredado():
    mov, _, _ = build_client_movement({**P, "banco": "Mercado Pago"}, DANIEL, OPS, HOY)
    assert mov["bank"] == "Mercado Pago"


def test_cliente_sin_historial_pide_el_banco():
    mov, missing, _ = build_client_movement(P, DANIEL, [], HOY)
    assert mov is None
    assert missing == "banco"


def test_order_id_sufija_la_segunda_del_dia():
    ops = OPS + [{"opId": "man-daniel-20260812", "date": "2026-08-12", "bank": "Uala"}]
    mov, _, _ = build_client_movement(P, DANIEL, ops, HOY)
    assert mov["order_id"] == "man-daniel-20260812-2"


def test_order_id_sufija_la_tercera_del_dia():
    ops = OPS + [
        {"opId": "man-daniel-20260812", "date": "2026-08-12", "bank": "Uala"},
        {"opId": "man-daniel-20260812-2", "date": "2026-08-12", "bank": "Uala"},
    ]
    mov, _, _ = build_client_movement(P, DANIEL, ops, HOY)
    assert mov["order_id"] == "man-daniel-20260812-3"


def test_slug_del_nombre_compuesto():
    cli = {"id": 7, "name": "Martín Pérez", "alias": "Tincho"}
    ops = [{"opId": "x", "date": "2026-08-01", "bank": "Uala"}]
    mov, _, _ = build_client_movement({**P, "cliente": "Tincho"}, cli, ops, HOY)
    assert mov["order_id"] == "man-martinperez-20260812"


def test_monto_en_pesos_se_convierte_a_usdt():
    mov, missing, _ = build_client_movement(
        {**P, "monto": 1578000, "unidad": "ars"}, DANIEL, OPS, HOY)
    assert missing is None
    assert mov["usd_gross"] == "1000.000000"
    assert mov["usd_net"] == "1000.000000"
    assert mov["total_ars"] == "1578000"


def test_pesos_sin_precio_pide_el_precio():
    mov, missing, _ = build_client_movement(
        {**P, "monto": 1578000, "unidad": "ars", "precio": None}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "precio"


def test_sin_precio_pide_el_precio():
    mov, missing, _ = build_client_movement({**P, "precio": None}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "precio"


@pytest.mark.parametrize("absurdo", [15, 99, 10001, 15780])
def test_precio_fuera_de_rango_se_repregunta(absurdo):
    mov, missing, _ = build_client_movement({**P, "precio": absurdo}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "precio"


@pytest.mark.parametrize("limite", [100, 10000])
def test_precio_en_el_borde_es_valido(limite):
    mov, missing, _ = build_client_movement({**P, "precio": limite}, DANIEL, OPS, HOY)
    assert missing is None
    assert mov["price"] == str(limite)


@pytest.mark.parametrize("malo", [0, None, "ni idea", -5])
def test_monto_invalido_se_repregunta(malo):
    mov, missing, _ = build_client_movement({**P, "monto": malo}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "monto"


@pytest.mark.parametrize("malo", [None, "", "cualquiera"])
def test_lado_desconocido_se_repregunta(malo):
    mov, missing, _ = build_client_movement({**P, "lado": malo}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "lado"


def test_fecha_explicita_manda_y_sufija_si_ya_hay_una():
    # El 10/08 ya tiene una op en OPS → la nueva sale con -2.
    mov, missing, _ = build_client_movement({**P, "fecha": "2026-08-10"}, DANIEL, OPS, HOY)
    assert missing is None
    assert mov["date"] == "2026-08-10"
    assert mov["order_id"] == "man-daniel-20260810-2"


@pytest.mark.parametrize("mala", ["2026-08-13", "2026-01-01", "el lunes", "13/08/2026"])
def test_fecha_invalida_se_repregunta(mala):
    mov, missing, _ = build_client_movement({**P, "fecha": mala}, DANIEL, OPS, HOY)
    assert mov is None
    assert missing == "fecha"


def test_avisa_si_el_precio_se_va_del_mercado():
    mov, missing, warns = build_client_movement(P, DANIEL, OPS, HOY, market_price=1800)
    assert missing is None
    assert len(warns) == 1
    assert "mercado" in warns[0]


def test_no_avisa_si_el_precio_esta_cerca_del_mercado():
    _, _, warns = build_client_movement(P, DANIEL, OPS, HOY, market_price=1583)
    assert warns == []


def test_sin_precio_de_mercado_no_hay_aviso():
    _, _, warns = build_client_movement(P, DANIEL, OPS, HOY, market_price=None)
    assert warns == []


def test_cada_campo_faltante_tiene_su_pregunta():
    for campo in ("lado", "monto", "precio", "fecha", "banco"):
        assert MISSING_QUESTIONS[campo].endswith("?")


from core.client_ops import apply_answer

PARCIAL = {"cliente": "Daniel", "lado": "vendi", "monto": 1000, "unidad": "usdt"}


def test_completa_el_precio():
    p = apply_answer(PARCIAL, "precio", "1578", HOY)
    assert p["precio"] == "1578"
    assert p["cliente"] == "Daniel"    # no pisa lo que ya se entendió


def test_completa_el_precio_en_formato_argentino():
    assert apply_answer(PARCIAL, "precio", "1.578,50", HOY)["precio"] == "1578.50"


def test_no_muta_los_params_originales():
    apply_answer(PARCIAL, "precio", "1578", HOY)
    assert "precio" not in PARCIAL


@pytest.mark.parametrize("texto", ["che dame el spread", "", "ni idea"])
def test_respuesta_que_no_es_un_precio_devuelve_none(texto):
    assert apply_answer(PARCIAL, "precio", texto, HOY) is None


def test_completa_el_monto_en_pesos_y_marca_la_unidad():
    p = apply_answer({"cliente": "Daniel"}, "monto", "1.578.000 pesos", HOY)
    assert p["monto"] == "1578000"
    assert p["unidad"] == "ars"


@pytest.mark.parametrize("texto", ["1000", "1000 usdt", "1.000 USDT"])
def test_monto_sin_mencion_de_pesos_es_usdt(texto):
    p = apply_answer({"cliente": "Daniel"}, "monto", texto, HOY)
    assert p["monto"] == "1000"
    assert p["unidad"] == "usdt"


@pytest.mark.parametrize("texto,esperado", [
    ("se los vendí", "vendi"), ("venta", "vendi"), ("le compré", "compre"),
    ("compra", "compre"),
])
def test_completa_el_lado(texto, esperado):
    assert apply_answer(PARCIAL, "lado", texto, HOY)["lado"] == esperado


def test_lado_ilegible_devuelve_none():
    assert apply_answer(PARCIAL, "lado", "no sé", HOY) is None


@pytest.mark.parametrize("texto,esperado", [
    ("hoy", "2026-08-12"), ("ayer", "2026-08-11"), ("2026-08-10", "2026-08-10"),
])
def test_completa_la_fecha(texto, esperado):
    assert apply_answer(PARCIAL, "fecha", texto, HOY)["fecha"] == esperado


@pytest.mark.parametrize("texto", ["el martes pasado", "cualquiera", ""])
def test_fecha_ilegible_devuelve_none(texto):
    assert apply_answer(PARCIAL, "fecha", texto, HOY) is None


@pytest.mark.parametrize("texto", ["Uala", "Mercado Pago", "Banco Galicia"])
def test_completa_el_banco(texto):
    assert apply_answer(PARCIAL, "banco", texto, HOY)["banco"] == texto


@pytest.mark.parametrize("texto", [
    "che mejor decime cómo viene el spread ahora",   # una frase, no un banco
    "",
])
def test_banco_que_es_una_frase_devuelve_none(texto):
    assert apply_answer(PARCIAL, "banco", texto, HOY) is None


def test_campo_desconocido_devuelve_none():
    assert apply_answer(PARCIAL, "vaya_a_saber", "1578", HOY) is None
