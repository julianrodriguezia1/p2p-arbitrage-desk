"""Agente de sync on-demand: poolea el VPS, corre el sync residencial y reporta.

Corre en la PC del usuario (IP residencial), headless. Reusa run_sync_default.
"""
import time
from typing import Callable, Optional

import requests

TOKEN_HEADER = "X-Sync-Token"


def poll_once(base_url: str, token: str, get=requests.get) -> Optional[str]:
    """Pregunta al VPS si hay un job pendiente. Devuelve job_id o None."""
    r = get(f"{base_url}/api/sync/poll", headers={TOKEN_HEADER: token}, timeout=15)
    r.raise_for_status()
    return r.json().get("job_id")


def report(base_url: str, token: str, job_id: str, ok: bool,
           result: Optional[dict] = None, error: Optional[str] = None,
           post=requests.post) -> None:
    """Reporta el resultado del sync al VPS."""
    post(f"{base_url}/api/sync/result", headers={TOKEN_HEADER: token},
         json={"job_id": job_id, "ok": ok, "result": result, "error": error},
         timeout=30)


def handle_job(job_id: str, run: Callable[[], dict], base_url: str, token: str,
               report_fn=report) -> None:
    """Corre el sync y reporta resultado (o el error si falla)."""
    try:
        result = run()
        report_fn(base_url, token, job_id, True, result=result)
    except Exception as exc:
        report_fn(base_url, token, job_id, False, error=str(exc))


def loop(config, *, interval: float = 4.0, poll=poll_once, sleep=time.sleep) -> None:
    """Loop infinito: poolea, y si hay job corre el sync y reporta. Headless."""
    from companion import sync_core
    base_url, token = config.VPS_API_URL, config.SYNC_AGENT_TOKEN
    while True:
        try:
            job_id = poll(base_url, token)
            if job_id:
                handle_job(job_id, lambda: sync_core.run_sync_default(config),
                           base_url, token)
        except Exception:
            pass  # red caída / VPS no responde: reintenta en la próxima vuelta
        sleep(interval)


if __name__ == "__main__":
    import config
    print("Agente de sync on-demand corriendo. Ctrl+C para cortar.")
    loop(config)
