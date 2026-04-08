package db

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/api"
	"github.com/KRMed/krmed-cloud-services/ml-platform/shared/schema"
)

// ErrJobNotFound is returned when no job matches the requested ID.
var ErrJobNotFound = errors.New("job not found")

// ErrInvalidTransition is returned when a requested status change is not allowed.
type ErrInvalidTransition struct {
	From schema.JobStatus
	To   schema.JobStatus
}

func (e *ErrInvalidTransition) Error() string {
	return fmt.Sprintf("invalid status transition: %s -> %s", e.From, e.To)
}

// jobRow maps all columns of the jobs table, including nullable FK columns
// added in migration 004 that are not yet surfaced in schema.Job.
type jobRow struct {
	ID              uuid.UUID
	Status          string
	BaseModel       string
	DatasetPath     string
	Hyperparameters []byte
	CheckpointPath  *string
	ErrorMessage    *string
	CreatedAt       time.Time
	UpdatedAt       time.Time
	ModelID         *int
	DatasetID       *int
}

func (r jobRow) toSchema() (schema.Job, error) {
	var hp schema.Hyperparameters
	if err := json.Unmarshal(r.Hyperparameters, &hp); err != nil {
		return schema.Job{}, fmt.Errorf("unmarshal hyperparameters: %w", err)
	}
	return schema.Job{
		ID:              r.ID,
		Status:          schema.JobStatus(r.Status),
		BaseModel:       r.BaseModel,
		DatasetPath:     r.DatasetPath,
		Hyperparameters: hp,
		CheckpointPath:  r.CheckpointPath,
		ErrorMessage:    r.ErrorMessage,
		CreatedAt:       r.CreatedAt,
		UpdatedAt:       r.UpdatedAt,
	}, nil
}

// validTransitions defines which status changes are permitted.
// Terminal statuses (completed, failed, cancelled) are absent — no transitions out.
var validTransitions = map[schema.JobStatus][]schema.JobStatus{
	schema.JobStatusQueued:  {schema.JobStatusRunning, schema.JobStatusCancelled},
	schema.JobStatusRunning: {schema.JobStatusCompleted, schema.JobStatusFailed, schema.JobStatusCancelled},
}

// UpdateJobFields holds the optional fields that may be changed via an update.
// A nil pointer means "leave this field unchanged."
type UpdateJobFields struct {
	Status         *schema.JobStatus
	CheckpointPath *string
	ErrorMessage   *string
}

// JobStore handles all database access for jobs.
type JobStore struct {
	pool *pgxpool.Pool
}

// NewJobStore creates a JobStore backed by the given connection pool.
func NewJobStore(pool *pgxpool.Pool) *JobStore {
	return &JobStore{pool: pool}
}

const jobColumns = `id, status, base_model, dataset_path, hyperparameters,
                    checkpoint_path, error_message, created_at, updated_at,
                    model_id, dataset_id`

func scanJobRow(row pgx.Row) (jobRow, error) {
	r := jobRow{}
	err := row.Scan(
		&r.ID, &r.Status, &r.BaseModel, &r.DatasetPath, &r.Hyperparameters,
		&r.CheckpointPath, &r.ErrorMessage, &r.CreatedAt, &r.UpdatedAt,
		&r.ModelID, &r.DatasetID,
	)
	return r, err
}

func scanJobRows(rows pgx.Rows) (jobRow, error) {
	r := jobRow{}
	err := rows.Scan(
		&r.ID, &r.Status, &r.BaseModel, &r.DatasetPath, &r.Hyperparameters,
		&r.CheckpointPath, &r.ErrorMessage, &r.CreatedAt, &r.UpdatedAt,
		&r.ModelID, &r.DatasetID,
	)
	return r, err
}

// Create inserts a new job with status "queued" and returns the created record.
func (s *JobStore) Create(ctx context.Context, req api.CreateJobRequest) (schema.Job, error) {
	hp, err := json.Marshal(req.Hyperparameters)
	if err != nil {
		return schema.Job{}, fmt.Errorf("marshal hyperparameters: %w", err)
	}

	r, err := scanJobRow(s.pool.QueryRow(ctx, `
		INSERT INTO jobs (base_model, dataset_path, hyperparameters, status)
		VALUES ($1, $2, $3, 'queued')
		RETURNING `+jobColumns,
		req.BaseModel, req.DatasetPath, hp,
	))
	if err != nil {
		return schema.Job{}, fmt.Errorf("insert job: %w", err)
	}

	return r.toSchema()
}

