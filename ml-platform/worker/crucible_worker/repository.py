"""Job repository contract.

Postgres is the source of truth for job state. The processor and reconciler
depend on this Protocol, not on psycopg2 directly, so they can be unit tested
against an in-memory fake (the same pattern the Go backend uses with its
jobStorer interface). PostgresJobRepository in db.py is the production
implementation.
"""

from dataclasses import dataclass
from typing import Optional, Protocol
from uuid import UUID

from shared.schema.job import Job


@dataclass(frozen=True)
class ModelMeta:
    """Allow-list metadata for a base model, used by the preflight guardrail."""

    hf_repo_id: str
    revision: str
    param_count: Optional[int]
    vram_hint: Optional[str]


class JobRepository(Protocol):
    def get_job(self, job_id: UUID) -> Optional[Job]:
        """Return the job, or None if it does not exist."""
        ...

    def get_model_meta(self, hf_repo_id: str) -> Optional[ModelMeta]:
        """Return allow-list metadata for the model's default revision, or None."""
        ...

    def mark_running(self, job_id: UUID) -> None:
        """Transition a job to 'running' and bump updated_at."""
        ...

    def heartbeat(self, job_id: UUID) -> None:
        """Bump updated_at for a running job so the reconciler sees it as live."""
        ...

    def mark_completed(self, job_id: UUID, checkpoint_path: str) -> None:
        """Transition a job to 'completed' and record its Garage checkpoint path."""
        ...

    def mark_failed(self, job_id: UUID, error_message: str) -> None:
        """Transition a job to 'failed' and record the reason."""
        ...

    def reset_to_queued(self, job_id: UUID) -> None:
        """Return an abandoned running job to 'queued' for re-execution."""
        ...

    def find_stale_running(self, older_than_seconds: int) -> list[UUID]:
        """Return running jobs whose heartbeat is older than the given age."""
        ...

    def find_orphan_queued(self, grace_seconds: int) -> list[UUID]:
        """Return queued jobs older than grace_seconds (candidates for re-enqueue)."""
        ...
