"""Postgres job repository (production JobRepository implementation).

Each method opens a short-lived connection and runs in a single transaction.
Job operations are infrequent (a handful per multi-hour job), so a connection
per call avoids stale-connection handling for no meaningful cost.

Status transitions are conditional on the current status so a cancel written by
the backend while a job runs is never overwritten: the DB cancel is
authoritative.
"""

from typing import Optional
from uuid import UUID

import psycopg2

from shared.schema.job import Hyperparameters, Job, JobStatus

from crucible_worker.repository import ModelMeta

_JOB_COLUMNS = (
    "id, status, base_model, dataset_path, hyperparameters, "
    "checkpoint_path, error_message, created_at, updated_at"
)


def _to_uuid(value) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _row_to_job(row) -> Job:
    hp = row[4] or {}
    return Job(
        id=_to_uuid(row[0]),
        status=JobStatus(row[1]),
        base_model=row[2],
        dataset_path=row[3],
        hyperparameters=Hyperparameters(
            learning_rate=hp["learning_rate"],
            epochs=hp["epochs"],
            batch_size=hp["batch_size"],
            lora_rank=hp["lora_rank"],
            lora_alpha=hp["lora_alpha"],
        ),
        checkpoint_path=row[5],
        error_message=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


class PostgresJobRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        return psycopg2.connect(self._database_url)

    def get_job(self, job_id: UUID) -> Optional[Job]:
        conn = self._connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_JOB_COLUMNS} FROM jobs WHERE id = %s",
                    (str(job_id),),
                )
                row = cur.fetchone()
                return _row_to_job(row) if row else None
        finally:
            conn.close()

    def get_model_meta(self, hf_repo_id: str) -> Optional[ModelMeta]:
        conn = self._connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT hf_repo_id, revision, param_count, vram_hint
                    FROM models
                    WHERE hf_repo_id = %s AND status = 'ready'
                    ORDER BY is_default DESC
                    LIMIT 1
                    """,
                    (hf_repo_id,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                return ModelMeta(
                    hf_repo_id=row[0],
                    revision=row[1],
                    param_count=row[2],
                    vram_hint=row[3],
                )
        finally:
            conn.close()

    def mark_running(self, job_id: UUID) -> None:
        self._update(
            "UPDATE jobs SET status = 'running', updated_at = NOW() "
            "WHERE id = %s AND status = 'queued'",
            (str(job_id),),
        )

    def heartbeat(self, job_id: UUID) -> None:
        self._update(
            "UPDATE jobs SET updated_at = NOW() "
            "WHERE id = %s AND status = 'running'",
            (str(job_id),),
        )

    def mark_completed(self, job_id: UUID, checkpoint_path: str) -> None:
        self._update(
            "UPDATE jobs SET status = 'completed', checkpoint_path = %s, "
            "updated_at = NOW() WHERE id = %s AND status = 'running'",
            (checkpoint_path, str(job_id)),
        )

    def mark_failed(self, job_id: UUID, error_message: str) -> None:
        self._update(
            "UPDATE jobs SET status = 'failed', error_message = %s, "
            "updated_at = NOW() WHERE id = %s AND status = 'running'",
            (error_message, str(job_id)),
        )

    def reset_to_queued(self, job_id: UUID) -> None:
        self._update(
            "UPDATE jobs SET status = 'queued', updated_at = NOW() "
            "WHERE id = %s AND status = 'running'",
            (str(job_id),),
        )

    def find_stale_running(self, older_than_seconds: int) -> list[UUID]:
        return self._select_ids(
            "SELECT id FROM jobs WHERE status = 'running' "
            "AND updated_at < NOW() - make_interval(secs => %s)",
            (older_than_seconds,),
        )

    def find_orphan_queued(self, grace_seconds: int) -> list[UUID]:
        return self._select_ids(
            "SELECT id FROM jobs WHERE status = 'queued' "
            "AND created_at < NOW() - make_interval(secs => %s) "
            "AND updated_at < NOW() - make_interval(secs => %s)",
            (grace_seconds, grace_seconds),
        )

    def _update(self, sql: str, params: tuple) -> None:
        conn = self._connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
        finally:
            conn.close()

    def _select_ids(self, sql: str, params: tuple) -> list[UUID]:
        conn = self._connect()
        try:
            with conn, conn.cursor() as cur:
                cur.execute(sql, params)
                return [_to_uuid(r[0]) for r in cur.fetchall()]
        finally:
            conn.close()
