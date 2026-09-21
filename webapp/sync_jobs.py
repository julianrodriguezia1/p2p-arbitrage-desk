"""Cola de un solo job de sync on-demand (en memoria). Máquina de estados pura."""
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

PENDING = "pending"
CLAIMED = "claimed"
DONE = "done"
ERROR = "error"

CLAIM_TIMEOUT_S = 20    # pending sin que ningún agente lo reclame
RESULT_TIMEOUT_S = 180  # claimed sin que el agente reporte resultado


@dataclass
class Job:
    job_id: str
    status: str
    created_at: float
    claimed_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class SyncJobs:
    def __init__(self, now: Callable[[], float] = time.time) -> None:
        self._now = now
        self._job: Optional[Job] = None

    def request(self) -> Job:
        j = self._job
        if j and j.status == PENDING and not self._claim_expired(j):
            return j
        if j and j.status == CLAIMED and not self._result_expired(j):
            return j
        self._job = Job(job_id=uuid.uuid4().hex, status=PENDING, created_at=self._now())
        return self._job

    def claim(self) -> Optional[Job]:
        j = self._job
        if j and j.status == PENDING and not self._claim_expired(j):
            j.status = CLAIMED
            j.claimed_at = self._now()
            return j
        return None

    def finish(self, job_id: str, ok: bool,
               result: Optional[dict] = None, error: Optional[str] = None) -> bool:
        j = self._job
        if not j or j.job_id != job_id or j.status != CLAIMED:
            return False
        j.status = DONE if ok else ERROR
        j.finished_at = self._now()
        j.result = result
        j.error = error
        return True

    def view(self, job_id: str) -> Optional[dict]:
        j = self._job
        if not j or j.job_id != job_id:
            return None
        status = j.status
        if status == PENDING and self._claim_expired(j):
            status = "no_agent"
        elif status == CLAIMED and self._result_expired(j):
            status = "timeout"
        return {"job_id": j.job_id, "status": status,
                "result": j.result, "error": j.error}

    def _claim_expired(self, j: Job) -> bool:
        return self._now() - j.created_at > CLAIM_TIMEOUT_S

    def _result_expired(self, j: Job) -> bool:
        return j.claimed_at is not None and self._now() - j.claimed_at > RESULT_TIMEOUT_S
