"""Control mensual de flujo de ARS por billetera / vía de pago (puro, sin red ni
HTML)."""
from __future__ import annotations

from collections import defaultdict

from core.movements import Side

UNCLASSIFIED = "Sin clasificar"


def _norm(label: str) -> str:
    return " ".join((label or "").split()).casefold()


def build_alias_lookup(alias_groups: dict[str, list[str]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for canonical, raws in alias_groups.items():
        for raw in raws:
            lookup[_norm(raw)] = canonical
    return lookup


def canonical_for(bank: str, lookup: dict[str, str],
                  unclassified: str = UNCLASSIFIED) -> tuple[str, bool]:
    key = _norm(bank)
    if key in lookup:
        return lookup[key], True
    return unclassified, False


def month_of(m) -> str:
    return m.date.strftime("%Y-%m")


def available_months(movements) -> list[str]:
    return sorted({month_of(m) for m in movements}, reverse=True)


def monthly_wallet_flows(movements, month, alias_groups, limits,
                         unclassified: str = UNCLASSIFIED) -> dict:
    lookup = build_alias_lookup(alias_groups)
    entra: dict[str, float] = defaultdict(float)
    sale: dict[str, float] = defaultdict(float)
    n_entra: dict[str, int] = defaultdict(int)
    n_sale: dict[str, int] = defaultdict(int)
    sin_mapear: set[str] = set()

    for m in movements:
        if month_of(m) != month:
            continue
        canonical, mapped = canonical_for(m.bank, lookup, unclassified)
        if not mapped:
            sin_mapear.add(m.bank)
        amount = float(m.total_ars)
        if m.side == Side.VENTA:
            entra[canonical] += amount
            n_entra[canonical] += 1
        else:
            sale[canonical] += amount
            n_sale[canonical] += 1

    result: dict = {}
    for w in set(entra) | set(sale):
        lim = limits.get(w, {})
        tope_in, tope_out = lim.get("in"), lim.get("out")
        e, s = entra[w], sale[w]
        result[w] = {
            "entra": e, "sale": s,
            "n_entra": n_entra[w], "n_sale": n_sale[w],
            "tope_in": tope_in, "tope_out": tope_out,
            "pct_in": round(e / tope_in * 100, 1) if tope_in else None,
            "pct_out": round(s / tope_out * 100, 1) if tope_out else None,
            "restante_in": tope_in - e if tope_in else None,
            "restante_out": tope_out - s if tope_out else None,
        }
    result["_sin_mapear"] = sorted(sin_mapear)
    return result
