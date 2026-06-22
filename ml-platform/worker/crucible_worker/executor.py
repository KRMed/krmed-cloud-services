"""Job execution seam.

The Executor turns a claimed job into a Garage checkpoint path. CachingExecutor
is the production implementation: it reads the base model from the HDD cache
(downloading from HF on a miss), runs the trainer into a temporary directory,
and uploads the resulting LoRA adapter to Garage. All of that is
GPU-independent; the only GPU concern is the injected Trainer.

The Trainer is the inner seam that Phase 5C fills with the real Unsloth QLoRA
trainer. It receives a local model path and an output directory and only has to
train; the cache and upload plumbing lives in CachingExecutor and never has to
change. StubTrainer keeps the whole chain runnable without a GPU.

StubExecutor remains a no-op Executor used to drive the processor lifecycle in
tests without touching HF or Garage.
"""

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from shared.schema.job import Job

from crucible_worker.checkpoint_store import CheckpointStore
from crucible_worker.model_cache import ModelCache
from crucible_worker.repository import ModelMeta

logger = logging.getLogger("crucible.worker.executor")


@dataclass(frozen=True)
class ExecutionResult:
    checkpoint_path: str


class Trainer(Protocol):
    def train(
        self,
        job: Job,
        model_path: Path,
        output_dir: Path,
        heartbeat: Callable[[], None],
    ) -> None:
        """Run the QLoRA fine-tune, writing the LoRA adapter into output_dir.

        Phase 5C implements this against the pinned Blackwell stack. Long runs
        must call heartbeat() periodically so the reconciler does not treat the
        job as abandoned. Raises on failure.
        """
        ...


class Executor(Protocol):
    def run(
        self, job: Job, model: ModelMeta, heartbeat: Callable[[], None]
    ) -> ExecutionResult:
        """Run the fine-tune and return the Garage checkpoint path.

        Raises on failure; the processor records the error and acks the job.
        """
        ...


def checkpoint_prefix(job: Job) -> str:
    """Garage prefix a job's LoRA adapter checkpoint is written under."""
    return f"checkpoints/{job.id}/"


class CachingExecutor:
    """Wraps the trainer seam with the model cache and the checkpoint uploader."""

    def __init__(
        self, cache: ModelCache, trainer: Trainer, store: CheckpointStore
    ) -> None:
        self._cache = cache
        self._trainer = trainer
        self._store = store

    def run(
        self, job: Job, model: ModelMeta, heartbeat: Callable[[], None]
    ) -> ExecutionResult:
        model_path = self._cache.ensure(model)
        heartbeat()

        with tempfile.TemporaryDirectory(prefix=f"crucible-{job.id}-") as tmp:
            output_dir = Path(tmp)
            self._trainer.train(job, model_path, output_dir, heartbeat)
            checkpoint_path = self._store.upload(job.id, output_dir)

        return ExecutionResult(checkpoint_path=checkpoint_path)


class StubTrainer:
    """Placeholder trainer used until the QLoRA trainer (Phase 5C) is built.

    Writes a marker file so the cache -> train -> upload chain runs end to end
    without a GPU. Phase 5C replaces this with the real Unsloth trainer.
    """

    def train(
        self,
        job: Job,
        model_path: Path,
        output_dir: Path,
        heartbeat: Callable[[], None],
    ) -> None:
        heartbeat()
        (output_dir / "STUB_ADAPTER.txt").write_text(
            f"stub adapter for job {job.id}; replaced by the Phase 5C trainer\n",
            encoding="utf-8",
        )


class StubExecutor:
    """No-op Executor used to drive the processor lifecycle in tests."""

    def run(
        self, job: Job, model: ModelMeta, heartbeat: Callable[[], None]
    ) -> ExecutionResult:
        heartbeat()
        return ExecutionResult(checkpoint_path=checkpoint_prefix(job))
