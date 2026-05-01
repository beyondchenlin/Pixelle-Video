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
    $updated = $content -replace "(?m)^${field}:\s*\w+", "${field}: $Result"
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

$ResolvedRepoRoot = Resolve-RepoRoot $RepoRoot

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
Write-RunnerLine "task: $($Task.id)"
$Results = New-Object System.Collections.Generic.List[object]
foreach ($command in @($Task.verification_commands)) {
    $result = Invoke-VerificationCommand $ResolvedRepoRoot ([string]$command)
    $Results.Add($result)
    if ($result.ExitCode -ne 0) {
        $report = New-CloseoutReport -Root $ResolvedRepoRoot -Task $Task -Results @($Results.ToArray()) -Status "verification_failed"
        Write-RunnerLine "status: verification_failed"
        Write-RunnerLine "report: $report"
        exit 1
    }
}

$reportPath = New-CloseoutReport -Root $ResolvedRepoRoot -Task $Task -Results @($Results.ToArray()) -Status "needs_review"
Write-RunnerLine "status: needs_review"
Write-RunnerLine "report: $reportPath"
exit 0
