"""Worker loop and entrypoint.

main() resolves config then hands off to the launcher, which runs one worker
loop per GPU (CUDA_VISIBLE_DEVICES pinned). run() is that per-GPU loop: it runs
the reconciler once at startup, then loops, claiming a job (blocking up to
queue_block_seconds), processing it, and running the reconciler on its interval.
The blocking claim timeout bounds how long shutdown and the reconciler wait.
"""

import logging
import threading
import time

import redis

from crucible_worker import config, launcher
from crucible_worker.checkpoint_store import GarageCheckpointStore
from crucible_worker.dataset_store import GarageDatasetStore
from crucible_worker.db import PostgresJobRepository
from crucible_worker.executor import CachingExecutor
from crucible_worker.model_cache import HFModelCache
from crucible_worker.processor import JobProcessor
from crucible_worker.reconciler import Reconciler
from crucible_worker.redis_queue import RedisQueue
from crucible_worker.status import StatusPublisher
from crucible_worker.trainer import UnslothQLoRATrainer

logger = logging.getLogger("crucible.worker")


def run(cfg: config.Config, stop: threading.Event) -> None:
    client = redis.Redis.from_url(cfg.redis_url, decode_responses=True)
    repo = PostgresJobRepository(cfg.database_url)
    queue = RedisQueue(client, cfg.queue_block_seconds)
    status = StatusPublisher(client)
    cache = HFModelCache(cfg.model_cache_dir)
    dataset_store = GarageDatasetStore.from_config(cfg)
    store = GarageCheckpointStore.from_config(cfg)
    executor = CachingExecutor(
        cache, dataset_store, UnslothQLoRATrainer(), store
    )

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
    logger.info("crucible worker starting on GPU(s) %s", ",".join(cfg.gpu_ids))
    launcher.run(cfg, run)
    logger.info("crucible worker stopped")


if __name__ == "__main__":
    main()