// GetByID returns the job with the given ID, or ErrJobNotFound.
func (s *JobStore) GetByID(ctx context.Context, id uuid.UUID) (schema.Job, error) {
	r, err := scanJobRow(s.pool.QueryRow(ctx, `
		SELECT `+jobColumns+`
		FROM jobs WHERE id = $1
	`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return schema.Job{}, ErrJobNotFound
	}
	if err != nil {
		return schema.Job{}, fmt.Errorf("query job: %w", err)
	}

	return r.toSchema()
}

// List returns a paginated slice of jobs and the total matching count.
func (s *JobStore) List(ctx context.Context, params api.ListJobsParams) ([]schema.Job, int, error) {
	limit := 50
	offset := 0
	if params.Limit != nil && *params.Limit > 0 {
		limit = *params.Limit
	}
	if params.Offset != nil && *params.Offset > 0 {
		offset = *params.Offset
	}

	var total int
	var rows pgx.Rows
	var err error

	if params.Status != nil {
		if err = s.pool.QueryRow(ctx,
			`SELECT COUNT(*) FROM jobs WHERE status = $1`, string(*params.Status),
		).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count jobs: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+jobColumns+`
			FROM jobs WHERE status = $1
			ORDER BY created_at DESC
			LIMIT $2 OFFSET $3
		`, string(*params.Status), limit, offset)
	} else {
		if err = s.pool.QueryRow(ctx, `SELECT COUNT(*) FROM jobs`).Scan(&total); err != nil {
			return nil, 0, fmt.Errorf("count jobs: %w", err)
		}
		rows, err = s.pool.Query(ctx, `
			SELECT `+jobColumns+`
			FROM jobs
			ORDER BY created_at DESC
			LIMIT $1 OFFSET $2
		`, limit, offset)
	}
	if err != nil {
		return nil, 0, fmt.Errorf("query jobs: %w", err)
	}
	defer rows.Close()

	jobs := make([]schema.Job, 0, min(total, limit))
	for rows.Next() {
		r, err := scanJobRows(rows)
		if err != nil {
			return nil, 0, fmt.Errorf("scan job row: %w", err)
		}
		j, err := r.toSchema()
		if err != nil {
			return nil, 0, err
		}
		jobs = append(jobs, j)
	}
	if err := rows.Err(); err != nil {
		return nil, 0, fmt.Errorf("iterate job rows: %w", err)
	}

	return jobs, total, nil
}

// Update applies non-nil fields to the job and returns the updated record.
// Status changes are validated inside a transaction with SELECT FOR UPDATE so
// the read-then-write is atomic and concurrent updates cannot bypass the
// transition check.
func (s *JobStore) Update(ctx context.Context, id uuid.UUID, fields UpdateJobFields) (schema.Job, error) {
	if fields.Status == nil {
		r, err := scanJobRow(s.pool.QueryRow(ctx, `
			UPDATE jobs SET
				checkpoint_path = COALESCE($2, checkpoint_path),
				error_message   = COALESCE($3, error_message),
				updated_at      = NOW()
			WHERE id = $1
			RETURNING `+jobColumns,
			id,
			fields.CheckpointPath,
			fields.ErrorMessage,
		))
		if errors.Is(err, pgx.ErrNoRows) {
			return schema.Job{}, ErrJobNotFound
		}
		if err != nil {
			return schema.Job{}, fmt.Errorf("update job: %w", err)
		}
		return r.toSchema()
	}

	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return schema.Job{}, fmt.Errorf("begin transaction: %w", err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck

	var currentStatus string
	if err := tx.QueryRow(ctx,
		`SELECT status FROM jobs WHERE id = $1 FOR UPDATE`, id,
	).Scan(&currentStatus); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return schema.Job{}, ErrJobNotFound
		}
		return schema.Job{}, fmt.Errorf("lock job: %w", err)
	}

	if err := validateTransition(schema.JobStatus(currentStatus), *fields.Status); err != nil {
		return schema.Job{}, err
	}

	r, err := scanJobRow(tx.QueryRow(ctx, `
		UPDATE jobs SET
			status          = $2::job_status,
			checkpoint_path = COALESCE($3, checkpoint_path),
			error_message   = COALESCE($4, error_message),
			updated_at      = NOW()
		WHERE id = $1
		RETURNING `+jobColumns,
		id,
		string(*fields.Status),
		fields.CheckpointPath,
		fields.ErrorMessage,
	))
	if err != nil {
		return schema.Job{}, fmt.Errorf("update job: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return schema.Job{}, fmt.Errorf("commit transaction: %w", err)
	}

	return r.toSchema()
}

func validateTransition(from, to schema.JobStatus) error {
	allowed, ok := validTransitions[from]
	if !ok {
		return &ErrInvalidTransition{From: from, To: to}
	}
	for _, s := range allowed {
		if s == to {
			return nil
		}
	}
	return &ErrInvalidTransition{From: from, To: to}
}

func statusToStringPtr(s *schema.JobStatus) *string {
	if s == nil {
		return nil
	}
	v := string(*s)
	return &v
}
