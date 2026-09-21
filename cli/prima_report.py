"""Reporte del logger de prima: ¿cuándo se abre la punta del BTC?

Lee el CSV de cli/prima_logger.py y resume la prima contra el USDT agrupada por
hora del día (ART) y por día de la semana. Es el equivalente de
cli/spread_report.py pero para la prima cripto/ARS.

    python -m cli.prima_report                      # todo lo logueado
    python -m cli.prima_report --asset ETH
    python -m cli.prima_report --incluir-libros-flacos
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from statistics import median

from core.prima_alt import MIN_COMPETIDORES

DEFAULT_CSV = Path("data/prima_log.csv")

WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
WEEKDAY_ES = {"Mon": "Lun", "Tue": "Mar", "Wed": "Mié", "Thu": "Jue",
              "Fri": "Vie", "Sat": "Sáb", "Sun": "Dom"}


def load_rows(path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _fnum(row: dict, key: str) -> float | None:
    """Celda numérica, o None si vino vacía. Vacío NO es cero."""
    v = (row.get(key) or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def filtrar_creibles(rows: list[dict]) -> list[dict]:
    """Saca las muestras cuya prima se apoyaba en un libro sin competencia.

    Promediar un 9,8% sostenido por 2 avisos con un 1,2% sostenido por 20
    envenena la mediana. Sin `n_ask` la muestra tampoco entra: no se sabe.
    """
    out = []
    for r in rows:
        n = _fnum(r, "n_ask")
        if n is not None and n >= MIN_COMPETIDORES:
            out.append(r)
    return out


def _stats(valores: list[float]) -> dict:
    return {
        "n": len(valores),
        "prima_mediana": median(valores),
        "prima_min": min(valores),
        "prima_max": max(valores),
    }


def resumen_activo(rows: list[dict]) -> dict[str, dict]:
    """Mediana / mínimo / máximo de la prima, por activo."""
    por_asset: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        v = _fnum(r, "prima_ask_pct")
        if v is not None:
            por_asset[r["asset"]].append(v)
    return {a: _stats(v) for a, v in por_asset.items() if v}


def _agrupar(rows: list[dict], asset: str, key: str) -> dict[str, list[float]]:
    g: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        if r.get("asset") != asset:
            continue
        v = _fnum(r, "prima_ask_pct")
        if v is not None:
            g[r[key]].append(v)
    return g


def por_hora(rows: list[dict], asset: str) -> list[tuple[int, dict]]:
    g = _agrupar(rows, asset, "hour")
    return sorted(((int(h), _stats(v)) for h, v in g.items()), key=lambda t: t[0])


def por_dia(rows: list[dict], asset: str) -> list[tuple[str, dict]]:
    g = _agrupar(rows, asset, "weekday")
    return sorted(((d, _stats(v)) for d, v in g.items()),
                  key=lambda t: WEEKDAY_ORDER.index(t[0]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--asset", default="BTC")
    ap.add_argument("--incluir-libros-flacos", action="store_true",
                    help="no filtra las muestras con menos de "
                         f"{MIN_COMPETIDORES} avisos detrás")
    args = ap.parse_args(argv)

    path = Path(args.csv)
    if not path.exists():
        print(f"no existe {path} — todavía no hay nada logueado.")
        return 1
    todas = load_rows(path)
    rows = todas if args.incluir_libros_flacos else filtrar_creibles(todas)
    if not rows:
        print(f"{len(todas)} filas leídas, ninguna con libro creíble "
              f"(>= {MIN_COMPETIDORES} avisos).")
        return 1

    descartadas = len(todas) - len(rows)
    print(f"{len(rows)} muestras" + (f" ({descartadas} descartadas por libro flaco)"
                                     if descartadas else ""))
    print(f"desde {todas[0]['timestamp_art']} hasta {todas[-1]['timestamp_art']}\n")

    print(f"{'activo':7}{'n':>6}{'prima mediana':>16}{'mín':>9}{'máx':>9}")
    for a, s in sorted(resumen_activo(rows).items(),
                       key=lambda kv: -kv[1]["prima_mediana"]):
        print(f"{a:7}{s['n']:>6}{s['prima_mediana']:>15.2f}%"
              f"{s['prima_min']:>8.2f}%{s['prima_max']:>8.2f}%")

    for titulo, datos, fmt in (
        (f"PRIMA DE {args.asset} POR HORA (ART)", por_hora(rows, args.asset),
         lambda k: f"{k:02d}h"),
        (f"PRIMA DE {args.asset} POR DÍA", por_dia(rows, args.asset),
         lambda k: WEEKDAY_ES.get(k, k)),
    ):
        if not datos:
            continue
        print(f"\n=== {titulo} ===")
        print(f"{'':6}{'n':>5}{'mediana':>10}{'mín':>9}{'máx':>9}")
        for k, s in datos:
            print(f"{fmt(k):6}{s['n']:>5}{s['prima_mediana']:>9.2f}%"
                  f"{s['prima_min']:>8.2f}%{s['prima_max']:>8.2f}%")

    print("\nprima = cuánto más caro que comprar USDT sale comprar el activo, "
          "en el mismo momento y venue.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
