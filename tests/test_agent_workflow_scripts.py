from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeAlias

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_FILES = (
    ".githooks/commit-msg",
    ".githooks/pre-commit",
    ".oceans/agent-standards.conf",
    "AGENTS.md",
    "docs/agent/prompting-workflow.md",
    "scripts/agent-bootstrap.ps1",
    "scripts/agent-bootstrap.sh",
    "scripts/agent-standards-hook.sh",
    "scripts/agent-verify.ps1",
    "scripts/agent-verify.sh",
    "scripts/dedupe-agent-docs.sh",
)
Verifier: TypeAlias = Callable[
    [Path, dict[str, str] | None], subprocess.CompletedProcess[str]
]


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=check,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _find_shell() -> str | None:
    shell = shutil.which("sh")
    if shell:
        return shell

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidate = Path(program_files) / "Git" / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def _find_powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _copy_workflow(repo: Path) -> None:
    for relative in WORKFLOW_FILES:
        source = REPO_ROOT / relative
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


@pytest.fixture
def agent_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _copy_workflow(repo)
    _run(["git", "init", "-b", "feature/agent-test"], cwd=repo, check=True)
    _run(["git", "config", "user.name", "Agent Workflow Test"], cwd=repo, check=True)
    _run(
        ["git", "config", "user.email", "agent-workflow@example.invalid"],
        cwd=repo,
        check=True,
    )
    _run(["git", "add", "--", "."], cwd=repo, check=True)
    _run(
        ["git", "commit", "-m", "chore: 初始化代理测试仓库"],
        cwd=repo,
        check=True,
    )
    return repo


@pytest.fixture(params=("shell", "powershell"))
def verifier(request: pytest.FixtureRequest) -> Verifier:
    if request.param == "shell":
        shell = _find_shell()
        if not shell:
            pytest.skip("当前环境没有类 Unix shell")

        def run_shell(
            repo: Path,
            env: dict[str, str] | None = None,
        ) -> subprocess.CompletedProcess[str]:
            return _run([shell, "scripts/agent-verify.sh"], cwd=repo, env=env)

        return run_shell

    powershell = _find_powershell()
    if not powershell:
        pytest.skip("当前环境没有 PowerShell")

    def run_powershell(
        repo: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return _run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/agent-verify.ps1",
            ],
            cwd=repo,
            env=env,
        )

    return run_powershell


def test_non_baseline_repository_branch_is_allowed(
    agent_repo: Path,
    verifier: Verifier,
) -> None:
    result = verifier(agent_repo, None)
    assert result.returncode == 0, result.stdout + result.stderr


def test_model_artifact_is_blocked(
    agent_repo: Path,
    verifier: Verifier,
) -> None:
    model = agent_repo / "local-model.gguf"
    model.write_bytes(b"not-a-real-model")
    _run(["git", "add", "--", model.name], cwd=agent_repo, check=True)

    result = verifier(agent_repo, None)

    assert result.returncode == 1
    assert model.name in result.stdout + result.stderr


def test_python_check_does_not_create_virtual_environment(
    agent_repo: Path,
    verifier: Verifier,
) -> None:
    ruff = shutil.which("ruff")
    if not ruff:
        candidate = Path(sys.executable).with_name(
            "ruff.exe" if os.name == "nt" else "ruff"
        )
        if candidate.is_file():
            ruff = str(candidate)
    if not ruff:
        pytest.skip("当前测试环境没有 ruff")

    source = agent_repo / "sample.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    _run(["git", "add", "--", source.name], cwd=agent_repo, check=True)
    env = os.environ.copy()
    env["PATH"] = str(Path(ruff).parent) + os.pathsep + env.get("PATH", "")

    result = verifier(agent_repo, env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (agent_repo / ".venv").exists()

@pytest.mark.parametrize(
    ("message", "expected_code"),
    (
        ("merge: 合并代理工作流", 0),
        ("fix: english only title", 1),
        ("release: 发布代理工作流", 1),
    ),
)
def test_commit_message_policy(
    agent_repo: Path,
    message: str,
    expected_code: int,
) -> None:
    shell = _find_shell()
    if not shell:
        pytest.skip("当前环境没有类 Unix shell")

    message_file = agent_repo / "commit-message.txt"
    message_file.write_text(message + "\n", encoding="utf-8")
    result = _run(
        [shell, "scripts/agent-standards-hook.sh", "commit-msg", str(message_file)],
        cwd=agent_repo,
    )

    assert result.returncode == expected_code, result.stdout + result.stderr

    powershell = _find_powershell()
    if powershell:
        powershell_result = _run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                "scripts/agent-verify.ps1",
                "-CommitMessageFile",
                str(message_file),
            ],
            cwd=agent_repo,
        )
        assert powershell_result.returncode == expected_code, (
            powershell_result.stdout + powershell_result.stderr
        )


def test_bootstrap_allows_baseline_consistently(agent_repo: Path) -> None:
    shell = _find_shell()
    powershell = _find_powershell()
    if not shell or not powershell:
        pytest.skip("一致性测试需要两个脚本运行环境")

    _run(["git", "branch", "-m", "main"], cwd=agent_repo, check=True)
    shell_result = _run([shell, "scripts/agent-bootstrap.sh"], cwd=agent_repo)
    powershell_result = _run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts/agent-bootstrap.ps1",
        ],
        cwd=agent_repo,
    )

    assert shell_result.returncode == 0, shell_result.stdout + shell_result.stderr
    assert powershell_result.returncode == 0, (
        powershell_result.stdout + powershell_result.stderr
    )


def test_commit_message_hook_does_not_repeat_full_verification() -> None:
    hook = (REPO_ROOT / ".githooks" / "commit-msg").read_text(encoding="utf-8")
    assert "agent-standards-hook.sh commit-msg" in hook
    assert "agent-verify" not in hook
