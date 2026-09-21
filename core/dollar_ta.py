"""Análisis técnico del USDT/ARS (dólar cripto). Funciones puras + fetch inyectable."""
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable


def parse_binance_klines(raw: list) -> list[tuple["date", Decimal]]:
    """Convierte klines de Binance (1d) a serie (fecha, precio_cierre), ascendente.

    Formato de cada kline: [openTime_ms, open, high, low, close, volume, ...].
    Usa el cierre (índice 4) como precio del día y openTime (índice 0, UTC) como
    fecha de la vela. Filas malformadas se saltean (no rompen).
    """
    serie: list[tuple[date, Decimal]] = []
    for k in raw:
        try:
            open_ms = int(k[0])
            close = Decimal(str(k[4]))
        except (KeyError, IndexError, TypeError, ValueError, InvalidOperation):
            continue
        d = datetime.fromtimestamp(open_ms / 1000, tz=timezone.utc).date()
        serie.append((d, close))
    serie.sort(key=lambda x: x[0])
    return serie


def fetch_history(
    http_get: "Callable[[], list[dict]]",
    *,
    today_price: Decimal | None = None,
    today: "date | None" = None,
) -> list[tuple["date", Decimal]]:
    """Baja ArgentinaDatos (vía http_get inyectado) y normaliza a (fecha, precio)."""
    raw = http_get()
    serie: list[tuple[date, Decimal]] = []
    for row in raw:
        try:
            compra = Decimal(str(row["compra"]))
            venta = Decimal(str(row["venta"]))
            fecha = date.fromisoformat(row["fecha"])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            continue
        serie.append((fecha, (compra + venta) / 2))
    serie.sort(key=lambda x: x[0])

    if today_price is not None:
        hoy = today or date.today()
        serie = [(d, p) for (d, p) in serie if d != hoy]
        serie.append((hoy, today_price))
        serie.sort(key=lambda x: x[0])
    return serie


def sma(values: list[Decimal], n: int) -> Decimal | None:
    """Media simple de los últimos `n` valores. None si no alcanzan."""
    if n <= 0 or len(values) < n:
        return None
    window = values[-n:]
    return sum(window, Decimal(0)) / Decimal(n)


def rsi(values: list[Decimal], n: int = 14) -> Decimal | None:
    """RSI clásico sobre los últimos `n` deltas. None si no alcanzan los datos."""
    if n <= 0 or len(values) < n + 1:
        return None
    deltas = [values[i] - values[i - 1] for i in range(len(values) - n, len(values))]
    gains = sum((d for d in deltas if d > 0), Decimal(0))
    losses = sum((-d for d in deltas if d < 0), Decimal(0))
    if losses == 0:
        return Decimal(100)
    if gains == 0:
        return Decimal(0)
    rs = (gains / Decimal(n)) / (losses / Decimal(n))
    return Decimal(100) - (Decimal(100) / (Decimal(1) + rs))


def _fmt(value: Decimal | float) -> str:
    """Formatea con 1 decimal y coma decimal (es-AR)."""
    return f"{float(value):.1f}".replace(".", ",")


def _clamp(value: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return max(lo, min(hi, value))


def analyze(
    series: list[tuple[date, Decimal]],
    *,
    ma_short: int = 50,
    ma_long: int = 200,
    rsi_period: int = 14,
    dev_threshold: Decimal = Decimal("3"),
    rsi_low: Decimal = Decimal("35"),
    rsi_high: Decimal = Decimal("65"),
    window: int = 200,
) -> dict:
    """Calcula indicadores + veredicto del USDT/ARS sobre una serie diaria."""
    series = sorted(series, key=lambda x: x[0])
    prices = [p for _, p in series]
    price = prices[-1] if prices else None

    ma_s = sma(prices, ma_short)
    ma_l = sma(prices, ma_long)
    rsi_val = rsi(prices, rsi_period)

    dev_s = ((price / ma_s) - 1) * 100 if (price and ma_s) else None
    dev_l = ((price / ma_l) - 1) * 100 if (price and ma_l) else None
    cross = None
    if ma_s is not None and ma_l is not None:
        cross = "golden" if ma_s >= ma_l else "death"

    # Veredicto: timing (desvío vs MA corta + RSI). Tendencia (cross) es contexto.
    verdict = "neutral"
    if dev_s is not None and rsi_val is not None:
        if dev_s >= dev_threshold or rsi_val > rsi_high:
            verdict = "vender"
        elif dev_s <= -dev_threshold or rsi_val < rsi_low:
            verdict = "estoquear"

    # Score -100..100 (positivo = caro/vender).
    score = Decimal(0)
    if dev_s is not None and rsi_val is not None:
        dev_comp = _clamp((dev_s / dev_threshold) * 50, Decimal(-100), Decimal(100))
        rsi_comp = _clamp(((rsi_val - 50) / 50) * 100, Decimal(-100), Decimal(100))
        score = _clamp((dev_comp + rsi_comp) / 2, Decimal(-100), Decimal(100))

    # Frase en español.
    if dev_s is None or rsi_val is None:
        phrase = "Todavía no hay suficiente historial para un veredicto confiable."
    else:
        donde = "por encima" if dev_s >= 0 else "por debajo"
        tend = {"golden": "alcista", "death": "bajista"}.get(cross, "indefinida")
        cola = {
            "vender": "→ caro, podés vender de más.",
            "estoquear": "→ barato, buen momento para estoquear.",
            "neutral": "→ en zona neutral.",
        }[verdict]
        phrase = (
            f"USDT {_fmt(abs(dev_s))}% {donde} de su MA{ma_short} y "
            f"RSI {_fmt(rsi_val)} {cola} Tendencia de fondo {tend}."
        )

    # Serie para el gráfico (con MA y RSI por punto), recortada a `window`.
    chart: list[dict] = []
    for i in range(len(series)):
        d, p = series[i]
        upto = prices[: i + 1]
        _ma50 = sma(upto, ma_short)
        _ma200 = sma(upto, ma_long)
        _rsi = rsi(upto, rsi_period)
        chart.append({
            "fecha": d.isoformat(),
            "price": float(p),
            "ma50": float(_ma50) if _ma50 is not None else None,
            "ma200": float(_ma200) if _ma200 is not None else None,
            "rsi": float(_rsi) if _rsi is not None else None,
        })
    if window and window > 0:
        chart = chart[-window:]

    hi = max(chart, key=lambda r: r["price"]) if chart else None
    lo = min(chart, key=lambda r: r["price"]) if chart else None

    return {
        "price": float(price) if price is not None else None,
        "ma50": float(ma_s) if ma_s is not None else None,
        "ma200": float(ma_l) if ma_l is not None else None,
        "dev_ma50_pct": float(dev_s) if dev_s is not None else None,
        "dev_ma200_pct": float(dev_l) if dev_l is not None else None,
        "rsi": float(rsi_val) if rsi_val is not None else None,
        "cross": cross,
        "verdict": verdict,
        "score": float(score),
        "phrase": phrase,
        "as_of": series[-1][0].isoformat() if series else None,
        "series": chart,
        "extremes": {
            "high": {"fecha": hi["fecha"], "price": hi["price"]} if hi else None,
            "low": {"fecha": lo["fecha"], "price": lo["price"]} if lo else None,
        },
    }
