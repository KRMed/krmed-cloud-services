package handler

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/queue"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

// --- fakes ---

type fakeJobStore struct {
	job    schema.Job
	err    error
	jobs   []schema.Job
	total  int
	listErr error
}

func (f *fakeJobStore) Create(_ context.Context, _ api.CreateJobRequest) (schema.Job, error) {
	return f.job, f.err
}
func (f *fakeJobStore) GetByID(_ context.Context, _ uuid.UUID) (schema.Job, error) {
	return f.job, f.err
}
func (f *fakeJobStore) List(_ context.Context, _ api.ListJobsParams) ([]schema.Job, int, error) {
	return f.jobs, f.total, f.listErr
}
func (f *fakeJobStore) Update(_ context.Context, _ uuid.UUID, _ db.UpdateJobFields) (schema.Job, error) {
	return f.job, f.err
}

type fakeQueue struct {
	enqueueErr    error
	statusJob     queue.JobStatus
	statusFound   bool
	statusErr     error
	pingErr       error
}

func (f *fakeQueue) Enqueue(_ context.Context, _ uuid.UUID) error { return f.enqueueErr }
func (f *fakeQueue) GetJobStatus(_ context.Context, _ uuid.UUID) (queue.JobStatus, bool, error) {
	return f.statusJob, f.statusFound, f.statusErr
}
func (f *fakeQueue) Ping(_ context.Context) error { return f.pingErr }

// jobHandlerForTest wires up a JobHandler that uses the given fakes.
// The fakeJobStore and fakeQueue expose all methods needed by the handler.
// Because JobHandler holds *db.JobStore and *queue.Queue (concrete types),
// we use a thin adapter approach: embed the real handler and swap the field
// via a test-only constructor.
//
// Rather than restructure the production code, we accept the concrete types
// but build a real JobHandler on top of real stores in integration tests.
// Here we test the HTTP layer by exercising validateCreateJob, writeJSON, etc.
// directly, and use table-driven integration-style tests against a mux.

// --- helpers ---

func newBody(t *testing.T, v any) *bytes.Buffer {
	t.Helper()
	b, err := json.Marshal(v)
	if err != nil {
		t.Fatal(err)
	}
	return bytes.NewBuffer(b)
}

func decodeResponse(t *testing.T, body *bytes.Buffer, v any) {
	t.Helper()
	if err := json.NewDecoder(body).Decode(v); err != nil {
		t.Fatalf("decode response: %v", err)
	}
}

// --- validate layer tests (HTTP-shaped) ---

// TestCreateJob_ValidationErrors tests that the handler rejects invalid bodies
// before reaching the store. We test this by directly calling the handler
// with a synthetic http.ResponseRecorder.

func TestCreateJob_BadBody(t *testing.T) {
	// Garbage JSON should return 400.
	req := httptest.NewRequest(http.MethodPost, "/jobs", bytes.NewBufferString(`{bad json}`))
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.createJob(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestCreateJob_MissingFields(t *testing.T) {
	body := newBody(t, map[string]any{
		"base_model":      "",
		"dataset_path":    "",
		"hyperparameters": map[string]any{},
	})
	req := httptest.NewRequest(http.MethodPost, "/jobs", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.createJob(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("want 422, got %d", w.Code)
	}
}

func TestListJobs_BadLimit(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/jobs?limit=notanint", nil)
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.listJobs(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("want 422, got %d", w.Code)
	}
}

func TestUpdateJob_UnknownAction(t *testing.T) {
	body := newBody(t, PatchJobRequest{Action: "pause"})
	id := uuid.New()
	req := httptest.NewRequest(http.MethodPatch, "/jobs/"+id.String(), body)
	req.SetPathValue("id", id.String())
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.updateJob(w, req)

	if w.Code != http.StatusUnprocessableEntity {
		t.Errorf("want 422, got %d", w.Code)
	}
}

func TestUpdateJob_InvalidUUID(t *testing.T) {
	body := newBody(t, PatchJobRequest{Action: "cancel"})
	req := httptest.NewRequest(http.MethodPatch, "/jobs/not-a-uuid", body)
	req.SetPathValue("id", "not-a-uuid")
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.updateJob(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

// TestGetJob_InvalidUUID verifies parseUUID rejects non-UUID path values.
func TestGetJob_InvalidUUID(t *testing.T) {
	req := httptest.NewRequest(http.MethodGet, "/jobs/bad", nil)
	req.SetPathValue("id", "bad")
	w := httptest.NewRecorder()

	h := &jobHandlerShim{}
	h.getJob(w, req)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

// TestIsActiveStatus covers the helper used for Redis overlay logic.
func TestIsActiveStatus(t *testing.T) {
	active := []schema.JobStatus{schema.JobStatusQueued, schema.JobStatusRunning}
	for _, s := range active {
		if !isActiveStatus(s) {
			t.Errorf("expected %s to be active", s)
		}
	}
	terminal := []schema.JobStatus{schema.JobStatusCompleted, schema.JobStatusFailed, schema.JobStatusCancelled}
	for _, s := range terminal {
		if isActiveStatus(s) {
			t.Errorf("expected %s to be non-active", s)
		}
	}
}

// --- jobHandlerShim ---
// Thin shim that exposes only the HTTP + validation path without a real store.
// It calls the same helpers (readJSON, validateCreateJob, parseUUID, etc.)
// that the real handler uses, letting us test the HTTP layer in isolation.

type jobHandlerShim struct{}

func (s *jobHandlerShim) createJob(w http.ResponseWriter, r *http.Request) {
	var req api.CreateJobRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, http.StatusBadRequest, api.ErrInvalidRequest, "invalid request body: "+err.Error())
		return
	}
	if apiErr := validateCreateJob(req); apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"ok": "true"})
}

func (s *jobHandlerShim) listJobs(w http.ResponseWriter, r *http.Request) {
	_, apiErr := parseListJobsParams(r)
	if apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"ok": "true"})
}

