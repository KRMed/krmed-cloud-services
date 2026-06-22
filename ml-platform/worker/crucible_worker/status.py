"""Live job status publisher.

The worker writes a small status hash to Redis (jobs:status:{id}) on every
transition. The backend reads it to serve low-latency status polls without
hitting Postgres on every frontend refresh. This is a cache, not the source of
truth: Postgres is authoritative.

The timestamp is RFC3339 with a numeric offset and no fractional seconds, which
the Go backend parses with time.RFC3339.
"""

from datetime import datetime, timezone

import redis

STATUS_KEY_FMT = "jobs:status:{}"
TERMINAL_TTL_SECONDS = 24 * 3600


def _now_rfc3339() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StatusPublisher:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def publish(self, job_id: str, status: str, terminal: bool = False) -> None:
        """Write the status hash, expiring it 24h after a terminal transition."""
        key = STATUS_KEY_FMT.format(job_id)
        pipe = self._client.pipeline()
        pipe.hset(key, mapping={"status": status, "updated_at": _now_rfc3339()})
        if terminal:
            pipe.expire(key, TERMINAL_TTL_SECONDS)
        pipe.execute()
