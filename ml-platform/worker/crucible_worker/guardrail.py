"""Preflight model-size guardrail.

A single 16GB card with QLoRA handles 7-8B comfortably and 13-14B tightly; 30B
and above is out of scope and must be rejected. This is the cheap, metadata
based gate run before any download or GPU work, using the parameter count from
the model allow-list. The authoritative load-time VRAM probe on the real card
is added with the trainer (Phase 5C); this gate keeps oversized jobs from ever
reaching it.

Thresholds mirror the CLAUDE.md model-size guardrail and the values in
scripts/register_model.py (hand-synced, same source of truth).
"""

from typing import Optional

COMFORTABLE_MAX_PARAMS = 8_500_000_000
TIGHT_MAX_PARAMS = 15_000_000_000


class OversizedModelError(ValueError):
    """Raised when a base model is too large for the GPU under QLoRA."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def check_model_fits(param_count: Optional[int], vram_hint: Optional[str]) -> None:
    """Reject models that cannot run on a single 16GB card under QLoRA.

    Raises OversizedModelError when the model is known to be too large. An
    unknown parameter count (None) with no 'unsupported' hint is allowed
    through; the load-time VRAM probe (Phase 5C) is the final authority.
    """
    if vram_hint == "unsupported":
        raise OversizedModelError(
            "model is flagged 'unsupported' for a single 16GB card"
        )
    if param_count is not None and param_count > TIGHT_MAX_PARAMS:
        raise OversizedModelError(
            f"model has ~{param_count:,} parameters, exceeding the "
            f"{TIGHT_MAX_PARAMS:,} limit for a single 16GB card under QLoRA"
        )
