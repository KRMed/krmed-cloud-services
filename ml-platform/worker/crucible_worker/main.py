"""Worker entrypoint.

Runs the reconciler once at startup, then loops: claim a job (blocking up to
queue_block_seconds), process it, and run the reconciler on its interval. The
blocking claim timeout bounds how long shutdown and the reconciler wait.
"""

import logging
import signal
import threading
import time

import redis

from crucible_worker import config
from crucible_worker.checkpoint_store import GarageCheckpointStore
from crucible_worker.db import PostgresJobRepository
from crucible_worker.executor import CachingExecutor, StubTrainer
from crucible_worker.model_cache import HFModelCache
from crucible_worker.processor import JobProcessor
from crucible_worker.reconciler import Reconciler
from crucible_worker.redis_queue import RedisQueue
from crucible_worker.status import StatusPublisher

logger = logging.getLogger("crucible.worker")


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle(signum, _frame):
        logger.info("received signal %s; shutting down after current job", signum)
        stop.set()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            signal.signal(sig, handle)


def run(cfg: config.Config, stop: threading.Event) -> None:
    client = redis.Redis.from_url(cfg.redis_url, decode_responses=True)
    repo = PostgresJobRepository(cfg.database_url)
    queue = RedisQueue(client, cfg.queue_block_seconds)
    status = StatusPublisher(client)
    cache = HFModelCache(cfg.model_cache_dir)
    store = GarageCheckpointStore.from_config(cfg)
    # StubTrainer is the Phase 5C drop-in point; cache + upload run for real.
    executor = CachingExecutor(cache, StubTrainer(), store)

    processor = JobProcessor(repo, queue, status, executor)
    reconciler = Reconciler(
        repo,
        queue,
        status,
        cfg.visibility_timeout_seconds,
        cfg.orphan_grace_seconds,
    )

    try:
        reconciler.reconcile()
        last_reconcile = time.monotonic()

        while not stop.is_set():
            raw_job_id = queue.claim()
            if raw_job_id is not None:
                processor.process(raw_job_id)

            if time.monotonic() - last_reconcile >= cfg.reconcile_interval_seconds:
                reconciler.reconcile()
                last_reconcile = time.monotonic()
    finally:
        client.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = config.load()
    stop = threading.Event()
    _install_signal_handlers(stop)
    logger.info("crucible worker starting")
    run(cfg, stop)
    logger.info("crucible worker stopped")


if __name__ == "__main__":
    main()
