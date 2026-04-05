package api

import "github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"

type JobResponse struct {
	Data  *schema.Job `json:"data"`
	Error *APIError   `json:"error"`
}

type ListJobsResponse struct {
	Data   []schema.Job `json:"data"`
	Total  int          `json:"total"`
	Limit  int          `json:"limit"`
	Offset int          `json:"offset"`
	Error  *APIError    `json:"error"`
}
