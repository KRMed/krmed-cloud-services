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
- Consumer: worker (reliable-queue pattern, **not** a naive pop)
- Value: job UUID (string) — full job details are fetched from Postgres by the worker
- One queue shared across all workers; multiple workers compete for jobs safely

Fine-tuning jobs run for hours, so a job lost on a worker crash is a real failure
mode. The worker must use a reliable-queue pattern rather than `BRPOP`:

- `BRPOPLPUSH jobs:queue jobs:processing` to atomically claim a job and move it
  to an in-flight list, then `LREM jobs:processing` on successful ack. A
  visibility timeout governs how long a claimed job may sit in `jobs:processing`
  before it is considered abandoned.
- A reconciler (run on worker startup and on a periodic tick) scans Postgres —
  the source of truth — for stale `queued`/`running` jobs with no live worker and
  re-enqueues them onto `jobs:queue`.

(Redis Streams with consumer groups and explicit ack is an acceptable
alternative implementation of the same guarantee.)

### Processing list

```
jobs:processing
```

- Type: **LIST**
- Producer/consumer: worker only (in-flight jobs claimed via `BRPOPLPUSH`)
- Value: job UUID (string)
- A job sits here from claim until ack; the reconciler re-enqueues entries that
  exceed the visibility timeout.

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
