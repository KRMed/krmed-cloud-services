package api

import "github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"

type CreateJobRequest struct {
	BaseModel       string                  `json:"base_model"`
	DatasetPath     string                  `json:"dataset_path"`
	Hyperparameters schema.Hyperparameters  `json:"hyperparameters"`
}

type ListJobsParams struct {
	Status *schema.JobStatus `json:"status,omitempty"`
	Limit  *int              `json:"limit,omitempty"`
	Offset *int              `json:"offset,omitempty"`
}
