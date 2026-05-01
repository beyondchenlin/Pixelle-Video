# Stage-Gated Delivery Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local delivery-loop runner that enforces the sequence `integration acceptance -> two review gates -> one feature delivery checkpoint -> return to integration acceptance`.

**Architecture:** Add a PowerShell runner that mirrors the closeout runner pattern and uses integration acceptance reports under `_runtime/integration_acceptance/` as the phase gate state. The runner never edits business code, never auto-commits, never auto-pushes, and never auto-dispatches agents. Tests use temporary git repositories and test-only JSON definitions so behavior is deterministic without touching real runtime services.

**Tech Stack:** PowerShell 5+, Python pytest, git CLI, existing closeout runner conventions.

---

## File Structure

- Create: `scripts/run_delivery_loop.ps1`
  - Owns phase selection, git clean checks, command execution, integration acceptance report generation, review gate marking, and phase advancement.
- Create: `tests/test_delivery_loop_runner.py`
  - Verifies list/status behavior, dirty worktree fail-fast, integration acceptance report generation, double review gate enforcement, and feature checkpoint blocking.

No production Python modules, API code, frontend code, or business pipeline files should be modified by this plan.

## Task 1: Add Failing List And Dirty-Gate Tests

**Files:**

- Create: `tests/test_delivery_loop_runner.py`
- Create later: `scripts/run_delivery_loop.ps1`

- [ ] **Step 1: Create the failing test file**

Create `tests/test_delivery_loop_runner.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py::test_delivery_loop_lists_phases_without_clean_worktree tests/test_delivery_loop_runner.py::test_delivery_loop_fails_fast_when_repo_is_dirty_for_acceptance
```

Expected: FAIL because `scripts/run_delivery_loop.ps1` does not exist.

- [ ] **Step 3: Do not commit red state**

Do not commit yet. Task 2 adds the minimal runner skeleton.

## Task 2: Implement Runner Skeleton, Phase Listing, And Dirty Gate

**Files:**

- Create: `scripts/run_delivery_loop.ps1`
- Modify: `tests/test_delivery_loop_runner.py`

- [ ] **Step 1: Create minimal runner skeleton**

Create `scripts/run_delivery_loop.ps1`:

```powershell
[CmdletBinding()]
param(
    [string]$RepoRoot = "",
    [string]$AcceptanceDefinitionPath = "",
    [switch]$ListPhases,
    [switch]$RunIntegrationAcceptance,
    [switch]$StartFeatureDelivery,
    [string]$ReportPath = "",
    [ValidateSet("none", "1", "2")]
    [string]$MarkReviewGate = "none",
    [ValidateSet("pending", "passed", "failed")]
    [string]$ReviewResult = "pending"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-RunnerLine {
    param([string]$Message)
    Write-Output $Message
}

function Resolve-RepoRoot {
    param([string]$PathValue)
    if ($PathValue) {
        return (Resolve-Path -LiteralPath $PathValue).Path
    }
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
}

function Assert-CleanGitWorktree {
    param([string]$Root)
    $status = & git -C $Root status --porcelain
    if ($LASTEXITCODE -ne 0) {
        Write-RunnerLine "failed to read git status"
        exit 2
    }
    if ($status) {
        Write-RunnerLine "git worktree is not clean"
        $status | ForEach-Object { Write-RunnerLine $_ }
        exit 2
    }
}

function Write-PhaseList {
    Write-RunnerLine "integration_acceptance`tRun real frontend/backend acceptance checks"
    Write-RunnerLine "feature_delivery`tImplement exactly one approved feature unit"
}

if ($ListPhases) {
    Write-PhaseList
    exit 0
}

if ($MarkReviewGate -ne "none") {
    Write-RunnerLine "review gate marking is not implemented yet"
    exit 3
}

$ResolvedRepoRoot = Resolve-RepoRoot $RepoRoot
Assert-CleanGitWorktree $ResolvedRepoRoot

if ($RunIntegrationAcceptance) {
    Write-RunnerLine "integration acceptance is not implemented yet"
    exit 3
}

if ($StartFeatureDelivery) {
    Write-RunnerLine "feature delivery checkpoint is not implemented yet"
    exit 3
}

Write-RunnerLine "no delivery loop action was requested"
exit 3
```

- [ ] **Step 2: Run skeleton tests**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py::test_delivery_loop_lists_phases_without_clean_worktree tests/test_delivery_loop_runner.py::test_delivery_loop_fails_fast_when_repo_is_dirty_for_acceptance
```

Expected: PASS.

- [ ] **Step 3: Run quality checks**

