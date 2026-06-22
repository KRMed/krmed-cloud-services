"""Runtime configuration loaded from environment variables.

Mirrors the backend config contract (DATABASE_URL, REDIS_URL, GARAGE_*) so the
worker and backend agree on the same services. Fails fast at startup listing
every missing variable, the same way the Go backend does.
"""

import os
from dataclasses import dataclass

# Garage credentials are required even though the queue core does not use them:
# the checkpoint upload (Phase 5B) does, and failing fast at startup is better
# than discovering a missing credential hours into a fine-tune run.
REQUIRED_ENV = [
    "DATABASE_URL",
    "REDIS_URL",
    "GARAGE_ENDPOINT",
    "GARAGE_ACCESS_KEY",
    "GARAGE_SECRET_KEY",
    "GARAGE_BUCKET",
]

DEFAULT_MODEL_CACHE_DIR = "/var/crucible/models"
DEFAULT_QUEUE_BLOCK_SECONDS = 5
DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 15 * 60
DEFAULT_RECONCILE_INTERVAL_SECONDS = 5 * 60
DEFAULT_ORPHAN_GRACE_SECONDS = 60
# One worker process per GPU id, each pinned via CUDA_VISIBLE_DEVICES. Default is
# the single RTX 5060 Ti; set CRUCIBLE_GPUS=0,1 to drive the planned dual card.
DEFAULT_GPU_IDS = ("0",)


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass(frozen=True)
class Config:
    database_url: str
    redis_url: str
    garage_endpoint: str
    garage_access_key: str
    garage_secret_key: str
    garage_bucket: str
    # Local HDD read-through cache for base models (Phase 5B reads from here).
    model_cache_dir: str
    # How long a single blocking queue claim waits before looping to run the
    # reconciler and re-check the stop signal.
    queue_block_seconds: int
    # A running job whose heartbeat is older than this is considered abandoned
    # by the reconciler and re-enqueued. Must exceed the executor heartbeat
    # interval by a wide margin so long fine-tunes are never falsely reclaimed.
    visibility_timeout_seconds: int
    reconcile_interval_seconds: int
    # A freshly created job may exist in Postgres before the backend's enqueue
    # LPUSH lands. The reconciler ignores queued jobs younger than this so it
    # does not race that window and double-enqueue.
    orphan_grace_seconds: int
    # GPU ids to run a worker process on, one job per GPU. A trailing default
    # keeps every existing keyword construction (including tests) valid.
    gpu_ids: tuple[str, ...] = DEFAULT_GPU_IDS


def _gpu_ids_env(key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(key)
    if raw is None or raw.strip() == "":
        return default
    ids = tuple(part.strip() for part in raw.split(",") if part.strip())
    if not ids:
        raise ConfigError(f"{key} is set but lists no GPU ids, got {raw!r}")
    return ids


def _int_env(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be an integer, got {raw!r}") from exc


def load() -> Config:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        raise ConfigError(
            f"missing required environment variables: {', '.join(missing)}"
        )

    return Config(
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        garage_endpoint=os.environ["GARAGE_ENDPOINT"],
        garage_access_key=os.environ["GARAGE_ACCESS_KEY"],
        garage_secret_key=os.environ["GARAGE_SECRET_KEY"],
        garage_bucket=os.environ["GARAGE_BUCKET"],
        model_cache_dir=os.environ.get("MODEL_CACHE_DIR", DEFAULT_MODEL_CACHE_DIR),
        queue_block_seconds=_int_env("QUEUE_BLOCK_SECONDS", DEFAULT_QUEUE_BLOCK_SECONDS),
        visibility_timeout_seconds=_int_env(
            "VISIBILITY_TIMEOUT_SECONDS", DEFAULT_VISIBILITY_TIMEOUT_SECONDS
        ),
        reconcile_interval_seconds=_int_env(
            "RECONCILE_INTERVAL_SECONDS", DEFAULT_RECONCILE_INTERVAL_SECONDS
        ),
        orphan_grace_seconds=_int_env(
            "ORPHAN_GRACE_SECONDS", DEFAULT_ORPHAN_GRACE_SECONDS
        ),
        gpu_ids=_gpu_ids_env("CRUCIBLE_GPUS", DEFAULT_GPU_IDS),
    )
