package schema

import (
	"time"

	"github.com/google/uuid"
)

type JobStatus string

const (
	JobStatusQueued    JobStatus = "queued"
	JobStatusRunning   JobStatus = "running"
	JobStatusCompleted JobStatus = "completed"
	JobStatusFailed    JobStatus = "failed"
	JobStatusCancelled JobStatus = "cancelled"
)

type Hyperparameters struct {
	LearningRate float64 `json:"learning_rate"`
	Epochs       int     `json:"epochs"`
	BatchSize    int     `json:"batch_size"`
	LoraRank     int     `json:"lora_rank"`
	LoraAlpha    float64 `json:"lora_alpha"`
}

type Job struct {
	ID               uuid.UUID       `json:"id"`
	Status           JobStatus       `json:"status"`
	BaseModel        string          `json:"base_model"`
	DatasetPath      string          `json:"dataset_path"`
	Hyperparameters  Hyperparameters `json:"hyperparameters"`
	CheckpointPath   *string         `json:"checkpoint_path"`
	ErrorMessage     *string         `json:"error_message"`
	CreatedAt        time.Time       `json:"created_at"`
	UpdatedAt        time.Time       `json:"updated_at"`
}
