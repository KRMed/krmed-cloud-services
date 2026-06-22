"""Single-job processing: claim to ack.

Handles one job id pulled off the reliable queue. The job is acked (removed from
jobs:processing) in every terminal outcome, including rejection and failure, so
nothing is left dangling in the in-flight list. Only an unexpected crash leaves
the id in jobs:processing for the reconciler to recover.

Rejections (unsupported dataset format, oversized model) are surfaced as a
failed job with an error message, the contract the rest of the platform expects.
"""

import logging
from uuid import UUID

from shared.schema.job import JobStatus

from crucible_worker.executor import Executor
from crucible_worker.guardrail import OversizedModelError, check_model_fits
from crucible_worker.redis_queue import RedisQueue
from crucible_worker.repository import JobRepository
from crucible_worker.status import StatusPublisher
from crucible_worker.validation import (
    UnsupportedDatasetFormatError,
    validate_dataset_format,
)

logger = logging.getLogger("crucible.worker.processor")

# A job already in one of these states must not be executed.
_TERMINAL_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)


class JobProcessor:
    def __init__(
        self,
        repo: JobRepository,
        queue: RedisQueue,
        status: StatusPublisher,
        executor: Executor,
    ) -> None:
        self._repo = repo
        self._queue = queue
        self._status = status
        self._executor = executor

    def process(self, raw_job_id: str) -> None:
        try:
            job_id = UUID(raw_job_id)
        except ValueError:
            logger.warning("discarding malformed job id %r from queue", raw_job_id)
            self._queue.ack(raw_job_id)
            return

        job = self._repo.get_job(job_id)
        if job is None:
            logger.warning("job %s not found in Postgres; acking", job_id)
            self._queue.ack(raw_job_id)
            return

        if job.status in _TERMINAL_STATUSES:
            # Most commonly a job cancelled by the backend after it was claimed.
            logger.info("job %s already %s; skipping", job_id, job.status.value)
            self._queue.ack(raw_job_id)
            return

        try:
            self._run(job)
        except (UnsupportedDatasetFormatError, OversizedModelError) as rejection:
            self._fail(raw_job_id, job_id, str(rejection))
        except Exception as exc:  # noqa: BLE001 - any failure must mark the job failed
            logger.exception("job %s failed during execution", job_id)
            self._fail(raw_job_id, job_id, f"worker error: {exc}")
        else:
            self._queue.ack(raw_job_id)

    def _run(self, job) -> None:
        self._repo.mark_running(job.id)
        self._status.publish(str(job.id), JobStatus.RUNNING.value)

        validate_dataset_format(job.dataset_path)

        model = self._repo.get_model_meta(job.base_model)
        if model is None:
            raise OversizedModelError(
                f"base model {job.base_model!r} is not in the allow-list"
            )
        check_model_fits(model.param_count, model.vram_hint)

        def heartbeat() -> None:
            self._repo.heartbeat(job.id)
            self._status.publish(str(job.id), JobStatus.RUNNING.value)

        result = self._executor.run(job, model, heartbeat)

        self._repo.mark_completed(job.id, result.checkpoint_path)
        self._status.publish(str(job.id), JobStatus.COMPLETED.value, terminal=True)
        logger.info("job %s completed -> %s", job.id, result.checkpoint_path)

    def _fail(self, raw_job_id: str, job_id: UUID, message: str) -> None:
        self._repo.mark_failed(job_id, message)
        self._status.publish(str(job_id), JobStatus.FAILED.value, terminal=True)
        self._queue.ack(raw_job_id)
        logger.info("job %s failed: %s", job_id, message)
