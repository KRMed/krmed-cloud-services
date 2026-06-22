from uuid import uuid4

import pytest

from crucible_worker.executor import StubExecutor, checkpoint_prefix
from crucible_worker.processor import JobProcessor
from crucible_worker.redis_queue import PROCESSING_KEY
from crucible_worker.repository import ModelMeta
from shared.schema.job import JobStatus
from tests.conftest import comfortable_model, make_job


@pytest.fixture
def stub_processor(repo, queue, status):
    return JobProcessor(repo, queue, status, StubExecutor())


def _simulate_claim(fake_redis, job_id: str) -> None:
    # BRPOPLPUSH would have left the id in the processing list.
    fake_redis.lpush(PROCESSING_KEY, job_id)


def test_completes_valid_job(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.QUEUED)
    repo.add_job(job)
    repo.add_model(comfortable_model(job.base_model))
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    stored = repo.jobs[job.id]
    assert stored.status == JobStatus.COMPLETED
    assert stored.checkpoint_path == checkpoint_prefix(job)
    assert queue.in_flight_ids() == set()
    assert fake_redis.hget(f"jobs:status:{job.id}", "status") == "completed"


def test_heartbeat_recorded_during_run(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.QUEUED)
    repo.add_job(job)
    repo.add_model(comfortable_model(job.base_model))
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    assert repo.method_calls("heartbeat") == [job.id]


def test_cancelled_job_is_skipped(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.CANCELLED)
    repo.add_job(job)
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    assert repo.method_calls("mark_running") == []
    assert repo.jobs[job.id].status == JobStatus.CANCELLED
    assert queue.in_flight_ids() == set()


def test_unsupported_dataset_fails_job(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.QUEUED, dataset_path="datasets/demo/x.txt")
    repo.add_job(job)
    repo.add_model(comfortable_model(job.base_model))
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    stored = repo.jobs[job.id]
    assert stored.status == JobStatus.FAILED
    assert "txt" in stored.error_message
    assert queue.in_flight_ids() == set()
    assert fake_redis.hget(f"jobs:status:{job.id}", "status") == "failed"


def test_unknown_model_fails_job(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.QUEUED)
    repo.add_job(job)  # no allow-list entry
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    stored = repo.jobs[job.id]
    assert stored.status == JobStatus.FAILED
    assert "allow-list" in stored.error_message
    assert queue.in_flight_ids() == set()


def test_oversized_model_fails_job(repo, queue, status, fake_redis, stub_processor):
    job = make_job(status=JobStatus.QUEUED)
    repo.add_job(job)
    repo.add_model(
        ModelMeta(job.base_model, "rev", 70_000_000_000, "unsupported")
    )
    _simulate_claim(fake_redis, str(job.id))

    stub_processor.process(str(job.id))

    assert repo.jobs[job.id].status == JobStatus.FAILED
    assert queue.in_flight_ids() == set()


def test_malformed_job_id_is_discarded(repo, queue, status, fake_redis, stub_processor):
    _simulate_claim(fake_redis, "not-a-uuid")

    stub_processor.process("not-a-uuid")

    assert queue.in_flight_ids() == set()
    assert repo.calls == []


def test_missing_job_is_acked(repo, queue, status, fake_redis, stub_processor):
    job_id = uuid4()
    _simulate_claim(fake_redis, str(job_id))

    stub_processor.process(str(job_id))

    assert queue.in_flight_ids() == set()


class _RaisingExecutor:
    def run(self, job, model, heartbeat):
        raise RuntimeError("cuda exploded")


def test_executor_failure_marks_job_failed(repo, queue, status, fake_redis):
    job = make_job(status=JobStatus.QUEUED)
    repo.add_job(job)
    repo.add_model(comfortable_model(job.base_model))
    _simulate_claim(fake_redis, str(job.id))
    processor = JobProcessor(repo, queue, status, _RaisingExecutor())

    processor.process(str(job.id))

    stored = repo.jobs[job.id]
    assert stored.status == JobStatus.FAILED
    assert "cuda exploded" in stored.error_message
    assert queue.in_flight_ids() == set()
