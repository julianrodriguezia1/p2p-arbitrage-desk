import pytest

from core.orchestrator import ACTIONS, classify, parse_action


def test_parse_action_json_plano():
    assert parse_action('{"action":"spread"}') == "spread"


def test_parse_action_con_markdown():
    assert parse_action('```json\n{"action":"stock"}\n```') == "stock"


def test_parse_action_con_prosa_alrededor():
    assert parse_action('Claro, esto va a stock:\n{"action":"precio"} listo') == "precio"


def test_parse_action_fuera_del_enum_cae_a_ayuda():
    assert parse_action('{"action":"borrar_todo"}') == "ayuda"


def test_parse_action_basura_cae_a_ayuda():
    assert parse_action("no hay json acá") == "ayuda"
    assert parse_action('{"foo":"bar"}') == "ayuda"


def test_todas_las_acciones_estan_documentadas():
    # cada acción del enum tiene una descripción (entra en el prompt)
    for a in ("spread", "precio", "stock", "estrategia", "billeteras",
              "actualizar", "ayuda"):
        assert a in ACTIONS


class _FakeResp:
    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        pass


class _FakeSession:
    def __init__(self, content):
        self.calls = []
        self._content = content

    def post(self, url, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResp(self._content)


@pytest.mark.parametrize("frase,esperado", [
    # Frases largas y con datos: el matcher local no las toca a propósito, las
    # tiene que leer el modelo.
    ("¿me conviene más comprar o esperar un rato?", "estrategia"),
    ("che, decime cuánto me queda de inventario propio", "stock"),
    ("a cuánto tendría que venderle a un cliente hoy", "precio"),
    ("traé las órdenes que entraron desde la mañana", "actualizar"),
])
def test_classify_rutea_a_la_accion(monkeypatch, frase, esperado):
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    monkeypatch.setattr(config, "NVIDIA_BASE_URL", "https://nv/v1", raising=False)
    monkeypatch.setattr(config, "NVIDIA_TEXT_MODEL", "text-x", raising=False)
    sess = _FakeSession('{"action":"%s"}' % esperado)
    assert classify(frase, session=sess)["action"] == esperado
    call = sess.calls[0]
    assert call["url"] == "https://nv/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer K"
    assert call["json"]["model"] == "text-x"
    # el texto del usuario viaja en el mensaje
    assert any(frase in str(m) for m in call["json"]["messages"])


@pytest.mark.parametrize("frase,esperado", [
    ("¿qué me conviene ahora?", "estrategia"),
    ("cuánto stock tengo", "stock"),
    ("a qué precio vendo", "precio"),
    ("traé las órdenes nuevas", "actualizar"),
    ("cómo viene el spread", "spread"),
    ("cómo vienen las billeteras", "billeteras"),
])
def test_no_regresion_las_acciones_viejas_siguen_sin_params(monkeypatch, frase, esperado):
    """Agrandar el prompt no puede romper el ruteo que ya funcionaba."""
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    sess = _FakeSession('{"action":"%s","params":{}}' % esperado)
    out = classify(frase, session=sess)
    assert out == {"action": esperado, "params": {}}


class _SessionRaises:
    def post(self, *a, **k):
        raise ConnectionError("boom")


def test_classify_error_de_red_cae_a_ayuda(monkeypatch):
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    # Marca 'error': el bot tiene que poder distinguir "no te entendí" de
    # "no llegué a preguntar". Ver test_classify_marca_el_fallo_de_infraestructura.
    # Frase que el matcher local no contesta: así el que falla es el modelo.
    assert classify("contame cualquier cosa de la vida", session=_SessionRaises()) == {
        "action": "ayuda", "params": {}, "error": "infra"}


# ── Router local: lo de todos los días no pasa por el modelo ───────────────

def test_una_palabra_no_toca_la_red(monkeypatch):
    """'oportunidad', 'binance', 'spread' se contestan solos: gratis, al toque
    y —lo importante— aunque NVIDIA esté caído."""
    sess = _FakeSession('{"action":"ayuda"}')
    assert classify("oportunidad", session=sess)["action"] == "estrategia"
    assert classify("binance", session=sess)["action"] == "binance"
    assert sess.calls == []


def test_si_el_modelo_no_contesta_igual_intenta_la_palabra():
    """Antes cualquier mensaje sin barra terminaba en 'no te pude leer'."""
    out = classify("decime dónde hay una oportunidad copada ahora",
                   session=_SessionRaises())
    assert out == {"action": "estrategia", "params": {}}


def test_binance_es_una_accion_del_enum():
    assert "binance" in ACTIONS


from datetime import date

from core.orchestrator import PARAMS, parse_result

HOY = date(2026, 8, 12)


def test_parse_result_devuelve_accion_y_params():
    out = parse_result('{"action":"registrar_op_cliente","params":'
                       '{"cliente":"Daniel","lado":"vendi","monto":1000,'
                       '"unidad":"usdt","precio":1578}}')
    assert out["action"] == "registrar_op_cliente"
    assert out["params"]["cliente"] == "Daniel"
    assert out["params"]["precio"] == 1578


def test_parse_result_descarta_params_fuera_del_esquema():
    out = parse_result('{"action":"registrar_op_cliente","params":'
                       '{"cliente":"Daniel","borrar_todo":true}}')
    assert "borrar_todo" not in out["params"]
    assert out["params"]["cliente"] == "Daniel"


def test_parse_result_sin_params_devuelve_dict_vacio():
    assert parse_result('{"action":"spread"}') == {"action": "spread", "params": {}}


def test_parse_result_params_que_no_son_dict_se_ignoran():
    out = parse_result('{"action":"spread","params":"cualquier cosa"}')
    assert out == {"action": "spread", "params": {}}


def test_parse_result_accion_inventada_cae_a_ayuda():
    out = parse_result('{"action":"transferir_todo","params":{"a":"x"}}')
    assert out == {"action": "ayuda", "params": {}}


def test_parse_result_basura_cae_a_ayuda():
    assert parse_result("no hay json") == {"action": "ayuda", "params": {}}


def test_las_acciones_nuevas_estan_en_el_enum_y_tienen_esquema():
    for a in ("registrar_op_cliente", "consultar_cliente", "cotizar"):
        assert a in ACTIONS
        assert a in PARAMS


def test_las_acciones_viejas_no_llevan_params():
    for a in ("spread", "precio", "stock", "estrategia", "billeteras",
              "actualizar", "ayuda"):
        assert a not in PARAMS


def test_el_prompt_dice_la_fecha_de_hoy():
    from core.orchestrator import build_prompt
    assert "2026-08-12" in build_prompt("le vendí 1000 a Daniel", today=HOY)


def test_classify_devuelve_dict_con_params(monkeypatch):
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    monkeypatch.setattr(config, "NVIDIA_BASE_URL", "https://nv/v1", raising=False)
    monkeypatch.setattr(config, "NVIDIA_TEXT_MODEL", "text-x", raising=False)
    sess = _FakeSession('{"action":"registrar_op_cliente","params":'
                        '{"cliente":"Daniel","lado":"vendi","monto":1000,'
                        '"unidad":"usdt","precio":1578,"banco":null,"fecha":null}}')
    out = classify("le vendí 1000 a Daniel a 1578", session=sess)
    assert out["action"] == "registrar_op_cliente"
    assert out["params"]["monto"] == 1000


def test_classify_error_de_red_cae_a_ayuda_con_dict():
    # Marca 'error': el bot tiene que poder distinguir "no te entendí" de
    # "no llegué a preguntar". Ver test_classify_marca_el_fallo_de_infraestructura.
    # Frase que el matcher local no contesta: así el que falla es el modelo.
    assert classify("contame cualquier cosa de la vida", session=_SessionRaises()) == {
        "action": "ayuda", "params": {}, "error": "infra"}


# ── Router local: lo de todos los días no pasa por el modelo ───────────────

def test_una_palabra_no_toca_la_red(monkeypatch):
    """'oportunidad', 'binance', 'spread' se contestan solos: gratis, al toque
    y —lo importante— aunque NVIDIA esté caído."""
    sess = _FakeSession('{"action":"ayuda"}')
    assert classify("oportunidad", session=sess)["action"] == "estrategia"
    assert classify("binance", session=sess)["action"] == "binance"
    assert sess.calls == []


def test_si_el_modelo_no_contesta_igual_intenta_la_palabra():
    """Antes cualquier mensaje sin barra terminaba en 'no te pude leer'."""
    out = classify("decime dónde hay una oportunidad copada ahora",
                   session=_SessionRaises())
    assert out == {"action": "estrategia", "params": {}}


def test_binance_es_una_accion_del_enum():
    assert "binance" in ACTIONS


def test_cotizar_acepta_el_param_activo():
    """Sin 'activo' en la allowlist, el filtro de parse_result lo tira y el bot
    cotiza USDT aunque el usuario haya pedido bitcoin."""
    assert "activo" in PARAMS["cotizar"]


def test_parse_result_deja_pasar_el_activo():
    out = parse_result('{"action":"cotizar","params":'
                       '{"lado_cliente":"compra","margen":2,"activo":"btc"}}')
    assert out["params"]["activo"] == "btc"


def test_el_prompt_le_ensena_a_distinguir_btc():
    from core.orchestrator import build_prompt
    p = build_prompt("a cuánto le vendo bitcoin", today=HOY).lower()
    assert "activo" in p and "btc" in p and "bitcoin" in p


# ── Fallo de infraestructura ≠ "no entendí" ───────────────────────────────
# Medido el 22/08/2026 contra el VPS: 5 de 8 frases cayeron en "ayuda", y las
# mismas frases un minuto después clasificaron bien en ~1s. No era el modelo
# sin entender, era NVIDIA rechazando o tardando (latencia de 1 a 16s). Como
# `except Exception: return ayuda` se tragaba todo, el bot contestaba el menú
# de comandos y parecía que no entendía lenguaje natural.

class _SessionFallaLasPrimeras:
    """Falla las N primeras llamadas y después contesta bien."""

    def __init__(self, fallos: int, content: str):
        self.fallos = fallos
        self.llamadas = 0
        self._content = content

    def post(self, url, headers=None, json=None, timeout=None):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise ConnectionError("boom")
        return _FakeResp(self._content)


def test_classify_reintenta_una_vez_y_clasifica_bien(monkeypatch):
    """El fallo es transitorio: el segundo intento ya trae la respuesta."""
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    sess = _SessionFallaLasPrimeras(1, '{"action":"spread"}')
    out = classify("che, cómo viene el mercado del dólar cripto", session=sess)
    assert out["action"] == "spread"
    assert sess.llamadas == 2


def test_classify_no_reintenta_si_la_primera_anda(monkeypatch):
    """Reintentar de gusto quema la cuota y encima dispara el rate limit."""
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    sess = _SessionFallaLasPrimeras(0, '{"action":"stock"}')
    classify("che, contame cómo viene mi inventario propio", session=sess)
    assert sess.llamadas == 1


def test_classify_marca_el_fallo_de_infraestructura(monkeypatch):
    """Tras agotar los intentos avisa que no pudo leer, no que no entendió: el
    bot tiene que decir 'repetímelo' en vez de mostrar el menú de ayuda."""
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    out = classify("contame cualquier cosa de la vida", session=_SessionRaises())
    assert out["action"] == "ayuda"
    assert out["error"] == "infra"


def test_classify_sin_entender_no_marca_error(monkeypatch):
    """El modelo contestó, solo que con algo fuera del enum. Eso SÍ es 'no
    entendí' y corresponde el menú de ayuda."""
    import config
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "K", raising=False)
    out = classify("mmm", session=_FakeSession('{"action":"borrar_todo"}'))
    assert out["action"] == "ayuda"
    assert out.get("error") is None


# ── Acción "donde": ranking de dónde comprar/vender ───────────────────────

def test_donde_esta_en_el_enum_con_sus_params():
    from core.orchestrator import ACTIONS, PARAMS

    assert "donde" in ACTIONS
    assert set(PARAMS["donde"]) == {"lado", "monto", "activo"}


def test_parse_result_filtra_params_inventados_en_donde():
    """Misma allowlist que el resto: lo que el modelo invente no pasa."""
    from core.orchestrator import parse_result

    out = parse_result('{"action":"donde","params":{"lado":"compro",'
                       '"monto":500,"borrar":"todo"}}')
    assert out == {"action": "donde",
                   "params": {"lado": "compro", "monto": 500}}
