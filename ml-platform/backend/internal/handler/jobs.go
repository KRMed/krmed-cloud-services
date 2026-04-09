package handler

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/google/uuid"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/queue"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

// JobHandler handles all job-related HTTP endpoints.
type JobHandler struct {
	jobs  *db.JobStore
	queue *queue.Queue
}

// NewJobHandler creates a JobHandler with the given stores.
func NewJobHandler(jobs *db.JobStore, q *queue.Queue) *JobHandler {
	return &JobHandler{jobs: jobs, queue: q}
}

// CreateJob handles POST /jobs.
// Inserts a job record and enqueues it. If enqueue fails, marks the job failed.
func (h *JobHandler) CreateJob(w http.ResponseWriter, r *http.Request) {
	var req api.CreateJobRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, api.ErrInvalidRequest, "invalid request body: "+err.Error())
		return
	}

	if apiErr := validateCreateJob(req); apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}

	job, err := h.jobs.Create(r.Context(), req)
	if err != nil {
		slog.ErrorContext(r.Context(), "create job", "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to create job")
		return
	}

	if err := h.queue.Enqueue(r.Context(), job.ID); err != nil {
		slog.ErrorContext(r.Context(), "enqueue job", "job_id", job.ID, "error", err)
		// Best-effort: mark the job failed so it isn't stuck in queued forever.
		errMsg := "enqueue failed: " + err.Error()
		status := schema.JobStatusFailed
		_, _ = h.jobs.Update(context.Background(), job.ID, db.UpdateJobFields{
			Status:       &status,
			ErrorMessage: &errMsg,
		})
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "job created but could not be enqueued")
		return
	}

	writeJSON(w, http.StatusCreated, api.JobResponse{Data: &job})
}

// GetJob handles GET /jobs/{id}.
// For non-terminal jobs, overlays fresher status from Redis if available.
func (h *JobHandler) GetJob(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id")
	if !ok {
		return
	}

	job, err := h.jobs.GetByID(r.Context(), id)
	if errors.Is(err, db.ErrJobNotFound) {
		writeError(w, http.StatusNotFound, api.ErrJobNotFound, "job not found")
		return
	}
	if err != nil {
		slog.ErrorContext(r.Context(), "get job", "job_id", id, "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to fetch job")
		return
	}

	// For active jobs, check Redis for a fresher updated_at from the worker.
	if isActiveStatus(job.Status) {
		if rs, found, err := h.queue.GetJobStatus(r.Context(), job.ID); err == nil && found {
			if rs.UpdatedAt.After(job.UpdatedAt) {
				job.Status = schema.JobStatus(rs.Status)
				job.UpdatedAt = rs.UpdatedAt
			}
		}
		// Redis errors are non-fatal: degrade gracefully to Postgres data.
	}

	writeJSON(w, http.StatusOK, api.JobResponse{Data: &job})
}

// ListJobs handles GET /jobs.
func (h *JobHandler) ListJobs(w http.ResponseWriter, r *http.Request) {
	params, apiErr := parseListJobsParams(r)
	if apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}

	jobs, total, err := h.jobs.List(r.Context(), params)
	if err != nil {
		slog.ErrorContext(r.Context(), "list jobs", "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to list jobs")
		return
	}

	limit := 50
	offset := 0
	if params.Limit != nil {
		limit = *params.Limit
	}
	if params.Offset != nil {
		offset = *params.Offset
	}

	writeJSON(w, http.StatusOK, api.ListJobsResponse{
		Data:   jobs,
		Total:  total,
		Limit:  limit,
		Offset: offset,
	})
}

// UpdateJob handles PATCH /jobs/{id}. Only the "cancel" action is supported.
func (h *JobHandler) UpdateJob(w http.ResponseWriter, r *http.Request) {
	id, ok := parseUUID(w, r, "id")
	if !ok {
		return
	}

	var req PatchJobRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, api.ErrInvalidRequest, "invalid request body: "+err.Error())
		return
	}

	if apiErr := validateJobUpdate(req); apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}

	status := schema.JobStatusCancelled
	job, err := h.jobs.Update(r.Context(), id, db.UpdateJobFields{Status: &status})
	if errors.Is(err, db.ErrJobNotFound) {
		writeError(w, http.StatusNotFound, api.ErrJobNotFound, "job not found")
		return
	}
	var transErr *db.ErrInvalidTransition
	if errors.As(err, &transErr) {
		writeError(w, http.StatusConflict, api.ErrInvalidRequest, transErr.Error())
		return
	}
	if err != nil {
		slog.ErrorContext(r.Context(), "cancel job", "job_id", id, "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to cancel job")
		return
	}

	// Remove from Redis queue so the worker never picks up a cancelled job.
	// If the job was already consumed (BRPOP), Dequeue is a no-op; the DB
	// cancel is still authoritative.
	if err := h.queue.Dequeue(r.Context(), id); err != nil {
		slog.WarnContext(r.Context(), "dequeue cancelled job", "job_id", id, "error", err)
	}

	writeJSON(w, http.StatusOK, api.JobResponse{Data: &job})
}

// parseUUID extracts a UUID path parameter by name, writing a 400 on failure.
func parseUUID(w http.ResponseWriter, r *http.Request, param string) (uuid.UUID, bool) {
	raw := r.PathValue(param)
	id, err := uuid.Parse(raw)
	if err != nil {
		writeError(w, http.StatusBadRequest, api.ErrInvalidRequest, "invalid job ID")
		return uuid.UUID{}, false
	}
	return id, true
}

// parseListJobsParams reads query params into a ListJobsParams, validating them.
func parseListJobsParams(r *http.Request) (api.ListJobsParams, *api.APIError) {
	params := api.ListJobsParams{}
	q := r.URL.Query()

	if s := q.Get("status"); s != "" {
		st := schema.JobStatus(s)
		params.Status = &st
	}
	if s := q.Get("limit"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil {
			return params, &api.APIError{Code: api.ErrInvalidRequest, Message: "limit must be an integer"}
		}
		params.Limit = &v
	}
	if s := q.Get("offset"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil {
			return params, &api.APIError{Code: api.ErrInvalidRequest, Message: "offset must be an integer"}
		}
		params.Offset = &v
	}

	if apiErr := validateListJobsParams(params); apiErr != nil {
		return params, apiErr
	}
	return params, nil
}

// isActiveStatus reports whether a job status is non-terminal.
func isActiveStatus(s schema.JobStatus) bool {
	return s == schema.JobStatusQueued || s == schema.JobStatusRunning
}
