import boto3
import pytest
from moto import mock_aws

from crucible_worker import config
from crucible_worker.dataset_store import DatasetDownloadError, GarageDatasetStore

BUCKET = "crucible"


@pytest.fixture
def s3_client():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


def test_download_single_file_returns_file_path(s3_client, tmp_path):
    key = "datasets/demo/abc123.csv"
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"text\nhello\n")

    result = GarageDatasetStore(s3_client, BUCKET).download(key, tmp_path)

    assert result == tmp_path / "abc123.csv"
    assert result.read_text() == "text\nhello\n"


def test_download_prefix_returns_dir_with_files(s3_client, tmp_path):
    prefix = "datasets/demo/v1"
    s3_client.put_object(Bucket=BUCKET, Key=f"{prefix}/part-0.parquet", Body=b"a")
    s3_client.put_object(Bucket=BUCKET, Key=f"{prefix}/nested/part-1.parquet", Body=b"b")

    result = GarageDatasetStore(s3_client, BUCKET).download(prefix, tmp_path)

    assert result == tmp_path
    assert (tmp_path / "part-0.parquet").read_bytes() == b"a"
    assert (tmp_path / "nested" / "part-1.parquet").read_bytes() == b"b"


def test_download_missing_prefix_raises(s3_client, tmp_path):
    with pytest.raises(DatasetDownloadError):
        GarageDatasetStore(s3_client, BUCKET).download("datasets/missing/v1", tmp_path)


def test_download_missing_file_raises(s3_client, tmp_path):
    with pytest.raises(DatasetDownloadError):
        GarageDatasetStore(s3_client, BUCKET).download(
            "datasets/missing/x.csv", tmp_path
        )


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

    store = GarageDatasetStore.from_config(cfg)

    assert store._bucket == "crucible"
    assert store._client.meta.endpoint_url == "http://garage:3900"
    assert store._client.meta.config.s3["addressing_style"] == "path"
