from datetime import timedelta

from crucible_worker.reconciler import Reconciler
from crucible_worker.redis_queue import PROCESSING_KEY, QUEUE_KEY
from shared.schema.job import JobStatus
from tests.conftest import make_job, now

VISIBILITY = 15 * 60
GRACE = 60


def _reconciler(repo, queue, status):
    return Reconciler(repo, queue, status, VISIBILITY, GRACE)


def test_abandoned_running_job_is_requeued(repo, queue, status):
    old = now() - timedelta(seconds=20 * 60)
    job = make_job(status=JobStatus.RUNNING, created_at=old, updated_at=old)
    repo.add_job(job)

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.abandoned_running == 1
    assert repo.jobs[job.id].status == JobStatus.QUEUED
    assert queue.queued_ids() == {str(job.id)}


def test_live_running_job_is_left_alone(repo, queue, status):
    job = make_job(status=JobStatus.RUNNING)  # heartbeat is fresh
    repo.add_job(job)

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.abandoned_running == 0
    assert repo.jobs[job.id].status == JobStatus.RUNNING
    assert queue.queued_ids() == set()


def test_orphan_queued_job_is_requeued(repo, queue, status):
    old = now() - timedelta(seconds=5 * 60)
    job = make_job(status=JobStatus.QUEUED, created_at=old, updated_at=old)
    repo.add_job(job)  # never landed in Redis

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.orphaned_queued == 1
    assert queue.queued_ids() == {str(job.id)}


def test_queued_job_already_in_redis_is_not_requeued(repo, queue, status, fake_redis):
    old = now() - timedelta(seconds=5 * 60)
    job = make_job(status=JobStatus.QUEUED, created_at=old, updated_at=old)
    repo.add_job(job)
    fake_redis.lpush(QUEUE_KEY, str(job.id))

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.orphaned_queued == 0
    assert fake_redis.lrange(QUEUE_KEY, 0, -1) == [str(job.id)]


def test_queued_job_in_flight_is_not_requeued(repo, queue, status, fake_redis):
    old = now() - timedelta(seconds=5 * 60)
    job = make_job(status=JobStatus.QUEUED, created_at=old, updated_at=old)
    repo.add_job(job)
    fake_redis.lpush(PROCESSING_KEY, str(job.id))

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.orphaned_queued == 0
    assert queue.queued_ids() == set()


def test_fresh_queued_job_within_grace_is_ignored(repo, queue, status):
    job = make_job(status=JobStatus.QUEUED)  # created just now
    repo.add_job(job)

    stats = _reconciler(repo, queue, status).reconcile()

    assert stats.orphaned_queued == 0
    assert queue.queued_ids() == set()
