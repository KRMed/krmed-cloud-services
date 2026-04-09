package handler

import (
	"encoding/json"
	"io"
	"net/http"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

const maxBodyBytes = 1 << 20 // 1 MB

// writeJSON encodes v as JSON and writes it with the given HTTP status.
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError writes an error envelope with the given HTTP status.
func writeError(w http.ResponseWriter, status int, code api.ErrorCode, message string) {
	writeJSON(w, status, map[string]any{
		"error": api.APIError{Code: code, Message: message},
	})
}

// readJSON decodes the request body into v, enforcing a 1 MB size limit.
func readJSON(r *http.Request, v any) error {
	dec := json.NewDecoder(io.LimitReader(r.Body, maxBodyBytes))
	dec.DisallowUnknownFields()
	return dec.Decode(v)
}
