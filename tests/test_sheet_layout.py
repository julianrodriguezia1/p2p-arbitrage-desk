from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source
from core.sheet_layout import (
    BLOCKS, DATA_START_ROW, movement_to_updates, find_first_empty_row, a1_range,
)


def make_movement(side=Side.COMPRA):
    return Movement(
        side=side, date=date(2026, 6, 1), order_id="2289483314363137",
        usd_gross=Decimal("16.92"), commission=Decimal("0.07"),
        usd_net=Decimal("16.85"), price=Decimal("1477"),
        total_ars=Decimal("25000"), exchange_coin="Binance / USDT",
        bank="Lemon Cash", source=Source.SCREENSHOT,
    )


def test_movement_to_updates_columnas_de_entrada_compra():
    # COMPRA base K(11): grupo1 K:N (fecha,id,bruto,comision), grupo2 Q:S; saltea O,P.
    # Montos como float; ID con apostrofo (texto).
    assert movement_to_updates(make_movement(Side.COMPRA), 3) == [
        ("K3:N3", ["01/06/26", "'2289483314363137", 16.92, 0.07]),
        ("Q3:S3", [25000.0, "Binance / USDT", "Lemon Cash"]),
    ]


def test_movement_to_updates_columnas_de_entrada_venta():
    # VENTA base A(1): grupo1 A:D (fecha,id,bruto,comision), grupo2 G:I; saltea E,F.
    assert movement_to_updates(make_movement(Side.VENTA), 5) == [
        ("A5:D5", ["01/06/26", "'2289483314363137", 16.92, 0.07]),
        ("G5:I5", [25000.0, "Binance / USDT", "Lemon Cash"]),
    ]


def test_bloques_compra_y_venta():
    assert BLOCKS[Side.VENTA].fecha_col == 1
    assert BLOCKS[Side.COMPRA].fecha_col == 11


def test_data_start_row_es_3():
    assert DATA_START_ROW == 3


def test_find_first_empty_row_arranca_en_3_por_defecto():
    # filas 1 (encabezado) y 2 (totales) se ignoran; datos desde la 3.
    values = [
        ["Fecha", "ID"],          # fila 1
        ["", "", "=SUM(...)"],    # fila 2 (totales)
        ["01/06/26", "x"],        # fila 3 (llena)
        ["", ""],                 # fila 4 (vacía)
    ]
    assert find_first_empty_row(values, fecha_col=1) == 4


def test_find_first_empty_row_appendea_si_todo_lleno():
    values = [["Fecha"], ["tot"], ["01/06/26"], ["02/06/26"]]
    assert find_first_empty_row(values, fecha_col=1) == 5


def test_a1_range():
    assert a1_range(11, 5, 3) == "K5:M5"
    assert a1_range(1, 3, 3) == "A3:C3"
    assert a1_range(17, 3, 3) == "Q3:S3"
