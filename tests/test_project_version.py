from __future__ import annotations

import tomllib
from pathlib import Path

from api.app import app, root
from api.routers.health import HealthResponse
from pixelle_video import __version__
from web.utils.async_helpers import get_project_version

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_version_is_consistent_across_runtime_surfaces():
    assert __version__ == "0.2.0"
    assert app.version == __version__
    assert HealthResponse().version == __version__
    assert get_project_version() == __version__


async def test_root_endpoint_reports_runtime_version():
    assert (await root())["version"] == __version__


def test_build_metadata_uses_single_version_source():
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)

    assert metadata["project"]["dynamic"] == ["version"]
    assert "version" not in metadata["project"]
    assert metadata["tool"]["hatch"]["version"]["path"] == "pixelle_video/_version.py"


def test_lockfile_does_not_duplicate_a_static_project_version():
    lock_text = (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8")
    package_block = lock_text.split('name = "pixelle-video"', 1)[1].split("[[package]]", 1)[0]
    assert "version =" not in package_block
