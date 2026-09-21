import pytest
from datetime import date
from decimal import Decimal
from core.movements import Movement, Side, Source
from core.sheet_writer import SheetWriter, MonthTabNotFound


class FakeWorksheet:
    def __init__(self, values):
        self._values = values
        self.batch_updates = []

    def get_all_values(self):
        return self._values

    def batch_update(self, data, value_input_option=None):
        self.batch_updates.append((data, value_input_option))


class FakeWorksheetNotFound(Exception):
    pass


class FakeSpreadsheet:
    def __init__(self, sheets):
        self._sheets = sheets  # dict: nombre -> FakeWorksheet

    def worksheet(self, name):
        if name not in self._sheets:
            raise FakeWorksheetNotFound(name)
        return self._sheets[name]


def make_movement(side=Side.COMPRA):
    return Movement(
        side=side, date=date(2026, 6, 1), order_id="999",
        usd_gross=Decimal("16.92"), commission=Decimal("0.07"),
        usd_net=Decimal("16.85"), price=Decimal("1477"),
        total_ars=Decimal("25000"), exchange_coin="Binance / USDT",
        bank="Lemon Cash", source=Source.SCREENSHOT,
    )


def test_escribe_compra_solo_columnas_de_entrada_desde_fila_3(monkeypatch):
    import core.sheet_writer as sw
    monkeypatch.setattr(sw.gspread, "WorksheetNotFound", FakeWorksheetNotFound)
    ws = FakeWorksheet([])  # pestaña "vacía" -> primera fila de datos = 3
    ss = FakeSpreadsheet({"Junio": ws})
    writer = SheetWriter(ss)

    rng = writer.write_movement(make_movement(Side.COMPRA))

    data, opt = ws.batch_updates[0]
    assert data == [
        {"range": "K3:N3", "values": [["01/06/26", "'999", 16.92, 0.07]]},
        {"range": "Q3:S3", "values": [[25000.0, "Binance / USDT", "Lemon Cash"]]},
    ]
    assert opt == "USER_ENTERED"
    assert rng == "K3"


def test_appendea_debajo_de_filas_llenas(monkeypatch):
    import core.sheet_writer as sw
    monkeypatch.setattr(sw.gspread, "WorksheetNotFound", FakeWorksheetNotFound)
    # 19 columnas; Venta (col A) llena en filas 3 y 4, vacía en la 5.
    grid = [
        ["Fecha"] + [""] * 18,        # fila 1
        [""] * 19,                     # fila 2 (totales)
        ["01/06/26"] + [""] * 18,      # fila 3
        ["02/06/26"] + [""] * 18,      # fila 4
        [""] * 19,                     # fila 5 (vacía)
    ]
    ws = FakeWorksheet(grid)
    ss = FakeSpreadsheet({"Junio": ws})
    writer = SheetWriter(ss)

    rng = writer.write_movement(make_movement(Side.VENTA))

    data, _ = ws.batch_updates[0]
    assert data[0]["range"] == "A5:D5"
    assert data[1]["range"] == "G5:I5"
    assert rng == "A5"


def test_tab_de_mes_inexistente_lanza_error(monkeypatch):
    import core.sheet_writer as sw
    monkeypatch.setattr(sw.gspread, "WorksheetNotFound", FakeWorksheetNotFound)
    ss = FakeSpreadsheet({})  # no existe "Junio"
    writer = SheetWriter(ss)
    with pytest.raises(MonthTabNotFound):
        writer.write_movement(make_movement())


if __name__ == "__main__":
    pytest.main([__file__])


# --- la planilla de Google es OPCIONAL: sin credenciales se guarda sólo en SQLite ---
def test_sin_credenciales_se_usa_un_escritor_nulo(tmp_path):
    from types import SimpleNamespace
    from core.sheet_writer import NullSheetWriter, writer_from_config
    cfg = SimpleNamespace(SHEET_ID="", GOOGLE_SERVICE_ACCOUNT_JSON=str(tmp_path / "no-existe.json"))
    w = writer_from_config(cfg)
    assert isinstance(w, NullSheetWriter)
    assert w.write_movement(object()) == "sin planilla"


def test_con_sheet_id_pero_sin_el_json_tambien_es_nulo(tmp_path):
    from types import SimpleNamespace
    from core.sheet_writer import NullSheetWriter, writer_from_config
    cfg = SimpleNamespace(SHEET_ID="abc", GOOGLE_SERVICE_ACCOUNT_JSON=str(tmp_path / "no-existe.json"))
    assert isinstance(writer_from_config(cfg), NullSheetWriter)
