"""Orquestador del bot de Telegram: texto libre → una acción del enum fijo.

El modelo (NVIDIA, OpenAI-compatible) SOLO clasifica la intención; la acción la
ejecuta el bot llamando a las funciones que ya existen en ``bot/commands.py``.
Nunca ejecuta algo fuera de ``ACTIONS`` y ante cualquier duda cae en ``ayuda``."""
from __future__ import annotations

import json
import logging
import time

import requests

from core.router_local import match

logger = logging.getLogger(__name__)

# Enum fijo de acciones. La descripción va en el prompt (para que el modelo
# elija) y también sirve de allowlist: nada fuera de estas claves se ejecuta.
ACTIONS: dict[str, str] = {
    "spread": "el spread entre exchanges / la mejor jugada de arbitraje ahora",
    "precio": "a qué precio comprar y vender USDT en este momento",
    "donde": "en QUÉ exchange le conviene comprar más barato o vender más caro "
             "(dónde compro, dónde vendo, dónde está más barato)",
    "stock": "cuánto USDT/BTC tiene y su P&L (inventario)",
    "estrategia": "qué le conviene hacer ahora, la mejor jugada neta de comisiones "
                  "(la mejor oportunidad de spread, comprando o vendiendo)",
    "binance": "la mejor jugada que pase por el P2P de Binance — las órdenes "
               "que suman para el Comerciante Verificado",
    "billeteras": "cuánto ARS entró/salió por cada billetera vs los topes AML",
    "actualizar": "traer/sincronizar las órdenes nuevas de Binance y Bybit",
    "registrar_op_cliente": "registrar/cargar una operación que YA hizo con un "
                            "CLIENTE (una persona): le vendió o le compró USDT",
    "consultar_cliente": "consultar qué operó con un cliente (última op, cuánto "
                         "le vendió, totales) — NO carga nada",
    "cotizar": "qué precio cotizarle a un cliente (de USDT o de BTC), con un "
               "margen de ganancia",
    "ayuda": "no se entiende el pedido, o pide ayuda / la lista de cosas que sabe hacer",
}

# Params permitidos por acción. Funciona de allowlist: lo que el modelo mande
# fuera de esta lista se descarta antes de que lo vea el resto del sistema.
PARAMS: dict[str, tuple[str, ...]] = {
    "registrar_op_cliente": ("cliente", "lado", "monto", "unidad", "precio",
                             "banco", "fecha"),
    "consultar_cliente": ("cliente", "periodo"),
    "cotizar": ("lado_cliente", "margen", "activo", "monto"),
    "donde": ("lado", "monto", "activo"),
}


def build_prompt(text: str, today=None) -> str:
    """Prompt rioplatense: describe las acciones, el esquema de datos de las que
    llevan, y pide SOLO el JSON de la elegida."""
    from datetime import date as _date

    hoy = (today or _date.today()).isoformat()
    opciones = "\n".join(f"  - {a}: {desc}" for a, desc in ACTIONS.items())
    return (
        "Sos el asistente de un trader de arbitraje USDT/ARS. Entendé lo que te "
        "escribe en criollo (modismos argentinos incluidos) y elegí UNA sola de "
        "estas acciones, la que mejor responda su mensaje:\n"
        f"{opciones}\n\n"
        "Si la acción lleva datos, sacálos del mensaje y ponelos en 'params'. "
        "Usá null en lo que el mensaje no diga — NO inventes:\n"
        '  donde: {"lado": "compro" si pregunta dónde COMPRAR, "vendo" si '
        'pregunta dónde VENDER, "ambos" si no se entiende cuál; "monto": el '
        'número en unidades de cripto si lo dice; "activo": "btc" o "usdt"}\n'
        '  registrar_op_cliente: {"cliente": nombre de la persona, "lado": '
        '"vendi" si el usuario le VENDIÓ USDT al cliente o "compre" si se los '
        'COMPRÓ, "monto": el número, "unidad": "usdt" salvo que diga pesos/ARS/'
        'palos/lucas y ahí "ars", "precio": ARS por USDT, "banco": método de '
        f'pago, "fecha": "YYYY-MM-DD" (hoy es {hoy}; resolvé "ayer", "el lunes")'
        "}\n"
        '  consultar_cliente: {"cliente": nombre, "periodo": "mes" o null}\n'
        '  cotizar: {"lado_cliente": "compra" si el CLIENTE le compra al usuario '
        'o "venta" si le vende, "margen": el % de ganancia o null, "activo": '
        '"btc" si habla de bitcoin/BTC, si no "usdt", "monto": cuánta cripta '
        'quiere operar si lo dice, o null. OJO: si NO dice de qué lado está '
        'el cliente, dejá "lado_cliente" en null — se le contestan las dos '
        'puntas}\n'
        "Las demás acciones van con params vacío: {}.\n\n"
        f"Mensaje del usuario: {text!r}\n\n"
        "Devolvé SOLO un objeto JSON, sin texto alrededor: "
        '{"action": "<una de las de arriba>", "params": {...}}'
    )


