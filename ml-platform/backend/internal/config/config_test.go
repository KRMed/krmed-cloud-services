package config

import (
	"os"
	"testing"
)

func TestLoad_MissingVars(t *testing.T) {
	// Ensure none of the required vars are set.
	required := []string{
		"DATABASE_URL", "REDIS_URL",
		"GARAGE_ENDPOINT", "GARAGE_ACCESS_KEY", "GARAGE_SECRET_KEY", "GARAGE_BUCKET",
	}
	for _, k := range required {
		t.Setenv(k, "")
	}

	_, err := Load()
	if err == nil {
		t.Fatal("expected error when required vars are missing, got nil")
	}

	// Error should mention all missing vars.
	msg := err.Error()
	for _, k := range required {
		if !contains(msg, k) {
			t.Errorf("error message missing var %q: %s", k, msg)
		}
	}
}

func TestLoad_AllVarsSet(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://user:pass@localhost/db")
	t.Setenv("REDIS_URL", "redis://localhost:6379")
	t.Setenv("GARAGE_ENDPOINT", "http://localhost:3900")
	t.Setenv("GARAGE_ACCESS_KEY", "access")
	t.Setenv("GARAGE_SECRET_KEY", "secret")
	t.Setenv("GARAGE_BUCKET", "crucible")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	if cfg.DatabaseURL != "postgres://user:pass@localhost/db" {
		t.Errorf("DatabaseURL = %q", cfg.DatabaseURL)
	}
	if cfg.RedisURL != "redis://localhost:6379" {
		t.Errorf("RedisURL = %q", cfg.RedisURL)
	}
	if cfg.Port != "8080" {
		t.Errorf("Port = %q, want default 8080", cfg.Port)
	}
}

func TestLoad_PortOverride(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://x")
	t.Setenv("REDIS_URL", "redis://x")
	t.Setenv("GARAGE_ENDPOINT", "http://x")
	t.Setenv("GARAGE_ACCESS_KEY", "x")
	t.Setenv("GARAGE_SECRET_KEY", "x")
	t.Setenv("GARAGE_BUCKET", "x")
	t.Setenv("PORT", "9090")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != "9090" {
		t.Errorf("Port = %q, want 9090", cfg.Port)
	}

	os.Unsetenv("PORT")
}

func TestLoad_PartialMissing(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://x")
	t.Setenv("REDIS_URL", "")
	t.Setenv("GARAGE_ENDPOINT", "")
	t.Setenv("GARAGE_ACCESS_KEY", "")
	t.Setenv("GARAGE_SECRET_KEY", "")
	t.Setenv("GARAGE_BUCKET", "")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for partial missing vars")
	}
	// DATABASE_URL is set, should NOT appear in the error.
	if contains(err.Error(), "DATABASE_URL") {
		t.Errorf("error incorrectly mentions DATABASE_URL: %s", err.Error())
	}
}

func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(s) > 0 && containsStr(s, sub))
}

func containsStr(s, sub string) bool {
	for i := range s {
		if i+len(sub) <= len(s) && s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}
