package db

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

func TestJobRow_ToSchema(t *testing.T) {
	hp := schema.Hyperparameters{
		LearningRate: 2e-4,
		Epochs:       3,
		BatchSize:    4,
		LoraRank:     8,
		LoraAlpha:    16,
	}
	hpJSON, _ := json.Marshal(hp)

	id := uuid.New()
	now := time.Now().UTC().Truncate(time.Second)
	ckpt := "checkpoints/abc"
	errMsg := "something failed"

	tests := []struct {
		name    string
		row     jobRow
		wantErr bool
	}{
		{
			name: "minimal queued job",
			row: jobRow{
				ID:              id,
				Status:          "queued",
				BaseModel:       "mistralai/Mistral-7B-v0.1",
				DatasetPath:     "datasets/train.csv",
				Hyperparameters: hpJSON,
				CreatedAt:       now,
				UpdatedAt:       now,
			},
		},
		{
			name: "completed job with checkpoint",
			row: jobRow{
				ID:              id,
				Status:          "completed",
				BaseModel:       "meta-llama/Llama-3-8B",
				DatasetPath:     "datasets/train.parquet",
				Hyperparameters: hpJSON,
				CheckpointPath:  &ckpt,
				CreatedAt:       now,
				UpdatedAt:       now,
			},
		},
		{
			name: "failed job with error message",
			row: jobRow{
				ID:              id,
				Status:          "failed",
				BaseModel:       "google/gemma-7b",
				DatasetPath:     "datasets/bad.json",
				Hyperparameters: hpJSON,
				ErrorMessage:    &errMsg,
				CreatedAt:       now,
				UpdatedAt:       now,
			},
		},
		{
			name:    "malformed hyperparameters",
			row:     jobRow{Hyperparameters: []byte(`not json`)},
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			j, err := tc.row.toSchema()
			if tc.wantErr {
				if err == nil {
					t.Fatal("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}

			if j.ID != tc.row.ID {
				t.Errorf("ID mismatch: got %v, want %v", j.ID, tc.row.ID)
			}
			if j.Status != schema.JobStatus(tc.row.Status) {
				t.Errorf("Status mismatch: got %v, want %v", j.Status, tc.row.Status)
			}
			if j.CheckpointPath != tc.row.CheckpointPath {
				t.Errorf("CheckpointPath mismatch")
			}
			if j.ErrorMessage != tc.row.ErrorMessage {
				t.Errorf("ErrorMessage mismatch")
			}
			if j.Hyperparameters.LearningRate != hp.LearningRate {
				t.Errorf("LearningRate mismatch: got %v, want %v", j.Hyperparameters.LearningRate, hp.LearningRate)
			}
		})
	}
}

func TestValidateTransition(t *testing.T) {
	tests := []struct {
		from    schema.JobStatus
		to      schema.JobStatus
		wantErr bool
	}{
		// Allowed transitions
		{schema.JobStatusQueued, schema.JobStatusRunning, false},
		{schema.JobStatusQueued, schema.JobStatusCancelled, false},
		{schema.JobStatusRunning, schema.JobStatusCompleted, false},
		{schema.JobStatusRunning, schema.JobStatusFailed, false},
		{schema.JobStatusRunning, schema.JobStatusCancelled, false},

		// Disallowed: terminal -> any
		{schema.JobStatusCompleted, schema.JobStatusRunning, true},
		{schema.JobStatusFailed, schema.JobStatusQueued, true},
		{schema.JobStatusCancelled, schema.JobStatusRunning, true},

		// Disallowed: skip states
		{schema.JobStatusQueued, schema.JobStatusCompleted, true},
		{schema.JobStatusQueued, schema.JobStatusFailed, true},
		{schema.JobStatusRunning, schema.JobStatusQueued, true},
	}

	for _, tc := range tests {
		err := validateTransition(tc.from, tc.to)
		if tc.wantErr && err == nil {
			t.Errorf("validateTransition(%s, %s): expected error, got nil", tc.from, tc.to)
		}
		if !tc.wantErr && err != nil {
			t.Errorf("validateTransition(%s, %s): unexpected error: %v", tc.from, tc.to, err)
		}
	}
}

func TestErrInvalidTransition_Error(t *testing.T) {
	e := &ErrInvalidTransition{From: schema.JobStatusQueued, To: schema.JobStatusCompleted}
	msg := e.Error()
	if msg == "" {
		t.Error("expected non-empty error message")
	}
}

func TestStatusToStringPtr(t *testing.T) {
	if statusToStringPtr(nil) != nil {
		t.Error("expected nil for nil input")
	}
	s := schema.JobStatusRunning
	ptr := statusToStringPtr(&s)
	if ptr == nil {
		t.Fatal("expected non-nil pointer")
	}
	if *ptr != "running" {
		t.Errorf("got %q, want %q", *ptr, "running")
	}
}
