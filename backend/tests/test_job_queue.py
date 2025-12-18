import time

from app.metrics import metrics
from app.services.job_queue import JobQueue


def test_job_queue_enqueue_accepts_callable_and_legacy_name_pattern() -> None:
    queue = JobQueue(poll_interval=0.01)

    def job(a: int, b: int) -> None:  # pragma: no cover
        raise AssertionError("not executed")

    queue.enqueue(job, 1, 2, k="v")
    queue.enqueue("legacy_name", job, 3, 4)

    first_job, first_args, first_kwargs = queue._queue.get_nowait()  # type: ignore[attr-defined]
    assert first_job is job
    assert first_args == (1, 2)
    assert first_kwargs == {"k": "v"}

    second_job, second_args, second_kwargs = queue._queue.get_nowait()  # type: ignore[attr-defined]
    assert second_job is job
    assert second_args == (3, 4)
    assert second_kwargs == {}


def test_job_queue_enqueue_invalid_target_is_ignored() -> None:
    queue = JobQueue(poll_interval=0.01)
    queue.enqueue("not-callable")
    assert queue._queue.qsize() == 0  # type: ignore[attr-defined]


def test_job_queue_worker_executes_jobs_and_tracks_errors() -> None:
    queue = JobQueue(poll_interval=0.01)

    ran = {"ok": False}

    def ok_job() -> None:
        ran["ok"] = True

    def failing_job() -> None:
        raise RuntimeError("boom")

    metrics.background_job_errors = 0

    queue.start()
    queue.start()  # idempotent
    try:
        queue.enqueue(failing_job)
        queue.enqueue(ok_job)

        deadline = time.time() + 2.0
        while queue._queue.unfinished_tasks:  # type: ignore[attr-defined]
            if time.time() > deadline:
                raise AssertionError("jobs did not finish in time")
            time.sleep(0.01)
    finally:
        queue.stop()

    assert ran["ok"] is True
    assert metrics.background_job_errors >= 1
