import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_delivery_loop.ps1"


def _powershell() -> str:
    executable = shutil.which("pwsh") or shutil.which("powershell")
    if executable is None:
        pytest.skip("PowerShell executable is required for delivery loop runner tests")
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
    (path / ".gitignore").write_text(
        "_runtime/*\n!_runtime/.gitkeep\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_acceptance_definition(
    path: Path,
    *,
    command: str | None = None,
    checks: list[dict[str, str]] | None = None,
) -> Path:
    if checks is None:
        if command is None:
            raise ValueError("command is required when checks are not provided")
        checks = [
            {
                "id": "fixture-check",
                "title": "Fixture check",
                "command": command,
            }
        ]
    definition = path / "integration_acceptance.json"
    definition.write_text(
        json.dumps(
            {
                "cycle_id": "fixture-cycle",
                "checks": checks,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "integration_acceptance.json"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "add acceptance definition"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return definition


def test_delivery_loop_lists_phases_without_clean_worktree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    result = _run_runner("-RepoRoot", str(repo), "-ListPhases")

    assert result.returncode == 0
    assert "integration_acceptance" in result.stdout
    assert "feature_delivery" in result.stdout


def test_delivery_loop_fails_fast_when_repo_is_dirty_for_acceptance(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    marker = repo / "should-not-run.txt"
    definition = _write_acceptance_definition(
        repo,
        command=f"Set-Content -LiteralPath '{marker}' -Value 'ran'",
    )
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")

    result = _run_runner(
        "-RepoRoot",
        str(repo),
        "-AcceptanceDefinitionPath",
        str(definition),
        "-RunIntegrationAcceptance",
    )

    assert result.returncode == 2
    assert "git worktree is not clean" in result.stdout
    assert not marker.exists()


def test_delivery_loop_runs_acceptance_and_writes_needs_review_report(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    definition = _write_acceptance_definition(
        repo,
        command="Write-Output 'acceptance-ok'",
    )

    result = _run_runner(
        "-RepoRoot",
        str(repo),
        "-AcceptanceDefinitionPath",
        str(definition),
        "-RunIntegrationAcceptance",
    )

    assert result.returncode == 0
    assert "status: needs_review" in result.stdout
    reports = sorted((repo / "_runtime" / "integration_acceptance").glob("*_fixture-cycle.md"))
    assert len(reports) == 1
    report = reports[0].read_text(encoding="utf-8")
    assert "cycle_id: fixture-cycle" in report
    assert "phase: integration_acceptance" in report
    assert "status: needs_review" in report
    assert "review_gate_1: pending" in report
    assert "review_gate_2: pending" in report
    assert "acceptance-ok" in report
    assert "Review Gate 1" in report
    assert "Review Gate 2" in report


def test_delivery_loop_stops_on_first_failing_acceptance_check(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    marker = repo / "should-not-run.txt"
    definition = _write_acceptance_definition(
        repo,
        checks=[
            {
                "id": "failing-check",
                "title": "Failing check",
                "command": "Write-Output 'before-failure'; exit 9",
            },
            {
                "id": "must-not-run",
                "title": "Must not run",
                "command": f"Set-Content -LiteralPath '{marker}' -Value 'ran'",
            },
        ],
    )

    result = _run_runner(
        "-RepoRoot",
        str(repo),
        "-AcceptanceDefinitionPath",
        str(definition),
        "-RunIntegrationAcceptance",
    )

    assert result.returncode == 1
    assert "status: verification_failed" in result.stdout
    assert not marker.exists()
    report = sorted((repo / "_runtime" / "integration_acceptance").glob("*_fixture-cycle.md"))[0]
    report_text = report.read_text(encoding="utf-8")
    assert "status: verification_failed" in report_text
    assert "before-failure" in report_text
    assert "must-not-run" not in report_text
