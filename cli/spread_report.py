"""Reporte del spread logger: a qué hora y día hay más spread USDT/ARS.

Lee el CSV que genera cli/spread_logger.py y resume el spread_pct agrupado
por hora del día (ART) y por día de la semana.
"""
import csv
from collections import defaultdict
from statistics import mean, median

# Orden y etiquetas castellano para los días (claves tal como las da %a en inglés).
WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_ES = {
    "Mon": "Lun", "Tue": "Mar", "Wed": "Mié", "Thu": "Jue",
    "Fri": "Vie", "Sat": "Sáb", "Sun": "Dom",
}


def load_rows(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def filter_outliers(rows: list[dict], min_pct: float, max_pct: float):
    """Descarta spreads no ejecutables (fantasmas spot/ilíquidos) fuera del rango.

    Devuelve (filas_validas, descartadas). Un spread tipo 20% entre mexc spot y
    mexcp2p no es arbitraje real, así que no debe contar para el análisis horario.
    """
    kept, dropped = [], 0
    for r in rows:
        try:
            pct = float(r["spread_pct"])
        except (KeyError, ValueError, TypeError):
            dropped += 1
            continue
        if min_pct <= pct <= max_pct:
            kept.append(r)
        else:
            dropped += 1
    return kept, dropped


def group_by(rows: list[dict], key: str) -> dict:
    """Agrupa spread_pct (float) por el campo `key`. Ignora filas inválidas."""
    g: dict = defaultdict(list)
    for r in rows:
        try:
            pct = float(r["spread_pct"])
            k = r[key]
        except (KeyError, ValueError, TypeError):
            continue
        g[k].append(pct)
    return dict(g)


def summarize(groups: dict) -> dict:
    """{clave: {n, mean, median, max}} por cada grupo no vacío."""
    out = {}
    for k, vals in groups.items():
        if vals:
            out[k] = {"n": len(vals), "mean": mean(vals),
                      "median": median(vals), "max": max(vals)}
    return out


def history_payload(raw_rows: list[dict], *, min_pct: float = -5.0,
                    max_pct: float = 5.0, recent: int = 24) -> dict:
    """Resumen del historial de spread para la API/dashboard (JSON-serializable).

    Stats por hora y por día usan datos filtrados (sin fantasmas); `recent`
    muestra las últimas lecturas crudas (más nuevas primero), marcando outliers.
    """
    rows, dropped = filter_outliers(raw_rows, min_pct, max_pct)

    def recent_list():
        out = []
        for r in reversed(raw_rows[-recent:]):
            try:
                pct = float(r["spread_pct"])
            except (KeyError, ValueError, TypeError):
                continue
            out.append({
                "timestamp": r.get("timestamp_art", ""),
                "spread_pct": pct,
                "ask_exchange": r.get("ask_exchange", ""),
                "bid_exchange": r.get("bid_exchange", ""),
                "best_ask": r.get("best_ask", ""),
                "best_bid": r.get("best_bid", ""),
                "outlier": not (min_pct <= pct <= max_pct),
            })
        return out

    if not rows:
        return {"samples": 0, "dropped": dropped, "from": None, "to": None,
                "by_hour": [], "by_weekday": [], "best_hours": [],
                "recent": recent_list()}

    hour_stats = summarize(group_by(rows, "hour"))
    wd_stats = summarize(group_by(rows, "weekday"))
    by_hour = [{"hour": int(h), **hour_stats[h]}
               for h in sorted(hour_stats, key=lambda x: int(x))]
    by_weekday = [{"weekday": d, "weekday_es": WEEKDAY_ES.get(d, d), **wd_stats[d]}
                  for d in sorted(wd_stats, key=lambda x: WEEKDAY_ORDER.index(x)
                                  if x in WEEKDAY_ORDER else 99)]
    best_hours = sorted(by_hour, key=lambda x: x["median"], reverse=True)[:3]
    return {
        "samples": len(rows), "dropped": dropped,
        "from": rows[0].get("timestamp_art"), "to": rows[-1].get("timestamp_art"),
        "by_hour": by_hour, "by_weekday": by_weekday,
        "best_hours": best_hours, "recent": recent_list(),
    }


def _print_hour_table(stats: dict) -> None:
    print(f"{'Hora':>5} {'n':>4} {'media%':>8} {'mediana%':>9} {'máx%':>7}")
    for h in sorted(stats, key=lambda x: int(x)):
        s = stats[h]
        print(f"{int(h):02d}:00 {s['n']:>4} {s['mean']:>8.3f} "
              f"{s['median']:>9.3f} {s['max']:>7.3f}")


def _print_weekday_table(stats: dict) -> None:
    print(f"{'Día':>5} {'n':>4} {'media%':>8} {'mediana%':>9} {'máx%':>7}")
    for d in sorted(stats, key=lambda x: WEEKDAY_ORDER.index(x)
                    if x in WEEKDAY_ORDER else 99):
        s = stats[d]
        print(f"{WEEKDAY_ES.get(d, d):>5} {s['n']:>4} {s['mean']:>8.3f} "
              f"{s['median']:>9.3f} {s['max']:>7.3f}")


def main(argv=None) -> None:
    import argparse
    p = argparse.ArgumentParser(description="Reporte de spread por hora/día.")
    p.add_argument("--in", dest="path", default="data/spread_log_usdt_ars.csv")
    p.add_argument("--max-spread", type=float, default=5.0,
                   help="descarta spreads > este %% (fantasmas spot/ilíquidos). Default 5")
    p.add_argument("--min-spread", type=float, default=-5.0,
                   help="descarta spreads < este %%. Default -5")
    args = p.parse_args(argv)

    try:
        raw = load_rows(args.path)
    except FileNotFoundError:
        print(f"No existe {args.path}. ¿Ya corrió el logger al menos una vez?")
        return
    if not raw:
        print("Todavía no hay muestras. Dejá el logger juntando datos un par de días.")
        return

    rows, dropped = filter_outliers(raw, args.min_spread, args.max_spread)
    if not rows:
        print(f"Las {len(raw)} muestras quedaron todas fuera del rango "
              f"[{args.min_spread}, {args.max_spread}]%. Subí --max-spread si querés verlas.")
        return

    nota = f"  ·  {dropped} descartada(s) por fantasma (>{args.max_spread}%)" if dropped else ""
    print(f"Muestras válidas: {len(rows)} de {len(raw)}{nota}  ·  "
          f"desde {rows[0]['timestamp_art']} hasta {rows[-1]['timestamp_art']}\n")

    hour_stats = summarize(group_by(rows, "hour"))
    print("=== Spread por hora del día (ART) ===")
    _print_hour_table(hour_stats)
    best = sorted(hour_stats.items(), key=lambda kv: kv[1]["median"], reverse=True)[:3]
    print("\nMejores horas para operar (por mediana de spread):")
    for h, s in best:
        print(f"  {int(h):02d}:00–{int(h):02d}:59  mediana {s['median']:.3f}%  (n={s['n']})")

    print("\n=== Spread por día de la semana ===")
    _print_weekday_table(summarize(group_by(rows, "weekday")))


if __name__ == "__main__":
    main()
