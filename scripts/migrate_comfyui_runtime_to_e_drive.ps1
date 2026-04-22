param(
    [string]$TargetBasePath = 'E:\comfyui-venv',
    [string]$ConfigPath = "$env:APPDATA\ComfyUI\config.json",
    [string]$OldBasePath = "$env:USERPROFILE\Documents\ComfyUI",
    [string]$PythonExe = '',
    [switch]$Apply,
    [switch]$RemoveOldVenv,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info {
    param([string]$Message)
    Write-Host "[INFO] $Message"
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        if ($WhatIf) {
            Write-Info "Would create directory: $Path"
        }
        else {
            New-Item -ItemType Directory -Path $Path -Force | Out-Null
            Write-Info "Created directory: $Path"
        }
    }
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "ComfyUI Desktop config not found: $ConfigPath"
}

$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$currentBasePath = [string]$config.basePath
$targetVenvPath = Join-Path $TargetBasePath '.venv'
$targetPythonPath = Join-Path $targetVenvPath 'Scripts\python.exe'
$oldVenvPath = Join-Path $OldBasePath '.venv'

Write-Info "Current ComfyUI Desktop basePath: $currentBasePath"
Write-Info "Target ComfyUI Desktop basePath:  $TargetBasePath"

Ensure-Directory $TargetBasePath
foreach ($directoryName in @('input', 'output', 'user', 'custom_nodes')) {
    Ensure-Directory (Join-Path $TargetBasePath $directoryName)
}

if ($PythonExe) {
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        throw "Specified Python executable does not exist: $PythonExe"
    }

    if (-not (Test-Path -LiteralPath $targetPythonPath)) {
        if ($WhatIf) {
            Write-Info "Would create virtual environment: $targetVenvPath"
        }
        else {
            & $PythonExe -m venv $targetVenvPath
            Write-Info "Created virtual environment: $targetVenvPath"
        }
    }
    else {
        Write-Info "Target virtual environment already exists: $targetVenvPath"
    }
}
elseif (-not (Test-Path -LiteralPath $targetPythonPath)) {
    Write-Warning "Target runtime venv does not exist yet. Pass -PythonExe <official-python.exe> to create it."
}

if ($Apply) {
    $config.basePath = $TargetBasePath
    $updatedJson = $config | ConvertTo-Json -Depth 8

    if ($WhatIf) {
        Write-Info "Would update basePath in: $ConfigPath"
    }
    else {
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($ConfigPath, $updatedJson, $utf8NoBom)
        Write-Info "Updated ComfyUI Desktop basePath in: $ConfigPath"
    }
}
else {
    Write-Info "Dry configuration mode: basePath not changed. Use -Apply to write config."
}

$basePathAfterRun = if ($Apply) { $TargetBasePath } else { $currentBasePath }
Write-Info "Effective basePath after this run: $basePathAfterRun"

if ($RemoveOldVenv) {
    if ($basePathAfterRun -ne $TargetBasePath) {
        throw "Refusing to remove old venv before basePath is switched to $TargetBasePath."
    }
    if (-not (Test-Path -LiteralPath $targetPythonPath)) {
        throw "Refusing to remove old venv because target runtime python is missing: $targetPythonPath"
    }
    if (-not (Test-Path -LiteralPath $oldVenvPath)) {
        Write-Info "Old runtime venv already absent: $oldVenvPath"
    }
    elseif ($WhatIf) {
        Write-Info "Would remove old runtime venv: $oldVenvPath"
    }
    else {
        Remove-Item -LiteralPath $oldVenvPath -Recurse -Force
        Write-Info "Removed old runtime venv: $oldVenvPath"
    }
}

Write-Host ''
Write-Host 'Next checks:' -ForegroundColor Cyan
Write-Host "1. Confirm ComfyUI Desktop config points to: $TargetBasePath"
Write-Host "2. Confirm runtime python exists at: $targetPythonPath"
Write-Host "3. Keep models under E:\comfyui\comfyui\models unchanged."
Write-Host "4. Install DeepSpeed prerequisites into the new runtime only after the new venv is healthy."
