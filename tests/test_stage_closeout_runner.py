import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_stage_closeout.ps1"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell executable is required for closeout runner tests")
    return executable


def _run_runner(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            _powershell(),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER),
            *args,
        ],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=path, check=True)
    (path / "README.md").write_text("# fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, text=True)


def _write_task_file(path: Path, *, command: str) -> Path:
    task_file = path / "tasks.json"
    task_file.write_text(
        json.dumps(
            [
                {
                    "id": "fixture-task",
                    "title": "Fixture task",
                    "stage": "fixture",
                    "description": "A deterministic test task.",
                    "verification_commands": [command],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "tasks.json"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add task file"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return task_file


def test_closeout_runner_fails_fast_when_repo_is_dirty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    marker = repo / "should-not-run.txt"
    task_file = _write_task_file(
        repo,
        command=f"Set-Content -LiteralPath '{marker}' -Value 'ran'",
    )
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    result = _run_runner(
        "-RepoRoot",
        str(repo),
        "-TaskDefinitionPath",
        str(task_file),
    )

    assert result.returncode == 2
    assert "git worktree is not clean" in result.stdout
    assert not marker.exists()
