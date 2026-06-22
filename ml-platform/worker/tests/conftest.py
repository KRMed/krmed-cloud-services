"""Shared test fixtures and in-memory fakes.

The Postgres repository (db.py) is not unit tested here; like the Go backend's
stores it needs a live database harness. The processor and reconciler are tested
against FakeJobRepository, which implements the JobRepository Protocol in
memory. Redis-backed code is tested against fakeredis.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID, uuid4

import fakeredis
import pytest

from crucible_worker.redis_queue import RedisQueue
from crucible_worker.repository import ModelMeta
from crucible_worker.status import StatusPublisher
from shared.schema.job import Hyperparameters, Job, JobStatus


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_job(
    status: JobStatus = JobStatus.QUEUED,
    base_model: str = "mistralai/Mistral-7B-Instruct-v0.2",
    dataset_path: str = "datasets/demo/abc123.csv",
    job_id: Optional[UUID] = None,
    created_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
) -> Job:
    ts = now()
    return Job(
        id=job_id or uuid4(),
        status=status,
        base_model=base_model,
        dataset_path=dataset_path,
        hyperparameters=Hyperparameters(
            learning_rate=2e-4, epochs=3, batch_size=2, lora_rank=16, lora_alpha=32.0
        ),
        checkpoint_path=None,
        error_message=None,
        created_at=created_at or ts,
        updated_at=updated_at or ts,
    )


def comfortable_model(hf_repo_id: str = "mistralai/Mistral-7B-Instruct-v0.2") -> ModelMeta:
    return ModelMeta(
        hf_repo_id=hf_repo_id,
        revision="deadbeef",
        param_count=7_000_000_000,
        vram_hint="comfortable",
    )


class FakeJobRepository:
    """In-memory JobRepository for processor and reconciler tests."""

    def __init__(self) -> None:
        self.jobs: dict[UUID, Job] = {}
        self.models: dict[str, ModelMeta] = {}
        self.calls: list[tuple[str, UUID]] = []

    def add_job(self, job: Job) -> None:
        self.jobs[job.id] = job

    def add_model(self, meta: ModelMeta) -> None:
        self.models[meta.hf_repo_id] = meta

    def get_job(self, job_id: UUID) -> Optional[Job]:
        return self.jobs.get(job_id)

    def get_model_meta(self, hf_repo_id: str) -> Optional[ModelMeta]:
        return self.models.get(hf_repo_id)

    def mark_running(self, job_id: UUID) -> None:
        self.calls.append(("mark_running", job_id))
        job = self.jobs[job_id]
        if job.status == JobStatus.QUEUED:
            job.status = JobStatus.RUNNING
            job.updated_at = now()

    def heartbeat(self, job_id: UUID) -> None:
        self.calls.append(("heartbeat", job_id))
        job = self.jobs[job_id]
        if job.status == JobStatus.RUNNING:
            job.updated_at = now()

    def mark_completed(self, job_id: UUID, checkpoint_path: str) -> None:
        self.calls.append(("mark_completed", job_id))
        job = self.jobs[job_id]
        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.COMPLETED
            job.checkpoint_path = checkpoint_path

    def mark_failed(self, job_id: UUID, error_message: str) -> None:
        self.calls.append(("mark_failed", job_id))
        job = self.jobs[job_id]
        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.FAILED
            job.error_message = error_message

    def reset_to_queued(self, job_id: UUID) -> None:
        self.calls.append(("reset_to_queued", job_id))
        job = self.jobs[job_id]
        if job.status == JobStatus.RUNNING:
            job.status = JobStatus.QUEUED
            job.updated_at = now()

    def find_stale_running(self, older_than_seconds: int) -> list[UUID]:
        cutoff = now() - timedelta(seconds=older_than_seconds)
        return [
            jid
            for jid, job in self.jobs.items()
            if job.status == JobStatus.RUNNING and job.updated_at < cutoff
        ]

    def find_orphan_queued(self, grace_seconds: int) -> list[UUID]:
        cutoff = now() - timedelta(seconds=grace_seconds)
        return [
            jid
            for jid, job in self.jobs.items()
            if job.status == JobStatus.QUEUED
            and job.created_at < cutoff
            and job.updated_at < cutoff
        ]

    def method_calls(self, name: str) -> list[UUID]:
        return [jid for method, jid in self.calls if method == name]


@pytest.fixture
def fake_redis():
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def queue(fake_redis):
    return RedisQueue(fake_redis, block_seconds=1)


@pytest.fixture
def status(fake_redis):
    return StatusPublisher(fake_redis)


@pytest.fixture
def repo():
    return FakeJobRepository()
