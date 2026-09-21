"""Orquesta run_sync: un solo sync a la vez (lock) y guarda el último resultado."""
import threading
from typing import Callable, Optional


class SyncController:
    def __init__(self, runner: Callable[[], dict]) -> None:
        self._runner = runner
        self._lock = threading.Lock()
        self.last_result: Optional[dict] = None

    def run(self) -> dict:
        if not self._lock.acquire(blocking=False):
            return {"busy": True}
        try:
            self.last_result = self._runner()
            return self.last_result
        finally:
            self._lock.release()
