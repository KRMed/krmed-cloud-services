package queue

import (
	"fmt"
	"testing"

	"github.com/google/uuid"
)

func TestJobQueueKey(t *testing.T) {
	if jobQueueKey != "jobs:queue" {
		t.Errorf("jobQueueKey = %q, want %q", jobQueueKey, "jobs:queue")
	}
}

func TestJobStatusKeyFormat(t *testing.T) {
	id := uuid.MustParse("123e4567-e89b-12d3-a456-426614174000")
	key := fmt.Sprintf(jobStatusKeyFmt, id)
	want := "jobs:status:123e4567-e89b-12d3-a456-426614174000"
	if key != want {
		t.Errorf("status key = %q, want %q", key, want)
	}
}
