package handler

import (
	"encoding/json"
	"errors"
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
// Returns an error if the body contains trailing content after the first JSON value.
func readJSON(r *http.Request, v any) error {
	dec := json.NewDecoder(io.LimitReader(r.Body, maxBodyBytes))
	dec.DisallowUnknownFields()
	if err := dec.Decode(v); err != nil {
		return err
	}
	if err := dec.Decode(&json.RawMessage{}); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain a single JSON object")
	}
	return nil
}
