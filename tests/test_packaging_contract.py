import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_package_does_not_publish_missing_console_entry_points() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "scripts" not in project["project"]


def test_docker_installs_browser_inside_project_environment() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "uv run playwright install --with-deps chromium" in dockerfile
    assert "    playwright install --with-deps chromium" not in dockerfile
