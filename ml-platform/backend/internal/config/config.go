package config

import (
	"fmt"
	"os"
	"strings"
)

// Config holds all runtime configuration loaded from environment variables.
type Config struct {
	Port             string
	DatabaseURL      string
	RedisURL         string
	GarageEndpoint   string
	GarageAccessKey  string
	GarageSecretKey  string
	GarageBucket     string
}

// Load reads configuration from environment variables and returns an error
// listing every missing required variable so operators can fix all issues
// in one restart.
func Load() (*Config, error) {
	var missing []string

	get := func(key string) string {
		v := os.Getenv(key)
		if v == "" {
			missing = append(missing, key)
		}
		return v
	}

	cfg := &Config{
		DatabaseURL:     get("DATABASE_URL"),
		RedisURL:        get("REDIS_URL"),
		GarageEndpoint:  get("GARAGE_ENDPOINT"),
		GarageAccessKey: get("GARAGE_ACCESS_KEY"),
		GarageSecretKey: get("GARAGE_SECRET_KEY"),
		GarageBucket:    get("GARAGE_BUCKET"),
	}

	if len(missing) > 0 {
		return nil, fmt.Errorf("missing required environment variables: %s", strings.Join(missing, ", "))
	}

	cfg.Port = os.Getenv("PORT")
	if cfg.Port == "" {
		cfg.Port = "8080"
	}

	return cfg, nil
}
