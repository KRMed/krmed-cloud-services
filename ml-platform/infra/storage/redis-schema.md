# Redis Key Schema

Redis is used for two things only: the job queue and live status updates.
Never store files or large payloads here.

## Keys

### Job queue

```
jobs:queue
```

- Type: **LIST**
- Producer: backend (LPUSH on job creation)
- Consumer: worker (BRPOP, blocking pop)
- Value: job UUID (string) — full job details are fetched from Postgres by the worker
- One queue shared across all workers; multiple workers compete for jobs safely via BRPOP

### Live job status

```
jobs:status:{job-id}
```

- Type: **HASH**
- Producer: worker (HSET on status transitions)
- Consumer: backend (HGETALL when serving status polls)
- Fields:
  - `status`      — current JobStatus string (queued/running/completed/failed/cancelled)
  - `updated_at`  — RFC3339 timestamp of last update
- TTL: set to 24h after job reaches a terminal state (completed/failed/cancelled)

## Conventions

- All keys are namespaced with `jobs:` to avoid collisions if other services share the instance.
- The queue holds UUIDs only — workers fetch job details from Postgres to keep Redis payloads tiny.
- Status hashes are written by the worker and read by the backend; they are not the source of
  truth (Postgres is). They exist purely for low-latency polling without hitting the database
  on every frontend refresh.
