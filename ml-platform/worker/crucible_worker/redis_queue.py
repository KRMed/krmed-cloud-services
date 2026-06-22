"""Redis reliable-queue consumer.

Fine-tune jobs run for hours, so a job lost on a worker crash is a real failure
mode. The worker claims jobs with BRPOPLPUSH (not a naive BRPOP): the job id
moves atomically from jobs:queue to jobs:processing, where it stays until the
worker acks it with LREM. A crash leaves the id in jobs:processing; the
reconciler (which trusts Postgres) re-enqueues it.

The backend produces with LPUSH (left) and the worker claims from the right, so
the queue is FIFO. Re-enqueues use LPUSH to match the producer.
"""

from typing import Optional

import redis

QUEUE_KEY = "jobs:queue"
PROCESSING_KEY = "jobs:processing"


class RedisQueue:
    def __init__(self, client: redis.Redis, block_seconds: int) -> None:
        self._client = client
        self._block_seconds = block_seconds

    def claim(self) -> Optional[str]:
        """Block up to block_seconds for a job, moving it to the processing list.

        Returns the job id string, or None on timeout so the caller can run the
        reconciler and re-check its stop signal.
        """
        return self._client.brpoplpush(
            QUEUE_KEY, PROCESSING_KEY, timeout=self._block_seconds
        )

    def ack(self, job_id: str) -> None:
        """Remove a fully handled job from the in-flight processing list."""
        self._client.lrem(PROCESSING_KEY, 0, job_id)

    def requeue(self, job_id: str) -> None:
        """Return a job to the pending queue, clearing any stale processing entry.

        Used by the reconciler for abandoned or orphaned jobs. Idempotent: the
        LREM clears the processing list and the LPUSH re-adds the job exactly
        once even if it was never in flight.
        """
        pipe = self._client.pipeline()
        pipe.lrem(PROCESSING_KEY, 0, job_id)
        pipe.lpush(QUEUE_KEY, job_id)
        pipe.execute()

    def queued_ids(self) -> set[str]:
        return set(self._client.lrange(QUEUE_KEY, 0, -1))

    def in_flight_ids(self) -> set[str]:
        return set(self._client.lrange(PROCESSING_KEY, 0, -1))

    def ping(self) -> None:
        self._client.ping()
