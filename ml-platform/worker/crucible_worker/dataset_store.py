"""Garage dataset download.

Datasets live in Garage under datasets/{name}/{version} either as a single
object key (csv/json/parquet) or as a prefix for a multi-file dataset
(garage-conventions.md). The worker must read the dataset locally before
training, so this fetches it into a local directory and returns the local path
the trainer should load. It relies only on core S3 list/get; Garage supports no
bucket policies or versioning.
"""

import logging
from pathlib import Path, PurePosixPath
from typing import Protocol

from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError, ClientError

from crucible_worker import config
from crucible_worker.garage import build_client

logger = logging.getLogger("crucible.worker.dataset_store")


class DatasetDownloadError(RuntimeError):
    """Raised when a dataset cannot be downloaded from Garage."""


class DatasetStore(Protocol):
    def download(self, dataset_path: str, local_dir: Path) -> Path:
        """Download the dataset into local_dir and return the local path.

        For a single-file dataset the returned path is the downloaded file; for
        a multi-file (prefix) dataset it is local_dir holding the files.
        """
        ...


def _is_single_file(dataset_path: str) -> bool:
    """A dataset key with a file extension is a single object, not a prefix."""
    return bool(PurePosixPath(dataset_path.rstrip("/")).suffix)


class GarageDatasetStore:
    """Downloads a dataset object or prefix from Garage to the local disk."""

    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    @classmethod
    def from_config(cls, cfg: config.Config) -> "GarageDatasetStore":
        return cls(build_client(cfg), cfg.garage_bucket)

    def download(self, dataset_path: str, local_dir: Path) -> Path:
        local_dir.mkdir(parents=True, exist_ok=True)
        if _is_single_file(dataset_path):
            return self._download_file(dataset_path, local_dir)
        return self._download_prefix(dataset_path, local_dir)

    def _download_file(self, key: str, local_dir: Path) -> Path:
        target = local_dir / PurePosixPath(key).name
        try:
            self._client.download_file(self._bucket, key, str(target))
        except (Boto3Error, BotoCoreError, ClientError) as exc:
            raise DatasetDownloadError(
                f"failed to download dataset {key} from bucket {self._bucket}: {exc}"
            ) from exc
        logger.info("downloaded dataset %s to %s", key, target)
        return target

    def _download_prefix(self, prefix: str, local_dir: Path) -> Path:
        prefix = prefix.rstrip("/") + "/"
        keys = self._list_keys(prefix)
        if not keys:
            raise DatasetDownloadError(
                f"no dataset objects found under {prefix} in bucket {self._bucket}"
            )

        for key in keys:
            relative = key[len(prefix):]
            target = local_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._client.download_file(self._bucket, key, str(target))
            except (Boto3Error, BotoCoreError, ClientError) as exc:
                raise DatasetDownloadError(
                    f"failed to download {key} from bucket {self._bucket}: {exc}"
                ) from exc

        logger.info("downloaded %d dataset object(s) from %s", len(keys), prefix)
        return local_dir

    def _list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if not key.endswith("/"):
                        keys.append(key)
        except (Boto3Error, BotoCoreError, ClientError) as exc:
            raise DatasetDownloadError(
                f"failed to list dataset prefix {prefix} in bucket {self._bucket}: {exc}"
            ) from exc
        return keys
