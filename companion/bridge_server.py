# companion/bridge_server.py
"""Servidor HTTP local del compañero: POST /sync (token) -> corre el sync."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from companion.controller import SyncController

TOKEN_HEADER = "X-Sync-Token"


def handle_sync(token_header: str | None, expected_token: str, runner: Callable[[], dict]) -> tuple[int, dict]:
    """Lógica pura del endpoint. Devuelve (status, body_dict)."""
    if not expected_token or token_header != expected_token:
        return 401, {"error": "unauthorized"}
    try:
        return 200, runner()
    except Exception as exc:  # el sync falló entero
        return 500, {"error": str(exc)}


def make_server(controller: "SyncController", token: str, port: int) -> HTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            if self.path != "/sync":
                self.send_response(404)
                self.end_headers()
                return
            status, body = handle_sync(
                self.headers.get(TOKEN_HEADER), token, controller.run
            )
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # silenciar el log ruidoso de stdlib
            pass

    return HTTPServer(("0.0.0.0", port), Handler)
