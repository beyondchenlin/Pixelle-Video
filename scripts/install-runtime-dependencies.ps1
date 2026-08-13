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

$previousBrowserCache = $env:PUPPETEER_CACHE_DIR
$previousSkipDownload = $env:PUPPETEER_SKIP_DOWNLOAD
$previousSkipHeadlessShell = $env:PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD
try {
    $env:PUPPETEER_CACHE_DIR = Join-Path $bridgeRoot '.cache\puppeteer'
    $env:PUPPETEER_SKIP_DOWNLOAD = 'true'
    $env:PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD = 'true'

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
            & node .\node_modules\puppeteer\lib\puppeteer\node\cli.js browsers install chrome
            if ($LASTEXITCODE -ne 0) {
                exit $LASTEXITCODE
            }
            & node --input-type=module -e "const bridge = await import('./src/render.mjs'); await bridge.resolveBrowserExecutable();"
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
    if ($null -eq $previousBrowserCache) {
        Remove-Item Env:PUPPETEER_CACHE_DIR -ErrorAction SilentlyContinue
    }
    else {
        $env:PUPPETEER_CACHE_DIR = $previousBrowserCache
    }
    if ($null -eq $previousSkipDownload) {
        Remove-Item Env:PUPPETEER_SKIP_DOWNLOAD -ErrorAction SilentlyContinue
    }
    else {
        $env:PUPPETEER_SKIP_DOWNLOAD = $previousSkipDownload
    }
    if ($null -eq $previousSkipHeadlessShell) {
        Remove-Item Env:PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD -ErrorAction SilentlyContinue
    }
    else {
        $env:PUPPETEER_SKIP_CHROME_HEADLESS_SHELL_DOWNLOAD = $previousSkipHeadlessShell
    }
}

Write-Host '[OK] Runtime dependencies installed and HyperFrames bridge verified.' -ForegroundColor Green