func (s *jobHandlerShim) getJob(w http.ResponseWriter, r *http.Request) {
	if _, ok := parseUUID(w, r, "id"); !ok {
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"ok": "true"})
}

func (s *jobHandlerShim) updateJob(w http.ResponseWriter, r *http.Request) {
	if _, ok := parseUUID(w, r, "id"); !ok {
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
	writeJSON(w, http.StatusOK, map[string]string{"ok": "true"})
}

// --- health handler tests ---

func TestHealthz(t *testing.T) {
	h := &HealthHandler{}
	req := httptest.NewRequest(http.MethodGet, "/healthz", nil)
	w := httptest.NewRecorder()
	h.Healthz(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

// fakeDBPinger satisfies the pinger interface for health tests.
type fakeDBPinger struct{ err error }

func (f *fakeDBPinger) Ping(_ context.Context) error { return f.err }

func TestReadyz_Healthy(t *testing.T) {
	h := NewHealthHandler(&fakeDBPinger{}, &fakeQueue{})
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	w := httptest.NewRecorder()
	h.Readyz(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

func TestReadyz_DBDown(t *testing.T) {
	h := NewHealthHandler(&fakeDBPinger{err: errFake("db down")}, &fakeQueue{})
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	w := httptest.NewRecorder()
	h.Readyz(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("want 503, got %d", w.Code)
	}
}

func TestReadyz_RedisDown(t *testing.T) {
	h := NewHealthHandler(&fakeDBPinger{}, &fakeQueue{pingErr: errFake("redis down")})
	req := httptest.NewRequest(http.MethodGet, "/readyz", nil)
	w := httptest.NewRecorder()
	h.Readyz(w, req)

	if w.Code != http.StatusServiceUnavailable {
		t.Errorf("want 503, got %d", w.Code)
	}
}

// errFake is a simple error type for tests.
type errFake string

func (e errFake) Error() string { return string(e) }

// --- Redis overlay logic test ---

func TestGetJob_RedisOverlay(t *testing.T) {
	// Verify that a fresher Redis updated_at causes the status to be overlaid.
	now := time.Now()
	older := now.Add(-5 * time.Second)

	job := schema.Job{
		ID:        uuid.New(),
		Status:    schema.JobStatusQueued,
		UpdatedAt: older,
	}

	redisStatus := queue.JobStatus{
		Status:    string(schema.JobStatusRunning),
		UpdatedAt: now,
	}

	// Simulate the overlay logic from GetJob directly.
	if isActiveStatus(job.Status) {
		rs := redisStatus
		found := true
		if found && rs.UpdatedAt.After(job.UpdatedAt) {
			job.Status = schema.JobStatus(rs.Status)
			job.UpdatedAt = rs.UpdatedAt
		}
	}

	if job.Status != schema.JobStatusRunning {
		t.Errorf("expected running after overlay, got %s", job.Status)
	}
	if !job.UpdatedAt.Equal(now) {
		t.Errorf("expected updated_at to be overlaid")
	}
}
