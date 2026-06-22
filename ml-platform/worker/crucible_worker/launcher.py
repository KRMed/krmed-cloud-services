"""GPU scheduling: one worker process per GPU.

The worker defaults to one job per GPU (CLAUDE.md). Each GPU gets its own OS
process with CUDA_VISIBLE_DEVICES pinned to a single device, so every process
sees exactly one card as cuda:0 and the CUDA context is never shared. The
processes are independent consumers of the same reliable Redis queue, which
already supports multiple consumers, so adding the planned second RTX 5060 Ti is
purely a config change (CRUCIBLE_GPUS=0,1), not an architectural one.

A single GPU runs inline in this process to keep the common path simple; two or
more spawn child processes supervised here. The multiprocessing context is
injectable so the spawn plan can be tested without real processes.
"""

import logging
import os
import signal
import threading
from typing import Callable, Optional

from crucible_worker import config

logger = logging.getLogger("crucible.worker.launcher")

# A worker loop: claims and processes jobs until stop is set.
WorkerFn = Callable[[config.Config, threading.Event], None]


def _install_signal_handlers(stop: threading.Event) -> None:
    def handle(signum, _frame):
        logger.info("received signal %s; shutting down after current job", signum)
        stop.set()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            signal.signal(sig, handle)


def _run_pinned(cfg: config.Config, gpu_id: str, worker: WorkerFn) -> None:
    """Pin this process to one GPU and run the worker loop until signalled."""
    os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id
    stop = threading.Event()
    _install_signal_handlers(stop)
    logger.info("worker bound to GPU %s", gpu_id)
    worker(cfg, stop)


# Module-level so the spawn start method can pickle it as the child target.
def _child_entry(cfg: config.Config, gpu_id: str, worker: WorkerFn) -> None:
    _run_pinned(cfg, gpu_id, worker)


def run(cfg: config.Config, worker: WorkerFn, mp_context=None) -> None:
    gpu_ids = cfg.gpu_ids
    if len(gpu_ids) == 1:
        _run_pinned(cfg, gpu_ids[0], worker)
        return

    import multiprocessing

    ctx = mp_context or multiprocessing.get_context("spawn")
    procs = []
    for gpu_id in gpu_ids:
        proc = ctx.Process(
            target=_child_entry,
            args=(cfg, gpu_id, worker),
            name=f"crucible-worker-gpu{gpu_id}",
        )
        proc.start()
        procs.append(proc)
        logger.info("launched worker process for GPU %s (pid %s)", gpu_id, proc.pid)

    _supervise(procs)


def _supervise(procs) -> None:
    """Forward termination to children, then wait for them all to exit.

    If any child exits, the rest are terminated so the pod stops as a unit and
    k8s restarts it cleanly rather than running degraded.
    """
    stopping = threading.Event()

    def handle(signum, _frame):
        logger.info("received signal %s; terminating worker processes", signum)
        stopping.set()
        for proc in procs:
            if proc.is_alive():
                proc.terminate()

    for sig in (signal.SIGINT, getattr(signal, "SIGTERM", None)):
        if sig is not None:
            signal.signal(sig, handle)

    while procs:
        for proc in list(procs):
            proc.join(timeout=1.0)
            if proc.is_alive():
                continue
            procs.remove(proc)
            if not stopping.is_set():
                _terminate_remaining(procs)
                stopping.set()


def _terminate_remaining(procs) -> None:
    for proc in procs:
        if proc.is_alive():
            logger.info("terminating remaining worker process %s", proc.name)
            proc.terminate()
