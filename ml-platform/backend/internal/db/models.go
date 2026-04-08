package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Model mirrors the columns of the models table returned to the API layer.
type Model struct {
	ID             int
	Name           string
	Version        string
	StoragePath    string
	PathType       string
	SizeBytes      int64
	Sha256Checksum string
	Status         string
	IsDefault      bool
	SourceURL      *string
	ArchivedAt     *time.Time
	CreatedAt      time.Time
}

// ListModelsParams controls filtering and pagination for model queries.
type ListModelsParams struct {
	// Status filters by registry status. Defaults to "ready" when nil.
	Status *string
	// Name filters by case-insensitive substring match when non-empty.
	Name   string
	Limit  int
	Offset int
}

// ModelStore handles database access for the model registry.
type ModelStore struct {
	pool *pgxpool.Pool
}

// NewModelStore creates a ModelStore backed by the given connection pool.
func NewModelStore(pool *pgxpool.Pool) *ModelStore {
	return &ModelStore{pool: pool}
}

const modelColumns = `id, name, version, storage_path, path_type, size_bytes,
                      sha256_checksum, status, is_default, source_url, archived_at, created_at`

func scanModel(rows pgx.Rows) (Model, error) {
	m := Model{}
	err := rows.Scan(
		&m.ID, &m.Name, &m.Version, &m.StoragePath, &m.PathType, &m.SizeBytes,
		&m.Sha256Checksum, &m.Status, &m.IsDefault, &m.SourceURL, &m.ArchivedAt, &m.CreatedAt,
	)
	return m, err
}

// List returns a paginated slice of models and the total matching count.
// Status defaults to "ready" when not set in params.
func (s *ModelStore) List(ctx context.Context, params ListModelsParams) ([]Model, int, error) {
	status := "ready"
	if params.Status != nil {
		status = *params.Status
	}
	limit := 50
	if params.Limit > 0 {
		limit = params.Limit
	}

	var (
		total int
		rows  pgx.Rows
		err   error
	)

	if params.Name != "" {
		namePattern := "%" + params.Name + "%"
		if err = s.pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM models WHERE status = $1 AND name ILIKE $2`,
			status, namePattern,
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count models: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+modelColumns+`
			FROM models
			WHERE status = $1 AND name ILIKE $2
			ORDER BY name, version
			LIMIT $3 OFFSET $4
		`, status, namePattern, limit, params.Offset)
	} else {
		if err = s.pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM models WHERE status = $1`, status,
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count models: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+modelColumns+`
			FROM models
			WHERE status = $1
			ORDER BY name, version
			LIMIT $2 OFFSET $3
		`, status, limit, params.Offset)
	}
	if err != nil {
		return nil, 0, fmt.Errorf("query models: %w", err)
	}
	defer rows.Close()

	models := make([]Model, 0, total)
	for rows.Next() {
		m, err := scanModel(rows)
		if err != nil {
			return nil, 0, fmt.Errorf("scan model row: %w", err)
		}
		models = append(models, m)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate model rows: %w", err)
	}

	return models, total, nil
}
