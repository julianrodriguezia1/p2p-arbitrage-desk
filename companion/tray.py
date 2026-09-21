# companion/tray.py
"""Icono de bandeja: 'Actualizar ahora' dispara el sync; corre el bridge en un thread."""
import threading

import pystray
from PIL import Image, ImageDraw

from companion.bridge_server import make_server
from companion.controller import SyncController


def _icon_image() -> Image.Image:
    img = Image.new("RGB", (64, 64), (16, 24, 32))
    d = ImageDraw.Draw(img)
    d.ellipse((16, 16, 48, 48), fill=(40, 200, 120))
    return img


def _format_balloon(result: dict) -> str:
    if result.get("busy"):
        return "Ya hay un sync corriendo…"
    if "error" in result:
        errs = result["error"].get("errores", [])
        return "Falló el sync: " + ("; ".join(errs) if errs else "error desconocido")
    partes = []
    for ex, r in result.items():
        linea = f"{ex}: {r['nuevas']} nuevas, {r['ya']} ya"
        if r.get("errores"):
            linea += f" ⚠️ {len(r['errores'])} err"
        partes.append(linea)
    return " | ".join(partes) if partes else "Sin novedades"


def run() -> None:
    import config
    controller = SyncController(lambda: run_sync_default_safe(config))
    server = make_server(controller, config.SYNC_BRIDGE_TOKEN, config.SYNC_BRIDGE_PORT)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def on_update(icon, item):
        result = controller.run()
        icon.notify(_format_balloon(result), "Sync")

    icon = pystray.Icon(
        "arbitrador-sync", _icon_image(), "Arbitrador sync",
        menu=pystray.Menu(
            pystray.MenuItem("Actualizar ahora", on_update),
            pystray.MenuItem("Salir", lambda icon, item: icon.stop()),
        ),
    )
    icon.run()


def run_sync_default_safe(config) -> dict:
    """Envuelve run_sync_default para no romper el icono si algo explota."""
    from companion.sync_core import run_sync_default
    try:
        return run_sync_default(config)
    except Exception as exc:
        return {"error": {"nuevas": 0, "ya": 0, "errores": [str(exc)]}}
