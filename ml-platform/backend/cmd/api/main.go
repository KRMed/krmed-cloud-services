package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/config"
	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/handler"
	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/queue"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	slog.SetDefault(logger)

	cfg, err := config.Load()
	if err != nil {
		slog.Error("load config", "error", err)
		os.Exit(1)
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()

	pool, err := db.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("connect to postgres", "error", err)
		os.Exit(1)
	}
	defer pool.Close()

	q, err := queue.NewClient(ctx, cfg.RedisURL)
	if err != nil {
		slog.Error("connect to redis", "error", err)
		os.Exit(1)
	}
	defer q.Close()

	jobStore := db.NewJobStore(pool)
	modelStore := db.NewModelStore(pool)
	datasetStore := db.NewDatasetStore(pool)

	jobH := handler.NewJobHandler(jobStore, q)
	modelH := handler.NewModelHandler(modelStore)
	datasetH := handler.NewDatasetHandler(datasetStore)
	healthH := handler.NewHealthHandler(pool, q)

	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", healthH.Healthz)
	mux.HandleFunc("GET /readyz", healthH.Readyz)
	mux.HandleFunc("POST /jobs", jobH.CreateJob)
	mux.HandleFunc("GET /jobs", jobH.ListJobs)
	mux.HandleFunc("GET /jobs/{id}", jobH.GetJob)
	mux.HandleFunc("PATCH /jobs/{id}", jobH.UpdateJob)
	mux.HandleFunc("GET /models", modelH.ListModels)
	mux.HandleFunc("GET /datasets", datasetH.ListDatasets)

	srv := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      withMiddleware(handler.CFAccessMiddleware(mux)),
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 30 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	serverErr := make(chan error, 1)
	go func() {
		slog.Info("server starting", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			serverErr <- err
		}
	}()

	select {
	case <-ctx.Done():
		slog.Info("shutting down")
	case err := <-serverErr:
		slog.Error("server error", "error", err)
		stop()
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
	}
}

// withMiddleware wraps the mux with request logging and panic recovery.
func withMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		rw := &statusWriter{ResponseWriter: w, status: http.StatusOK}

		defer func() {
			if p := recover(); p != nil {
				slog.ErrorContext(r.Context(), "panic recovered", "panic", p)
				rw.Header().Set("Content-Type", "application/json")
				rw.WriteHeader(http.StatusInternalServerError)
				_ = json.NewEncoder(rw).Encode(map[string]any{
					"error": api.APIError{Code: api.ErrInternalServer, Message: "internal server error"},
				})
			}
			slog.InfoContext(r.Context(), "request",
				"method", r.Method,
				"path", r.URL.Path,
				"status", rw.status,
				"duration_ms", time.Since(start).Milliseconds(),
			)
		}()

		next.ServeHTTP(rw, r)
	})
}

// statusWriter captures the HTTP status code written by a handler.
type statusWriter struct {
	http.ResponseWriter
	status int
}

func (sw *statusWriter) WriteHeader(status int) {
	sw.status = status
	sw.ResponseWriter.WriteHeader(status)
}