def parse_action(content: str) -> str:
    """Extrae el primer objeto JSON del texto del modelo y valida la acción.

    Cualquier cosa rara (sin JSON, sin clave 'action', acción fuera del enum)
    cae en 'ayuda' — el orquestador nunca ejecuta algo que no esté en ACTIONS."""
    start = content.find("{")
    if start == -1:
        return "ayuda"
    try:
        obj, _ = json.JSONDecoder().raw_decode(content[start:])
    except ValueError:
        return "ayuda"
    action = str(obj.get("action", "")).strip().lower() if isinstance(obj, dict) else ""
    return action if action in ACTIONS else "ayuda"


def parse_result(content: str) -> dict:
    """Extrae {'action', 'params'} del texto del modelo.

    La acción pasa por el mismo allowlist de parse_action y los params se
    filtran contra PARAMS: nada que el modelo invente llega más adentro."""
    action = parse_action(content)
    if action == "ayuda":
        return {"action": "ayuda", "params": {}}
    start = content.find("{")
    try:
        obj, _ = json.JSONDecoder().raw_decode(content[start:])
    except ValueError:
        return {"action": action, "params": {}}
    raw = obj.get("params") if isinstance(obj, dict) else None
    permitidos = PARAMS.get(action, ())
    params = ({k: v for k, v in raw.items() if k in permitidos}
              if isinstance(raw, dict) else {})
    return {"action": action, "params": params}


# Latencia medida de NVIDIA el 22/08/2026 desde el VPS: entre 1 y 16 segundos,
# muy variable, y con rate limit si se le tiran varias seguidas. Con 30s se
# perdían clasificaciones que estaban bien.
# 45s cortaba a kimi-k3 (mide 35-64s) justo cuando es el unico modelo gratuito
# que clasifica bien: los rapidos (lightning, gpt-oss-20b) contestan "ayuda" a
# todo o devuelven JSON roto. Medido 2026-09-03.
TIMEOUT = 75
INTENTOS = 2
ESPERA_REINTENTO = 0.5


def classify(text: str, *, session=None, today=None) -> dict:
    """Rutea el texto libre a {'action', 'params'} vía NVIDIA.

    Distingue dos fracasos que antes se veían iguales:
      - el modelo contestó algo fuera del enum  → {'action': 'ayuda'} a secas,
        que es "no te entendí" y corresponde mostrar el menú;
      - no hubo respuesta (timeout, rate limit, red) → además 'error': 'infra',
        para que el bot diga "repetímelo" en vez del menú. Que el bot conteste
        ayuda cuando en realidad no llegó a preguntar es lo que hace parecer
        que no entiende lenguaje natural.

    Reintenta una vez: en la medición, todas las que fallaron salieron bien al
    segundo intento. La sesión HTTP se inyecta para testear con un fake.
    """
    import config

    # Lo de todos los días ("oportunidad", "binance", "spread") se contesta sin
    # red: gratis, instantáneo y —sobre todo— sigue andando con NVIDIA caído.
    local = match(text)
    if local is not None:
        return local

    sess = session or requests
    body = {
        "model": config.NVIDIA_TEXT_MODEL,
        "temperature": 0.0,
        "max_tokens": 256,          # los params necesitan más que los 64 de antes
        "messages": [{"role": "user", "content": build_prompt(text, today=today)}],
    }
    url = config.NVIDIA_BASE_URL.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {config.NVIDIA_API_KEY}"}

    for intento in range(1, INTENTOS + 1):
        try:
            resp = sess.post(url, headers=headers, json=body, timeout=TIMEOUT)
            resp.raise_for_status()
            choices = resp.json().get("choices") or []
            if not choices:
                raise ValueError("respuesta sin choices")
            return parse_result(choices[0]["message"]["content"])
        except Exception as exc:
            # Se loguea el error real: antes desaparecía y no había forma de
            # saber si el bot no entendía o si NVIDIA no había contestado.
            logger.warning("Router NVIDIA falló (intento %d/%d): %s: %s",
                           intento, INTENTOS, type(exc).__name__, exc)
            if intento < INTENTOS:
                time.sleep(ESPERA_REINTENTO)
    # Sin modelo, una acción probable es mejor que un "no te pude leer".
    flojo = match(text, solo_corto=False)
    if flojo is not None:
        return flojo
    return {"action": "ayuda", "params": {}, "error": "infra"}
