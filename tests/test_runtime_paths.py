import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pixelle_video.utils.logging_util import _resolve_logging_config
from pixelle_video.utils.os_util import (
    configure_runtime_environment,
    get_pixelle_video_root_path,
    get_temp_path,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_configure_runtime_environment_routes_temp_and_cache_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", None)
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    monkeypatch.delenv("PIXELLE_VIDEO_RUNTIME_ROOT", raising=False)
    monkeypatch.setenv("TMP", str(tmp_path / "system-tmp"))
    monkeypatch.setenv("TEMP", str(tmp_path / "system-temp"))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "system-tmpdir"))
    monkeypatch.delenv("UV_CACHE_DIR", raising=False)
    monkeypatch.delenv("RUFF_CACHE_DIR", raising=False)

    configured = configure_runtime_environment()

    runtime_root = tmp_path / "_runtime"
    temp_dir = runtime_root / "temp"
    assert configured["PIXELLE_VIDEO_RUNTIME_ROOT"] == str(runtime_root.resolve())
    assert os.environ["TMP"] == str(temp_dir)
    assert os.environ["TEMP"] == str(temp_dir)
    assert os.environ["TMPDIR"] == str(temp_dir)
    assert tempfile.gettempdir() == str(temp_dir)
    assert os.environ["UV_CACHE_DIR"] == str(runtime_root / "uv-cache")
    assert os.environ["RUFF_CACHE_DIR"] == str(runtime_root / "ruff-cache")

    with tempfile.NamedTemporaryFile(delete=True) as handle:
        assert Path(handle.name).parent == temp_dir


def test_get_temp_path_uses_runtime_root(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    work_dir = tmp_path / "elsewhere"
    project_root.mkdir()
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(project_root))
    monkeypatch.delenv("PIXELLE_VIDEO_RUNTIME_ROOT", raising=False)

    assert Path(get_temp_path("frame.html")) == project_root / "_runtime" / "temp" / "frame.html"


def test_root_path_falls_back_to_package_repository_not_cwd(monkeypatch, tmp_path):
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)
    monkeypatch.delenv("PIXELLE_VIDEO_ROOT", raising=False)
    monkeypatch.delenv("PIXELLE_VIDEO_RUNTIME_ROOT", raising=False)

    assert Path(get_pixelle_video_root_path()) == REPO_ROOT
    assert Path(get_temp_path("frame.html")) == REPO_ROOT / "_runtime" / "temp" / "frame.html"
    assert not (outside_cwd / "_runtime").exists()


def test_importing_package_from_external_cwd_uses_repo_runtime(tmp_path):
    outside_cwd = tmp_path / "outside-import"
    outside_cwd.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os, tempfile, pixelle_video; "
                "print('RESULT=' + json.dumps({"
                "'runtime': os.environ.get('PIXELLE_VIDEO_RUNTIME_ROOT'), "
                "'temp': tempfile.gettempdir()"
                "}))"
            ),
        ],
        cwd=outside_cwd,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "PIXELLE_VIDEO_ROOT": "",
            "PIXELLE_VIDEO_RUNTIME_ROOT": "",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    payload_line = next(line for line in result.stdout.splitlines() if line.startswith("RESULT="))
    payload = json.loads(payload_line.removeprefix("RESULT="))
    assert Path(payload["runtime"]) == REPO_ROOT / "_runtime"
    assert Path(payload["temp"]) == REPO_ROOT / "_runtime" / "temp"
    assert not (outside_cwd / "_runtime").exists()


def test_pytest_basetemp_uses_repo_runtime_when_invoked_from_external_cwd(tmp_path):
    outside_cwd = tmp_path / "outside"
    outside_cwd.mkdir()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(REPO_ROOT / "tests" / "test_runtime_paths.py"),
            "-q",
            "-k",
            "test_get_temp_path_uses_runtime_root",
        ],
        cwd=outside_cwd,
        env={
            **os.environ,
            "PYTHONPATH": str(REPO_ROOT),
            "PIXELLE_VIDEO_ROOT": "",
            "PIXELLE_VIDEO_RUNTIME_ROOT": "",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert (REPO_ROOT / "_runtime" / "pytest-basetemp").exists()
    assert not (outside_cwd / "_runtime").exists()


def test_legacy_logs_config_resolves_to_runtime_logs(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    monkeypatch.delenv("PIXELLE_VIDEO_RUNTIME_ROOT", raising=False)

    resolved = _resolve_logging_config({"log_dir": "logs"})

    assert Path(resolved["log_dir"]) == tmp_path / "_runtime" / "logs"
