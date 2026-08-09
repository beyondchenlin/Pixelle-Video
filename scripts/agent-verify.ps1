param(
    [switch]$AllowBaselineBranch,
    [switch]$AllowRiskyFiles,
    [string]$CommitMessageFile,
    [string]$BaselineBranch = 'main',
    [string]$DevBranch = 'dev',
    [string]$TaskPrefix = 'codex'
)

$ErrorActionPreference = 'Continue'
$failed = $false

function Fail($message) {
    Write-Host "[FAIL] $message" -ForegroundColor Red
    $script:failed = $true
}

function Pass($message) {
    Write-Host "[OK] $message" -ForegroundColor Green
}

function Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Cyan
}

function Get-AgentConfigValue($path, $key, $defaultValue) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        return $defaultValue
    }

    $lines = Get-Content -LiteralPath $path -Encoding UTF8
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#') -or $trimmed -notmatch '=') {
            continue
        }

        $parts = $trimmed -split '=', 2
        if ($parts[0].Trim() -eq $key) {
            return $parts[1].Trim()
        }
    }

    return $defaultValue
}

function Test-Enabled($value) {
    return ($value -in @('1', 'true', 'yes', 'on'))
}

function Test-TrackedOrStaged($path) {
    & git ls-files --error-unmatch $path *> $null
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    $staged = GitLines @('diff', '--cached', '--name-only', '--', $path)
    return ($staged.Count -gt 0)
}

function Test-AgentDoc($path, $required) {
    if (-not (Test-Enabled $required)) {
        return
    }

    if (-not (Test-Path -LiteralPath (Join-Path $repoRoot $path) -PathType Leaf)) {
        Fail "$path is missing. Run agent-operating-system bootstrap, or install the agent standards hook."
    } elseif (-not (Test-TrackedOrStaged $path)) {
        Fail "$path exists but is not tracked or staged."
    } else {
        Pass "$path exists"
    }
}

function GitLines($arguments) {
    $output = & git @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    return @($output | Where-Object { $_ -ne $null -and $_ -ne '' })
}

function Get-RuffCommand($root) {
    $candidates = @(
        (Join-Path $root '.venv/Scripts/ruff.exe'),
        (Join-Path $root '.venv/bin/ruff')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }

    $command = Get-Command ruff -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

$repoRoot = (& git rev-parse --show-toplevel 2>$null)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoRoot)) {
    throw 'Not inside a git repository.'
}
Set-Location $repoRoot

$configFile = Join-Path $repoRoot '.oceans/agent-standards.conf'
$BaselineBranch = Get-AgentConfigValue $configFile 'baseline_branch' $BaselineBranch
$DevBranch = Get-AgentConfigValue $configFile 'dev_branch' $DevBranch
$TaskPrefix = Get-AgentConfigValue $configFile 'task_prefix' $TaskPrefix
$requireAgents = Get-AgentConfigValue $configFile 'require_agents_md' '1'
$requireClaude = Get-AgentConfigValue $configFile 'require_claude_md' '0'
$commitMessagePolicy = Get-AgentConfigValue $configFile 'commit_message' 'conventional'
$commitTypes = @(
    (Get-AgentConfigValue $configFile 'commit_types' 'feat,fix,docs,style,refactor,perf,test,chore,build,ci,revert,merge') -split ',' |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne '' }
)
$commitTitleLanguage = Get-AgentConfigValue $configFile 'commit_title_language' 'zh'

$gitDir = (& git rev-parse --git-dir).Trim()
$isMergeInProgress = Test-Path -LiteralPath (Join-Path $gitDir 'MERGE_HEAD')

Info "Repository: $repoRoot"

$branch = (& git branch --show-current).Trim()
if ([string]::IsNullOrWhiteSpace($branch)) {
    Fail 'Detached HEAD is not allowed for normal agent work.'
} elseif ($BaselineBranch -ne $DevBranch -and $branch -eq $BaselineBranch -and -not ($AllowBaselineBranch -or $isMergeInProgress)) {
    Fail "Work is on $BaselineBranch. Use $DevBranch or a $TaskPrefix/<task-name> branch, or pass -AllowBaselineBranch for intentional baseline maintenance."
} elseif ($branch -eq $DevBranch) {
    Pass "Development branch policy: $branch"
} elseif ($branch -like "$TaskPrefix/*") {
    Pass "Agent task branch policy: $branch"
} else {
    Pass "Non-baseline repository branch: $branch"
}

