package handler

import (
	"context"
	"net/http"
	"time"
)

// pinger is anything that can be pinged (pgxpool.Pool and queue.Queue both satisfy this).
type pinger interface {
	Ping(ctx context.Context) error
}

// HealthHandler serves liveness and readiness probes.
type HealthHandler struct {
	db    pinger
	queue pinger
}

// NewHealthHandler creates a HealthHandler with the given dependency pingers.
func NewHealthHandler(db pinger, queue pinger) *HealthHandler {
	return &HealthHandler{db: db, queue: queue}
}

// Healthz is the liveness probe. Always returns 200.
func (h *HealthHandler) Healthz(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// Readyz is the readiness probe. Pings Postgres and Redis; returns 503 if either fails.
func (h *HealthHandler) Readyz(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()

	checks := map[string]string{
		"postgres": "ok",
		"redis":    "ok",
	}
	healthy := true

	if err := h.db.Ping(ctx); err != nil {
		checks["postgres"] = err.Error()
		healthy = false
	}
	if err := h.queue.Ping(ctx); err != nil {
		checks["redis"] = err.Error()
		healthy = false
	}

	status := http.StatusOK
	if !healthy {
		status = http.StatusServiceUnavailable
	}
	writeJSON(w, status, map[string]any{"checks": checks})
}
