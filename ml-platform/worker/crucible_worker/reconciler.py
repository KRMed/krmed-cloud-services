"""Reconciler: recover jobs Redis lost or workers abandoned.

1. Abandoned running jobs. A worker that crashed mid-run leaves a job 'running'
   in Postgres with a stale heartbeat (and its id stuck in jobs:processing).
   These are reset to 'queued' and re-enqueued.

2. Orphaned queued jobs. A job created in Postgres whose enqueue never landed
   (or was lost to a Redis flush) sits 'queued' but appears in neither
   jobs:queue nor jobs:processing. These are re-enqueued. A grace window avoids
   racing the backend's non-atomic insert-then-enqueue on fresh jobs.

Runs on startup and on a periodic tick.
"""

import logging
from dataclasses import dataclass

from crucible_worker.redis_queue import RedisQueue
from crucible_worker.repository import JobRepository
from crucible_worker.status import StatusPublisher
from shared.schema.job import JobStatus

logger = logging.getLogger("crucible.worker.reconciler")


@dataclass(frozen=True)
class ReconcileStats:
    abandoned_running: int
    orphaned_queued: int


class Reconciler:
    def __init__(
        self,
        repo: JobRepository,
        queue: RedisQueue,
        status: StatusPublisher,
        visibility_timeout_seconds: int,
        orphan_grace_seconds: int,
    ) -> None:
        self._repo = repo
        self._queue = queue
        self._status = status
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._orphan_grace_seconds = orphan_grace_seconds

    def reconcile(self) -> ReconcileStats:
        abandoned = self._recover_abandoned_running()
        orphaned = self._recover_orphaned_queued()
        if abandoned or orphaned:
            logger.info(
                "reconciled: %d abandoned running, %d orphaned queued",
                abandoned,
                orphaned,
            )
        return ReconcileStats(abandoned_running=abandoned, orphaned_queued=orphaned)

    def _recover_abandoned_running(self) -> int:
        stale = self._repo.find_stale_running(self._visibility_timeout_seconds)
        for job_id in stale:
            self._repo.reset_to_queued(job_id)
            self._status.publish(str(job_id), JobStatus.QUEUED.value)
            self._queue.requeue(str(job_id))
        return len(stale)

    def _recover_orphaned_queued(self) -> int:
        candidates = self._repo.find_orphan_queued(self._orphan_grace_seconds)
        if not candidates:
            return 0

        live = self._queue.queued_ids() | self._queue.in_flight_ids()
        recovered = 0
        for job_id in candidates:
            if str(job_id) not in live:
                self._queue.requeue(str(job_id))
                recovered += 1
        return recovered
