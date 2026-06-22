"""Garage checkpoint upload.

The worker writes LoRA adapter checkpoints to Garage under checkpoints/{job-id}/
(garage-conventions.md). Garage implements the core S3 operations plus multipart
upload, so this relies only on put/upload - no bucket policies, ACLs, or
versioning. Path-style addressing is required: Garage does not support
virtual-host-style bucket addressing.
"""

import logging
from pathlib import Path
from typing import Protocol
from uuid import UUID

import boto3
from boto3.exceptions import Boto3Error
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from crucible_worker import config

logger = logging.getLogger("crucible.worker.checkpoint_store")

# Garage ignores the region, but botocore requires one to be set.
_GARAGE_REGION = "garage"

# Multipart thresholds from garage-conventions.md.
_MULTIPART_THRESHOLD = 8 * 1024 * 1024
_MULTIPART_CHUNKSIZE = 512 * 1024 * 1024


class CheckpointUploadError(RuntimeError):
    """Raised when a checkpoint cannot be uploaded to Garage."""


class CheckpointStore(Protocol):
    def upload(self, job_id: UUID, local_dir: Path) -> str:
        """Upload the adapter directory and return its Garage prefix."""
        ...


def _build_client(cfg: config.Config):
    return boto3.client(
        "s3",
        endpoint_url=cfg.garage_endpoint,
        aws_access_key_id=cfg.garage_access_key,
        aws_secret_access_key=cfg.garage_secret_key,
        region_name=_GARAGE_REGION,
        config=BotoConfig(s3={"addressing_style": "path"}),
    )


class GarageCheckpointStore:
    """Uploads a local adapter directory to the Garage checkpoints prefix."""

    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket
        self._transfer = TransferConfig(
            multipart_threshold=_MULTIPART_THRESHOLD,
            multipart_chunksize=_MULTIPART_CHUNKSIZE,
        )

    @classmethod
    def from_config(cls, cfg: config.Config) -> "GarageCheckpointStore":
        return cls(_build_client(cfg), cfg.garage_bucket)

    def upload(self, job_id: UUID, local_dir: Path) -> str:
        prefix = f"checkpoints/{job_id}/"
        files = sorted(p for p in local_dir.rglob("*") if p.is_file())
        if not files:
            raise CheckpointUploadError(
                f"no checkpoint files produced for job {job_id} in {local_dir}"
            )

        for path in files:
            key = prefix + path.relative_to(local_dir).as_posix()
            try:
                self._client.upload_file(
                    str(path), self._bucket, key, Config=self._transfer
                )
            except (Boto3Error, BotoCoreError, ClientError) as exc:
                raise CheckpointUploadError(
                    f"failed to upload {key} to bucket {self._bucket}: {exc}"
                ) from exc

        logger.info(
            "uploaded %d checkpoint file(s) to %s/%s", len(files), self._bucket, prefix
        )
        return prefix
