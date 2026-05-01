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
