package handler

import (
	"log/slog"
	"net/http"
	"strconv"

	"github.com/KRMed/krmed-cloud-services/ml-platform/backend/internal/db"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

// listDatasetsResponse is the response envelope for GET /datasets.
// Kept backend-internal until the frontend needs it in shared/api.
type listDatasetsResponse struct {
	Data   []db.Dataset `json:"data"`
	Total  int          `json:"total"`
	Limit  int          `json:"limit"`
	Offset int          `json:"offset"`
}

// DatasetHandler handles dataset registry endpoints.
type DatasetHandler struct {
	datasets *db.DatasetStore
}

// NewDatasetHandler creates a DatasetHandler.
func NewDatasetHandler(datasets *db.DatasetStore) *DatasetHandler {
	return &DatasetHandler{datasets: datasets}
}

// ListDatasets handles GET /datasets.
func (h *DatasetHandler) ListDatasets(w http.ResponseWriter, r *http.Request) {
	params, apiErr := parseListDatasetsParams(r)
	if apiErr != nil {
		writeError(w, http.StatusUnprocessableEntity, apiErr.Code, apiErr.Message)
		return
	}

	datasets, total, err := h.datasets.List(r.Context(), params)
	if err != nil {
		slog.ErrorContext(r.Context(), "list datasets", "error", err)
		writeError(w, http.StatusInternalServerError, api.ErrInternalServer, "failed to list datasets")
		return
	}

	writeJSON(w, http.StatusOK, listDatasetsResponse{
		Data:   datasets,
		Total:  total,
		Limit:  params.Limit,
		Offset: params.Offset,
	})
}

func parseListDatasetsParams(r *http.Request) (db.ListDatasetsParams, *api.APIError) {
	params := db.ListDatasetsParams{Limit: 50}
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
