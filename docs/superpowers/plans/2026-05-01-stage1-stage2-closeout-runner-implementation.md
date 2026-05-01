# Stage1 Stage2 Closeout Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PowerShell closeout runner that verifies Stage1 / Stage2 remaining closeout tasks, writes reports, and enforces two global review gates before advancing.

**Architecture:** The runner is a local PowerShell script with a finite built-in task queue and optional test-only task definition file. It never edits business code, never commits, and writes all mutable reports under `_runtime/stage_closeout/`. Pytest tests execute the script against temporary git repositories so git clean/dirty behavior is verified without mutating the real workspace.

**Tech Stack:** PowerShell 5+, Python pytest, git CLI, existing `ruff` and pytest commands.

---

## File Structure

- Create: `scripts/run_stage_closeout.ps1`
  - Owns task selection, git clean checks, command execution, report generation, review gate marking, and built-in Stage1 / Stage2 task definitions.
- Create: `tests/test_stage_closeout_runner.py`
  - Verifies dirty worktree fail-fast, successful single-task report generation, review gate marking, continuation blocking, and built-in task listing.

No production Python modules or business pipeline files should be modified.

## Task 1: Add Failing Dirty-Worktree Test

**Files:**

- Create: `tests/test_stage_closeout_runner.py`
- Create later: `scripts/run_stage_closeout.ps1`

- [ ] **Step 1: Write the failing test file**

Create `tests/test_stage_closeout_runner.py`:

```python
from __future__ import annotations

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
    subprocess.run(["git", "commit", "-m", "add task file"], cwd=path, check=True, capture_output=True, text=True)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_fails_fast_when_repo_is_dirty
```

Expected: FAIL because `scripts/run_stage_closeout.ps1` does not exist.

- [ ] **Step 3: Commit is skipped for red state**

Do not commit after this task; the next task adds the minimal script to make this test pass.

## Task 2: Implement Runner Skeleton And Dirty Gate

**Files:**

- Create: `scripts/run_stage_closeout.ps1`
- Test: `tests/test_stage_closeout_runner.py`

- [ ] **Step 1: Create minimal PowerShell runner**

Create `scripts/run_stage_closeout.ps1`:

```powershell
[CmdletBinding()]
param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$TaskDefinitionPath = "",
    [string]$TaskId = "",
    [switch]$ContinueAfterReviewed,
    [string]$ReportPath = "",
    [ValidateSet("none", "1", "2")]
    [string]$MarkReviewGate = "none",
    [ValidateSet("pending", "passed", "failed")]
    [string]$ReviewResult = "pending",
    [switch]$ListTasks
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-RunnerLine {
    param([string]$Message)
    Write-Output $Message
}

function Resolve-RepoRoot {
    param([string]$PathValue)
    return (Resolve-Path -LiteralPath $PathValue).Path
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

function Get-TaskDefinitions {
    param([string]$PathValue)
    if ($PathValue) {
        $raw = Get-Content -Raw -LiteralPath $PathValue
        return @($raw | ConvertFrom-Json)
    }
    return @()
}

$ResolvedRepoRoot = Resolve-RepoRoot $RepoRoot

if ($MarkReviewGate -ne "none") {
    Write-RunnerLine "review gate marking is not implemented yet"
    exit 3
}

Assert-CleanGitWorktree $ResolvedRepoRoot

$Tasks = Get-TaskDefinitions $TaskDefinitionPath
if (-not $Tasks -or $Tasks.Count -eq 0) {
    Write-RunnerLine "no closeout tasks are available"
    exit 3
}

Write-RunnerLine "closeout runner skeleton verified"
exit 0
```

