package handler

import (
	"context"
	"net/http"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
)

// ctxKey is an unexported type for context keys set by this package.
type ctxKey int

const ctxUserEmail ctxKey = 0

// CFAccessMiddleware enforces Cloudflare Access authentication on all routes
// except the k8s probe endpoints. Cloudflare Access injects the
// Cf-Access-Authenticated-User-Email header into every request it forwards
// after successful authentication. Requests arriving without this header
// have not passed through CF Access and are rejected with 401.
//
// /healthz and /readyz are exempt so k8s liveness and readiness probes
// can reach the origin directly without CF Access credentials.
func CFAccessMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/healthz" || r.URL.Path == "/readyz" {
			next.ServeHTTP(w, r)
			return
		}

		email := r.Header.Get("Cf-Access-Authenticated-User-Email")
		if email == "" {
			writeError(w, http.StatusUnauthorized, api.ErrUnauthorized, "Cloudflare Access authentication required")
			return
		}

		ctx := context.WithValue(r.Context(), ctxUserEmail, email)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// UserEmail returns the authenticated user's email from the request context.
// Returns an empty string if the middleware was not applied or the route is exempt.
func UserEmail(ctx context.Context) string {
	email, _ := ctx.Value(ctxUserEmail).(string)
	return email
}