Run:

```powershell
python -m ruff check tests/test_delivery_loop_runner.py
git diff --check scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
```

Expected: both pass.

- [ ] **Step 4: Commit and push**

Run:

```powershell
git add scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
git commit -m "test: 增加阶段门控循环运行器骨架" -m "- 增加阶段列表和脏工作区 fail-fast 测试" -m "- 新增 run_delivery_loop.ps1 最小骨架"
git push origin dev
```

## Task 3: Add Integration Acceptance Report Generation

**Files:**

- Modify: `scripts/run_delivery_loop.ps1`
- Modify: `tests/test_delivery_loop_runner.py`

- [ ] **Step 1: Add failing report test**

Append to `tests/test_delivery_loop_runner.py`:

```python
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
```

- [ ] **Step 2: Run report test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py::test_delivery_loop_runs_acceptance_and_writes_needs_review_report tests/test_delivery_loop_runner.py::test_delivery_loop_stops_on_first_failing_acceptance_check
```

Expected: FAIL because acceptance execution, fail-fast command handling, and report writing are not implemented.

- [ ] **Step 3: Add acceptance definition and command helpers**

Add these functions to `scripts/run_delivery_loop.ps1` before the main action block:

```powershell
function Get-AcceptanceDefinition {
    param([string]$PathValue)
    if ($PathValue) {
        $raw = Get-Content -Raw -LiteralPath $PathValue
        return $raw | ConvertFrom-Json
    }
    return [PSCustomObject]@{
        cycle_id = "default-integration-acceptance"
        checks = @(
            [PSCustomObject]@{
                id = "stage-closeout"
                title = "Stage1 Stage2 closeout status"
                command = "powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_stage_closeout.ps1 -ContinueAfterReviewed"
            },
            [PSCustomObject]@{
                id = "global-quality"
                title = "Global lint"
                command = "python -m ruff check pixelle_video api web tests"
            },
            [PSCustomObject]@{
                id = "cross-stage-tests"
                title = "Cross-stage pipeline and text rendering tests"
                command = "python -m pytest -q tests/test_standard_pipeline_staged_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_pipeline_text_rendering_contract.py tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py"
            },
            [PSCustomObject]@{
                id = "diff-check"
                title = "Git whitespace diff check"
                command = "git diff --check"
            }
        )
    }
}

function Invoke-DeliveryCommand {
    param(
        [string]$Root,
        [string]$Command
    )
    Push-Location $Root
    try {
        $output = & powershell -NoProfile -ExecutionPolicy Bypass -Command $Command 2>&1
        $code = $LASTEXITCODE
        if ($null -eq $code) {
            $code = 0
        }
        return [PSCustomObject]@{
            Command = $Command
            ExitCode = [int]$code
            Output = @($output | ForEach-Object { [string]$_ })
        }
    }
    finally {
        Pop-Location
    }
}

