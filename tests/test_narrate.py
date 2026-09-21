from types import SimpleNamespace

from core.narrate import narrate, _build_prompt


def _alert():
    return SimpleNamespace(
        title="🟡 Arbitraje media espera",
        detail="Comprá tomando en bybitp2p @ 1.564 → vendé publicando en okexp2p @ 1.575 · +0,50% neto",
    )


def test_sin_generador_devuelve_el_texto_numerico():
    alerts = [_alert()]
    from core.spread_alert import format_message
    assert narrate(alerts) == format_message(alerts)


def test_alertas_vacias_devuelve_string_vacio():
    assert narrate([]) == ""


def test_con_generador_reescribe_en_criollo():
    out = narrate([_alert()], generate=lambda p: "Che, comprá en Bybit y vendé en OKX, +0,5% limpio. Dale.")
    assert out == "Che, comprá en Bybit y vendé en OKX, +0,5% limpio. Dale."


def test_el_prompt_lleva_los_numeros_exactos():
    seen = {}
    def gen(prompt):
        seen["p"] = prompt
        return "ok"
    narrate([_alert()], generate=gen)
    assert "1.564" in seen["p"] and "1.575" in seen["p"] and "+0,50% neto" in seen["p"]


def test_si_el_generador_explota_cae_al_fallback():
    from core.spread_alert import format_message
    def boom(prompt):
        raise RuntimeError("LLM caído")
    alerts = [_alert()]
    assert narrate(alerts, generate=boom) == format_message(alerts)


def test_rechaza_salida_con_ask_o_bid():
    from core.spread_alert import format_message
    alerts = [_alert()]
    assert narrate(alerts, generate=lambda p: "comprá al ask y vendé al bid") == format_message(alerts)


def test_no_rechaza_palabras_que_contienen_bid_o_ask():
    alerts = [_alert()]
    out = narrate(
        alerts,
        generate=lambda p: "Entrá rápido, debido a que el spread se cierra ya",
    )
    assert out == "Entrá rápido, debido a que el spread se cierra ya"


def test_rechaza_salida_vacia():
    from core.spread_alert import format_message
    alerts = [_alert()]
    assert narrate(alerts, generate=lambda p: "   ") == format_message(alerts)


def test_default_generate_off_devuelve_none(monkeypatch):
    import config
    import core.narrate as narr
    monkeypatch.setattr(config, "SPREAD_NARRATE", False)
    assert narr.default_generate() is None


def test_default_generate_on_devuelve_el_adapter(monkeypatch):
    import config
    import core.narrate as narr
    monkeypatch.setattr(config, "SPREAD_NARRATE", True)
    assert narr.default_generate() is narr.ada_generate
