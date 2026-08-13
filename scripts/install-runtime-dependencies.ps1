$ErrorActionPreference = 'Stop'

function Fail($message) {
    throw $message
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$bridgeRoot = Join-Path $repoRoot 'tools\hyperframes_bridge'

foreach ($requiredPath in @(
    (Join-Path $repoRoot 'uv.lock'),
    (Join-Path $bridgeRoot 'package-lock.json')
)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        Fail "Required lock file not found: $requiredPath"
    }
}

foreach ($commandName in @('uv', 'node', 'npm')) {
    if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) {
        Fail "Required command not found: $commandName"
    }
}

$nodeVersion = (& node --version).Trim()
if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)$') {
    Fail "Unable to determine Node.js version: $nodeVersion"
}
if ([int]$Matches.major -lt 22 -or ([int]$Matches.major -eq 22 -and [int]$Matches.minor -lt 12)) {
    Fail "Node.js 22.12.0 or newer is required; found $nodeVersion"
}

$managedEnvironment = @(
    'PUPPETEER_CACHE_DIR',
    'PUPPETEER_SKIP_DOWNLOAD',
    'PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD',
    'PUPPETEER_EXECUTABLE_PATH',
    'PRODUCER_HEADLESS_SHELL_PATH',
    'PIXELLE_REQUIRE_PINNED_BROWSER'
)
$previousEnvironment = @{}
foreach ($variableName in $managedEnvironment) {
    $previousEnvironment[$variableName] = [Environment]::GetEnvironmentVariable(
        $variableName,
        'Process'
    )
}
try {
    $env:PUPPETEER_CACHE_DIR = Join-Path $bridgeRoot '.cache\puppeteer'
    $env:PUPPETEER_SKIP_DOWNLOAD = 'true'
    $env:PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD = 'true'
    $env:PIXELLE_REQUIRE_PINNED_BROWSER = 'true'
    [Environment]::SetEnvironmentVariable('PUPPETEER_EXECUTABLE_PATH', $null, 'Process')
    [Environment]::SetEnvironmentVariable('PRODUCER_HEADLESS_SHELL_PATH', $null, 'Process')

    Push-Location $repoRoot
    try {
        & uv sync --frozen
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        & npm ci --omit=dev --prefix $bridgeRoot
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        Push-Location $bridgeRoot
        try {
            & npm run browser:install
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            & npm run runtime:verify
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    foreach ($variableName in $managedEnvironment) {
        [Environment]::SetEnvironmentVariable(
            $variableName,
            $previousEnvironment[$variableName],
            'Process'
        )
    }
}

Write-Host '[OK] Runtime dependencies installed and HyperFrames bridge verified.' -ForegroundColor Green
