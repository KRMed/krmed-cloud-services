package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Model mirrors the columns of the models allow-list table returned to the API
// layer. Base-model weights are not stored by Crucible; this is metadata about
// which Hugging Face repos and revisions users may fine-tune.
type Model struct {
	ID          int
	HFRepoID    string
	Revision    string
	DisplayName string
	ParamCount  *int64
	VramHint    *string
	Status      string
	IsDefault   bool
	ArchivedAt  *time.Time
	CreatedAt   time.Time
}

// ListModelsParams controls filtering and pagination for model queries.
type ListModelsParams struct {
	// Status filters by registry status. Defaults to "ready" when nil.
	Status *string
	// Search filters by case-insensitive substring match against the HF repo ID and display name when non-empty.
	Search string
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

const modelColumns = `id, hf_repo_id, revision, display_name, param_count,
                      vram_hint, status, is_default, archived_at, created_at`

func scanModel(rows pgx.Rows) (Model, error) {
	m := Model{}
	err := rows.Scan(
		&m.ID, &m.HFRepoID, &m.Revision, &m.DisplayName, &m.ParamCount,
		&m.VramHint, &m.Status, &m.IsDefault, &m.ArchivedAt, &m.CreatedAt,
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

	if params.Search != "" {
		searchPattern := "%" + params.Search + "%"
		if err = s.pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM models
			 WHERE status = $1 AND (hf_repo_id ILIKE $2 OR display_name ILIKE $2)`,
			status, searchPattern,
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count models: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+modelColumns+`
			FROM models
			WHERE status = $1 AND (hf_repo_id ILIKE $2 OR display_name ILIKE $2)
			ORDER BY display_name, revision
			LIMIT $3 OFFSET $4
		`, status, searchPattern, limit, params.Offset)
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
			ORDER BY display_name, revision
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
