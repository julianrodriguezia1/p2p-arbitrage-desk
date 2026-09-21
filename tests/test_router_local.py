"""Router determinístico: lo de todos los días tiene que andar sin el modelo."""
import pytest

from core.router_local import match


@pytest.mark.parametrize("frase,esperado", [
    ("oportunidad", "estrategia"),
    ("Oportunidad", "estrategia"),
    ("/oportunidad", "estrategia"),
    ("oportunidades", "estrategia"),
    ("la mejor oportunidad", "estrategia"),
    ("mejor jugada", "estrategia"),
    ("que hago", "estrategia"),
    ("qué hago?", "estrategia"),
    ("binance", "binance"),
    ("BINANCE", "binance"),
    ("verificado", "binance"),
    ("comerciante verificado", "binance"),
    ("spread", "spread"),
    ("stock", "stock"),
    ("billeteras", "billeteras"),
    ("actualizar", "actualizar"),
    ("sincronizar", "actualizar"),
    ("ayuda", "ayuda"),
    ("hola", "ayuda"),
])
def test_palabras_sueltas_no_necesitan_el_modelo(frase, esperado):
    r = match(frase)
    assert r is not None, frase
    assert r["action"] == esperado


def test_donde_compro_y_donde_vendo_traen_el_lado():
    assert match("donde compro") == {"action": "donde", "params": {"lado": "compro"}}
    assert match("dónde vendo") == {"action": "donde", "params": {"lado": "vendo"}}


def test_una_frase_larga_la_decide_el_modelo():
    """El matcher local es para palabras sueltas. Una op de cliente lleva datos
    y tiene que ir al modelo, aunque adentro diga 'binance'."""
    assert match("le vendí 1000 usdt a Daniel a 1578 por binance") is None


def test_en_modo_flojo_la_frase_larga_si_cae_en_la_palabra():
    """Cuando el modelo no contestó, es mejor una acción probable que un
    'no te pude leer'."""
    r = match("che, decime dónde hay una oportunidad ahora que ando con tiempo",
              solo_corto=False)
    assert r["action"] == "estrategia"


def test_lo_que_no_matchea_devuelve_none():
    assert match("caballo") is None
    assert match("") is None


def test_en_modo_flojo_un_texto_con_numeros_no_se_adivina():
    """Con números adentro puede ser la carga de una op de cliente: contestarle
    otra cosa le haría creer que quedó cargada."""
    assert match("le vendí 1000 a Daniel a 1578", solo_corto=False) is None
