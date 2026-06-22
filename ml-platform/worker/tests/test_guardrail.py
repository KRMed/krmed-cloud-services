import pytest

from crucible_worker.guardrail import (
    TIGHT_MAX_PARAMS,
    OversizedModelError,
    check_model_fits,
)


def test_comfortable_model_passes():
    check_model_fits(7_000_000_000, "comfortable")


def test_tight_model_passes():
    check_model_fits(14_000_000_000, "tight")


def test_at_tight_limit_passes():
    check_model_fits(TIGHT_MAX_PARAMS, "tight")


def test_just_over_tight_limit_rejected():
    with pytest.raises(OversizedModelError):
        check_model_fits(TIGHT_MAX_PARAMS + 1, "tight")


def test_unsupported_hint_rejected_even_without_param_count():
    with pytest.raises(OversizedModelError):
        check_model_fits(None, "unsupported")


def test_unknown_param_count_allowed():
    # Unknown size with no 'unsupported' hint defers to the load-time probe (5C).
    check_model_fits(None, None)


def test_thirty_billion_rejected():
    with pytest.raises(OversizedModelError):
        check_model_fits(30_000_000_000, "unsupported")
