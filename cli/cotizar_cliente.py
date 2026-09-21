"""Cotización a cliente en 3 renglones: qué comprás, qué le cotizás, qué ganás.

Pega a `/api/cotizacion` del VPS (fuente única de precios ejecutables) y traduce
la respuesta a los pasos concretos con `core.plan_cliente`.

    python -m cli.cotizar_cliente 660000 --asset BTC --cliente Daniel

BTC va SIEMPRE por `ARS → USDT (P2P) → BTC (spot)`: comprarlo por el libro P2P
sale ~1% más caro (ver `docs/investigacion-prima-btc-alts-ars.md`).
"""
import argparse
import sys

import requests

from core.plan_cliente import plan_para_cliente

# Arranque para estimar el tamaño del pedido en cripto: el precio ejecutable
# depende del volumen, así que se pide una cotización chica, se ve a cuánto
# está, y se vuelve a pedir con el tamaño real.
_SONDEO = {"BTC": 0.001, "USDT": 100.0}


def cotizar(base_url: str, asset: str, size: float, margen_pct: float,
            session=None) -> dict:
    """GET /api/cotizacion con el tamaño en cripto."""
    sess = session or requests
    resp = sess.get(base_url.rstrip("/") + "/api/cotizacion",
                    params={"asset": asset, "size": size, "margen": margen_pct},
                    timeout=60)
    resp.raise_for_status()
    return resp.json()


def _mejor_compra(cot: dict) -> dict:
    compras = cot.get("buys") or []
    if not compras:
        raise SystemExit("No hay ninguna punta de compra disponible ahora.")
    return compras[0]


def plan_desde_vps(base_url: str, *, ars: float, asset: str, margen_pct: float,
                   spot_fee_pct: float, fee_red: float = 0.0,
                   session=None) -> tuple[dict, dict]:
    """Cotiza, ajusta el tamaño al monto real del cliente y arma el plan."""
    asset = asset.strip().upper()
    cot = cotizar(base_url, asset, _SONDEO.get(asset, 1.0), margen_pct, session)
    # Segunda pasada con el tamaño real: el precio ejecutable cambia con el
    # volumen y la primera sólo servía para estimarlo.
    size = ars / cot["precio_venta_cliente"]
    cot = cotizar(base_url, asset, size, margen_pct, session)
    mejor = _mejor_compra(cot)
    via = mejor.get("via") or {}
    plan = plan_para_cliente(
        ars=ars, asset=asset, margen_pct=margen_pct,
        costo_venue=mejor["price"],
        usdt_price=via.get("usdt_price"),
        spot_price=via.get("spot_price"),
        spot_fee_pct=spot_fee_pct,
        fee_red=fee_red,
    )
    plan["venue"] = mejor["venue"]
    plan["stock"] = mejor.get("stock")
    plan["fuente_spot"] = via.get("fuente")
    return plan, cot


def _ars(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def _num(x: float, dec: int) -> str:
    return f"{x:,.{dec}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def render(plan: dict, cliente: str | None = None) -> str:
    """Los renglones que el usuario lee en el teléfono para operar."""
    quien = f" · {cliente}" if cliente else ""
    asset = plan["asset"]
    dec = 8 if asset == "BTC" else 2
    L = [f"COTIZAR {asset}{quien} · {_ars(plan['ars_cliente'])} ARS", ""]

    if plan["usdt_a_comprar"] is None:
        L.append(f"1. Comprás {_num(plan['entrega_bruta'], 2)} USDT en "
                 f"{plan['venue']} a {_num(plan['costo_venue'], 2)} "
                 f"→ {_ars(plan['ars_a_gastar'])} ARS")
        L.append(f"2. Le mandás {_num(plan['entrega'], 2)} USDT")
    else:
        L.append(f"1. Comprás {_num(plan['usdt_a_comprar'], 2)} USDT en "
                 f"{plan['venue']} a {_num(plan['usdt_price'], 2)} "
                 f"→ {_ars(plan['ars_a_gastar'])} ARS")
        L.append(f"2. Comprás {asset} en spot a {_num(plan['spot_price'], 1)} USDT "
                 f"→ {_num(plan['entrega_bruta'], dec)} {asset}")
        L.append(f"3. Retirás {_num(plan['entrega_bruta'], dec)} {asset} "
                 f"(pagás {_num(plan['fee_red'], dec)} de red) → "
                 f"le llegan {_num(plan['entrega'], dec)} {asset} exactos")

    L += ["", f"LE DECÍS: {_ars(plan['precio_cliente'])} ARS por {asset}"]
    if plan.get("precio_cliente_usdt"):
        L.append(f"           {_num(plan['precio_cliente_usdt'], 2)} USDT por {asset}")
    L.append(f"           recibe {_num(plan['entrega'], dec)} {asset} exactos")
    neto = " (neta, el fee de red ya está pagado)" if plan.get("fee_red") else ""
    L += ["", f"Ganás {_ars(plan['ganancia_ars'])} ARS "
              f"({_num(plan['ganancia_pct'], 2)}%){neto}"]
    if plan.get("stock") is not None and plan["stock"] < plan["entrega_bruta"]:
        L.append(f"⚠️ Ojo: en esa punta hay {_num(plan['stock'], dec)} "
                 f"{asset}, menos de lo que necesitás.")
    return "\n".join(L)


def main(argv=None) -> None:
    import config

    # La consola de Windows viene en cp1252 y se atraganta con las flechas.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser(description="Cotización a cliente en 3 renglones.")
    ap.add_argument("ars", type=float, help="pesos que manda el cliente")
    ap.add_argument("--asset", default="BTC", help="BTC (default) o USDT")
    ap.add_argument("--margen", type=float, default=None,
                    help="%% de ganancia; default el de config (COTIZA_MARGEN_PCT)")
    ap.add_argument("--cliente", default=None, help="nombre, sólo para el título")
    args = ap.parse_args(argv)

    if not config.VPS_API_URL:
        raise SystemExit("VPS_API_URL no configurada en .env")
    margen = config.COTIZA_MARGEN_PCT if args.margen is None else args.margen
    fee_red = config.BTC_NETWORK_FEE if args.asset.strip().upper() == "BTC" else 0.0
    plan, _ = plan_desde_vps(config.VPS_API_URL, ars=args.ars, asset=args.asset,
                             margen_pct=margen,
                             spot_fee_pct=config.SPOT_FEE_PCT, fee_red=fee_red)
    print(render(plan, args.cliente))


if __name__ == "__main__":
    main()
