"""
Register a dataset in the Crucible dataset registry.

Computes the SHA256 of the dataset content (used as both version and checksum),
uploads to Garage, and inserts a row into the datasets table.

The dataset ID is printed to stdout on success so it can be captured as a
workflow output in Argo Workflows.

Usage:
    python register_dataset.py \\
        --name my-dataset \\
        --local-path /path/to/dataset.csv \\
        --source-description "Exported from internal annotation tool, 2026-04-07"
"""

import argparse
import hashlib
import os
import sys
from pathlib import Path
from typing import Optional

import boto3
import psycopg2
from boto3.s3.transfer import TransferConfig


REQUIRED_ENV = [
    "GARAGE_ENDPOINT",
    "GARAGE_ACCESS_KEY",
    "GARAGE_SECRET_KEY",
    "GARAGE_BUCKET",
    "DATABASE_URL",
]

MULTIPART_THRESHOLD = 8 * 1024 * 1024      # 8 MB
MULTIPART_CHUNK_SIZE = 512 * 1024 * 1024   # 512 MB


def check_env() -> dict:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"Error: missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return {k: os.environ[k] for k in REQUIRED_ENV}


def _hash_file_into(h: "hashlib._Hash", path: Path) -> None:
    """Stream a file into an existing hash object in fixed-size chunks."""
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)


def checksum_file(path: Path) -> str:
    h = hashlib.sha256()
    _hash_file_into(h, path)
    return h.hexdigest()


def checksum_directory(directory: Path) -> str:
    """SHA256 of each file's relative path and contents, in sorted path order.

    Both path and contents are included so that two directories with identical
    file contents but different layouts produce different checksums. Files are
    streamed in chunks to avoid loading large files into memory.
    """
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_file():
            h.update(file.relative_to(directory).as_posix().encode())
            _hash_file_into(h, file)
    return h.hexdigest()


def total_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def upload_dataset(s3, bucket: str, local_path: Path, name: str, version: str) -> tuple[str, str]:
    """
    Upload dataset to Garage. Returns (storage_path, path_type).

    Single files go to datasets/{name}/{version}.{ext} (path_type='object').
    Directories go to datasets/{name}/{version}/ (path_type='prefix').
    """
    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=MULTIPART_CHUNK_SIZE,
    )

    if local_path.is_file():
        ext = local_path.suffix  # e.g. ".csv", ".parquet"
        key = f"datasets/{name}/{version}{ext}"
        print(f"  uploading {local_path.name} -> {key}")
        s3.upload_file(str(local_path), bucket, key, Config=config)

        # Verify
        s3.head_object(Bucket=bucket, Key=key)

        return key, "object"

    # Directory upload
    prefix = f"datasets/{name}/{version}/"
    uploaded = []
    for file in sorted(local_path.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(local_path)
        key = f"{prefix}{relative.as_posix()}"
        print(f"  uploading {relative} -> {key}")
        s3.upload_file(str(file), bucket, key, Config=config)
        uploaded.append(key)

    # Verify
    paginator = s3.get_paginator("list_objects_v2")
    found = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            found.add(obj["Key"])
    missing = set(uploaded) - found
    if missing:
        raise RuntimeError(f"Upload verification failed — missing keys: {missing}")

    return prefix, "prefix"


def reserve_dataset_row(
    db_url: str,
    name: str,
    version: str,
    storage_path: str,
    path_type: str,
    size_bytes: int,
    sha256_checksum: str,
    source_description: Optional[str],
) -> tuple[int, bool]:
    """Insert a 'pending' row before upload begins.

    Because version = content checksum, a collision on (name, version) means
    the exact same content is already registered under this name:
    - If 'ready': return the existing ID and signal no upload is needed.
    - If 'pending': remove the stale row and reserve a fresh one.

    Returns (dataset_id, already_registered).
    """
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status FROM datasets WHERE name = %s AND version = %s",
                    (name, version),
                )
                existing = cur.fetchone()
                if existing:
                    existing_id, existing_status = existing
                    if existing_status == "ready":
                        return existing_id, True
                    # pending row from a failed previous run — clean it up
                    cur.execute("DELETE FROM datasets WHERE id = %s", (existing_id,))

                cur.execute(
                    """
                    INSERT INTO datasets
                        (name, version, storage_path, path_type, size_bytes,
                         sha256_checksum, status, source_description)
                    VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                    RETURNING id
                    """,
                    (name, version, storage_path, path_type, size_bytes, sha256_checksum, source_description),
                )
                return cur.fetchone()[0], False
    finally:
        conn.close()


