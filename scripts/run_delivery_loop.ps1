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
                id = "global-lint"
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

if ($StartFeatureDelivery) {
    Write-RunnerLine "feature delivery checkpoint is not implemented yet"
    exit 3
}

Write-RunnerLine "no delivery loop action was requested"
exit 3
