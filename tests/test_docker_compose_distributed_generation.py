from pathlib import Path

import yaml


def load_compose():
    return yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))


def env_list_to_dict(values):
    result = {}
    for value in values:
        key, _, env_value = value.partition("=")
        result[key] = env_value
    return result


def test_compose_defines_distributed_generation_services():
    services = load_compose()["services"]

    assert {"postgres", "redis", "migrate", "worker"}.issubset(services)
    assert services["postgres"]["healthcheck"]["test"]
    assert services["redis"]["healthcheck"]["test"]
    assert services["migrate"]["command"] == ".venv/bin/python -m api.tasks.migrate upgrade"
    assert services["worker"]["command"] == ".venv/bin/python -m api.tasks.worker"


def test_api_worker_and_web_share_task_backend_environment():
    services = load_compose()["services"]

    for service_name in ["api", "web", "worker"]:
        env = env_list_to_dict(services[service_name]["environment"])
        assert env["PIXELLE_TASK_BACKEND"] == "postgres"
        assert env["PIXELLE_REDIS_URL"] == "redis://redis:6379/0"
        assert env["PIXELLE_REQUIRE_DISTRIBUTED_COORDINATION"] == "true"
        assert env["PIXELLE_ARTIFACT_BACKEND"] == "local"

    assert env_list_to_dict(services["api"]["environment"])["PIXELLE_EXECUTION_MODE"] == "worker"
    assert env_list_to_dict(services["worker"]["environment"])["PIXELLE_EXECUTION_MODE"] == "worker"
