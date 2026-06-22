from pathlib import Path

import pytest
from huggingface_hub.errors import HfHubHTTPError
from requests import Response

from crucible_worker import model_cache
from crucible_worker.model_cache import HFModelCache, ModelCacheError
from crucible_worker.repository import ModelMeta


def _model() -> ModelMeta:
    return ModelMeta(
        hf_repo_id="mistralai/Mistral-7B-Instruct-v0.2",
        revision="deadbeef",
        param_count=7_000_000_000,
        vram_hint="comfortable",
    )


def test_ensure_downloads_pinned_revision_and_returns_path(monkeypatch, tmp_path):
    calls = {}

    def fake_snapshot_download(repo_id, revision, cache_dir):
        calls.update(repo_id=repo_id, revision=revision, cache_dir=cache_dir)
        return str(tmp_path / "snapshot")

    monkeypatch.setattr(model_cache, "snapshot_download", fake_snapshot_download)

    result = HFModelCache(str(tmp_path)).ensure(_model())

    assert result == Path(tmp_path / "snapshot")
    assert calls == {
        "repo_id": "mistralai/Mistral-7B-Instruct-v0.2",
        "revision": "deadbeef",
        "cache_dir": str(tmp_path),
    }


def test_ensure_wraps_hub_errors(monkeypatch, tmp_path):
    def boom(repo_id, revision, cache_dir):
        raise HfHubHTTPError("404 client error", response=Response())

    monkeypatch.setattr(model_cache, "snapshot_download", boom)

    with pytest.raises(ModelCacheError) as exc:
        HFModelCache(str(tmp_path)).ensure(_model())

    assert "mistralai/Mistral-7B-Instruct-v0.2@deadbeef" in str(exc.value)
