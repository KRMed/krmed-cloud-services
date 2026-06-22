from crucible_worker.redis_queue import PROCESSING_KEY, QUEUE_KEY, RedisQueue


def test_claim_moves_job_to_processing(fake_redis, queue):
    fake_redis.lpush(QUEUE_KEY, "job-1")

    claimed = queue.claim()

    assert claimed == "job-1"
    assert queue.in_flight_ids() == {"job-1"}
    assert queue.queued_ids() == set()


def test_claim_returns_none_on_empty_queue(queue):
    assert queue.claim() is None


def test_claim_is_fifo(fake_redis, queue):
    # Producer LPUSHes (left); claim pops from the right, so oldest wins.
    fake_redis.lpush(QUEUE_KEY, "first")
    fake_redis.lpush(QUEUE_KEY, "second")

    assert queue.claim() == "first"
    assert queue.claim() == "second"


def test_ack_removes_from_processing(fake_redis, queue):
    fake_redis.lpush(QUEUE_KEY, "job-1")
    queue.claim()

    queue.ack("job-1")

    assert queue.in_flight_ids() == set()


def test_requeue_moves_processing_back_to_queue(fake_redis, queue):
    fake_redis.lpush(QUEUE_KEY, "job-1")
    queue.claim()

    queue.requeue("job-1")

    assert queue.in_flight_ids() == set()
    assert queue.queued_ids() == {"job-1"}


def test_requeue_does_not_duplicate(fake_redis, queue):
    queue.requeue("job-1")

    assert fake_redis.lrange(QUEUE_KEY, 0, -1) == ["job-1"]
    assert fake_redis.lrange(PROCESSING_KEY, 0, -1) == []
