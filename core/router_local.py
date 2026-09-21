"""Router determinístico: palabra suelta → acción, sin pasar por el modelo.

Existe porque el router de NVIDIA se cae (timeout, rate limit, sin key en el
VPS) y entonces CUALQUIER mensaje sin barra contestaba "se me colgó el
traductor". Lo que se escribe todo el día —"oportunidad", "binance", "spread"—
tiene que andar aunque no haya modelo, y de paso sale gratis e instantáneo.

Dos modos:
  - estricto (el default): sólo mensajes cortos. Una frase larga lleva datos
    (un cliente, un monto) y esa la tiene que leer el modelo, aunque adentro
    diga "binance".
  - flojo (``solo_corto=False``): se usa recién cuando el modelo NO contestó.
    Ahí una acción probable es mejor que un "no te pude leer".
"""
from __future__ import annotations

import re
import unicodedata

# Hasta acá se considera "palabra suelta" y lo contesta el matcher sin modelo.
MAX_PALABRAS = 4

# (patrones, acción, params). Orden = prioridad: lo más específico primero.
REGLAS: tuple[tuple[tuple[str, ...], str, dict], ...] = (
    (("donde compro", "donde comprar", "donde esta mas barato"),
     "donde", {"lado": "compro"}),
    (("donde vendo", "donde vender", "donde pagan mas"),
     "donde", {"lado": "vendo"}),
    (("oportunidad", "oportunidades", "mejor jugada", "mejor spread",
      "mejor negocio", "que hago", "que me conviene", "donde gano",
      "jugada", "estrategia", "conviene", "hago"),
     "estrategia", {}),
    (("binance", "verificado", "comerciante", "merchant"),
     "binance", {}),
    (("spread",), "spread", {}),
    (("stock", "inventario"), "stock", {}),
    (("billetera", "billeteras", "topes"), "billeteras", {}),
    (("actualizar", "actualiza", "sincronizar", "sincroniza", "sync",
      "ordenes nuevas"), "actualizar", {}),
    (("precio", "precios"), "precio", {}),
    (("ayuda", "help", "hola", "menu", "que sabes hacer"), "ayuda", {}),
)


def normalizar(text: str) -> str:
    """minúsculas, sin acentos, sin signos y sin la barra del comando."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", text or "")
        if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-z0-9]+", " ", sin_acentos.lower())
    return limpio.strip()


def _contiene(texto: str, patron: str) -> bool:
    """El patrón arranca en un límite de palabra, pero puede seguir: así
    'oportunidades' entra por 'oportunidad' y 'ayudame' por 'ayuda'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(patron), texto) is not None


def match(text: str, *, solo_corto: bool = True) -> dict | None:
    """{'action', 'params'} si el texto cae en una regla; None si no."""
    t = normalizar(text)
    if not t:
        return None
    if solo_corto and len(t.split()) > MAX_PALABRAS:
        return None
    # En modo flojo no se adivina sobre un texto con números: ahí vive la carga
    # de una op de cliente ("le vendí 1000 a Daniel a 1578") y contestarle un
    # spread le haría creer que la op quedó cargada. Mejor pedirle que repita.
    if not solo_corto and re.search(r"\d", t):
        return None
    for patrones, action, params in REGLAS:
        if any(_contiene(t, p) for p in patrones):
            return {"action": action, "params": dict(params)}
    return None
