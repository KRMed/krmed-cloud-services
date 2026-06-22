"""Tests for the GPU-independent helpers in trainer.py.

UnslothQLoRATrainer.train itself needs the Blackwell card and is verified by
scripts/qlora_smoke_test.py on the GPU box, not here. These cover the pure
dataset-resolution logic that gates a run before any GPU work starts.
"""

import pytest

from crucible_worker.trainer import (
    TrainerError,
    dataset_load_spec,
    resolve_text_field,
)


def test_resolve_text_field_accepts_text_column():
    assert resolve_text_field(["text", "label"]) == "text"


def test_resolve_text_field_rejects_missing_text_column():
    with pytest.raises(TrainerError) as exc:
        resolve_text_field(["prompt", "completion"])
    assert "text" in str(exc.value)


def test_dataset_load_spec_single_csv_file(tmp_path):
    f = tmp_path / "data.csv"
    f.write_text("text\nhi\n")

    fmt, files = dataset_load_spec(f)

    assert fmt == "csv"
    assert files == [str(f)]


def test_dataset_load_spec_directory_groups_files(tmp_path):
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "b.jsonl").write_text("{}")

    fmt, files = dataset_load_spec(tmp_path)

    assert fmt == "json"  # both jsonl and json map to the json loader
    assert len(files) == 2


def test_dataset_load_spec_rejects_unknown_extension(tmp_path):
    (tmp_path / "notes.txt").write_text("nope")

    with pytest.raises(TrainerError) as exc:
        dataset_load_spec(tmp_path)
    assert "txt" in str(exc.value)


def test_dataset_load_spec_rejects_mixed_formats(tmp_path):
    (tmp_path / "a.csv").write_text("text\nhi\n")
    (tmp_path / "b.parquet").write_bytes(b"x")

    with pytest.raises(TrainerError) as exc:
        dataset_load_spec(tmp_path)
    assert "mixes" in str(exc.value)


def test_dataset_load_spec_rejects_missing_path(tmp_path):
    with pytest.raises(TrainerError):
        dataset_load_spec(tmp_path / "does-not-exist")


def test_dataset_load_spec_rejects_empty_dir(tmp_path):
    with pytest.raises(TrainerError):
        dataset_load_spec(tmp_path)
