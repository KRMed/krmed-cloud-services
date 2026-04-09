package handler

import (
	"log/slog"
	"net/http"
	"strconv"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

// listModelsResponse is the response envelope for GET /models.
// Kept backend-internal until the frontend needs it in shared/api.
type listModelsResponse struct {
	Data   []db.Model `json:"data"`
	Total  int        `json:"total"`
	Limit  int        `json:"limit"`
	Offset int        `json:"offset"`
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

	writeJSON(w, http.StatusOK, listModelsResponse{
		Data:   models,
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
		if err != nil || v < 0 || v > 200 {
			return params, &api.APIError{Code: api.ErrInvalidRequest, Message: "limit must be an integer between 0 and 200"}
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
