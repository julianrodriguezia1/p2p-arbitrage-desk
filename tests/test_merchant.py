"""Progreso hacia el Comerciante Verificado de Binance P2P.

Requisitos que el usuario pasó el 2026-08-28 (Argentina, estimativos). Acá sólo
viven los 3 que se pueden medir con trades.db: los otros (antigüedad, 98% de
finalización, KYC, depósito, tiempo de liberación) ya los tiene resueltos y no
se muestran.
"""
import importlib
import itertools
from datetime import date
from decimal import Decimal

import pytest

import config
from core.movements import Movement, Side, Source
from core.merchant import progreso


HOY = date(2026, 8, 28)

# Los números de orden P2P de Binance son enteros de 20 dígitos.
_ORDEN = itertools.count(22900000000000000000)


def _mov(fecha: date, usd: str, exchange: str = "Binance / USDT",
         order_id: str | None = None) -> Movement:
    return Movement(
        side=Side.COMPRA, date=fecha, order_id=order_id or str(next(_ORDEN)),
        usd_gross=Decimal(usd), commission=Decimal("0"), usd_net=Decimal(usd),
        price=Decimal("1600"), total_ars=Decimal(usd) * Decimal("1600"),
        exchange_coin=exchange, bank="Galicia", source=Source.BINANCE_API,
    )


def _req(p, clave):
    return next(r for r in p.requisitos if r.clave == clave)


def test_config_trae_las_metas_del_verificado():
    importlib.reload(config)
    assert config.MERCHANT_OPS_30D == 400
    assert config.MERCHANT_VOL_30D_BTC == 0.5
    assert config.MERCHANT_VOL_HIST_BTC == 1.0
    assert config.MERCHANT_VENTANA_DIAS == 30


def test_cuenta_solo_las_operaciones_de_binance():
    movs = [_mov(HOY, "100"), _mov(HOY, "100", "Lemon / USDT"),
            _mov(HOY, "100", "Bybit / USDT"), _mov(HOY, "100", "Binance / USDC")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "ops_30d").valor == 2


def test_deja_afuera_lo_que_cayo_de_la_ventana_de_30_dias():
    movs = [_mov(date(2026, 8, 20), "100"),   # adentro
            _mov(date(2026, 7, 28), "100")]   # 31 días atrás: afuera
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "ops_30d").valor == 1


def test_volumen_30d_se_expresa_en_btc():
    movs = [_mov(HOY, "25000"), _mov(HOY, "25000")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    r = _req(p, "vol_30d_btc")
    assert r.valor == pytest.approx(0.5)
    assert r.meta == 0.5
    assert r.cumple is True


def test_volumen_historico_suma_todo_aunque_este_fuera_de_la_ventana():
    movs = [_mov(HOY, "50000"), _mov(date(2026, 5, 26), "50000")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "vol_hist_btc").valor == pytest.approx(1.0)
    assert _req(p, "vol_30d_btc").valor == pytest.approx(0.5)


def test_sin_precio_de_btc_los_volumenes_dicen_FALTA_y_no_inventan_numero():
    movs = [_mov(HOY, "50000")]
    p = progreso(movs, hoy=HOY, btc_usd=None)
    for clave in ("vol_30d_btc", "vol_hist_btc"):
        r = _req(p, clave)
        assert r.valor is None
        assert r.pct is None
        assert r.cumple is False
        assert "FALTA" in r.nota
    # las operaciones sí se cuentan: no dependen del precio de BTC
    assert _req(p, "ops_30d").valor == 1


def test_el_historico_avisa_desde_cuando_mide():
    movs = [_mov(date(2026, 5, 26), "1000"), _mov(HOY, "1000")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert p.desde == date(2026, 5, 26)
    assert "26/05/2026" in _req(p, "vol_hist_btc").nota


def test_sin_operaciones_de_binance_todo_en_cero_y_sin_fecha():
    p = progreso([_mov(HOY, "100", "Lemon / USDT")], hoy=HOY, btc_usd=100_000.0)
    assert p.desde is None
    assert _req(p, "ops_30d").valor == 0
    assert _req(p, "vol_30d_btc").valor == pytest.approx(0.0)
    assert all(not r.cumple for r in p.requisitos)


def test_avance_se_reporta_en_porcentaje_y_no_pasa_de_cien():
    movs = [_mov(HOY, "100") for _ in range(200)]   # 200 ops de USD 100
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "ops_30d").pct == pytest.approx(50.0)   # 200 de 400
    muchas = [_mov(HOY, "100") for _ in range(500)]
    p2 = progreso(muchas, hoy=HOY, btc_usd=100_000.0)
    assert _req(p2, "ops_30d").pct == 100.0
    assert _req(p2, "ops_30d").cumple is True


def test_no_cuenta_las_filas_de_binance_que_no_son_ordenes_p2p():
    """Compras de spot y ops de cliente se cargan como "Binance / USDT" pero
    Binance no las cuenta para el Verificado: su order_id no es un número de
    orden P2P (medido el 2026-08-30: 21 filas así, 8.857 USD de más)."""
    movs = [_mov(HOY, "100"),
            _mov(HOY, "500", order_id="spot-20260617-155213"),
            _mov(HOY, "300", order_id="cliente-carlos-20260617"),
            _mov(HOY, "400", order_id="LUCAS-20260715-92"),
            _mov(HOY, "600", order_id="151513515")]   # id corto: no es P2P
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "ops_30d").valor == 1
    assert _req(p, "vol_30d_btc").valor == pytest.approx(0.001)   # sólo los 100


def test_las_filas_de_btc_se_convierten_a_usd_con_el_precio():
    """`usd_gross` de una fila "Binance / BTC" viene en BTC, no en USD: sumarla
    de plano hunde el volumen (la orden del 21/08 valía 951 USD y contaba 0,01)."""
    movs = [_mov(HOY, "0.01208483", exchange="Binance / BTC")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "ops_30d").valor == 1
    assert _req(p, "vol_30d_btc").valor == pytest.approx(0.01208483)
    assert _req(p, "vol_hist_btc").valor == pytest.approx(0.01208483)


def test_btc_y_usdt_se_suman_en_la_misma_unidad():
    movs = [_mov(HOY, "0.5", exchange="Binance / BTC"),
            _mov(HOY, "50000")]
    p = progreso(movs, hoy=HOY, btc_usd=100_000.0)
    assert _req(p, "vol_30d_btc").valor == pytest.approx(1.0)