function New-IntegrationAcceptanceDirectory {
    param([string]$Root)
    $dir = Join-Path $Root "_runtime/integration_acceptance"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Get-CurrentCommit {
    param([string]$Root)
    $commit = (& git -C $Root rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        return "unknown"
    }
    return $commit
}

function Get-CurrentBranch {
    param([string]$Root)
    $branch = (& git -C $Root branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $branch) {
        return "unknown"
    }
    return $branch
}
```

- [ ] **Step 4: Add report writer**

Add this function to `scripts/run_delivery_loop.ps1`:

```powershell
function New-IntegrationAcceptanceReport {
    param(
        [string]$Root,
        [object]$Definition,
        [object[]]$Results,
        [string]$Status
    )
    $dir = New-IntegrationAcceptanceDirectory $Root
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $path = Join-Path $dir "$timestamp`_$($Definition.cycle_id).md"
    $commit = Get-CurrentCommit $Root
    $branch = Get-CurrentBranch $Root
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("<!-- delivery-loop")
    $lines.Add("phase: integration_acceptance")
    $lines.Add("cycle_id: $($Definition.cycle_id)")
    $lines.Add("status: $Status")
    $lines.Add("review_gate_1: pending")
    $lines.Add("review_gate_2: pending")
    $lines.Add("-->")
    $lines.Add("")
    $lines.Add("# Integration Acceptance Report: $($Definition.cycle_id)")
    $lines.Add("")
    $lines.Add("- phase: integration_acceptance")
    $lines.Add("- cycle_id: $($Definition.cycle_id)")
    $lines.Add("- status: $Status")
    $lines.Add("- branch: $branch")
    $lines.Add("- commit: $commit")
    $lines.Add("")
    $lines.Add("## Acceptance Commands")
    foreach ($result in $Results) {
        $lines.Add("")
        $lines.Add('```powershell')
        $lines.Add($result.Command)
        $lines.Add('```')
        $lines.Add("")
        $lines.Add("exit_code: $($result.ExitCode)")
        $lines.Add("")
        $lines.Add('```text')
        foreach ($item in $result.Output) {
            $lines.Add($item)
        }
        $lines.Add('```')
    }
    $lines.Add("")
    $lines.Add("## Review Gate 1")
    $lines.Add("")
    $lines.Add("- [ ] Stage1 / Stage2 user-visible entries remain reachable.")
    $lines.Add("- [ ] Stage2 projection preview remains preview-only.")
    $lines.Add("- [ ] Title, subtitle, and text rendering do not conflict with Stage1 / Stage2 data flow.")
    $lines.Add("- [ ] No local paths, provider URLs, workflow paths, raw prompts, or raw responses are exposed.")
    $lines.Add("")
    $lines.Add("## Review Gate 2")
    $lines.Add("")
    $lines.Add("- [ ] Failures identify a command, page, screenshot, or log.")
    $lines.Add("- [ ] No hidden persistence outside _runtime was introduced.")
    $lines.Add("- [ ] Next work must be exactly one approved feature unit.")
    $lines.Add("- [ ] Any plan drift has been captured in a spec or plan update.")
    Set-Content -LiteralPath $path -Value $lines -Encoding UTF8
    return $path
}
```

- [ ] **Step 5: Wire `-RunIntegrationAcceptance`**

Replace the current `if ($RunIntegrationAcceptance)` block with:

```powershell
if ($RunIntegrationAcceptance) {
    $definition = Get-AcceptanceDefinition $AcceptanceDefinitionPath
    $results = New-Object System.Collections.Generic.List[object]
    foreach ($check in @($definition.checks)) {
        $result = Invoke-DeliveryCommand $ResolvedRepoRoot ([string]$check.command)
        $results.Add($result)
        if ($result.ExitCode -ne 0) {
            $report = New-IntegrationAcceptanceReport -Root $ResolvedRepoRoot -Definition $definition -Results @($results.ToArray()) -Status "verification_failed"
            Write-RunnerLine "status: verification_failed"
            Write-RunnerLine "report: $report"
            exit 1
        }
    }

    $report = New-IntegrationAcceptanceReport -Root $ResolvedRepoRoot -Definition $definition -Results @($results.ToArray()) -Status "needs_review"
    Write-RunnerLine "status: needs_review"
    Write-RunnerLine "report: $report"
    exit 0
}
```

- [ ] **Step 6: Run report tests**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py
python -m ruff check tests/test_delivery_loop_runner.py
git diff --check scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
```

Expected: all pass.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
git commit -m "feat: 生成集成体验验收报告" -m "- 执行集成验收命令并记录输出" -m "- 将报告写入 _runtime/integration_acceptance" -m "- 验证失败时保留 verification_failed 报告"
git push origin dev
```

## Task 4: Add Review Gate Marking And Feature Delivery Blocking

**Files:**

- Modify: `scripts/run_delivery_loop.ps1`
- Modify: `tests/test_delivery_loop_runner.py`

- [ ] **Step 1: Add failing review gate and feature checkpoint test**

Append to `tests/test_delivery_loop_runner.py`:

```python
def test_delivery_loop_requires_acceptance_review_before_feature_delivery(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    definition = _write_acceptance_definition(
        repo,
        command="Write-Output 'acceptance-ok'",
    )

    acceptance = _run_runner(
        "-RepoRoot",
        str(repo),
        "-AcceptanceDefinitionPath",
        str(definition),
        "-RunIntegrationAcceptance",
    )
    assert acceptance.returncode == 0
    report = sorted((repo / "_runtime" / "integration_acceptance").glob("*_fixture-cycle.md"))[0]

    blocked = _run_runner(
        "-RepoRoot",
        str(repo),
        "-StartFeatureDelivery",
    )
    assert blocked.returncode == 3
    assert "integration acceptance review gates are not complete" in blocked.stdout

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
    assert "- status: needs_review" in report.read_text(encoding="utf-8")

    still_blocked = _run_runner(
        "-RepoRoot",
        str(repo),
        "-StartFeatureDelivery",
    )
    assert still_blocked.returncode == 3
    assert "integration acceptance review gates are not complete" in still_blocked.stdout

    gate_two = _run_runner(
        "-RepoRoot",
        str(repo),
        "-ReportPath",
        str(report),
        "-MarkReviewGate",
        "2",
        "-ReviewResult",
        "passed",
    )
    assert gate_two.returncode == 0
    report_text = report.read_text(encoding="utf-8")
    assert "status: passed" in report_text
    assert "- status: passed" in report_text

    feature = _run_runner(
        "-RepoRoot",
        str(repo),
        "-StartFeatureDelivery",
    )
    assert feature.returncode == 0
    assert "status: feature_delivery_ready" in feature.stdout
    assert "implement exactly one approved feature unit" in feature.stdout
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py::test_delivery_loop_requires_acceptance_review_before_feature_delivery
```

Expected: FAIL because review gate marking and feature checkpoint are not implemented.

- [ ] **Step 3: Add metadata and review gate helpers**

Add these functions to `scripts/run_delivery_loop.ps1`:

```powershell
function Get-ReportMetadata {
    param([string]$PathValue)
    $content = Get-Content -Raw -LiteralPath $PathValue
    $metadata = @{}
    foreach ($line in ($content -split "`r?`n")) {
        if ($line -match "^phase:\s*(.+)$") {
            $metadata["phase"] = $Matches[1].Trim()
        }
        elseif ($line -match "^cycle_id:\s*(.+)$") {
            $metadata["cycle_id"] = $Matches[1].Trim()
        }
        elseif ($line -match "^status:\s*(.+)$") {
            $metadata["status"] = $Matches[1].Trim()
        }
        elseif ($line -match "^review_gate_1:\s*(.+)$") {
            $metadata["review_gate_1"] = $Matches[1].Trim()
        }
        elseif ($line -match "^review_gate_2:\s*(.+)$") {
            $metadata["review_gate_2"] = $Matches[1].Trim()
        }
        elseif ($line -eq "-->") {
            break
        }
    }
    return $metadata
}

function Set-ReviewGateResult {
    param(
        [string]$PathValue,
        [string]$Gate,
        [string]$Result
    )
    if (-not $PathValue) {
        Write-RunnerLine "ReportPath is required when marking a review gate"
        exit 3
    }

    $content = Get-Content -Raw -LiteralPath $PathValue
    $field = "review_gate_$Gate"
    $updated = $content -replace "(?m)^${field}:\s*\w+", "${field}: $Result"
    $metadata = Get-ReportMetadata $PathValue
    $otherGate = if ($Gate -eq "1") { "review_gate_2" } else { "review_gate_1" }
    $otherResult = if ($metadata.ContainsKey($otherGate)) { $metadata[$otherGate] } else { "pending" }

    if ($Result -eq "failed") {
        $updated = $updated -replace "(?m)^status:\s*\w+", "status: review_failed"
        $updated = $updated -replace "(?m)^- status:\s*\w+", "- status: review_failed"
    }
    elseif ($Result -eq "passed" -and $otherResult -eq "passed") {
        $updated = $updated -replace "(?m)^status:\s*\w+", "status: passed"
        $updated = $updated -replace "(?m)^- status:\s*\w+", "- status: passed"
    }

    Set-Content -LiteralPath $PathValue -Value $updated -Encoding UTF8
    Write-RunnerLine "review_gate_${Gate}: $Result"
}

function Get-LatestIntegrationAcceptanceReport {
    param([string]$Root)
    $dir = Join-Path $Root "_runtime/integration_acceptance"
    if (-not (Test-Path -LiteralPath $dir)) {
        return $null
    }
    $reports = @(Get-ChildItem -LiteralPath $dir -Filter "*.md" | Sort-Object LastWriteTime -Descending)
    if ($reports.Count -eq 0) {
        return $null
    }
    return $reports[0].FullName
}

function Assert-IntegrationAcceptancePassed {
    param([string]$Root)
    $report = Get-LatestIntegrationAcceptanceReport $Root
    if ($null -eq $report) {
        Write-RunnerLine "integration acceptance report was not found"
        exit 3
    }
    $metadata = Get-ReportMetadata $report
    if ($metadata["phase"] -ne "integration_acceptance" -or $metadata["status"] -ne "passed") {
        Write-RunnerLine "integration acceptance review gates are not complete"
        Write-RunnerLine "report: $report"
        exit 3
    }
    return $report
}
```

- [ ] **Step 4: Move review marking before clean gate**

In the main action block, place this before `Assert-CleanGitWorktree`:

```powershell
if ($MarkReviewGate -ne "none") {
    Set-ReviewGateResult $ReportPath $MarkReviewGate $ReviewResult
    exit 0
}
```

Remove the older placeholder review gate block.

- [ ] **Step 5: Implement feature checkpoint**

Replace the current `if ($StartFeatureDelivery)` block with:

```powershell
if ($StartFeatureDelivery) {
    $report = Assert-IntegrationAcceptancePassed $ResolvedRepoRoot
    Write-RunnerLine "status: feature_delivery_ready"
    Write-RunnerLine "integration_acceptance_report: $report"
    Write-RunnerLine "next: implement exactly one approved feature unit"
    exit 0
}
```

- [ ] **Step 6: Run delivery loop tests**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py
python -m ruff check tests/test_delivery_loop_runner.py
git diff --check scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
```

Expected: all pass.

- [ ] **Step 7: Commit and push**

Run:

```powershell
git add scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
git commit -m "feat: 强制集成验收双重 review gate" -m "- 支持标记集成验收报告 review gate" -m "- 阻止未通过验收的功能开发入口" -m "- 输出单功能开发就绪状态"
git push origin dev
```

## Task 5: Final Verification And First Real Integration Acceptance Run

**Files:**

- Verify: `scripts/run_delivery_loop.ps1`
- Verify: `tests/test_delivery_loop_runner.py`

- [ ] **Step 1: Run focused verification**

Run:

```powershell
python -m pytest -q tests/test_delivery_loop_runner.py
python -m ruff check tests/test_delivery_loop_runner.py
git diff --check
```

Expected: all pass.

- [ ] **Step 2: Run the real default integration acceptance once**

Run:

```powershell
$runOutput = powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -RunIntegrationAcceptance
$runOutput
$report = (
    $runOutput |
    Select-String '^report: ' |
    Select-Object -Last 1
).Line -replace '^report:\s*', ''
if (-not $report) {
    throw "Delivery loop runner did not print a report path."
}
```

Expected: command succeeds, output contains `status: needs_review`, and `$report` points to `_runtime/integration_acceptance/*.md`.

- [ ] **Step 3: Perform Review Gate 1 manually**

Open the generated report and verify:

- Stage1 / Stage2 closeout still reports passed.
- Stage2 projection remains preview-only.
- Title, subtitle, and text rendering are still covered by cross-stage tests.
- No local paths, provider URLs, workflow paths, raw prompts, or raw responses are exposed by normal user-visible flows.

If checks pass, mark gate 1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -ReportPath $report -MarkReviewGate 1 -ReviewResult passed
```

- [ ] **Step 4: Perform Review Gate 2 manually**

Open the report again and verify:

- Failures identify specific commands.
- Mutable state is only under `_runtime/`.
- The next action is exactly one approved feature unit.
- No hidden auto-agent, auto-commit, or auto-push behavior exists.

If checks pass, mark gate 2:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -ReportPath $report -MarkReviewGate 2 -ReviewResult passed
```

- [ ] **Step 5: Confirm feature delivery checkpoint**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_delivery_loop.ps1 -StartFeatureDelivery
```

Expected output includes:

```text
status: feature_delivery_ready
next: implement exactly one approved feature unit
```

- [ ] **Step 6: Commit final adjustments if any**

If any wording or test fixes were needed:

```powershell
git add scripts/run_delivery_loop.ps1 tests/test_delivery_loop_runner.py
git commit -m "fix: 完善阶段门控循环运行器细节"
git push origin dev
```

If no changes are needed, do not create an empty commit.

## Task 6: Write Next Feature Selection Note

**Files:**

- Create: `docs/superpowers/plans/2026-05-02-next-feature-selection-note.md`

- [ ] **Step 1: Create feature selection note**

Create `docs/superpowers/plans/2026-05-02-next-feature-selection-note.md`:

```markdown
# Next Feature Selection Note

Integration acceptance is the gate before feature delivery. After it passes, choose exactly one feature unit for the next implementation cycle.

Recommended next feature order:

1. Stage2 projection preview frontend acceptance improvements
2. IP character design chain
3. AssetBible / SceneCast editing and reuse
4. Workbench regenerate and stale recovery loop
5. Title, subtitle, and text rendering next-stage integration

Selection rule:

- Pick one item only.
- Write or update its spec.
- Write its implementation plan.
- Implement with TDD.
- After completion, return to integration acceptance before picking another feature.
```

- [ ] **Step 2: Commit and push**

Run:

```powershell
git add docs/superpowers/plans/2026-05-02-next-feature-selection-note.md
git commit -m "docs: 记录下一功能选择规则" -m "- 明确集成验收通过后只能选择一个功能单元" -m "- 记录推荐功能优先级"
git push origin dev
```
