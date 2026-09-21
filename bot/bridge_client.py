"""Lógica pura del comando /actualizar: pega al bridge del compañero."""
import requests

from companion.bridge_server import TOKEN_HEADER

_NOMBRES = {"binance": "Binance", "bybit": "Bybit"}


def is_authorized(chat_id: int, allowed: int) -> bool:
    return chat_id == allowed


def format_sync_result(result: dict) -> str:
    if result.get("busy"):
        return "⏳ Ya hay un sync corriendo, probá en un toque."
    lineas = []
    for ex, r in result.items():
        nombre = _NOMBRES.get(ex, ex)
        linea = f"• {nombre}: {r['nuevas']} nuevas, {r['ya']} ya estaban"
        if r["errores"]:
            linea += "\n   ⚠️ " + "; ".join(r["errores"])
        lineas.append(linea)
    return "✅ Sync listo\n" + "\n".join(lineas) if lineas else "Sin novedades"


def actualizar_text(bridge_url: str, token: str, post=requests.post) -> str:
    try:
        resp = post(bridge_url, headers={TOKEN_HEADER: token}, timeout=180)
    except Exception:
        return "💻 No me pude conectar con tu compu. ¿Está prendida y con el sync abierto?"
    if resp.status_code != 200:
        try:
            detalle = resp.json().get("error", "")
        except Exception:
            detalle = ""
        return f"❌ El sync falló ({resp.status_code}). {detalle}".strip()
    return format_sync_result(resp.json())
