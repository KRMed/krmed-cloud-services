"""Dataset format validation.

The worker rejects unsupported dataset formats before training starts and
surfaces the rejection via job status, the same contract used for the VRAM
guardrail. v1 supports CSV, JSON, and Parquet.

This module validates the declared format from the Garage dataset key. Single
file datasets carry their format in the extension (the common case). Directory
(prefix) datasets have no extension here; their content level validation is
deferred to the cache/download stage (Phase 5B), so this returns None for them
rather than rejecting.
"""

from pathlib import PurePosixPath
from typing import Optional

SUPPORTED_FORMATS = frozenset({"csv", "json", "parquet"})


class UnsupportedDatasetFormatError(ValueError):
    """Raised when a dataset's declared format is not supported."""

    def __init__(self, fmt: str, dataset_path: str) -> None:
        self.format = fmt
        self.dataset_path = dataset_path
        super().__init__(
            f"unsupported dataset format {fmt!r} for {dataset_path!r}; "
            f"supported formats: {', '.join(sorted(SUPPORTED_FORMATS))}"
        )


def detect_format(dataset_path: str) -> Optional[str]:
    """Return the lowercase extension of a single file dataset key.

    Returns None when the key has no extension (a directory/prefix dataset),
    signalling that the format must be determined from content later.
    """
    suffix = PurePosixPath(dataset_path).suffix.lower().lstrip(".")
    return suffix or None


def validate_dataset_format(dataset_path: str) -> Optional[str]:
    """Validate the declared format of a dataset key.

    Returns the format string for a recognised single file dataset, or None for
    a prefix dataset whose format is checked at content read time. Raises
    UnsupportedDatasetFormatError for a present but unsupported extension.
    """
    fmt = detect_format(dataset_path)
    if fmt is None:
        return None
    if fmt not in SUPPORTED_FORMATS:
        raise UnsupportedDatasetFormatError(fmt, dataset_path)
    return fmt
