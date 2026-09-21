"""Tests del reporte de prima: resume el CSV sin mentir sobre lo que no midió."""
import pytest

from cli.prima_report import (
    filtrar_creibles,
    por_dia,
    por_hora,
    resumen_activo,
)


def _f(asset="BTC", hour=14, weekday="Sun", prima="1.20", ancho="1.55",
       n_ask="20", depth="70000"):
    return {"asset": asset, "hour": hour, "weekday": weekday,
            "prima_ask_pct": prima, "ancho_pct": ancho,
            "n_ask": n_ask, "depth_ask_usd": depth}


def test_resumen_activo_da_mediana_y_rango():
    filas = [_f(prima="1.00"), _f(prima="1.20"), _f(prima="1.60")]
    r = resumen_activo(filas)["BTC"]
    assert r["n"] == 3
    assert r["prima_mediana"] == pytest.approx(1.20)
    assert r["prima_min"] == pytest.approx(1.00)
    assert r["prima_max"] == pytest.approx(1.60)


def test_resumen_activo_separa_por_activo():
    r = resumen_activo([_f(asset="BTC", prima="1.2"), _f(asset="ETH", prima="1.6")])
    assert set(r) == {"BTC", "ETH"}
    assert r["ETH"]["prima_mediana"] == pytest.approx(1.6)


def test_resumen_ignora_filas_sin_prima():
    """Una punta que faltó se guarda vacía; no puede contar como 0."""
    r = resumen_activo([_f(prima="1.2"), _f(prima=""), _f(prima="1.4")])
    assert r["BTC"]["n"] == 2
    assert r["BTC"]["prima_mediana"] == pytest.approx(1.3)


def test_por_hora_agrupa_y_ordena():
    filas = [_f(hour=3, prima="2.0"), _f(hour=3, prima="2.2"), _f(hour=15, prima="1.0")]
    r = por_hora(filas, "BTC")
    assert [h for h, _ in r] == [3, 15]
    assert dict(r)[3]["prima_mediana"] == pytest.approx(2.1)


def test_por_dia_usa_el_orden_de_la_semana_no_alfabetico():
    filas = [_f(weekday="Sun", prima="1.0"), _f(weekday="Mon", prima="2.0"),
             _f(weekday="Sat", prima="3.0")]
    assert [d for d, _ in por_dia(filas, "BTC")] == ["Mon", "Sat", "Sun"]


def test_filtrar_creibles_saca_las_muestras_de_libro_vacio():
    """Una prima sostenida por 2 avisos no entra al promedio: ensucia el número."""
    filas = [_f(n_ask="20", prima="1.2"), _f(n_ask="2", prima="9.8")]
    ok = filtrar_creibles(filas)
    assert len(ok) == 1
    assert ok[0]["prima_ask_pct"] == "1.2"


def test_filtrar_creibles_tolera_conteo_ausente():
    filas = [_f(n_ask=""), _f(n_ask="20")]
    assert len(filtrar_creibles(filas)) == 1
