package handler

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// okHandler is a trivial handler that always returns 200.
var okHandler = http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
	w.WriteHeader(http.StatusOK)
})

func TestCFAccessMiddleware_ProbeExempt(t *testing.T) {
	h := CFAccessMiddleware(okHandler)

	for _, path := range []string{"/healthz", "/readyz"} {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)

		if w.Code != http.StatusOK {
			t.Errorf("path %s: want 200 (probe exempt), got %d", path, w.Code)
		}
	}
}

func TestCFAccessMiddleware_MissingHeader(t *testing.T) {
	h := CFAccessMiddleware(okHandler)

	req := httptest.NewRequest(http.MethodGet, "/jobs", nil)
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestCFAccessMiddleware_WithHeader(t *testing.T) {
	h := CFAccessMiddleware(okHandler)

	req := httptest.NewRequest(http.MethodGet, "/jobs", nil)
	req.Header.Set("Cf-Access-Authenticated-User-Email", "user@example.com")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

func TestCFAccessMiddleware_EmailInContext(t *testing.T) {
	var capturedEmail string
	capture := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		capturedEmail = UserEmail(r.Context())
		w.WriteHeader(http.StatusOK)
	})

	h := CFAccessMiddleware(capture)
	req := httptest.NewRequest(http.MethodPost, "/jobs", nil)
	req.Header.Set("Cf-Access-Authenticated-User-Email", "alice@example.com")
	w := httptest.NewRecorder()
	h.ServeHTTP(w, req)

	if capturedEmail != "alice@example.com" {
		t.Errorf("want email in context, got %q", capturedEmail)
	}
}
