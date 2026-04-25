import pytest

from api.config import APIConfig
from api.tasks.factory import build_task_manager


def test_api_config_reads_distributed_task_environment(monkeypatch):
    monkeypatch.setenv("PIXELLE_TASK_BACKEND", "postgres")
    monkeypatch.setenv("PIXELLE_POSTGRES_DSN", "postgresql+asyncpg://u:p@postgres:5432/pixelle")
    monkeypatch.setenv("PIXELLE_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION", "true")
    monkeypatch.setenv("PIXELLE_EXECUTION_MODE", "worker")
    monkeypatch.setenv("PIXELLE_ARTIFACT_BASE_URL", "http://api.test/api/files")

    config = APIConfig.from_env()

    assert config.task_backend == "postgres"
    assert config.postgres_dsn.startswith("postgresql+asyncpg://")
    assert config.redis_url == "redis://redis:6379/0"
    assert config.require_distributed_coordination is True
    assert config.execution_mode == "worker"
    assert config.artifact_base_url == "http://api.test/api/files"


def test_api_config_reads_submit_lock_wait_environment(monkeypatch):
    monkeypatch.setenv("PIXELLE_GENERATION_SUBMIT_LOCK_WAIT_SECONDS", "7.5")
    monkeypatch.setenv("PIXELLE_GENERATION_SUBMIT_LOCK_POLL_SECONDS", "0.25")

    config = APIConfig.from_env()

    assert config.generation_submit_lock_wait_seconds == 7.5
    assert config.generation_submit_lock_poll_seconds == 0.25


def test_api_config_rejects_heartbeat_that_cannot_refresh_lease():
    with pytest.raises(ValueError, match="generation_heartbeat_seconds"):
        APIConfig(
            generation_lease_ttl_seconds=30,
            generation_heartbeat_seconds=30,
        )


def test_production_distributed_mode_fails_without_redis(monkeypatch):
    monkeypatch.setenv("PIXELLE_TASK_BACKEND", "postgres")
    monkeypatch.setenv("PIXELLE_POSTGRES_DSN", "postgresql+asyncpg://u:p@postgres:5432/pixelle")
    monkeypatch.delenv("PIXELLE_REDIS_URL", raising=False)
    monkeypatch.setenv("PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION", "true")

    config = APIConfig.from_env()

    with pytest.raises(RuntimeError, match="PIXELLE_REDIS_URL"):
        build_task_manager(config)


def test_memory_backend_factory_keeps_embedded_execution(monkeypatch):
    monkeypatch.delenv("PIXELLE_TASK_BACKEND", raising=False)
    monkeypatch.delenv("PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION", raising=False)

    manager = build_task_manager(APIConfig.from_env())

    assert manager.execution_mode == "embedded"
