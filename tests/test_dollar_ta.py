from datetime import date, timedelta
from decimal import Decimal

from core.dollar_ta import sma, rsi, analyze, fetch_history, parse_binance_klines


def test_sma_promedia_ultimos_n():
    assert sma([Decimal(1), Decimal(2), Decimal(3), Decimal(4)], 2) == Decimal("3.5")


def test_sma_sin_datos_suficientes_es_none():
    assert sma([Decimal(1)], 2) is None


def test_rsi_serie_creciente_es_100():
    vals = [Decimal(x) for x in range(1, 20)]  # estrictamente creciente
    assert rsi(vals, 14) == Decimal(100)


def test_rsi_serie_decreciente_es_0():
    vals = [Decimal(x) for x in range(20, 1, -1)]  # estrictamente decreciente
    assert rsi(vals, 14) == Decimal(0)


def test_rsi_sin_datos_suficientes_es_none():
    assert rsi([Decimal(1), Decimal(2)], 14) is None


def _serie(prices):
    """Lista (fecha, precio) diaria terminando hoy, en orden ascendente."""
    start = date.today() - timedelta(days=len(prices) - 1)
    return [(start + timedelta(days=i), Decimal(str(p))) for i, p in enumerate(prices)]


def test_analyze_precio_muy_por_encima_dice_vender():
    # 210 días planos en 1000 y un salto final fuerte -> caro vs MA50, RSI alto.
    prices = [1000] * 210 + [1100]
    out = analyze(_serie(prices))
    assert out["verdict"] == "vender"
    assert out["score"] > 0
    assert out["dev_ma50_pct"] > 0


def test_analyze_precio_muy_por_debajo_dice_estoquear():
    prices = [1000] * 210 + [900]
    out = analyze(_serie(prices))
    assert out["verdict"] == "estoquear"
    assert out["score"] < 0


def test_analyze_precio_en_la_media_es_neutral():
    # micro-oscilación 1000<->1001 para que RSI ~50 y desvío ~0 -> neutral
    prices = [1000 + (i % 2) for i in range(220)]
    out = analyze(_serie(prices))
    assert out["verdict"] == "neutral"
    assert -3 < out["dev_ma50_pct"] < 3


def test_analyze_recorta_series_a_window():
    prices = list(range(1, 301))  # 300 puntos
    out = analyze(_serie(prices), window=90)
    assert len(out["series"]) == 90
    assert out["extremes"]["high"]["price"] >= out["extremes"]["low"]["price"]


def _raw(rows):
    return [{"casa": "cripto", "compra": c, "venta": v, "fecha": f} for f, c, v in rows]


def test_fetch_history_normaliza_y_ordena():
    raw = _raw([("2024-01-03", 800, 820), ("2024-01-01", 700, 700)])
    out = fetch_history(lambda: raw)
    assert [d.isoformat() for d, _ in out] == ["2024-01-01", "2024-01-03"]
    assert out[1][1] == Decimal("810")  # (800+820)/2


def test_fetch_history_appendea_precio_de_hoy():
    raw = _raw([("2024-01-01", 700, 700)])
    hoy = date(2024, 1, 2)
    out = fetch_history(lambda: raw, today_price=Decimal("750"), today=hoy)
    assert out[-1] == (hoy, Decimal("750"))


def test_fetch_history_reemplaza_si_hoy_ya_existe():
    raw = _raw([("2024-01-02", 700, 700)])
    hoy = date(2024, 1, 2)
    out = fetch_history(lambda: raw, today_price=Decimal("760"), today=hoy)
    assert len(out) == 1
    assert out[-1] == (hoy, Decimal("760"))


def test_fetch_history_saltea_fila_no_numerica():
    raw = [
        {"casa": "cripto", "compra": "N/A", "venta": "N/A", "fecha": "2024-01-01"},
        {"casa": "cripto", "compra": 700, "venta": 700, "fecha": "2024-01-02"},
    ]
    out = fetch_history(lambda: raw)
    assert len(out) == 1
    assert out[0] == (date(2024, 1, 2), Decimal("700"))


# --- Binance klines (fuente primaria) ---

def _kline(open_ms, close):
    # Formato Binance: [openTime, open, high, low, close, volume, closeTime, ...]
    return [open_ms, "0", "0", "0", str(close), "100.0", open_ms + 1, "x", 1, "x", "x", "0"]


def test_parse_binance_klines_usa_cierre_y_ordena():
    raw = [
        _kline(1704067200000, "1005.0"),  # 2024-01-01 00:00 UTC
        _kline(1703980800000, "902.0"),   # 2023-12-31 00:00 UTC
    ]
    out = parse_binance_klines(raw)
    assert [d.isoformat() for d, _ in out] == ["2023-12-31", "2024-01-01"]
    assert out[1][1] == Decimal("1005.0")  # usa el cierre (índice 4)


def test_parse_binance_klines_saltea_malformada():
    raw = [
        ["solo-un-campo"],                       # muy corta -> IndexError
        _kline(1704067200000, "N/A"),            # cierre no numérico -> InvalidOperation
        _kline(1704153600000, "1010.0"),         # válida
    ]
    out = parse_binance_klines(raw)
    assert len(out) == 1
    assert out[0][1] == Decimal("1010.0")
