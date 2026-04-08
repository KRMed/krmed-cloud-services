package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Dataset mirrors the columns of the datasets table returned to the API layer.
type Dataset struct {
	ID                int
	Name              string
	Version           string
	StoragePath       string
	PathType          string
	SizeBytes         int64
	Sha256Checksum    string
	Status            string
	SourceDescription *string
	ArchivedAt        *time.Time
	CreatedAt         time.Time
}

// ListDatasetsParams controls filtering and pagination for dataset queries.
type ListDatasetsParams struct {
	// Status filters by registry status. Defaults to "ready" when nil.
	Status *string
	// Name filters by case-insensitive substring match when non-empty.
	Name   string
	Limit  int
	Offset int
}

// DatasetStore handles database access for the dataset registry.
type DatasetStore struct {
	pool *pgxpool.Pool
}

// NewDatasetStore creates a DatasetStore backed by the given connection pool.
func NewDatasetStore(pool *pgxpool.Pool) *DatasetStore {
	return &DatasetStore{pool: pool}
}

const datasetColumns = `id, name, version, storage_path, path_type, size_bytes,
                        sha256_checksum, status, source_description, archived_at, created_at`

func scanDataset(rows pgx.Rows) (Dataset, error) {
	d := Dataset{}
	err := rows.Scan(
		&d.ID, &d.Name, &d.Version, &d.StoragePath, &d.PathType, &d.SizeBytes,
		&d.Sha256Checksum, &d.Status, &d.SourceDescription, &d.ArchivedAt, &d.CreatedAt,
	)
	return d, err
}

// List returns a paginated slice of datasets and the total matching count.
// Status defaults to "ready" when not set in params.
func (s *DatasetStore) List(ctx context.Context, params ListDatasetsParams) ([]Dataset, int, error) {
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
			`SELECT COUNT(*) FROM datasets WHERE status = $1 AND name ILIKE $2`,
			status, namePattern,
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count datasets: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+datasetColumns+`
			FROM datasets
			WHERE status = $1 AND name ILIKE $2
			ORDER BY name, version
			LIMIT $3 OFFSET $4
		`, status, namePattern, limit, params.Offset)
	} else {
		if err = s.pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM datasets WHERE status = $1`, status,
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count datasets: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+datasetColumns+`
			FROM datasets
			WHERE status = $1
			ORDER BY name, version
			LIMIT $2 OFFSET $3
		`, status, limit, params.Offset)
	}
	if err != nil {
		return nil, 0, fmt.Errorf("query datasets: %w", err)
	}
	defer rows.Close()

	datasets := make([]Dataset, 0, total)
	for rows.Next() {
		d, err := scanDataset(rows)
		if err != nil {
			return nil, 0, fmt.Errorf("scan dataset row: %w", err)
		}
		datasets = append(datasets, d)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate dataset rows: %w", err)
	}

	return datasets, total, nil
}
