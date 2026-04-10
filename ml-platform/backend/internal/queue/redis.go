package queue

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/redis/go-redis/v9"
)

const (
	jobQueueKey      = "jobs:queue"
	jobStatusKeyFmt  = "jobs:status:%s"
)

// JobStatus holds the live status fields stored in Redis by the worker.
type JobStatus struct {
	Status    string
	UpdatedAt time.Time
}

// Queue wraps the Redis client with job-specific operations.
type Queue struct {
	client *redis.Client
}

// NewClient parses redisURL, pings the server, and returns a Queue.
func NewClient(ctx context.Context, redisURL string) (*Queue, error) {
	opts, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("parse redis URL: %w", err)
	}

	client := redis.NewClient(opts)
	if err := client.Ping(ctx).Err(); err != nil {
		_ = client.Close()
		return nil, fmt.Errorf("ping redis: %w", err)
	}

	return &Queue{client: client}, nil
}

// Enqueue pushes a job ID onto the left end of the job queue list.
// Workers consume from the right end via BRPOP.
func (q *Queue) Enqueue(ctx context.Context, jobID uuid.UUID) error {
	if err := q.client.LPush(ctx, jobQueueKey, jobID.String()).Err(); err != nil {
		return fmt.Errorf("enqueue job %s: %w", jobID, err)
	}
	return nil
}

// GetJobStatus fetches the live status hash written by the worker.
// Returns found=false (with no error) when the key does not exist.
func (q *Queue) GetJobStatus(ctx context.Context, jobID uuid.UUID) (JobStatus, bool, error) {
	key := fmt.Sprintf(jobStatusKeyFmt, jobID)
	vals, err := q.client.HGetAll(ctx, key).Result()
	if err != nil {
		return JobStatus{}, false, fmt.Errorf("hgetall %s: %w", key, err)
	}
	if len(vals) == 0 {
		return JobStatus{}, false, nil
	}

	js := JobStatus{Status: vals["status"]}
	if raw, ok := vals["updated_at"]; ok {
		t, err := time.Parse(time.RFC3339, raw)
		if err != nil {
			// Malformed timestamp -- treat as absent rather than hard error.
			return JobStatus{Status: js.Status}, true, nil
		}
		js.UpdatedAt = t
	}

	return js, true, nil
}

// Dequeue removes a job ID from the job queue. This is called when cancelling a
// queued job so the worker never picks it up. If the job has already been consumed
// by a worker (BRPOP), LREM returns 0 — this is not an error; the DB cancel is
// still authoritative and the worker must respect it before executing.
func (q *Queue) Dequeue(ctx context.Context, jobID uuid.UUID) error {
	if _, err := q.client.LRem(ctx, jobQueueKey, 0, jobID.String()).Result(); err != nil {
		return fmt.Errorf("dequeue job %s: %w", jobID, err)
	}
	return nil
}

// Ping checks that Redis is reachable.
func (q *Queue) Ping(ctx context.Context) error {
	if err := q.client.Ping(ctx).Err(); err != nil {
		return fmt.Errorf("redis ping: %w", err)
	}
	return nil
}

// Close shuts down the underlying Redis client.
func (q *Queue) Close() error {
	return q.client.Close()
}
