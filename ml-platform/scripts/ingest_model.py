"""
Ingest a model into the Crucible model registry.

Downloads from HuggingFace Hub (if --source is a repo ID) or reads from a local
path, uploads to Garage, and registers the model in Postgres.

Usage:
    python ingest_model.py \\
        --name mistral-7b-instruct \\
        --version abc123def456 \\
        --source mistralai/Mistral-7B-Instruct-v0.2 \\
        [--set-default]
"""

import argparse
import hashlib
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

import boto3
import psycopg2
from boto3.s3.transfer import TransferConfig
from huggingface_hub import snapshot_download


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


def is_hf_repo_id(source: str) -> bool:
    # Local paths start with / . or ~ or exist on disk
    if os.path.exists(source):
        return False
    if source.startswith(("/", ".", "~")):
        return False
    # HF repo IDs are in the form "org/model-name"
    return "/" in source


def _hash_file_into(h: "hashlib._Hash", path: Path) -> None:
    """Stream a file into an existing hash object in fixed-size chunks."""
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)


def compute_directory_checksum(directory: Path) -> str:
    """SHA256 of each file's relative path and contents, in sorted path order.

    Both path and contents are included so that two directories with identical
    file contents but different layouts produce different checksums. Files are
    streamed in chunks to avoid loading multi-GB weight files into memory.
    """
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_file():
            h.update(file.relative_to(directory).as_posix().encode())
            _hash_file_into(h, file)
    return h.hexdigest()


def total_directory_size(directory: Path) -> int:
    return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())


def upload_directory(s3, bucket: str, directory: Path, prefix: str) -> list[str]:
    """Upload all files in directory to Garage under prefix. Returns list of uploaded keys."""
    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=MULTIPART_CHUNK_SIZE,
    )
    uploaded = []
    for file in sorted(directory.rglob("*")):
        if not file.is_file():
            continue
        relative = file.relative_to(directory)
        key = f"{prefix}{relative.as_posix()}"
        print(f"  uploading {relative} -> {key}")
        s3.upload_file(str(file), bucket, key, Config=config)
        uploaded.append(key)
    return uploaded


def verify_upload(s3, bucket: str, prefix: str, expected_keys: list[str]) -> None:
    paginator = s3.get_paginator("list_objects_v2")
    found = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            found.add(obj["Key"])
    missing = set(expected_keys) - found
    if missing:
        raise RuntimeError(f"Upload verification failed — missing keys: {missing}")


def reserve_model_row(
    db_url: str,
    name: str,
    version: str,
    storage_path: str,
    size_bytes: int,
    sha256_checksum: str,
    source_url: Optional[str],
) -> int:
    """Insert a 'pending' row before upload begins.

    If a 'ready' row already exists for (name, version), raises ValueError.
    If a 'pending' row exists (leftover from a failed previous attempt), removes
    it so this attempt can start clean.

    Returns the new model ID.
    """
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, status FROM models WHERE name = %s AND version = %s",
                    (name, version),
                )
                existing = cur.fetchone()
                if existing:
                    existing_id, existing_status = existing
                    if existing_status == "ready":
                        raise ValueError(
                            f"Model {name}@{version} is already registered (id={existing_id}). "
                            "Use a different version string or archive the existing entry first."
                        )
                    # pending row from a failed previous run — clean it up
                    cur.execute("DELETE FROM models WHERE id = %s", (existing_id,))

                cur.execute(
                    """
                    INSERT INTO models
                        (name, version, storage_path, path_type, size_bytes,
                         sha256_checksum, status, is_default, source_url)
                    VALUES (%s, %s, %s, 'prefix', %s, %s, 'pending', false, %s)
                    RETURNING id
                    """,
                    (name, version, storage_path, size_bytes, sha256_checksum, source_url),
                )
                return cur.fetchone()[0]
    finally:
        conn.close()


def activate_model_row(db_url: str, model_id: int, name: str, set_default: bool) -> None:
    """Mark the row 'ready' and optionally set it as the default for its name."""
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE models SET status = 'ready' WHERE id = %s",
                    (model_id,),
                )
                if set_default:
                    cur.execute(
                        "UPDATE models SET is_default = false WHERE name = %s AND id != %s",
                        (name, model_id),
                    )
                    cur.execute(
                        "UPDATE models SET is_default = true WHERE id = %s",
                        (model_id,),
                    )
    finally:
        conn.close()


def delete_model_row(db_url: str, model_id: int) -> None:
    """Compensating action: remove a pending row after a failed upload."""
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM models WHERE id = %s AND status = 'pending'", (model_id,))
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a model into the Crucible registry")
    parser.add_argument("--name", required=True, help="Human name for the model (e.g. mistral-7b-instruct)")
    parser.add_argument("--version", required=True, help="HuggingFace commit SHA or arbitrary version string")
    parser.add_argument("--source", required=True, help="HuggingFace repo ID or local directory path")
    parser.add_argument("--set-default", action="store_true", help="Set this version as the default for its name")
    args = parser.parse_args()

    env = check_env()

    s3 = boto3.client(
        "s3",
        endpoint_url=env["GARAGE_ENDPOINT"],
        aws_access_key_id=env["GARAGE_ACCESS_KEY"],
        aws_secret_access_key=env["GARAGE_SECRET_KEY"],
    )
    bucket = env["GARAGE_BUCKET"]
    prefix = f"models/{args.name}/{args.version}/"

    with tempfile.TemporaryDirectory() as tmp:
        if is_hf_repo_id(args.source):
            print(f"Downloading {args.source} @ {args.version} from HuggingFace Hub...", file=sys.stderr)
            model_dir = Path(snapshot_download(
                repo_id=args.source,
                revision=args.version,
                local_dir=tmp,
            ))
            source_url = f"https://huggingface.co/{args.source}"
        else:
            model_dir = Path(args.source).expanduser().resolve()
            if not model_dir.is_dir():
                print(f"Error: local path does not exist or is not a directory: {model_dir}", file=sys.stderr)
                sys.exit(1)
            source_url = None

        print("Computing checksum...", file=sys.stderr)
        checksum = compute_directory_checksum(model_dir)
        size = total_directory_size(model_dir)

        print("Reserving registry row...", file=sys.stderr)
        model_id = reserve_model_row(
            db_url=env["DATABASE_URL"],
            name=args.name,
            version=args.version,
            storage_path=prefix,
            size_bytes=size,
            sha256_checksum=checksum,
            source_url=source_url,
        )

        try:
            print(f"Uploading to {bucket}/{prefix}...", file=sys.stderr)
            uploaded_keys = upload_directory(s3, bucket, model_dir, prefix)

            print("Verifying upload...", file=sys.stderr)
            verify_upload(s3, bucket, prefix, uploaded_keys)
        except Exception:
            print("Upload failed — removing reserved row...", file=sys.stderr)
            delete_model_row(env["DATABASE_URL"], model_id)
            raise

        print("Activating registry row...", file=sys.stderr)
        activate_model_row(env["DATABASE_URL"], model_id, args.name, args.set_default)

    print(
        f"\nDone.\n"
        f"  model_id:  {model_id}\n"
        f"  name:      {args.name}\n"
        f"  version:   {args.version}\n"
        f"  size:      {size / 1024 / 1024:.1f} MB\n"
        f"  checksum:  {checksum}\n"
        f"  prefix:    {bucket}/{prefix}\n"
        f"  default:   {args.set_default}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