def activate_dataset_row(db_url: str, dataset_id: int) -> None:
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE datasets SET status = 'ready' WHERE id = %s",
                    (dataset_id,),
                )
    finally:
        conn.close()


def delete_dataset_row(db_url: str, dataset_id: int) -> None:
    """Compensating action: remove a pending row after a failed upload."""
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM datasets WHERE id = %s AND status = 'pending'",
                    (dataset_id,),
                )
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a dataset in the Crucible registry")
    parser.add_argument("--name", required=True, help="Dataset name")
    parser.add_argument("--local-path", required=True, help="Path to dataset file or directory")
    parser.add_argument("--source-description", help="Free text describing where this dataset came from")
    args = parser.parse_args()

    env = check_env()

    local_path = Path(args.local_path).expanduser().resolve()
    if not local_path.exists():
        print(f"Error: path does not exist: {local_path}", file=sys.stderr)
        sys.exit(1)

    s3 = boto3.client(
        "s3",
        endpoint_url=env["GARAGE_ENDPOINT"],
        aws_access_key_id=env["GARAGE_ACCESS_KEY"],
        aws_secret_access_key=env["GARAGE_SECRET_KEY"],
    )

    print("Computing checksum (this is also the version)...", file=sys.stderr)
    if local_path.is_file():
        checksum = checksum_file(local_path)
    else:
        checksum = checksum_directory(local_path)
    version = checksum
    size = total_size(local_path)

    bucket = env["GARAGE_BUCKET"]

    # Determine storage path shape before reserving the row (needed for path_type)
    if local_path.is_file():
        storage_path = f"datasets/{args.name}/{version}{local_path.suffix}"
        path_type = "object"
    else:
        storage_path = f"datasets/{args.name}/{version}/"
        path_type = "prefix"

    print("Reserving registry row...", file=sys.stderr)
    dataset_id, already_registered = reserve_dataset_row(
        db_url=env["DATABASE_URL"],
        name=args.name,
        version=version,
        storage_path=storage_path,
        path_type=path_type,
        size_bytes=size,
        sha256_checksum=checksum,
        source_description=args.source_description,
    )

    if already_registered:
        print(f"Dataset {args.name}@{version[:12]} already registered — returning existing entry.", file=sys.stderr)
        # Only the ID goes to stdout so workflow orchestrators can capture it cleanly
        print(dataset_id)
        print(
            f"\nDone (idempotent).\n"
            f"  dataset_id:  {dataset_id}\n"
            f"  name:        {args.name}\n"
            f"  version:     {version}",
            file=sys.stderr,
        )
        return

    try:
        print(f"Uploading to {bucket}/{storage_path}...", file=sys.stderr)
        upload_dataset(s3, bucket, local_path, args.name, version)
    except Exception:
        print("Upload failed — removing reserved row...", file=sys.stderr)
        delete_dataset_row(env["DATABASE_URL"], dataset_id)
        raise

    print("Activating registry row...", file=sys.stderr)
    activate_dataset_row(env["DATABASE_URL"], dataset_id)

    # Only the ID goes to stdout so workflow orchestrators can capture it cleanly
    print(dataset_id)
    print(
        f"\nDone.\n"
        f"  dataset_id:  {dataset_id}\n"
        f"  name:        {args.name}\n"
        f"  version:     {version}\n"
        f"  size:        {size / 1024 / 1024:.1f} MB\n"
        f"  path_type:   {path_type}\n"
        f"  storage:     {bucket}/{storage_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
