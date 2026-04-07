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


def compute_directory_checksum(directory: Path) -> str:
    """SHA256 of all file contents concatenated in sorted relative-path order."""
    h = hashlib.sha256()
    for file in sorted(directory.rglob("*")):
        if file.is_file():
            h.update(file.read_bytes())
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


def register_model(
    db_url: str,
    name: str,
    version: str,
    storage_path: str,
    size_bytes: int,
    sha256_checksum: str,
    source_url: str | None,
    set_default: bool,
) -> int:
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO models
                        (name, version, storage_path, path_type, size_bytes,
                         sha256_checksum, status, is_default, source_url)
                    VALUES (%s, %s, %s, 'prefix', %s, %s, 'ready', false, %s)
                    RETURNING id
                    """,
                    (name, version, storage_path, size_bytes, sha256_checksum, source_url),
                )
                model_id = cur.fetchone()[0]

                if set_default:
                    cur.execute(
                        "UPDATE models SET is_default = false WHERE name = %s AND id != %s",
                        (name, model_id),
                    )
                    cur.execute(
                        "UPDATE models SET is_default = true WHERE id = %s",
                        (model_id,),
                    )
        return model_id
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
            print(f"Downloading {args.source} @ {args.version} from HuggingFace Hub...")
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

        print("Computing checksum...")
        checksum = compute_directory_checksum(model_dir)
        size = total_directory_size(model_dir)

        print(f"Uploading to {bucket}/{prefix}...")
        uploaded_keys = upload_directory(s3, bucket, model_dir, prefix)

        print("Verifying upload...")
        verify_upload(s3, bucket, prefix, uploaded_keys)

        print("Registering in database...")
        model_id = register_model(
            db_url=env["DATABASE_URL"],
            name=args.name,
            version=args.version,
            storage_path=prefix,
            size_bytes=size,
            sha256_checksum=checksum,
            source_url=source_url,
            set_default=args.set_default,
        )

    print(
        f"\nDone.\n"
        f"  model_id:  {model_id}\n"
        f"  name:      {args.name}\n"
        f"  version:   {args.version}\n"
        f"  size:      {size / 1024 / 1024:.1f} MB\n"
        f"  checksum:  {checksum}\n"
        f"  prefix:    {bucket}/{prefix}\n"
        f"  default:   {args.set_default}"
    )


if __name__ == "__main__":
    main()
