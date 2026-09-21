"""Escritura de movimientos en la Google Sheet via gspread."""
import gspread
from google.oauth2.service_account import Credentials

from .movements import Movement
from .sheet_layout import BLOCKS, _col_letter, find_first_empty_row, movement_to_updates

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class MonthTabNotFound(Exception):
    """No existe la pestana del mes correspondiente al movimiento."""


class SheetWriter:
    def __init__(self, spreadsheet):
        self._ss = spreadsheet

    def write_movement(self, m: Movement) -> str:
        """Escribe las columnas de entrada del movimiento en su bloque/mes.

        No toca las columnas de formula (Comision, USD neto, Promedio). Devuelve la
        celda de inicio (ej. 'A3' o 'K3').
        """
        try:
            ws = self._ss.worksheet(m.month_tab())
        except gspread.WorksheetNotFound as exc:
            raise MonthTabNotFound(m.month_tab()) from exc

        block = BLOCKS[m.side]
        values = ws.get_all_values()
        row = find_first_empty_row(values, fecha_col=block.fecha_col)
        updates = movement_to_updates(m, row)
        ws.batch_update(
            [{"range": rng, "values": [vals]} for rng, vals in updates],
            value_input_option="USER_ENTERED",
        )
        return f"{_col_letter(block.fecha_col)}{row}"


class NullSheetWriter:
    """Escritor que no escribe: la planilla de Google es opcional. Sin
    credenciales los movimientos quedan sólo en la base SQLite."""

    def write_movement(self, m) -> str:
        return "sin planilla"


def writer_from_config(config):
    """SheetWriter si hay SHEET_ID y el JSON de la service account existe; si
    no, NullSheetWriter. Así el dashboard arranca recién clonado, sin Google."""
    from pathlib import Path
    ruta = str(getattr(config, "GOOGLE_SERVICE_ACCOUNT_JSON", "") or "")
    if not getattr(config, "SHEET_ID", "") or not ruta or not Path(ruta).is_file():
        return NullSheetWriter()
    return SheetWriter(open_spreadsheet(ruta, config.SHEET_ID))


def open_spreadsheet(service_account_json: str, sheet_id: str):
    """Abre la Sheet nativa con credenciales de service account."""
    creds = Credentials.from_service_account_file(service_account_json, scopes=_SCOPES)
    return gspread.authorize(creds).open_by_key(sheet_id)
