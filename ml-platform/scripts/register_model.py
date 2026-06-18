"""
Register a base model in the Crucible allow-list.

Crucible does NOT store base-model weights. The worker downloads them from the
Hugging Face Hub on demand and caches them on the GPU box local HDD (a
read-through cache, reconstructible from HF). This script only records an
allow-list entry in Postgres (which HF repo + revision users may fine-tune),
auto-deriving display metadata from the Hub.

Usage:
    python register_model.py \\
        --repo-id mistralai/Mistral-7B-Instruct-v0.2 \\
        [--revision <commit-sha>] \\
        [--display-name "Mistral 7B Instruct"] \\
        [--set-default]
"""

import argparse
import os
import sys
from typing import Optional

import psycopg2
from huggingface_hub import model_info


REQUIRED_ENV = ["DATABASE_URL"]

# VRAM guardrail thresholds (total parameter counts) for a single 16GB card with
# QLoRA. "Model-size guardrail": 7-8B comfortable, 13-14B
# tight (gradient checkpointing, batch size 1-2), 30B+ out of scope.
COMFORTABLE_MAX_PARAMS = 8_500_000_000
TIGHT_MAX_PARAMS = 15_000_000_000


def check_env() -> dict:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"Error: missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)
    return {k: os.environ[k] for k in REQUIRED_ENV}


def vram_hint_for(param_count: Optional[int]) -> Optional[str]:
    """Map a parameter count to a coarse VRAM feasibility hint.

    Returns None when the count is unknown. The hint is advisory for the UI; the
    worker preflight check is the authoritative gate that rejects oversized jobs.
    """
    if param_count is None:
        return None
    if param_count <= COMFORTABLE_MAX_PARAMS:
        return "comfortable"
    if param_count <= TIGHT_MAX_PARAMS:
        return "tight"
    return "unsupported"


def fetch_hf_metadata(repo_id: str, revision: Optional[str]) -> tuple[str, Optional[int]]:
    """Resolve the concrete commit SHA and total parameter count from the HF Hub.

    Returns (resolved_revision, param_count). param_count is None when the Hub
    does not expose safetensors metadata for the repo.
    """
    info = model_info(repo_id, revision=revision)
    resolved_revision = info.sha
    if not resolved_revision:
        raise RuntimeError(f"Hugging Face Hub did not return a commit SHA for {repo_id}")

    param_count = None
    safetensors = getattr(info, "safetensors", None)
    if safetensors is not None and getattr(safetensors, "total", None):
        param_count = int(safetensors.total)
    return resolved_revision, param_count


def register_model(
    db_url: str,
    hf_repo_id: str,
    revision: str,
    display_name: str,
    param_count: Optional[int],
    vram_hint: Optional[str],
    set_default: bool,
) -> int:
    """Insert an allow-list row and return its ID.

    A single metadata insert: there is no large upload to stage, so no transient
    'pending' state is needed (unlike dataset ingestion). Raises ValueError if
    (hf_repo_id, revision) is already registered.
    """
    conn = psycopg2.connect(db_url)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id FROM models WHERE hf_repo_id = %s AND revision = %s",
                    (hf_repo_id, revision),
                )
                existing = cur.fetchone()
                if existing:
                    raise ValueError(
                        f"Model {hf_repo_id}@{revision} is already registered (id={existing[0]})."
                    )

                cur.execute(
                    """
                    INSERT INTO models
                        (hf_repo_id, revision, display_name, param_count, vram_hint, status, is_default)
                    VALUES (%s, %s, %s, %s, %s, 'ready', false)
                    RETURNING id
                    """,
                    (hf_repo_id, revision, display_name, param_count, vram_hint),
                )
                model_id = cur.fetchone()[0]

                if set_default:
                    cur.execute(
                        "UPDATE models SET is_default = false WHERE hf_repo_id = %s AND id != %s",
                        (hf_repo_id, model_id),
                    )
                    cur.execute(
                        "UPDATE models SET is_default = true WHERE id = %s",
                        (model_id,),
                    )
                return model_id
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Register a base model in the Crucible allow-list")
    parser.add_argument("--repo-id", required=True, help="Hugging Face repo ID (e.g. mistralai/Mistral-7B-Instruct-v0.2)")
    parser.add_argument("--revision", help="HF commit SHA or branch/tag. Defaults to the current default-branch commit.")
    parser.add_argument("--display-name", help="Human label for the UI. Defaults to the repo name.")
    parser.add_argument("--set-default", action="store_true", help="Make this the default revision for the repo")
    args = parser.parse_args()

    env = check_env()

    print(f"Resolving {args.repo_id} metadata from the Hugging Face Hub...", file=sys.stderr)
    revision, param_count = fetch_hf_metadata(args.repo_id, args.revision)
    hint = vram_hint_for(param_count)
    display_name = args.display_name or args.repo_id.split("/")[-1]

    if hint == "unsupported":
        print(
            f"Warning: {args.repo_id} has ~{param_count:,} parameters and is flagged "
            "'unsupported' for a single 16GB card. Jobs against it will be rejected by "
            "the worker preflight check.",
            file=sys.stderr,
        )

    model_id = register_model(
        db_url=env["DATABASE_URL"],
        hf_repo_id=args.repo_id,
        revision=revision,
        display_name=display_name,
        param_count=param_count,
        vram_hint=hint,
        set_default=args.set_default,
    )

    param_display = f"{param_count:,}" if param_count is not None else "unknown"
    print(
        f"\nDone.\n"
        f"  model_id:      {model_id}\n"
        f"  hf_repo_id:    {args.repo_id}\n"
        f"  revision:      {revision}\n"
        f"  display_name:  {display_name}\n"
        f"  param_count:   {param_display}\n"
        f"  vram_hint:     {hint or 'unknown'}\n"
        f"  default:       {args.set_default}",
        file=sys.stderr,
    )

if __name__ == "__main__":
    main()
