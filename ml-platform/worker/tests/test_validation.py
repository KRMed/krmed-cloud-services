import pytest

from crucible_worker.validation import (
    UnsupportedDatasetFormatError,
    detect_format,
    validate_dataset_format,
)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("datasets/demo/abc.csv", "csv"),
        ("datasets/demo/abc.json", "json"),
        ("datasets/demo/abc.parquet", "parquet"),
        ("datasets/demo/ABC.CSV", "csv"),
    ],
)
def test_supported_single_file_formats(path, expected):
    assert validate_dataset_format(path) == expected


@pytest.mark.parametrize("path", ["datasets/demo/v1/", "datasets/demo/v1"])
def test_prefix_dataset_defers_to_content_check(path):
    # No extension: format is determined later (Phase 5B), not rejected here.
    assert detect_format(path) is None
    assert validate_dataset_format(path) is None


def test_unsupported_extension_raises():
    with pytest.raises(UnsupportedDatasetFormatError) as exc:
        validate_dataset_format("datasets/demo/abc.txt")
    assert exc.value.format == "txt"
    assert exc.value.dataset_path == "datasets/demo/abc.txt"


def test_unsupported_extension_message_lists_supported_formats():
    with pytest.raises(UnsupportedDatasetFormatError) as exc:
        validate_dataset_format("datasets/demo/abc.xlsx")
    message = str(exc.value)
    assert "csv" in message and "json" in message and "parquet" in message
