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
