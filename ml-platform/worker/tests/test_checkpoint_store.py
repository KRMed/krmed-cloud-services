from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

from crucible_worker import config
from crucible_worker.checkpoint_store import (
    CheckpointUploadError,
    GarageCheckpointStore,
)

BUCKET = "crucible"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def _keys(client) -> set[str]:
    resp = client.list_objects_v2(Bucket=BUCKET)
    return {obj["Key"] for obj in resp.get("Contents", [])}


def test_upload_writes_files_under_job_prefix(s3_client, tmp_path):
    (tmp_path / "adapter_config.json").write_text("{}")
    (tmp_path / "adapter_model.safetensors").write_bytes(b"weights")
    job_id = uuid4()

    prefix = GarageCheckpointStore(s3_client, BUCKET).upload(job_id, tmp_path)

    assert prefix == f"checkpoints/{job_id}/"
    assert _keys(s3_client) == {
        f"checkpoints/{job_id}/adapter_config.json",
        f"checkpoints/{job_id}/adapter_model.safetensors",
    }


def test_upload_preserves_nested_paths(s3_client, tmp_path):
    nested = tmp_path / "checkpoint-500"
    nested.mkdir()
    (nested / "adapter_model.safetensors").write_bytes(b"x")
    job_id = uuid4()

    GarageCheckpointStore(s3_client, BUCKET).upload(job_id, tmp_path)

    assert (
        f"checkpoints/{job_id}/checkpoint-500/adapter_model.safetensors"
        in _keys(s3_client)
    )


def test_upload_empty_dir_raises(s3_client, tmp_path):
    with pytest.raises(CheckpointUploadError):
        GarageCheckpointStore(s3_client, BUCKET).upload(uuid4(), tmp_path)


def test_upload_wraps_s3_errors(s3_client, tmp_path):
    (tmp_path / "adapter_config.json").write_text("{}")
    store = GarageCheckpointStore(s3_client, "does-not-exist")

    with pytest.raises(CheckpointUploadError):
        store.upload(uuid4(), tmp_path)


def test_from_config_builds_path_style_client():
    cfg = config.Config(
        database_url="postgres://x",
        redis_url="redis://x",
        garage_endpoint="http://garage:3900",
        garage_access_key="key",
        garage_secret_key="secret",
        garage_bucket="crucible",
        model_cache_dir="/var/crucible/models",
        queue_block_seconds=5,
        visibility_timeout_seconds=900,
        reconcile_interval_seconds=300,
        orphan_grace_seconds=60,
    )

    store = GarageCheckpointStore.from_config(cfg)

    assert store._bucket == "crucible"
    assert store._client.meta.endpoint_url == "http://garage:3900"
    assert store._client.meta.config.s3["addressing_style"] == "path"
