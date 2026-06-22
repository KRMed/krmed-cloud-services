import pytest

from crucible_worker.config import (
    DEFAULT_GPU_IDS,
    DEFAULT_MODEL_CACHE_DIR,
    DEFAULT_ORPHAN_GRACE_SECONDS,
    DEFAULT_QUEUE_BLOCK_SECONDS,
    DEFAULT_RECONCILE_INTERVAL_SECONDS,
    DEFAULT_VISIBILITY_TIMEOUT_SECONDS,
    REQUIRED_ENV,
    ConfigError,
    load,
)

ALL_ENV_KEYS = [
    "DATABASE_URL",
    "REDIS_URL",
    "GARAGE_ENDPOINT",
    "GARAGE_ACCESS_KEY",
    "GARAGE_SECRET_KEY",
    "GARAGE_BUCKET",
    "MODEL_CACHE_DIR",
    "QUEUE_BLOCK_SECONDS",
    "VISIBILITY_TIMEOUT_SECONDS",
    "RECONCILE_INTERVAL_SECONDS",
    "ORPHAN_GRACE_SECONDS",
    "CRUCIBLE_GPUS",
]


@pytest.fixture
def clean_env(monkeypatch):
    for key in ALL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


def _set_required(env):
    for key in REQUIRED_ENV:
        env.setenv(key, f"value-for-{key}")


def test_load_with_required_vars_applies_defaults(clean_env):
    _set_required(clean_env)

    config = load()

    assert config.database_url == "value-for-DATABASE_URL"
    assert config.garage_bucket == "value-for-GARAGE_BUCKET"
    assert config.model_cache_dir == DEFAULT_MODEL_CACHE_DIR
    assert config.queue_block_seconds == DEFAULT_QUEUE_BLOCK_SECONDS
    assert config.visibility_timeout_seconds == DEFAULT_VISIBILITY_TIMEOUT_SECONDS
    assert config.reconcile_interval_seconds == DEFAULT_RECONCILE_INTERVAL_SECONDS
    assert config.orphan_grace_seconds == DEFAULT_ORPHAN_GRACE_SECONDS
    assert config.gpu_ids == DEFAULT_GPU_IDS


def test_missing_required_vars_raises_listing_all(clean_env):
    with pytest.raises(ConfigError) as exc:
        load()
    message = str(exc.value)
    for key in REQUIRED_ENV:
        assert key in message


def test_missing_single_var_named_in_error(clean_env):
    _set_required(clean_env)
    clean_env.delenv("REDIS_URL")

    with pytest.raises(ConfigError) as exc:
        load()
    message = str(exc.value)
    assert "REDIS_URL" in message
    assert "DATABASE_URL" not in message


def test_empty_required_var_treated_as_missing(clean_env):
    _set_required(clean_env)
    clean_env.setenv("GARAGE_BUCKET", "")

    with pytest.raises(ConfigError) as exc:
        load()
    assert "GARAGE_BUCKET" in str(exc.value)


def test_int_overrides_are_parsed(clean_env):
    _set_required(clean_env)
    clean_env.setenv("QUEUE_BLOCK_SECONDS", "10")
    clean_env.setenv("VISIBILITY_TIMEOUT_SECONDS", "1800")
    clean_env.setenv("MODEL_CACHE_DIR", "/mnt/models")

    config = load()

    assert config.queue_block_seconds == 10
    assert config.visibility_timeout_seconds == 1800
    assert config.model_cache_dir == "/mnt/models"


def test_blank_int_override_falls_back_to_default(clean_env):
    _set_required(clean_env)
    clean_env.setenv("QUEUE_BLOCK_SECONDS", "")

    config = load()

    assert config.queue_block_seconds == DEFAULT_QUEUE_BLOCK_SECONDS


def test_non_integer_int_env_raises(clean_env):
    _set_required(clean_env)
    clean_env.setenv("RECONCILE_INTERVAL_SECONDS", "not-a-number")

    with pytest.raises(ConfigError) as exc:
        load()
    assert "RECONCILE_INTERVAL_SECONDS" in str(exc.value)


def test_crucible_gpus_parsed_into_tuple(clean_env):
    _set_required(clean_env)
    clean_env.setenv("CRUCIBLE_GPUS", "0,1")

    config = load()

    assert config.gpu_ids == ("0", "1")


def test_crucible_gpus_blank_falls_back_to_default(clean_env):
    _set_required(clean_env)
    clean_env.setenv("CRUCIBLE_GPUS", "  ")

    config = load()

    assert config.gpu_ids == DEFAULT_GPU_IDS


def test_config_is_frozen(clean_env):
    _set_required(clean_env)
    config = load()
    with pytest.raises(Exception):
        config.database_url = "mutated"  # type: ignore[misc]
