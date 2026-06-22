from pathlib import Path
from uuid import UUID

from crucible_worker.executor import CachingExecutor, StubTrainer, checkpoint_prefix
from tests.conftest import comfortable_model, make_job


class FakeCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.calls = []

    def ensure(self, model):
        self.calls.append(model)
        return self._path


class FakeStore:
    def __init__(self) -> None:
        self.job_id = None
        self.uploaded_names = None

    def upload(self, job_id: UUID, local_dir: Path) -> str:
        self.job_id = job_id
        self.uploaded_names = sorted(
            p.name for p in local_dir.rglob("*") if p.is_file()
        )
        return f"checkpoints/{job_id}/"


class RecordingTrainer:
    def __init__(self) -> None:
        self.seen = None

    def train(self, job, model_path, output_dir, heartbeat):
        self.seen = (job.id, model_path, output_dir.exists())
        (output_dir / "adapter_config.json").write_text("{}")


def test_caching_executor_caches_trains_then_uploads(tmp_path):
    job = make_job()
    model = comfortable_model(job.base_model)
    model_path = tmp_path / "model"
    model_path.mkdir()
    cache = FakeCache(model_path)
    store = FakeStore()
    beats = []

    result = CachingExecutor(cache, StubTrainer(), store).run(
        job, model, lambda: beats.append(1)
    )

    assert cache.calls == [model]
    assert result.checkpoint_path == checkpoint_prefix(job)
    assert store.job_id == job.id
    assert store.uploaded_names == ["STUB_ADAPTER.txt"]
    assert beats  # heartbeats fired during the run


def test_trainer_receives_cached_model_path_and_existing_output_dir(tmp_path):
    job = make_job()
    model = comfortable_model(job.base_model)
    model_path = tmp_path / "model"
    model_path.mkdir()
    trainer = RecordingTrainer()
    store = FakeStore()

    CachingExecutor(FakeCache(model_path), trainer, store).run(
        job, model, lambda: None
    )

    assert trainer.seen == (job.id, model_path, True)
    assert store.uploaded_names == ["adapter_config.json"]
