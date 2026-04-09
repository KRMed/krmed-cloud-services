package handler

import (
	"log/slog"
	"net/http"
	"strconv"
	"time"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

// modelResponse is the API representation of a model registry entry.
type modelResponse struct {
	ID        int       `json:"id"`
	Name      string    `json:"name"`
	Version   string    `json:"version"`
	Status    string    `json:"status"`
	IsDefault bool      `json:"is_default"`
	SizeBytes int64     `json:"size_bytes"`
	SourceURL *string   `json:"source_url"`
	CreatedAt time.Time `json:"created_at"`
}

func toModelResponse(m db.Model) modelResponse {
	return modelResponse{
		ID:        m.ID,
		Name:      m.Name,
		Version:   m.Version,
		Status:    m.Status,
		IsDefault: m.IsDefault,
		SizeBytes: m.SizeBytes,
		SourceURL: m.SourceURL,
		CreatedAt: m.CreatedAt,
	}
}

// listModelsResponse is the response envelope for GET /models.
// Kept backend-internal until the frontend needs it in shared/api.
type listModelsResponse struct {
	Data   []modelResponse `json:"data"`
	Total  int             `json:"total"`
	Limit  int             `json:"limit"`
	Offset int             `json:"offset"`
}

// ModelHandler handles model registry endpoints.
type ModelHandler struct {
	models *db.ModelStore
}

// NewModelHandler creates a ModelHandler.
func NewModelHandler(models *db.ModelStore) *ModelHandler {
	return &ModelHandler{models: models}
}

// ListModels handles GET /models.
func (h *ModelHandler) ListModels(w http.ResponseWriter, r *http.Request) {
	params, apiErr := parseListModelsParams(r)
	if apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}

	models, total, err := h.models.List(r.Context(), params)
	if err != nil {
		slog.ErrorContext(r.Context(), "list models", "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to list models")
		return
	}

	data := make([]modelResponse, len(models))
	for i, m := range models {
		data[i] = toModelResponse(m)
	}
	writeJSON(w, http.StatusOK, listModelsResponse{
		Data:   data,
		Total:  total,
		Limit:  params.Limit,
		Offset: params.Offset,
	})
}

func parseListModelsParams(r *http.Request) (db.ListModelsParams, *api.APIError) {
	params := db.ListModelsParams{Limit: 50}
	q := r.URL.Query()

	if s := q.Get("status"); s != "" {
		params.Status = &s
	}
	if s := q.Get("name"); s != "" {
		params.Name = s
	}
	if s := q.Get("limit"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil || v < 1 || v > 200 {
			return params, &api.APIError{Code: api.ErrInvalidRequest, Message: "limit must be an integer between 1 and 200"}
		}
		params.Limit = v
	}
	if s := q.Get("offset"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil || v < 0 {
			return params, &api.APIError{Code: api.ErrInvalidRequest, Message: "offset must be a non-negative integer"}
		}
		params.Offset = v
	}

	return params, nil
}
