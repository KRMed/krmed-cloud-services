"""Hugging Face read-through model cache on the GPU box local HDD.

Base-model weights are not stored in Garage (CLAUDE.md): the worker downloads
them from the Hugging Face Hub on a cache miss and reuses the local copy on a
hit. snapshot_download performs the read-through itself - with a pinned revision
it returns the cached snapshot when present and fetches it when absent. Weights
are immutable per revision, so a cached revision never needs revalidation and
independent caches on future GPU nodes can never disagree.

A Hugging Face token, when needed for gated repos, is read from the environment
by huggingface_hub (HF_TOKEN); it is never passed or stored here.
"""

import logging
from pathlib import Path
from typing import Protocol

from huggingface_hub import snapshot_download
from huggingface_hub.errors import HfHubHTTPError

from crucible_worker.repository import ModelMeta

logger = logging.getLogger("crucible.worker.model_cache")


class ModelCacheError(RuntimeError):
    """Raised when a base model cannot be fetched into the local cache."""


class ModelCache(Protocol):
    def ensure(self, model: ModelMeta) -> Path:
        """Return the local path to the model snapshot, downloading on a miss."""
        ...


class HFModelCache:
    """Read-through cache backed by the local HDD and the Hugging Face Hub."""

    def __init__(self, cache_dir: str) -> None:
        self._cache_dir = cache_dir

    def ensure(self, model: ModelMeta) -> Path:
        try:
            path = snapshot_download(
                repo_id=model.hf_repo_id,
                revision=model.revision,
                cache_dir=self._cache_dir,
            )
        except HfHubHTTPError as exc:
            raise ModelCacheError(
                f"failed to fetch {model.hf_repo_id}@{model.revision}: {exc}"
            ) from exc

        logger.info(
            "base model %s@%s ready at %s",
            model.hf_repo_id,
            model.revision,
            path,
        )
        return Path(path)
