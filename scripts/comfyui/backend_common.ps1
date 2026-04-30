Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-PixelleRepoRoot {
    return (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
}

function Resolve-BackendValue {
    param(
        [string]$Provided,
        [string]$EnvironmentName,
        [string]$Default
    )

    if ($Provided -and $Provided.Trim()) {
        return $Provided
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue -and $environmentValue.Trim()) {
        return $environmentValue
    }

    return $Default
}

function Resolve-BackendInt {
    param(
        [int]$Provided,
        [string]$EnvironmentName,
        [int]$Default
    )

    if ($Provided -gt 0) {
        return $Provided
    }

    $environmentValue = [Environment]::GetEnvironmentVariable($EnvironmentName)
    if ($environmentValue -and $environmentValue.Trim()) {
        return [int]$environmentValue
    }

    return $Default
}

function ConvertTo-SqliteUrl {
    param([string]$DatabasePath)
    return "sqlite:///$($DatabasePath -replace '\\', '/')"
}

function Resolve-PixelleComfyUIBackendConfig {
    param(
        [string]$PythonExe,
        [string]$ComfyUIRoot,
        [string]$DataRoot,
        [string]$ExtraModelsConfig,
        [string]$FrontEndRoot,
        [string]$DatabaseUrl,
        [string]$RuntimeDir,
        [string]$LogsDir,
        [string]$HostAddress,
        [int]$Port
    )

    $repoRoot = Get-PixelleRepoRoot
    $resolvedDataRoot = Resolve-BackendValue $DataRoot 'PIXELLE_COMFYUI_DATA_ROOT' 'E:\ComfyUIData'
    $resolvedComfyUIRoot = Resolve-BackendValue $ComfyUIRoot 'PIXELLE_COMFYUI_ROOT' 'E:\comfyui\resources\ComfyUI'
    $defaultFrontEndRoot = Join-Path $resolvedComfyUIRoot 'web_custom_versions\desktop_app'
    $defaultDatabaseUrl = ConvertTo-SqliteUrl (Join-Path $resolvedDataRoot 'user\comfyui.db')

    return [ordered]@{
        RepoRoot = $repoRoot
        PythonExe = Resolve-BackendValue $PythonExe 'PIXELLE_COMFYUI_PYTHON' (Join-Path $resolvedDataRoot '.venv\Scripts\python.exe')
        ComfyUIRoot = $resolvedComfyUIRoot
        DataRoot = $resolvedDataRoot
        ExtraModelsConfig = Resolve-BackendValue $ExtraModelsConfig 'PIXELLE_COMFYUI_EXTRA_MODELS_CONFIG' (Join-Path $env:APPDATA 'ComfyUI\extra_models_config.yaml')
        FrontEndRoot = Resolve-BackendValue $FrontEndRoot 'PIXELLE_COMFYUI_FRONTEND_ROOT' $defaultFrontEndRoot
        DatabaseUrl = Resolve-BackendValue $DatabaseUrl 'PIXELLE_COMFYUI_DATABASE_URL' $defaultDatabaseUrl
        RuntimeDir = Resolve-BackendValue $RuntimeDir 'PIXELLE_COMFYUI_RUNTIME_DIR' (Join-Path $repoRoot '_runtime\comfyui')
        LogsDir = Resolve-BackendValue $LogsDir 'PIXELLE_COMFYUI_LOGS_DIR' (Join-Path $repoRoot 'logs\comfyui')
        HostAddress = Resolve-BackendValue $HostAddress 'PIXELLE_COMFYUI_HOST' '127.0.0.1'
        Port = Resolve-BackendInt $Port 'PIXELLE_COMFYUI_PORT' 8000
    }
}

function Get-BackendPidFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.pid')
}

function Get-BackendLauncherPidFile {
    param([hashtable]$Config)
    return (Join-Path $Config.RuntimeDir 'comfyui-backend.launcher.pid')
}

function Get-BackendStdoutLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stdout.log')
}

function Get-BackendStderrLog {
    param([hashtable]$Config)
    return (Join-Path $Config.LogsDir 'comfyui-backend.stderr.log')
}

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Assert-BackendPrerequisites {
    param([hashtable]$Config)

    $mainPy = Join-Path $Config.ComfyUIRoot 'main.py'
    $inputDir = Join-Path $Config.DataRoot 'input'
    $outputDir = Join-Path $Config.DataRoot 'output'
    $userDir = Join-Path $Config.DataRoot 'user'

    if (-not (Test-Path -LiteralPath $Config.PythonExe -PathType Leaf)) {
        throw "ComfyUI Python executable does not exist: $($Config.PythonExe)"
    }
    if (-not (Test-Path -LiteralPath $mainPy -PathType Leaf)) {
        throw "ComfyUI main.py does not exist: $mainPy"
    }
    foreach ($directory in @($inputDir, $outputDir, $userDir)) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
            throw "ComfyUI data directory does not exist: $directory"
        }
    }
    if ($Config.ExtraModelsConfig -and -not (Test-Path -LiteralPath $Config.ExtraModelsConfig -PathType Leaf)) {
        throw "ComfyUI extra models config does not exist: $($Config.ExtraModelsConfig)"
    }
    if ($Config.FrontEndRoot -and -not (Test-Path -LiteralPath $Config.FrontEndRoot -PathType Container)) {
        throw "ComfyUI front-end root does not exist: $($Config.FrontEndRoot)"
    }
    if (-not $Config.DatabaseUrl.StartsWith('sqlite:///')) {
        throw "ComfyUI database URL must use sqlite:///: $($Config.DatabaseUrl)"
    }
}

