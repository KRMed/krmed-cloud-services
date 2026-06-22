"""Job execution seam.

The Executor runs the actual QLoRA fine-tune: read the base model from the HDD
cache, train, and upload the LoRA adapter checkpoint to Garage. The real
implementation lands in Phase 5C (it depends on the pinned Blackwell stack and a
smoke test on the real card). The worker core orchestrates around this Protocol
so the trainer drops in without touching the queue lifecycle.

StubExecutor lets the core run end to end without a GPU: it performs no
training and returns the deterministic Garage checkpoint prefix the real trainer
will write to.
"""

from dataclasses import dataclass
from typing import Callable, Protocol

from shared.schema.job import Job

from crucible_worker.repository import ModelMeta


@dataclass(frozen=True)
class ExecutionResult:
    checkpoint_path: str


class Executor(Protocol):
    def run(
        self, job: Job, model: ModelMeta, heartbeat: Callable[[], None]
    ) -> ExecutionResult:
        """Run the fine-tune and return the Garage checkpoint path.

        Long runs must call heartbeat() periodically so the reconciler does not
        treat the job as abandoned. Raises on failure; the processor records the
        error and acks the job.
        """
        ...


def checkpoint_prefix(job: Job) -> str:
    """Garage prefix a job's LoRA adapter checkpoint is written under."""
    return f"checkpoints/{job.id}/"


class StubExecutor:
    """No-op executor used until the QLoRA trainer (Phase 5C) is built."""

    def run(
        self, job: Job, model: ModelMeta, heartbeat: Callable[[], None]
    ) -> ExecutionResult:
        heartbeat()
        return ExecutionResult(checkpoint_path=checkpoint_prefix(job))
