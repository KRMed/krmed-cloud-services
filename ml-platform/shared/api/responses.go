package api

import "github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"

type JobResponse struct {
	Data  *schema.Job `json:"data"`
	Error *string     `json:"error"`
}

type ListJobsResponse struct {
	Data   []schema.Job `json:"data"`
	Total  int          `json:"total"`
	Limit  int          `json:"limit"`
	Offset int          `json:"offset"`
	Error  *string      `json:"error"`
}