function Get-BackendArguments {
    param([hashtable]$Config)

    $arguments = New-Object System.Collections.Generic.List[string]
    [void]$arguments.Add((Join-Path $Config.ComfyUIRoot 'main.py'))
    [void]$arguments.Add('--user-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'user'))
    [void]$arguments.Add('--input-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'input'))
    [void]$arguments.Add('--output-directory')
    [void]$arguments.Add((Join-Path $Config.DataRoot 'output'))
    if ($Config.FrontEndRoot) {
        [void]$arguments.Add('--front-end-root')
        [void]$arguments.Add($Config.FrontEndRoot)
    }
    [void]$arguments.Add('--base-directory')
    [void]$arguments.Add($Config.DataRoot)
    [void]$arguments.Add('--database-url')
    [void]$arguments.Add($Config.DatabaseUrl)

    if ($Config.ExtraModelsConfig) {
        [void]$arguments.Add('--extra-model-paths-config')
        [void]$arguments.Add($Config.ExtraModelsConfig)
    }

    [void]$arguments.Add('--listen')
    [void]$arguments.Add($Config.HostAddress)
    [void]$arguments.Add('--port')
    [void]$arguments.Add([string]$Config.Port)

    return [string[]]$arguments.ToArray()
}

function Get-BackendListener {
    param([hashtable]$Config)

    $hostAddress = [string]$Config.HostAddress
    return Get-NetTCPConnection `
        -LocalPort $Config.Port `
        -ErrorAction SilentlyContinue |
        Where-Object {
            $_.State -eq 'Listen' -and (
                $_.LocalAddress -eq $hostAddress -or
                $_.LocalAddress -eq '0.0.0.0' -or
                $_.LocalAddress -eq '::' -or
                $hostAddress -eq '0.0.0.0' -or
                $hostAddress -eq '::'
            )
        } |
        Select-Object -First 1
}

function Get-ProcessInfo {
    param([int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Test-ManagedComfyUIProcess {
    param(
        [hashtable]$Config,
        [int]$ProcessId
    )

    $processInfo = Get-ProcessInfo $ProcessId
    if (-not $processInfo) {
        return $false
    }

    $commandLine = [string]$processInfo.CommandLine
    $mainPy = Join-Path $Config.ComfyUIRoot 'main.py'
    return ($commandLine -like "*$mainPy*" -and $commandLine -like "*--base-directory*" -and $commandLine -like "*$($Config.DataRoot)*")
}

function Stop-ManagedComfyUIProcess {
    param(
        [hashtable]$Config,
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return $false
    }
    if (-not (Test-ManagedComfyUIProcess $Config $ProcessId)) {
        return $false
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    return $true
}

function Stop-ManagedComfyUIProcessesForConfig {
    param([hashtable]$Config)

    $mainPy = Join-Path $Config.ComfyUIRoot 'main.py'
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $commandLine = [string]$_.CommandLine
            $commandLine -like "*$mainPy*" -and
            $commandLine -like "*--base-directory*" -and
            $commandLine -like "*$($Config.DataRoot)*"
        } |
        ForEach-Object {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Remove-BackendPidFiles {
    param([hashtable]$Config)

    foreach ($path in @((Get-BackendPidFile $Config), (Get-BackendLauncherPidFile $Config))) {
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Read-BackendPid {
    param([hashtable]$Config)

    $pidFile = Get-BackendPidFile $Config
    return Read-BackendPidFromFile $pidFile
}

function Read-BackendLauncherPid {
    param([hashtable]$Config)

    $pidFile = Get-BackendLauncherPidFile $Config
    return Read-BackendPidFromFile $pidFile
}

function Read-BackendPidFromFile {
    param([string]$PidFile)

    if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
        return $null
    }

    $rawPid = (Get-Content -LiteralPath $pidFile -Raw).Trim()
    if (-not $rawPid) {
        return $null
    }

    $parsedPid = 0
    if (-not [int]::TryParse($rawPid, [ref]$parsedPid)) {
        return $null
    }

    return $parsedPid
}

function Write-BackendJson {
    param([object]$Payload)
    $Payload | ConvertTo-Json -Depth 12 -Compress
}

function Write-BackendMessage {
    param(
        [switch]$Json,
        [object]$Payload,
        [string]$Message
    )

    if ($Json) {
        Write-BackendJson $Payload
    }
    else {
        Write-Output $Message
    }
}
