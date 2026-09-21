"""Logica pura de ubicacion y armado de filas en la planilla. Sin gspread ni red.

Estructura real de cada pestaña de mes, por lado (Venta/Compra):
- Fila 1: encabezados (combinados en 2 filas de alto para algunas columnas).
- Fila 2: fila de TOTALES (formulas SUM + la tasa 0,16%) — NO se toca.
- Fila 3 en adelante: filas de datos.

Por cada fila de datos, la planilla tiene FORMULAS en Comision, USD neto y Promedio;
esas columnas NO se escriben. Solo se cargan las 6 columnas de ENTRADA, que quedan
en dos grupos contiguos por lado:
    [Fecha, ID, USD bruto]   y   [Total ARS, Exchange/Cripto, Banco]
"""
from dataclasses import dataclass

from .movements import Movement, Side

DATA_START_ROW = 3  # fila 1 = encabezados, fila 2 = totales, datos desde la 3

# Offsets (desde la columna Fecha del bloque) de las 6 columnas de entrada.
_GRUPO2_OFFSET = 6  # tras Fecha(+0) ID(+1) USDbruto(+2) y las 3 de formula(+3..+5)


@dataclass(frozen=True)
class Block:
    """Bloque de columnas de un lado. `fecha_col` es 1-indexado (A=1, K=11)."""
    fecha_col: int


BLOCKS: dict[Side, Block] = {
    Side.VENTA: Block(fecha_col=1),    # entrada en A,B,C y G,H,I
    Side.COMPRA: Block(fecha_col=11),  # entrada en K,L,M y Q,R,S
}


def _col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def a1_range(first_col: int, row: int, length: int) -> str:
    """Rango A1 de una porcion de fila: ej. (11, 5, 3) -> 'K5:M5'."""
    return f"{_col_letter(first_col)}{row}:{_col_letter(first_col + length - 1)}{row}"


def find_first_empty_row(
    values: list[list[str]], fecha_col: int, start_row: int = DATA_START_ROW
) -> int:
    """Primera fila (1-indexada) cuya celda `Fecha` del bloque esta vacia."""
    col0 = fecha_col - 1
    row = start_row
    while True:
        idx = row - 1
        if idx >= len(values):
            return row
        cell = values[idx][col0] if col0 < len(values[idx]) else ""
        if cell.strip() == "":
            return row
        row += 1


def movement_to_updates(m: Movement, row: int) -> list[tuple[str, list]]:
    """Pares (rango_A1, valores) de las columnas de ENTRADA, salteando las formulas.

    Dos grupos contiguos: [Fecha, ID, USD bruto, Comision] y [Total ARS, Exchange, Banco].
    Se escribe la Comision real de Binance (col +3); USD neto y Promedio (col +4, +5)
    quedan como formula de la planilla, que recalcula sola al cambiar la Comision.

    Los montos van como `float` (no texto) para que Google Sheets los guarde como
    numeros sin importar el locale (en es-AR el separador decimal es la coma y un
    string con punto se interpretaria mal). El ID va con apostrofo inicial para
    forzar texto: un numero de 20 digitos como numero pierde precision.
    """
    base = BLOCKS[m.side].fecha_col
    grupo1 = [m.date.strftime("%d/%m/%y"), f"'{m.order_id}", float(m.usd_gross), float(m.commission)]
    grupo2 = [float(m.total_ars), m.exchange_coin, m.bank]
    return [
        (a1_range(base, row, 4), grupo1),
        (a1_range(base + _GRUPO2_OFFSET, row, 3), grupo2),
    ]
