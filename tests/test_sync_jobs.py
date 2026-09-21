from webapp.sync_jobs import SyncJobs, PENDING, CLAIMED, DONE, ERROR


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t
    def advance(self, secs): self.t += secs


def test_request_crea_pending():
    j = SyncJobs(now=FakeClock())
    job = j.request()
    assert job.status == PENDING
    assert job.job_id


def test_request_reusa_pending_existente():
    j = SyncJobs(now=FakeClock())
    a = j.request()
    b = j.request()
    assert a.job_id == b.job_id  # no crea uno nuevo si hay pending vigente


def test_claim_marca_claimed():
    j = SyncJobs(now=FakeClock())
    job = j.request()
    claimed = j.claim()
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert claimed.status == CLAIMED


def test_claim_sin_pending_devuelve_none():
    j = SyncJobs(now=FakeClock())
    assert j.claim() is None


def test_claim_pending_vencido_devuelve_none():
    clk = FakeClock()
    j = SyncJobs(now=clk)
    j.request()
    clk.advance(21)  # > CLAIM_TIMEOUT_S
    assert j.claim() is None


def test_finish_marca_done_con_resultado():
    j = SyncJobs(now=FakeClock())
    job = j.request()
    j.claim()
    ok = j.finish(job.job_id, True, result={"binance": {"nuevas": 1}})
    assert ok is True
    v = j.view(job.job_id)
    assert v["status"] == DONE
    assert v["result"] == {"binance": {"nuevas": 1}}


def test_finish_job_inexistente_devuelve_false():
    j = SyncJobs(now=FakeClock())
    assert j.finish("noexiste", True) is False


def test_view_pending_vencido_es_no_agent():
    clk = FakeClock()
    j = SyncJobs(now=clk)
    job = j.request()
    clk.advance(21)
    assert j.view(job.job_id)["status"] == "no_agent"


def test_view_claimed_vencido_es_timeout():
    clk = FakeClock()
    j = SyncJobs(now=clk)
    job = j.request()
    j.claim()
    clk.advance(181)  # > RESULT_TIMEOUT_S
    assert j.view(job.job_id)["status"] == "timeout"


def test_view_job_distinto_devuelve_none():
    j = SyncJobs(now=FakeClock())
    j.request()
    assert j.view("otro-id") is None
