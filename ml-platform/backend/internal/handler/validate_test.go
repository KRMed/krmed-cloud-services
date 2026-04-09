package handler

import (
	"testing"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

func TestValidateCreateJob(t *testing.T) {
	validHP := schema.Hyperparameters{
		LearningRate: 2e-4,
		Epochs:       3,
		BatchSize:    4,
		LoraRank:     8,
		LoraAlpha:    16,
	}

	tests := []struct {
		name    string
		req     api.CreateJobRequest
		wantErr bool
	}{
		{
			name: "valid request",
			req:  api.CreateJobRequest{BaseModel: "mistral-7b", DatasetPath: "s3://bucket/data.csv", Hyperparameters: validHP},
		},
		{
			name:    "missing base_model",
			req:     api.CreateJobRequest{DatasetPath: "s3://bucket/data.csv", Hyperparameters: validHP},
			wantErr: true,
		},
		{
			name:    "missing dataset_path",
			req:     api.CreateJobRequest{BaseModel: "mistral-7b", Hyperparameters: validHP},
			wantErr: true,
		},
		{
			name: "learning_rate zero",
			req: api.CreateJobRequest{
				BaseModel: "mistral-7b", DatasetPath: "s3://bucket/data.csv",
				Hyperparameters: schema.Hyperparameters{LearningRate: 0, Epochs: 1, BatchSize: 1, LoraRank: 1, LoraAlpha: 1},
			},
			wantErr: true,
		},
		{
			name: "learning_rate above 1",
			req: api.CreateJobRequest{
				BaseModel: "mistral-7b", DatasetPath: "s3://bucket/data.csv",
				Hyperparameters: schema.Hyperparameters{LearningRate: 1.1, Epochs: 1, BatchSize: 1, LoraRank: 1, LoraAlpha: 1},
			},
			wantErr: true,
		},
		{
			name: "negative epochs",
			req: api.CreateJobRequest{
				BaseModel: "mistral-7b", DatasetPath: "s3://bucket/data.csv",
				Hyperparameters: schema.Hyperparameters{LearningRate: 1e-3, Epochs: -1, BatchSize: 1, LoraRank: 1, LoraAlpha: 1},
			},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateCreateJob(tt.req)
			if tt.wantErr && err == nil {
				t.Error("expected error, got nil")
			}
			if !tt.wantErr && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}

func TestValidateListJobsParams(t *testing.T) {
	intPtr := func(v int) *int { return &v }
	statusPtr := func(s schema.JobStatus) *schema.JobStatus { return &s }

	tests := []struct {
		name    string
		params  api.ListJobsParams
		wantErr bool
	}{
		{name: "empty params"},
		{name: "valid status", params: api.ListJobsParams{Status: statusPtr(schema.JobStatusQueued)}},
		{name: "valid limit", params: api.ListJobsParams{Limit: intPtr(10)}},
		{name: "limit zero", params: api.ListJobsParams{Limit: intPtr(0)}},
		{name: "limit at max", params: api.ListJobsParams{Limit: intPtr(200)}},
		{name: "limit over max", params: api.ListJobsParams{Limit: intPtr(201)}, wantErr: true},
		{name: "negative limit", params: api.ListJobsParams{Limit: intPtr(-1)}, wantErr: true},
		{name: "negative offset", params: api.ListJobsParams{Offset: intPtr(-1)}, wantErr: true},
		{
			name:    "unknown status",
			params:  api.ListJobsParams{Status: statusPtr("unknown")},
			wantErr: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateListJobsParams(tt.params)
			if tt.wantErr && err == nil {
				t.Error("expected error, got nil")
			}
			if !tt.wantErr && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}

func TestValidateJobUpdate(t *testing.T) {
	tests := []struct {
		name    string
		req     PatchJobRequest
		wantErr bool
	}{
		{name: "cancel", req: PatchJobRequest{Action: "cancel"}},
		{name: "empty action", req: PatchJobRequest{Action: ""}, wantErr: true},
		{name: "unknown action", req: PatchJobRequest{Action: "pause"}, wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateJobUpdate(tt.req)
			if tt.wantErr && err == nil {
				t.Error("expected error, got nil")
			}
			if !tt.wantErr && err != nil {
				t.Errorf("unexpected error: %v", err)
			}
		})
	}
}
