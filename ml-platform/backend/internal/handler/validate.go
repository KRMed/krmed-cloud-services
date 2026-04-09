package handler

import (
	"fmt"
	"strings"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

// validateCreateJob checks all fields of a CreateJobRequest.
// Returns a single APIError containing all violations, or nil if valid.
func validateCreateJob(req api.CreateJobRequest) *api.APIError {
	var errs []string

	if strings.TrimSpace(req.BaseModel) == "" {
		errs = append(errs, "base_model is required")
	}
	if strings.TrimSpace(req.DatasetPath) == "" {
		errs = append(errs, "dataset_path is required")
	}

	hp := req.Hyperparameters
	if hp.LearningRate <= 0 || hp.LearningRate > 1 {
		errs = append(errs, "learning_rate must be in (0, 1]")
	}
	if hp.Epochs <= 0 {
		errs = append(errs, "epochs must be > 0")
	}
	if hp.BatchSize <= 0 {
		errs = append(errs, "batch_size must be > 0")
	}
	if hp.LoraRank <= 0 {
		errs = append(errs, "lora_rank must be > 0")
	}
	if hp.LoraAlpha <= 0 {
		errs = append(errs, "lora_alpha must be > 0")
	}

	if len(errs) > 0 {
		return &api.APIError{
			Code:    api.ErrInvalidRequest,
			Message: strings.Join(errs, "; "),
		}
	}
	return nil
}

// validateListJobsParams validates pagination and status filter values.
func validateListJobsParams(params api.ListJobsParams) *api.APIError {
	var errs []string

	if params.Limit != nil && *params.Limit < 1 {
		errs = append(errs, "limit must be >= 1")
	}
	if params.Limit != nil && *params.Limit > 200 {
		errs = append(errs, "limit must be <= 200")
	}
	if params.Offset != nil && *params.Offset < 0 {
		errs = append(errs, "offset must be >= 0")
	}
	if params.Status != nil {
		switch *params.Status {
		case schema.JobStatusQueued, schema.JobStatusRunning,
			schema.JobStatusCompleted, schema.JobStatusFailed,
			schema.JobStatusCancelled:
			// valid
		default:
			errs = append(errs, fmt.Sprintf("unknown status %q", *params.Status))
		}
	}

	if len(errs) > 0 {
		return &api.APIError{Code: api.ErrInvalidRequest, Message: strings.Join(errs, "; ")}
	}
	return nil
}

// PatchJobRequest is the body accepted by PATCH /jobs/{id}.
type PatchJobRequest struct {
	Action string `json:"action"`
}

// validateJobUpdate ensures the patch body is a known action.
func validateJobUpdate(req PatchJobRequest) *api.APIError {
	if req.Action != "cancel" {
		return &api.APIError{
			Code:    api.ErrInvalidRequest,
			Message: fmt.Sprintf("unknown action %q; only \"cancel\" is supported", req.Action),
		}
	}
	return nil
}
