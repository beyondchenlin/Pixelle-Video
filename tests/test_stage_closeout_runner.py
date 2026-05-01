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
    (path / ".gitignore").write_text("_runtime/*\n!_runtime/.gitkeep\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=path, check=True)
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


def test_closeout_runner_runs_one_task_and_writes_needs_review_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    task_file = _write_task_file(
        repo,
        command="Write-Output 'verification-ok'",
    )

    result = _run_runner(
        "-RepoRoot",
        str(repo),
        "-TaskDefinitionPath",
        str(task_file),
    )

    assert result.returncode == 0
    assert "status: needs_review" in result.stdout
    reports = sorted((repo / "_runtime" / "stage_closeout").glob("*_fixture-task.md"))
    assert len(reports) == 1
    report = reports[0].read_text(encoding="utf-8")
    assert "task_id: fixture-task" in report
    assert "status: needs_review" in report
    assert "review_gate_1: pending" in report
    assert "review_gate_2: pending" in report
    assert "verification-ok" in report
    assert "Review Gate 1" in report
    assert "Review Gate 2" in report


def _write_two_task_file(path: Path) -> Path:
    task_file = path / "tasks.json"
    task_file.write_text(
        json.dumps(
            [
                {
                    "id": "task-one",
                    "title": "Task one",
                    "stage": "fixture",
                    "description": "First deterministic task.",
                    "verification_commands": ["Write-Output 'one-ok'"],
                },
                {
                    "id": "task-two",
                    "title": "Task two",
                    "stage": "fixture",
                    "description": "Second deterministic task.",
                    "verification_commands": ["Write-Output 'two-ok'"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "tasks.json"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add two task file"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return task_file


def test_closeout_runner_requires_two_review_gates_before_next_task(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    task_file = _write_two_task_file(repo)

    first = _run_runner("-RepoRoot", str(repo), "-TaskDefinitionPath", str(task_file))
    assert first.returncode == 0
    first_report = sorted((repo / "_runtime" / "stage_closeout").glob("*_task-one.md"))[0]

    blocked = _run_runner(
        "-RepoRoot",
        str(repo),
        "-TaskDefinitionPath",
        str(task_file),
        "-ContinueAfterReviewed",
    )
    assert blocked.returncode == 3
    assert "review gates are not complete" in blocked.stdout

    gate_one = _run_runner(
        "-RepoRoot",
        str(repo),
        "-ReportPath",
        str(first_report),
        "-MarkReviewGate",
        "1",
        "-ReviewResult",
        "passed",
    )
    assert gate_one.returncode == 0
    assert "review_gate_1: passed" in first_report.read_text(encoding="utf-8")
    assert "status: needs_review" in first_report.read_text(encoding="utf-8")

    still_blocked = _run_runner(
        "-RepoRoot",
        str(repo),
        "-TaskDefinitionPath",
        str(task_file),
        "-ContinueAfterReviewed",
    )
    assert still_blocked.returncode == 3
    assert "review gates are not complete" in still_blocked.stdout

    gate_two = _run_runner(
        "-RepoRoot",
        str(repo),
        "-ReportPath",
        str(first_report),
        "-MarkReviewGate",
        "2",
        "-ReviewResult",
        "passed",
    )
    assert gate_two.returncode == 0
    assert "status: passed" in first_report.read_text(encoding="utf-8")

    second = _run_runner(
        "-RepoRoot",
        str(repo),
        "-TaskDefinitionPath",
        str(task_file),
        "-ContinueAfterReviewed",
    )
    assert second.returncode == 0
    assert "task-two" in second.stdout
    assert sorted((repo / "_runtime" / "stage_closeout").glob("*_task-two.md"))


def test_closeout_runner_marks_review_gate_without_clean_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    task_file = _write_task_file(
        repo,
        command="Write-Output 'verification-ok'",
    )
    first = _run_runner("-RepoRoot", str(repo), "-TaskDefinitionPath", str(task_file))
    assert first.returncode == 0
    report = sorted((repo / "_runtime" / "stage_closeout").glob("*_fixture-task.md"))[0]
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    gate_one = _run_runner(
        "-RepoRoot",
        str(repo),
        "-ReportPath",
        str(report),
        "-MarkReviewGate",
        "1",
        "-ReviewResult",
        "passed",
    )

    assert gate_one.returncode == 0
    assert "review_gate_1: passed" in report.read_text(encoding="utf-8")