- [ ] **Step 2: Run dirty gate test**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_fails_fast_when_repo_is_dirty
```

Expected: PASS.

- [ ] **Step 3: Run formatter/lint check for touched files**

Run:

```powershell
python -m ruff check tests/test_stage_closeout_runner.py
git diff --check scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
```

Expected: both pass.

- [ ] **Step 4: Commit**

Run:

```powershell
git add scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
git commit -m "test: 增加收口运行器脏工作区校验"
```

## Task 3: Add Verification Execution And Report Generation

**Files:**

- Modify: `tests/test_stage_closeout_runner.py`
- Modify: `scripts/run_stage_closeout.ps1`

- [ ] **Step 1: Add failing report-generation test**

Append to `tests/test_stage_closeout_runner.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_runs_one_task_and_writes_needs_review_report
```

Expected: FAIL because the runner does not execute commands or write reports.

- [ ] **Step 3: Replace runner with command execution and report writer**

Update `scripts/run_stage_closeout.ps1` so the bottom half after `$Tasks = ...` is:

```powershell
function New-ReportDirectory {
    param([string]$Root)
    $dir = Join-Path $Root "_runtime/stage_closeout"
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

function Invoke-VerificationCommand {
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

function New-CloseoutReport {
    param(
        [string]$Root,
        [object]$Task,
        [object[]]$Results,
        [string]$Status
    )
    $dir = New-ReportDirectory $Root
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $path = Join-Path $dir "$timestamp`_$($Task.id).md"
    $commit = Get-CurrentCommit $Root
    $branch = Get-CurrentBranch $Root
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("<!-- stage-closeout")
    $lines.Add("task_id: $($Task.id)")
    $lines.Add("status: $Status")
    $lines.Add("review_gate_1: pending")
    $lines.Add("review_gate_2: pending")
    $lines.Add("-->")
    $lines.Add("")
    $lines.Add("# Stage Closeout Report: $($Task.title)")
    $lines.Add("")
    $lines.Add("- task_id: $($Task.id)")
    $lines.Add("- stage: $($Task.stage)")
    $lines.Add("- status: $Status")
    $lines.Add("- branch: $branch")
    $lines.Add("- commit: $commit")
    $lines.Add("")
    $lines.Add("## Verification Commands")
    foreach ($result in $Results) {
        $lines.Add("")
        $lines.Add("```powershell")
        $lines.Add($result.Command)
        $lines.Add("```")
        $lines.Add("")
        $lines.Add("exit_code: $($result.ExitCode)")
        $lines.Add("")
        $lines.Add("```text")
        foreach ($item in $result.Output) {
            $lines.Add($item)
        }
        $lines.Add("```")
    }
    $lines.Add("")
    $lines.Add("## Review Gate 1")
    $lines.Add("")
    $lines.Add("- [ ] Stage1 / Stage2 boundary still matches the original plan.")
    $lines.Add("- [ ] No second source of truth was introduced.")
    $lines.Add("- [ ] Preview-only features remain out of the main generation path.")
    $lines.Add("- [ ] No local paths, provider URLs, workflow paths, raw prompts, or raw responses are exposed.")
    $lines.Add("- [ ] Title/subtitle/text-rendering changes do not conflict with this task.")
    $lines.Add("")
    $lines.Add("## Review Gate 2")
    $lines.Add("")
    $lines.Add("- [ ] Tests cover the core regression risks.")
    $lines.Add("- [ ] Failures identify a specific task and command.")
    $lines.Add("- [ ] No hidden persistence side effects were introduced.")
    $lines.Add("- [ ] No cross-module duplicate state was introduced.")
    $lines.Add("- [ ] Next task can proceed without splitting this task further.")
    Set-Content -LiteralPath $path -Value $lines -Encoding UTF8
    return $path
}

function Select-Task {
    param(
        [object[]]$Tasks,
        [string]$RequestedTaskId
    )
    if ($RequestedTaskId) {
        $match = @($Tasks | Where-Object { $_.id -eq $RequestedTaskId })
        if ($match.Count -ne 1) {
            Write-RunnerLine "task was not found: $RequestedTaskId"
            exit 3
        }
        return $match[0]
    }
    return $Tasks[0]
}

if (-not $Tasks -or $Tasks.Count -eq 0) {
    Write-RunnerLine "no closeout tasks are available"
    exit 3
}

$Task = Select-Task $Tasks $TaskId
$Results = New-Object System.Collections.Generic.List[object]
foreach ($command in @($Task.verification_commands)) {
    $result = Invoke-VerificationCommand $ResolvedRepoRoot ([string]$command)
    $Results.Add($result)
    if ($result.ExitCode -ne 0) {
        $report = New-CloseoutReport $ResolvedRepoRoot $Task @($Results) "verification_failed"
        Write-RunnerLine "status: verification_failed"
        Write-RunnerLine "report: $report"
        exit 1
    }
}

$reportPath = New-CloseoutReport $ResolvedRepoRoot $Task @($Results) "needs_review"
Write-RunnerLine "status: needs_review"
Write-RunnerLine "report: $reportPath"
exit 0
```

- [ ] **Step 4: Run report test**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_runs_one_task_and_writes_needs_review_report
```

Expected: PASS.

- [ ] **Step 5: Run all runner tests**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py
```

Expected: all runner tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
git commit -m "feat: 生成收口验证报告"
```

## Task 4: Add Review Gate Marking And Continuation Blocking

**Files:**

- Modify: `tests/test_stage_closeout_runner.py`
- Modify: `scripts/run_stage_closeout.ps1`

- [ ] **Step 1: Add failing review gate test**

Append to `tests/test_stage_closeout_runner.py`:

```python
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
    subprocess.run(["git", "commit", "-m", "add two task file"], cwd=path, check=True, capture_output=True, text=True)
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
```

- [ ] **Step 2: Run review gate test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_requires_two_review_gates_before_next_task
```

Expected: FAIL because marking and continuation checks are not implemented.

- [ ] **Step 3: Add report metadata helpers**

Add these functions to `scripts/run_stage_closeout.ps1` before task selection:

```powershell
function Get-ReportMetadata {
    param([string]$PathValue)
    $content = Get-Content -Raw -LiteralPath $PathValue
    $metadata = @{}
    foreach ($line in ($content -split "`r?`n")) {
        if ($line -match "^task_id:\s*(.+)$") {
            $metadata["task_id"] = $Matches[1].Trim()
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
    $updated = $content -replace "(?m)^$field:\s*\w+", "$field: $Result"
    $metadata = Get-ReportMetadata $PathValue
    $otherGate = if ($Gate -eq "1") { "review_gate_2" } else { "review_gate_1" }
    $otherResult = if ($metadata.ContainsKey($otherGate)) { $metadata[$otherGate] } else { "pending" }
    if ($Result -eq "failed") {
        $updated = $updated -replace "(?m)^status:\s*\w+", "status: review_failed"
    }
    elseif ($Result -eq "passed" -and $otherResult -eq "passed") {
        $updated = $updated -replace "(?m)^status:\s*\w+", "status: passed"
    }
    Set-Content -LiteralPath $PathValue -Value $updated -Encoding UTF8
    Write-RunnerLine "review_gate_${Gate}: $Result"
}

function Get-LatestReportForTask {
    param(
        [string]$Root,
        [string]$TaskIdValue
    )
    $dir = Join-Path $Root "_runtime/stage_closeout"
    if (-not (Test-Path -LiteralPath $dir)) {
        return $null
    }
    $reports = @(Get-ChildItem -LiteralPath $dir -Filter "*_$TaskIdValue.md" | Sort-Object LastWriteTime -Descending)
    if ($reports.Count -eq 0) {
        return $null
    }
    return $reports[0].FullName
}

function Select-NextTaskWithReports {
    param(
        [string]$Root,
        [object[]]$Tasks,
        [string]$RequestedTaskId,
        [bool]$AllowContinue
    )
    if ($RequestedTaskId) {
        return Select-Task $Tasks $RequestedTaskId
    }
    $sawPassedTask = $false
    foreach ($task in $Tasks) {
        $report = Get-LatestReportForTask $Root ([string]$task.id)
        if ($null -eq $report) {
            if ($sawPassedTask -and -not $AllowContinue) {
                Write-RunnerLine "previous task passed; rerun with -ContinueAfterReviewed to advance"
                exit 3
            }
            return $task
        }
        $metadata = Get-ReportMetadata $report
        if ($metadata["status"] -eq "passed") {
            $sawPassedTask = $true
            continue
        }
        Write-RunnerLine "review gates are not complete for task: $($task.id)"
        Write-RunnerLine "report: $report"
        exit 3
    }
    Write-RunnerLine "all closeout tasks are passed"
    exit 0
}
```

- [ ] **Step 4: Wire review marking and task selection**

Update the main flow:

```powershell
if ($MarkReviewGate -ne "none") {
    Set-ReviewGateResult $ReportPath $MarkReviewGate $ReviewResult
    exit 0
}

Assert-CleanGitWorktree $ResolvedRepoRoot

$Tasks = Get-TaskDefinitions $TaskDefinitionPath
if (-not $Tasks -or $Tasks.Count -eq 0) {
    Write-RunnerLine "no closeout tasks are available"
    exit 3
}

$Task = Select-NextTaskWithReports $ResolvedRepoRoot $Tasks $TaskId ([bool]$ContinueAfterReviewed)
```

Remove the older direct `$Task = Select-Task $Tasks $TaskId` line.

- [ ] **Step 5: Print task ID when running**

Before executing commands, add:

```powershell
Write-RunnerLine "task: $($Task.id)"
```

- [ ] **Step 6: Run review gate tests**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py
```

Expected: all runner tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
git commit -m "feat: 强制收口任务双重 review gate"
```

## Task 5: Add Built-In Stage Closeout Task Queue

**Files:**

- Modify: `tests/test_stage_closeout_runner.py`
- Modify: `scripts/run_stage_closeout.ps1`

- [ ] **Step 1: Add failing list-tasks test**

Append to `tests/test_stage_closeout_runner.py`:

```python
def test_closeout_runner_lists_builtin_stage_tasks() -> None:
    result = _run_runner("-ListTasks")

    assert result.returncode == 0
    assert "stage1a-contract" in result.stdout
    assert "stage1b-workbench-stale-artifact" in result.stdout
    assert "stage2-assetbible-scenecast-projection" in result.stdout
    assert "stage1-stage2-boundary" in result.stdout
```

- [ ] **Step 2: Run list test to verify it fails**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py::test_closeout_runner_lists_builtin_stage_tasks
```

Expected: FAIL because built-in tasks are empty.

- [ ] **Step 3: Implement built-in task definitions**

Replace `Get-TaskDefinitions` in `scripts/run_stage_closeout.ps1` with:

```powershell
function Get-BuiltinCloseoutTasks {
    return @(
        [PSCustomObject]@{
            id = "stage1a-contract"
            title = "Stage1A contract verification"
            stage = "stage1a"
            description = "Verify LLM trace, PromptPlan, ImagePromptComposer, and StandardPipeline planning contracts."
            verification_commands = @(
                "python -m pytest -q tests/test_llm_interaction_trace_model.py tests/test_llm_interaction_recorder.py tests/test_llm_service_trace_capture.py tests/test_llm_trace_api.py tests/test_prompt_plan_model.py tests/test_prompt_plan_service.py tests/test_image_prompt_composer.py tests/test_standard_pipeline_storyboard_generation.py"
            )
        },
        [PSCustomObject]@{
            id = "stage1b-workbench-stale-artifact"
            title = "Stage1B Workbench stale artifact verification"
            stage = "stage1b"
            description = "Verify Workbench, stale propagation, artifact bridge, regeneration, API, and UI contracts."
            verification_commands = @(
                "python -m pytest -q tests/test_storyboard_workbench_artifact_bridge.py tests/test_storyboard_workbench_api.py tests/test_storyboard_workbench_service.py tests/test_storyboard_workbench_frontend_api.py tests/test_storyboard_workbench_panel_ui.py tests/test_storyboard_workbench_stale_ui.py tests/test_storyboard_frame_regeneration.py tests/test_stale_dependency_models.py tests/test_stale_dependency_repository_contract.py tests/test_stale_dependency_read_model.py tests/test_stale_dependency_propagation.py tests/test_stale_dependency_api.py tests/test_stale_write_integration.py"
            )
        },
        [PSCustomObject]@{
            id = "stage2-assetbible-scenecast-projection"
            title = "Stage2 AssetBible SceneCast projection verification"
            stage = "stage2"
            description = "Verify AssetBible, SceneCast, PromptPlan projection preview, API, and UI contracts."
            verification_commands = @(
                "python -m pytest -q tests/test_asset_bible_models.py tests/test_scene_cast_model.py tests/test_scene_casting_validation.py tests/test_prompt_composer_asset_projection.py tests/test_asset_prompt_plan_composer.py tests/test_asset_bible_api.py tests/test_asset_prompt_plan_projection_ui.py tests/test_stage2_projection_pipeline_ui.py"
            )
        },
        [PSCustomObject]@{
            id = "stage1-stage2-boundary"
            title = "Stage1 Stage2 boundary verification"
            stage = "cross-stage"
            description = "Verify global lint, staged/hyperframes pipeline, and text rendering contracts."
            verification_commands = @(
                "python -m ruff check pixelle_video api web tests",
                "python -m pytest -q tests/test_standard_pipeline_staged_mode.py tests/test_standard_pipeline_hyperframes_mode.py tests/test_pipeline_text_rendering_contract.py tests/test_text_rendering_preview_service.py tests/test_text_rendering_preview_api.py",
                "git diff --check"
            )
        }
    )
}

function Get-TaskDefinitions {
    param([string]$PathValue)
    if ($PathValue) {
        $raw = Get-Content -Raw -LiteralPath $PathValue
        return @($raw | ConvertFrom-Json)
    }
    return Get-BuiltinCloseoutTasks
}
```

- [ ] **Step 4: Implement `-ListTasks` before clean-gate**

Move task loading above `Assert-CleanGitWorktree`, then add:

```powershell
$Tasks = Get-TaskDefinitions $TaskDefinitionPath
if ($ListTasks) {
    foreach ($task in $Tasks) {
        Write-RunnerLine "$($task.id)`t$($task.stage)`t$($task.title)"
    }
    exit 0
}

Assert-CleanGitWorktree $ResolvedRepoRoot
```

Remove the older duplicate `$Tasks = Get-TaskDefinitions $TaskDefinitionPath` line after the clean gate. This ensures `-ListTasks` works even during active development.

- [ ] **Step 5: Run list and runner tests**

Run:

```powershell
python -m pytest -q tests/test_stage_closeout_runner.py
```

Expected: all runner tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
git commit -m "feat: 内置 Stage1 Stage2 收口任务队列"
```

## Task 6: Final Verification And Push

**Files:**

- Verify: `scripts/run_stage_closeout.ps1`
- Verify: `tests/test_stage_closeout_runner.py`

- [ ] **Step 1: Run focused verification**

Run:

```powershell
python -m ruff check tests/test_stage_closeout_runner.py
python -m pytest -q tests/test_stage_closeout_runner.py
git diff --check
```

Expected: all pass.

- [ ] **Step 2: Run first real closeout task once**

Run:

```powershell
$runOutput = powershell -ExecutionPolicy Bypass -File scripts/run_stage_closeout.ps1 -TaskId stage1a-contract
$runOutput
$report = (
    $runOutput |
    Select-String '^report: ' |
    Select-Object -Last 1
).Line -replace '^report:\s*', ''
if (-not $report) {
    throw "Closeout runner did not print a report path."
}
```

Expected: command succeeds, output contains `status: needs_review`, and `$report` points to a report under `_runtime/stage_closeout/`.

- [ ] **Step 3: Perform Review Gate 1 manually**

Open the generated report. Verify:

- Stage1 / Stage2 boundaries are unchanged.
- No second fact source is introduced.
- Stage2 projection remains preview-only.
- No local paths, provider URLs, workflow paths, raw prompts, or raw responses are exposed.
- Title/subtitle/text-rendering changes are not pulled into this runner.

If all checks pass, mark gate 1:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_stage_closeout.ps1 -ReportPath $report -MarkReviewGate 1 -ReviewResult passed
```

Expected: report contains `review_gate_1: passed`.

- [ ] **Step 4: Perform Review Gate 2 manually**

Open the generated report again. Verify:

- Tests cover command execution, report generation, dirty gate, review gate blocking, and built-in task listing.
- Failures include task ID, report path, command, and exit code.
- No hidden persistence is created outside `_runtime/stage_closeout/`.
- No duplicate business state is introduced.
- The next closeout task can be run separately.

If all checks pass, mark gate 2:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_stage_closeout.ps1 -ReportPath $report -MarkReviewGate 2 -ReviewResult passed
```

Expected: report contains `status: passed`.

- [ ] **Step 5: Commit final verification adjustments if any**

If any formatting or report wording changes were needed:

```powershell
git add scripts/run_stage_closeout.ps1 tests/test_stage_closeout_runner.py
git commit -m "fix: 完善收口运行器报告细节"
```

If no changes are needed, do not create an empty commit.

- [ ] **Step 6: Push**

Run:

```powershell
git push origin dev
```

Expected: push succeeds and `git rev-parse HEAD` matches `git rev-parse origin/dev`.
