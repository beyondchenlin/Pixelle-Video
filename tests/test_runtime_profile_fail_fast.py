import pytest
from pydantic import ValidationError

from api.config import APIConfig

PRODUCTION_ENV_VARS = [
    "PIXELLE_RUNTIME_PROFILE",
    "PIXELLE_TASK_BACKEND",
    "PIXELLE_POSTGRES_DSN",
    "PIXELLE_REDIS_URL",
    "PIXELLE_ARTIFACT_BACKEND",
    "PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL",
    "PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET",
]


def _clear_runtime_env(monkeypatch):
    for name in PRODUCTION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_dev_runtime_profile_allows_in_memory_tasks_and_local_artifacts(monkeypatch):
    _clear_runtime_env(monkeypatch)

    config = APIConfig.from_env()

    assert config.runtime_profile == "dev"
    assert config.task_backend == "memory"
    assert config.artifact_backend == "local"
    assert config.artifact_base_path == "output"


def test_production_runtime_profile_requires_postgres_and_object_store(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("PIXELLE_RUNTIME_PROFILE", "production")

    with pytest.raises(ValidationError) as exc_info:
        APIConfig.from_env()

    message = str(exc_info.value)
    assert "PIXELLE_TASK_BACKEND" in message
    assert "PIXELLE_POSTGRES_DSN" in message
    assert "PIXELLE_REDIS_URL" in message
    assert "PIXELLE_ARTIFACT_BACKEND" in message
    assert "PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL" in message
    assert "PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET" in message


def test_production_runtime_profile_treats_whitespace_settings_as_missing():
    with pytest.raises(ValidationError) as exc_info:
        APIConfig(
            runtime_profile="production",
            task_backend="postgres",
            postgres_dsn="   ",
            redis_url="\t",
            artifact_backend="s3",
            artifact_object_store_endpoint_url=" ",
            artifact_object_store_bucket="\n",
        )

    message = str(exc_info.value)
    assert "PIXELLE_POSTGRES_DSN" in message
    assert "PIXELLE_REDIS_URL" in message
    assert "PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL" in message
    assert "PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET" in message


def test_production_runtime_profile_accepts_required_settings(monkeypatch):
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("PIXELLE_RUNTIME_PROFILE", "production")
    monkeypatch.setenv("PIXELLE_TASK_BACKEND", "postgres")
    monkeypatch.setenv("PIXELLE_POSTGRES_DSN", "postgresql+asyncpg://u:p@db:5432/pixelle")
    monkeypatch.setenv("PIXELLE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("PIXELLE_ARTIFACT_BACKEND", "s3")
    monkeypatch.setenv("PIXELLE_ARTIFACT_OBJECT_STORE_ENDPOINT_URL", "https://s3.example.test")
    monkeypatch.setenv("PIXELLE_ARTIFACT_OBJECT_STORE_BUCKET", "pixelle-prod")

    config = APIConfig.from_env()

    assert config.runtime_profile == "production"
    assert config.task_backend == "postgres"
    assert config.artifact_backend == "s3"
    assert config.artifact_object_store_endpoint_url == "https://s3.example.test"
    assert config.artifact_object_store_bucket == "pixelle-prod"
