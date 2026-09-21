"""Empuja un movimiento al endpoint /api/movement del VPS (no escribe local)."""
import argparse
import json

import requests


def push(movement: dict, base_url: str, session=None) -> tuple[int, str]:
    """POST del movimiento a {base_url}/api/movement. Devuelve (status, text)."""
    sess = session or requests
    url = base_url.rstrip("/") + "/api/movement"
    resp = sess.post(url, json=movement, timeout=30)
    return resp.status_code, resp.text


def list_clients(base_url: str, session=None) -> list[dict]:
    """GET /api/clients — la lista con resumen (snake_case)."""
    sess = session or requests
    resp = sess.get(base_url.rstrip("/") + "/api/clients", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_client(client_id: int, base_url: str, session=None) -> dict:
    """GET /api/clients/{id} — {"client": {...}, "movements": [...]}."""
    sess = session or requests
    resp = sess.get(f"{base_url.rstrip('/')}/api/clients/{client_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_client(name: str, base_url: str, session=None) -> dict:
    """POST /api/clients — crea el cliente y devuelve el dict del dashboard."""
    sess = session or requests
    resp = sess.post(base_url.rstrip("/") + "/api/clients",
                     json={"name": name, "status": "activo"}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def assign_client(order_id: str, client_id: int, base_url: str,
                  session=None) -> tuple[int, str]:
    """PUT /api/movements/{order_id}/client — linkea la op al cliente."""
    sess = session or requests
    resp = sess.put(f"{base_url.rstrip('/')}/api/movements/{order_id}/client",
                    json={"client_id": client_id}, timeout=30)
    return resp.status_code, resp.text


def main(argv=None) -> None:
    import config

    parser = argparse.ArgumentParser(description="Empuja un movimiento al VPS.")
    parser.add_argument("--json", required=True, help="Movimiento en JSON.")
    args = parser.parse_args(argv)

    if not config.VPS_API_URL:
        raise SystemExit("VPS_API_URL no configurada en .env")
    status, text = push(json.loads(args.json), config.VPS_API_URL)
    print(status, text)


if __name__ == "__main__":
    main()