$stagedFiles = GitLines @('diff', '--cached', '--name-only', '--diff-filter=ACMRD')
if ($stagedFiles.Count -eq 0) {
    Info 'No staged files found. Running format checks against working tree diff.'
} else {
    Pass "Staged files: $($stagedFiles.Count)"
}

$diffCheckArgs = if ($stagedFiles.Count -gt 0) { @('diff', '--check', '--cached') } else { @('diff', '--check') }
$diffCheck = & git @diffCheckArgs 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail "git diff --check failed:`n$($diffCheck -join [Environment]::NewLine)"
} else {
    Pass 'git diff --check'
}

$riskyPatterns = @(
    '(^|/)\.env($|[./])',
    '\.(pem|key|p12|pfx)$',
    '\.(zip|7z|rar)$',
    '(^|/)config\.ya?ml$',
    '(^|/)extra_models_config\.ya?ml$',
    '(^|/)data/cache/',
    '(^|/)data/template/',
    '(^|/)data/attachment/',
    '\.log$',
    '\.(safetensors|ckpt|gguf|pt|pth|onnx|bin|engine)$'
)

if ($stagedFiles.Count -gt 0 -and -not $AllowRiskyFiles) {
    $risky = @()
    foreach ($file in $stagedFiles) {
        $normalized = $file -replace '\\', '/'
        foreach ($pattern in $riskyPatterns) {
            if ($normalized -match $pattern) {
                $risky += $file
                break
            }
        }
    }
    if ($risky.Count -gt 0) {
        Fail "Risky staged files require explicit review:`n$($risky -join [Environment]::NewLine)"
    } else {
        Pass 'No risky staged files'
    }
}

Test-AgentDoc 'AGENTS.md' $requireAgents
Test-AgentDoc 'CLAUDE.md' $requireClaude
Test-AgentDoc 'docs/agent/prompting-workflow.md' '1'
if ((Test-Enabled $requireClaude) -and -not (Select-String -LiteralPath (Join-Path $repoRoot 'CLAUDE.md') -SimpleMatch 'AGENTS.md' -Quiet)) {
    Fail 'CLAUDE.md must point to root AGENTS.md instead of maintaining a drifting parallel rule set.'
}
if (-not (Select-String -LiteralPath (Join-Path $repoRoot 'AGENTS.md') -SimpleMatch 'docs/agent/prompting-workflow.md' -Quiet)) {
    Fail 'AGENTS.md must index docs/agent/prompting-workflow.md.'
}

$pythonFiles = @()
if ($stagedFiles.Count -gt 0) {
    $pythonFiles = @(
        $stagedFiles | Where-Object {
            $_ -match '\.py$' -and (Test-Path -LiteralPath $_ -PathType Leaf)
        }
    )
}

if ($pythonFiles.Count -gt 0) {
    $ruffCommand = Get-RuffCommand $repoRoot
    if (-not $ruffCommand) {
        Fail 'ruff is not installed. Run uv sync explicitly before committing; the hook will not create or update an environment.'
    } else {
        $lint = & $ruffCommand check --no-cache -- @pythonFiles 2>&1
        if ($LASTEXITCODE -ne 0) {
            Fail "ruff failed:`n$($lint -join [Environment]::NewLine)"
        } else {
            Pass "ruff checked $($pythonFiles.Count) staged Python file(s)"
        }
    }
} else {
    Info 'No staged Python files to lint.'
}

if ($CommitMessageFile -and $commitMessagePolicy -notin @('off', 'none')) {
    if (-not (Test-Path -LiteralPath $CommitMessageFile -PathType Leaf)) {
        Fail "Commit message file not found: $CommitMessageFile"
    } else {
        $firstLine = (Get-Content -LiteralPath $CommitMessageFile -Encoding UTF8 | Select-Object -First 1)
        $match = [regex]::Match($firstLine, '^(?<type>[a-z]+)(\([A-Za-z0-9._-]+\))?: (?<title>.+)$')
        if (-not $match.Success) {
            Fail "Commit message must use '<type>: <title>' or '<type>(scope): <title>'. Found: $firstLine"
        } elseif ($match.Groups['type'].Value -notin $commitTypes) {
            Fail "Commit type '$($match.Groups['type'].Value)' is not allowed. Allowed types: $($commitTypes -join ', ')"
        } elseif ($commitTitleLanguage -eq 'zh' -and $match.Groups['title'].Value -notmatch '[\u3400-\u4DBF\u4E00-\u9FFF]') {
            Fail "Commit title must contain Chinese text. Found: $firstLine"
        } else {
            Pass 'Commit message format'
        }
    }
}

if ($failed) {
    exit 1
}

Pass 'agent verification passed'
